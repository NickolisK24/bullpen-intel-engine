"""Batch Team State Share Artifact generation (Share Cards SC-03B-01).

This is an orchestration layer *around* the existing SC-03A single-team
generation service. It owns none of the intelligence: not team-state or
readiness calculation, not eligibility, not evidence ranking, not payload
composition, not equivalence/integrity hashing, not deduplication, not the
publication transaction. It only:

  1. validates one shared trusted source snapshot / product-date authority,
  2. enumerates the canonical MLB team set (or an explicit operator subset),
  3. calls ``generate_team_state_artifact`` once per team, in a stable order,
  4. captures each deterministic per-team outcome, and
  5. produces a deterministic, auditable coverage summary.

Each team is an independent atomic attempt handled entirely by the single-team
service (which commits publication + its durable audit atomically and fails
closed on its own). One team's refusal or failure never skips another team, and
the batch never leaves a partially published artifact behind because it never
opens its own artifact transaction.

Fail-closed batch authority: if the shared source snapshot is missing,
untrusted, or does not match the operator's declared ``source_snapshot_id`` /
``product_date``, the whole batch is refused *before* any team is attempted, so
one invalid global source never becomes N misleading per-team failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from services.share_artifact_generation import (
    OUTCOME_FAILED_CLOSED,
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    generate_team_state_artifact,
)
from services.team_directory import valid_team_ids
from services.team_state_source import resolve_latest_trusted_snapshot


# Batch-level outcome vocabulary (distinct from, but derived from, the
# single-team audit outcomes). Every attempted team maps to exactly one.
BATCH_OUTCOME_GENERATED = 'generated'
BATCH_OUTCOME_REUSED = 'reused'
BATCH_OUTCOME_REFUSED = 'refused'
BATCH_OUTCOME_FAILED = 'failed'

# Internal actor / request-source attribution for the durable generation audit,
# consistent with the single-team admin conventions ('admin_api').
BATCH_ACTOR = 'admin_batch_api'
BATCH_REQUEST_SOURCE = 'internal_admin_batch_api'

# Non-sensitive failure code when a per-team attempt raises unexpectedly despite
# the single-team service being designed to fail closed and return a result.
FAILURE_BATCH_TEAM_ERROR = 'batch_team_error'


class BatchValidationError(ValueError):
    """The batch request itself is malformed (bad snapshot id / date / team ids).

    Distinct from a source-authority refusal: this is an operator input error,
    surfaced before any snapshot resolution or team attempt.
    """


class BatchSourceAuthorityError(Exception):
    """The shared trusted source snapshot is globally unusable for this batch.

    Raised before any team is attempted. ``reason_code`` is a non-sensitive,
    governed string (e.g. ``snapshot_missing``, ``snapshot_untrusted``,
    ``snapshot_id_mismatch``, ``product_date_mismatch``).
    """

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class BatchAccountingError(AssertionError):
    """The batch accounting invariant was violated (attempted != sum of outcomes)."""


@dataclass(frozen=True)
class BatchTeamResult:
    """Deterministic per-team terminal outcome within a batch."""

    team_id: int
    outcome: str  # generated / reused / refused / failed
    public_id: Optional[str] = None
    reason_code: Optional[str] = None       # populated for refused
    failure_code: Optional[str] = None      # populated for failed
    audit_id: Optional[int] = None
    source_snapshot_id: Optional[int] = None
    product_date: Optional[date] = None

    def to_dict(self) -> dict:
        return {
            'team_id': self.team_id,
            'outcome': self.outcome,
            'public_id': self.public_id,
            'reason_code': self.reason_code,
            'failure_code': self.failure_code,
            'audit_id': self.audit_id,
            'source_snapshot_id': self.source_snapshot_id,
            'product_date': self.product_date.isoformat() if self.product_date else None,
        }


@dataclass(frozen=True)
class BatchGenerationResult:
    """Deterministic, auditable coverage summary for a batch attempt.

    The ordered ``results`` plus the counts form the stable contract: the same
    inputs against the same authoritative source produce the same ordered
    result. ``started_at`` / ``completed_at`` are operational metadata only and
    are intentionally excluded from the deterministic contract.
    """

    source_snapshot_id: Optional[int]
    product_date: Optional[date]
    results: tuple                    # ordered tuple[BatchTeamResult]
    canonical_team_count: int         # full-league expected size (for coverage)
    expected_team_ids: tuple          # what this batch intended to attempt (ordered)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        # Coverage/accounting invariant — loudly fail rather than silently
        # mis-report. attempted == generated + reused + refused + failed.
        if self.attempted_count != (
            self.generated_count
            + self.reused_count
            + self.refused_count
            + self.failed_count
        ):
            raise BatchAccountingError(
                'batch accounting invariant violated: attempted_count '
                f'{self.attempted_count} != generated {self.generated_count} + '
                f'reused {self.reused_count} + refused {self.refused_count} + '
                f'failed {self.failed_count}'
            )

    # -- derived counts ------------------------------------------------------
    @property
    def attempted_count(self) -> int:
        return len(self.results)

    def _count(self, outcome: str) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    @property
    def generated_count(self) -> int:
        return self._count(BATCH_OUTCOME_GENERATED)

    @property
    def reused_count(self) -> int:
        return self._count(BATCH_OUTCOME_REUSED)

    @property
    def refused_count(self) -> int:
        return self._count(BATCH_OUTCOME_REFUSED)

    @property
    def failed_count(self) -> int:
        return self._count(BATCH_OUTCOME_FAILED)

    # -- coverage ------------------------------------------------------------
    @property
    def accounted_team_ids(self) -> frozenset:
        return frozenset(r.team_id for r in self.results)

    @property
    def missing_team_ids(self) -> tuple:
        """Expected canonical teams with no terminal result of any kind.

        A refused or failed team is *accounted for* — only a team that produced
        no result at all is missing. Ordered for determinism.
        """
        accounted = self.accounted_team_ids
        return tuple(t for t in self.expected_team_ids if t not in accounted)

    @property
    def missing_count(self) -> int:
        return len(self.missing_team_ids)

    @property
    def is_complete(self) -> bool:
        """True when every expected team is accounted for by a terminal result.

        A batch with any missing/unaccounted team is operationally unsuccessful
        even if some artifacts were generated.
        """
        return self.missing_count == 0

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            'source_snapshot_id': self.source_snapshot_id,
            'product_date': self.product_date.isoformat() if self.product_date else None,
            'canonical_team_count': self.canonical_team_count,
            'attempted_count': self.attempted_count,
            'generated_count': self.generated_count,
            'reused_count': self.reused_count,
            'refused_count': self.refused_count,
            'failed_count': self.failed_count,
            'missing_count': self.missing_count,
            'missing_team_ids': list(self.missing_team_ids),
            'is_complete': self.is_complete,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'results': [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Team enumeration
# ---------------------------------------------------------------------------


def _canonical_team_ids(session=None) -> tuple:
    """The canonical MLB team set, in stable ascending team-id order.

    Reuses the existing team authority (``services.team_directory``) — the same
    universe the public team surfaces are built from. No second team registry.
    """
    return tuple(sorted(valid_team_ids()))


def _normalize_requested_subset(team_ids: Iterable) -> tuple:
    """Validate + de-duplicate an explicit operator subset into stable order.

    Well-formedness only (positive ints). Whether a well-formed id is a real
    current team is decided by the governed single-team path (an unknown team is
    refused deterministically), so it stays accounted for rather than silently
    dropped. Raises ``BatchValidationError`` on any malformed id.
    """
    normalized = set()
    for raw in team_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise BatchValidationError(f'invalid_team_id:{raw!r}')
        if value <= 0:
            raise BatchValidationError(f'invalid_team_id:{raw!r}')
        normalized.add(value)
    if not normalized:
        raise BatchValidationError('empty_team_subset')
    return tuple(sorted(normalized))


# ---------------------------------------------------------------------------
# Source authority
# ---------------------------------------------------------------------------


def _validate_batch_source_authority(*, source_snapshot_id, product_date, authority):
    """Fail closed on a globally unusable shared source snapshot.

    Raised *before* any team attempt so one invalid source never fans out into N
    misleading per-team failures.
    """
    if not authority.is_present:
        raise BatchSourceAuthorityError('snapshot_missing')
    if not authority.is_trusted:
        raise BatchSourceAuthorityError(authority.unavailable_reason or 'snapshot_untrusted')
    if authority.snapshot_id != source_snapshot_id:
        raise BatchSourceAuthorityError('snapshot_id_mismatch')
    if authority.data_through != product_date:
        raise BatchSourceAuthorityError('product_date_mismatch')


# ---------------------------------------------------------------------------
# Per-team outcome mapping
# ---------------------------------------------------------------------------


def _batch_outcome(single_result) -> str:
    if single_result.outcome == OUTCOME_PUBLISHED:
        return BATCH_OUTCOME_GENERATED
    if single_result.outcome == OUTCOME_REUSED:
        return BATCH_OUTCOME_REUSED
    if single_result.outcome == OUTCOME_REFUSED:
        return BATCH_OUTCOME_REFUSED
    # OUTCOME_FAILED_CLOSED or anything unexpected -> failed (never a success).
    return BATCH_OUTCOME_FAILED


def _refusal_reason_code(single_result) -> Optional[str]:
    if single_result.blocking_conditions:
        return single_result.blocking_conditions[0]
    if single_result.reasons:
        return single_result.reasons[0]
    return None


def _team_result_from_single(team_id, single_result) -> BatchTeamResult:
    outcome = _batch_outcome(single_result)
    return BatchTeamResult(
        team_id=team_id,
        outcome=outcome,
        public_id=single_result.public_id,
        reason_code=_refusal_reason_code(single_result) if outcome == BATCH_OUTCOME_REFUSED else None,
        failure_code=single_result.failure_code if outcome == BATCH_OUTCOME_FAILED else None,
        audit_id=single_result.audit_id,
        source_snapshot_id=single_result.source_snapshot_id,
        product_date=single_result.product_date,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_team_state_artifacts_batch(
    *,
    source_snapshot_id: int,
    product_date: date,
    actor: str = BATCH_ACTOR,
    team_ids: Optional[Iterable] = None,
    generator=None,
    session=None,
    _clock=None,
) -> BatchGenerationResult:
    """Attempt Team State artifact generation across the canonical MLB team set.

    Delegates every team to the existing SC-03A single-team generation service.
    Requires an explicit trusted source authority (``source_snapshot_id`` +
    ``product_date``); the shared latest published snapshot must match both or
    the whole batch is refused before any team is attempted.

    ``team_ids`` optionally restricts the run to a deterministic operator subset.
    ``generator`` / ``_clock`` are test seams (defaulting to the real
    single-team service and ``datetime.utcnow``).

    Raises ``BatchValidationError`` on malformed input and
    ``BatchSourceAuthorityError`` on a globally unusable source.
    """
    if source_snapshot_id is None:
        raise BatchValidationError('missing_source_snapshot_id')
    try:
        source_snapshot_id = int(source_snapshot_id)
    except (TypeError, ValueError):
        raise BatchValidationError('invalid_source_snapshot_id')
    if not isinstance(product_date, date):
        raise BatchValidationError('invalid_product_date')

    generate = generator or generate_team_state_artifact
    clock = _clock or datetime.utcnow

    # 1. Resolve + validate ONE shared trusted source snapshot (fail closed).
    snapshot, authority = resolve_latest_trusted_snapshot()
    _validate_batch_source_authority(
        source_snapshot_id=source_snapshot_id,
        product_date=product_date,
        authority=authority,
    )

    # 2. Enumerate teams in a stable order.
    canonical = _canonical_team_ids(session=session)
    if team_ids is None:
        expected = canonical
    else:
        expected = _normalize_requested_subset(team_ids)

    started_at = clock()

    # 3. Attempt each team independently, threading the SAME validated snapshot.
    results = []
    for team_id in expected:
        try:
            single = generate(
                team_id,
                requested_date=product_date,
                actor=actor,
                request_source=BATCH_REQUEST_SOURCE,
                snapshot=snapshot,
                session=session,
            )
            results.append(_team_result_from_single(team_id, single))
        except Exception:
            # Defense in depth: the single-team service is designed to fail
            # closed and return a result, but an unexpected raise must not skip
            # the remaining teams. Record an accounted 'failed' outcome.
            results.append(
                BatchTeamResult(
                    team_id=team_id,
                    outcome=BATCH_OUTCOME_FAILED,
                    failure_code=FAILURE_BATCH_TEAM_ERROR,
                    source_snapshot_id=authority.snapshot_id,
                    product_date=authority.data_through,
                )
            )

    completed_at = clock()

    return BatchGenerationResult(
        source_snapshot_id=authority.snapshot_id,
        product_date=authority.data_through,
        results=tuple(results),
        canonical_team_count=len(canonical),
        expected_team_ids=tuple(expected),
        started_at=started_at,
        completed_at=completed_at,
    )
