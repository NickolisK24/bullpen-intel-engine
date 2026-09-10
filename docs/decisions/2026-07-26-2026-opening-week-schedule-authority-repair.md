# Decision: 2026 opening-week schedule-authority repair (Foundation 2 completion)

- **Date:** 2026-07-26
- **Status:** Implemented (repository work only), retry-safe (contract v2). No production
  schedule repair, no production backfill, no production write, no Foundation 3.
- **Scope:** Restore the MISSING canonical `ScheduledGame` authority for exactly 47
  completed 2026 opening-week regular-season games so the existing Foundation 1/2
  resolver and backfill can attribute their 418 pitching appearances. No migration, no
  performance metric, no direct appearance-team write.

## Decision statement

The 418 remaining 2026 legacy appearance-team rows belong to 47 completed regular-season
games with missing canonical schedule authority. The repair restores official schedule
authority first and then relies on the existing governed appearance-team resolver and
backfill. No appearance team is assigned directly from current roster or current-team
data.

## 1. Foundation 2 production-complete audit result

The merged production residual audit returned `result=pass`, `exit_code=0`,
`residual_population.total_rows=418`, `distinct_games=47`, `exact_backfill_eligible_rows=0`,
`unclassified_rows=0`, `category_totals_reconcile=true`, `invalid_stored_states=0`,
`foundation_2_status=production_complete`. Every residual row classified `no_schedule_rows`.

## 2. Exact 418-row / 47-game residual evidence

All 418 rows are inside the campaign window, dated 2026-03-25 through 2026-03-29,
`game_type='R'`, with no `ScheduledGame` and no `CompletedGameContext` authority. The 47
`game_pk` values are pinned as a fixed allowlist in the repair service
(`TARGET_GAMES`, ordered by `(game_date, game_pk)`: 1 game on 03-25, 11 on 03-26, 8 on
03-27, 15 on 03-28, 12 on 03-29). The repair never broadens beyond this set; a production
residual set that no longer matches these 47 fails closed.

## 3. Why all 47 games are aggregation-relevant regular-season authority gaps

These are completed regular-season (`R`) games; their appearances belong in any canonical
2026 regular-season bullpen aggregation. The residual audit's
`rows_relevant_through_campaign_cutoff=0` reflects the current evidence model (a game with
no schedule authority cannot be proven relevant), NOT proof of irrelevance — so the gap is
repaired rather than omitted.

## 4. Investigation root cause

`GameLog` is populated per-pitcher from the MLB per-season `gameLog` feed
(`mlb_api.get_pitcher_game_logs` → `sync._ingest_game_log_split` / `pitcher_game_log_backfill`),
and a completed status-bearing split is inserted independent of the schedule ledger. The
schedule/ledger ingestion default `start_date` is `2026-03-30`
(`.github/workflows/baseballos-production-maintenance.yml`), so `scheduled_games` was
populated only from 2026-03-30 onward. Opening week 2026-03-25..29 falls strictly before
that start date, so those 47 games were never ingested into `ScheduledGame` — while the
per-pitcher lane still captured their appearances. `resolve_from_schedule` reads
`ScheduledGame` only, so those appearances could never resolve. The MLB schedule endpoint
returns these games (ingestion is a pass-through with no season-start filter); the fix is
to ingest that window's authority for the 47 games.

## 5. Official MLB authority contract

Per target date the repair calls the existing `mlb_client.get_schedule(date, date)` once
(the client exposes no single-`gamePk` schedule method), indexes the returned games by
`gamePk`, and selects the approved set. A game is repairable only when its official
evidence proves: exact `gamePk`; `officialDate` equal to the approved date; `gameType='R'`;
`status_state='final'` (via `game_finality.classify_status`); a present home team id AND
away team id; a single, non-conflicting source record; and no contradiction with the
appearances' stored opponent abbreviations (opponent text is a contradiction check only,
never the repair authority). Any missing/non-final/postponed/suspended/unsupported/
duplicate/contradictory game fails the whole run closed.

## 6. Canonical ScheduledGame persistence path

The repair does not invent a row shape: apply delegates each game to the existing
`schedule_ingestion.ingest_games([game], source='opening_week_schedule_repair_2026',
commit=False)` — the same canonical writer `intraday_schedule_repair` uses — which upserts
both team sides (`_upsert_row`, keyed `(team_id, game_pk)`, idempotent) plus the sibling
`SlateGame`, and commits per game. Rows are written with the official home/away sides,
opponent ids, official date, `game_type`, and `status_state='final'`.

## 7. CompletedGameContext decision

`CompletedGameContext` is deliberately NOT written by the repair. The Foundation 1 resolver
reads `ScheduledGame` only (`resolve_from_schedule`); schedule ingestion never generates
context; and the Foundation 2 backfill resolves the appearances via its box-score tier,
cross-checked against the repaired schedule, when context is absent. `CompletedGameContext`
remains the separate existing postgame/backfill path and is reported as
`skipped_count=47`.

