# SP-04 Adaptive Schedule & Game-State Sync

## 1. Objective

SP-04 makes authoritative MLB schedule state the operational heartbeat of the Sync Pipeline. A one-shot worker fetches a baseball-date schedule, records SP-03 evidence, stops cleanly on unchanged content, applies only complete authoritative changes to the existing schedule authority, classifies meaningful transitions, creates narrowly scoped SP-02 work, records SP-01 outcomes, and persists the next poll as a future job.

This package establishes capability only. It does not change a Render service, GitHub Actions schedule, application-start scheduler, or production cadence.

## 2. Existing Infrastructure Reused

| Component | SP-04 disposition | Reason |
| --- | --- | --- |
| `ScheduledGame` and `schedule_ingestion` | EXTEND | Existing `(team_id, game_pk)` schedule authority, identity, date, matchup, series, doubleheader, suspended/resumed links, and legacy finality remain canonical. |
| `game_finality` | REUSE AS-IS | Existing conservative public/finality compatibility mapping remains unchanged. Operational state is separate. |
| SP-03 schedule subject and observation | WRAP | The existing date-range `/schedule` identity, normalized payload, immutable versions, completeness, empty-valid result, and fetch-attempt evidence remain authoritative. |
| `GameObservationState` and CU change detection | DO NOT TOUCH | This remains the accepted live-feed/PBP/boxscore observation authority. SP-04 does not substitute schedule finality for accepted final baseball evidence. |
| SP-02 `SyncJob` | REUSE AS-IS | `fetch_schedule` and `reconcile_final_game`, priority, `available_at`, active dedupe, leases, fencing, attempts, and retry policy already satisfy the execution contract. |
| SP-01 `SyncRun` | REUSE AS-IS | `schedule_game_state`, schedule source domain, scopes, stages, counters, failure evidence, and zero-mutation semantics already exist. |
| Continuous execution and change-impact orchestration | MIGRATE/WRAP LATER | CU remains production-safe and authoritative for its current path. SP-08/SP-09 decide convergence. |
| Daily/postgame schedules | DO NOT TOUCH | Existing triggers remain the only production wake-up mechanisms until later activation/certification. |

## 3. MLB Status Audit

The repository's MLB client calls `GET /schedule` with `sportId=1`, `hydrate=team`, and a bounded start/end date. `schedule_ingestion` previously preserved `statusCode` and reduced status to `scheduled`, `final`, `postponed`, `suspended`, or `other`. `game_finality` additionally protects against ambiguous abstract-final values and keeps accepted final status separate from boxscore usability.

SP-04 preserves the legacy field and stores the raw `detailedState` and `abstractGameState` alongside it. The operational mapper uses explicit precedence: postponed, suspended, cancelled, delayed, final, live, pregame, scheduled, unknown. Raw strings remain available when MLB introduces a state not yet mapped. This audit is repository- and fixture-observed; it is not a claim that MLB formally guarantees every status code forever.

## 4. Normalized Game-State Vocabulary

The backend-owned `GameState` values are:

| Value | Source interpretation |
| --- | --- |
| `scheduled` | `S`, Preview, or Scheduled |
| `pregame` | `P`, `PW`, `PR`, Pre-Game, Pregame, or Warmup |
| `live` | `I`, Live, or In Progress |
| `delayed` | detailed status contains Delayed, including delayed start |
| `suspended` | detailed status contains Suspended |
| `postponed` | detailed status contains Postponed |
| `cancelled` | `C` or detailed status contains Cancelled |
| `final` | `F`, `O`, `FR`, `FT`, Final, Game Over, Completed Early, or Final: Tied |
| `unknown` | no supported decisive mapping |

`ScheduledGame.status_state` is not changed: it remains the legacy public/finality compatibility field. `ScheduledGame.operational_state` is the SP-04 polling state. Official MLB status, never a clock or inning inference, owns state.

## 5. Transition Vocabulary

`GameStateTransition` contains `game_discovered`, `game_time_changed`, `game_status_changed`, `game_pregame`, `game_started`, `game_delayed`, `game_suspended`, `game_postponed`, `game_resumed`, `game_final`, and `game_final_corrected`.

Classification is a pure comparison of the prior persisted meaningful game-state snapshot and the new source snapshot. A stable per-game SHA-256 digest covers gamePk, baseball date, scheduled UTC time, operational/raw status, teams, score when supplied by schedule, doubleheader/game number, and resumed links. Unrelated schedule payload changes therefore create no game transition. A same-state Final digest change is `game_final_corrected`, not another `game_final`.

A newly discovered already-final game is `game_discovered`; SP-12 historical closure or SP-07 bootstrap reconciliation must decide how to reconcile pre-existing finals. This avoids misrepresenting discovery as a newly observed live-to-final transition.

