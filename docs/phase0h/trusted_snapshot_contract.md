# Trusted Snapshot Contract

## Definition

The trusted published dashboard snapshot is an existing `DashboardSnapshot`
row for `SNAPSHOT_TYPE_BULLPEN_DASHBOARD` with:

- `status = SNAPSHOT_STATUS_READY` (`'ready'`)
- `is_published = True`
- non-null `sync_run_id`, enforced by the
  `ck_dashboard_snapshots_published_requires_sync_run` database constraint
- `payload_version = DASHBOARD_PAYLOAD_VERSION` (`1`)
- slate-coverage validations passed
- payload-internal `freshness.data_through` and
  `freshness.availability_reference_date` matching the row-level
  `data_through` and `availability_reference_date`

Operationally, `snapshot_unavailable_reason(snapshot)` returning `None` is the
code-level proof that these gates currently pass.

## Snapshot Date Semantics

`data_through` is the product date for the published view of final games through
calendar day D. It is not wall-clock time and it is not a host-local freshness
claim. `snapshot_generated_at` and `published_at` describe when the row was
generated or published; they do not redefine the product date.

## Publish Gates

Snapshot publication is tied to writer-guarded sync-run provenance. A published
snapshot must point at the `SyncRun` that produced it, and the sync run can point
back through `published_dashboard_snapshot_id`.

Publish is withheld when existing slate coverage says the snapshot cannot be
trusted for public display:

- `DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING`
- `DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE`

Those reasons are stored on withheld snapshot rows through the current snapshot
machinery. Phase 0H does not change the builder, writer guard, cadence, or
`JOB_DASHBOARD_SNAPSHOT_BUILD` semantics.

## Freshness Authority

`board_freshness.board_freshness_block()` is the public freshness authority. It
prefers the trusted published dashboard snapshot and falls back to durable sync
status only when no valid published snapshot is available.

The `previous_published_view` served-consistency state is the only public
acknowledgment that newer raw data exists while the product is still serving the
last trusted published view. Raw sync dates do not become public freshness by
themselves.

## Comparability Rule

What Changed compares two trusted published snapshots whose `data_through`
values are exactly one calendar day apart. If that proof fails, the comparison
fails closed and emits typed reason codes instead of partial diffs.

The frozen reason set includes:

- `REASON_NO_PRIOR_SNAPSHOT`
- `REASON_PRIOR_SNAPSHOT_UNPUBLISHED`
- `REASON_CURRENT_SNAPSHOT_UNTRUSTED`
- `REASON_SNAPSHOTS_NOT_COMPARABLE`
- `REASON_COMPARISON_WITHHELD`
- `REASON_PRIOR_SLATE_COVERAGE_MISSING`
- `REASON_PRIOR_SLATE_INCOMPLETE`
- `REASON_CURRENT_SLATE_COVERAGE_MISSING`
- `REASON_CURRENT_SLATE_INCOMPLETE`
- `REASON_DATA_THROUGH_MISSING`
- `REASON_VALIDATIONS_FAILED`

The frozen state set includes `STATE_CHANGES_DETECTED`,
`STATE_NO_MEANINGFUL_CHANGES`, and `STATE_INSUFFICIENT_CONTEXT`.

## Off-Days, Postponed, Suspended, And Non-Final Slates

Off-day snapshots can be trusted when slate coverage is known, validations pass,
and `complete_enough_to_publish` is true. Postponed, suspended, and non-final
slate conditions are represented by the existing stored slate-coverage reason
codes inside the snapshot payload. Non-final slates withhold publish and
comparison through the existing coverage gates.

## Disjointness

Internal read and evidence readiness does not vote in snapshot trust. Snapshot
trust is decided by `DashboardSnapshot`, its stored payload metadata, slate
coverage, and sync-run provenance.

Conversely, snapshot trust does not certify internal read or evidence readiness.
`PHASE0E_READ_BUILD`, recompute status, and reconciliation remain separate
internal concerns.

## Frozen Legacy Surfaces

The legacy What Changed surfaces are frozen:

- `backend/services/what_changed_since_yesterday.py`
- `backend/services/what_changed_since_yesterday_public.py`

They run as-is. Phase 0H does not extend, rename, wrap, or re-derive those
surfaces, and the snapshot audit endpoint does not import them.

## Gate Statement

The Phase 0B public evidence gate remains closed. This contract authorizes no
public endpoint, no frontend surface, no Data & Trust copy, no methodology copy,
no static preview, no Today/dashboard/board change, and no public evidence
exposure.
