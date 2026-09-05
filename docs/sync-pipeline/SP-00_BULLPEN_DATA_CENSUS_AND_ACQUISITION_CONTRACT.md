# SP-00 — Bullpen Data Census and Acquisition Contract

**Status:** Contract proposal; no runtime implementation

**Repository:** `NickolisK24/bullpen-intel-engine`

**Integration target:** `feat/sync-pipeline`

**SP-00 branch:** `feat/sp00-bullpen-data-census`

**Research accessed:** 2026-09-05

**Scope:** Backend repository audit, public-source research, data-model assessment, and acquisition contract only

## 1. Executive Finding

BaseballOS already has a stronger canonical bullpen substrate than a UI-led reading of the repository suggests. It acquires official MLB schedules, rosters, transactions, people, player game logs, game boxscores, linescores, play-by-play, and v1.1 live feeds. It persists appearance-grain pitching lines, historical roster snapshots, transactions, schedule context, starter/bullpen game splits, completed-game context, normalized final play-by-play, and a surprisingly broad set of pitch observations from MLB game feeds. It also has durable run, failure, work-item, source-observation, fingerprint, snapshot, evidence, and publication records. The Continuous Updates (CU-01 through CU-08) work provides a reusable change-detection-to-publication chain and must not be replaced merely to obtain a cleaner package taxonomy.

The present system is nevertheless lossy in important ways:

1. The MLB client often returns selected subtrees and discards the original response. Transactions are explicitly normalized from a transient response; linescore and live-feed raw responses are explicitly transient (`backend/services/mlb_api.py:610-678`).
2. `GameLog` is an excellent appearance ledger but stores one mutable current line per pitcher/game. Correction counters and last-correction metadata exist, but prior field values are not preserved (`backend/models/game_log.py:95-167`).
3. Final PBP plate-appearance rows are replaced on correction, while pitch rows preserve current/superseded state but update an existing natural-key row in place. Neither is a complete immutable observation-version archive (`backend/services/play_by_play_foundation.py:594-616`, `backend/services/play_by_play_foundation.py:800-866`).
4. BaseballOS does not call Baseball Savant/Statcast. Its pitch table captures many values exposed in MLB PBP, but lacks the richer atomic Savant contract: effective speed, spin axis, official expected metrics, run expectancy/win-expectancy deltas, wOBA values, explicit base occupancy before the pitch, handedness, and newer arm-angle fields.
5. Historical organizational depth is partial. Active/40-man roster snapshots and transactions are strong for observed MLB dates, but there is no complete durable player-team membership interval model, minor-league assignment history, or minor-league appearance/workload acquisition contract.
6. Several useful deployment facts are derived repeatedly from PBP and appearances, or retained only inside snapshots/evidence JSON. Canonical appearance entry/exit state and batter-sequence facts deserve reproducible domain facts rather than publication-only representations.
7. Current source observations use a mix of normalized facts, current-state JSON, fingerprints, and source metadata. There is no universal observation/version contract across domains.

The permanent acquisition rule is therefore:

> Acquire reliable, bullpen-relevant public observations at the smallest practical reproducible grain; retain canonical baseball facts permanently; version corrections without silently rewriting cited history; derive windows and interpretations from atomic facts; publish only separately governed semantics.

PostgreSQL remains appropriate. A full MLB reliever-only atomic contract is measured in hundreds of thousands of pitches and tens of thousands of appearances per season—not a distributed-data scale. With disciplined partitioning/indexing and no duplicate raw blobs, expected growth is comfortably within a solo-founder-maintainable PostgreSQL deployment.

## 2. Governing Acquisition Principle

The governing design is **Acquire broadly. Preserve atomic facts. Derive intentionally. Publish selectively.**

This means:

- Acquisition is justified by durable bullpen intelligence value, not by whether the current UI displays a field.
- Official identity, game, schedule, roster, transaction, boxscore, PBP, and Statcast observations are preferred over reconstructed or third-party summaries.
- Atomic facts are preferred when they unlock arbitrary future windows, correction replay, or new descriptive intelligence.
- Normalization must avoid both extremes: a single opaque giant payload and a schema that duplicates every source response field.
- Source payloads may be kept as content-addressed observation artifacts when needed for audit/replay, but canonical rows remain the normal query surface.
- Derived metrics are versioned, reproducible, and rebuildable from retained inputs.
- Unknown remains unknown. Missing workload is never converted to zero. Missing enrichment never invalidates otherwise supported core bullpen state.
- Workload is observed use, not medical readiness. Pitch change is observed change, not injury evidence. The contract excludes prediction, private health state, betting, fantasy advice, and inferred manager intent.

## 3. Repository Audit Method

The audit used the following evidence order:

1. Executable callers and outbound request construction.
2. SQLAlchemy models and Alembic migrations.
3. Normalizers, reconcilers, correction paths, and downstream services.
4. Scheduler/workflow entry points and command wrappers.
5. Tests as contract evidence.
6. Current documentation as corroboration, never as the sole implementation claim.

Repository-wide searches covered MLB/Stats API names, URLs, HTTP clients, schedule/roster/transaction/game terminology, all SQLAlchemy models and JSON columns, sync/refresh/backfill/repair scripts, application lifecycle hooks, workflows, snapshot/publication services, CU modules, and cache-miss behavior. Frontend files were not changed and were consulted only where necessary to identify a backend field consumer.

Key repository evidence:

- Resilient MLB client, retry policy, and endpoint methods: `backend/services/mlb_api.py:20-231`, `backend/services/mlb_api.py:478-745`.
- Appearance ledger schema and provenance: `backend/models/game_log.py:52-167`.
- Schedule authority: `backend/models/scheduled_game.py:23-80`.
- Roster/transaction history: `backend/models/roster_status_snapshot.py:32-66`, `backend/models/player_transaction.py:45-127`.
- Final PBP/pitch normalization: `backend/models/play_by_play_foundation.py:38-245`, `backend/services/play_by_play_foundation.py:619-770`.
- Live-feed material observation and fingerprinting: `backend/services/game_change_detection.py:1-35`, `backend/services/game_change_detection.py:68-210`, `backend/services/game_change_detection.py:283-360`.
- Daily/postgame entry points: `backend/services/sync.py:5823-6549`, `backend/services/sync.py:6549-7179`.
- GitHub fallback schedules and commands: `.github/workflows/baseballos-sync.yml:30-40`, `.github/workflows/baseballos-sync.yml:127-324`.
- CU chain and default-off control: `backend/services/continuous_execution.py:39-189`, `backend/services/continuous_execution.py:313-458`.

### Audit limitations

- SP-00 did not query production PostgreSQL. Schema and behavior claims are code/migration-proven; production row coverage and historical completeness remain separately measurable.
- No source was mutated. Public endpoints were sampled read-only.
- The repository has no root `render.yaml`; Render dashboard configuration cannot be proven exhaustively from Git alone. The report records repository-documented Render cron commands as **documented/current-expected**, not independently observed deployed state.
- External APIs have no published stability or service-level guarantee identified by this audit. Endpoint behavior observed on 2026-09-05 is labeled experimental where official documentation is incomplete.

## 4. Current Sync Architecture Inventory

### 4.1 Core acquisition and reconciliation components

| Component | Current role | Authority/writes | Disposition |
|---|---|---|---|
| `services/mlb_api.py` | Shared MLB GET client; timeouts, bounded retries, jitter, `Retry-After`, endpoint metrics | Source access only | **EXTEND** with typed source-domain clients and pagination/completeness contracts |
| `services/schedule_ingestion.py` | Rolling MLB schedule normalization into two team/game rows | Canonical schedule writer | **REUSE AS-IS**, then extend provenance/versioning |
| `services/roster_status_sync.py` | Active/40-man roster evidence and daily snapshots | Canonical current pitcher fields plus dated snapshots | **EXTEND** into membership intervals and fuller depth coverage |
| `services/transaction_ingestion.py` | Bounded official transaction ingestion, classification, correction metadata, sync windows | Canonical transaction writer | **REUSE AS-IS**; add paging/completeness and membership effects |
| `services/sync.py` | Legacy broad daily/postgame orchestration, boxscore fallback, fatigue, evidence, snapshots | Current production canonical/publication authority | **WRAP IN NEW CONTROL PLANE**; do not replace prematurely |
| `services/game_driven_ingestion.py` | Game-scoped finality, boxscore extraction, idempotent GameLog reconciliation, optional PBP | Shadow/write/authoritative-capable, governed | **REUSE AS-IS** as SP-07/SP-09 foundation |
| `services/play_by_play_foundation.py` | Final normalized play and pitch storage, correction/supersession handling | Optional, nonblocking final-game enrichment | **EXTEND**; preserve raw observation versions and fill context gaps |
| `services/game_change_detection.py` | CU-02 bounded live-feed material observation/fingerprint | Persists non-public current observation and work obligation | **REUSE AS-IS**; extend observation ledger rather than replacing |
| `services/continuous_execution.py` | One-shot CU-02→CU-07 orchestration with locks, budgets, allowlists, breakers | Default off; production modes separately gated | **WRAP IN NEW CONTROL PLANE** and activate only in later packages |
| `services/incremental_workload_rest.py` | CU-04 affected-pitcher workload/rest recalculation | Derived-only bounded chain | **EXTEND** after atomic workload contract exists |
| `services/incremental_arm_read_team_state.py` | CU-05 affected-pitcher/team derived state | Governed semantic layer | **REUSE AS-IS**; SP-00 does not change semantics |
| `services/incremental_read_model_rebuild.py` | CU-06 bounded read-model cohort | Shadow/proof read models | **REUSE AS-IS** |
| `services/incremental_publication.py` | CU-07 atomic candidate/pointer/cache-handoff proof | Proof authority unless explicitly adapted | **REUSE AS-IS**; integrate with durable publication authority in SP-11 |
| `services/intraday_reconcile.py` | Read-only drift census across rosters, identities, transactions, schedules | Audit only | **REUSE AS-IS** as SP-12/SP-14 diagnostic |
| Repair/backfill services and workflows | Bounded incident-specific reconciliation | Mixed read-only/planned/governed write | **MIGRATE** behind SP-13 registry over time; retire only after parity proof |

### 4.2 Current orchestration shape

```text
Render Cron (documented primary) or GitHub Actions fallback/manual recovery
  -> run_due_sync.py
  -> durable due-window + writer/concurrency guards
  -> daily | morning schedule-only | postgame service
  -> MLB Stats API acquisition
  -> canonical rows (schedule, pitcher, roster, transaction, GameLog, PBP)
  -> derived workload/fatigue/evidence/Team State/read models
  -> publication completeness gates
  -> immutable/published snapshot and downstream artifacts

Separately, dormant/controlled CU execution:
  run_continuous_cycle.py (one shot, no scheduler in repository)
  -> CU-02 material observation/fingerprint
  -> durable work obligation
  -> CU-03 reviewed impact plan
  -> CU-01 canonical reconciliation
  -> CU-04 workload/rest
  -> CU-05 Team State
  -> CU-06 read models
  -> CU-07 proof/explicit publisher
```

## 5. Current External Source Inventory

No production baseball source other than MLB Stats API was found. No Savant/Statcast CSV client, pybaseball dependency, or unrelated baseball HTTP client was found. Email/GitHub delivery clients are not baseball sources.

