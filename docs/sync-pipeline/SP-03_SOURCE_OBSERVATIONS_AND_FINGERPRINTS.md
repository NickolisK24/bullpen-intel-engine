# SP-03 Source Observations and Fingerprints

## 1. Objective

SP-03 establishes the durable evidence boundary between an external baseball source and later canonical mutation. A successful fetch can now identify the logical request, preserve a versioned observation, distinguish meaningful change from replay, state completeness, retain a deduplicated payload when appropriate, and link the evidence to the `SyncRun` and `SyncJob` that produced it.

This package does not activate new sources, change fetch cadence, interpret baseball impact, or alter publication semantics.

## 2. Existing Infrastructure Reused

The implementation converges with existing infrastructure instead of replacing it:

- `SourceDomain` from SP-01 remains the domain vocabulary.
- `SyncRun` remains the logical-operation envelope; `SyncJob` remains the executable-work envelope.
- `game_change_detection.py` continues to own CU live-feed material normalization, source-order acceptance, finality transitions, and affected-entity detection.
- `GameObservationState` remains the mutable pointer to the currently accepted live-game observation. It now points to the immutable evidence version from which that state came.
- CU work obligations remain keyed to their established accepted observation fingerprint and revision. They are not migrated in SP-03.
- `mlb_api.py` retains its HTTP timeout, retry, jitter, and metric behavior. The source-evidence service does not perform HTTP retries.
- Existing transaction correction metadata, final PBP correction structures, canonical rows, failures, and publication fingerprints remain intact.

Reuse disposition:

| Existing concept | SP-03 disposition |
|---|---|
| CU material live-feed fingerprint | REUSE AS-IS and verify parity with the generic v1 fingerprint |
| `GameObservationState` accepted-current pointer | EXTEND with `source_observation_id` |
| CU work obligations/checkpoints | DO NOT TOUCH; migrate only if later orchestration proves necessary |
| SP-01 `SourceDomain`, `SyncRun` | REUSE AS-IS |
| SP-02 `SyncJob` and job attempts | REUSE AS-IS; source fetch attempts remain a separate concern |
| Schedule and transaction canonical stores | EXTEND with provenance pointers only |
| Final PBP correction/supersession | DO NOT TOUCH; later source-path migration |
| Publication/cache fingerprints | DO NOT TOUCH; they identify products, not provider observations |

## 3. Source Observation Definition

A source observation is an immutable material version of what one provider returned for one stable source subject. It records source evidence only. It does not claim that canonical baseball facts changed or decide which teams, pitchers, snapshots, or publications are affected.

One source fetch creates exactly one `SourceFetchAttempt`. A successful complete fetch may create a new `SourceObservation`, or may link the attempt to an existing observation when content is unchanged. A failed fetch creates no observation.

## 4. Provider / Domain Model

Provider and domain are separate controlled values:

- Providers: `mlb_stats_api`, `baseball_savant`.
- Domains: the SP-01 `SourceDomain` vocabulary, including `schedule`, `roster`, `transactions`, `live_feed`, `boxscore`, `play_by_play`, and `statcast`.

Only MLB Stats API paths are integrated in SP-03. `baseball_savant` is representational readiness, not activated acquisition. New providers require an explicit governed change; they are not free-text additions.

## 5. Source Subject Identity

`SourceSubject` is the stable logical request target. Its SHA-256 `identity_key` covers:

- provider;
- source domain;
- endpoint or dataset contract;
- subject type and subject key;
- normalized request identity;
- baseball date or requested date range.

Supported subject types are `league`, `baseball_date`, `date_range`, `game`, `team`, `player`, `pitcher`, and `source_query`. Examples are one MLB live feed for one game, one schedule date range, and one transaction date range. Observation version is deliberately absent from subject identity.

## 6. Request Identity

`build_source_identity()` canonicalizes request parameters using sorted object keys, compact JSON encoding, ISO dates/times, and an explicit request schema version. Equivalent object-key ordering produces the same `request_identity`; meaningful parameter or sequence changes do not.

The current request identity contract is `request-json-sha256-v1`. Future request-schema evolution must increment `request_schema_version` or introduce a new identity algorithm version rather than reinterpret historical identity.

## 7. Observation Version Model

Versions are monotonically numbered within a subject. A first authoritative response creates V1. A different later authoritative response creates V2 and points `predecessor_observation_id` to the previously authoritative version. All older rows remain present. A later return to an older content fingerprint still creates a new version because it is a new transition in source history.

The database enforces unique `(source_subject_id, version_number)` and a unique transition `dedupe_key`. PostgreSQL writers lock the subject row before comparing or advancing versions. This serializes versions for one subject while allowing unrelated subjects to proceed concurrently.

`source_updated_at`, `source_revision`, and `source_etag` are nullable because not every provider exposes them. They never replace BaseballOS observation time.

## 8. Fingerprint Contract

`source-json-sha256-v1` is SHA-256 over deterministic compact JSON:

