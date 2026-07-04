# Source Readiness And Provenance Framework

## Purpose

Phase 0C source/storage work must fail closed by default. A field or table is
not ready for later consumers unless its source, provenance, correction policy,
readiness state, and failure behavior are explicit.

## Provenance Pattern

Future source-backed tables should use `SourceProvenanceMixin` when the generic
field names fit:

- `source`
- `sync_run_id`
- `first_seen_at`
- `last_corrected_at`
- `correction_count`
- `correction_source`

Existing tables may use an adapter instead. Current game-log correction
provenance remains on the established Phase 0A fields:

- `stat_correction_count`
- `last_stat_correction_at`
- `last_stat_correction_source`
- `last_stat_correction_sync_run_id`

## Correction Policy Registration

Correction-sensitive storage must register a policy before it ships. A policy
declares:

- source family
- model/table owner
- identity keys that must not silently change
- fields that may update after final ingest
- fields that become UNKNOWN or NULL on unsafe conflict
- conflicts that must dead-letter

Unregistered correction-sensitive fields fail the framework contract test.

## Readiness States

Source readiness states are:

- `ready`: source family has usable, provenance-backed data.
- `degraded`: source family has data but unresolved failures or blockers exist.
- `stale`: source family has data but it is past its stale threshold.
- `unavailable`: source family was attempted but usable data/provenance is not
  available.
- `never_fetched`: source family has no successful or attempted fetch/ingest.
- `unknown`: readiness could not be evaluated.

All states except `ready` fail closed for future consumers.

## Internal Diagnostics

Internal pipeline health includes source-readiness diagnostics for existing
foundations only. It does not create public copy or public evidence behavior.

Initial diagnostic families:

- `finality_authority`
- `statsapi_core`
- `game_logs`
- `slate_coverage`
- `dashboard_snapshots`
- `roster_status_current`

Not-yet-built Phase 0C source families must not be marked ready.

## Required Tests For Future Branches

Each later Phase 0C storage branch should add tests proving:

- final-only source gate
- nullable/UNKNOWN handling
- no fabricated zero defaults for unknown values
- provenance is present
- correction policy is registered
- unsafe correction conflicts dead-letter or clear to UNKNOWN/NULL as declared
- readiness family reports ready only when source data is usable
- stale, unavailable, degraded, never-fetched, and unknown states fail closed
- public payloads do not consume framework-only data in Phase 0C
