"""Recommendation Engine V1 candidate-level orchestration."""

from dataclasses import replace

from recommendation.builder import build_recommendation_response
from recommendation.contracts import (
    BASE_RECOMMENDATION_LIMITATIONS,
    RecommendationCandidate,
    RecommendationExplanation,
    RecommendationLimitation,
    RecommendationRequest,
)
from recommendation.enums import RefusalReason
from recommendation.result import RecommendationResult


class RecommendationEngine:
    """
    Foundation engine for Recommendation Engine V1.

    This class evaluates a single candidate through the approved gate,
    category-assignment, and builder pipeline. It intentionally does not select,
    rank, score, or compare pitchers.
    """

    policy_name = 'recommendation_engine_v1'
    policy_document = 'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'
    implementation_plan = 'docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md'
    implementation_phase = 'candidate_engine_integration'

    def recommend(
        self,
        request: RecommendationRequest | None = None,
        candidate: RecommendationCandidate | None = None,
    ):
        metadata = self._base_metadata(request)
        candidate_value, refusal = self._resolve_candidate(request, candidate)

        if refusal is not None:
            return self._refuse(
                reason=refusal['reason'],
                explanation_code=refusal['code'],
                explanation_message=refusal['message'],
                metadata={
                    **metadata,
                    'candidate_pipeline_enabled': False,
                    'refusal_boundary': refusal['code'],
                },
            )

        result = build_recommendation_response(
            candidate=candidate_value,
            context=self._context_from_request(request),
        )
        return replace(
            result,
            metadata={
                **result.metadata,
                **metadata,
                'candidate_pipeline_enabled': True,
                'engine_entrypoint': 'RecommendationEngine.recommend',
            },
        )

    def _base_metadata(self, request):
        metadata = {
            'policy': self.policy_name,
            'policy_document': self.policy_document,
            'implementation_plan': self.implementation_plan,
            'implementation_phase': self.implementation_phase,
            'decision_logic_enabled': False,
            'ranking_applied': False,
            'selection_made': False,
            'selected_pitcher_id': None,
        }
        if isinstance(request, RecommendationRequest):
            metadata['request'] = request.to_dict()
        return metadata

    def _resolve_candidate(self, request, candidate):
        if candidate is not None:
            if not isinstance(candidate, RecommendationCandidate):
                return None, {
                    'reason': RefusalReason.INSUFFICIENT_DATA,
                    'code': 'invalid_candidate',
                    'message': 'A valid recommendation candidate is required.',
                }
            return candidate, None

        if request is None:
            return None, {
                'reason': RefusalReason.INSUFFICIENT_DATA,
                'code': 'no_candidate_provided',
                'message': 'No candidate was provided for recommendation evaluation.',
            }

        if not isinstance(request, RecommendationRequest):
            return None, {
                'reason': RefusalReason.INSUFFICIENT_DATA,
                'code': 'invalid_request',
                'message': 'A valid recommendation request is required.',
            }

        if len(request.candidates) == 0:
            return None, {
                'reason': RefusalReason.INSUFFICIENT_DATA,
                'code': 'no_candidate_provided',
                'message': 'No candidate was provided for recommendation evaluation.',
            }

        if len(request.candidates) > 1:
            return None, {
                'reason': RefusalReason.INSUFFICIENT_DATA,
                'code': 'multi_candidate_ranking_not_implemented',
                'message': (
                    'Recommendation Engine V1 does not rank or select across '
                    'multiple candidates in this phase.'
                ),
            }

        candidate_value = request.candidates[0]
        if not isinstance(candidate_value, RecommendationCandidate):
            return None, {
                'reason': RefusalReason.INSUFFICIENT_DATA,
                'code': 'invalid_candidate',
                'message': 'A valid recommendation candidate is required.',
            }
        return candidate_value, None

    def _context_from_request(self, request):
        if not isinstance(request, RecommendationRequest):
            return {}

        context = dict(request.metadata)
        if request.category is not None:
            context['requested_category'] = request.category.value
            context['requested_category_code'] = request.category.name
        if request.team_id is not None:
            context['team_id'] = request.team_id
        if request.team_name is not None:
            context['team_name'] = request.team_name
        return context

    def _refuse(self, reason, explanation_code, explanation_message, metadata):
        return RecommendationResult.refuse(
            reason=reason,
            explanations=(
                RecommendationExplanation(
                    code=explanation_code,
                    message=explanation_message,
                ),
            ),
            limitations=(
                *BASE_RECOMMENDATION_LIMITATIONS,
                RecommendationLimitation(
                    code='engine_fail_closed',
                    message=(
                        'RecommendationEngine.recommend failed closed and did '
                        'not emit category eligibility.'
                    ),
                ),
            ),
            metadata=metadata,
        )
