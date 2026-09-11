# Production lineage audit

Audit date: 2026-09-11. No production writes, upgrades, metadata edits, or configuration changes were performed.

## Topology and source identity

Main base: `a56c4bf90197aaf96a021355f66ef544e8842044`. Integration source: `0ce244420df6de3ab54f1d952d794b112b56deb7` (Outcome A). All 64 migration files common to these snapshots have identical Git blobs. Integration adds exactly 16 files; it extends main rather than forking its Alembic history. Both original graphs have one head. The full 80-revision graph has one base (`3b06397ddc6b`) and no branch or merge points.

```text
base -> ... -> d5a8c2f7e1b4 -> e8a4c2f9b1d6  [old main head]
  -> b5e7c1d9a4f2
  -> c4f8a2d7e6b1
  -> d7a3e9c1f5b2
  -> e8b4f1a2c6d9
  -> f3c7a1d9e5b2
  -> a6d2e8f4b1c7
  -> e8b4c2d6f1a9
  -> f9c2a7e4b1d6
  -> c1d4e7a9b2f6
  -> d2e5f8a1c4b7
  -> e3f6a9b2d5c8
  -> f1a4c8d2e6b9
  -> b7d3e9f1a5c2
  -> c9d4e6f8a1b2
  -> d2e5f8a1b4c7
  -> e3f6a9b2c5d8
                                             [integration and production head]
```

After promotion the graph itself is unchanged: main owns the same 80 definitions and single head `e3f6a9b2c5d8`. No new reconciliation revision is needed. The atomic-publication revision `e3f6a9b2d5c8` is a distinct earlier ancestor, not an alias.

The JSON [identity manifest](../../backend/migrations/production_lineage.json) records each filename, parent, full introduction commit, and source SHA-256. Every introduction commit belongs to integration history. The table below follows parent order. Full column/index operations are in the linked immutable definitions.

## Revision inventory

Main boundary revision `e8a4c2f9b1d6` is `e8a4c2f9b1d6_add_team_public_publications.py`, parent `d5a8c2f7e1b4`, introduced at `ce64b219ee1ebbd6ca58585675fff28273b90cb8` and already in main. It creates `team_public_publications` and `team_public_current_pointers` with constraints/indexes, with no backfill; downgrade drops both. Main has the dormant publication-storage mappings, and integration inherits them. It is a recorded production ancestor and is unchanged.

