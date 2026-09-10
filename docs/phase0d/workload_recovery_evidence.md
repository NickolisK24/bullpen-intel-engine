# Phase 0D-02 Workload Recovery Evidence

## Scope

This branch adds the first production Phase 0D evidence family: internal-only
reliever workload and recovery facts. The family writes to the existing
`evidence_objects` and `evidence_citations` tables through the Phase 0D-01
contract. It adds no public surface, no public serializer, no frontend UI, and
no new evidence table.

## Rule Definitions

All rules are version `v1`, default to `internal_only`, and require the
`game_logs` and `slate_coverage` source families.

1. `workload_last_final_appearance`: Records the pitcher last final appearance
   date and game within the trailing 30 product-day lookback ending on the
   evidence date.
2. `workload_days_of_rest`: Records the count of full off-days between the
   pitcher most recent final appearance and the evidence date within the
   trailing 30 product-day lookback.
3. `workload_window_appearances`: Counts final appearances in each trailing 3,
   5, 7, and 14 product-day window ending on the evidence date; doubleheader
   appearances count as separate appearances on one distinct appearance day.
4. `workload_window_pitches`: Sums pitches thrown in final appearances for each
   trailing 3, 5, 7, and 14 product-day window ending on the evidence date when
   every included pitch count is known.
5. `workload_window_outs`: Sums outs recorded in final appearances for each
   trailing 3, 5, 7, and 14 product-day window ending on the evidence date.
6. `workload_window_batters_faced`: Sums batters faced in final appearances for
   each trailing 3, 5, 7, and 14 product-day window ending on the evidence date
   when every included batters-faced count is known.
7. `usage_back_to_back`: Records that a relief-scoped appearance occurred on
   the evidence date and on the immediately prior product day.
8. `usage_three_in_four`: Records that relief-scoped appearances occurred on at
   least 3 distinct appearance days in the trailing 4 product days ending on the
   evidence date.
9. `usage_four_in_six`: Records that relief-scoped appearances occurred on at
   least 4 distinct appearance days in the trailing 6 product days ending on the
   evidence date.
10. `outing_multi_inning`: Records a relief-scoped outing on the evidence date
    with at least 4 outs recorded.
11. `outing_high_pitch`: Records a relief-scoped outing on the evidence date
    with at least 25 pitches thrown.
12. `appearance_short_rest`: Records a relief-scoped appearance on the evidence
    date with at most 1 full off-day since the previous final appearance.

## Threshold Rationale

The 25-pitch outing threshold is a factual workload marker, not a conclusion.
It creates a conservative internal evidence object for a visibly larger relief
outing while avoiding any claim about next-game use, staff preference, or
player condition.

## Emission Policy

The family uses positive-or-unknown emission for flags.

- Rules 1 and 2 emit for the pitcher population.
- Rule 3 emits every 3, 5, 7, and 14 product-day appearance window, including
  provable zero-appearance windows.
- Rules 4, 5, and 6 emit only when the window has at least one appearance.
- Rules 7 through 12 emit when the condition is met.
- Rules 7 through 12 emit `unknown` when the pitcher appeared on the evidence
  date and the condition cannot be determined.
- Rules 7 through 12 emit nothing when the condition is provably false.

Absence of a flag is not a claim.

## Product-Day And Window Behavior

Every trailing window is inclusive of the evidence date. A 3-day window ending
on July 4 covers July 2, July 3, and July 4. A 14-day window ending on July 4
covers June 21 through July 4.

The builder selects pitchers from stored final game logs and emits evidence for
the requested product date. Historical pitchers with stored game logs but no
appearance in the 30-day lookback can receive the bounded
`no_recent_appearance_in_lookback` fact.

## Doubleheaders

Two final appearances on the same product day count as two appearances for
appearance totals. They count as one distinct appearance day for distinct-day
patterns. A same-day doubleheader pair does not satisfy back-to-back usage by
itself.

