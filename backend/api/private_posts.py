"""Private posting-board API.

The posting board is not a public BaseballOS surface. It reuses the existing
bullpen dashboard payload only after bearer authentication and an explicit
email allowlist check.
"""

from flask import Blueprint, current_app, g, jsonify

from api.bullpen import bullpen_dashboard_response_payload
from utils.auth_tokens import normalize_email
from utils.identity import require_authenticated_user


private_posts_bp = Blueprint('private_posts', __name__)


def _split_allowed_emails(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return str(value).replace('\n', ',').split(',')


def private_posting_board_allowed_emails():
    """Return the configured posting-board allowlist as normalized emails."""
    configured = current_app.config.get('PRIVATE_POSTING_BOARD_ALLOWED_EMAILS', '')
    return {
        email
        for email in (
            normalize_email(candidate)
            for candidate in _split_allowed_emails(configured)
        )
        if email
    }


def user_can_access_private_posting_board(user):
    if user is None:
        return False
    allowed = private_posting_board_allowed_emails()
    if not allowed:
        return False
    return normalize_email(getattr(user, 'email', None)) in allowed


@private_posts_bp.route('/dashboard', methods=['GET'])
@require_authenticated_user
def get_private_posts_dashboard():
    """Serve the posting-board data only to explicitly allowed users."""
    if not user_can_access_private_posting_board(g.current_user):
        return jsonify({'error': 'posting_board_forbidden'}), 403
    return jsonify(bullpen_dashboard_response_payload())
