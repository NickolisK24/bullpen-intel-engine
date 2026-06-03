"""Recommendation Engine API routes."""

from collections.abc import Mapping
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from recommendation import (
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationEngine,
    RecommendationRequest,
    assemble_v2_context,
    require_v2_governance_safe,
    require_v2_trust_metadata,
    v2_governance_errors,
)
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)


recommendations_bp = Blueprint('recommendations', __name__)

CONTRACT_DOCUMENT = 'docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md'
POLICY_DOCUMENT = 'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'
IMPLEMENTATION_PLAN = 'docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md'
API_ENGINE_VERSION = 'recommendation_engine_v1_candidate_api'
V2_CONTRACT_DOCUMENT = 'docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md'
V2_API_ENGINE_VERSION = 'recommendation_engine_v2_bullpen_state_api'
V2_BULLPEN_STATE_ENDPOINT = '/api/recommendations/v2/bullpen-state'
V2_DEFAULT_LIMIT = 750
V2_MAX_LIMIT = 750
V2_AVAILABILITY_INVENTORY_ORDER = (
    'Available',
    'Monitor',
    'Limited',
    'Avoid',
    'Unavailable',
    'Unknown',
)
V2_UNSAFE_REQUEST_FIELDS = frozenset(
    {
        'rank',
        'ranking',
        'winner',
        'priority',
        'priority_score',
        'score',
        'score_ordering',
        'selected_pitcher',
        'selected_pitcher_id',
        'selected_candidate',
        'selected_candidate_id',
        'recommended_pitcher',
        'recommended_option',
        'preferred_pitcher',
        'preferred_option',
        'use_this_pitcher',
        'best_candidate',
        'best_pitcher',
        'top_candidate',
        'pitcher_choice',
        'prediction',
        'predicted_performance',
        'performance_prediction',
        'performance_forecast',
        'predicted_injury',
        'injury_prediction',
        'injury_risk_prediction',
        'predicted_saves',
        'save_prediction',
        'game_prediction',
        'game_outcome_prediction',
        'outcome_prediction',
        'projected_outcome',
        'projected_performance',
    }
)


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


@recommendations_bp.route('/v2/bullpen-state', methods=['GET'])
def get_v2_bullpen_state():
    rows = ()
    team_id = request.args.get('team_id', type=int)
    limit = _v2_limit_from_request()
    unsafe_request_errors = _v2_unsafe_request_errors(request.args)

    if unsafe_request_errors:
        assembly = assemble_v2_context(
            (_v2_unsafe_request_candidate_payload(request.args),),
            team_id=team_id,
            team_name=None,
            generated_at=_v2_generated_at(rows),
        )
    else:
        rows = tuple(latest_fatigue_rows(team_id=team_id, limit=limit))
        records = classify_latest_fatigue_rows(
            rows,
            mode=CURRENT_AVAILABILITY_MODE,
        )
        assembly = assemble_v2_context(
            tuple(_v2_candidate_from_record(record) for record in records),
            team_id=team_id,
            team_name=_v2_team_name_from_rows(rows),
            generated_at=_v2_generated_at(rows),
            metadata={
                'api_endpoint': V2_BULLPEN_STATE_ENDPOINT,
                'api_contract': V2_CONTRACT_DOCUMENT,
                'engine_version': V2_API_ENGINE_VERSION,
            },
        )

    payload = _v2_api_response_payload(_v2_public_assembly_payload(assembly))
    return jsonify(payload)


def _v2_limit_from_request():
    limit = request.args.get('limit', V2_DEFAULT_LIMIT, type=int)
    if not isinstance(limit, int) or limit <= 0:
        return V2_DEFAULT_LIMIT
    return min(limit, V2_MAX_LIMIT)


def _v2_unsafe_request_errors(args):
    unsafe_payload = {
        key: args.get(key)
        for key in args.keys()
        if str(key).lower() in V2_UNSAFE_REQUEST_FIELDS
    }
    return v2_governance_errors(unsafe_payload) if unsafe_payload else []


