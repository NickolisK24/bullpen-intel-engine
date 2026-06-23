"""Digest preferences + one-click unsubscribe (Phase D2D).

Two small surfaces:

  • /api/digest/preferences  (authenticated) — read and update the user's digest
    opt-in and cadence. Opt-in is explicit; a user is never enrolled by default.
  • /api/digest/unsubscribe  (no auth) — a signed, user-scoped, one-click link
    placed in every digest email that disables the digest.

No email is sent here and nothing is scheduled — this only manages preferences.
"""

from flask import Blueprint, g, jsonify, request

from models.user import User
from services.notification_prefs import (
    VALID_CADENCES,
    apply_digest_prefs,
    disable_digest,
    get_digest_prefs,
)
from utils.auth_tokens import verify_unsubscribe_token
from utils.db import db
from utils.identity import require_authenticated_user


digest_bp = Blueprint('digest', __name__)


@digest_bp.route('/preferences', methods=['GET'])
@require_authenticated_user
def get_preferences():
    """Return the signed-in user's normalized digest preferences."""
    return jsonify({'notification_prefs': get_digest_prefs(g.current_user)}), 200


@digest_bp.route('/preferences', methods=['PUT'])
@require_authenticated_user
def update_preferences():
    """Update the user's digest opt-in / cadence (explicit opt-in required)."""
    data = request.get_json(silent=True) or {}
    enabled = data.get('digest_enabled', None)
    cadence = data.get('digest_cadence', None)

    if enabled is not None and not isinstance(enabled, bool):
        return jsonify({'error': 'invalid_digest_enabled'}), 400
    if cadence is not None and (
        not isinstance(cadence, str) or cadence.strip().lower() not in VALID_CADENCES
    ):
        return jsonify({'error': 'invalid_cadence'}), 400

    prefs = apply_digest_prefs(g.current_user, enabled=enabled, cadence=cadence)
    db.session.commit()
    return jsonify({'notification_prefs': prefs}), 200


def _unsubscribe_html(ok):
    if ok:
        body = (
            '<h1>You are unsubscribed</h1>'
            '<p>You will no longer receive team digest emails. '
            'You can turn them back on anytime from your account.</p>'
        )
    else:
        body = (
            '<h1>Link not valid</h1>'
            '<p>This unsubscribe link is invalid or has expired.</p>'
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>BaseballOS digest</title></head>'
        f'<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;">{body}</body></html>'
    )


@digest_bp.route('/unsubscribe', methods=['GET', 'POST'])
def unsubscribe():
    """One-click unsubscribe via a signed, user-scoped token (no auth required).

    Disables the digest for the token's user. Always returns 200 so a click from
    an email never shows an error page; ``?format=json`` returns a JSON payload
    instead of the HTML confirmation. An invalid/expired token is a safe no-op.
    """
    token = (
        request.args.get('token')
        or (request.get_json(silent=True) or {}).get('token')
        or ''
    ).strip()
    wants_json = request.args.get('format') == 'json'

    claims = verify_unsubscribe_token(token)
    user = db.session.get(User, claims['uid']) if claims else None
    valid = bool(
        claims
        and user is not None
        and (not claims.get('email') or user.email == claims.get('email'))
    )

    if valid:
        disable_digest(user)
        db.session.commit()

    if wants_json:
        return jsonify({'ok': valid, 'digest_enabled': False if valid else None}), 200
    return _unsubscribe_html(valid), 200