| Provider | Endpoint / parameters | Purpose and cadence | Caller(s) | Consumed / ignored | Destination / consumer | Resilience / incremental behavior |
|---|---|---|---|---|---|---|
| MLB Stats API | `GET /teams?sportId=1` | MLB team identity; daily/repair support | roster evidence, assignment, intraday | Returns team object; consumers select ID/name metadata; most venue/division fields unused | In-memory team maps, pitcher team labels | Shared 10s timeout, 3 retries; full scan |
| MLB Stats API | `GET /teams?season=&hydrate=sport` | team level/parent organization for transaction rehab classification | transaction ingest/repair | Stores `team_id`, `sport_id`, `parent_org_id`, season in memory; response otherwise discarded | transaction subtype derivation | Full scan by season; no response persistence |
| MLB Stats API | `GET /teams/{id}/roster?rosterType={pitchers|active|40Man|...}&season=&date=&hydrate=` | current/exact-date roster evidence | roster status sync/evidence/repair | Person ID, name, jersey, position/status used; many person/bio fields ignored | `pitchers`, `roster_status_snapshots` | One team/type/date request; no pagination; omission is distinguished from failure in newer paths |
| MLB Stats API | `GET /people/{id}/stats?stats=gameLog&group=pitching&season=&sportId=1` | legacy season game-log ingestion/backfill | daily sync, pitcher log backfill, audits | Appearance stats subset; provider split object otherwise discarded | `game_logs` | Per pitcher full-season scan; expensive, not incremental; no paging |
| MLB Stats API | `GET /people/{id}` / `GET /people?personIds=` | identity/team/hand/position resolution | assignment, identity repair, transaction qualification | ID/name/current team/position/hand/age subset; bio fields mostly ignored | `pitchers`, transaction qualification | Single/batch reads; current-state response, not versioned |
| MLB Stats API | `GET /people/{id}/stats?stats={season|career|lastXGames|yearByYear}&group=pitching` | aggregate pitcher/prospect helpers | limited/legacy | Selected first stat object/splits; source context not persisted | transient consumers | Not a primary sync path; no paging |
| MLB Stats API | `GET /schedule?sportId=1&hydrate=team&startDate=&endDate=&teamId=` | schedule, game identity/status/finality, rolling context | schedule ingestion, daily/postgame, CU-02, repairs | Game identity/date/teams/status/doubleheader/series/resumption; probable pitchers are not hydrated by this method | `scheduled_games`, work planning, snapshots | Bounded date windows; full response dates flattened; no raw response |
| MLB Stats API | `GET /transactions?sportId=1&startDate=&endDate=&teamId=&playerId=` | roster movement/IL/public transaction facts | daily transaction ingestion, intraday audit | Explicit typed fields only; description and other payload fields discarded | `player_transactions`, sync-window ledger, roster-depth evidence | Bounded window; correction-aware upsert; **no limit/offset pagination implemented** |
| MLB Stats API | `GET /game/{gamePk}/boxscore` | finality, authoritative appearance set, pitcher lines, team-at-appearance, bullpen order | daily/postgame/game-driven/audits | Many official pitching line fields used; batting/fielding/bench and unused pitching stats discarded | `game_logs`, completed context, team splits | One per game where cached; authoritative core; bounded retries |
| MLB Stats API | `GET /game/{gamePk}/linescore` | inning scores and coarse completed-game context | postgame | Derived context only; raw response discarded | `completed_game_contexts` | Optional/degraded; per game; no raw retention |
| MLB Stats API | `GET /game/{gamePk}/playByPlay` | final event/pitch context | postgame/game-driven | Normalized play and pitch subset; runner movement/credits and several event details not fully normalized | `game_play_by_play_events`, `game_pitch_events`, `play_by_play_processed_games`, completed context | Optional for core appearance; correction-aware; complete-game fetch, not deltas |
| MLB Stats API | `GET /api/v1.1/game/{gamePk}/feed/live` | CU-02 current material observation, finality and change detection | continuous detector | Canonical material subset plus source timestamp; raw full feed discarded | `game_observation_states`, `sync_jobs` | Schedule + one feed/game; fingerprint incremental; bounded correction horizon |
| MLB Stats API | minor-league `/teams?sportIds=11,12,13,14,16`, people search, year-by-year stats | helper/prospect support | limited/manual product paths | Returned transiently | no comprehensive relief-depth ledger | Not part of authoritative bullpen sync |

The endpoint implementations and parameter contracts are code-proven at `backend/services/mlb_api.py:478-741`. The generic HTTP behavior retries 429 and 5xx plus connection/timeouts, does not retry other 4xx, caps backoff, and records endpoint metrics (`backend/services/mlb_api.py:20-231`).

## 6. Current Database/Data Model Census

### 6.1 Material canonical and operational tables

| Table/model | Grain, key, and purpose | Material fields / JSON | History, mutation, reproduction |
|---|---|---|---|
| `pitchers` / `Pitcher` | One current pitcher; PK `id`; unique MLBAM `mlb_id`; team IDs are plain MLB integers | name, current team/name/abbr, assignment status/source/time, position, throws, age, jersey, active, roster raw/normalized status | Mutable current dimension. Historical team/status cannot be reproduced from this row alone; use snapshots/transactions/GameLog appearance team. |
| `game_logs` / `GameLog` | One pitcher appearance per `(pitcher_id, mlb_game_pk)`; FK pitcher and sync run | date/opponent/type, GS, IP + canonical outs, pitches/strikes/balls, H/R/ER/BB/K/HR/HBP/WP/BF/GF, LI, IR/IRS, save opportunity/hold/BS/W/L/S, appearance-team provenance, source revision | Mutable canonical current appearance. Correction count/last source retained, prior values not retained. Reproducible if official boxscore/gameLog still available; exact historical source version is not. |
| `scheduled_games` / `ScheduledGame` | Team-game row, unique `(team_id, game_pk)` | date/time, opponent, home/away, type, raw/normalized status, doubleheader/series, original/resumed linkage, source | Mutable upsert. Enough for calendar context; change history is absent. Re-fetchable, but prior announced times/statuses may not be reproducible. |
| `roster_status_snapshots` / `RosterStatusSnapshot` | Pitcher/team/date/roster-source observation; unique composite defined in model | active/40-man booleans, position, two-way, normalized/raw status, source/sync/correction timestamps | Date-grain historical snapshot, corrected in place with counters. Reproducible only where exact-date source remains available. No interval or absent-member row. |
| `player_transactions` / `PlayerTransaction` | One normalized transaction key; optional FK pitcher, MLB player identity | from/to team, transaction/effective/resolution/retro dates, raw type code, normalized category, IL flags/list, participant qualification, rehab subtype/materiality/evidence JSON, source/query window | Corrected in place with counters. Source description/raw record is not retained. Key uses official ID or deterministic fallback. |
| `player_transaction_sync_windows` | One acquisition attempt/window | query bounds, counts, status, quality counters, sync run | Append-oriented operational completeness ledger; useful for proving windows, not event versions. |
| `game_play_by_play_events` / `GamePlayByPlayEvent` | Normalized event order `(game, event_index)` | play/at-bat ID, inning/outs/score, pitcher/batter/team, change/scoring/mound flags, provenance | Game rows are delete-and-reinserted when fingerprint changes; correction metadata is copied but prior event values vanish. |
| `game_pitch_events` / `GamePitchEvent` | Pitch natural key `(game, at_bat_index, play_event_index)` | count/outs, pitcher/batter/teams, pitch/call, velocity, spin, extension, plate/release/trajectory vectors, movement, BBE basics, source revision/fingerprint, current/superseded state | Rich atomic MLB-feed fact. Existing keys update in place; disappeared keys become superseded. Prior values for corrected same key are not retained. |
| `play_by_play_processed_games` | One game PBP completion marker | finality, counts, unresolved/mismatch counts, event/pitch fingerprints, accepted sequence/authority, retry/failure/correction metadata | Mutable marker; supports completeness and correction decisions. |
| `team_game_pitching_splits` / `TeamGamePitchingSplit` | One team/game derived split | starter identity/outs/pitches/BF/balls/GS; bullpen outs/pitches/BF/balls/reliever count; totals; completeness JSON; off-days, density, series, DH, postponement/resumption, extras; correction metadata | Derived canonical domain fact, corrected in place. Rebuildable from complete GameLog + schedule; missing atomic facts reduce completeness. |
| `completed_game_contexts` / `CompletedGameContext` | One team/game derived narrative context | final score, starter exit, bullpen entry, largest lead/deficit, late runs, lead/change tags, confidence | Derived and mutable; no source/provenance/correction fields in model. Should be reproducible from PBP/boxscore if retained completely. |
| `fatigue_scores` / `FatigueScore` | Pitcher/calculation time derived score | component scores, days since last appearance, 7/14 appearances, 7-day pitches/IP/LI, risk label | Appendable calculations, but semantic/version identity is weak; underlying GameLogs are the durable authority. Public meaning remains governed separately. |
| `game_observation_states` / `GameObservationState` | One current material live observation per game | current normalized observation JSON/fingerprint, prior fingerprint only, source/time/finality/classification/diff JSON | Mutable current state. It proves latest transition but not the full observation sequence. Raw feed and older normalized observations are lost. |
| `game_ingestion_work_items` | One game/represented-date/candidate obligation | scope/finality/source, status/attempts/error, source revision, expected/reconciled rows, completion-proof JSON | Durable mutable work checkpoint. Operational, not source truth. |
| `sync_jobs` | Durable named/scope/date work obligation | family/lane/status/attempts/heartbeat/errors/details JSON/sync run | Mutable queue-like record with unique identity. Reusable SP-02 substrate; payload schema needs versioning. |
| `sync_runs` | One orchestration run | job/source/stage/status, source/derived dates, counts, API/retry counts, error | Append-oriented run ledger, later finalized. |
| `sync_failures` | Dead-letter/failure item | entity ref, payload JSON, error, resolution state/time | Append and later resolved. Payload may contain audit context; not canonical data. |
| `sync_schedule_attempts` | One due-window trigger attempt | mode/source/intended window/times/outcome/snapshot IDs/publication/recovery/operator/failure | Durable scheduler authority and dedupe evidence. |
| `postgame_processed_games` | One game postgame marker | game/team/final state, log and resolution counts, retry/status/reason/timestamps | Mutable lifecycle checkpoint. Distinct from canonical appearance/PBP completeness. |
| `evidence_objects` + citations | Versioned product evidence object keyed by evidence identity | claim/rule/subject/date, payload/trace/limitations JSON, correction and invalidation metadata | Derived evidence with correction hooks; downstream semantic layer, not source observation. |
| `composed_reads` + components/citations | Versioned read composition | completeness/reasons/limitations/component JSON, source/sync/correction/invalidation/supersession | Derived read model with lineage; should consume, not replace, canonical facts. |
| `dashboard_snapshots` | Immutable-intent publication candidate/version | payload JSON/version, data-through/reference date, status/current publication fields, source/error | Historical payloads retained; current publication pointer represented by flags/queries. Rebuildability depends on retained canonical/evidence inputs. |
| `team_progressive_publications` | Team/game-triggered publication | data-through/reference, payload/identity/fingerprints, source run, supersession/current state | Append/supersession publication history; public layer only. |
| `team_public_publications` + current pointers | Per-team immutable publication and single pointer | payload/proof/source identity/version/current pointer | Strong reusable SP-11 model; not acquisition storage. |

### 6.2 Loss, duplication, and recomputation findings

| Finding class | Proven example | Contract consequence |
|---|---|---|
| Retrieved then discarded | Transaction raw response is transient and converted to typed fields; linescore/PBP/live feed raw payloads are documented transient (`mlb_api.py:610-678`) | Add content-addressed source observation metadata/artifact retention where correction replay or contract debugging merits it. Do not store every duplicate response. |
| Held in Python, not persisted | Full boxscore objects and optional linescore/PBP inputs are passed through context generation; only selected facts survive (`sync.py:2368-2451`) | Persist stable atomic facts needed for later derivation; fingerprint the rest. |
| Aggregate when atomic available | `CompletedGameContext` and `TeamGamePitchingSplit` store useful aggregates; exact appearance entry/exit/base-out state is not a first-class canonical entity | Add canonical appearance-context facts derived from retained PBP. Keep aggregates as rebuildable acceleration. |
| JSON deserving first-class schema | `GameObservationState.observation` contains game identity/status/line/pitching evidence; `SyncJob.details_json` contains version-sensitive work payload | Keep bounded observation JSON but add immutable observation revisions; version job payload schemas and index routing columns. |
| Repeated computation | Workload windows, role/deployment profiles, concentration, recent/season comparisons are repeatedly derived from `GameLog`/snapshots | Retain atomic appearances/pitches; optionally persist versioned derived facts for expensive shared cohorts, never as sole truth. |
| Cannot reproduce later | Prior schedule times/status, prior mutable GameLog values, prior same-key pitch values, full live observations, exact raw transaction text | Introduce observation versions and canonical change lineage. |
| Silent historical overwrite risk | `GameLog`, roster snapshot, transaction, completed context and same-key pitch corrections update rows with counters but no prior values | Corrections must create immutable source/canonical versions or change records before current projection changes. |
| Duplicated baseball fact | Game/date/team/status exists across schedule rows, work items, observations, markers, GameLogs, contexts and snapshots | Establish canonical identity references; operational and publication records should point to canonical facts rather than independently author them. |

## 7. Current Data Flow

### 7.1 Final appearance path

```text
MLB schedule
  -> finality classification (status plus usable official pitching evidence)
  -> one game boxscore
  -> official pitcher order and pitching line extraction
  -> pitcher identity resolution
  -> GameLog upsert at (pitcher, game)
  -> appearance-team authority from official boxscore side
  -> correction provenance + affected-entity markers
  -> workload/fatigue/Team State/evidence/read models
  -> completeness-gated snapshot/publication
```

### 7.2 Final PBP/pitch path

```text
final-and-usable game + boxscore
  -> /playByPlay optional acquisition
  -> validate game/team/pitcher/order coverage
  -> normalized play events
  -> normalized pitch events with source/event fingerprints
  -> per-game completion marker
  -> current/superseded pitch state and downstream evidence
```

PBP enrichment is intentionally nonblocking for core GameLog success (`backend/services/sync.py:2509-2525`). This is the correct failure boundary and should survive.

### 7.3 Live change path

CU-02 takes a bounded active/correction slate, fetches one v1.1 feed per candidate, canonicalizes only material game identity/status/finality/linescore/pitching evidence, fingerprints it, rejects stale/ambiguous/weaker changes, and creates a durable work obligation (`backend/services/game_change_detection.py:213-280`). Exact material replay performs no state rewrite (`backend/services/game_change_detection.py:131-141`).

