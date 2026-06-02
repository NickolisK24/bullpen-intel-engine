"""Category assignment foundation for Recommendation Engine V1."""

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
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationFreshnessState,
)
from recommendation.gates import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    RecommendationGateResult,
)


WORKLOAD_EVIDENCE_KEYS = {
    'fatigue_score',
    'fatigue_risk_level',
    'pitches_yesterday',
    'pitches_last_3_days',
    'pitches_last_5_days',
    'appearances_last_3_days',
    'appearances_last_5_days',
    'days_rest',
    'latest_game_date',
}
LEVERAGE_EVIDENCE_KEYS = {
    'high_leverage_evidence',
    'leverage_evidence',
    'role_evidence',
}


@dataclass(frozen=True)
class RecommendationCategoryBlock:
    category: RecommendationCategory
    reasons: tuple[str, ...]

    def to_dict(self):
        return {
            'category': self.category.value,
            'category_code': self.category.name,
            'reasons': list(self.reasons),
        }


@dataclass(frozen=True)
class RecommendationCategoryAssignment:
    pitcher_id: int | None
    pitcher_name: str | None
    assigned_categories: tuple[RecommendationCategory, ...]
    blocked_categories: tuple[RecommendationCategoryBlock, ...]
    assignment_explanations: tuple[RecommendationExplanation, ...]
    limitations: tuple[RecommendationLimitation, ...]
    gate_result: Mapping[str, Any] | None
    confidence_state: RecommendationConfidence
    freshness_state: RecommendationFreshnessState
    availability_state: str | None
    ranking_applied: bool = False
    selection_made: bool = False
    selected_pitcher_id: int | None = None

    def to_dict(self):
        return {
            'pitcher_id': self.pitcher_id,
            'pitcher_name': self.pitcher_name,
            'assigned_categories': [
                category.value for category in self.assigned_categories
            ],
            'assigned_category_codes': [
                category.name for category in self.assigned_categories
            ],
            'blocked_categories': [
                blocked.to_dict() for blocked in self.blocked_categories
            ],
            'assignment_explanations': [
                explanation.to_dict()
                for explanation in self.assignment_explanations
            ],
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'gate_result': dict(self.gate_result) if self.gate_result else None,
            'confidence_state': self.confidence_state.value,
            'confidence_state_code': self.confidence_state.name,
            'freshness_state': self.freshness_state.value,
            'freshness_state_code': self.freshness_state.name,
            'availability_state': self.availability_state,
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
            'selected_pitcher_id': self.selected_pitcher_id,
        }


def assign_recommendation_categories(
    gate_result: RecommendationGateResult | None,
    candidate: RecommendationCandidate | None = None,
    context: Mapping[str, Any] | None = None,
):
    context = _as_mapping(context)
    if not isinstance(gate_result, RecommendationGateResult):
        return _fail_closed_assignment(
            reason='missing_or_invalid_gate_result',
            context=context,
        )

    evidence = _candidate_evidence(candidate)
    assigned = []
    blocked = []
    explanations = []

    _assign_best_available_arm(gate_result, assigned, blocked, explanations)
    _assign_freshest_high_leverage_arm(
        gate_result,
        evidence,
        assigned,
        blocked,
        explanations,
    )
    _assign_lowest_current_workload_risk(
        gate_result,
        evidence,
        assigned,
        blocked,
        explanations,
    )
    _assign_use_with_caution(gate_result, assigned, blocked, explanations)
    _assign_avoid_tonight(gate_result, assigned, blocked, explanations)
    _assign_bullpen_stress_alert(context, assigned, blocked, explanations)

    if not assigned and not explanations:
        explanations.append(
            RecommendationExplanation(
                code='no_categories_assigned',
                message='No recommendation categories were assigned.',
            )
        )

    return RecommendationCategoryAssignment(
        pitcher_id=gate_result.pitcher_id,
        pitcher_name=gate_result.pitcher_name,
        assigned_categories=tuple(assigned),
        blocked_categories=tuple(blocked),
        assignment_explanations=tuple(explanations),
        limitations=_limitations(gate_result, assigned, blocked),
        gate_result=gate_result.to_dict(),
        confidence_state=gate_result.confidence_state,
        freshness_state=gate_result.freshness_state,
        availability_state=gate_result.availability_state,
    )


