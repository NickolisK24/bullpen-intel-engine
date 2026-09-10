"""Public roster-readiness contract and safe roster-count serialization."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime

from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from services import source_readiness
from services.roster_authority import FIELD_INVARIANCE, ROSTER_STATUS_CATEGORY_ORDER
from services.roster_status_sync import (
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    roster_status_cache_divergence_count,
)


CAPABILITY = 'public_roster_readiness_v1'
VERSION = '2026-07-24.team-scope'
SOURCE_AUTHORITY = 'official_mlb_roster'
SOURCE_LABEL = 'Official MLB roster data'

ROSTER_DEPENDENT_COUNT_FIELDS = tuple(FIELD_INVARIANCE.keys())

_READER_LIMITATIONS = {
    'source_stale': 'Roster status has not been verified recently.',
    'source_unavailable': 'Current active-roster coverage could not be verified.',
    'source_never_fetched': 'Current active-roster coverage has not been verified yet.',
    'roster_snapshots_missing': 'Current active-roster coverage has not been verified yet.',
    'roster_snapshot_team_coverage_incomplete': (
        'Current active-roster coverage could not be verified completely.'
    ),
    'roster_status_cache_divergence': (
        'Roster status is being reconciled against official roster evidence.'
    ),
    'dead_letters_unresolved': 'Roster status has unresolved source conflicts.',
    'provenance_missing': 'Roster status verification provenance is incomplete.',
    'readiness_query_failed': 'Roster status verification could not be checked.',
    'readiness_framework_error': 'Roster status verification could not be checked.',
    'readiness_framework_unavailable': 'Roster status verification could not be checked.',
}

_DEFAULT_LIMITATION = 'Current usable bullpen depth cannot be verified from official roster status.'
_TEAM_SCOPABLE_REASON_CODES = frozenset({
    'dead_letters_unresolved',
    'roster_snapshot_team_coverage_incomplete',
    'roster_status_cache_divergence',
})
_ROSTER_FAILURE_ENTITY_TYPES = (
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
)
_GLOBAL_FAIL_CLOSED_STATES = frozenset({
    source_readiness.STALE,
    source_readiness.UNAVAILABLE,
    source_readiness.NEVER_FETCHED,
    source_readiness.UNKNOWN,
})


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _dedupe(values):
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _reader_limitations(reason_codes):
    limitations = [_READER_LIMITATIONS.get(code) for code in reason_codes or []]
    if not any(limitations):
        limitations.append(_DEFAULT_LIMITATION)
    return _dedupe(limitations)


def _coverage_contract(family, *, scope, team_id):
    coverage = dict((family or {}).get('coverage') or {})
    teams_missing = list(coverage.get('teams_missing') or [])
    missing_ids = {
        parsed
        for parsed in (_positive_int(value) for value in teams_missing)
        if parsed is not None
    }
    normalized_team_id = _positive_int(team_id)
    team_covered = None
    if normalized_team_id is not None:
        team_covered = normalized_team_id not in missing_ids
    league_complete = not teams_missing
    return {
        'scope': scope,
        'complete': league_complete,
        'scope_complete': team_covered if scope == 'team' else league_complete,
        'team_id': normalized_team_id,
        'team_covered': team_covered,
        'snapshot_date': coverage.get('snapshot_date'),
        'teams_expected': coverage.get('teams_expected'),
        'teams_covered': coverage.get('teams_covered'),
        'teams_missing_count': len(teams_missing),
    }


def _unresolved_roster_failures():
    return (
        SyncFailure.query
        .filter(SyncFailure.resolved.is_(False))
        .filter(SyncFailure.entity_type.in_(_ROSTER_FAILURE_ENTITY_TYPES))
        .order_by(SyncFailure.id.asc())
        .all()
    )


def _failure_pitcher_team_maps(failures):
    local_pitcher_ids = set()
    mlb_ids = set()
    for failure in failures:
        payload = failure.payload or {}
        local_id = _positive_int(payload.get('pitcher_id'))
        mlb_id = _positive_int(payload.get('mlb_id'))
        if failure.entity_type == ROSTER_STATUS_CONFLICT_ENTITY_TYPE and mlb_id is None:
            mlb_id = _positive_int(failure.entity_ref)
        if local_id is not None:
            local_pitcher_ids.add(local_id)
        if mlb_id is not None:
            mlb_ids.add(mlb_id)

    by_local_id = {}
    if local_pitcher_ids:
        by_local_id = {
            pitcher.id: _positive_int(pitcher.team_id)
            for pitcher in Pitcher.query.filter(Pitcher.id.in_(local_pitcher_ids)).all()
        }
    by_mlb_id = {}
    if mlb_ids:
        by_mlb_id = {
            pitcher.mlb_id: _positive_int(pitcher.team_id)
            for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids)).all()
        }
    return by_local_id, by_mlb_id


def _failure_team_ids(failure, *, by_local_id, by_mlb_id):
    payload = failure.payload or {}
    local_id = _positive_int(payload.get('pitcher_id'))
    mlb_id = _positive_int(payload.get('mlb_id'))
    if failure.entity_type == ROSTER_STATUS_CONFLICT_ENTITY_TYPE and mlb_id is None:
        mlb_id = _positive_int(failure.entity_ref)

    # A conflict follows the pitcher's current team first. Historical conflict
    # payloads may retain old/incoming team ids after a trade, while the public
    # team page must fail closed for the team that currently owns the unresolved
    # pitcher identity.
    if failure.entity_type == ROSTER_STATUS_CONFLICT_ENTITY_TYPE:
        current_team_id = by_local_id.get(local_id) or by_mlb_id.get(mlb_id)
        if current_team_id is not None:
            return {current_team_id}
        fallback_ids = {
            parsed
            for parsed in (
                _positive_int(payload.get('incoming_team_id')),
                _positive_int(payload.get('existing_team_id')),
            )
            if parsed is not None
        }
        return fallback_ids

    team_ids = set()
    direct_team_id = _positive_int(payload.get('team_id'))
    if direct_team_id is not None:
        team_ids.add(direct_team_id)
    if failure.entity_type in {
        ROSTER_STATUS_FETCH_ENTITY_TYPE,
        ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    }:
        entity_team_id = _positive_int(failure.entity_ref)
        if entity_team_id is not None:
            team_ids.add(entity_team_id)
    mapped_team_id = by_local_id.get(local_id) or by_mlb_id.get(mlb_id)
    if mapped_team_id is not None:
        team_ids.add(mapped_team_id)
    return team_ids


def _team_dead_letter_evaluation(team_id):
    failures = _unresolved_roster_failures()
    if not failures:
        return {
            'team_failure_count': 0,
            'unscoped_failure_count': 0,
        }

    by_local_id, by_mlb_id = _failure_pitcher_team_maps(failures)
    team_failure_count = 0
    unscoped_failure_count = 0
    for failure in failures:
        failure_team_ids = _failure_team_ids(
            failure,
            by_local_id=by_local_id,
            by_mlb_id=by_mlb_id,
        )
        if not failure_team_ids:
            unscoped_failure_count += 1
        elif team_id in failure_team_ids:
            team_failure_count += 1
    return {
        'team_failure_count': team_failure_count,
        'unscoped_failure_count': unscoped_failure_count,
    }


def _team_scope_decision(*, family, status, reason_codes, coverage):
    team_id = coverage.get('team_id')
    team_missing = coverage.get('team_covered') is False
    family_fail_closed = bool((family or {}).get('fail_closed')) or status != source_readiness.READY
    evaluation = {
        'mode': 'team',
        'isolated_from_league_degradation': False,
        'team_missing': team_missing,
        'team_dead_letter_count': 0,
        'unscoped_dead_letter_count': 0,
        'team_cache_divergence_count': 0,
    }

    if team_id is None:
        return False, status, list(reason_codes), evaluation
    if status == source_readiness.READY and not family_fail_closed:
        effective_reasons = []
        if team_missing:
            effective_reasons.append('roster_snapshot_team_coverage_incomplete')
        return not team_missing, (
            source_readiness.READY if not team_missing else source_readiness.DEGRADED
        ), effective_reasons, evaluation
    if status in _GLOBAL_FAIL_CLOSED_STATES:
        return False, status, list(reason_codes), evaluation

    reason_set = set(reason_codes)
    if (
        status != source_readiness.DEGRADED
        or not reason_set
        or not reason_set.issubset(_TEAM_SCOPABLE_REASON_CODES)
    ):
        return False, status, list(reason_codes), evaluation

    effective_reasons = []
    if team_missing:
        effective_reasons.append('roster_snapshot_team_coverage_incomplete')

    if 'dead_letters_unresolved' in reason_set:
        dead_letters = _team_dead_letter_evaluation(team_id)
        evaluation['team_dead_letter_count'] = dead_letters['team_failure_count']
        evaluation['unscoped_dead_letter_count'] = dead_letters['unscoped_failure_count']
        if dead_letters['team_failure_count'] or dead_letters['unscoped_failure_count']:
            effective_reasons.append('dead_letters_unresolved')

    if 'roster_status_cache_divergence' in reason_set:
        divergence_count = roster_status_cache_divergence_count(team_ids=[team_id])
        evaluation['team_cache_divergence_count'] = divergence_count
        if divergence_count:
            effective_reasons.append('roster_status_cache_divergence')

    claims_available = not effective_reasons
    evaluation['isolated_from_league_degradation'] = claims_available
    effective_status = source_readiness.READY if claims_available else source_readiness.DEGRADED
    return claims_available, effective_status, effective_reasons, evaluation


def build_public_roster_readiness(
    *,
    reference_date=None,
    team_id=None,
    scope='team',
    family=None,
) -> dict:
    family = family or source_readiness.roster_status_snapshot_readiness_payload(
        reference_date=reference_date,
    )
    normalized_scope = 'team' if str(scope or '').strip().lower() == 'team' else 'league'
    league_reason_codes = list((family or {}).get('reason_codes') or [])
    league_status = (family or {}).get('status') or source_readiness.UNKNOWN
    coverage = _coverage_contract(family, scope=normalized_scope, team_id=team_id)

    if normalized_scope == 'team':
        claims_available, effective_status, reason_codes, scope_evaluation = _team_scope_decision(
            family=family,
            status=league_status,
            reason_codes=league_reason_codes,
            coverage=coverage,
        )
    else:
        fail_closed = bool((family or {}).get('fail_closed')) or league_status != source_readiness.READY
        claims_available = not fail_closed
        effective_status = league_status
        reason_codes = list(league_reason_codes)
        scope_evaluation = {
            'mode': 'league',
            'isolated_from_league_degradation': False,
        }

    reader_limitations = [] if claims_available else _reader_limitations(reason_codes)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source_authority': SOURCE_AUTHORITY,
        'source_label': SOURCE_LABEL,
        'source_family': source_readiness.FAMILY_ROSTER_STATUS_SNAPSHOTS,
        'readiness_state': effective_status,
        'league_readiness_state': league_status,
        'claims_available': claims_available,
        'counts_withheld': not claims_available,
        'withheld_fields': [] if claims_available else list(ROSTER_DEPENDENT_COUNT_FIELDS),
        'last_verified_at': _iso((family or {}).get('last_successful_at')),
        'last_attempted_at': _iso((family or {}).get('last_attempted_at')),
        'data_through': coverage.get('snapshot_date') or _iso((family or {}).get('last_successful_at')),
        'stale_after_days': (family or {}).get('stale_after_days'),
        'data_age_days': (family or {}).get('data_age_days'),
        'coverage': coverage,
        'scope_evaluation': scope_evaluation,
        'reader_limitations': reader_limitations,
        'reason_codes': _dedupe(reason_codes),
        'league_reason_codes': _dedupe(league_reason_codes),
    }


def roster_claims_available(readiness) -> bool:
    return bool((readiness or {}).get('claims_available'))


def apply_public_roster_readiness(authority, readiness):
    result = deepcopy(authority or {})
    result['readiness'] = dict(readiness or {})
    if roster_claims_available(readiness):
        return result

    result['counts'] = {
        field: None
        for field in ROSTER_DEPENDENT_COUNT_FIELDS
    }
    result['category_counts'] = {
        category: None
        for category in ROSTER_STATUS_CATEGORY_ORDER
    }
    result['population'] = {
        'total_candidates': None,
        'known_count': None,
        'unknown_count': None,
        'roster_status_coverage': None,
    }
    result['evidence'] = {
        field: []
        for field in ROSTER_DEPENDENT_COUNT_FIELDS
    }
    result['category_evidence'] = {
        category: []
        for category in ROSTER_STATUS_CATEGORY_ORDER
    }
    limitations = list(result.get('limitations') or [])
    limitations.extend((readiness or {}).get('reader_limitations') or [])
    result['limitations'] = _dedupe(limitations)
    return result


__all__ = [
    'CAPABILITY',
    'VERSION',
    'ROSTER_DEPENDENT_COUNT_FIELDS',
    'apply_public_roster_readiness',
    'build_public_roster_readiness',
    'roster_claims_available',
]
