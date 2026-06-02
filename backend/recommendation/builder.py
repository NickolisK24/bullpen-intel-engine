"""Response builder for Recommendation Engine V1 candidate evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from recommendation.categories import (
    RecommendationCategoryAssignment,
    assign_recommendation_categories,
)
from recommendation.contracts import (
    BASE_RECOMMENDATION_LIMITATIONS,
    DEFAULT_REFUSAL_MESSAGE,
    RecommendationCandidate,
    RecommendationConfidenceContext,
    RecommendationExplanation,
    RecommendationFreshnessContext,
    RecommendationLimitation,
)
from recommendation.enums import (
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationFreshnessState,
    RefusalReason,
)
from recommendation.gates import RecommendationGateResult, evaluate_candidate_gates
from recommendation.result import RecommendationResult


ENGINE_VERSION = 'recommendation_engine_v1_builder'
POLICY_VERSION = 'recommendation_engine_v1'

POSITIVE_CATEGORIES = {
    RecommendationCategory.BEST_AVAILABLE_ARM,
    RecommendationCategory.FRESHEST_HIGH_LEVERAGE_ARM,
    RecommendationCategory.LOWEST_CURRENT_WORKLOAD_RISK,
}

_UNSET = object()


def build_recommendation_response(
    candidate: RecommendationCandidate | None = None,
    gate_result=_UNSET,
    category_assignment=_UNSET,
    context: Mapping | None = None,
):
    context = _as_mapping(context)

    if gate_result is _UNSET:
        if candidate is None:
            return _refuse(
                reason=RefusalReason.INSUFFICIENT_DATA,
                explanation_code='missing_candidate',
                explanation_message='No candidate was provided for response building.',
                metadata=_base_metadata(context=context),
            )
        gate_result = evaluate_candidate_gates(candidate)

    if not isinstance(gate_result, RecommendationGateResult):
        return _refuse(
            reason=RefusalReason.INSUFFICIENT_DATA,
            explanation_code='missing_or_invalid_gate_result',
            explanation_message='A valid eligibility gate result is required before response building.',
            metadata=_base_metadata(context=context),
        )

    if category_assignment is _UNSET:
        category_assignment = assign_recommendation_categories(
            gate_result,
            candidate=candidate,
            context=context,
        )

    if not isinstance(category_assignment, RecommendationCategoryAssignment):
        return _refuse(
            reason=RefusalReason.INSUFFICIENT_DATA,
            explanation_code='missing_or_invalid_category_assignment',
            explanation_message='A valid category assignment result is required before response building.',
            metadata=_base_metadata(context=context, gate_result=gate_result),
            confidence=_confidence_context(gate_result),
            freshness=_freshness_context(gate_result),
        )

    metadata = _metadata(
        gate_result=gate_result,
        category_assignment=category_assignment,
        context=context,
    )
    explanations = _combined_explanations(gate_result, category_assignment)
    limitations = _combined_limitations(gate_result, category_assignment)

    if _must_refuse(gate_result, category_assignment):
        return RecommendationResult.refuse(
            reason=_refusal_reason(gate_result, category_assignment),
            message=DEFAULT_REFUSAL_MESSAGE,
            confidence=_confidence_context(gate_result),
            freshness=_freshness_context(gate_result),
            explanations=explanations,
            limitations=limitations,
            metadata=metadata,
        )

    return RecommendationResult.recommendation(
        category=_response_category(category_assignment),
        pitcher_id=category_assignment.pitcher_id,
        pitcher_name=category_assignment.pitcher_name,
        confidence=_confidence_context(gate_result),
        freshness=_freshness_context(gate_result),
        explanations=explanations,
        limitations=limitations,
        alternatives=(),
        metadata=metadata,
    )


def _response_category(category_assignment):
    assigned = tuple(category_assignment.assigned_categories)
    if (
        RecommendationCategory.AVOID_TONIGHT in assigned
        and not any(category in POSITIVE_CATEGORIES for category in assigned)
    ):
        return RecommendationCategory.AVOID_TONIGHT
    return assigned[0]


def _must_refuse(gate_result, category_assignment):
    return (
        gate_result.excluded
        or not gate_result.eligible
        or not category_assignment.assigned_categories
        or category_assignment.selection_made
        or category_assignment.ranking_applied
        or category_assignment.pitcher_id is None
        or not category_assignment.pitcher_name
        or gate_result.confidence_state in (
            RecommendationConfidence.LOW,
            RecommendationConfidence.UNKNOWN,
        )
        or gate_result.freshness_state in (
            RecommendationFreshnessState.STALE,
            RecommendationFreshnessState.MISSING,
            RecommendationFreshnessState.HISTORICAL,
            RecommendationFreshnessState.INCOMPLETE,
            RecommendationFreshnessState.UNKNOWN,
        )
    )


def _refusal_reason(gate_result, category_assignment):
    exclusions = set(gate_result.exclusion_reasons)
    if 'low_confidence' in exclusions or 'unknown_confidence' in exclusions:
        return RefusalReason.LOW_CONFIDENCE
    if 'stale_freshness' in exclusions:
        return RefusalReason.STALE_DATA
    if any(reason.endswith('_freshness') for reason in exclusions):
        return RefusalReason.UNKNOWN_FRESHNESS
    if not category_assignment.assigned_categories:
        return RefusalReason.NO_ELIGIBLE_PITCHERS
    if gate_result.excluded or not gate_result.eligible:
        return RefusalReason.INSUFFICIENT_DATA
    return RefusalReason.INSUFFICIENT_DATA


def _confidence_context(gate_result):
    return RecommendationConfidenceContext(
        level=gate_result.confidence_state,
        reasons=tuple(gate_result.exclusion_reasons + gate_result.caution_reasons),
    )


def _freshness_context(gate_result):
    return RecommendationFreshnessContext(
        state=gate_result.freshness_state,
        limitations=tuple(
            reason for reason in gate_result.exclusion_reasons
            if 'freshness' in reason
        ),
    )


def _combined_explanations(gate_result, category_assignment):
    explanations = list(gate_result.explanations)
    explanations.extend(category_assignment.assignment_explanations)
    explanations.append(
        RecommendationExplanation(
            code='builder_category_eligibility_only',
            message='Response builder composed category eligibility only; no ranking or final selection was applied.',
        )
    )
    return tuple(explanations)


def _combined_limitations(gate_result, category_assignment):
    by_code = {}
    for limitation in BASE_RECOMMENDATION_LIMITATIONS:
        by_code[limitation.code] = limitation
    for limitation in gate_result.limitations:
        by_code[limitation.code] = limitation
    for limitation in category_assignment.limitations:
        by_code[limitation.code] = limitation
    by_code['builder_not_final_recommender'] = RecommendationLimitation(
        code='builder_not_final_recommender',
        message='Builder output is candidate-level composition only; it does not rank, compare, or select pitchers.',
    )
    return tuple(by_code.values())


def _metadata(gate_result, category_assignment, context):
    assigned_codes = [category.name for category in category_assignment.assigned_categories]
    positive_codes = [
        category.name
        for category in category_assignment.assigned_categories
        if category in POSITIVE_CATEGORIES
    ]
    return {
        **_base_metadata(context=context, gate_result=gate_result),
        'category_assignment': category_assignment.to_dict(),
        'assigned_categories': [
            category.value for category in category_assignment.assigned_categories
        ],
        'assigned_category_codes': assigned_codes,
        'positive_category_codes': positive_codes,
        'blocked_categories': [
            blocked.to_dict() for blocked in category_assignment.blocked_categories
        ],
        'availability_state': category_assignment.availability_state,
        'ranking_applied': False,
        'selection_made': False,
        'selected_pitcher_id': None,
        'response_mode': 'candidate_category_eligibility',
    }


def _base_metadata(context=None, gate_result=None):
    metadata = {
        'policy_version': POLICY_VERSION,
        'engine_version': ENGINE_VERSION,
        'ranking_applied': False,
        'selection_made': False,
        'selected_pitcher_id': None,
        'response_mode': 'candidate_category_eligibility',
    }
    if context:
        metadata['context'] = dict(context)
    if gate_result is not None:
        metadata['gate_result'] = gate_result.to_dict()
    return metadata


def _refuse(
    reason,
    explanation_code,
    explanation_message,
    metadata,
    confidence=None,
    freshness=None,
):
    return RecommendationResult.refuse(
        reason=reason,
        message=DEFAULT_REFUSAL_MESSAGE,
        confidence=confidence,
        freshness=freshness,
        explanations=(
            RecommendationExplanation(
                code=explanation_code,
                message=explanation_message,
            ),
        ),
        limitations=(
            *BASE_RECOMMENDATION_LIMITATIONS,
            RecommendationLimitation(
                code='builder_fail_closed',
                message='Builder failed closed and did not emit category eligibility.',
            ),
        ),
        metadata=metadata,
    )


def _as_mapping(value):
    return value if isinstance(value, Mapping) else {}
