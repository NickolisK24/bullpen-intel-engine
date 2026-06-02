"""Recommendation Engine V2 backend domain object foundation.

These objects model bullpen-level context only. They do not expose API
behavior, rank candidates, select pitchers, or change Recommendation Engine V1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from recommendation.enums import (
    RecommendationConfidence,
    RecommendationFreshnessState,
)


V2_POLICY_NAME = 'recommendation_engine_v2_domain_foundation'
V2_PHASE = 'phase_1_backend_domain_object_foundation'
V2_TRUST_METADATA_POLICY = 'mandatory_v2_trust_metadata'
NO_RANKING_APPLIED = False
NO_SELECTION_MADE = False
V2_REQUIRED_TRUST_METADATA_FIELDS = frozenset(
    {
        'confidence',
        'freshness',
        'limitations',
        'explanations',
        'refusal_reasons',
        'data_state',
        'source_evidence_state',
        'governance_state',
        'ranking_applied',
        'selection_made',
    }
)

FORBIDDEN_V2_FIELD_NAMES = frozenset(
    {
        'rank',
        'ranking',
        'winner',
        'priority',
        'priority_score',
        'score',
        'score_ordering',
        'selected_pitcher',
        'selected_pitcher_id',
        'selected_candidate',
        'selected_candidate_id',
        'recommended_pitcher',
        'recommended_option',
        'preferred_pitcher',
        'preferred_option',
        'use_this_pitcher',
        'best_candidate',
        'best_pitcher',
        'top_candidate',
        'pitcher_choice',
        'prediction',
        'predicted_performance',
        'performance_prediction',
        'performance_forecast',
        'predicted_injury',
        'injury_prediction',
        'injury_risk_prediction',
        'predicted_saves',
        'save_prediction',
        'game_prediction',
        'game_outcome_prediction',
        'outcome_prediction',
        'projected_outcome',
        'projected_performance',
    }
)

ALLOWED_GOVERNANCE_FIELD_NAMES = frozenset(
    {
        'ranking_applied',
        'selection_made',
    }
)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return dict(value or {})


def _normalize_tuple(values):
    return tuple(values or ())


def _field_name_is_forbidden(field_name: str) -> bool:
    normalized = field_name.lower()
    if normalized in ALLOWED_GOVERNANCE_FIELD_NAMES:
        return False
    return normalized in FORBIDDEN_V2_FIELD_NAMES


def v2_governance_errors(payload: Any, path: str = 'payload') -> list[str]:
    """Return forbidden V2 governance fields found in a serialized payload."""
    errors: list[str] = []

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_path = f'{path}.{key_text}'
            if _field_name_is_forbidden(key_text):
                errors.append(f'{key_path} uses a forbidden V2 field name.')
            errors.extend(v2_governance_errors(value, key_path))
        return errors

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            errors.extend(v2_governance_errors(item, f'{path}[{index}]'))

    return errors


def require_v2_governance_safe(payload: Any) -> None:
    errors = v2_governance_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def v2_trust_metadata_errors(payload: Any, path: str = 'payload') -> list[str]:
    """Return missing or unsafe mandatory V2 trust metadata errors."""
    errors: list[str] = []

    if isinstance(payload, Mapping):
        if _payload_requires_trust_metadata(payload):
            errors.extend(_trust_metadata_mapping_errors(payload, path))
        for key, value in payload.items():
            errors.extend(v2_trust_metadata_errors(value, f'{path}.{key}'))
        return errors

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            errors.extend(v2_trust_metadata_errors(item, f'{path}[{index}]'))

    return errors


def require_v2_trust_metadata(payload: Any) -> None:
    errors = v2_trust_metadata_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def _payload_requires_trust_metadata(payload: Mapping[str, Any]) -> bool:
    return 'ranking_applied' in payload or 'selection_made' in payload


def _trust_metadata_mapping_errors(
    payload: Mapping[str, Any],
    path: str,
) -> list[str]:
    errors: list[str] = []
    if payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path}.ranking_applied must be false.')
    if payload.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path}.selection_made must be false.')

    trust_source = _trust_metadata_source(payload)
    if not isinstance(trust_source, Mapping):
        errors.append(f'{path} is missing mandatory V2 trust metadata.')
        return errors

    for field_name in sorted(V2_REQUIRED_TRUST_METADATA_FIELDS):
        if field_name not in trust_source:
            errors.append(
                f'{path} trust metadata is missing required field {field_name}.'
            )

    if trust_source.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path} trust metadata ranking_applied must be false.')
    if trust_source.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path} trust metadata selection_made must be false.')
    if not isinstance(trust_source.get('freshness'), Mapping):
        errors.append(f'{path} trust metadata freshness must be represented.')
    if not isinstance(trust_source.get('limitations'), list):
        errors.append(f'{path} trust metadata limitations must be represented.')
    if not isinstance(trust_source.get('explanations'), list):
        errors.append(f'{path} trust metadata explanations must be represented.')
    if not isinstance(trust_source.get('refusal_reasons'), list):
        errors.append(
            f'{path} trust metadata refusal_reasons must be represented.'
        )
    return errors


def _trust_metadata_source(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if V2_REQUIRED_TRUST_METADATA_FIELDS.issubset(payload.keys()):
        return payload
    for key in ('trust_metadata', 'trust_summary', 'context'):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _trust_metadata_payload(context_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        'policy': V2_TRUST_METADATA_POLICY,
        'scope': context_payload['scope'],
        'confidence': context_payload['confidence'],
        'confidence_code': context_payload['confidence_code'],
        'data_state': context_payload['data_state'],
        'source_evidence_state': context_payload['source_evidence_state'],
        'governance_state': context_payload['governance_state'],
        'generated_at': context_payload['generated_at'],
        'freshness': context_payload['freshness'],
        'limitations': context_payload['limitations'],
        'limitation_count': len(context_payload['limitations']),
        'explanations': context_payload['explanations'],
        'explanation_count': len(context_payload['explanations']),
        'refusal_reasons': context_payload['refusal_reasons'],
        'refusal_reason_count': len(context_payload['refusal_reasons']),
        'trust_validation_errors': context_payload['trust_validation_errors'],
        'ranking_applied': context_payload['ranking_applied'],
        'selection_made': context_payload['selection_made'],
    }
    require_v2_governance_safe(payload)
    return payload


@dataclass(frozen=True)
class V2Explanation:
    code: str
    message: str
    applies_to: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        require_v2_governance_safe(self.details)

    def to_dict(self):
        payload = {
            'code': self.code,
            'message': self.message,
            'applies_to': self.applies_to,
            'details': dict(self.details),
        }
        require_v2_governance_safe(payload)
        return payload


@dataclass(frozen=True)
class V2Limitation:
    limitation_id: str
    message: str
    severity: str = 'informational'
    applies_to: str = 'recommendation_context'

    def to_dict(self):
        return {
            'limitation_id': self.limitation_id,
            'message': self.message,
            'severity': self.severity,
            'applies_to': self.applies_to,
        }


@dataclass(frozen=True)
class V2FreshnessMetadata:
    state: RecommendationFreshnessState = RecommendationFreshnessState.UNKNOWN
    data_through: str | None = None
    last_successful_sync: str | None = None
    latest_sync_status: str | None = None
    stale_warning: str | None = None
    missing_data_warning: str | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'limitations', _normalize_tuple(self.limitations))

    def to_dict(self):
        return {
            'state': self.state.value,
            'state_code': self.state.name,
            'data_through': self.data_through,
            'last_successful_sync': self.last_successful_sync,
            'latest_sync_status': self.latest_sync_status,
            'stale_warning': self.stale_warning,
            'missing_data_warning': self.missing_data_warning,
            'limitations': list(self.limitations),
        }


@dataclass(frozen=True)
class V2Refusal:
    refusal_id: str
    reason: str
    message: str
    applies_to: str

    def to_dict(self):
        return {
            'refusal_id': self.refusal_id,
            'reason': self.reason,
            'message': self.message,
            'applies_to': self.applies_to,
        }


BASE_V2_LIMITATIONS = (
    V2Limitation(
        limitation_id='public_workload_data_only',
        message='Based on public workload data tracked by BaseballOS.',
        applies_to='recommendation_context',
    ),
    V2Limitation(
        limitation_id='not_injury_or_medical',
        message='Not a medical or injury conclusion.',
        applies_to='recommendation_context',
    ),
    V2Limitation(
        limitation_id='not_performance_forecast',
        message='Not a performance forecast.',
        applies_to='recommendation_context',
    ),
    V2Limitation(
        limitation_id='no_manager_intent',
        message='BaseballOS does not know manager intent or bullpen warm-up activity.',
        applies_to='recommendation_context',
    ),
    V2Limitation(
        limitation_id='user_decides',
        message='The user remains responsible for the final decision.',
        applies_to='recommendation_context',
    ),
)


@dataclass(frozen=True)
class RecommendationContext:
    scope: str = 'bullpen_state'
    confidence: RecommendationConfidence = RecommendationConfidence.UNKNOWN
    data_state: str = 'unknown'
    source_evidence_state: str = 'represented'
    governance_state: str = 'compliant'
    generated_at: str | None = None
    freshness: V2FreshnessMetadata = field(default_factory=V2FreshnessMetadata)
    limitations: tuple[V2Limitation, ...] = BASE_V2_LIMITATIONS
    explanations: tuple[V2Explanation, ...] = ()
    refusal_reasons: tuple[V2Refusal, ...] = ()
    trust_validation_errors: tuple[str, ...] = ()
    ranking_applied: bool = NO_RANKING_APPLIED
    selection_made: bool = NO_SELECTION_MADE

    def __post_init__(self):
        if self.ranking_applied is not NO_RANKING_APPLIED:
            raise ValueError('Recommendation Engine V2 must preserve ranking_applied=False.')
        if self.selection_made is not NO_SELECTION_MADE:
            raise ValueError('Recommendation Engine V2 must preserve selection_made=False.')
        if self.confidence is None:
            raise ValueError('Recommendation Engine V2 requires confidence trust metadata.')
        if not self.data_state:
            raise ValueError('Recommendation Engine V2 requires data_state trust metadata.')
        if not self.source_evidence_state:
            raise ValueError(
                'Recommendation Engine V2 requires source evidence state metadata.'
            )
        if not self.governance_state:
            raise ValueError(
                'Recommendation Engine V2 requires governance state metadata.'
            )
        if self.freshness is None:
            raise ValueError('Recommendation Engine V2 requires freshness metadata.')
        if self.limitations is None:
            raise ValueError('Recommendation Engine V2 requires limitation metadata.')
        if self.explanations is None:
            raise ValueError('Recommendation Engine V2 requires explanation metadata.')
        if self.refusal_reasons is None:
            raise ValueError('Recommendation Engine V2 requires refusal metadata.')
        object.__setattr__(self, 'limitations', _normalize_tuple(self.limitations))
        object.__setattr__(self, 'explanations', _normalize_tuple(self.explanations))
        object.__setattr__(
            self,
            'refusal_reasons',
            _normalize_tuple(self.refusal_reasons),
        )
        object.__setattr__(
            self,
            'trust_validation_errors',
            _normalize_tuple(self.trust_validation_errors),
        )

    def to_dict(self):
        payload = {
            'scope': self.scope,
            'policy': V2_POLICY_NAME,
            'phase': V2_PHASE,
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
            'confidence': self.confidence.value,
            'confidence_code': self.confidence.name,
            'data_state': self.data_state,
            'source_evidence_state': self.source_evidence_state,
            'governance_state': self.governance_state,
            'generated_at': self.generated_at,
            'freshness': self.freshness.to_dict(),
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'explanations': [
                explanation.to_dict() for explanation in self.explanations
            ],
            'refusal_reasons': [
                refusal.to_dict() for refusal in self.refusal_reasons
            ],
            'trust_validation_errors': list(self.trust_validation_errors),
        }
        payload['trust_metadata'] = _trust_metadata_payload(payload)
        require_v2_governance_safe(payload)
        require_v2_trust_metadata(payload)
        return payload


def _context_for_scope(scope: str) -> RecommendationContext:
    return RecommendationContext(scope=scope)


def _with_context(payload: dict[str, Any], context: RecommendationContext):
    context_payload = context.to_dict()
    payload['context'] = context_payload
    payload['ranking_applied'] = context_payload['ranking_applied']
    payload['selection_made'] = context_payload['selection_made']
    payload['confidence'] = context_payload['confidence']
    payload['data_state'] = context_payload['data_state']
    payload['source_evidence_state'] = context_payload['source_evidence_state']
    payload['governance_state'] = context_payload['governance_state']
    payload['freshness'] = context_payload['freshness']
    payload['limitations'] = context_payload['limitations']
    payload['explanations'] = context_payload['explanations']
    payload['refusal_reasons'] = context_payload['refusal_reasons']
    payload['trust_metadata'] = context_payload['trust_metadata']
    require_v2_governance_safe(payload)
    require_v2_trust_metadata(payload)
    return payload


@dataclass(frozen=True)
class CandidateGroup:
    group_id: str
    label: str
    criteria: tuple[str, ...]
    candidates: tuple[Mapping[str, Any], ...] = ()
    neutral_sequence_basis: str = 'input_sequence_preserved'
    context: RecommendationContext = field(
        default_factory=lambda: _context_for_scope('candidate_group')
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        candidates = tuple(dict(candidate) for candidate in self.candidates)
        metadata = _freeze_mapping(self.metadata)
        require_v2_governance_safe(candidates)
        require_v2_governance_safe(metadata)
        object.__setattr__(self, 'criteria', _normalize_tuple(self.criteria))
        object.__setattr__(self, 'candidates', candidates)
        object.__setattr__(self, 'metadata', metadata)

    def to_dict(self):
        payload = {
            'group_id': self.group_id,
            'label': self.label,
            'criteria': list(self.criteria),
            'candidate_count': len(self.candidates),
            'candidates': [dict(candidate) for candidate in self.candidates],
            'neutral_sequence_basis': self.neutral_sequence_basis,
            'metadata': dict(self.metadata),
        }
        return _with_context(payload, self.context)


@dataclass(frozen=True)
class BullpenState:
    team_id: int | None = None
    team_name: str | None = None
    bullpen_status: str = 'unknown'
    inventory: Mapping[str, Any] = field(default_factory=dict)
    readiness: Mapping[str, Any] = field(default_factory=dict)
    workload: Mapping[str, Any] = field(default_factory=dict)
    stress: Mapping[str, Any] = field(default_factory=dict)
    candidate_groups: tuple[CandidateGroup, ...] = ()
    context: RecommendationContext = field(
        default_factory=lambda: _context_for_scope('bullpen_state')
    )

    def __post_init__(self):
        object.__setattr__(self, 'inventory', _freeze_mapping(self.inventory))
        object.__setattr__(self, 'readiness', _freeze_mapping(self.readiness))
        object.__setattr__(self, 'workload', _freeze_mapping(self.workload))
        object.__setattr__(self, 'stress', _freeze_mapping(self.stress))
        object.__setattr__(
            self,
            'candidate_groups',
            _normalize_tuple(self.candidate_groups),
        )
        require_v2_governance_safe(self.inventory)
        require_v2_governance_safe(self.readiness)
        require_v2_governance_safe(self.workload)
        require_v2_governance_safe(self.stress)

    def to_dict(self):
        payload = {
            'team_id': self.team_id,
            'team_name': self.team_name,
            'bullpen_status': self.bullpen_status,
            'inventory': dict(self.inventory),
            'readiness': dict(self.readiness),
            'workload': dict(self.workload),
            'stress': dict(self.stress),
            'candidate_groups': [
                group.to_dict() for group in self.candidate_groups
            ],
        }
        return _with_context(payload, self.context)


@dataclass(frozen=True)
class TeamBullpenContext:
    team_id: int | None = None
    team_name: str | None = None
    leverage_inventory: Mapping[str, Any] = field(default_factory=dict)
    workload_distribution: Mapping[str, Any] = field(default_factory=dict)
    readiness_distribution: Mapping[str, Any] = field(default_factory=dict)
    stress_indicators: Mapping[str, Any] = field(default_factory=dict)
    team_summary: Mapping[str, Any] = field(default_factory=dict)
    context: RecommendationContext = field(
        default_factory=lambda: _context_for_scope('team_bullpen_context')
    )

    def __post_init__(self):
        object.__setattr__(
            self,
            'leverage_inventory',
            _freeze_mapping(self.leverage_inventory),
        )
        object.__setattr__(
            self,
            'workload_distribution',
            _freeze_mapping(self.workload_distribution),
        )
        object.__setattr__(
            self,
            'readiness_distribution',
            _freeze_mapping(self.readiness_distribution),
        )
        object.__setattr__(
            self,
            'stress_indicators',
            _freeze_mapping(self.stress_indicators),
        )
        object.__setattr__(
            self,
            'team_summary',
            _freeze_mapping(self.team_summary),
        )
        require_v2_governance_safe(self.leverage_inventory)
        require_v2_governance_safe(self.workload_distribution)
        require_v2_governance_safe(self.readiness_distribution)
        require_v2_governance_safe(self.stress_indicators)
        require_v2_governance_safe(self.team_summary)

    def to_dict(self):
        payload = {
            'team_id': self.team_id,
            'team_name': self.team_name,
            'leverage_inventory': dict(self.leverage_inventory),
            'workload_distribution': dict(self.workload_distribution),
            'readiness_distribution': dict(self.readiness_distribution),
            'stress_indicators': dict(self.stress_indicators),
            'team_summary': dict(self.team_summary),
        }
        return _with_context(payload, self.context)


__all__ = [
    'BASE_V2_LIMITATIONS',
    'NO_RANKING_APPLIED',
    'NO_SELECTION_MADE',
    'V2_PHASE',
    'V2_POLICY_NAME',
    'V2_REQUIRED_TRUST_METADATA_FIELDS',
    'V2_TRUST_METADATA_POLICY',
    'BullpenState',
    'CandidateGroup',
    'RecommendationContext',
    'TeamBullpenContext',
    'V2Explanation',
    'V2FreshnessMetadata',
    'V2Limitation',
    'V2Refusal',
    'require_v2_governance_safe',
    'require_v2_trust_metadata',
    'v2_governance_errors',
    'v2_trust_metadata_errors',
]