### 7.4 Roster/transaction path

Official active and 40-man observations update current pitcher state and produce dated snapshots. Official transactions are normalized into deterministic event keys, aligned to exact-date roster evidence where available, corrected in place, and connected to roster-depth evidence. Current design preserves important facts but lacks full membership intervals and raw event versions.

## 8. Existing Continuous Updates Reuse Assessment

| CU capability | Evidence-based assessment | Classification | SP integration |
|---|---|---|---|
| CU-01 continuous reliever ingestion | Canonical schedule/finality, game-scoped boxscore, deterministic appearance extraction, idempotent correction-aware GameLog reconciliation | **REUSE AS-IS** | SP-07 final reconciliation and SP-09 mutation engine |
| CU-02 game change detection | Durable material observation/fingerprint, source ordering, bounded slate and correction window | **EXTEND** | SP-03 observation versions and SP-04 adaptive game state |
| CU-03 change-impact orchestration | Reviewed plan fingerprints and bounded affected entities | **REUSE AS-IS** | SP-09 control point |
| CU-04 incremental workload/rest | Bounded affected-pitcher recomputation from canonical appearances | **EXTEND** | SP-10; teach it richer atomic inputs/windows later |
| CU-05 incremental arm reads/Team State | Existing governed semantics and bounded team state | **REUSE AS-IS** | SP-10; no semantic change in SP-00 |
| CU-06 incremental read models | Deterministic bounded cohort and comparison | **REUSE AS-IS** | SP-10 |
| CU-07 atomic publication/cache handoff | Expected-current concurrency, immutable candidate, atomic pointer, retryable cache handoff | **REUSE AS-IS** | SP-11 |
| CU-08 controlled execution | One-shot, default-off, locks, budgets, circuit breaker, allowlists, durable run evidence | **WRAP IN NEW CONTROL PLANE** | SP-01/SP-02/SP-04; do not build parallel orchestration |
| Existing final-game updates | Production daily/postgame authority with completeness gates and durable markers | **MIGRATE GRADUALLY** | SP-07/SP-12/SP-14 only after parity proof |

The current CU chain has no daemon, loop, queue broker, or repository scheduler hook. This is a useful composable execution unit, not yet the complete permanent scheduler. SP-01 and SP-02 should orchestrate it rather than reimplement its baseball logic.

## 9. External MLB Stats API Research

### 9.1 Confirmed endpoint capabilities

The official MLB Stats API OpenAPI document exposes:

- teams and team rosters, including roster type and historical date/season parameters;
- people, batch people, search, and player change-log resources;
- schedule filters by date/range/team/game/type/season;
- transactions filtered by dates, team, player, type, division and limit;
- player/team stats with season/date/window, split/situation, opponent, handedness, pitch/event and game filters;
- game boxscore, linescore, play-by-play, v1.1 live feed, timestamps and diff-patch;
- stats search/metrics, game win probability and context metrics.

The current BaseballOS client uses only a subset. Useful future official-source candidates include `feed/live/diffPatch`, `feed/live/timestamps`, explicit probable-pitcher hydration, people changes, stats search/metrics, and game context/win-probability endpoints. These are **candidate endpoints requiring empirical stability proof**, not automatic requirements.

### 9.2 Official pitching-line observations

A read-only boxscore sample on 2026-09-05 confirmed pitcher line keys including outs, innings, pitches, strikes, balls, batters faced, hits/runs/earned runs, walks, strikeouts, home runs, HBP, wild pitches, games started/finished, saves, holds, blown saves, save opportunities, inherited runners, and inherited runners scored. BaseballOS already stores nearly all bullpen-relevant members of that group. It does not need to reconstruct holds or inherited-runner counts when the official line supplies them; PBP remains the reconciliation and richer-context source.

### 9.3 Splits and aggregates

Official stats endpoints can request game logs, season/career/year-by-year, date windows, handedness and situation codes. Provider aggregates are useful for reconciliation and hard-to-reconstruct official categories. They should not replace atomic appearance, plate-appearance or pitch facts. Where BaseballOS can derive K%, BB%, K-BB%, recent splits, inning splits, home/away, workload windows, and group performance from atomic facts, those remain derived domain facts.

### 9.4 Reliability boundary

MLB is Tier A for identity, schedule/status, roster, transaction, official game records and official Statcast observations. Public endpoint availability and response schema stability have no service-level guarantee found in this research. The future client must pin observation schema versions, validate required fields, retain fingerprints, and fail closed on core ambiguity.

## 10. External Statcast/Baseball Savant Research

### 10.1 Atomic pitch dataset

The official Baseball Savant CSV documentation and a read-only CSV sample confirm pitch-grain rows keyed in practice by game, at-bat and pitch number/play context. Available fields include:

- pitch type/name, game/date/type, pitcher and batter MLBAM IDs;
- release speed, effective speed, release position, extension, spin rate and spin axis;
- horizontal/vertical movement, gravity-relative and arm-side movement, plate location and zone;
- pitch result description/type, count, outs, inning/half, base occupancy, batter/pitcher handedness;
- at-bat and pitch sequence numbers, home/away/batting/fielding score and post-pitch score;
- event/outcome, batted-ball type, hit location, exit velocity, launch angle, distance;
- estimated BA, SLG and wOBA on contact, actual wOBA value/denominator, BABIP/ISO values;
- win-expectancy and run-expectancy deltas, context-neutral pitcher run value;
- arm angle in the current CSV contract;
- fielding alignment and fielder identities.

The CSV contains deprecated and era-dependent fields. Nullability is meaningful. Historical coverage changes by tracking era: pitch tracking predates full Statcast, Statcast became league-wide in 2015, and the tracking platform changed to Hawk-Eye in 2020. Cross-era comparisons need explicit availability/version metadata.

### 10.2 Atomic versus aggregate

| Data | Atomic source available? | Contract decision |
|---|---|---|
| pitch identity/type/sequence/result/count/location | Yes | Permanently retain normalized pitch observation |
| velocity/spin/movement/release/extension/arm angle | Yes, with era/null caveats | Permanently retain normalized observation and source schema/version |
| base/out/score/handedness context | Yes | Retain; supports deployment and matchup derivation |
| batted-ball EV/LA/distance/type | Yes when tracked | Retain on pitch/BBE record; null does not mean zero |
| xBA/xSLG/xwOBA and run/win deltas | Atomic row values available | Retain provider values with provider/version identity; formulas may change |
| chase, zone, swing, whiff, foul, called strike, put-away | Mostly reproducible from atomic location/result/count plus a declared zone taxonomy | Derive and version; preserve provider aggregate only for reconciliation where useful |
| pitch usage/arsenal/velocity/movement windows | Reproducible from atomic pitches | Derive by arbitrary window; optional materialized aggregates |
| barrel/hard-hit | Atomic components and provider fields available | Retain components/provider estimate; derive threshold classifications with rule version |
| active spin | Public aggregate/glossary support exists, but an atomic active-spin CSV column was not confirmed in the sampled contract | **UNKNOWN / REQUIRES PROOF** before acquisition promise |
| launch direction | Hit coordinates/alignment exist, but a stable explicit public launch-direction contract was not confirmed | **UNKNOWN / REQUIRES PROOF**; derive spray direction only with documented geometry |
| pitch-specific run value | Atomic `delta_pitcher_run_exp` observed | Retain provider observation; derive aggregates |

### 10.3 Relationship to current `game_pitch_events`

Current MLB PBP storage already has pitch type/call, count/outs, pitcher/batter/team, start/end speed, spin rate/direction, extension, zone/plate, release and trajectory vectors, movement, and basic batted-ball measures (`backend/models/play_by_play_foundation.py:162-245`). Statcast acquisition must enrich or reconcile that natural pitch identity, not create an unrelated duplicate universe. A canonical pitch should allow multiple source observations with declared authority and matching status.

## 11. Complete Bullpen/Reliever Data Domain Census

### 11.1 Identity and organization

- MLBAM person ID is the durable canonical external identity.
- Throwing hand and primary/listed position are relevant and should be retained.
- Current organization and roster status are current projections; membership intervals and transaction events are historical facts.
- Birth date/debut may support age/experience cohorts and identity disambiguation. Retain birth date rather than a mutable age value if acquired; expose only where relevant.
- Height/weight are not required for the core contract. They may be optional Tier C bio enrichment if a specific pitch-mechanics study is approved; do not collect by default merely because available.
- Minor-league identity mapping uses the same MLBAM identity where official. External crosswalks are optional and require a defensible source.

### 11.2 Roster and relief depth

Required observations: active roster, 40-man roster, official position/status, team/date, transactions, assignments/options/recalls/IL activity, and explicit source absence/completeness. Future depth must distinguish observed roster eligibility from predicted call-up availability. Minor-league workload is relevant for potential reinforcement context but must be framed as observed use, not availability prediction.

### 11.3 Game, appearance, and deployment

Required canonical facts include exact appearance order, entry/exit inning and score, base/out state, inherited runners/scored, batters faced, multi-inning state, handedness sequence, save/hold/BS official outcomes, and source completeness. Leverage can be retained as an official provider observation where present or derived reproducibly from a versioned run/win expectancy table. “Highest leverage” and role/deployment profiles are derived, never manager-intent claims.

### 11.4 Workload

The atomic workload authority is the appearance plus its pitches, outs, batters faced, and date/time/game identity. From those facts BaseballOS can derive 2/3/5/7/10/14/30-day or arbitrary windows, consecutive-day patterns, back-to-back/three-straight/3-in-4/4-in-6/5-in-7, pitch spikes, multi-inning work, recent-versus-baseline, and bullpen concentration. Current `GameLog` is sufficient for most arbitrary day windows where pitches/outs/BF are non-null; it is not sufficient for within-game workload sequencing or historical source-version replay.

### 11.5 Performance

Official appearance lines support IP/ERA inputs, WHIP inputs, H/R/ER/K/BB/HR/HBP/WP, BF, saves/holds/BS and inherited traffic. Plate appearances/pitches support K%, BB%, K-BB%, opponent results, splits, FIP inputs, pitch results, chase/zone/strike/put-away, contact quality and expected metrics. BaseballOS should retain atomic denominators and derive rates. Provider season aggregates are reconciliation aids, not canonical replacements.

### 11.6 Rotation-to-bullpen transfer

Starter identity/outs/pitches/BF and team totals already support starter versus bullpen splits. PBP can support exit inning/state, openers, bullpen games and exact handoff. Schedule supports extra innings, series and recovery density. The future contract must classify starter/reliever at the game appearance, not from mutable current role.

### 11.7 Schedule and recovery

Official schedule supports prior/upcoming games, off-days, consecutive game days, home/road, doubleheaders, postponements, suspended/resumed games, extra innings and series structure. Venue/team metadata can support observed venue and time-zone transitions, but no reliable official travel itinerary was established. “Travel burden” is rejected unless later based on a documented public schedule-geography derivation with explicit limitations; actual travel is not to be invented.

### 11.8 Additional historically valuable domains

The following are high-value derivations unlocked by atomic pitches and appearances:

- pitch sequencing by count, batter hand, outing segment, and prior pitch;
- within-outing velocity/movement/release change;
- arsenal addition/removal and usage change with minimum-sample guards;
- release-point stability and arm-angle change as descriptive observations only;
- zone, chase, whiff, called-strike, foul and contact-quality changes;
- platoon usage and batter-quality context without intent claims;
- inherited-traffic difficulty and outcomes;
- days since activation/recall and observed workload since activation;
- bullpen composition/churn, workload distribution and role concentration;
- series-level usage concentration and recovery runway;
- times-facing-batter/lineup-position context where reproducible from PBP.

Warmup activity, bullpen phone calls, private medical state, unannounced availability, grip/intent, and proprietary pitch classifications are not reliably public and are rejected.

## 12. Master Field/Data Matrix

Status codes: `ACQUIRED_AND_STORED`, `ACQUIRED_NOT_STORED`, `STORED_BUT_UNUSED`, `DERIVED_NOT_PERSISTED`, `PARTIALLY_STORED`, `NOT_ACQUIRED`, `UNKNOWN_REQUIRES_PROOF`.

The matrix groups only fields that share a source, grain, retention, temperature and correction contract. A group is not permission to collapse its atomic members into one column.

