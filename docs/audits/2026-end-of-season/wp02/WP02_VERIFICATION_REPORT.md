# WP-0.2 Verification Report

**Branch:** `fix/phase0-wp02-security-operations`
**Base:** `origin/main` `a7a5d1e25af76f70b6bebde2caffae5ee540a668`
**Authorship:** every commit is authored and committed by Nickolis Kacludis <nickoliskacludis@gmail.com>, set via local `-c` git config, with no co-author trailers.

## Reproduced before fixing

| Failure | Reproduction on `origin/main` | After fix |
|---|---|---|
| internal-enrichment `forbidden_prediction_framing: 'Will'` | `render_claim_template(..., 'Active-pitcher census changed by +1 for team 116: Will Vest, no removals.')` raises the exact production message. The new roster-depth test fails on `main`'s services with the same error. | Delta, explained and unexplained objects build COMPLETE with "Will Vest" and "Chad Green" kept verbatim; authored "will" is still rejected |
| shadow-activation-health `validator_reported_failure` | `run_due_sync.main` output fed to `main`'s validator fails on `sync_status` (observed `executed`), `daily_publication_proof` and `game_driven_report_missing`. These are the production invariants. | PASS for a healthy executed cycle; labelled no-op for `already_satisfied`; FAILED for `failed`/`blocked` and for an unverified daily proof |

## Tests

### New

| File | Covers | Local result |
|---|---|---|
| `tests/test_wp02_production_health.py` | offseason quiet day healthy; missed publication critical; stale read presented as current critical; inconsistent read model; future dating; non-production environment; API down; backend deployment identity (behind main, missing, not comparable); git ancestry comparison; `/api/health` reports `RENDER_GIT_COMMIT`; URL derivation | 15 passed |
| `tests/test_wp02_shadow_summary_contract.py` | real `run_due_sync` producer to validator contract; executed, already_satisfied, failed and blocked; legacy shape still accepted | 12 passed |
| `tests/test_wp02_workflow_security.py` | every workflow declares permissions; no secrets in `pull_request` workflows; no `pull_request_target`; `DATABASE_URL` surface can only shrink; only the two distribution jobs can write contents, and they push fast-forward to main only; no tracked or doc credentials; `.env` files are examples only; the scanner's patterns | 8 passed |
| `tests/test_wp02_restore_rehearsal.py` | real `pg_dump`/`pg_restore` round trip on disposable PostgreSQL 16 databases; lost-row detection; missing canonical tables block "verified"; unsafe targets refused; no credentials in output | 5 passed |
| `tests/test_roster_depth_evidence.py` (2 added) | pitcher names in claims; authored forbidden language still rejected next to a name | passed |

Each new failure-reproduction test was confirmed to **fail against `origin/main`** and pass with the fix.

### Updated

- `tests/test_game_driven_shadow_activation_workflow.py`: the scheduled-workflow allowlist adds `production-health.yml`. A new guard requires that workflow to hold no database credential and no `contents: write`.

### Full backend suite, local

CI-style run: four shards, a fresh PostgreSQL 16.15 database each, and CI environment variables.

| Shard | Files | Result |
|---|---|---|
| 1 | 94 | 2,333 passed, 1 skipped |
| 2 | 108 | 2,782 passed, 2 skipped |
| 3 | 163 | 3,666 passed, 1 skipped, 6 deselected (`test_postgame_lookback.py` calls the live MLB API, which this environment's network blocks; CI runs it) |
| 4 | 92 | 2,032 passed |

- `python scripts/ci_shard.py verify`: PASS.
- GitHub Actions results are recorded on the pull request.

### Health CLI end to end

- `check_production_health.py` was run against a locally served API (test configuration, empty database, `RENDER_GIT_COMMIT` set).
- It correctly reported `critical`: `api_environment`, `publication_recent` and `data_dating`.
- It reported `deployed_release: ok` and `read_model_consistency: ok`.
- It was **not** run against production: the API host is blocked from this environment.

## Not verified (access required)

| Item | Blocker | Who / where |
|---|---|---|
| Production API serving, release and publication freshness | API host denied by network policy | runs automatically from GitHub Actions after merge (`production-health.yml`) |
| Render deployed commit, deploy status, Cron last runs | Render API and dashboard not accessible | founder: Render dashboard → service → Events and Logs |
| Supabase backups, retention, PITR | provider console not accessible | founder: Supabase → Database → Backups / Add-ons |
| Production dump and restore drill | no read-only role; no access | founder, using WP02_BACKUP_RECOVERY.md |
| Repository settings (visibility, rulesets) | no settings API in this session | founder, using WP02_BRANCH_PROTECTION_PLAN.md |
| `USER_AUTH_SECRET` set in production | Render environment not visible | founder |

## Confirmations

- No credential value appears in any file, commit, test fixture, log or output produced by this package. History and tree scans redact before printing.
- No production record, credential, repository setting, branch protection or deployment was changed.
- Nothing was merged.
