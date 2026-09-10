# CU-01I — Main Integration and Render Cron Proof

**Verdict: PASS — READY FOR MAIN**

CU-01 remains a non-authoritative ingestion foundation after a normal merge of
current `origin/main`. The merge adds no scheduled execution, changes no cron
expression or sync command, and does not promote the game-driven lane. The
exact 15-game proof, workload parity, replay/restart, ordering, pitch ownership,
publication, and historical sentinels all passed.

## 1–4. Branch and integration checkpoints

| Item | Value |
|---|---|
| Branch | `feat/continuous-reliever-ingestion` |
| Starting CU-01R HEAD | `7509bdacf64bca25f79a319fa00ca847fcdab235` |
| CU-01 checkpoint | `1bf3978663d2ef0fb562cc49e2b1dea411d03214` |
| CU-01P checkpoint | `8be2d6afe47906b4be2155238cc07142fdfaa15e` |
| CU-01R checkpoint | `7509bdacf64bca25f79a319fa00ca847fcdab235` |
| Integrated `origin/main` | `90de9d83b75b20e19378a714c107f73139aa8bb3` |
| Normal merge commit | `d147cc66fe9fa991ec6155cbd7afadefa54a8714` |
| Pre-merge relationship | 3 commits ahead, 6 commits behind |
| Post-merge relationship | 4 commits ahead, 0 commits behind |

All three named CU checkpoints and the integrated main commit are ancestors of
the merge commit. No rebase, squash, or history rewrite occurred.

## 5. Upstream six-commit audit

The audit used each commit's actual first-parent diff, not its title alone.

### `da1facd09b2e37312fb572d0d09a3c521ca1b260`

`fix: align rested options across surfaces`

Files: `backend/services/published_team_rest_status_listing.py`,
`backend/services/tonight_intelligence_service.py`,
`backend/services/tonight_intelligence_snapshot.py`,
`backend/tests/freeze_policy.py`,
`backend/tests/test_published_team_rest_status_listing.py`,
`backend/tests/test_qa_reconciliation_scenarios.py`,
`backend/tests/test_tonight_intelligence_endpoint.py`,
`backend/tests/test_tonight_intelligence_service.py`,
`backend/tests/test_tonight_intelligence_snapshot.py`,
`frontend/src/components/home/IntelligenceSurface.jsx`, and
`frontend/tests/intelligenceSurface.test.mjs`.

Classification: **MATERIAL INTERACTION** with current Tonight/read-model
semantics and their tests, but **NO INTERACTION** with Render configuration,
cron, sync commands, ingestion, GameLog, PBP, finality, migrations, or
environment handling. It does not call the CU-01 path.

### `b08fadc3c501e25ad2cd597580d0eae84a632bc1`

`test: assign rested status coverage to CI shard`

File: `backend/tests/ci_shard_manifest.json`.

Classification: **CONFLICT RISK** limited to the test manifest. CU-01 had added
two test-file assignments to the same shard; upstream added the Rested Options
test assignment.

### `72ec066aac96561ac45b1213862c63e06502b2dc`

`test: freeze performance freshness fixtures`

Files: `backend/tests/test_performance_intelligence.py` and
`backend/tests/test_performance_intelligence_admin_api.py`.

Classification: **LOW INTERACTION**. This is fixture/test correction only. It
does not alter runtime performance-freshness or CU-01 semantics.

### `2c20219e7a8bb4b560f31ed43e4cd4bcf1b64890`

`Merge pull request #766 from NickolisK24/fix/performance-intelligence-freshness-fixtures`

First-parent files: the two performance-intelligence test files above.

Classification: **LOW INTERACTION** integration history; no additional runtime
change beyond `72ec066...`.

### `d35190509de5b9e27bdfaa94bc6b34e78260b8be`

`Merge remote-tracking branch 'origin/main' into fix/rested-options-consistency`

First-parent files: the two performance-intelligence test files above.

Classification: **LOW INTERACTION** integration history; it combines the two
upstream branches without changing CU-01 or scheduling.

### `90de9d83b75b20e19378a714c107f73139aa8bb3`

`Merge pull request #765 from NickolisK24/fix/rested-options-consistency`

First-parent files: the Rested Options backend/frontend files, tests, freeze
policy, and shard manifest listed above.

Classification: **MATERIAL INTERACTION** with Tonight/read-model semantics and
**CONFLICT RISK** for the shard manifest only. No Render, cron, sync command,
ingestion, GameLog, PBP, finality, migration, or environment file changed in
the six-commit range.

