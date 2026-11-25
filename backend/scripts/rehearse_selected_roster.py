"""Rehearse a dated off-active roster observation in the socket-only publication handoff."""
from types import SimpleNamespace

from sqlalchemy import text

from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.source_observation import SourceObservation, SourceSubject
from services.mlb_api import MLBApiClient
from services.primary_roster_inputs import replay_membership
from services.roster_status_sync import build_exact_date_team_roster_status_index, persist_missing_exact_roster_status_snapshots
from sync_v3.discovery import roster_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.product_reads import _public_arms
from utils.db import db


class CapturedRoster:
    get_team_roster = MLBApiClient.get_team_roster

    def __init__(self, team, day, bodies):
        self.team = team
        self.day = day
        self.bodies = bodies

    def _get(self, endpoint, params):
        kind = params['rosterType']
        if endpoint != f'/teams/{self.team}/roster' or params != dict(rosterType=kind, date=str(self.day)):
            raise ValueError('Unexpected retained roster request')
        return self.bodies[kind]


def matched_departure_evidence(team, mlb, day, bodies, observations):
    client = CapturedRoster(team, day, bodies)
    for kind, row in observations.items():
        if client.get_team_roster(team, roster_type=kind, date=str(day)) != row.payload_artifact.payload_json['records']:
            raise ValueError(f'Target and retained {kind} roster contents differ')
    links = dict(active_roster_observation_id=observations['active'].id,
                 forty_man_roster_observation_id=observations['40Man'].id)
    companion = observations['active'].payload_artifact.payload_json.get('companion_observations')
    if companion != {k: r.id for k, r in observations.items() if k != 'active'}:
        raise ValueError('The four target observations do not belong to the same roster capture')
    # Verify the primary ledger's authority, completeness, date and payload hashes.
    if replay_membership(SimpleNamespace(team_id=team, mlb_id=mlb, snapshot_date=day, **links)) != (False, True):
        raise ValueError('Exact inputs must support off-active and continuing forty-man membership')
    index, errors = build_exact_date_team_roster_status_index(team, day, client=client)
    if errors or mlb not in index:
        raise ValueError('Dated target roster classification is incomplete')
    return index[mlb], links


def prepare_departure(cur, generation, day, team, mlb):
    before, _ = _public_arms(cur, generation)
    after, after_status = _public_arms(cur, generation, board_date=True)
    player = before.get(mlb)
    if not player or player['team_id'] != team or not player['public_id'] or after_status != 'mapped' or mlb in after:
        raise ValueError('Expected a mapped workload arm absent from the selected availability population')
    # A primary roster acquisition serializes new versions on its subject. Hold
    # the target source/roster inventory fixed until this disposable handoff ends.
    db.session.execute(text('LOCK TABLE source_subjects, source_observations, roster_status_snapshots '
                            'IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
    target = db.session.query(Pitcher).filter_by(id=player['public_id'], mlb_id=mlb).with_for_update(
        read=True, nowait=True).one()
    bodies, receipts, observations = {}, {}, {}
    for request in roster_requests(day, [team]):
        kind = request.params()['rosterType']
        source = latest_qualified_source(cur, request.endpoint, request.params())
        if source is None:
            raise ValueError(f'Missing qualified {kind} observation')
        if kind == 'active':
            cur.execute("""SELECT 1 FROM candidate.generation_inputs g
                           JOIN candidate.workload_history_sources h ON h.snapshot=g.snapshot
                           WHERE g.generation=%s AND h.source_id=%s LIMIT 1""", (generation, source))
            if cur.fetchone() is None:
                raise ValueError('Selected availability roster differs from the latest acquisition')
        acquired = replay(cur, source)
        bodies[kind] = acquired.body
        subjects = SourceSubject.query.filter_by(
            subject_key=f'primary:{team}:{kind}', baseball_date=day, provider='mlb_stats_api',
            source_domain='roster', subject_type='team', endpoint=request.endpoint
        ).all()
        matches = [subject for subject in subjects if subject.request_parameters == request.params()]
        if len(matches) != 1:
            raise ValueError(f'Missing or ambiguous original target {kind} request')
        row = (SourceObservation.query.filter_by(source_subject_id=matches[0].id)
               .order_by(SourceObservation.version_number.desc()).first())
        if row is None or row.payload_artifact is None or not row.is_authoritative or row.completeness != 'complete':
            raise ValueError(f'Missing authoritative target {kind} observation')
        observations[kind] = row
        receipts[kind] = dict(acquisition=source, observation=row.id, fingerprint=row.fingerprint)

    evidence, links = matched_departure_evidence(team, mlb, day, bodies, observations)
    return (dict(team=team, mlb=mlb, day=str(day), views=receipts),
            dict(pitcher=target, team_id=team, snapshot_date=day, evidence=evidence, observation_links=links))


def reconcile_departure(candidate, run_id, *, verify_only=False):
    from services.roster_status_sync import classify_roster_evidence

    key = dict(pitcher_id=candidate['pitcher'].id, snapshot_date=candidate['snapshot_date'])
    row = RosterStatusSnapshot.query.filter_by(**key).one_or_none()
    if row is None:
        if verify_only:
            raise ValueError('The attributed roster snapshot is missing on retry')
        timestamp = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        report = persist_missing_exact_roster_status_snapshots([candidate], timestamp=timestamp, sync_run_id=run_id)
        if report['conflicts'] or report['created'] != 1:
            raise ValueError('Roster writer refused the exact-date observation')
        row = RosterStatusSnapshot.query.filter_by(**key).one()
        if row.sync_run_id != run_id:
            raise ValueError('The new roster snapshot lacks its originating sync run')
    classification = classify_roster_evidence(candidate['evidence'])
    if (row.team_id != candidate['team_id'] or row.mlb_id != candidate['pitcher'].mlb_id or row.first_seen_at is None or row.sync_run_id is None
            or row.roster_status != classification['status'] or row.source != classification['source']
            or any(getattr(row, k) != v for k, v in candidate['observation_links'].items())
            or (row.active_roster, row.forty_man_roster) != (False, True) or replay_membership(row) != (False, True)):
        raise ValueError('The attributed roster snapshot differs from its dated source evidence')
