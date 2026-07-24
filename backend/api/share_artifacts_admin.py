"""Internal admin API for governed Team State Share Artifact generation and
operations (Share Cards SC-03A trigger + SC-03B-01 batch + SC-03B-03 operations).

Internal only. Reuses the existing ``require_admin_token`` authorization. This
introduces no public route, no ``/share`` page, and no public artifact API. The
generation routes validate inputs and return the deterministic result contract;
the read-only operations routes (SC-03B-03) summarize existing durable records —
they invoke no generation and mutate nothing. Everything fails closed with
sanitized errors (no raw internal exceptions are exposed).
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request

from api.query_params import (
    parse_enum_param,
    parse_non_negative_int_param,
    parse_positive_int_param,
    query_param_error_response,
)
from utils.auth import require_admin_token


share_artifacts_admin_bp = Blueprint('share_artifacts_admin', __name__)

# Bounded operations read sizes.
_OPS_DEFAULT_LIMIT = 25
_OPS_MAX_LIMIT = 100


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


def _parse_required_date(raw):
    if raw in (None, ''):
        return None, False
    try:
        return date.fromisoformat(str(raw)), True
    except (TypeError, ValueError):
        return None, False


def _parse_team_ids(raw):
    """Parse an optional explicit team subset. Returns (team_ids, ok).

    ``None``/absent means "the full canonical set" (team_ids=None, ok=True). A
    provided value must be a non-empty list of ints; anything else is invalid.
    """
    if raw is None:
        return None, True
    if not isinstance(raw, list) or not raw:
        return None, False
    parsed = []
    for value in raw:
        team_id = _parse_team_id(value)
        if team_id is None:
            return None, False
        parsed.append(team_id)
    return parsed, True


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


@share_artifacts_admin_bp.route('/team-state/batch', methods=['POST'])
@require_admin_token
def generate_team_state_batch():
    """Attempt Team State generation across the canonical MLB team set.

    Internal/admin only. Requires an explicit trusted source authority
    (``source_snapshot_id`` + ``product_date``); an optional ``team_ids`` subset
    restricts the run. Delegates every team to the single-team generation
    service and returns the deterministic coverage summary. A globally invalid
    source is refused (409) before any team is attempted; malformed input is a
    400; unexpected internal errors fail closed (503) without leaking details.
    """
    body = request.get_json(silent=True) or {}

    source_snapshot_id = _parse_team_id(
        body.get('source_snapshot_id', request.args.get('source_snapshot_id'))
    )
    if source_snapshot_id is None:
        return jsonify({'status': 'failed', 'error': 'invalid_source_snapshot_id'}), 400

    product_date, ok = _parse_required_date(
        body.get('product_date', request.args.get('product_date'))
    )
    if not ok:
        return jsonify({'status': 'failed', 'error': 'invalid_product_date'}), 400

    team_ids, ok = _parse_team_ids(body.get('team_ids'))
    if not ok:
        return jsonify({'status': 'failed', 'error': 'invalid_team_ids'}), 400

    # Import lazily so app import never pulls the generation graph at load time.
    from services.share_artifact_batch_generation import (
        BATCH_ACTOR,
        BatchSourceAuthorityError,
        BatchValidationError,
        generate_team_state_artifacts_batch,
    )

    try:
        result = generate_team_state_artifacts_batch(
            source_snapshot_id=source_snapshot_id,
            product_date=product_date,
            actor=BATCH_ACTOR,
            team_ids=team_ids,
        )
    except BatchValidationError as exc:
        return jsonify({'status': 'failed', 'error': str(exc)}), 400
    except BatchSourceAuthorityError as exc:
        # The declared/shared source is globally unusable — refuse the whole
        # batch before any team is attempted (precondition conflict).
        return jsonify({'status': 'failed', 'reason': exc.reason_code}), 409
    except Exception:
        return jsonify({'status': 'failed', 'error': 'internal_error'}), 503

    payload = result.to_dict()
    payload['status'] = 'completed' if result.is_complete else 'incomplete'
    return jsonify(payload), 200


# ---------------------------------------------------------------------------
# SC-03B-03 — read-only operations / coverage / monitoring
# ---------------------------------------------------------------------------


@share_artifacts_admin_bp.route('/operations/overview', methods=['GET'])
@require_admin_token
def operations_overview():
    """Coverage + integrity overview for the latest trusted snapshot (read-only).

    Invokes no generation and mutates nothing. Fails closed: an impossible
    accounting result surfaces as a sanitized 500 rather than a plausible summary.
    """
    from services.share_artifact_operations import (
        ShareArtifactOperationsError,
        build_coverage_overview,
    )
    try:
        overview = build_coverage_overview()
    except ShareArtifactOperationsError:
        return jsonify({'error': 'operations_accounting_error'}), 500
    except Exception:
        return jsonify({'error': 'internal_error'}), 503
    return jsonify(overview), 200


@share_artifacts_admin_bp.route('/operations/artifacts', methods=['GET'])
@require_admin_token
def operations_artifacts():
    """Bounded, newest-first recent immutable artifacts (read-only projection)."""
    limit, err = parse_positive_int_param(
        request.args, 'limit', default=_OPS_DEFAULT_LIMIT, maximum=_OPS_MAX_LIMIT, clamp_max=True,
    )
    if err:
        return query_param_error_response(err)
    offset, err = parse_non_negative_int_param(request.args, 'offset', default=0)
    if err:
        return query_param_error_response(err)
    team_id, err = parse_positive_int_param(request.args, 'team_id', default=None)
    if err:
        return query_param_error_response(err)

    from services.share_artifact_operations import list_operational_artifacts
    try:
        payload = list_operational_artifacts(team_id=team_id, limit=limit, offset=offset)
    except Exception:
        return jsonify({'error': 'internal_error'}), 503
    return jsonify(payload), 200


@share_artifacts_admin_bp.route('/operations/audits', methods=['GET'])
@require_admin_token
def operations_audits():
    """Bounded, newest-first recent generation audit attempts (read-only)."""
    from models.share_artifact_generation_audit import ShareArtifactGenerationAudit

    limit, err = parse_positive_int_param(
        request.args, 'limit', default=_OPS_DEFAULT_LIMIT, maximum=_OPS_MAX_LIMIT, clamp_max=True,
    )
    if err:
        return query_param_error_response(err)
    offset, err = parse_non_negative_int_param(request.args, 'offset', default=0)
    if err:
        return query_param_error_response(err)
    team_id, err = parse_positive_int_param(request.args, 'team_id', default=None)
    if err:
        return query_param_error_response(err)
    source_snapshot_id, err = parse_positive_int_param(request.args, 'source_snapshot_id', default=None)
    if err:
        return query_param_error_response(err)
    outcome, err = parse_enum_param(
        request.args, 'outcome', ShareArtifactGenerationAudit.OUTCOMES, normalize=str.lower,
    )
    if err:
        return query_param_error_response(err)
    product_date, ok = _parse_requested_date(request.args.get('product_date'))
    if not ok:
        return jsonify({'error': 'invalid_product_date'}), 400

    from services.share_artifact_operations import (
        ShareArtifactOperationsError,
        list_operational_audits,
    )
    try:
        payload = list_operational_audits(
            team_id=team_id, outcome=outcome, source_snapshot_id=source_snapshot_id,
            product_date=product_date, limit=limit, offset=offset,
        )
    except ShareArtifactOperationsError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        return jsonify({'error': 'internal_error'}), 503
    return jsonify(payload), 200