The Render-era scheduler implementation predates this range and was already in
the common base `74addba25f6113b7fb9ca943ee4e2b5a67bd6351`; it was audited
separately below.

## 6. Conflicts and resolutions

One conflict occurred: `backend/tests/ci_shard_manifest.json`.

Resolution: retain CU-01's `test_cu01p_proof.py` and
`test_continuous_reliever_ingestion.py` assignments, retain upstream's
`test_published_team_rest_status_listing.py` assignment, and combine their
balancing inputs in shard 2. Manifest verification subsequently found 393
files and 8,970 test node IDs, each assigned exactly once.

There were no runtime, publication, frontend, environment, or migration
conflicts. No `ours`/`theirs` wholesale resolution was used.

## 7. Current Render Cron execution map

The repository intentionally has no root `render.yaml`; the existing Render
web service and three Cron Job resources are dashboard-managed. Repository
evidence specifies this production contract:

| Render job | UTC schedule | Command | Target and effects |
|---|---|---|---|
| BaseballOS Daily primary | `5 10 * * *` | `python backend/scripts/run_due_sync.py --mode daily --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT10:05:00Z')" --days-back 7 --public-only` | `sync_due._run_daily` → `sync.run_daily_sync`; authoritative legacy canonical acquisition/writes, governed dashboard snapshot publication, then schedule/Tonight refresh |
| BaseballOS postgame primary | `5 2,4,6 * * *` | `python backend/scripts/run_due_sync.py --mode postgame --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT%H:05:00Z')" --public-only` | `sync_due._run_postgame` → marker recovery → `sync.run_postgame_refresh`; completed-game reconciliation and existing gated publication, then schedule/Tonight refresh |
| BaseballOS morning primary | `5 14 * * *` | `python backend/scripts/run_due_sync.py --mode morning --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT14:05:00Z')" --public-only` | `sync_due._run_morning` → `refresh_schedule_and_tonight`; schedule correction and Tonight cache coherence |

`run_due_sync.py` forces `AUTO_SYNC=false`, validates the production execution
context before application/database initialization, and dispatches through the
durable due-window service. `sync_schedule_attempts` and the PostgreSQL advisory
writer lock prevent two schedulers from executing or publishing the same
window concurrently. A satisfied later trigger records `already_satisfied`.

Required Render environment is the web service's protected environment group
for `DATABASE_URL`, `SECRET_KEY`, `ADMIN_API_TOKEN`, and publication
dependencies, plus `APP_ENV=production`, `AUTO_SYNC=false`,
`BASEBALLOS_SCHEDULER_AUTHORITY=render_cron_v1`, and
`BASEBALLOS_PRODUCTION_BRANCH=main`. Render supplies `RENDER=true`.

Migrations are not run by cron. The documented production path applies
`flask db upgrade` as a release/pre-deploy operation before enabling jobs.

Repository evidence can prove intended commands, code paths, and fallback
wiring. It cannot independently inspect the live dashboard-managed Render
resource values; live Render configuration remains deployment/operations
evidence, not a repository claim.

## 8–9. Production authority and GitHub Actions role

```text
Render Cron primary trigger
  -> run_due_sync.py
  -> execution-context validation
  -> due-window ledger + public PostgreSQL advisory lock
  -> daily legacy writer / postgame legacy reconciliation / morning refresh
  -> existing completeness and publication gates
  -> canonical snapshot/publication and schedule/Tonight refresh as applicable

GitHub delayed fallback trigger
  -> the same run_due_sync.py command and durable window identity
  -> already_satisfied no-op, lock-blocked result, or the same authoritative work
```

GitHub Actions is not CI-only. `.github/workflows/baseballos-sync.yml` retains
delayed production fallback schedules: daily `17 10 * * *`, postgame
`11 2,4,6 * * *`, and morning `23 14 * * *`, all UTC. Daily and postgame set
`GAME_DRIVEN_INGESTION_MODE=shadow`; backfill explicitly sets it to `off`.
The intraday repair workflow remains manual-only and has no schedule trigger.

Scheduler authority is distinct from baseball/publication authority. The
legacy scheduled daily and postgame writers remain authoritative; existing
publication proofs remain authoritative.

## 10–11. Migration integration

Upstream added no migration. The merge retained both CU migrations:

- `f1c2d3e4a5b6_add_continuous_reliever_ingestion.py`
- `b4e7c9d2a1f6_add_pbp_observation_order.py`

All three proof databases passed upgrade, downgrade, and re-upgrade. The
upgraded schemas contained the GameLog and pitch-event structures plus the
persisted observation-order marker fields; downgrade removed the CU-owned
structures as expected; re-upgrade restored them. Flask-Migrate reports one
head: **`b4e7c9d2a1f6`**. No migration was dropped or rewritten.

