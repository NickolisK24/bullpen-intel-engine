# Decision: Canonical team-at-appearance authority (Bullpen Performance Context — Foundation 1 of 6)

- **Date:** 2026-07-26
- **Status:** Implemented (Foundation 1 only). Steps 2–6 remain unstarted.
- **Scope:** Persist, at ingestion, the MLB team a pitcher REPRESENTED in each game.
  No performance metrics, no rankings, no Team State payload/card change, no
  historical backfill, no SC-05.

## Decision statement

Every BaseballOS pitching appearance must retain the MLB team represented in that
game. Historical team attribution is derived from official game-side evidence and
never from the pitcher's mutable current team assignment. Missing or conflicting
appearance-team authority fails closed.

## 1. Why current `Pitcher.team_id` is invalid for historical attribution

`GameLog` (grain `(pitcher_id, mlb_game_pk)`) stores every per-appearance pitching
stat but **no team column**. Every team-level rollup therefore attributes an
appearance through the pitcher's CURRENT `Pitcher.team_id`. When a pitcher is traded,
optioned, released, or reassigned, `Pitcher.team_id` changes and the historical
appearance is silently re-attributed to the new team — or dropped from the former
team. The production season bullpen-ERA reader
(`services/season_era.py::build_season_era_payload`) buckets a pitcher's whole
regular season under the current team and even self-documents the defect
(`season_era.py`: *"Game logs do not store team-at-appearance, so bullpen ERA is
grouped by current pitcher team assignment."*). The same current-team join underlies
`team_game_pitching_splits`, `public_team_relief_work`, `bullpen_context`,
`game_context`, `narrative_memory`, and `slate_editorial_ranker`.

**Reproduced defect:** a reliever who pitched for Team A (3 ER) and later joined Team
B (so `Pitcher.team_id = B`) is aggregated into Team B's bullpen ERA; Team A's line
loses those innings entirely.

## 2. Canonical team-at-appearance definition

The canonical appearance identity is `(pitcher_id, mlb_game_pk)` — the existing
`GameLog` unique key. In MLB a pitcher pitches for exactly one team per game, so one
`GameLog` row represents exactly one pitcher/game/team-side appearance. The
represented team is a durable FACT of that row.

## 3. Model & migration decision

No durable, official-evidence-based, per-`(pitcher, game)` team authority existed:
`TeamGamePitchingSplit` is per-`(team, game)` and reconstructs pitcher membership
through `Pitcher.team_id`; `CompletedGameContext` records only the starter;
`GamePlayByPlayEvent.fielding_team_id` is event-grain and PBP-gated. `GameLog` is the
natural home. Foundation 1 therefore ADDS four nullable columns to `game_logs`
(migration `a4f1c7e9b3d2`, single head, additive, reversible, no backfill):

- `appearance_team_id` — the represented MLB team (plain integer, no FK, matching the
  project-wide no-teams-table convention used by `ScheduledGame`).
- `appearance_team_source` — the official source that resolved it.
- `appearance_team_status` — `resolved` / `unresolved` / `conflict` (CHECK-constrained;
  NULL = legacy unbackfilled).
- `appearance_team_reason` — a governed reason code.

Indexes `(appearance_team_id, game_date)` and `(mlb_game_pk, appearance_team_id)`
support the future team-season aggregation. Existing rows and constraints are
unchanged.

## 4. Source precedence

`services/appearance_team_authority.py::resolve_for_write` formalizes one precedence
contract (most authoritative first):

1. **Official box-score pitching side** (`boxscore_side`) — the postgame refresh
   already resolves and conflict-checks each line's side; it is now persisted.
2. **Official schedule ledger** (`schedule_opponent`) — the `ScheduledGame` side that
   FACES the appearance's official opponent, used by the daily-sync game-log lane
   whose per-pitcher payload carries only the opponent, not the pitcher's own side.

The pitcher's current team is **forbidden** as an attribution source (used only as an
out-of-band diagnostic in the coverage audit). Two authoritative sources that
disagree fail closed as `conflict`; missing authority fails closed as `unresolved`.
Neither is ever encoded as a fake team id.

## 5. Future-write paths updated

- Daily-sync game-log ingestion (`sync._ingest_game_log_split`) — resolves via the
  schedule ledger.
