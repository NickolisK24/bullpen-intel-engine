"""Digest preferences, unsubscribe & engagement tracking (Phase D2D + D2E).

Surfaces:

  • /api/digest/preferences  (authenticated) — read and update the user's digest
    opt-in and cadence. Opt-in is explicit; a user is never enrolled by default.
  • /api/digest/unsubscribe  (no auth) — a signed, user-scoped, one-click link
    placed in every digest email that disables the digest.
  • /api/digest/open         (no auth) — a 1x1 pixel that records an email open.
  • /api/digest/click        (no auth) — records a deep-link click, attributes a
    return, and redirects to the team's view.

The open/click endpoints are our own (provider-independent) tracking; no email is
sent here and nothing is scheduled or composed.
"""

from flask import Blueprint, Response, current_app, g, jsonify, redirect, request

from models.user import User
from services.notification_prefs import (
    VALID_CADENCES,
    apply_digest_prefs,
    disable_digest,
    get_digest_prefs,
)
from services.digest_metrics import record_click, record_open
from utils.auth_tokens import verify_unsubscribe_token
from utils.db import db
from utils.identity import require_authenticated_user


digest_bp = Blueprint('digest', __name__)

# A 1x1 transparent GIF returned by the open-tracking pixel.
_TRACKING_PIXEL = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01'
    b'\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


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


def _pixel_response():
    response = Response(_TRACKING_PIXEL, mimetype='image/gif')
    # Discourage caching so repeat opens are observed; never breaks rendering.
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    return response


@digest_bp.route('/open', methods=['GET'])
def open_pixel():
    """Record an email open from a signed tracking token; always return a pixel.

    No auth: this is loaded by the recipient's email client. An invalid/expired
    token simply yields the pixel without recording (a safe no-op).
    """
    record_open((request.args.get('t') or '').strip())
    return _pixel_response()


def _team_deep_link(delivery):
    base = (current_app.config.get('FRONTEND_BASE_URL') or '').rstrip('/')
    if delivery is not None and delivery.team_id is not None:
        return f'{base}/?team={delivery.team_id}&source=digest'
    return f'{base}/' if base else '/'


@digest_bp.route('/click', methods=['GET'])
def click_redirect():
    """Record a deep-link click + attribute a return, then redirect to the team.

    No auth. The redirect target is always reconstructed from our own config
    (FRONTEND_BASE_URL + the delivery's team), never from a request parameter, so
    there is no open-redirect surface. An invalid token redirects to the app root.
    """
    delivery = record_click((request.args.get('t') or '').strip())
    return redirect(_team_deep_link(delivery), code=302)
