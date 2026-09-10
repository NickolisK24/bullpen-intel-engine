"""Backend-authored season ERA summaries for public bullpen payloads."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from models.game_log import GameLog
from services.availability_reference_date import product_current_date
from utils.games_started import is_relief
from utils.innings import log_innings_outs, outs_to_decimal_innings


CAPABILITY = 'season_era_v1'
VERSION = '2026-06-16.foundation'
REGULAR_SEASON_GAME_TYPE = 'R'


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_era(value):
    if value is None:
        return None
    return round(float(value), 2)


def era_from_components(earned_runs, innings_outs):
    """Return ERA from raw earned runs and outs, or None with no outs."""
    outs = _safe_int(innings_outs)
    if outs <= 0:
        return None
    return (float(earned_runs or 0) * 27.0) / outs


def _empty_components():
    return {
        'earned_runs': 0,
        'innings_outs': 0,
        'appearances': 0,
        'unknown_innings_rows': 0,
    }


def era_components(logs, *, relief_only=False):
    """
    Aggregate raw ERA inputs.

    Bullpen ERA uses relief-only appearances: games_started == 0. It is
    computed from total earned runs and total outs, not by averaging pitcher
    ERAs. Rows without a clear starter/relief split are excluded from the
    relief-only grain.
    """
    components = _empty_components()
    for log in logs or []:
        if relief_only and not is_relief(log):
            continue
        outs = log_innings_outs(log)
        if outs is None:
            components['unknown_innings_rows'] += 1
            continue
        components['earned_runs'] += _safe_int(_value(log, 'earned_runs'), 0)
        components['innings_outs'] += outs
        components['appearances'] += 1
    return components


def era_line(logs, *, relief_only=False):
    components = era_components(logs, relief_only=relief_only)
    era = era_from_components(
        components['earned_runs'],
        components['innings_outs'],
    )
    return {
        **components,
        'innings': round(outs_to_decimal_innings(components['innings_outs']), 3),
        'era': _round_era(era),
    }


def _season_bounds(reference_date=None):
    ref = reference_date or product_current_date()
    season = ref.year
    return season, date(season, 1, 1), ref


def _pitcher_identity(pitcher):
    return {
        'pitcher_id': _value(pitcher, 'id'),
        'mlb_id': _value(pitcher, 'mlb_id'),
        'name': _value(pitcher, 'full_name'),
        'team_id': _value(pitcher, 'team_id'),
        'team_name': _value(pitcher, 'team_name'),
        'team_abbreviation': _value(pitcher, 'team_abbreviation'),
    }


def _team_identity(pitcher):
    return {
        'team_id': _value(pitcher, 'team_id'),
        'team_name': _value(pitcher, 'team_name'),
        'team_abbreviation': _value(pitcher, 'team_abbreviation'),
    }


def _logs_for_current_season(pitcher_ids, reference_date=None):
    if not pitcher_ids:
        return []
    _season, season_start, season_end = _season_bounds(reference_date)
    return (
        GameLog.query
        .filter(
            GameLog.pitcher_id.in_(pitcher_ids),
            GameLog.game_type == REGULAR_SEASON_GAME_TYPE,
            GameLog.game_date >= season_start,
            GameLog.game_date <= season_end,
        )
        .all()
    )


def _records_by_pitcher(records):
    by_pitcher = {}
    for record in records or []:
        pitcher = _value(record, 'pitcher')
        pitcher_id = _value(pitcher, 'id')
        if pitcher_id is None:
            continue
        by_pitcher[pitcher_id] = record
    return by_pitcher


def build_season_era_payload(availability_records, *, reference_date=None):
    """
    Build season ERA for the governed/current bullpen population.

    Per-pitcher ERA uses each governed pitcher's full regular-season line. Team
    bullpen ERA aggregates those pitchers' relief-only regular-season rows by
    current team assignment.
    """
    season, _season_start, season_end = _season_bounds(reference_date)
    records_by_pitcher = _records_by_pitcher(availability_records)
    pitcher_ids = list(records_by_pitcher)
    logs_by_pitcher = defaultdict(list)
    for log in _logs_for_current_season(pitcher_ids, reference_date=season_end):
        logs_by_pitcher[log.pitcher_id].append(log)

    pitcher_items = []
    team_logs = defaultdict(list)
    team_pitcher_ids = defaultdict(set)
    unknown_relief_split_rows = 0

    for pitcher_id, record in records_by_pitcher.items():
        pitcher = _value(record, 'pitcher')
        logs = logs_by_pitcher.get(pitcher_id, [])
        line = era_line(logs)
        pitcher_items.append({
            **_pitcher_identity(pitcher),
            'season': season,
            'source': 'game_logs',
            **line,
        })

        team_id = _value(pitcher, 'team_id')
        if team_id is not None:
            team_logs[team_id].extend(logs)
            team_pitcher_ids[team_id].add(pitcher_id)
            unknown_relief_split_rows += sum(
                1
                for log in logs
                if _value(log, 'games_started') is None
            )

    team_lookup = {}
    for record in records_by_pitcher.values():
        pitcher = _value(record, 'pitcher')
        team_id = _value(pitcher, 'team_id')
        if team_id is not None and team_id not in team_lookup:
            team_lookup[team_id] = _team_identity(pitcher)

    bullpen_items = []
    for team_id, logs in team_logs.items():
        line = era_line(logs, relief_only=True)
        bullpen_items.append({
            **team_lookup.get(team_id, {'team_id': team_id}),
            'season': season,
            'source': 'game_logs.relief_only',
            'pitcher_count': len(team_pitcher_ids[team_id]),
            **line,
        })

    pitcher_items.sort(key=lambda item: (
        item.get('team_abbreviation') or '',
        item.get('name') or '',
        item.get('pitcher_id') or 0,
    ))
    bullpen_items.sort(key=lambda item: (
        item.get('team_abbreviation') or '',
        item.get('team_id') or 0,
    ))

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'season': season,
        'reference_date': season_end.isoformat() if season_end else None,
        'definitions': {
            'pitcher_season_era': (
                'All regular-season appearances for each governed bullpen pitcher: '
                'earned_runs * 27 / innings_outs.'
            ),
            'bullpen_season_era': (
                'Current governed bullpen pitchers only, relief appearances only '
                '(games_started == 0), aggregated from raw earned runs and outs.'
            ),
        },
        'limitations': [
            'Bullpen ERA is innings-weighted from raw earned runs and outs; it is not an average of pitcher ERAs.',
            'Rows without a clear games_started value are excluded from bullpen relief-only ERA.',
            'Game logs do not store team-at-appearance, so bullpen ERA is grouped by current pitcher team assignment.',
        ],
        'pitchers': pitcher_items,
        'bullpens': bullpen_items,
        'unknown_relief_split_rows': unknown_relief_split_rows,
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'build_season_era_payload',
    'era_components',
    'era_from_components',
    'era_line',
]
