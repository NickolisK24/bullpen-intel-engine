"""
Shared Availability Engine evaluation modes.

Normal API output remains calendar-based current availability. The latest
workload snapshot mode is explicitly non-current and exists only for
admin/development validation and threshold review.
"""

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import desc, or_

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from services.availability import (
    ACTIVE_WINDOW_DAYS,
    CONFIDENCE_LOW,
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    classify_availability,
)
from services.availability_explanations import (
    FETCH_FAILED_WORKLOAD_LIMITATION,
    FETCH_FAILED_WORKLOAD_REASON,
)
from services.availability_reference_date import product_current_date
from utils.db import db


CURRENT_AVAILABILITY_MODE = 'current_availability'
LATEST_WORKLOAD_SNAPSHOT_MODE = 'latest_workload_snapshot'
SNAPSHOT_REFERENCE_STRATEGY = 'per_pitcher_latest_game_date'
SNAPSHOT_WARNING = (
    'Historical workload snapshot for validation only. '
    'Do not treat as current bullpen availability.'
)
WORKLOAD_FETCH_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'


def _iso_or_none(value):
    return value.isoformat() if value else None


def _append_unique(items, value):
    if value not in items:
        items.append(value)


def _unresolved_workload_fetch_failure_refs(pitchers):
    refs = [
        str(pitcher.mlb_id)
        for pitcher in pitchers
        if getattr(pitcher, 'mlb_id', None) is not None
    ]
    if not refs:
        return set()
    rows = (
        db.session.query(SyncFailure.entity_ref)
        .filter(SyncFailure.entity_type == WORKLOAD_FETCH_FAILURE_ENTITY_TYPE)
        .filter(SyncFailure.resolved.is_(False))
        .filter(SyncFailure.entity_ref.in_(refs))
        .all()
    )
    return {row[0] for row in rows}


def _apply_workload_fetch_failure(availability):
    updated = dict(availability or {})
    if updated.get('availability_status') == STATUS_AVAILABLE:
        updated['availability_status'] = STATUS_MONITOR
    elif not updated.get('availability_status'):
        updated['availability_status'] = STATUS_MONITOR
    updated['confidence'] = CONFIDENCE_LOW
    updated['data_state'] = 'incomplete'

    reasons = list(updated.get('reasons') or [])
    _append_unique(reasons, FETCH_FAILED_WORKLOAD_REASON)
    updated['reasons'] = reasons

    limitations = list(updated.get('limitations') or [])
    _append_unique(limitations, FETCH_FAILED_WORKLOAD_LIMITATION)
    updated['limitations'] = limitations

    inputs = dict(updated.get('inputs') or {})
    inputs['freshness_state'] = 'incomplete'
    inputs['workload_fetch_failed'] = True
    updated['inputs'] = inputs
    return updated


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
        'reference_date': _iso_or_none(reference_date or product_current_date()),
        'is_current_availability': True,
    }


def latest_fatigue_rows(
    team_id=None,
    risk_level=None,
    limit=None,
    order_by_score=False,
    calculated_at_lte=None,
):
    score_scope = db.session.query(FatigueScore)
    if calculated_at_lte is not None:
        score_scope = score_scope.filter(FatigueScore.calculated_at <= calculated_at_lte)
    score_scope = score_scope.subquery()

    subq = (
        db.session.query(
            score_scope.c.pitcher_id,
            db.func.max(score_scope.c.calculated_at).label('max_calc'),
        )
        .group_by(score_scope.c.pitcher_id)
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
        .filter(or_(GameLog.pitches_thrown > 0, GameLog.innings_pitched_outs > 0))
        .scalar()
    )


def latest_game_dates_for(pitcher_ids):
    pitcher_ids = [pitcher_id for pitcher_id in pitcher_ids if pitcher_id is not None]
    if not pitcher_ids:
        return {}

    rows = (
        db.session.query(
            GameLog.pitcher_id,
            db.func.max(GameLog.game_date),
        )
        .filter(GameLog.pitcher_id.in_(pitcher_ids))
        .filter(or_(GameLog.pitches_thrown > 0, GameLog.innings_pitched_outs > 0))
        .group_by(GameLog.pitcher_id)
        .all()
    )
    return {pitcher_id: latest_game_date for pitcher_id, latest_game_date in rows}


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


