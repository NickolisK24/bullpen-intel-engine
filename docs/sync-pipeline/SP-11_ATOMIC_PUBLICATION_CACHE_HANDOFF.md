# SP-11 Atomic Publication & Cache Handoff

## 1. Objective

SP-11 promotes one eligible SP-10 cohort into an immutable publication generation, binds every artifact to that generation, and moves one database current pointer atomically. It does not recompute baseball intelligence or activate the new path in production.

## 2. Existing Publication Infrastructure Reused

The implementation converges on established behavior:

| Existing component | Disposition | SP-11 use |
|---|---|---|
| SP-10 `DerivedIntelligenceCohort` and `DerivedCohortSnapshot` | REUSE AS-IS | Sole candidate intelligence and artifact payloads. |
| CU-07 `incremental_publication` | WRAP/GENERALIZE | Reuses validation-before-publish, expected-current serialization, short pointer transition, semantic identity, and post-commit cache concepts. |
| `DashboardSnapshot` publication | DO NOT TOUCH | Production dashboard authority remains active during coexistence. |
| `TeamPublicPublication` and per-team pointers | MIGRATE LATER | Existing immutable team artifacts and compare-and-set evidence remain parity inputs. |
| immutable `ShareArtifact` records | REUSE AS-IS / LINK LATER | Their frozen source-snapshot semantics remain unchanged; SP-14 owns reader convergence. |
| Today and Tonight database snapshots | MIGRATE LATER | Existing publication identity checks remain; cache-miss live fallbacks are documented legacy paths. |
| legacy postgame/CU publication | DO NOT TOUCH | No retirement or production routing occurs in SP-11. |

SP-11 introduces a common manifest around SP-10 candidate artifacts, not a replacement baseball read-model builder.

## 3. Publication Unit

The unit is exactly one completed, non-live SP-10 cohort. A bounded cohort may replace one artifact and inherit all unaffected artifacts from its predecessor while still producing one coherent generation.

## 4. Manifest Contract

`atomic_publications` records:

* deterministic publication fingerprint and `atomic-publication-v1` schema;
* predecessor publication, cohort, impact plan, correlation, and SyncRun;
* baseball date, authority, source data-through, entity scope, completed/withheld domains;
* method versions and input-manifest fingerprint;
* completeness, lifecycle, timestamps, artifact counts, durations, and validation failure detail.

Source data-through is the newest observed source timestamp in the cohort input manifest, falling back to the cohort baseball-date boundary when no observation timestamp exists. Publish time is never substituted for source data-through.

## 5. Publication Status

Lifecycle values are `preparing`, `ready`, `published`, `failed`, and `superseded`. A row becomes `published` only in the transaction that changes the singleton pointer. The predecessor then becomes `superseded`; its artifacts and lineage remain intact.

## 6. Eligibility

The validator fails closed unless:

* cohort status is `complete`;
* authority is `final`, `corrected_final`, `roster_authoritative`, or `pregame_authoritative`;
* no domain is withheld and at least one domain completed;
* impact plan exists and is not superseded;
* a freshly captured SP-10 input manifest exactly matches the cohort watermark;
* required candidate snapshots exist and have non-empty object payloads;
* the candidate is not older than a current overlapping artifact.

Live, partial, stale, failed, superseded, drifted, or empty-artifact cohorts do not move the pointer.

## 7. Required Domain Matrix

The v1 candidate mapping is centralized:

| Artifact entity | Required completed domain |
|---|---|
| pitcher | `pitcher_snapshot` |
| team | `team_snapshot` |
| game | `game_context` |

Every affected entity for a completed required domain must have its candidate snapshot. Missing optional domains are not serialized as zero. SP-14 may extend the matrix after parity certification.

## 8. Artifact Model

`atomic_publication_artifacts` identifies `(publication, artifact type, entity type, entity key)` and records schema, payload fingerprint, and source cohort. A newly created artifact references its immutable `DerivedCohortSnapshot`. An inherited artifact references the predecessor artifact. Exactly one source reference is required.

