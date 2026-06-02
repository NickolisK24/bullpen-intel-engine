"""
Recommendation Engine V1 foundation package.

This package defines contracts and fail-closed defaults only. It does not
select, rank, or score recommendation candidates.
"""

from recommendation.contracts import (
    DEFAULT_REFUSAL_MESSAGE,
    BASE_RECOMMENDATION_LIMITATIONS,
    RecommendationCandidate,
    RecommendationConfidenceContext,
    RecommendationExplanation,
    RecommendationFreshnessContext,
    RecommendationLimitation,
    RecommendationRefusal,
    RecommendationRequest,
)
from recommendation.categories import (
    RecommendationCategoryAssignment,
    RecommendationCategoryBlock,
    assign_recommendation_categories,
)
from recommendation.engine import RecommendationEngine
from recommendation.enums import (
    RecommendationCandidatePool,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationFreshnessState,
    RecommendationOutcome,
    RefusalReason,
)
from recommendation.gates import (
    RecommendationGateResult,
    evaluate_candidate_gates,
    evaluate_candidate_pool,
)
from recommendation.result import RecommendationResult
from recommendation.validators import (
    is_valid_recommendation_result,
    recommendation_result_errors,
)

__all__ = [
    'BASE_RECOMMENDATION_LIMITATIONS',
    'DEFAULT_REFUSAL_MESSAGE',
    'RecommendationCandidate',
    'RecommendationCandidatePool',
    'RecommendationCategory',
    'RecommendationCategoryAssignment',
    'RecommendationCategoryBlock',
    'RecommendationConfidence',
    'RecommendationConfidenceContext',
    'RecommendationEngine',
    'RecommendationExplanation',
    'RecommendationFreshnessContext',
    'RecommendationFreshnessState',
    'RecommendationGateResult',
    'RecommendationLimitation',
    'RecommendationOutcome',
    'RecommendationRefusal',
    'RecommendationRequest',
    'RecommendationResult',
    'RefusalReason',
    'assign_recommendation_categories',
    'evaluate_candidate_gates',
    'evaluate_candidate_pool',
    'is_valid_recommendation_result',
    'recommendation_result_errors',
]
