"""V5 Bullpen Intelligence observation API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from observations.api_assembly import (
    build_preview_observation_collection,
    build_sample_observation_collection,
    fail_closed_observation_api_payload,
    observation_api_payload,
)


observations_bp = Blueprint('observations', __name__)

OBSERVATION_PROHIBITED_QUERY_TOKENS = (
    'best',
    'recommend',
    'rank',
    'select',
    'matchup',
    'predict',
    'save',
    'injury',
    'performance',
)


@observations_bp.route('', methods=['GET'])
@observations_bp.route('/', methods=['GET'])
def get_observations():
    query_refusal = _query_refusal(request.args)
    if query_refusal:
        return jsonify(query_refusal), 400

    collection = build_sample_observation_collection()
    if collection is None:
        return jsonify(
            fail_closed_observation_api_payload(
                reason_code='builder_validation_failed',
                summary='Observation output is withheld because deterministic builder validation failed.',
                source_mode='deterministic_sample_state',
            )
        )

    return jsonify(
        observation_api_payload(
            collection,
            source_mode='deterministic_sample_state',
        )
    )


@observations_bp.route('/preview', methods=['POST'])
def preview_observations():
    payload = request.get_json(silent=True)
    collection = build_preview_observation_collection(payload)
    if collection is None:
        return jsonify(
            fail_closed_observation_api_payload(
                reason_code='invalid_supplied_state',
                summary='Observation output is withheld because supplied state failed validation.',
                source_mode='supplied_preview_state',
            )
        ), 400

    return jsonify(
        observation_api_payload(
            collection,
            source_mode='supplied_preview_state',
        )
    )


def _query_refusal(args):
    for key in args.keys():
        normalized_key = str(key).lower()
        reason_code = (
            'forbidden_request_parameter'
            if _contains_prohibited_query_intent(normalized_key)
            else 'unsupported_request_parameter'
        )
        for value in args.getlist(key):
            if _contains_prohibited_query_intent(str(value).lower()):
                reason_code = 'forbidden_request_parameter'
                break
        return fail_closed_observation_api_payload(
            reason_code=reason_code,
            summary='Observation output is withheld because request parameters are not supported for this route.',
            source_mode='deterministic_sample_state',
        )
    return None


def _contains_prohibited_query_intent(value: str) -> bool:
    return any(token in value for token in OBSERVATION_PROHIBITED_QUERY_TOKENS)
