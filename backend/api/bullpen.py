import json
import os

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import desc
from datetime import date, datetime, timedelta, timezone

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from services.fatigue import calculate_fatigue, get_risk_level
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    availability_mode_metadata,
    classify_fatigue_rows,
    classify_latest_fatigue_rows,
    latest_fatigue_rows as availability_latest_fatigue_rows,
)
from services.availability_summary import summarize_availability_records
from services.bullpen_board import BOARD_GROUP_ORDER, build_board_payload, build_team_context
from services.bullpen_comparison import build_team_comparison
from services.pitcher_role import ROLE_KEYS, ROLE_WINDOW_DAYS, classify_usage_role
from services.mlb_api import mlb_client
from services import sync as sync_service
from services import sync_metadata
from utils.auth import require_admin_token

bullpen_bp = Blueprint('bullpen', __name__)

FATIGUE_ERA_RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'analysis',
    'fatigue_era_results.json',
)

def _truthy(value):
    """Parse a query-string boolean tolerantly."""
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _active_pitcher_cutoff(days: int = ACTIVE_WINDOW_DAYS):
    """Calendar-date cutoff for the active/current bullpen list."""
    return date.today() - timedelta(days=days)


def _recent_pitcher_ids_subquery(days: int = ACTIVE_WINDOW_DAYS):
    """
    Subquery returning pitcher_ids whose most recent game_log.game_date falls
    within the last `days` days relative to today's date. This intentionally
    treats historical local snapshots as inactive/stale instead of pretending
    old data is current bullpen availability.
    """
    cutoff = _active_pitcher_cutoff(days)
    return (
        db.session.query(GameLog.pitcher_id.label('pitcher_id'))
        .group_by(GameLog.pitcher_id)
        .having(db.func.max(GameLog.game_date) >= cutoff)
        .subquery()
    )


def _latest_fatigue_query(team_id=None, risk_level=None):
    """Latest fatigue-score rows with optional user-visible filters applied."""
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc')
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )

    query = (
        db.session.query(FatigueScore, Pitcher)
        .join(subq, (FatigueScore.pitcher_id == subq.c.pitcher_id) &
                    (FatigueScore.calculated_at == subq.c.max_calc))
        .join(Pitcher, FatigueScore.pitcher_id == Pitcher.id)
    )

    if team_id:
        query = query.filter(Pitcher.team_id == team_id)
    if risk_level:
        query = query.filter(FatigueScore.risk_level == risk_level.upper())

    return query


def _fatigue_list_meta(filtered_count, fresh_filtered_count, returned_count, include_stale, team_id, risk_level):
    """Trust metadata explaining why a fatigue list may be empty."""
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).scalar()
    total_game_logs = db.session.query(db.func.count(GameLog.id)).scalar() or 0

    total_scored = (
        db.session.query(db.func.count(db.func.distinct(FatigueScore.pitcher_id)))
        .scalar()
        or 0
    )

    return {
        'include_stale': include_stale,
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'active_cutoff_date': _active_pitcher_cutoff().isoformat(),
        'latest_game_date': latest_game_date.isoformat() if latest_game_date else None,
        'total_game_logs': int(total_game_logs),
        'total_scored_pitchers': int(total_scored),
        'filtered_scored_pitchers': int(filtered_count),
        'fresh_filtered_pitchers': int(fresh_filtered_count),
        'stale_filtered_pitchers': int(max(filtered_count - fresh_filtered_count, 0)),
        'returned_pitchers': int(returned_count),
        'filters': {
            'team_id': team_id,
            'risk_level': risk_level.upper() if risk_level else None,
        },
    }


def _availability_context(pitcher_id, reference_date=None):
    """Fetch the current workload window needed by the availability service."""
    ref = reference_date or date.today()
    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )
    window_start = ref - timedelta(days=4)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= ref,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return logs, latest_game_date


def _availability_for(pitcher_id, score, reference_date=None):
    logs, latest_game_date = _availability_context(pitcher_id, reference_date=reference_date)
    return classify_availability(
        score=score,
        game_logs=logs,
        reference_date=reference_date or date.today(),
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )


