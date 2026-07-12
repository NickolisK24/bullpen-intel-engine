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
from models.scheduled_game import ScheduledGame
from models.team_game_pitching_split import TeamGamePitchingSplit
from services.availability_reference_date import product_current_date
from services.game_shape import (
    BULK_FOLLOWER_MIN_OUTS,
    OPENER_MAX_OUTS,
    SHAPE_BULLPEN_GAME,
    SHAPE_NORMAL_START,
    SHAPE_OPENER_BULK_GAME,
    SHAPE_SHORT_START,
    game_shape_of,
)
from utils.games_started import RELIEF, START, games_started_state
from utils.innings import log_innings_outs, outs_to_decimal_innings


CAPABILITY = 'rotation_support_pressure_v1'
LEAGUE_CAPABILITY = 'league_rotation_support_pressure_v1'
VERSION = '2026-06-18.phase2'

DEFAULT_WINDOW_DAYS = 7
SHORT_START_OUTS = 15
SHORT_START_MAX_OUTS = SHORT_START_OUTS - 1
MIN_ANALYZED_GAMES = 3
MIN_COMPLETE_TEAM_GAME_OUTS = 24
MATERIAL_EXCLUDED_GAME_SHARE = 0.25

# Game-shape buckets for a classified team game (see services.game_shape). Only
# rotation starts drive starter depth, short-start rate, and rotation-driven
# bullpen burden; opener/bulk and bullpen games are tracked separately.
KIND_ROTATION_START = 'rotation_start'
KIND_OPENER_BULK = 'opener_bulk_game'
KIND_BULLPEN_GAME = 'bullpen_game'

STATUS_SUPPORTIVE = 'supportive'
STATUS_NEUTRAL = 'neutral'
STATUS_MODERATE = 'moderate_pressure'
STATUS_HEAVY = 'heavy_pressure'
STATUS_LIMITED = 'limited_read'

# Transitional compatibility statuses only. Phase 0J frontend closeout retires
# their public display in favor of factual starter-length language.

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
HISTORICAL_TEAM_ATTRIBUTION_LIMITATION = (
    'Starter exposure uses stored team-game pitching split rows keyed by team and game, not the pitcher current roster assignment.'
)
INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION = (
    'Rotation Support Pressure is a Limited Read because some final team games lack complete stored team-at-game pitching splits.'
)
INCOMPLETE_STARTER_IDENTIFICATION_LIMITATION = (
    'Some recent team games are excluded because starter identity is incomplete or ambiguous.'
)
PARTIAL_SOURCE_COVERAGE_LIMITATION = (
    'Rotation Support Pressure is a Limited Read because the stored team-game source window is partial.'
)
OPENER_BULK_LIMITATION = (
    'Opener/bulk and bullpen games are classified by game shape: an opener is not '
    'counted as a rotation start, and bulk-follower innings are tracked separately '
    'rather than as rotation-driven bullpen pressure.'
)
SOURCE_LIMITATIONS = [
    CURRENT_ASSIGNMENT_LIMITATION,
    OPENER_BULK_LIMITATION,
]
SPLIT_SOURCE_LIMITATIONS = [
    HISTORICAL_TEAM_ATTRIBUTION_LIMITATION,
    OPENER_BULK_LIMITATION,
]

