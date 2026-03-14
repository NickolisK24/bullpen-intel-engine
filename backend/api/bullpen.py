from flask import Blueprint, jsonify, request
from sqlalchemy import desc
from datetime import date, timedelta

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from services.fatigue import calculate_fatigue, get_risk_level
from services.mlb_api import mlb_client

bullpen_bp = Blueprint('bullpen', __name__)


# ─── Fatigue Scores ───────────────────────────────────────────────────────────

@bullpen_bp.route('/fatigue', methods=['GET'])
def get_fatigue_scores():
    """
    Get current fatigue scores for all pitchers.
    Optional query params:
      - team_id: filter by team
      - risk_level: LOW | MODERATE | HIGH | CRITICAL
      - limit: max results (default 50)
    """
    team_id = request.args.get('team_id', type=int)
    risk_level = request.args.get('risk_level')
    limit = request.args.get('limit', 50, type=int)

    # Get the most recent fatigue score per pitcher using a subquery
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

    query = query.order_by(desc(FatigueScore.raw_score)).limit(limit)
    results = query.all()

    return jsonify([
        {**score.to_dict(), 'pitcher': pitcher.to_dict()}
        for score, pitcher in results
    ])


@bullpen_bp.route('/fatigue/<int:pitcher_id>', methods=['GET'])
def get_pitcher_fatigue(pitcher_id):
    """Get detailed fatigue profile for a single pitcher."""
    pitcher = Pitcher.query.get_or_404(pitcher_id)

    # Latest score
    latest = (
        FatigueScore.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(desc(FatigueScore.calculated_at))
        .first()
    )

    # Recent game logs
    seven_days_ago = date.today() - timedelta(days=14)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date >= seven_days_ago)
        .order_by(desc(GameLog.game_date))
        .all()
    )

    # Historical fatigue trend (last 30 days of scores)
    thirty_days_ago = date.today() - timedelta(days=30)
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
        'pitcher': pitcher.to_dict(),
        'current_fatigue': latest.to_dict() if latest else None,
        'recent_logs': [log.to_dict() for log in logs],
        'fatigue_trend': [s.to_dict() for s in history],
    })


@bullpen_bp.route('/fatigue/recalculate', methods=['POST'])
def recalculate_fatigue():
    """Trigger fatigue recalculation for all pitchers."""
    pitchers = Pitcher.query.filter_by(active=True).all()
    updated = []

    for pitcher in pitchers:
        fourteen_days_ago = date.today() - timedelta(days=14)
        logs = (
            GameLog.query
            .filter(GameLog.pitcher_id == pitcher.id, GameLog.game_date >= fourteen_days_ago)
            .order_by(desc(GameLog.game_date))
            .all()
        )
        score = calculate_fatigue(pitcher, logs)
        db.session.add(score)
        updated.append({'pitcher': pitcher.full_name, 'score': round(score.raw_score, 1), 'risk': score.risk_level})

    db.session.commit()
    return jsonify({'recalculated': len(updated), 'results': updated})


# ─── Pitchers ─────────────────────────────────────────────────────────────────

@bullpen_bp.route('/pitchers', methods=['GET'])
def get_pitchers():
    """Get all pitchers, optionally filtered by team."""
    team_id = request.args.get('team_id', type=int)
    query = Pitcher.query.filter_by(active=True)
    if team_id:
        query = query.filter_by(team_id=team_id)
    pitchers = query.order_by(Pitcher.team_name, Pitcher.full_name).all()
    return jsonify([p.to_dict() for p in pitchers])


@bullpen_bp.route('/pitchers/<int:pitcher_id>/logs', methods=['GET'])
def get_pitcher_logs(pitcher_id):
    """Get game logs for a pitcher."""
    days = request.args.get('days', 30, type=int)
    since = date.today() - timedelta(days=days)
    logs = (
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
            'team_id': t.team_id,
            'team_name': t.team_name,
            'team_abbreviation': t.team_abbreviation,
            'pitcher_count': t.pitcher_count,
        }
        for t in teams
    ])


@bullpen_bp.route('/teams/<int:team_id>/bullpen', methods=['GET'])
def get_team_bullpen(team_id):
    """
    Get full bullpen overview for a team.
    Returns pitchers with their current fatigue scores.
    """
    pitchers = Pitcher.query.filter_by(team_id=team_id, active=True).all()

    results = []
    for pitcher in pitchers:
        latest_score = (
            FatigueScore.query
            .filter_by(pitcher_id=pitcher.id)
            .order_by(desc(FatigueScore.calculated_at))
            .first()
        )
        results.append({
            'pitcher': pitcher.to_dict(),
            'fatigue': latest_score.to_dict() if latest_score else None,
        })

    # Sort by fatigue score descending (most fatigued first)
    results.sort(key=lambda x: x['fatigue']['raw_score'] if x['fatigue'] else 0, reverse=True)
    return jsonify(results)


# ─── Stats & Aggregates ───────────────────────────────────────────────────────

@bullpen_bp.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """Dashboard overview stats."""
    total_pitchers = Pitcher.query.filter_by(active=True).count()
    total_logs = GameLog.query.count()

    # Risk breakdown
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
        db.session.query(db.func.avg(FatigueScore.raw_score)).scalar() or 0
    )

    return jsonify({
        'total_pitchers': total_pitchers,
        'total_game_logs': total_logs,
        'risk_breakdown': risk_breakdown,
        'avg_fatigue_score': round(float(avg_fatigue), 1),
        'scored_pitchers': len(latest_scores),
    })


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
    logs = mlb_client.get_pitcher_game_logs(player_id, season=season)
    return jsonify(logs)
