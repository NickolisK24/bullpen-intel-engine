# Decision: Foundation 3A — canonical 2026 season bullpen aggregation + independent MLB validation

- **Date:** 2026-07-27
- **Status:** Implemented (repository work only). No production aggregation, no production
  MLB validation, no production write, no public exposure, no Foundation 3B.
- **Scope:** The single canonical backend authority for team-level season bullpen
  performance, plus an independent official-MLB validator. Read-only. Public exposure remains
  blocked until the validation matches every mandatory team and league total in production.

## Decision statement

Canonical season bullpen performance is calculated from completed regular-season relief
appearances using historical appearance-team authority (`GameLog.appearance_team_id`),
authoritative starter identity (`GameLog.games_started`), and integer outs. Public use
remains blocked until an independent official-MLB validation matches every mandatory team and
league total.

## 1. Foundation 2 production-complete evidence

The merged production residual audit returned `result=pass`, `exit_code=0`,
`residual_population.total_rows=0`, `distinct_games=0`, `exact_backfill_eligible_rows=0`,
`unclassified_rows=0`, `category_totals_reconcile=true`, `coverage.season_null_legacy=0`,
`coverage.invalid_stored_states=0`, `foundation_2_status=production_complete`,
`foundation_3_gate=ready_for_review`, `database_writes_performed=false`. The repair sequence
proved all 47 missing opening-week games have canonical schedule authority, all 418 affected
appearances resolved, and no 2026 legacy-NULL / unresolved / conflict rows remain. These are
acceptance evidence only; none is hardcoded into application logic.

## 2. User problem and branch test

For a fan, writer, or analyst who needs a trustworthy answer to "how has this bullpen
actually performed this season?" — this branch creates the verified canonical source that can
eventually show a team's bullpen performance without current-team leakage, missing games,
starter contamination, or unexplained arithmetic.

## 3. Canonical historical team authority

`GameLog.appearance_team_id` (Foundation 1), used ONLY for rows with
`appearance_team_status == 'resolved'`. `Pitcher.team_id`, current roster, current
organization, current role, and current bullpen assignment are never consulted. A traded
pitcher's appearances aggregate to the historical team of each appearance (test-proven).

## 4. Relief classification authority

`GameLog.games_started` (official per-game `gamesStarted`): `0` = relief (included), `1` =
starter (excluded), `NULL` = start unknown. There is no appearance-order / innings fallback.
An opener credited with the start (`games_started == 1`) is a starter; a bulk follower or a
position player pitching (`games_started == 0`) is a relief appearance.

## 5. Exact inclusion contract

An appearance contributes only when: `game_date` present and `<= as_of_date` and in the
requested season; `mlb_game_pk` present; the game is a canonical final regular-season ('R')
game (all its `ScheduledGame` rows `status_state == final`, `game_type == 'R'`);
`appearance_team_status == 'resolved'` with a present `appearance_team_id` that is one of the
two teams that played the game; `innings_pitched_outs` a valid non-negative integer;
`games_started == 0`; and the row is not a duplicate `(pitcher_id, game_pk)`.

## 6. Exact exclusion and refusal contract

Rows never contribute (each with a deterministic reason code) when: `game_pk_missing`;
`schedule_authority_missing` (no final-R schedule authority / non-final / postponed /
suspended-without-final); `legacy_null_appearance`; `appearance_team_not_resolved`;
`contradictory_game_authority`; `appearance_team_missing`; `appearance_team_not_in_game`;
`innings_outs_invalid`; `starter_identity_unknown`; `starter_excluded`; `duplicate_appearance`.
Nothing is zero-filled. Blocking rows drive FAIL (legacy/unresolved/conflict/not-in-game/
invalid-outs/duplicate) or INCONCLUSIVE (starter identity unknown).

## 7. Metric-support matrix

| Metric | Support |
|---|---|
| final_regular_season_games, team_games_with_relief_usage, relief_appearances, unique_relievers | supported |
| bullpen_outs, bullpen_innings_display, runs_allowed, earned_runs, hits_allowed, walks, strikeouts, home_runs_allowed, bullpen_era | supported_with_validation |
| batters_faced | supported_with_validation (optional; NULL-aware → per-team unsupported if any included row lacks it) |
| saves, blown_saves, holds | supported (optional; official `saves`/`blownSaves`/`holds` flag projections) |
| hit_batters | blocked_by_missing_source (no GameLog field) |
| inherited_runners, inherited_runners_scored | unsupported (`inherited_runner_evidence_not_available` — official-when-present but frequently NULL; complete semantics unproven) |

Nothing was invented to fill the matrix; unknown stays unknown.

## 8. Canonical source per metric

Historical team → `GameLog.appearance_team_id`. Relief/starter → `GameLog.games_started`.
Pitching outs → `GameLog.innings_pitched_outs`. Counting stats → official `GameLog`
`earned_runs`/`runs_allowed`/`hits_allowed`/`walks`/`strikeouts`/`home_runs_allowed`. Finality
→ `game_finality.classify_status` + `ScheduledGame.STATE_FINAL`. Game type/date → canonical
`ScheduledGame` + `GameLog` authority.

