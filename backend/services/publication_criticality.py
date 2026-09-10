"""Publication-critical vs best-effort work classification (daily-sync trust).

Founder-approved publication-critical contract. The daily sync separates work that
is REQUIRED to establish the current public trusted snapshot ("publication
critical") from best-effort maintenance (historical/enrichment corrections). A
trusted snapshot may publish when every publication-critical requirement is
complete, even when best-effort work is deferred or dead-lettered — but a
publication-critical or unknown-criticality failure must still withhold, and the
existing finality / appearance-ledger / freshness / provenance gates are
unchanged.

This module owns ONE canonical classifier + completeness result. Legacy work
classification consumes the current roster-status and position caches populated
from the same official roster evidence used by canonical Roster Authority; it
introduces no second roster registry and no second slate authority. Unknown
criticality ALWAYS fails closed (treated as publication-critical for the gate).
"""

from __future__ import annotations

from typing import Iterable, Optional

from services.roster_authority import (
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
    roster_status_category_for_status,
)


CRITICALITY_PUBLICATION_CRITICAL = 'publication_critical'
CRITICALITY_BEST_EFFORT = 'best_effort'
CRITICALITY_UNKNOWN = 'unknown'

# Explicit current roster positions that cannot belong to BaseballOS's governed
# bullpen population.  Unknown/blank positions are deliberately absent: they
# continue through the roster-status classifier and therefore fail closed when
# roster authority is unknown.  Two-way and pitching positions are also absent.
EXPLICIT_NON_PITCHER_POSITIONS = frozenset({
    'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'OF', 'IF', 'DH', 'PH',
    'PR', 'UT', 'UTIL', 'UTILITY',
})

PUBLICATION_CRITICAL_COMPLETE = 'complete'
PUBLICATION_CRITICAL_INCOMPLETE = 'incomplete'
PUBLICATION_CRITICAL_UNAVAILABLE = 'unavailable'

# Reason codes surfaced on the completeness result (non-sensitive).
REASON_CRITICAL_COMPLETE = 'publication_critical_complete'
REASON_CRITICAL_FAILED = 'publication_critical_failed'
REASON_CRITICAL_UNRESOLVED = 'publication_critical_unresolved'
REASON_UNKNOWN_CRITICALITY = 'unknown_criticality_failure'
REASON_AUTHORITY_UNAVAILABLE = 'publication_critical_authority_unavailable'
REASON_NON_GAMELOG_FAILURE = 'non_gamelog_publication_critical_failure'


def criticality_for_roster_status(roster_status) -> str:
    """Publication criticality for a game-log work item from its pitcher's synced
    canonical roster-status code.

    Reuses the canonical roster-status category
    (``roster_status_category_for_status`` — no second roster registry, and no
    per-team query cost that would itself starve the ingestion budget). This
    status-only primitive remains conservative; ``criticality_for_player`` adds
    the governed explicit-non-pitcher exclusion. Mapping:

    * active MLB roster            -> ``publication_critical``
    * missing / unrecognized code  -> ``unknown`` (fail closed)
    * optioned / IL / off-roster / historical -> ``best_effort``
    """
    category = roster_status_category_for_status(roster_status)
    if category == ROSTER_STATUS_CATEGORY_ACTIVE:
        return CRITICALITY_PUBLICATION_CRITICAL
    if category == ROSTER_STATUS_CATEGORY_UNKNOWN:
        return CRITICALITY_UNKNOWN
    return CRITICALITY_BEST_EFFORT


def criticality_for_player(roster_status, position) -> str:
    """Classify one legacy player GameLog item against the public bullpen scope.

    The legacy repair lane intentionally queries every locally active tracked
    player, including position players who own legitimate pitching appearances.
    An explicitly non-pitching current roster position cannot enter the governed
    active-bullpen population, so its repair fetch is best-effort even when the
    player is on the active MLB roster.  Missing or unfamiliar position evidence
    never creates this exception and retains the fail-closed roster-status result.
    """
    normalized_position = str(position or '').strip().upper()
    if normalized_position in EXPLICIT_NON_PITCHER_POSITIONS:
        return CRITICALITY_BEST_EFFORT
    return criticality_for_roster_status(roster_status)


def build_publication_critical_result(
    *,
    critical_total: int = 0,
    critical_completed: int = 0,
    critical_failed: int = 0,
    critical_unresolved: int = 0,
    unknown_criticality: int = 0,
    best_effort_total: int = 0,
    best_effort_completed: int = 0,
    best_effort_deferred: int = 0,
    non_gamelog_critical_failed: int = 0,
    authority_available: bool = True,
    reason_codes: Optional[Iterable[str]] = None,
) -> dict:
    """One authoritative publication-critical completeness result (fail-closed).

    ``complete`` requires: zero publication-critical failures (game-log AND
    non-game-log), zero unresolved publication-critical work, and zero
    unknown-criticality failures. Best-effort deferred work may be > 0 and never
    blocks. If the criticality authority itself was unavailable, the result is
    ``unavailable`` (fail closed — never ``complete``).
    """
    reasons = list(reason_codes or [])
    critical_failed_total = int(critical_failed) + int(non_gamelog_critical_failed)

    if not authority_available:
        status = PUBLICATION_CRITICAL_UNAVAILABLE
        complete = False
        if REASON_AUTHORITY_UNAVAILABLE not in reasons:
            reasons.append(REASON_AUTHORITY_UNAVAILABLE)
    else:
        complete = (
            critical_failed_total == 0
            and int(critical_unresolved) == 0
            and int(unknown_criticality) == 0
        )
        status = (
            PUBLICATION_CRITICAL_COMPLETE if complete else PUBLICATION_CRITICAL_INCOMPLETE
        )

    if critical_failed_total:
        reasons.append(REASON_CRITICAL_FAILED)
    if critical_unresolved:
        reasons.append(REASON_CRITICAL_UNRESOLVED)
    if unknown_criticality:
        reasons.append(REASON_UNKNOWN_CRITICALITY)
    if non_gamelog_critical_failed:
        reasons.append(REASON_NON_GAMELOG_FAILURE)
    if complete and not reasons:
        reasons.append(REASON_CRITICAL_COMPLETE)

    return {
        'status': status,
        'complete': complete,
        'publication_critical_total': int(critical_total),
        'publication_critical_completed': int(critical_completed),
        'publication_critical_failed': critical_failed_total,
        'publication_critical_unresolved': int(critical_unresolved),
        'unknown_criticality': int(unknown_criticality),
        'best_effort_total': int(best_effort_total),
        'best_effort_completed': int(best_effort_completed),
        'best_effort_deferred': int(best_effort_deferred),
        'non_gamelog_publication_critical_failed': int(non_gamelog_critical_failed),
        'reason_codes': list(dict.fromkeys(reasons)),
    }
