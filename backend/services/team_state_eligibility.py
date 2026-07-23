"""Deterministic Team State V1 eligibility engine (SC-02).

Given a governed ``TeamStateSource``, this engine produces a completely
deterministic decision about whether BaseballOS is allowed to create a Team
State Share Artifact. There is no AI generation, no LLM summary, and no
probabilistic logic: the same governed evidence always yields the same decision.

The decision is expressed as a ``TeamStateEligibilityResult`` with the fields
required by the spec — ``eligible``, ``blocking_conditions``, ``trust_state``,
``reasons``, ``evidence_summary``, ``payload_version``.

Trust gates (any one blocks; all violations are reported, not just the first):

* missing snapshot            — no trusted published snapshot authorized generation
* stale snapshot              — the snapshot / freshness is stale
* incomplete evidence         — required governed evidence is missing/incomplete
* authority validation failed — unknown team, or readiness team mismatch
* insufficient trust          — fail-closed, governance violation, untrusted
                                contract state, or confidence below the bar
* unsupported team state       — the readiness status is not one V1 may publish

The engine reuses the governed vocabularies of the existing
``team_operations`` capability rather than inventing new ones, and fails closed
whenever the governed evidence is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from team_operations.contracts import (
    ALLOWED_READINESS_STATUS_CODES,
    READINESS_STATUSES,
    team_operations_governance_errors,
)

from services.team_state_source import TeamStateSource


# The canonical Team State V1 payload contract version.
TEAM_STATE_V1 = 'team-state-1.0.0'


# Blocking condition codes.
BLOCK_MISSING_SNAPSHOT = 'missing_snapshot'
BLOCK_STALE_SNAPSHOT = 'stale_snapshot'
BLOCK_INCOMPLETE_EVIDENCE = 'incomplete_evidence'
BLOCK_AUTHORITY_VALIDATION_FAILED = 'authority_validation_failed'
BLOCK_INSUFFICIENT_TRUST = 'insufficient_trust'
BLOCK_UNSUPPORTED_TEAM_STATE = 'unsupported_team_state'


# Trust-state summary codes.
TRUST_TRUSTED = 'trusted'
TRUST_INSUFFICIENT = 'insufficient'
TRUST_FAIL_CLOSED = 'fail_closed'


# The readiness statuses a Team State V1 card may be published for. The
# governed ``data_limited`` and ``refused`` statuses are deliberately excluded.
SUPPORTED_TEAM_STATE_CODES = frozenset({
    'operationally_stable',
    'operationally_constrained',
    'operationally_stressed',
})

# Governed confidence values that clear the V1 trust bar.
SUFFICIENT_CONFIDENCE = frozenset({'high', 'medium'})

# Governed freshness / data states.
STALE_STATES = frozenset({'stale', 'historical'})
INCOMPLETE_STATES = frozenset({'missing', 'incomplete', 'unknown'})
UNTRUSTED_CONTRACT_STATES = frozenset({'unavailable', 'refused'})


@dataclass(frozen=True)
class TeamStateEligibilityResult:
    """A deterministic eligibility decision for a Team State Share Artifact."""

    eligible: bool
    blocking_conditions: tuple
    trust_state: str
    reasons: tuple
    evidence_summary: Mapping[str, Any]
    payload_version: str

    def to_dict(self) -> dict:
        return {
            'eligible': self.eligible,
            'blocking_conditions': list(self.blocking_conditions),
            'trust_state': self.trust_state,
            'reasons': list(self.reasons),
            'evidence_summary': dict(self.evidence_summary),
            'payload_version': self.payload_version,
        }


def _as_mapping(value) -> Optional[Mapping[str, Any]]:
    return value if isinstance(value, Mapping) else None


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _classify_snapshot_reason(reason: str) -> str:
    text = (reason or '').lower()
    # Completeness first: coverage/ledger/incompleteness reasons are evidence
    # gaps, not staleness. (Checked before staleness so "coverage" — which
    # contains "age" — is not misread as an age/staleness signal.)
    if any(token in text for token in ('coverage', 'incomplete', 'ledger', 'partial', 'missing')):
        return BLOCK_INCOMPLETE_EVIDENCE
    if any(token in text for token in ('stale', 'degrad', 'freshness', 'unavailable', 'data_age')):
        return BLOCK_STALE_SNAPSHOT
    return BLOCK_INSUFFICIENT_TRUST


def _readiness_status_code(readiness: Mapping[str, Any]) -> Optional[str]:
    block = _as_mapping(readiness.get('readiness')) or {}
    return block.get('status_code')


def _constraint_categories(readiness: Mapping[str, Any]) -> list:
    constraints = readiness.get('constraints') or []
    categories = set()
    for constraint in constraints:
        if isinstance(constraint, Mapping) and constraint.get('category') is not None:
            categories.add(str(constraint.get('category')))
    return sorted(categories)


def _evidence_summary(source: TeamStateSource, readiness: Optional[Mapping[str, Any]]) -> dict:
    snapshot = source.snapshot
    trust_metadata = _as_mapping(readiness.get('trust_metadata')) if readiness else None
    freshness = _as_mapping(readiness.get('freshness')) if readiness else None
    constraints = readiness.get('constraints') if readiness else None
    return {
        'team_id': source.team_id,
        'team_valid': source.team_valid,
        'snapshot_id': snapshot.snapshot_id,
        'snapshot_present': snapshot.is_present,
        'snapshot_trusted': snapshot.is_trusted,
        'snapshot_unavailable_reason': snapshot.unavailable_reason,
        'data_through': snapshot.data_through.isoformat() if snapshot.data_through else None,
        'readiness_present': readiness is not None,
        'readiness_status_code': _readiness_status_code(readiness) if readiness else None,
        'contract_state': readiness.get('contract_state') if readiness else None,
        'freshness_state': freshness.get('freshness_state') if freshness else None,
        'data_state': trust_metadata.get('data_state') if trust_metadata else None,
        'confidence': trust_metadata.get('confidence') if trust_metadata else None,
        'constraint_count': len(constraints) if isinstance(constraints, (list, tuple)) else 0,
        'constraint_categories': _constraint_categories(readiness) if readiness else [],
    }


def _trust_state(eligible: bool, reasons: list) -> str:
    if eligible:
        return TRUST_TRUSTED
    if 'readiness_fail_closed' in reasons or 'readiness_governance_violation' in reasons:
        return TRUST_FAIL_CLOSED
    return TRUST_INSUFFICIENT


def evaluate_team_state_eligibility(
    source: TeamStateSource,
    *,
    payload_version: str = TEAM_STATE_V1,
) -> TeamStateEligibilityResult:
    """Deterministically decide whether a Team State artifact may be created."""
    blocking: list = []
    reasons: list = []

    def block(condition: str, reason: str) -> None:
        if condition not in blocking:
            blocking.append(condition)
        if reason not in reasons:
            reasons.append(reason)

    readiness = _as_mapping(source.readiness)

    # --- Authority validation -------------------------------------------------
    if not source.team_valid:
        block(BLOCK_AUTHORITY_VALIDATION_FAILED, 'team_id_not_recognized')

    if readiness is None:
        block(BLOCK_INCOMPLETE_EVIDENCE, 'readiness_evidence_missing')
    else:
        if team_operations_governance_errors(readiness):
            block(BLOCK_INSUFFICIENT_TRUST, 'readiness_governance_violation')
        team_block = _as_mapping(readiness.get('team')) or {}
        readiness_team_id = _int_or_none(team_block.get('team_id'))
        if readiness_team_id is not None and readiness_team_id != source.team_id:
            block(BLOCK_AUTHORITY_VALIDATION_FAILED, 'readiness_team_mismatch')

    # --- Snapshot authority ---------------------------------------------------
    snapshot = source.snapshot
    if not snapshot.is_present:
        block(BLOCK_MISSING_SNAPSHOT, 'snapshot_missing')
    elif not snapshot.is_trusted:
        reason = snapshot.unavailable_reason or 'snapshot_untrusted'
        block(_classify_snapshot_reason(reason), f'snapshot:{reason}')

    # --- Freshness / completeness / trust from governed readiness enums -------
    if readiness is not None:
        freshness = _as_mapping(readiness.get('freshness')) or {}
        freshness_state = freshness.get('freshness_state')
        if freshness_state in STALE_STATES:
            block(BLOCK_STALE_SNAPSHOT, f'freshness_state:{freshness_state}')
        elif freshness_state in INCOMPLETE_STATES:
            block(BLOCK_INCOMPLETE_EVIDENCE, f'freshness_state:{freshness_state}')

        trust_metadata = _as_mapping(readiness.get('trust_metadata')) or {}
        data_state = trust_metadata.get('data_state')
        if data_state in STALE_STATES:
            block(BLOCK_STALE_SNAPSHOT, f'data_state:{data_state}')
        elif data_state in INCOMPLETE_STATES:
            block(BLOCK_INCOMPLETE_EVIDENCE, f'data_state:{data_state}')

        fail_closed = _as_mapping(readiness.get('fail_closed')) or {}
        if fail_closed.get('failed_closed') is True or fail_closed.get('state') == 'critical_failure':
            block(BLOCK_INSUFFICIENT_TRUST, 'readiness_fail_closed')

        contract_state = readiness.get('contract_state')
        if contract_state in UNTRUSTED_CONTRACT_STATES:
            block(BLOCK_INSUFFICIENT_TRUST, f'contract_state:{contract_state}')

        confidence = trust_metadata.get('confidence')
        if confidence not in SUFFICIENT_CONFIDENCE:
            block(BLOCK_INSUFFICIENT_TRUST, f'confidence:{confidence}')

        # --- Supported team state --------------------------------------------
        status_code = _readiness_status_code(readiness)
        if status_code not in ALLOWED_READINESS_STATUS_CODES:
            block(BLOCK_UNSUPPORTED_TEAM_STATE, f'status_code_unknown:{status_code}')
        elif status_code not in SUPPORTED_TEAM_STATE_CODES:
            block(BLOCK_UNSUPPORTED_TEAM_STATE, f'status_code_unsupported:{status_code}')

    eligible = not blocking
    return TeamStateEligibilityResult(
        eligible=eligible,
        blocking_conditions=tuple(blocking),
        trust_state=_trust_state(eligible, reasons),
        reasons=tuple(reasons),
        evidence_summary=_evidence_summary(source, readiness),
        payload_version=payload_version,
    )


# Re-exported for callers that want the human-readable status label map without
# reaching into team_operations directly.
TEAM_STATE_STATUS_LABELS = dict(READINESS_STATUSES)
