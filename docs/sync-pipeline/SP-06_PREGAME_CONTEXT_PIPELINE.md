# SP-06 Pregame Context Pipeline

## 1. Objective

SP-06 gives BaseballOS one durable official record of changeable pregame context for each MLB game. It records game-grain MLB source evidence, preserves probable-starter revisions, keeps a simple current projection on the existing schedule row, and schedules bounded one-shot refresh work through the existing Sync Pipeline.

This is backend execution capability only. It does not activate production scheduling, rebuild Tonight or Matchup, predict starter usage, or change any public baseball meaning.

## 2. Existing Infrastructure Reused

| Existing component | SP-06 disposition | Contract |
| --- | --- | --- |
| `ScheduledGame` | EXTEND | Remains game/time/team/state authority and gains only a current pregame projection and poll metadata. |
| SP-04 operational game state | REUSE AS-IS | Decides whether pregame polling remains relevant. SP-06 does not create a second scheduled-time or game-state authority. |
| SP-03 source subjects/observations | REUSE AS-IS | Own immutable request evidence, completeness, fetch attempts, fingerprints, and correction lineage. |
| SP-02 `SyncJob` | EXTEND vocabulary / REUSE execution | `fetch_pregame_context` uses existing priority, `available_at`, active dedupe, lease fencing, attempts, and retries. |
| SP-01 `SyncRun` | REUSE AS-IS | `pregame_context` runs record game/team scope, source reads/changes, canonical mutation, warnings, and zero-mutation success. |
| SP-05 roster membership | READ/CROSS-CHECK ONLY | A proven active-roster mismatch is reported; pregame evidence never changes membership or current team. |
| Existing Tonight/Matchup builders | DO NOT TOUCH | They remain publication/read-model consumers until SP-09/SP-11 adopt pregame mutations. |
| CU live-feed probable IDs | MIGRATE LATER | Useful material observation evidence, but not a durable pregame revision history. SP-08 owns live convergence. |

No parallel schedule, queue, run, source-fingerprint, roster, or public read-model system was introduced.

## 3. Pregame Context Definition

The SP-06 authoritative projection contains:

- MLB `gamePk` and `officialDate`;
- official scheduled instant as observed, while `ScheduledGame.game_datetime` remains SP-04 authority;
- home and away MLB team IDs;
- nullable official probable-pitcher MLB IDs and names for both sides;
- game type, game number, doubleheader flag, venue, and resumed-from game identity when supplied;
- immutable source observation, explicit completeness, meaningful fingerprint version, observed time, and revision lineage.

Official lineup ingestion, handedness summaries, weather, travel, projected lineups, matchup statistics, starter-length forecasts, and bullpen predictions are not included. Existing canonical pitcher handedness may be joined later when identity is resolved; SP-06 performs no extra bio fetch.

## 4. Source Authority

The sole authority is official MLB Stats API `GET /api/v1/schedule` at game grain:

```text
sportId=1
gamePk=<MLB gamePk>
hydrate=team,probablePitcher,venue
```

Provider is `mlb_stats_api`; domain is `pregame`; subject type is `game`; subject key is `game:<gamePk>`. The request-schema version is 1. Equivalent request parameters produce the same SP-03 identity. No third-party, fantasy, beat-report, rotation-order, or inferred starter source is accepted.

The official OpenAPI lists `gamePk` and `gamePks` schedule filters. A bounded request was also observed to return one game with hydrated team, probable-pitcher, venue, time, type, and status fields. These endpoint-shape claims are experimentally observed, not a service-level stability guarantee. See Appendix A.

## 5. Probable Starter Contract

The stable source identity is the probable pitcher's MLBAM ID. Name is retained as source context. If a matching `Pitcher.mlb_id` already exists, the context version stores its canonical pitcher FK. If not, the MLBAM ID remains authoritative and the canonical FK is null; SP-06 does not manufacture a roster member, team assignment, active flag, or bullpen role.

Probable starter is pregame context, not final starter authority. SP-07 must independently determine actual starters and relief appearances from the official final record.

## 6. Completeness

| State | Meaning | May replace current context? |
| --- | --- | ---: |
| `complete` | Exactly the requested game is present with valid gamePk, official date, and both team identities; probable pitchers may legitimately be absent | Yes |
| `partial` | Requested game exists but required game/team identity is malformed, or a supplied probable-pitcher object lacks usable identity | No |
| `unknown` | The requested game is absent, duplicated, or coverage cannot be established | No |
| `failed` | Request raised; SP-03 records a failed attempt and creates no observation | No |

Unknown probable starter is not incomplete evidence. A complete response can have both starters, one starter, or neither starter named. A targeted game request returning zero games is not `empty_valid`, because the already-known requested game is expected.

## 7. Current vs Historical Context

Current reads use the `ScheduledGame` projection and its `pregame_context_version_id`. Both team-perspective rows for one gamePk point to the same version and contain the same home/away probable values. `current_pregame_context(game_pk)` resolves that pointer.