- Postgame refresh (`sync._ingest_boxscore_pitching_line`) — resolves via the
  box-score side, cross-checked against the schedule.
- The shared upsert (`sync._upsert_game_log_from_authoritative_values`) — writes the
  authority on INSERT and reconciles it on correction.
- The pitcher game-log backfill delegates to the daily path (covered automatically).
- Seed/fixture factory (`seed.py`) — resolves via the schedule ledger.

Ordering: official game/box-score authority → pitcher resolved → represented team
resolved → row written → team-split/ledger recompute → per-game commit (unchanged).

## 6. Correction behavior

Team-at-appearance is reconciled OUTSIDE the generic stat-correction loop
(`reconcile_on_update`): a stat-only correction never erases attribution; an unchanged
re-sweep never backfills a legacy row (Step 2 owns that); the same represented team is
idempotent regardless of source; a different team from a HIGHER-precedence official
source is a governed correction (`appearance_team_corrected`); from a LOWER-precedence
source it is ignored (no flap); at EQUAL precedence it fails closed as `conflict`.
Ordinary roster synchronization touches none of these columns.

## 7. Starter / reliever separation

Attribution is written for ALL pitching appearances — starters, relievers, openers,
bulk/followers — from official game participation, independent of role, roster
position, fatigue, or current bullpen membership. Role classification stays separate;
future bullpen metrics filter relief appearances AFTER attribution.

## 8. Idempotency, concurrency, immutability

Equivalent reprocessing yields the same authority; a `Pitcher.team_id` change never
rewrites history; the `(pitcher_id, mlb_game_pk)` uniqueness prevents duplicate
appearances; authoritative team corrections remain possible through the governed path
but not through roster sync.

## 9. Observability

`services/appearance_team_coverage.py::build_appearance_team_coverage` is a read-only
audit: total / resolved / unresolved / conflict / NULL-legacy counts, by season and by
source, plus a current-team-mismatch diagnostic (resolved appearances whose
represented team differs from the pitcher's current team). Reason codes:
`appearance_team_resolved_boxscore`, `appearance_team_resolved_schedule`,
`appearance_team_unresolved`, `appearance_team_source_conflict`,
`appearance_team_corrected`. No public exposure; no external payloads or secrets
logged; performs no backfill.

## 10. Read contract

`resolve_appearance_team(game_log)` is the single canonical accessor future work must
consume. A legacy NULL row reads as `unresolved` (team_id None) and is excluded from
team-season aggregation until Step 2 backfills it. No reader is migrated in this step;
the current-team readers (season_era, team_game_pitching_splits, public_team_relief_work,
bullpen_context, game_context, narrative_memory, slate_editorial_ranker) are documented
for Steps 2–3.

## 11. Historical rows intentionally left unbackfilled

The migration modifies no existing row; legacy appearances keep `appearance_team_id =
NULL` (read as unresolved). Step 2 performs the 2026 backfill.

## 12. Step-2 backfill prerequisites

Step 2 backfills historical rows using the SAME source precedence: the official
box-score side per `(pitcher, game_pk)` (primary), falling back to the schedule
ledger's opponent-facing side. Rows with no official side resolve `unresolved`; two
disagreeing official sources resolve `conflict`. It must never use `Pitcher.team_id`.
Unresolved/conflict rows stay excluded from aggregation and are surfaced by the
coverage audit.

## 13. Future season bullpen aggregation dependency

Step 3's canonical season bullpen aggregation replaces the current-team join with the
`resolve_appearance_team` accessor + the `appearance_team_id` indexes, aggregating only
`resolved` relief appearances by represented team.

## 14. Existing Team State artifacts remain unchanged

Team State v1.2, its card, its payload, all prior immutable artifacts, and the public
APIs are unchanged. This work adds a durable ingestion fact only.

## 15. SC-05 remains blocked.

## References

- `models/game_log.py` (columns + status vocabulary)
- `migrations/versions/a4f1c7e9b3d2_add_game_log_appearance_team.py`
- `services/appearance_team_authority.py` (resolver + precedence + read accessor)
- `services/appearance_team_coverage.py` (read-only coverage audit)
- `services/sync.py` (daily-sync + postgame write wiring), `seed.py`
- `tests/test_appearance_team_authority.py`
