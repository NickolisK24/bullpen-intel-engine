# API startup migration recovery

The shared database advanced beyond main's Alembic head `e8a4c2f9b1d6`
to `d2e5f8a1b4c7`, then `e3f6a9b2c5d8`. Main cannot resolve those revisions,
so `flask db upgrade` exits before Gunicorn starts.

Deploy the hotfix through main, then set `SKIP_STARTUP_MIGRATIONS=true` only on
Render's `baseballos-api` and redeploy. Keep root `backend` and start command
`bash scripts/render_start.sh`. Only exact lowercase `true` bypasses migrations;
unset, false, empty, and other values retain the normal fail-closed behavior.
Do not put the override in a shared environment group or integration service.

Daily Edition preparation stays enabled and fail-closed. Its helper imports the
application and calls `ensure_snapshot_for_current_publication`, without resolving
Alembic revisions. The inspected integration migrations retain main's columns;
the writer-fencing triggers do not target `intelligence_surface_snapshots`.
This is source evidence, not a successful run against the live database.
The existing helper can upsert and commit a missing/stale Daily Edition artifact;
it does not advance the trusted publication pointer. The hotfix adds no database
writes or schema operations, but does not make existing startup read-only.

## Production verification

- Confirm the deployed main commit contains this hotfix and the service reaches
  Running/Live. Confirm `feat/sync-pipeline` remains unmerged and isolated.
- With the override enabled, require the explicit migration-skip WARNING,
  Daily Edition completion, and Gunicorn startup/listening/worker logs. There
  must be no migration-applied success message. Without it, migrations must run.
- GET `/api/health`: require HTTP 200 and `status: ok`. This existing route is
  a process check, not database readiness proof; no repository Render health
  path setting was found during inspection.
- Require HTTP 200 and meaningful JSON from `/api/bullpen/dashboard`,
  `/api/bullpen/teams/145/board-v2`, `/api/bullpen/intelligence/tonight`, and
  `/api/bullpen/intelligence/today`. Verify team identity, trusted publication
  identity, current dates, and valid payloads; a 200 unavailable envelope alone
  is insufficient. Accept an empty surface only when its reason is supported.
- Verify Daily Edition's startup result (`ready` or justified `generated`) and
  matching served publication. `no_trusted_publication` requires investigation
  on a populated production database.
- Inspect startup and subsequent request logs for no UndefinedTable,
  UndefinedColumn, Alembic revision errors, or helper failures.
- Verify read-only evidence that this hotfix made no schema/revision or public
  pointer changes. Do not manufacture database writes for verification. Any
  normal artifact write by the retained helper must be reported separately;
  do not claim the entire database stayed unchanged without evidence.

## Rollback and follow-up

Remove the variable (or set it to `false`) and redeploy to restore mandatory
migrations. Reverting the hotfix also restores that behavior. Either action
will reproduce the startup outage while main cannot resolve the database head;
neither is a database repair. Never stamp, manually edit `alembic_version`,
downgrade, or remove integration schema as rollback.

Separately repair production schema ownership: only the production deployment
path should have migration authority; integration/shadow workloads must not
upgrade production. Use a separate integration database or read-only production
credentials where possible. Make schema promotion an explicit controlled
deployment step, then remove the emergency override. Normal application startup
must remain fail-closed. This hotfix does not implement that architecture repair.
