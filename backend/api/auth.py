"""Identity / auth API (Phase D1C — magic-link authentication).

Stateless, passwordless authentication:

  • POST /api/auth/request-link — email a short-lived magic link (generic
    response, no account enumeration).
  • POST /api/auth/verify       — exchange a magic-link token for a bearer token.
  • GET  /api/auth/me           — current identity; anonymous without a valid token.
  • POST /api/auth/logout       — stateless client-side token discard.

There is no sign-in UI, team-following API, notification, or onboarding here —
those belong to later phases. Every endpoint is anonymous-safe and none mutates
data beyond creating/confirming the requesting user's own account.
"""

from flask import Blueprint, jsonify, request

from models.user import User
from utils.auth_email import send_magic_link
from utils.auth_tokens import (
    build_magic_link,
    generate_bearer_token,
    generate_magic_link_token,
    normalize_email,
    verify_magic_link_token,
)
from utils.db import db
from utils.identity import identity_for, resolve_current_user
from utils.time import utc_now_naive


auth_bp = Blueprint('auth', __name__)

# Identical whether or not the email is valid/known, so the response can never be
# used to discover which addresses have accounts.
GENERIC_REQUEST_LINK_MESSAGE = 'If that email can receive a sign-in link, one is on its way.'


@auth_bp.route('/me', methods=['GET'])
def get_me():
    """Return the current identity. Anonymous unless a valid bearer token is sent."""
    return jsonify(identity_for(resolve_current_user()))


@auth_bp.route('/request-link', methods=['POST'])
def request_link():
    """Email a magic link for the given address. Always returns a generic success."""
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    if email:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email)
            db.session.add(user)
            db.session.commit()
        token = generate_magic_link_token(email)
        send_magic_link(email, build_magic_link(token), token=token)
    # Generic response regardless of validity/existence (no account enumeration).
    # The link/token is never returned in the response body.
    return jsonify({'ok': True, 'message': GENERIC_REQUEST_LINK_MESSAGE})


@auth_bp.route('/verify', methods=['POST'])
def verify():
    """Exchange a valid magic-link token for a bearer token + user payload."""
    data = request.get_json(silent=True) or {}
    email = verify_magic_link_token((data.get('token') or '').strip())
    if not email:
        return jsonify({'error': 'invalid_or_expired_token'}), 401

    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email)
        db.session.add(user)

    now = utc_now_naive()
    if user.email_verified_at is None:
        user.email_verified_at = now
    user.last_login_at = now
    db.session.commit()

    return jsonify({'token': generate_bearer_token(user), 'user': user.to_dict()})


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Stateless logout: the client discards its bearer token.

    There is no sessions table and no server-side revocation, so this is a no-op
    acknowledgement; the token simply stops being sent by the client.
    """
    return jsonify({'ok': True})