## Suspended And Resumed Games

Suspended or resumed games are counted once on the product day already carried
by stored game logs and slate coverage. If slate coverage reports unresolved
resumed-game linkage for an affected day, affected window and pattern evidence
fails closed to `unknown` or `partial` with
`ambiguous_resumed_game_in_window`.

## Off Days

A day with zero scheduled games is coverage-complete when stored schedule
material proves the off day. Off days remain in product-day windows and can
create full off-days for rest calculations.

## Incomplete Slate Behavior

When a window contains an incomplete slate day:

- appearance counts become lower-bound `partial` objects;
- pitch, out, and batters-faced sums become `unknown`;
- usage patterns become `unknown` when the pitcher appeared on the evidence
  date;
- the affected day is cited through a `slate_coverage` citation with
  `window_validity` role.

## Missing Game Log Behavior

If no final appearance exists in the 30 product-day lookback, the family can
emit a bounded no-recent-appearance fact with coverage citations. It does not
impute missing appearances, and it does not infer current roster state.

## Unknown Pitch Count Behavior

Any null pitch count required for a sum makes the pitch total `unknown`.
Known rows remain cited, and the trace records `known_count` and
`known_subtotal`. The known subtotal is never rendered as the total.

For outing-level pitch flags, a null pitch count on a relief-scoped evidence
date appearance emits `unknown_pitch_count_for_outing`.

## Unknown Batters Faced Behavior

Any null batters-faced value required for a sum makes the batters-faced total
`unknown`. Known rows remain cited, and the trace records `known_count` and
`known_subtotal`. The known subtotal is never rendered as the total.

## Reason Codes

- `incomplete_slate_day_in_window`
- `rest_window_coverage_gap`
- `unknown_pitch_count_in_window`
- `unknown_batters_faced_in_window`
- `unknown_pitch_count_for_outing`
- `appearance_role_unknown`
- `no_recent_appearance_in_lookback`
- `window_precedes_coverage_history`
- `ambiguous_resumed_game_in_window`
- `source_family_not_ready`

## Citations Required

Every counted or summed `game_logs` row is cited with:

- `source_family=game_logs`
- `source_table=game_logs`
- source row id
- the field names used by the rule
- cited values
- correction metadata where available

Window-validity citations use:

- `source_family=slate_coverage`
- `source_table=slate_coverage`
- `citation_role=window_validity`
- the affected product day as `source_pk`
- coverage fields used by the rule

Objects with no game-log citation are allowed only for provable zero-appearance
windows and bounded no-recent-appearance facts. Those objects cite their slate
coverage basis.

## Explicit Non-Claims

This family makes no claims about:

- availability
- freshness
- fatigue
- readiness
- trust
- confidence
- pressure
- prediction
- score, rank, or grade
- role inference

It also makes no claims about roster status, IL status, manager intent,
pitch-level traits, Statcast data, inherited traffic, clean/traffic context,
starter exposure, or public product labels.

## Calendar Context Dependency Decision

The builder does not read `calendar_context` directly. It reads `game_logs` for
appearance facts and `slate_coverage` for product-day completeness, off days,
postponed-game exclusion, and suspended/resumed linkage safety. Because
`slate_coverage` already encapsulates the calendar/product-day completeness
behavior needed by this branch, `calendar_context` is not registered as an
independent required input family for 0D-02.

## Sync And Recompute

Daily and postgame sync run the workload evidence stage after fatigue
recalculation when enabled by `PHASE0D_EVIDENCE_BUILD`. The stage is fail-soft:
exceptions are dead-lettered, a warning is logged, and sync continues.

When a cited `game_logs` row is corrected, dependent evidence rows are marked
`recompute_needed` through the Phase 0D-01 recompute hook. The workload
evidence rebuild path refreshes only marked evidence keys and preserves prior
claim and invalidation provenance in the computation trace.
