# WP-0.2 Security Findings

**Date:** 2026-11-05
**Base:** `origin/main` `a7a5d1e25af76f70b6bebde2caffae5ee540a668` (WP-0.1 merge `ee05828cd` plus four automation preview commits)
**Baseline:** 2026 end-of-season audit, EOS-007 to EOS-013 and EOS-025 (`audit/2026-end-of-season-platform-audit` branch). This record re-verifies them; it does not take them as given.

No secret value was printed, stored or committed while producing this record. Scans redact credentials before output.

## Severity key

- **Exposed**: a secret value is readable in tracked files, history or logs.
- **Over-scoped**: a secret is stored safely, but too many jobs or branches can use it.
- **Over-privileged**: a credential has broader database or API rights than its use needs.
- **Potential**: an exposure path exists, with no evidence it was used.

## Findings

| ID | Finding | Class | Severity | Evidence |
|---|---|---|---|---|
| S-1 | No secret value in tracked files or in history | — (negative result) | — | Full-history scan of 2,927 commits on all refs (`git log --all -p`, unshallowed). Every database URL with an inline password points at a placeholder host: localhost, CI `postgres`, `example`, `.invalid`, `.internal`. All six `AKIA…` hits are the `AKIAABCDEF…` test fixture or a detection regex. No `ghp_`, `github_pat_`, private keys, `sk_live_`, Slack tokens or long JWTs. Tracked `.env*` files are `*.example` only. |
| S-2 | Production `DATABASE_URL` reaches 25 of 28 workflows | Over-scoped | **High** | `grep -l secrets.DATABASE_URL .github/workflows/*.yml` returns 25. All secrets are repository-level, and no workflow uses `environment:`. |
| S-3 | A pushed branch can run production database code | Over-scoped, Potential | **High** | `workflow_dispatch` runs the workflow file from the dispatched branch. Most database workflows have no ref guard. Where a guard exists (`github.ref == 'refs/heads/main'`, shell `GITHUB_REF` checks), it lives in the same file the branch can edit. Only the owner (`NickolisK24`, admin) has push access, so the exposure is a compromised owner credential or token, not a third party. |
| S-4 | 9 write-capable production workflows; 11 read-only workflows enforce read-only only in Python | Over-privileged | **High** | Write-capable: `baseballos-sync`, `baseballos-production-maintenance`, `baseballos-intraday-repair`, `appearance_team_backfill_2026`, `unresolved_appearance_team_repair_2026`, `phantom_game_log_reconciliation`, `official_pitching_line_repair_apply`, `official_pitching_line_matt_festa_apply`, `manual-game-driven-noop-qualification`. Five diagnostics enforce read-only at the database level (`default_transaction_read_only` or `SET TRANSACTION READ ONLY` plus a write probe); the other 11 rely on `rollback()` or labels. All of them use the same full-privilege `DATABASE_URL`. |
| S-5 | `main` is unprotected | Potential | **High** | `list_branches`: `main` `"protected": false`. No ruleset requires pull requests or checks. Bot commits push straight to `main` with the job's `GITHUB_TOKEN` (`contents: write`). See WP02_BRANCH_PROTECTION_PLAN.md. |
| S-6 | Public repository | Context | — | Fork pull requests receive no secrets; that is GitHub's default and still true. `ci.yml` and `phantom_game_log_guard.yml`, the only `pull_request` workflows, reference no secrets, and none uses `pull_request_target`. This is now pinned by a test. |
| S-7 | `ci.yml` ran with the default token permissions | Over-privileged | Low | It was the only workflow with no `permissions:` block. **Fixed:** `permissions: contents: read`. |
| S-8 | `USER_AUTH_SECRET` falls back to `SECRET_KEY` | Over-scoped | Medium | `backend/config.py:158-161`. When unset, one key signs both sessions and user tokens, and a rotation of either invalidates both. Production does not validate `USER_AUTH_SECRET` separately. Whether it is set in production is **UNVERIFIED**, because Render environment access is blocked. |
| S-9 | Distribution dispatch token held by Render | Over-scoped | Medium | `BASEBALLOS_DISTRIBUTION_GITHUB_TOKEN` (fine-grained, Actions write) is documented as held by the Render Daily and postgame Cron Jobs (`docs/current/SYNC_PIPELINE.md`). A fine-grained token cannot be limited to one workflow, so it can dispatch any workflow, including the write-capable ones. Its expiry and scope are **UNVERIFIED**. |
| S-10 | No rate limiting; sign-in creates users before verification (EOS-011) | Potential (abuse) | High | Unchanged on main (`backend/api/auth.py`). Out of WP-0.2's implementation scope; scheduled for WP-0.5 in the roadmap. |
| S-11 | An unknown `APP_ENV` silently becomes development (EOS-025) | Potential | Medium | `backend/app.py:86-88`. Mitigated: non-production configs refuse a non-local database (`config.py:96-102`). Unchanged. |
| S-12 | CORS keeps localhost origins in production (EOS-025) | Potential | Low | `backend/app.py:125-133`. Unchanged. |

## Audit claims re-checked

| Audit claim | Result |
|---|---|
| EOS-010: "`DATABASE_URL` is provided to 25 of 27 workflows" | Accurate: 25. WP-0.2 adds one workflow with no database secret, so it is now 25 of 28. |
| EOS-010: "repository is public, `main` unprotected, no rulesets" | Confirmed for `main` protection. Public visibility is consistent with the audit and the Vercel and Supabase integrations; it was not re-queried, because no repository-settings tool was available. |
| EOS-010: "no workflow uses `environment:`" | Confirmed. |
| EOS-010: "20 of 27 are one-off 2026 workflows; 8 can write" | Partly. 9 can write: the audit did not count `manual-game-driven-noop-qualification`, which writes ledger rows. |
| EOS-007: "the sync workflow is red by construction" | Confirmed and root-caused. Fixed in WP-0.2; see WP02_OPERATIONAL_HEALTH.md. |
| EOS-008: "no alerting" | Confirmed. A minimal alert is added; see WP02_OPERATIONAL_HEALTH.md. |
| EOS-009: "backups unproven" | Still UNVERIFIED: no provider access. See WP02_BACKUP_RECOVERY.md. |
| "Production database credentials used across numerous workflows" | Accurate as **over-scoped** (S-2). No evidence of **exposure** (S-1). Using a secret in a workflow does not expose its value: GitHub masks it in logs, and no workflow echoes it. |

## Guards added (fail CI if the surface grows)

`backend/tests/test_wp02_workflow_security.py`:

- every workflow declares `permissions:`;
- no `pull_request` workflow references `secrets.*`, and none uses `pull_request_target`;
- the set of workflows that reference `secrets.DATABASE_URL` can only shrink;
- only `baseballos-sync/static-team-story-preview` and `baseballos-generated-distribution/deliver-generated-content` hold `contents: write`, and every `git push` is a fast-forward to `HEAD:refs/heads/main`;
- no tracked file or doc contains a credential-shaped value; `.env` files are examples only.
