# SEC-01: Supabase RLS and database exposure hardening

## Summary

Supabase project `jbhzvzlqrledmlqrlzim` exposes the `public` schema through
PostgREST. Its security advisor reported:

- `rls_disabled_in_public` (ERROR) on 89 tables;
- `function_search_path_mutable` (WARN) on 9 functions.

With Supabase's default grants, anyone holding the project's public (anon) API
key could read and write every BaseballOS table directly. The live grants were
not read from this sandbox; the advisor finding plus Supabase's defaults make
this the working assumption. That includes user
emails, subscribers, traffic analytics and the whole sync control plane.

Migration `e5b9c3a7d1f4` makes the storage layer deny-by-default for PostgREST
roles:

- it enables row level security (not FORCE) on all 89 tables, by explicit
  name, with no policies;
- it revokes the `anon` and `authenticated` table and owned-sequence
  privileges;
- it pins `search_path = public, pg_temp` on the 9 functions.

The migration first proves from the catalog that no trusted backend role would
be restricted. If one would be, it refuses and changes nothing.

No product, sync, publication or response-shape behavior changes.

## Threat model

| Actor | Capability before SEC-01 | After SEC-01 |
| --- | --- | --- |
| Anyone with the anon API key. It is public by design in Supabase, e.g. `https://<ref>.supabase.co/rest/v1/<table>`. | Full `SELECT/INSERT/UPDATE/DELETE` on all 89 tables via Supabase's default `GRANT ALL ... TO anon`: user emails, subscribers, traffic rows, sync jobs, repair requests, publications. Writes could corrupt publication authority or inject product content. | No table privileges and no RLS policy: `permission denied`. |
| A Supabase Auth user (`authenticated`) | The same as anon. BaseballOS never issues Supabase Auth sessions, but self sign-up may be enabled on the project. | Denied, as for anon. |
| `rpc/<function>` via PostgREST | `baseballos_selector_resources` is callable (`EXECUTE` is granted to PUBLIC by default). It is `SECURITY INVOKER`, so it runs with the caller's table access. | It still runs with the caller's access, which is now none. |
| A search-path hijack (an object shadowing a `public` name through a caller-controlled `search_path`) | The functions resolve unqualified names through the caller's `search_path`, including `pg_temp` first if the caller arranges it. | Fixed to `public, pg_temp`, with `pg_temp` last. |
| The BaseballOS backend (Render API and GitHub Actions jobs) | Full access. | Unchanged: the table owner or BYPASSRLS roles are exempt, and the migration proves this. |

Out of scope: the credentials themselves (see "Secret and history audit"),
network restrictions, and Supabase Storage/Auth configuration.

## Access-model audit

| Question | Finding | Evidence |
| --- | --- | --- |
| Production backend DB role | A direct PostgreSQL connection via `DATABASE_URL`: Render's per-service value and the GitHub Actions secret `DATABASE_URL`. Migrations use either Render startup in `DATABASE_MIGRATION_MODE=owner` or the dedicated `DATABASE_MIGRATION_URL` secret (Production Maintenance `migrate`). The concrete role name is outside the repository and was not observable from this sandbox. | `backend/config.py`; `.github/workflows/*.yml`; `docs/current/PRODUCTION_MIGRATION_AUTHORITY.md` |
| BYPASSRLS / table owner | Not assumed. The migration evaluates it in production at apply time (see "Backend safety proof"). `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` itself requires ownership, so the migration can only succeed when run as the owner. | Migration guard |
| Supabase client keys in the repo, frontend or runtime | None. No `SUPABASE_*`, `VITE_SUPABASE*` or `NEXT_PUBLIC_SUPABASE*` variables, anon keys or service-role keys. `frontend/.env.example` defines only `VITE_API_BASE_URL`, `VITE_APP_ENV`, `VITE_RELEASE_SHA` and `VITE_SENTRY_DSN`. | Repo-wide search; env example history |
| Frontend calls Supabase directly | No. There is no `@supabase/supabase-js` dependency, no `createClient` and no `supabase.from(`. The frontend calls only the BaseballOS API. | `frontend/package.json`; `test_no_client_talks_to_supabase_directly` |
| Backend uses Supabase REST | No. There are no `*.supabase.co/rest/v1` calls. The only Supabase references are the stack label, the URL-scheme normalization comment and the local-development denylist of Supabase hosts. | Repo-wide search |
| anon/authenticated used intentionally | No. BaseballOS identity is its own magic-link bearer auth (`utils/identity.py`), not Supabase Auth. `auth.uid()` appears nowhere. | `models/user.py`; `utils/identity.py` |
| Tables meant for direct public REST reads | None. | The consumer search above |
| Tables meant for user-scoped direct REST access | None. `/api/me` and follows go through the Flask API with BaseballOS bearer tokens. | `api/me.py` |
| service_role usage | None in the repo, workflows or frontend. | Repo-wide search |

