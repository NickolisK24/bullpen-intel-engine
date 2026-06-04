"""V4 Evidence and Explanation backend domain contracts.

These contracts are internal backend-domain objects only. They define the
stable vocabulary, serialization shape, and governance validation required by
the V4 Evidence and Explanation layer without integrating with routes,
availability, recommendations, readiness, or frontend surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


CAPABILITY = 'v4_evidence_and_explanation'
CONTRACT = 'baseballos.v4.explanation.domain'
CONTRACT_VERSION = 'v4_phase_4'

NO_RANKING_APPLIED = False
NO_SELECTION_MADE = False
NO_RECOMMENDATION_MADE = False
NO_PREDICTION_MADE = False
DECISION_SCOPE = 'explanation_only'
ADVICE_SCOPE = 'none'


class ExplanationScope(str, Enum):
    AVAILABILITY_STATE = 'availability_state'
    WORKLOAD_STATE = 'workload_state'
    READINESS_STATE = 'readiness_state'
    RISK_DISTRIBUTION = 'risk_distribution'
    FRESHNESS_STATE = 'freshness_state'
    TRUST_STATE = 'trust_state'
    COVERAGE_STATE = 'coverage_state'


class SubjectType(str, Enum):
    PITCHER = 'pitcher'
    TEAM = 'team'
    BULLPEN = 'bullpen'
    DISTRIBUTION = 'distribution'
    SYSTEM = 'system'


ALLOWED_EXPLANATION_SCOPES = frozenset(scope.value for scope in ExplanationScope)
ALLOWED_SUBJECT_TYPES = frozenset(subject.value for subject in SubjectType)

ALLOWED_CONFIDENCE_LEVELS = frozenset({'high', 'medium', 'low', 'unknown'})
ALLOWED_FRESHNESS_STATUSES = frozenset(
    {
        'current',
        'stale',
        'missing',
        'incomplete',
        'historical',
        'unknown',
    }
)
ALLOWED_TRUST_STATUSES = frozenset(
    {
        'trusted',
        'limited',
        'failed',
        'uncertified',
        'unknown',
    }
)

REASON_CODE_DEFINITIONS = {
    'WORKLOAD_RECENT_USAGE_ELEVATED': {
        'scope': ExplanationScope.WORKLOAD_STATE.value,
        'label': 'Recent usage elevated',
        'summary': 'Recent public workload evidence contributes to elevated workload.',
    },
    'FRESHNESS_STALE_SOURCE': {
        'scope': ExplanationScope.FRESHNESS_STATE.value,
        'label': 'Source freshness stale',
        'summary': 'Source freshness is stale for the explained state.',
    },
    'COVERAGE_PARTIAL': {
        'scope': ExplanationScope.COVERAGE_STATE.value,
        'label': 'Coverage partial',
        'summary': 'Coverage evidence is partial for the explained state.',
    },
    'TRUST_LIMITED': {
        'scope': ExplanationScope.TRUST_STATE.value,
        'label': 'Trust limited',
        'summary': 'Trust metadata limits confidence in the explanation.',
    },
    'AVAILABILITY_MONITOR_THRESHOLD_MET': {
        'scope': ExplanationScope.AVAILABILITY_STATE.value,
        'label': 'Monitor threshold met',
        'summary': 'Governed availability evidence supports Monitor state.',
    },
    'READINESS_DEGRADED_BY_LIMITATIONS': {
        'scope': ExplanationScope.READINESS_STATE.value,
        'label': 'Readiness degraded by limitations',
        'summary': 'Readiness context is degraded by visible limitations.',
    },
}

ALLOWED_REASON_CODES = frozenset(REASON_CODE_DEFINITIONS)

LIMITATION_TYPE_DEFINITIONS = {
    'missing_data': 'Required data or metadata is unavailable.',
    'stale_data': 'Source data is not current.',
    'partial_coverage': 'Evidence coverage is incomplete.',
    'uncertified_source': 'The source is not certified for this explanation.',
    'limited_confidence': 'Explanation confidence is limited.',
    'insufficient_context': 'BaseballOS lacks context needed for deeper claims.',
}

ALLOWED_LIMITATION_TYPES = frozenset(LIMITATION_TYPE_DEFINITIONS)

REQUIRED_GOVERNANCE_FIELDS = frozenset(
    {
        'ranking_applied',
        'selection_made',
        'recommendation_made',
        'prediction_made',
        'decision_scope',
        'advice_scope',
    }
)

ALLOWED_GOVERNANCE_FIELD_NAMES = REQUIRED_GOVERNANCE_FIELDS

FORBIDDEN_V4_FIELD_NAMES = frozenset(
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
        'recommended_pitcher_id',
        'recommended_option',
        'preferred_pitcher',
        'preferred_option',
        'best_arm',
        'best_candidate',
        'best_pitcher',
        'top_candidate',
        'pitcher_choice',
        'matchup',
        'matchup_advice',
        'prediction',
        'predicted_performance',
        'performance_prediction',
        'performance_forecast',
        'predicted_injury',
        'injury_prediction',
        'predicted_saves',
        'save_prediction',
        'game_prediction',
        'game_outcome_prediction',
        'outcome_prediction',
        'projected_outcome',
        'projected_performance',
        'hidden_priority_ordering',
    }
)


def _tuple_value(values: Any) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, tuple):
        return values
    if isinstance(values, list):
        return tuple(values)
    return (values,)


def _required_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field_name} is required.')
    return value


def _enum_value(value: str | Enum, allowed: frozenset[str], field_name: str) -> str:
    raw_value = value.value if isinstance(value, Enum) else value
    if raw_value not in allowed:
        raise ValueError(f'{field_name} uses unsupported vocabulary.')
    return str(raw_value)


def _field_name_is_forbidden(field_name: str) -> bool:
    normalized = field_name.lower()
    if normalized in ALLOWED_GOVERNANCE_FIELD_NAMES:
        return False
    return normalized in FORBIDDEN_V4_FIELD_NAMES


def validate_explanation_scope(scope: str | ExplanationScope) -> str:
    return _enum_value(scope, ALLOWED_EXPLANATION_SCOPES, 'scope')


def validate_subject_type(subject_type: str | SubjectType) -> str:
    return _enum_value(subject_type, ALLOWED_SUBJECT_TYPES, 'subject_type')


def validate_reason_code(code: str) -> str:
    return _enum_value(code, ALLOWED_REASON_CODES, 'reason_code')


def validate_limitation_type(limitation_type: str) -> str:
    return _enum_value(
        limitation_type,
        ALLOWED_LIMITATION_TYPES,
        'limitation_type',
    )


def governance_payload_errors(
    payload: Mapping[str, Any] | None,
    path: str = 'governance',
) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, Mapping):
        return [f'{path} is missing.']

    missing = sorted(REQUIRED_GOVERNANCE_FIELDS.difference(payload.keys()))
    for field_name in missing:
        errors.append(f'{path} is missing required field {field_name}.')

    if payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path}.ranking_applied must be false.')
    if payload.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path}.selection_made must be false.')
    if payload.get('recommendation_made') is not NO_RECOMMENDATION_MADE:
        errors.append(f'{path}.recommendation_made must be false.')
    if payload.get('prediction_made') is not NO_PREDICTION_MADE:
        errors.append(f'{path}.prediction_made must be false.')
    if payload.get('decision_scope') != DECISION_SCOPE:
        errors.append(f'{path}.decision_scope must be explanation_only.')
    if payload.get('advice_scope') != ADVICE_SCOPE:
        errors.append(f'{path}.advice_scope must be none.')

    return errors


def v4_governance_errors(payload: Any, path: str = 'payload') -> list[str]:
    """Return unsafe V4 governance fields in a nested payload."""

    errors: list[str] = []

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_path = f'{path}.{key_text}'
            if _field_name_is_forbidden(key_text):
                errors.append(f'{key_path} uses a forbidden V4 field name.')
            if key_text in REQUIRED_GOVERNANCE_FIELDS:
                errors.extend(
                    governance_payload_errors(
                        {
                            **{
                                'ranking_applied': NO_RANKING_APPLIED,
                                'selection_made': NO_SELECTION_MADE,
                                'recommendation_made': NO_RECOMMENDATION_MADE,
                                'prediction_made': NO_PREDICTION_MADE,
                                'decision_scope': DECISION_SCOPE,
                                'advice_scope': ADVICE_SCOPE,
                            },
                            key_text: value,
                        },
                        path,
                    )
                )
            errors.extend(v4_governance_errors(value, key_path))
        return errors

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            errors.extend(v4_governance_errors(item, f'{path}[{index}]'))

    return errors


def require_governance_payload_safe(payload: Mapping[str, Any] | None) -> None:
    errors = governance_payload_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def require_v4_governance_safe(payload: Any) -> None:
    errors = v4_governance_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


@dataclass(frozen=True)
class V4GovernancePayload:
    ranking_applied: bool = NO_RANKING_APPLIED
    selection_made: bool = NO_SELECTION_MADE
    recommendation_made: bool = NO_RECOMMENDATION_MADE
    prediction_made: bool = NO_PREDICTION_MADE
    decision_scope: str = DECISION_SCOPE
    advice_scope: str = ADVICE_SCOPE

    def __post_init__(self):
        require_governance_payload_safe(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
            'recommendation_made': self.recommendation_made,
            'prediction_made': self.prediction_made,
            'decision_scope': self.decision_scope,
            'advice_scope': self.advice_scope,
        }


@dataclass(frozen=True)
class V4FreshnessReference:
    status: str = 'unknown'
    data_through: str | None = None
    last_sync_at: str | None = None
    source_updated_at: str | None = None
    freshness_failure: str | None = None
    summary: str | None = None

    def __post_init__(self):
        _enum_value(self.status, ALLOWED_FRESHNESS_STATUSES, 'freshness.status')

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status,
            'data_through': self.data_through,
            'last_sync_at': self.last_sync_at,
            'source_updated_at': self.source_updated_at,
            'freshness_failure': self.freshness_failure,
            'summary': self.summary,
        }


@dataclass(frozen=True)
class V4TrustReference:
    status: str = 'unknown'
    source: str | None = None
    contract: str | None = None
    certification_status: str | None = None
    trust_failure: str | None = None
    summary: str | None = None

    def __post_init__(self):
        _enum_value(self.status, ALLOWED_TRUST_STATUSES, 'trust.status')

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status,
            'source': self.source,
            'contract': self.contract,
            'certification_status': self.certification_status,
            'trust_failure': self.trust_failure,
            'summary': self.summary,
        }


@dataclass(frozen=True)
class V4Confidence:
    level: str = 'unknown'
    summary: str | None = None

    def __post_init__(self):
        _enum_value(self.level, ALLOWED_CONFIDENCE_LEVELS, 'confidence.level')

    def to_dict(self) -> dict[str, Any]:
        return {
            'level': self.level,
            'summary': self.summary,
        }


@dataclass(frozen=True)
class V4Reason:
    code: str
    label: str | None = None
    summary: str | None = None
    scope: str | ExplanationScope | None = None

    @classmethod
    def from_code(cls, code: str) -> 'V4Reason':
        validate_reason_code(code)
        definition = REASON_CODE_DEFINITIONS[code]
        return cls(
            code=code,
            label=definition['label'],
            summary=definition['summary'],
            scope=definition['scope'],
        )

    def __post_init__(self):
        validate_reason_code(self.code)
        definition = REASON_CODE_DEFINITIONS[self.code]
        resolved_scope = self.scope or definition['scope']
        object.__setattr__(
            self,
            'scope',
            validate_explanation_scope(resolved_scope),
        )
        object.__setattr__(self, 'label', self.label or definition['label'])
        object.__setattr__(self, 'summary', self.summary or definition['summary'])

    def to_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'scope': self.scope,
            'label': self.label,
            'summary': self.summary,
            'display_safe': True,
            'certification_required': True,
        }


@dataclass(frozen=True)
class V4Limitation:
    limitation_type: str
    summary: str
    severity: str = 'informational'
    affected_scopes: tuple[str | ExplanationScope, ...] = field(default_factory=tuple)
    requires_refusal: bool = False

    def __post_init__(self):
        validate_limitation_type(self.limitation_type)
        _required_text(self.summary, 'limitation.summary')
        object.__setattr__(
            self,
            'affected_scopes',
            tuple(validate_explanation_scope(scope) for scope in self.affected_scopes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'limitation_type': self.limitation_type,
            'severity': self.severity,
            'summary': self.summary,
            'affected_scopes': list(self.affected_scopes),
            'requires_refusal': self.requires_refusal,
        }


@dataclass(frozen=True)
class V4EvidenceItem:
    evidence_id: str
    evidence_type: str
    label: str
    value: Any
    unit: str | None = None
    source: str | None = None
    freshness: V4FreshnessReference = field(default_factory=V4FreshnessReference)
    trust_status: str = 'unknown'
    impact: str | None = None
    limitation: V4Limitation | None = None

    def __post_init__(self):
        _required_text(self.evidence_id, 'evidence_id')
        _required_text(self.evidence_type, 'evidence_type')
        _required_text(self.label, 'label')
        _enum_value(self.trust_status, ALLOWED_TRUST_STATUSES, 'trust_status')

    def to_dict(self) -> dict[str, Any]:
        payload = {
            'evidence_id': self.evidence_id,
            'evidence_type': self.evidence_type,
            'label': self.label,
            'value': self.value,
            'unit': self.unit,
            'source': self.source,
            'freshness': self.freshness.to_dict(),
            'trust_status': self.trust_status,
            'impact': self.impact,
            'limitation': self.limitation.to_dict() if self.limitation else None,
        }
        require_v4_governance_safe(payload)
        return payload


@dataclass(frozen=True)
class V4Explanation:
    explanation_id: str
    scope: str | ExplanationScope
    subject_type: str | SubjectType
    subject_id: str
    state_explained: str
    summary: str
    primary_reasons: tuple[V4Reason, ...] = field(default_factory=tuple)
    supporting_evidence: tuple[V4EvidenceItem, ...] = field(default_factory=tuple)
    limitations: tuple[V4Limitation, ...] = field(default_factory=tuple)
    freshness: V4FreshnessReference = field(default_factory=V4FreshnessReference)
    trust: V4TrustReference = field(default_factory=V4TrustReference)
    confidence: V4Confidence = field(default_factory=V4Confidence)
    governance: V4GovernancePayload = field(default_factory=V4GovernancePayload)
    generated_at: str | None = None

    def __post_init__(self):
        _required_text(self.explanation_id, 'explanation_id')
        _required_text(self.subject_id, 'subject_id')
        _required_text(self.state_explained, 'state_explained')
        _required_text(self.summary, 'summary')
        object.__setattr__(
            self,
            'scope',
            validate_explanation_scope(self.scope),
        )
        object.__setattr__(
            self,
            'subject_type',
            validate_subject_type(self.subject_type),
        )
        object.__setattr__(self, 'primary_reasons', _tuple_value(self.primary_reasons))
        object.__setattr__(
            self,
            'supporting_evidence',
            _tuple_value(self.supporting_evidence),
        )
        object.__setattr__(self, 'limitations', _tuple_value(self.limitations))

    def to_dict(self) -> dict[str, Any]:
        payload = {
            'capability': CAPABILITY,
            'contract': CONTRACT,
            'contract_version': CONTRACT_VERSION,
            'explanation_id': self.explanation_id,
            'scope': self.scope,
            'subject_type': self.subject_type,
            'subject_id': self.subject_id,
            'state_explained': self.state_explained,
            'summary': self.summary,
            'primary_reasons': [reason.to_dict() for reason in self.primary_reasons],
            'supporting_evidence': [
                evidence.to_dict() for evidence in self.supporting_evidence
            ],
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'freshness': self.freshness.to_dict(),
            'trust': self.trust.to_dict(),
            'confidence': self.confidence.to_dict(),
            'governance': self.governance.to_dict(),
            'generated_at': self.generated_at,
        }
        require_v4_governance_safe(payload)
        return payload
