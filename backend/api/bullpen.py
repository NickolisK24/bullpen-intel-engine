import json
import os

from flask import Blueprint, jsonify, request
from sqlalchemy import desc
from datetime import date, datetime, timedelta

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from services.fatigue import calculate_fatigue, get_risk_level
from services.mlb_api import mlb_client
from services import sync as sync_service

bullpen_bp = Blueprint('bullpen', __name__)

FATIGUE_ERA_RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'analysis',
    'fatigue_era_results.json',
)

ACTIVE_WINDOW_DAYS = 14


def _truthy(value):
    """Parse a query-string boolean tolerantly."""
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _recent_pitcher_ids_subquery(days: int = ACTIVE_WINDOW_DAYS):
    """
    Subquery returning pitcher_ids whose most recent game_log.game_date falls
    within the last `days` days. Used to suppress stale rows from list views.
    """
    cutoff = date.today() - timedelta(days=days)
    return (
        db.session.query(GameLog.pitcher_id.label('pitcher_id'))
        .group_by(GameLog.pitcher_id)
        .having(db.func.max(GameLog.game_date) >= cutoff)
        .subquery()
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
    """
    team_id       = request.args.get('team_id', type=int)
    risk_level    = request.args.get('risk_level')
    limit         = request.args.get('limit', 50, type=int)
    include_stale = _truthy(request.args.get('include_stale'))

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

    if not include_stale:
        recent = _recent_pitcher_ids_subquery()
        query  = query.join(recent, recent.c.pitcher_id == Pitcher.id)

    if team_id:
        query = query.filter(Pitcher.team_id == team_id)
    if risk_level:
        query = query.filter(FatigueScore.risk_level == risk_level.upper())

    query   = query.order_by(desc(FatigueScore.raw_score)).limit(limit)
    results = query.all()

    return jsonify([
        {**score.to_dict(), 'pitcher': pitcher.to_dict()}
        for score, pitcher in results
    ])


@bullpen_bp.route('/fatigue/<int:pitcher_id>', methods=['GET'])
def get_pitcher_fatigue(pitcher_id):
    """Get detailed fatigue profile for a single pitcher."""
    pitcher = Pitcher.query.get_or_404(pitcher_id)

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
        'recent_logs':     [log.to_dict() for log in logs],
        'fatigue_trend':   [s.to_dict() for s in history],
    })


@bullpen_bp.route('/fatigue/recalculate', methods=['POST'])
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
def sync_recent_logs():
    """
    Pull the latest game logs from the MLB Stats API for the current season
    and recalculate fatigue scores. Safe to call repeatedly — skips duplicates.

    Optional JSON body:
      { "days_back": 7 }  — how far back to look for new games (default: 7)

    Delegates to services/sync.py so the scheduled daily job and the manual
    POST go through the exact same code path.
    """
    body      = request.get_json(silent=True) or {}
    days_back = body.get('days_back', 7)

    try:
        pull = sync_service.sync_recent_logs(days_back=days_back)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500

    # Live mode: score against today — same behavior as before.
    fatigue_updated = sync_service.recalculate_all_fatigue(use_last_game_date=False)

    return jsonify({
        'status':               'ok',
        'new_logs_added':       pull['new_logs_added'],
        'fatigue_recalculated': fatigue_updated,
        'errors':               pull['errors'],
        'synced_at':            datetime.utcnow().isoformat(),
        'days_back':            days_back,
    })


@bullpen_bp.route('/sync/status', methods=['GET'])
def get_sync_status():
    """
    Return the last-run status written by the daily APScheduler job.
    Frontend uses this to render the "Last synced" pill on the dashboard.
    """
    return jsonify(sync_service.read_status())


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

    return jsonify([
        {
            'pitcher': pitcher.to_dict(),
            'fatigue': score.to_dict() if score else None,
        }
        for pitcher, score in results
    ])


# ─── Stats & Aggregates ───────────────────────────────────────────────────────

@bullpen_bp.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """Dashboard overview stats."""
    total_pitchers = Pitcher.query.filter_by(active=True).count()
    total_logs     = GameLog.query.count()

    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc')
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )
    latest_scores = (
        db.session.query(FatigueScore)
        .join(subq, (FatigueScore.pitcher_id == subq.c.pitcher_id) &
                    (FatigueScore.calculated_at == subq.c.max_calc))
        .all()
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