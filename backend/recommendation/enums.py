"""Enumerations for Recommendation Engine V1 contracts."""

from enum import Enum


class StringEnum(str, Enum):
    """String-valued enum with stable API serialization values."""

    def __str__(self):
        return self.value


class RecommendationCategory(StringEnum):
    BEST_AVAILABLE_ARM = 'Best Available Arm'
    FRESHEST_HIGH_LEVERAGE_ARM = 'Freshest High-Leverage Arm'
    LOWEST_CURRENT_WORKLOAD_RISK = 'Lowest Current Workload Risk'
    USE_WITH_CAUTION = 'Use With Caution'
    AVOID_TONIGHT = 'Avoid Tonight'
    BULLPEN_STRESS_ALERT = 'Bullpen Stress Alert'


class RecommendationConfidence(StringEnum):
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    UNKNOWN = 'unknown'


class RecommendationFreshnessState(StringEnum):
    FRESH = 'fresh'
    STALE = 'stale'
    MISSING = 'missing'
    HISTORICAL = 'historical'
    INCOMPLETE = 'incomplete'
    UNKNOWN = 'unknown'


class RefusalReason(StringEnum):
    INSUFFICIENT_DATA = 'insufficient_data'
    STALE_DATA = 'stale_data'
    LOW_CONFIDENCE = 'low_confidence'
    NO_ELIGIBLE_PITCHERS = 'no_eligible_pitchers'
    DATA_UNAVAILABLE = 'data_unavailable'
    UNKNOWN_FRESHNESS = 'unknown_freshness'
    CATEGORY_OUT_OF_SCOPE = 'category_out_of_scope'
    UNSUPPORTED_CLAIM_REQUESTED = 'unsupported_claim_requested'
    MISSING_LIMITATIONS = 'missing_limitations'


class RecommendationOutcome(StringEnum):
    RECOMMENDATION = 'recommendation'
    REFUSAL = 'refusal'


class RecommendationCandidatePool(StringEnum):
    GENERAL = 'general'
    POSITIVE = 'positive'
    CAUTIONARY = 'cautionary'