- object keys are sorted recursively;
- dates and datetimes are normalized deterministically;
- JSON whitespace and input object ordering are irrelevant;
- sequence order remains meaningful unless a source adapter explicitly declares a record collection order-insensitive;
- volatile transport metadata is excluded by the adapter's material payload.

Schedule and transaction adapters sort normalized endpoint records before fingerprinting because provider record order is not part of their meaning. Live feed fingerprints the already-established CU material observation. SP-03 asserts that the generic fingerprint equals the existing CU fingerprint so the same live observation cannot acquire two meanings.

## 9. Fingerprint Versioning

Every observation stores `fingerprint_algorithm` and `fingerprint_version`. A future normalization change must introduce a new version. Matching content under a different fingerprint version is not treated as proof of unchanged content by the v1 comparison contract. This separates an algorithm migration from a provider correction.

## 10. Completeness Contract

Completeness values are:

| Value | Meaning | Authoritative current version? |
|---|---|---|
| `complete` | Adapter has affirmative evidence that the requested response is complete | Yes |
| `partial` | Some requested source evidence is present, but coverage is incomplete | No |
| `unknown` | A response exists, but the adapter cannot prove completeness | No |
| `failed` | External request failed; fetch-attempt-only state | No observation is created |

HTTP 200 alone is not completeness proof. Adapters must evaluate response shape, pagination, truncation, and requested coverage. Partial/unknown observations are durable evidence but never replace `latest_authoritative_observation()`.

## 11. Empty-Valid Semantics

`empty_valid` requires `completeness=complete` and `record_count=0`. It is a successful authoritative observation, not source failure. A transaction window with no transactions and a schedule range with no games can therefore be proven complete and empty. Repeating identical empty evidence is `unchanged` and does not create another version.

## 12. Raw Payload Retention

SP-03 uses `SourcePayloadArtifact` for optional content-addressed JSON retention. The artifact key is content hash plus payload schema version plus payload kind. Identical retained payloads are stored once even when referenced by different subjects or observations.

The integrated paths retain normalized, material JSON:

- live feed: the bounded CU material observation, not the giant transport payload;
- schedule: returned game records for the bounded request;
- transactions: returned normalized transaction records for the bounded request.

This is not a mandate to retain every giant endpoint response. Future boxscore/PBP adapters should select replay-useful payload boundaries. Future Statcast ingestion should normally retain normalized atomic pitch/batted-ball rows and observation metadata rather than repeated season-sized JSON artifacts. `retain_payload=False` supports metadata-only observations where refetch and normalized atomic retention are sufficient.

Permanently retained: subject/version identity, fingerprints, lineage, completeness, source timestamps/revisions, execution links, attempts, and retained artifact references. Safely discarded: duplicate artifact copies, volatile transport headers without audit value, retry sleep detail already represented by the MLB client, and private or unrelated data.

## 13. Fetch Attempt Contract

`SourceFetchAttempt` is compact request evidence, distinct from `SyncJobAttempt`. It records:

- subject and produced/reused observation;
- nullable run and job IDs;
- status, outcome, and completeness;
- started/completed timestamps and duration;
- HTTP status and HTTP-layer retry count when supplied;
- response bytes and record count when known;
- error class/message on failure.

Outcomes are `new`, `unchanged`, `changed`, `corrected`, `partial`, `empty_valid`, and `failed`. Attempt statuses are `succeeded`, `partial`, and `failed`. `unchanged` is successful. HTTP retries remain inside the MLB client; job retries remain SP-02 work.

## 14. Correction / Predecessor Lineage

For one subject:

```text
V1 complete
  -> later materially different complete response
V2 complete, predecessor=V1, outcome=changed or corrected
```

`corrected` is an adapter-supplied source-context label for an accepted historical/final revision; otherwise a different fingerprint is `changed`. Both retain V1. SP-03 does not decide whether V2 should mutate canonical records or republish history. SP-09 and SP-13 consume the evidence and apply governed impact/correction policy.

Partial evidence may point to the latest authoritative predecessor but does not supersede it as current authority.

## 15. Concurrency Contract

Recording is transactional. The service:

1. creates or finds the stable subject under database uniqueness;
2. locks that subject row with `SELECT ... FOR UPDATE`;
3. reads the latest authoritative observation;
4. reuses identical complete content or computes the next version;
5. creates/reuses a content-addressed artifact;
6. inserts one database-deduplicated transition and one fetch attempt.

PostgreSQL tests prove concurrent first writes converge on one V1 and two attempts, and concurrent changed writes converge on one V2 pointing to preserved V1. The subject lock is intentionally per source subject; unrelated source work is not globally serialized.

## 16. Run / Job Linkage

Observations and fetch attempts have nullable `sync_run_id` and `sync_job_id`. Identity is independent of execution, so manual and historical observations do not require a synthetic job. When both exist, the links show exactly which logical operation and executable unit observed the source version.

The evidence service never finalizes a run or changes job lifecycle. A failed fetch attempt does not itself decide a `SyncRun` result or a `SyncJob` retry. Those decisions remain with orchestration and SP-02.

## 17. Representative Integrations

Three existing MLB Stats API paths prove the abstraction without rerouting scheduling:

