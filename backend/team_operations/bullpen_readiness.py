"""Team Operations Bullpen Readiness domain assembly."""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable, Mapping

from team_operations.contracts import (
    ALLOWED_READINESS_STATUS_CODES,
    CAPABILITY,
    CONTRACT,
    CONTRACT_VERSION,
    DECISIVE_RULE_DATA_LIMITED,
    DECISIVE_RULE_FRESH_COVERAGE,
    DECISIVE_RULE_MARGIN_FLOOR,
    DECISIVE_RULE_RESIDUAL_STRETCHED,
    DECISIVE_RULE_SEVERITY_SHARE,
    NO_RANKING_APPLIED,
    NO_SELECTION_MADE,
    READINESS_STATUSES,
    SCOPE,
    TEAM_STATE_CONTRACT_A,
    TEAM_STATE_METHOD_VERSION,
    TeamOperationsFailClosedMetadata,
    TeamOperationsFreshnessMetadata,
    TeamOperationsRefusalMetadata,
    TeamOperationsTrustMetadata,
    freshness_validation_errors,
    require_team_operations_governance_safe,
    trust_metadata_validation_errors,
)


# Exact Contract A thresholds, resolved once from the frozen contract. Held as
# Fractions so a boundary case (clean_share == 3/5, severe_share == 1/3) is
# decided by exact arithmetic, never by a rounded display value.
_CLEAN_SHARE_FRESH_MIN = Fraction(*TEAM_STATE_CONTRACT_A['clean_share_fresh_min'])
_CLEAN_COUNT_FRESH_MIN = TEAM_STATE_CONTRACT_A['clean_count_fresh_min']
_SEVERE_COUNT_FRESH_MAX = TEAM_STATE_CONTRACT_A['severe_count_fresh_max']
_CLEAN_COUNT_VULNERABLE_MAX = TEAM_STATE_CONTRACT_A['clean_count_vulnerable_max']
_SEVERE_SHARE_VULNERABLE_MIN = Fraction(*TEAM_STATE_CONTRACT_A['severe_share_vulnerable_min'])