Historical reads use append-only `game_pregame_context_versions`. `pregame_context_at(game_pk, observed_at)` returns the latest revision observed at or before the requested time. Historical truth therefore does not require reparsing source payload artifacts.

## 8. Versioning

The first complete meaningful context creates V1. A later complete meaningful change creates V2 with `predecessor_version_id=V1`; V1 remains queryable. A replay with the same meaningful fingerprint creates no context version even if irrelevant source metadata changed. A complete return to an earlier starter configuration is still a new chronological version because it follows the current predecessor.

Partial/unknown observations remain SP-03 evidence but never advance the current projection. Failure leaves both current and historical context unchanged.

## 9. Fingerprint / Meaningful Change

`pregame-context-v1` is SHA-256 over deterministic JSON containing gamePk, baseball date, observed scheduled instant, home/away teams, probable-pitcher IDs/names, venue, game type/number, doubleheader flag, and resumed-from identity. Volatile transport metadata, unrelated schedule description fields, and response ordering are excluded.

The SP-03 source fingerprint and SP-06 context fingerprint answer different questions: the former proves source-payload change; the latter proves a BaseballOS pregame-context change.

## 10. Change Vocabulary

Structured append-only mutation values are:

- `pregame_context_discovered`
- `probable_starter_added`
- `probable_starter_changed`
- `probable_starter_removed`
- `pregame_context_changed`

Starter mutations retain side/team, old MLBAM ID, new MLBAM ID, gamePk, baseball date, source observation, context version, and SyncRun. Removal is possible only from a complete authoritative observation. A non-starter meaningful change uses the generic context event.

## 11. Roster Cross-Check Boundary

SP-05 remains roster authority. After a complete context change, SP-06 compares a probable MLBAM ID only when SP-05 already has a non-empty current active-roster population for that club. A mismatch is recorded in the run outcome as `roster_confirmation_deferred`.

SP-06 does not close/open membership, change `Pitcher.team_id`, or enqueue a roster job from ambiguous absence. Targeted roster confirmation can be activated later when orchestration has a proven freshness contract.

## 12. Game-State Boundary

SP-04 supplies `ScheduledGame.operational_state` and `game_datetime`. SP-06 polls scheduled, pregame, delayed-before-start, postponed, and unknown games. It stops and clears future pregame polling for live, suspended-after-start, final, and cancelled games. Existing context is preserved as history.

A resumed game that has already begun does not become a new probable-starter event. A game-time change affects SP-06 priority only after SP-04 updates schedule authority; SP-06 never writes `game_datetime`.

## 13. Polling Policy

Policy `pregame-context-poll-v1` is deterministic and uses UTC-naive instants:

| State/time to first pitch | Interval | Priority |
| --- | ---: | ---: |
| Scheduled, more than 6 hours | 6 hours | 300 |
| Scheduled, 2–6 hours | 30 minutes | 100 |
| Scheduled, 30–120 minutes | 10 minutes | 100 |
| Scheduled, less than 30 minutes or scheduled time passed | 2 minutes | 15 |
| Pregame/warmup | 90 seconds | 15 |
| Delayed before start | 3 minutes | 15 |
| Postponed | 6 hours | 300 |
| Unknown operational state | 30 minutes | 100 |
| Live, suspended after start, final, cancelled | Stop | none |

Lower numeric priority is higher. There is no jitter in v1. `next_pregame_poll_at` and policy version survive process restarts.

## 14. Queue / Dedupe / Priority

The job type is `fetch_pregame_context`, scope type is `game`, and payload schema is 1. Payload contains gamePk, baseball date, reason, policy version, and optional SP-04 transition-observation provenance. It never contains a source response.

Active dedupe is:

```text
PREGAME_CONTEXT:<gamePk>:<available-minute>:pregame-context-poll-v1
```

Repeated planning of one due generation collapses through the SP-02 partial unique index. Different gamePks in a doubleheader never collapse. Later minute generations remain valid after the current work settles.

## 15. Worker Flow

The one-shot worker:

1. receives a claimed/fenced SP-02 job;
2. creates or attaches a `pregame_context` SyncRun;
3. reads SP-04 game state and stops if pregame is closed;
4. fetches the official game through the existing MLB client;
5. records SP-03 fetch attempt, observation, payload artifact, and completeness;
6. revalidates its lease;
7. projects and fingerprints only complete context;
8. locks only the gamePk, appends a version/mutations if meaningful, and updates both schedule projections;
9. records roster discrepancies without changing roster authority;
10. persists the next due SP-02 job when relevant;
11. records SP-01 outcome and returns for SP-02 settlement.

No busy loop or production route invokes this worker in SP-06.

## 16. Failure / Partial Behavior

- A source failure records a failed SP-03 attempt, leaves known-good context intact, and rethrows so SP-02 applies bounded retry.
- Partial or unknown evidence is retained but produces no context version, no starter-removal event, and no current-projection change.
- An unchanged complete fetch is successful zero-mutation work and may advance only the next poll.
- An official complete removal creates a new version and `probable_starter_removed`; the predecessor remains intact.