def logs_for_availability_windows(pitcher_ids, evaluation_dates):
    pitcher_ids = [pitcher_id for pitcher_id in pitcher_ids if pitcher_id is not None]
    if not pitcher_ids:
        return {}

    valid_dates = [
        evaluation_date
        for evaluation_date in evaluation_dates.values()
        if evaluation_date is not None
    ]
    if not valid_dates:
        return {pitcher_id: [] for pitcher_id in pitcher_ids}

    earliest_window_start = min(valid_dates) - timedelta(days=4)
    latest_window_end = max(valid_dates)
    rows = (
        GameLog.query
        .filter(
            GameLog.pitcher_id.in_(pitcher_ids),
            GameLog.game_date >= earliest_window_start,
            GameLog.game_date <= latest_window_end,
        )
        .order_by(GameLog.pitcher_id, desc(GameLog.game_date))
        .all()
    )

    grouped = defaultdict(list)
    for log in rows:
        evaluation_date = evaluation_dates.get(log.pitcher_id)
        if evaluation_date is None:
            continue

        window_start = evaluation_date - timedelta(days=4)
        if window_start <= log.game_date <= evaluation_date:
            grouped[log.pitcher_id].append(log)

    return {pitcher_id: grouped.get(pitcher_id, []) for pitcher_id in pitcher_ids}


def evaluation_date_for_mode(mode, latest_game_date, current_reference_date=None):
    current_reference_date = current_reference_date or product_current_date()
    if mode == LATEST_WORKLOAD_SNAPSHOT_MODE:
        return latest_game_date or current_reference_date
    return current_reference_date


def _classified_record(
    score,
    pitcher,
    latest_game_date,
    evaluation_date,
    logs,
    mode,
    workload_fetch_failed=False,
):
    availability = classify_availability(
        score=score,
        game_logs=logs,
        reference_date=evaluation_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )
    if mode == CURRENT_AVAILABILITY_MODE and workload_fetch_failed:
        availability = _apply_workload_fetch_failure(availability)

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


def classify_fatigue_row(score, pitcher, reference_date=None, mode=CURRENT_AVAILABILITY_MODE):
    current_reference_date = reference_date or product_current_date()
    latest_game_date = latest_game_date_for(pitcher.id)
    evaluation_date = evaluation_date_for_mode(
        mode,
        latest_game_date=latest_game_date,
        current_reference_date=current_reference_date,
    )
    logs = logs_for_availability_window(pitcher.id, evaluation_date)
    return _classified_record(
        score=score,
        pitcher=pitcher,
        latest_game_date=latest_game_date,
        evaluation_date=evaluation_date,
        logs=logs,
        mode=mode,
        workload_fetch_failed=(
            mode == CURRENT_AVAILABILITY_MODE
            and str(pitcher.mlb_id) in _unresolved_workload_fetch_failure_refs([pitcher])
        ),
    )


def classify_fatigue_rows(rows, reference_date=None, mode=CURRENT_AVAILABILITY_MODE):
    rows = list(rows or [])
    current_reference_date = reference_date or product_current_date()
    pitcher_ids = [pitcher.id for _score, pitcher in rows]
    latest_game_dates = latest_game_dates_for(pitcher_ids)
    evaluation_dates = {
        pitcher.id: evaluation_date_for_mode(
            mode,
            latest_game_date=latest_game_dates.get(pitcher.id),
            current_reference_date=current_reference_date,
        )
        for _score, pitcher in rows
    }
    logs_by_pitcher = logs_for_availability_windows(pitcher_ids, evaluation_dates)
    fetch_failure_refs = (
        _unresolved_workload_fetch_failure_refs([pitcher for _score, pitcher in rows])
        if mode == CURRENT_AVAILABILITY_MODE
        else set()
    )

    return [
        _classified_record(
            score=score,
            pitcher=pitcher,
            latest_game_date=latest_game_dates.get(pitcher.id),
            evaluation_date=evaluation_dates[pitcher.id],
            logs=logs_by_pitcher.get(pitcher.id, []),
            mode=mode,
            workload_fetch_failed=str(pitcher.mlb_id) in fetch_failure_refs,
        )
        for score, pitcher in rows
    ]


def classify_latest_fatigue_rows(rows, reference_date=None, mode=CURRENT_AVAILABILITY_MODE):
    return classify_fatigue_rows(rows, reference_date=reference_date, mode=mode)