**Conclusion:** the BaseballOS API is the only public surface. No table has a
direct-access contract, so deny-by-default with no policies is correct and
complete. No access-model decision is outstanding.

## Table classification (89)

The posture is the same for every category: RLS on, no policy, and no client
privileges. The classification records why no category needs an exception. It
lives in the migration's explicit lists and is checked by tests.

### A. Strict internal (43)

Control plane, source ingestion, mutation logs, audits, certification, repair,
queues and closures:

`atomic_publication_cache_handoffs`, `availability_backtest_results`,
`baseball_date_closure_blockers`, `baseball_date_closure_versions`,
`baseball_date_closures`, `canonical_impact_plan_entities`,
`canonical_impact_plan_mutations`, `canonical_impact_plans`,
`compatibility_write_events`, `derived_cohort_inputs`, `editorial_post_history`,
`final_game_mutations`, `game_ingestion_work_items`, `game_observation_states`,
`legacy_read_audit_runs`, `legacy_read_divergences`, `live_game_mutations`,
`official_pitching_line_repair_executions`, `pitcher_season_ledger_coverage`,
`play_by_play_processed_games`, `player_transaction_sync_windows`,
`postgame_processed_games`, `pregame_context_mutations`,
`provisional_pitching_appearance_states`, `repair_request_blockers`,
`repair_request_chunks`, `repair_requests`, `roster_membership_mutations`,
`share_artifact_generation_audits`, `source_fetch_attempts`,
`source_observations`, `source_payload_artifacts`, `source_subjects`,
`sync_certification_checks`, `sync_certification_runs`, `sync_failures`,
`sync_job_attempts`, `sync_jobs`, `sync_legacy_transition_states`,
`sync_run_scopes`, `sync_runs`, `sync_schedule_attempts`,
`team_state_publication_proofs`.

### B. User-private (6)

`users` (emails), `user_followed_teams`, `audience_subscribers`,
`traffic_internal_visitors`, `traffic_page_views` and `traffic_share_actions`.
Supabase Auth is not used, so there are no owner-scoped policies: direct access
is denied entirely.

### C. Public product data (39)

The data is public baseball information or published read models, but the
storage shape contains unpublished or pending rows, superseded versions and
operational metadata. The BaseballOS API is the contract.

`atomic_publication_artifacts`, `atomic_publication_current`,
`atomic_publications`, `completed_game_contexts`, `composed_read_components`,
`composed_read_evidence_citations`, `composed_reads`, `dashboard_snapshots`,
`derived_cohort_snapshots`, `derived_intelligence_cohort_domains`,
`derived_intelligence_cohorts`, `evidence_citations`, `evidence_objects`,
`fatigue_scores`, `final_game_versions`, `final_pitching_appearance_versions`,
`game_logs`, `game_pitch_events`, `game_play_by_play_events`,
`game_pregame_context_versions`, `intelligence_surface_snapshots`, `pitchers`,
`player_transaction_versions`, `player_transactions`, `prospects`,
`roster_membership_intervals`, `roster_status_snapshots`, `scheduled_games`,
`share_artifact_assets`, `share_artifact_evidence`, `share_artifact_relations`,
`share_artifacts`, `slate_games`, `team_game_pitching_splits`,
`team_progressive_publications`, `team_public_current_pointers`,
`team_public_publications`, `tonight_intelligence_snapshots` and
`tonight_publications`.