## 17. Doubleheaders

All source subjects, versions, mutations, current pointers, jobs, and dedupe keys use gamePk. Team/date is never identity. A same-date doubleheader therefore retains different probable starters and independent polling generations for each game.

## 18. Suspended / Resumed Games

When a game has begun and becomes suspended, pregame polling stops and the original context remains historical. SP-04 retains schedule/resumption identity; SP-08 owns any resumed live data. SP-06 does not reinterpret the original probable starter as a probable starter for the continuation.

## 19. Database / Index Design

Migration `a6d2e8f4b1c7` follows `f3c7a1d9e5b2` and is additive.

New tables:

- `game_pregame_context_versions`: one immutable meaningful revision per game/source observation, with predecessor, probable starters, optional canonical pitcher FKs, game context, fingerprint, completeness, and provenance.
- `pregame_context_mutations`: compact SP-09 handoff facts for discovery, starter changes, removals, and other meaningful context changes.

`scheduled_games` gains nullable current probable-pitcher/name fields, observation/version pointers, fingerprint/version/completeness/update fields, and durable next-poll/policy fields. Existing rows are not guessed or backfilled. Indexes support due polling, probable MLBAM lookup, observation history, game/date history, and mutation lookup. JSON is not added or indexed.

PostgreSQL takes a transaction advisory lock derived from gamePk and row-locks that game's schedule/version rows. Unrelated games remain concurrent. Database uniqueness on `(game_pk, version_number)` and `(game_pk, source_observation_id, fingerprint_version)` is a second safety fence.

## 20. Explicit Non-Goals

- No Render, GitHub Actions, APScheduler, worker-service, or wake-up cadence change.
- No final-game reconciliation, final starter authority, live bullpen/game delta, or Statcast ingestion.
- No workload, Team State, arm read, role, deployment, rotation-transfer, prediction, or manager-intent logic.
- No Tonight/Matchup rebuild, publication, API payload, frontend, copy, or user-visible change.
- No official lineup or weather acquisition.
- No broad historical probable-starter backfill; MLB historical availability and announcement-time fidelity remain unproven.

## 21. SP-07 / SP-09 / SP-10 Handoffs

**SP-07:** probable starter is context only. Final reconciliation must independently establish actual starter, relief appearance set, pitching lines, and final evidence from official final sources.

**SP-09:** consume `pregame_context_mutations` to calculate affected game/team read-model work. SP-06 intentionally does not rebuild or publish any consumer.

**SP-10:** may compare historical probable context with SP-07 actual starter and retained workload to describe rotation-to-bullpen transfer. It must not use probable identity to predict starter length.

**SP-12/SP-14:** a later planner may seed league-wide upcoming work, and SP-14 may activate/certify the wake-up path. Until then, SP-06 is dormant capability.

## 22. Acceptance Checklist

- [x] Official MLB game-grain probable-starter source contract is defined and proven read-only.
- [x] Unknown starter remains null under complete evidence.
- [x] Current projection and historical predecessor versions are queryable.
- [x] Every current field points to exact SP-03 evidence.
- [x] Context fingerprint excludes irrelevant source metadata.
- [x] Unchanged fetches create no new context version.
- [x] Complete meaningful changes append versions and structured mutations.
- [x] Partial/unknown/failure cannot clear current authority.
- [x] Starter removal requires complete evidence.
- [x] Existing pitcher identity is reused without inventing roster/role state.
- [x] Roster discrepancies do not mutate SP-05 authority.
- [x] SP-04 owns game time/state and closes polling once the game begins.
- [x] GamePk keeps doubleheaders distinct.
- [x] SP-02 jobs are durable, prioritized, future-available, and active-deduplicated.
- [x] PostgreSQL per-game locking prevents duplicate versions/mutations/current projection races.
- [x] Migration is additive, nullable-first, preservation-safe, and downgrade-capable.
- [x] No production scheduling, derived intelligence, publication, API, frontend, or main-branch behavior changed.

## Appendix A — Official Source and Natural Read-Only Proof

Accessed 2026-09-08. No production database writes were performed.

1. **MLB Stats API OpenAPI document:** <https://docs.statsapi.mlb.com/openapi.json>. Supports the official `/api/v1/schedule` operation and its `gamePk`, `gamePks`, date, team, and field filters. The document does not provide a service-level guarantee for probable-pitcher announcement timing.
2. **Official MLB game-grain pregame request:** <https://statsapi.mlb.com/api/v1/schedule?sportId=1&gamePk=824792&hydrate=team,probablePitcher,venue>. Experimental observation returned exactly gamePk `824792`, official date/time/type/status, both team IDs, venue, and both probable-pitcher MLBAM IDs/names.
3. **Official MLB date sample:** <https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-09-09&hydrate=team,probablePitcher,venue>. Experimental observation returned 15 games: 11 with both probable starters and 4 with exactly one probable starter absent. This supports the contract that a successfully returned official game may be complete while one probable starter remains unknown. Counts are a dated observation, not a permanent schedule or completeness guarantee.
