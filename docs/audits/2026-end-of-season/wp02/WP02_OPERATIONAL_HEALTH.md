# WP-0.2 Operational Health

## 1. Scheduled workflow reliability

Evidence base: "BaseballOS Bullpen Sync" scheduled runs 847–858 (2026-11-01 to 11-05) on `main`.

- In every inspected run, `public-sync` (publication-critical) and `static-team-story-preview` (distribution) **succeeded**.
- Preview commits for snapshots 5814, 5815, 5817 and 5820 landed on `main`.
- The runs were red because of two observer or internal jobs.

### internal-enrichment: false positive on a pitcher's name (fixed)

- **Symptom:** `Phase 0D evidence step failed: step=roster_depth_rebuild`, then `claim language violates forbidden_prediction_framing: 'Will'`.
- **Root cause:**
  - `services/evidence_language.py` lints the **rendered** claim with `\bwill\b` (case-insensitive).
  - Roster-depth claims are built with f-strings that insert `Pitcher.full_name` (`services/roster_depth_evidence.py`: daily depth delta, explained changes and unexplained changes).
  - A reliever named "Will …" (for example Will Vest) on the 2026-07-24 recompute date matched as prediction framing. "Chad Green" trips the colour rule the same way.
- **Why it repeats:**
  - The rows stay `RECOMPUTE_NEEDED`, and the oldest date is retried first.
  - The single stage-level `try/except` rolls back the whole `workload_evidence` phase.
  - So the current date's Phase 0D evidence is never built.
- **Reproduced:** `render_claim_template(ClaimTemplate('x',1,'{claim}'), {'claim': '...: Will Vest, no removals.'})` raises the exact production message on `origin/main`.
- **Fix:**
  - `lint_claim_language` and `assert_claim_language_allowed` accept `proper_nouns`: exact strings the caller inserted, masked for linting only.
  - The parameter is threaded through `render_claim_template`, `build_evidence_object(claim_proper_nouns=...)` and roster-depth `_build_object`.
  - The three name-bearing roster-depth claims pass the names they inserted.
  - Authored text is still linted in full, so "Will Vest will be available" is still rejected.
- **Publication impact:** none. The job has `continue-on-error`, holds the internal lock, and never publishes.
- **Not done (separate hardening):** per-date isolation in `rebuild_marked_roster_depth_evidence`, so that one poisoned date cannot block the current date. Recorded as a remaining risk.

### shadow-activation-health: validator read the wrong summary format (fixed)

- **Symptom:** `Activation health is FAILED (reason=validator_reported_failure)` on every daily and postgame cycle.
- **Root cause:**
  - Since the Render-primary cutover the workflow writes its summary with `scripts/run_due_sync.py`: `{status: executed|already_satisfied|failed|blocked, mode, ..., result: {sync, publication_proof, ...}}`.
  - `scripts/validate_game_driven_shadow_cycle.py` read the legacy `run_daily_sync.py` format instead: top-level `sync.status`, `publication_proof` and `sync.game_driven_ingestion`.
  - Every real summary failed on `sync_status` (observed `executed`), `daily_publication_proof` and `game_driven_report_missing`. Reproduced on `origin/main` through the real `run_due_sync.main` output.
- **Fix:** `normalize_sync_summary` unwraps the `run_due_sync` format into the fields the existing checks expect.
  - `executed`: all existing lane checks run unchanged.
  - `already_satisfied`: PASS as a **labelled no-op** (`work_state: already_satisfied_no_cycle`). It requires runner exit 0, `executed: false` and `satisfied_by_attempt_id`. It is not presented as proof of lane health.
  - `failed` or `blocked`: FAILED (`due_outcome`), with the lane still evaluated for diagnostics.
  - The legacy format is still accepted.
- **Not changed:** the job is still allowed to fail the run.
  - Decision D-040 (canonical Decision Ledger) keeps "neither publication nor observer gates weakened". With the contract fixed, red now means a real observer failure, so `continue-on-error` was **not** added.
  - If the shadow lane itself is unhealthy, the next production cycle will show that honestly, and it should then be judged on its own merits (DEC-04: retire or repair).

### Publication-critical versus optional (as configured on `main`)

| Job | Role | Fails the run? |
|---|---|---|
| `public-sync` | publication-critical | yes |
| `static-team-story-preview` | distribution (publishes previews) | yes |
| `team-state-vnext-proof` | proof validation | yes |
| `shadow-activation-health` | observer (D-040) | yes, by decision; now meaningful |
| `internal-enrichment` | internal, non-public | no (`continue-on-error`) |

### Open publication-critical item outside WP-0.2