### D. Migration metadata (1)

`alembic_version`.

A clean migration to `c3e7a1d9f5b2` produces exactly these 89 tables, with no
views, matching the advisor count. The test suite asserts that the explicit
list equals the migrated schema.

## Backend safety proof

PostgreSQL applies RLS only to a role that is not a superuser, lacks
BYPASSRLS, and does not have the privileges of the table owner. This holds
because FORCE is not used. Before changing anything, the migration runs a
catalog query over **every** role in the database, not just the one it
connects as. It lists any role that:

- is not a superuser, not BYPASSRLS, not a predefined `pg_*` group role, and
  not `anon` or `authenticated`;
- holds table or column privileges on a protected table;
- is not a member of that table's owner (`pg_has_role(..., 'USAGE')`, the same
  test PostgreSQL uses for the owner exemption).

If any such role exists, the upgrade raises
`sec01_rls_would_restrict_trusted_roles: [<role names>]` inside the migration
transaction and changes nothing.

This proves the property for any credential Render or GitHub Actions uses,
whichever role it authenticates as:

- a role without privileges cannot read these tables regardless of RLS;
- a role with privileges passes only if RLS cannot apply to it.

The `service_role` default grants do not block the guard, because that role is
BYPASSRLS.

FORCE ROW LEVEL SECURITY is **not** used. Its only effect would be to subject
the owner (the backend) to RLS, which is the opposite of the goal.

**Refusal behavior:** a refused startup migration fails that deploy under the
existing migration authority. Render keeps the previous deploy serving. The
production head stays `c3e7a1d9f5b2`, and the new code does not depend on the
new revision (there is no model or query change), so sync keeps running.
Resolve the refusal by making each named role the owner, making it BYPASSRLS,
or revoking its privileges, then redeploy.

## Grant strategy

The migration revokes the least privilege possible from `anon` and
`authenticated`:

- `REVOKE ALL` on the 89 tables and on the serial or identity sequences they
  own. The sequences are derived from the explicit table list via `pg_depend`.
- The step runs only when those roles exist, so it is a no-op on CI and local
  PostgreSQL.

RLS and privileges are independent layers. The test re-grants a table to
`anon` inside a transaction and shows RLS still returns 0 rows and rejects
inserts.

The following are unchanged:

- `service_role`: the Supabase admin role, BYPASSRLS, unused by BaseballOS.
- Schema `USAGE`.
- Default privileges for future tables.
- Function `EXECUTE`. It stays granted to PUBLIC, and all functions are
  invoker-rights.

Future tables are covered by the schema-wide RLS test instead.

No PUBLIC table grants exist before or after.

## Function search_path remediation

All 9 functions are `LANGUAGE plpgsql`, `SECURITY INVOKER` and owned by the
migration role. None is `SECURITY DEFINER`.

- The 8 `baseballos_guard_*` functions are trigger functions (writer fences).
- `baseballos_selector_resources(text, jsonb)` is a helper the selector fence
  calls.

Their bodies reference unqualified `public` tables:

- `final_game_versions`
- `compatibility_write_events`
- `pitchers`
- `roster_membership_intervals`
- `scheduled_games`
- `dashboard_snapshots`
- `atomic_publication_artifacts`

They also call `baseballos_selector_resources` and built-ins from
`pg_catalog`, which is always searched first. No extension-schema objects are
referenced.

The fix is `ALTER FUNCTION ... SET search_path = public, pg_temp`:

