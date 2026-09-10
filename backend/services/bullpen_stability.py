"""Team-level bullpen stability and recent churn intelligence.

This layer describes whether the current bullpen group has been stable in
recent usage or whether the usage picture is changing. It does not infer
transactions, roster moves, performance quality, or future availability.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from models.game_log import GameLog
from services.availability import STATUS_UNAVAILABLE
from services.availability_reference_date import product_current_date
from services.bullpen_eligibility_vocabulary import record_is_bullpen_eligible
from services.roster_authority import is_off_active_roster
from utils.games_started import RELIEF, UNKNOWN, games_started_state
from utils.innings import decimal_innings_to_outs, log_innings_outs


CAPABILITY = 'bullpen_stability_v1'
LEAGUE_CAPABILITY = 'league_bullpen_stability_v1'
VERSION = '2026-06-18.phase3'

DEFAULT_WINDOW_DAYS = 14
LATE_WINDOW_DAYS = 5
MIN_RECENTLY_USED_BULLPEN_ARMS = 3
STABLE_CORE_MIN_APPEARANCES = 2
STABLE_CORE_MIN_OUTS = 6
MODERATE_NEW_ARM_COUNT = 2
HEAVY_NEW_ARM_COUNT = 4
MODERATE_CHURN_SHARE = 0.25
HEAVY_CHURN_SHARE = 0.50

STATUS_STABLE = 'stable'
STATUS_MODERATE_CHURN = 'moderate_churn'
STATUS_HEAVY_CHURN = 'heavy_churn'
STATUS_LIMITED_READ = 'limited_read'

NO_BULLPEN_LIMITATION = (
    'No bullpen-eligible pitchers were available for Bullpen Stability.'
)
LIMITED_SAMPLE_LIMITATION = (
    'Bullpen Stability is a Limited Read because fewer than three bullpen arms '
    'have recent relief usage in the window.'
)
UNKNOWN_SPLIT_LIMITATION = (
    'Some recent pitching logs are missing gamesStarted, so they are not used '
    'for relief-specific stability reads.'
)
USAGE_PATTERN_LIMITATION = (
    'Bullpen stability uses usage patterns and roster status only; roster-move data is not used.'
)
CURRENT_ASSIGNMENT_LIMITATION = (
    'Bullpen stability uses currently assigned pitchers because game logs do '
    'not yet store team-at-appearance.'
)
SMALL_DENOMINATOR_CHURN_LIMITATION = (
    'Bullpen Stability keeps status conservative because one new/reintroduced '
    'arm in a small recent-used sample is a limited churn signal.'
)
SOURCE_LIMITATIONS = [
    USAGE_PATTERN_LIMITATION,
    CURRENT_ASSIGNMENT_LIMITATION,
]

DEFINITIONS = {
    'active_bullpen_count': (
        'Current bullpen-eligible pitchers not classified as inactive or fully unavailable.'
    ),
    'recently_used_bullpen_count': (
        'Distinct bullpen-eligible pitchers with relief appearances in the analysis window.'
    ),
    'new_or_reintroduced_arm_count': (
        'Relievers whose first relief appearance in the window falls in the final five days '
        'and who have not yet met the stable-core workload threshold.'
    ),
    'inactive_or_unavailable_count': (
        'Current bullpen-eligible pitchers classified as inactive by roster status or fully '
        'Unavailable by the availability read.'
    ),
    'stable_core_count': (
        'Relievers with multiple relief appearances or at least six relief outs in the window.'
    ),
    'churn_share': (
        'New/reintroduced arms divided by recently used bullpen arms.'
    ),
}

METHODOLOGY_NOTES = [
    'Status thresholds are reasoned defaults for explanation, not validated predictive thresholds.',
    'Churn describes recent usage stability, not bullpen quality.',
    'No specific roster-move label is inferred without a roster-move source.',
]


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


def _date_value(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _window(reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    ref = reference_date or product_current_date()
    return ref - timedelta(days=int(window_days or DEFAULT_WINDOW_DAYS) - 1), ref


def _is_regular_season(log: Any) -> bool:
    return _value(log, 'game_type') in (None, '', 'R')


def _is_relief_log(log: Any) -> bool:
    return games_started_state(_value(log, 'games_started')) == RELIEF


def _has_unknown_split(log: Any) -> bool:
    return games_started_state(_value(log, 'games_started')) == UNKNOWN


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


def _pitcher(record: dict[str, Any]) -> Any:
    return record.get('pitcher')


def _pitcher_id(record: dict[str, Any]) -> int | None:
    return (
        record.get('pitcher_id')
        or _value(_pitcher(record), 'id')
        or _value(record.get('pitcher'), 'pitcher_id')
    )


def _is_bullpen_record(record: dict[str, Any]) -> bool:
    return record_is_bullpen_eligible(record)


def _read_key(record: dict[str, Any]) -> str:
    return _nested(record.get('pitcher_labels'), 'read', 'key', default='') or ''


def _availability_status(record: dict[str, Any]) -> str:
    return str((record.get('availability') or {}).get('availability_status') or '')


def _is_fully_unavailable(record: dict[str, Any]) -> bool:
    return (
        is_off_active_roster(record.get('roster_status'))
        or _read_key(record) == 'unavailable'
        or _availability_status(record) == STATUS_UNAVAILABLE
    )


def _team_identity(team):
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _rounded_share(part, total):
    if not total:
        return 0.0
    return round(float(part or 0) / float(total), 2)


def recent_bullpen_stability_logs_by_pitcher(
    pitcher_ids,
    *,
    reference_date=None,
    window_days=DEFAULT_WINDOW_DAYS,
):
    """Fetch recent game logs for current bullpen candidates."""
    ids = [int(pid) for pid in pitcher_ids or [] if pid is not None]
    if not ids:
        return {}

    window_start, ref = _window(reference_date, window_days)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(ids))
        .filter(GameLog.game_type == 'R')
        .filter(GameLog.game_date >= window_start)
        .filter(GameLog.game_date <= ref)
        .all()
    )
    grouped = defaultdict(list)
    for log in logs:
        grouped[log.pitcher_id].append(log)
    return dict(grouped)


def _records(records):
    normalized = []
    for record in records or []:
        if not _is_bullpen_record(record):
            continue
        pitcher_id = _pitcher_id(record)
        if pitcher_id is None:
            continue
        normalized.append({
            'pitcher_id': int(pitcher_id),
            'name': record.get('name') or _value(_pitcher(record), 'full_name'),
            'inactive_or_unavailable': _is_fully_unavailable(record),
            'roster_unavailable': is_off_active_roster(record.get('roster_status')),
            'availability_status': _availability_status(record),
        })
    return normalized


def _usage_by_pitcher(records, logs_by_pitcher, *, reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    window_start, ref = _window(reference_date, window_days)
    record_ids = {record['pitcher_id'] for record in records}
    usage = {}
    unknown_split_rows = 0

    for pitcher_id in record_ids:
        relief_logs = []
        for log in logs_by_pitcher.get(pitcher_id, []) or []:
            game_date = _date_value(_value(log, 'game_date'))
            if game_date is None or game_date < window_start or game_date > ref:
                continue
            if not _is_regular_season(log):
                continue
            if _has_unknown_split(log):
                unknown_split_rows += 1
                continue
            if not _is_relief_log(log):
                continue
            outs = _log_outs(log)
            if outs is None or outs <= 0:
                continue
            relief_logs.append({
                'game_date': game_date,
                'outs': outs,
                'pitches': int(_value(log, 'pitches_thrown', 0) or 0),
            })

        if relief_logs:
            first_date = min(item['game_date'] for item in relief_logs)
            last_date = max(item['game_date'] for item in relief_logs)
            usage[pitcher_id] = {
                'relief_appearances': len(relief_logs),
                'relief_outs': sum(item['outs'] for item in relief_logs),
                'pitches': sum(item['pitches'] for item in relief_logs),
                'first_relief_date': first_date,
                'last_relief_date': last_date,
            }

    return usage, unknown_split_rows, window_start, ref


def _is_stable_core(item):
    return (
        int(item.get('relief_appearances') or 0) >= STABLE_CORE_MIN_APPEARANCES
        or int(item.get('relief_outs') or 0) >= STABLE_CORE_MIN_OUTS
    )


def _is_new_or_reintroduced(item, ref):
    if _is_stable_core(item):
        return False
    first_date = item.get('first_relief_date')
    if first_date is None:
        return False
    late_cutoff = ref - timedelta(days=LATE_WINDOW_DAYS - 1)
    return first_date >= late_cutoff


def _arm_summary(record, item):
    return {
        'pitcher_id': record['pitcher_id'],
        'name': record['name'],
        'relief_appearances': int(item.get('relief_appearances') or 0),
        'relief_outs': int(item.get('relief_outs') or 0),
        'first_relief_date': item['first_relief_date'].isoformat(),
        'last_relief_date': item['last_relief_date'].isoformat(),
    }


def _status(
    *,
    total_bullpen_count,
    recently_used_bullpen_count,
    new_or_reintroduced_arm_count,
    churn_share,
):
    if total_bullpen_count <= 0 or recently_used_bullpen_count < MIN_RECENTLY_USED_BULLPEN_ARMS:
        return STATUS_LIMITED_READ
    if new_or_reintroduced_arm_count < MODERATE_NEW_ARM_COUNT:
        return STATUS_STABLE
    if (
        new_or_reintroduced_arm_count >= HEAVY_NEW_ARM_COUNT
        or churn_share >= HEAVY_CHURN_SHARE
    ):
        return STATUS_HEAVY_CHURN
    if (
        new_or_reintroduced_arm_count >= MODERATE_NEW_ARM_COUNT
        or churn_share >= MODERATE_CHURN_SHARE
    ):
        return STATUS_MODERATE_CHURN
    return STATUS_STABLE


def _summary(status, window_days, stable_core_count, new_or_reintroduced_arm_count):
    stable_word = 'arm' if stable_core_count == 1 else 'arms'
    new_word = 'arm' if new_or_reintroduced_arm_count == 1 else 'arms'
    if status == STATUS_LIMITED_READ:
        return 'Bullpen Stability is a Limited Read because recent relief usage is too thin to describe churn.'
    if status == STATUS_STABLE:
        return (
            f'The bullpen usage picture has been stable, with {stable_core_count} stable-core {stable_word} '
            f'and {new_or_reintroduced_arm_count} new/reintroduced {new_word} in the last {window_days} days.'
        )
    label = 'heavy churn' if status == STATUS_HEAVY_CHURN else 'moderate churn'
    return (
        f'The bullpen has shown {label}, with {new_or_reintroduced_arm_count} {new_word} '
        'newly entering or re-entering the recent usage picture.'
    )


def build_team_bullpen_stability(
    records,
    *,
    logs_by_pitcher=None,
    team=None,
    reference_date=None,
    window_days=DEFAULT_WINDOW_DAYS,
):
    """Build serializable Bullpen Stability intelligence for one team."""
    normalized = _records(records)
    usage, unknown_split_rows, window_start, ref = _usage_by_pitcher(
        normalized,
        logs_by_pitcher or {},
        reference_date=reference_date,
        window_days=window_days,
    )

    records_by_id = {record['pitcher_id']: record for record in normalized}
    stable_core = []
    new_or_reintroduced = []
    for pitcher_id, item in usage.items():
        record = records_by_id.get(pitcher_id)
        if record is None:
            continue
        if _is_stable_core(item):
            stable_core.append(_arm_summary(record, item))
        if _is_new_or_reintroduced(item, ref):
            new_or_reintroduced.append(_arm_summary(record, item))

    stable_core.sort(key=lambda item: (str(item.get('name') or '').lower(), item.get('pitcher_id') or 0))
    new_or_reintroduced.sort(
        key=lambda item: (str(item.get('first_relief_date') or ''), str(item.get('name') or '').lower())
    )

    total_bullpen_count = len(normalized)
    recently_used_bullpen_count = len(usage)
    inactive_or_unavailable_count = sum(
        1
        for record in normalized
        if record['inactive_or_unavailable']
    )
    active_bullpen_count = max(total_bullpen_count - inactive_or_unavailable_count, 0)
    new_or_reintroduced_arm_count = len(new_or_reintroduced)
    stable_core_count = len(stable_core)
    churn_share = _rounded_share(new_or_reintroduced_arm_count, recently_used_bullpen_count)
    status = _status(
        total_bullpen_count=total_bullpen_count,
        recently_used_bullpen_count=recently_used_bullpen_count,
        new_or_reintroduced_arm_count=new_or_reintroduced_arm_count,
        churn_share=churn_share,
    )

    limitations = []
    if total_bullpen_count <= 0:
        limitations.append(NO_BULLPEN_LIMITATION)
    if recently_used_bullpen_count < MIN_RECENTLY_USED_BULLPEN_ARMS:
        limitations.append(LIMITED_SAMPLE_LIMITATION)
    if (
        new_or_reintroduced_arm_count == 1
        and recently_used_bullpen_count <= MIN_RECENTLY_USED_BULLPEN_ARMS
    ):
        limitations.append(SMALL_DENOMINATOR_CHURN_LIMITATION)
    if unknown_split_rows > 0:
        limitations.append(UNKNOWN_SPLIT_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': team.get('team_abbreviation') if isinstance(team, dict) else None,
        **_team_identity(team),
        'status': status,
        'window_days': int(window_days or DEFAULT_WINDOW_DAYS),
        'reference_date': ref.isoformat() if ref else None,
        'window_start': window_start.isoformat() if window_start else None,
        'active_bullpen_count': active_bullpen_count,
        'total_bullpen_count': total_bullpen_count,
        'recently_used_bullpen_count': recently_used_bullpen_count,
        'new_or_reintroduced_arm_count': new_or_reintroduced_arm_count,
        'inactive_or_unavailable_count': inactive_or_unavailable_count,
        'stable_core_count': stable_core_count,
        'churn_share': churn_share,
        'unknown_split_row_count': unknown_split_rows,
        'stable_core': stable_core,
        'new_or_reintroduced_arms': new_or_reintroduced,
        'definitions': dict(DEFINITIONS),
        'thresholds': {
            'window_days': int(window_days or DEFAULT_WINDOW_DAYS),
            'late_window_days': LATE_WINDOW_DAYS,
            'min_recently_used_bullpen_arms': MIN_RECENTLY_USED_BULLPEN_ARMS,
            'stable_core_min_appearances': STABLE_CORE_MIN_APPEARANCES,
            'stable_core_min_outs': STABLE_CORE_MIN_OUTS,
            'moderate_new_arm_count': MODERATE_NEW_ARM_COUNT,
            'heavy_new_arm_count': HEAVY_NEW_ARM_COUNT,
            'moderate_churn_share': MODERATE_CHURN_SHARE,
            'heavy_churn_share': HEAVY_CHURN_SHARE,
        },
        'methodology_notes': list(METHODOLOGY_NOTES),
        'source_limitations': list(SOURCE_LIMITATIONS),
        'summary': _summary(
            status,
            int(window_days or DEFAULT_WINDOW_DAYS),
            stable_core_count,
            new_or_reintroduced_arm_count,
        ),
        'limitations': limitations,
    }


def build_league_bullpen_stability_payload(team_items):
    teams = list(team_items or [])
    return {
        'capability': LEAGUE_CAPABILITY,
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
    'CURRENT_ASSIGNMENT_LIMITATION',
    'DEFAULT_WINDOW_DAYS',
    'LEAGUE_CAPABILITY',
    'LIMITED_SAMPLE_LIMITATION',
    'NO_BULLPEN_LIMITATION',
    'SMALL_DENOMINATOR_CHURN_LIMITATION',
    'SOURCE_LIMITATIONS',
    'STATUS_HEAVY_CHURN',
    'STATUS_LIMITED_READ',
    'STATUS_MODERATE_CHURN',
    'STATUS_STABLE',
    'UNKNOWN_SPLIT_LIMITATION',
    'USAGE_PATTERN_LIMITATION',
    'VERSION',
    'build_league_bullpen_stability_payload',
    'build_team_bullpen_stability',
    'recent_bullpen_stability_logs_by_pitcher',
]
