# WP-0.2 Backup and Recovery

**Status:**
- Provider backups: **UNVERIFIED**. No Supabase or Render console or API access from this environment; outbound requests to the provider hosts are refused by the network policy (proxy 403).
- Repository rehearsal tooling: **BUILT AND TESTED** against isolated local databases.

Nothing here claims backups are reliable because a provider advertises them.

## What the evidence says about the database

- The production database is Supabase Postgres. Evidence:
  - the RLS migration `e5b9c3a7d1f4`;
  - a **Supabase Preview** GitHub check, project `jbhzvzlqrledmlqrlzim`, posts on this repository's PRs (seen on PR #910).
- Render hosts the API and Cron Jobs; it is not documented as hosting the database.
- No repository runbook for dump, restore or point-in-time recovery existed before WP-0.2. `docs/current/PRODUCTION_MIGRATION_AUTHORITY.md` calls a restore "a separate incident decision".

## Questions that must be answered in the Supabase dashboard

| Question | Where | Record |
|---|---|---|
| Do daily backups exist, and when was the last one? | Project → Database → Backups | date and time of the latest backup |
| Retention | same | days |
| Is point-in-time recovery enabled? | Project → Add-ons → PITR | yes/no; window |
| Plan tier (Free tier has no downloadable backups) | Organization → Billing | tier |
| Do backups include all schemas (`public`, `auth`, `storage`)? | Backups page / support docs for the tier | yes/no |
| Is there an independent copy outside Supabase? | — | currently **none known** |

Until answered, treat the season record as having **no proven recovery path**. Severity is High; it becomes Critical if backups turn out to be absent (EOS-009).

## Independent copy and rehearsal (`backend/scripts/database_restore_rehearsal.py`)

The tool runs in three steps. Each is safe and none writes to the source:

1. **`dump`**
   - Runs `pg_dump --format=custom --serializable-deferrable` from `SOURCE_DATABASE_URL`, which should be the read-only role in WP02_CREDENTIAL_CONTAINMENT.md, step 1.
   - Writes a manifest with:
     - the dump's sha256 and size;
     - the Alembic head;
     - row counts for `alembic_version`, `pitchers`, `game_logs`, `scheduled_games`, `player_transactions`, `roster_status_snapshots`, `dashboard_snapshots`, `share_artifacts`, `team_state_publication_proofs` and `sync_runs`.
2. **`restore`**
   - Runs `pg_restore --exit-on-error` into `TARGET_DATABASE_URL`.
   - **Refuses** unless the target database name contains `rehearsal`, `restore` or `scratch`.
   - **Refuses** a target equal to the source or to `DATABASE_URL`, and any non-empty target.
3. **`verify`**
   - Recounts the canonical tables in the restored copy and compares them with the manifest and the Alembic head.
   - Exits 1 on any difference, and also when a canonical table was missing from the dump.

Connection strings come only from the environment. Output shows `host:port/db`, never credentials.

### Production rehearsal procedure (founder or operator)

Requires the read-only role, a scratch Postgres (local, or a separate Supabase or Render project), and PostgreSQL 16 client tools.

```bash
export SOURCE_DATABASE_URL='<read-only role URL>'            # never paste into files
python backend/scripts/database_restore_rehearsal.py dump --output /secure/baseballos-$(date -u +%F).dump
createdb baseballos_restore_rehearsal                          # on the SCRATCH server
export TARGET_DATABASE_URL='postgresql://<scratch>/baseballos_restore_rehearsal'
python backend/scripts/database_restore_rehearsal.py restore --input /secure/baseballos-YYYY-MM-DD.dump
python backend/scripts/database_restore_rehearsal.py verify  --manifest /secure/baseballos-YYYY-MM-DD.dump.manifest.json
```

**Pass** (EOS-009 acceptance) means `verified: true`, which requires:
- identical counts for `game_logs`, `scheduled_games` and `share_artifacts`, and every other canonical table;
- the same Alembic head.

Store the dump off-provider (encrypted storage the founder controls). Record its date and sha256 here.

## Evidence from this package

- `backend/tests/test_wp02_restore_rehearsal.py` runs the real `pg_dump` → `pg_restore` → verify round trip between two disposable PostgreSQL 16 databases. It also proves:
  - lost rows are detected;
  - missing canonical tables block a "verified" result;
  - non-scratch, non-empty, source-equal and application-database targets are refused;
  - no credential appears in output.
- Result: 5 passed locally, on PostgreSQL 16.15. CI runs it in shard 1; see WP02_VERIFICATION_REPORT.md.

## Not done (requires access or approval)

- No production dump was taken: there is no read-only role and no access.
- Provider backup existence, retention and PITR are unverified.
- There is no scheduled off-provider dump. It needs the read-only role and a storage destination; it should not be added before step 1 of the containment plan.
