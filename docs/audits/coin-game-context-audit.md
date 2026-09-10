# COIN Game Context Audit

**Status:** Audit only. No feature code in this commit.
**Scope:** Determine the safest way to add Completed Game Context (Game Context Intelligence) to BaseballOS so the 6am ET sync can generate game-aware bullpen stories.
**Date:** 2026-06-26

---

## Summary

BaseballOS today understands the bullpen almost entirely through *pitcher workload*: innings, pitches, recent appearances, rest, fatigue, and availability. It does **not** understand *game context* — what the score was when the starter left, what the bullpen inherited, whether a lead was protected or lost, the largest lead/deficit, late runs allowed, comeback, or "Game Shape" outcome.

The data plumbing to add this is mostly in place. The system already runs a postgame refresh that fetches completed games and ingests per-pitcher boxscore lines. The gap is that ingestion is **pitcher-centric** and **boxscore-only**: there is no team/game-level outcome record, and the running score state (needed to know the score *at the moment* the starter exited / the bullpen entered) is not fetched.

**Recommendation:** Add a thin, derived **Completed Game Context** layer. During the postgame refresh, temporarily fetch play-by-play (or linescore as a fallback), extract structured context, store **only the derived fields** in one new table keyed by `(team_id, game_pk)`, and never persist raw play-by-play. Feed that table into story generation as a new, optional context source. Implementation is **safe to begin** after this audit, in the phases below.

---

## Current Sync Flow

Data moves through the system in two scheduled jobs, both driven by GitHub Actions (`.github/workflows/baseballos-sync.yml`).

**Schedule (cron, UTC):**
- `0 10 * * *` → **daily sync** (~6am ET) — the authoritative morning refresh.
- `*/30 22-23 * * *`, `*/30 0-6 * * *`, `30 7 * * *` → **postgame refresh** — lightweight evening/overnight catch-up after games go final.