- On 2026-11-01 the first post-WP-0.1 daily run published snapshot 5814 and then failed with `league_team_state_artifact_set_incomplete`: the artifact gate expected 30 artifacts after every club was withheld as Season Complete.
- A tested fix exists as commit `51a0ed491` on branch `fix/wp01-competition-withheld-artifact-gate`. It is **not pushed**; it is awaiting founder approval from the WP-0.1 report.
- Daily windows run on Render Cron, whose logs are not visible here. Whether each Render daily run since then has failed the same way is **UNVERIFIED**. Snapshots kept publishing (5815, 5817, 5820), because the gate raises after the publication commit.

## 2. Monitoring contract (implemented)

`backend/services/production_health.py`, `backend/scripts/check_production_health.py`, `.github/workflows/production-health.yml`.

| Question | Check | Critical when |
|---|---|---|
| Is BaseballOS serving requests? | `GET /api/health` | not 200 / `status != ok` |
| Is it production? | `environment` | not `production` |
| Did the latest deployment land? | `release` (Render `RENDER_GIT_COMMIT`, newly exposed) vs. the latest commit on `main` that changed `backend/` (2-hour grace) | deployed commit does not contain it. Missing release: warning, never silently healthy |
| Did a publication fail when one was expected? | `publication_authority.published_at` | older than 36 h. A trusted snapshot publishes daily in season **and** offseason |
| Is published data correctly dated? | `data_through` | missing, in the future, or after `published_at` |
| Are public read models consistent? | `/api/bullpen/team-states` | not 30 rows, or `represented + withheld != 30`, or the count disagrees with the rows |
| Is a stale historical read presented as current? | represented clubs vs. `data_through` age | any current Team State on data older than 5 days (the October 2026 failure) |
| Offseason quiet day | all 30 `season_complete`, nothing represented | never. Recorded as `info` |

- **Alert delivery:** a critical result exits 1. The scheduled run (`37 */6 * * *`) then fails, and GitHub's existing failed-scheduled-run notification emails the repository owner. No new service or credential was added; the workflow holds no database secret.
- **API base:** the repository variable `BASEBALLOS_API_BASE_URL` (recommended; not a secret), falling back to the existing `BASEBALLOS_SYNC_URL` secret.
- **Not covered, and why:**
  - **Offseason roster-transaction processing and authoritative-source failures.** The public API exposes no ingestion freshness for transactions, and a credential-free check cannot see the database. The existing manual `baseballos-scheduler-health.yml` (database-backed) remains the tool. A public `/api/health/ingestion` summary would be a follow-up.
  - **Database unavailable.** Observed indirectly: the listing endpoint fails, which is critical.

## 3. Render deployment verification

**BLOCKED.** `api.render.com` and the API host are refused by this environment's network policy (proxy 403), and no Render credential is available.

- **Inventory (documented, not observed):**
  - web service `baseballos-api`, dashboard-managed with no `render.yaml`;
  - Cron Jobs: BaseballOS Daily primary (`5 10 * * *`), postgame primary (`5 2,4,6 * * *`) and morning primary (`5 14 * * *`), all running `run_due_sync.py` from branch `main`;
  - historically `baseballos-continuous-shadow-detect` (EOS-016; current status unknown).
- **Auto-deploy:** documented as auto-deploy from `main` (`docs/current/PRODUCTION_MIGRATION_AUTHORITY.md`).
- **What WP-0.2 adds:** `/api/health` now returns `release`, from Render's `RENDER_GIT_COMMIT`, which `continuous_publication_admission.py` already relies on. After this PR deploys, `production-health.yml` verifies the deployed commit against `main` on every run, without Render access.
- **Still needs an operator with Render access:** latest deploy status per service, failed deploys, startup errors, and Cron Job last-run status. Render dashboard → each service → Events and Logs.

## 4. Offseason operating rules

| Situation | Classification |
|---|---|
| No games scheduled / no new appearances / `data_through` unchanged since 2026-10-28 | normal (info) |
| No roster transactions today | normal |
| Daily trusted publication still occurs | expected; its absence for more than 36 h is critical |
| Every club `season_complete`, nothing represented | normal offseason |
| A club shows a current Team State on data older than 5 days | critical (stale presented as current) |
| API or listing unreachable | critical |
| Shadow lane `already_satisfied` | labelled no-op, not failure |

No offseason product redesign was implemented (out of scope).

## 5. Staging

None exists. Only development, test and production configurations exist. The restore rehearsal (WP02_BACKUP_RECOVERY.md) produces a scratch copy that can serve as a pre-production check, but it is not a deployed staging service. Creating one (a separate Render service plus a database restored from a dump) is a founder decision.
