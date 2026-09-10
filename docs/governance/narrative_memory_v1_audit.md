# Narrative Memory V1 Audit

## Executive summary

BaseballOS already has enough persisted workload history to support a small Narrative Memory V1, but it does not yet remember stories as stories. The durable foundation is the `game_logs` table, which stores pitcher appearances by date and can support multi-day workload windows when the data has been seeded or continuously synced. `fatigue_scores` and `sync_runs` add useful calculated and freshness history, but they are not full daily team snapshots.

The current observation and story layers are generated from runtime payloads. They can explain what is true now, but they do not persist selected stories, narrative themes, or story continuity across days. A practical V1 should therefore start by deriving continuity evidence from existing game logs and current availability helpers before adding any story archive or new public surface.

## What BaseballOS already remembers

- Pitcher appearances are persisted in `backend/models/game_log.py` with `pitcher_id`, `mlb_game_pk`, `game_date`, opponent, innings, pitches, leverage, save/hold/blown-save flags, and standard line statistics.
- Game log uniqueness is enforced by `(pitcher_id, mlb_game_pk)`, which supports append-style sync without duplicate appearances.
- Game logs are indexed by pitcher/date, game id, and game type, which makes pitcher workload windows viable.
- `backend/seed.py` can seed historical seasons through `HISTORICAL_SEASONS = [2024, 2025]`, so the repository has a path for multi-season workload history when the seed process has been run.
- `backend/services/sync.py` appends recent game logs during daily sync. The default recent sync window is seven days, but existing rows are retained.
- `backend/models/fatigue_score.py` persists calculated pitcher fatigue rows with `calculated_at`, 7-day and 14-day workload fields, days since last appearance, and risk level.
- `backend/models/sync_run.py` persists sync metadata, including latest game/workload dates, latest fatigue calculation time, record counts, API calls, failures, and status.
- `backend/services/sync_metadata.py` exposes durable freshness and coverage metadata from persisted data and sync runs.
- `backend/services/team_changes.py` can compare a team bullpen state against the previous completed team game.
- `backend/api/bullpen.py` exposes pitcher recent logs, pitcher fatigue trend, team changes, dashboard, landscape, board, and game-context views that can provide partial historical context.

## What BaseballOS does not remember yet

- Surfaced stories are not persisted.
- Observations are not archived as daily records.
- There is no narrative thread identifier for "same story continuing."
- There is no daily team bullpen snapshot table.
- There is no dedicated pitcher trend table.
- Current team assignment is stored on `Pitcher`, but historical team membership is not modeled as its own timeline.
- Runtime story candidates do not have stable cross-day identity.
- Observation IDs are deterministic for a supplied payload, but they are not persisted and do not prove that an observation continued across days.
- `backend/api/observations.py` currently serves deterministic sample and preview collections, not persisted production observation history.
- `frontend/src/components/home/homeIntelligenceView.js`, `frontend/src/components/stories/storiesFeedView.js`, and `frontend/src/components/bullpen/board/teamBullpenStoryView.js` derive human-readable stories from current payloads, not from stored story memory.
- Sync status JSON is overwritten as an operational cache. Durable sync history comes from `sync_runs`, not the JSON file.

## Existing files/modules relevant to narrative memory

| Area | Files/modules | Narrative memory relevance |
| --- | --- | --- |
| Raw pitcher workload | `backend/models/game_log.py`, `backend/services/sync.py`, `backend/seed.py` | Best existing source for multi-day bullpen usage, repeated appearances, and workload concentration. |
| Calculated workload state | `backend/models/fatigue_score.py`, `backend/services/fatigue.py` | Useful for current and recent calculated state, but `calculated_at` is a calculation timestamp rather than a guaranteed daily baseball snapshot. |
| Sync freshness | `backend/models/sync_run.py`, `backend/services/sync_metadata.py` | Supports trust language around data-through dates, sync gaps, and freshness limitations. |
| Team changes | `backend/services/team_changes.py` | Closest existing continuity primitive, but only compares current state to the previous completed team game. |
| Availability windows | `backend/services/availability_snapshot.py`, `backend/services/bullpen_population.py` | Existing helpers can compute short workload windows and role context from stored game logs. |
| Team intelligence | `backend/services/bullpen_board.py`, `backend/services/bullpen_stress.py`, `backend/services/game_context.py` | Runtime team context and stress signals that could be paired with historical workload windows. |
| Backend routes | `backend/api/bullpen.py`, `backend/api/observations.py` | Existing routes expose some history, but no endpoint currently returns narrative continuity or stored story history. |
| Observation contracts | `backend/observations/contracts.py`, `backend/observations/builders.py`, `backend/observations/enums.py` | Evidence and limitation contracts are useful patterns for V1, but current observation generation is not archived. |
| Homepage/stories language | `frontend/src/components/home/homeIntelligenceView.js`, `frontend/src/components/stories/storiesFeedView.js`, `frontend/src/utils/bullpenLanguage.js` | Human-readable story presentation exists, but it operates on current candidates and does not remember prior selections. |
| Story Engine V1 branch | `feature/story-engine-v1-foundation` | Relevant unmerged context for story tiering, significance, suppression, and evidence quality. Narrative Memory V1 should not depend on it until merged. |

## Recommended Narrative Memory V1 scope

Start with a small backend continuity read model over existing persisted workload data. Do not add UI, a public story API, or runtime product behavior in the first implementation pass.

The smallest useful V1 should:

- Accept a team, pitcher, reference date, and fixed windows such as 7, 10, and 14 days.
- Derive continuity evidence from `GameLog` rows first.
- Reuse existing availability and team-change helpers where they already explain current state.
- Return explainable facts such as repeated arm usage, recent recovery after a stressful stretch, or pitcher workload trend changes.
- Include evidence fields for window start, window end, data-through date, appearance counts, pitch counts, involved pitchers, and limitations.
- Avoid saying "this story has been developing for X days" unless the claim can be proven from either persisted game-log dates or a future story archive.
- Treat exact story continuity as a later storage problem, not a requirement for the first V1.

Existing game logs are likely enough for the first V1 if the product claim is "the stored workload data shows this pattern over the last N days." A new story or observation archive becomes necessary when BaseballOS needs to say that the same selected story was active, suppressed, escalated, or resolved across multiple days.

## Risks / trust concerns

- The `GET /pitchers/<id>/logs?days=N` route is anchored to the host date, not an explicit product reference date, which can make historical windows less precise.
- `FatigueScore.calculated_at` should not be treated as a complete daily state history unless scores are known to have been calculated daily.
- Current team assignment can change, so team-level historical claims need care around trades, options, and roster movement.
- A seven-day sync window is enough for daily catch-up but not a substitute for complete historical coverage if sync jobs fail for long stretches.
- Story language must not overstate certainty. If data coverage is partial, claims should say so through evidence and limitations.
- "Closer" or role-specific language should only be used when role evidence is strong enough. Otherwise, use pitcher or late-inning arm language.
- Deterministic observation IDs are useful, but without persistence they do not provide narrative memory.
- A first V1 that only reconstructs from game logs can identify workload patterns, but it cannot remember editorial decisions such as which story was selected yesterday.

## Suggested next implementation branch name

`feature/narrative-memory-v1-foundation`