## 12. Render Cron regression result

**PASS.** CU-01/CU-01I adds no Render service or repository Render Blueprint,
changes no cron expression, changes no scheduled workflow trigger, and changes
no `run_due_sync.py` command. Deploying the merged code therefore cannot by
itself increase cadence.

The lane's deployed default is `off`. `shadow` plans/fetches/projects and
writes nothing. Only explicit `write` reconciles canonical rows, and only the
separately named `authoritative` mode can supply publication-critical
completeness. Current GitHub daily/postgame automation selects only `shadow`.
Postgame refuses writing modes before planning because it lacks a two-writer
conflict-prevention mechanism. No shadow command was promoted.

## 13. Shared-code regression result

**PASS.** Shared GameLog reconciliation, finality, pitching-line extraction,
source provenance, PBP, pitcher identity, daily/postgame wiring, snapshot
trust, and publication-proof suites passed. The exact proof also exercised the
same authoritative postgame parser as the parity baseline. The merge brought
no upstream change into any shared CU runtime file.

## 14. Exact 15-game replay

Live source recapture: `2026-08-28T17:39:46.512830+00:00`; raw capture
fingerprint `6087a32e2301b4f73763e7c7714717886f96b49da16008726fed338e31f9dd7a`.
The capture fingerprint differs from CU-01R's earlier capture, but normalized
counts and the authoritative GameLog fingerprint remained identical. The old
raw payload was not retained, so the exact raw-field delta is not claimed.

| gamePk | Date | Relievers | Pitches | GameLog first pass | Compared values | Result |
|---:|---|---:|---:|---|---:|---|
| 823826 | 2026-08-25 | 12 | 365 | 14 insert | 72 | PASS |
| 823989 | 2026-08-25 | 11 | 395 | 13 insert | 66 | PASS |
| 823180 | 2026-08-26 | 9 | 356 | 11 insert | 54 | PASS |
| 824878 | 2026-08-26 | 9 | 343 | 11 insert | 54 | PASS |
| 823016 | 2026-08-25 | 6 | 310 | 8 insert | 36 | PASS |
| 822692 | 2026-08-26 | 6 | 303 | 8 insert | 36 | PASS |
| 822771 | 2026-08-27 | 7 | 309 | 9 insert | 42 | PASS |
| 823014 | 2026-08-27 | 7 | 290 | 9 insert | 42 | PASS |
| 823825 | 2026-08-26 | 5 | 271 | 7 insert | 30 | PASS |
| 822773 | 2026-08-25 | 9 | 323 | 11 insert | 54 | PASS |
| 823585 | 2026-08-25 | 8 | 314 | 10 insert | 48 | PASS |
| 823505 | 2026-08-25 | 8 | 325 | 10 insert | 48 | PASS |
| 824963 | 2026-08-26 | 5 | 242 | 7 insert | 30 | PASS |
| 822694 | 2026-08-27 | 7 | 326 | 9 insert | 42 | PASS |
| 823179 | 2026-08-27 | 7 | 281 | 9 insert | 42 | PASS |

Totals exactly retained the accepted baseline: **15 games, 146 canonical
pitching appearances, 116 reliever appearances, 4,753 pitch events, and 2,239
reliever pitch events**. Every game was `final_and_usable`. Finality, supported
line coverage, game-side ownership, null semantics, affected entities,
optional PBP, publication safety, and historical safety passed for every game.

## 15. Workload parity

**696 / 696 PASS.** The authoritative baseline still contains 146 GameLogs and
has the unchanged fingerprint
`a4dd34416a28b7c5f75ed64fe9eaeba3a737e4335bc7b1da5a1413f96a709fa3`.
Compared fields remained `game_date`, `innings_pitched_outs`,
`pitches_thrown`, `batters_faced`, `games_started`, and
`appearance_team_id`. The denominator and contract were not changed.

## 16–17. No-op and restart proof

Replay set: `823826`, `823989`, `823180`, `823016`, `822694`.

| Pass | GameLog mutations | Pitch mutations | Affected pitchers | Affected teams | Canonical facts |
|---|---:|---:|---|---|---|
| Exact second replay | 0 | 0 | `[]` | `[]` | unchanged |
| Restart + exact third replay | 0 | 0 | `[]` | `[]` | unchanged |

