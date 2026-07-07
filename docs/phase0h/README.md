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

Legacy What Changed surfaces remain frozen and untouched. Public daily-changes
work remains blocked pending separate ratification.