| Field | Domain | Definition | Source | Endpoint/Dataset | Authority Tier | Current BaseballOS Status | Current Storage | Raw/Derived | Desired Storage | Key/Grain | Hot/Warm/Cold | Acquisition Trigger | Historical Backfill | Correction Strategy | Current Consumer | Future Potential | Required/Optional | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MLBAM player ID | Identity | Official person identity | MLB | people/roster/boxscore | A | ACQUIRED_AND_STORED | `pitchers.mlb_id`, PBP IDs | Normalized | Canonical player | player | Cold/Warm | first sight + roster/transaction change | all retained players | version aliases/merges | all pitcher reads | cross-source join | Required | Never key by name |
| Full name | Identity | Official display name | MLB | people/roster | A | ACQUIRED_AND_STORED | `pitchers.full_name` | Normalized | current plus name history if changed | player/effective time | Cold | first sight/change | people lookup | version material changes | display/search | identity continuity | Required | Current-only today |
| Throwing hand | Identity | Official throws R/L | MLB | people/roster | A | ACQUIRED_AND_STORED | `pitchers.throws` | Normalized | canonical player attribute | player | Cold | first sight/reconcile | people | correction version | role/matchups | platoon context | Required | Null-safe |
| Position / two-way status | Identity/roster | Official listed position at observation | MLB | roster/people | A | ACQUIRED_AND_STORED | pitcher + roster snapshot | Raw + normalized | dated membership attribute | player/team/date | Warm | roster event/daily | roster-by-date | append/version | eligibility | role population | Required | Do not infer relief role from position alone |
| Birth date / debut | Identity | Stable bio useful for experience cohorts | MLB | people | A | PARTIALLY_STORED | mutable `age`; no birth/debut | Raw/normalized | player bio fields | player | Cold | identity creation/reconcile | people | corrected version | none | age/experience descriptive analysis | Optional | Prefer birth date to age |
| Height / weight | Identity | Listed bio measurements | MLB | people | A | NOT_ACQUIRED | none | Raw | none by default | player | Cold | approved use only | none | replace current | none | mechanics research | Optional | Tier C; avoid collection without use |
| Current MLB team | Assignment | Current projected organization | MLB | people/roster | A | ACQUIRED_AND_STORED | `pitchers.team_*` | Normalized projection | current assignment projection | player | Warm/Hot | roster/transaction | current reconcile | update with event link | roster/team reads | active bullpen | Required | Not historical authority |
| Player-team membership interval | Assignment | Effective membership start/end and roster class | MLB-derived | roster + transactions | A/B | PARTIALLY_STORED | dated snapshots/events only | Canonical | membership interval + observations | player/team/start | Warm | roster/transaction change | exact-date snapshots + tx | close/open intervals with lineage | roster depth | churn, days active | Required | Derive interval only from complete observations |
| Active roster membership | Roster | Observed active list inclusion | MLB | team roster `active` | A | ACQUIRED_AND_STORED | roster snapshots | Raw/normalized | permanent dated observation + interval | team/player/date | Hot/Warm | pregame, tx, final reconcile | roster by date | append correction version | active bullpen | composition history | Required | Absence requires complete roster proof |
| 40-man membership | Roster depth | Observed 40-man inclusion | MLB | team roster `40Man` | A | ACQUIRED_AND_STORED | roster snapshots | Raw/normalized | permanent dated observation + interval | team/player/date | Warm | tx + daily | roster by date | append correction version | depth evidence | reinforcement pool | Required | Not call-up prediction |
| Option/recall/assignment/IL event | Transaction | Official movement event | MLB | `/transactions` | A | ACQUIRED_AND_STORED | `player_transactions` | Raw normalized | permanent event + source observation | tx ID/fallback key | Warm | several daily/event | season windows | version correction, never silent | What Changed/depth | churn, days since activation | Required | Pagination proof needed |
| Transaction description | Transaction | Official textual description | MLB | `/transactions` | A | ACQUIRED_NOT_STORED | transient | Raw | optional source observation/artifact | tx observation | Cold | event acquisition | windows | immutable observation version | none | audit/disambiguation | Optional | Do not publish ungoverned prose |
| Minor-league assignment | Org depth | Official affiliate/team assignment | MLB | rosters/transactions/teams | A | PARTIALLY_STORED | transaction subtype; no full ledger | Raw/canonical | membership observation/interval | player/team/date | Warm/Cold | transaction/daily reconcile | season/date roster | version | limited | depth context | Required for depth phase | Team-level coverage must be proven |
| Minor-league workload | Org depth/workload | Official appearances/pitches/outs/BF at affiliate | MLB | MiLB schedule/boxscore/stats | A | NOT_ACQUIRED | none | Raw/canonical | appearance + optional pitch facts | player/game | Warm/Cold | completed MiLB game for tracked depth | tracked-player seasons | same correction contract | none | observed reinforcement workload | Optional | No availability prediction |
| Game PK | Game identity | Official game identity | MLB | schedule/game feeds | A | ACQUIRED_AND_STORED | many tables | Normalized | canonical game FK | game | Hot | schedule first sight | seasons | alias/resumption linkage | all flows | universal join | Required | Remove duplicate authorship over time |
| Official game date/time/type | Game | Official date, scheduled UTC, game type | MLB | schedule/live | A | ACQUIRED_AND_STORED | scheduled game/observations | Raw normalized | canonical game version + current projection | game/revision | Hot/Warm | schedule changes | seasons | version announced changes | schedule/context | timing/recovery | Required | Prior scheduled times currently lost |
| Home/away teams and venue | Game | Official participants/location | MLB | schedule/live | A | PARTIALLY_STORED | teams stored; venue mostly discarded | Raw normalized | canonical game/team/venue | game | Warm | schedule first sight/change | seasons | version | schedule | travel proxy/time zone | Required teams; venue optional | Actual travel remains unknown |
| Status/finality | Game state | Coded/detailed/abstract state plus usable-final evidence | MLB | schedule/live/boxscore | A | ACQUIRED_AND_STORED | schedule + observation/markers | Raw/canonical | immutable observations + current state | game/observation seq | Hot | adaptive polling | seasons/finals | append transition/correction | sync gates | latency/state machine | Required | Final requires usable boxscore |
| Probable pitchers | Pregame | Official probable starter IDs at observation | MLB | schedule hydration/live | A | PARTIALLY_STORED | CU observation JSON only when live feed supplies | Raw observation | versioned pregame observation | game/team/time | Hot/Warm | schedule refresh/change | limited historical | append changes | limited | pregame rotation context | Required | Do not treat as final starter |
| Doubleheader/series/postponed/suspended/resumed | Schedule | Official calendar/game linkage | MLB | schedule | A | ACQUIRED_AND_STORED | scheduled games + team splits | Raw/canonical/derived | canonical game/version | game/team | Hot/Warm | status change | seasons | append status/link changes | recovery/rotation | burden context | Required | Preserve original and resumed dates |
| Extra innings | Game context | Game exceeded regulation innings | MLB | linescore/PBP/boxscore | A/B | ACQUIRED_AND_STORED | team split derived flag | Derived | derived game fact | game/team | Warm | final | seasons | rebuild/version | rotation context | burden | Required | Rebuildable |
| Off-days/consecutive days/series structure | Recovery | Calendar-derived recovery context | MLB schedule | schedule | B | ACQUIRED_AND_STORED | team splits/snapshots | Derived | versioned derived day/team facts or on read | team/date | Warm | schedule change/final | seasons | recompute affected dates | Team Board | recovery runway | Required | Not medical readiness |
| Time-zone/venue transition | Recovery | Scheduled venue/time-zone change proxy | MLB teams/venues + schedule | schedule/team metadata | B | NOT_ACQUIRED | none | Raw + derived | venue/time-zone observation + derived transition | team/game | Cold/Warm | schedule change | seasons | rebuild | none | descriptive recovery context | Optional | Never call this actual travel |
| Pitcher appearance set/order | Appearance | Official pitchers and order used per team/game | MLB | boxscore | A | ACQUIRED_AND_STORED | GameLog + order transient/contexts | Raw/canonical | canonical appearance with sequence | game/team/pitcher | Hot/Warm | live change/final | seasons | version correction | workload | deployment/role | Required | Order should be first-class |
| Starter flag / games started | Appearance | Official appearance started game | MLB | boxscore/gameLog | A | ACQUIRED_AND_STORED | GameLog GS | Raw/canonical | appearance role fact | appearance | Warm | final | seasons | version | rotation/role | opener/bullpen-game classification | Required | Classify per game |
| Appearance outs/IP | Workload/performance | Official outs and display innings | MLB | boxscore/gameLog | A | ACQUIRED_AND_STORED | GameLog outs/IP | Raw/canonical | canonical integer outs; IP derived | appearance | Hot/Warm | live/final | seasons | version | workload/performance | arbitrary windows | Required | Outs is authority |
| Pitches/strikes/balls | Workload | Official appearance pitch totals | MLB | boxscore/gameLog | A | ACQUIRED_AND_STORED | GameLog | Raw/canonical | appearance totals plus atomic pitches | appearance/pitch | Hot/Warm | live/final | seasons | version/reconcile | workload | strike %, pitch spikes | Required | Null is not zero |
| Batters faced | Workload/performance | Official BF | MLB | boxscore/gameLog | A | ACQUIRED_AND_STORED | GameLog | Raw/canonical | appearance | appearance | Hot/Warm | final | seasons | version | performance | rate denominators | Required | Atomic PA reconciliation |
| H/R/ER/BB/K/HR/HBP/WP | Performance | Official appearance outcomes | MLB | boxscore/gameLog | A | ACQUIRED_AND_STORED | GameLog | Raw/canonical | appearance + PA outcomes | appearance/PA | Warm | final/correction | seasons | version | performance | ERA/WHIP/FIP/rates/windows | Required | Preserve official ER corrections |
| GF/W/L/S/HLD/BS/SVO | Decisions | Official appearance decisions | MLB | boxscore | A | ACQUIRED_AND_STORED | GameLog | Raw/canonical | appearance decisions | appearance | Warm | final/correction | seasons | version | roles/performance | deployment outcomes | Required | Hold and BS were experimentally confirmed |
| Inherited runners / scored | Deployment/performance | Official inherited traffic counts | MLB | boxscore | A | ACQUIRED_AND_STORED | GameLog | Raw/canonical | appearance plus entry runner identities/state | appearance | Warm | final/correction | seasons | version | evidence | difficulty/strand context | Required | Official counts plus PBP reconciliation |
| Entry inning/half/order | Deployment | Exact point reliever entered | MLB | PBP/boxscore order | A/B | PARTIALLY_STORED | PBP enables derivation; context aggregates | Derived canonical | appearance context | appearance | Hot/Warm | pitch change/final | PBP seasons | recompute/version | evidence | role/deployment | Required | First-class, not only evidence JSON |
| Entry score differential | Deployment | Fielding-team lead/tie/deficit on entry | MLB | PBP | B | DERIVED_NOT_PERSISTED | evidence/context only | Derived | appearance context | appearance | Hot/Warm | entry/final | PBP seasons | recompute | entry-band evidence | leverage/role | Required | Direction from fielding team |
| Entry base/out state | Deployment | Occupied bases and outs on entry | MLB | PBP runner state | A/B | PARTIALLY_STORED | outs/events; base state not first-class | Raw/derived | appearance context | appearance | Hot/Warm | entry/final | PBP seasons | recompute | inherited evidence | traffic difficulty | Required | Validate against official IR |
| Exit inning/score/base/out | Deployment | State when pitcher leaves | MLB | PBP | B | DERIVED_NOT_PERSISTED | limited completed context | Derived | appearance context | appearance | Warm | final | PBP seasons | recompute | limited | leads protected/lost, multi-inning | Required | Substitution semantics need proof |
| Save/hold situation at entry | Deployment | Rule-based opportunity context | MLB + rules | boxscore/PBP | A/B | PARTIALLY_STORED | `save_situation`, official SVO | Raw/derived | appearance context + official result | appearance | Warm | final | seasons | reconcile | roles | usage bands | Required | Separate situation from awarded result |
| Leverage index | Deployment | Event importance by win-probability swing | MLB/derived | boxscore/context metrics/PBP | A/B | PARTIALLY_STORED | GameLog nullable LI | Raw/derived | event and appearance LI with formula/source version | PA/appearance | Warm | final | seasons | version | workload/roles | high-leverage use | Optional but high-value | Official availability inconsistent; proof needed |
| Batter handedness / pitcher handedness | Matchup | Sides at pitch/PA | MLB/Savant | PBP/CSV | A | PARTIALLY_STORED | pitcher hand only; pitch matchup discarded | Raw | pitch/PA | pitch/PA | Warm | final Statcast/PBP | seasons | version | none | platoon usage/results | Required | Present in source |
| Batter identity and PA result | Performance/matchup | Opponent and terminal event | MLB/Savant | PBP/CSV | A | PARTIALLY_STORED | pitch batter ID/event type; limited PA row | Raw/canonical | plate appearance | game/at-bat | Warm | final | seasons | version | story evidence | splits, opponent results | Required | Normalize PA separately |
| Pitch sequence/count/result | Pitch | Ordered pitch and before/after count/result | MLB/Savant | PBP/CSV | A | ACQUIRED_AND_STORED | game pitch events | Raw/canonical | canonical pitch + source observations | game/at-bat/event | Warm/Hot | live optional; final reconcile | 2015+ preferred | version | limited | sequencing, swing/whiff/zone | Required | Add before-count/base state |
| Pitch type/name | Pitch | Provider classification | MLB/Savant | PBP/CSV | A | ACQUIRED_AND_STORED | code/description | Raw observation | multi-source observation + canonical current | pitch/source | Warm | final | tracking era | version/reclassify | none | arsenal/usage | Required | Provider classifications can change |
| Release/start/effective velocity | Pitch characteristic | Observed speed and perceived/effective speed | MLB/Savant | PBP/CSV | A | PARTIALLY_STORED | start/end only | Raw | pitch observation | pitch/source | Warm | final Statcast | tracking era | version | none | velo trends/within outing | Required | Effective speed not current |
| Release spin rate/direction/axis/active spin | Pitch characteristic | Spin observations | MLB/Savant | PBP/CSV/leaderboards | A | PARTIALLY_STORED | rate/direction; no axis/active | Raw | pitch observation where atomic | pitch/source | Warm | final Statcast | era-aware | version | none | shape/change | Rate/axis required; active spin unknown | Active-spin atomic proof required |
| Movement | Pitch characteristic | Horizontal/vertical/IVB/gravity/arm-side movement | MLB/Savant | PBP/CSV | A | STORED_BUT_UNUSED | pfx/break fields; no production domain consumer found | Raw | pitch observation with coordinate definition/version | pitch/source | Warm | final | era-aware | version | proof/audit only | pitch shape/change | Required | Coordinate systems must be documented |
| Release position/extension/arm angle | Pitch characteristic | Release point and arm angle | MLB/Savant | PBP/CSV | A | PARTIALLY_STORED | position + extension; no arm angle | Raw | pitch observation | pitch/source | Warm | final | era-aware | version | none | stability/change | Required | Descriptive only |
| Plate location/zone/strike-zone bounds | Pitch location | Crossing point and zone | MLB/Savant | PBP/CSV | A | STORED_BUT_UNUSED | plate x/z, zone, top/bottom; no production domain consumer found | Raw | pitch observation | pitch/source | Warm | final | tracking era | version | proof/audit only | zone/chase/command descriptions | Required | Umpire call distinct from geometric zone |
| Swing/whiff/foul/called strike/ball/BIP | Pitch result | Pitch outcome taxonomy | MLB/Savant | PBP/CSV | A/B | PARTIALLY_STORED | call and booleans | Raw + derived taxonomy | pitch plus versioned classification | pitch | Warm | final | seasons | reclassify rule version | none | whiff/strike/foul rates | Required | Preserve raw description/call |
| Exit velocity/launch angle/distance/BB type | Contact | Tracked batted-ball observation | MLB/Savant | PBP/CSV | A | STORED_BUT_UNUSED | basic hit data; no production domain consumer found | Raw | pitch-linked BBE observation | BBE/source | Warm | final Statcast | 2015+ | version | proof/audit only | contact-quality windows | Required where observed | Null coverage metadata required |
| Launch direction/spray | Contact | Direction of batted ball | Savant/PBP coordinates | CSV | B | UNKNOWN_REQUIRES_PROOF | none | Derived | only after geometry contract | BBE | Cold/Warm | final | 2015+ | formula version | none | platoon/contact shape | Optional | Do not claim explicit field yet |
| Hard-hit / barrel | Contact | Provider/threshold quality classification | Savant | CSV/glossary | A/B | NOT_ACQUIRED | none | Raw components + derived | BBE classification with rule version | BBE | Warm | final | 2015/2016+ | version | none | allowed-contact quality | Required | Hard-hit threshold documented; barrel provider metric preferred |
| xBA/xSLG/xwOBA/wOBA | Expected/result value | Provider expected and actual value per BBE/PA | Savant | CSV | A | NOT_ACQUIRED | none | Raw provider metric | pitch/PA observation with provider version | BBE/PA | Warm | final | 2015+ | version | none | expected-performance windows | Required | Not independently canonical forever; formula can evolve |
| Run value / win expectancy delta | Context/value | Provider change in run/win expectation | Savant/MLB | CSV/context metrics | A/B | NOT_ACQUIRED | none | Raw provider metric | pitch/PA observation + model version | pitch/PA | Warm | final | supported era | version | none | leverage, pitch value | Optional/high-value | Do not mix context-neutral and leveraged |
| Pitch usage/arsenal outcomes | Pitch aggregate | Rates/outcomes by pitch type/window | Derived from pitches | canonical pitch table | B | DERIVED_NOT_PERSISTED | ad hoc reads | Derived | versioned aggregate/cache | pitcher/pitch type/window/as-of | Warm | new final pitches | rebuild all | recompute | none | arsenal change | Required derived | Atomic pitches remain truth |
| Chase/zone/whiff/strike/put-away rates | Pitch aggregate | Defined numerator/denominator rates | Derived/Savant reconciliation | pitches/CSV aggregates | B | DERIVED_NOT_PERSISTED | none | Derived | versioned aggregate/cache | pitcher/window/type | Warm | new pitches | rebuild | recompute | none | command/miss trends | Required derived | Declare taxonomy and denominator |
| Appearance/workload arbitrary windows | Workload | Sums/counts and calendar patterns | Derived | canonical appearances | B | ACQUIRED_AND_STORED | GameLog inputs; selected snapshot/fatigue outputs | Derived | compute or materialize by cohort/version | pitcher/as-of/window | Hot/Warm | appearance/final | rebuild | recompute affected | Team State/Team Board | any future window | Required | Avoid one-column-per-window canonical schema |
| Multi-inning/pitch spike/recent-baseline | Workload | Appearance shape and relative use | Derived | appearances | B | DERIVED_NOT_PERSISTED | snapshot/evidence | Derived | versioned derived facts | pitcher/as-of | Warm | final | rebuild | recompute | roles/stories | usage change | Required derived | Baseline definition versioned |
| Bullpen workload concentration | Team workload | Share/distribution across relievers | Derived | appearances + membership | B | DERIVED_NOT_PERSISTED | evidence/snapshot JSON | Derived | cohort derived fact | team/as-of/window | Warm | final/roster | rebuild | recompute | stories/Team Board | concentration/inequality | Required derived | Membership/population explicit |
| ERA/WHIP/K%/BB%/K-BB%/HR rate/FIP inputs | Performance | Standard rate/count measures | Derived from official facts | appearances/PA | A/B | PARTIALLY_STORED | counts stored; rates in reads | Derived | versioned aggregate/cache | pitcher/team/window | Warm | final | rebuild | recompute | performance reads | arbitrary splits | Required derived | FIP constant season-versioned |
| L/R, home/away, inning, leverage splits | Performance/deployment | Context splits | Derived/official reconciliation | PA/pitch/game | B | PARTIALLY_STORED | some contextual data, no durable split facts | Derived | computed/materialized aggregates | subject/context/window | Warm/Cold | final | PBP/Statcast era | recompute | limited | deep reliever profiles | Optional/high-value | Atomic denominators first |
| Starter pitches/outs/BF/exit state | Rotation transfer | Starter workload and handoff | MLB | boxscore/PBP | A/B | ACQUIRED_AND_STORED | team split + completed context | Raw/derived | canonical appearance/context | team/game | Warm | final | seasons | version/rebuild | rotation context | short starts/transfer | Required | Exit base/out needs extension |
| Bullpen outs/pitches/BF/relievers used | Rotation transfer | Work transferred to relief corps | Derived | official appearances/team totals | B | ACQUIRED_AND_STORED | team game split | Derived | versioned team-game fact | team/game | Warm | final | seasons | recompute | rotation context | rolling burden | Required | Rebuildable |
| Opener/bullpen game classification | Rotation transfer | Descriptive game shape | Derived | appearance order/workload | B | PARTIALLY_STORED | role logic; no canonical classification | Derived | versioned game/team fact | team/game | Warm | final | seasons | recompute | limited | workload transfer | Required derived | Rule must avoid current-role assumptions |
| Source observation ID/fingerprint/schema | Lineage | Immutable acquisition identity and content hash | Every source | all | A/internal | PARTIALLY_STORED | mixed fields/tables | Raw metadata | universal observation ledger | source/domain/key/revision | All | every acquisition | backfill creates observations | append only | ops | audit/replay/corrections | Required | SP-03 core |
| Completeness/coverage record | Lineage | Expected, received, omitted, failed scope | Every source | all | internal | PARTIALLY_STORED | markers/windows/runs | Derived operational fact | domain acquisition manifest | run/domain/window | All | every job | historical audit | append/correct status | publication gates | trustworthy unknowns | Required | Absence requires completeness proof |