DEFINITIONS = {
    'games_in_window': (
        'Distinct games represented by currently assigned pitchers in the analysis window.'
    ),
    'games_analyzed': (
        'Rotation starts (normal or short) with usable starter/bullpen split data. '
        'Opener/bulk and bullpen games are tracked separately; excluded games are not counted here.'
    ),
    'games_excluded': (
        'Games in the window excluded because starter/relief workload data is incomplete or ambiguous.'
    ),
    'opener_bulk_games': (
        'Games classified as opener/bulk by game shape. The opener is not counted as a rotation '
        'start, and the bulk follower is separated from rotation-driven bullpen burden.'
    ),
    'bullpen_games': (
        'Games with no credited starter, classified as bullpen games by game shape and tracked '
        'separately rather than excluded as incomplete or ambiguous data.'
    ),
    'bulk_follower_outs': (
        'Outs recorded by bulk-length followers in opener/bulk games, kept visible but separated '
        'from rotation-driven bullpen pressure.'
    ),
    'starter_outs': (
        'Outs recorded by the pitcher with games_started == 1 in analyzed rotation starts.'
    ),
    'bullpen_outs_required': (
        'Relief outs recorded by pitchers with games_started == 0 in analyzed rotation starts.'
    ),
    'short_start_count': (
        'Analyzed starts where the starter completed fewer than 15 outs, or five innings.'
    ),
    'short_start_rate': (
        'Short starts divided by analyzed starts. Games with ambiguous starter/relief splits are excluded.'
    ),
}
SPLIT_DEFINITIONS = {
    **DEFINITIONS,
    'games_in_window': (
        'Distinct final team games represented by scheduled-game rows or stored team-game pitching split rows in the analysis window.'
    ),
    'games_excluded': (
        'Games in the window excluded because stored team-game pitching splits, starter identity, or game-shape proof are incomplete.'
    ),
    'starter_outs': (
        'Outs recorded by the stored starter in complete team-game pitching split rows for analyzed rotation starts.'
    ),
    'bullpen_outs_required': (
        'Stored relief outs for analyzed rotation starts, from team-game pitching split rows.'
    ),
    'short_start_count': (
        'Analyzed starts where the stored starter completed fewer than 15 outs, or five innings.'
    ),
}

METHODOLOGY_NOTES = [
    'Status thresholds are reasoned defaults for explanation, not validated predictive thresholds.',
    'Game logs do not store team-at-appearance, so this read groups logs by current pitcher team assignment.',
    'Opener/bulk and bullpen games are classified by game shape; openers are excluded from '
    'starter-depth and short-start reads, and bulk-follower innings are tracked separately.',
]
SPLIT_METHODOLOGY_NOTES = [
    'Status thresholds are reasoned defaults for explanation, not validated predictive thresholds.',
    'The public starter-exposure window uses stored team-game pitching split rows keyed by team and game.',
    'Expected final team games come from scheduled-game rows when available; missing or partial split rows limit the read.',
    'Opener/bulk and bullpen games are separated only when game-shape evidence reconciles to the stored team-game split.',
]

REASON_NO_RECENT_GAMES = 'no_recent_games'
REASON_INSUFFICIENT_TRUSTWORTHY_GAMES = 'insufficient_trustworthy_games'
REASON_INCOMPLETE_HISTORICAL_TEAM_ATTRIBUTION = 'incomplete_historical_team_attribution'
REASON_INCOMPLETE_STARTER_IDENTIFICATION = 'incomplete_starter_identification'
REASON_OPENER_BULK_HANDLING = 'opener_bulk_handling'
REASON_PARTIAL_SOURCE_COVERAGE = 'partial_source_coverage'
REASON_MATERIAL_EXCLUSION_SHARE = 'material_exclusion_share'


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


def recent_team_game_splits(team_id, *, reference_date=None, window_days=DEFAULT_WINDOW_DAYS):
    """Fetch the split-backed public source window for starter exposure.

    Scheduled final team games provide the expected team-at-game set when present.
    Stored ``team_game_pitching_splits`` rows provide starter/bullpen facts keyed
    by team and game. No pitcher current-team or active filter is used to decide
    whether a historical team game belongs in the window.
    """
    if team_id is None:
        return {
            'splits': [],
            'expected_game_pks': [],
            'source_window_partial': False,
            'expected_game_source': 'missing_team',
        }

    window_start, ref = _window(reference_date, window_days)
    expected_rows = (
        ScheduledGame.query
        .filter(ScheduledGame.team_id == team_id)
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .filter(ScheduledGame.game_type == 'R')
        .filter(ScheduledGame.game_date >= window_start)
        .filter(ScheduledGame.game_date <= ref)
        .order_by(ScheduledGame.game_date.asc(), ScheduledGame.game_pk.asc())
        .all()
    )
    split_rows = (
        TeamGamePitchingSplit.query
        .filter(TeamGamePitchingSplit.team_id == team_id)
        .filter(TeamGamePitchingSplit.game_type == 'R')
        .filter(TeamGamePitchingSplit.game_date >= window_start)
        .filter(TeamGamePitchingSplit.game_date <= ref)
        .order_by(TeamGamePitchingSplit.game_date.asc(), TeamGamePitchingSplit.mlb_game_pk.asc())
        .all()
    )
    expected_game_pks = _ordered_unique(
        row.game_pk for row in expected_rows if row.game_pk is not None
    )
    if expected_game_pks:
        expected_game_source = 'scheduled_final_team_games'
        source_window_partial = False
    else:
        expected_game_pks = _ordered_unique(
            row.mlb_game_pk for row in split_rows if row.mlb_game_pk is not None
        )
        expected_game_source = 'team_game_pitching_splits'
        source_window_partial = bool(split_rows)

    return {
        'splits': split_rows,
        'expected_game_pks': expected_game_pks,
        'source_window_partial': source_window_partial,
        'expected_game_source': expected_game_source,
        'scheduled_final_game_count': len(expected_rows),
        'split_row_count': len(split_rows),
    }


