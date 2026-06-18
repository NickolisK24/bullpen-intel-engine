"""Team-level Rotation Support Pressure intelligence.

This layer measures how much recent starter workload is pushing innings into
the bullpen. It uses only clear game-log start/relief splits and reports
limitations instead of filling missing game context with assumptions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from utils.games_started import RELIEF, START, games_started_state
from utils.innings import log_innings_outs, outs_to_decimal_innings


CAPABILITY = 'rotation_support_pressure_v1'
LEAGUE_CAPABILITY = 'league_rotation_support_pressure_v1'
VERSION = '2026-06-18.phase2'

DEFAULT_WINDOW_DAYS = 7
SHORT_START_OUTS = 15
MIN_ANALYZED_GAMES = 3
MIN_COMPLETE_TEAM_GAME_OUTS = 24
MATERIAL_EXCLUDED_GAME_SHARE = 0.25

STATUS_SUPPORTIVE = 'supportive'
STATUS_NEUTRAL = 'neutral'
STATUS_MODERATE = 'moderate_pressure'
STATUS_HEAVY = 'heavy_pressure'
STATUS_LIMITED = 'limited_read'

SUPPORTIVE_AVG_INNINGS_MIN = 5.7
SUPPORTIVE_SHORT_START_RATE_MAX = 0.20
MODERATE_AVG_INNINGS_MAX = 5.0
MODERATE_SHORT_START_RATE_MIN = 0.33
HEAVY_AVG_INNINGS_MAX = 4.5
HEAVY_SHORT_START_RATE_MIN = 0.50

NO_RECENT_GAMES_LIMITATION = (
    'No recent team games were available for Rotation Support Pressure.'
)
LIMITED_SAMPLE_LIMITATION = (
    'Rotation Support Pressure is a Limited Read because fewer than three recent team games '
    'have complete starter/relief workload data.'
)
INCOMPLETE_GAME_DATA_LIMITATION = (
    'Some recent team games are excluded because starter/relief workload data is incomplete or ambiguous.'
)
UNKNOWN_SPLIT_LIMITATION = (
    'Some game-log rows are missing gamesStarted, so those games are excluded from starter/relief-specific workload reads.'
)
MATERIAL_EXCLUSION_LIMITATION = (
    'Rotation Support Pressure is a Limited Read because a material share of recent games has incomplete starter/relief workload data.'
)
CURRENT_ASSIGNMENT_LIMITATION = (
    'Rotation support uses currently assigned pitchers because game logs do not yet store team-at-appearance.'
)
OPENER_BULK_LIMITATION = (
    'Credited starters are used as recorded; opener/bulk-reliever roles are not separately inferred.'
)
SOURCE_LIMITATIONS = [
    CURRENT_ASSIGNMENT_LIMITATION,
    OPENER_BULK_LIMITATION,
]

DEFINITIONS = {
    'games_in_window': (
        'Distinct games represented by currently assigned pitchers in the analysis window.'
    ),
    'games_analyzed': (
        'Games with usable starter/bullpen split data. Excluded games are not counted here.'
    ),
    'games_excluded': (
        'Games in the window excluded because starter/relief workload data is incomplete or ambiguous.'
    ),
    'starter_outs': (
        'Outs recorded by the pitcher with games_started == 1 in analyzed team games.'
    ),
    'bullpen_outs_required': (
        'Relief outs recorded by pitchers with games_started == 0 in analyzed team games.'
    ),
    'short_start_count': (
        'Analyzed starts where the starter completed fewer than 15 outs, or five innings.'
    ),
    'short_start_rate': (
        'Short starts divided by analyzed starts. Games with ambiguous starter/relief splits are excluded.'
    ),
}

METHODOLOGY_NOTES = [
    'Status thresholds are reasoned defaults for explanation, not validated predictive thresholds.',
    'Game logs do not store team-at-appearance, so this read groups logs by current pitcher team assignment.',
    'Opener and bulk-reliever roles are not separately inferred from the credited starter flag.',
]


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


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


def _game_type(log: Any):
    return _value(log, 'game_type')


def _is_regular_season(log: Any) -> bool:
    return _game_type(log) in (None, '', 'R')


def _game_pk(log: Any):
    return _value(log, 'mlb_game_pk')


def _log_outs(log: Any) -> int | None:
    if isinstance(log, dict):
        outs = log.get('innings_pitched_outs')
        if outs is not None:
            try:
                parsed = int(outs)
            except (TypeError, ValueError):
                return None
            return parsed if parsed >= 0 else None
    return log_innings_outs(log)


def _team_identity(team):
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _window(reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    ref = reference_date or product_current_date()
    return ref - timedelta(days=int(window_days or DEFAULT_WINDOW_DAYS) - 1), ref


def recent_team_game_logs(team_id, *, reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    """Fetch recent current-team pitching logs for Rotation Support Pressure."""
    if team_id is None:
        return []

    window_start, ref = _window(reference_date, window_days)
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(Pitcher.team_id == team_id)
        .filter(Pitcher.active == True)
        .filter(GameLog.game_type == 'R')
        .filter(GameLog.game_date >= window_start)
        .filter(GameLog.game_date <= ref)
        .all()
    )


def _logs_by_game(logs, *, reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    window_start, ref = _window(reference_date, window_days)
    grouped = defaultdict(list)
    rows_without_game_pk = 0
    for log in logs or []:
        game_date = _date_value(_value(log, 'game_date'))
        if game_date is None or game_date < window_start or game_date > ref:
            continue
        if not _is_regular_season(log):
            continue
        game_pk = _game_pk(log)
        if game_pk is None:
            rows_without_game_pk += 1
            continue
        grouped[game_pk].append(log)
    return grouped, rows_without_game_pk, window_start, ref


def _analyzed_game(game_logs):
    start_logs = []
    relief_logs = []
    unknown_logs = []
    missing_innings_rows = 0

    for log in game_logs or []:
        state = games_started_state(_value(log, 'games_started'))
        outs = _log_outs(log)
        if outs is None:
            missing_innings_rows += 1
            continue
        if state == START:
            start_logs.append((log, outs))
        elif state == RELIEF:
            relief_logs.append((log, outs))
        else:
            unknown_logs.append((log, outs))

    if missing_innings_rows > 0:
        return None, 'missing_innings'
    if unknown_logs:
        return None, 'unknown_split'
    if len(start_logs) != 1:
        return None, 'multiple_starters' if len(start_logs) > 1 else 'no_starter'

    starter_outs = start_logs[0][1]
    relief_outs = sum(outs for _log, outs in relief_logs)
    known_outs = starter_outs + relief_outs
    if known_outs < MIN_COMPLETE_TEAM_GAME_OUTS:
        return None, 'incomplete_outs'

    return {
        'starter_outs': starter_outs,
        'bullpen_outs_required': relief_outs,
        'total_known_outs': known_outs,
        'short_start': starter_outs < SHORT_START_OUTS,
    }, None


def _round_innings(outs, digits=1):
    return round(outs_to_decimal_innings(outs), digits)


def _round_innings_value(outs, digits=2):
    return round(float(outs or 0) / 3.0, digits)


def _round_rate(part, total):
    if not total:
        return 0.0
    return round(float(part or 0) / float(total), 2)


def _status(games_analyzed, games_in_window, excluded_games, starter_avg_innings, short_start_rate):
    if games_analyzed < MIN_ANALYZED_GAMES:
        return STATUS_LIMITED
    if games_in_window and excluded_games / games_in_window > MATERIAL_EXCLUDED_GAME_SHARE:
        return STATUS_LIMITED
    if starter_avg_innings < HEAVY_AVG_INNINGS_MAX or short_start_rate >= HEAVY_SHORT_START_RATE_MIN:
        return STATUS_HEAVY
    if starter_avg_innings < MODERATE_AVG_INNINGS_MAX or short_start_rate >= MODERATE_SHORT_START_RATE_MIN:
        return STATUS_MODERATE
    if (
        starter_avg_innings >= SUPPORTIVE_AVG_INNINGS_MIN
        and short_start_rate <= SUPPORTIVE_SHORT_START_RATE_MAX
    ):
        return STATUS_SUPPORTIVE
    return STATUS_NEUTRAL


def _summary(status, games_analyzed, starter_avg_innings, bullpen_innings, window_days):
    if games_analyzed <= 0:
        return 'Rotation Support Pressure is a Limited Read because recent starter/relief workload data is incomplete.'
    if status == STATUS_LIMITED:
        return (
            f'The rotation averaged {round(starter_avg_innings, 1)} innings per analyzed start, '
            'but the Rotation Support Pressure read is limited by sample or split coverage.'
        )
    return (
        f'The rotation averaged {round(starter_avg_innings, 1)} innings per start over the last '
        f'{window_days} days, requiring {round(bullpen_innings, 1)} bullpen innings.'
    )


def build_team_rotation_support_pressure(
    logs,
    *,
    team=None,
    reference_date=None,
    window_days=DEFAULT_WINDOW_DAYS,
):
    """Build serializable Rotation Support Pressure for one team."""
    grouped, rows_without_game_pk, window_start, ref = _logs_by_game(
        logs,
        reference_date=reference_date,
        window_days=window_days,
    )
    exclusion_reasons = Counter()
    analyzed_games = []

    for _game_pk, game_logs in grouped.items():
        item, reason = _analyzed_game(game_logs)
        if item is None:
            exclusion_reasons[reason] += 1
            continue
        analyzed_games.append(item)

    games_analyzed = len(analyzed_games)
    games_in_window = len(grouped)
    games_excluded = sum(exclusion_reasons.values())
    starter_outs = sum(game['starter_outs'] for game in analyzed_games)
    bullpen_outs = sum(game['bullpen_outs_required'] for game in analyzed_games)
    short_start_count = sum(1 for game in analyzed_games if game['short_start'])

    starter_avg_outs = starter_outs / games_analyzed if games_analyzed else 0
    starter_avg_innings = _round_innings_value(starter_avg_outs, 2) if games_analyzed else 0.0
    short_start_rate = _round_rate(short_start_count, games_analyzed)
    status = _status(
        games_analyzed,
        games_in_window,
        games_excluded,
        starter_avg_innings,
        short_start_rate,
    )

    limitations = []
    if games_in_window == 0:
        limitations.append(NO_RECENT_GAMES_LIMITATION)
    if games_analyzed < MIN_ANALYZED_GAMES:
        limitations.append(LIMITED_SAMPLE_LIMITATION)
    if games_excluded > 0 or rows_without_game_pk > 0:
        limitations.append(INCOMPLETE_GAME_DATA_LIMITATION)
    if exclusion_reasons.get('unknown_split'):
        limitations.append(UNKNOWN_SPLIT_LIMITATION)
    if games_in_window and games_excluded / games_in_window > MATERIAL_EXCLUDED_GAME_SHARE:
        limitations.append(MATERIAL_EXCLUSION_LIMITATION)

    bullpen_innings = _round_innings(bullpen_outs, 1)
    payload = {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': team.get('team_abbreviation') if isinstance(team, dict) else None,
        **_team_identity(team),
        'status': status,
        'window_days': int(window_days or DEFAULT_WINDOW_DAYS),
        'reference_date': ref.isoformat() if ref else None,
        'window_start': window_start.isoformat() if window_start else None,
        'games_in_window': games_in_window,
        'games_analyzed': games_analyzed,
        'games_excluded': games_excluded,
        'starter_outs': starter_outs,
        'starter_innings': _round_innings(starter_outs, 1),
        'starter_avg_outs': round(starter_avg_outs, 2),
        'starter_avg_innings': starter_avg_innings,
        'bullpen_outs_required': bullpen_outs,
        'bullpen_innings_required': bullpen_innings,
        'bullpen_avg_innings_required': (
            _round_innings_value(bullpen_outs / games_analyzed, 2)
            if games_analyzed
            else 0.0
        ),
        'short_start_count': short_start_count,
        'short_start_rate': short_start_rate,
        'excluded_game_reasons': dict(exclusion_reasons),
        'rows_without_game_pk': rows_without_game_pk,
        'definitions': dict(DEFINITIONS),
        'thresholds': {
            'short_start_outs': SHORT_START_OUTS,
            'min_analyzed_games': MIN_ANALYZED_GAMES,
            'supportive_avg_innings_min': SUPPORTIVE_AVG_INNINGS_MIN,
            'supportive_short_start_rate_max': SUPPORTIVE_SHORT_START_RATE_MAX,
            'moderate_avg_innings_max': MODERATE_AVG_INNINGS_MAX,
            'moderate_short_start_rate_min': MODERATE_SHORT_START_RATE_MIN,
            'heavy_avg_innings_max': HEAVY_AVG_INNINGS_MAX,
            'heavy_short_start_rate_min': HEAVY_SHORT_START_RATE_MIN,
            'material_excluded_game_share': MATERIAL_EXCLUDED_GAME_SHARE,
        },
        'methodology_notes': list(METHODOLOGY_NOTES),
        'source_limitations': list(SOURCE_LIMITATIONS),
        'summary': _summary(
            status,
            games_analyzed,
            starter_avg_innings,
            bullpen_innings,
            int(window_days or DEFAULT_WINDOW_DAYS),
        ),
        'limitations': limitations,
    }
    return payload


def build_league_rotation_support_payload(team_items):
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
    'HEAVY_AVG_INNINGS_MAX',
    'HEAVY_SHORT_START_RATE_MIN',
    'INCOMPLETE_GAME_DATA_LIMITATION',
    'LEAGUE_CAPABILITY',
    'LIMITED_SAMPLE_LIMITATION',
    'MATERIAL_EXCLUSION_LIMITATION',
    'NO_RECENT_GAMES_LIMITATION',
    'OPENER_BULK_LIMITATION',
    'SOURCE_LIMITATIONS',
    'STATUS_HEAVY',
    'STATUS_LIMITED',
    'STATUS_MODERATE',
    'STATUS_NEUTRAL',
    'STATUS_SUPPORTIVE',
    'UNKNOWN_SPLIT_LIMITATION',
    'VERSION',
    'build_league_rotation_support_payload',
    'build_team_rotation_support_pressure',
    'recent_team_game_logs',
]
