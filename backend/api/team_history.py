"""Public Team State History API."""

from flask import Blueprint, jsonify, request

from services.team_state_history import build_team_state_history


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
