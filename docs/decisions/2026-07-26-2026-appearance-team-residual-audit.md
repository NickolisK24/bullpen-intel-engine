# Decision: Read-only 2026 residual appearance-team audit (Foundation 2 production completion)

- **Date:** 2026-07-26
- **Status:** Implemented (audit only). No residual repair, no performance aggregation,
  no Foundation 3. No production audit executed during implementation.
- **Scope:** Classify, READ-ONLY, every remaining 2026 legacy-NULL appearance-team row
  so the Foundation 2 campaign can be judged complete and the Foundation 3 gate decided
  on evidence. No database write, no migration, no metric.

## Decision statement

The remaining 2026 legacy appearance-team rows are audited read-only before any repair
or performance aggregation is allowed. Every residual row must receive one deterministic
exclusion category, and Foundation 3 remains blocked whenever a completed in-window MLB
appearance lacks trustworthy historical team attribution.

## 1. Foundation 1 production PASS

Foundation 1 (team-at-appearance authority: migration `a4f1c7e9b3d2`, the stored-state
CHECK invariant, the resolver, the read-only production audit) is live and
production-verified.

## 2. Foundation 2 campaign totals

The governed 2026 backfill processed every row eligible under its selection contract:
initial 2026 legacy-NULL 12,490 → processed 12,072 → residual 418. Current production
appearance-team totals: total_game_logs 44,320; resolved 12,458; unresolved 1;
conflict 0; null_legacy (all seasons) 31,861; null_legacy_2026 418; invalid_stored_states 0.

## 3. Full-range no-target verification

A final no-cursor dry run over 2026-01-01..2026-07-25 (batch 500) returned
`inconclusive` / `no_target_rows` / 0 selected / 0 targeted / no writes / exhausted —
proving the cursor campaign skipped nothing still eligible under the contract. The 418
residuals are therefore excluded by one or more eligibility conditions, not skipped.

## 4. Why 418 rows require classification

"96.7% processed" is not a completion criterion. The remaining 3.3% must each be
explained: are they legitimately out of the campaign scope, temporarily ineligible,
in-window data defects, or eligible rows that expose a selection defect? Foundation 3
stays blocked until the residual population is understood.

## 5. Residual target

`GameLog.appearance_team_status IS NULL AND EXTRACT(year FROM game_date) = season`. The
operator supplies season, campaign_start_date, campaign_end_date (default 2026-01-01 /
2026-07-25 — never the wall clock), and bounded row/game detail limits. The report also
buckets the population by inside-window / before-window / after-cutoff / missing-date.

## 6. Classification precedence

Each row gets exactly one primary category by deterministic top-down precedence:
missing_game_date → before_campaign_window → after_campaign_cutoff → missing_game_pk →
no_schedule_rows → no_final_schedule_state → postponed_or_suspended_disqualifier →
contradictory_finality → incomplete_schedule_sides → contradictory_schedule_authority →
exceptional_game_type → eligible_but_not_selected → other_classified_exclusion →
unclassified. Categories are mutually exclusive and reconcile exactly to the residual
total. `missing_game_date` and `missing_game_pk` are structurally unreachable in
production (both columns are NOT NULL) and are expected to be zero.

## 7. Schedule / finality categories

Finality is read from the local `ScheduledGame` ledger exactly as Foundation 2 reads it:
a game is final-eligible when a `final` row exists and no `postponed`/`suspended` row
exists. no_final, postponed/suspended-disqualifier, and contradictory_finality (final +
disqualifier) partition the non-eligible games; incomplete/contradictory sides and
exceptional_game_type refine the final-eligible games. `CompletedGameContext` presence is
reported but is never an attribution source here.

## 8. Foundation 2 query-parity proof

The audit does not re-approximate eligibility: it CALLS the real
`appearance_team_backfill_2026._select_game_keys` (paginated with its own keyset cursor,
no silent cap) to obtain the exact set of game_pks Foundation 2 would select, and counts
residual rows in that set as `exact_backfill_eligible_rows`. The production expected
value is 0; any value > 0 is a critical selection/authority defect → result FAIL,
foundation_2_status incomplete, foundation_3_gate blocked. The audit never repairs those
rows automatically.

## 9. Read-only guarantee

Only SELECTs, bounded in-memory classification, and JSON/summary generation. No INSERT,
UPDATE, DELETE, flush, commit, ORM mutation, backfill, reconciliation write, schedule or
appearance-team mutation, marker, Team State generation, or Share Artifact generation.
A SQL-capture test proves the application database receives only SELECT statements, and
the report carries `database_writes_performed: false`.

## 10. Bounded report contract

One deterministic JSON report: capability, mode, result, exit_code, generated_at,
git_sha, migration_head/expected, inputs, coverage, residual_population, primary_categories
(row/game/percentage), category_totals_reconcile, exact_backfill_eligible_rows,
unclassified_rows, by_month/by_game_type/by_finality_state, schedule_coverage,
context_coverage, bullpen_aggregation_relevance, bounded row/game samples, samples_truncated,
decision_reasons, foundation_2_status, foundation_3_gate, database_writes_performed. All
sample lists are bounded and deterministically ordered; no secrets, connection strings,
raw payloads, or raw exception text.

## 11. Result and exit-code contract

PASS/0 when all rows classified, totals reconcile, invalid_stored_states 0,
exact_backfill_eligible_rows 0, unclassified 0. FAIL/1 when eligible rows remain, totals
do not reconcile, an invalid stored state exists, or the migration head differs.
INCONCLUSIVE/2 when some rows cannot be classified or no residual rows exist.

## 12. Production workflow instructions

The read-only residual audit is a `residual_audit` operation on the manual, dispatch-only
Foundation 2 maintenance workflow (`appearance_team_backfill_2026.yml`): no confirmation
phrase (no write is possible), campaign dates validated before database access, minimal
`contents: read` permissions, masked secrets, bounded timeout, a private 14-day artifact,
and a job summary using the audit's real field names. The founder runs it after merge and
provides the JSON.

## 13. Foundation 2 completion criteria

Foundation 2 is production-complete only when exact_backfill_eligible_rows is 0, all 418
residual rows are explained, every category is a legitimate exclusion or an understood
deferred case, no in-window completed MLB appearance required for aggregation lacks a safe
attribution, and invalid_stored_states remain 0.

## 14. Foundation 3 gate criteria

Foundation 3 may be unblocked only when the residual categories do not compromise season
bullpen aggregation through the approved cutoff, any aggregation-relevant residual rows
have a documented exclusion policy, aggregation can fail closed on unresolved/conflict/
legacy rows, and the data-through boundary is explicit. It stays blocked while any
in-window completed MLB appearance lacks attribution, eligible rows were skipped, relevance
is uncertain, categories do not reconcile, or unclassified rows remain.

## 15–18. No migration / no repair / no performance aggregation / SC-05

No migration, table, checkpoint, classification column, or repair marker is added; the
audit is computed read-only from current evidence and the Alembic head stays
`a4f1c7e9b3d2`. No residual row is modified and no repair is inferred before the
classification report is seen. No bullpen ERA, relief innings, saves, rankings, Team
State, or Share Card performance context is computed. SC-05 remains blocked.
