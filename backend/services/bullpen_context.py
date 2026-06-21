"""
Bullpen Context Engine V1 foundation.

Internal diagnostic evidence only. This module does not render product copy,
select stories, rank teams, alter observations, or infer causality.
"""

from datetime import date, timedelta

from models.game_log import GameLog
from models.pitcher import Pitcher
from utils.db import db
from utils.games_started import (
    MATERIAL_UNKNOWN_START_LIMITATION,
    UNKNOWN_START_LIMITATION,
    games_started_summary,
    is_relief,
    is_start,
)
from utils.innings import log_innings_decimal
from services.bullpen_concentration_context import (
    BULLPEN_CONCENTRATION_WINDOW_DAYS,
    build_bullpen_concentration_context,
    build_league_bullpen_concentration_baseline,
    empty_bullpen_concentration_context,
)
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_population import current_availability_records
from services.availability_snapshot import latest_fatigue_rows
from services.bullpen_optionality_context import (
    build_bullpen_optionality_context,
    empty_bullpen_optionality_context,
)
from services.bullpen_population import usage_logs_by_pitcher
from services.rotation_context import build_rotation_context
from services.role_stability_context import (
    build_role_stability_context,
    empty_role_stability_context,
)


BULLPEN_CONTEXT_SAMPLE_CAP = 5
BULLPEN_CONTEXT_WINDOW_DAYS = 7
ROTATION_TREND_MIN_DELTA_IP = 0.3

CONTEXT_LIMITATIONS = [
    'Context is descriptive.',
    'Context is not causal proof.',
    'Context does not explain every bullpen state.',
    'Context does not override observations.',
]

CURRENT_TEAM_ASSIGNMENT_LIMITATION = (
    'Context uses pitchers currently assigned to the team; historical team '
    'membership is not modeled separately.'
)
NULL_START_LIMITATION = (
    'Rows missing gamesStarted are excluded from start/relief-specific context.'
)
NO_GAME_LOG_CONTEXT_LIMITATION = (
    'No stored game-log context was found for this team.'
)


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iso(value):
    return value.isoformat() if value else None


def _round(value):
    return round(float(value), 1) if value is not None else None


def _pct_delta(current, previous):
    if previous in (None, 0):
        return None
    return round((current - previous) / previous, 2)


def _reference_date(team_id=None, reference_date=None):
    ref = _as_date(reference_date)
    if ref is not None:
        return ref

    query = db.session.query(db.func.max(GameLog.game_date)).join(
        Pitcher,
        GameLog.pitcher_id == Pitcher.id,
    )
    if team_id is not None:
        query = query.filter(Pitcher.team_id == team_id)
    return query.scalar()


def _window_pair(reference_date):
    if reference_date is None:
        return None
    days = BULLPEN_CONTEXT_WINDOW_DAYS
    return {
        'last_7': {
            'start_date': reference_date - timedelta(days=days - 1),
            'end_date': reference_date,
        },
        'prev_7': {
            'start_date': reference_date - timedelta(days=(days * 2) - 1),
            'end_date': reference_date - timedelta(days=days),
        },
    }


def _serialize_windows(windows):
    if windows is None:
        return None
    return {
        key: {
            'start_date': _iso(value['start_date']),
            'end_date': _iso(value['end_date']),
        }
        for key, value in windows.items()
    }


def _window_days():
    return BULLPEN_CONTEXT_WINDOW_DAYS


def _team_identity(team_id):
    row = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id == team_id)
        .first()
    )
    if row is None:
        return {'team_id': team_id, 'team_name': None, 'team_abbreviation': None}
    return {
        'team_id': row.team_id,
        'team_name': row.team_name,
        'team_abbreviation': row.team_abbreviation,
    }


def _team_logs(team_id, start_date, end_date):
    return (
        GameLog.query
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(
            Pitcher.team_id == team_id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= end_date,
        )
        .all()
    )


def _league_logs(start_date, end_date):
    return (
        GameLog.query
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(
            Pitcher.team_id.isnot(None),
            GameLog.game_date >= start_date,
            GameLog.game_date <= end_date,
        )
        .all()
    )


