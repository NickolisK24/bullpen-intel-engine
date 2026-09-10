"""Active-bullpen readiness coverage contract (Share Cards SC-03B-07).

Founder-approved upstream readiness-contract correction. This is the deterministic
team-level trust classifier that replaces the previous whole-roster ``any()``
collapse (a single non-fresh pitcher forced the entire team to
``confidence=low`` / ``data_state=incomplete`` / ``status_code=data_limited``).

It owns ONLY the pure aggregation math: given already-resolved active-bullpen
coverage counts, it derives ``high`` / ``medium`` / ``low`` / ``unknown`` and the
matching ``data_state``, per the approved contract. It reuses the canonical
active-bullpen authority and the completed-appearance ledger via its callers — it
resolves neither roster membership nor rest itself.

Approved contract (DECISION 3/4/5):

* ``high``    — authority complete, source current, every active-bullpen pitcher
                has a usable current record, no material conflict.
* ``medium``  — authority complete, source current, no conflict, and bounded
                partial coverage: >= 75% usable AND >= 6 usable AND <= 2 unresolved.
* ``low``     — authority complete but coverage insufficient (below the medium bar),
                a material source conflict, an incomplete source window, or
                applicable sync failures.
* ``unknown`` — no authoritative active-bullpen roster to classify against
                (fail closed; never silently downgraded to low/medium).

``data_state`` follows confidence: ``fresh`` for high/medium (bounded partial
coverage still communicates "fresh" — the limitation carries the caveat),
``incomplete`` for coverage-insufficient low, ``stale`` for a genuinely outdated
source, ``missing`` when there is no authority.

Integer-only comparisons keep the 75% boundary deterministic (no float drift).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


CONFIDENCE_HIGH = 'high'
CONFIDENCE_MEDIUM = 'medium'
CONFIDENCE_LOW = 'low'
CONFIDENCE_UNKNOWN = 'unknown'

DATA_STATE_FRESH = 'fresh'
DATA_STATE_INCOMPLETE = 'incomplete'
DATA_STATE_STALE = 'stale'
DATA_STATE_MISSING = 'missing'

# Approved medium-confidence thresholds (DECISION 3).
MIN_MEDIUM_USABLE = 6
MAX_MEDIUM_UNRESOLVED = 2
MEDIUM_COVERAGE_NUMERATOR = 3     # >= 75% expressed as usable*4 >= active*3
MEDIUM_COVERAGE_DENOMINATOR = 4

# Structured limitation code for bounded partial coverage (DECISION 5).
PARTIAL_COVERAGE_LIMITATION_CODE = 'partial_active_bullpen_coverage'

# Non-sensitive reason codes surfaced on the trust read.
REASON_COMPLETE_COVERAGE = 'complete_active_bullpen_coverage'
REASON_PARTIAL_COVERAGE = 'partial_active_bullpen_coverage'
REASON_INSUFFICIENT_COVERAGE = 'insufficient_active_bullpen_coverage'
REASON_NO_ACTIVE_BULLPEN_AUTHORITY = 'active_bullpen_authority_unavailable'
REASON_SOURCE_CONFLICT = 'material_source_conflict'
REASON_SOURCE_WINDOW_INCOMPLETE = 'source_window_incomplete'
REASON_SOURCE_STALE = 'source_stale'


@dataclass(frozen=True)
class TeamCoverageAssessment:
    """Deterministic team-level active-bullpen coverage verdict."""

    confidence: str
    data_state: str
    active_bullpen_count: int
    usable_record_count: int
    unresolved_record_count: int
    reason_code: str
    coverage_numerator: int          # usable * 4 (for transparency; no float)
    coverage_denominator: int        # active * 4

    @property
    def is_partial(self) -> bool:
        return self.confidence == CONFIDENCE_MEDIUM

    def coverage_limitation(self) -> Optional[dict]:
        """Structured partial-coverage limitation (DECISION 5), or None.

        Emitted for medium (bounded partial coverage) and for coverage-insufficient
        low so the operator/read can see exactly how many active-bullpen records were
        usable vs unresolved. Never exposes a pitcher identity or a raw payload.
        """
        if self.confidence in (CONFIDENCE_HIGH, CONFIDENCE_UNKNOWN):
            return None
        return {
            'code': PARTIAL_COVERAGE_LIMITATION_CODE,
            'active_bullpen_count': self.active_bullpen_count,
            'usable_record_count': self.usable_record_count,
            'unresolved_record_count': self.unresolved_record_count,
        }


def _meets_medium_coverage(active: int, usable: int, unresolved: int) -> bool:
    """The approved bounded-partial-coverage gate (DECISION 3), integer-only.

    >= 75% usable AND >= 6 usable AND <= 2 unresolved.
    """
    if usable < MIN_MEDIUM_USABLE:
        return False
    if unresolved > MAX_MEDIUM_UNRESOLVED:
        return False
    # usable / active >= 3/4  <=>  usable*4 >= active*3
    return usable * MEDIUM_COVERAGE_DENOMINATOR >= active * MEDIUM_COVERAGE_NUMERATOR


def assess_team_coverage(
    *,
    authority_complete: bool,
    source_current: bool,
    active_bullpen_count: int,
    usable_record_count: int,
    unresolved_record_count: int,
    source_conflict: bool = False,
    source_window_complete: bool = True,
) -> TeamCoverageAssessment:
    """Classify a team's active-bullpen readiness trust deterministically.

    Fail-closed precedence:

    1. No authoritative active bullpen -> ``unknown`` (never downgraded to low).
    2. A material source conflict, or an incomplete required source window ->
       ``low`` / ``incomplete`` (bounded coverage cannot rescue an unsafe source).
    3. Source genuinely outdated -> ``low`` / ``stale``.
    4. Otherwise, coverage decides: complete -> ``high``; bounded partial (approved
       thresholds) -> ``medium``; insufficient -> ``low`` / ``incomplete``.

    ``usable_record_count`` + ``unresolved_record_count`` must equal
    ``active_bullpen_count`` (every active-bullpen record is one or the other).
    """
    active = max(int(active_bullpen_count), 0)
    usable = max(int(usable_record_count), 0)
    unresolved = max(int(unresolved_record_count), 0)

    # 1. No authoritative active bullpen -> unknown (fail closed).
    if not authority_complete or active <= 0:
        return TeamCoverageAssessment(
            confidence=CONFIDENCE_UNKNOWN,
            data_state=DATA_STATE_MISSING,
            active_bullpen_count=active,
            usable_record_count=usable,
            unresolved_record_count=unresolved,
            reason_code=REASON_NO_ACTIVE_BULLPEN_AUTHORITY,
            coverage_numerator=usable * MEDIUM_COVERAGE_DENOMINATOR,
            coverage_denominator=active * MEDIUM_COVERAGE_DENOMINATOR,
        )

    # 2. Material source conflict or incomplete source window -> low / incomplete.
    if source_conflict:
        return _low(active, usable, unresolved, REASON_SOURCE_CONFLICT, DATA_STATE_INCOMPLETE)
    if not source_window_complete:
        return _low(active, usable, unresolved, REASON_SOURCE_WINDOW_INCOMPLETE, DATA_STATE_INCOMPLETE)

    # 3. Genuinely outdated source -> low / stale.
    if not source_current:
        return _low(active, usable, unresolved, REASON_SOURCE_STALE, DATA_STATE_STALE)

    # 4. Coverage decides.
    if usable == active and unresolved == 0:
        return TeamCoverageAssessment(
            confidence=CONFIDENCE_HIGH,
            data_state=DATA_STATE_FRESH,
            active_bullpen_count=active,
            usable_record_count=usable,
            unresolved_record_count=unresolved,
            reason_code=REASON_COMPLETE_COVERAGE,
            coverage_numerator=usable * MEDIUM_COVERAGE_DENOMINATOR,
            coverage_denominator=active * MEDIUM_COVERAGE_DENOMINATOR,
        )
    if _meets_medium_coverage(active, usable, unresolved):
        return TeamCoverageAssessment(
            confidence=CONFIDENCE_MEDIUM,
            data_state=DATA_STATE_FRESH,
            active_bullpen_count=active,
            usable_record_count=usable,
            unresolved_record_count=unresolved,
            reason_code=REASON_PARTIAL_COVERAGE,
            coverage_numerator=usable * MEDIUM_COVERAGE_DENOMINATOR,
            coverage_denominator=active * MEDIUM_COVERAGE_DENOMINATOR,
        )
    return _low(active, usable, unresolved, REASON_INSUFFICIENT_COVERAGE, DATA_STATE_INCOMPLETE)


def _low(active, usable, unresolved, reason_code, data_state) -> TeamCoverageAssessment:
    return TeamCoverageAssessment(
        confidence=CONFIDENCE_LOW,
        data_state=data_state,
        active_bullpen_count=active,
        usable_record_count=usable,
        unresolved_record_count=unresolved,
        reason_code=reason_code,
        coverage_numerator=usable * MEDIUM_COVERAGE_DENOMINATOR,
        coverage_denominator=active * MEDIUM_COVERAGE_DENOMINATOR,
    )


# ---------------------------------------------------------------------------
# Active-bullpen population resolution (UX-001 production correction).
#
# The coverage math above already judges a team against its canonical current
# active bullpen. The readiness DISTRIBUTIONS that decide the internal status
# must be built from that same population, or a team can be judged trustworthy
# on one population and stressed on another. Resolving membership lives here so
# both consumers share one recipe and one resolution per team.
# ---------------------------------------------------------------------------


def resolve_active_bullpen_membership(team_id, reference_date):
    """Return ``(member_pitcher_ids, authority_complete)`` for a team.

    Reuses the Canonical Roster Authority (active roster + Role Authority, gated
    by the public roster-readiness source). No second roster filter is
    introduced here. Fails closed — an absent team id, an unreadable authority,
    or an authority that identifies no active-bullpen arm all return an empty
    set with ``authority_complete`` False, which the trust classifier turns into
    ``unknown`` rather than a silently downgraded state.
    """
    if team_id is None:
        return frozenset(), False
    try:
        # Deferred: the roster authority lives in the api layer, which imports
        # this module's siblings.
        from api.bullpen import build_team_roster_authority

        authority = build_team_roster_authority(team_id, reference_date=reference_date)
        arms = (authority.get('evidence') or {}).get('bullpen_arms') or []
        ids = frozenset(
            arm.get('pitcher_id') for arm in arms if arm.get('pitcher_id') is not None
        )
        return ids, bool(ids)
    except Exception:
        return frozenset(), False


def select_active_bullpen_records(records, member_ids):
    """Keep only the classified records belonging to the canonical active bullpen.

    Everything else on the team — starters, injured-list arms, off-active
    organizational depth, and any other pitcher carrying a fatigue score — is
    excluded from the readiness distributions. Those records are not discarded
    from the product: the Team Board still shows them as roster and off-active
    context. They simply do not decide the current active bullpen's Team State.
    """
    member_ids = member_ids or frozenset()
    selected = []
    for record in records or ():
        pitcher_id = getattr(record.get('pitcher'), 'id', None)
        if pitcher_id is not None and pitcher_id in member_ids:
            selected.append(record)
    return tuple(selected)
