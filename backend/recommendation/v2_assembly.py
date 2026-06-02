"""Recommendation Engine V2 backend context assembly layer.

This module maps existing availability and workload evidence into the V2
domain objects. It is internal-only and does not expose API or frontend
behavior.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from recommendation.contracts import RecommendationCandidate
from recommendation.enums import RecommendationConfidence, RecommendationFreshnessState
from recommendation.v2 import (
    BASE_V2_LIMITATIONS,
    BullpenState,
    CandidateGroup,
    RecommendationContext,
    TeamBullpenContext,
    V2Explanation,
    V2FreshnessMetadata,
    V2Limitation,
    V2Refusal,
    require_v2_governance_safe,
    require_v2_trust_metadata,
    v2_governance_errors,
)


V2_CONTEXT_ASSEMBLY_PHASE = 'phase_2_backend_context_assembly'
V2_CONTEXT_ASSEMBLY_SOURCE = 'existing_availability_workload_evidence'
V2_NEUTRAL_INTELLIGENCE_PHASE = 'phase_3_neutral_intelligence_expansion'
V2_INVENTORY_VISIBILITY_PHASE = 'phase_4_inventory_visibility_layer'
V2_TEAM_BULLPEN_CONTEXT_PHASE = 'phase_5_team_bullpen_context_layer'
V2_TRUST_METADATA_INTEGRATION_PHASE = 'phase_6_trust_metadata_integration'
V2_REFUSAL_FAIL_CLOSED_PHASE = 'phase_7_refusal_fail_closed_integration'

AVAILABILITY_STATUS_ORDER = (
    'Available',
    'Monitor',
    'Limited',
    'Avoid',
    'Unavailable',
    'Unknown',
)
CONFIDENCE_ORDER = ('high', 'medium', 'low', 'unknown')
DATA_STATE_ORDER = ('fresh', 'stale', 'missing', 'incomplete', 'historical', 'unknown')
DEGRADED_DATA_STATES = frozenset({'stale', 'incomplete', 'historical', 'unknown'})
FAIL_CLOSED_TRUST_ERROR_FIELDS = frozenset(
    {
        'confidence',
        'freshness',
        'data_state',
        'refusal',
        'limitations',
        'explanations',
        'unsupported_trust_fields',
        'malformed_evidence',
    }
)
ELIGIBILITY_CATEGORY_ORDER = (
    'evidence_complete',
    'cautionary_evidence',
    'refused_or_degraded_evidence',
    'unknown_evidence',
)
REFUSAL_CATEGORY_ORDER = (
    'no_refusal',
    'availability_refusal',
    'freshness_refusal',
    'confidence_refusal',
    'missing_evidence_refusal',
)
WORKLOAD_CATEGORY_ORDER = ('low', 'moderate', 'elevated', 'unknown')
NEUTRAL_INTELLIGENCE_DIMENSIONS = (
    'eligibility',
    'refusal',
    'freshness',
    'readiness',
    'workload',
)
GROUPING_DIMENSION_ORDER = (
    'availability_status',
    *NEUTRAL_INTELLIGENCE_DIMENSIONS,
)
INVENTORY_VISIBILITY_SECTIONS = (
    'availability',
    'eligibility',
    'refusal',
    'freshness',
    'readiness',
    'workload',
)
TEAM_BULLPEN_CONTEXT_SECTIONS = (
    'team_bullpen_status',
    'availability_distribution',
    'eligibility_distribution',
    'refusal_distribution',
    'freshness_distribution',
    'readiness_distribution',
    'workload_distribution',
    'limitation_summary',
    'explanation_summary',
    'trust_summary',
)

ELIGIBILITY_CATEGORY_LABELS = {
    'evidence_complete': 'Evidence Complete',
    'cautionary_evidence': 'Cautionary Evidence',
    'refused_or_degraded_evidence': 'Refused Or Degraded Evidence',
    'unknown_evidence': 'Unknown Evidence',
}

REFUSAL_CATEGORY_LABELS = {
    'no_refusal': 'No Refusal Metadata',
    'availability_refusal': 'Availability Refusal Metadata',
    'freshness_refusal': 'Freshness Refusal Metadata',
    'confidence_refusal': 'Confidence Refusal Metadata',
    'missing_evidence_refusal': 'Missing Evidence Refusal Metadata',
}


@dataclass(frozen=True)
class V2ContextAssembly:
    bullpen_state: BullpenState
    team_context: TeamBullpenContext
    recommendation_context: RecommendationContext
    candidate_groups: tuple[CandidateGroup, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, 'candidate_groups', tuple(self.candidate_groups))
        object.__setattr__(self, 'metadata', dict(self.metadata or {}))
        require_v2_governance_safe(self.metadata)

    def to_dict(self):
        recommendation_context = self.recommendation_context.to_dict()
        payload = {
            'metadata': dict(self.metadata),
            'recommendation_context': recommendation_context,
            'bullpen_state': self.bullpen_state.to_dict(),
            'team_context': self.team_context.to_dict(),
            'candidate_groups': [
                group.to_dict() for group in self.candidate_groups
            ],
            'trust_metadata': recommendation_context['trust_metadata'],
            'ranking_applied': False,
            'selection_made': False,
        }
        require_v2_governance_safe(payload)
        require_v2_trust_metadata(payload)
        return payload


def assemble_v2_context(
    candidates: Iterable[RecommendationCandidate | Mapping[str, Any]] | None,
    *,
    team_id: int | None = None,
    team_name: str | None = None,
    generated_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> V2ContextAssembly:
    """Assemble internal V2 bullpen context from existing backend evidence."""
    source_metadata = dict(metadata or {})
    require_v2_governance_safe(source_metadata)

    records = [_candidate_record(candidate) for candidate in list(candidates or ())]
    unsafe_errors = _unsafe_input_errors(records)
    trust_validation_errors = _trust_input_errors(records)
    if unsafe_errors:
        context = _recommendation_context(
            records=(),
            scope='bullpen_state',
            generated_at=generated_at,
            explicit_refusals=(
                V2Refusal(
                    refusal_id='unsupported_governance_fields',
                    reason='unsupported_fields',
                    message=(
                        'V2 context assembly refused because source evidence '
                        'contains ranking, selection, prediction, or other '
                        'governance-unsafe fields.'
                    ),
                    applies_to='context_assembly',
                ),
            ),
            explicit_explanations=(
                V2Explanation(
                    code='context_assembly_failed_closed',
                    message='Context assembly failed closed before grouping candidates.',
                    applies_to='context_assembly',
                    details={'error_count': len(unsafe_errors)},
                ),
            ),
        )
        refusal_fail_closed = _refusal_fail_closed_summary(
            records=(),
            context=context,
            failed_closed=True,
            unsafe_errors=unsafe_errors,
            trust_validation_errors=(),
        )
        inventory_visibility = _inventory_visibility_summary(
            records=(),
            candidate_groups=(),
            context=context,
            failed_closed=True,
            refusal_fail_closed=refusal_fail_closed,
        )
        team_bullpen_context_summary = _team_bullpen_context_summary(
            records=(),
            inventory_visibility=inventory_visibility,
            context=context,
            failed_closed=True,
            refusal_fail_closed=refusal_fail_closed,
        )
        bullpen_state = BullpenState(
            team_id=team_id,
            team_name=team_name,
            bullpen_status='refused',
            inventory={
                'total_pitchers': 0,
                'availability_status_counts': _ordered_counts(Counter(), AVAILABILITY_STATUS_ORDER),
                'candidate_group_count': 0,
                'neutral_intelligence_dimensions': list(NEUTRAL_INTELLIGENCE_DIMENSIONS),
                'visibility_summary': inventory_visibility,
            },
            readiness={
                'data_state_counts': _ordered_counts(Counter(), DATA_STATE_ORDER),
                'eligibility_category_counts': _ordered_counts(Counter(), ELIGIBILITY_CATEGORY_ORDER),
                'refusal_category_counts': _ordered_counts(Counter(), REFUSAL_CATEGORY_ORDER),
                'freshness_category_counts': _ordered_counts(Counter(), DATA_STATE_ORDER),
            },
            workload={
                'workload_evidence_available': False,
                'workload_category_counts': _ordered_counts(Counter(), WORKLOAD_CATEGORY_ORDER),
            },
            stress={'stress_level': 'unknown'},
            candidate_groups=(),
            context=context,
        )
        team_context = TeamBullpenContext(
            team_id=team_id,
            team_name=team_name,
            leverage_inventory={'source_evidence_available': False},
            workload_distribution={
                'workload_evidence_available': False,
                'workload_category_counts': _ordered_counts(Counter(), WORKLOAD_CATEGORY_ORDER),
            },
            readiness_distribution={
                'data_state_counts': _ordered_counts(Counter(), DATA_STATE_ORDER),
                'eligibility_category_counts': _ordered_counts(Counter(), ELIGIBILITY_CATEGORY_ORDER),
                'refusal_category_counts': _ordered_counts(Counter(), REFUSAL_CATEGORY_ORDER),
                'freshness_category_counts': _ordered_counts(Counter(), DATA_STATE_ORDER),
            },
            stress_indicators={'stress_level': 'unknown'},
            team_summary=team_bullpen_context_summary,
            context=context,
        )
        return V2ContextAssembly(
            bullpen_state=bullpen_state,
            team_context=team_context,
            recommendation_context=context,
            candidate_groups=(),
            metadata={
                'assembly_phase': V2_CONTEXT_ASSEMBLY_PHASE,
                'source': V2_CONTEXT_ASSEMBLY_SOURCE,
                'input_candidate_count': len(records),
                'assembled_candidate_count': 0,
                'failed_closed': True,
                'unsafe_input_error_count': len(unsafe_errors),
                'neutral_intelligence': _neutral_intelligence_summary(
                    records=(),
                    candidate_groups=(),
                    context=context,
                    failed_closed=True,
                    refusal_fail_closed=refusal_fail_closed,
                ),
                'inventory_visibility': inventory_visibility,
                'team_bullpen_context_summary': team_bullpen_context_summary,
                'refusal_fail_closed': refusal_fail_closed,
                'trust_metadata': _context_trust_metadata(
                    context,
                    failed_closed=True,
                ),
            },
        )

    context = _recommendation_context(
        records=records,
        scope='bullpen_state',
        generated_at=generated_at,
        trust_validation_errors=trust_validation_errors,
    )
    output_records = (
        ()
        if _should_suppress_candidate_output(trust_validation_errors)
        else records
    )
    candidate_groups = _candidate_groups(output_records, generated_at=generated_at)
    failed_closed = bool(context.refusal_reasons)
    refusal_fail_closed = _refusal_fail_closed_summary(
        records=records,
        context=context,
        failed_closed=failed_closed,
        unsafe_errors=(),
        trust_validation_errors=trust_validation_errors,
    )
    neutral_intelligence = _neutral_intelligence_summary(
        records=output_records,
        candidate_groups=candidate_groups,
        context=context,
        failed_closed=failed_closed,
        refusal_fail_closed=refusal_fail_closed,
    )
    inventory_visibility = _inventory_visibility_summary(
        records=output_records,
        candidate_groups=candidate_groups,
        context=context,
        failed_closed=failed_closed,
        refusal_fail_closed=refusal_fail_closed,
    )
    team_bullpen_context_summary = _team_bullpen_context_summary(
        records=output_records,
        inventory_visibility=inventory_visibility,
        context=context,
        failed_closed=failed_closed,
        refusal_fail_closed=refusal_fail_closed,
    )
    bullpen_state = _bullpen_state(
        records=output_records,
        candidate_groups=candidate_groups,
        context=context,
        team_id=team_id,
        team_name=team_name,
        inventory_visibility=inventory_visibility,
    )
    team_context = _team_bullpen_context(
        records=output_records,
        context=context,
        team_id=team_id,
        team_name=team_name,
        team_summary=team_bullpen_context_summary,
    )

    return V2ContextAssembly(
        bullpen_state=bullpen_state,
        team_context=team_context,
        recommendation_context=context,
        candidate_groups=candidate_groups,
        metadata={
            **source_metadata,
            'assembly_phase': V2_CONTEXT_ASSEMBLY_PHASE,
            'source': V2_CONTEXT_ASSEMBLY_SOURCE,
            'input_candidate_count': len(records),
            'assembled_candidate_count': len(output_records),
            'failed_closed': failed_closed,
            'neutral_ordering': 'input_order_preserved_within_groups',
            'neutral_intelligence': neutral_intelligence,
            'inventory_visibility': inventory_visibility,
            'team_bullpen_context_summary': team_bullpen_context_summary,
            'refusal_fail_closed': refusal_fail_closed,
            'trust_metadata': _context_trust_metadata(
                context,
                failed_closed=failed_closed,
            ),
        },
    )


def _candidate_record(candidate):
    malformed_evidence = False
    if isinstance(candidate, RecommendationCandidate):
        payload = candidate.to_dict()
    elif isinstance(candidate, Mapping):
        payload = dict(candidate)
    else:
        payload = {}
        malformed_evidence = True

    availability = _as_mapping(payload.get('availability'))
    metadata = _as_mapping(payload.get('metadata'))
    inputs = _as_mapping(availability.get('inputs') or payload.get('inputs'))

    return {
        'source_payload': payload,
        'malformed_evidence': malformed_evidence,
        'pitcher_id': payload.get('pitcher_id'),
        'pitcher_name': payload.get('pitcher_name'),
        'team_id': payload.get('team_id'),
        'team_name': payload.get('team_name'),
        'availability_status': _availability_status(availability, payload),
        'confidence': _confidence_value(availability, metadata),
        'data_state': _data_state_value(availability, metadata),
        'reasons': tuple(availability.get('reasons') or ()),
        'limitations': tuple(availability.get('limitations') or ()),
        'inputs': inputs,
        'data_through': _first_value(
            metadata.get('data_through'),
            availability.get('data_through'),
            inputs.get('latest_game_date'),
        ),
        'last_successful_sync': _first_value(
            metadata.get('last_successful_sync'),
            availability.get('last_successful_sync'),
        ),
        'latest_sync_status': _first_value(
            metadata.get('latest_sync_status'),
            availability.get('latest_sync_status'),
        ),
        'high_leverage_evidence': bool(metadata.get('high_leverage_evidence')),
    }


def _unsafe_input_errors(records):
    errors = []
    for index, record in enumerate(records):
        for error in v2_governance_errors(record['source_payload']):
            errors.append(f'candidate[{index}]: {error}')
    return errors


def _trust_input_errors(records):
    errors = []
    for index, record in enumerate(records):
        if record.get('malformed_evidence'):
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'malformed_evidence',
                    'message': 'Candidate evidence has an unsupported source shape.',
                }
            )
            continue

        payload = record['source_payload']
        availability = _as_mapping(payload.get('availability'))
        metadata = _as_mapping(payload.get('metadata'))
        if not _has_any_field(availability, metadata, field_names=('confidence',)):
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'confidence',
                    'message': 'Candidate evidence is missing confidence metadata.',
                }
            )
        if not _has_any_field(
            availability,
            metadata,
            field_names=('data_state', 'freshness_state'),
        ):
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'freshness',
                    'message': 'Candidate evidence is missing freshness metadata.',
                }
            )
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'data_state',
                    'message': 'Candidate evidence is missing data-state metadata.',
                }
            )
        if not _has_any_field(
            availability,
            payload,
            field_names=('availability_status', 'status'),
        ):
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'refusal',
                    'message': 'Candidate evidence is missing refusal-state metadata.',
                }
            )
        if 'limitations' not in availability:
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'limitations',
                    'message': 'Candidate evidence is missing limitation metadata.',
                }
            )
        if 'reasons' not in availability:
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'explanations',
                    'message': 'Candidate evidence is missing explanation metadata.',
                }
            )
        if (
            'trust_metadata' in metadata
            and not isinstance(metadata.get('trust_metadata'), Mapping)
        ):
            errors.append(
                {
                    'candidate_index': index,
                    'field': 'unsupported_trust_fields',
                    'message': 'Candidate evidence has unsupported trust metadata.',
                }
            )
    return tuple(errors)


def _recommendation_context(
    *,
    records,
    scope,
    generated_at,
    explicit_refusals=(),
    explicit_explanations=(),
    trust_validation_errors=(),
):
    records = tuple(records)
    trust_validation_errors = tuple(trust_validation_errors or ())
    confidence = _aggregate_confidence(records)
    data_state = _aggregate_data_state(records)
    refusals = list(explicit_refusals)
    explanations = list(explicit_explanations)
    limitations = list(BASE_V2_LIMITATIONS)

    if not records:
        refusals.append(
            V2Refusal(
                refusal_id='missing_context_evidence',
                reason='missing_inputs',
                message='V2 context assembly requires availability evidence.',
                applies_to=scope,
            )
        )
        explanations.append(
            V2Explanation(
                code='no_candidate_evidence',
                message='No candidate availability evidence was provided.',
                applies_to=scope,
            )
        )
        limitations.append(
            V2Limitation(
                limitation_id='missing_availability_evidence',
                message='No availability records were available for V2 assembly.',
                applies_to=scope,
            )
        )
    else:
        explanations.append(
            V2Explanation(
                code='context_assembled_from_existing_evidence',
                message=(
                    'V2 context was assembled from existing availability and '
                    'workload evidence without ranking or selection.'
                ),
                applies_to=scope,
                details={'candidate_count': len(records)},
            )
        )

    trust_error_fields = _trust_error_fields(trust_validation_errors)
    for field_name in trust_error_fields:
        refusal_id = _trust_refusal_id(field_name)
        refusals.append(
            V2Refusal(
                refusal_id=refusal_id,
                reason=refusal_id,
                message=(
                    'V2 context failed closed because required trust metadata '
                    f'is missing or unsupported: {field_name}.'
                ),
                applies_to=scope,
            )
        )
        limitations.append(
            V2Limitation(
                limitation_id=refusal_id,
                message=(
                    'Required V2 trust metadata is missing or unsupported: '
                    f'{field_name}.'
                ),
                applies_to=scope,
            )
        )

    if trust_validation_errors:
        explanations.append(
            V2Explanation(
                code='trust_metadata_validation_failed',
                message='V2 trust metadata validation produced fail-closed metadata.',
                applies_to=scope,
                details={
                    'error_count': len(trust_validation_errors),
                    'missing_or_unsupported_fields': list(trust_error_fields),
                },
            )
        )

    if data_state in {'stale', 'missing', 'incomplete', 'historical', 'unknown'}:
        refusals.append(
            V2Refusal(
                refusal_id=f'{data_state}_data_state',
                reason=f'data_state_{data_state}',
                message=(
                    'V2 context is degraded or refused because source data '
                    f'state is {data_state}.'
                ),
                applies_to=scope,
            )
        )

    for limitation in _source_limitations(records, applies_to=scope):
        limitations.append(limitation)
    for explanation in _source_explanations(records, applies_to=scope):
        explanations.append(explanation)

    return RecommendationContext(
        scope=scope,
        confidence=confidence,
        data_state=data_state,
        source_evidence_state=_source_evidence_state(
            records=records,
            trust_validation_errors=trust_validation_errors,
        ),
        governance_state='failed_closed' if refusals else 'compliant',
        generated_at=generated_at,
        freshness=_freshness_metadata(records, data_state=data_state),
        limitations=tuple(_unique_limitations(limitations)),
        explanations=tuple(_unique_explanations(explanations)),
        refusal_reasons=tuple(_unique_refusals(refusals)),
        trust_validation_errors=tuple(
            _trust_error_messages(trust_validation_errors)
        ),
    )


def _candidate_groups(records, generated_at):
    groups = []
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='availability_status',
            group_id_prefix='availability',
            category_order=AVAILABILITY_STATUS_ORDER,
            category_for_record=lambda record: record['availability_status'] or 'Unknown',
            label_for_category=lambda category: f'Availability: {category}',
            criteria_name='availability_status',
        )
    )
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='eligibility',
            group_id_prefix='eligibility',
            category_order=ELIGIBILITY_CATEGORY_ORDER,
            category_for_record=_eligibility_category,
            label_for_category=lambda category: (
                f'Eligibility: {ELIGIBILITY_CATEGORY_LABELS.get(category, category)}'
            ),
            criteria_name='eligibility_category',
        )
    )
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='refusal',
            group_id_prefix='refusal',
            category_order=REFUSAL_CATEGORY_ORDER,
            category_for_record=_refusal_category,
            label_for_category=lambda category: (
                f'Refusal: {REFUSAL_CATEGORY_LABELS.get(category, category)}'
            ),
            criteria_name='refusal_category',
        )
    )
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='freshness',
            group_id_prefix='freshness',
            category_order=DATA_STATE_ORDER,
            category_for_record=lambda record: record['data_state'] or 'unknown',
            label_for_category=lambda category: f'Freshness: {category}',
            criteria_name='freshness_category',
        )
    )
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='readiness',
            group_id_prefix='readiness',
            category_order=AVAILABILITY_STATUS_ORDER,
            category_for_record=lambda record: record['availability_status'] or 'Unknown',
            label_for_category=lambda category: f'Readiness: {category}',
            criteria_name='readiness_category',
        )
    )
    groups.extend(
        _dimension_candidate_groups(
            records=records,
            generated_at=generated_at,
            dimension='workload',
            group_id_prefix='workload',
            category_order=WORKLOAD_CATEGORY_ORDER,
            category_for_record=_workload_category,
            label_for_category=lambda category: f'Workload: {category}',
            criteria_name='workload_category',
        )
    )
    return tuple(groups)


def _dimension_candidate_groups(
    *,
    records,
    generated_at,
    dimension,
    group_id_prefix,
    category_order,
    category_for_record,
    label_for_category,
    criteria_name,
):
    buckets = OrderedDict()
    record_buckets = OrderedDict()
    for category in category_order:
        buckets[category] = []
        record_buckets[category] = []

    for record in records:
        category = category_for_record(record)
        if category not in buckets:
            buckets[category] = []
            record_buckets[category] = []
        record_buckets[category].append(record)
        buckets[category].append(
            _candidate_group_entry(
                record,
                grouping_dimension=dimension,
                group_category=category,
            )
        )

    groups = []
    for category, candidates in buckets.items():
        if not candidates:
            continue
        context = _recommendation_context(
            records=record_buckets[category],
            scope='candidate_group',
            generated_at=generated_at,
        )
        groups.append(
            CandidateGroup(
                group_id=f'{group_id_prefix}_{_slug(category)}',
                label=label_for_category(category),
                criteria=(f'{criteria_name}={category}',),
                candidates=tuple(candidates),
                neutral_sequence_basis='input_sequence_preserved',
                context=context,
                metadata={
                    'grouping_dimension': dimension,
                    'category': category,
                    'intelligence_phase': V2_NEUTRAL_INTELLIGENCE_PHASE,
                    'ordering_policy': 'input_order_preserved_not_preference',
                    'category_ordering_policy': (
                        'documented_static_taxonomy_not_preference'
                    ),
                },
            )
        )
    return tuple(groups)


def _candidate_group_entry(record, *, grouping_dimension=None, group_category=None):
    entry = {
        'pitcher_id': record['pitcher_id'],
        'pitcher_name': record['pitcher_name'],
        'team_id': record['team_id'],
        'team_name': record['team_name'],
        'availability_status': record['availability_status'],
        'confidence': record['confidence'],
        'data_state': record['data_state'],
        'workload_evidence': {
            'fatigue_value_available': record['inputs'].get('fatigue_score') is not None,
            'recent_pitch_count_available': record['inputs'].get('pitches_yesterday') is not None,
            'latest_game_date_available': record['inputs'].get('latest_game_date') is not None,
        },
        'group_membership': {
            'dimension': grouping_dimension,
            'category': group_category,
            'basis': 'source_evidence_category_match',
        },
        'explanation_support': {
            'availability_status': record['availability_status'],
            'confidence': record['confidence'],
            'data_state': record['data_state'],
            'source_reason_count': len(record['reasons']),
            'source_limitation_count': len(record['limitations']),
        },
    }
    require_v2_governance_safe(entry)
    return entry


def _neutral_intelligence_summary(
    *,
    records,
    candidate_groups,
    context,
    failed_closed,
    refusal_fail_closed=None,
):
    records = tuple(records)
    candidate_groups = tuple(candidate_groups)
    payload = {
        'phase': V2_NEUTRAL_INTELLIGENCE_PHASE,
        'dimensions': list(NEUTRAL_INTELLIGENCE_DIMENSIONS),
        'eligibility_distribution': _eligibility_distribution(records),
        'refusal_distribution': _refusal_distribution(records),
        'freshness_distribution': _freshness_distribution(records),
        'readiness_distribution': _readiness_distribution(records),
        'workload_distribution': _workload_category_distribution(records),
        'grouping_dimension_counts': _ordered_counts(
            Counter(
                group.metadata.get('grouping_dimension', 'unknown')
                for group in candidate_groups
            ),
            GROUPING_DIMENSION_ORDER,
        ),
        'candidate_group_count': len(candidate_groups),
        'failed_closed': bool(failed_closed),
        'refusal_fail_closed': dict(refusal_fail_closed or {}),
        'ordering_policy': 'input_order_preserved_within_groups',
        'trust_metadata': _context_trust_metadata(
            context,
            failed_closed=failed_closed,
        ),
        'ranking_applied': False,
        'selection_made': False,
    }
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


def _inventory_visibility_summary(
    *,
    records,
    candidate_groups,
    context,
    failed_closed,
    refusal_fail_closed=None,
):
    records = tuple(records)
    candidate_groups = tuple(candidate_groups)
    payload = {
        'phase': V2_INVENTORY_VISIBILITY_PHASE,
        'source': 'v2_context_assembly_records',
        'total_inventory_count': len(records),
        'sections': list(INVENTORY_VISIBILITY_SECTIONS),
        'availability_inventory': _availability_inventory(records),
        'eligibility_inventory': _eligibility_inventory(records),
        'refusal_inventory': _refusal_inventory(records, context),
        'freshness_inventory': _freshness_inventory(records, context),
        'readiness_inventory': _readiness_inventory_summary(records),
        'workload_inventory': _workload_inventory(records),
        'evidence_inventory': _evidence_inventory(records, candidate_groups),
        'limitation_inventory': _limitation_inventory(records, context),
        'explanation_inventory': _explanation_inventory(records, context),
        'refusal_fail_closed': dict(refusal_fail_closed or {}),
        'trust_metadata': _inventory_trust_metadata(context, failed_closed),
        'ordering_policy': 'input_order_preserved_within_inventory_categories',
        'ranking_applied': False,
        'selection_made': False,
    }
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


def _availability_inventory(records):
    counts = _readiness_distribution(records)
    return {
        'available_count': counts['Available'],
        'monitor_count': counts['Monitor'],
        'limited_count': counts['Limited'],
        'avoid_count': counts['Avoid'],
        'unavailable_count': counts['Unavailable'],
        'unknown_count': counts['Unknown'],
        'status_counts': counts,
        'members_by_status': _inventory_members_by_category(
            records=records,
            category_order=AVAILABILITY_STATUS_ORDER,
            category_for_record=lambda record: record['availability_status'] or 'Unknown',
            section='availability',
        ),
    }


def _eligibility_inventory(records):
    counts = _eligibility_distribution(records)
    return {
        'category_counts': counts,
        'evidence_complete_count': counts['evidence_complete'],
        'cautionary_evidence_count': counts['cautionary_evidence'],
        'refused_or_degraded_evidence_count': counts['refused_or_degraded_evidence'],
        'unknown_evidence_count': counts['unknown_evidence'],
        'members_by_category': _inventory_members_by_category(
            records=records,
            category_order=ELIGIBILITY_CATEGORY_ORDER,
            category_for_record=_eligibility_category,
            section='eligibility',
        ),
    }


def _refusal_inventory(records, context):
    counts = _refusal_distribution(records)
    refused_count = sum(counts[category] for category in counts if category != 'no_refusal')
    return {
        'category_counts': counts,
        'refused_count': refused_count,
        'no_refusal_count': counts['no_refusal'],
        'context_refusal_reason_count': len(context.refusal_reasons),
        'context_refusal_reasons': [
            refusal.to_dict() for refusal in context.refusal_reasons
        ],
        'members_by_category': _inventory_members_by_category(
            records=records,
            category_order=REFUSAL_CATEGORY_ORDER,
            category_for_record=_refusal_category,
            section='refusal',
        ),
    }


def _freshness_inventory(records, context):
    counts = _freshness_distribution(records)
    return {
        'data_state_counts': counts,
        'fresh_count': counts['fresh'],
        'stale_count': counts['stale'],
        'missing_data_count': (
            counts['missing'] + counts['incomplete'] + counts['unknown']
        ),
        'historical_count': counts['historical'],
        'freshness': context.freshness.to_dict(),
        'members_by_data_state': _inventory_members_by_category(
            records=records,
            category_order=DATA_STATE_ORDER,
            category_for_record=lambda record: record['data_state'] or 'unknown',
            section='freshness',
        ),
    }


def _readiness_inventory_summary(records):
    availability_counts = _readiness_distribution(records)
    confidence_counts = _ordered_counts(
        Counter(record['confidence'] for record in records),
        CONFIDENCE_ORDER,
    )
    return {
        'readiness_distribution': availability_counts,
        'confidence_counts': confidence_counts,
        'available_or_monitor_count': (
            availability_counts['Available'] + availability_counts['Monitor']
        ),
        'limited_or_avoid_count': (
            availability_counts['Limited'] + availability_counts['Avoid']
        ),
        'unavailable_or_unknown_count': (
            availability_counts['Unavailable'] + availability_counts['Unknown']
        ),
        'members_by_readiness': _inventory_members_by_category(
            records=records,
            category_order=AVAILABILITY_STATUS_ORDER,
            category_for_record=lambda record: record['availability_status'] or 'Unknown',
            section='readiness',
        ),
    }


def _workload_inventory(records):
    summary = _workload_summary(records)
    return {
        'category_counts': summary['workload_category_counts'],
        'fatigue_band_counts': summary['fatigue_band_counts'],
        'recent_pitch_usage_counts': summary['recent_pitch_usage_counts'],
        'workload_evidence_available': summary['workload_evidence_available'],
        'fatigue_value_available_count': summary['fatigue_value_available_count'],
        'recent_pitch_count_available_count': summary['recent_pitch_count_available_count'],
        'missing_workload_input_count': summary['missing_workload_input_count'],
        'members_by_workload': _inventory_members_by_category(
            records=records,
            category_order=WORKLOAD_CATEGORY_ORDER,
            category_for_record=_workload_category,
            section='workload',
        ),
    }


def _evidence_inventory(records, candidate_groups):
    group_counts = _ordered_counts(
        Counter(
            group.metadata.get('grouping_dimension', 'unknown')
            for group in candidate_groups
        ),
        GROUPING_DIMENSION_ORDER,
    )
    return {
        'source_record_count': len(records),
        'source_reason_count': sum(len(record['reasons']) for record in records),
        'source_limitation_count': sum(len(record['limitations']) for record in records),
        'candidate_group_count': len(candidate_groups),
        'candidate_group_dimension_counts': group_counts,
        'candidate_group_reference': [
            {
                'group_id': group.group_id,
                'grouping_dimension': group.metadata.get('grouping_dimension'),
                'category': group.metadata.get('category'),
                'candidate_count': len(group.candidates),
            }
            for group in candidate_groups
        ],
        'ordering_policy': 'input_order_preserved_within_inventory_categories',
    }


def _limitation_inventory(records, context):
    source_limitations = _unique_texts(
        limitation
        for record in records
        for limitation in record['limitations']
    )
    return {
        'source_limitation_count': sum(len(record['limitations']) for record in records),
        'source_limitations': source_limitations,
        'context_limitation_count': len(context.limitations),
        'context_limitations': [
            limitation.to_dict() for limitation in context.limitations
        ],
    }


def _explanation_inventory(records, context):
    source_reasons = _unique_texts(
        reason
        for record in records
        for reason in record['reasons']
    )
    return {
        'source_reason_count': sum(len(record['reasons']) for record in records),
        'source_reason_messages': source_reasons,
        'context_explanation_count': len(context.explanations),
        'context_explanations': [
            explanation.to_dict() for explanation in context.explanations
        ],
    }


def _inventory_trust_metadata(context, failed_closed):
    return _context_trust_metadata(context, failed_closed=failed_closed)


def _context_trust_metadata(context, *, failed_closed):
    context_payload = context.to_dict()
    payload = dict(context_payload['trust_metadata'])
    payload['phase'] = V2_TRUST_METADATA_INTEGRATION_PHASE
    payload['failed_closed'] = bool(failed_closed)
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


def _refusal_fail_closed_summary(
    *,
    records,
    context,
    failed_closed,
    unsafe_errors,
    trust_validation_errors,
):
    records = tuple(records)
    trust_validation_errors = tuple(trust_validation_errors or ())
    trust_error_fields = _trust_error_fields(trust_validation_errors)
    critical_failure = _has_critical_refusal_failure(
        records=records,
        unsafe_errors=unsafe_errors,
        trust_error_fields=trust_error_fields,
    )
    reason_codes = _refusal_fail_closed_reason_codes(
        context=context,
        unsafe_errors=unsafe_errors,
        trust_error_fields=trust_error_fields,
    )

    if critical_failure:
        state = 'failed_closed'
    elif context.refusal_reasons:
        state = 'degraded'
    else:
        state = 'passed'

    payload = {
        'phase': V2_REFUSAL_FAIL_CLOSED_PHASE,
        'state': state,
        'critical_failure': critical_failure,
        'safe_partial_output_allowed': state == 'degraded',
        'reason_codes': reason_codes,
        'refusal_reason_count': len(context.refusal_reasons),
        'limitation_count': len(context.limitations),
        'explanation_count': len(context.explanations),
        'trust_validation_error_count': len(trust_validation_errors),
        'unsafe_source_error_count': len(tuple(unsafe_errors or ())),
        'source_evidence_state': context.source_evidence_state,
        'governance_state': context.governance_state,
        'failed_closed': bool(failed_closed),
        'trust_metadata': _context_trust_metadata(
            context,
            failed_closed=failed_closed,
        ),
        'ranking_applied': context.ranking_applied,
        'selection_made': context.selection_made,
    }
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


def _has_critical_refusal_failure(*, records, unsafe_errors, trust_error_fields):
    if tuple(unsafe_errors or ()):
        return True
    if not tuple(records):
        return True
    return bool(set(trust_error_fields) & FAIL_CLOSED_TRUST_ERROR_FIELDS)


def _should_suppress_candidate_output(trust_validation_errors):
    trust_error_fields = set(_trust_error_fields(trust_validation_errors))
    return bool(trust_error_fields & {'malformed_evidence', 'unsupported_trust_fields'})


def _refusal_fail_closed_reason_codes(
    *,
    context,
    unsafe_errors,
    trust_error_fields,
):
    reason_codes = OrderedDict()
    if tuple(unsafe_errors or ()):
        reason_codes['governance_unsafe_source_evidence'] = (
            'governance_unsafe_source_evidence'
        )
    for field_name in trust_error_fields:
        reason_code = _trust_refusal_id(field_name)
        reason_codes[reason_code] = reason_code
    for refusal in context.refusal_reasons:
        reason_codes[refusal.reason] = refusal.reason
    return list(reason_codes.values())


def _inventory_members_by_category(
    *,
    records,
    category_order,
    category_for_record,
    section,
):
    buckets = OrderedDict((category, []) for category in category_order)
    for record in records:
        category = category_for_record(record)
        if category not in buckets:
            buckets[category] = []
        buckets[category].append(
            _inventory_member_entry(record, section=section, category=category)
        )
    return {category: list(members) for category, members in buckets.items()}


def _inventory_member_entry(record, *, section, category):
    entry = {
        'pitcher_id': record['pitcher_id'],
        'pitcher_name': record['pitcher_name'],
        'team_id': record['team_id'],
        'team_name': record['team_name'],
        'availability_status': record['availability_status'],
        'confidence': record['confidence'],
        'data_state': record['data_state'],
        'inventory_membership': {
            'section': section,
            'category': category,
            'basis': 'source_evidence_category_match',
        },
        'evidence': {
            'source_reason_count': len(record['reasons']),
            'source_limitation_count': len(record['limitations']),
            'fatigue_value_available': record['inputs'].get('fatigue_score') is not None,
            'recent_pitch_count_available': record['inputs'].get('pitches_yesterday') is not None,
            'latest_game_date_available': record['inputs'].get('latest_game_date') is not None,
            'high_leverage_evidence': record['high_leverage_evidence'],
        },
    }
    require_v2_governance_safe(entry)
    return entry


def _team_bullpen_context_summary(
    *,
    records,
    inventory_visibility,
    context,
    failed_closed,
    refusal_fail_closed=None,
):
    records = tuple(records)
    inventory_visibility = dict(inventory_visibility or {})
    availability_inventory = _as_mapping(
        inventory_visibility.get('availability_inventory')
    )
    eligibility_inventory = _as_mapping(
        inventory_visibility.get('eligibility_inventory')
    )
    refusal_inventory = _as_mapping(inventory_visibility.get('refusal_inventory'))
    freshness_inventory = _as_mapping(inventory_visibility.get('freshness_inventory'))
    readiness_inventory = _as_mapping(inventory_visibility.get('readiness_inventory'))
    workload_inventory = _as_mapping(inventory_visibility.get('workload_inventory'))
    limitation_inventory = _as_mapping(inventory_visibility.get('limitation_inventory'))
    explanation_inventory = _as_mapping(
        inventory_visibility.get('explanation_inventory')
    )
    trust_metadata = _as_mapping(inventory_visibility.get('trust_metadata'))
    evidence_inventory = _as_mapping(inventory_visibility.get('evidence_inventory'))

    availability_distribution = dict(
        _as_mapping(availability_inventory.get('status_counts'))
    )
    if not availability_distribution:
        availability_distribution = _readiness_distribution(records)
    eligibility_distribution = dict(
        _as_mapping(eligibility_inventory.get('category_counts'))
    )
    if not eligibility_distribution:
        eligibility_distribution = _eligibility_distribution(records)
    refusal_distribution = dict(_as_mapping(refusal_inventory.get('category_counts')))
    if not refusal_distribution:
        refusal_distribution = _refusal_distribution(records)
    freshness_distribution = dict(
        _as_mapping(freshness_inventory.get('data_state_counts'))
    )
    if not freshness_distribution:
        freshness_distribution = _freshness_distribution(records)
    readiness_distribution = dict(
        _as_mapping(readiness_inventory.get('readiness_distribution'))
    )
    if not readiness_distribution:
        readiness_distribution = _readiness_distribution(records)
    workload_distribution = dict(
        _as_mapping(workload_inventory.get('category_counts'))
    )
    if not workload_distribution:
        workload_distribution = _workload_category_distribution(records)

    payload = {
        'phase': V2_TEAM_BULLPEN_CONTEXT_PHASE,
        'source': 'v2_inventory_visibility_and_context_assembly',
        'sections': list(TEAM_BULLPEN_CONTEXT_SECTIONS),
        'team_bullpen_status': _team_bullpen_status(
            records=records,
            availability_distribution=availability_distribution,
            freshness_distribution=freshness_distribution,
            workload_distribution=workload_distribution,
            failed_closed=failed_closed,
        ),
        'total_pitcher_count': len(records),
        'availability_distribution': availability_distribution,
        'eligibility_distribution': eligibility_distribution,
        'refusal_distribution': refusal_distribution,
        'freshness_distribution': freshness_distribution,
        'data_state_distribution': freshness_distribution,
        'readiness_distribution': readiness_distribution,
        'workload_distribution': workload_distribution,
        'readiness_context': {
            'available_or_monitor_count': readiness_inventory.get(
                'available_or_monitor_count',
                readiness_distribution.get('Available', 0)
                + readiness_distribution.get('Monitor', 0),
            ),
            'limited_or_avoid_count': readiness_inventory.get(
                'limited_or_avoid_count',
                readiness_distribution.get('Limited', 0)
                + readiness_distribution.get('Avoid', 0),
            ),
            'unavailable_or_unknown_count': readiness_inventory.get(
                'unavailable_or_unknown_count',
                readiness_distribution.get('Unavailable', 0)
                + readiness_distribution.get('Unknown', 0),
            ),
            'confidence_counts': dict(
                _as_mapping(readiness_inventory.get('confidence_counts'))
            ),
        },
        'workload_context': {
            'workload_evidence_available': bool(
                workload_inventory.get('workload_evidence_available')
            ),
            'fatigue_band_counts': dict(
                _as_mapping(workload_inventory.get('fatigue_band_counts'))
            ),
            'recent_pitch_usage_counts': dict(
                _as_mapping(workload_inventory.get('recent_pitch_usage_counts'))
            ),
            'missing_workload_input_count': int(
                workload_inventory.get('missing_workload_input_count', 0)
            ),
        },
        'leverage_context': _leverage_inventory(records),
        'refusal_context': {
            'refused_count': int(refusal_inventory.get('refused_count', 0)),
            'context_refusal_reason_count': len(context.refusal_reasons),
            'context_refusal_reasons': [
                refusal.to_dict() for refusal in context.refusal_reasons
            ],
        },
        'limitation_summary': dict(limitation_inventory),
        'explanation_summary': dict(explanation_inventory),
        'refusal_fail_closed': dict(refusal_fail_closed or {}),
        'trust_summary': dict(trust_metadata),
        'evidence_summary': dict(evidence_inventory),
        'member_reference': _team_member_reference(records),
        'failed_closed': bool(failed_closed),
        'ordering_policy': 'input_order_preserved_across_team_context_reference',
        'ranking_applied': context.ranking_applied,
        'selection_made': context.selection_made,
    }
    require_v2_governance_safe(payload)
    return payload


def _team_member_reference(records):
    members = []
    for record in records:
        entry = {
            'pitcher_id': record['pitcher_id'],
            'pitcher_name': record['pitcher_name'],
            'team_id': record['team_id'],
            'team_name': record['team_name'],
            'availability_status': record['availability_status'],
            'eligibility_category': _eligibility_category(record),
            'refusal_category': _refusal_category(record),
            'freshness_state': record['data_state'],
            'readiness_category': record['availability_status'] or 'Unknown',
            'workload_category': _workload_category(record),
            'context_membership': {
                'basis': 'source_input_sequence',
                'sequence_policy': 'input_order_preserved_not_preference',
            },
        }
        require_v2_governance_safe(entry)
        members.append(entry)
    return members


def _team_bullpen_status(
    *,
    records,
    availability_distribution,
    freshness_distribution,
    workload_distribution,
    failed_closed,
):
    if not records:
        return 'missing_evidence'
    if failed_closed:
        return 'degraded_evidence'
    avoid_or_unavailable = (
        int(availability_distribution.get('Avoid', 0))
        + int(availability_distribution.get('Unavailable', 0))
    )
    monitor_or_limited = (
        int(availability_distribution.get('Monitor', 0))
        + int(availability_distribution.get('Limited', 0))
    )
    stale_or_missing = (
        int(freshness_distribution.get('stale', 0))
        + int(freshness_distribution.get('missing', 0))
        + int(freshness_distribution.get('incomplete', 0))
        + int(freshness_distribution.get('unknown', 0))
    )
    if avoid_or_unavailable or int(workload_distribution.get('elevated', 0)):
        return 'stress_visible'
    if monitor_or_limited or stale_or_missing:
        return 'monitor'
    return 'stable'


def _bullpen_state(
    records,
    candidate_groups,
    context,
    team_id,
    team_name,
    inventory_visibility,
):
    availability_counts = Counter(record['availability_status'] or 'Unknown' for record in records)
    confidence_counts = Counter(record['confidence'] for record in records)
    data_state_counts = Counter(record['data_state'] for record in records)
    status = _bullpen_status(availability_counts, data_state_counts, len(records))

    return BullpenState(
        team_id=team_id,
        team_name=team_name,
        bullpen_status=status,
        inventory={
            'total_pitchers': len(records),
            'availability_status_counts': _ordered_counts(availability_counts, AVAILABILITY_STATUS_ORDER),
            'candidate_group_count': len(candidate_groups),
            'neutral_intelligence_dimensions': list(NEUTRAL_INTELLIGENCE_DIMENSIONS),
            'visibility_summary': inventory_visibility,
        },
        readiness={
            'confidence_counts': _ordered_counts(confidence_counts, CONFIDENCE_ORDER),
            'data_state_counts': _ordered_counts(data_state_counts, DATA_STATE_ORDER),
            'eligibility_category_counts': _eligibility_distribution(records),
            'refusal_category_counts': _refusal_distribution(records),
            'freshness_category_counts': _freshness_distribution(records),
            'readiness_basis': 'availability_confidence_and_data_state',
        },
        workload=_workload_summary(records),
        stress=_stress_summary(records, availability_counts, data_state_counts),
        candidate_groups=candidate_groups,
        context=context,
    )


def _team_bullpen_context(records, context, team_id, team_name, team_summary):
    availability_counts = Counter(record['availability_status'] or 'Unknown' for record in records)
    data_state_counts = Counter(record['data_state'] for record in records)
    confidence_counts = Counter(record['confidence'] for record in records)

    return TeamBullpenContext(
        team_id=team_id,
        team_name=team_name,
        leverage_inventory=_leverage_inventory(records),
        workload_distribution=_workload_distribution(records),
        readiness_distribution={
            'availability_status_counts': _ordered_counts(availability_counts, AVAILABILITY_STATUS_ORDER),
            'data_state_counts': _ordered_counts(data_state_counts, DATA_STATE_ORDER),
            'confidence_counts': _ordered_counts(confidence_counts, CONFIDENCE_ORDER),
            'eligibility_category_counts': _eligibility_distribution(records),
            'refusal_category_counts': _refusal_distribution(records),
            'freshness_category_counts': _freshness_distribution(records),
        },
        stress_indicators=_stress_summary(records, availability_counts, data_state_counts),
        team_summary=team_summary,
        context=context,
    )


def _workload_summary(records):
    inputs = [record['inputs'] for record in records]
    return {
        'workload_evidence_available': any(inputs),
        'fatigue_value_available_count': sum(
            1 for item in inputs if item.get('fatigue_score') is not None
        ),
        'recent_pitch_count_available_count': sum(
            1 for item in inputs if item.get('pitches_yesterday') is not None
        ),
        'missing_workload_input_count': sum(1 for item in inputs if not item),
        'fatigue_band_counts': _fatigue_band_counts(inputs),
        'recent_pitch_usage_counts': _recent_pitch_usage_counts(inputs),
        'workload_category_counts': _workload_category_distribution(records),
    }


def _workload_distribution(records):
    summary = _workload_summary(records)
    return {
        'fatigue_band_counts': summary['fatigue_band_counts'],
        'recent_pitch_usage_counts': summary['recent_pitch_usage_counts'],
        'missing_workload_input_count': summary['missing_workload_input_count'],
        'workload_category_counts': summary['workload_category_counts'],
    }


def _stress_summary(records, availability_counts, data_state_counts):
    avoid_or_unavailable = (
        availability_counts.get('Avoid', 0) + availability_counts.get('Unavailable', 0)
    )
    cautionary = (
        availability_counts.get('Monitor', 0) + availability_counts.get('Limited', 0)
    )
    stale_or_missing = (
        data_state_counts.get('stale', 0)
        + data_state_counts.get('missing', 0)
        + data_state_counts.get('incomplete', 0)
    )
    elevated_workload = sum(
        1 for record in records
        if _fatigue_band(record['inputs'].get('fatigue_score')) == 'elevated'
        or _recent_pitch_usage(record['inputs'].get('pitches_yesterday')) == 'elevated'
    )
    if not records:
        stress_level = 'unknown'
    elif avoid_or_unavailable or elevated_workload:
        stress_level = 'elevated'
    elif cautionary or stale_or_missing:
        stress_level = 'monitor'
    else:
        stress_level = 'normal'

    return {
        'stress_level': stress_level,
        'avoid_or_unavailable_count': avoid_or_unavailable,
        'cautionary_status_count': cautionary,
        'stale_missing_or_incomplete_count': stale_or_missing,
        'elevated_workload_count': elevated_workload,
        'stress_basis': 'availability_status_data_state_and_workload_inputs',
    }


def _leverage_inventory(records):
    available_high_leverage = sum(
        1 for record in records
        if record['high_leverage_evidence']
        and record['availability_status'] in {'Available', 'Monitor'}
    )
    return {
        'source_evidence_available': any(record['high_leverage_evidence'] for record in records),
        'available_high_leverage_evidence_count': available_high_leverage,
        'leverage_evidence_limitations': (
            []
            if any(record['high_leverage_evidence'] for record in records)
            else ['No leverage evidence was supplied to V2 context assembly.']
        ),
    }


def _eligibility_distribution(records):
    return _ordered_counts(
        Counter(_eligibility_category(record) for record in records),
        ELIGIBILITY_CATEGORY_ORDER,
    )


def _refusal_distribution(records):
    return _ordered_counts(
        Counter(_refusal_category(record) for record in records),
        REFUSAL_CATEGORY_ORDER,
    )


def _freshness_distribution(records):
    return _ordered_counts(
        Counter(record['data_state'] or 'unknown' for record in records),
        DATA_STATE_ORDER,
    )


def _readiness_distribution(records):
    return _ordered_counts(
        Counter(record['availability_status'] or 'Unknown' for record in records),
        AVAILABILITY_STATUS_ORDER,
    )


def _workload_category_distribution(records):
    return _ordered_counts(
        Counter(_workload_category(record) for record in records),
        WORKLOAD_CATEGORY_ORDER,
    )


def _eligibility_category(record):
    status = record['availability_status'] or 'Unknown'
    confidence = str(record['confidence'] or 'unknown').lower()
    data_state = str(record['data_state'] or 'unknown').lower()

    if status in {'Unavailable', 'Unknown'} or data_state in {'missing', 'unknown'}:
        return 'refused_or_degraded_evidence'
    if data_state in {'stale', 'incomplete', 'historical'} or confidence in {'low', 'unknown'}:
        return 'refused_or_degraded_evidence'
    if status in {'Monitor', 'Limited', 'Avoid'} or confidence == 'medium':
        return 'cautionary_evidence'
    if status == 'Available' and data_state == 'fresh' and confidence == 'high':
        return 'evidence_complete'
    return 'unknown_evidence'


def _refusal_category(record):
    status = record['availability_status'] or 'Unknown'
    confidence = str(record['confidence'] or 'unknown').lower()
    data_state = str(record['data_state'] or 'unknown').lower()

    if status == 'Unknown':
        return 'missing_evidence_refusal'
    if data_state in {'missing', 'unknown'}:
        return 'missing_evidence_refusal'
    if data_state in {'stale', 'incomplete', 'historical'}:
        return 'freshness_refusal'
    if status == 'Unavailable':
        return 'availability_refusal'
    if confidence in {'low', 'unknown'}:
        return 'confidence_refusal'
    return 'no_refusal'


def _workload_category(record):
    fatigue_band = _fatigue_band(record['inputs'].get('fatigue_score'))
    recent_usage = _recent_pitch_usage(record['inputs'].get('pitches_yesterday'))
    bands = {fatigue_band, recent_usage}
    if 'elevated' in bands:
        return 'elevated'
    if 'moderate' in bands:
        return 'moderate'
    if bands == {'unknown'}:
        return 'unknown'
    return 'low'


def _aggregate_confidence(records):
    if not records:
        return RecommendationConfidence.UNKNOWN
    values = {_confidence_value_from_text(record['confidence']) for record in records}
    if RecommendationConfidence.LOW in values or RecommendationConfidence.UNKNOWN in values:
        return RecommendationConfidence.LOW
    if RecommendationConfidence.MEDIUM in values:
        return RecommendationConfidence.MEDIUM
    return RecommendationConfidence.HIGH


def _aggregate_data_state(records):
    if not records:
        return 'missing'
    states = {str(record['data_state'] or 'unknown').lower() for record in records}
    for state in ('missing', 'stale', 'incomplete', 'historical', 'unknown'):
        if state in states:
            return state
    if states == {'fresh'}:
        return 'fresh'
    return sorted(states)[0]


def _freshness_metadata(records, data_state):
    return V2FreshnessMetadata(
        state=_freshness_state_from_data_state(data_state),
        data_through=_max_text(record['data_through'] for record in records),
        last_successful_sync=_max_text(
            record['last_successful_sync'] for record in records
        ),
        latest_sync_status=_latest_sync_status(records),
        stale_warning=(
            'Some source evidence is stale.'
            if data_state in {'stale', 'historical'}
            else None
        ),
        missing_data_warning=(
            'Some source evidence is missing or incomplete.'
            if data_state in {'missing', 'incomplete', 'unknown'}
            else None
        ),
        limitations=tuple(
            reason for reason in (
                f'data_state_{data_state}'
                if data_state != 'fresh' else None,
            )
            if reason
        ),
    )


def _source_limitations(records, applies_to):
    limitations = OrderedDict()
    for record in records:
        for index, limitation in enumerate(record['limitations']):
            text = str(limitation)
            key = _slug(text) or f'source_limitation_{index}'
            limitations[key] = V2Limitation(
                limitation_id=f'source_{key}',
                message=text,
                applies_to=applies_to,
            )
    return tuple(limitations.values())


def _source_explanations(records, applies_to):
    explanations = OrderedDict()
    for record in records:
        for index, reason in enumerate(record['reasons']):
            text = str(reason)
            key = _slug(text) or f'source_reason_{index}'
            explanations[key] = V2Explanation(
                code=f'source_{key}',
                message=text,
                applies_to=applies_to,
            )
    return tuple(explanations.values())


def _availability_status(availability, payload):
    value = (
        availability.get('availability_status')
        or availability.get('status')
        or payload.get('availability_status')
        or 'Unknown'
    )
    return str(value)


def _confidence_value(availability, metadata):
    value = availability.get('confidence') or metadata.get('confidence') or 'unknown'
    return str(value).lower()


def _data_state_value(availability, metadata):
    value = (
        metadata.get('freshness_state')
        or metadata.get('data_state')
        or availability.get('freshness_state')
        or availability.get('data_state')
        or 'unknown'
    )
    if str(value).lower() == 'stable':
        return 'fresh'
    return str(value).lower()


def _confidence_value_from_text(value):
    normalized = str(value or 'unknown').lower()
    for member in RecommendationConfidence:
        if normalized in {member.value.lower(), member.name.lower()}:
            return member
    return RecommendationConfidence.UNKNOWN


def _freshness_state_from_data_state(data_state):
    normalized = str(data_state or 'unknown').lower()
    for member in RecommendationFreshnessState:
        if normalized in {member.value.lower(), member.name.lower()}:
            return member
    return RecommendationFreshnessState.UNKNOWN


def _bullpen_status(availability_counts, data_state_counts, total):
    if total == 0:
        return 'unknown'
    if data_state_counts.get('missing', 0) == total:
        return 'refused'
    if availability_counts.get('Unavailable', 0) or availability_counts.get('Avoid', 0):
        return 'stress_visible'
    if availability_counts.get('Monitor', 0) or availability_counts.get('Limited', 0):
        return 'monitor'
    return 'stable'


def _fatigue_band_counts(inputs):
    return _ordered_counts(
        Counter(_fatigue_band(item.get('fatigue_score')) for item in inputs),
        ('low', 'moderate', 'elevated', 'unknown'),
    )


def _recent_pitch_usage_counts(inputs):
    return _ordered_counts(
        Counter(_recent_pitch_usage(item.get('pitches_yesterday')) for item in inputs),
        ('low', 'moderate', 'elevated', 'unknown'),
    )


def _fatigue_band(value):
    if value is None:
        return 'unknown'
    numeric = _to_float(value)
    if numeric is None:
        return 'unknown'
    if numeric >= 60:
        return 'elevated'
    if numeric >= 40:
        return 'moderate'
    return 'low'


def _recent_pitch_usage(value):
    if value is None:
        return 'unknown'
    numeric = _to_float(value)
    if numeric is None:
        return 'unknown'
    if numeric >= 35:
        return 'elevated'
    if numeric >= 15:
        return 'moderate'
    return 'low'


def _ordered_counts(counter, order):
    counts = {key: int(counter.get(key, 0)) for key in order}
    for key in sorted(counter):
        if key not in counts:
            counts[key] = int(counter[key])
    return counts


def _unique_limitations(limitations):
    by_id = OrderedDict()
    for limitation in limitations:
        by_id[limitation.limitation_id] = limitation
    return tuple(by_id.values())


def _unique_explanations(explanations):
    by_code = OrderedDict()
    for explanation in explanations:
        by_code[explanation.code] = explanation
    return tuple(by_code.values())


def _unique_refusals(refusals):
    by_id = OrderedDict()
    for refusal in refusals:
        by_id[refusal.refusal_id] = refusal
    return tuple(by_id.values())


def _unique_texts(values):
    by_text = OrderedDict()
    for value in values:
        text = str(value)
        by_text[text] = text
    return list(by_text.values())


def _latest_sync_status(records):
    statuses = [record['latest_sync_status'] for record in records if record['latest_sync_status']]
    if any(str(status).lower() == 'failed' for status in statuses):
        return 'failed'
    return statuses[-1] if statuses else None


def _max_text(values):
    normalized = [str(value) for value in values if value]
    return max(normalized) if normalized else None


def _first_value(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _has_any_field(*mappings, field_names):
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        for field_name in field_names:
            if mapping.get(field_name) is not None:
                return True
    return False


def _trust_error_fields(trust_validation_errors):
    fields = OrderedDict()
    for error in trust_validation_errors:
        field_name = str(error.get('field') or 'trust_metadata')
        fields[field_name] = field_name
    return tuple(fields.values())


def _trust_refusal_id(field_name):
    if field_name in {'malformed_evidence', 'unsupported_trust_fields'}:
        return field_name
    return f'missing_{field_name}_metadata'


def _trust_error_messages(trust_validation_errors):
    messages = []
    for error in trust_validation_errors:
        messages.append(
            (
                f"candidate[{error.get('candidate_index')}]."
                f"{error.get('field')}: {error.get('message')}"
            )
        )
    return tuple(messages)


def _source_evidence_state(*, records, trust_validation_errors):
    if not records:
        return 'missing'
    trust_error_fields = set(_trust_error_fields(trust_validation_errors))
    if 'malformed_evidence' in trust_error_fields:
        return 'malformed'
    if 'unsupported_trust_fields' in trust_error_fields:
        return 'unsupported'
    if trust_validation_errors:
        return 'trust_metadata_incomplete'
    return 'represented'


def _as_mapping(value):
    return value if isinstance(value, Mapping) else {}


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _slug(value):
    text = str(value or '').strip().lower()
    chars = [character if character.isalnum() else '_' for character in text]
    return '_'.join(part for part in ''.join(chars).split('_') if part)


__all__ = [
    'V2_CONTEXT_ASSEMBLY_PHASE',
    'V2_CONTEXT_ASSEMBLY_SOURCE',
    'V2_NEUTRAL_INTELLIGENCE_PHASE',
    'V2_INVENTORY_VISIBILITY_PHASE',
    'V2_TEAM_BULLPEN_CONTEXT_PHASE',
    'V2_TRUST_METADATA_INTEGRATION_PHASE',
    'V2_REFUSAL_FAIL_CLOSED_PHASE',
    'NEUTRAL_INTELLIGENCE_DIMENSIONS',
    'INVENTORY_VISIBILITY_SECTIONS',
    'TEAM_BULLPEN_CONTEXT_SECTIONS',
    'V2ContextAssembly',
    'assemble_v2_context',
]
