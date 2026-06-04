"""Team Operations Readiness adapter for V4 explanations.

This module builds V4 explanation objects from existing Team Operations
Bullpen Readiness payloads. It does not calculate readiness, change readiness
status assignment, mutate API responses, or integrate with frontend surfaces.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from explanations.builders import (
    build_evidence_item,
    build_explanation,
    build_limitation,
    build_numeric_evidence,
)
from explanations.contracts import (
    ALLOWED_EXPLANATION_SCOPES,
    V4Explanation,
    validate_explanation_scope,
)
from team_operations.contracts import (
    ALLOWED_READINESS_STATUS_CODES,
    CONTRACT as READINESS_CONTRACT,
    NO_RANKING_APPLIED,
    NO_SELECTION_MADE,
    require_team_operations_governance_safe,
)


READINESS_EXPLANATION_SOURCE = 'team_operations_bullpen_readiness'
READINESS_EXPLANATION_CONTRACT = READINESS_CONTRACT
READINESS_EXPLANATION_CERTIFICATION_STATUS = (
    'certified_with_non_blocking_operational_gaps'
)

SUPPORTED_READINESS_EXPLANATION_SCOPES = frozenset(
    {
        'readiness_state',
        'workload_state',
        'coverage_state',
        'freshness_state',
        'trust_state',
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
    'historical': 'historical',
    'unknown': 'unknown',
}

_NUMERIC_EVIDENCE_GROUPS = (
    (
        'workload_pressure',
        'workload',
        (
            ('low_count', 'Low workload count', 'pitchers'),
            ('moderate_count', 'Moderate workload count', 'pitchers'),
            ('elevated_count', 'Elevated workload count', 'pitchers'),
            ('unknown_count', 'Unknown workload count', 'pitchers'),
        ),
    ),
    (
        'availability_distribution',
        'availability',
        (
            ('available', 'Available inventory count', 'pitchers'),
            ('monitor', 'Monitor inventory count', 'pitchers'),
            ('limited', 'Limited inventory count', 'pitchers'),
            ('avoid', 'Avoid inventory count', 'pitchers'),
            ('unavailable', 'Unavailable inventory count', 'pitchers'),
            ('unknown', 'Unknown availability count', 'pitchers'),
            ('total', 'Total availability inventory count', 'pitchers'),
        ),
    ),
    (
        'coverage_inventory',
        'coverage',
        (
            ('active_pitcher_count', 'Active pitcher count', 'pitchers'),
            ('current_workload_data_count', 'Current workload data count', 'pitchers'),
            ('missing_workload_data_count', 'Missing workload data count', 'pitchers'),
            ('availability_covered_count', 'Availability covered count', 'pitchers'),
            ('availability_missing_count', 'Availability missing count', 'pitchers'),
        ),
    ),
    (
        'handedness_coverage',
        'coverage',
        (
            ('left_handed_count', 'Left handed count', 'pitchers'),
            ('right_handed_count', 'Right handed count', 'pitchers'),
            ('unknown_count', 'Unknown handedness count', 'pitchers'),
        ),
    ),
)


def _required_mapping(
    value: Mapping[str, Any] | None,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f'{field_name} must be a readiness mapping.')
    return value


def _optional_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f'{field_name} must be a mapping when provided.')
    return value


def _sequence(value: Any, field_name: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise ValueError(f'{field_name} must be a sequence when provided.')


def _readiness_status(readiness_payload: Mapping[str, Any]) -> str:
    readiness = _required_mapping(readiness_payload.get('readiness'), 'readiness')
    status_code = readiness.get('status_code')
    if status_code not in ALLOWED_READINESS_STATUS_CODES:
        raise ValueError('readiness status uses unsupported vocabulary.')
    return str(status_code)


def _scope(scope: str) -> str:
    resolved = validate_explanation_scope(scope)
    if resolved not in SUPPORTED_READINESS_EXPLANATION_SCOPES:
        raise ValueError('readiness explanation scope is not supported.')
    return resolved


def _subject_reference(
    readiness_payload: Mapping[str, Any],
    explicit_subject_id: str | int | None,
) -> tuple[str, str]:
    if explicit_subject_id is not None and str(explicit_subject_id).strip():
        return 'bullpen', str(explicit_subject_id).strip()

    team = _optional_mapping(readiness_payload.get('team'), 'team')
    team_id = team.get('team_id')
    if team_id is not None and str(team_id).strip():
        return 'bullpen', f'team:{str(team_id).strip()}:bullpen'

    team_abbreviation = team.get('team_abbreviation')
    if team_abbreviation is not None and str(team_abbreviation).strip():
        return 'bullpen', f'team:{str(team_abbreviation).strip()}:bullpen'

    return 'system', 'team_operations_bullpen_readiness'


def _require_safe_readiness_payload(readiness_payload: Mapping[str, Any]) -> None:
    if readiness_payload.get('ranking_applied') is not NO_RANKING_APPLIED:
        raise ValueError('ranking_applied must be false for readiness explanations.')
    if readiness_payload.get('selection_made') is not NO_SELECTION_MADE:
        raise ValueError('selection_made must be false for readiness explanations.')

    trust_metadata = _optional_mapping(
        readiness_payload.get('trust_metadata'),
        'trust_metadata',
    )
    if trust_metadata.get('ranking_applied') is not NO_RANKING_APPLIED:
        raise ValueError('trust_metadata.ranking_applied must be false.')
    if trust_metadata.get('selection_made') is not NO_SELECTION_MADE:
        raise ValueError('trust_metadata.selection_made must be false.')

    require_team_operations_governance_safe(readiness_payload)


def _freshness_status(freshness: Mapping[str, Any]) -> str:
    status = str(freshness.get('freshness_state') or 'unknown')
    if status not in {
        'current',
        'stale',
        'missing',
        'incomplete',
        'historical',
        'unknown',
    }:
        raise ValueError('freshness_state uses unsupported vocabulary.')
    return status


def _confidence_level(trust_metadata: Mapping[str, Any]) -> str:
    confidence = str(trust_metadata.get('confidence') or 'unknown')
    if confidence not in _CONFIDENCE_TO_TRUST:
        raise ValueError('trust confidence uses unsupported vocabulary.')
    return confidence


def _data_state(trust_metadata: Mapping[str, Any]) -> str:
    data_state = str(trust_metadata.get('data_state') or 'unknown')
    if data_state not in _DATA_STATE_TO_FRESHNESS:
        raise ValueError('trust data_state uses unsupported vocabulary.')
    return data_state


def _freshness_reference(freshness: Mapping[str, Any]) -> dict[str, Any]:
    status = _freshness_status(freshness)
    freshness_failure = None
    if status != 'current':
        freshness_failure = f'readiness_{status}_freshness'

    return {
        'status': status,
        'data_through': freshness.get('data_through')
        or freshness.get('latest_workload_date'),
        'last_sync_at': freshness.get('last_successful_sync'),
        'source_updated_at': freshness.get('latest_fatigue_calculated_at')
        or freshness.get('generated_at'),
        'freshness_failure': freshness_failure,
        'summary': _freshness_summary(status),
    }


def _freshness_summary(status: str) -> str:
    if status == 'current':
        return 'Readiness explanation uses current Team Operations freshness metadata.'
    if status == 'stale':
        return 'Readiness explanation is limited by stale source freshness.'
    if status == 'missing':
        return 'Readiness explanation is limited by missing freshness metadata.'
    if status == 'incomplete':
        return 'Readiness explanation is limited by incomplete freshness metadata.'
    if status == 'historical':
        return 'Readiness explanation is limited by historical freshness metadata.'
    return 'Readiness explanation freshness is unknown.'


def _trust_reference(trust_metadata: Mapping[str, Any]) -> dict[str, Any]:
    confidence = _confidence_level(trust_metadata)
    data_state = _data_state(trust_metadata)
    governance_state = str(trust_metadata.get('governance_state') or 'unknown')
    validation_errors = _sequence(
        trust_metadata.get('trust_validation_errors'),
        'trust_validation_errors',
    )

    status = _CONFIDENCE_TO_TRUST[confidence]
    if governance_state == 'refused' or validation_errors:
        status = 'failed'
    elif data_state != 'fresh' and status == 'trusted':
        status = 'limited'

    trust_failure = None
    if status != 'trusted':
        trust_failure = f'readiness_{status}_trust'

    return {
        'status': status,
        'source': READINESS_EXPLANATION_SOURCE,
        'contract': READINESS_EXPLANATION_CONTRACT,
        'certification_status': READINESS_EXPLANATION_CERTIFICATION_STATUS,
        'trust_failure': trust_failure,
        'summary': 'Trust reflects existing Team Operations metadata and confidence.',
    }


def _confidence_reference(trust_metadata: Mapping[str, Any]) -> dict[str, Any]:
    confidence = _confidence_level(trust_metadata)
    return {
        'level': confidence,
        'summary': (
            'Explanation confidence mirrors the existing Team Operations '
            'confidence metadata.'
        ),
    }


def _state_explained(
    *,
    scope: str,
    readiness_payload: Mapping[str, Any],
    trust: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> str:
    if scope == 'readiness_state':
        return _readiness_status(readiness_payload)
    if scope == 'workload_state':
        workload = _optional_mapping(
            readiness_payload.get('workload_pressure'),
            'workload_pressure',
        )
        return str(
            workload.get('pressure_state_code')
            or workload.get('pressure_state')
            or 'unknown'
        )
    if scope == 'coverage_state':
        coverage = _optional_mapping(
            readiness_payload.get('coverage_inventory'),
            'coverage_inventory',
        )
        handedness = _optional_mapping(
            readiness_payload.get('handedness_coverage'),
            'handedness_coverage',
        )
        return (
            f"workload:{coverage.get('coverage_state', 'unknown')};"
            f"handedness:{handedness.get('coverage_state', 'unknown')}"
        )
    if scope == 'freshness_state':
        return _freshness_status(freshness)
    if scope == 'trust_state':
        return _trust_reference(trust)['status']
    raise ValueError('readiness explanation scope is not supported.')


def _summary(scope: str) -> str:
    if scope == 'workload_state':
        return 'This workload state reflects team-level workload pressure evidence.'
    if scope == 'coverage_state':
        return 'This coverage state reflects workload, availability, and handedness coverage evidence.'
    if scope == 'freshness_state':
        return 'This freshness state reflects source sync and workload-recency evidence.'
    if scope == 'trust_state':
        return 'This trust state reflects Team Operations trust metadata and confidence evidence.'
    return (
        'This readiness state reflects workload, freshness, coverage, trust, '
        'and limitation evidence.'
    )


def _constraint_categories(readiness_payload: Mapping[str, Any]) -> set[str]:
    categories: set[str] = set()
    for constraint in _sequence(readiness_payload.get('constraints'), 'constraints'):
        if isinstance(constraint, Mapping):
            category = constraint.get('category')
            if category:
                categories.add(str(category))
    return categories


def _reason_codes(
    *,
    readiness_payload: Mapping[str, Any],
    trust: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> tuple[str, ...]:
    readiness_status = _readiness_status(readiness_payload)
    workload = _optional_mapping(
        readiness_payload.get('workload_pressure'),
        'workload_pressure',
    )
    coverage = _optional_mapping(
        readiness_payload.get('coverage_inventory'),
        'coverage_inventory',
    )
    handedness = _optional_mapping(
        readiness_payload.get('handedness_coverage'),
        'handedness_coverage',
    )
    categories = _constraint_categories(readiness_payload)
    freshness_status = _freshness_status(freshness)
    confidence = _confidence_level(trust)
    data_state = _data_state(trust)
    validation_errors = _sequence(
        trust.get('trust_validation_errors'),
        'trust_validation_errors',
    )

    codes: list[str] = []
    if readiness_status in {'operationally_constrained', 'operationally_stressed', 'data_limited', 'refused'}:
        codes.append('READINESS_DEGRADED_BY_LIMITATIONS')
    if (
        workload.get('pressure_state') == 'elevated'
        or workload.get('elevated_count', 0)
        or 'workload' in categories
    ):
        codes.append('WORKLOAD_RECENT_USAGE_ELEVATED')
    if freshness_status != 'current' or 'freshness' in categories:
        codes.append('FRESHNESS_STALE_SOURCE')
    if (
        coverage.get('coverage_state') in {'partial', 'missing', 'unknown'}
        or handedness.get('coverage_state') in {'partial', 'missing', 'unknown'}
        or 'coverage' in categories
    ):
        codes.append('COVERAGE_PARTIAL')
    if (
        confidence in {'medium', 'low', 'unknown'}
        or data_state != 'fresh'
        or validation_errors
        or 'trust' in categories
    ):
        codes.append('TRUST_LIMITED')

    return _dedupe(codes)


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return tuple(deduped)


def _trust_status_for_evidence(trust: Mapping[str, Any]) -> str:
    return _trust_reference(trust)['status']


def _base_evidence(
    *,
    readiness_payload: Mapping[str, Any],
    freshness: Mapping[str, Any],
    trust: Mapping[str, Any],
    freshness_ref: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    readiness = _required_mapping(readiness_payload.get('readiness'), 'readiness')
    evidence = [
        build_evidence_item(
            evidence_type='readiness_status',
            label='Readiness status',
            value=readiness.get('status'),
            unit='status',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_readiness_state',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_status_code',
            label='Readiness status code',
            value=readiness.get('status_code'),
            unit='status_code',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_readiness_state',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_contract_state',
            label='Readiness contract state',
            value=readiness_payload.get('contract_state'),
            unit='state',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_output_boundary',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_basis',
            label='Readiness basis',
            value=list(readiness.get('basis') or ()),
            unit='sources',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_input_scope',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_freshness_state',
            label='Freshness state',
            value=_freshness_status(freshness),
            unit='state',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_freshness_boundary',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_trust_confidence',
            label='Trust confidence',
            value=_confidence_level(trust),
            unit='level',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_confidence_boundary',
        ).to_dict(),
        build_evidence_item(
            evidence_type='readiness_trust_data_state',
            label='Trust data state',
            value=_data_state(trust),
            unit='state',
            source=READINESS_EXPLANATION_SOURCE,
            freshness=freshness_ref,
            trust_status=trust_status,
            impact='explains_trust_boundary',
        ).to_dict(),
    ]
    return evidence


def _state_evidence(
    readiness_payload: Mapping[str, Any],
    *,
    freshness_ref: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []

    workload = _optional_mapping(
        readiness_payload.get('workload_pressure'),
        'workload_pressure',
    )
    if workload:
        evidence.append(
            build_evidence_item(
                evidence_type='workload_pressure_state',
                label='Workload pressure state',
                value=workload.get('pressure_state'),
                unit='state',
                source=READINESS_EXPLANATION_SOURCE,
                freshness=freshness_ref,
                trust_status=trust_status,
                impact='explains_workload_state',
            ).to_dict()
        )

    coverage = _optional_mapping(
        readiness_payload.get('coverage_inventory'),
        'coverage_inventory',
    )
    if coverage:
        evidence.append(
            build_evidence_item(
                evidence_type='coverage_inventory_state',
                label='Coverage inventory state',
                value=coverage.get('coverage_state'),
                unit='state',
                source=READINESS_EXPLANATION_SOURCE,
                freshness=freshness_ref,
                trust_status=trust_status,
                impact='explains_coverage_state',
            ).to_dict()
        )

    handedness = _optional_mapping(
        readiness_payload.get('handedness_coverage'),
        'handedness_coverage',
    )
    if handedness:
        evidence.append(
            build_evidence_item(
                evidence_type='handedness_coverage_state',
                label='Handedness coverage state',
                value=handedness.get('coverage_state'),
                unit='state',
                source=READINESS_EXPLANATION_SOURCE,
                freshness=freshness_ref,
                trust_status=trust_status,
                impact='explains_coverage_state',
            ).to_dict()
        )

    return evidence


def _numeric_evidence(
    readiness_payload: Mapping[str, Any],
    *,
    freshness_ref: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for group_name, category, fields in _NUMERIC_EVIDENCE_GROUPS:
        group = _optional_mapping(readiness_payload.get(group_name), group_name)
        if not group:
            continue
        for field_name, label, unit in fields:
            value = group.get(field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            evidence.append(
                build_numeric_evidence(
                    evidence_type=f'{group_name}_{field_name}',
                    label=label,
                    value=value,
                    unit=unit,
                    source=READINESS_EXPLANATION_SOURCE,
                    freshness=freshness_ref,
                    trust_status=trust_status,
                    impact=f'explains_{category}_state',
                ).to_dict()
            )
    return evidence


def _constraint_evidence(
    readiness_payload: Mapping[str, Any],
    *,
    freshness_ref: Mapping[str, Any],
    trust_status: str,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for constraint in _sequence(readiness_payload.get('constraints'), 'constraints'):
        if not isinstance(constraint, Mapping):
            continue
        constraint_id = constraint.get('constraint_id')
        if not constraint_id:
            continue
        evidence.append(
            build_evidence_item(
                evidence_type=f"readiness_constraint_{constraint_id}",
                label=f"Readiness constraint {constraint_id}",
                value={
                    'category': constraint.get('category'),
                    'severity': constraint.get('severity'),
                    'affected_area': constraint.get('affected_area'),
                    'count': constraint.get('count'),
                    'message': constraint.get('message'),
                    'evidence': list(constraint.get('evidence') or ()),
                },
                unit='constraint',
                source=READINESS_EXPLANATION_SOURCE,
                freshness=freshness_ref,
                trust_status=trust_status,
                impact='explains_readiness_limitation',
            ).to_dict()
        )
    return evidence


def _supporting_evidence(
    *,
    readiness_payload: Mapping[str, Any],
    freshness: Mapping[str, Any],
    trust: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    freshness_ref = _freshness_reference(freshness)
    trust_status = _trust_status_for_evidence(trust)
    return tuple(
        [
            *_base_evidence(
                readiness_payload=readiness_payload,
                freshness=freshness,
                trust=trust,
                freshness_ref=freshness_ref,
                trust_status=trust_status,
            ),
            *_state_evidence(
                readiness_payload,
                freshness_ref=freshness_ref,
                trust_status=trust_status,
            ),
            *_numeric_evidence(
                readiness_payload,
                freshness_ref=freshness_ref,
                trust_status=trust_status,
            ),
            *_constraint_evidence(
                readiness_payload,
                freshness_ref=freshness_ref,
                trust_status=trust_status,
            ),
        ]
    )


def _limitation_type_for(text: str) -> str:
    normalized = text.lower()
    if 'stale' in normalized or 'freshness' in normalized:
        return 'stale_data'
    if 'missing' in normalized or 'unavailable' in normalized or 'withheld' in normalized:
        return 'missing_data'
    if 'partial' in normalized or 'incomplete' in normalized or 'coverage' in normalized or 'handedness' in normalized:
        return 'partial_coverage'
    if 'confidence' in normalized or 'trust' in normalized:
        return 'limited_confidence'
    return 'insufficient_context'


def _limitation_severity(limitation_type: str, raw_severity: str | None = None) -> str:
    if raw_severity == 'blocking':
        return 'blocking'
    if limitation_type in {'missing_data', 'stale_data'}:
        return 'degrades_confidence'
    if limitation_type in {'partial_coverage', 'limited_confidence'}:
        return 'limits_confidence'
    return raw_severity or 'informational'


def _limitations(
    *,
    readiness_payload: Mapping[str, Any],
    trust: Mapping[str, Any],
    freshness: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    limitations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_limitation(
        limitation_type: str,
        summary: str,
        *,
        raw_severity: str | None = None,
        requires_refusal: bool = False,
    ) -> None:
        summary = str(summary).strip()
        if not summary:
            return
        key = (limitation_type, summary)
        if key in seen:
            return
        seen.add(key)
        limitations.append(
            build_limitation(
                limitation_type=limitation_type,
                severity=_limitation_severity(limitation_type, raw_severity),
                summary=summary,
                affected_scopes=('readiness_state',),
                requires_refusal=requires_refusal,
            ).to_dict()
        )

    for raw_limitation in _sequence(readiness_payload.get('limitations'), 'limitations'):
        if isinstance(raw_limitation, Mapping):
            summary = raw_limitation.get('message') or raw_limitation.get('summary')
            raw_severity = raw_limitation.get('severity')
        else:
            summary = raw_limitation
            raw_severity = None
        limitation_type = _limitation_type_for(str(summary))
        add_limitation(
            limitation_type,
            str(summary),
            raw_severity=str(raw_severity) if raw_severity else None,
            requires_refusal=str(raw_severity) == 'blocking',
        )

    freshness_status = _freshness_status(freshness)
    if freshness_status == 'stale':
        add_limitation(
            'stale_data',
            'Readiness explanation is limited by stale freshness metadata.',
        )
    elif freshness_status in {'missing', 'unknown'}:
        add_limitation(
            'missing_data',
            'Readiness explanation is limited by missing freshness metadata.',
        )
    elif freshness_status in {'incomplete', 'historical'}:
        add_limitation(
            'partial_coverage',
            'Readiness explanation is limited by incomplete freshness metadata.',
        )

    trust_ref = _trust_reference(trust)
    if trust_ref['status'] == 'limited':
        add_limitation(
            'limited_confidence',
            'Readiness explanation confidence is limited by trust metadata.',
        )
    elif trust_ref['status'] in {'failed', 'unknown'}:
        add_limitation(
            'limited_confidence',
            'Readiness explanation trust status limits confidence.',
        )

    return tuple(limitations)


def build_readiness_explanation(
    readiness_payload: Mapping[str, Any],
    *,
    subject_id: str | int | None = None,
    scope: str = 'readiness_state',
    generated_at: str | None = None,
) -> V4Explanation:
    """Build a deterministic V4 explanation from a Team Operations payload."""

    readiness_payload = _required_mapping(readiness_payload, 'readiness_payload')
    resolved_scope = _scope(scope)
    if resolved_scope not in ALLOWED_EXPLANATION_SCOPES:
        raise ValueError('readiness explanation scope uses unsupported vocabulary.')
    _require_safe_readiness_payload(readiness_payload)
    _readiness_status(readiness_payload)

    trust = _required_mapping(
        readiness_payload.get('trust_metadata'),
        'trust_metadata',
    )
    freshness = _required_mapping(readiness_payload.get('freshness'), 'freshness')
    subject_type, resolved_subject_id = _subject_reference(
        readiness_payload,
        subject_id,
    )
    resolved_generated_at = generated_at or readiness_payload.get('generated_at')

    return build_explanation(
        scope=resolved_scope,
        subject_type=subject_type,
        subject_id=resolved_subject_id,
        state_explained=_state_explained(
            scope=resolved_scope,
            readiness_payload=readiness_payload,
            trust=trust,
            freshness=freshness,
        ),
        summary=_summary(resolved_scope),
        reason_codes=_reason_codes(
            readiness_payload=readiness_payload,
            trust=trust,
            freshness=freshness,
        ),
        supporting_evidence=_supporting_evidence(
            readiness_payload=readiness_payload,
            freshness=freshness,
            trust=trust,
        ),
        limitations=_limitations(
            readiness_payload=readiness_payload,
            trust=trust,
            freshness=freshness,
        ),
        freshness=_freshness_reference(freshness),
        trust=_trust_reference(trust),
        confidence=_confidence_reference(trust),
        generated_at=resolved_generated_at,
    )


def serialize_readiness_explanation(
    readiness_payload: Mapping[str, Any],
    *,
    subject_id: str | int | None = None,
    scope: str = 'readiness_state',
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build and serialize a deterministic V4 readiness explanation."""

    return build_readiness_explanation(
        readiness_payload,
        subject_id=subject_id,
        scope=scope,
        generated_at=generated_at,
    ).to_dict()
