"""
Operator/founder-facing system observability endpoints.

These are not end-user surfaces. They expose the health of the ingestion
pipeline — last run per job, per-domain freshness, and unresolved dead-letters
— so the operator can see at a glance whether the trust surfaces are being
backed by live, healthy data. Gated behind the same admin token that protects
the sync/recalculate write endpoints.
"""

import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from services import sync_metadata
from services import slate_coverage, source_readiness
from utils.auth import require_admin_token


system_bp = Blueprint('system', __name__)

def _utc_iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


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


@system_bp.route('/internal/team-evidence', methods=['GET'])
@require_admin_token
def get_internal_team_evidence():
    """Internal Phase 0G team evidence trail for operator review."""
    from services.internal_team_evidence import (
        TeamEvidenceNotFound,
        TeamEvidenceRequestError,
        build_internal_team_evidence_payload,
        error_payload,
    )

    product_date = (
        request.args.get('date')
        or request.args.get('data_through')
        or request.args.get('dataThrough')
    )
    try:
        payload = build_internal_team_evidence_payload(
            team_id=request.args.get('team_id') or request.args.get('teamId'),
            product_date=product_date,
        )
    except TeamEvidenceRequestError as exc:
        return jsonify(error_payload(str(exc), status=400)), 400
    except TeamEvidenceNotFound as exc:
        return jsonify(error_payload(str(exc), status=404)), 404

    return jsonify(payload)


@system_bp.route('/internal/snapshot-audit', methods=['GET'])
@require_admin_token
def get_internal_snapshot_audit():
    """Internal Phase 0H trusted snapshot audit for operator review.

    Never intentionally 502s: if the full bounded summary cannot finish
    inside safe request limits (statement timeout / time budget / any
    unexpected error), the route degrades to a cheap DB-row fallback payload
    that is explicitly marked non-ratifiable. Stage checkpoints are logged
    (stage names and elapsed ms only — never tokens, query values, or
    payload contents) so a production failure pinpoints the exact stage.
    """
    from services.internal_snapshot_audit import (
        SnapshotAuditRequestError,
        SnapshotAuditSummaryUnavailable,
        build_internal_snapshot_audit_fallback_payload,
        build_internal_snapshot_audit_payload,
        error_payload,
    )
    from utils.db import db

    started = time.monotonic()
    stages = []

    def checkpoint(stage_name):
        stages.append(stage_name)
        current_app.logger.info(
            '[snapshot-audit] stage=%s elapsed_ms=%d',
            stage_name,
            int((time.monotonic() - started) * 1000),
        )

    checkpoint('auth_passed')
    product_date = (
        request.args.get('date')
        or request.args.get('data_through')
        or request.args.get('dataThrough')
    )
    window_days = (
        request.args.get('window')
        or request.args.get('window_days')
        or request.args.get('windowDays')
    )
    checkpoint('request_normalized')

    failure_stage = None
    failure_code = None
    try:
        payload = build_internal_snapshot_audit_payload(
            product_date=product_date,
            window_days=window_days,
            checkpoint=checkpoint,
        )
        checkpoint('summary_succeeded')
        return jsonify(payload)
    except SnapshotAuditRequestError as exc:
        return jsonify(error_payload(str(exc), status=400)), 400
    except SnapshotAuditSummaryUnavailable as exc:
        failure_stage = exc.stage
        failure_code = exc.code
        current_app.logger.warning(
            '[snapshot-audit] summary unavailable; degrading to DB-row '
            'fallback. stage=%s code=%s',
            failure_stage,
            failure_code,
        )
    except Exception as exc:
        failure_stage = stages[-1] if stages else None
        # Class name only: DB error messages can embed connection details.
        failure_code = f'summary_exception:{type(exc).__name__}'
        current_app.logger.warning(
            '[snapshot-audit] summary failed; degrading to DB-row fallback. '
            'stage=%s error_type=%s',
            failure_stage,
            type(exc).__name__,
        )

    db.session.rollback()
    checkpoint('fallback_started')
    try:
        fallback = build_internal_snapshot_audit_fallback_payload(
            product_date=product_date,
            window_days=window_days,
            failure_stage=failure_stage,
            failure_code=failure_code,
            checkpoint=checkpoint,
        )
    except Exception:
        current_app.logger.exception(
            'Internal route /internal/snapshot-audit fallback failed; '
            '@require_admin_token remains aligned with /internal/pitcher-evidence.'
        )
        return jsonify(error_payload(
            'internal_snapshot_audit_failed',
            status=500,
        )), 500

    checkpoint('fallback_succeeded')
    return jsonify(fallback), 200


@system_bp.route('/internal/pitcher-evidence', methods=['GET'])
@require_admin_token
def get_internal_pitcher_evidence():
    """Internal Phase 0F pitcher evidence trail for operator review."""
    from services.internal_pitcher_evidence import (
        PitcherEvidenceNotFound,
        PitcherEvidenceRequestError,
        build_internal_pitcher_evidence_payload,
        error_payload,
    )

    product_date = (
        request.args.get('date')
        or request.args.get('data_through')
        or request.args.get('dataThrough')
    )
    try:
        payload = build_internal_pitcher_evidence_payload(
            pitcher_id=request.args.get('pitcher_id') or request.args.get('pitcherId'),
            mlb_id=request.args.get('mlb_id') or request.args.get('mlbId'),
            product_date=product_date,
        )
    except PitcherEvidenceRequestError as exc:
        return jsonify(error_payload(str(exc), status=400)), 400
    except PitcherEvidenceNotFound as exc:
        return jsonify(error_payload(str(exc), status=404)), 404

    return jsonify(payload)