# ─── Fatigue Scores ───────────────────────────────────────────────────────────

@bullpen_bp.route('/fatigue', methods=['GET'])
def get_fatigue_scores():
    """
    Get current fatigue scores for all pitchers.
    Optional query params:
      - team_id: filter by team
      - risk_level: LOW | MODERATE | HIGH | CRITICAL
      - limit: max results (default 50)
      - include_stale: when truthy, include pitchers whose most recent
                       appearance is older than 14 days. Default false.
      - with_meta: when truthy, return {data, meta} instead of the legacy array.
    """
    team_id       = request.args.get('team_id', type=int)
    risk_level    = request.args.get('risk_level')
    limit         = request.args.get('limit', 50, type=int)
    include_stale = _truthy(request.args.get('include_stale'))
    with_meta     = _truthy(request.args.get('with_meta'))

    base_query     = _latest_fatigue_query(team_id=team_id, risk_level=risk_level)
    filtered_count = base_query.count()
    recent         = _recent_pitcher_ids_subquery()
    fresh_query    = base_query.join(recent, recent.c.pitcher_id == Pitcher.id)
    fresh_count    = fresh_query.count()
    query          = base_query
    if not include_stale:
        query  = query.join(recent, recent.c.pitcher_id == Pitcher.id)

    query   = query.order_by(desc(FatigueScore.raw_score)).limit(limit)
    results = query.all()

    records = classify_fatigue_rows(
        results,
        mode=CURRENT_AVAILABILITY_MODE,
    )

    data = []
    for record in records:
        score = record['score']
        pitcher = record['pitcher']
        data.append({
            **score.to_dict(),
            'pitcher': pitcher.to_dict(),
            'availability': record['availability'],
        })
    if not with_meta:
        return jsonify(data)

    return jsonify({
        'data': data,
        'meta': _fatigue_list_meta(
            filtered_count=filtered_count,
            fresh_filtered_count=fresh_count,
            returned_count=len(data),
            include_stale=include_stale,
            team_id=team_id,
            risk_level=risk_level,
        ),
    })


@bullpen_bp.route('/fatigue/snapshot', methods=['GET'])
@require_admin_token
def get_latest_workload_snapshot():
    """
    Admin/development-only validation view of the latest known workload window.

    This intentionally does not represent current bullpen availability. It
    anchors each pitcher on their own most recent game log so local historical
    datasets can exercise availability thresholds without changing public
    calendar-based freshness behavior.
    """
    team_id    = request.args.get('team_id', type=int)
    risk_level = request.args.get('risk_level')
    limit      = request.args.get('limit', 750, type=int)

    rows = availability_latest_fatigue_rows(
        team_id=team_id,
        risk_level=risk_level,
        limit=limit,
        order_by_score=True,
    )
    records = classify_latest_fatigue_rows(rows, mode=LATEST_WORKLOAD_SNAPSHOT_MODE)

    data = []
    for record in records:
        score = record['score']
        pitcher = record['pitcher']
        data.append({
            **score.to_dict(),
            'pitcher': pitcher.to_dict(),
            'availability': record['availability'],
            'availability_mode': {
                'mode': LATEST_WORKLOAD_SNAPSHOT_MODE,
                'evaluation_date': record['evaluation_date'].isoformat() if record['evaluation_date'] else None,
                'latest_game_date': record['latest_game_date'].isoformat() if record['latest_game_date'] else None,
                'is_current_availability': False,
            },
        })

    meta = availability_mode_metadata(LATEST_WORKLOAD_SNAPSHOT_MODE, records=records)
    meta.update({
        'total_pitchers': len(records),
        'returned_pitchers': len(data),
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'filters': {
            'team_id': team_id,
            'risk_level': risk_level.upper() if risk_level else None,
        },
    })
    response = jsonify({'data': data, 'meta': meta})
    response.headers['X-BaseballOS-Data-Mode'] = LATEST_WORKLOAD_SNAPSHOT_MODE
    response.headers['X-BaseballOS-Current-Availability'] = 'false'
    return response