def _starter_logs(logs):
    return [log for log in logs or [] if is_start(log)]


def _bullpen_logs(logs):
    return [log for log in logs or [] if is_relief(log)]


def _start_signal_state(summary):
    if summary.material_unknown:
        return 'material_unknown'
    if summary.unknown:
        return 'partial'
    return 'complete'


def _start_signal_fields(logs):
    summary = games_started_summary(logs)
    return {
        'start_classification_state': _start_signal_state(summary),
        'unknown_start_rows': summary.unknown,
        'unknown_start_row_share': round(summary.unknown_share, 2),
    }


def _avg_innings(logs):
    values = [
        value
        for value in (log_innings_decimal(log) for log in logs or [])
        if value is not None
    ]
    if not values:
        return None
    return _round(sum(values) / len(values))


def _rotation_trend(last_avg, prev_avg):
    if last_avg is None or prev_avg is None:
        return 'insufficient_data'
    delta = round(last_avg - prev_avg, 1)
    if delta <= -ROTATION_TREND_MIN_DELTA_IP:
        return 'shorter_outings'
    if delta >= ROTATION_TREND_MIN_DELTA_IP:
        return 'longer_outings'
    return 'stable_outings'


def _demand_trend(last_appearances, prev_appearances, last_pitches, prev_pitches):
    if last_appearances == 0 and prev_appearances == 0:
        return 'insufficient_data'

    appearance_delta = last_appearances - prev_appearances
    pitch_delta = last_pitches - prev_pitches
    if (appearance_delta > 0 and pitch_delta >= 0) or (pitch_delta > 0 and appearance_delta >= 0):
        return 'increasing_demand'
    if (appearance_delta < 0 and pitch_delta <= 0) or (pitch_delta < 0 and appearance_delta <= 0):
        return 'decreasing_demand'
    if appearance_delta == 0 and pitch_delta == 0:
        return 'stable_demand'
    return 'mixed_demand'


def _rotation_context(last_logs, prev_logs, windows):
    all_logs = [*(last_logs or []), *(prev_logs or [])]
    layer1 = build_rotation_context(
        all_logs,
        reference_date=windows['last_7']['end_date'] if windows else None,
    )
    signal = _start_signal_fields(all_logs)
    last_starts = _starter_logs(last_logs)
    prev_starts = _starter_logs(prev_logs)
    last_avg = _avg_innings(last_starts)
    prev_avg = _avg_innings(prev_starts)
    trend = _rotation_trend(last_avg, prev_avg)
    delta = None if last_avg is None or prev_avg is None else round(last_avg - prev_avg, 1)
    if signal['start_classification_state'] == 'material_unknown':
        trend = 'insufficient_start_data'
    return {
        'context_available': trend not in ('insufficient_data', 'insufficient_start_data'),
        'evidence_type': 'starter_innings_pitched',
        'window_days': _window_days(),
        'starter_avg_ip_last_7': last_avg,
        'starter_avg_ip_prev_7': prev_avg,
        'starter_starts_last_7': len(last_starts),
        'starter_starts_prev_7': len(prev_starts),
        'delta_ip': delta,
        'trend': trend,
        'windows': _serialize_windows(windows),
        'rotation_avg_ip_7d': layer1['rotation_avg_ip_7d'],
        'rotation_avg_ip_14d': layer1['rotation_avg_ip_14d'],
        'rotation_ip_trend': layer1['rotation_ip_trend'],
        'early_bullpen_entry_rate': layer1['early_bullpen_entry_rate'],
        'bullpen_coverage_ip_7d': layer1['bullpen_coverage_ip_7d'],
        'rotation_games_analyzed_7d': layer1['games_analyzed_7d'],
        'rotation_games_analyzed_14d': layer1['games_analyzed_14d'],
        'rotation_games_excluded_14d': layer1['games_excluded_14d'],
        'rotation_early_bullpen_entry_games_14d': layer1['early_bullpen_entry_games_14d'],
        'rotation_context_layer': layer1,
        **signal,
    }