## 8. Dry-run-first workflow, confirmation & fingerprint controls

Dry run is the default (zero writes; a SQL-capture test proves no INSERT/UPDATE/DELETE).
Apply requires `apply=True`, the exact confirmation phrase
`RUN_2026_OPENING_WEEK_SCHEDULE_REPAIR`, AND a matching `expected_fingerprint` — all checked
before any write. The fingerprint (contract v2) binds the repair + resolver contract
versions, season, campaign window, ordered target `game_pk` set, per-game official evidence
(date, type, final status code, home/away ids, doubleheader/game number, planned rows,
context action), **each game's existing-authority disposition and normalized existing
summary and planned write count**, the missing/already_satisfied/conflicting totals,
expected residual/game counts, and the migration head — never timestamps or unstable
ordering. The v2 bump means any v1 dry-run fingerprint can no longer approve an apply.

## 9. Retry-safe existing-authority dispositions (canonical equivalence)

Apply commits ONE game per transaction and stops at the first failure, so a partial apply
leaves earlier games committed. Rather than refuse every later retry, the planner classifies
each of the 47 target games against the freshly fetched official evidence into exactly one
deterministic, mutually exclusive disposition (totals always reconcile to 47):

- **missing** — no canonical schedule authority exists (no `ScheduledGame` rows and no
  sibling `SlateGame`). Plan the canonical two-sided write; write only in approved apply.
- **already_satisfied** — the complete, correct authority already exists: exactly two
  `ScheduledGame` sides keyed `(team_id, game_pk)`, each with the right opponent, home/away
  orientation, official date, `game_type`, final `status_state`, and doubleheader/game-number
  metadata, PLUS a consistent sibling `SlateGame` (home/away/game_number/doubleheader and a
  `completed` state). Skip with zero writes; the game is still bound into the fingerprint and
  report.
- **conflict** — partial or contradictory authority: one side only, an extra/duplicate side,
  any mismatched identity/opponent/orientation/date/type/finality/doubleheader field, or an
  absent/contradictory sibling `SlateGame`. Fail closed; never silently overwrite. A game
  whose official evidence is itself unusable is also a conflict, keeping its specific
  official-evidence reason code.

"already_satisfied" is NOT "some rows exist": `_schedule_conflict_reason` /
`_slate_conflict_reason` compare every authority-determining field the canonical writer
(`_upsert_row` + `upsert_slate_game`) persists, indexed by `team_id` so the result is
independent of row order. Any field the schema does not store is not invented; no stored
authority field is ignored.

Each missing game is ingested and committed in its own transaction; a per-game ingest error
rolls back only that game and stops the run (stop-at-first-failure), so earlier games stay
committed and later games are untouched. A retry therefore skips previously committed games
as `already_satisfied`, plans and writes only the remaining `missing` games, and fails closed
on any `conflict`. A rerun after all 47 are complete is a valid PASS/0 no-op (zero writes).
The completed `ScheduledGame` rows themselves are the durable progress ledger — no
repair-state table, checkpoint, or marker is added. The run also fails closed on residual
set/count mismatch, migration-head mismatch, invalid stored states, or any official-evidence
problem.

## 9a. Operator recovery after a partial apply

1. Inspect the failed apply artifact (`games_committed`, `failed_games`, `apply` block).
2. Correct the external/transient cause (source availability, connectivity) WITHOUT manually
   editing target schedule rows.
3. Run a new schedule-repair dry run.
4. Confirm the committed games now classify `already_satisfied` and the remainder `missing`
   (and `games_conflicting=0`).
5. Approve the NEW fingerprint (it differs from the pre-partial one).
6. Run apply with the new fingerprint — only the remaining `missing` games are written.
7. Repeat until all 47 games are `already_satisfied`.
8. Run the existing Foundation 2 backfill dry run → approve → apply.
9. Run the residual audit and require `total_rows=0`.

## 10. Post-repair backfill sequence & residual-audit acceptance

The repair writes NO `GameLog` appearance-team field. After schedule authority exists, the
operator runs the existing Foundation 2 backfill (dry run → approved fingerprint → apply)
which discovers the 47 games and resolves the 418 appearances (fixtures prove
`proposed_resolved=418 / unresolved=0 / conflict=0`, `games_committed=47`,
`season_null_legacy=0`, `invalid_stored_states=0`), then the residual audit
(`total_rows=0`). The full chain is proven end to end in fixtures on PostgreSQL and SQLite.

## 11. Boundaries

No migration (head stays `a4f1c7e9b3d2`); no direct appearance-team mutation; no performance
aggregation, ERA, saves, rankings, Team State, or Share Card change. Foundation 3 remains
blocked until the production repair + backfill + residual audit confirm zero 2026
legacy-NULL rows. SC-05 remains blocked.
