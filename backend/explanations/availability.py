"""Availability Engine adapter for V4 Evidence and Explanation objects.

This module builds V4 explanations from existing Availability Engine output.
It does not classify availability, change thresholds, mutate API response
payloads, or integrate with frontend surfaces.
"""

from __future__ import annotations

from typing import Any, Mapping

from explanations.builders import (
    build_evidence_item,
    build_explanation,
    build_limitation,
    build_numeric_evidence,
)
from explanations.contracts import V4Explanation


AVAILABILITY_EXPLANATION_SOURCE = 'availability_engine_v1'
AVAILABILITY_EXPLANATION_CONTRACT = 'availability_engine_v1'
AVAILABILITY_EXPLANATION_CERTIFICATION_STATUS = 'complete'

SUPPORTED_AVAILABILITY_STATUSES = frozenset(
    {
        'Available',
        'Monitor',
        'Limited',
        'Avoid',
        'Unavailable',
    }
)

_CONFIDENCE_TO_TRUST = {
    'high': 'trusted',
    'medium': 'limited',
    'low': 'limited',
    'unknown': 'unknown',
}

_DATA_STATE_TO_FRESHNESS = {
    'fresh': 'current',
    'stale': 'stale',
    'missing': 'missing',
    'incomplete': 'incomplete',
    'unknown': 'unknown',
}

_NUMERIC_INPUT_EVIDENCE = (
    ('fatigue_score', 'Recent workload index', 'index'),
    ('pitches_yesterday', 'Pitches yesterday', 'pitches'),
    ('pitches_last_3_days', 'Pitches in 3 days', 'pitches'),
    ('pitches_last_5_days', 'Pitches in 5 days', 'pitches'),
    ('appearances_last_3_days', 'Appearances in 3 days', 'appearances'),
    ('appearances_last_5_days', 'Appearances in 5 days', 'appearances'),
    ('days_rest', 'Days of rest', 'days'),
)

_CONTEXT_INPUT_EVIDENCE = (
    ('back_to_back', 'Back-to-back appearances'),
    ('three_in_four', 'Three appearances in four days'),
    ('four_in_five', 'Four appearances in five days'),
)


def _required_mapping(value: Mapping[str, Any] | None, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f'{field_name} must be an availability mapping.')
    return value


def _required_subject_id(subject_id: str | int | None) -> str:
    resolved = str(subject_id).strip() if subject_id is not None else ''
    if not resolved:
        raise ValueError('subject_id is required for availability explanation.')
    return resolved


def _availability_status(availability: Mapping[str, Any]) -> str:
    status = availability.get('availability_status')
    if status not in SUPPORTED_AVAILABILITY_STATUSES:
        raise ValueError('availability_status uses unsupported vocabulary.')
    return str(status)


def _confidence_level(availability: Mapping[str, Any]) -> str:
    confidence = availability.get('confidence') or 'unknown'
    if confidence not in _CONFIDENCE_TO_TRUST:
        raise ValueError('availability confidence uses unsupported vocabulary.')
    return str(confidence)


def _data_state(availability: Mapping[str, Any]) -> str:
    data_state = availability.get('data_state') or 'unknown'
    if data_state not in _DATA_STATE_TO_FRESHNESS:
        raise ValueError('availability data_state uses unsupported vocabulary.')
    return str(data_state)


