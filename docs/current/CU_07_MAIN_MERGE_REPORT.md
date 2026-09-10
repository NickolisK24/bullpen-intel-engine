# CU-07 Main Merge Report

## Repository identity

- Feature branch: `feat/atomic-incremental-publication`
- Accepted CU-07 commit: `0914a6463f55f7ed6002276f76579f852b2ce36b`
- Pre-push `origin/main`: `9c32320d563e4a9f595a111f877d00974483f4b2`
- Upstream drift before push: none (`0 behind / 1 ahead`)
- Pull request: [#775](https://github.com/NickolisK24/bullpen-intel-engine/pull/775)
- Pull request title: `feat: add atomic incremental publication proof path`

The accepted commit remained the feature HEAD at initial push and was pushed
without force, rebase, squash, or history rewrite. The only later feature-branch
change is this merge report. The unrelated untracked
`BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` remained untouched.

## Final local validation

### PostgreSQL atomicity

A disposable local PostgreSQL 16 database ran:

`tests/test_schedule_tonight_refresh_postgres.py tests/test_incremental_publication.py`

Result: **32 passed**.

This selection proved:

- complete old state visible before commit;
- staged candidate invisible;
- complete new state visible after commit;
- mixed-state reads: zero;
- failed transaction preserves old current state;
- overlapping candidates produce one expected-current winner;
- stale and expected-current conflicts fail closed;
- cache handoff follows durable commit;
- cache retry is idempotent.

### Focused and regression selections

- CU-01 through CU-07 focused chain: **128 passed, 2 PostgreSQL-only skipped**
- final publication/history sanity selection: **140 passed**
- scheduling/governance: **573 passed, 1 known Windows `bash -n` path case deselected**
- CI shard verification: **399 files / 9,091 tests, assigned exactly once**
- Python compilation: **PASS**
- whitespace/diff checks: **PASS**
- Alembic graph: **PASS**, one head `c6d8e1f3a5b7`
- full backend suite: **NOT RUN**

The original accepted publication/cache/history proof remains **215 passed**.

## Authority and namespace audits

### Production versus proof authority

Production publication continues to use the existing `bullpen_dashboard`
`DashboardSnapshot` authority and the existing date/version-keyed Tonight snapshot
path. CU-07 uses only `cu07_incremental_proof`.

Required identity separation is therefore proven:

`production publication authority != CU-07 proof publication authority`

Repository search found `cu07_incremental_proof` only in the isolated CU-07 service,
its tests, and CU-07 documentation. It is absent from public APIs, frontend code,
Render commands, GitHub schedules, sync commands, and production cache defaults.

### Expected-current and concurrency

The final commit requires `expected_current_id`. Mismatch returns conflict without
authority mutation. PostgreSQL transactions take the CU-07 proof-scoped advisory
lock before current/candidate row locks. Two overlapping candidates were executed
concurrently: exactly one committed and one conflicted.

The lock is intentionally one proof-authority lock. CU-07 introduces no application-
wide or distributed lock and does not change existing production writer locks.

### Transaction boundary

Candidate construction, CU-01 through CU-06 work, MLB acquisition, and cache work
remain outside the final transaction. The authority transaction performs only:

1. proof-scoped lock;
2. current and candidate row validation;
3. expected-current and ordering checks;
4. atomic pointer rotation;
5. commit.

### Cache ordering and namespace safety

Cache handoff occurs only after the database commit. The proof cache adapter is
explicitly supplied, publication-ID aware, and has no production default. Cache
failure returns a retry-required result while reads fall back to committed database
authority. Retry is idempotent and unrelated cache keys remain untouched.

No live cache adapter, purge, or invalidation was invoked.

### Historical immutability and unrelated entities

Corrections create a new proof publication. Prior payload JSON remains unchanged;
only its current-pointer flag rotates under the existing snapshot pattern. The
historical payload fingerprint remained stable in failure, retry, correction, and
stale-candidate tests.

The unrelated Team C production snapshot and current flag remained unchanged. No
Team C cache key was handed off.

### No-op and retry

- identical semantic candidate: no new authority transition;
- repeated accepted candidate: no duplicate publication;
- failed staged candidate: unserved and retryable;
- cache retry: same publication ID and same bounded keys;
- stale candidate: cannot overwrite current.

## Final diff audit

The PR changes only:

- isolated incremental publication service;
- CU-07 atomicity/failure/concurrency tests;
- CI shard ownership for the new test file;
- CU-07 proof and merge documentation.

The diff makes no changes to:

- production publication pointers or namespace defaults;
- public Team Board, League, Matchup, Tonight, or Pitcher routes;
- frontend files;
- live cache invalidation;
- Render configuration or cadence;
- GitHub production schedules;
- workers, polling, or daemons;
- CU-01 through CU-06 semantics;
- migrations.

## Hosted validation

Required PR validation status is recorded on PR #775. Merge is authorized only
after required PostgreSQL migrations/shards, collection accounting, backend tests,
frontend checks, dependency audit, and required deployment-preview checks reach
terminal success. A missing, skipped, timed-out, or failed required check is not a
pass.

## Merge and post-merge verification

- Merge strategy: **normal merge commit** (no squash/rebase/cherry-pick)
- PR merge commit SHA: recorded by GitHub on PR #775 after merge
- Resulting `main` HEAD: the PR merge commit recorded by GitHub
- Accepted CU-07 ancestry: required and verified after merge
- Remote feature branch: retained

Post-merge repository verification must confirm:

- `0914a6463f55f7ed6002276f76579f852b2ce36b` is an ancestor of `main`;
- one Alembic head remains;
- `cu07_incremental_proof` remains dormant;
- production pointer and routes remain unchanged;
- live cache behavior remains unchanged;
- scheduling/polling remain unchanged.

## Automatic deployment behavior

Existing repository integrations may run CI/Vercel automation after merge. No
manual deployment, production migration, environment change, proof publication,
or cache invalidation is authorized by CU-07.

## Remaining risks

- CU-07 is an isolated proof authority, not production serving authority.
- Production Dashboard and Tonight authority remain independent.
- The proof cache adapter is not a live production cache integration.
- Full backend suite was not run locally; focused semantic, PostgreSQL, publication,
  scheduling, and shard-accounting evidence was used.
- CU-08 activation remains separately governed.

## Verdict and exact next action

Merge verdict is **MERGED SAFELY** only after PR #775 required hosted validation
passes and GitHub creates the normal merge commit. The exact next action then is to
observe existing automatic checks without intervention and stop. CU-08 must be a
separate task.