- bodies (`prosrc`), security and volatility are unchanged;
- names resolve exactly as before under the default `"$user", public` path,
  since no `"$user"` schema is referenced.

Bodies were not rewritten, so the behavior is preserved exactly. The lineage
proof asserts identical function bodies and trigger definitions.

## Migration design

- `backend/migrations/versions/e5b9c3a7d1f4_enable_rls_deny_by_default.py`
  revises `c3e7a1d9f5b2` and is a single linear transition.
- It uses explicit table and function lists. It does not enumerate tables at
  runtime, and it refuses if a listed table is missing.
- It is deterministic DDL with no data changes.
- It is PostgreSQL-only (a no-op on other dialects, which the migration chain
  does not support anyway).
- A single migration is used: every table gets the same posture, so phasing
  would add ordering risk without reducing blast radius.

### Rollback

- **Preferred:** leave RLS on. Any trusted-role problem is prevented by the
  guard up front.
- **Emergency rollback:** `flask db downgrade c3e7a1d9f5b2` under the existing
  migration authority, as an owner-mode, reviewed operation. It:
  - resets the function search paths;
  - re-grants `ALL` on the tables and owned sequences to `anon` and
    `authenticated` (Supabase's default, i.e. the exact pre-SEC-01 exposure);
  - disables RLS.

The test proves downgrade restores the previous table and function state and
anon access, and that re-upgrading reapplies SEC-01. Downgrading re-opens the
advisor findings, so use it only to restore service.

## Test evidence

`backend/tests/test_sec01_supabase_rls.py` covers the following.

**Static checks:**

- The four categories are a disjoint partition of 89 tables (43/6/39/1).
- Every migration-defined function is in the hardened list (9).
- No client talks to Supabase directly: no frontend dependency, no client or
  key references in the frontend, backend or workflows.
- The migration never uses FORCE and never creates policies.

**PostgreSQL, Supabase-like setup:**

- The setup has a non-superuser, non-BYPASSRLS owner login role; `anon` and
  `authenticated` with Supabase's default table and sequence grants; and a
  BYPASSRLS `service_role`.
- **Before:** at `c3e7a1d9f5b2`, 0 of 89 tables have RLS, anon can read user
  emails and authenticated can insert sync runs. This reproduces the advisor
  finding.
- **Guard:** a non-owner, non-BYPASSRLS role with `SELECT` on `sync_runs` makes
  the upgrade refuse. The head, every table and every function are unchanged.
- **After:**
  - every public table has RLS and none has FORCE;
  - `pg_policies` is empty (the policy allowlist);
  - `anon` and `authenticated` hold no table, column or sequence privileges;
  - there are no PUBLIC grants;
  - function bodies are identical and `proconfig` is the hardened path.
- **Untrusted roles:** for both `anon` and `authenticated` (via `SET ROLE`, as
  PostgREST does):
  - `SELECT` on each of the 89 tables fails;
  - `INSERT`, `UPDATE` and `DELETE` fail.
  - With a grant re-added, RLS still shows 0 rows, updates and deletes affect
    0 rows, and inserts violate row-level security.
- **Backend owner:**
  - reads, inserts, updates and deletes all work;
  - the schedule fence trigger (hardened `search_path`) resolves its tables
    during an update;
  - `service_role` still reads.
- **Downgrade:** restores the exact prior state and anon access, and
  re-upgrading reapplies SEC-01.
- **Clean database:** a fresh migration to `e5b9c3a7d1f4` yields exactly the
  classified tables. At head, every table has RLS, with no FORCE and no
  policies. This is the **schema-wide guard**: a future migration that adds a
  public table without RLS fails it.

**Lineage** (`test_production_lineage.py`): the existing-database upgrade
`c3e7a1d9f5b2 -> e5b9c3a7d1f4` leaves every row, column, index, constraint,
function body and trigger identical. Real production-mode startup (owner mode,
Daily Edition helper, Gunicorn health) passes at the new head.

**Backend regression under RLS:** the full backend suite (4 shards) ran as a
non-superuser, non-BYPASSRLS owner role, with an event trigger enabling RLS on
every table the fixtures create. See "Results" below.

## Advisor expectations

After the migration is applied (by the normal deploy path, never by hand):

- `rls_disabled_in_public`: 0
- `function_search_path_mutable`: 0
- `rls_enabled_no_policy` (INFO): expected on the 89 tables. It is intentional,
  since deny-by-default means no policies.

The production advisor must be rechecked after deployment.

## Secret and history audit

All 2,782 commits across all refs were searched for the following:

- **JWT-shaped strings:** only synthetic HS256 fixtures with a single `sub`
  claim, in traffic-measurement redaction tests. No `iss`, `role` or `ref`
  claims, so none is a Supabase key.
- **Inline-credential PostgreSQL URLs:** only localhost and test placeholders
  (`example.invalid`, `prod-db.internal` in disposable-target tests).
- **Supabase hosts:** only the local-development denylist patterns.
- **Key names:** no `sb_secret_`, `sb_publishable_` or `SUPABASE_*` key
  variables.
- **The project ref:** never committed.
- **Committed `.env` files:** only examples, whose `DATABASE_URL` values point
  at localhost.

**Credential rotation required: no.**

## Known limitations

1. The production role name and attributes were not observed directly. The
   in-migration catalog guard is the proof, and it runs in production at apply
   time.
2. `service_role` keeps Supabase's default grants (BYPASSRLS). Its key is not
   used by BaseballOS. Protect it, or rotate it if it is ever shared.
3. `EXECUTE` on the 9 functions stays granted to PUBLIC. They are
   invoker-rights, so a client gains nothing. Revoking it from PUBLIC could
   affect non-owner writers.
4. Supabase default privileges still grant future tables to `anon` and
   `authenticated`. The schema-wide test forces every new table to get RLS in
   its migration, which denies them regardless.
5. A role granted table privileges **after** this migration (for example a
   future non-owner integration role) would be subject to RLS. It must be the
   owner or BYPASSRLS, or be given explicit policies in a reviewed migration.

## Results

Base: `main` at `22f6303428b22d637cdae2a071b23a68e58d812f`.

| Run | Result |
| --- | --- |
| `test_sec01_supabase_rls.py` (superuser harness, which creates the roles) | 6/6 passed |
| `test_production_lineage.py`, `test_phase0e_exit_docs.py`, `test_migration_authority.py` | 71 passed, 1 skipped |
| Clean database: upgrade to head, downgrade to `c3e7a1d9f5b2`, upgrade again | 89/89 tables with RLS, 0 with FORCE, 9/9 functions hardened; the round trip is clean |
| **Full backend suite under RLS**, as a non-superuser, non-BYPASSRLS owner role (`CREATEDB` only), with RLS enabled on every created table | See the breakdown below |
| `scripts/ci_shard.py verify` | PASS |
| Frontend `npm test` | 1284/1284 passed (no frontend changes) |
| `git diff --check` | clean |

Breakdown of the backend suite under RLS:

- Shard 1: 2256 passed, 1 skipped.
- Shard 2: 2533 passed, 2 skipped.
- Shard 3, excluding `test_postgame_lookback.py`: 3450 passed and 1 skipped.
  The one error is the new SEC-01 test, which needs `CREATEROLE` to build its
  own roles; that is a harness limitation, not an RLS effect.
- `test_postgame_lookback.py`: identical with RLS and on the superuser baseline
  without RLS (4 passed, the same 2 failed). The sandbox blocks the MLB API.
- Shard 4: 1945 passed.

The backend behaves identically as the owner with RLS enabled. That covers:

- Tonight;
- Team Board and Dashboard;
- Pitcher and Matchup;
- schedule refresh;
- Daily, Postgame and recovery-morning governance;
- artifact generation;
- the sync control plane, roster authority and the source observation
  pipeline.

The GitHub Actions results for this branch are in the PR.
