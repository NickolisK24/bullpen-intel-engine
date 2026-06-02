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
    v2_governance_errors,
)


V2_CONTEXT_ASSEMBLY_PHASE = 'phase_2_backend_context_assembly'
V2_CONTEXT_ASSEMBLY_SOURCE = 'existing_availability_workload_evidence'

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
        payload = {
            'metadata': dict(self.metadata),
            'recommendation_context': self.recommendation_context.to_dict(),
            'bullpen_state': self.bullpen_state.to_dict(),
            'team_context': self.team_context.to_dict(),
            'candidate_groups': [
                group.to_dict() for group in self.candidate_groups
            ],
            'ranking_applied': False,
            'selection_made': False,
        }
        require_v2_governance_safe(payload)
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
                        'contains ranking or selection fields.'
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
        bullpen_state = BullpenState(
            team_id=team_id,
            team_name=team_name,
            bullpen_status='refused',
            inventory={'total_pitchers': 0, 'availability_status_counts': _ordered_counts(Counter(), AVAILABILITY_STATUS_ORDER)},
            readiness={'data_state_counts': _ordered_counts(Counter(), DATA_STATE_ORDER)},
            workload={'workload_evidence_available': False},
            stress={'stress_level': 'unknown'},
            candidate_groups=(),
            context=context,
        )
        team_context = TeamBullpenContext(
            team_id=team_id,
            team_name=team_name,
            leverage_inventory={'source_evidence_available': False},
            workload_distribution={'workload_evidence_available': False},
            readiness_distribution={'data_state_counts': _ordered_counts(Counter(), DATA_STATE_ORDER)},
            stress_indicators={'stress_level': 'unknown'},
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
            },
        )

    context = _recommendation_context(
        records=records,
        scope='bullpen_state',
        generated_at=generated_at,
    )
    candidate_groups = _candidate_groups(records, generated_at=generated_at)
    bullpen_state = _bullpen_state(
        records=records,
        candidate_groups=candidate_groups,
        context=context,
        team_id=team_id,
        team_name=team_name,
    )
    team_context = _team_bullpen_context(
        records=records,
        context=context,
        team_id=team_id,
        team_name=team_name,
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
            'assembled_candidate_count': len(records),
            'failed_closed': bool(context.refusal_reasons),
            'neutral_ordering': 'input_order_preserved_within_groups',
        },
    )


def _candidate_record(candidate):
    if isinstance(candidate, RecommendationCandidate):
        payload = candidate.to_dict()
    elif isinstance(candidate, Mapping):
        payload = dict(candidate)
    else:
        payload = {}

    availability = _as_mapping(payload.get('availability'))
    metadata = _as_mapping(payload.get('metadata'))
    inputs = _as_mapping(availability.get('inputs') or payload.get('inputs'))

    return {
        'source_payload': payload,
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


def _recommendation_context(
    *,
    records,
    scope,
    generated_at,
    explicit_refusals=(),
    explicit_explanations=(),
):
    records = tuple(records)
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
        generated_at=generated_at,
        freshness=_freshness_metadata(records, data_state=data_state),
        limitations=tuple(_unique_limitations(limitations)),
        explanations=tuple(_unique_explanations(explanations)),
        refusal_reasons=tuple(_unique_refusals(refusals)),
    )


def _candidate_groups(records, generated_at):
    buckets = OrderedDict()
    for status in AVAILABILITY_STATUS_ORDER:
        buckets[status] = []

    for record in records:
        status = record['availability_status'] or 'Unknown'
        if status not in buckets:
            buckets[status] = []
        buckets[status].append(_candidate_group_entry(record))

    groups = []
    for status, candidates in buckets.items():
        if not candidates:
            continue
        context = _recommendation_context(
            records=[
                record for record in records
                if (record['availability_status'] or 'Unknown') == status
            ],
            scope='candidate_group',
            generated_at=generated_at,
        )
        groups.append(
            CandidateGroup(
                group_id=f'availability_{_slug(status)}',
                label=f'Availability: {status}',
                criteria=(f'availability_status={status}',),
                candidates=tuple(candidates),
                neutral_sequence_basis='input_sequence_preserved',
                context=context,
                metadata={
                    'grouping_dimension': 'availability_status',
                    'ordering_policy': 'input_order_preserved_not_preference',
                },
            )
        )
    return tuple(groups)


def _candidate_group_entry(record):
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
    }
    require_v2_governance_safe(entry)
    return entry


def _bullpen_state(records, candidate_groups, context, team_id, team_name):
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
        },
        readiness={
            'confidence_counts': _ordered_counts(confidence_counts, CONFIDENCE_ORDER),
            'data_state_counts': _ordered_counts(data_state_counts, DATA_STATE_ORDER),
            'readiness_basis': 'availability_confidence_and_data_state',
        },
        workload=_workload_summary(records),
        stress=_stress_summary(records, availability_counts, data_state_counts),
        candidate_groups=candidate_groups,
        context=context,
    )


def _team_bullpen_context(records, context, team_id, team_name):
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
        },
        stress_indicators=_stress_summary(records, availability_counts, data_state_counts),
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
    }


def _workload_distribution(records):
    summary = _workload_summary(records)
    return {
        'fatigue_band_counts': summary['fatigue_band_counts'],
        'recent_pitch_usage_counts': summary['recent_pitch_usage_counts'],
        'missing_workload_input_count': summary['missing_workload_input_count'],
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
    'V2ContextAssembly',
    'assemble_v2_context',
]
