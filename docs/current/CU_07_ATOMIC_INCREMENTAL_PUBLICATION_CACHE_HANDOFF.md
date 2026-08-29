# CU-07 — Atomic Incremental Publication & Cache Handoff

## 1. Branch and baseline

- Branch: `feat/atomic-incremental-publication`
- Starting main SHA: `9c32320d563e4a9f595a111f877d00974483f4b2`
- `origin/main` after final fetch: `9c32320d563e4a9f595a111f877d00974483f4b2`
- Main drift: none
- Production activation: none

## 2. Targeted publication architecture audit

### Current publication authority

The broad scheduled authority writes a complete `DashboardSnapshot` and rotates
`is_published` within one database transaction. Team Board and League public
builders read the latest valid `bullpen_dashboard` snapshot. A prior snapshot's
payload and `published_at` remain historical evidence after its current-pointer
flag is removed.

Tonight is independent. `TonightIntelligenceSnapshot` is an exact response JSON
upsert keyed by `(reference_date, snapshot_version)`. Production Tonight reads are
snapshot-only, but that date/version row is not transactionally tied to the
Dashboard pointer. Matchup composition is also not a separately persisted member
of the Dashboard publish transaction.

Therefore current production does **not** expose one atomic primitive spanning
Team Board, League, Matchup, and Tonight. Ordered writes to those existing public
authorities would permit mixed state and were rejected for CU-07.

### Current cache architecture

The primary current caches are database snapshot rows, not Redis/CDN invalidation:

- Dashboard/Team Board: current `DashboardSnapshot`
- Tonight: versioned `TonightIntelligenceSnapshot`
- published Share Artifacts: immutable HTTP-cacheable resources

No governed external targeted cache invalidation hook currently joins the four
CU-06 surfaces. `schedule_tonight_refresh` commits schedule authority before
regenerating Tonight, while dashboard publication runs optional Share Artifact
generation only after the durable snapshot commit. Cache or optional-artifact
failure is not allowed to roll back committed database authority.

### Current scheduling and publication command

Render Cron remains primary and repository documentation records:

| Lane | Schedule (UTC) | Existing command |
|---|---:|---|
| daily | `5 10 * * *` | `run_due_sync.py --mode daily ... --days-back 7 --public-only` |
| postgame | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` |
| morning | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` |

GitHub Actions remains delayed fallback/reconciliation at minutes 17/23/11. No
workflow, Render command, sync service, public route, worker, or polling loop calls
CU-07.

## 3. Chosen isolated publication seam

CU-07 reuses `dashboard_snapshots` under the dedicated snapshot type
`cu07_incremental_proof`. This is a disposable proof authority namespace, not a
second production pointer:

- public readers still request `bullpen_dashboard` or Tonight's existing table;
- the proof row contains the complete Team Board/League/Matchup/Tonight cohort;
- one row is the manifest and one `is_published` transition moves the whole cohort;
- no public route reads the proof type;
- `production_authority_affected` is always false.

This is the narrowest seam that exercises the real database storage and pointer
rotation pattern without changing production serving. No schema was added.

## 4. Publication cohort and identity contracts

For one affected game the required cohort is:

- every requested affected Team Board;
- the same teams' League rows;
- the affected Matchup;
- the affected Tonight entry.

Validation rejects incomplete CU-06 status/parity, failures, parity mismatches,
missing represented date, missing source identity, invalid source ordering,
missing teams, surface-map membership mismatches, and rebuilt-identity mismatches.

Two deterministic SHA-256 identities are used:

1. `semantic_fingerprint` covers the represented date, exact affected team/game
   cohort, contract version, and every semantic surface payload. Known transient
   fields (`generated_at`, `elapsed_ms`, `served_from`) are excluded.
2. `candidate_id` additionally binds the semantic fingerprint to the trusted
   upstream source/canonical identity and explicit upstream order.

Local wall-clock time is neither identity nor ordering evidence. Exact semantic
replay is `no_action` even if observed through a later run identity.

## 5. Lifecycle and transaction boundary

The bounded lifecycle is:

`BUILT/VALIDATED -> STAGED (non-serving) -> CURRENT`

or fail closed as validation-aborted, staged-but-unserved, stale, conflict, or
rolled back.

