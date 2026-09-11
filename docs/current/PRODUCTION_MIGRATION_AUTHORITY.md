# Production migration authority

Status: repository recovery candidate; neither Outcome A nor this package has
been deployed or adopted operationally. No production changes are authorized
by this document. Normal sync-pipeline development remains paused until both
packages and the live recovery exit checks are complete.

## Ownership and lineage

Main's controlled production deployment/promotion path owns production schema.
Integration/shadow is non-authoritative and must use verify-only execution.
Application configuration is a fail-closed entrypoint boundary; database roles
are required to prevent arbitrary privileged clients or old deployments from
bypassing it.

The incident was a missing-history problem, not two Alembic branches. Main at
`a56c4bf90197aaf96a021355f66ef544e8842044` knew 64 revisions through
`e8a4c2f9b1d6`. Integration extended that same chain by 16 revisions, and advanced
the shared database to `e3f6a9b2c5d8`. Main could not resolve that revision during
startup. PR #834 restored serving with the exact emergency skip.

This main-based package promotes those 16 immutable definitions from Outcome A
commit `0ce244420df6de3ab54f1d952d794b112b56deb7`, plus its production-facing
migration controls. It imports no integration models, services, routes or jobs.
There is no new migration and no new target ID. Old main -> 16 real historical
revisions -> `e3f6a9b2c5d8` becomes the complete main-owned graph. The similarly
named `e3f6a9b2d5c8` remains an earlier, distinct revision.

See [the graph and production evidence audit](PRODUCTION_LINEAGE_AUDIT.md) and
[the immutable identity manifest](../../backend/migrations/production_lineage.json).
Observed production head on 2026-09-11 was exactly `e3f6a9b2c5d8`; recheck before
rollout. Reconciliation at that head is a no-op, including version metadata.
A fresh database executes all 80 historical definitions normally.

## Exact configuration

`DATABASE_MIGRATION_MODE` accepts exactly `owner`, `verify_only`, or `disabled`.
No whitespace, alternate case, empty string or arbitrary truthy value is accepted.

- `owner`: may execute migrations. With `APP_ENV=production`, require trusted
  platform main provenance: `GITHUB_REF=refs/heads/main` or
  `RENDER_GIT_BRANCH=main`; conflicting supplied refs fail closed.
  `SYNC_PIPELINE_SHADOW_MODE` must be absent or exactly `false`.
- `verify_only`: inspect one expected head; never upgrade. Outcome A requires
  this exact mode in shadow and repair before work begins, with required head
  `e3f6a9b2c5d8`. Missing, multiple, older or unknown heads stop execution.
- `disabled`: grants no authority. Schema-gated startup refuses it except when
  the API emergency skip is active; unrelated runtime paths acquire no new
  migration behavior.

Missing mode fails closed where authority is required. The explicit exception
is exact `SKIP_STARTUP_MIGRATIONS=true`: startup logs a WARNING and bypasses only
schema startup, permits absent mode (logged disabled), and rejects invalid mode.
It neither grants ownership nor bypasses Daily Edition preparation. Promotion
refuses this emergency setting. Keep it API-only until the exit sequence below.

Normal startup in owner mode prints current/target heads, runs the guarded
upgrade, verifies the resulting head, prepares Daily Edition and starts Gunicorn.
Any failure blocks serving. Daily Edition can write its existing artifact; this
is not a globally read-only startup. Its semantics are unchanged.

## Migration execution paths

| Entrypoint | Authority after its package is adopted |
| --- | --- |
| `scripts/render_start.sh` | Canonical helper; owner upgrade, verify-only head check, or exact emergency skip. Then existing Daily Edition and server. |
| `scripts/database_migrations.py promote` | Deliberate owner-only, main commit/target-pinned promotion; no server or scheduler. |
| Production Maintenance `migrate` | Main-only manual dispatch invoking promote, dedicated `DATABASE_MIGRATION_URL` secret, explicit target. |
| CI `postgres-migrations` | Explicit owner; disposable localhost PostgreSQL only. |
| Direct Flask/Alembic via `migrations/env.py` | Mutation contexts require owner; current-head inspection remains available without ownership. |
| Integration `baseballos-sync.yml` shadow/repair steps (Outcome A) | Replaced former upgrades with verification; service/repair entrypoints independently check mode/head. |
| Render `baseballos-continuous-shadow-detect` (Outcome A) | Existing `run_sync_pipeline_shadow.py` cron command; verify before work, no automatic upgrade. |

Repository searches also found historical manual setup examples and disposable
migration-proof/test helpers. App initialization only registers Flask-Migrate;
Daily Edition, daily/postgame/morning/continuous cron and public runtime do not
upgrade schema. Named-path tests reject new uncontrolled upgrade callers.
The live integration cron inspected for Outcome A uses `feat/sync-pipeline`,
every three minutes, with `python backend/scripts/run_sync_pipeline_shadow.py
--max-jobs 24 --include-morning --include-continuous-observation`; it has no
upgrade in its Render command. Its old workflow steps can still migrate until
Outcome A is adopted. Do not mistake a local commit for live enforcement.

## Deliberate promotion

After review and green CI, use Production Maintenance on **main**, operation
`migrate`, confirmation `RUN_PRODUCTION_MAINTENANCE`, target
`e3f6a9b2c5d8`. The migration step alone receives owner mode and the dedicated
`DATABASE_MIGRATION_URL` as DATABASE_URL. Protect this secret and main deployment
permissions externally; no such provider change has been made here.

Equivalent operator command from `backend` in a clean checkout:

```sh
python -m scripts.database_migrations promote \
  --source-branch main --expected-commit <full-reviewed-main-merge-sha> \
  --target-head e3f6a9b2c5d8
```