def _v2_unsafe_request_candidate_payload(args):
    return {
        key: args.get(key)
        for key in args.keys()
        if str(key).lower() in V2_UNSAFE_REQUEST_FIELDS
    }


def _v2_candidate_from_record(record):
    availability = dict(record.get('availability') or {})
    inputs = dict(availability.get('inputs') or {})
    latest_game_date = record.get('latest_game_date')
    score = record.get('score')
    availability['data_through'] = (
        availability.get('data_through')
        or _iso_or_none(latest_game_date)
        or inputs.get('latest_game_date')
    )
    availability['latest_sync_status'] = availability.get('latest_sync_status')
    availability['last_successful_sync'] = availability.get('last_successful_sync')

    pitcher = record.get('pitcher')
    return RecommendationCandidate(
        pitcher_id=record.get('pitcher_id'),
        pitcher_name=record.get('pitcher_name'),
        team_id=getattr(pitcher, 'team_id', None),
        team_name=getattr(pitcher, 'team_name', None),
        availability=availability,
        metadata={
            'data_through': availability.get('data_through'),
            'last_successful_sync': availability.get('last_successful_sync'),
            'latest_sync_status': availability.get('latest_sync_status'),
            'high_leverage_evidence': _v2_high_leverage_evidence(score),
        },
    )


def _v2_high_leverage_evidence(score):
    leverage = getattr(score, 'avg_leverage_last_7', None)
    return leverage is not None and float(leverage or 0) >= 1.5


def _v2_team_name_from_rows(rows):
    names = {
        getattr(pitcher, 'team_name', None)
        for _score, pitcher in rows
        if getattr(pitcher, 'team_name', None)
    }
    return next(iter(names)) if len(names) == 1 else None


def _v2_generated_at(rows):
    timestamps = [
        score.calculated_at
        for score, _pitcher in rows
        if getattr(score, 'calculated_at', None) is not None
    ]
    if timestamps:
        return max(timestamps).isoformat()
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _v2_api_response_payload(assembly_payload):
    context = dict(assembly_payload.get('recommendation_context') or {})
    metadata = dict(assembly_payload.get('metadata') or {})
    refusal_fail_closed = dict(metadata.get('refusal_fail_closed') or {})
    critical_failure = bool(refusal_fail_closed.get('critical_failure'))
    freshness = _v2_api_freshness(context.get('freshness'))
    limitations = [
        _v2_api_limitation(item)
        for item in context.get('limitations') or []
    ]
    explanations = [
        _v2_api_explanation(item)
        for item in context.get('explanations') or []
    ]
    refusal_reasons = [
        dict(item)
        for item in context.get('refusal_reasons') or []
    ]
    trust_metadata = _v2_api_trust_metadata(context, refusal_fail_closed)

    payload = {
        'scope': 'bullpen_state',
        'ranking_applied': False,
        'selection_made': False,
        'confidence': context.get('confidence'),
        'data_state': context.get('data_state'),
        'generated_at': context.get('generated_at'),
        'freshness': freshness,
        'limitations': limitations,
        'explanations': explanations,
        'refusal_reasons': refusal_reasons,
        'fail_closed': _v2_api_fail_closed(
            refusal_fail_closed,
            trust_metadata=trust_metadata,
        ),
        'trust_metadata': trust_metadata,
        'bullpen_state': (
            None
            if critical_failure
            else _v2_api_bullpen_state(
                assembly_payload,
                freshness=freshness,
                limitations=limitations,
                explanations=explanations,
                refusal_reasons=refusal_reasons,
                trust_metadata=trust_metadata,
            )
        ),
    }
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


def _v2_public_assembly_payload(assembly):
    """Build only the internal fields needed by the public V2 API contract."""
    return {
        'metadata': dict(assembly.metadata),
        'recommendation_context': assembly.recommendation_context.to_dict(),
        'bullpen_state': {
            'bullpen_status': assembly.bullpen_state.bullpen_status,
            'inventory': dict(assembly.bullpen_state.inventory),
            'stress': dict(assembly.bullpen_state.stress),
        },
        'team_context': {
            'leverage_inventory': dict(assembly.team_context.leverage_inventory),
            'stress_indicators': dict(assembly.team_context.stress_indicators),
        },
        'candidate_groups': [
            _v2_public_candidate_group_payload(group)
            for group in assembly.candidate_groups
        ],
    }


