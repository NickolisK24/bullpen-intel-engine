"""Deterministic V5 observation builders.

Phase 5 builders convert explicit trusted-state dictionaries into governed
observation contracts. They do not read files, call services, query
persistence, expose routes, or integrate runtime data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from observations.contracts import (
    BullpenObservation,
    ObservationCollection,
    ObservationEvidence,
    ObservationLimitation,
)
from observations.enums import (
    ObservationFamily,
    ObservationSeverity,
    ObservationType,
)


StateMap = Mapping[str, Any]
BuilderInput = tuple['DeterministicObservationBuilder', StateMap]


class DeterministicObservationBuilder:
    """Base builder for a single governed observation family."""

    observation_type: ObservationType
    family: ObservationFamily
    default_severity: ObservationSeverity
    default_title: str
    default_summary: str
    default_explanation_reference: str | None = None

    def build(self, state: StateMap) -> BullpenObservation | None:
        """Return a governed observation or suppress unsafe input."""

        try:
            state_payload = _require_mapping(state, 'state')
            observation = BullpenObservation(
                observation_id=_observation_id_for(self.family.value, state_payload),
                observation_type=self.observation_type,
                family=self.family,
                severity=state_payload.get('severity', self.default_severity),
                title=state_payload.get('title', self.default_title),
                summary=state_payload.get('summary', self.default_summary),
                evidence=_evidence_from_state(state_payload),
                limitations=_limitations_from_state(state_payload),
                confidence=_required_mapping_from_state(state_payload, 'confidence'),
                freshness=_required_mapping_from_state(state_payload, 'freshness'),
                trust_status=state_payload.get('trust_status'),
                explanation_reference=state_payload.get(
                    'explanation_reference',
                    self.default_explanation_reference,
                ),
                generated_at=state_payload.get('generated_at'),
            )
        except (TypeError, ValueError):
            return None

        return observation


class InventoryObservationBuilder(DeterministicObservationBuilder):
    observation_type = ObservationType.INVENTORY
    family = ObservationFamily.INVENTORY
    default_severity = ObservationSeverity.MONITOR
    default_title = 'Availability inventory is constrained.'
    default_summary = (
        'Availability inventory is constrained by the supplied trusted snapshot.'
    )
    default_explanation_reference = 'v4:availability:inventory'


class ReadinessObservationBuilder(DeterministicObservationBuilder):
    observation_type = ObservationType.READINESS
    family = ObservationFamily.READINESS
    default_severity = ObservationSeverity.MONITOR
    default_title = 'Readiness limitations are present.'
    default_summary = (
        'Readiness limitations are present in the supplied trusted snapshot.'
    )
    default_explanation_reference = 'v4:team_operations_readiness:summary'


class WorkloadPressureObservationBuilder(DeterministicObservationBuilder):
    observation_type = ObservationType.WORKLOAD_PRESSURE
    family = ObservationFamily.WORKLOAD_PRESSURE
    default_severity = ObservationSeverity.ELEVATED
    default_title = 'Bullpen workload pressure is elevated.'
    default_summary = (
        'Bullpen workload pressure is elevated in the supplied trusted snapshot.'
    )
    default_explanation_reference = 'v4:team_operations_readiness:workload'


class FreshnessObservationBuilder(DeterministicObservationBuilder):
    observation_type = ObservationType.FRESHNESS
    family = ObservationFamily.FRESHNESS
    default_severity = ObservationSeverity.MONITOR
    default_title = 'Freshness protection is affecting bullpen records.'
    default_summary = (
        'Freshness protection is affecting bullpen records in the supplied '
        'trusted snapshot.'
    )
    default_explanation_reference = 'v4:availability:freshness'


class TrustObservationBuilder(DeterministicObservationBuilder):
    observation_type = ObservationType.TRUST
    family = ObservationFamily.TRUST
    default_severity = ObservationSeverity.MONITOR
    default_title = 'Trust limitations are present in the current snapshot.'
    default_summary = (
        'Trust limitations are present in the supplied trusted snapshot.'
    )
    default_explanation_reference = 'v4:availability:trust'


def build_observation_collection(
    collection_id: str,
    builder_inputs: Sequence[BuilderInput],
    *,
    generated_at: str | None = None,
    freshness: StateMap | None = None,
    confidence: StateMap | None = None,
    limitations: Sequence[ObservationLimitation | StateMap] | None = None,
) -> ObservationCollection | None:
    """Assemble a governed observation collection from deterministic builders."""

    try:
        observations: list[BullpenObservation] = []
        suppression_reasons: list[str] = []

        for builder, state in tuple(builder_inputs or ()):
            observation = builder.build(state)
            if observation is None:
                suppression_reasons.append(
                    f'{builder.family.value}_observation_suppressed'
                )
                continue
            observations.append(observation)

        return ObservationCollection(
            collection_id=collection_id,
            observations=tuple(observations),
            generated_at=generated_at,
            freshness=dict(freshness or {}),
            confidence=dict(confidence or {}),
            limitations=_limitations_from_raw(limitations or ()),
            suppressed_count=len(suppression_reasons),
            suppression_reasons=tuple(suppression_reasons),
        )
    except (TypeError, ValueError):
        return None


def _observation_id_for(prefix: str, state: StateMap) -> str:
    explicit_id = state.get('observation_id')
    if isinstance(explicit_id, str) and explicit_id.strip():
        return explicit_id

    identity_payload = {
        'family': prefix,
        'evidence': state.get('evidence'),
        'freshness': state.get('freshness'),
        'confidence': state.get('confidence'),
        'trust_status': state.get('trust_status'),
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, default=str).encode('utf-8')
    ).hexdigest()[:12]
    return f'{prefix}:{digest}'


def _evidence_from_state(state: StateMap) -> tuple[ObservationEvidence, ...]:
    raw_evidence = state.get('evidence')
    if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes)):
        raise ValueError('evidence must include at least one item.')
    if not raw_evidence:
        raise ValueError('evidence must include at least one item.')

    evidence_items: list[ObservationEvidence] = []
    for item in raw_evidence:
        if isinstance(item, ObservationEvidence):
            evidence_items.append(item)
            continue
        payload = _require_mapping(item, 'evidence')
        evidence_items.append(
            ObservationEvidence(
                evidence_id=payload.get('evidence_id'),
                source=payload.get('source'),
                source_type=payload.get('source_type'),
                label=payload.get('label'),
                value=payload.get('value'),
                freshness_status=payload.get('freshness_status'),
                data_through=payload.get('data_through'),
                generated_at=payload.get('generated_at'),
                metadata=payload.get('metadata', {}),
            )
        )

    return tuple(evidence_items)


def _limitations_from_state(state: StateMap) -> tuple[ObservationLimitation, ...]:
    return _limitations_from_raw(state.get('limitations', ()))


def _limitations_from_raw(
    raw_limitations: Sequence[ObservationLimitation | StateMap] | None,
) -> tuple[ObservationLimitation, ...]:
    if raw_limitations is None:
        return ()
    if not isinstance(raw_limitations, Sequence) or isinstance(
        raw_limitations,
        (str, bytes),
    ):
        raise ValueError('limitations must be a sequence.')

    limitations: list[ObservationLimitation] = []
    for item in raw_limitations:
        if isinstance(item, ObservationLimitation):
            limitations.append(item)
            continue
        payload = _require_mapping(item, 'limitation')
        limitations.append(
            ObservationLimitation(
                limitation_type=payload.get('limitation_type'),
                summary=payload.get('summary'),
                severity=payload.get(
                    'severity',
                    ObservationSeverity.INFORMATIONAL,
                ),
                source=payload.get('source'),
                metadata=payload.get('metadata', {}),
            )
        )

    return tuple(limitations)


def _required_mapping_from_state(state: StateMap, field_name: str) -> dict[str, Any]:
    return _require_mapping(state.get(field_name), field_name)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f'{field_name} is required.')
    return dict(value)