Payload fingerprints are deterministic SHA-256 digests of canonical JSON. Artifact reads revalidate that the resolved candidate payload still matches the stored fingerprint.

## 9. Snapshot Promotion

Promotion creates references; it does not rewrite or copy SP-10 payloads. Candidate snapshots remain cohort-bound and immutable in meaning. Existing Dashboard, Tonight, Today, team-publication, and share-artifact records are not modified.

## 10. Generation / Inheritance Model

SP-11 uses generation with predecessor inheritance. New artifacts replace matching keys. Every unaffected predecessor artifact receives a generation-local association pointing to its prior artifact. Thus a one-pitcher correction stays bounded while a reader still resolves one complete publication ID.

Created versus inherited counts are recorded on the manifest, and every artifact retains its source cohort.

## 11. Current Pointer

`atomic_publication_current` is a guarded singleton row (`singleton_id = 1`). PostgreSQL publication takes one transaction-scoped advisory lock and a row lock on the pointer. The pointer changes only after eligibility, artifact, lineage, and watermark validation have succeeded.

The database pointer is the authoritative publication state. No environment variable, cache entry, or independently selected latest row is authority.

## 12. Atomicity

Candidate preparation is computed before the publication lock. Under the short locked transaction SP-11 revalidates the cohort, persists the manifest and artifact associations, changes the pointer, marks lifecycle state, and records cache-handoff intent. A failure before commit leaves the prior pointer current and no partial generation visible.

External cache calls never occur while the database transaction is locked.

## 13. Publication Ordering

For overlapping artifact keys, a cohort with an older durable cohort ID cannot replace an artifact sourced from a newer cohort. Unrelated roster, pregame, and final scopes may still publish by inheriting each other’s unaffected artifacts. Corrected-final cohorts create a new generation and predecessor link.

Eligibility and the input watermark are checked again immediately before pointer transition, so a superseded or drifted candidate cannot publish late.

## 14. Final / Corrected / Roster / Pregame Rules

* `final`: may promote final cohort snapshots supplied by SP-10.
* `corrected_final`: creates a successor generation and replaces only affected keys.
* `roster_authoritative`: promotes only SP-10 artifacts present for its requested scope; unrelated final/game artifacts inherit.
* `pregame_authoritative`: promotes game-context artifacts; unrelated bullpen artifacts inherit.
* `live`: rejected in v1 and remains internal.

SP-11 never derives or widens those scopes.

## 15. Read Consistency

`read_current_publication_bundle()` resolves the singleton pointer once, loads only artifact associations bearing that publication ID, follows inherited references to immutable SP-10 snapshots, and stamps every returned artifact with the same publication ID. The new path never performs independent `latest` selection per surface.

Consumers should resolve the publication once per request and pass that identity through all reads. If current artifact validation fails, the helper serves the intact predecessor as one degraded generation and identifies both the fallback reason and rejected current publication. It never computes or mixes latest rows. Existing public endpoints are not switched in this package.

## 16. Cache Handoff

`atomic_publication_cache_handoffs` records `pending`, `complete`, `retry_wait`, or `not_configured`, publication-versioned keys, attempts, errors, and completion time. When an adapter is configured, pointer commit enqueues one `handoff_publication_cache` job deduped by publication fingerprint. The adapter receives the committed publication bundle after the database transaction.

The repository currently uses database snapshot caches and has no common external invalidation adapter. Dormant SP-11 therefore records `not_configured` by default rather than introducing Redis or CDN infrastructure.

## 17. Cache Failure Recovery

Cache failure updates only the handoff record and allows SP-02 retry. The committed publication stays current. Retrying the same handoff reuses the same publication and versioned keys; it never creates another publication. V1 does not cache the current pointer, so every authoritative generation selection falls back to the database singleton and a late cache retry cannot regress it.

