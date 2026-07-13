"""Public roster-readiness contract and safe roster-count serialization."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime

from services import source_readiness
from services.roster_authority import FIELD_INVARIANCE, ROSTER_STATUS_CATEGORY_ORDER


CAPABILITY = 'public_roster_readiness_v1'
VERSION = '2026-07-12.phase0i'
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


def _reader_limitations(reason_codes):
    limitations = [_READER_LIMITATIONS.get(code) for code in reason_codes or []]
    if not any(limitations):
        limitations.append(_DEFAULT_LIMITATION)
    return _dedupe(limitations)


def _coverage_contract(family, *, scope, team_id):
    coverage = dict((family or {}).get('coverage') or {})
    teams_missing = list(coverage.get('teams_missing') or [])
    team_covered = None
    if team_id is not None:
        team_covered = int(team_id) not in {int(value) for value in teams_missing}
    return {
        'scope': scope,
        'complete': not teams_missing,
        'team_id': team_id,
        'team_covered': team_covered,
        'snapshot_date': coverage.get('snapshot_date'),
        'teams_expected': coverage.get('teams_expected'),
        'teams_covered': coverage.get('teams_covered'),
        'teams_missing_count': len(teams_missing),
    }


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
    reason_codes = list((family or {}).get('reason_codes') or [])
    status = (family or {}).get('status') or source_readiness.UNKNOWN
    fail_closed = bool((family or {}).get('fail_closed')) or status != source_readiness.READY
    coverage = _coverage_contract(family, scope=scope, team_id=team_id)
    team_missing = coverage.get('team_covered') is False
    claims_available = not fail_closed and not team_missing
    if team_missing and 'roster_snapshot_team_coverage_incomplete' not in reason_codes:
        reason_codes.append('roster_snapshot_team_coverage_incomplete')

    reader_limitations = [] if claims_available else _reader_limitations(reason_codes)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source_authority': SOURCE_AUTHORITY,
        'source_label': SOURCE_LABEL,
        'source_family': source_readiness.FAMILY_ROSTER_STATUS_SNAPSHOTS,
        'readiness_state': status,
        'claims_available': claims_available,
        'counts_withheld': not claims_available,
        'withheld_fields': [] if claims_available else list(ROSTER_DEPENDENT_COUNT_FIELDS),
        'last_verified_at': _iso((family or {}).get('last_successful_at')),
        'last_attempted_at': _iso((family or {}).get('last_attempted_at')),
        'data_through': coverage.get('snapshot_date') or _iso((family or {}).get('last_successful_at')),
        'stale_after_days': (family or {}).get('stale_after_days'),
        'data_age_days': (family or {}).get('data_age_days'),
        'coverage': coverage,
        'reader_limitations': reader_limitations,
        'reason_codes': _dedupe(reason_codes),
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
