"""Eligibility and exclusion gates for Recommendation Engine V1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from recommendation.contracts import (
    BASE_RECOMMENDATION_LIMITATIONS,
    RecommendationCandidate,
    RecommendationExplanation,
    RecommendationLimitation,
)
from recommendation.enums import (
    RecommendationCandidatePool,
    RecommendationConfidence,
    RecommendationFreshnessState,
)


STATUS_AVAILABLE = 'Available'
STATUS_MONITOR = 'Monitor'
STATUS_LIMITED = 'Limited'
STATUS_AVOID = 'Avoid'
STATUS_UNAVAILABLE = 'Unavailable'

PASSING_FRESHNESS_STATES = {RecommendationFreshnessState.FRESH}
PASSING_CONFIDENCE_STATES = {
    RecommendationConfidence.HIGH,
    RecommendationConfidence.MEDIUM,
}


@dataclass(frozen=True)
class RecommendationGateResult:
    pitcher_id: int | None
    pitcher_name: str | None
    eligible: bool
    excluded: bool
    exclusion_reasons: tuple[str, ...]
    caution_reasons: tuple[str, ...]
    confidence_state: RecommendationConfidence
    freshness_state: RecommendationFreshnessState
    availability_state: str | None
    explanations: tuple[RecommendationExplanation, ...]
    limitations: tuple[RecommendationLimitation, ...] = BASE_RECOMMENDATION_LIMITATIONS
    candidate_pool: RecommendationCandidatePool = RecommendationCandidatePool.GENERAL
    positive_pool_eligible: bool = False

    def to_dict(self):
        return {
            'pitcher_id': self.pitcher_id,
            'pitcher_name': self.pitcher_name,
            'eligible': self.eligible,
            'excluded': self.excluded,
            'exclusion_reasons': list(self.exclusion_reasons),
            'caution_reasons': list(self.caution_reasons),
            'confidence_state': self.confidence_state.value,
            'confidence_state_code': self.confidence_state.name,
            'freshness_state': self.freshness_state.value,
            'freshness_state_code': self.freshness_state.name,
            'availability_state': self.availability_state,
            'explanations': [
                explanation.to_dict() for explanation in self.explanations
            ],
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'candidate_pool': self.candidate_pool.value,
            'candidate_pool_code': self.candidate_pool.name,
            'positive_pool_eligible': self.positive_pool_eligible,
        }


def evaluate_candidate_gates(
    candidate: RecommendationCandidate | None,
    candidate_pool: RecommendationCandidatePool = RecommendationCandidatePool.GENERAL,
):
    if candidate is None:
        return _build_result(
            candidate=None,
            candidate_pool=candidate_pool,
            confidence=RecommendationConfidence.UNKNOWN,
            freshness=RecommendationFreshnessState.UNKNOWN,
            availability_status=None,
            exclusion_reasons=('missing_candidate',),
            caution_reasons=(),
        )

    availability = _as_mapping(candidate.availability)
    metadata = _as_mapping(candidate.metadata)
    confidence = _confidence_from(availability, candidate.metadata)
    freshness = _freshness_from(availability, candidate.metadata)
    freshness_present = _freshness_present(availability, metadata)
    availability_status = _availability_status_from(availability)
    exclusion_reasons = []
    caution_reasons = []

    if candidate.pitcher_id is None:
        exclusion_reasons.append('missing_pitcher_identity')

    if not availability:
        exclusion_reasons.append('missing_availability')
    elif availability_status is None:
        exclusion_reasons.append('missing_availability_status')
    elif availability_status == STATUS_UNAVAILABLE:
        exclusion_reasons.append('availability_unavailable')
    elif availability_status == STATUS_AVOID:
        if candidate_pool == RecommendationCandidatePool.POSITIVE:
            exclusion_reasons.append('avoid_not_positive_candidate')
        else:
            caution_reasons.append('avoid_only_for_avoidance_context')
    elif availability_status == STATUS_LIMITED:
        if candidate_pool == RecommendationCandidatePool.POSITIVE:
            exclusion_reasons.append('limited_not_positive_candidate')
        else:
            caution_reasons.append('limited_use_only')
    elif availability_status == STATUS_MONITOR:
        caution_reasons.append('monitor_requires_review')
    elif availability_status != STATUS_AVAILABLE:
        exclusion_reasons.append('unsupported_availability_status')

    if confidence == RecommendationConfidence.LOW:
        exclusion_reasons.append('low_confidence')
    elif confidence == RecommendationConfidence.UNKNOWN:
        exclusion_reasons.append('unknown_confidence')
    elif confidence == RecommendationConfidence.MEDIUM:
        caution_reasons.append('medium_confidence_requires_limitation')

    if not freshness_present:
        exclusion_reasons.append('missing_freshness')
    elif freshness == RecommendationFreshnessState.STALE:
        exclusion_reasons.append('stale_freshness')
    elif freshness == RecommendationFreshnessState.MISSING:
        exclusion_reasons.append('missing_freshness')
    elif freshness == RecommendationFreshnessState.UNKNOWN:
        exclusion_reasons.append('unknown_freshness')
    elif freshness in (
        RecommendationFreshnessState.HISTORICAL,
        RecommendationFreshnessState.INCOMPLETE,
    ):
        exclusion_reasons.append(f'{freshness.value}_freshness')

    unique_exclusions = _unique(exclusion_reasons)
    unique_cautions = _unique(caution_reasons)

    return _build_result(
        candidate=candidate,
        candidate_pool=candidate_pool,
        confidence=confidence,
        freshness=freshness,
        availability_status=availability_status,
        exclusion_reasons=unique_exclusions,
        caution_reasons=unique_cautions,
    )


def evaluate_candidate_pool(
    candidates: tuple[RecommendationCandidate, ...] | list[RecommendationCandidate],
    candidate_pool: RecommendationCandidatePool = RecommendationCandidatePool.GENERAL,
):
    return tuple(
        evaluate_candidate_gates(candidate, candidate_pool=candidate_pool)
        for candidate in candidates
    )


def _build_result(
    candidate,
    candidate_pool,
    confidence,
    freshness,
    availability_status,
    exclusion_reasons,
    caution_reasons,
):
    excluded = bool(exclusion_reasons)
    positive_pool_eligible = (
        not excluded
        and confidence == RecommendationConfidence.HIGH
        and freshness == RecommendationFreshnessState.FRESH
        and availability_status in (STATUS_AVAILABLE, STATUS_MONITOR)
    )

    eligible = not excluded
    explanations = _explanations(
        exclusion_reasons=exclusion_reasons,
        caution_reasons=caution_reasons,
        eligible=eligible,
    )

    return RecommendationGateResult(
        pitcher_id=getattr(candidate, 'pitcher_id', None),
        pitcher_name=getattr(candidate, 'pitcher_name', None),
        eligible=eligible,
        excluded=excluded,
        exclusion_reasons=tuple(exclusion_reasons),
        caution_reasons=tuple(caution_reasons),
        confidence_state=confidence,
        freshness_state=freshness,
        availability_state=availability_status,
        explanations=explanations,
        limitations=_limitations(caution_reasons, exclusion_reasons),
        candidate_pool=candidate_pool,
        positive_pool_eligible=positive_pool_eligible,
    )


def _as_mapping(value):
    return value if isinstance(value, Mapping) else {}


def _availability_status_from(availability):
    status = availability.get('availability_status') or availability.get('status')
    return str(status) if status is not None else None


def _confidence_from(availability, metadata):
    raw = availability.get('confidence') or _as_mapping(metadata).get('confidence')
    return _enum_from_value(
        RecommendationConfidence,
        raw,
        default=RecommendationConfidence.UNKNOWN,
    )


def _freshness_from(availability, metadata):
    metadata = _as_mapping(metadata)
    raw = (
        metadata.get('freshness_state')
        or metadata.get('data_state')
        or availability.get('freshness_state')
        or availability.get('data_state')
    )
    if isinstance(raw, str) and raw.lower() == 'stable':
        return RecommendationFreshnessState.FRESH
    return _enum_from_value(
        RecommendationFreshnessState,
        raw,
        default=RecommendationFreshnessState.UNKNOWN,
    )


def _freshness_present(availability, metadata):
    return any(
        key in metadata or key in availability
        for key in ('freshness_state', 'data_state')
    )


def _enum_from_value(enum_type, value, default):
    if isinstance(value, enum_type):
        return value
    if value is None:
        return default

    normalized = str(value).strip().lower()
    for member in enum_type:
        if normalized in (member.value.lower(), member.name.lower()):
            return member
    return default


def _explanations(exclusion_reasons, caution_reasons, eligible):
    if not exclusion_reasons and not caution_reasons:
        return (
            RecommendationExplanation(
                code='eligibility_passed',
                message='Candidate passed Recommendation Engine V1 eligibility gates.',
            ),
        )

    explanations = []
    for reason in exclusion_reasons:
        explanations.append(
            RecommendationExplanation(
                code=reason,
                message=_reason_message(reason),
            )
        )
    for reason in caution_reasons:
        explanations.append(
            RecommendationExplanation(
                code=reason,
                message=_reason_message(reason),
            )
        )
    if eligible:
        explanations.append(
            RecommendationExplanation(
                code='eligible_with_caution',
                message='Candidate may proceed only with the listed cautions.',
            )
        )
    return tuple(explanations)


def _limitations(caution_reasons, exclusion_reasons):
    limitations = list(BASE_RECOMMENDATION_LIMITATIONS)
    if caution_reasons:
        limitations.append(
            RecommendationLimitation(
                code='candidate_requires_caution',
                message='Candidate requires cautionary handling before any recommendation use.',
            )
        )
    if exclusion_reasons:
        limitations.append(
            RecommendationLimitation(
                code='candidate_excluded',
                message='Candidate is excluded because trusted recommendation inputs are insufficient or disqualifying.',
            )
        )
    return tuple(limitations)


def _reason_message(reason):
    messages = {
        'missing_candidate': 'No candidate was provided for eligibility evaluation.',
        'missing_pitcher_identity': 'Pitcher identity is missing.',
        'missing_availability': 'Availability output is missing.',
        'missing_availability_status': 'Availability status is missing.',
        'availability_unavailable': 'Availability status is Unavailable.',
        'avoid_not_positive_candidate': 'Avoid status cannot enter the positive recommendation pool.',
        'limited_not_positive_candidate': 'Limited status cannot enter the positive recommendation pool.',
        'avoid_only_for_avoidance_context': 'Avoid status may only support avoidance or stress context.',
        'limited_use_only': 'Limited status requires cautionary or limited-use handling.',
        'monitor_requires_review': 'Monitor status requires review of workload caution evidence.',
        'unsupported_availability_status': 'Availability status is not supported by Recommendation Engine V1 policy.',
        'low_confidence': 'Low confidence fails closed.',
        'unknown_confidence': 'Unknown confidence fails closed.',
        'medium_confidence_requires_limitation': 'Medium confidence requires visible limitations.',
        'stale_freshness': 'Stale freshness fails closed.',
        'missing_freshness': 'Freshness metadata is missing.',
        'unknown_freshness': 'Unknown freshness fails closed.',
        'historical_freshness': 'Historical freshness cannot support current recommendations.',
        'incomplete_freshness': 'Incomplete freshness cannot support current recommendations.',
    }
    return messages.get(reason, reason.replace('_', ' ').capitalize())


def _unique(values):
    return tuple(dict.fromkeys(values))
