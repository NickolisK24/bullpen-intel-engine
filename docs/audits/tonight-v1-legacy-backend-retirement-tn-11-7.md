# Tonight v1 legacy backend retirement (TN-11.7)

## Outcome

Outcome B: the internal migration is complete, and public v5 compatibility is
retained.

- No scheduler, publication, repair, continuous or startup path generates or
  depends on the legacy tonight_v5 cache or the legacy Today (Daily Edition)
  read model.
- The default Tonight contract is now tonight_v1.
- `contract=tonight_v5` and `/intelligence/today` remain as explicit,
  deprecated public compatibility. They are unauthenticated public
  endpoints, and the repository cannot prove there are no external callers.
- No schema change, no migration, and no deleted rows.

## Target authority model

```
trusted Dashboard publication
    -> post-publication hook -> immutable tonight_v1 row (created once)
    -> operational jobs: ensure_tonight_v1_for_publication (reuse; create once if the hook missed)
    -> GET /intelligence/tonight (default) and ?contract=tonight_v1 serve that row
```

`tonight_read_model.ensure_tonight_v1_for_publication(snapshot, *, source)`:

- If a row exists for that publication identity, it is reused as-is. It is
  never rebuilt, compared or overwritten, so a later schedule change can
  neither mutate it nor raise `TonightPublicationConflict`.
- Otherwise the row is created once through the same generator the hook uses.
- It honors the `TONIGHT_V1_PROJECTION_ENABLED` off-switch.
- It never raises, and logs one line:
  `tonight_v1 ensure source=… snapshot_id=… status=created|reused|skipped|failed … legacy_tonight_v5=not_generated`.

## Call graph before

| Consumer | Class | Legacy dependency |
| --- | --- | --- |
| `sync_due._run_daily` / `_run_postgame` / `_run_morning` (Render primary, GitHub fallback, recovery) | A | `refresh_schedule_and_tonight` rebuilt tonight_v5; the window was successful only if the v5 build verified. |
| `scripts/refresh_slate_schedule.py` | A (manual/legacy morning runner) | `refresh_schedule_and_tonight` |
| `continuous_production_publication._refresh_tonight` | A (env-gated continuous chain) | `generate_tonight_snapshot_for_date` after every publication; a failure meant `retry_required`. |
| `intraday_repair.run_intraday_roster_repair` | A | The Today rebuild was a pre-publication prerequisite (a failure blocked publication); a tonight_v5 rebuild followed. |
| `intraday_completed_game_repair` | A | Same as above. |
| `incremental_read_model_rebuild` (CU-06) | A (env-gated continuous chain) | `_default_tonight_builder` → `tonight_intelligence_service.serve_tonight` per game, with parity checks. |
| `incremental_publication` (CU-07) | A (env-gated continuous chain) | Required a tonight_v5 entry per game (`tonight_cohort_incomplete`), cache key `tonight:{game}`, and fingerprinted it. |
| `app.py` `DAILY_EDITION_PUBLICATION_REQUIRED` | A | In production, every Dashboard publication first prepared the Today snapshot (`dashboard_snapshot` → `prepare_snapshot_for_publication`). |
| `scripts/render_start.sh` | A | `prepare_daily_edition_snapshot` ran before gunicorn under `set -e`, so a Today failure blocked API startup. |
| `api/bullpen.py` `GET /intelligence/tonight` (no contract) | A/D | Served tonight_v5 by default. |
| `public_serving_authority.trusted_tonight_view` | D | Production v5 view. |
| `GET /intelligence/today` | D | Legacy Today lead story (live build on miss). |
| `sync._safe_generate_intelligence_surface_snapshot` + helpers | E | Dead: never called, unit-tested only. |
| `scripts/run_tonight_refresh.py`, `prepare_daily_edition_snapshot.py`, `repair_daily_edition_context.py` (manual maintenance workflow), `run_cu01p_proof.py` | B | Operator/proof tools; none is scheduled. |
| `todays_story_editorial_review`, `story_selection_trace_v1` | B | Read-only internal review of stored Today rows. |
| Frontend | none | TN-11 removed every v5/Today client. `getTonightV1` is the sole Tonight client. |

## Call graph after

