# Tonight authority hardening (TN-00)

Status: sequencing and same-snapshot assembly corrected; no migration; no
public semantic or frontend change.
Surface: `GET /api/bullpen/intelligence/tonight` and the stored
`tonight_intelligence_snapshots` row it serves.

## Previous race

The intraday roster repair (`services/intraday_repair.py`) and the intraday
completed-game repair (`services/intraday_completed_game_repair.py`) rebuilt
and committed Tonight **before** calling `complete_sync_run_with_snapshot`.
`generate_tonight_snapshot_for_date` commits its own row, so a publication that
then failed (or published but did not prove it was serving) rolled back only
the dashboard. The stored Tonight payload had already been replaced with work
built from candidate data, while the trusted Team Board stayed on the previous
publication.

The CU-06 incremental rebuild (`_default_tonight_builder`) injected Team State,
workload, and rest sidecars resolved from the shadow snapshot but no rotation
sidecar. Because some sidecars were injected, `serve_tonight` took its
per-builder branch and resolved rotation from the **current public** snapshot,
so one rebuilt Tonight entry mixed two publications.

## Corrected sequence

Both repair paths now run:

1. acquire and reconcile data
2. rebuild Today (unchanged)
3. `complete_with_snapshot` publishes the replacement trusted Dashboard
4. the publication proof verifies the new snapshot is serving
5. `refresh_tonight_after_publication` rebuilds Tonight from that trusted state
6. Tonight commits

If step 3 or 4 fails, the existing exception path runs as before (rollback, run
marked failed) and the Tonight builder is never called: the stored Tonight
payload is unchanged.

If step 5 fails, the publication is already durable and cannot be undone. The
helper rolls back the Tonight attempt, keeps the previous stored Tonight
payload, reports `status: partial` with `tonight_refresh: retry_required`, and
does not rewrite the published sync run as failed. This mirrors the existing
post-publication `_refresh_tonight` in `continuous_production_publication`.

## Same-snapshot sidecar invariant

`_default_tonight_builder` now also injects the rotation listing bound to the
same snapshot resolver, so Team State (the league listing built from the shadow
snapshot), workload, rotation, and rest all resolve from that one snapshot.

As a structural guard, `serve_tonight` no longer lets a partially injected call
fall back to the current public snapshot: a sidecar the caller did not inject
is withheld instead. The production path (no injected sidecars) still resolves
all four from one `resolve_current_trusted_dashboard_snapshot()` call.

## Trusted serving and envelopes

`trusted_tonight_view` stays snapshot-only: no live build, no build on miss, no
game-log or FatigueScore reads, fail closed. Every Tonight response (stored,
empty, trusted-snapshot-unavailable, live timeout, 400, 503) now carries the
same shell: `status`, `reference_date`, `cards`, `card_count`, `games`,
`game_count`, `empty_reason`, `limitations`. The 400 keeps its existing
`reason_code`, `parameter`, and `message` fields.

## Deferred to TN-01

The stored Tonight row still has no durable binding to a dashboard snapshot id,
sync run, or `data_through`, and its `bullpen_context` is still read from live
FatigueScore and game logs at build time. Adding the binding needs a schema
change and a new read model, so TN-00 claims only ordering and same-snapshot
assembly. Daily and postgame due windows also still refresh Tonight after
their publication attempt even when that attempt was withheld; the frozen
sidecars stay on the trusted snapshot, and the live `bullpen_context` is
replaced in TN-01.
