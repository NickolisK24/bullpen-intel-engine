# Production migration authority

This package prevents further automatic schema promotion by integration work.
It does not reconcile main's migration lineage or authorize deployment.

## Incident and migration-path audit

PR #834 restored the API at main commit `a56c4bf90197aaf96a021355f66ef544e8842044`.
The database is at `e3f6a9b2c5d8`; main's graph ends at `e8a4c2f9b1d6`.
The integration graph has 16 subsequent revisions, ending at the database head.
None of these revisions is copied, rewritten, stamped, or downgraded here.

Repository-wide command/import searches found these executable paths:

| Path | Before | After |
| --- | --- | --- |
| `backend/scripts/render_start.sh` | Unconditional upgrade on integration base; main has PR #834's exact emergency skip | Canonical startup authority decision, then unchanged Daily Edition and server |
| `.github/workflows/baseballos-sync.yml`, `shadow_sp` | Upgrade before shadow work | Verify only before work; shadow service independently enforces mode and exact head |
| Same workflow, `repair_final` | Upgrade before repair dispatch | Verify only before dispatch; repair CLI also enforces mode and exact head |
| `.github/workflows/baseballos-production-maintenance.yml`, `migrate` | Manual upgrade from selected workflow ref using shared runtime secret | Deliberate main-only, commit/target-checked promotion with dedicated credential |
| `.github/workflows/ci.yml`, `postgres-migrations` | Upgrade disposable localhost PostgreSQL | Same upgrade with explicit owner mode; no production secrets |
| Flask/Alembic CLI through `backend/migrations/env.py` | No authority guard | Every mutation context requires explicit owner authority; current-head display remains read-only |

The live Render cron `baseballos-continuous-shadow-detect` was inspected read-only:
branch `feat/sync-pipeline`, every three minutes, command
`python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation`.
It has no upgrade in its start command. The accidental upgrade paths were the
GitHub shadow/repair workflow steps, before the existing expected-head check.

`app.py` registers Flask-Migrate without upgrading. Daily Edition preparation
can write its existing artifact but never migrates schema. Normal daily,
postgame, morning, and continuous cron scripts do not run schema upgrades.
The CU-01P/CU-04/CU-05 proof scripts and test fixtures create disposable schemas;
CU-01P directly exercises migration upgrade/downgrade functions in that local
proof database. Historical setup instructions describe manual Flask migration
commands; those now encounter the same Alembic authority guard. No other
executable upgrade caller was found. SQL privileges remain the enforcement
boundary against arbitrary scripts or old deployed code.

## Exact configuration contract

`DATABASE_MIGRATION_MODE` accepts only `owner`, `verify_only`, or `disabled`.
Whitespace, alternate case, empty values, and arbitrary truthy values are invalid.

- `owner`: may mutate schema. Production also requires platform main provenance
  (`GITHUB_REF=refs/heads/main` or `RENDER_GIT_BRANCH=main`, with no conflicting
  supplied ref). `SYNC_PIPELINE_SHADOW_MODE` must be absent or exactly `false`.
- `verify_only`: may inspect the current head; cannot upgrade. Shadow/repair
  requires this exact mode and head `e3f6a9b2c5d8` before any work begins.
- `disabled`: grants no migration authority. Ordinary runtime tasks do not
  inspect schema because of this setting. Schema-gated startup and shadow work
  refuse to proceed in this mode unless the API emergency skip is active.

Missing mode never grants authority. On this package's startup path it fails
closed unless exact `SKIP_STARTUP_MIGRATIONS=true` is active. This is an
intentional configuration requirement for future adoption; deployed main is
untouched and retains PR #834 behavior. With explicit owner mode, normal startup
still upgrades, prepares Daily Edition, and starts Gunicorn; failure stops it.
With verify-only mode, startup checks the repository's single head instead.

The emergency skip bypasses only the startup schema step, never Daily Edition.
It permits an absent mode (logged as disabled), rejects an invalid mode, and
does not grant upgrade authority. Promotion rejects an active emergency skip.
Keep the override on `baseballos-api` until lineage reconciliation is complete.
Never set it on integration/shadow services or a shared environment group.

## Deliberate schema promotion

