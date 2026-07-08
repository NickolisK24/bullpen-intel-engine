from flask import Blueprint, jsonify, request

from services.audience_signup import (
    AUDIENCE_SIGNUP_DEFAULT_SOURCE,
    AUDIENCE_SIGNUP_INVALID_MESSAGE,
    AUDIENCE_SIGNUP_INVALID_REASON,
    AUDIENCE_SIGNUP_SUCCESS_MESSAGE,
    signup_audience_subscriber,
)


audience_bp = Blueprint('audience', __name__)


@audience_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    result = signup_audience_subscriber(
        data.get('email'),
        source=data.get('source') or AUDIENCE_SIGNUP_DEFAULT_SOURCE,
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': AUDIENCE_SIGNUP_INVALID_MESSAGE,
            'reason': AUDIENCE_SIGNUP_INVALID_REASON,
        }), 400

    return jsonify({
        'success': True,
        'message': AUDIENCE_SIGNUP_SUCCESS_MESSAGE,
    })
