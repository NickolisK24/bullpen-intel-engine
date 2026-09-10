"""Read-only current SP-05 roster-authority coverage reporting."""

from __future__ import annotations

from datetime import date, datetime

from models.roster_membership import RosterMembershipInterval
from models.source_observation import (
    SourceFetchAttempt,
    SourceObservation,
    SourceSubject,
)
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
    morning_run = latest_shadow_morning_run(baseball_date)
    expected = tuple(sorted({
        int(value)
        for value in (
            expected_team_ids
            if expected_team_ids is not None
            else expected_team_ids_from_run(morning_run)
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
            }

        current_active_count = RosterMembershipInterval.query.filter_by(
            team_id=team_id,
            membership_type='active_roster',
            effective_end_date=None,
            is_current_version=True,
        ).count()
        active = evidence['active']
        forty_man = evidence['40Man']
        active_membership_covered = bool(
            active['authoritative']
            and (active['record_count'] or 0) > 0
            and current_active_count > 0
        )
        if active_membership_covered:
            complete_active.append(team_id)
        elif active['authoritative'] and active['record_count'] == 0:
            suspicious_empty.append(team_id)
        elif active['status'] == 'failed':
            failed.append(team_id)
        elif active['completeness'] == 'partial':
            partial.append(team_id)
        elif active['attempt_id'] is None:
            missing.append(team_id)
        else:
            stale.append(team_id)
        if forty_man['authoritative']:
            complete_forty_man.append(team_id)
        teams.append({
            'team_id': team_id,
            'current_active_pitcher_intervals': current_active_count,
            'active_membership_covered': active_membership_covered,
            'active': active,
            'forty_man': forty_man,
        })

    expected_count_valid = len(expected) == EXPECTED_MLB_TEAMS
    active_coverage_count = len(complete_active)
    status = (
        'complete'
        if expected_count_valid and active_coverage_count == EXPECTED_MLB_TEAMS
        and not suspicious_empty
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
    }


__all__ = [
    'EXPECTED_MLB_TEAMS',
    'expected_team_ids_from_run',
    'latest_shadow_morning_run',
    'roster_authority_coverage',
]
