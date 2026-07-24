"""Shared request handling for the Share Artifact operations reads (SC-03B-03).

Both authorization boundaries — the admin-token API (SC-03B-03A) and the
browser-session API (SC-03B-03B) — delegate here so they share the exact same
operational read service, view-model contracts, validation, pagination rules,
and status vocabulary. Only the authorization differs; the read logic and its
bounds live in one place and are never duplicated per boundary.

These builders return ``(response, status)`` where ``response`` is a Flask JSON
response the caller may further annotate (e.g. add no-store headers on the
browser boundary). They invoke no generation and mutate nothing.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify

from api.query_params import (
    parse_enum_param,
    parse_non_negative_int_param,
    parse_positive_int_param,
    query_param_error_response,
)


OPS_DEFAULT_LIMIT = 25
OPS_MAX_LIMIT = 100


def _parse_iso_date(raw):
    if raw in (None, ''):
        return None, True
    try:
        return date.fromisoformat(str(raw)), True
    except (TypeError, ValueError):
        return None, False


def build_overview_response():
    from services.share_artifact_operations import (
        ShareArtifactOperationsError,
        build_coverage_overview,
    )
    try:
        return jsonify(build_coverage_overview()), 200
    except ShareArtifactOperationsError:
        return jsonify({'error': 'operations_accounting_error'}), 500
    except Exception:
        return jsonify({'error': 'internal_error'}), 503


def build_artifacts_response(args):
    limit, err = parse_positive_int_param(
        args, 'limit', default=OPS_DEFAULT_LIMIT, maximum=OPS_MAX_LIMIT, clamp_max=True,
    )
    if err:
        return query_param_error_response(err)
    offset, err = parse_non_negative_int_param(args, 'offset', default=0)
    if err:
        return query_param_error_response(err)
    team_id, err = parse_positive_int_param(args, 'team_id', default=None)
    if err:
        return query_param_error_response(err)

    from services.share_artifact_operations import list_operational_artifacts
    try:
        return jsonify(list_operational_artifacts(team_id=team_id, limit=limit, offset=offset)), 200
    except Exception:
        return jsonify({'error': 'internal_error'}), 503


def build_audits_response(args):
    from models.share_artifact_generation_audit import ShareArtifactGenerationAudit

    limit, err = parse_positive_int_param(
        args, 'limit', default=OPS_DEFAULT_LIMIT, maximum=OPS_MAX_LIMIT, clamp_max=True,
    )
    if err:
        return query_param_error_response(err)
    offset, err = parse_non_negative_int_param(args, 'offset', default=0)
    if err:
        return query_param_error_response(err)
    team_id, err = parse_positive_int_param(args, 'team_id', default=None)
    if err:
        return query_param_error_response(err)
    source_snapshot_id, err = parse_positive_int_param(args, 'source_snapshot_id', default=None)
    if err:
        return query_param_error_response(err)
    outcome, err = parse_enum_param(
        args, 'outcome', ShareArtifactGenerationAudit.OUTCOMES, normalize=str.lower,
    )
    if err:
        return query_param_error_response(err)
    product_date, ok = _parse_iso_date(args.get('product_date'))
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
