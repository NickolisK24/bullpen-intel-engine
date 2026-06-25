"""Digest preferences, unsubscribe & engagement tracking (Phase D2D + D2E).

Surfaces:

  • /api/digest/preferences  (authenticated) — read and update the user's digest
    opt-in and cadence. Opt-in is explicit; a user is never enrolled by default.
  • /api/digest/unsubscribe  (no auth) — a signed, user-scoped, one-click link
    placed in every digest email that disables the digest.
  • /api/digest/open         (no auth) — a 1x1 pixel that records an email open.
  • /api/digest/click        (no auth) — records a deep-link click, attributes a
    return, and redirects to the team's view.
  • /api/digest/email-events (signature-gated) — provider (Resend) deliverability
    webhook → canonical digest_delivered / digest_bounced / digest_complaint.

The open/click endpoints are our own (provider-independent) tracking; no email is
sent here and nothing is scheduled or composed. The webhook only observes
provider-reported delivery — it never changes digest behavior or existing metrics.
"""

from datetime import timedelta

from flask import Blueprint, Response, current_app, g, jsonify, redirect, request

from models.digest_metrics import STATUS_SENT, DigestDelivery
from models.user import User
from services.notification_prefs import (
    VALID_CADENCES,
    apply_digest_prefs,
    disable_digest,
    get_digest_prefs,
)
from services.digest_metrics import record_click, record_open
from services.product_events import (
    SOURCE_ONE_CLICK,
    SOURCE_SETTINGS,
    normalize_short_text,
    record_digest_bounced,
    record_digest_complaint,
    record_digest_delivered,
    record_digest_optin_change,
)
from utils.auth_tokens import normalize_email, verify_unsubscribe_token
from utils.db import db
from utils.identity import require_authenticated_user
from utils.time import utc_now_naive
from utils.webhook_signing import verify_webhook_signature


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

    before = get_digest_prefs(g.current_user)
    prefs = apply_digest_prefs(g.current_user, enabled=enabled, cadence=cadence)
    record_digest_optin_change(g.current_user, before, prefs, source=SOURCE_SETTINGS)
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
        before = get_digest_prefs(user)
        disable_digest(user)
        record_digest_optin_change(user, before, get_digest_prefs(user), source=SOURCE_ONE_CLICK)
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


# ── Provider deliverability webhook (Phase D2A-7) ─────────────────────────────

# How far back to correlate a provider event to a sent digest for the recipient.
# Generous because a spam complaint can arrive days after the send.
DELIVERABILITY_CORRELATION_WINDOW_DAYS = 30


def _first_recipient(data):
    to = data.get('to')
    if isinstance(to, list):
        to = to[0] if to else None
    return normalize_email(to) if to else None


def _user_for_email(email):
    if not email:
        return None
    return User.query.filter_by(email=email).first()


def _recent_sent_digest(user):
    """Most recent SENT digest delivery for the user within the window, or None.

    This both confirms the provider event concerns a DIGEST email (not, e.g., a
    magic link) and supplies a best-effort delivery_id / team_id for the fact.
    """
    if user is None:
        return None
    cutoff = utc_now_naive() - timedelta(days=DELIVERABILITY_CORRELATION_WINDOW_DAYS)
    return (
        DigestDelivery.query
        .filter(
            DigestDelivery.user_id == user.id,
            DigestDelivery.status == STATUS_SENT,
            DigestDelivery.sent_at.isnot(None),
            DigestDelivery.sent_at >= cutoff,
        )
        .order_by(DigestDelivery.sent_at.desc())
        .first()
    )


@digest_bp.route('/email-events', methods=['POST'])
def email_events_webhook():
    """Provider (Resend) deliverability webhook → canonical digest events.

    Signature-gated (Svix). Maps email.delivered / email.bounced / email.complained
    to digest_delivered / digest_bounced / digest_complaint for DIGEST emails only,
    correlated to a recent sent delivery for the recipient. Resolves the user by
    email but never stores the email, and never changes digest behavior or existing
    metrics. Returns 200 for any accepted (validly signed) request so the provider
    does not retry; an invalid signature is rejected.
    """
    raw_body = request.get_data(as_text=True)
    secret = current_app.config.get('EMAIL_WEBHOOK_SECRET')
    env = current_app.config.get('APP_ENV', 'development')
    if secret:
        valid = verify_webhook_signature(
            secret,
            svix_id=request.headers.get('svix-id'),
            svix_timestamp=request.headers.get('svix-timestamp'),
            body=raw_body,
            signature_header=request.headers.get('svix-signature'),
        )
        if not valid:
            return jsonify({'error': 'invalid_signature'}), 400
    elif env == 'production':
        # Never accept unsigned provider events in production.
        return jsonify({'error': 'webhook_not_configured'}), 403
    else:
        current_app.logger.warning(
            '/api/digest/email-events accepted without verification: '
            'EMAIL_WEBHOOK_SECRET is unset (development).'
        )

    payload = request.get_json(silent=True) or {}
    event_type = str(payload.get('type') or '')
    if event_type not in ('email.delivered', 'email.bounced', 'email.complained'):
        return jsonify({'ok': True, 'ignored': event_type or 'unknown'}), 200

    data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    user = _user_for_email(_first_recipient(data))
    delivery = _recent_sent_digest(user)
    if user is None or delivery is None:
        # Not a known digest recipient with a recent send -> not a digest fact.
        return jsonify({'ok': True, 'ignored': 'no_digest_correlation'}), 200

    provider_message_id = normalize_short_text(data.get('email_id') or data.get('id'))
    if event_type == 'email.delivered':
        record_digest_delivered(
            user_id=user.id, delivery_id=delivery.id, team_id=delivery.team_id,
            provider_message_id=provider_message_id,
        )
    elif event_type == 'email.bounced':
        bounce = data.get('bounce') if isinstance(data.get('bounce'), dict) else {}
        record_digest_bounced(
            user_id=user.id, delivery_id=delivery.id, team_id=delivery.team_id,
            provider_message_id=provider_message_id,
            bounce_type=normalize_short_text(bounce.get('type')),
        )
    else:  # email.complained
        record_digest_complaint(
            user_id=user.id, delivery_id=delivery.id, team_id=delivery.team_id,
            provider_message_id=provider_message_id,
        )
    db.session.commit()
    return jsonify({'ok': True}), 200