@bullpen_bp.route('/fatigue/<int:pitcher_id>', methods=['GET'])
def get_pitcher_fatigue(pitcher_id):
    """Get detailed fatigue profile for a single pitcher."""
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None:
        abort(404)

    latest = (
        FatigueScore.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(desc(FatigueScore.calculated_at))
        .first()
    )

    # Anchor recent_logs / fatigue_trend on the pitcher's most recent game
    # so historical (e.g. 2024-2025 seed) data still produces non-empty
    # windows. Fall back to today if the pitcher has no logs at all.
    last_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )
    anchor = last_game_date if last_game_date else date.today()

    fourteen_days_ago = anchor - timedelta(days=14)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date >= fourteen_days_ago)
        .order_by(desc(GameLog.game_date))
        .all()
    )

    thirty_days_ago = anchor - timedelta(days=30)
    history = (
        FatigueScore.query
        .filter(
            FatigueScore.pitcher_id == pitcher_id,
            FatigueScore.calculated_at >= thirty_days_ago
        )
        .order_by(FatigueScore.calculated_at)
        .all()
    )

    return jsonify({
        'pitcher':         pitcher.to_dict(),
        'current_fatigue': latest.to_dict() if latest else None,
        'availability':    _availability_for(pitcher_id, latest),
        'recent_logs':     [log.to_dict() for log in logs],
        'fatigue_trend':   [s.to_dict() for s in history],
    })


@bullpen_bp.route('/fatigue/recalculate', methods=['POST'])
@require_admin_token
def recalculate_fatigue():
    """
    Trigger fatigue recalculation for all pitchers.
    Uses each pitcher's last game date as the reference point — not today —
    so historical data produces meaningful scores.
    """
    pitchers = Pitcher.query.filter_by(active=True).all()
    updated  = []

    for pitcher in pitchers:
        latest_log = (
            GameLog.query
            .filter_by(pitcher_id=pitcher.id)
            .order_by(GameLog.game_date.desc())
            .first()
        )

        if not latest_log:
            continue

        reference_date = latest_log.game_date
        window_start   = reference_date - timedelta(days=14)

        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date  >= window_start,
                GameLog.game_date  <= reference_date
            )
            .order_by(desc(GameLog.game_date))
            .all()
        )

        score = calculate_fatigue(pitcher, logs, reference_date=reference_date)
        db.session.add(score)
        updated.append({
            'pitcher': pitcher.full_name,
            'score':   round(score.raw_score, 1),
            'risk':    score.risk_level,
        })

    db.session.commit()
    return jsonify({'recalculated': len(updated), 'results': updated})


# ─── Sync (Live Data Refresh) ─────────────────────────────────────────────────