def _v2_public_candidate_group_payload(group):
    return {
        'group_id': group.group_id,
        'label': group.label,
        'criteria': list(group.criteria),
        'candidate_count': len(group.candidates),
        'neutral_sequence_basis': group.neutral_sequence_basis,
        'candidates': [dict(candidate) for candidate in group.candidates],
        'confidence': group.context.confidence.value,
    }


def _v2_api_bullpen_state(
    assembly_payload,
    *,
    freshness,
    limitations,
    explanations,
    refusal_reasons,
    trust_metadata,
):
    bullpen_state = dict(assembly_payload.get('bullpen_state') or {})
    inventory = dict(bullpen_state.get('inventory') or {})
    stress = dict(bullpen_state.get('stress') or {})
    return {
        'status': bullpen_state.get('bullpen_status'),
        'stress_level': stress.get('stress_level'),
        'readiness_summary': _v2_readiness_summary(inventory),
        'inventory_summary': _v2_inventory_summary(
            assembly_payload,
            freshness=freshness,
            limitations=limitations,
        ),
        'candidate_groups': _v2_candidate_groups(
            assembly_payload,
            freshness=freshness,
            limitations=limitations,
            explanations=explanations,
            refusal_reasons=refusal_reasons,
        ),
        'team_context': _v2_team_context(
            assembly_payload,
            explanations=explanations,
            limitations=limitations,
        ),
        'trust': dict(trust_metadata),
    }


def _v2_api_freshness(freshness):
    freshness = dict(freshness or {})
    return {
        'sync_timestamp': freshness.get('last_successful_sync'),
        'data_through': freshness.get('data_through'),
        'freshness_state': freshness.get('state'),
        'state_code': freshness.get('state_code'),
        'stale_warning': freshness.get('stale_warning'),
        'missing_data_warning': freshness.get('missing_data_warning'),
        'limitations': list(freshness.get('limitations') or []),
    }


def _v2_api_limitation(limitation):
    limitation = dict(limitation or {})
    return {
        'limitation_id': limitation.get('limitation_id'),
        'message': limitation.get('message'),
        'severity': limitation.get('severity'),
        'applies_to': limitation.get('applies_to'),
    }


def _v2_api_explanation(explanation):
    explanation = dict(explanation or {})
    details = dict(explanation.get('details') or {})
    return {
        'explanation_id': explanation.get('code'),
        'level': _v2_explanation_level(explanation.get('applies_to')),
        'message': explanation.get('message'),
        'evidence': _v2_explanation_evidence(details),
        'applies_to': explanation.get('applies_to'),
    }


def _v2_explanation_level(applies_to):
    value = str(applies_to or 'bullpen_state')
    if 'group' in value:
        return 'group'
    if 'team' in value:
        return 'team'
    if 'refusal' in value:
        return 'refusal'
    return 'bullpen'


def _v2_explanation_evidence(details):
    evidence = []
    for key in sorted(details):
        evidence.append(f'{key}: {details[key]}')
    return evidence


def _v2_api_fail_closed(refusal_fail_closed, *, trust_metadata):
    return {
        'state': refusal_fail_closed.get('state'),
        'failed_closed': bool(refusal_fail_closed.get('failed_closed')),
        'critical_failure': bool(refusal_fail_closed.get('critical_failure')),
        'safe_partial_output_allowed': bool(
            refusal_fail_closed.get('safe_partial_output_allowed')
        ),
        'reason_codes': list(refusal_fail_closed.get('reason_codes') or []),
        'source_evidence_state': refusal_fail_closed.get('source_evidence_state'),
        'governance_state': refusal_fail_closed.get('governance_state'),
        'trust_metadata': dict(trust_metadata),
        'ranking_applied': False,
        'selection_made': False,
    }