Use explicit owner mode, production configuration, trusted main provenance and
the approved migration credential; keep emergency skip absent/false in this
one-off process. Fetch first: both HEAD and origin/main must equal the reviewed
SHA. The command checks source and target, prints current/target, upgrades and
verifies final head. It refuses tracked drift, mismatched source/target or lack
of authority. Never log a connection URL.

For read-only preflight, use `DATABASE_MIGRATION_MODE=verify_only` with
`python -m scripts.database_migrations verify`. Reads use a separate PostgreSQL
transaction explicitly set read-only. Any mismatch stops the rollout; investigate
source/history and catalog evidence, never stamp or automatically repair it.

## Future rollout and recovery exit

These are operator steps for a later authorized rollout, not actions performed
by this package:

1. Keep integration/shadow development and schema promotion paused. Review,
   push and merge Outcome A into `feat/sync-pipeline` after its CI passes.
   Adopt its workflow/cron controls with exact verify-only configuration before
   resuming any integration execution. Confirm the deployed commit and verify
   logs; retire old upgrade-capable workflow runs and credentials.
2. Establish the credential boundary below. Recheck the production head with
   read-only access: exactly `e3f6a9b2c5d8`, one row; repeat catalog comparison
   if any integration activity or schema drift occurred. Abort on mismatch.
3. Review this main-based PR, run all CI including PostgreSQL/shard checks,
   then merge only this bounded package into main. Keep the API's existing
   emergency skip enabled during its automatic deployment. Do not manually
   trigger a duplicate deployment when auto-deploy runs.
4. Verify the API deployed the exact reviewed main merge SHA. From that same
   clean commit, perform verify-only preflight and the deliberate owner
   promotion above. For the observed production state, current and target must
   both be `e3f6a9b2c5d8`; no `Running upgrade` step is expected. Save sanitized
   logs and confirm the head afterward. Stop on any unexpected DDL or mismatch.
5. Set `DATABASE_MIGRATION_MODE=owner` on baseballos-api only, with trusted
   Render main provenance and the approved migration credential available to
   the startup owner process. Keep `SYNC_PIPELINE_SHADOW_MODE` absent/false.
   Once steps 1-4 pass, remove SKIP_STARTUP_MIGRATIONS or set it exactly `false`.
   This needs a controlled restart/deployment. Environment edits may themselves
   deploy; observe that deployment before requesting another.
6. Observe, in order: `mode=owner emergency_skip=false`, current/target head
   `e3f6a9b2c5d8`, migration execution and successful verification, Daily Edition
   begins/completes, Gunicorn boots, Render Live. There must be no skip WARNING.
7. Require 200 from `/api/health`, `/api/bullpen/dashboard`,
   `/api/bullpen/teams/145/board-v2`, `/api/bullpen/intelligence/tonight`, and
   `/api/bullpen/intelligence/today`. Validate board and current surfaces against
   real publication identities/current baseball context, not merely HTTP status.
   Verify Daily Edition's existing artifact behavior. Inspect logs for
   UndefinedTable, UndefinedColumn, SQLAlchemy and Alembic errors. Confirm
   version remains e3f6a9b2c5d8 and integration is still verify-only.
8. Only after these live checks pass is the emergency override retired and
   normal integration development eligible to resume. Carry the main-owned
   history/contract into integration under review; identical historical files
   need no renaming or reparenting. Do not merge integration runtime into main.

Local exit proof runs full migrations on PostgreSQL, preserves seeded main and
integration rows across repeated no-op upgrades, starts the actual main app and
Daily Edition helper, and on Linux boots default Gunicorn and verifies HTTP
health with owner mode and no skip. The empty-publication helper path is covered
there; populated Daily Edition behavior has separate application tests and must
also be observed during the live rollout. Local proof is not production recovery.

## External database-role work

Existing workflows use `secrets.DATABASE_URL`; Render supplies per-service
DATABASE_URL. Repository code does not establish or revoke PostgreSQL roles.
Before claiming durable production isolation, an operator must:

- Use a dedicated schema-owner/migrator role only in protected main promotion
  and explicitly authorized production startup. Keep DATABASE_MIGRATION_URL
  inaccessible to integration and unreviewed workflow refs.
- Give integration a distinct non-owner/non-superuser data role without
  CREATEDB, CREATEROLE, schema-owner membership or role escalation. Remove
  inherited/PUBLIC CREATE privileges, ownership and DDL-capable function access.
  Revoking grants from an object owner alone is insufficient.
- Deny integration writes to alembic_version; permit SELECT for verification.
  Grant only needed table DML and sequence usage. Integration needs bounded data
  writes, so blanket read-only credentials may not support its jobs. Prefer a
  separate integration database where practical.
- Rebind services and retire shared privileged credentials; test allowed DML
  and denied DDL/version writes in an isolated provider test database first.
- Separate production runtime from migration credentials when introducing a
  dedicated deployment migration phase. Until then, requested API owner startup
  uses the migration-capable credential; it does not imply least-privilege
  runtime separation has already been achieved. A future runtime-only process
  can use verify_only after the controlled promotion phase.

## Rollback constraints

Before adoption, discard/revert the topic package only. After adoption, prefer
rolling back runtime while retaining the immutable migration definitions and
Outcome A controls. If reverting to PR #834's main build, restore the API-only
exact emergency skip before restart; that build cannot resolve the newer head.
Do not remove the history and restart without the override.

Do not downgrade, stamp, change version rows, remove fences, drop tables or erase
retained data. Stop integration before reverting any authority control; keep
credential isolation intact. A database restore is a separate incident decision,
not this package's rollback. Schema history remains forward-owned by main.
