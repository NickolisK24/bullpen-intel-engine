"""Contracts for Team Operations Bullpen Readiness.

The contracts in this module are backend-domain objects only. They preserve
team-level readiness output and enforce the governance boundary required by
the V3 readiness planning documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


CAPABILITY = 'team_operations_bullpen_readiness'
SCOPE = 'team_bullpen_readiness'
CONTRACT = 'team_operations_bullpen_readiness_api_contract'
CONTRACT_VERSION = 'v3_phase_4'
NO_RANKING_APPLIED = False
NO_SELECTION_MADE = False

CONTRACT_STATES = frozenset(
    {
        'available',
        'degraded',
        'refused',
        'unavailable',
    }
)

READINESS_STATUSES = {
    'operationally_stable': 'Operationally Stable',
    'operationally_constrained': 'Operationally Constrained',
    'operationally_stressed': 'Operationally Stressed',
    'data_limited': 'Data Limited',
    'refused': 'Refused',
}
ALLOWED_READINESS_STATUS_CODES = frozenset(READINESS_STATUSES)

ALLOWED_CONSTRAINT_CATEGORIES = frozenset(
    {
        'workload',
        'availability',
        'freshness',
        'trust',
        'coverage',
        'refusal',
        'governance',
    }
)
ALLOWED_CONSTRAINT_SEVERITIES = frozenset(
    {
        'informational',
        'caution',
        'blocking',
    }
)
ALLOWED_PRESSURE_STATES = frozenset({'low', 'moderate', 'elevated', 'unknown'})
ALLOWED_COVERAGE_STATES = frozenset({'covered', 'partial', 'missing', 'unknown'})
ALLOWED_CONFIDENCE_VALUES = frozenset({'high', 'medium', 'low', 'unknown'})
ALLOWED_DATA_STATES = frozenset(
    {'fresh', 'stale', 'missing', 'incomplete', 'historical', 'unknown'}
)
ALLOWED_FRESHNESS_STATES = frozenset(
    {'current', 'stale', 'missing', 'incomplete', 'historical', 'unknown'}
)
ALLOWED_FAIL_CLOSED_STATES = frozenset(
    {
        'not_failed_closed',
        'degraded_safe_output',
        'refused',
        'critical_failure',
    }
)

REQUIRED_TRUST_METADATA_FIELDS = frozenset(
    {
        'confidence',
        'confidence_reasons',
        'data_state',
        'source_evidence_state',
        'governance_state',
        'generated_at',
        'limitations',
        'explanations',
        'refusal_reasons',
        'trust_validation_errors',
        'ranking_applied',
        'selection_made',
    }
)

REQUIRED_FRESHNESS_FIELDS = frozenset(
    {
        'freshness_state',
        'data_through',
        'latest_workload_date',
        'last_successful_sync',
        'latest_sync_status',
        'latest_fatigue_calculated_at',
        'generated_at',
        'stale_warning',
        'missing_data_warning',
        'limitations',
    }
)

FORBIDDEN_TEAM_OPERATIONS_FIELD_NAMES = frozenset(
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
        'use_this_pitcher',
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
        'injury_risk_prediction',
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

ALLOWED_GOVERNANCE_FIELD_NAMES = frozenset(
    {
        'ranking_applied',
        'selection_made',
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


def _field_name_is_forbidden(field_name: str) -> bool:
    normalized = field_name.lower()
    if normalized in ALLOWED_GOVERNANCE_FIELD_NAMES:
        return False
    return normalized in FORBIDDEN_TEAM_OPERATIONS_FIELD_NAMES


def team_operations_governance_errors(
    payload: Any,
    path: str = 'payload',
) -> list[str]:
    """Return forbidden Team Operations governance fields in a payload."""

    errors: list[str] = []

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            key_path = f'{path}.{key_text}'
            if _field_name_is_forbidden(key_text):
                errors.append(
                    f'{key_path} uses a forbidden Team Operations field name.'
                )
            errors.extend(team_operations_governance_errors(value, key_path))
        return errors

    if isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            errors.extend(
                team_operations_governance_errors(item, f'{path}[{index}]')
            )

    return errors


def require_team_operations_governance_safe(payload: Any) -> None:
    errors = team_operations_governance_errors(payload)
    if errors:
        raise ValueError(' '.join(errors))


def trust_metadata_validation_errors(
    payload: Mapping[str, Any] | None,
    path: str = 'trust_metadata',
) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, Mapping):
        return [f'{path} is missing.']

    missing = sorted(REQUIRED_TRUST_METADATA_FIELDS.difference(payload.keys()))
    for field_name in missing:
        errors.append(f'{path} is missing required field {field_name}.')

    if payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        errors.append(f'{path}.ranking_applied must be false.')
    if payload.get('selection_made') is not NO_SELECTION_MADE:
        errors.append(f'{path}.selection_made must be false.')
    if payload.get('confidence') not in ALLOWED_CONFIDENCE_VALUES:
        errors.append(f'{path}.confidence uses unsupported vocabulary.')
    if payload.get('data_state') not in ALLOWED_DATA_STATES:
        errors.append(f'{path}.data_state uses unsupported vocabulary.')

    for field_name in (
        'confidence_reasons',
        'limitations',
        'explanations',
        'refusal_reasons',
        'trust_validation_errors',
    ):
        if field_name in payload and not isinstance(payload[field_name], list):
            errors.append(f'{path}.{field_name} must be represented as a list.')

    return errors


def freshness_validation_errors(
    payload: Mapping[str, Any] | None,
    path: str = 'freshness',
) -> list[str]:
    errors: list[str] = []

    if not isinstance(payload, Mapping):
        return [f'{path} is missing.']

    missing = sorted(REQUIRED_FRESHNESS_FIELDS.difference(payload.keys()))
    for field_name in missing:
        errors.append(f'{path} is missing required field {field_name}.')

    if payload.get('freshness_state') not in ALLOWED_FRESHNESS_STATES:
        errors.append(f'{path}.freshness_state uses unsupported vocabulary.')

    if 'limitations' in payload and not isinstance(payload['limitations'], list):
        errors.append(f'{path}.limitations must be represented as a list.')

    return errors


@dataclass(frozen=True)
class TeamOperationsTrustMetadata:
    confidence: str
    confidence_reasons: tuple[Any, ...] = field(default_factory=tuple)
    data_state: str = 'unknown'
    source_evidence_state: str = 'missing'
    governance_state: str = 'compliant'
    generated_at: str | None = None
    limitations: tuple[Any, ...] = field(default_factory=tuple)
    explanations: tuple[Any, ...] = field(default_factory=tuple)
    refusal_reasons: tuple[Any, ...] = field(default_factory=tuple)
    trust_validation_errors: tuple[Any, ...] = field(default_factory=tuple)
    ranking_applied: bool = NO_RANKING_APPLIED
    selection_made: bool = NO_SELECTION_MADE

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> 'TeamOperationsTrustMetadata':
        return cls(
            confidence=str(payload.get('confidence', 'unknown')),
            confidence_reasons=_tuple_value(payload.get('confidence_reasons')),
            data_state=str(payload.get('data_state', 'unknown')),
            source_evidence_state=str(
                payload.get('source_evidence_state', 'missing')
            ),
            governance_state=str(payload.get('governance_state', 'compliant')),
            generated_at=payload.get('generated_at'),
            limitations=_tuple_value(payload.get('limitations')),
            explanations=_tuple_value(payload.get('explanations')),
            refusal_reasons=_tuple_value(payload.get('refusal_reasons')),
            trust_validation_errors=_tuple_value(
                payload.get('trust_validation_errors')
            ),
            ranking_applied=payload.get('ranking_applied', NO_RANKING_APPLIED),
            selection_made=payload.get('selection_made', NO_SELECTION_MADE),
        )

    def __post_init__(self):
        if self.ranking_applied is not NO_RANKING_APPLIED:
            raise ValueError('ranking_applied must be false.')
        if self.selection_made is not NO_SELECTION_MADE:
            raise ValueError('selection_made must be false.')
        if self.confidence not in ALLOWED_CONFIDENCE_VALUES:
            raise ValueError('confidence uses unsupported vocabulary.')
        if self.data_state not in ALLOWED_DATA_STATES:
            raise ValueError('data_state uses unsupported vocabulary.')

    def to_dict(self) -> dict[str, Any]:
        payload = {
            'scope': SCOPE,
            'capability': CAPABILITY,
            'confidence': self.confidence,
            'confidence_reasons': list(self.confidence_reasons),
            'data_state': self.data_state,
            'source_evidence_state': self.source_evidence_state,
            'governance_state': self.governance_state,
            'generated_at': self.generated_at,
            'limitations': list(self.limitations),
            'explanations': list(self.explanations),
            'refusal_reasons': list(self.refusal_reasons),
            'trust_validation_errors': list(self.trust_validation_errors),
            'ranking_applied': self.ranking_applied,
            'selection_made': self.selection_made,
        }
        require_team_operations_governance_safe(payload)
        return payload


@dataclass(frozen=True)
class TeamOperationsFreshnessMetadata:
    freshness_state: str
    data_through: str | None = None
    latest_workload_date: str | None = None
    last_successful_sync: str | None = None
    latest_sync_status: str | None = None
    latest_fatigue_calculated_at: str | None = None
    generated_at: str | None = None
    stale_warning: str | None = None
    missing_data_warning: str | None = None
    limitations: tuple[Any, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> 'TeamOperationsFreshnessMetadata':
        return cls(
            freshness_state=str(payload.get('freshness_state', 'unknown')),
            data_through=payload.get('data_through'),
            latest_workload_date=payload.get('latest_workload_date'),
            last_successful_sync=payload.get('last_successful_sync'),
            latest_sync_status=payload.get('latest_sync_status'),
            latest_fatigue_calculated_at=payload.get('latest_fatigue_calculated_at'),
            generated_at=payload.get('generated_at'),
            stale_warning=payload.get('stale_warning'),
            missing_data_warning=payload.get('missing_data_warning'),
            limitations=_tuple_value(payload.get('limitations')),
        )

    def __post_init__(self):
        if self.freshness_state not in ALLOWED_FRESHNESS_STATES:
            raise ValueError('freshness_state uses unsupported vocabulary.')

    def to_dict(self) -> dict[str, Any]:
        return {
            'freshness_state': self.freshness_state,
            'data_through': self.data_through,
            'latest_workload_date': self.latest_workload_date,
            'last_successful_sync': self.last_successful_sync,
            'latest_sync_status': self.latest_sync_status,
            'latest_fatigue_calculated_at': self.latest_fatigue_calculated_at,
            'generated_at': self.generated_at,
            'stale_warning': self.stale_warning,
            'missing_data_warning': self.missing_data_warning,
            'limitations': list(self.limitations),
        }


@dataclass(frozen=True)
class TeamOperationsRefusalMetadata:
    refused: bool = False
    refusal_id: str | None = None
    reason: str | None = None
    message: str | None = None
    applies_to: str | None = None
    recovery_note: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> 'TeamOperationsRefusalMetadata':
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            refused=bool(payload.get('refused', False)),
            refusal_id=payload.get('refusal_id'),
            reason=payload.get('reason'),
            message=payload.get('message'),
            applies_to=payload.get('applies_to'),
            recovery_note=payload.get('recovery_note'),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'refused': self.refused,
            'refusal_id': self.refusal_id,
            'reason': self.reason,
            'message': self.message,
            'applies_to': self.applies_to,
            'recovery_note': self.recovery_note,
        }


@dataclass(frozen=True)
class TeamOperationsFailClosedMetadata:
    failed_closed: bool = False
    state: str = 'not_failed_closed'
    reason_codes: tuple[Any, ...] = field(default_factory=tuple)
    critical_failure: bool = False
    safe_partial_output_allowed: bool = True

    def __post_init__(self):
        if self.state not in ALLOWED_FAIL_CLOSED_STATES:
            raise ValueError('fail-closed state uses unsupported vocabulary.')

    def to_dict(self) -> dict[str, Any]:
        return {
            'failed_closed': self.failed_closed,
            'state': self.state,
            'reason_codes': list(self.reason_codes),
            'critical_failure': self.critical_failure,
            'safe_partial_output_allowed': self.safe_partial_output_allowed,
        }
