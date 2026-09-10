"""Controlled CU observation outcomes and operational severity."""

from __future__ import annotations

from dataclasses import asdict, dataclass

ACCEPTED_CHANGE = 'accepted_change'
ACCEPTED_NO_CHANGE = 'accepted_no_change'
DUPLICATE = 'duplicate'
STALE = 'stale'
SUPERSEDED = 'superseded'
SAFE_REJECTION = 'safe_rejection'
AMBIGUOUS_NONBLOCKING = 'ambiguous_nonblocking'
OPTIONAL_PARTIAL = 'optional_partial'
AMBIGUOUS_BLOCKING = 'ambiguous_blocking'
MALFORMED = 'malformed'
SOURCE_FAILURE = 'source_failure'
INVARIANT_VIOLATION = 'invariant_violation'

HEALTHY = 'healthy'
WARNING = 'warning'
BLOCKING = 'blocking'


@dataclass(frozen=True)
class ObservationOutcome:
    outcome: str
    severity: str
    retryable: bool
    blocks_required_obligation: bool

    def to_dict(self):
        return asdict(self)


def classify(classification, *, reason='', accepted=False,
             current_authority_satisfied=False):
    reason = str(reason or '')
    if classification in {'new_game', 'changed', 'finalized', 'corrected'}:
        if accepted:
            return ObservationOutcome(ACCEPTED_CHANGE, HEALTHY, False, False)
        return ObservationOutcome(INVARIANT_VIOLATION, BLOCKING, False, True)
    if classification == 'unchanged':
        return ObservationOutcome(DUPLICATE, HEALTHY, False, False)
    if classification == 'stale_observation':
        outcome = SUPERSEDED if reason == 'weaker_source_authority' else STALE
        return ObservationOutcome(outcome, HEALTHY, False, False)
    if classification == 'ambiguous_observation':
        if reason == 'final_evidence_regression':
            return ObservationOutcome(SAFE_REJECTION, WARNING, False, False)
        if reason == 'equal_revision_with_different_material_content':
            return ObservationOutcome(
                AMBIGUOUS_NONBLOCKING if current_authority_satisfied
                else AMBIGUOUS_BLOCKING,
                WARNING if current_authority_satisfied else BLOCKING,
                not current_authority_satisfied,
                not current_authority_satisfied,
            )
        return ObservationOutcome(AMBIGUOUS_BLOCKING, BLOCKING, True, True)
    if classification == 'partial_observation':
        return ObservationOutcome(
            OPTIONAL_PARTIAL if current_authority_satisfied else AMBIGUOUS_BLOCKING,
            WARNING if current_authority_satisfied else BLOCKING,
            not current_authority_satisfied,
            not current_authority_satisfied,
        )
    if classification == 'malformed_observation':
        return ObservationOutcome(MALFORMED, BLOCKING, True, True)
    if classification == 'source_failure':
        return ObservationOutcome(SOURCE_FAILURE, BLOCKING, True, True)
    if accepted is False and current_authority_satisfied:
        return ObservationOutcome(SAFE_REJECTION, WARNING, False, False)
    return ObservationOutcome(INVARIANT_VIOLATION, BLOCKING, False, True)