| Revision / definition | Parent | Introduced commit | Schema objects and behavior | Downgrade |
| --- | --- | --- | --- | --- |
| [b5e7c1d9a4f2](../../backend/migrations/versions/b5e7c1d9a4f2_add_sync_control_plane.py) | `e8a4c2f9b1d6` | `e3a96eafc43a` | Create `sync_run_scopes`. Extend `sync_failures`, `sync_run_scopes`, `sync_runs`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [c4f8a2d7e6b1](../../backend/migrations/versions/c4f8a2d7e6b1_add_durable_sync_job_queue.py) | `b5e7c1d9a4f2` | `570ce255b59b` | Create `sync_job_attempts`. Extend `sync_jobs`. Replace job uniqueness with active-job dedupe indexes. | Drops introduced objects/columns/indexes; not a recovery path. |
| [d7a3e9c1f5b2](../../backend/migrations/versions/d7a3e9c1f5b2_add_source_observation_evidence.py) | `c4f8a2d7e6b1` | `6faccd7ba9ee` | Create `source_subjects`, `source_payload_artifacts`, `source_observations`, `source_fetch_attempts`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [e8b4f1a2c6d9](../../backend/migrations/versions/e8b4f1a2c6d9_add_adaptive_game_state_fields.py) | `d7a3e9c1f5b2` | `16d368339be9` | Extend `scheduled_games`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [f3c7a1d9e5b2](../../backend/migrations/versions/f3c7a1d9e5b2_add_roster_transaction_authority.py) | `e8b4f1a2c6d9` | `cc1ea7c05bd1` | Create `roster_membership_intervals`, `roster_membership_mutations`, `player_transaction_versions`. Extend `player_transactions`, `roster_status_snapshots`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [a6d2e8f4b1c7](../../backend/migrations/versions/a6d2e8f4b1c7_add_pregame_context_authority.py) | `f3c7a1d9e5b2` | `980aa9986282` | Create `game_pregame_context_versions`, `pregame_context_mutations`. Extend `scheduled_games`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [e8b4c2d6f1a9](../../backend/migrations/versions/e8b4c2d6f1a9_add_final_game_reconciliation.py) | `a6d2e8f4b1c7` | `6af93815bc8e` | Create `final_game_versions`, `final_pitching_appearance_versions`, `final_game_mutations`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [f9c2a7e4b1d6](../../backend/migrations/versions/f9c2a7e4b1d6_add_live_game_delta.py) | `e8b4c2d6f1a9` | `9fdc5dd3d599` | Create `provisional_pitching_appearance_states`, `live_game_mutations`. Extend `game_observation_states`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [c1d4e7a9b2f6](../../backend/migrations/versions/c1d4e7a9b2f6_add_canonical_impact_plans.py) | `f9c2a7e4b1d6` | `ffac609d32e5` | Create `canonical_impact_plans`, `canonical_impact_plan_mutations`, `canonical_impact_plan_entities`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [d2e5f8a1c4b7](../../backend/migrations/versions/d2e5f8a1c4b7_add_derived_intelligence_cohorts.py) | `c1d4e7a9b2f6` | `60429a7a4db5` | Create `derived_intelligence_cohorts`, `derived_intelligence_cohort_domains`, `derived_cohort_inputs`, `derived_cohort_snapshots`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [e3f6a9b2d5c8](../../backend/migrations/versions/e3f6a9b2d5c8_add_atomic_publications.py) | `d2e5f8a1c4b7` | `b0a1d360857e` | Create `atomic_publications`, `atomic_publication_artifacts`, `atomic_publication_current`, `atomic_publication_cache_handoffs`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [f1a4c8d2e6b9](../../backend/migrations/versions/f1a4c8d2e6b9_add_daily_closure.py) | `e3f6a9b2d5c8` | `94e0ca0ac1e5` | Create `baseball_date_closures`, `baseball_date_closure_versions`, `baseball_date_closure_blockers`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [b7d3e9f1a5c2](../../backend/migrations/versions/b7d3e9f1a5c2_add_repair_orchestration.py) | `f1a4c8d2e6b9` | `ff49cd00ccbf` | Create `repair_requests`, `repair_request_chunks`, `repair_request_blockers`. Extend `canonical_impact_plans`. | Drops introduced objects/columns/indexes; not a recovery path. |
| [c9d4e6f8a1b2](../../backend/migrations/versions/c9d4e6f8a1b2_add_sync_certification.py) | `b7d3e9f1a5c2` | `0fad7f037e01` | Create `sync_certification_runs`, `sync_certification_checks`, `sync_legacy_transition_states`.  | Drops introduced objects/columns/indexes; not a recovery path. |
| [d2e5f8a1b4c7](../../backend/migrations/versions/d2e5f8a1b4c7_isolate_roster_authority.py) | `c9d4e6f8a1b2` | `1917fefa7a34` | Add `roster_membership_intervals.is_void` (false default); replace current-open uniqueness with player/team/type scope. | Refuses retained void history; otherwise restores narrower uniqueness and drops is_void. |
| [e3f6a9b2c5d8](../../backend/migrations/versions/e3f6a9b2c5d8_fence_compatibility_writers.py) | `d2e5f8a1b4c7` | `ea79ca78865d` | Create `compatibility_write_events`. Extend `player_transaction_versions`. Relax transaction observation nullability and fingerprint uniqueness; install six functions and eleven writer-fencing triggers on existing shared tables. | Refuses incompatible retained history; otherwise removes fences and restores earlier constraints. |

All sixteen upgrade bodies are schema definitions with no explicit data backfill or row deletion. Defaults populate added non-null fields on existing rows. Fencing functions contain runtime data writes; installing them is not equivalent to executing their write paths. These functions already exist in production and will not be reinstalled by the reconciliation. This is not a claim that the historical schema is behavior-free.

The fencing file changed within integration after its introduction (commits `8f843f06d`, `846e9100c`, `2a76915e3`). This package freezes the exact Outcome A snapshot, not an earlier introduction version. Read-only production function-body hashes match that snapshot. No historical body or revision identity is edited here.

## Production evidence and its limits

Observed at `2026-09-11 19:54:37.774631+00:00` using an explicitly read-only PostgreSQL transaction (read-only setting verified, statement timeout 15 seconds):