Second-pass rows remained 55 GameLogs and 1,752 pitch rows; fingerprint
`d2e219ff119a23107e81ef3f4f13634a8d4a926a3adc8e95b53a27b692bdffc8`
was unchanged before/after. After the controlled correction and full engine /
Flask application reconstruction, third-pass fingerprint
`5ac0b72c88503af662ae40ef6956f51fecd9facb99964988da186be5e111b06b`
was unchanged before/after. No ephemeral-only state is required.

## 18. Observation-order result

**PASS, controlled real-payload replay.** Game `823826`, pitch `(33, 2)`:

1. A at governed sequence 1 was canonical; identical A was a no-op.
2. B at sequence 2 was `newer_accepted`: one update and one supersession,
   affecting only pitcher `680767` and historical team `146`.
3. A replay was `stale_rejected`: zero mutations and zero affected entities.
4. B replay was identical.
5. After engine/application restart, A remained `stale_rejected`; canonical
   fingerprint remained
   `21746c2d13a5763f18ced18d79376b956bb42b5b29148ba9fe2e41a20e9a96e8`.

Neighboring pitch fingerprints remained unchanged. Focused tests also passed
ambiguous-order rejection, weaker-authority rejection, persisted sequencing,
and exclusion of local acquisition time from authority. MLB exposes no usable
monotonic PBP revision here, so this remains controlled rather than naturally
observed revision proof.

## 19. Batted-ball ownership

**PASS.** Across 4,753 events, 846 in-play pitches carried
`batted_ball_event_type`; non-in-play/non-owning pitches carrying it: **0**.

Manual sample, game `822692`, at-bat 0:

| Event | Call | In play | Event type | Launch speed | Launch angle |
|---:|---|---|---|---:|---:|
| 3 | Called Strike | false | null | null | null |
| 4 | In play, no out | true | double | 60.7 | 24.0 |

The non-owning pitch remains null; only the owning event carries the double and
batted-ball tracking.

## 20. Optional PBP result

**PASS, partial/nonblocking.** A controlled PBP fetch failure for game `822694`
left the core run complete with 9 canonical GameLogs, 7 changed relievers, and
historically affected teams 115 and 120. PBP was observably incomplete with
reason `play_by_play_fetch_failed`, stored zero pitch rows, and reported
`publication_affected=false`.

## 21. Position-player pitching

**PASS.** Pedro Pagés remained `C`, Jorbit Vivas remained `3B`, and Myles Straw
remained `CF`, with their active/current team identities preserved. Their
historical pitching appearances did not turn them into current bullpen
pitchers.

## 22. Publication sentinels

**PASS.** Before/after counts and full-row fingerprints were identical for:

- dashboard snapshots, including the published historical sentinel;
- intelligence surface and Tonight snapshots;
- share artifacts, assets, evidence, relations, and generation audits; and
- progressive team publications.

No CU proof path invoked a publication pointer, What Changed, public read-model
rebuild, frontend payload mutation, or public cache invalidation.
`publication_affected` remained false.

## 23. Historical sentinels

**PASS.** Historical `appearance_team_id` stayed stable after changing a
pitcher's mutable current `team_id` to unrelated team `999999`. Existing
snapshot/artifact sentinels remained byte-for-byte logically identical. Replay
created no GameLog, pitch, snapshot, or publication history.

## 24. Performance-freshness upstream analysis

Upstream commit `72ec066...` freezes the current performance-freshness fixture
clock in two test modules; it does not change runtime semantics. Those two
files now pass. Together with the upstream Rested Options/Tonight integration
group, the result was **216 passed**. The comparable broad diagnostic had
exactly seven fewer failures than CU-01R's unintegrated result, matching the
seven previously identified freshness-fixture failures. CU-01 did not require
or receive a semantic change for these fixtures.

## 25. Focused and relevant test results

| Validation | Result |
|---|---|
| CU-01/CU-01P/CU-01R focused tests | **16 passed** |
| Shared ingestion/finality/authority/PBP/postgame/snapshot suite | **529 passed, 1 skipped** |
| Render due-window/scheduler/shadow tests (excluding Windows-only bash-path case) | **190 passed, 1 deselected** |
| Upstream performance/Rested Options/Tonight tests | **216 passed** |
| Upstream frontend Intelligence Surface test | **83 passed** |
| Exact 15-game proof harness | **PASS** |
| CI shard verification | **PASS** — 393 files, 8,970 node IDs exactly once |
| Python compilation | **PASS** |
| Migration upgrade/downgrade/re-upgrade | **PASS** in three databases |
| Alembic heads | **PASS** — one head, `b4e7c9d2a1f6` |

One repository workflow syntax test fails on Windows because WSL `bash -n`
receives an unconverted `C:\...\Temp\...sh` filename. This is the previously
known host-path mismatch, not a YAML/shell-content failure and not introduced
by CU-01I.