def _ordered_unique(values):
    seen = []
    for value in values or []:
        if value not in seen:
            seen.append(value)
    return seen


def _int_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _split_reason_codes(split):
    raw = _value(split, 'split_reason_codes') or []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if item]
    return [str(raw)] if raw else []


def _starter_identity_reason(split):
    codes = set(_split_reason_codes(split))
    if 'starter_identity_ambiguous' in codes:
        return 'starter_identity_ambiguous'
    if 'starter_games_started_unknown' in codes:
        return 'starter_games_started_unknown'
    return 'starter_identity_unknown'


def _split_row_reason(split):
    codes = _split_reason_codes(split)
    critical = [
        'starter_outs_unknown',
        'bullpen_outs_unknown',
        'total_team_outs_unknown',
        'no_team_game_logs',
        'suspended_resumed_ambiguous',
    ]
    for code in critical:
        if code in codes:
            return code
    status = _value(split, 'split_completeness_status')
    if status == TeamGamePitchingSplit.STATUS_UNKNOWN:
        return 'split_row_unknown'
    if status == TeamGamePitchingSplit.STATUS_PARTIAL:
        return 'split_row_partial'
    return 'split_row_incomplete'


def _verified_team_game_logs_for_split(split):
    team_id = _value(split, 'team_id')
    game_pk = _value(split, 'mlb_game_pk')
    if team_id is None or game_pk is None:
        return []

    logs = (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(GameLog.mlb_game_pk == game_pk)
        .filter(GameLog.game_type == 'R')
        .filter(Pitcher.team_id == team_id)
        .all()
    )
    if not logs:
        return []

    outs = [_log_outs(log) for log in logs]
    if any(value is None for value in outs):
        return []
    expected_total = _int_value(_value(split, 'total_team_outs'))
    if expected_total is not None and sum(outs) != expected_total:
        return []

    starter_pitcher_id = _value(split, 'starter_pitcher_id')
    starter_outs = _int_value(_value(split, 'starter_outs_recorded'))
    if starter_pitcher_id is not None and starter_outs is not None:
        starter_matches = [
            log for log in logs
            if _value(log, 'pitcher_id') == starter_pitcher_id
            and games_started_state(_value(log, 'games_started')) == START
            and _log_outs(log) == starter_outs
        ]
        if not starter_matches:
            return []

    return logs


def _verified_shape_for_split(split):
    logs = _verified_team_game_logs_for_split(split)
    if not logs:
        return None, []
    return game_shape_of(logs), logs


def _relief_logs_with_outs(logs):
    rows = []
    for log in logs or []:
        if games_started_state(_value(log, 'games_started')) != RELIEF:
            continue
        outs = _log_outs(log)
        if outs is not None:
            rows.append((log, outs))
    return rows


