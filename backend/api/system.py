"""
Operator/founder-facing system observability endpoints.

These are not end-user surfaces. They expose the health of the ingestion
pipeline — last run per job, per-domain freshness, and unresolved dead-letters
— so the operator can see at a glance whether the trust surfaces are being
backed by live, healthy data. Gated behind the same admin token that protects
the sync/recalculate write endpoints.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify

from services import sync_metadata
from utils.auth import require_admin_token


system_bp = Blueprint('system', __name__)


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
