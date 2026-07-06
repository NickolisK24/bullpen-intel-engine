from flask import Blueprint, jsonify

from services.public_team_relief_work import (
    TeamNotFoundError,
    build_public_team_relief_work_payload,
)


team_recent_work_bp = Blueprint('team_recent_work', __name__)


@team_recent_work_bp.route('/teams/<int:team_id>/relief-work', methods=['GET'])
def team_relief_work(team_id):
    try:
        payload = build_public_team_relief_work_payload(team_id)
    except TeamNotFoundError:
        return jsonify({'error': 'team_not_found'}), 404
    return jsonify(payload)
