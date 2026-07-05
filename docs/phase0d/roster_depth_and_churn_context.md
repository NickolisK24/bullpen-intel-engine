# Phase 0D-06 - Roster Depth And Churn Context Evidence

## Scope

This branch defines the internal-only roster-depth and transaction-churn
evidence family. It writes through the existing `evidence_objects` and
`evidence_citations` tables and adds no new evidence tables.

The family uses:

- `roster_status_snapshots` as current-state authority
- `player_transactions` as typed explanatory facts
- `player_transaction_sync_windows` as the transaction-window coverage
  denominator
- stored `roster_snapshot_alignment` and `explanatory_linkage_eligible` fields
  only

## Registered Rules

0D-06 registers 14 rules, all v1 and all `internal_only`.

1. `team_active_pitcher_census v1`
2. `team_active_reliever_count v1`
3. `team_roster_snapshot_state v1`
4. `pitcher_il_placement_context v1`
5. `pitcher_il_activation_context v1`
6. `team_public_il_count v1`
7. `team_transaction_churn_window v1`
8. `team_transaction_category_counts_window v1`
9. `team_option_recall_churn v1`
10. `team_roster_movement_churn v1`
11. `team_depth_delta_daily v1`
12. `team_roster_changes_explained v1`
13. `team_roster_changes_unexplained v1`
14. `team_transaction_alignment_state v1`

## Definitions

### RULE 1 - team_active_pitcher_census v1

The count of pitchers on the team's active roster per the current roster
snapshot.

Current snapshot:

- latest `roster_status_snapshots` rows with `snapshot_date <= D`
- same-day only when `snapshot_date == D`
- stale when `snapshot_date < D`

Active pitcher:

- `roster_status = active`
- `active_roster = true`
- pitcher-scoped snapshot row

Two-way players:

- include if pitching eligibility is sourced through `two_way_eligible` or
  position fields
- state their count separately

This census counts the population the bullpen draws from. It does not partition
starters from relievers. It does not state availability.

Completeness:

- complete only with same-day snapshot and known active-roster membership for
  every counted row
- membership unknown -> PARTIAL lower-bound count with unknown-membership count
  rendered
- stale snapshot -> UNKNOWN
- missing snapshot -> UNKNOWN
- degraded source state -> degraded with reason

### RULE 2 - team_active_reliever_count v1

Allowed completeness: `('unknown',)`.

How many active-roster pitchers are relievers.

UNKNOWN by design. BaseballOS has no official role source. Role inference is
out of scope for this family. 0D-07 may produce usage observations, but usage
observations are not a roster partition. Whether any reliever/starter partition
is ever authorized is a Phase 0D-09 decision.

This rule exists so the gap is citable.

### RULE 3 - team_roster_snapshot_state v1

The team's roster-snapshot basis for the evidence date:

- latest snapshot date
- snapshot age in days
- row coverage
- cache divergence state if stored
- degraded source state if stored

This is descriptive data-state evidence only.

### RULE 4 - pitcher_il_placement_context v1

A public IL placement fact for a pitcher from a typed transaction.

State only:

- IL list type as sourced
- transaction date
- retroactive date when sourced

Safe phrasing:

`On the 15-day IL per MLB transaction data, placed 2026-06-28.`

If retroactive date exists:

`On the 15-day IL per MLB transaction data, placed 2026-06-28, retroactive to 2026-06-26.`

No injury description, severity, cause, or return timetable exists in this
claim.

A pitcher without such a fact may only be described as:

`no public IL placement fact in stored data`

That phrasing is never a health claim.

### RULE 5 - pitcher_il_activation_context v1

A public IL activation/removal fact for a pitcher from a typed transaction.

Safe phrasing:

`Activated from the 15-day IL per MLB transaction data on 2026-07-02.`

This states the roster event only. It never states readiness, recovery,
availability, or health.

### RULE 6 - team_public_il_count v1

The count of the team's pitchers whose CURRENT roster snapshot status is IL.

The roster snapshot decides the count. Aligned IL placement transactions are
cited as explanation where they exist.

A snapshot-IL pitcher without a matching stored transaction still counts, with
missing linkage noted.

A placement transaction without current snapshot IL status does not count as
current IL.

This is a count of public IL facts, never a statement about anyone's health or
about pitchers not on the IL.

Complete only on a same-day snapshot with known membership.

### RULE 7 - team_transaction_churn_window v1

The count of stored typed transactions touching the team as source or
destination over the trailing 7-day and 14-day windows ending on the evidence
date.

Windows:

- 7-day: `[D-6, D]`
- 14-day: `[D-13, D]`

Complete only when transaction sync-window coverage shows every day in the
window was successfully fetched.

Uncovered days make the count a lower-bound PARTIAL with uncovered ranges
cited.

An unfetched day is never "no transactions."

This is a descriptive count of roster movement, not instability, pressure, or
quality judgment.

Thresholds: `window_days = 7 and 14`.

### RULE 8 - team_transaction_category_counts_window v1

The team's windowed transaction counts broken out by stored normalized
categories.

Use exactly the categories the ingestion stores. Do not invent categories.

Expected supported categories include:

- `option`
- `recall`
- `trade`
- `DFA`
- `outright`
- `release`
- `selection`
- `activation`
- `IL placement`
- `IL activation`
- `unknown`

Unknown types are counted as unknown-type, never interpreted.

Same coverage validity as the total churn count.

Thresholds: `window_days = 7 and 14`.

### RULE 9 - team_option_recall_churn v1