Read-model building and validation happen before staging. Staging commits a
non-serving row. The final authority transaction contains only:

1. PostgreSQL transaction advisory lock for the proof namespace;
2. current-row and candidate-row locks;
3. expected-current comparison;
4. stale/ambiguous ordering checks;
5. old-current flag removal and candidate-current flag assignment;
6. database commit.

No MLB call, canonical ingestion, derived calculation, CU-06 rebuild, network
cache call, Share Artifact generation, or public read occurs inside that final
transaction.

The `expected_current_id` guard is mandatory. A concurrent candidate that observed
an older current ID conflicts rather than overwriting the winner. PostgreSQL's
transaction advisory lock also serializes the no-current and overlapping-row cases
that a row lock alone cannot cover.

## 6. Cache handoff and retry

Cache authority follows the database commit. The test adapter receives versioned
entries keyed by the committed proof publication ID, for only:

- `team_board:<team>`
- `league_row:<team>`
- `matchup:<gamePk>`
- `tonight:<gamePk>`

Reads first resolve the durable DB current publication ID and accept cache content
only under that exact version. Old cache content therefore cannot masquerade as the
new publication. A cache failure returns `committed_cache_pending`; the durable new
authority remains current and reads fall back to it. `retry_cache_handoff` is
idempotent and creates no second publication.

No live production cache was touched.

## 7. Files changed and schema

- `backend/services/incremental_publication.py`
- `backend/tests/test_incremental_publication.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_07_ATOMIC_INCREMENTAL_PUBLICATION_CACHE_HANDOFF.md`

Schema changes: **none**. Alembic retains one head: `c6d8e1f3a5b7`.

## 8. Proof environment

- SQLite: fast deterministic cohort, validation, rollback, retry, history, and
  chain tests
- Disposable local PostgreSQL 16 container/database: all focused tests including
  transactional visibility and concurrent overlapping commits
- Isolated snapshot type: `cu07_incremental_proof`
- Isolated in-memory versioned cache adapter
- Production pointer/cache/schedules: untouched

## 9. Strongest end-to-end proof

Controlled real-shape fixture:

`CU-02 FINALIZED -> CU-03 authorized plan -> CU-01 -> CU-04 -> CU-05 -> CU-06 -> CU-07`

Observed:

- GameLogs inserted: 4
- pitch events inserted: 4
- affected relievers: 2
- historically owning teams: 2
- CU-04 parity: match
- CU-05 parity: match
- CU-06 parity: match
- CU-07 cohort: two boards, two League rows, one Matchup, one Tonight entry
- authority commit: one proof pointer transition
- cache keys handed off: 6
- production `bullpen_dashboard` current rows created/changed: 0
- downstream/public activation after CU-07: 0

This is controlled real-shape evidence, not production activation.

## 10. Atomicity, failure, and retry proofs

| Case | Result | Current authority after | Partial/mixed state | Cache effect |
|---|---|---|---|---|
| missing Team Board | validation aborted | old/none | none | none |
| missing League row | validation aborted | old/none | none | none |
| missing Matchup | validation aborted | old/none | none | none |
| missing Tonight entry | validation aborted | old/none | none | none |
| CU-06 parity mismatch | validation aborted | old/none | none | none |
| failure after stage | staged, unserved, retryable | old | none | none |
| failure before pointer swap | rollback | old | none | none |
| failure after swap/flush before commit | rollback | old | none | none |
| expected-current changed | conflict | winner | none | none |
| older candidate after newer | stale | newer | none | none |
| same order/different identity | ambiguous conflict | current | none | none |
| duplicate semantic candidate | no action | current | none | none |
| cache handoff failure | committed/cache pending | new | none | fallback to DB |
| cache retry twice | idempotent success | same new ID | none | same 6 keys |

### Mixed-state observation

A PostgreSQL reader was run while the writer had flushed both flag changes but had
not committed. It observed the complete old manifest. After commit it observed the
complete new manifest. It never observed the staged candidate or a surface subset.

### Concurrent candidates

Two threads staged overlapping candidates against the same expected current ID.
The PostgreSQL advisory lock serialized their authority transactions. Exactly one
committed; the other returned `expected_current_mismatch`. Exactly one proof row
remained current.

### Multi-team same-game atomicity

