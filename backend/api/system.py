"""
Operator/founder-facing system observability endpoints.

These are not end-user surfaces. They expose the health of the ingestion
pipeline — last run per job, per-domain freshness, and unresolved dead-letters
— so the operator can see at a glance whether the trust surfaces are being
backed by live, healthy data. Gated behind the same admin token that protects
the sync/recalculate write endpoints.
"""

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from services import sync_metadata
from utils.auth import require_admin_token


system_bp = Blueprint('system', __name__)


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
            'freshness': {
                'freshness_state': 'metadata_unavailable',
                'degradation': {'state': 'unavailable', 'fail_closed': True},
            },
            'sync_status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'last_successful_sync': None,
            'dead_letters': {'unresolved_count': 0, 'recent': []},
            'error': 'Pipeline health metadata unavailable.',
        }), 200
