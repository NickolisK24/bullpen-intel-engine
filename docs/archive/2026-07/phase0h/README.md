# Phase 0H

Branch 01 adds three internal certification artifacts:

- `docs/phase0h/trusted_snapshot_contract.md`
- behavior-freeze tests for trusted snapshot, freshness, comparability, and
  frozen What Changed rules
- `GET /api/system/internal/snapshot-audit`

The snapshot audit route is admin-gated, read-only, and quote-only. It exists so
Nickolis, editorial review, and legal review can inspect why a day published,
withheld, or lacks a comparable baseline using stored snapshot rows and stored
payload fields.

Phase 0B public evidence gate remains closed. This branch adds no public
endpoint, no frontend, no sync change, no schema change, no migration, and no
snapshot builder change.

Legacy What Changed surfaces remained frozen and untouched during this phase.
Public daily-changes work remained blocked pending separate ratification.

## Branch 02

Branch 02 hardens the internal snapshot-audit output. It adds controlled
extraction for stored legacy What Changed comparison metadata, adjacent
published/trusted baseline summary diagnostics, and flags for stored comparison
metadata that does not match the adjacent trusted snapshot contract.

It changes no trust rules, public surfaces, sync, schema, migrations, dashboard
snapshot builder behavior, or legacy What Changed behavior. Public daily-changes
work remains blocked.

## Branch 03

Branch 03 is a production reliability/diagnosis branch for the snapshot-audit
route. In production the valid-token path returned empty-body 502s (~8.3s and
~61.4s) with no bounded JSON, which means the Gunicorn worker was killed at the
process level (worker `--timeout 60` SIGKILL) before the route's exception
handling could run. The bounded-summary path reads many JSON-path projections
of the `json`-typed `dashboard_snapshots.payload` column; Postgres re-parses
the full payload document per extracted field per row, which is too expensive
inside web request limits.

Branch 03 adds, without changing any trust rule or public surface:

- Stage checkpoint logs on the internal route (stage names and elapsed ms
  only — never tokens, request values, or payload contents), so a production
  failure pinpoints the exact stage even if the worker is killed.
- A transaction-scoped `SET LOCAL statement_timeout` (5s) plus a wall-clock
  time budget (20s) on the bounded-summary path, so an over-budget summary
  raises a catchable error instead of the worker being SIGKILLed.
- A degraded DB-row fallback: if the summary path fails or exceeds budget,
  the route returns bounded JSON built only from cheap snapshot row columns.
  The fallback is explicitly marked `route_status: degraded`,
  `ratification_ready: false`, `decision_4_5_supported: false`; it never
  fabricates trusted-pair counts, comparable counts, or reason codes — those
  fields are explicit nulls with diagnostics explaining why.
- `backend/scripts/run_internal_snapshot_audit.py`: an operator CLI that runs
  the same audit builder against `DATABASE_URL` outside the web request path
  with relaxed limits. This is the ratification path when the web route can
  only degrade: exit 0 prints full memo-friendly summary JSON; exit 1 prints
  the degraded fallback (never ratification evidence).

No cheaper in-request ratification path was added: trust and comparability
evidence exist only inside stored payload JSON, and cheap row columns cannot
prove trusted pairs without guessing, which is forbidden.

Decision 4/5 cannot be ratified from fallback-only evidence. The route stays
admin-gated and internal-only. Public daily-changes work remains blocked.

## Production Ratification - July 12, 2026

Phase 0H production ratification is recorded from the July 12, 2026 protected
audit evidence.

Verified evidence:

- The snapshot-audit route remained internal/admin-only.
- The audit window was 14 days.
- 11 historically published snapshots were inspected.
- 11 published snapshots were trusted.
- Six trusted adjacent pairs were found.
- Two adjacent pairs were fully comparable.
- Four unsuitable adjacent pairs were correctly withheld.
- Zero non-adjacent comparisons were produced.
- Recent rows were not truncated.
- An incomplete candidate snapshot did not replace the last valid publication.
- Decisions 4/5 were ratified.
- D-15 is closed.
- Public What Changed is technically unblocked.

Recent partial scheduled syncs remain an operational monitoring concern. They
do not invalidate Phase 0H ratification because the trusted snapshot path failed
closed correctly: partial or incomplete candidates did not replace the last
valid publication and unsuitable comparisons were withheld.
