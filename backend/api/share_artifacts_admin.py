"""Internal admin trigger for governed Team State Share Artifact generation
(Share Cards SC-03A).

Internal only. Reuses the existing ``require_admin_token`` authorization. This
introduces no public route, no ``/share`` page, and no public artifact API. It
validates its inputs, returns the deterministic generation result contract, and
fails closed with sanitized errors (no raw internal exceptions are exposed).
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request

from utils.auth import require_admin_token


share_artifacts_admin_bp = Blueprint('share_artifacts_admin', __name__)


def _parse_team_id(raw):
    try:
        team_id = int(raw)
    except (TypeError, ValueError):
        return None
    return team_id if team_id > 0 else None


def _parse_requested_date(raw):
    if raw in (None, ''):
        return None, True
    try:
        return date.fromisoformat(str(raw)), True
    except (TypeError, ValueError):
        return None, False


@share_artifacts_admin_bp.route('/team-state/generate', methods=['POST'])
@require_admin_token
def generate_team_state():
    body = request.get_json(silent=True) or {}

    team_id = _parse_team_id(body.get('team_id', request.args.get('team_id')))
    if team_id is None:
        return jsonify({'error': 'invalid_team_id'}), 400

    requested_date, ok = _parse_requested_date(
        body.get('requested_date', request.args.get('requested_date'))
    )
    if not ok:
        return jsonify({'error': 'invalid_requested_date'}), 400

    # Import lazily so app import never pulls the generation graph at load time.
    from services.share_artifact_generation import (
        OUTCOME_FAILED_CLOSED,
        generate_team_state_artifact,
    )

    try:
        result = generate_team_state_artifact(
            team_id,
            requested_date=requested_date,
            actor='admin_api',
            request_source='internal_admin_api',
        )
    except Exception:
        # Defense in depth: the service already fails closed, but never leak a
        # raw internal exception to the caller.
        return jsonify({'outcome': OUTCOME_FAILED_CLOSED, 'failure_code': 'internal_error'}), 503

    status = 503 if result.outcome == OUTCOME_FAILED_CLOSED else 200
    return jsonify(result.to_dict()), status
