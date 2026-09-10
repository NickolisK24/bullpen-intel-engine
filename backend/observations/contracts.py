"""V5 Bullpen Intelligence observation domain contracts.

These contracts are the Phase 4 backend-domain foundation only. They define
governed observation objects, serialization, and validation without building
observation generators, API routes, frontend surfaces, database state, or
runtime observation generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from observations.enums import (
    ObservationFamily,
    ObservationSeverity,
    ObservationTrustStatus,
    ObservationType,
)
from observations.validators import (
    NO_RANKING_APPLIED,
    NO_SELECTION_MADE,
    require_collection_payload_valid,
    require_observation_payload_valid,
    required_text,
    validate_observation_family,
    validate_observation_severity,
    validate_observation_trust_status,
    validate_observation_type,
)


CAPABILITY = 'v5_bullpen_intelligence_surface'
CONTRACT = 'baseballos.v5.observation.domain'
CONTRACT_VERSION = 'v5_phase_4'


def _tuple_value(values: Any) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, tuple):
        return values
    if isinstance(values, list):
        return tuple(values)
    return (values,)


def _mapping_value(value: Mapping[str, Any] | None, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f'{field_name} is required.')
    return dict(value)


@dataclass(frozen=True)
class ObservationEvidence:
    evidence_id: str
    source: str
    source_type: str
    label: str
    value: Any = None
    freshness_status: str | None = None
    data_through: str | None = None
    generated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        required_text(self.evidence_id, 'evidence_id')
        required_text(self.source, 'source')
        required_text(self.source_type, 'source_type')
        required_text(self.label, 'label')
        object.__setattr__(self, 'metadata', dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            'evidence_id': self.evidence_id,
            'source': self.source,
            'source_type': self.source_type,
            'label': self.label,
            'value': self.value,
            'freshness_status': self.freshness_status,
            'data_through': self.data_through,
            'generated_at': self.generated_at,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True)
class ObservationLimitation:
    limitation_type: str
    summary: str
    severity: str = ObservationSeverity.INFORMATIONAL.value
    source: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        required_text(self.limitation_type, 'limitation_type')
        required_text(self.summary, 'limitation.summary')
        object.__setattr__(
            self,
            'severity',
            validate_observation_severity(self.severity),
        )
        object.__setattr__(self, 'metadata', dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            'limitation_type': self.limitation_type,
            'summary': self.summary,
            'severity': self.severity,
            'source': self.source,
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True)
class BullpenObservation:
    observation_id: str
    observation_type: str | ObservationType
    family: str | ObservationFamily
    severity: str | ObservationSeverity
    title: str
    summary: str
    evidence: tuple[ObservationEvidence, ...] = field(default_factory=tuple)
    limitations: tuple[ObservationLimitation, ...] = field(default_factory=tuple)
    confidence: Mapping[str, Any] = field(default_factory=dict)
    freshness: Mapping[str, Any] = field(default_factory=dict)
    trust_status: str | ObservationTrustStatus = ObservationTrustStatus.SUPPORTED
    explanation_reference: str | None = None
    generated_at: str | None = None
    ranking_applied: bool = field(default=NO_RANKING_APPLIED, init=False)
    selection_made: bool = field(default=NO_SELECTION_MADE, init=False)

    def __post_init__(self):
        required_text(self.observation_id, 'observation_id')
        object.__setattr__(
            self,
            'observation_type',
            validate_observation_type(self.observation_type),
        )
        object.__setattr__(self, 'family', validate_observation_family(self.family))
        object.__setattr__(
            self,
            'severity',
            validate_observation_severity(self.severity),
        )
        required_text(self.title, 'title')
        required_text(self.summary, 'summary')
        object.__setattr__(self, 'evidence', _tuple_value(self.evidence))
        object.__setattr__(self, 'limitations', _tuple_value(self.limitations))
        object.__setattr__(self, 'confidence', _mapping_value(self.confidence, 'confidence'))
        object.__setattr__(self, 'freshness', _mapping_value(self.freshness, 'freshness'))
        object.__setattr__(
            self,
            'trust_status',
            validate_observation_trust_status(self.trust_status),
        )
        require_observation_payload_valid(self.to_dict(validate=False))

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        payload = {
            'capability': CAPABILITY,
            'contract': CONTRACT,
            'contract_version': CONTRACT_VERSION,
            'observation_id': self.observation_id,
            'observation_type': self.observation_type,
            'family': self.family,
            'severity': self.severity,
            'title': self.title,
            'summary': self.summary,
            'evidence': [item.to_dict() for item in self.evidence],
            'limitations': [item.to_dict() for item in self.limitations],
            'confidence': dict(self.confidence),
            'freshness': dict(self.freshness),
            'trust_status': self.trust_status,
            'explanation_reference': self.explanation_reference,
            'generated_at': self.generated_at,
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
        }
        if validate:
            require_observation_payload_valid(payload)
        return payload


@dataclass(frozen=True)
class ObservationCollection:
    collection_id: str
    observations: tuple[BullpenObservation, ...] = field(default_factory=tuple)
    generated_at: str | None = None
    freshness: Mapping[str, Any] = field(default_factory=dict)
    confidence: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[ObservationLimitation, ...] = field(default_factory=tuple)
    suppressed_count: int = 0
    suppression_reasons: tuple[str, ...] = field(default_factory=tuple)
    ranking_applied: bool = field(default=NO_RANKING_APPLIED, init=False)
    selection_made: bool = field(default=NO_SELECTION_MADE, init=False)

    def __post_init__(self):
        required_text(self.collection_id, 'collection_id')
        object.__setattr__(self, 'observations', _tuple_value(self.observations))
        object.__setattr__(self, 'freshness', dict(self.freshness or {}))
        object.__setattr__(self, 'confidence', dict(self.confidence or {}))
        object.__setattr__(self, 'limitations', _tuple_value(self.limitations))
        object.__setattr__(self, 'suppression_reasons', _tuple_value(self.suppression_reasons))
        if self.suppressed_count < 0:
            raise ValueError('suppressed_count cannot be negative.')
        require_collection_payload_valid(self.to_dict(validate=False))

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        payload = {
            'capability': CAPABILITY,
            'contract': CONTRACT,
            'contract_version': CONTRACT_VERSION,
            'collection_id': self.collection_id,
            'generated_at': self.generated_at,
            'observation_count': len(self.observations),
            'observations': [
                observation.to_dict() for observation in self.observations
            ],
            'freshness': dict(self.freshness),
            'confidence': dict(self.confidence),
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'suppressed_count': self.suppressed_count,
            'suppression_reasons': list(self.suppression_reasons),
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
        }
        if validate:
            require_collection_payload_valid(payload)
        return payload


def serialize_observation(observation: BullpenObservation) -> dict[str, Any]:
    if not isinstance(observation, BullpenObservation):
        raise ValueError('observation must be a BullpenObservation.')
    return observation.to_dict()


def serialize_collection(collection: ObservationCollection) -> dict[str, Any]:
    if not isinstance(collection, ObservationCollection):
        raise ValueError('collection must be an ObservationCollection.')
    return collection.to_dict()