def _assign_best_available_arm(gate_result, assigned, blocked, explanations):
    category = RecommendationCategory.BEST_AVAILABLE_ARM
    if _positive_category_allowed(gate_result):
        _assign(
            category,
            assigned,
            explanations,
            'best_available_arm_eligible',
            'Candidate is eligible for Best Available Arm consideration. This is not final selection.',
        )
        return

    _block(category, blocked, _positive_block_reasons(gate_result))


def _assign_freshest_high_leverage_arm(
    gate_result,
    evidence,
    assigned,
    blocked,
    explanations,
):
    category = RecommendationCategory.FRESHEST_HIGH_LEVERAGE_ARM
    reasons = []
    if not _positive_category_allowed(gate_result):
        reasons.extend(_positive_block_reasons(gate_result))
    if not _has_workload_evidence(evidence):
        reasons.append('missing_workload_evidence')
    if not _has_leverage_evidence(evidence):
        reasons.append('missing_leverage_evidence')

    if reasons:
        _block(category, blocked, reasons)
        return

    _assign(
        category,
        assigned,
        explanations,
        'freshest_high_leverage_arm_eligible',
        'Candidate has the required freshness and existing leverage evidence for category eligibility. This is not final selection.',
    )


def _assign_lowest_current_workload_risk(
    gate_result,
    evidence,
    assigned,
    blocked,
    explanations,
):
    category = RecommendationCategory.LOWEST_CURRENT_WORKLOAD_RISK
    reasons = []
    if not _positive_category_allowed(gate_result):
        reasons.extend(_positive_block_reasons(gate_result))
    if not _has_workload_evidence(evidence):
        reasons.append('missing_workload_evidence')

    if reasons:
        _block(category, blocked, reasons)
        return

    _assign(
        category,
        assigned,
        explanations,
        'lowest_current_workload_risk_eligible',
        'Candidate has workload or fatigue evidence for workload-risk category eligibility. This is not final selection.',
    )


def _assign_use_with_caution(gate_result, assigned, blocked, explanations):
    category = RecommendationCategory.USE_WITH_CAUTION
    if gate_result.eligible and gate_result.caution_reasons:
        _assign(
            category,
            assigned,
            explanations,
            'use_with_caution_eligible',
            'Candidate passed gates with caution reasons and may be used only in cautionary context.',
        )
        return

    reasons = []
    if gate_result.excluded:
        reasons.extend(gate_result.exclusion_reasons)
    if not gate_result.caution_reasons:
        reasons.append('no_caution_reasons')
    _block(category, blocked, reasons)


def _assign_avoid_tonight(gate_result, assigned, blocked, explanations):
    category = RecommendationCategory.AVOID_TONIGHT
    trusted = _trusted_for_avoidance(gate_result)
    avoid_status = gate_result.availability_state in (STATUS_AVOID, STATUS_UNAVAILABLE)

    if trusted and avoid_status:
        _assign(
            category,
            assigned,
            explanations,
            'avoid_tonight_eligible',
            'Candidate has trusted availability evidence for avoidance-category eligibility.',
        )
        return

    reasons = []
    if not trusted:
        reasons.append('trusted_avoidance_evidence_unavailable')
    if not avoid_status:
        reasons.append('availability_not_avoid_or_unavailable')
    _block(category, blocked, reasons)


def _assign_bullpen_stress_alert(context, assigned, blocked, explanations):
    category = RecommendationCategory.BULLPEN_STRESS_ALERT
    if context.get('bullpen_stress_evidence') and context.get('team_scope'):
        _assign(
            category,
            assigned,
            explanations,
            'bullpen_stress_alert_eligible',
            'Team-level bullpen stress evidence is available for category eligibility.',
        )
        return

    _block(category, blocked, ('requires_bullpen_context',))


def _positive_category_allowed(gate_result):
    return (
        gate_result.eligible
        and not gate_result.excluded
        and gate_result.positive_pool_eligible
        and gate_result.confidence_state == RecommendationConfidence.HIGH
        and gate_result.freshness_state == RecommendationFreshnessState.FRESH
    )