| Consumer | New dependency |
| --- | --- |
| Daily / recovery_daily | Ingest and publish (unchanged), then `refresh_schedule` (schedule only), then `ensure_tonight_v1_for_publication(current trusted publication)`. Success = sync status successful AND publication proof verified AND schedule refresh ok. tonight_v1 is reported in the proof and never gates success. |
| Postgame | Same, with the existing `expected_pending_active_slate` rule. |
| Morning | `refresh_schedule`, then ensure v1 for the current publication. Success = schedule ok. |
| `refresh_slate_schedule.py` | `refresh_schedule` |
| Continuous publication | After a commit or durable receipt, `ensure_tonight_v1_for_publication(that exact publication)`. `retry_required` only when a v1 row that should exist could not be ensured; a disabled projection counts as complete. |
| Intraday roster / completed-game repair | No Today prerequisite. After the verified publication, `ensure_tonight_v1_after_publication(result, snapshot, ensurer)`. A failure gives `partial` + `tonight_refresh=retry_required`; the publication stays durable and the run is never rewritten as failed. |
| CU-06 bounded rebuild | Tonight scope removed. It rebuilds team boards, league rows and matchups only. |
| CU-07 cohort | Tonight cohort, surface and cache key removed. `COHORT_CONTRACT` is now `incremental_publication_cohort_v2`. |
| `app.py` | `DAILY_EDITION_PUBLICATION_REQUIRED = False` in every environment. |
| `render_start.sh` | Migrations, then server. No Today preparation. |

Internal v5/Today consumers went from 11 live paths to 0.
`test_tonight_legacy_backend_retirement.py` pins that with a static scan of
every migrated module, the frontend, the scripts and all workflows.

## Contract decisions

| Request | Before | After |
| --- | --- | --- |
| `GET /intelligence/tonight` | tonight_v5 | tonight_v1 (current trusted publication; never builds; fails closed in the v1 shape; `reference_date` is rejected with a 400 in the Tonight shell) |
| `?contract=` (empty) | tonight_v5 | tonight_v1 |
| `?contract=tonight_v1` | tonight_v1 | tonight_v1 (unchanged) |
| `?contract=tonight_v5` | tonight_v5 | tonight_v5, deprecated: `Deprecation: true`, `X-BaseballOS-Contract: tonight_v5`, and a `Link` header with `rel="successor-version"` pointing to `?contract=tonight_v1`. Behavior is otherwise unchanged (production: stored snapshot only, fails closed). |
| any other contract | 400 | 400 (unchanged) |
| `GET /intelligence/today` | Today lead story | Unchanged behavior, plus `Deprecation` and successor `Link` headers. No scheduled or publication path writes Today any more. A request can still build and store a row live on a miss; that is request-time compatibility only. |

The v5 compatibility view is never part of tonight_v1 authority. It cannot
block publication, tonight_v1 generation or sync success, and nothing
refreshes it synchronously. With no scheduled refresh, its stored cache ages.
Production serving is snapshot-only, so a miss is an honest `empty`
(`trusted_tonight_snapshot_unavailable`). An operator can still warm it
explicitly with `run_tonight_refresh.py`.

## Retained, intentionally

| Item | Why |
| --- | --- |
| `tonight_intelligence_snapshots` table and rows | Historical data and the source for the deprecated v5 view. Runtime scheduled writes stopped. |
| `intelligence_surface_snapshots` table and rows | Historical data and the source for `/intelligence/today` and internal review tools. Scheduled writes stopped. |
| `tonight_intelligence_service`, `tonight_intelligence_snapshot`, `trusted_tonight_view` | Serve only the explicit `contract=tonight_v5` branch. |
| `schedule_tonight_refresh.refresh_schedule_and_tonight` | Deprecated; no internal caller. Kept for explicit operator warming of the v5 cache. |
| `intelligence_surface_snapshot` builders and `dashboard_snapshot`'s `DAILY_EDITION_PUBLICATION_REQUIRED` branch | The branch is config-off. `dashboard_snapshot.py` is a digest-pinned canonical module and is byte-identical to main. |
| `sync._safe_generate_intelligence_surface_snapshot` + helpers | Dead (class E, never called). Removal is left to the cleanup package. |
| Operator scripts and the manual `daily_edition_context_repair` maintenance workflow | Explicit, confirmation-gated maintenance of the deprecated caches; never scheduled. |

## Future cleanup (not in this package)

- Measure or announce the public deprecation window. Then remove
  `contract=tonight_v5`, `/intelligence/today`, `trusted_tonight_view`, and the
  v5 and Today builders and scripts.
- Remove the dead `sync.py` Today helper and the config-off
  `DAILY_EDITION_PUBLICATION_REQUIRED` branch. The branch removal needs a
  governed change to the digest-pinned `dashboard_snapshot.py`.
- Plan a deliberate schema package for `tonight_intelligence_snapshots` and
  `intelligence_surface_snapshots` (archive, then drop).
- Do a governed revision of the canonical product docs for the Tonight home.
