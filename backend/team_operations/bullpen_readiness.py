"""Team Operations Bullpen Readiness domain assembly."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from team_operations.contracts import (
    ALLOWED_READINESS_STATUS_CODES,
    CAPABILITY,
    CONTRACT,
    CONTRACT_VERSION,
    NO_RANKING_APPLIED,
    NO_SELECTION_MADE,
    READINESS_STATUSES,
    SCOPE,
    TeamOperationsFailClosedMetadata,
    TeamOperationsFreshnessMetadata,
    TeamOperationsRefusalMetadata,
    TeamOperationsTrustMetadata,
    freshness_validation_errors,
    require_team_operations_governance_safe,
    trust_metadata_validation_errors,
)


READINESS_BASIS = (
    'availability_distribution',
    'workload_pressure',
    'freshness',
    'trust_metadata',
)

BASELINE_LIMITATIONS = (
    {
        'limitation_id': 'public_workload_data_only',
        'message': 'Readiness is based on public workload data tracked by BaseballOS.',
        'severity': 'informational',
        'applies_to': 'readiness',
    },
    {
        'limitation_id': 'not_medical_information',
        'message': 'Readiness is not injury or medical information.',
        'severity': 'informational',
        'applies_to': 'readiness',
    },
    {
        'limitation_id': 'not_performance_forecast',
        'message': 'Readiness is not a performance forecast.',
        'severity': 'informational',
        'applies_to': 'readiness',
    },
    {
        'limitation_id': 'no_manager_intent_or_warmup_state',
        'message': 'Manager intent and bullpen warm-up state are not available.',
        'severity': 'informational',
        'applies_to': 'readiness',
    },
    {
        'limitation_id': 'user_decision_responsibility',
        'message': 'The user remains responsible for baseball decisions.',
        'severity': 'informational',
        'applies_to': 'readiness',
    },
)


def assemble_bullpen_readiness(
    *,
    team: Mapping[str, Any] | None = None,
    pitcher_records: Iterable[Mapping[str, Any]] | None = None,
    trust_metadata: Mapping[str, Any] | None = None,
    freshness: Mapping[str, Any] | None = None,
    refusal: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a deterministic team-level bullpen readiness payload."""

    refusal_metadata = TeamOperationsRefusalMetadata.from_mapping(refusal)
    generated_at = _resolve_generated_at(generated_at, freshness, trust_metadata)

    if refusal_metadata.refused:
        return _fail_closed_payload(
            reason_code=refusal_metadata.reason or 'refusal_required',
            refusal_id=refusal_metadata.refusal_id or 'refusal_required',
            message=refusal_metadata.message
            or 'Readiness output is refused by supplied refusal metadata.',
            team=team,
            trust_metadata=trust_metadata,
            freshness=freshness,
            generated_at=generated_at,
        )

    trust_errors = trust_metadata_validation_errors(trust_metadata)
    if trust_errors:
        return _fail_closed_payload(
            reason_code='trust_metadata_missing'
            if not isinstance(trust_metadata, Mapping)
            else 'trust_metadata_incomplete',
            refusal_id='missing_trust_metadata'
            if not isinstance(trust_metadata, Mapping)
            else 'incomplete_trust_metadata',
            message='Readiness output is refused because required trust metadata is missing.',
            team=team,
            trust_metadata=trust_metadata,
            freshness=freshness,
            generated_at=generated_at,
            validation_errors=trust_errors,
        )

    freshness_errors = freshness_validation_errors(freshness)
    if freshness_errors:
        return _fail_closed_payload(
            reason_code='freshness_metadata_missing'
            if not isinstance(freshness, Mapping)
            else 'freshness_metadata_incomplete',
            refusal_id='missing_freshness_metadata'
            if not isinstance(freshness, Mapping)
            else 'incomplete_freshness_metadata',
            message='Readiness output is refused because required freshness metadata is missing.',
            team=team,
            trust_metadata=trust_metadata,
            freshness=freshness,
            generated_at=generated_at,
            validation_errors=freshness_errors,
        )

    trust = TeamOperationsTrustMetadata.from_mapping(trust_metadata)
    freshness_metadata = TeamOperationsFreshnessMetadata.from_mapping(freshness)
    records = tuple(_normalize_pitcher_record(record) for record in pitcher_records or ())

    availability_distribution = _availability_distribution(records)
    workload_pressure = _workload_pressure(records, freshness_metadata)
    coverage_inventory = _coverage_inventory(records)
    handedness_coverage = _handedness_coverage(records)
    constraints = _constraints(
        availability_distribution,
        workload_pressure,
        coverage_inventory,
        handedness_coverage,
        freshness_metadata,
        trust,
    )
    readiness_code = _readiness_status_code(
        availability_distribution,
        workload_pressure,
        coverage_inventory,
        handedness_coverage,
        freshness_metadata,
        trust,
    )
    contract_state = (
        'degraded'
        if readiness_code == 'data_limited' or constraints
        else 'available'
    )
    fail_closed_state = (
        TeamOperationsFailClosedMetadata(
            failed_closed=False,
            state='degraded_safe_output',
            reason_codes=tuple(_constraint_ids(constraints)),
            critical_failure=False,
            safe_partial_output_allowed=True,
        )
        if contract_state == 'degraded'
        else TeamOperationsFailClosedMetadata()
    )

    payload = _base_payload(
        contract_state=contract_state,
        generated_at=generated_at,
        team=_team_payload(team),
        readiness=_readiness_payload(readiness_code),
        constraints=constraints,
        workload_pressure=workload_pressure,
        availability_distribution=availability_distribution,
        coverage_inventory=coverage_inventory,
        handedness_coverage=handedness_coverage,
        explanations=_explanations(readiness_code, workload_pressure, coverage_inventory),
        limitations=list(BASELINE_LIMITATIONS) + _dynamic_limitations(constraints),
        trust_metadata=trust.to_dict(),
        freshness=freshness_metadata.to_dict(),
        refusal=TeamOperationsRefusalMetadata().to_dict(),
        fail_closed=fail_closed_state.to_dict(),
    )
    require_team_operations_governance_safe(payload)
    return payload