## 13. Missing Data Gap Analysis

### P0 foundation gaps

1. **Universal immutable source observation/version identity.** Existing fingerprints are strong but domain-specific and usually retain only current material content.
2. **Canonical game and appearance references.** Today many tables repeat game/team/date fields without formal FKs or a team dimension. A canonical game row plus game-team participation should become identity authority without forcing a risky rewrite of existing rows.
3. **Correction history.** Current counters say that a correction occurred but often cannot reconstruct before/after values.
4. **Acquisition completeness manifests.** Transactions, rosters and Statcast need explicit expected scope, pagination/chunking, record counts, source watermark and omissions.
5. **Statcast atomic enrichment.** No current acquisition exists.

### P1 bullpen-intelligence gaps

1. First-class canonical appearance order and entry/exit/base-out/score context.
2. Plate-appearance facts and handedness context sufficient for splits and inherited-traffic reconstruction.
3. Full historical roster membership/depth intervals, including official minor-league assignment context for tracked 40-man relievers.
4. Pregame probable-pitcher observation history.
5. Derived workload/performance/pitch-characteristic facts with explicit calculation versions and arbitrary-window support.

### P2 enrichment/efficiency gaps

1. Feed diff/patch or timestamp-based adaptive retrieval after empirical proof.
2. Official context/win-probability reconciliation for leverage.
3. Venue/time-zone transition context.
4. Optional tracked-depth minor-league appearances and Statcast where officially available.

## 14. Raw vs Canonical vs Derived Contract

| Layer | Definition | Retention and examples |
|---|---|---|
| **RAW SOURCE OBSERVATION** | Provider response or bounded record exactly as observed, with request identity, time, HTTP/source metadata, schema label and content hash | Retain immutable record-level observations permanently for transactions, rosters, game revisions, appearances, PBP and Statcast. Retain a content-addressed compressed payload artifact only when record-level normalization cannot replay/diagnose the source contract. Do not duplicate identical bodies. |
| **NORMALIZED CANONICAL FACT** | Provider-neutral baseball identity/fact selected under authority and correction rules | Players, games, teams, game-team, appearances, pitches, plate appearances, roster memberships, transactions. Current projection may be mutable only if immutable observation/canonical versions remain. |
| **DERIVED DOMAIN FACT** | Reproducible result from canonical facts and a versioned rule | Workload windows, consecutive-day patterns, deployment bands, pitch usage, contact-quality rates, rotation transfer, role movement. Store inputs/version/as-of/completeness. |
| **SNAPSHOT** | Frozen cohort/as-of representation for historical comparison and publication proof | Team State/history/dashboard/team publication candidates. Never source authority. |
| **READ MODEL / PUBLICATION FIELD** | Consumer-specific field selected from snapshot/derived facts under semantic governance | Team Board, Today, APIs, generated distributions. May be withheld independently. Never drive acquisition scope. |

### Recommended raw boundary

- Retain each normalized atomic Statcast/PBP pitch and its source observation metadata; do not retain a giant duplicate game CSV for every retry.
- Content-address identical whole-response payloads and link observations only where a full payload is needed for replay/audit.
- Store provider-only fields that can change definition (pitch classification, xwOBA, run value) as source observations with provider/schema version, then choose a canonical projection.
- Retain official aggregate lines for reconciliation even when atomic facts can derive rates.
- Never make provider leaderboard aggregates the only historical store.

## 15. Source Authority Matrix

| Domain | Tier A canonical/authoritative | Tier B reliable derived | Tier C optional enrichment | Reject |
|---|---|---|---|---|
| Identity/team | MLB people/teams/rosters | canonical identity resolution | approved public crosswalk | name-only identity guessing |
| Schedule/game | MLB schedule, live feed, boxscore/PBP | calendar density, recovery runway | venue/time-zone proxy | inferred actual travel |
| Appearance/performance | official boxscore/gameLog/PBP | rates/splits/FIP/workload | third-party reconciliation after review | proprietary/unverifiable claims |
| Transactions/depth | MLB transactions and dated rosters | membership intervals when completeness proven | official MiLB workload | speculative call-up/option eligibility prediction |
| Pitch tracking | official Statcast/Savant observations; official MLB PBP | BaseballOS pitch taxonomies/windows | stable public derived leaderboards | scraped pitch labels without provenance |
| Leverage | official event/context metrics if stable | versioned reproducible LI/run-expectancy model | reputable reconciliation | black-box leverage/rank |
| Health/readiness | public official roster status only | observed workload wording | none by default | private medical, injury inference, predicted availability |

Tier A does not mean “schema cannot change.” It means source ownership is canonical. Validation/versioning is still mandatory.

## 16. Data Temperature & Cadence Matrix