def _empty_rotation_context(windows=None):
    return {
        'context_available': False,
        'evidence_type': 'starter_innings_pitched',
        'window_days': _window_days(),
        'starter_avg_ip_last_7': None,
        'starter_avg_ip_prev_7': None,
        'starter_starts_last_7': 0,
        'starter_starts_prev_7': 0,
        'delta_ip': None,
        'trend': 'insufficient_data',
        'windows': _serialize_windows(windows),
        'rotation_avg_ip_7d': None,
        'rotation_avg_ip_14d': None,
        'rotation_ip_trend': None,
        'early_bullpen_entry_rate': None,
        'bullpen_coverage_ip_7d': None,
        'rotation_games_analyzed_7d': 0,
        'rotation_games_analyzed_14d': 0,
        'rotation_games_excluded_14d': 0,
        'rotation_early_bullpen_entry_games_14d': 0,
        'rotation_context_layer': None,
        'start_classification_state': 'complete',
        'unknown_start_rows': 0,
        'unknown_start_row_share': 0.0,
    }


def _usage_demand_context(last_logs, prev_logs, windows):
    all_logs = [*(last_logs or []), *(prev_logs or [])]
    signal = _start_signal_fields(all_logs)
    last_bullpen = _bullpen_logs(last_logs)
    prev_bullpen = _bullpen_logs(prev_logs)
    last_appearances = len(last_bullpen)
    prev_appearances = len(prev_bullpen)
    last_pitches = sum(int(log.pitches_thrown or 0) for log in last_bullpen)
    prev_pitches = sum(int(log.pitches_thrown or 0) for log in prev_bullpen)
    trend = _demand_trend(last_appearances, prev_appearances, last_pitches, prev_pitches)
    if signal['start_classification_state'] == 'material_unknown':
        trend = 'insufficient_start_data'
    return {
        'context_available': trend not in ('insufficient_data', 'insufficient_start_data'),
        'evidence_type': 'bullpen_appearance_and_pitch_volume',
        'window_days': _window_days(),
        'bullpen_appearances_last_7': last_appearances,
        'bullpen_appearances_prev_7': prev_appearances,
        'bullpen_pitches_last_7': last_pitches,
        'bullpen_pitches_prev_7': prev_pitches,
        'appearance_delta': last_appearances - prev_appearances,
        'pitch_delta': last_pitches - prev_pitches,
        'appearance_pct_delta': _pct_delta(last_appearances, prev_appearances),
        'pitch_pct_delta': _pct_delta(last_pitches, prev_pitches),
        'unknown_start_rows_excluded': signal['unknown_start_rows'],
        'trend': trend,
        'windows': _serialize_windows(windows),
        **signal,
    }


def _empty_usage_demand_context(windows=None):
    return {
        'context_available': False,
        'evidence_type': 'bullpen_appearance_and_pitch_volume',
        'window_days': _window_days(),
        'bullpen_appearances_last_7': 0,
        'bullpen_appearances_prev_7': 0,
        'bullpen_pitches_last_7': 0,
        'bullpen_pitches_prev_7': 0,
        'appearance_delta': 0,
        'pitch_delta': 0,
        'appearance_pct_delta': None,
        'pitch_pct_delta': None,
        'unknown_start_rows_excluded': 0,
        'trend': 'insufficient_data',
        'windows': _serialize_windows(windows),
        'start_classification_state': 'complete',
        'unknown_start_rows': 0,
        'unknown_start_row_share': 0.0,
    }


def _bullpen_concentration_context(team_logs, reference_date):
    window_start = reference_date - timedelta(days=BULLPEN_CONCENTRATION_WINDOW_DAYS - 1)
    league_baseline = build_league_bullpen_concentration_baseline(
        _league_logs(window_start, reference_date),
        reference_date=reference_date,
    )
    return build_bullpen_concentration_context(
        team_logs,
        reference_date=reference_date,
        league_baseline=league_baseline,
    )


def _empty_bullpen_concentration_context():
    return empty_bullpen_concentration_context()


def _optionality_records(team_id, reference_date):
    rows = latest_fatigue_rows(team_id=team_id)
    return current_availability_records(rows, reference_date=reference_date)