# The freshness states that withhold a Team State (fail closed). Anything that is
# not fully current is a data limitation, not a baseball condition.
_NON_CURRENT_FRESHNESS_STATES = frozenset(
    {'stale', 'missing', 'incomplete', 'historical', 'unknown'}
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
        'message': 'Readiness is based on public workload data, not private team information.',
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
    # Team State vNext (Contract A). The state is decided by the status-only
    # partition of the canonical readiness population — nothing else. Workload
    # pressure, raw fatigue scores, and handedness coverage are computed above as
    # governed context for other surfaces, but they do NOT decide the state.
    team_state_partition = _team_state_partition(availability_distribution)
    readiness_code, decisive_rule, decisive_inputs = _contract_a_decision(
        team_state_partition,
        coverage_inventory,
        handedness_coverage,
        freshness_metadata,
        trust,
    )
    team_state_evidence = _team_state_evidence(
        readiness_code=readiness_code,
        decisive_rule=decisive_rule,
        decisive_inputs=decisive_inputs,
        partition=team_state_partition,
        coverage_inventory=coverage_inventory,
        handedness_coverage=handedness_coverage,
        freshness=freshness_metadata,
        trust=trust,
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
        team_state_evidence=team_state_evidence,
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
                message='The public workload record is not strong enough for a full readiness summary.',
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


def _team_state_partition(availability_distribution: Mapping[str, Any]) -> dict[str, int]:
    """Status-only clean/moderate/severe/unknown partition of the active bullpen.

    This is a straight regrouping of the governed availability statuses the
    availability authority already published — no status is escalated, no raw
    score is read, and an UNKNOWN arm is never promoted to clean. The partition
    invariant ``clean + moderate + severe + unknown == active_pitcher_count`` holds
    by construction because ``availability_distribution`` already places every
    active record in exactly one status bucket.
    """
    clean_count = availability_distribution['available']
    moderate_count = (
        availability_distribution['monitor'] + availability_distribution['limited']
    )
    severe_count = (
        availability_distribution['avoid'] + availability_distribution['unavailable']
    )
    unknown_count = availability_distribution['unknown']
    active_pitcher_count = availability_distribution['total']
    return {
        'active_pitcher_count': active_pitcher_count,
        'clean_count': clean_count,
        'moderate_count': moderate_count,
        'severe_count': severe_count,
        'unknown_count': unknown_count,
    }


def _team_state_data_gate(
    partition: Mapping[str, int],
    coverage_inventory: Mapping[str, Any],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> dict[str, Any] | None:
    """Trust / data-quality gate. Returns the withholding reason, or None to pass.

    This preserves the existing fail-closed trust behavior exactly. Handedness is
    only ever a TRUST signal here (routed to ``data_limited``); it never produces a
    baseball state. An empty active population has no Team State — reporting one
    would convert a data condition into a classification — so it withholds too.
    """
    if freshness.freshness_state in _NON_CURRENT_FRESHNESS_STATES:
        return {'gate': 'freshness', 'freshness_state': freshness.freshness_state}
    if trust.confidence in {'low', 'unknown'} or trust.data_state != 'fresh':
        return {
            'gate': 'trust',
            'trust_confidence': trust.confidence,
            'trust_data_state': trust.data_state,
        }
    # Share Cards SC-03B-07: team trust is the canonical active-bullpen coverage
    # authority (high/medium = sufficient current coverage). The coarser whole-active
    # coverage_inventory / handedness gates only fail closed a team the trust
    # authority has NOT already deemed sufficiently covered. Handedness is confined
    # to this trust routing — it can withhold a read, but it can never downgrade a
    # baseball state.
    trust_coverage_sufficient = trust.confidence in {'high', 'medium'}
    if not trust_coverage_sufficient and coverage_inventory['coverage_state'] in {
        'missing',
        'unknown',
        'partial',
    }:
        return {'gate': 'coverage', 'coverage_state': coverage_inventory['coverage_state']}
    if not trust_coverage_sufficient and handedness_coverage['coverage_state'] in {
        'missing',
        'unknown',
    }:
        return {
            'gate': 'handedness',
            'handedness_coverage_state': handedness_coverage['coverage_state'],
        }
    if partition['active_pitcher_count'] == 0:
        return {'gate': 'empty_population', 'active_pitcher_count': 0}
    return None


def _contract_a_decision(
    partition: Mapping[str, int],
    coverage_inventory: Mapping[str, Any],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> tuple[str, str, dict[str, Any]]:
    """Locked Contract A precedence. Returns (status_code, decisive_rule, inputs).

    Exact precedence, evaluated in this order and no other:

      1. TRUST / DATA GATE   -> data_limited (no public Team State)
      2. VULNERABLE          -> operationally_stressed
                                clean_count <= 2  OR  severe_share >= 1/3
      3. FRESH               -> operationally_stable
                                clean_share >= 3/5 AND clean_count >= 5
                                AND severe_count <= 1
      4. STRETCHED           -> operationally_constrained  (residual)

    Vulnerable is evaluated before Fresh. Shares are compared as exact rationals so
    clean_share == 3/5 and severe_share == 1/3 land on the qualifying side of the
    boundary without any float ambiguity.
    """
    gate = _team_state_data_gate(
        partition, coverage_inventory, handedness_coverage, freshness, trust
    )
    if gate is not None:
        return 'data_limited', DECISIVE_RULE_DATA_LIMITED, dict(gate)

    total = partition['active_pitcher_count']
    clean = partition['clean_count']
    severe = partition['severe_count']
    clean_share = Fraction(clean, total)
    severe_share = Fraction(severe, total)

    # 2. VULNERABLE — margin floor first, then severity share.
    if clean <= _CLEAN_COUNT_VULNERABLE_MAX:
        return (
            'operationally_stressed',
            DECISIVE_RULE_MARGIN_FLOOR,
            {'clean_count': clean, 'clean_count_vulnerable_max': _CLEAN_COUNT_VULNERABLE_MAX},
        )
    if severe_share >= _SEVERE_SHARE_VULNERABLE_MIN:
        return (
            'operationally_stressed',
            DECISIVE_RULE_SEVERITY_SHARE,
            {
                'severe_count': severe,
                'active_pitcher_count': total,
                'severe_share': _share(severe, total),
            },
        )

    # 3. FRESH — strong clean coverage with at most one severe arm.
    if (
        clean_share >= _CLEAN_SHARE_FRESH_MIN
        and clean >= _CLEAN_COUNT_FRESH_MIN
        and severe <= _SEVERE_COUNT_FRESH_MAX
    ):
        return (
            'operationally_stable',
            DECISIVE_RULE_FRESH_COVERAGE,
            {
                'clean_count': clean,
                'clean_share': _share(clean, total),
                'severe_count': severe,
                'active_pitcher_count': total,
            },
        )

    # 4. STRETCHED — neither route fired.
    return (
        'operationally_constrained',
        DECISIVE_RULE_RESIDUAL_STRETCHED,
        {
            'clean_count': clean,
            'clean_share': _share(clean, total),
            'severe_count': severe,
            'severe_share': _share(severe, total),
            'active_pitcher_count': total,
        },
    )


def _share(count: int, denominator: int) -> float | None:
    """Display-only ratio (never used to decide the state). None when empty."""
    if not denominator:
        return None
    return count / denominator


def _team_state_evidence(
    *,
    readiness_code: str,
    decisive_rule: str,
    decisive_inputs: Mapping[str, Any],
    partition: Mapping[str, int],
    coverage_inventory: Mapping[str, Any],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> dict[str, Any]:
    """Canonical Team State evidence vector from the exact classifier inputs.

    Built from the same partition and the same decision that produced the state —
    one population, one threshold interpretation. Shares are emitted as floats for
    readability; the thresholds are emitted as exact rationals ``[numerator,
    denominator]`` so a downstream reader can reproduce the boundary arithmetic.
    """
    total = partition['active_pitcher_count']
    material_limitations = _team_state_material_limitations(
        readiness_code=readiness_code,
        partition=partition,
        handedness_coverage=handedness_coverage,
        freshness=freshness,
        trust=trust,
    )
    return {
        'method_version': TEAM_STATE_METHOD_VERSION,
        'contract': TEAM_STATE_CONTRACT_A['contract'],
        'basis': TEAM_STATE_CONTRACT_A['basis'],
        'readiness_status_code': readiness_code,
        'active_pitcher_count': total,
        'clean_count': partition['clean_count'],
        'moderate_count': partition['moderate_count'],
        'severe_count': partition['severe_count'],
        'unknown_count': partition['unknown_count'],
        'clean_share': _share(partition['clean_count'], total),
        'moderate_share': _share(partition['moderate_count'], total),
        'severe_share': _share(partition['severe_count'], total),
        'unknown_share': _share(partition['unknown_count'], total),
        'decisive_rule': decisive_rule,
        'decisive_inputs': dict(decisive_inputs),
        'thresholds_applied': _team_state_thresholds_applied(),
        'trust_state': trust.confidence,
        'trust_data_state': trust.data_state,
        'freshness_state': freshness.freshness_state,
        'material_limitations': material_limitations,
        'evidence_references': {
            'population_authority': 'resolve_readiness_population',
            'membership_authority': 'resolve_active_bullpen_membership',
            'availability_authority': 'services.availability',
            'coverage_state': coverage_inventory.get('coverage_state'),
        },
    }


def _team_state_thresholds_applied() -> dict[str, Any]:
    """The locked Contract A thresholds, exact rationals plus float for readability."""
    clean_share = TEAM_STATE_CONTRACT_A['clean_share_fresh_min']
    severe_share = TEAM_STATE_CONTRACT_A['severe_share_vulnerable_min']
    return {
        'clean_share_fresh_min': list(clean_share),
        'clean_share_fresh_min_value': clean_share[0] / clean_share[1],
        'clean_count_fresh_min': TEAM_STATE_CONTRACT_A['clean_count_fresh_min'],
        'severe_count_fresh_max': TEAM_STATE_CONTRACT_A['severe_count_fresh_max'],
        'clean_count_vulnerable_max': TEAM_STATE_CONTRACT_A['clean_count_vulnerable_max'],
        'severe_share_vulnerable_min': list(severe_share),
        'severe_share_vulnerable_min_value': severe_share[0] / severe_share[1],
    }


def _team_state_material_limitations(
    *,
    readiness_code: str,
    partition: Mapping[str, int],
    handedness_coverage: Mapping[str, Any],
    freshness: TeamOperationsFreshnessMetadata,
    trust: TeamOperationsTrustMetadata,
) -> list[dict[str, Any]]:
    """Structured, non-prose material limitations attached to the evidence vector."""
    limitations: list[dict[str, Any]] = []
    if readiness_code == 'data_limited':
        limitations.append({
            'limitation_id': 'team_state_withheld',
            'detail': 'Team State is withheld because governed evidence did not clear the trust/data bar.',
        })
    if partition['unknown_count']:
        # Preserved, never dropped and never counted as clean: an arm with no
        # governed availability state stays UNKNOWN in the partition.
        limitations.append({
            'limitation_id': 'unknown_arms_present',
            'count': partition['unknown_count'],
            'detail': 'Some active bullpen arms have no governed availability state.',
        })
    if handedness_coverage.get('coverage_state') == 'partial':
        limitations.append({
            'limitation_id': 'handedness_partial',
            'detail': 'Bullpen handedness coverage is partial. This is context only and does not change Team State.',
        })
    if freshness.freshness_state != 'current':
        limitations.append({
            'limitation_id': f'freshness_{freshness.freshness_state}',
            'detail': 'Current workload evidence is not fully current.',
        })
    if trust.confidence == 'medium':
        limitations.append({
            'limitation_id': 'bounded_partial_coverage',
            'detail': 'Read confidence is medium: current active-bullpen coverage is bounded but partial.',
        })
    return limitations


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
        team_state_evidence=_refused_team_state_evidence(
            reason_code=reason_code,
            trust_payload=trust_payload,
            freshness_payload=freshness_payload,
        ),
    )
    require_team_operations_governance_safe(payload)
    return payload


def _refused_team_state_evidence(
    *,
    reason_code: str,
    trust_payload: Mapping[str, Any],
    freshness_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Team State evidence for a refused/fail-closed read: no state, no partition.

    Carries the method version and the withheld decisive rule so a refused
    publication still records WHICH method refused, with a null partition (no
    records were classified) rather than a fabricated zero-arm state.
    """
    return {
        'method_version': TEAM_STATE_METHOD_VERSION,
        'contract': TEAM_STATE_CONTRACT_A['contract'],
        'basis': TEAM_STATE_CONTRACT_A['basis'],
        'readiness_status_code': 'refused',
        'active_pitcher_count': None,
        'clean_count': None,
        'moderate_count': None,
        'severe_count': None,
        'unknown_count': None,
        'clean_share': None,
        'moderate_share': None,
        'severe_share': None,
        'unknown_share': None,
        'decisive_rule': DECISIVE_RULE_DATA_LIMITED,
        'decisive_inputs': {'gate': 'refused', 'reason_code': reason_code},
        'thresholds_applied': _team_state_thresholds_applied(),
        'trust_state': trust_payload.get('confidence'),
        'trust_data_state': trust_payload.get('data_state'),
        'freshness_state': freshness_payload.get('freshness_state'),
        'material_limitations': [{
            'limitation_id': 'team_state_refused',
            'detail': 'Readiness output failed closed before any Team State was assembled.',
        }],
        'evidence_references': {
            'population_authority': 'resolve_readiness_population',
            'membership_authority': 'resolve_active_bullpen_membership',
            'availability_authority': 'services.availability',
            'coverage_state': None,
        },
    }


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
    team_state_evidence: Mapping[str, Any],
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
        'team_state_evidence': dict(team_state_evidence),
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
        return 'Team-level bullpen readiness looks steady from current public workload evidence.'
    if status_code == 'operationally_constrained':
        return 'Team-level bullpen readiness is constrained by workload or coverage context.'
    if status_code == 'operationally_stressed':
        return 'Team-level bullpen readiness is stressed by current workload or availability constraints.'
    if status_code == 'data_limited':
        return 'Team-level bullpen visibility is limited by freshness, trust, or coverage evidence.'
    return 'Readiness output is refused because required evidence is unavailable.'


def _readiness_explanation(status_code: str) -> str:
    if status_code == 'operationally_stable':
        return 'Readiness looks steady because freshness is current and workload pressure is low.'
    if status_code == 'operationally_constrained':
        return 'Readiness has less room because moderate workload or coverage constraints are present.'
    if status_code == 'operationally_stressed':
        return 'Readiness looks stressed because elevated workload or unavailable arms are present.'
    if status_code == 'data_limited':
        return 'Readiness visibility is limited because current evidence is incomplete, not fully current, or based on an unclear read.'
    return 'Readiness output was refused before team-level assembly.'