## 26. Broader diagnostic

Classification: **FAIL** for the completed default-environment run and
**INCOMPLETE** for the explicitly file-backed disposable SQLite run.

- Completed comparable run: **8,771 passed, 73 skipped, 94 failed, 32 errors**
  in 253.21 seconds.
- CU-01R comparable baseline: 8,760 passed, 73 skipped, 101 failed, 32 errors.
- Delta: eleven more passes and seven fewer failures over four additional
  collected tests. The seven repaired failures are the upstream
  performance-freshness fixtures.
- The remaining clusters include the known Windows `bash -n` path handling,
  branch/source-hash freeze tests, and database-environment-dependent audit and
  trusted-board fixtures. The isolated core CU/shared suite has no failures.
- The explicitly qualified disposable SQLite run exceeded 420 seconds before
  pytest emitted a terminal summary and is therefore **INCOMPLETE**, not pass.

No newly consistent CU-01I runtime failure was found.

## 27. Remaining risks

1. Render resources are dashboard-managed. Repository proof cannot attest that
   the live dashboard still exactly matches the documented schedules,
   commands, and environment; that requires post-deploy operational evidence.
2. The full PostgreSQL CI matrix was not reproduced locally. Some broader
   tests explicitly require PostgreSQL transaction/read-lock behavior.
3. The qualified broad SQLite diagnostic remained incomplete at 420 seconds.
4. The current raw MLB capture fingerprint differs from the earlier proof
   capture. Normalized canonical facts and parity are identical, but the old
   raw response was intentionally not retained for field-level diffing.
5. Natural MLB revision ordering remains unavailable; correction sequencing is
   proven through the governed controlled replay contract.

## 28. Proven claims

- The accepted CU checkpoints remain immutable ancestors of a normal main merge.
- CU-01I adds no schedule, cadence, command, authority, publication, or frontend change.
- Existing legacy daily/postgame sync remains production baseball authority.
- The exact 15 games retain canonical counts, ownership, and null semantics.
- All 696 comparable workload values match current authority.
- Exact replay and post-restart replay cause zero mutations and zero affected entities.
- Newer governed corrections remain possible; stale, ambiguous, and weaker evidence fail closed.
- Batted-ball facts remain scoped to their owning pitch.
- Optional PBP failure remains nonblocking.
- Position-player pitching does not mutate current roster identity.
- Publication and historical sentinels remain unchanged.
- The migration graph has one valid head and passes reversible proof migration cycles.

## 29. Unproven claims

- Live Render dashboard resource state was not inspected or changed.
- No deployment, production migration, production cron execution, or public
  post-deploy observation was performed.
- The broad backend suite is not globally green in this Windows/local database
  environment, and the qualified run did not complete.
- A naturally observed monotonic MLB PBP correction remains unproven.
- The exact raw-field cause of the recapture fingerprint change is unknown.

## 30. Final verdict

# PASS — READY FOR MAIN

The material acceptance statement is supported by repository diffs, the
integrated shared-code suites, and the exact real-game proof. The remaining
unknowns are deployment/operations or pre-existing broad-environment limits;
none requires changing CU-01 semantics or beginning CU-02.

## 31. Recommended production integration action

1. Push `feat/continuous-reliever-ingestion` without rewriting history.
2. Open a PR to `main` and require the full hosted CI matrix, including
   PostgreSQL shards, migration checks, and frontend tests.
3. Merge with a normal merge commit; do not squash or rebase the named CU
   checkpoints.
4. Let the existing Render deploy/release process apply `flask db upgrade`;
   do not run migrations from cron and do not manually alter Render resources.
5. Verify one Alembic head, application health, and unchanged documented Render
   Cron job commands/schedules/environment in the Render dashboard.
6. Observe the next natural daily, postgame, and morning primary windows plus
   delayed GitHub fallback reconciliation. Confirm durable attempts, advisory
   locking/already-satisfied behavior, existing publication gates, and shadow
   non-authority.
7. Keep `GAME_DRIVEN_INGESTION_MODE` at the current `off`/reviewed `shadow`
   posture. Do not select `write` or `authoritative` during this integration.

## 32. Exact next slice

After the normal PR merge and existing Render deployment, perform a bounded
**CU-01 production deployment observation**: verify migration/application
health and observe one natural Render primary plus GitHub fallback window for
each current mode, without changing cadence, authority, or publication rules.
This is operational confirmation of CU-01 under the deployed scheduler—not
CU-02 and not continuous polling.
