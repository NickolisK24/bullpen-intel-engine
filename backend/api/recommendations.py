"""Recommendation Engine V1 API routes."""

from collections.abc import Mapping

from flask import Blueprint, jsonify, request

from recommendation import (
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationEngine,
    RecommendationRequest,
)


recommendations_bp = Blueprint('recommendations', __name__)

CONTRACT_DOCUMENT = 'docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md'
POLICY_DOCUMENT = 'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'
IMPLEMENTATION_PLAN = 'docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md'
API_ENGINE_VERSION = 'recommendation_engine_v1_candidate_api'


@recommendations_bp.route('/candidate', methods=['POST'])
def evaluate_candidate_recommendation():
    body = request.get_json(silent=True)
    engine = RecommendationEngine()

    try:
        if not isinstance(body, Mapping):
            result = engine.recommend()
            return jsonify(_response_payload(result)), 400

        result, candidate_payload = _evaluate_body(engine, body)
        return jsonify(_response_payload(result, candidate_payload=candidate_payload))
    except Exception:
        result = engine.recommend(candidate='invalid')
        return jsonify(_response_payload(result)), 500


def _evaluate_body(engine, body):
    request_value = _request_from_body(body)

    if 'candidates' in body:
        candidates_payload = body.get('candidates')
        if isinstance(candidates_payload, list):
            candidates = tuple(
                _candidate_from_payload(candidate_payload)
                for candidate_payload in candidates_payload
            )
            request_value = _request_from_body(body, candidates=candidates)
            candidate_payload = (
                candidates_payload[0]
                if candidates_payload and isinstance(candidates_payload[0], Mapping)
                else None
            )
        else:
            request_value = _request_from_body(body, candidates=())
            candidate_payload = None
        return engine.recommend(request_value), candidate_payload

    candidate_payload = body.get('candidate')
    candidate = _candidate_from_payload(candidate_payload)
    if isinstance(candidate, RecommendationCandidate):
        return engine.recommend(request=request_value, candidate=candidate), candidate_payload

    return engine.recommend(request=request_value, candidate=candidate), candidate_payload


def _request_from_body(body, candidates=()):
    request_payload = _as_mapping(body.get('request'))
    metadata = dict(_as_mapping(request_payload.get('metadata')))
    for key in ('request_id', 'source', 'client'):
        if key in request_payload:
            metadata[key] = request_payload.get(key)

    return RecommendationRequest(
        category=_category_from_value(request_payload.get('category')),
        team_id=request_payload.get('team_id'),
        team_name=request_payload.get('team_name'),
        candidates=tuple(candidates),
        metadata=metadata,
    )


def _candidate_from_payload(candidate_payload):
    if not isinstance(candidate_payload, Mapping):
        return candidate_payload

    return RecommendationCandidate(
        pitcher_id=candidate_payload.get('pitcher_id'),
        pitcher_name=candidate_payload.get('pitcher_name'),
        team_id=candidate_payload.get('team_id'),
        team_name=candidate_payload.get('team_name'),
        availability=_as_mapping(candidate_payload.get('availability')),
        metadata=_as_mapping(candidate_payload.get('metadata')),
    )


def _category_from_value(value):
    if value is None:
        return None

    normalized = _normalize_category(value)
    for category in RecommendationCategory:
        if normalized in (
            _normalize_category(category.name),
            _normalize_category(category.value),
        ):
            return category
    return None


def _response_payload(result, candidate_payload=None):
    result_payload = result.to_dict()
    metadata = dict(result_payload.get('metadata') or {})
    return {
        'data': _data_payload(result_payload, metadata, candidate_payload),
        'meta': _meta_payload(metadata),
    }


