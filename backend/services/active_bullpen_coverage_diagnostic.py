"""Read-only explanation of a team's active-bullpen readiness coverage.

When a Dashboard candidate is withheld with
``snapshot_team_state_ineligible:<team>:data_state:incomplete,confidence:low,
status_code_unsupported:data_limited`` the publication proof records only the
reason codes. It does not record which active-bullpen arms were unusable or why,
so the incident cannot be reconstructed from the run.

This module answers that question from the same authorities the proof reads. It
re-runs the membership and per-record usability rules of
``api.team_operations._assess_active_bullpen_coverage`` and names, for every
active-bullpen arm, the first reason its record is not usable. It classifies
nothing new, writes nothing, and changes no gate: the team-level verdict is
produced by the unchanged ``assess_team_coverage``.

Cause codes (one per arm, first match wins, mirroring the production rule):

* ``usable_fresh``                 a record with an appearance in the active window
* ``usable_ledger_rest``           no recent appearance, and the ledger proves it
* ``usable_ledger_confirmed_no_recent_workload``
                                   no score, no appearance in the active window,
                                   and the ledger and roster evidence prove it
* ``no_record_pitcher_unknown``    the roster authority names an unknown pitcher
* ``no_record_other_team``         the pitcher's ``team_id`` is another club
* ``no_record_inactive_pitcher``   ``Pitcher.active`` is false, so never scored
* ``no_record_assignment_unconfirmed`` no score; team assignment not ``ASSIGNED``
* ``no_record_mlb_id_missing``     no score; no MLB id to check fetch failures by
* ``no_record_recent_workload_unscored`` no score, yet a log sits in the window
* ``no_record_team_game_not_final`` no score; a team game in the ledger window
                                   is live, suspended, or unsettled
* ``unresolved_fetch_failure``     an unresolved ``pitcher_game_logs`` dead letter
* ``unresolved_incomplete_log``    a log in the window lacks date or pitch count
* ``unresolved_missing_history``   the record has no score or no appearance date
* ``unresolved_rest_unproven``     no recent appearance and the ledger is incomplete
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable, Mapping, Optional

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from services import ledger_confirmed_rest as unscored_rest
from services.mlb_club_directory import MLB_CLUBS
from services.team_readiness_coverage import (
    assess_team_coverage,
    resolve_active_bullpen_membership,
)
from utils.db import db


CAUSE_USABLE_FRESH = 'usable_fresh'
CAUSE_USABLE_LEDGER_REST = 'usable_ledger_rest'
CAUSE_NO_RECORD_PITCHER_UNKNOWN = 'no_record_pitcher_unknown'
CAUSE_NO_RECORD_OTHER_TEAM = 'no_record_other_team'
CAUSE_NO_RECORD_INACTIVE_PITCHER = 'no_record_inactive_pitcher'
CAUSE_USABLE_LEDGER_CONFIRMED_NO_RECENT_WORKLOAD = (
    'usable_ledger_confirmed_no_recent_workload'
)
CAUSE_NO_RECORD_ASSIGNMENT_UNCONFIRMED = 'no_record_assignment_unconfirmed'
CAUSE_NO_RECORD_MLB_ID_MISSING = 'no_record_mlb_id_missing'
CAUSE_NO_RECORD_RECENT_WORKLOAD_UNSCORED = 'no_record_recent_workload_unscored'
CAUSE_NO_RECORD_TEAM_GAME_NOT_FINAL = 'no_record_team_game_not_final'
CAUSE_UNRESOLVED_FETCH_FAILURE = 'unresolved_fetch_failure'
CAUSE_UNRESOLVED_INCOMPLETE_LOG = 'unresolved_incomplete_log'
CAUSE_UNRESOLVED_MISSING_HISTORY = 'unresolved_missing_history'
CAUSE_UNRESOLVED_REST_UNPROVEN = 'unresolved_rest_unproven'

USABLE_CAUSES = frozenset({
    CAUSE_USABLE_FRESH,
    CAUSE_USABLE_LEDGER_REST,
    CAUSE_USABLE_LEDGER_CONFIRMED_NO_RECENT_WORKLOAD,
})

# The unscored-rest proof's reason, as the diagnostic's per-arm cause.
_UNSCORED_CAUSES = {
    unscored_rest.REASON_CONFIRMED: CAUSE_USABLE_LEDGER_CONFIRMED_NO_RECENT_WORKLOAD,
    unscored_rest.REASON_PITCHER_UNKNOWN: CAUSE_NO_RECORD_PITCHER_UNKNOWN,
    unscored_rest.REASON_OTHER_TEAM: CAUSE_NO_RECORD_OTHER_TEAM,
    unscored_rest.REASON_INACTIVE: CAUSE_NO_RECORD_INACTIVE_PITCHER,
    unscored_rest.REASON_ASSIGNMENT_UNCONFIRMED: CAUSE_NO_RECORD_ASSIGNMENT_UNCONFIRMED,
    unscored_rest.REASON_MLB_ID_MISSING: CAUSE_NO_RECORD_MLB_ID_MISSING,
    unscored_rest.REASON_LEDGER_INCOMPLETE: 'unresolved_rest_unproven',
    unscored_rest.REASON_FETCH_FAILURE_OPEN: 'unresolved_fetch_failure',
    unscored_rest.REASON_WINDOW_LOG_INCOMPLETE: 'unresolved_incomplete_log',
    unscored_rest.REASON_RECENT_APPEARANCE_UNSCORED: CAUSE_NO_RECORD_RECENT_WORKLOAD_UNSCORED,
    unscored_rest.REASON_TEAM_GAME_NOT_FINAL: CAUSE_NO_RECORD_TEAM_GAME_NOT_FINAL,
}

PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'

_ABBREVIATIONS = {club.team_id: club.abbreviation for club in MLB_CLUBS}


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _classified_team_records(team_id, availability_date):
    """The exact records the production resolver classifies for this team."""
    from api.team_operations import TEAM_OPERATIONS_DEFAULT_LIMIT
    from services.availability_snapshot import (
        CURRENT_AVAILABILITY_MODE,
        classify_latest_fatigue_rows,
        latest_fatigue_rows,
    )

    rows = tuple(latest_fatigue_rows(team_id=team_id, limit=TEAM_OPERATIONS_DEFAULT_LIMIT))
    records = classify_latest_fatigue_rows(
        rows, reference_date=availability_date, mode=CURRENT_AVAILABILITY_MODE,
    )
    return {
        getattr(record.get('pitcher'), 'id', None): record
        for record in records
        if getattr(record.get('pitcher'), 'id', None) is not None
    }


def _ledger_complete(availability_date):
    from api.team_operations import _appearance_ledger_complete
    return _appearance_ledger_complete(availability_date)


def _open_fetch_failures(mlb_ids: Iterable) -> dict:
    refs = [str(ref) for ref in mlb_ids if ref is not None]
    if not refs:
        return {}
    rows = (
        SyncFailure.query
        .filter(SyncFailure.entity_type == PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE)
        .filter(SyncFailure.resolved.is_(False))
        .filter(SyncFailure.entity_ref.in_(refs))
        .order_by(SyncFailure.created_at.asc(), SyncFailure.id.asc())
        .all()
    )
    failures = {}
    for row in rows:
        failures.setdefault(row.entity_ref, []).append({
            'sync_failure_id': row.id,
            'created_at': _iso(row.created_at),
            'job_name': row.job_name,
            'sync_run_id': row.sync_run_id,
            'error_label': _safe_error_label(row.error),
        })
    return failures


_URL = re.compile(r'\S+://\S*')
_ASSIGNMENT = re.compile(r'\S*=\S*')


def _safe_error_label(error):
    """A short, artifact-safe label for a stored failure message.

    Only the first line before any detail separator is kept, with URLs and
    ``key=value`` fragments removed, so no connection string, token or query
    parameter can travel into an uploaded diagnostic artifact.
    """
    first_line = (error or '').strip().splitlines()[0] if (error or '').strip() else ''
    label = first_line.split(': ', 1)[0]
    label = _ASSIGNMENT.sub('[redacted]', _URL.sub('[url]', label))
    return label[:120]


def _latest_log_date(pitcher_id):
    return (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )


def _incomplete_window_logs(record):
    evaluation_date = record.get('evaluation_date')
    if not isinstance(evaluation_date, date):
        return []
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id == getattr(record.get('pitcher'), 'id', None))
        .filter(GameLog.game_date >= evaluation_date - timedelta(days=4))
        .filter(GameLog.game_date <= evaluation_date)
        .all()
    )
    return [
        {'mlb_game_pk': log.mlb_game_pk, 'game_date': _iso(log.game_date)}
        for log in logs
        if log.game_date is None or log.pitches_thrown is None
    ]


def _arm_evidence(pitcher, record, availability_date):
    """Every input the production classifier reads for this arm, as observed."""
    availability = (record or {}).get('availability') or {}
    score = (record or {}).get('score')
    latest = (record or {}).get('latest_game_date')
    if latest is None and pitcher is not None:
        latest = _latest_log_date(pitcher.id)
    window_logs = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher.id)
        .filter(GameLog.game_date >= availability_date - timedelta(days=4))
        .filter(GameLog.game_date <= availability_date)
        .all()
        if pitcher is not None else []
    )
    return {
        'pitcher_team_id': getattr(pitcher, 'team_id', None),
        'pitcher_active': getattr(pitcher, 'active', None),
        'roster_status': getattr(pitcher, 'roster_status', None),
        'team_assignment_status': getattr(pitcher, 'team_assignment_status', None),
        'readiness_record_exists': record is not None,
        'fatigue_calculated_at': _iso(getattr(score, 'calculated_at', None)),
        'record_data_state': availability.get('data_state'),
        'record_confidence': availability.get('confidence'),
        'latest_game_log_date': _iso(latest),
        'days_since_last_appearance': (
            (availability_date - latest).days if isinstance(latest, date) else None
        ),
        'window_log_count': len(window_logs),
        'window_logs_missing_pitch_count': sum(
            1 for log in window_logs if log.pitches_thrown is None
        ),
    }


def _arm_without_record(unscored_reason, failures):
    cause = _UNSCORED_CAUSES[unscored_reason]
    detail = {'unscored_rest_reason': unscored_reason}
    if cause == CAUSE_UNRESOLVED_FETCH_FAILURE:
        detail['open_fetch_failures'] = failures
    return cause, detail


def _arm_with_record(record, ledger_complete, failures):
    availability = record.get('availability') or {}
    data_state = availability.get('data_state')
    inputs = availability.get('inputs') or {}
    if data_state == 'fresh':
        return CAUSE_USABLE_FRESH, {}
    if data_state == 'stale':
        if ledger_complete:
            return CAUSE_USABLE_LEDGER_REST, {}
        return CAUSE_UNRESOLVED_REST_UNPROVEN, {}
    if data_state == 'incomplete' and inputs.get('workload_fetch_failed'):
        return CAUSE_UNRESOLVED_FETCH_FAILURE, {'open_fetch_failures': failures}
    if data_state == 'incomplete':
        return CAUSE_UNRESOLVED_INCOMPLETE_LOG, {
            'incomplete_logs': _incomplete_window_logs(record),
        }
    return CAUSE_UNRESOLVED_MISSING_HISTORY, {
        'score_present': record.get('score') is not None,
        'latest_game_date': _iso(record.get('latest_game_date')),
    }


def diagnose_active_bullpen_coverage(
    team_id: int,
    *,
    membership_date: date,
    availability_date: date,
    source_current: bool = True,
    ledger_complete: Optional[bool] = None,
) -> dict:
    """Explain one team's active-bullpen coverage at the given reference dates.

    ``source_current`` is the league freshness verdict the coverage classifier
    receives; it is team-independent, so the caller supplies it. ``ledger_complete``
    may be passed to share one ledger evaluation across teams.
    """
    member_ids, authority_complete = resolve_active_bullpen_membership(
        team_id, membership_date,
    )
    if ledger_complete is None:
        ledger_complete = _ledger_complete(availability_date)
    records = _classified_team_records(team_id, availability_date)
    pitchers = {
        pitcher.id: pitcher
        for pitcher in (
            Pitcher.query.filter(Pitcher.id.in_(sorted(member_ids))).all()
            if member_ids else []
        )
    }
    failures = _open_fetch_failures(pitcher.mlb_id for pitcher in pitchers.values())
    unscored_reasons = unscored_rest.evaluate_unscored_rest(
        [pid for pid in member_ids if pid not in records],
        team_id=team_id, reference_date=availability_date,
        ledger_complete=ledger_complete,
    )

    arms = []
    for pitcher_id in sorted(member_ids):
        pitcher = pitchers.get(pitcher_id)
        record = records.get(pitcher_id)
        pitcher_failures = failures.get(str(getattr(pitcher, 'mlb_id', None)), [])
        if record is None:
            cause, detail = _arm_without_record(
                unscored_reasons[pitcher_id], pitcher_failures,
            )
        else:
            cause, detail = _arm_with_record(record, ledger_complete, pitcher_failures)
        arms.append({
            'pitcher_id': pitcher_id,
            'mlb_id': getattr(pitcher, 'mlb_id', None),
            'pitcher_name': getattr(pitcher, 'full_name', None),
            'cause': cause,
            'usable': cause in USABLE_CAUSES,
            'open_fetch_failure_count': len(pitcher_failures),
            **_arm_evidence(pitcher, record, availability_date),
            **detail,
        })

    usable = sum(1 for arm in arms if arm['usable'])
    assessment = assess_team_coverage(
        authority_complete=authority_complete,
        source_current=source_current,
        active_bullpen_count=len(member_ids),
        usable_record_count=usable,
        unresolved_record_count=len(member_ids) - usable,
    )
    cause_counts = {}
    for arm in arms:
        cause_counts[arm['cause']] = cause_counts.get(arm['cause'], 0) + 1
    return {
        'team_id': team_id,
        'membership_date': _iso(membership_date),
        'availability_date': _iso(availability_date),
        'authority_complete': authority_complete,
        'ledger_complete': ledger_complete,
        'source_current': source_current,
        'active_bullpen_count': len(member_ids),
        'usable_record_count': usable,
        'unresolved_record_count': len(member_ids) - usable,
        'coverage_pct': _coverage_pct(len(member_ids), usable),
        'medium_bar': {
            'min_usable': 6, 'max_unresolved': 2, 'min_coverage_pct': 75.0,
        },
        'unresolved_headroom': unresolved_headroom(len(member_ids), usable),
        'eligible_coverage': assessment.confidence in ('high', 'medium'),
        'confidence': assessment.confidence,
        'data_state': assessment.data_state,
        'coverage_reason_code': assessment.reason_code,
        'cause_counts': dict(sorted(cause_counts.items())),
        'arms': arms,
    }


def _coverage_pct(active, usable):
    return round(usable * 100.0 / active, 1) if active else None


def unresolved_headroom(active: int, usable: int) -> int:
    """How many more arms could turn unresolved before the team drops to ``low``.

    Negative when the team is already below the ``medium`` bar. Mirrors the
    approved thresholds: >= 6 usable, <= 2 unresolved, usable >= 75% of active.
    """
    unresolved = active - usable
    by_unresolved = 2 - unresolved
    by_usable = usable - 6
    by_share = (usable * 4 - active * 3) // 4 if usable * 4 >= active * 3 else -1
    return min(by_unresolved, by_usable, by_share)


def diagnose_league(
    team_ids: Iterable[int],
    *,
    membership_date: date,
    availability_date: date,
    source_current: bool = True,
) -> dict:
    """Coverage for every team, ordered from least headroom to most."""
    ledger_complete = _ledger_complete(availability_date)
    teams = []
    for team_id in team_ids:
        report = diagnose_active_bullpen_coverage(
            team_id,
            membership_date=membership_date,
            availability_date=availability_date,
            source_current=source_current,
            ledger_complete=ledger_complete,
        )
        teams.append({
            'team': _ABBREVIATIONS.get(team_id),
            **{key: report[key] for key in (
                'team_id', 'authority_complete', 'active_bullpen_count',
                'usable_record_count', 'unresolved_record_count', 'coverage_pct',
                'unresolved_headroom', 'confidence', 'data_state',
                'eligible_coverage', 'coverage_reason_code', 'cause_counts',
            )},
        })
    teams.sort(key=lambda team: (team['unresolved_headroom'], team['team_id']))
    return {
        'membership_date': _iso(membership_date),
        'availability_date': _iso(availability_date),
        'ledger_complete': ledger_complete,
        'ineligible_team_ids': [
            team['team_id'] for team in teams if not team['eligible_coverage']
        ],
        'one_arm_from_failing': [
            team['team_id'] for team in teams if team['unresolved_headroom'] == 0
        ],
        'two_arms_from_failing': [
            team['team_id'] for team in teams if team['unresolved_headroom'] == 1
        ],
        'teams': teams,
    }


def reference_dates_for_snapshot(snapshot) -> tuple:
    """The (membership, availability) dates the publication proof used for it."""
    from services.availability_reference_date import trusted_slate_reference_dates
    return trusted_slate_reference_dates(
        getattr(snapshot, 'data_through', None),
        getattr(snapshot, 'availability_reference_date', None),
    )


def summary_line(report: Mapping) -> str:
    return (
        f"team={report['team_id']} active={report['active_bullpen_count']} "
        f"usable={report['usable_record_count']} "
        f"unresolved={report['unresolved_record_count']} "
        f"confidence={report['confidence']} data_state={report['data_state']} "
        f"causes={report['cause_counts']}"
    )