def _bullpen_optionality_context(team_id, reference_date):
    records = _optionality_records(team_id, reference_date)
    pitcher_ids = [
        record['pitcher'].id
        for record in records
        if record.get('pitcher') is not None
    ]
    logs_by_pitcher = usage_logs_by_pitcher(
        pitcher_ids,
        days=ACTIVE_WINDOW_DAYS,
        include_stale=False,
        reference_date=reference_date,
    )
    return build_bullpen_optionality_context(
        records,
        logs_by_pitcher=logs_by_pitcher,
        reference_date=reference_date,
    )


def _empty_bullpen_optionality_context():
    return empty_bullpen_optionality_context()


def _role_stability_context(team_id, reference_date):
    start_date = reference_date - timedelta(days=(BULLPEN_CONCENTRATION_WINDOW_DAYS * 2) - 1)
    return build_role_stability_context(
        _team_logs(team_id, start_date, reference_date),
        reference_date=reference_date,
    )


def _empty_role_stability_context():
    return empty_role_stability_context()


def _availability_context():
    return {
        'context_available': False,
        'reason': 'not_implemented',
        'data_source': None,
    }


def _context_limitations(last_logs, prev_logs):
    limitations = list(CONTEXT_LIMITATIONS)
    limitations.append(CURRENT_TEAM_ASSIGNMENT_LIMITATION)
    summary = games_started_summary([*(last_logs or []), *(prev_logs or [])])
    if summary.unknown:
        limitations.append(NULL_START_LIMITATION)
    if summary.material_unknown:
        limitations.append(MATERIAL_UNKNOWN_START_LIMITATION)
    elif summary.unknown:
        limitations.append(UNKNOWN_START_LIMITATION)
    return limitations


def build_team_bullpen_context(team_id, reference_date=None):
    """
    Evidence contract for one team.

    The output is intentionally diagnostic-only: it supplies supporting context
    that future product work may inspect, but it does not change observations.
    """
    ref = _reference_date(team_id=team_id, reference_date=reference_date)
    windows = _window_pair(ref)
    if windows is None:
        return {
            'team_id': team_id,
            'team': _team_identity(team_id),
            'reference_date': None,
            'data_through_date': None,
            'rotation_context': _empty_rotation_context(),
            'usage_demand_context': _empty_usage_demand_context(),
            'bullpen_concentration_context': _empty_bullpen_concentration_context(),
            'bullpen_optionality_context': _empty_bullpen_optionality_context(),
            'role_stability_context': _empty_role_stability_context(),
            'availability_context': _availability_context(),
            'limitations': [*CONTEXT_LIMITATIONS, NO_GAME_LOG_CONTEXT_LIMITATION],
        }

    last_logs = _team_logs(team_id, windows['last_7']['start_date'], windows['last_7']['end_date'])
    prev_logs = _team_logs(team_id, windows['prev_7']['start_date'], windows['prev_7']['end_date'])
    all_logs = [*last_logs, *prev_logs]

    return {
        'team_id': team_id,
        'team': _team_identity(team_id),
        'reference_date': _iso(ref),
        'data_through_date': _iso(ref),
        'rotation_context': _rotation_context(last_logs, prev_logs, windows),
        'usage_demand_context': _usage_demand_context(last_logs, prev_logs, windows),
        'bullpen_concentration_context': _bullpen_concentration_context(all_logs, ref),
        'bullpen_optionality_context': _bullpen_optionality_context(team_id, ref),
        'role_stability_context': _role_stability_context(team_id, ref),
        'availability_context': _availability_context(),
        'limitations': _context_limitations(last_logs, prev_logs),
    }


def sample_bullpen_context_team_ids(limit=BULLPEN_CONTEXT_SAMPLE_CAP):
    rows = (
        db.session.query(Pitcher.team_id)
        .join(GameLog, GameLog.pitcher_id == Pitcher.id)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .order_by(Pitcher.team_id)
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if row[0] is not None]


def build_league_sample_bullpen_context(limit=BULLPEN_CONTEXT_SAMPLE_CAP):
    team_ids = sample_bullpen_context_team_ids(limit=limit)
    return [build_team_bullpen_context(team_id) for team_id in team_ids]
