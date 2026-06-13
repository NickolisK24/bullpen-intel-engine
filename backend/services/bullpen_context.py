"""
Bullpen Context Engine V1 foundation.

Internal diagnostic evidence only. This module does not render product copy,
select stories, rank teams, alter observations, or infer causality.
"""

from datetime import date, timedelta

from models.game_log import GameLog
from models.pitcher import Pitcher
from utils.db import db


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
    'Rows missing gamesStarted are treated as bullpen appearances for usage '
    'demand only.'
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


def _starter_logs(logs):
    return [log for log in logs or [] if log.games_started == 1]


def _bullpen_logs(logs):
    return [log for log in logs or [] if log.games_started != 1]


def _avg_innings(logs):
    values = [float(log.innings_pitched or 0.0) for log in logs or []]
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
    last_starts = _starter_logs(last_logs)
    prev_starts = _starter_logs(prev_logs)
    last_avg = _avg_innings(last_starts)
    prev_avg = _avg_innings(prev_starts)
    trend = _rotation_trend(last_avg, prev_avg)
    delta = None if last_avg is None or prev_avg is None else round(last_avg - prev_avg, 1)
    return {
        'context_available': trend != 'insufficient_data',
        'evidence_type': 'starter_innings_pitched',
        'starter_avg_ip_last_7': last_avg,
        'starter_avg_ip_prev_7': prev_avg,
        'starter_starts_last_7': len(last_starts),
        'starter_starts_prev_7': len(prev_starts),
        'delta_ip': delta,
        'trend': trend,
        'windows': _serialize_windows(windows),
    }


def _usage_demand_context(last_logs, prev_logs, windows):
    last_bullpen = _bullpen_logs(last_logs)
    prev_bullpen = _bullpen_logs(prev_logs)
    last_appearances = len(last_bullpen)
    prev_appearances = len(prev_bullpen)
    last_pitches = sum(int(log.pitches_thrown or 0) for log in last_bullpen)
    prev_pitches = sum(int(log.pitches_thrown or 0) for log in prev_bullpen)
    trend = _demand_trend(last_appearances, prev_appearances, last_pitches, prev_pitches)
    null_start_rows = sum(
        1
        for log in [*(last_logs or []), *(prev_logs or [])]
        if log.games_started is None
    )
    return {
        'context_available': trend != 'insufficient_data',
        'evidence_type': 'bullpen_appearance_and_pitch_volume',
        'bullpen_appearances_last_7': last_appearances,
        'bullpen_appearances_prev_7': prev_appearances,
        'bullpen_pitches_last_7': last_pitches,
        'bullpen_pitches_prev_7': prev_pitches,
        'appearance_delta': last_appearances - prev_appearances,
        'pitch_delta': last_pitches - prev_pitches,
        'appearance_pct_delta': _pct_delta(last_appearances, prev_appearances),
        'pitch_pct_delta': _pct_delta(last_pitches, prev_pitches),
        'null_start_rows_included_as_bullpen': null_start_rows,
        'trend': trend,
        'windows': _serialize_windows(windows),
    }


def _availability_context():
    return {
        'context_available': False,
        'reason': 'not_implemented',
        'data_source': None,
    }


def _context_limitations(last_logs, prev_logs):
    limitations = list(CONTEXT_LIMITATIONS)
    limitations.append(CURRENT_TEAM_ASSIGNMENT_LIMITATION)
    if any(log.games_started is None for log in [*(last_logs or []), *(prev_logs or [])]):
        limitations.append(NULL_START_LIMITATION)
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
            'rotation_context': {
                'context_available': False,
                'evidence_type': 'starter_innings_pitched',
                'trend': 'insufficient_data',
                'windows': None,
            },
            'usage_demand_context': {
                'context_available': False,
                'evidence_type': 'bullpen_appearance_and_pitch_volume',
                'trend': 'insufficient_data',
                'windows': None,
            },
            'availability_context': _availability_context(),
            'limitations': list(CONTEXT_LIMITATIONS),
        }

    last_logs = _team_logs(team_id, windows['last_7']['start_date'], windows['last_7']['end_date'])
    prev_logs = _team_logs(team_id, windows['prev_7']['start_date'], windows['prev_7']['end_date'])

    return {
        'team_id': team_id,
        'team': _team_identity(team_id),
        'reference_date': _iso(ref),
        'data_through_date': _iso(ref),
        'rotation_context': _rotation_context(last_logs, prev_logs, windows),
        'usage_demand_context': _usage_demand_context(last_logs, prev_logs, windows),
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