| Domain | Temp | Trigger | Routine cadence | Correction cadence | Backfill |
|---|---|---|---|---|---|
| Game state/live appearance/pitch totals | HOT | scheduled start, active state, material feed change | adaptive: pregame 10–15m; live 30–90s only after source-budget proof; dormant/offseason none | final reconciliation plus 2–3 day sweep | game/date replay |
| Final boxscore/appearance set | HOT→WARM | final-pending/final transition | immediate then bounded retries | next morning, 2–7 day rolling correction | season games |
| Final PBP/pitches | WARM | final-and-usable | after final; retry separately from core | 2–7 day plus nightly closure | 2015+ prioritized; earlier PBP as supported |
| Statcast pitches/BBE | WARM | final game / Savant availability | post-final delayed acquisition; nightly closure | 3/7/30-day staged reconcile; offseason season seal | 2015+ reliever pitches, era-aware |
| Active roster | HOT/WARM | transaction or pregame | several daily in-season; daily offseason | next morning and exact-date repair | retained dates/season roster where available |
| 40-man/depth roster | WARM | transaction | daily in-season; lower offseason | daily/weekly closure | season/date snapshots |
| Transactions | WARM | source window | several daily + morning | rolling 7/30-day, offseason full-season seal | season windows with pagination manifests |
| Probable pitchers/pregame context | HOT/WARM | schedule/announcement change | several daily, higher near game | retain all observed revisions | limited historical if available |
| Schedule/recovery | WARM | schedule/status change | morning + postgame + adaptive game state | daily rolling season window | full seasons |
| People/bio/reference | COLD | new identity or change indication | weekly/monthly reconcile | monthly/offseason | all relevant players |
| Derived workload/deployment/Team State | HOT/WARM | canonical mutation | event-driven affected cohort | morning/full nightly reconcile | rebuild from facts |
| Historical aggregates/season seals | COLD | nightly/offseason closure | nightly/weekly | full season seal after corrections | all retained seasons |

## 17. Proposed Storage/Schema Direction

No migrations are authorized in SP-00. Conceptual direction:

### Reuse without forcing new tables

- Keep `pitchers` as current player projection; add stable bio only when justified.
- Keep `game_logs` as the primary current appearance line during migration.
- Keep `scheduled_games`, roster snapshots, transactions, team-game splits, sync runs/jobs/failures, PBP markers, evidence and publication tables.
- Keep bounded JSON for source-specific observation details, work payloads, completeness reasons, snapshot payloads and evidence trace.

### Extend existing tables

- `game_logs`: canonical appearance ID/sequence, source observation/version FK, current-version pointer or companion version table.
- `scheduled_games`: canonical game FK, venue/probable-pitcher current projection, source version pointer.
- `game_pitch_events`: canonical pitch identity, explicit before-state/handedness, source-match status; stop losing corrected same-key values via companion versions.
- `roster_status_snapshots`: observation/version link and completeness-manifest link.
- `player_transactions`: source observation link and retained raw type/description payload where needed.
- operational records: payload schema version and observation/job dependency edges.

### Likely new conceptual entities

| Entity | Purpose and grain |
|---|---|
| `source_acquisition_runs` / manifests | source/domain/request window/chunk/watermark/completeness/HTTP result |
| `source_observations` | immutable content-addressed source record or payload revision |
| `canonical_games` + `game_team_participants` | one game and its official participants/current status pointer |
| `canonical_appearances` + `appearance_versions` | pitcher/team/game/order current fact plus immutable corrections |
| `plate_appearances` / versions | game/at-bat terminal result, matchup and base/out/score context |
| `pitch_observations` or companion source versions | one provider observation per canonical pitch/revision; enrich existing pitch table rather than duplicate it blindly |
| `roster_membership_observations` + intervals | observed inclusion/absence and derived membership interval |
| `player_team_assignment_intervals` | canonical effective organization history when evidence is complete |
| `appearance_context_facts` | entry/exit, inherited traffic, score/base/out, order; rebuildable but shared |
| `derived_fact_versions` | optional generic or domain-specific materializations keyed by rule/as-of/input fingerprint |
| `canonical_correction_events` | before/after canonical version, cause, source revision, affected entities |

### JSON decisions

Keep JSON for sparse provider metadata, reason codes, completeness diagnostics, source-specific payload fragments, and immutable publication/evidence bodies. Normalize identifiers, dates, game/team/player keys, status, counts, pitch measurements, roster membership, transaction type, and any field used for joins/filtering/correction comparisons.

## 18. Historical Retention Contract

### Permanently retain

- canonical player/game/team identities and aliases;
- official appearances, plate appearances, pitches and tracked batted-ball observations;
- roster membership and transaction observations;
- schedule/status/finality revisions material to baseball state;
- source observation fingerprints, schema/version, acquisition manifests and correction lineage;
- canonical fact versions referenced by snapshots/evidence/publications;
- derived snapshots and published artifacts under existing immutability contracts.

### Normalized permanent retention

Pitch/PA/appearance observations, roster/transaction facts and game context should be normalized. Large identical source responses should be content-addressed and deduplicated, not copied per poll.

### Metadata/fingerprint only

Identical no-change polling responses may keep request/result metadata, upstream revision and content hash without another body. Low-value team/venue display payloads may be safely re-fetched if no cited history depends on them.

### Periodic compaction

Operational logs, verbose success diagnostics and superseded cache entries may be compacted after a declared retention period. Compaction must never delete source/canonical versions referenced by a correction, evidence object, snapshot or publication.

### Never retain

Secrets/auth headers, private health information, speculative injury/readiness/intent, unrelated tracking data, arbitrary full MLB data without bullpen relevance, duplicated identical payload bodies, or scraped copyrighted prose without a defined contract.

## 19. Correction & Versioning Contract

Every correctable domain follows:

```text
initial observation
  -> immutable source observation revision
  -> canonical selection/version
  -> derived facts and snapshots cite canonical input versions

later source observation
  -> compare authority + source order + material fingerprint
  -> reject stale/weaker/ambiguous, or accept as correction
  -> create new source and canonical versions
  -> record before/after correction event and affected entities
  -> invalidate/recompute dependent derived facts
  -> create a new snapshot/publication only if its own gate permits
  -> never rewrite a cited historical publication
```

Required version-aware domains: game status/finality, schedule time/linkage, boxscore appearance lines/decisions/ER, PBP/pitches, Statcast classifications/expected metrics, roster membership, transactions, and canonical identity/team assignment.

Provider corrections must not silently alter the meaning of a prior BaseballOS snapshot. A snapshot cites the exact canonical versions it used. A newer corrected snapshot may supersede it for current serving while history preserves both.

Current strengths to reuse include CU source ordering/fingerprints, GameLog correction markers, transaction/roster correction counters, PBP stale/ambiguous/weaker rejection, evidence invalidation, expected-current publication, and immutable publication history. The gap is preservation of before/after source and canonical values.

## 20. Source Failure/Degradation Contract

| Domain | Failure class | Required future behavior |
|---|---|---|
| Game identity/status/finality | CORE / FAIL-CLOSED | Do not assert current/final state; retain last proven state with stale/unknown metadata; no dependent canonical mutation |
| Official appearance set/outs/pitches | CORE / FAIL-CLOSED | Never convert missing to zero; withhold workload/Team State advancement dependent on that game |
| Player identity/team-at-appearance | CORE / FAIL-CLOSED for affected row | Quarantine unresolved appearance; do not infer from current team |
| Active roster completeness | CORE / FAIL-CLOSED for active-bullpen population | Do not treat omitted roster as empty; retain prior proven roster as stale and block current-composition claims |
| Transactions | DEGRADED BUT SERVABLE | Serve last proven roster/Team State with transaction freshness limitation; retry window and preserve completeness gap |
| PBP appearance context | DEGRADED BUT SERVABLE | Core appearance/workload can proceed; entry/inherited/deployment claims withhold |
| Statcast pitch enrichment | OPTIONAL / LAST-KNOWN-GOOD | Core Team State remains; pitch-characteristic facts remain stale/unavailable, never fabricated |
| Minor-league depth workload | OPTIONAL / LAST-KNOWN-GOOD | Active MLB bullpen remains available; organizational depth enrichment withholds |
| Bio/reference | HISTORICAL ONLY / LAST-KNOWN-GOOD | Continue using last canonical identity where unambiguous; queue reconcile |
| Derived recomputation | DEGRADED BUT SERVABLE or FAIL-CLOSED by consumer | Keep prior cited snapshot serving; never publish partially mixed cohort as current |

## 21. Data Volume and PostgreSQL Capacity Analysis

### Assumptions

- MLB regular season: 2,430 games; postseason adds a small margin.
- Approximately 7–9 relief appearances across both teams per game, plus opener/bullpen-game variance: roughly 18,000–23,000 relief appearances/year.
- Official MLB reported more than 725,000 total tracked pitches and 125,000 batted balls in 2023. Assuming relievers throw roughly 40–48%, expect about 290,000–350,000 reliever pitches and 50,000–65,000 reliever batted balls/year.
- 250–400 distinct pitchers may make meaningful MLB relief appearances in a season; the larger player/depth universe is still well under a few thousand identities.
- MLB roster/transaction observations: tens of thousands of membership rows if all 30 teams are observed several times daily with deduplication; official material transactions themselves are only thousands/year.

### Rough annual growth

| Entity | Rows/year | Approximate storage including moderate indexes |
|---|---:|---:|
| Games/team participation/status versions | 5,000–30,000 | <100 MB |
| Relief appearances + versions/context | 20,000–35,000 | 50–200 MB |
| Plate appearances faced by relievers | 80,000–120,000 | 150–500 MB |
| Reliever pitch observations | 300,000–400,000 | 0.5–1.5 GB depending on width/indexes |
| Reliever BBE observations | 50,000–80,000 | mostly pitch-linked; 50–200 MB incremental |
| Roster/membership/transaction observations | 20,000–100,000 after no-change dedupe | 50–300 MB |
| Acquisition/correction/derived manifests | 50,000–250,000 | 100–500 MB |
| Content-addressed compressed source artifacts | workload-dependent | target <1–3 GB/year with identical-body dedupe and selective retention |

A practical planning range is **2–6 GB/year including indexes and selective raw artifacts**, with substantially less if raw whole-game bodies are retained only for changed/final observations. Even a decade remains ordinary PostgreSQL scale.

### Query/index implications

- Partition high-growth pitch/source-observation tables by season or game date only when row counts/maintenance justify it; do not preemptively shard.
- Primary access patterns need `(pitcher_id, game_date)`, `(game_pk, at_bat_index, pitch_number/event_index)`, `(team_id, game_date)`, `(source, natural_key, observed_at/revision)`, and current-version partial indexes.
- Avoid indexing every measurement. Pitch type/date/pitcher and canonical join keys matter; analytical scans can use bounded date partitions/materialized aggregates.
- Use COPY/batched inserts for Statcast backfill, not row-by-row ORM loops.
- Keep JSON GIN indexes rare and query-driven.

**Finding:** PostgreSQL remains the correct store. Kafka, Kubernetes, a data lake, ClickHouse, and microservices are not justified. The harder problems are source correctness, lineage, idempotency, and bounded orchestration—not throughput.

## 22. Backfill Requirements

Backfill is domain- and era-aware:

1. Build canonical game/team identity and season manifests first.
2. Reconcile official final boxscores and appearance lines for all target seasons.
3. Backfill PBP and plate appearances where the official source provides complete usable records.
4. Backfill Statcast reliever pitches from 2015 forward, recording tracking era and null coverage. Validate chunk completeness by date/game/pitcher and compare counts to official game pitching totals.
5. Reconstruct roster/transaction observations only where exact-date or event sources can prove them. Never synthesize full membership history from current rosters.
6. Backfill derived appearance context, workload, performance, rotation transfer and pitch aggregates from canonical versions.
7. Seal each season/domain with expected/received/missing/failed manifests and rerunnable repair lists.

Priority order: current season → prior season → 2015+ Statcast era → older official appearance/PBP history as supported. Backfills run through SP-13 controls, never automatic request-time work and never as an unbounded production startup hook.

## 23. Legacy Sync Inventory

### 23.1 Production and operational entry points