def _v2_api_trust_metadata(context, refusal_fail_closed):
    trust = dict(context.get('trust_metadata') or {})
    trust['fail_closed_state'] = refusal_fail_closed.get('state')
    trust['ranking_applied'] = False
    trust['selection_made'] = False
    return trust


def _v2_readiness_summary(inventory):
    total = int(inventory.get('total_pitchers') or 0)
    counts = dict(inventory.get('availability_status_counts') or {})
    return (
        f"Inventory includes {total} bullpen records: "
        f"{counts.get('Available', 0)} available, "
        f"{counts.get('Monitor', 0)} monitor, "
        f"{counts.get('Limited', 0)} limited, "
        f"{counts.get('Avoid', 0)} avoid, and "
        f"{counts.get('Unavailable', 0)} unavailable."
    )


def _v2_inventory_summary(assembly_payload, *, freshness, limitations):
    metadata = dict(assembly_payload.get('metadata') or {})
    inventory_visibility = dict(metadata.get('inventory_visibility') or {})
    availability_inventory = dict(
        inventory_visibility.get('availability_inventory') or {}
    )
    members_by_status = dict(availability_inventory.get('members_by_status') or {})
    status_counts = dict(availability_inventory.get('status_counts') or {})
    return [
        {
            'inventory_type': f'{_v2_slug(status)}_inventory',
            'label': f'{status} Inventory',
            'count': int(status_counts.get(status, 0)),
            'members': [
                _v2_member_payload(member)
                for member in members_by_status.get(status, [])
            ],
            'evidence': [
                f'availability_status: {status}',
                'member order preserves neutral source order',
            ],
            'limitations': limitations,
            'freshness': freshness,
            'confidence': assembly_payload['recommendation_context']['confidence'],
        }
        for status in V2_AVAILABILITY_INVENTORY_ORDER
    ]


def _v2_candidate_groups(
    assembly_payload,
    *,
    freshness,
    limitations,
    explanations,
    refusal_reasons,
):
    return [
        {
            'group_id': group.get('group_id'),
            'label': group.get('label'),
            'description': _v2_group_description(group),
            'eligibility_basis': list(group.get('criteria') or []),
            'candidate_count': int(group.get('candidate_count') or 0),
            'ordering': _v2_group_ordering(group),
            'candidates': [
                _v2_member_payload(candidate)
                for candidate in group.get('candidates') or []
            ],
            'explanations': explanations,
            'limitations': limitations,
            'confidence': group.get('confidence'),
            'freshness': freshness,
            'refusal_reasons': refusal_reasons,
        }
        for group in assembly_payload.get('candidate_groups') or []
    ]


def _v2_group_description(group):
    criteria = ', '.join(group.get('criteria') or [])
    return f'Pitchers matching documented non-ranking criteria: {criteria}.'


def _v2_group_ordering(group):
    basis = group.get('neutral_sequence_basis') or 'input_sequence_preserved'
    return f'{basis}_non_ranking'


def _v2_team_context(assembly_payload, *, explanations, limitations):
    team_context = dict(assembly_payload.get('team_context') or {})
    summary = dict(
        dict(assembly_payload.get('metadata') or {}).get(
            'team_bullpen_context_summary'
        )
        or {}
    )
    return {
        'workload_distribution': dict(summary.get('workload_distribution') or {}),
        'availability_distribution': dict(
            summary.get('availability_distribution') or {}
        ),
        'leverage_inventory': dict(team_context.get('leverage_inventory') or {}),
        'readiness_indicators': dict(summary.get('readiness_context') or {}),
        'stress_indicators': dict(team_context.get('stress_indicators') or {}),
        'explanations': explanations,
        'limitations': limitations,
    }


def _v2_member_payload(member):
    return {
        'pitcher_id': member.get('pitcher_id'),
        'display_name': member.get('pitcher_name'),
    }


def _v2_slug(value):
    return str(value or 'unknown').strip().lower().replace(' ', '_')


def _iso_or_none(value):
    return value.isoformat() if value else None


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