@bullpen_bp.route('/sync', methods=['POST'])
@require_admin_token
def sync_recent_logs():
    """
    Pull the latest game logs from the MLB Stats API for the current season
    and recalculate fatigue scores. Safe to call repeatedly — skips duplicates.

    Optional JSON body:
      { "days_back": 7 }  — how far back to look for new games (default: 7)

    Delegates to services/sync.py so the scheduled daily job and the manual
    POST go through the exact same code path. Also writes sync_status.json
    so the dashboard "Last synced" pill reflects manual runs too.
    """
    body      = request.get_json(silent=True) or {}
    days_back = body.get('days_back', 7)
    source    = str(body.get('source') or sync_metadata.SOURCE_MANUAL)[:30]
    started   = datetime.now(timezone.utc)
    sync_run_id = sync_metadata.start_sync_run(
        source=source,
        started_at=started.replace(tzinfo=None),
    )

    try:
        pull = sync_service.sync_recent_logs(days_back=days_back)
    except Exception as e:
        db.session.rollback()
        sync_metadata.finish_sync_run(
            sync_run_id,
            status=sync_metadata.STATUS_FAILED,
            errors=1,
            error_message=str(e),
        )
        # Persist failure status so the dashboard reflects the bad state.
        sync_service.write_status({
            'last_sync':       started.isoformat(),
            'status':          sync_metadata.STATUS_FAILED,
            'pitchers_updated': 0,
            'new_logs_added':  0,
            'errors':          1,
            'message':         str(e),
            'finished_at':     datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500

    # Live mode: score against today — same behavior as before.
    fatigue_updated = sync_service.recalculate_all_fatigue(use_last_game_date=False)
    finished        = datetime.now(timezone.utc)
    sync_metadata.finish_sync_run(
        sync_run_id,
        status=sync_metadata.STATUS_SUCCESS,
        completed_at=finished.replace(tzinfo=None),
        records_processed=pull['new_logs_added'],
        new_logs_added=pull['new_logs_added'],
        pitchers_updated=fatigue_updated,
        errors=pull['errors'],
    )

    # Mirror what the daily APScheduler job writes so /sync/status stays accurate.
    sync_service.write_status({
        'last_sync':       started.isoformat(),
        'status':          sync_metadata.STATUS_SUCCESS,
        'pitchers_updated': fatigue_updated,
        'new_logs_added':  pull['new_logs_added'],
        'errors':          pull['errors'],
        'message':         '',
        'finished_at':     finished.isoformat(),
    })

    return jsonify({
        'status':               'ok',
        'new_logs_added':       pull['new_logs_added'],
        'fatigue_recalculated': fatigue_updated,
        'errors':               pull['errors'],
        'synced_at':            finished.isoformat(),
        'sync_run_id':          sync_run_id,
        'days_back':            days_back,
    })


@bullpen_bp.route('/sync/status', methods=['GET'])
def get_sync_status():
    """
    Return the last sync status, enriched with the actual data snapshot
    (latest game date + game-log count) from the database.

    This lets the dashboard distinguish three real states that the bare status
    file cannot: a successful/failed live sync, a loaded historical snapshot
    (data present but no sync has run — e.g. after `python seed.py`), and a
    genuinely empty system. The snapshot date is real DB data, never a faked
    sync timestamp.

    Authority: durable sync_runs metadata is the source of truth (see
    services/sync_metadata.build_sync_status_payload). backend/logs/sync_status.json
    is cache-only — it is passed in as a fallback and is only consulted when no
    durable run exists (e.g. the sync_runs migration has not been applied yet).
    """
    legacy_status = sync_service.read_status()
    try:
        return jsonify(sync_metadata.build_sync_status_payload(legacy_status=legacy_status))
    except Exception:
        # A DB hiccup must never turn the status pill into a hard error.
        legacy_status['data'] = {
            'game_logs': None,
            'latest_game_date': None,
            'latest_workload_date': None,
            'latest_fatigue_calculated_at': None,
        }
        legacy_status['freshness'] = {
            'is_current': False,
            'label': 'Freshness metadata unavailable.',
            'limitations': ['Could not read durable sync metadata.'],
        }
        return jsonify(legacy_status)


# ─── Pitchers ─────────────────────────────────────────────────────────────────

@bullpen_bp.route('/pitchers', methods=['GET'])
def get_pitchers():
    """Get all pitchers, optionally filtered by team."""
    team_id  = request.args.get('team_id', type=int)
    query    = Pitcher.query.filter_by(active=True)
    if team_id:
        query = query.filter_by(team_id=team_id)
    pitchers = query.order_by(Pitcher.team_name, Pitcher.full_name).all()
    return jsonify([p.to_dict() for p in pitchers])


@bullpen_bp.route('/pitchers/<int:pitcher_id>/logs', methods=['GET'])
def get_pitcher_logs(pitcher_id):
    """Get game logs for a pitcher."""
    days  = request.args.get('days', 30, type=int)
    since = date.today() - timedelta(days=days)
    logs  = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date >= since)
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return jsonify([log.to_dict() for log in logs])


# ─── Teams ────────────────────────────────────────────────────────────────────

@bullpen_bp.route('/teams', methods=['GET'])
def get_teams():
    """Get all teams that have pitchers in the DB."""
    teams = (
        db.session.query(
            Pitcher.team_id,
            Pitcher.team_name,
            Pitcher.team_abbreviation,
            db.func.count(Pitcher.id).label('pitcher_count')
        )
        .filter(Pitcher.active == True)
        .group_by(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .order_by(Pitcher.team_name)
        .all()
    )
    return jsonify([
        {
            'team_id':           t.team_id,
            'team_name':         t.team_name,
            'team_abbreviation': t.team_abbreviation,
            'pitcher_count':     t.pitcher_count,
        }
        for t in teams
    ])


def _team_bullpen_rows(team_id, include_stale=False):
    """
    Latest fatigue + availability for a team's active pitchers.

    Single joined query (no N+1). Returns the (pitcher, score) result rows and a
    {pitcher_id: availability} map so the bullpen overview and Tonight's Bullpen
    Board share one availability calculation instead of duplicating it.
    """
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc')
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )

    query = (
        db.session.query(Pitcher, FatigueScore)
        .filter(Pitcher.team_id == team_id, Pitcher.active == True)
        .outerjoin(subq, subq.c.pitcher_id == Pitcher.id)
        .outerjoin(
            FatigueScore,
            (FatigueScore.pitcher_id == subq.c.pitcher_id) &
            (FatigueScore.calculated_at == subq.c.max_calc)
        )
    )

    if not include_stale:
        recent = _recent_pitcher_ids_subquery()
        query  = query.join(recent, recent.c.pitcher_id == Pitcher.id)

    results = query.order_by(desc(FatigueScore.raw_score)).all()

    availability_rows = [
        (score, pitcher)
        for pitcher, score in results
    ]
    availability_by_pitcher = {
        record['pitcher_id']: record['availability']
        for record in classify_fatigue_rows(
            availability_rows,
            mode=CURRENT_AVAILABILITY_MODE,
        )
    }
    return results, availability_by_pitcher


@bullpen_bp.route('/teams/<int:team_id>/bullpen', methods=['GET'])
def get_team_bullpen(team_id):
    """
    Get full bullpen overview for a team.
    Single joined query — no N+1 issue.

    Optional query params:
      - include_stale: when truthy, include pitchers whose most recent
                       appearance is older than 14 days. Default false.
    """
    include_stale = _truthy(request.args.get('include_stale'))
    results, availability_by_pitcher = _team_bullpen_rows(team_id, include_stale)

    return jsonify([
        {
            'pitcher': pitcher.to_dict(),
            'fatigue': score.to_dict() if score else None,
            'availability': availability_by_pitcher.get(pitcher.id),
        }
        for pitcher, score in results
    ])


def _board_freshness_block():
    """
    Compact freshness/trust block for the board, derived from the same durable
    sync metadata the dashboard trusts. Never raises — a DB hiccup degrades to a
    clearly-labelled "unavailable" state instead of failing the board.
    """
    try:
        status_payload = sync_metadata.build_sync_status_payload(
            legacy_status=sync_service.read_status()
        )
        freshness = status_payload.get('freshness') or {}
        data = status_payload.get('data') or {}
        return {
            'data_through': data.get('latest_game_date'),
            'latest_workload_date': data.get('latest_workload_date'),
            'last_successful_sync': status_payload.get('last_successful_sync'),
            'sync_status': status_payload.get('status'),
            'is_current': freshness.get('is_current', False),
            'label': freshness.get('label'),
            'limitations': list(freshness.get('limitations') or []),
        }
    except Exception:
        return {
            'data_through': None,
            'latest_workload_date': None,
            'last_successful_sync': None,
            'sync_status': None,
            'is_current': False,
            'label': 'Freshness metadata unavailable.',
            'limitations': ['Could not read durable sync metadata.'],
        }


def _team_info_lookup(team_id):
    """Best-effort {team_id, team_name, team_abbreviation} even with no pitchers in window."""
    row = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id == team_id)
        .first()
    )
    if row is None:
        return {'team_id': team_id, 'team_name': None, 'team_abbreviation': None}
    return {'team_id': row.team_id, 'team_name': row.team_name, 'team_abbreviation': row.team_abbreviation}