## 9. Team-game bullpen-outs cross-check ownership

`GameLog` appearance-team relief rows are the SOLE authoritative aggregation source.
`team_game_pitching_splits.bullpen_outs_recorded` is grouped by CURRENT `Pitcher.team_id`
(a documented Foundation-0 limitation this aggregation supersedes — self-noted in
`season_era.py` and the splits service), so it is a per-team DIAGNOSTIC cross-check, NOT a
fail-closed global invariant: a divergence caps a team's trust at `partial`
(`split_outs_reconciliation_divergence`) and is reported, but never globally FAILs the run.
The reconciliation that gates PASS is the internal GameLog self-consistency (team totals sum
to league totals; game-grain relief outs equal team-grain league outs; row accounting
reconciles).

## 10. Integer-outs requirement

All innings arithmetic uses integer outs. Decimal baseball innings (1.1, 1.2) are never
summed. `bullpen_innings_display` is `outs//3 . outs%3`.

## 11. ERA formula and rounding

`bullpen_era = earned_runs * 27 / bullpen_outs`, computed from the exact integer numerator
(`earned_runs * 27`) and denominator (`bullpen_outs`) via `Decimal`, displayed at two decimals
(ROUND_HALF_UP). Component totals are never rounded before division. When `bullpen_outs == 0`,
ERA is `null` with `era_denominator_zero` — never `0.00`.

## 12–13. Team result contract + league reconciliation

Each team returns `team` (mlb_id/name/abbreviation), `scope`, `coverage`, `workload`,
`performance` (+ exact ERA components), `optional_metrics` (support_status/value/reason_code),
`trust` (complete/partial/unavailable + reason codes + contract versions), and
`reconciliation` (game_log_bullpen_outs / team_game_split_bullpen_outs / outs_match). The
report includes league reconciliation: `expected_team_count` (from canonical schedule
authority, not assumed 30), teams returned/complete/partial/unavailable, league totals,
`team_totals_reconcile`, `bullpen_outs_reconcile`, `duplicate_appearance_count`,
`excluded_row_count`. Missing teams are never zero-filled.

## 14. Independent official validation path

Official schedule (season start → as_of, month-chunked, cached) → final regular-season games
only → each game's box score fetched once → official starter per side identified
(`gamesStarted == 1`, else ordered `pitchers[0]`) and EXCLUDED → all other pitchers summed as
relief per official side team id. This never reads the local GameLog aggregation and never
uses current team membership. Uses the existing `mlb_client` retry/timeout patterns; raw MLB
payloads are never logged.

## 15. Exact mismatch policy

Mandatory counting metrics (`relief_appearances`, `bullpen_outs`, `runs_allowed`,
`earned_runs`, `hits_allowed`, `walks`, `strikeouts`, `home_runs_allowed`) compare EXACTLY.
ERA is validated through its components, never a rounded value. Any mandatory mismatch → FAIL;
missing/unfetchable official evidence → INCONCLUSIVE (never PASS, never a false mismatch);
unsupported optional metrics stay explicitly unsupported. No numeric tolerance hides integer
mismatches.

## 16–19. Boundaries

No migration (Alembic head stays `a4f1c7e9b3d2`), no persistence/materialization table, no
rankings/leaderboards/percentiles, no public API or frontend change, no Team State or Share
Card change (`season_era.py`, `public_team_relief_work.py`, `bullpen_context.py`,
`team_state*`, `share_artifact*`, `backend/api/`, `frontend/` untouched).

## 20. Inherited-runner decision

`inherited_runners` / `inherited_runners_scored` are reported `unsupported` with
`inherited_runner_evidence_not_available`. The fields exist and are official when present, but
the gameLog feed frequently omits them (NULL ≠ zero) so complete per-appearance semantics are
unproven; no acquisition system is built. Unknown stays unknown.

## 21. Production validation instructions

After a later PR merge, the founder runs the CLI / workflow first in `local_only` mode, then
`official_validation`, against production and reviews the full JSON. No production write, no
backfill, no schedule repair.

## 22–23. Public-reader gate / Share Card performance gate

Local PASS → `foundation_3_status=aggregation_ready_for_validation`,
`public_reader_gate=blocked`. Official-validation PASS →
`validated_ready_for_reader_review`, `public_reader_gate=ready_for_review`. The Share Card
performance gate remains `blocked` in both cases — it requires a later reviewed contract for
what metric appears, how it is explained, evidence receipts, freshness, immutable-artifact
semantics, and historical/current comparison behavior. A matching aggregation does NOT unblock
Share Card performance context.

## 24. Correction propagation

The aggregator is a pure deterministic read model: same database state + same inputs → same
semantic result (`generated_at` is excluded from semantics). A corrected `GameLog` naturally
changes the next aggregation; no stale derived total is persisted.

## 25. Foundation 3 next-step boundary

Foundation 3B (synchronized public reader, governed comparison context, Team State / Share
Card integration) remains unstarted and blocked until the production local-only aggregation
and official validation both pass and are reviewed. SC-05 remains out of scope.