def _classify_split_team_game(split):
    starter_status = _value(split, 'starter_identity_status')
    starter_outs = _int_value(_value(split, 'starter_outs_recorded'))
    bullpen_outs = _int_value(_value(split, 'bullpen_outs_recorded'))
    total_outs = _int_value(_value(split, 'total_team_outs'))
    split_status = _value(split, 'split_completeness_status')

    if starter_status != TeamGamePitchingSplit.STARTER_KNOWN:
        shape, logs = _verified_shape_for_split(split)
        if shape == SHAPE_BULLPEN_GAME and total_outs is not None and total_outs >= MIN_COMPLETE_TEAM_GAME_OUTS:
            return {
                'kind': KIND_BULLPEN_GAME,
                'shape': shape,
                'bullpen_game_outs': sum(outs for _log, outs in _relief_logs_with_outs(logs)),
                'total_known_outs': total_outs,
            }, None
        return None, _starter_identity_reason(split)

    if split_status == TeamGamePitchingSplit.STATUS_UNKNOWN:
        return None, _split_row_reason(split)
    if starter_outs is None:
        return None, 'starter_outs_unknown'
    if bullpen_outs is None:
        return None, 'bullpen_outs_unknown'
    if total_outs is None:
        return None, 'total_team_outs_unknown'
    if total_outs < MIN_COMPLETE_TEAM_GAME_OUTS:
        return None, 'incomplete_outs'

    if starter_outs <= OPENER_MAX_OUTS and bullpen_outs >= BULK_FOLLOWER_MIN_OUTS:
        shape, logs = _verified_shape_for_split(split)
        if shape == SHAPE_OPENER_BULK_GAME:
            relief_logs = _relief_logs_with_outs(logs)
            return {
                'kind': KIND_OPENER_BULK,
                'shape': shape,
                'opener_outs': starter_outs,
                'bulk_follower_outs': _bulk_follower_outs(relief_logs),
                'total_known_outs': total_outs,
            }, None
        if shape not in (SHAPE_SHORT_START, SHAPE_NORMAL_START):
            return None, 'opener_bulk_unverified'

    shape = SHAPE_NORMAL_START if starter_outs >= SHORT_START_OUTS else SHAPE_SHORT_START
    return {
        'kind': KIND_ROTATION_START,
        'shape': shape,
        'starter_outs': starter_outs,
        'bullpen_outs_required': bullpen_outs,
        'total_known_outs': total_outs,
        'short_start': starter_outs < SHORT_START_OUTS,
    }, None


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


def _bulk_follower_outs(relief_logs):
    """Outs thrown by bulk-length follower(s) within a confirmed opener/bulk game.

    The game has already been classified ``OPENER_BULK_GAME`` by services.game_shape;
    the bulk arm(s) are the relief appearance(s) covering at least BULK_FOLLOWER_MIN_OUTS,
    matching the classifier's own definition (no second classifier).
    """
    return sum(outs for _log, outs in relief_logs if outs >= BULK_FOLLOWER_MIN_OUTS)


