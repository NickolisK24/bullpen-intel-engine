# WP-0.2 Credential Containment

**Status:** Plan only. **No credential was rotated, revoked or moved.** Every step below changes production or repository settings, so each needs founder approval.

There is no confirmed exposure (WP02_SECURITY_FINDINGS.md, S-1), so this is containment of over-scoped credentials, not incident response. Nothing here requires an emergency rotation.

## Credential inventory (names only)

| Credential | Holders (verified from repository files) | Used for | Depends on it |
|---|---|---|---|
| `DATABASE_URL` (full-privilege production role) | 25 GitHub workflows; Render API web service and Cron Jobs (documented, not observable here) | All production reads and writes | API, sync, distribution, every diagnostic |
| `DATABASE_MIGRATION_URL` | `baseballos-production-maintenance.yml` migrate step | Schema migration owner | Migrations only |
| `SECRET_KEY` | 24 workflows; Render | Flask secret; also signs user tokens when `USER_AUTH_SECRET` is unset | All signed sessions and tokens |
| `BASEBALLOS_ADMIN_API_TOKEN` → `ADMIN_API_TOKEN` | 24 workflows; Render | Admin API bearer | Admin routes, production boot check |
| `BASEBALLOS_SYNC_URL` | `baseballos-sync.yml`, `production-health.yml` (new) | Public API URL, not a credential | Health checks |
| `BASEBALLOS_DISTRIBUTION_GITHUB_TOKEN` | Render Daily and postgame Cron Jobs | Dispatches `baseballos-generated-distribution.yml` | Preview publication |
| `GITHUB_TOKEN` (per job) | All workflows | Scoped by each workflow's `permissions:` | Bot pushes (2 jobs) |

## Target state

1. **Two GitHub environments.** Each is restricted with **Deployment branches: `main` only**.
   - `production-read`: a read-only database role (`DATABASE_URL_READONLY`). No reviewers, so scheduled and diagnostic runs are not blocked.
   - `production-write`: the full `DATABASE_URL`, with required reviewer `NickolisK24` for manual write workflows. The scheduled `baseballos-sync.yml` jobs must not require reviewers. Either give them a third environment, `production-scheduled` (main only, no reviewers), or keep them on `production-write` without reviewers.
2. **Repository-level production secrets removed.** With the secrets only in environments limited to `main`, a workflow run from any other branch receives nothing (audit acceptance G-8.4).
3. **A read-only Postgres role for diagnostics.** Grant `SELECT` on `public`, set `default_transaction_read_only = on` and a connection limit, and grant no write privileges or DDL.
4. **A distinct `USER_AUTH_SECRET`.** Set it explicitly, so a `SECRET_KEY` rotation no longer logs every user out and a leak of one does not compromise both.
5. **A narrower dispatch path.** Replace the Render-held fine-grained token (Actions write, which can dispatch *any* workflow) with a GitHub App or a `repository_dispatch`-only mechanism. Until then, keep its expiry short and record it.

## Order of operations (no downtime)

Each step is independently reversible. Do not skip ahead: the scheduled sync must keep its secrets at every step.

1. **Read-only role.** Create it in the database (Supabase SQL editor or `psql` as owner):
   ```sql
   CREATE ROLE baseballos_readonly LOGIN PASSWORD '<generated; store only in the secret manager>' CONNECTION LIMIT 5;
   ALTER ROLE baseballos_readonly SET default_transaction_read_only = on;
   GRANT CONNECT ON DATABASE postgres TO baseballos_readonly;
   GRANT USAGE ON SCHEMA public TO baseballos_readonly;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO baseballos_readonly;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO baseballos_readonly;
   ```
   Verify that a write is refused: `INSERT ...` must fail with `cannot execute INSERT in a read-only transaction`. This role is also the **source** for the backup rehearsal (WP02_BACKUP_RECOVERY.md).
2. **Environments.** Create `production-read` and `production-write` (Settings → Environments), each limited to the `main` branch. Copy the secrets **into** the environments. Keep the repository-level copies for now, so nothing breaks.
3. **Workflow PR.** Add `environment:` to each job that holds a production secret: `production-read` for the 16 read-only workflows, which switch to `DATABASE_URL_READONLY`, and `production-write` for the 9 write-capable ones. Merge it, then confirm one scheduled `baseballos-sync` run and one dispatched read-only diagnostic both succeed.
4. **Remove the repository-level copies** of `DATABASE_URL`, `SECRET_KEY` and `BASEBALLOS_ADMIN_API_TOKEN`. Then dispatch a diagnostic from a non-`main` branch: it must fail to receive the secrets (G-8.4).
5. **Rotate `DATABASE_URL`'s password.** Optional, and not required by any evidence of exposure. Rotate during a quiet offseason window, in this order:
   1. create the new password;
   2. update Render's environment group (this redeploys the API, so watch it go Live);
   3. update the GitHub environment secret;
   4. run `production-health.yml`;
   5. revoke the old password.
6. **Set `USER_AUTH_SECRET`** on Render. This invalidates outstanding magic-link and bearer tokens, so users sign in again; announce or accept that.
7. **Archive the one-off 2026 workflows** that have already run: the `official_pitching_line_*`, `phantom_game_log_reconciliation`, `unresolved_appearance_team_*` and `appearance_team_backfill_2026` workflows. Delete them from `main`. Their records stay in `docs/decisions/`. Doing this removes 9 of the 25 secret holders, including 5 of the 9 write paths. The roadmap places workflow deletion in Phase 3b; it can move earlier on founder approval.

## What WP-0.2 changed now

- `ci.yml` declares `permissions: contents: read`.
- The new `production-health.yml` holds **no** database credential and only `contents: read`.
- `backend/tests/test_wp02_workflow_security.py` freezes the secret surface so it can only shrink.

## Verification commands

```bash
# Workflows still holding the production DB secret (target: 0 at repo level after step 4)
grep -l 'secrets.DATABASE_URL' .github/workflows/*.yml | wc -l
# Guards
cd backend && python -m pytest -q tests/test_wp02_workflow_security.py
```