## 6. Source Observation Flow

`observe_schedule()` is the SP-04 non-mutating acquisition/evidence boundary. It reuses the frozen ingestion module's established schedule identity builder and the same MLB client, request identity, canonical collection fingerprint, payload artifact behavior, fetch-attempt behavior, and run/job links. The legacy ingestion module remains byte-for-byte unchanged because a governed incident-audit contract pins it.

The one-shot path is:

1. Start or attach a `schedule_game_state` SyncRun.
2. Fetch one baseball date through the existing MLB client.
3. Record the SP-03 observation and fetch attempt.
4. If complete and changed, compare per-game snapshots and call existing `ingest_games()`.
5. Persist operational state, provenance, transition, and next poll on both established team-game rows.
6. Enqueue justified downstream/follow-up jobs.
7. Record run counters and finish the run.

The worker revalidates and extends its SP-02 lease after acquisition and again immediately before committing canonical work. SP-02 settlement performs the final ownership check, so a reclaimed stale worker cannot mutate schedule authority after its fetch.

## 7. Polling Policy

Policy `game-state-poll-v1` uses deterministic UTC-naive timestamps and enforces a 60-second minimum and 24-hour maximum.

| State/context | Interval | Priority |
| --- | ---: | ---: |
| Live | 90 seconds | 10 |
| Delayed | 120 seconds | 10 |
| Pregame/warmup | 150 seconds | 25 |
| Scheduled, start passed or under 1 hour | 5 minutes before start; 2 minutes after scheduled start | 20 |
| Scheduled, 1–4 hours | 15 minutes | 100 |
| Scheduled, 4–24 hours | 30 minutes | 100 |
| Scheduled, more than 24 hours | 6 hours | 300 |
| Suspended | 30 minutes | 300 |
| Postponed | 6 hours | 300 |
| Cancelled | 24 hours | 300 |
| Newly Final/unreconciled | 15 minutes | 20 |
| Final explicitly known reconciled | 24 hours | 300 |
| Unknown | 30 minutes | 100 |
| Empty-valid current date | 6 hours | 300 |
| Empty-valid future date | 12 hours | 300 |
| Empty-valid past date | 24 hours | 300 |

No jitter is used in v1, keeping decisions reproducible.

## 8. Polling Policy Version

`POLLING_POLICY_VERSION = game-state-poll-v1` is stored on `ScheduledGame`, in poll job payloads/dedupe identities, and in run outcome metadata. A later policy change can therefore be distinguished from a source state change.

## 9. Poll Planning

`plan_game_state_polls()` finds persisted games whose `next_poll_at` is null or due, bounded by default to yesterday through seven days ahead, groups them by MLB baseball date, calculates each game's state-aware priority, and enqueues one date-grain fetch. Explicit date input supports repair/backfill planning without silently scanning all history. The worker fetches the date once and still calculates game-specific decisions. The earliest per-game deadline controls the next date fetch, avoiding wasteful game-by-game schedule calls.

Restart durability comes from two existing stores: `ScheduledGame.next_poll_at` records each entity decision, while the future SP-02 `fetch_schedule` job records executable due work. The planner repairs missing/due work idempotently after restart.

## 10. Queue / Priority / Dedupe Contract

SP-04 uses existing job types only:

- `fetch_schedule`: baseball-date scope, payload schema v1, policy version, reason, and optional gamePk list.
- `reconcile_final_game`: game scope, payload schema v1, baseball date, source observation ID, and transition.

Lower numeric priority is higher. Central constants are 10 active, 20 near-start/final, 25 pregame, 100 normal, and 300 cold.

Poll dedupe is `GAME_STATE:{baseball_date}:{available-minute}:{policy-version}`. It does not require unknown future source content. Concurrent planners collapse on SP-02's active partial unique index, while a later due-time generation remains enqueueable. Final handoff dedupe is `RECONCILE_FINAL_GAME:{gamePk}:observation:{source_observation_id}`.

## 11. Canonical Schedule Update

Complete changed observations reuse `ingest_games()` and its stable gamePk/team identity, matchup, date, scheduled time, doubleheader, series, and resumed-link upsert. No second game table exists. SP-04 adds operational fields only. Legacy `status_state` continues to be written exactly as before.

## 12. Source Provenance

`source_observation_id` remains the current canonical schedule provenance. `last_transition_observation_id` freezes the exact immutable observation that justified the last meaningful transition. `game_state_fingerprint` is a meaningful per-game projection, not a replacement for the complete SP-03 source fingerprint or payload.

## 13. Finality Handoff