def _positive_block_reasons(gate_result):
    reasons = []
    if not gate_result.eligible:
        reasons.append('candidate_not_eligible')
    if gate_result.excluded:
        reasons.append('candidate_excluded')
    if not gate_result.positive_pool_eligible:
        reasons.append('not_positive_pool_eligible')
    if gate_result.confidence_state != RecommendationConfidence.HIGH:
        reasons.append('positive_category_requires_high_confidence')
    if gate_result.freshness_state != RecommendationFreshnessState.FRESH:
        reasons.append('positive_category_requires_fresh_data')
    return tuple(dict.fromkeys(reasons))


def _trusted_for_avoidance(gate_result):
    return (
        gate_result.confidence_state in (
            RecommendationConfidence.HIGH,
            RecommendationConfidence.MEDIUM,
        )
        and gate_result.freshness_state == RecommendationFreshnessState.FRESH
    )


def _candidate_evidence(candidate):
    if candidate is None:
        return {}
    availability = _as_mapping(candidate.availability)
    metadata = _as_mapping(candidate.metadata)
    inputs = _as_mapping(availability.get('inputs'))
    return {
        'availability': availability,
        'metadata': metadata,
        'inputs': inputs,
    }


def _has_workload_evidence(evidence):
    inputs = evidence.get('inputs') or {}
    metadata = evidence.get('metadata') or {}
    if metadata.get('workload_evidence') or metadata.get('fatigue_evidence'):
        return True
    return any(inputs.get(key) is not None for key in WORKLOAD_EVIDENCE_KEYS)


def _has_leverage_evidence(evidence):
    metadata = evidence.get('metadata') or {}
    return any(bool(metadata.get(key)) for key in LEVERAGE_EVIDENCE_KEYS)


def _assign(category, assigned, explanations, code, message):
    assigned.append(category)
    explanations.append(
        RecommendationExplanation(
            code=code,
            message=message,
        )
    )


def _block(category, blocked, reasons):
    blocked.append(
        RecommendationCategoryBlock(
            category=category,
            reasons=tuple(dict.fromkeys(reasons)),
        )
    )


def _limitations(gate_result, assigned, blocked):
    limitations = list(BASE_RECOMMENDATION_LIMITATIONS)
    limitations.append(
        RecommendationLimitation(
            code='category_assignment_only',
            message='Category assignment is eligibility mapping only; it does not select, rank, or recommend a pitcher.',
        )
    )
    if gate_result.caution_reasons:
        limitations.append(
            RecommendationLimitation(
                code='candidate_has_cautions',
                message='Candidate has gate caution reasons that must remain visible before future recommendation use.',
            )
        )
    if blocked:
        limitations.append(
            RecommendationLimitation(
                code='categories_blocked',
                message='One or more categories are blocked by Recommendation Engine V1 policy gates or missing evidence.',
            )
        )
    if not assigned:
        limitations.append(
            RecommendationLimitation(
                code='no_category_selection',
                message='No category was assigned; no recommendation should be emitted.',
            )
        )
    return tuple(limitations)


def _fail_closed_assignment(reason, context):
    blocked = tuple(
        RecommendationCategoryBlock(
            category=category,
            reasons=(reason,),
        )
        for category in RecommendationCategory
    )
    explanation = RecommendationExplanation(
        code=reason,
        message='Category assignment failed closed because no valid gate result was provided.',
    )
    limitations = list(BASE_RECOMMENDATION_LIMITATIONS)
    limitations.append(
        RecommendationLimitation(
            code='category_assignment_only',
            message='Category assignment is eligibility mapping only; it does not select, rank, or recommend a pitcher.',
        )
    )
    limitations.append(
        RecommendationLimitation(
            code='missing_gate_result',
            message='A valid eligibility gate result is required before category assignment.',
        )
    )
    return RecommendationCategoryAssignment(
        pitcher_id=None,
        pitcher_name=None,
        assigned_categories=(),
        blocked_categories=blocked,
        assignment_explanations=(explanation,),
        limitations=tuple(limitations),
        gate_result=None,
        confidence_state=RecommendationConfidence.UNKNOWN,
        freshness_state=RecommendationFreshnessState.UNKNOWN,
        availability_state=None,
        ranking_applied=False,
        selection_made=False,
        selected_pitcher_id=None,
    )


def _as_mapping(value):
    return value if isinstance(value, Mapping) else {}
