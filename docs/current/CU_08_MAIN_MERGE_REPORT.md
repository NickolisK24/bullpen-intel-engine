# CU-08 Main Merge Report

## Repository identity

- Feature branch: `feat/controlled-continuous-execution`
- Accepted CU-08 commit: `1640563eaa03ed596ad21c3c3c8bc48e083f0956`
- Pre-push `origin/main`: `4b82cc0345c9bbe735a844d7d414f88182c51ba8`
- Upstream drift before push: none (`0 behind / 1 ahead` before this report)
- Schema changes: none
- Alembic head: `c6d8e1f3a5b7`

The accepted commit remained the feature HEAD at initial verification. This report
is the only follow-up repository change. The branch was not rebased, squashed, or
force-updated. The unrelated untracked
`BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` remained untouched.

## Final local validation

- CU-01 through CU-08 focused chain: **153 passed, 3 PostgreSQL-only skipped**.
- Broad coexistence/authority/publication/scheduling selection: **943 passed,
  3 PostgreSQL-only skipped** outside the known Windows-to-bash temporary-path
  family.
- Known Windows-only qualification: 13 failures reproduced in tests that pass a
  Windows temporary path to bash; no CU-08 assertion failed.
- Test-database safety and migration fixtures: **12 passed, 13 skipped**.
- Alembic single-head guard: **PASS**, `c6d8e1f3a5b7`.
- CI shard verification: **400 files / 9,117 tests**, assigned exactly once.
- Python compilation: **PASS**.
- Whitespace/diff checks: **PASS**.
- Full backend suite: **NOT RUN**.

The accepted local PostgreSQL advisory-lock and CU-07 concurrency proofs remain
the implementation checkpoint. The merge machine's repository environment pointed
to a non-local database, so the disposable-database guard correctly refused a new
local PostgreSQL run. Hosted PostgreSQL validation is therefore a mandatory merge
gate, not inferred from the SQLite run.

## Default-OFF and mode matrix

Configuration resolution remains fail closed:

- missing mode resolves to `OFF`;
- invalid mode resolves to `OFF` with `invalid_mode`;
- missing execution enablement blocks every non-OFF mode;
- missing production-publication permission blocks production modes;
- `LIMITED_LIVE` requires a nonempty game or team allowlist;
- `FULL_LIVE` additionally requires explicit acknowledgement.

Mode behavior remains:

- `OFF`: no continuous work;
- `SHADOW_DETECT`: CU-02 detection only;
- `SHADOW_FULL_CHAIN`: CU-02 through CU-06, without production publication;
- `PROOF_PUBLICATION`: CU-07 proof namespace only;
- `LIMITED_LIVE`: explicit bounded allowlist and publication authorization;
- `FULL_LIVE`: explicit enablement, publication authorization, and acknowledgement.

No mode is activated by merging the code.

## Production-publisher, kill-switch, and allowlist audit

The one-shot command does not receive a production publisher by default. Proof
publication requires an explicitly supplied isolated publisher. Production modes
fail closed without separate publication authorization.

The execution enable flag is the operational kill switch. Disabling it makes the
next cycle perform no continuous production work and does not affect existing
scheduled jobs. Production publication has its own independent gate.

`LIMITED_LIVE` cannot fall through to all games: an empty or invalid allowlist is
rejected. Maximum games, canonical actions, publication cohorts, source requests,
runtime, and core failures remain bounded.

## Source budget, runtime, and recurring no-op proof

The accepted natural 15-game scheduled-slate proof remains the measured evidence:

- initial cycle: 15 games, 16 requests, 0 retries, approximately 781 ms;
- exact replay: 15 unchanged games, 16 requests, 0 retries, approximately 465 ms;
- replay downstream work: zero across CU-03 through CU-07.

The final local tests re-proved source-budget, retry, circuit-breaker, missed-cycle,
restart, and unchanged-cycle behavior. The deterministic runtime was not remeasured
against MLB during the merge task; the accepted sub-second measurement remains well
inside the 120-second stop-starting-work boundary and the proposed future three-
minute cadence. No cadence is activated here.

## Overlap and existing-authority coexistence