After this mechanism is separately reviewed for main, use Production Maintenance
on **main**, operation `migrate`, existing confirmation
`RUN_PRODUCTION_MAINTENANCE`, and an explicitly reviewed `migration_target_head`.
Only that step receives `DATABASE_MIGRATION_MODE=owner` and binds the dedicated
`DATABASE_MIGRATION_URL` secret as its `DATABASE_URL`.

Equivalent operator command from a clean checkout of the reviewed main commit:

```sh
python -m scripts.database_migrations promote \
  --source-branch main --expected-commit <full-reviewed-main-sha> \
  --target-head <reviewed-alembic-head>
```

Run from `backend`, with explicit owner mode, production configuration and
trusted platform main provenance. Refresh `origin/main` first. Both HEAD and
origin/main must equal the supplied full SHA; tracked changes are refused.
The command checks the single repository target, prints source/commit and
current/target heads, upgrades, then verifies the resulting exact head. It never
starts the server or scheduler. A nonzero result blocks promotion; do not stamp,
downgrade, change a version row, or attempt automatic repair on mismatch.

For drift detection, run `python -m scripts.database_migrations verify` with
verify-only mode. Reads use a separate connection and PostgreSQL transaction
explicitly set read-only. Missing/multiple/unknown heads fail closed. Shadow
retains its established `expected_migration_head_..._got_...` error contract.

## Credentials and rollout work still required

Current workflows share `secrets.DATABASE_URL`; Render supplies per-service
`DATABASE_URL`. Local configuration loads it from the environment/dotenv. No
credential values were exposed and no provider configuration was changed.

Provider-side work is required before claiming a database privilege boundary:

1. Create a dedicated schema-owner/migrator role and store its credential only
   as the protected production `DATABASE_MIGRATION_URL` secret. Restrict secret
   access to reviewed main promotion; use an approval-protected deployment
   environment at the provider/repository boundary.
2. Give API runtime and integration distinct non-owner, non-superuser roles,
   without CREATEDB, CREATEROLE, schema-owner membership, or role escalation.
   Transfer ownership of existing objects away from these runtime roles;
   revoking grants from an object owner is insufficient.
3. Revoke database/schema CREATE privileges (including inherited/PUBLIC grants)
   and all writes to `alembic_version` from runtime/integration. Grant SELECT on
   it for verification. Grant only needed data-table DML and sequence usage;
   restrict DDL-capable functions. Integration needs data writes for its bounded
   jobs, so a globally read-only credential is not generally sufficient.
4. Rebind each service's DATABASE_URL without sharing the migrator credential.
   Verify allowed DML and denied DDL/version writes in an isolated provider test
   database first. Prefer a separate integration database wherever practical.
5. Before later deploying this package to integration, configure only its
   runtime mode as verify_only. Missing mode deliberately stops its next run.
   Do not deploy or change the recovered API as part of this package.

Existing deployments and provider roles do not change when this branch is
committed. Repository guards and tests protect these entrypoints; they cannot
revoke credentials held by old code or prevent an external privileged client.

## Exit condition and rollback

Outcome A is the repository boundary preventing automatic integration upgrades.
Outcome B remains required: reconcile production's `e3f6a9b2c5d8` lineage with a
reviewed main-owned graph, without merging all integration behavior. Prove the
controlled owner migration and normal API startup against that reconciled graph,
then remove `SKIP_STARTUP_MIGRATIONS=true`. Do not remove it before this proof.

Before deployment, rollback is reverting this package on its topic branch.
After future adoption, stop integration jobs before reverting any authority
guard: an old workflow could otherwise regain its automatic upgrade path.
Keep credential isolation and the API emergency override until the separate
lineage repair is proven. Never roll back by downgrading or changing schema
version metadata. Public baseball behavior and publication authority are unchanged.

## Local validation

The focused authority/shadow/recovery-startup/maintenance group passed 151 tests.
The broader PostgreSQL-backed migration, fencing, pipeline, publication, and CI
contract group passed 395 tests. After centralizing head reads, the focused
151-test group passed again on PostgreSQL. A fresh isolated PostgreSQL database
upgraded through the full graph to e3f6a9b2c5d8 under owner mode; verify-only and
Flask current-head inspection then succeeded. These are local proofs, not hosted
CI, deployed integration enforcement, or production lineage reconciliation.