1. **CU live feed** — accepted first, unchanged, changed, final, and correction observations are recorded from the existing material CU projection. `GameObservationState.source_observation_id` points at the immutable accepted version. Existing source ordering and work-obligation behavior are unchanged.
2. **Schedule range ingestion** — each existing `ingest_schedule()` fetch records complete/empty/failed attempt evidence. Created or updated `ScheduledGame` rows point to the source observation. The canonical upsert behavior is unchanged.
3. **Transaction range ingestion** — each existing `sync_transactions()` fetch records complete, empty-valid, partial/unknown-shape, or failed evidence. `PlayerTransactionSyncWindow` points to the response observation. Existing transaction correction, readiness, and dead-letter behavior remains authoritative.

These are wrappers around existing fetch points. They introduce no new endpoint calls and no new invocation path.

## 18. Existing Source Paths Deferred

| Source path | Deferred owner / reason |
|---|---|
| Adaptive schedule/game-state polling | SP-04; cadence and state machine |
| Roster and 40-man observations | SP-05; roster membership contract |
| Pregame/probable-starter context | SP-06 |
| Final boxscore and final PBP reconciliation | SP-07 |
| Live delta expansion beyond current CU material observation | SP-08 |
| Source-to-canonical impact and derived-from linkage | SP-09 |
| Statcast/Savant acquisition and atomic pitch storage | Later governed acquisition package; SP-03 only provides identity/evidence primitives |
| Morning/nightly wide reconciliation | SP-12 |
| Historical correction repair/backfill | SP-13 |
| Source-health dashboards, alerts, retention operations | SP-14 |

Existing PBP supersession, transaction correction rows, roster provenance, GameLog correction behavior, publication digests, and cache fingerprints remain domain-local until their owning package can migrate them without semantic risk.

## 19. Database / Index Design

Migration `d7a3e9c1f5b2` is additive and creates:

- `source_subjects` — stable provider/domain/request identity;
- `source_payload_artifacts` — deduplicated retained JSON;
- `source_observations` — immutable content versions and predecessor lineage;
- `source_fetch_attempts` — one row per external request outcome.

It adds nullable, `ON DELETE SET NULL` evidence pointers to `game_observation_states`, `scheduled_games`, and `player_transaction_sync_windows`. Existing rows require no guessed backfill and remain valid with null pointers. Downgrade removes only the additive pointers/tables.

Indexes support provider/domain and entity subject lookup, baseball date, request identity, latest/authoritative subject versions, fingerprint, outcome/time, predecessor, run/job, and fetch status/time queries. JSON payloads are deliberately not indexed. Subject and artifact deletion is restricted while evidence refers to them; deleting a predecessor or canonical provenance pointer sets nullable links where configured rather than cascading observation deletion.

## 20. Explicit Non-Goals

SP-03 does not:

- add an MLB or Savant endpoint;
- backfill historical source observations;
- add pitch-level tables or broad Statcast ingestion;
- change source polling, Render, GitHub Actions, or worker activation;
- replace the MLB client's HTTP retry policy;
- route production work through a new scheduler or queue path;
- determine canonical mutations or affected entities;
- change workload, Team State, arm reads, roles, performance, What Changed, publication, API, or frontend semantics;
- migrate every existing fingerprint or source path.

## 21. SP-04 Handoff

SP-04 can use the service boundary as follows:

```text
fetch schedule/game state
  -> build_source_identity(...)
  -> record_source_observation(...)
  -> outcome=unchanged: no state-change work
  -> outcome=new/changed/corrected: emit bounded game-state work
  -> completeness=partial/unknown: preserve evidence, do not assert full authority
  -> fetch failure: record_source_fetch_failure(...), preserve last known-good
```

SP-04 should pass its `SyncRun`/`SyncJob` IDs, keep request parameters explicit, define domain-specific completeness proof, and use the returned observation ID as the source-version reference in downstream job payload/dedupe identity. It must not treat a successful fetch as proof of source change.

## 22. Acceptance Checklist

- [x] One canonical source-observation service and schema exist.
- [x] SP-01 domain/run and SP-02 job vocabulary are reused.
- [x] Stable provider/domain/subject/request identity is deterministic.
- [x] Fingerprints are deterministic and explicitly versioned.
- [x] Identical complete content creates no new version.
- [x] Changed/corrected content creates a linked immutable version.
- [x] Previous versions are preserved, including A-to-B-to-A history.
- [x] Completeness and empty-valid semantics are explicit.
- [x] Partial/unknown evidence does not replace complete authority.
- [x] Failed fetches create attempts, not fake empty observations.
- [x] Retained JSON is content-addressed and deduplicated.
- [x] Run/job linkage is nullable and lifecycle-neutral.
- [x] Live feed, schedule, and transactions prove bounded integration.
- [x] PostgreSQL concurrent identical and changed writes are proven.
- [x] Migration upgrade/downgrade preserves existing linked rows.
- [x] No scheduler, endpoint, cadence, baseball, publication, API, or frontend semantic change is included.