Option and recall movement for the team over the trailing 7-day and 14-day
windows:

- option count
- recall count
- count of players appearing in more than one option/recall event in the window

Repeat movement is stated as a count with players cited.

Do not use shuttle, instability, pressure, or quality language.

Same coverage validity as other churn rules.

Thresholds: `window_days = 7 and 14`.

### RULE 10 - team_roster_movement_churn v1

DFA, outright, release, claim, trade, and contract-selection movement for the
team over trailing 7-day and 14-day windows.

Count by category with players cited.

Cross-team moves count for both source and destination team from each team's
perspective.

Same coverage validity as other churn rules.

Thresholds: `window_days = 7 and 14`.

### RULE 11 - team_depth_delta_daily v1

The day-over-day change in the team's active-pitcher census between:

- prior product day's same-day snapshot
- evidence date's same-day snapshot

State:

- count change
- named additions
- named removals

Requires both snapshots for their dates with known membership.

Missing or stale side makes delta UNKNOWN.

This states movement only. It does not state availability, readiness, or depth
quality.

### RULE 12 - team_roster_changes_explained v1

Of the evidence date's census additions and removals, those explained by an
aligned, explanatory-eligible typed transaction.

A change is explained only when the stored alignment facts support:

- matching player
- team perspective
- date window
- `explanatory_linkage_eligible`

Each explained change cites:

- prior/current snapshot rows where stored
- explaining transaction

A transaction explains a change. It never overrides what snapshots say
happened.

### RULE 13 - team_roster_changes_unexplained v1

Census additions and removals with no aligned explanatory transaction in stored
data.

State plainly as unexplained.

Cite:

- relevant snapshot rows
- searched transaction window / coverage basis

Never force-explain. Never guess. Never treat unexplained as an error by
itself.

### RULE 14 - team_transaction_alignment_state v1

The alignment quality of the team's windowed transactions against roster
snapshots, rolled up from stored per-row alignment.

Report counts of:

- aligned
- misaligned
- no-snapshot
- unknown alignment
- unknown-type transactions

This is descriptive data-quality evidence that later reads can cite when
transaction explanation is weak.

Thresholds: `window_days = 7 and 14`.

## Deliverable Mapping

- Bullpen census resolves to active-pitcher census.
- Reliever count is locked UNKNOWN.
- Reliever/starter partition decision is deferred to 0D-09.

## Authority And Explanation

Snapshots decide current state. Transactions explain movement.

A transaction never overrides the current roster snapshot. A placement
transaction without current snapshot IL status does not count as current IL. A
snapshot IL pitcher without a matching placement transaction still counts, with
the missing linkage noted.

## Transaction Window Coverage

The existing `player_transaction_sync_windows` table is the coverage
denominator. A transaction window is complete only when successful sync-window
rows cover every date in `[D-6, D]` or `[D-13, D]`.

If a date is not covered by a successful sync-window row, churn evidence becomes
lower-bound PARTIAL and cites the uncovered ranges. An unfetched date is never
treated as a zero-transaction date.

No new transaction coverage table is added.

## Alignment

0D-06 consumes stored `roster_snapshot_alignment` and
`explanatory_linkage_eligible` values. It does not recompute alignment locally.

Aligned rows may explain changes. Misaligned, no-snapshot, unknown, and
unknown-type rows are counted as context only and never explain a change.

## Depth Delta

Depth delta requires both the prior product-day snapshot and evidence-date
snapshot. Both sides must have known active-roster membership. Rows with unknown
membership are excluded and cited; the delta fails closed rather than guessing
direction.

Explained and unexplained changes are derived after snapshot set arithmetic.
Transactions explain changes only when stored alignment supports the linkage.

## Reason Codes

- `snapshot_missing`
- `snapshot_stale`
- `snapshot_membership_unknown`
- `snapshot_coverage_incomplete`
- `snapshot_cache_divergence`
- `reliever_partition_unavailable`
- `transaction_window_uncovered`
- `transaction_type_unknown`
- `alignment_misaligned`
- `alignment_no_snapshot`
- `alignment_unknown`
- `delta_prior_snapshot_unavailable`
- `change_unexplained`
- `no_public_il_fact`
- `source_family_not_ready`

## Limitations

- Roster snapshots cover pitchers; this census counts pitchers only.
- Transaction lower-bound counts mean at least one date lacks successful
  coverage.
- Reliever count is unavailable by design.
- IL evidence states public roster events only.

## Citation Requirements

- Census, IL, and delta objects cite the snapshot rows used.
- Churn objects cite counted transactions and transaction sync-window rows with
  `citation_role = window_coverage`.
- Every transaction citation includes `transaction_key`, normalized category,
  team perspective, transaction date, and alignment fields where used.
- Explained changes cite snapshot rows and the explaining transaction.
- Unexplained changes cite snapshot rows and the searched transaction-window
  basis.
- No object emits without citations.

## Explicit Non-Claims

0D-06 does not make:

- health claims
- injury severity claims
- return timetable claims
- availability/readiness/fatigue/pressure/trust/confidence claims
- healthy/injury-free/full strength/nobody-is-hurt/cleared/ready/available
  claims
- role claims
- reliever/starter partition claims
- manager/front-office intent claims
- team quality/depth quality judgments
- prediction claims
- betting/odds claims
- raw transaction JSON claims
- free-text injury description claims
- public product surface changes
- frontend changes
- public API/copy changes
- score/rank/grade claims
- pitch-level/Statcast claims