def _data_payload(result_payload, metadata, candidate_payload):
    return {
        'outcome': result_payload.get('outcome'),
        'outcome_code': result_payload.get('outcome_code'),
        'category': result_payload.get('category'),
        'category_code': result_payload.get('category_code'),
        'candidate': _candidate_payload(result_payload, metadata, candidate_payload),
        'confidence': result_payload.get('confidence') or {},
        'freshness': _freshness_payload(result_payload, candidate_payload),
        'availability': _availability_payload(metadata, candidate_payload),
        'assigned_categories': _assigned_categories(metadata),
        'blocked_categories': list(metadata.get('blocked_categories') or []),
        'explanations': list(result_payload.get('explanations') or []),
        'limitations': list(result_payload.get('limitations') or []),
        'alternatives': list(result_payload.get('alternatives') or []),
        'refusal': result_payload.get('refusal'),
    }


def _meta_payload(metadata):
    meta = dict(metadata)
    meta['policy'] = meta.get('policy') or 'recommendation_engine_v1'
    meta['policy_version'] = (
        meta.get('policy_version')
        or meta.get('policy')
        or 'recommendation_engine_v1'
    )
    meta['engine_version'] = meta.get('engine_version') or API_ENGINE_VERSION
    meta['policy_document'] = meta.get('policy_document') or POLICY_DOCUMENT
    meta['contract_document'] = CONTRACT_DOCUMENT
    meta['implementation_plan'] = (
        meta.get('implementation_plan') or IMPLEMENTATION_PLAN
    )
    meta['response_mode'] = (
        meta.get('response_mode') or 'candidate_category_eligibility'
    )
    meta['candidate_pipeline_enabled'] = bool(
        meta.get('candidate_pipeline_enabled', False)
    )
    meta['ranking_applied'] = False
    meta['selection_made'] = False
    meta['selected_pitcher_id'] = None
    return meta


def _candidate_payload(result_payload, metadata, candidate_payload):
    candidate = _as_mapping(candidate_payload)
    gate_result = _gate_result(metadata)
    return {
        'pitcher_id': (
            result_payload.get('pitcher_id')
            or gate_result.get('pitcher_id')
            or candidate.get('pitcher_id')
        ),
        'pitcher_name': (
            result_payload.get('pitcher_name')
            or gate_result.get('pitcher_name')
            or candidate.get('pitcher_name')
        ),
        'team_id': candidate.get('team_id'),
        'team_name': candidate.get('team_name'),
    }


def _freshness_payload(result_payload, candidate_payload):
    freshness = dict(result_payload.get('freshness') or {})
    candidate = _as_mapping(candidate_payload)
    metadata = _as_mapping(candidate.get('metadata'))
    availability = _as_mapping(candidate.get('availability'))

    for key in ('data_through', 'last_successful_sync', 'latest_sync_status'):
        freshness[key] = (
            freshness.get(key)
            or metadata.get(key)
            or availability.get(key)
        )
    return freshness


def _availability_payload(metadata, candidate_payload):
    candidate = _as_mapping(candidate_payload)
    availability = _as_mapping(candidate.get('availability'))
    return {
        'availability_status': (
            availability.get('availability_status')
            or availability.get('status')
            or metadata.get('availability_state')
        ),
        'confidence': availability.get('confidence'),
        'data_state': (
            availability.get('data_state')
            or availability.get('freshness_state')
        ),
        'reasons': list(availability.get('reasons') or []),
        'limitations': list(availability.get('limitations') or []),
    }


def _assigned_categories(metadata):
    assignment = _as_mapping(metadata.get('category_assignment'))
    categories = (
        assignment.get('assigned_categories')
        or metadata.get('assigned_categories')
        or []
    )
    codes = (
        assignment.get('assigned_category_codes')
        or metadata.get('assigned_category_codes')
        or []
    )
    return [
        {
            'category': category,
            'category_code': codes[index] if index < len(codes) else None,
        }
        for index, category in enumerate(categories)
    ]


def _gate_result(metadata):
    if isinstance(metadata.get('gate_result'), Mapping):
        return metadata['gate_result']

    assignment = _as_mapping(metadata.get('category_assignment'))
    return _as_mapping(assignment.get('gate_result'))


def _as_mapping(value):
    return value if isinstance(value, Mapping) else {}


def _normalize_category(value):
    return str(value).strip().lower().replace('-', '_').replace(' ', '_')
