"""
Shared Availability Engine evaluation modes.

Normal API output remains calendar-based current availability. The latest
workload snapshot mode is explicitly non-current and exists only for
admin/development validation and threshold review.
"""

from datetime import date, timedelta

from sqlalchemy import desc

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from utils.db import db


CURRENT_AVAILABILITY_MODE = 'current_availability'
LATEST_WORKLOAD_SNAPSHOT_MODE = 'latest_workload_snapshot'
SNAPSHOT_REFERENCE_STRATEGY = 'per_pitcher_latest_game_date'
SNAPSHOT_WARNING = (
    'Historical workload snapshot for validation only. '
    'Do not treat as current bullpen availability.'
)


def _iso_or_none(value):
    return value.isoformat() if value else None


def _truthy_limit(limit):
    return limit if isinstance(limit, int) and limit > 0 else None


def availability_mode_metadata(mode, records=None, reference_date=None):
    records = list(records or [])
    if mode == LATEST_WORKLOAD_SNAPSHOT_MODE:
        snapshot_date = max(
            (record.get('latest_game_date') for record in records if record.get('latest_game_date')),
            default=None,
        )
        return {
            'mode': LATEST_WORKLOAD_SNAPSHOT_MODE,
            'snapshot_date': _iso_or_none(snapshot_date),
            'reference_strategy': SNAPSHOT_REFERENCE_STRATEGY,
            'is_current_availability': False,
            'warning': SNAPSHOT_WARNING,
        }

    return {
        'mode': CURRENT_AVAILABILITY_MODE,
        'reference_date': _iso_or_none(reference_date or date.today()),
        'is_current_availability': True,
    }


def latest_fatigue_rows(team_id=None, risk_level=None, limit=None, order_by_score=False):
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc'),
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )

    query = (
        db.session.query(FatigueScore, Pitcher)
        .join(
            subq,
            (FatigueScore.pitcher_id == subq.c.pitcher_id)
            & (FatigueScore.calculated_at == subq.c.max_calc),
        )
        .join(Pitcher, FatigueScore.pitcher_id == Pitcher.id)
    )

    if team_id:
        query = query.filter(Pitcher.team_id == team_id)
    if risk_level:
        query = query.filter(FatigueScore.risk_level == risk_level.upper())

    if order_by_score:
        query = query.order_by(desc(FatigueScore.raw_score), Pitcher.full_name)
    else:
        query = query.order_by(Pitcher.team_abbreviation, Pitcher.full_name)

    limit = _truthy_limit(limit)
    if limit:
        query = query.limit(limit)

    return query.all()


def latest_game_date_for(pitcher_id):
    return (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )


def logs_for_availability_window(pitcher_id, reference_date):
    window_start = reference_date - timedelta(days=4)
    return (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= reference_date,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )


def evaluation_date_for_mode(mode, latest_game_date, current_reference_date=None):
    current_reference_date = current_reference_date or date.today()
    if mode == LATEST_WORKLOAD_SNAPSHOT_MODE:
        return latest_game_date or current_reference_date
    return current_reference_date


def classify_fatigue_row(score, pitcher, reference_date=None, mode=CURRENT_AVAILABILITY_MODE):
    current_reference_date = reference_date or date.today()
    latest_game_date = latest_game_date_for(pitcher.id)
    evaluation_date = evaluation_date_for_mode(
        mode,
        latest_game_date=latest_game_date,
        current_reference_date=current_reference_date,
    )
    logs = logs_for_availability_window(pitcher.id, evaluation_date)
    availability = classify_availability(
        score=score,
        game_logs=logs,
        reference_date=evaluation_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )

    return {
        'pitcher_id': pitcher.id,
        'pitcher_name': pitcher.full_name,
        'team': pitcher.team_abbreviation,
        'score': score,
        'pitcher': pitcher,
        'availability': availability,
        'mode': mode,
        'evaluation_date': evaluation_date,
        'latest_game_date': latest_game_date,
    }


def classify_latest_fatigue_rows(rows, reference_date=None, mode=CURRENT_AVAILABILITY_MODE):
    return [
        classify_fatigue_row(score, pitcher, reference_date=reference_date, mode=mode)
        for score, pitcher in rows
    ]