def _resolve_generated_at(
    generated_at: str | None,
    freshness: Mapping[str, Any] | None,
    trust_metadata: Mapping[str, Any] | None,
) -> str | None:
    if generated_at:
        return generated_at
    if isinstance(freshness, Mapping) and freshness.get('generated_at'):
        return freshness.get('generated_at')
    if isinstance(trust_metadata, Mapping) and trust_metadata.get('generated_at'):
        return trust_metadata.get('generated_at')
    return None


def _normalize_pitcher_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'availability_status': str(
            record.get('availability_status')
            or record.get('availability')
            or 'unknown'
        ).lower(),
        'workload_category': str(
            record.get('workload_category')
            or record.get('workload_pressure')
            or 'unknown'
        ).lower(),
        'throwing_hand': str(
            record.get('throwing_hand') or record.get('handedness') or 'unknown'
        ).lower(),
        'has_current_workload': bool(record.get('has_current_workload', True)),
        'has_availability': bool(record.get('has_availability', True)),
        'active': bool(record.get('active', True)),
    }


def _availability_distribution(records: tuple[dict[str, Any], ...]) -> dict[str, int]:
    distribution = {
        'available': 0,
        'monitor': 0,
        'limited': 0,
        'avoid': 0,
        'unavailable': 0,
        'unknown': 0,
        'total': 0,
    }
    for record in _active_records(records):
        status = record['availability_status']
        if not record['has_availability']:
            status = 'unknown'
        if status not in distribution or status == 'total':
            status = 'unknown'
        distribution[status] += 1
        distribution['total'] += 1
    return distribution