## 18. Idempotence

`cohort_id` and publication fingerprint are unique. An already published cohort returns its existing manifest. Artifact keys are unique within a publication, cache handoff is unique per publication, and cache work uses SP-02 active dedupe.

## 19. Crash Recovery

* Before pointer commit: the transaction rolls back; the prior generation remains current.
* Immediately after commit: a publication-job retry finds the existing publication and returns it.
* During cache work: the publication remains authoritative and the cache job retries independently.

No recovery path recomputes intelligence.

## 20. Concurrency / Fencing

The advisory lock serializes generation transitions without serializing SP-10 derivation. Row locking protects the singleton pointer. SP-02 claim-token heartbeats fence the publication worker before preparation and immediately before transition. Database uniqueness converges duplicate cohort attempts. A stale worker cannot pass the final fence, move the pointer, or enqueue cache work.

## 21. Legacy Coexistence

Production remains on existing DashboardSnapshot, per-team publication, Today, Tonight, share-artifact, daily, postgame, and CU paths. SP-11 adds a dormant publication substrate only. No existing GET handler resolves `atomic_publication_current`, and no migration initializes its pointer.

Remaining SP-14 retirement work includes Today/Tonight cache-miss live builders, DashboardSnapshot `is_published` selection, per-team pointers, share/preview linkage, and any independently resolved latest reads. Those must move only after natural parity and mixed-generation certification.

## 22. Parity

SP-11 does not reshape candidate payloads: artifact payloads are exact SP-10 `DerivedCohortSnapshot` objects. Tests verify bounded final/correction, roster-like team, and pregame game artifact promotion; inheritance preserves unrelated content byte-for-byte. Existing CU-07 and team-publication test suites remain the semantic and transactional parity baseline. Full production reader parity remains an SP-14 gate because this package intentionally does not activate readers.

## 23. Database / Index Design

Migration `e3f6a9b2d5c8` is additive and creates:

* `atomic_publications`;
* `atomic_publication_artifacts`;
* `atomic_publication_current`;
* `atomic_publication_cache_handoffs`.

Indexes support publication date/status, authority/status, correlation, artifact generation/entity lookup, and retryable cache handoffs. JSON payload columns are not indexed. No existing public rows are rewritten, no historical publication is guessed, and downgrade removes only SP-11 tables.

## 24. Explicit Non-Goals

SP-11 does not compute workload, Arm Read, Team State, roles, performance, snapshots, What Changed, or any other baseball intelligence. It does not change public APIs, frontend code, production schedules, scheduler cadence, acquisition, caches/CDNs, deployment, or legacy serving authority.

## 25. SP-12 / SP-14 Handoff

SP-12 can call `publish_derived_cohort` for one eligible morning/nightly cohort; it must not bypass eligibility or pointer locking. SP-14 must certify artifact parity, request-level single-generation reads, cache convergence, naturally produced cohorts, and each legacy-path retirement before production activation.

## 26. Acceptance Checklist

* [x] One eligible cohort maps to one immutable publication manifest.
* [x] Fingerprint, schema, predecessor, source data-through, methods, and watermark are durable.
* [x] Candidate snapshots are referenced without recomputation or payload copying.
* [x] Unaffected artifacts inherit under one new generation.
* [x] One guarded database pointer changes atomically.
* [x] New-path reads resolve one publication generation.
* [x] Live, partial, stale, superseded, drifted, and malformed candidates fail closed.
* [x] Older overlapping work cannot regress a newer artifact.
* [x] Publication and cache handoff are independently recoverable and idempotent.
* [x] SP-02 fencing and PostgreSQL locks protect concurrent publication.
* [x] Migration is additive and initializes no production pointer.
* [x] Legacy publication and public readers remain unchanged for SP-14 certification.
* [x] No intelligence, scheduler, frontend, or production activation change is included.
