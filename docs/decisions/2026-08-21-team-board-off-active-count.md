# Team Board Off-Active Count Authority

## Decision

The Team Board Bullpen Summary may publish an exact Off-Active Count by
projecting the existing canonical Roster Authority field
`counts.inactive_roster_context_count`. The Team Board does not count rendered
rows, transaction events, roster snapshots, or pitcher cards.

The additive public contract is `team_board_off_active_count_v1`. Its source is
`roster_authority_v1` version `2026-06-25.foundation`, which is already frozen
inside the trusted Team Board publication.

## Population and current-state authority

The population is the canonical full bullpen-eligible roster population built
through `eligible_bullpen_pitcher_contexts` with inactive and stale context
included. This is the same view-invariant population that feeds the deeper
Roster Context read. Current classified roster status partitions each canonical
pitcher identity exactly once into active, off-active, or unconfirmed context.
Historical transaction rows and historical roster snapshots are not counted.

The qualifying off-active categories are:

- injured list;
- optioned or minors;
- 40-man, not active;
- restricted or special list;
- non-roster depth.

Active-roster pitchers and pitchers with unconfirmed roster status are excluded.
The bullpen-relevance rule is inherited from the canonical bullpen-eligible
population; organizational membership alone does not qualify a pitcher.

The represented date is the roster readiness `data_through` date, falling back
only to the frozen Roster Authority reference date. The projection does not read
the clock or current mutable roster state.

## Qualification and unknown behavior

The number is available only when public roster readiness authorizes current
claims and does not withhold roster-dependent counts. The canonical count must
be a non-negative integer, its off-active evidence must contain the same number
of distinct valid pitcher identities, its qualifying category counts must
reconcile, and active or unconfirmed evidence must not overlap it.

Even when source readiness is generally current, any nonzero canonical
`roster_unknown_count` withholds the exact Off-Active Count. A candidate whose
current roster bucket is unconfirmed could belong in the off-active population,
so the known subset is not presented as a complete total.

A proven empty population publishes numeric zero. Missing readiness, an
incompatible authority version, a missing reference date, malformed or duplicate
evidence, a category mismatch, or population overlap withholds only Off-Active
Count. Unknown is never converted to zero.

## Relationship to Roster Context

The Bullpen Summary count exactly equals the named `Off the active roster`
evidence population in Roster Context when the authority qualifies. Recent
Transactions remains a separate chronology and cannot add to or subtract from
the count. The frontend renders the backend value and the backend-owned context
label verbatim and performs no roster classification or arithmetic.

## Scope

This decision does not change Roster Authority, roster-status classification,
Recent Transactions, active-bullpen membership, Recently Used Arms, Rest Status,
Performance, workload, Team State, Roles and Deployment, Rotation Impact, What
Changed, daily sync, or historical publication behavior.