def _workload_pressure(
    records: tuple[dict[str, Any], ...],
    freshness: TeamOperationsFreshnessMetadata,
) -> dict[str, Any]:
    counts = {'low': 0, 'moderate': 0, 'elevated': 0, 'unknown': 0}
    for record in _active_records(records):
        category = record['workload_category']
        if not record['has_current_workload']:
            category = 'unknown'
        if category not in counts:
            category = 'unknown'
        counts[category] += 1

    pressure_state = 'unknown'
    if counts['elevated']:
        pressure_state = 'elevated'
    elif counts['unknown']:
        pressure_state = 'unknown'
    elif counts['moderate']:
        pressure_state = 'moderate'
    elif counts['low']:
        pressure_state = 'low'

    return {
        'pressure_state': pressure_state,
        'pressure_state_code': pressure_state,
        'low_count': counts['low'],
        'moderate_count': counts['moderate'],
        'elevated_count': counts['elevated'],
        'unknown_count': counts['unknown'],
        'latest_workload_date': freshness.latest_workload_date,
        'summary': _workload_summary(pressure_state),
    }


def _coverage_inventory(records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    active_records = tuple(_active_records(records))
    active_count = len(active_records)
    current_workload_count = sum(
        1 for record in active_records if record['has_current_workload']
    )
    availability_count = sum(
        1 for record in active_records if record['has_availability']
    )
    missing_workload_count = active_count - current_workload_count
    availability_missing_count = active_count - availability_count

    if active_count == 0:
        coverage_state = 'missing'
    elif missing_workload_count or availability_missing_count:
        coverage_state = 'partial'
    else:
        coverage_state = 'covered'

    return {
        'active_pitcher_count': active_count,
        'current_workload_data_count': current_workload_count,
        'missing_workload_data_count': missing_workload_count,
        'availability_covered_count': availability_count,
        'availability_missing_count': availability_missing_count,
        'coverage_state': coverage_state,
    }


def _handedness_coverage(records: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    left_count = 0
    right_count = 0
    unknown_count = 0
    for record in _active_records(records):
        handedness = record['throwing_hand']
        if handedness in {'left', 'l', 'lhp'}:
            left_count += 1
        elif handedness in {'right', 'r', 'rhp'}:
            right_count += 1
        else:
            unknown_count += 1

    if left_count + right_count + unknown_count == 0:
        coverage_state = 'missing'
    elif unknown_count:
        coverage_state = 'partial'
    else:
        coverage_state = 'covered'

    limitations = []
    if unknown_count:
        limitations.append(
            f'{unknown_count} active pitcher record(s) are missing throwing-hand data.'
        )

    return {
        'left_handed_count': left_count,
        'right_handed_count': right_count,
        'unknown_count': unknown_count,
        'coverage_state': coverage_state,
        'limitations': limitations,
    }


def _constraints(
    availability_distribution: Mapping[str, Any],
    workload_pressure: Mapping[str, Any],
    coverage_inventory: Mapping[str, Any],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []

    if freshness.freshness_state != 'current':
        constraints.append(
            _constraint(
                constraint_id=f'freshness_{freshness.freshness_state}',
                category='freshness',
                severity='caution',
                affected_area='readiness',
                count=1,
                message='Current workload evidence is not fully current.',
                evidence=[f'freshness_state: {freshness.freshness_state}'],
            )
        )

    if trust.confidence in {'low', 'unknown'} or trust.data_state != 'fresh':
        constraints.append(
            _constraint(
                constraint_id='trust_metadata_limited',
                category='trust',
                severity='caution',
                affected_area='trust_metadata',
                count=1,
                message='Trust metadata limits the readiness summary.',
                evidence=[
                    f'confidence: {trust.confidence}',
                    f'data_state: {trust.data_state}',
                ],
            )
        )

    missing_workload = coverage_inventory['missing_workload_data_count']
    missing_availability = coverage_inventory['availability_missing_count']
    if missing_workload or missing_availability:
        constraints.append(
            _constraint(
                constraint_id='coverage_partial',
                category='coverage',
                severity='caution',
                affected_area='coverage_inventory',
                count=missing_workload + missing_availability,
                message='Some active pitcher records have incomplete readiness evidence.',
                evidence=[
                    f'missing_workload_data_count: {missing_workload}',
                    f'availability_missing_count: {missing_availability}',
                ],
            )
        )

    if handedness_coverage['unknown_count']:
        constraints.append(
            _constraint(
                constraint_id='handedness_partial',
                category='coverage',
                severity='informational',
                affected_area='handedness_coverage',
                count=handedness_coverage['unknown_count'],
                message='Some active pitcher records are missing throwing-hand data.',
                evidence=[
                    f"handedness_unknown_count: {handedness_coverage['unknown_count']}"
                ],
            )
        )

    if workload_pressure['elevated_count']:
        constraints.append(
            _constraint(
                constraint_id='workload_elevated',
                category='workload',
                severity='caution',
                affected_area='workload_pressure',
                count=workload_pressure['elevated_count'],
                message='Elevated team-level workload pressure is present.',
                evidence=[f"elevated_count: {workload_pressure['elevated_count']}"],
            )
        )

    unavailable_count = availability_distribution['avoid'] + availability_distribution[
        'unavailable'
    ]
    if unavailable_count:
        constraints.append(
            _constraint(
                constraint_id='availability_constrained',
                category='availability',
                severity='caution',
                affected_area='availability_distribution',
                count=unavailable_count,
                message='Availability distribution contains constrained inventory.',
                evidence=[f'avoid_or_unavailable_count: {unavailable_count}'],
            )
        )

    return constraints


def _readiness_status_code(
    availability_distribution: Mapping[str, Any],
    workload_pressure: Mapping[str, Any],
    coverage_inventory: Mapping[str, Any],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> str:
    if freshness.freshness_state in {'stale', 'missing', 'incomplete', 'historical', 'unknown'}:
        return 'data_limited'
    if trust.confidence in {'low', 'unknown'} or trust.data_state != 'fresh':
        return 'data_limited'
    if coverage_inventory['coverage_state'] in {'missing', 'unknown'}:
        return 'data_limited'
    if coverage_inventory['coverage_state'] == 'partial':
        return 'data_limited'
    if handedness_coverage['coverage_state'] in {'missing', 'unknown'}:
        return 'data_limited'
    if workload_pressure['elevated_count'] or availability_distribution[
        'unavailable'
    ]:
        return 'operationally_stressed'
    if (
        availability_distribution['monitor']
        or availability_distribution['limited']
        or availability_distribution['avoid']
        or handedness_coverage['coverage_state'] == 'partial'
        or workload_pressure['moderate_count']
    ):
        return 'operationally_constrained'
    return 'operationally_stable'


def _readiness_payload(status_code: str) -> dict[str, Any]:
    if status_code not in ALLOWED_READINESS_STATUS_CODES:
        raise ValueError('readiness status uses unsupported vocabulary.')
    return {
        'status': READINESS_STATUSES[status_code],
        'status_code': status_code,
        'summary': _readiness_summary(status_code),
        'basis': list(READINESS_BASIS),
    }


def _constraint(
    *,
    constraint_id: str,
    category: str,
    severity: str,
    affected_area: str,
    count: int,
    message: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        'constraint_id': constraint_id,
        'category': category,
        'severity': severity,
        'affected_area': affected_area,
        'count': count,
        'message': message,
        'evidence': evidence,
    }


def _explanations(
    readiness_code: str,
    workload_pressure: Mapping[str, Any],
    coverage_inventory: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            'explanation_id': f'readiness_{readiness_code}',
            'level': 'readiness',
            'message': _readiness_explanation(readiness_code),
            'evidence': [
                f"pressure_state: {workload_pressure['pressure_state']}",
                f"coverage_state: {coverage_inventory['coverage_state']}",
            ],
            'applies_to': 'readiness',
        }
    ]


def _dynamic_limitations(constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limitations: list[dict[str, Any]] = []
    if any(constraint['constraint_id'] == 'coverage_partial' for constraint in constraints):
        limitations.append(
            {
                'limitation_id': 'partial_evidence_coverage',
                'message': 'Some active pitcher records have incomplete readiness evidence.',
                'severity': 'caution',
                'applies_to': 'coverage_inventory',
            }
        )
    if any(
        str(constraint['constraint_id']).startswith('freshness_')
        for constraint in constraints
    ):
        limitations.append(
            {
                'limitation_id': 'freshness_limited',
                'message': 'Current evidence freshness limits readiness confidence.',
                'severity': 'caution',
                'applies_to': 'freshness',
            }
        )
    return limitations


def _fail_closed_payload(
    *,
    reason_code: str,
    refusal_id: str,
    message: str,
    team: Mapping[str, Any] | None,
    trust_metadata: Mapping[str, Any] | None,
    freshness: Mapping[str, Any] | None,
    generated_at: str | None,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    validation_errors = validation_errors or []
    trust_payload = _safe_trust_payload(
        trust_metadata,
        generated_at,
        reason_code,
        validation_errors,
    )
    freshness_payload = _safe_freshness_payload(freshness, generated_at)
    refusal_payload = TeamOperationsRefusalMetadata(
        refused=True,
        refusal_id=refusal_id,
        reason=reason_code,
        message=message,
        applies_to='readiness',
        recovery_note='Refresh evidence before exposing readiness.',
    ).to_dict()
    fail_closed_payload = TeamOperationsFailClosedMetadata(
        failed_closed=True,
        state='critical_failure',
        reason_codes=(reason_code,),
        critical_failure=True,
        safe_partial_output_allowed=False,
    ).to_dict()

    payload = _base_payload(
        contract_state='refused',
        generated_at=generated_at,
        team=_team_payload(team),
        readiness={
            'status': READINESS_STATUSES['refused'],
            'status_code': 'refused',
            'summary': message,
            'basis': ['trust_metadata', 'freshness', 'fail_closed'],
        },
        constraints=[
            _constraint(
                constraint_id=reason_code,
                category=_reason_category(reason_code),
                severity='blocking',
                affected_area='readiness',
                count=1,
                message=message,
                evidence=validation_errors,
            )
        ],
        workload_pressure=None,
        availability_distribution=None,
        coverage_inventory=None,
        handedness_coverage=None,
        explanations=[
            {
                'explanation_id': f'readiness_refused_{reason_code}',
                'level': 'refusal',
                'message': 'Readiness output failed closed before summary assembly.',
                'evidence': [reason_code],
                'applies_to': 'refusal',
            }
        ],
        limitations=[
            {
                'limitation_id': 'readiness_refused',
                'message': 'Readiness output is withheld until required metadata is available.',
                'severity': 'blocking',
                'applies_to': 'readiness',
            }
        ],
        trust_metadata=trust_payload,
        freshness=freshness_payload,
        refusal=refusal_payload,
        fail_closed=fail_closed_payload,
    )
    require_team_operations_governance_safe(payload)
    return payload


def _safe_trust_payload(
    trust_metadata: Mapping[str, Any] | None,
    generated_at: str | None,
    reason_code: str,
    validation_errors: list[str],
) -> dict[str, Any]:
    if isinstance(trust_metadata, Mapping) and not trust_metadata_validation_errors(
        trust_metadata
    ):
        payload = TeamOperationsTrustMetadata.from_mapping(trust_metadata).to_dict()
        payload['refusal_reasons'] = list(payload['refusal_reasons']) + [reason_code]
        payload['trust_validation_errors'] = list(
            payload['trust_validation_errors']
        ) + validation_errors
        payload['governance_state'] = 'refused'
        return payload

    return TeamOperationsTrustMetadata(
        confidence='unknown',
        confidence_reasons=(reason_code,),
        data_state='unknown',
        source_evidence_state='missing',
        governance_state='refused',
        generated_at=generated_at,
        limitations=('readiness_refused',),
        explanations=(f'readiness_refused_{reason_code}',),
        refusal_reasons=(reason_code,),
        trust_validation_errors=tuple(validation_errors or (reason_code,)),
    ).to_dict()


def _safe_freshness_payload(
    freshness: Mapping[str, Any] | None,
    generated_at: str | None,
) -> dict[str, Any]:
    if isinstance(freshness, Mapping) and not freshness_validation_errors(freshness):
        return TeamOperationsFreshnessMetadata.from_mapping(freshness).to_dict()

    return TeamOperationsFreshnessMetadata(
        freshness_state='unknown',
        generated_at=generated_at,
        missing_data_warning='Required metadata is missing.',
        limitations=('readiness_refused',),
    ).to_dict()


def _base_payload(
    *,
    contract_state: str,
    generated_at: str | None,
    team: Mapping[str, Any] | None,
    readiness: Mapping[str, Any],
    constraints: list[Mapping[str, Any]],
    workload_pressure: Mapping[str, Any] | None,
    availability_distribution: Mapping[str, Any] | None,
    coverage_inventory: Mapping[str, Any] | None,
    handedness_coverage: Mapping[str, Any] | None,
    explanations: list[Mapping[str, Any]],
    limitations: list[Mapping[str, Any]],
    trust_metadata: Mapping[str, Any],
    freshness: Mapping[str, Any],
    refusal: Mapping[str, Any],
    fail_closed: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        'capability': CAPABILITY,
        'scope': SCOPE,
        'contract': CONTRACT,
        'contract_version': CONTRACT_VERSION,
        'contract_state': contract_state,
        'ranking_applied': NO_RANKING_APPLIED,
        'selection_made': NO_SELECTION_MADE,
        'generated_at': generated_at,
        'team': team,
        'readiness': dict(readiness),
        'constraints': [dict(constraint) for constraint in constraints],
        'workload_pressure': dict(workload_pressure) if workload_pressure else None,
        'availability_distribution': dict(availability_distribution)
        if availability_distribution
        else None,
        'coverage_inventory': dict(coverage_inventory) if coverage_inventory else None,
        'handedness_coverage': dict(handedness_coverage)
        if handedness_coverage
        else None,
        'explanations': [dict(explanation) for explanation in explanations],
        'limitations': [dict(limitation) for limitation in limitations],
        'trust_metadata': dict(trust_metadata),
        'freshness': dict(freshness),
        'refusal': dict(refusal),
        'fail_closed': dict(fail_closed),
    }


def _team_payload(team: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if team is None:
        return None
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _active_records(records: tuple[dict[str, Any], ...]):
    return (record for record in records if record.get('active', True))


def _constraint_ids(constraints: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(constraint['constraint_id']) for constraint in constraints)


def _reason_category(reason_code: str) -> str:
    if 'trust' in reason_code:
        return 'trust'
    if 'freshness' in reason_code:
        return 'freshness'
    if 'governance' in reason_code:
        return 'governance'
    return 'refusal'


def _workload_summary(pressure_state: str) -> str:
    if pressure_state == 'low':
        return 'Recent workload pressure is low at the team level.'
    if pressure_state == 'moderate':
        return 'Recent workload pressure is moderate at the team level.'
    if pressure_state == 'elevated':
        return 'Recent workload pressure is elevated at the team level.'
    return 'Recent workload pressure is partially unknown.'


def _readiness_summary(status_code: str) -> str:
    if status_code == 'operationally_stable':
        return 'Team-level bullpen readiness is operationally stable from current public workload evidence.'
    if status_code == 'operationally_constrained':
        return 'Team-level bullpen readiness is constrained by workload or coverage context.'
    if status_code == 'operationally_stressed':
        return 'Team-level bullpen readiness is stressed by current workload or availability constraints.'
    if status_code == 'data_limited':
        return 'Team-level bullpen readiness is data limited by freshness, trust, or coverage evidence.'
    return 'Readiness output is refused because required evidence is unavailable.'


def _readiness_explanation(status_code: str) -> str:
    if status_code == 'operationally_stable':
        return 'Readiness is operationally stable because freshness is current and workload pressure is low.'
    if status_code == 'operationally_constrained':
        return 'Readiness is operationally constrained because moderate workload or coverage constraints are present.'
    if status_code == 'operationally_stressed':
        return 'Readiness is operationally stressed because elevated workload or unavailable inventory is present.'
    if status_code == 'data_limited':
        return 'Readiness is data limited because current evidence is incomplete, stale, or low confidence.'
    return 'Readiness output was refused before team-level assembly.'
