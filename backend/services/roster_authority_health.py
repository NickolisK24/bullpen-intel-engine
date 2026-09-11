"""Read-only current SP-05 roster-authority coverage reporting."""

from __future__ import annotations

from datetime import date, datetime

from models.roster_membership import RosterMembershipInterval
from models.source_observation import (
    SourceFetchAttempt,
    SourceObservation,
    SourceSubject,
    SourcePayloadArtifact,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_authority_scope import classify_roster_team
from services.roster_transaction_authority import _pitcher_entries
from models.sync_run import SyncRun, SyncRunScope
from utils.db import db
from utils.time import utc_now_naive


EXPECTED_MLB_TEAMS = 30
ROSTER_TYPES = ('active', '40Man')


def latest_shadow_morning_run(baseball_date):
    return (
        SyncRun.query
        .filter_by(
            source='sp12_morning_shadow',
            baseball_date=baseball_date,
        )
        .order_by(SyncRun.id.desc())
        .first()
    )


def expected_team_ids_from_run(run):
    if run is None:
        return ()
    values = {
        int(row.scope_key)
        for row in SyncRunScope.query.filter_by(
            sync_run_id=run.id,
            scope_type='team',
        ).all()
    }
    return tuple(sorted(values))


def roster_authority_coverage(
    baseball_date: date,
    *,
    expected_team_ids=None,
    now: datetime | None = None,
):
    """Return exact, read-only active/40-man evidence for one baseball date."""
    now = now or utc_now_naive()
    current_intervals = RosterMembershipInterval.query.filter_by(
        is_current_version=True, is_void=False,
    ).all()
    boundary_ids = {
        value for row in current_intervals
        for value in (row.opened_by_observation_id, row.closed_by_observation_id)
        if value is not None
    }
    retained = db.session.query(SourceObservation, SourceSubject, SourcePayloadArtifact).join(
        SourceSubject, SourceSubject.id == SourceObservation.source_subject_id,
    ).outerjoin(SourcePayloadArtifact, SourcePayloadArtifact.id == SourceObservation.payload_artifact_id).filter(
        SourceSubject.source_domain == 'roster',
        db.or_(SourceSubject.baseball_date == baseball_date, SourceObservation.id.in_(boundary_ids)),
    ).all()
    scope_cache = {}
    for observation, subject, artifact in retained:
        params = subject.request_parameters or {}
        records = (artifact.payload_json or {}).get('records') if artifact else None
        owner = None
        if (isinstance(records, list) and len(records) == observation.record_count
                and subject.provider == 'mlb_stats_api' and params.get('teamId') is not None
                and subject.subject_key == f"{params['teamId']}:{params.get('rosterType')}"):
            owner = classify_roster_team(params['teamId'], records=records)
        scope_cache[observation.id] = (owner, subject, records or [])

    def observation_scope(observation):
        return scope_cache.get(observation.id, (None, None, [])) if observation else (None, None, [])
    morning_run = latest_shadow_morning_run(baseball_date)
    expected = tuple(sorted({
        int(value)
        for value in (
            expected_team_ids
            if expected_team_ids is not None
            else MLB_TEAM_IDS
        )
    }))
    teams = []
    complete_active = []
    complete_forty_man = []
    partial = []
    failed = []
    stale = []
    missing = []
    suspicious_empty = []

    for team_id in expected:
        evidence = {}
        for roster_type in ROSTER_TYPES:
            subject = (
                SourceSubject.query
                .filter_by(
                    source_domain='roster',
                    subject_type='team',
                    subject_key=f'{team_id}:{roster_type}',
                    baseball_date=baseball_date,
                )
                .order_by(SourceSubject.id.desc())
                .first()
            )
            attempt = None
            observation = None
            if subject is not None:
                attempt = (
                    SourceFetchAttempt.query
                    .filter_by(source_subject_id=subject.id)
                    .order_by(SourceFetchAttempt.completed_at.desc(), SourceFetchAttempt.id.desc())
                    .first()
                )
                if attempt is not None and attempt.source_observation_id is not None:
                    observation = db.session.get(
                        SourceObservation, attempt.source_observation_id,
                    )
            authoritative_observation = (
                SourceObservation.query.filter_by(
                    source_subject_id=subject.id, is_authoritative=True, completeness='complete',
                ).order_by(SourceObservation.id.desc()).first() if subject else None
            )
            source_members = set()
            source_scope_valid = False
            if authoritative_observation is not None:
                ownership, represented, records = observation_scope(authoritative_observation)
                source_scope_valid = bool(ownership and ownership['mlb_membership_authority']
                                          and ownership['requested_team_id'] == team_id)
                source_members = set(_pitcher_entries(records))
            membership_type = 'active_roster' if roster_type == 'active' else 'forty_man_roster'
            intervals = RosterMembershipInterval.query.filter_by(
                team_id=team_id, membership_type=membership_type,
                effective_end_date=None, is_current_version=True, is_void=False,
            ).all()
            canonical_members = {row.player_mlb_id for row in intervals}
            authority_mismatches = []
            for interval in intervals:
                opening = db.session.get(SourceObservation, interval.opened_by_observation_id)
                owner, represented, _ = observation_scope(opening)
                if (not owner or not owner['mlb_membership_authority']
                        or owner['requested_team_id'] != team_id
                        or (represented.request_parameters or {}).get('rosterType') != roster_type
                        or interval.organization_id != team_id):
                    authority_mismatches.append(interval.id)
            exact_match = bool(source_scope_valid and source_members == canonical_members
                               and not authority_mismatches and len(intervals) == len(canonical_members))
            complete = bool(
                attempt is not None
                and attempt.status == 'succeeded'
                and attempt.completeness == 'complete'
                and observation is not None
                and observation.is_authoritative
                and observation.completeness == 'complete'
            )
            evidence[roster_type] = {
                'subject_id': subject.id if subject else None,
                'attempt_id': attempt.id if attempt else None,
                'observation_id': observation.id if observation else None,
                'sync_run_id': attempt.sync_run_id if attempt else None,
                'sync_job_id': attempt.sync_job_id if attempt else None,
                'status': attempt.status if attempt else 'missing',
                'outcome': attempt.outcome if attempt else None,
                'completeness': attempt.completeness if attempt else 'unknown',
                'record_count': attempt.record_count if attempt else None,
                'completed_at': (
                    attempt.completed_at.isoformat() if attempt else None
                ),
                'freshness_age_seconds': (
                    max(0, int((now - attempt.completed_at).total_seconds()))
                    if attempt else None
                ),
                'authoritative': complete,
                'latest_complete_observation_id': authoritative_observation.id if authoritative_observation else None,
                'source_member_ids': sorted(source_members),
                'interval_member_ids': sorted(canonical_members),
                'missing_canonical_member_ids': sorted(source_members - canonical_members),
                'extra_canonical_member_ids': sorted(canonical_members - source_members),
                'authority_source_mismatch_interval_ids': authority_mismatches,
                'source_scope_valid': source_scope_valid,
                'exact_match': exact_match,
            }

        current_active_count = RosterMembershipInterval.query.filter_by(
            team_id=team_id,
            membership_type='active_roster',
            effective_end_date=None,
            is_current_version=True,
            is_void=False,
        ).count()
        active = evidence['active']
        forty_man = evidence['40Man']
        active_membership_covered = bool(
            active['authoritative']
            and forty_man['authoritative']
            and active['exact_match']
        )
        if active_membership_covered:
            complete_active.append(team_id)
        elif active['authoritative'] and active['record_count'] == 0:
            suspicious_empty.append(team_id)
        elif 'failed' in {active['status'], forty_man['status']}:
            failed.append(team_id)
        elif 'partial' in {active['completeness'], forty_man['completeness']}:
            partial.append(team_id)
        elif active['attempt_id'] is None or forty_man['attempt_id'] is None:
            missing.append(team_id)
        else:
            stale.append(team_id)
        if forty_man['authoritative'] and forty_man['exact_match']:
            complete_forty_man.append(team_id)
        teams.append({
            'team_id': team_id,
            'current_active_pitcher_intervals': current_active_count,
            'active_membership_covered': active_membership_covered,
            'active': active,
            'forty_man': forty_man,
        })

    violations = []
    for interval in current_intervals:
        if interval.membership_type not in ('active_roster', 'forty_man_roster'):
            continue
        for boundary, observation_id in [('opening', interval.opened_by_observation_id),
                                          ('closing', interval.closed_by_observation_id)]:
            if observation_id is None:
                continue
            owner, subject, _ = observation_scope(db.session.get(SourceObservation, observation_id))
            if (interval.team_id not in MLB_TEAM_IDS or not owner
                    or not owner['mlb_membership_authority'] or owner['requested_team_id'] != interval.team_id):
                violations.append({'interval_id': interval.id, 'boundary': boundary,
                                   'team_id': interval.team_id, 'observation_id': observation_id})
    expected_count_valid = set(expected) == set(MLB_TEAM_IDS)
    active_coverage_count = len(complete_active)
    status = (
        'complete'
        if expected_count_valid and active_coverage_count == EXPECTED_MLB_TEAMS
        and len(complete_forty_man) == EXPECTED_MLB_TEAMS and not violations
        else 'incomplete'
    )
    return {
        'status': status,
        'baseball_date': baseball_date.isoformat(),
        'measured_at': now.isoformat(),
        'expected_teams': EXPECTED_MLB_TEAMS,
        'enumerated_teams': len(expected),
        'morning_sync_run_id': morning_run.id if morning_run else None,
        'active_roster_coverage_count': active_coverage_count,
        'forty_man_coverage_count': len(complete_forty_man),
        'complete_active_team_ids': complete_active,
        'complete_forty_man_team_ids': complete_forty_man,
        'missing_team_ids': sorted(set(missing)),
        'partial_team_ids': sorted(set(partial)),
        'failed_team_ids': sorted(set(failed)),
        'stale_team_ids': sorted(set(stale)),
        'suspicious_empty_active_team_ids': sorted(set(suspicious_empty)),
        'teams': teams,
        'active_exact_match_count': sum(row['active']['exact_match'] for row in teams),
        'forty_man_exact_match_count': sum(row['forty_man']['exact_match'] for row in teams),
        'affiliate_ownership_violations': violations,
        'affiliate_ownership_violation_count': len(violations),
    }


__all__ = [
    'EXPECTED_MLB_TEAMS',
    'expected_team_ids_from_run',
    'latest_shadow_morning_run',
    'roster_authority_coverage',
]
