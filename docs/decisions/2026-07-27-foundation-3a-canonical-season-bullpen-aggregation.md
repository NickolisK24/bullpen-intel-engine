# Decision: Foundation 3A — canonical 2026 season bullpen aggregation + independent MLB validation

- **Date:** 2026-07-27
- **Status:** Implemented (repository work only), trust-contract corrected (§26). No production
  aggregation, no production MLB validation, no production write, no public exposure, no
  Foundation 3B.
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
`schedule_authority_missing` (NO ScheduledGame rows at all — Correction 1, blocking
INCONCLUSIVE, see §5a); `contradictory_game_authority` (the game's ScheduledGame sides disagree
on finality/type — FAIL); `game_not_final` (uniform non-final / postponed / suspended-without-
final / non-R — a legitimately excluded game, deliberately DISTINCT from missing authority and
non-blocking); `legacy_null_appearance`; `appearance_team_not_resolved`; `appearance_team_missing`;
`appearance_team_not_in_game`; `innings_outs_invalid`; `starter_identity_unknown`;
`starter_excluded`; `duplicate_appearance`. Nothing is zero-filled. Blocking rows drive FAIL
(legacy/unresolved/conflict/not-in-game/invalid-outs/duplicate/contradictory-schedule) or
INCONCLUSIVE (missing schedule authority; unknown starter identity).

## 5a. Missing in-scope schedule authority is a blocking evidence gap (Correction 1)

An "otherwise in-scope" appearance (requested season; `game_date` present and `<= as_of_date`;
`game_pk` present) whose game_pk has NO canonical `ScheduledGame` authority does NOT silently
drop: silent omission would make the season totals incomplete. It is INCONCLUSIVE/2 with
`decision_reasons=['schedule_authority_missing']`, `foundation_3_status=aggregation_inconclusive`,
`public_reader_gate=blocked`, `share_card_performance_gate=blocked`, and it is surfaced in
coverage as `schedule_authority_missing_rows` / `schedule_authority_missing_games` (multiple
rows of one game count one game). No local-only or official-validation PASS is possible while
`schedule_authority_missing_rows > 0`. Contradictory schedule authority remains FAIL; a
legitimately non-final/postponed game (`game_not_final`) is a non-blocking exclusion and can
never be confused with missing authority.

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

## 9. Canonical reconciliation & the non-governing current-team split (Correction 3)

`GameLog` appearance-team relief rows are the SOLE authoritative aggregation source. The
GOVERNING reconciliation is appearance-team-correct: relief outs summed at the GAME grain must
equal relief outs summed at the TEAM grain (`canonical_game_grain_bullpen_outs` ==
`canonical_team_grain_bullpen_outs`, exposed with `canonical_outs_match`); a mismatch — e.g. an
appearance attributed to a team that did not play the game (`appearance_team_not_in_game`) — is
a FAIL.

`team_game_pitching_splits.bullpen_outs_recorded` is grouped by CURRENT `Pitcher.team_id`
(documented Foundation-0 leakage — self-noted in `season_era.py` and the splits service), so it
is STRICTLY NON-GOVERNING: it can never mark a team `partial`/`unavailable`, never permit or
prevent a local or official PASS, and never change `foundation_3_status`, `public_reader_gate`,
or `share_card_performance_gate`. It is surfaced only as
`reconciliation.current_team_split_diagnostic` (`support_status: unsupported`,
`reason_code: current_team_leakage`, plus `observed_value`). A divergence or a missing split
cannot alter canonical trust — traded-pitcher historical aggregation stays correct even when the
current-team split disagrees.

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
`reconciliation` (canonical_game_grain_bullpen_outs / canonical_team_grain_bullpen_outs /
canonical_outs_match / current_team_split_diagnostic). The report includes league
reconciliation: `expected_team_count` (from canonical schedule authority, not assumed 30),
teams returned/complete/partial/unavailable, league totals, `team_totals_reconcile`,
`bullpen_outs_reconcile`, `duplicate_appearance_count`, `excluded_row_count`. Missing teams are
never zero-filled.

## 14. Independent official validation path & official starter identity (Correction 2)

Official schedule (season start → as_of, month-chunked, cached) → final regular-season games
only → each game's box score fetched once → the official starter per side identified STRICTLY
by exactly one `gamesStarted == 1` line and EXCLUDED → all other pitchers summed as relief per
official side team id. Pitcher-array position is NEVER used: there is no `pitchers[0]` /
appearance-order / innings / role / current-team fallback. Home and away starter evidence is
evaluated INDEPENDENTLY, and a side's relief totals are accepted only after its unique starter
is proven. A team-game with ZERO `gamesStarted == 1` lines yields INCONCLUSIVE
(`official_starter_identity_missing`); MORE THAN ONE yields FAIL
(`official_starter_identity_contradictory`); both are surfaced as
`official_games_missing_unique_starter` / `official_games_with_multiple_starters`. This never
reads the local GameLog aggregation and never uses current team membership; raw MLB payloads
are never logged.

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

## 26. Result precedence (corrected trust contract)

**Local precedence:** (1) critical FAIL — migration-head mismatch, invalid stored state,
contradictory game authority, duplicate canonical appearance, historical-team leakage
(`appearance_team_not_in_game`), canonical game-grain-vs-team-grain reconciliation failure, or
a database-write attempt; (2) INCONCLUSIVE — missing schedule authority for in-scope rows,
unknown starter identity, incomplete mandatory local evidence, or an unestablished team
population; (3) PASS — all mandatory local evidence complete, all canonical reconciliations
pass, no missing schedule authority, no invalid/unresolved/conflict/legacy row in scope,
read-only invariant holds.

**Official-validation precedence** (only on a local PASS): local FAIL stays FAIL; local
INCONCLUSIVE stays INCONCLUSIVE; then (1) contradictory official evidence (multiple
`gamesStarted == 1`) → FAIL; (2) missing official evidence — a fetch failure or a game lacking
a unique official starter → INCONCLUSIVE (a later mismatch can never replace this evidence
failure with a misleading verdict); (3) a mandatory metric mismatch on complete-evidence teams
→ FAIL; (4) uncovered expected teams → INCONCLUSIVE; else PASS. The Share Card performance gate
stays `blocked` in every mode.

Required decision statements:

- An in-scope appearance without canonical schedule authority prevents the season aggregation
  from passing, because silent omission would make the resulting totals incomplete.
- Official starter identity requires exactly one official `gamesStarted` marker; pitcher-array
  ordering is not historical evidence.
- Current-team-derived pitching splits are non-governing diagnostics and cannot approve, reject,
  or downgrade appearance-team-correct season totals.
