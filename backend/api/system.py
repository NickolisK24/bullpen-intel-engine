"""
Operator/founder-facing system observability endpoints.

These are not end-user surfaces. They expose the health of the ingestion
pipeline — last run per job, per-domain freshness, and unresolved dead-letters
— so the operator can see at a glance whether the trust surfaces are being
backed by live, healthy data. Gated behind the same admin token that protects
the sync/recalculate write endpoints.
"""

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from services import sync_metadata
from services import slate_coverage, source_readiness
from utils.auth import require_admin_token


system_bp = Blueprint('system', __name__)

PRODUCT_EVENTS_DEFAULT_LIMIT = 25
PRODUCT_EVENTS_MAX_LIMIT = 100
PRODUCT_EVENT_NAME_MAX_LEN = 64
PRODUCT_EVENT_PAYLOAD_STRING_MAX_LEN = 120
PRODUCT_EVENT_PAYLOAD_KEY_LIMIT = 12
PRODUCT_EVENT_SENSITIVE_KEY_PARTS = ('email', 'token', 'secret', 'address')


def _redact_email(email):
    if not email or '@' not in str(email):
        return '***'
    name, _, domain = str(email).partition('@')
    return f'{(name[:1] or "")}***@{domain}'


def _int_arg(name, *, default, minimum, maximum):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _event_name_arg():
    value = str(request.args.get('event_name') or '').strip()
    return value[:PRODUCT_EVENT_NAME_MAX_LEN] or None


def _utc_iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _payload_value_summary(key, value):
    key_text = str(key or '').lower()
    if any(part in key_text for part in PRODUCT_EVENT_SENSITIVE_KEY_PARTS):
        return '[redacted]'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if '@' in text:
            return '[redacted]'
        if len(text) > PRODUCT_EVENT_PAYLOAD_STRING_MAX_LEN:
            return f'{text[:PRODUCT_EVENT_PAYLOAD_STRING_MAX_LEN]}...'
        return text
    if isinstance(value, list):
        return {'type': 'array', 'count': len(value)}
    if isinstance(value, dict):
        return {
            'type': 'object',
            'keys': sorted(str(k) for k in value.keys())[:PRODUCT_EVENT_PAYLOAD_KEY_LIMIT],
        }
    return str(type(value).__name__)


def _payload_summary(payload):
    if not isinstance(payload, dict) or not payload:
        return {}
    return {
        str(key)[:PRODUCT_EVENT_NAME_MAX_LEN]: _payload_value_summary(key, value)
        for key, value in payload.items()
    }


def _product_event_admin_row(event):
    return {
        'id': event.id,
        'event_name': event.event_name,
        'occurred_at': _utc_iso(event.occurred_at),
        'created_at': _utc_iso(event.created_at),
        'schema_version': event.schema_version,
        'user_id': event.user_id,
        'anon_id_present': bool(event.anon_id),
        'team_id': event.team_id,
        'run_id': event.run_id,
        'delivery_id': event.delivery_id,
        'source': event.source,
        'payload_keys': sorted(str(key) for key in (event.payload or {}).keys()) if isinstance(event.payload, dict) else [],
        'payload_summary': _payload_summary(event.payload),
    }


@system_bp.route('/digest-status', methods=['GET'])
@require_admin_token
def get_digest_status():
    """Operator visibility into the daily team digest.

    Runs the digest decision pipeline in dry-run mode (no email is sent) and
    reports how many users were considered, how many would send, and how many
    were suppressed or skipped (by reason). Safe to call anytime; this is a
    point-in-time snapshot, not a metrics system.
    """
    from services.digest_delivery import run_digest_job
    summary = run_digest_job(current_app._get_current_object(), dry_run=True)
    return jsonify(summary)


@system_bp.route('/digest-metrics', methods=['GET'])
@require_admin_token
def get_digest_metrics():
    """Durable digest metrics for the operator (Phase D2E).

    Lifetime totals (sent, suppressed, opens, clicks, attributed returns) plus
    open/click/return rates and recent run aggregates — enough to answer whether
    the digest is bringing users back. Admin-gated; measurement only.
    """
    from services.digest_metrics import metrics_overview
    return jsonify(metrics_overview())


@system_bp.route('/product-events', methods=['GET'])
@require_admin_token
def get_product_events():
    """Recent Product Intelligence events for operator verification.

    Read-only and admin-gated. This endpoint intentionally exposes only the
    fields needed to confirm that the append-only product_events stream is
    flowing; it never returns raw anon_id values or email addresses.
    """
    from models.product_event import ProductEvent

    limit = _int_arg(
        'limit',
        default=PRODUCT_EVENTS_DEFAULT_LIMIT,
        minimum=1,
        maximum=PRODUCT_EVENTS_MAX_LIMIT,
    )
    event_name = _event_name_arg()

    query = ProductEvent.query
    if event_name:
        query = query.filter(ProductEvent.event_name == event_name)
    events = (
        query
        .order_by(ProductEvent.occurred_at.desc(), ProductEvent.id.desc())
        .limit(limit)
        .all()
    )

    return jsonify({
        'capability': 'product_intelligence_events',
        'limit': limit,
        'filters': {'event_name': event_name},
        'events': [_product_event_admin_row(event) for event in events],
    })


