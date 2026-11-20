"""Dated pitcher labels from cited editions of the published league Team Board."""
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import selectinload

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.roster_status_snapshot import RosterStatusSnapshot
from models.share_artifact import ShareArtifact, LIFECYCLE_PUBLISHED
from services.dashboard_snapshot import SNAPSHOT_TYPE_BULLPEN_DASHBOARD
from services.pitcher_public_labels import READ_PUBLIC_LABELS, ROLE_PUBLIC_LABELS
from services.public_serving_authority import TEAM_BOARD_PACKAGE_KEY
from services.share_artifact_public import share_route
from services.share_artifacts import ShareArtifactIntegrityError, verify_share_artifact_integrity
from services.team_board_what_changed import frozen_board_reads
from services.team_board_snapshot_team_state import receipt_value, receipt_availability_method
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from utils.db import db


def _labels(snapshot, team, team_id, pitcher_id):
    reads = frozen_board_reads(snapshot, team_id, team, include_limited=True)
    if reads is None or pitcher_id not in reads:
        return None
    record = next(r for r in team['records'] if r['pitcher_id'] == pitcher_id)
    role = record.get('public_role_read') or {}
    role_label = ROLE_PUBLIC_LABELS.get(role.get('key'), {}).get('label')
    read = reads[pitcher_id]
    return {
        'role': role_label if role_label == role.get('label') else None,
        'read': READ_PUBLIC_LABELS[read[0]]['label'] if read else None,
    }


def _club_editions(pitcher_id, team_id, start, end):
    artifacts = ShareArtifact.query.options(selectinload(ShareArtifact.evidence)).filter_by(
        artifact_type=TEAM_STATE_ARTIFACT_TYPE, lifecycle_state=LIFECYCLE_PUBLISHED, team_id=team_id,
    ).filter(ShareArtifact.product_date.between(start, end)).order_by(
        ShareArtifact.product_date.desc(), ShareArtifact.published_at.desc(), ShareArtifact.id.desc(),
    ).all()
    editions = {}
    for artifact in artifacts:
        editions.setdefault(artifact.product_date, artifact)
    league = {a.source_snapshot_id: a for a in editions.values()
              if a.subject_type is None and a.published_at}
    if not league:
        return {}
    body = DashboardSnapshot.payload
    path = (TEAM_BOARD_PACKAGE_KEY, 'by_team_id', str(team_id))
    fields = ('team', 'default_pitcher_ids', 'records', 'bullpen_membership_authority',
              'arm_read_method', 'roster_authority', 'frozen_team_state')
    rows = db.session.query(
        DashboardSnapshot.id, DashboardSnapshot.data_through, DashboardSnapshot.availability_reference_date,
        DashboardSnapshot.sync_run_id, body['freshness'], body[(TEAM_BOARD_PACKAGE_KEY, 'contract')],
        body[(TEAM_BOARD_PACKAGE_KEY, 'data_through')], body[(TEAM_BOARD_PACKAGE_KEY, 'availability_reference_date')],
        body[(TEAM_BOARD_PACKAGE_KEY, 'frozen_team_state_by_team_id')],
        *(body[path + (field,)] for field in fields),
    ).filter(DashboardSnapshot.id.in_(league), DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
             DashboardSnapshot.status == 'ready', DashboardSnapshot.published_at.isnot(None))
    results = {}
    for snapshot_id, day, reference, run_id, freshness, contract, through, availability, state_receipts, *values in rows:
        artifact = league[snapshot_id]
        if (day != artifact.product_date or run_id is None
                or artifact.source_sync_run_id not in (None, run_id)):
            continue
        try:
            verify_share_artifact_integrity(artifact)
        except ShareArtifactIntegrityError:
            continue
        team = dict(zip(fields, values))
        snapshot = SimpleNamespace(id=snapshot_id, data_through=day, availability_reference_date=reference,
            payload={'freshness': freshness, TEAM_BOARD_PACKAGE_KEY: {
                'contract': contract, 'data_through': through, 'availability_reference_date': availability,
                'by_team_id': {str(team_id): team}}})
        if isinstance(state_receipts, dict):
            snapshot.payload[TEAM_BOARD_PACKAGE_KEY]['frozen_team_state_by_team_id'] = state_receipts
        present, state = receipt_value(snapshot, team_id)
        if not present or state.get('available') is not True:
            continue
        labels = _labels(snapshot, team, team_id, pitcher_id)
        if labels and any(labels.values()):
            results[day] = {**labels, 'team_id': team_id, 'team': (team['team'].get('team_abbreviation') or str(team_id)),
                            'method': receipt_availability_method(snapshot, team_id),
                            'snapshot_id': snapshot_id, 'citation': share_route(artifact.public_id),
                            'reference_date': reference.isoformat()}
    return results


def pitcher_publication_history(pitcher, end):
    """Read one week plus the preceding comparison day. Never bridge publication gaps."""
    prior = end - timedelta(days=7)
    team_ids = {team for team, in db.session.query(GameLog.appearance_team_id).filter(
        GameLog.pitcher_id == pitcher.id, GameLog.game_date.between(prior.replace(month=1, day=1), end),
        GameLog.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED,
    ).distinct()}
    # Roster dates also find a former club where the pitcher never entered a game.
    team_ids.update(team for team, in db.session.query(RosterStatusSnapshot.team_id).filter(
        RosterStatusSnapshot.pitcher_id == pitcher.id,
        RosterStatusSnapshot.snapshot_date.between(prior, end + timedelta(days=1)),
    ).distinct())
    if pitcher.team_id:
        team_ids.add(pitcher.team_id)
    clubs = [_club_editions(pitcher.id, team_id, prior, end) for team_id in sorted(team_ids)]
    result = []
    previous = None
    for offset in range(8):
        day = prior + timedelta(days=offset)
        matches = [club[day] for club in clubs if day in club]
        entry = matches[0] if len(matches) == 1 else None
        changes = {}
        if entry and previous and entry['team_id'] == previous['team_id'] and (
            date.fromisoformat(entry['reference_date']) - date.fromisoformat(previous['reference_date']) == timedelta(days=1)
        ):
            for field in ('role', 'read'):
                if field == 'read' and (not entry['method'] or entry['method'] != previous['method']):
                    continue
                if entry[field] and previous[field] and entry[field] != previous[field]:
                    changes[field] = {'from': previous[field], 'citation': previous['citation']}
        if offset:
            result.append({'date': day.isoformat(), 'edition': entry, 'changes': changes})
        previous = entry
    return {'pitcher_id': pitcher.id, 'through': end.isoformat(), 'days': result[::-1]}