A transition from a non-final operational state to authoritative Final creates one high-priority `reconcile_final_game` job. It is attached to the current SyncRun and parent poll job and carries gamePk, baseball date, immutable source observation ID, and `game_final`. SP-04 does not execute that job. SP-07 must fetch and reconcile the official final boxscore/PBP/appearance record and must preserve the existing distinction between schedule Final and accepted usable final baseball evidence.

## 14. Postponement / Suspension / Resume

Postponed and suspended states are explicit and never imply finality or deletion. Existing original/resumed dates and gamePk links remain source facts. Transitioning delayed or suspended to Live is `game_resumed`. MLB gamePk remains identity; SP-04 never invents a replacement identity.

## 15. Doubleheader Handling

All canonical, transition, poll payload, and downstream identities use gamePk. Two games with the same teams and baseball date remain separate in `ScheduledGame` and in transition scope. The shared date fetch is only acquisition batching, not game identity.

## 16. Baseball Date Handling

MLB `officialDate` owns baseball date. UTC `gameDate` owns scheduled instant. Runs and jobs use the official baseball date even when the first pitch occurs after UTC midnight. Tests cover two same-date doubleheader gamePks whose UTC timestamps fall on the following date.

## 17. Failure / Partial / Empty Behavior

- Failure: SP-03 records the failed fetch attempt; no observation, canonical mutation, transition, or fake absence is created. SP-02 schedules the retry and the prior known-good state remains.
- Partial/unknown: evidence is retained but is not authoritative; missing games are not deleted and transitions are not emitted.
- Empty complete: `empty_valid` is a successful zero-mutation observation and receives a cold follow-up.
- Unchanged complete: no new observation version, canonical update, transition, or downstream reconciliation is created. The run records one source read, zero changes/mutations/downstream work, and zero-mutation success.

## 18. Scheduler Boundary

SP-04 provides a planner and one-shot worker only. No loop, daemon activation, Render Blueprint, GitHub workflow, APScheduler configuration, or cadence changed. The present production wake-up interval may be too slow to realize 90-second live polling; activation and wake-up certification remain a later operational decision, principally SP-14 with SP-08 requirements.

## 19. Representative Execution Path

Tests execute a real SP-02 claim/handler/settlement around the SP-04 worker, use the existing MLB client boundary with bounded fixtures, persist SP-03 source observations and attempts, update existing schedule rows, attach SP-01 runs/scopes/outcomes, enqueue final work, and schedule the next one-shot poll. No production path is rerouted in this package.

## 20. Explicit Non-Goals

SP-04 does not add endpoints, change HTTP retries, ingest Statcast, expand rosters or transactions, ingest live pitches/relievers, reconcile final boxscores, compute workload/Team State/roles/deployment, rebuild read models, publish, add a dashboard, alter frontend payloads, or change production scheduling.

## 21. SP-05 / SP-07 / SP-08 Handoffs

- SP-05 may use game identity/state/time to prioritize roster and transaction refresh, but roster authority remains independent.
- SP-06 receives gamePk, scheduled time, state, transition, and next-poll context for richer pregame work.
- SP-07 implements `reconcile_final_game`; it must treat the supplied observation as schedule provenance, not final appearance proof.
- SP-08 may later create live-game delta work from `game_started`/`game_resumed`; SP-04 deliberately does not enqueue or execute live ingestion.
- SP-12 must bootstrap complete historical/final schedules that are discovered already Final rather than observed transitioning to Final.
- SP-13 consumes `game_final_corrected` reconciliation work and SP-03 predecessor lineage for correction decisions.
- SP-14 owns activation cadence, monitoring, alerting, and legacy retirement.

## 22. Acceptance Checklist

- [x] One normalized operational game-state vocabulary exists without changing legacy public finality.
- [x] One deterministic transition classifier exists.
- [x] Schedule polling uses SP-03 observations/fetch attempts and run/job links.
- [x] Unchanged, partial, failure, and empty-valid behavior fail safely.
- [x] Adaptive policy is centralized, bounded, deterministic, and versioned.
- [x] Entity decisions and executable due work survive restarts.
- [x] SP-02 priority, `available_at`, payload version, and database dedupe are reused.
- [x] Live-to-Final creates one durable SP-07 handoff; unchanged Final does not duplicate it.
- [x] Same-state meaningful Final change is a correction generation.
- [x] Doubleheaders and official baseball dates remain distinct/correct.
- [x] PostgreSQL CI owns concurrent planner/dedupe and inherited queue/source concurrency proof.
- [x] Migration is additive, nullable-first, indexed narrowly, and downgrade-capable.
- [x] No production cadence, acquisition domain, baseball/public semantic, frontend, or main-branch change exists.
