from flask import Blueprint, jsonify

from services.public_recent_work import (
    PitcherNotFoundError,
    build_public_recent_work_payload,
)


recent_work_bp = Blueprint('recent_work', __name__)


@recent_work_bp.route('/pitchers/<int:pitcher_id>/recent-work', methods=['GET'])
def pitcher_recent_work(pitcher_id):
    try:
        payload = build_public_recent_work_payload(pitcher_id)
    except PitcherNotFoundError:
        return jsonify({'error': 'pitcher_not_found'}), 404
    return jsonify(payload)