def _recent_logs_by_pitcher(pitcher_ids, days=ROLE_WINDOW_DAYS):
    """
    Recent game logs grouped by pitcher_id, in a single query (no N+1).

    Used to classify observed usage role. Returns {} when there are no pitchers.
    """
    if not pitcher_ids:
        return {}
    cutoff = date.today() - timedelta(days=days)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(pitcher_ids), GameLog.game_date >= cutoff)
        .all()
    )
    grouped = {}
    for log in logs:
        grouped.setdefault(log.pitcher_id, []).append(log)
    return grouped


def _build_team_board(team_id, include_stale=False, freshness=None):
    """
    Build a Tonight's Bullpen Board payload for one team.

    Shared by the board route and the comparison route so both consume the exact
    same grouped/context output and the same observed-usage-role classification
    (built once here, no duplicate availability or role calculation).
    """
    results, availability_by_pitcher = _team_bullpen_rows(team_id, include_stale)
    logs_by_pitcher = _recent_logs_by_pitcher([pitcher.id for pitcher, _ in results])
    today = date.today()

    team_info = None
    records = []
    for pitcher, score in results:
        records.append({
            'name': pitcher.full_name,
            'pitcher_id': pitcher.id,
            'fatigue_score': score.raw_score if score else None,
            'availability': availability_by_pitcher.get(pitcher.id),
            'role': classify_usage_role(
                logs_by_pitcher.get(pitcher.id, []),
                reference_date=today,
            ),
        })
        if team_info is None:
            team_info = {
                'team_id': pitcher.team_id,
                'team_name': pitcher.team_name,
                'team_abbreviation': pitcher.team_abbreviation,
            }

    if team_info is None:
        team_info = _team_info_lookup(team_id)

    freshness = freshness or _board_freshness_block()
    return build_board_payload(
        team=team_info,
        records=records,
        freshness=freshness,
        limitations=freshness.get('limitations'),
    )


