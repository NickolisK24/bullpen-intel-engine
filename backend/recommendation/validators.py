"""Validation helpers for Recommendation Engine V1 result contracts."""

from recommendation.contracts import RecommendationRefusal
from recommendation.enums import RecommendationOutcome
from recommendation.result import RecommendationResult


def recommendation_result_errors(result):
    errors = []

    if not isinstance(result, RecommendationResult):
        return ['Result must be a RecommendationResult instance.']

    if result.is_refusal:
        if not isinstance(result.refusal, RecommendationRefusal):
            errors.append('Refusal result must include a refusal object.')
        if result.category is not None:
            errors.append('Refusal result must not include a category.')
        if result.pitcher_id is not None:
            errors.append('Refusal result must not include a pitcher id.')
        if result.pitcher_name is not None:
            errors.append('Refusal result must not include a pitcher name.')
        if result.has_recommendation:
            errors.append('Refusal result must not emit a recommendation.')
        return errors

    if result.outcome != RecommendationOutcome.RECOMMENDATION:
        errors.append('Non-refusal result must have recommendation outcome.')
    if result.category is None:
        errors.append('Recommendation result must include a category.')
    if result.pitcher_id is None:
        errors.append('Recommendation result must include a pitcher id.')
    if not result.pitcher_name:
        errors.append('Recommendation result must include a pitcher name.')
    if not result.explanations:
        errors.append('Recommendation result must include explanations.')
    if not result.limitations:
        errors.append('Recommendation result must include limitations.')

    return errors


def is_valid_recommendation_result(result):
    return recommendation_result_errors(result) == []