| Entry point | Current purpose / authority | Used? / overlap / risk | SP-01–SP-14 disposition |
|---|---|---|---|
| Render Cron `run_due_sync.py --mode daily` at documented `05 10 UTC` | Primary broad daily canonical + publication authority | Deployed state not repo-proven; overlaps GitHub fallback safely via durable due window/lock | SP-01 registers trigger; SP-12 retains reconciliation; SP-14 retires only after proof |
| Render Cron `--mode morning` at documented `05 14 UTC` | Schedule/Tonight correction | Expected current; narrow | SP-06/SP-12 absorb |
| Render Cron `--mode postgame` at documented `05 02,04,06 UTC` | Final-game reconciliation/publication | Core current authority | SP-07/SP-12 preserve then migrate |
| GitHub `baseballos-sync.yml` `17 10`, `23 14`, `11 2,4,6 UTC` | Delayed fallback plus manual recovery/backfill | Repository-proven scheduled commands; duplicates primary by design, guarded | Retain fallback through SP-14 certification |
| GitHub explicit `backfill` | Manual date-scoped postgame replay | Used operational path; risk of mixed legacy controls | Register under SP-13 |
| GitHub `intraday` mode | Read-only drift audit | Manual only; no canonical/public write | Keep as SP-12/SP-14 diagnostic |
| `baseballos-intraday-repair.yml` | Manual governed repair workflows | Manual-only; can mutate bounded roster/schedule/identity facts depending mode | Consolidate behind SP-13; no retirement in SP-00 |
| `baseballos-production-maintenance.yml` | Manual maintenance/repair | Manual; inspect per incident | SP-13 registry/permissions |
| `baseballos-scheduler-health.yml` | Manual read-only scheduler health | Intentionally not scheduled | SP-14 observability |
| `run_continuous_cycle.py` | One-shot CU chain | Dormant unless externally scheduled/configured; no repository cron | SP-01/SP-04 wrapper; no parallel chain |
| `run_daily_sync.py`, `run_postgame_refresh.py`, schedule-only scripts | Direct CLI service wrappers | Used by workflows/backfills/operators | Normalize commands under SP-01 control plane |
| Incident/audit workflows (appearance team, official pitching line, phantom logs, no-op proof, starter alignment, inherited runners) | Narrow read-only or governed correction proof | Historical and some operational; high inventory complexity | Catalog permissions and migrate valid repairs to SP-13; archive only SP-14 |
| Application startup scheduler (`AUTO_SYNC`) | In-process daily scheduler path exists in code/config | Production expected disabled; actual deployed env not proven here; dual-authority risk if enabled | SP-01 inventory/gate; SP-14 verify disabled/retire |
| Endpoint-triggered bullpen sync | Admin sync route/service entry exists | Auth-protected manual trigger; can overlap without shared control if misused | Route through SP-01 job creation before retirement |
| Request-time Tonight cache miss build | Historically could compute/write on miss; production serving authority guards now prevent browser-driven rebuild | Verify every deployment mode; request-time writes are undesirable | SP-11 removes remaining write-on-read paths after proof |
| One-off scripts under `backend/scripts` | audits, proofs, backfills, repairs, exports | Many are intentionally manual; filenames do not prove live use | SP-13/SP-14 manifest: owner, mode, permissions, last use, replacement |

### 23.2 Negative inventory findings

- No root `render.yaml`; Render dashboard jobs cannot be enumerated solely from repository IaC.
- No queue broker/worker service was identified as current production authority.
- No Statcast/Savant acquisition entry point exists.
- No automatic historical backfill should be inferred from manual workflows.

## 24. SP-01 through SP-14 Implementation Mapping

| Package | Contract scope from SP-00 | Adjustment/recommendation |
|---|---|---|
| SP-01 Sync Control Plane | Domain registry, trigger/cadence policy, run identity, locks, budgets, source failure class, existing command adapters | Explicitly wrap `run_due_sync` and CU execution; inventory admin/startup/manual triggers |
| SP-02 Durable Job Queue | Extend `sync_jobs` into dependency-aware durable work with lease/heartbeat/backoff/payload schema version | Do not introduce a broker until PostgreSQL queue evidence fails |
| SP-03 Source Acquisition / Observations / Fingerprints | Universal immutable source observations, acquisition manifests, request chunks/pagination, content-addressed payload artifacts, schema versions | Broaden scope to include correction-version primitives and source completeness |
| SP-04 Adaptive Game State | Schedule/live-feed adaptive state machine, timestamps/diff-patch evaluation, material observation ledger | Reuse CU-02; add immutable revisions before increasing cadence |
| SP-05 Roster & Transactions | Active/40-man observations, paging/completeness, membership intervals, assignments, optional tracked MiLB depth | Explicitly include historical membership and source-absence semantics |
| SP-06 Pregame Context | Probable-pitcher revisions, schedule/venue/series/recovery context | Preserve observed probable changes; reject actual-travel inference |
| SP-07 Final Game Reconciliation | Official boxscore appearances, decisions, PBP/PA/pitches, starter/bullpen split, final completeness | Include atomic appearance context and coordinate PBP vs Statcast finalization |
| SP-08 Live Game Delta | Live appearance/pitch deltas with bounded poll/diff strategy | Core minimal facts first; do not require Statcast enrichment for live core |
| SP-09 Canonical Mutation & Impact Engine | Authority selection, immutable canonical versions, correction events, affected-entity graph | Reuse CU-01/CU-03; add before/after lineage |
| SP-10 Derived Intelligence & Snapshot Cohort | Arbitrary workload, deployment, performance, pitch characteristics, rotation transfer, roster depth; calculation registry | Broaden beyond current Team State UI while keeping public semantics unchanged |
| SP-11 Atomic Publication & Cache Handoff | Reuse CU-07/per-team immutable publication, eliminate write-on-read paths | Publication fields remain consumers, never acquisition drivers |
| SP-12 Morning Reconciliation & Nightly Historical Closure | Full domain completeness seals, Statcast delayed closure, roster/transaction/schedule correction sweeps | Add domain/season seal manifests and staged correction horizons |
| SP-13 Corrections / Repair / Backfill | Generic repair registry, era-aware backfill, missing-chunk retries, cited-history preservation | Absorb valid one-off repair scripts gradually; preserve governed audit modes |
| SP-14 Observability / Production Certification / Legacy Retirement | Per-domain freshness/completeness/SLOs, source cost, natural production proof, exact legacy inventory/retirement | Require deployed Render inventory and proof before declaring retirement |

No package numbering change is recommended. The material scope adjustments are: SP-03 owns immutable observation/completeness primitives; SP-05 owns membership intervals; SP-07 owns canonical PA/appearance context; SP-10 explicitly covers future-facing derived pitch/performance intelligence; SP-12 seals domain completeness; SP-14 must discover dashboard-managed Render state.

## 25. Explicit Non-Goals

- No new sync pipeline, queue, migration, endpoint, worker, cron or cadence change in SP-00.
- No change to current production sync, finality, workload, rest, Team State, arm reads, What Changed, snapshot or publication behavior.
- No frontend/distribution/public-copy work.
- No predictive availability, manager intent, injury inference, betting, fantasy or medical state.
- No arbitrary full-MLB ingestion unrelated to bullpen intelligence.
- No commitment to an undocumented Savant field or endpoint without empirical proof.
- No distributed-infrastructure adoption without measured PostgreSQL insufficiency.
- No legacy retirement before parity and natural production certification.

## 26. Risks / Unknowns Requiring Future Proof

1. **Savant production contract:** CSV is public and documented at field level, but rate limits, bulk-chunk limits, late-arrival timing, historical correction behavior and schema-change notification are not documented as an SLA. SP-03 must run bounded empirical probes.
2. **Pitch identity matching:** PBP uses at-bat/play-event indices and play IDs; Savant exposes game/at-bat/pitch numbers. A season-scale match-rate proof is required before canonical merge.
3. **Active spin:** useful publicly, but an atomic stable field was not confirmed in the sampled CSV contract.
4. **Launch direction:** derivable candidates exist, but a stable official explicit field/coordinate formula requires proof.
5. **Leverage:** boxscore LI is nullable/inconsistent. Official context metrics/win probability need stability and historical coverage tests; otherwise use a versioned public formula.
6. **Transaction pagination/completeness:** current client does not paginate. Official endpoint exposes limit/filters, but truncation/default-limit behavior must be tested.
7. **Historical roster availability:** exact-date roster endpoints may not reproduce every prior intra-day change. Membership intervals must expose coverage limitations.
8. **Minor-league workload:** endpoint availability is plausible/official, but tracked-player coverage, pitch counts, Statcast availability and correction behavior require a dedicated proof.
9. **Production coverage:** schema capability does not establish that all historical rows are complete. SP-12/SP-14 need measured database census by season/domain.
10. **Render inventory:** dashboard-managed cron/service environment cannot be established from repository state; live read-only inspection is required later.
11. **PBP correction history:** current plate-event replace and same-key pitch update behavior loses prior values. Migration must preserve current readers while adding versions.
12. **Source terms/operational use:** before production-scale Savant backfill, confirm applicable public-use terms, respectful request rates and caching expectations.

## 27. Final Recommended Acquisition Contract

### What BaseballOS acquires

1. Official MLB identities, teams, games, schedules/status, probable pitchers, active and 40-man rosters, transactions and public roster status.
2. Official game appearances and pitching lines for every MLB pitcher, with reliever/starter classification at the appearance grain.
3. Final PBP, plate appearances and pitch events for bullpen-relevant games/appearances.
4. Official Statcast/Savant pitch and BBE observations for MLB relievers, enriched onto canonical pitches after identity proof.
5. Starter and total-team workload needed to quantify rotation-to-bullpen transfer.
6. Optional official MiLB assignment/workload observations for tracked organizational relief depth, only after source proof.

### Grain and retention

- Identity: player/team/game.
- Membership: player/team/roster class/observed time, plus evidence-bounded intervals.
- Transaction: official transaction ID or deterministic source event key.
- Appearance: game/team/pitcher/order.
- Plate appearance: game/at-bat.
- Pitch: game/at-bat/pitch sequence, matched to source play identity where available.
- BBE: pitch/terminal PA.
- Observation: source/domain/natural key/revision/acquired time.

All atomic baseball facts and material versions are permanent. Identical polls are deduplicated by fingerprint. Derived metrics cite rule and input versions. Snapshots/publications cite exact canonical cohorts.

### Frequency and triggers

- HOT source work is state/event adaptive and bounded.
- WARM work runs after final/transaction/roster changes and through daily correction windows.
- COLD work performs nightly/offseason closure and governed backfill.
- Source failure policy is domain-specific; appearance/core roster absence fails closed while Statcast/minor-league enrichment degrades independently.

### Current systems satisfying the contract

The MLB client resilience layer, schedule ingestion, GameLog appearance ledger, roster snapshots, transaction ledger, game-driven ingestion, PBP/pitch foundation, sync metadata/dead letters, CU change/impact/incremental chain, and atomic publication proof all satisfy meaningful portions and should be evolved in place.

### Missing implementation ownership

SP-03 supplies universal observations/completeness; SP-05 membership/depth; SP-06 pregame revisions; SP-07 canonical appearance/PA/final facts; SP-08 live deltas; SP-09 correction-aware canonical versions; SP-10 broader derived intelligence; SP-12 closure; SP-13 backfill/repair; SP-14 deployed certification and retirement.

## 28. SP-00 Acceptance Checklist

- [x] Current bullpen/reliever acquisition endpoints inventoried from executable code.
- [x] Current canonical, derived, snapshot, publication and operational tables censused.
- [x] Retrieved-but-discarded, aggregate-only, JSON, recomputation, overwrite and duplication cases identified.
- [x] Current data flows traced source → normalization → database → derived state → publication.
- [x] Current synchronization entry points inventoried, with deployed Render limitation stated.
- [x] CU-01 through CU-08 overlap assessed for reuse.
- [x] Official MLB Stats API capabilities researched from primary OpenAPI and live read-only samples.
- [x] Official Savant/Statcast atomic and aggregate capabilities researched from primary sources and a live read-only CSV sample.
- [x] Every domain assigned source authority, raw/canonical/derived layer, temperature, trigger, backfill, correction and failure posture.
- [x] Master field/data matrix completed with explicit current-state proof classifications.
- [x] Data scale estimated with assumptions; PostgreSQL affirmed.
- [x] Retention and correction/versioning contracts defined.
- [x] Every implementation gap mapped to SP-01 through SP-14.
- [x] Non-goals preserve backend-only, non-semantic, non-production scope.
- [ ] Production row completeness measured — intentionally deferred; requires read-only production census.
- [ ] Deployed Render dashboard configuration observed — intentionally deferred to authorized live inspection/SP-14.
- [ ] Savant rate/correction/match-rate proof completed — intentionally deferred to SP-03 empirical work.

## Appendix A — External Source Ledger

All sources accessed 2026-09-05.

