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
from recommendation.engine import RecommendationEngine
from recommendation.enums import (
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationFreshnessState,
    RecommendationOutcome,
    RefusalReason,
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
    'RecommendationCategory',
    'RecommendationConfidence',
    'RecommendationConfidenceContext',
    'RecommendationEngine',
    'RecommendationExplanation',
    'RecommendationFreshnessContext',
    'RecommendationFreshnessState',
    'RecommendationLimitation',
    'RecommendationOutcome',
    'RecommendationRefusal',
    'RecommendationRequest',
    'RecommendationResult',
    'RefusalReason',
    'is_valid_recommendation_result',
    'recommendation_result_errors',
]
