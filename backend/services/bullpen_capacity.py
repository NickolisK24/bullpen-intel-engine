"""Team-level bullpen capacity loss intelligence.

This layer measures how much bullpen capacity is fully unavailable without
turning limited workload reads into unavailable capacity. It is intentionally
payload-first so boards, dashboards, stories, and share cards can consume one
backend-authored object instead of re-deriving capacity on each surface.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from models.game_log import GameLog
from services.availability import STATUS_UNAVAILABLE
from services.availability_reference_date import product_current_date
from services.bullpen_resource_health import build_bullpen_resource_health
from services.bullpen_trust_hierarchy import build_bullpen_trust_hierarchy
from utils.innings import decimal_innings_to_outs, log_innings_outs


CAPABILITY = 'bullpen_capacity_intelligence_v1'
VERSION = '2026-06-18.phase1'

WEIGHTING_SEASON_RELIEF_OUTS = 'season_relief_outs'
WEIGHTING_COUNT_BASED = 'count_based'

MIN_WEIGHTED_TOTAL_RELIEF_OUTS = 30
MIN_WEIGHTED_COVERAGE_SHARE = 0.75

COUNT_BASED_LIMITATION = (
    'Capacity uses count-based weighting because relief workload sample is limited.'
)
UNAVAILABLE_ZERO_OUTS_LIMITATION = (
    'Capacity uses count-based weighting because one or more unavailable bullpen arms have limited relief workload history.'
)
UNKNOWN_CAPACITY_LIMITATION = (
    'Some bullpen capacity is based on limited-read or unknown availability inputs.'
)
NO_CAPACITY_LIMITATION = (
    'No bullpen-eligible pitchers were available to measure capacity loss.'
)
NO_TRUST_ARM_LIMITATION = (
    'No relievers have a clear Trust Arm label, so Trust Capacity Loss is a Limited Read.'
)

LIMITED_DATA_STATES = {'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown'}
UNKNOWN_CONFIDENCE = {'none', 'unknown'}

CAPACITY_DEFINITIONS = {
    'available_capacity_pct': (
        'Share of measured bullpen capacity not classified as fully unavailable; '
        'this can include Monitor, Limited, or Avoid arms and should not be read '
        'as clean or fully available capacity. Limited-read or unknown capacity '
        'is reported separately.'
    ),
    'unavailable_capacity_pct': (
        'Share of measured bullpen capacity classified as fully unavailable by '
        'roster status or current availability read.'
    ),
    'unknown_limited_read_capacity_pct': (
        'Share of measured bullpen capacity with limited-read or unknown '
        'availability inputs.'
    ),
}


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _nested(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _pitcher(record: dict[str, Any]) -> Any:
    return record.get('pitcher')


def _pitcher_id(record: dict[str, Any]) -> int | None:
    return (
        record.get('pitcher_id')
        or _value(_pitcher(record), 'id')
        or _value(record.get('pitcher'), 'pitcher_id')
    )


def _is_bullpen_record(record: dict[str, Any]) -> bool:
    eligibility = record.get('eligibility')
    if eligibility is None:
        return True
    return bool(eligibility.get('eligible'))


def _is_roster_unavailable(record: dict[str, Any]) -> bool:
    roster_status = record.get('roster_status') or {}
    return (
        roster_status.get('is_inactive_context') is True
        or roster_status.get('is_active_mlb') is False
    )


def _availability_status(record: dict[str, Any]) -> str:
    return str((record.get('availability') or {}).get('availability_status') or '')


def _read_key(record: dict[str, Any]) -> str:
    return _nested(record.get('pitcher_labels'), 'read', 'key', default='') or ''


def _role_key(record: dict[str, Any]) -> str:
    return _nested(record.get('pitcher_labels'), 'role', 'key', default='') or ''


def _is_limited_read(record: dict[str, Any]) -> bool:
    availability = record.get('availability') or {}
    data_state = _norm(availability.get('data_state'))
    confidence = _norm(availability.get('confidence'))
    return (
        _read_key(record) == 'limited_read'
        or data_state in LIMITED_DATA_STATES
        or confidence in UNKNOWN_CONFIDENCE
    )


def _capacity_state(record: dict[str, Any]) -> tuple[str, str]:
    if _is_roster_unavailable(record):
        return 'unavailable', 'roster'
    if _read_key(record) == 'unavailable' or _availability_status(record) == STATUS_UNAVAILABLE:
        return 'unavailable', 'availability'
    if _is_limited_read(record):
        return 'unknown', 'limited_read'
    return 'available', 'active'


def _log_outs(log: Any) -> int | None:
    if isinstance(log, dict):
        outs = log.get('innings_pitched_outs')
        if outs is not None:
            try:
                parsed = int(outs)
            except (TypeError, ValueError):
                return None
            return parsed if parsed >= 0 else None
        return decimal_innings_to_outs(log.get('innings_pitched'))
    return log_innings_outs(log)


def _is_regular_season(log: Any) -> bool:
    game_type = _value(log, 'game_type')
    return game_type in (None, '', 'R')


def _is_relief_log(log: Any) -> bool:
    try:
        return int(_value(log, 'games_started')) == 0
    except (TypeError, ValueError):
        return False


def relief_outs_by_pitcher_from_logs(logs: list[Any]) -> dict[int, int]:
    outs_by_pitcher: dict[int, int] = defaultdict(int)
    for log in logs or []:
        if not _is_regular_season(log) or not _is_relief_log(log):
            continue
        pitcher_id = _value(log, 'pitcher_id')
        if pitcher_id is None:
            continue
        outs = _log_outs(log)
        if outs is None or outs <= 0:
            continue
        outs_by_pitcher[int(pitcher_id)] += outs
    return dict(outs_by_pitcher)


def season_relief_outs_by_pitcher(pitcher_ids, reference_date=None):
    ids = [int(pid) for pid in pitcher_ids or [] if pid is not None]
    if not ids:
        return {}

    ref = reference_date or product_current_date()
    season_start = date(ref.year, 1, 1)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(ids))
        .filter(GameLog.game_type == 'R')
        .filter(GameLog.game_date >= season_start)
        .filter(GameLog.game_date <= ref)
        .all()
    )
    return relief_outs_by_pitcher_from_logs(logs)


def _weighting(records, relief_outs_by_pitcher):
    total = len(records)
    relief_outs_by_pitcher = relief_outs_by_pitcher or {}
    total_outs = sum(int(relief_outs_by_pitcher.get(record['pitcher_id'], 0) or 0) for record in records)
    unavailable_zero_outs = sum(
        1
        for record in records
        if (
            record['state'] == 'unavailable'
            and int(relief_outs_by_pitcher.get(record['pitcher_id'], 0) or 0) <= 0
        )
    )
    covered = sum(
        1
        for record in records
        if int(relief_outs_by_pitcher.get(record['pitcher_id'], 0) or 0) > 0
    )
    coverage_share = covered / total if total else 0
    sample = {
        'total_relief_outs': total_outs,
        'pitchers_with_relief_outs': covered,
        'unavailable_pitchers_without_relief_outs': unavailable_zero_outs,
        'total_bullpen_pitcher_count': total,
        'min_weighted_total_relief_outs': MIN_WEIGHTED_TOTAL_RELIEF_OUTS,
        'min_weighted_coverage_share': MIN_WEIGHTED_COVERAGE_SHARE,
    }

    strong_weighted_sample = (
        total > 0
        and total_outs >= MIN_WEIGHTED_TOTAL_RELIEF_OUTS
        and coverage_share >= MIN_WEIGHTED_COVERAGE_SHARE
    )
    if strong_weighted_sample and unavailable_zero_outs == 0:
        return {
            'method': WEIGHTING_SEASON_RELIEF_OUTS,
            'basis': 'season relief outs',
            'sample': sample,
            'weights': {
                record['pitcher_id']: int(relief_outs_by_pitcher.get(record['pitcher_id'], 0) or 0)
                for record in records
            },
            'limitations': [],
        }

    limitations = []
    if unavailable_zero_outs > 0:
        limitations.append(UNAVAILABLE_ZERO_OUTS_LIMITATION)
    if total > 0 and not strong_weighted_sample:
        limitations.append(COUNT_BASED_LIMITATION)

    return {
        'method': WEIGHTING_COUNT_BASED,
        'basis': 'equal bullpen pitcher count',
        'sample': sample,
        'weights': {record['pitcher_id']: 1 for record in records},
        'limitations': limitations,
    }


def _pct(part, total):
    if not total:
        return 0
    return round(float(part or 0) / float(total) * 100)


def _capacity_status(unavailable_pct, known_capacity_weight, total_capacity_weight):
    if total_capacity_weight <= 0:
        return 'no_data'
    if known_capacity_weight <= 0:
        return 'limited_read'
    if unavailable_pct >= 40:
        return 'constrained'
    if unavailable_pct >= 20:
        return 'elevated'
    if unavailable_pct > 0:
        return 'manageable'
    return 'clear'


def _capacity_summary(unavailable_pct, total):
    if total <= 0:
        return 'No bullpen capacity could be measured from the current bullpen population.'
    if unavailable_pct <= 0:
        return 'No measured relief capacity is fully unavailable.'
    return f'The bullpen is operating with {unavailable_pct}% of measured relief capacity unavailable.'


def _trust_summary(available, total):
    if total <= 0:
        return 'Trust capacity is a Limited Read because no clear Trust Arms are labeled.'
    return f'{available} of {total} Trust Arms are currently available.'


def _serialize_weighting(weighting):
    return {
        'method': weighting['method'],
        'basis': weighting['basis'],
        'sample': weighting['sample'],
    }


def _team_identity(team):
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _records(records):
    normalized = []
    for record in records or []:
        if not _is_bullpen_record(record):
            continue
        pitcher_id = _pitcher_id(record)
        if pitcher_id is None:
            continue
        state, reason = _capacity_state(record)
        normalized.append({
            'pitcher_id': int(pitcher_id),
            'name': record.get('name') or _value(_pitcher(record), 'full_name'),
            'role_key': _role_key(record),
            'read_key': _read_key(record),
            'state': state,
            'state_reason': reason,
            'roster_unavailable': _is_roster_unavailable(record),
            'availability_status': _availability_status(record),
        })
    return normalized


def _sum_weight(records, weights, state=None, *, predicate=None):
    total = 0
    for record in records:
        if state is not None and record['state'] != state:
            continue
        if predicate is not None and not predicate(record):
            continue
        total += weights.get(record['pitcher_id'], 0)
    return total


def build_team_bullpen_capacity(
    records,
    *,
    team=None,
    relief_outs_by_pitcher=None,
):
    """Build serializable capacity loss intelligence for one team."""
    normalized = _records(records)
    relief_outs_by_pitcher = relief_outs_by_pitcher or {}
    weighting = _weighting(normalized, relief_outs_by_pitcher)
    weights = weighting['weights']
    total_weight = sum(weights.values())
    available_weight = _sum_weight(normalized, weights, 'available')
    unavailable_weight = _sum_weight(normalized, weights, 'unavailable')
    unknown_weight = _sum_weight(normalized, weights, 'unknown')
    inactive_unavailable_weight = _sum_weight(
        normalized,
        weights,
        'unavailable',
        predicate=lambda record: record['roster_unavailable'],
    )
    known_weight = available_weight + unavailable_weight

    available_pct = _pct(available_weight, total_weight)
    unavailable_pct = _pct(unavailable_weight, total_weight)
    unknown_pct = _pct(unknown_weight, total_weight)
    inactive_unavailable_pct = _pct(inactive_unavailable_weight, total_weight)
    limitations = list(weighting['limitations'])
    if not normalized and NO_CAPACITY_LIMITATION not in limitations:
        limitations.append(NO_CAPACITY_LIMITATION)
    if unknown_weight > 0 and UNKNOWN_CAPACITY_LIMITATION not in limitations:
        limitations.append(UNKNOWN_CAPACITY_LIMITATION)

    trust_records = [record for record in normalized if record['role_key'] == 'trust_arm']
    trust_weight = sum(weights.get(record['pitcher_id'], 0) for record in trust_records)
    trust_available_weight = _sum_weight(trust_records, weights, 'available')
    trust_unavailable_weight = _sum_weight(trust_records, weights, 'unavailable')
    trust_unknown_weight = _sum_weight(trust_records, weights, 'unknown')
    trust_unavailable_pct = _pct(trust_unavailable_weight, trust_weight)
    trust_limitations = list(weighting['limitations'])
    if not trust_records:
        trust_limitations.append(NO_TRUST_ARM_LIMITATION)
    if trust_unknown_weight > 0 and UNKNOWN_CAPACITY_LIMITATION not in trust_limitations:
        trust_limitations.append(UNKNOWN_CAPACITY_LIMITATION)

    capacity_loss = {
        'status': _capacity_status(unavailable_pct, known_weight, total_weight),
        'available_capacity_pct': available_pct,
        'unavailable_capacity_pct': unavailable_pct,
        'inactive_roster_unavailable_capacity_pct': inactive_unavailable_pct,
        'unknown_limited_read_capacity_pct': unknown_pct,
        'available_pitcher_count': sum(1 for record in normalized if record['state'] == 'available'),
        'unavailable_pitcher_count': sum(1 for record in normalized if record['state'] == 'unavailable'),
        'inactive_roster_unavailable_pitcher_count': sum(
            1
            for record in normalized
            if record['state'] == 'unavailable' and record['roster_unavailable']
        ),
        'availability_unavailable_pitcher_count': sum(
            1
            for record in normalized
            if record['state'] == 'unavailable' and not record['roster_unavailable']
        ),
        'unknown_limited_read_pitcher_count': sum(1 for record in normalized if record['state'] == 'unknown'),
        'total_bullpen_pitcher_count': len(normalized),
        'summary': _capacity_summary(unavailable_pct, len(normalized)),
        'definitions': dict(CAPACITY_DEFINITIONS),
        'weighting': _serialize_weighting(weighting),
        'limitations': limitations,
    }

    trust_capacity_loss = {
        'status': (
            'limited_read'
            if not trust_records
            else _capacity_status(
                trust_unavailable_pct,
                trust_available_weight + trust_unavailable_weight,
                trust_weight,
            )
        ),
        'trust_arms_available': sum(1 for record in trust_records if record['state'] == 'available'),
        'trust_arms_total': len(trust_records),
        'trust_arms_unavailable': sum(1 for record in trust_records if record['state'] == 'unavailable'),
        'trust_arms_unknown_limited_read': sum(1 for record in trust_records if record['state'] == 'unknown'),
        'trust_capacity_unavailable_pct': trust_unavailable_pct,
        'unknown_limited_read_trust_capacity_pct': _pct(trust_unknown_weight, trust_weight),
        'summary': _trust_summary(
            sum(1 for record in trust_records if record['state'] == 'available'),
            len(trust_records),
        ),
        'definitions': {
            'trust_capacity_unavailable_pct': (
                'Share of measured Trust Arm capacity classified as fully unavailable; '
                'Trust Arms come from existing backend-authored public role labels.'
            ),
            'unknown_limited_read_trust_capacity_pct': (
                'Share of measured Trust Arm capacity with limited-read or unknown '
                'availability inputs.'
            ),
        },
        'weighting': _serialize_weighting(weighting),
        'limitations': trust_limitations,
    }

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': team.get('team_abbreviation') if isinstance(team, dict) else None,
        **_team_identity(team),
        'resource_health': build_bullpen_resource_health(records, team=team),
        'trust_hierarchy': build_bullpen_trust_hierarchy(
            records,
            team=team,
            relief_outs_by_pitcher=relief_outs_by_pitcher,
            include_pitchers=False,
        ),
        'capacity_loss': capacity_loss,
        'trust_capacity_loss': trust_capacity_loss,
    }


def build_league_capacity_payload(team_capacity_items):
    teams = list(team_capacity_items or [])
    return {
        'capability': 'league_bullpen_capacity_intelligence_v1',
        'version': VERSION,
        'source': 'backend',
        'teams_evaluated': len(teams),
        'teams': teams,
        'by_team_id': {
            str(item.get('team_id')): item
            for item in teams
            if item.get('team_id') is not None
        },
    }


__all__ = [
    'CAPABILITY',
    'COUNT_BASED_LIMITATION',
    'UNAVAILABLE_ZERO_OUTS_LIMITATION',
    'UNKNOWN_CAPACITY_LIMITATION',
    'NO_TRUST_ARM_LIMITATION',
    'VERSION',
    'WEIGHTING_COUNT_BASED',
    'WEIGHTING_SEASON_RELIEF_OUTS',
    'build_league_capacity_payload',
    'build_team_bullpen_capacity',
    'relief_outs_by_pitcher_from_logs',
    'season_relief_outs_by_pitcher',
]
