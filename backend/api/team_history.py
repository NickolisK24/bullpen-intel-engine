"""Public Team State History API."""

from datetime import date

from flask import Blueprint, jsonify, request

from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from services.pitcher_trends import season_pitch_characteristics
from services.team_state_history import build_team_state_history, history_season, history_team
from utils.db import db


team_history_bp = Blueprint('team_history', __name__)


@team_history_bp.route('/teams/<team_abbreviation>/history', methods=['GET'])
def get_team_state_history(team_abbreviation):
    try:
        payload = build_team_state_history(
            team_abbreviation,
            season=request.args.get('season', '2026'),
        )
    except ValueError:
        return jsonify({'status': 'invalid_request', 'error': 'season_invalid'}), 400
    if payload is None:
        return jsonify({'status': 'not_found', 'error': 'team_not_found'}), 404
    return jsonify(payload)


@team_history_bp.get('/teams/<team_abbreviation>/history/pitchers/<int:pitcher_id>')
def get_team_history_pitcher(team_abbreviation, pitcher_id):
    try:
        season = history_season(request.args.get('season', '2026'))
        start = date(season, 1, 1)
        through = min(date(season, 12, 31), product_current_date())
    except ValueError:
        return jsonify({'error': 'season_invalid'}), 400
    team = history_team(team_abbreviation)
    if team is None:
        return jsonify({'error': 'team_not_found'}), 404
    team_id = int(team['team_id'])
    if not 0 < pitcher_id <= 2147483647:
        return jsonify({'error': 'pitcher_id_invalid'}), 400
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None or through < start:
        return jsonify({'error': 'pitch_history_unavailable'}), 404
    read = season_pitch_characteristics(pitcher, through, appearance_team_id=team_id)
    if not read['months']:
        return jsonify({'error': 'pitch_history_unavailable'}), 404
    return jsonify(read)