def _classify_team_game(game_logs):
    """Classify one team-game for Rotation Support Pressure.

    Returns ``(record, reason)``. ``record`` carries a ``kind`` describing how the
    game contributes; ``reason`` is set only for genuine data-quality exclusions
    (missing innings, ambiguous splits, incomplete outs). Game Shape decides
    routing so opener/bulk and bullpen games no longer distort starter depth,
    short-start rate, or rotation-driven bullpen burden.
    """
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

    # Genuine data-quality exclusions: real missing/ambiguous data, not a game shape.
    if missing_innings_rows > 0:
        return None, 'missing_innings'
    if unknown_logs:
        return None, 'unknown_split'

    shape = game_shape_of(game_logs)
    relief_outs = sum(outs for _log, outs in relief_logs)

    # Bullpen game: no credited starter by shape. Track separately rather than
    # excluding as generic missing data, so a planned bullpen game is not read as
    # incomplete or ambiguous coverage.
    if shape == SHAPE_BULLPEN_GAME:
        if relief_outs < MIN_COMPLETE_TEAM_GAME_OUTS:
            return None, 'incomplete_outs'
        return {
            'kind': KIND_BULLPEN_GAME,
            'shape': shape,
            'bullpen_game_outs': relief_outs,
            'total_known_outs': relief_outs,
        }, None

    # A rotation read needs exactly one credited starter.
    if len(start_logs) != 1:
        return None, 'multiple_starters' if len(start_logs) > 1 else 'no_starter'

    starter_outs = start_logs[0][1]
    known_outs = starter_outs + relief_outs
    if known_outs < MIN_COMPLETE_TEAM_GAME_OUTS:
        return None, 'incomplete_outs'

    # Opener/bulk game: the credited starter is an opener, not a rotation start.
    # Keep it out of starter-depth and short-start reads; the bulk follower's
    # innings stay visible as transparency but are not rotation-driven pressure.
    if shape == SHAPE_OPENER_BULK_GAME:
        return {
            'kind': KIND_OPENER_BULK,
            'shape': shape,
            'opener_outs': starter_outs,
            'bulk_follower_outs': _bulk_follower_outs(relief_logs),
            'total_known_outs': known_outs,
        }, None

    # NORMAL_START / SHORT_START: a genuine rotation start. Behavior is unchanged
    # from the pre-Game-Shape read.
    return {
        'kind': KIND_ROTATION_START,
        'shape': shape,
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
    shape_counts = Counter()
    rotation_games = []
    opener_bulk_records = []
    bullpen_game_records = []

    for _game_pk, game_logs in grouped.items():
        item, reason = _classify_team_game(game_logs)
        if item is None:
            exclusion_reasons[reason] += 1
            continue
        shape_counts[item['shape']] += 1
        kind = item['kind']
        if kind == KIND_ROTATION_START:
            rotation_games.append(item)
        elif kind == KIND_OPENER_BULK:
            opener_bulk_records.append(item)
        elif kind == KIND_BULLPEN_GAME:
            bullpen_game_records.append(item)

    # Only rotation starts drive starter depth, short-start rate, and rotation-driven
    # bullpen burden. Opener/bulk and bullpen games are tracked separately so a team
    # that uses openers is not read as having short-start rotation pressure.
    games_analyzed = len(rotation_games)
    games_in_window = len(grouped)
    games_excluded = sum(exclusion_reasons.values())
    opener_bulk_games = len(opener_bulk_records)
    bullpen_games = len(bullpen_game_records)

    starter_outs = sum(game['starter_outs'] for game in rotation_games)
    bullpen_outs = sum(game['bullpen_outs_required'] for game in rotation_games)
    short_start_count = sum(1 for game in rotation_games if game['short_start'])
    bulk_follower_outs = sum(game['bulk_follower_outs'] for game in opener_bulk_records)
    bullpen_game_outs = sum(game['bullpen_game_outs'] for game in bullpen_game_records)

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
        'opener_bulk_games': opener_bulk_games,
        'bullpen_games': bullpen_games,
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
        'bulk_follower_outs': bulk_follower_outs,
        'bulk_follower_innings': _round_innings(bulk_follower_outs, 1),
        'bullpen_game_outs': bullpen_game_outs,
        'bullpen_game_innings': _round_innings(bullpen_game_outs, 1),
        'game_shape_distribution': dict(shape_counts),
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


def _append_unique(items, value):
    if value and value not in items:
        items.append(value)


def _split_window_parts(split_window):
    if isinstance(split_window, dict):
        splits = list(split_window.get('splits') or [])
        expected_game_pks = list(split_window.get('expected_game_pks') or [])
        source_window_partial = bool(split_window.get('source_window_partial'))
        expected_game_source = split_window.get('expected_game_source')
        scheduled_final_game_count = int(split_window.get('scheduled_final_game_count') or 0)
        split_row_count = int(split_window.get('split_row_count') or len(splits))
    else:
        splits = list(split_window or [])
        expected_game_pks = _ordered_unique(
            _value(row, 'mlb_game_pk') for row in splits if _value(row, 'mlb_game_pk') is not None
        )
        source_window_partial = False
        expected_game_source = 'caller_supplied_splits'
        scheduled_final_game_count = 0
        split_row_count = len(splits)

    splits = sorted(
        splits,
        key=lambda row: (
            _date_value(_value(row, 'game_date')) or date.min,
            _value(row, 'mlb_game_pk') or 0,
        ),
    )
    if not expected_game_pks:
        expected_game_pks = _ordered_unique(
            _value(row, 'mlb_game_pk') for row in splits if _value(row, 'mlb_game_pk') is not None
        )
    return {
        'splits': splits,
        'expected_game_pks': expected_game_pks,
        'source_window_partial': source_window_partial,
        'expected_game_source': expected_game_source,
        'scheduled_final_game_count': scheduled_final_game_count,
        'split_row_count': split_row_count,
    }


def _split_limitation_reasons(exclusion_reasons, *, games_in_window, games_analyzed, source_window_partial):
    reasons = []
    if games_in_window == 0:
        _append_unique(reasons, REASON_NO_RECENT_GAMES)
    if games_analyzed < MIN_ANALYZED_GAMES:
        _append_unique(reasons, REASON_INSUFFICIENT_TRUSTWORTHY_GAMES)
    if source_window_partial:
        _append_unique(reasons, REASON_PARTIAL_SOURCE_COVERAGE)
    if any(
        reason in exclusion_reasons
        for reason in (
            'split_row_missing',
            'split_row_unknown',
            'split_row_partial',
            'split_row_incomplete',
            'no_team_game_logs',
            'suspended_resumed_ambiguous',
        )
    ):
        _append_unique(reasons, REASON_INCOMPLETE_HISTORICAL_TEAM_ATTRIBUTION)
        _append_unique(reasons, REASON_PARTIAL_SOURCE_COVERAGE)
    if any(
        reason.startswith('starter_identity') or reason == 'starter_games_started_unknown'
        for reason in exclusion_reasons
    ):
        _append_unique(reasons, REASON_INCOMPLETE_STARTER_IDENTIFICATION)
    if any(reason in exclusion_reasons for reason in ('opener_bulk_unverified', 'bullpen_game_unverified')):
        _append_unique(reasons, REASON_OPENER_BULK_HANDLING)
    if games_in_window and sum(exclusion_reasons.values()) / games_in_window > MATERIAL_EXCLUDED_GAME_SHARE:
        _append_unique(reasons, REASON_MATERIAL_EXCLUSION_SHARE)
    return reasons


def _split_limitations(exclusion_reasons, limitation_reasons):
    limitations = []
    if REASON_NO_RECENT_GAMES in limitation_reasons:
        _append_unique(limitations, NO_RECENT_GAMES_LIMITATION)
    if REASON_INSUFFICIENT_TRUSTWORTHY_GAMES in limitation_reasons:
        _append_unique(limitations, LIMITED_SAMPLE_LIMITATION)
    if exclusion_reasons:
        _append_unique(limitations, INCOMPLETE_GAME_DATA_LIMITATION)
    if REASON_INCOMPLETE_HISTORICAL_TEAM_ATTRIBUTION in limitation_reasons:
        _append_unique(limitations, INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION)
    if REASON_INCOMPLETE_STARTER_IDENTIFICATION in limitation_reasons:
        _append_unique(limitations, INCOMPLETE_STARTER_IDENTIFICATION_LIMITATION)
    if REASON_PARTIAL_SOURCE_COVERAGE in limitation_reasons:
        _append_unique(limitations, PARTIAL_SOURCE_COVERAGE_LIMITATION)
    if REASON_MATERIAL_EXCLUSION_SHARE in limitation_reasons:
        _append_unique(limitations, MATERIAL_EXCLUSION_LIMITATION)
    for limitation in SPLIT_SOURCE_LIMITATIONS:
        _append_unique(limitations, limitation)
    return limitations


def build_team_rotation_support_pressure_from_splits(
    split_window,
    *,
    team=None,
    reference_date=None,
    window_days=DEFAULT_WINDOW_DAYS,
):
    """Build public starter-exposure context from stored team-game split rows."""
    parts = _split_window_parts(split_window)
    splits = parts['splits']
    expected_game_pks = parts['expected_game_pks']
    split_by_game = {
        _value(row, 'mlb_game_pk'): row
        for row in splits
        if _value(row, 'mlb_game_pk') is not None
    }
    _, window_ref = _window(reference_date, window_days)
    window_start, ref = _window(window_ref, window_days)

    exclusion_reasons = Counter()
    source_reason_codes = Counter()
    shape_counts = Counter()
    rotation_games = []
    opener_bulk_records = []
    bullpen_game_records = []

    for game_pk in expected_game_pks:
        split = split_by_game.get(game_pk)
        if split is None:
            exclusion_reasons['split_row_missing'] += 1
            continue
        item, reason = _classify_split_team_game(split)
        if item is None:
            exclusion_reasons[reason] += 1
            for code in _split_reason_codes(split):
                source_reason_codes[code] += 1
            continue
        shape_counts[item['shape']] += 1
        kind = item['kind']
        if kind == KIND_ROTATION_START:
            rotation_games.append(item)
        elif kind == KIND_OPENER_BULK:
            opener_bulk_records.append(item)
        elif kind == KIND_BULLPEN_GAME:
            bullpen_game_records.append(item)

    games_in_window = len(expected_game_pks)
    games_analyzed = len(rotation_games)
    games_excluded = sum(exclusion_reasons.values())
    opener_bulk_games = len(opener_bulk_records)
    bullpen_games = len(bullpen_game_records)

    starter_outs = sum(game['starter_outs'] for game in rotation_games)
    bullpen_outs = sum(game['bullpen_outs_required'] for game in rotation_games)
    short_start_count = sum(1 for game in rotation_games if game['short_start'])
    bulk_follower_outs = sum(game['bulk_follower_outs'] for game in opener_bulk_records)
    bullpen_game_outs = sum(game['bullpen_game_outs'] for game in bullpen_game_records)

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
    limitation_reasons = _split_limitation_reasons(
        exclusion_reasons,
        games_in_window=games_in_window,
        games_analyzed=games_analyzed,
        source_window_partial=parts['source_window_partial'],
    )
    limitations = _split_limitations(exclusion_reasons, limitation_reasons)

    bullpen_innings = _round_innings(bullpen_outs, 1)
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
        'games_in_window': games_in_window,
        'games_analyzed': games_analyzed,
        'games_excluded': games_excluded,
        'opener_bulk_games': opener_bulk_games,
        'bullpen_games': bullpen_games,
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
        'bulk_follower_outs': bulk_follower_outs,
        'bulk_follower_innings': _round_innings(bulk_follower_outs, 1),
        'bullpen_game_outs': bullpen_game_outs,
        'bullpen_game_innings': _round_innings(bullpen_game_outs, 1),
        'game_shape_distribution': dict(shape_counts),
        'excluded_game_reasons': dict(exclusion_reasons),
        'source_reason_codes': dict(source_reason_codes),
        'limitation_reasons': limitation_reasons,
        'rows_without_game_pk': 0,
        'definitions': dict(SPLIT_DEFINITIONS),
        'thresholds': {
            'short_start_outs': SHORT_START_OUTS,
            'short_start_max_outs': SHORT_START_MAX_OUTS,
            'min_analyzed_games': MIN_ANALYZED_GAMES,
            'supportive_avg_innings_min': SUPPORTIVE_AVG_INNINGS_MIN,
            'supportive_short_start_rate_max': SUPPORTIVE_SHORT_START_RATE_MAX,
            'moderate_avg_innings_max': MODERATE_AVG_INNINGS_MAX,
            'moderate_short_start_rate_min': MODERATE_SHORT_START_RATE_MIN,
            'heavy_avg_innings_max': HEAVY_AVG_INNINGS_MAX,
            'heavy_short_start_rate_min': HEAVY_SHORT_START_RATE_MIN,
            'material_excluded_game_share': MATERIAL_EXCLUDED_GAME_SHARE,
        },
        'methodology_notes': list(SPLIT_METHODOLOGY_NOTES),
        'source_limitations': list(SPLIT_SOURCE_LIMITATIONS),
        'source_window': {
            'source': 'team_game_pitching_splits',
            'expected_game_source': parts['expected_game_source'],
            'scheduled_final_game_count': parts['scheduled_final_game_count'],
            'split_row_count': parts['split_row_count'],
            'source_window_partial': parts['source_window_partial'],
        },
        'summary': _summary(
            status,
            games_analyzed,
            starter_avg_innings,
            bullpen_innings,
            int(window_days or DEFAULT_WINDOW_DAYS),
        ),
        'limitations': limitations,
    }


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
    'HISTORICAL_TEAM_ATTRIBUTION_LIMITATION',
    'INCOMPLETE_GAME_DATA_LIMITATION',
    'INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION',
    'INCOMPLETE_STARTER_IDENTIFICATION_LIMITATION',
    'LEAGUE_CAPABILITY',
    'LIMITED_SAMPLE_LIMITATION',
    'MATERIAL_EXCLUSION_LIMITATION',
    'NO_RECENT_GAMES_LIMITATION',
    'OPENER_BULK_LIMITATION',
    'PARTIAL_SOURCE_COVERAGE_LIMITATION',
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
    'build_team_rotation_support_pressure_from_splits',
    'recent_team_game_logs',
    'recent_team_game_splits',
]
