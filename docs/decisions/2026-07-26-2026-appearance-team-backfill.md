# Decision: Governed 2026 historical team-at-appearance backfill (Bullpen Performance Context — Foundation 2 of 6)

- **Date:** 2026-07-26
- **Status:** Implemented (Foundation 2 only). Steps 3–6 remain unstarted. No production
  backfill has been executed; the mechanism is built, tested, and gated.
- **Scope:** Durably attribute the MLB team a pitcher REPRESENTED to the legacy 2026
  `GameLog` rows Foundation 1 intentionally left NULL, from official game-side
  evidence only. No schema change, no performance metric, no ranking, no Team State
  payload/card change, no reader migration, no SC-05.

## Decision statement

The 2026 legacy `GameLog` rows (`appearance_team_status IS NULL`) are attributed to
their represented team through the SAME Foundation 1 resolver and box-score parser —
never a second implementation and never the pitcher's mutable current team. The
backfill is dry-run by default, resumable, idempotent, per-game atomic, and audited
before and after every batch. Missing or conflicting authority fails closed exactly
as it does at live ingestion.

## 1. Prerequisite baseline

Foundation 1 (`feat/team-at-appearance-authority`, PR #534) is merged to `main`; the
follow-up read-only production audit (PR #535) is merged on top. The single Alembic
head is `a4f1c7e9b3d2`, the `appearance_team_*` columns and their stored-state CHECK
invariant exist, and `services/appearance_team_authority.py` +
`services/appearance_team_coverage.py` are in place. This foundation adds NO
migration — the head stays `a4f1c7e9b3d2`, and no historical `UPDATE` runs inside
Alembic. Attribution is data, applied by a governed job, not by a migration.

## 2. Target population

A row is a backfill target iff ALL hold:

- `appearance_team_status IS NULL` — legacy only. An explicit `unresolved`/`conflict`
  is never selected and never overwritten (the legacy pass does not regress a decision
  the live path already made).
- `game_date ∈ [start_date, end_date]` — the OFFICIAL game date, never the wall clock.
- The game is FINAL in the local `ScheduledGame` ledger (a `status_state = 'final'`
  row and no `postponed`/`suspended` row for the same `game_pk`). A not-yet-final game
  is simply never targeted; its rows stay NULL until it finalizes. This keeps the
  keyset cursor monotonic and the historical sweep resumable, and it prevents
  attributing a game whose participation is not yet official.

Work is grouped by DISTINCT `mlb_game_pk`. Foundation 1 established the appearance
grain as `(pitcher_id, mlb_game_pk)` and that a box score lists a pitcher on exactly
one side; suspended/resumed games use distinct `game_pk`s, so one `game_pk` maps to a
single official team-side per pitcher.

## 3. Two-tier, local-evidence-first resolution

Per distinct final `game_pk`, `services/appearance_team_backfill_2026.py` resolves
every target appearance, most-local first, always through the Foundation 1 contract:

1. **Tier 1 — local (no network).** The appearance's opponent team id is derived from
   local official evidence in `CompletedGameContext` — either the row whose
   `starter_player_id` is this pitcher (unambiguous per-pitcher identity) or the row
   whose `opponent_name` exactly matches the appearance's stored opponent — and passed
   to Foundation 1's `resolve_for_write(game_pk=…, opponent_team_id=…)`, which resolves
   the schedule-facing side and FAILS CLOSED on any ambiguity. A derived opponent id
   is only a proposal that the schedule authority re-resolves, so an ambiguous local
   signal can never produce a wrong attribution — it falls through to Tier 2.
2. **Tier 2 — one box-score call.** Only for appearances Tier 1 could not resolve, a
   single `mlb_client.get_game_boxscore(game_pk)` is fetched, parsed by the Foundation
   1 parser `sync._extract_pitching_lines_from_boxscore`, and each appearance resolved
   by the Foundation 1 seam `sync._appearance_team_for_boxscore_line` (box-score side
   authoritative, cross-checked against the schedule → `conflict` on disagreement). An
   appearance with no matching pitching line is `unresolved`. A `--no-api` mode leaves
   the remainder `unresolved` without any network call.

No second resolver or parser is defined. `Pitcher.team_id` is never read; the only
per-pitcher column consulted is the immutable `Pitcher.mlb_id`, used solely to match a
box-score line to its appearance.

## 4. Determinism: keyset cursor + batch fingerprint

Selection is ordered `(game_date ASC, game_pk ASC)` and paginated by a KEYSET cursor
(`after_game_date`/`after_game_pk`), never OFFSET, so a large sweep resumes across
runs without re-doing or skipping work; the run echoes `next_cursor` and `exhausted`.
Each batch carries a SHA-256 `batch_fingerprint` over the ordered work set (backfill +
resolver contract versions, window, cursor, and each game's `game_pk`/`game_date`/
sorted `game_log_id`s). The fingerprint is stable across dry-run/apply on the same
state, changes when the work set or cursor changes, and is invalidated if either
contract version moves.

## 5. Governance: dry-run default, apply gates

Dry run is the default: zero writes, a deterministic JSON report, and the fingerprint.
Apply requires `apply=True` AND the exact confirmation phrase
`RUN_2026_APPEARANCE_TEAM_BACKFILL`; an optional `expected_fingerprint` must equal the
computed fingerprint. Both gates are checked BEFORE any mutation — a failed gate
returns a `refused` summary having written nothing. The CLI
(`scripts/run_2026_appearance_team_backfill.py`) and the `workflow_dispatch`-only
workflow (`appearance_team_backfill_2026.yml`, concurrency-grouped, private artifact,
no schedule/push trigger) both enforce the phrase.

## 6. Per-game atomicity & idempotency

Each game is resolved and (in apply) committed in its own transaction; a per-game
failure (e.g., a box-score fetch error) rolls back only that game and is reported
without aborting the batch. Because only NULL-status rows are targeted, a re-run after
a successful apply selects nothing — the backfill is idempotent, and applying twice
leaves attributions unchanged.

## 7. Coverage audit & invariant

Every run computes the read-only Foundation 1 coverage
(`build_appearance_team_coverage`) before and after, plus an invalid-stored-state
count that mirrors the DB CHECK invariant; the run reports `failed` if any invalid
state is observed (the CHECK makes that impossible to commit). Resolved rows carry a
team and official source/reason; `unresolved`/`conflict` rows carry no team — so the
production audit's provenance checks continue to pass and 2026 `null_legacy` trends to
zero as the campaign proceeds.

## 8. What this step does NOT do

No migration and no Alembic head change; no historical `UPDATE` in a migration; no new
checkpoint table (the keyset cursor needs none). No ERA/saves/holds/ranking, no Team
State payload or card change, no reader migrated off the current-team join (Steps 3–6
own that), no SC-05, and no production backfill executed during implementation.