@bullpen_bp.route('/teams/<int:team_id>/board', methods=['GET'])
def get_team_bullpen_board(team_id):
    """
    Tonight's Bullpen Board — existing availability classifications grouped for a
    coach-facing read of "what does this bullpen look like tonight?".

    Presentation only: no ranking, no selection, no recommendation, no
    prediction. Reuses the same query and Availability Engine V1 output as the
    bullpen overview, groups pitchers by availability status, and orders them
    alphabetically within each group.

    Optional query params:
      - include_stale: when truthy, include pitchers whose most recent
                       appearance is older than 14 days. Default false.
    """
    include_stale = _truthy(request.args.get('include_stale'))
    return jsonify(_build_team_board(team_id, include_stale))


@bullpen_bp.route('/teams/compare', methods=['GET'])
def compare_team_bullpens():
    """
    Team Bullpen Comparison — descriptive side-by-side of two team bullpens.

    Aggregates two existing board payloads (V1 groups + V2 team context) into a
    transparent count comparison answering "which bullpen appears more available
    tonight?". No team ranking, grading, scoring, matchup, or recommendation —
    every observation shows both raw counts.

    Required query params:
      - team_a, team_b: team ids to compare.
    Optional:
      - include_stale: include pitchers with no games in the last 14 days.
    """
    team_a = request.args.get('team_a', type=int)
    team_b = request.args.get('team_b', type=int)
    if team_a is None or team_b is None:
        abort(400, description='team_a and team_b query parameters are required.')

    include_stale = _truthy(request.args.get('include_stale'))
    # One freshness read shared by both boards — it is system-wide, not per-team.
    freshness = _board_freshness_block()
    board_a = _build_team_board(team_a, include_stale, freshness=freshness)
    board_b = _build_team_board(team_b, include_stale, freshness=freshness)

    comparison = build_team_comparison(
        board_a,
        board_b,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    return jsonify({
        'capability': 'team_bullpen_comparison',
        'generated_at': comparison['generated_at'],
        'ranking_applied': False,
        'selection_made': False,
        'team_a': board_a,
        'team_b': board_b,
        'comparison': comparison,
    })


# ─── Stats & Aggregates ───────────────────────────────────────────────────────

@bullpen_bp.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """Dashboard overview stats."""
    total_pitchers = Pitcher.query.filter_by(active=True).count()
    total_logs     = GameLog.query.count()

    latest_rows = availability_latest_fatigue_rows()
    latest_scores = [score for score, _pitcher in latest_rows]
    availability_records = classify_latest_fatigue_rows(
        latest_rows,
        mode=CURRENT_AVAILABILITY_MODE,
    )

    risk_breakdown = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
    for score in latest_scores:
        if score.risk_level in risk_breakdown:
            risk_breakdown[score.risk_level] += 1

    avg_fatigue = (
        sum(s.raw_score for s in latest_scores) / len(latest_scores)
        if latest_scores else 0
    )

    return jsonify({
        'total_pitchers':    total_pitchers,
        'total_game_logs':   total_logs,
        'risk_breakdown':    risk_breakdown,
        'avg_fatigue_score': round(float(avg_fatigue), 1),
        'scored_pitchers':   len(latest_scores),
        'availability_summary': summarize_availability_records(availability_records),
    })


@bullpen_bp.route('/dashboard', methods=['GET'])
def get_bullpen_dashboard():
    """
    League-wide bullpen overview for the landing dashboard.

    Reuses existing systems only — Availability Engine V1 (availability summary),
    the V2 Team Context Layer (bullpen health), and the usage-role classifier —
    aggregated across all currently-scored pitchers. Presentation/context only:
    no ranking, selection, recommendation, or prediction.
    """
    latest_rows = availability_latest_fatigue_rows()
    availability_records = classify_latest_fatigue_rows(
        latest_rows,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    summary = summarize_availability_records(availability_records)
    status_counts = summary.get('statuses') or {}
    groups = [
        {'status': status, 'count': int(status_counts.get(status, 0))}
        for status in BOARD_GROUP_ORDER
    ]

    freshness = _board_freshness_block()
    context = build_team_context(groups, freshness=freshness)

    # Usage-role composition across the same scored-pitcher set (one logs query).
    pitcher_ids = [pitcher.id for _score, pitcher in latest_rows]
    logs_by_pitcher = _recent_logs_by_pitcher(pitcher_ids)
    today = date.today()
    role_counts = {key: 0 for key in ROLE_KEYS}
    for pitcher_id in pitcher_ids:
        role = classify_usage_role(logs_by_pitcher.get(pitcher_id, []), reference_date=today)
        key = role['role_key']
        role_counts[key] = role_counts.get(key, 0) + 1

    return jsonify({
        'capability': 'bullpen_dashboard',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'all_tracked_bullpens',
        'context': context,
        'roles': {
            'order': list(ROLE_KEYS),
            'counts': role_counts,
            'total': len(pitcher_ids),
        },
        'freshness': freshness,
        'availability_summary': summary,
    })


# ─── Insights ─────────────────────────────────────────────────────────────────

@bullpen_bp.route('/insights/fatigue-era', methods=['GET'])
def get_fatigue_era_insight():
    """
    Return precomputed fatigue → next-appearance ERA analysis.

    Reads backend/analysis/fatigue_era_results.json — generated by
    `python -m analysis.fatigue_era_analysis`. The script is intentionally
    run out-of-band (manually or as a future scheduled job) because it
    walks every reliever's full 2024-2025 history.
    """
    if not os.path.exists(FATIGUE_ERA_RESULTS_PATH):
        return jsonify({
            'status': 'not_generated',
            'message': 'Run the analysis script first',
        })

    try:
        with open(FATIGUE_ERA_RESULTS_PATH, 'r') as fh:
            return jsonify(json.load(fh))
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to load analysis results: {str(e)}',
        }), 500


# ─── MLB API Passthrough ──────────────────────────────────────────────────────

@bullpen_bp.route('/mlb/teams', methods=['GET'])
def get_mlb_teams():
    """Proxy: Get all MLB teams from the Stats API."""
    teams = mlb_client.get_all_teams()
    return jsonify(teams)


@bullpen_bp.route('/mlb/pitcher/<int:player_id>/logs', methods=['GET'])
def get_mlb_pitcher_logs(player_id):
    """Proxy: Get live pitcher game logs from MLB Stats API."""
    season = request.args.get('season', type=int)
    logs   = mlb_client.get_pitcher_game_logs(player_id, season=season)
    return jsonify(logs)
