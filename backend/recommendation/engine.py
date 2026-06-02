"""Fail-closed Recommendation Engine V1 foundation."""

from recommendation.contracts import RecommendationExplanation, RecommendationRequest
from recommendation.enums import RefusalReason
from recommendation.result import RecommendationResult


class RecommendationEngine:
    """
    Foundation engine for Recommendation Engine V1.

    This class intentionally does not select, rank, or score pitchers. Until
    recommendation policy gates and category assignment are implemented, every
    call returns a valid refusal response.
    """

    policy_name = 'recommendation_engine_v1'
    policy_document = 'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'
    implementation_plan = 'docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md'
    implementation_phase = 'foundation'

    def recommend(self, request: RecommendationRequest | None = None):
        metadata = {
            'policy': self.policy_name,
            'policy_document': self.policy_document,
            'implementation_plan': self.implementation_plan,
            'implementation_phase': self.implementation_phase,
            'decision_logic_enabled': False,
        }
        if request is not None:
            metadata['request'] = request.to_dict()

        return RecommendationResult.refuse(
            reason=RefusalReason.INSUFFICIENT_DATA,
            explanations=(
                RecommendationExplanation(
                    code='foundation_fail_closed',
                    message=(
                        'Recommendation Engine V1 foundation is available, '
                        'but recommendation decision logic is not implemented.'
                    ),
                ),
            ),
            metadata=metadata,
        )