| Source title | URL | Supports |
|---|---|---|
| MLB Stats API official documentation UI | https://docs.statsapi.mlb.com/ | Official public API documentation authority |
| MLB Stats API OpenAPI document | https://docs.statsapi.mlb.com/openapi.json | Endpoint paths and parameters for teams, people, rosters, schedule, transactions, stats, boxscore, PBP, live feed, metrics and context endpoints |
| MLB Stats API schedule endpoint (experimental observation) | https://statsapi.mlb.com/api/v1/schedule?sportId=1 | Schedule/game/status payload availability; query behavior must still be validated per requested hydration |
| MLB Stats API roster endpoint (experimental observation) | https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=40Man&season=2026 | 40-man roster/person/status payload availability |
| MLB Stats API transaction endpoint (experimental observation) | https://statsapi.mlb.com/api/v1/transactions?startDate=09/01/2026&endDate=09/04/2026&sportId=1 | Public transaction payload availability; pagination completeness remains unproven |
| MLB Stats API sampled game boxscore (experimental observation) | https://statsapi.mlb.com/api/v1/game/823665/boxscore | Official pitcher-line keys including holds, blown saves, inherited runners and appearance counts |
| MLB Stats API sampled live feed (experimental observation) | https://statsapi.mlb.com/api/v1.1/game/823665/feed/live | Pitch event, coordinates, movement, score, matchup and runner structures |
| Baseball Savant Statcast Search CSV documentation | https://baseballsavant.mlb.com/csv-docs | Definitions and names for atomic CSV fields |
| Baseball Savant Statcast Search | https://baseballsavant.mlb.com/statcast_search | Public query surface and aggregate metric/filter availability |
| Baseball Savant CSV query (experimental observation) | https://baseballsavant.mlb.com/statcast_search/csv?all=true&type=pitcher&player_type=pitcher&pitchers_lookup%5B%5D=663542&game_date_gt=2026-08-01&game_date_lt=2026-09-04 | Current atomic CSV header, including effective speed, spin axis, expected metrics, run/win deltas and arm angle |
| MLB Statcast glossary | https://www.mlb.com/glossary/statcast | Official scope, tracking eras, atomic measurements, expected metrics, pitch and BBE scale; cites 725k pitches/125k BBE in 2023 |
| MLB Active Spin glossary | https://www.mlb.com/glossary/statcast/active-spin | Definition and relevance of active spin; does not prove atomic CSV availability |
| MLB Expected wOBA glossary | https://www.mlb.com/glossary/statcast/expected-woba | xwOBA components and pitcher applicability |
| MLB Hold glossary | https://www.mlb.com/glossary/standard-stats/hold | Official hold definition and relation to save opportunities |
| MLB Blown Save glossary | https://www.mlb.com/glossary/standard-stats/blown-save | Official blown-save definition |
| MLB Inherited Runner glossary | https://www.mlb.com/glossary/standard-stats/inherited-runner | Official inherited-runner definition |
| MLB Leverage Index glossary | https://www.mlb.com/glossary/advanced-stats/leverage-index | Meaning and interpretation of LI |
| MLB FIP glossary | https://www.mlb.com/glossary/advanced-stats/fielding-independent-pitching | FIP inputs and season-dependent constant |
| MLB Suspended Game glossary | https://www.mlb.com/glossary/rules/suspended-game | Suspended/resumed game semantics |
| MLB 27th Man glossary | https://www.mlb.com/glossary/transactions/27th-man | Doubleheader/suspended-game roster context and pitcher option-day caveat |

## Appendix B — Repository Evidence Ledger

| Claim | Evidence |
|---|---|
| Only shared baseball HTTP client found is MLB Stats API | `backend/config.py:112`; `backend/services/mlb_api.py:20-231` |
| Current endpoints and parameters | `backend/services/mlb_api.py:478-741` |
| Raw transactions/linescore/PBP/live feed are transient in client contract | `backend/services/mlb_api.py:610-678` |
| GameLog appearance grain, fields and provenance | `backend/models/game_log.py:52-167` |
| Schedule fields and uniqueness | `backend/models/scheduled_game.py:23-80` |
| Roster snapshot fields/history | `backend/models/roster_status_snapshot.py:32-66` |
| Transaction fields, JSON and correction metadata | `backend/models/player_transaction.py:45-127` |
| Team starter/bullpen split and schedule context | `backend/models/team_game_pitching_split.py:63-143` |
| Final PBP event and pitch schemas | `backend/models/play_by_play_foundation.py:38-245` |
| Normalized pitch extraction fields | `backend/services/play_by_play_foundation.py:619-770` |
| PBP event replacement and pitch correction/supersession | `backend/services/play_by_play_foundation.py:594-616`; `backend/services/play_by_play_foundation.py:800-866` |
| Live observation source/fingerprint behavior | `backend/services/game_change_detection.py:33-35`; `backend/services/game_change_detection.py:68-210` |
| Bounded active/correction slate | `backend/services/game_change_detection.py:213-280` |
| Live material observation includes probable pitchers and game status | `backend/services/game_change_detection.py:283-360` |
| Completed-context inputs degrade independently | `backend/services/sync.py:2368-2451` |
| Official boxscore stores holds/BS/inherited traffic when present | `backend/services/sync.py:514-587` |
| Final PBP is nonblocking for core postgame outcome | `backend/services/sync.py:2509-2525` |
| Operational run/job/failure/schedule ledgers | `backend/models/sync_run.py:8-46`; `backend/models/sync_job.py:8-41`; `backend/models/sync_failure.py:18-40`; `backend/models/sync_schedule_attempt.py:9-29` |
| GitHub fallback schedules and commands | `.github/workflows/baseballos-sync.yml:30-40`; `.github/workflows/baseballos-sync.yml:127-324` |
| Continuous execution is mode-gated and one-shot | `backend/services/continuous_execution.py:39-189`; `backend/services/continuous_execution.py:313-458` |

## Appendix C — Status and Decision Vocabulary

### Current-state status

- `ACQUIRED_AND_STORED`: executable source path and durable field/table proven.
- `ACQUIRED_NOT_STORED`: source value/response is read but no durable destination is proven.
- `STORED_BUT_UNUSED`: durable field proven; no material current consumer found.
- `DERIVED_NOT_PERSISTED`: reproducible logic exists but result is transient or publication-only.
- `PARTIALLY_STORED`: some atomic members/coverage/history are retained, others are not.
- `NOT_ACQUIRED`: no source call/field path found.
- `UNKNOWN_REQUIRES_PROOF`: availability or production contract could not be established safely.

### Existing-component disposition

- `REUSE AS-IS`: contract already satisfies the needed responsibility.
- `EXTEND`: retain ownership and add fields/version/completeness.
- `WRAP IN NEW CONTROL PLANE`: preserve baseball logic while replacing trigger/orchestration authority.
- `MIGRATE`: move responsibility after parity proof.
- `DEPRECATE LATER`: keep operational until certified replacement.
- `REPLACE ONLY IF PROVEN NECESSARY`: evidence, not package aesthetics, must justify replacement.

## Appendix D — Named Workflow and CLI Inventory

This appendix prevents broad phrases such as “repair scripts” from hiding an entry point. “Manual” means the checked-in workflow has `workflow_dispatch` and no schedule unless separately stated. Repository presence does not prove recent production use.

### D.1 Checked-in workflows

| Workflow | Trigger | Baseball-data relevance | Classification / future disposition |
|---|---|---|---|
| `baseballos-sync.yml` | Scheduled + manual | Daily, morning, postgame, historical backfill, read-only intraday audit, internal enrichment and downstream proofs | Current repository production/fallback authority; wrap SP-01, retain through SP-14 |
| `baseballos-intraday-repair.yml` | Manual | Governed roster/transaction/schedule/identity/completed-game repair modes | SP-13 registry; preserve until parity |
| `baseballos-production-maintenance.yml` | Manual | Production maintenance and accuracy reconciliation | SP-13 registry; per-mode authority review |
| `baseballos-scheduler-health.yml` | Manual | Read-only delivery/freshness check | SP-14 observability |
| `appearance_team_backfill_2026.yml` | Manual | Historical team-at-appearance correction | SP-13; season-specific legacy |
| `canonical_season_bullpen_aggregation.yml` | Manual | Rebuild/reconcile season bullpen aggregation | SP-10/SP-13; retain until canonical rebuild parity |
| `inherited-runners-authority-diagnostic.yml` | Manual | Read-only source-authority diagnostic | SP-14 diagnostic; no acquisition authority |
| `manual-game-driven-noop-qualification.yml` | Manual | Governed CU no-op write qualification | CU proof-only; archive after SP-09 certification |
| `manual-noop-qualification-candidate-audit.yml` | Manual | Read-only CU candidate audit | SP-14 diagnostic |
| `manual-postgame-publication-incident-audit.yml` | Manual | Read-only/recovery incident proof | SP-13/SP-14 |
| `official_pitching_line_completeness.yml` | Manual | Appearance-line completeness audit | SP-12/SP-14 |
| `official_pitching_line_repair_plan.yml` | Manual | Bounded repair planning | SP-13 |
| `official_pitching_line_repair_apply.yml` | Manual | Governed appearance-line correction | SP-13 |
| `official_pitching_line_repair_closeout.yml` | Manual | Repair verification | SP-13/SP-14 |
| `official_pitching_line_transition_diagnostic.yml` | Manual | Diagnostic for source transition/correction | SP-14 |
| `official_pitching_line_matt_festa_apply.yml` | Manual | One-row historical correction | Incident-specific; archive only after preserved evidence/parity |
| `official-starter-alignment-audit.yml` | Manual | Starter identity/alignment audit | SP-12/SP-14 |
| `phantom_game_log_reconciliation.yml` | Manual | GameLog phantom-row reconciliation | SP-13 |
| `phantom_game_log_guard.yml` | Code event | CI guard against phantom GameLogs | Keep as regression guard; not production sync |
| `unresolved_appearance_team_diagnostic_2026.yml` | Manual | Read-only unresolved team audit | SP-14 |
| `unresolved_appearance_team_repair_2026.yml` | Manual | Governed team-at-appearance repair | SP-13 |
| `team-state-history-export.yml` | Manual | Read-only historical snapshot export | Not acquisition; keep as audit/export |
| `team-state-population-compare.yml` | Manual | Read-only Team State comparison | SP-10/SP-14 proof |
| `baseballos-generated-distribution.yml` | Manual | Static distribution export only | Out of SP-00 acquisition scope; explicitly not a source/sync authority |
| `ci.yml` | Code event + manual | Tests/lints only | Not a production sync entry point |

### D.2 Named executable sync, audit, backfill and repair commands

| Command/script family | Current use | Disposition |
|---|---|---|
| `run_due_sync.py`, `run_daily_sync.py`, `run_postgame_refresh.py` | Primary due-window/direct daily/final orchestration wrappers | SP-01 adapters; retain current service authority during migration |
| `run_continuous_cycle.py` | One-shot, gated CU chain; no checked-in schedule | SP-01/SP-04 wrapper; do not duplicate |
| `run_intraday_reconcile.py`, `run_intraday_repair.py`, `run_intraday_completed_game_repair.py` | Read-only drift audit and explicit governed repairs | SP-12/SP-13 |
| `backfill_pitcher_game_logs.py`, `backfill_game_log_innings_outs.py`, `backfill_games_started.py`, `backfill_completed_game_context.py` | Historical one-domain backfills | Register/version in SP-13; replace only after parity |
| `run_2026_appearance_team_backfill.py`, `run_2026_opening_week_schedule_repair.py`, `run_2026_residual_audit.py`, `run_appearance_team_coverage_audit.py` | Season-specific team/schedule authority correction and audits | Incident legacy; SP-13/SP-14 |
| `run_official_pitching_line_completeness_2026.py`, `run_official_pitching_line_repair_plan_2026.py`, `run_official_pitching_line_repair_apply_2026.py`, `run_official_pitching_line_repair_closeout_2026.py`, `run_official_pitching_line_transition_diagnostic_2026.py`, `run_official_pitching_line_matt_festa_apply_2026.py` | Official-line diagnosis, plan/apply/closeout and one-row repair | Consolidate into SP-13 correction workflow after proof |
| `run_phantom_game_log_reconciliation.py`, `run_unresolved_appearance_team_repair_2026.py` | GameLog/team correction | SP-13 |
| `appearance_ledger_audit.py`, `inspect_gamelog_field_authority.py`, `profile_daily_ingestion_readonly.py`, `sync_trace.py`, `production_accuracy_reconciliation.py`, `run_reconciliation_audit.py` | Read-only or controlled operational diagnostics | SP-14 evidence suite; maintain safe read-only modes |
| `game_driven_ingestion.py`, `run_game_driven_noop_qualification.py`, `run_cu01p_proof.py`, `run_cu04_proof.py`, `run_cu05_proof.py`, `validate_game_driven_shadow_cycle.py` | CU execution/proof tooling | Preserve as SP-09/SP-10 certification until superseded |
| `recalculate_after_games_started_backfill.py`, `recalculate_after_innings_backfill.py` | Follow-on derived recalculation after historical changes | Replace with dependency-driven SP-09/SP-10 invalidation only after parity |

### D.3 Application and read-path entry points

- `backend/app.py:20-72` conditionally creates an in-process APScheduler daily job when `AUTO_SYNC=true`; checked-in production workflows force it false, but deployed environment state requires separate proof.
- `backend/api/bullpen.py:916-1136` exposes the authenticated manual `POST /api/bullpen/sync` path backed by the same sync service.
- `backend/api/bullpen.py:1137-1150` exposes sync status only and is not a writer.
- Production snapshot-serving guards are intended to prevent browser cache misses from becoming production-authoritative rebuilds; SP-11/SP-14 must enumerate and prove every write-on-read branch before retirement.
