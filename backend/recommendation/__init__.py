"""
Recommendation Engine foundation package.

This package defines V1 contracts plus V2 backend domain foundations. It does
not select, rank, or score recommendation candidates.
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
from recommendation.builder import build_recommendation_response
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
from recommendation.v2 import (
    BASE_V2_LIMITATIONS,
    NO_RANKING_APPLIED,
    NO_SELECTION_MADE,
    V2_PHASE,
    V2_POLICY_NAME,
    BullpenState,
    CandidateGroup,
    RecommendationContext,
    TeamBullpenContext,
    V2Explanation,
    V2FreshnessMetadata,
    V2Limitation,
    V2Refusal,
    require_v2_governance_safe,
    v2_governance_errors,
)
from recommendation.v2_assembly import (
    INVENTORY_VISIBILITY_SECTIONS,
    NEUTRAL_INTELLIGENCE_DIMENSIONS,
    TEAM_BULLPEN_CONTEXT_SECTIONS,
    V2_CONTEXT_ASSEMBLY_PHASE,
    V2_CONTEXT_ASSEMBLY_SOURCE,
    V2_INVENTORY_VISIBILITY_PHASE,
    V2_NEUTRAL_INTELLIGENCE_PHASE,
    V2_TEAM_BULLPEN_CONTEXT_PHASE,
    V2ContextAssembly,
    assemble_v2_context,
)

__all__ = [
    'BASE_RECOMMENDATION_LIMITATIONS',
    'BASE_V2_LIMITATIONS',
    'DEFAULT_REFUSAL_MESSAGE',
    'NO_RANKING_APPLIED',
    'NO_SELECTION_MADE',
    'RecommendationCandidate',
    'RecommendationCandidatePool',
    'RecommendationCategory',
    'RecommendationCategoryAssignment',
    'RecommendationCategoryBlock',
    'RecommendationConfidence',
    'RecommendationConfidenceContext',
    'RecommendationContext',
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
    'V2_PHASE',
    'V2_POLICY_NAME',
    'V2_CONTEXT_ASSEMBLY_PHASE',
    'V2_CONTEXT_ASSEMBLY_SOURCE',
    'V2_NEUTRAL_INTELLIGENCE_PHASE',
    'V2_INVENTORY_VISIBILITY_PHASE',
    'V2_TEAM_BULLPEN_CONTEXT_PHASE',
    'NEUTRAL_INTELLIGENCE_DIMENSIONS',
    'INVENTORY_VISIBILITY_SECTIONS',
    'TEAM_BULLPEN_CONTEXT_SECTIONS',
    'BullpenState',
    'CandidateGroup',
    'TeamBullpenContext',
    'V2ContextAssembly',
    'V2Explanation',
    'V2FreshnessMetadata',
    'V2Limitation',
    'V2Refusal',
    'assemble_v2_context',
    'build_recommendation_response',
    'assign_recommendation_categories',
    'evaluate_candidate_gates',
    'evaluate_candidate_pool',
    'is_valid_recommendation_result',
    'recommendation_result_errors',
    'require_v2_governance_safe',
    'v2_governance_errors',
]