Team A, Team B, their League rows, Matchup, and Tonight live in one manifest row.
Removing any one required member aborts before staging. There is no per-surface
current write to partially succeed.

### Historical immutability and correction

A controlled 18-to-19-pitch semantic correction produced a new candidate and a new
current proof publication. The prior row's payload fingerprint and JSON remained
unchanged; only its current-pointer flag rotated, matching existing snapshot
history semantics. The older candidate could not republish over the correction.

### Unrelated-team sentinel

Team C's production snapshot payload and current flag remained byte-for-byte
unchanged while the A/B proof cohort committed. Team C had no cache key handed off.

### Restart/no-op

Removing the application-scoped session and rereading preserved the committed
candidate and ordering evidence. Exact semantic replay returned `no_action` and
created no row or cache handoff. At the full chain boundary, CU-02 `UNCHANGED`
continues to stop CU-03 through CU-07 before invocation, as established by the
accepted upstream no-op contracts.

## 11. Performance and transaction timing

Representative local two-team/one-game proof timing:

- combined candidate build + validation: 0.093 ms
- stage commit: 1.823 ms
- authority transaction: 3.456 ms
- cache handoff: 0.027 ms
- cohort objects: 6 (two boards, two League rows, Matchup, Tonight)
- targeted cache keys: 6

Times are diagnostic, not a service-level claim. Expensive upstream work remains
outside the authority transaction.

## 12. Validation results

### Focused and chain

- SQLite CU-07: 19 passed, 2 PostgreSQL-only skipped
- PostgreSQL CU-07: 21 passed
- CU-01 through CU-07 focused chain selection: 128 passed, 2 PostgreSQL-only skipped

### Publication/cache/history

- Qualified local publication selection: 215 passed
- An initial unqualified run had 201 passed / 14 failed because `create_app('test')`
  correctly rejected the ambient non-local DB URL. Exact qualified rerun passed.

### Scheduling/governance

- 573 passed
- 1 known Windows-only failure: WSL `bash -n` cannot open a Windows temporary-file
  path. No workflow or schedule assertion failed.

### Other checks

- PostgreSQL rollback, expected-current conflict, overlapping commit, and
  before/after visibility: PASS
- CI shard verification: 399 files, 9,091 tests, assigned exactly once
- Python compilation: PASS
- whitespace/diff check: PASS
- Alembic head: one head, `c6d8e1f3a5b7`
- Full backend diagnostic: NOT RUN (targeted semantic and PostgreSQL proof used)

## 13. Proven claims

- A complete CU-06 cohort can be represented by one deterministic immutable
  manifest.
- PostgreSQL readers observe all-old or all-new proof authority, never mixed.
- Incomplete, mismatched, stale, ambiguous, and conflicting candidates fail closed.
- Overlapping candidates produce exactly one expected-current winner.
- Pre-commit and commit-time failure preserve old current state.
- Cache handoff happens only after durable commit and can be retried idempotently.
- Historical payloads remain immutable.
- Unrelated production snapshots and cache keys remain untouched.
- CU-07 introduces no schema, public route, schedule, worker, polling, frontend, or
  production-authority change.

## 14. Unproven claims and remaining risks

- CU-07 is not production serving authority and has not been run against production.
- Current production Dashboard and Tonight authorities remain independent; moving
  public reads to a shared manifest is intentionally deferred.
- The cache adapter is an isolated contract proof because no equivalent governed
  external targeted cache exists today.
- Naturally concurrent production publication and naturally observed cache outage
  were not exercised.
- Public Pitcher detail remains outside the CU-06/CU-07 cohort. Current Pitcher
  endpoints derive from their existing DB/read seams; no claim is made that CU-07
  atomically republishes them.
- What Changed remains outside the candidate and was not fabricated.
- Full backend suite was not run.

These are activation/integration questions, not failures of the isolated atomic
proof contract.

## 15. Final verdict and next action

**PASS — CU-07 ACCEPTED**

Recommended integration action: with `origin/main` unchanged, perform a separate
safe push/PR task, require hosted PostgreSQL and required CI, audit the final diff,
and merge with a normal merge commit. Do not activate the proof namespace.

Only after CU-07 is safely merged should a separately authorized CU-08 decide
whether and how the shared publication manifest becomes a controlled production
authority and scheduled continuous execution begins.