@system_bp.route('/product-event-heartbeat', methods=['GET'])
@require_admin_token
def get_product_event_heartbeat():
    """Per-event Name / Count / Most-Recent for operator verification.

    Lets an operator confirm at a glance that every Product Intelligence event is
    still flowing — every canonical event is listed, so a zero count or a stale
    timestamp surfaces a stopped beacon. Operational verification only: no rates,
    no rollups, no time series, no analytics.
    """
    from models.product_event import ProductEvent
    from services.product_events import CANONICAL_PRODUCT_EVENTS
    from utils.db import db

    rows = (
        db.session.query(
            ProductEvent.event_name,
            db.func.count(ProductEvent.id),
            db.func.max(ProductEvent.occurred_at),
        )
        .group_by(ProductEvent.event_name)
        .all()
    )
    seen = {name: (count, most_recent) for name, count, most_recent in rows}

    events = []
    for name in CANONICAL_PRODUCT_EVENTS:
        count, most_recent = seen.pop(name, (0, None))
        events.append({
            'event_name': name,
            'count': int(count or 0),
            'most_recent': _utc_iso(most_recent),
        })
    # Defensive: surface any non-canonical names already in the table, too.
    for name in sorted(seen):
        count, most_recent = seen[name]
        events.append({
            'event_name': name,
            'count': int(count or 0),
            'most_recent': _utc_iso(most_recent),
        })

    return jsonify({
        'capability': 'product_intelligence_heartbeat',
        'generated_at': _utc_iso(datetime.now(timezone.utc)),
        'events': events,
    })


@system_bp.route('/digest-test-send', methods=['POST'])
@require_admin_token
def digest_test_send():
    """Admin-gated SINGLE-USER digest test (dry-run by default).

    The controlled-smoke-test path. Safety properties:
      • Targets exactly ONE user, by explicit email — it never iterates users,
        so it can never broadcast (a missing email is a 400, not "everyone").
      • Dry-run unless ``send: true`` is passed explicitly; dry-run sends nothing
        and persists nothing.
      • Does NOT require DIGEST_SEND_ENABLED (that flag only gates the scheduled
        broad job, which this path never invokes) and never schedules anything.
      • Respects opt-in / unsubscribe unless ``force: true`` (an explicit
        single-user test override). The verified-email gate and composer
        suppression are always enforced — force never sends to an unverified
        address and never sends a suppressed (no-team / no-change / stale) digest.
      • Records exactly one delivery (+ tracking) only on a real send; logs the
        target redacted.

    Body: {"email": "<addr>", "send": false, "force": false}
    """
    from models.user import User
    from services.digest_delivery import deliver_team_digest
    from services.digest_metrics import DbDigestRecorder
    from utils.auth_tokens import normalize_email
    from utils.db import db

    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email'))
    if not email:
        return jsonify({'error': 'email_required'}), 400
    send = data.get('send') is True
    force = data.get('force') is True

    user = User.query.filter_by(email=email).first()
    if user is None:
        return jsonify({'error': 'user_not_found', 'target': _redact_email(email)}), 404

    recorder = DbDigestRecorder() if send else None
    result = deliver_team_digest(
        user, dry_run=not send, force=force, recorder=recorder,
    )
    if send:
        db.session.commit()

    current_app.logger.info(
        '[digest-test] target=%s send=%s force=%s status=%s',
        _redact_email(email), send, force, result.get('status'),
    )
    return jsonify({
        'mode': 'send' if send else 'dry_run',
        'target': _redact_email(email),
        'user_id': user.id,
        'force': force,
        'requires_digest_send_enabled': False,
        'digest_send_enabled': bool(current_app.config.get('DIGEST_SEND_ENABLED')),
        'result': result,
        'links': {
            'frontend_base_url': current_app.config.get('FRONTEND_BASE_URL'),
            'public_api_base_url': current_app.config.get('PUBLIC_API_BASE_URL') or None,
            'public_api_base_url_set': bool(current_app.config.get('PUBLIC_API_BASE_URL')),
        },
    })


@system_bp.route('/email-delivery-health', methods=['GET'])
@require_admin_token
def get_email_delivery_health():
    """Operator check that the active email provider is configured to send.

    Reports the resolved provider, whether a sender is set, readiness, and any
    config issues. Admin-gated; never exposes the API key.
    """
    from utils.email_delivery import email_delivery_health
    return jsonify(email_delivery_health())


@system_bp.route('/pipeline-health', methods=['GET'])
@require_admin_token
def get_pipeline_health():
    """
    Pipeline health for the operator: last run per job with its status,
    per-domain freshness classification (fresh / stale / unavailable), and the
    count of unresolved dead-letters.

    Never raises into a 500 for a DB hiccup — it degrades to an explicit
    unavailable payload so the health check itself fails closed rather than
    looking healthy.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        payload = sync_metadata.pipeline_health_payload()
        payload['generated_at'] = generated_at
        return jsonify(payload)
    except Exception:
        return jsonify({
            'capability': 'pipeline_health',
            'generated_at': generated_at,
            'jobs': [],
            'domains': {},
            'source_readiness': source_readiness.unknown_source_readiness_payload(),
            'freshness': {
                'freshness_state': 'metadata_unavailable',
                'degradation': {'state': 'unavailable', 'fail_closed': True},
            },
            'slate_coverage': slate_coverage.unknown_slate_coverage(),
            'sync_status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'last_successful_sync': None,
            'dead_letters': {'unresolved_count': 0, 'recent': []},
            'error': 'Pipeline health metadata unavailable.',
        }), 200