- Exactly one recorded head: `e3f6a9b2c5d8`.
- All 44 tables touched by the extension exist, including all 37 newly created tables. Thirty of the 37 new tables contain rows.
- Compared a fresh PostgreSQL database built from these definitions with the production catalog: all 844 columns (type, nullability, defaults) and 228 indexes across the 44 tables match. All eleven trigger definitions match; all six function-body hashes match the frozen source.
- No customer data, credentials, connection URLs, or row contents were retained in this report.

Empty new structures at observation: `baseball_date_closure_blockers`, `baseball_date_closure_versions`, `baseball_date_closures`, `repair_request_blockers`, `sync_certification_checks`, `sync_certification_runs`, `sync_legacy_transition_states`.

Applied status for every inventory row: the recorded descendant head plus matching physical schema supports already-applied history. This is not an independent execution log for each historical invocation. The no-op test proves behavior on a production-shaped local database, not an undisclosed production migration. Catalog observation is a timestamped snapshot; recheck before promotion.

Main models/services/routes/scripts have no references to the 37 new table names. Main continues to use extended shared tables (sync_runs, sync_jobs, scheduled_games, roster_status_snapshots, player_transactions, game_observation_states, and the fenced canonical tables) through its existing mappings. Integration models and services reference the new structures for source evidence, roster/pregame/final/live versions, canonical plans, cohorts, atomic publications, closure, repair, certification and compatibility-write evidence. Its shadow entrypoint requires the exact fencing head. Those runtime files are excluded from this package.

## Strategy decision

| Option | Correctness, safety, and maintenance assessment |
| --- | --- |
| A: promote exact historical definitions | Chosen. Complete parent chain resolves the recorded revision. Existing head performs no migration; fresh database executes the real history. No runtime feature code is necessary. Historical downgrade remains prohibited operationally. |
| B: branch/merge revision | Rejected for this graph: there are no sibling heads to merge. An ancestor/descendant merge invents divergence and does not eliminate the need for missing definitions. |
| C: compatibility migrations from old main | Rejected: a new identifier cannot make the recorded unknown revision resolvable. Conditional duplicate object creation would obscure applied history and complicate fresh upgrades. |
| D: wait for complete feature promotion | Possible only by prolonging the emergency override. Unnecessary: history is independently promotable, and full runtime promotion exceeds scope. |
| E: new no-op child after importing history | Alembic-native but unnecessary: the existing head already gives one truthful target. It would mutate the version row and require changing integration expected-head protection without repairing additional schema. |

Alembic merges join multiple heads; see [Working with Branches](https://alembic.sqlalchemy.org/en/latest/branches.html). No stamping, aliasing, squashing, downgrading or historical reparenting is used.

## Base and runtime isolation

A main-based topic is safer than branching this production PR from Outcome A: that branch includes unfinished integration runtime ancestry. This package selectively carries its production authority helper, startup, Alembic guard and manual promotion workflow; adds a pre-upgrade current/target log; and imports the 16 definitions unchanged. Main models, routes, jobs, public logic, frontend and feature flags remain unchanged. Outcome A remains on its original branch for separate integration adoption.

The promotion manifest and tests pin identities, reject duplicate IDs, prove the original main head and reconciled single head, and distinguish both similarly named revisions. Fresh and populated PostgreSQL tests perform real upgrades, compare all 88 public tables and schema fingerprints before/after repeated no-op upgrades, and exercise main startup and the Daily Edition helper. Linux also runs the actual default Gunicorn server and HTTP health check without emergency skip. See the [operations procedure](PRODUCTION_MIGRATION_AUTHORITY.md) for remaining adoption and live exit checks.

## Local validation record

- Focused authority, lineage, emergency startup and maintenance: 132 passed.
- Broader PostgreSQL migration/public API/CI contracts: 319 passed.
- Dependent head and runtime-isolation contracts: 116 passed; one historical
  Phase 0E document-branch test skipped because that branch scope is absent.
- Outcome A authority/shadow/fencing compatibility, on its unchanged branch:
  108 passed against a separate disposable PostgreSQL database.
- Linux with pinned backend dependencies: three lineage tests passed, including
  real default Gunicorn startup and HTTP health; the Git worktree scope check
  was deselected inside the container and passed in the Windows worktree.
- Shard accounting: 416 files, 9,656 node IDs, each assigned exactly once.
- All 16 staged promoted blobs equal their source; all 64 main migration blobs
  are unchanged. Staged and working-tree whitespace checks pass.

These groups overlap; counts are not a claimed distinct-test total. The complete
9,656-test suite and hosted CI have not run for this unpushed topic. Production
was inspected read-only; no production promotion/startup exit test was attempted.