def _inputs(availability: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_inputs = availability.get('inputs') or {}
    if not isinstance(raw_inputs, Mapping):
        raise ValueError('availability inputs must be a mapping when provided.')
    return raw_inputs


def _freshness_reference(data_state: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    freshness_status = _DATA_STATE_TO_FRESHNESS[data_state]
    latest_game_date = inputs.get('latest_game_date')
    reference_date = inputs.get('reference_date')

    summary = 'The stored workload data is current enough for this pitcher note.'
    freshness_failure = None
    if freshness_status == 'stale':
        summary = 'The read is limited because the stored workload data is stale.'
        freshness_failure = 'stale_workload_data'
    elif freshness_status == 'missing':
        summary = 'The read is limited because BaseballOS does not have recent workload data for him.'
        freshness_failure = 'missing_workload_data'
    elif freshness_status == 'incomplete':
        summary = 'The read is limited because some recent workload detail is incomplete.'
        freshness_failure = 'incomplete_workload_data'
    elif freshness_status == 'unknown':
        summary = 'The read is limited because workload freshness is unknown.'
        freshness_failure = 'unknown_freshness_state'

    return {
        'status': freshness_status,
        'data_through': latest_game_date,
        'last_sync_at': None,
        'source_updated_at': reference_date,
        'freshness_failure': freshness_failure,
        'summary': summary,
    }


def _trust_status(confidence: str) -> str:
    return _CONFIDENCE_TO_TRUST[confidence]


def _trust_reference(confidence: str, data_state: str) -> dict[str, Any]:
    trust_status = _trust_status(confidence)
    trust_failure = None
    if trust_status == 'limited':
        trust_failure = f'{data_state}_availability_evidence'
    elif trust_status == 'unknown':
        trust_failure = 'unknown_availability_evidence'

    return {
        'status': trust_status,
        'source': AVAILABILITY_EXPLANATION_SOURCE,
        'contract': AVAILABILITY_EXPLANATION_CONTRACT,
        'certification_status': AVAILABILITY_EXPLANATION_CERTIFICATION_STATUS,
        'trust_failure': trust_failure,
        'summary': _trust_summary(trust_status, data_state),
    }


def _trust_summary(trust_status: str, data_state: str) -> str:
    if trust_status == 'trusted':
        return 'The public workload record is strong enough for this note.'
    if data_state == 'stale':
        return 'BaseballOS is keeping this note limited because the stored workload data is stale.'
    if data_state == 'missing':
        return 'BaseballOS is keeping this note limited because recent workload data is missing.'
    if data_state == 'incomplete':
        return 'BaseballOS is keeping this note limited because recent workload detail is incomplete.'
    return 'BaseballOS is keeping this note limited to the public workload record.'


def _reason_codes(
    *,
    status: str,
    data_state: str,
    reasons: tuple[str, ...],
    confidence: str,
) -> tuple[str, ...]:
    codes: list[str] = []

    if status == 'Monitor':
        codes.append('AVAILABILITY_MONITOR_THRESHOLD_MET')
    if reasons and data_state != 'missing':
        codes.append('WORKLOAD_RECENT_USAGE_ELEVATED')
    if data_state == 'stale':
        codes.append('FRESHNESS_STALE_SOURCE')
    if data_state == 'incomplete':
        codes.append('COVERAGE_PARTIAL')
    if data_state == 'missing' or confidence in {'medium', 'low'}:
        codes.append('TRUST_LIMITED')

    deduped: list[str] = []
    for code in codes:
        if code not in deduped:
            deduped.append(code)
    return tuple(deduped)


def _limitation_type_for(text: str, data_state: str) -> str:
    normalized = text.lower()
    if 'stale' in normalized or data_state == 'stale':
        return 'stale_data'
    if 'missing' in normalized or data_state == 'missing':
        return 'missing_data'
    if 'incomplete' in normalized or data_state == 'incomplete':
        return 'partial_coverage'
    if 'confidence' in normalized:
        return 'limited_confidence'
    return 'insufficient_context'


def _limitation_severity(limitation_type: str) -> str:
    if limitation_type in {'missing_data', 'stale_data'}:
        return 'degrades_confidence'
    if limitation_type in {'partial_coverage', 'limited_confidence'}:
        return 'limits_confidence'
    return 'informational'


def _limitations(
    availability: Mapping[str, Any],
    *,
    data_state: str,
    confidence: str,
) -> tuple[dict[str, Any], ...]:
    raw_limitations = availability.get('limitations') or ()
    if not isinstance(raw_limitations, (list, tuple)):
        raise ValueError('availability limitations must be a sequence when provided.')

    limitations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_limitation(limitation_type: str, summary: str) -> None:
        key = (limitation_type, summary)
        if key in seen:
            return
        seen.add(key)
        limitation = build_limitation(
            limitation_type=limitation_type,
            severity=_limitation_severity(limitation_type),
            summary=summary,
            affected_scopes=('availability_state',),
        ).to_dict()
        limitations.append(limitation)

    for raw_limitation in raw_limitations:
        summary = str(raw_limitation).strip()
        if not summary:
            continue
        limitation_type = _limitation_type_for(summary, data_state)
        add_limitation(limitation_type, summary)

    if data_state == 'missing':
        add_limitation('missing_data', 'Stored workload data is missing for this pitcher.')
    if data_state == 'stale':
        add_limitation('stale_data', 'Stored workload data is stale for this pitcher.')
    if data_state == 'incomplete':
        add_limitation('partial_coverage', 'Some recent workload detail is incomplete for this pitcher.')
    if confidence in {'medium', 'low', 'unknown'}:
        add_limitation(
            'limited_confidence',
            'BaseballOS is keeping this note limited to the public workload evidence.',
        )

    return tuple(limitations)


def _base_evidence(
    *,
    status: str,
    confidence: str,
    data_state: str,
    freshness: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    return [
        build_evidence_item(
            evidence_type='availability_status',
            label='Availability status',
            value=status,
            unit='status',
            source=AVAILABILITY_EXPLANATION_SOURCE,
            freshness=freshness,
            trust_status=trust_status,
            impact='explains_availability_state',
        ).to_dict(),
        build_evidence_item(
            evidence_type='availability_confidence',
            label='Availability confidence',
            value=confidence,
            unit='level',
            source=AVAILABILITY_EXPLANATION_SOURCE,
            freshness=freshness,
            trust_status=trust_status,
            impact='explains_confidence_boundary',
        ).to_dict(),
        build_evidence_item(
            evidence_type='availability_data_state',
            label='Availability data state',
            value=data_state,
            unit='state',
            source=AVAILABILITY_EXPLANATION_SOURCE,
            freshness=freshness,
            trust_status=trust_status,
            impact='explains_freshness_boundary',
        ).to_dict(),
    ]


def _workload_evidence(
    *,
    inputs: Mapping[str, Any],
    data_state: str,
    freshness: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    if data_state == 'missing':
        return []

    evidence: list[dict[str, Any]] = []
    for key, label, unit in _NUMERIC_INPUT_EVIDENCE:
        if key not in inputs:
            continue
        value = inputs.get(key)
        if value is None:
            continue
        evidence.append(
            build_numeric_evidence(
                evidence_type=f'availability_{key}',
                label=label,
                value=value,
                unit=unit,
                source=AVAILABILITY_EXPLANATION_SOURCE,
                freshness=freshness,
                trust_status=trust_status,
                impact='explains_availability_state',
            ).to_dict()
        )

    for key, label in _CONTEXT_INPUT_EVIDENCE:
        if inputs.get(key) is not True:
            continue
        evidence.append(
            build_evidence_item(
                evidence_type=f'availability_{key}',
                label=label,
                value=True,
                unit='flag',
                source=AVAILABILITY_EXPLANATION_SOURCE,
                freshness=freshness,
                trust_status=trust_status,
                impact='explains_availability_state',
            ).to_dict()
        )

    return evidence


def build_availability_explanation(
    availability: Mapping[str, Any],
    *,
    subject_id: str | int | None,
    generated_at: str | None = None,
) -> V4Explanation:
    """Build a deterministic V4 explanation from Availability Engine output."""

    availability = _required_mapping(availability, 'availability')
    resolved_subject_id = _required_subject_id(subject_id)
    status = _availability_status(availability)
    confidence = _confidence_level(availability)
    data_state = _data_state(availability)
    inputs = _inputs(availability)
    reasons = tuple(str(reason) for reason in availability.get('reasons') or ())
    freshness = _freshness_reference(data_state, inputs)
    trust_status = _trust_status(confidence)
    trust = _trust_reference(confidence, data_state)
    evidence = [
        *_base_evidence(
            status=status,
            confidence=confidence,
            data_state=data_state,
            freshness=freshness,
            trust_status=trust_status,
        ),
        *_workload_evidence(
            inputs=inputs,
            data_state=data_state,
            freshness=freshness,
            trust_status=trust_status,
        ),
    ]
    limitations = _limitations(
        availability,
        data_state=data_state,
        confidence=confidence,
    )

    return build_explanation(
        scope='availability_state',
        subject_type='pitcher',
        subject_id=resolved_subject_id,
        state_explained=status,
        summary=_availability_summary(
            status=status,
            data_state=data_state,
            reasons=reasons,
            inputs=inputs,
        ),
        reason_codes=_reason_codes(
            status=status,
            data_state=data_state,
            reasons=reasons,
            confidence=confidence,
        ),
        supporting_evidence=evidence,
        limitations=limitations,
        freshness=freshness,
        trust=trust,
        confidence={
            'level': confidence,
            'summary': _confidence_summary(confidence, data_state),
        },
        generated_at=generated_at,
    )


def _availability_summary(
    *,
    status: str,
    data_state: str,
    reasons: tuple[str, ...],
    inputs: Mapping[str, Any],
) -> str:
    if data_state == 'stale':
        return 'BaseballOS is treating him as a monitor arm, but the stored workload data is stale.'
    if data_state == 'missing':
        return 'BaseballOS cannot say much yet because recent workload data is missing.'
    if data_state == 'incomplete':
        return 'BaseballOS is keeping this note limited because recent workload detail is incomplete.'

    if reasons:
        if status == 'Monitor':
            return 'He has pitched recently enough that BaseballOS is treating him as a monitor arm.'
        if status == 'Limited':
            return 'Recent usage points to a lighter lane if he is needed.'
        if status == 'Avoid':
            return 'Recent usage is heavy enough that BaseballOS is holding this as a rest-risk note.'
        if status == 'Unavailable':
            return 'A heavy recent stretch has his workload up enough to make him unavailable.'

    pitches_yesterday = inputs.get('pitches_yesterday')
    if status == 'Available' and isinstance(pitches_yesterday, (int, float)) and pitches_yesterday <= 0:
        return 'He has no workload from yesterday in the stored data.'
    if status == 'Available':
        return 'His recent workload is light enough for BaseballOS to keep this note open.'
    return 'BaseballOS is limiting this note to the stored public workload data.'


def _confidence_summary(confidence: str, data_state: str) -> str:
    if confidence == 'high' and data_state == 'fresh':
        return 'The public workload record is current enough for this note.'
    if data_state == 'stale':
        return 'The safest note stays limited until fresher workload data is available.'
    if data_state == 'missing':
        return 'The safest note stays limited until recent workload data is available.'
    if data_state == 'incomplete':
        return 'The safest note stays limited until the workload detail is more complete.'
    return 'The safest note stays limited to what the public workload record can support.'


def serialize_availability_explanation(
    availability: Mapping[str, Any],
    *,
    subject_id: str | int | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build and serialize a deterministic V4 availability explanation."""

    return build_availability_explanation(
        availability,
        subject_id=subject_id,
        generated_at=generated_at,
    ).to_dict()