The accepted PostgreSQL proof established one advisory-lock winner and one clean
skip for overlapping cycles. The final focused and broad selections re-proved that
continuous/postgame and continuous/daily orderings converge without duplicate
GameLogs, doubled workload, false history, stale rollback, or publication-order
changes. Existing scheduled daily and postgame syncs remain production authority.

## Proof namespace isolation

`cu07_incremental_proof` remains referenced only by the isolated CU-07 service,
tests, and documentation. No public route, frontend surface, schedule, sync command,
or default cache/publication configuration reads it or makes it production current.

## Render and GitHub scheduling audit

The CU-08 diff changes no `.github/workflows` file and no frontend file. The
repository has no tracked Render service-definition file; current Render jobs are
managed outside this diff. Repository searches found the one-shot command only in
its developer command and service implementation.

Therefore this change adds:

- no Render Cron job or cron-expression change;
- no GitHub production schedule or cadence change;
- no worker or daemon;
- no infinite polling loop;
- no automatic invocation of the continuous command.

## Final diff audit

The feature diff is limited to:

- the bounded continuous-cycle service;
- explicit fail-closed mode configuration;
- the unscheduled one-shot command;
- cycle locking, budgets, allowlists, kill switch, and circuit breaker;
- bounded game-observation support;
- focused tests and CI shard ownership;
- proof and merge documentation.

It contains no migration, frontend change, Team State or read-model semantic change,
production route change, cache-authority change, production publisher default, or
scheduling activation.

## Hosted validation and pull request

- Remote feature HEAD:
  `71f4fa67a1f72dd485b3c726d7af4eb1074a9bc9`
- Pull request: [#776](https://github.com/NickolisK24/bullpen-intel-engine/pull/776)
- Hosted PostgreSQL migrations: **PASS**
- Hosted PostgreSQL shards 1 through 4: **PASS**
- Hosted collection/shard accounting: **PASS**
- Hosted frontend tests and production build: **PASS**
- Hosted dependency audit: **PASS**
- Vercel preview and preview comments: **PASS**
- Supabase preview: skipped by the existing integration and not a required CU-08
  validation path

A failed, skipped, timed-out, or unavailable required check is not a pass and blocks
merge.

## Merge and post-merge verification

- Merge strategy: normal merge commit only
- PR merge commit SHA: `3f00e58bfc2f709fb69b8bfedeff9fda7b1ea41b`
- Resulting `main` HEAD after CU-08 merge:
  `3f00e58bfc2f709fb69b8bfedeff9fda7b1ea41b`
- Accepted CU-08 ancestry: **PASS**
- Final feature-head ancestry: **PASS**
- Remote feature branch: retained at
  `71f4fa67a1f72dd485b3c726d7af4eb1074a9bc9`

Post-merge verification must confirm mode still defaults to `OFF`, no Render or
GitHub schedule invokes CU-08, no production publisher is wired by default,
`cu07_incremental_proof` remains isolated, and scheduled syncs remain authority.

## Natural versus controlled evidence

Natural evidence covers the bounded 15-game scheduled slate and exact unchanged
replay. Live progression and finality behavior remain controlled real-shape proof;
no natural live transition was observed. This merge does not upgrade that claim.

## Automatic deployment and actions not performed

Existing CI or preview automation may run after push/merge. This task does not
manually deploy, run a production migration, modify Render or environment variables,
invoke the continuous command against production, invalidate caches, enable
`SHADOW_DETECT`, or begin CU-09.

The existing Vercel preview integration ran successfully for PR #776. The existing
post-merge GitHub CI run started automatically on `main`; no manual deployment or
production activation was requested or performed.

## Remaining risks

- Natural recurring live/finality evidence has not been collected.
- Production full-chain p95 and source pressure are not yet measured.
- The command intentionally has no default production publisher.
- Full backend tests were not rerun locally; bounded semantic, authority,
  scheduling, shard, and hosted PostgreSQL evidence govern this merge.

## Verdict and exact next action

Final verdict: **MERGED SAFELY**.

The exact next action is to let existing post-merge CI/preview automation finish
without intervention and stop. Any production rollout, including `SHADOW_DETECT`,
requires separate explicit authorization.