**Daily sync** — `backend/scripts/run_daily_sync.py` → `services/sync.py::run_daily_sync(app, days_back=7, ...)`. Staged pipeline tracked in `sync_runs.stage`:
1. Team assignments (`sync_team_assignments`)
2. Roster status (`sync_roster_statuses`)
3. Log ingestion (`sync_recent_logs` — pulls each tracked pitcher's `gameLog` for the last N days)
4. Fatigue recalculation (`recalculate_all_fatigue`)
5. Availability backtest refresh
6. Dashboard snapshot build + publish
7. Published / Failed

**Postgame refresh** — `backend/scripts/run_postgame_refresh.py` → `services/sync.py::run_postgame_refresh(...)`:
- Resolves a single schedule date (`postgame_schedule_date()` rolls back to the prior baseball day before 6am ET so early-morning runs don't scan an empty slate).
- Calls `get_schedule()` for that date, filters to **completed** games (`is_completed_game()`), skips games already in `postgame_processed_games`.
- For each new completed game: `get_game_boxscore(game_pk)` → extract pitching lines → match MLB IDs to local `pitchers` → insert `GameLog` rows (deduped by `(pitcher_id, mlb_game_pk)`), backfilling `leverage_index`.
- Writes a `PostgameProcessedGame` marker, then recalculates fatigue only if logs were added. No roster/team-assignment/backtest work.

### MLB data actually fetched (`services/mlb_api.py`)

Base URL: `https://statsapi.mlb.com/api/v1`.

| Method | Endpoint | Used by | Game-level data |
|---|---|---|---|
| `get_pitcher_game_logs(player_id)` | `/people/{id}/stats?stats=gameLog&group=pitching` | daily sync | per-pitcher line only |
| `get_schedule(...)` | `/schedule?sportId=1&hydrate=team` | postgame refresh | game status **and final team scores** (`teams.home/away.score`, `isWinner`) |
| `get_game_boxscore(game_pk)` | `/game/{game_pk}/boxscore` | postgame refresh + backfill | aggregate per-pitcher pitching lines + `leverageIndex` |
| `get_game_pitching_lines(game_pk)` | (wraps boxscore) | postgame refresh | per-pitcher outs/stats/team |

**Not implemented today:**
- **Linescore** — `/game/{game_pk}/linescore` (per-inning runs). No method exists.
- **Play-by-play / live feed** — `/game/{game_pk}/playByPlay` or `/game/{game_pk}/feed/live` (running score per event, inning, half-inning). No method exists.

So ingestion is **boxscore-only**. Final scores are technically reachable from the schedule response already, but the *running score state* (score when the starter exited, score when the bullpen entered, largest lead, turning inning) requires play-by-play or, partially, linescore — neither of which is fetched.

---

## Current Story Inputs

Story generation is a deterministic, multi-stage pipeline (no external LLM). It runs **on demand via the API**, not as part of the 6am sync:

```
bullpen_context.build_team_bullpen_context(team_id, reference_date)
  → story_observation_engine   (selects observation types by threshold/severity)
  → story_construction_engine   (builds fact frames)
  → story_reasoning_engine_v1   (internal editorial intent)
  → story_writer_v1             (deterministic prose)
  → story_four_beat_interpreter_v1 (maps to public beat)
  → story_intelligence_service_v1.build_team_story(...)  ← orchestrator
  → story_feed / story_blueprint_v1 (public 5-section structure)
```

API entry: `GET /teams/<team_id>/story` → `api/bullpen.py::get_team_story` → `build_team_story(team_id, as_of_date, ...)`.

### What story generation currently knows

Only **workload / availability / structural** signals, all sourced from `bullpen_context` sub-layers:
- Rotation context — starter innings trend, early-bullpen-entry rate, coverage IP absorbed.
- Concentration context — workload share on the top-3 arms, concentration band.
- Optionality context — rested/available arm counts, clean-workload options, close-game paths.
- Role stability context — current vs. previous late-game core, stability band.
- Injury context — inactive/IL bullpen arms, depth-pressure band.

### What story generation does **not** know

- The **score** at any point in a game (final, or at starter exit / bullpen entry).
- Whether the bullpen **inherited a lead or a deficit**.
- Whether the bullpen **protected or lost** a lead; comeback completed.
- **Largest lead / largest deficit**, **late runs allowed** (innings 7–9), **turning inning**.
- Any **Game Shape outcome** (the existing `game_shape.py` classifies *structure* — opener/bulk/bullpen/short-start — but not *result*).

Three existing services touch "game" concepts but **none capture score/result context**:
- `services/game_context.py` — descriptive schedule anchor only (last game date, opponent) from stored `GameLog`; explicitly reports `home_away` and `scheduled_time` as unavailable.
- `services/game_shape.py` — deterministic structural classifier (`normal_start` / `short_start` / `opener_bulk_game` / `bullpen_game` / `unknown`); infrastructure only, no score, not yet wired into metrics or stories.
- `services/consequence_intelligence.py` — day-over-day availability *trends* ("more flexibility than yesterday"); no within-game scoring.

---

## Current Data Gaps

To support BaseballOS-style game stories, the following are missing end-to-end (no fetch, no storage, no story input):

1. **Running score state** — score when the starter exited; score when the bullpen entered. Requires play-by-play (or linescore approximation).
2. **Inherited situation** — lead vs. deficit handed to the bullpen.
3. **Lead trajectory** — largest lead, largest deficit during the game.
4. **Bullpen result** — lead protected, lead lost, comeback completed, turning inning.
5. **Late-game damage** — runs allowed in innings 7–9 / "late runs allowed".
6. **Game-level outcome record** — there is no team/game row. `postgame_processed_games` stores only `mlb_game_pk`, date, type, `home_team_id`, `away_team_id`, `final_state` (a status string, **not a score**), and processing counters.
7. **Opponent/home-away at game grain** — opponent exists per `GameLog` row; clean home/away and opponent at the team-game grain is not stored.
8. **Schedule for the next game** — not stored; the system cannot safely say "tonight vs X" (see Story Language Rules).

### Relevant existing models (for reference)

- `game_logs` — per-pitcher per-game line. Natural key `(pitcher_id, mlb_game_pk)`. Has `game_date`, `game_type`, `opponent`, `games_started`, innings/outs, `pitches_thrown`, W/L/S/hold/blown_save, `leverage_index`, `inherited_runners(_scored)`. **No team_id column** (team is via `pitcher.team_id`); **no score**.
- `pitchers` — identity + `team_id` (plain integer, not an FK).
- `postgame_processed_games` — game processing marker (see gap #6).
- `sync_runs`, `sync_failures` — pipeline audit + dead-letter.
- `fatigue_scores`, `dashboard_snapshots` — derived outputs.
- **No `teams` table** — team ids are plain integers validated via `services/team_directory.py::valid_team_ids()` against active pitchers. **No `games` table** — games exist only implicitly through `game_logs` / `postgame_processed_games`.

---

## Recommended Architecture

Add a **lightweight, derived Completed Game Context layer** that sits beside the existing postgame refresh and feeds story generation. Keep it additive and fail-closed: if context can't be derived for a game, store nothing for that game and let stories fall back to today's workload-only behavior.

**Preferred direction (as specified, and consistent with the codebase's "infrastructure-only, derived" patterns like `game_shape.py`):**

1. **Do not store raw play-by-play permanently.** It is large, changes the storage profile, and is not needed once context is extracted.
2. **Consume play-by-play (or linescore) temporarily during sync.** Add a fetch method to `services/mlb_api.py` (e.g. `get_game_play_by_play(game_pk)` → `/game/{game_pk}/playByPlay`, and/or `get_game_linescore(game_pk)` → `/game/{game_pk}/linescore`). Hold the response in memory only.
3. **Extract structured completed-game context** in a new pure module, e.g. `services/completed_game_context.py`, mirroring `game_shape.py`'s style: deterministic, input = (this team's `GameLog` lines for the game) + (temporary play-by-play/linescore) + (schedule scores), output = a structured dict with a `confidence` and explicit limitations. Reuse `game_shape.classify_game_shape()` for the structural read.
4. **Store only the derived context** in one new table, keyed by `(team_id, game_pk)`. This is the single source of truth the story layer reads.

**Where to integrate:** Extend `run_postgame_refresh` (and the daily sync's log-ingestion stage as a backfill path) to, after `GameLog` rows for a completed game are written, derive and upsert one Completed Game Context row per team in that game. This keeps it on the same boxscore-driven path that already knows which games are newly final, and reuses the `postgame_processed_games` idempotency guard.

**Why a separate table rather than extending `postgame_processed_games`:** that table is a *processing marker* (one row per game, no team grain, no scores). Completed Game Context is *per team per game* and is read by the story layer. Keeping them separate preserves the marker's single responsibility and lets context be recomputed without touching the idempotency ledger.

### Should a new table/model be added?

**Yes — one new table.** A new `team_game_context` (model `CompletedGameContext`) keyed by `(team_id, game_pk)` with a unique constraint, plus an index on `(team_id, game_date)` for "most recent game" lookups. This is the smallest footprint that supports per-team story reads. No FK to a `teams` table is needed (none exists; follow the existing plain-`team_id` convention).

### Should play-by-play be stored?

**No.** Fetch it temporarily during sync, extract the structured fields, then discard. Store only the derived context. If play-by-play is unavailable for a game, degrade to linescore (per-inning runs + final score) for the coarser fields (final score, largest lead, late runs by inning) and mark the finer fields (exact starter-exit score, turning inning) as `null` with lowered `confidence`.

---

## Proposed Completed Game Context Fields

One row per `(team_id, game_pk)`. All score fields are from the perspective of `team_id` ("for" = this team, "against" = opponent).

| Field | Type | Notes |
|---|---|---|
| `team_id` | int | this team (plain integer, app convention) |
| `game_pk` | int | MLB game id; with `team_id` forms the natural key |
| `game_date` | date | |
| `opponent_team_id` | int, null | |
| `opponent_name` | str, null | |
| `home_away` | str, null | `'home'` / `'away'` |
| `final_score_for` | int, null | |
| `final_score_against` | int, null | |
| `starter_player_id` | int, null | from `games_started` / game_shape |
| `starter_name` | str, null | |
| `starter_ip` | float, null | |
| `starter_pitch_count` | int, null | may be null (see Risks) |
| `starter_exit_inning` | int, null | requires play-by-play |
| `starter_exit_score_for` | int, null | requires play-by-play |
| `starter_exit_score_against` | int, null | requires play-by-play |
| `bullpen_entry_inning` | int, null | |
| `bullpen_entry_score_for` | int, null | |
| `bullpen_entry_score_against` | int, null | |
| `lead_when_bullpen_entered` | int, null | derived; 0/absent if not leading |
| `deficit_when_bullpen_entered` | int, null | derived |
| `largest_lead` | int, null | |
| `largest_deficit` | int, null | |
| `late_runs_allowed` | int, null | bullpen runs allowed, innings 7+ |
| `runs_allowed_innings_7_to_9` | int, null | |
| `lead_protected` | bool, null | tri-state; null = undetermined |
| `lead_lost` | bool, null | |
| `comeback_completed` | bool, null | |
| `turning_inning` | int, null | requires play-by-play |
| `game_shape_created` | str, null | reuse `game_shape` vocabulary |
| `game_shape_protected` | bool, null | |
| `bullpen_story_tag` | str, null | derived tag for story selection |
| `confidence` | str/float | `'high'`/`'medium'`/`'low'` (or 0–1); driven by data completeness |
| `generated_at` | datetime | derivation timestamp |

Use **nullable + tri-state booleans** throughout so partial data (e.g. linescore-only games, missing pitch counts) degrades gracefully instead of asserting false facts. `confidence` must reflect which fields were actually derived vs. inferred vs. missing — the story layer should gate language on it.

---

## Story Language Rules

These rules protect against inventing future context. They mirror the system's existing relative-time discipline (stories already use `reference_date`-relative wording, and `what_changed_since_yesterday_*` compares snapshots, not calendar dates).

**Allowed (safe) phrasing:**
- "after their most recent game"
- "coming out of yesterday"
- "their next bullpen test"
- "the last time the bullpen was used"

**Forbidden unless verified schedule data exists for that specific game:**
- "tonight against X"
- "tomorrow"
- "next game against X"

**Rules:**
1. **Yesterday / completed game** — only describe a game that is *final* and has a stored Completed Game Context row. Use past tense.
2. **Today** — describe availability/workload as of `reference_date`. Do not assert a game is happening unless schedule data confirms it.
3. **Tonight / next game** — emit a concrete opponent or "tonight" **only if** verified schedule data for that game is present. Otherwise use the safe relative phrasings above. Default to safe wording when uncertain.
4. **Never** name an opponent for a future game from inference. No "tomorrow vs X" without schedule confirmation.
5. **Confidence gating** — if a Completed Game Context row has low `confidence` or null result fields, the story must not assert protected/lost/comeback outcomes; it should fall back to neutral workload language.

---

## Implementation Phases

1. **Audit only** *(this commit)* — document flow, gaps, and the safe plan. No feature code.
2. **Data model + extraction service** — add `CompletedGameContext` model + migration; add `services/completed_game_context.py` (pure, deterministic extraction with `confidence` + limitations); add `mlb_api` play-by-play/linescore fetch methods. No sync wiring yet; unit-test extraction against fixtures.
3. **Sync integration** — wire extraction into `run_postgame_refresh` (and a daily-sync backfill path) on the existing boxscore path; upsert per-team rows; reuse `postgame_processed_games` idempotency; record nothing on failure (fail-closed). Add a `sync_runs` stage if useful for observability.
4. **Story integration** — expose Completed Game Context as a new optional input to `story_observation_engine` / `bullpen_context`; add game-context observation/beat(s); enforce Story Language Rules; gate on `confidence`.
5. **Schedule support (later)** — only after 1–4 are stable, add verified next-game schedule storage so "tonight vs X" becomes allowed. Until then, safe relative language only.
6. **UI / story polish** — surface game-context beats in the bullpen board / story feed; copy and presentation refinement.

---

## Test Plan

Test categories to add (matching existing `backend/tests/` conventions — e.g. `test_game_shape.py`, `test_postgame_refresh.py`, `test_story_observation_engine.py`):

1. **Extraction unit tests** (`test_completed_game_context.py`) — feed fixture play-by-play / linescore / boxscore and assert each derived field: starter-exit score/inning, bullpen-entry state, lead/deficit, largest lead/deficit, late runs (7–9), lead_protected/lost, comeback, turning inning, `game_shape_created`, `confidence`.
2. **Degradation tests** — linescore-only input (no play-by-play) yields coarse fields + lowered confidence and `null` for fine fields; missing pitch counts → `starter_pitch_count = null`, not 0.
3. **Edge-case fixtures** — doubleheaders (two `game_pk` same date), suspended/resumed games, extra innings, opener/bulk games, bullpen games, walk-off endings, shutout/blowout, no-final / in-progress (must be skipped).
4. **Model/migration tests** — unique constraint on `(team_id, game_pk)`, index behavior, upsert/re-run idempotency.
5. **Sync integration tests** — extend `test_postgame_refresh.py`: newly-final games produce context rows; already-processed games don't duplicate; extraction failure is fail-closed (no partial row) and recorded as a `sync_failure`.
6. **Story input tests** — observation engine consumes context and emits the expected beat; low/`null` confidence falls back to neutral workload language.
7. **Language guardrail tests** — assert forbidden phrasings ("tonight against", "tomorrow", "next game against X") never appear without verified schedule data; safe phrasings used otherwise.
8. **Trend-overfit guard** — a single game's context must not, by itself, flip a multi-day trend label.

---

## Risks / Guardrails

- **Misleading story language** — inventing "tonight/tomorrow vs X" without schedule data. *Guard:* Story Language Rules + Phase 5 gating; safe relative wording by default.
- **Incomplete game data** — play-by-play missing or partial. *Guard:* tri-state/nullable fields, `confidence`, fail-closed (no row rather than a wrong row).
- **Doubleheaders** — two games per team per date. *Guard:* key on `game_pk`, never on `(team_id, date)`; tests with both games.
- **Suspended games** — resumed under a different `game_pk`, no link in our data. *Guard:* known `game_shape` detection gap; mark low confidence, don't assert outcomes.
- **Extra innings** — "late runs (7–9)" must not silently drop innings 10+. *Guard:* define late-runs precisely; separate 7–9 from total late innings in tests.
- **Opener / bulk-pitcher games** — no single "starter". *Guard:* reuse `game_shape` classification; populate starter fields as null/derived accordingly; don't force a starter.
- **Missing pitch counts** — boxscore may omit `pitches_thrown`. *Guard:* `starter_pitch_count` nullable; never coerce to 0.
- **Schedule assumptions** — assuming a next game exists. *Guard:* no future context without verified schedule data (Phase 5).
- **Overfitting one game into a trend** — one good/bad bullpen night reframed as a pattern. *Guard:* keep Completed Game Context descriptive of *that game*; trend labels stay multi-day; explicit overfit-guard test.
- **Storage/perf creep** — temptation to persist raw play-by-play. *Guard:* store derived fields only; PBP is consumed in-memory and discarded.

---

## Conclusion

The safest path is a thin, derived, fail-closed Completed Game Context layer: temporarily consume play-by-play/linescore during the existing postgame refresh, extract structured per-team context, store only the derived fields in one new `(team_id, game_pk)` table, and feed it into story generation behind a confidence gate and strict relative-time language rules. No raw play-by-play is stored, no new team/games entity model is required beyond the single context table, and the existing sync/idempotency machinery is reused.

**Implementation is safe to begin** at Phase 2 once this audit is accepted.
