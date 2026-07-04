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
- `roster_status_snapshots`
- `player_transactions`

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

## 0C-03 Boxscore Field Rules

`batters_faced`, `balls`, `games_finished`, `inherited_runners`, and
`inherited_runners_scored` are nullable raw boxscore facts. Missing, blank,
unparseable, or structurally absent source values stay `NULL`; explicit source
zero stays `0`.

Historical `inherited_runners` and `inherited_runners_scored` zeroes were
fabricated by model defaults rather than an authoritative ingest path, so 0C-03
repairs those stored zeroes to `NULL`. Other historical zero-valued pitching
stats are not rewritten in 0C-03 because they are already part of the
established daily/postgame pitching-line stat path and correction policy.

Future backfill of the new fields must be its own scoped operation. It must use
the finality authority, registered correction policy, source provenance, and
fail-closed handling. No historical value should be silently imputed.

## 0C-04 Roster Snapshot Rules

Roster status snapshots are dated source facts. They are not health reads,
depth-pressure reads, role reads, IL-pressure reads, availability labels, or
public evidence interpretations.

`roster_status_snapshots` is the storage authority for roster status facts. The
current roster fields on `pitchers` are a derived compatibility cache populated
only from the latest valid roster snapshot. Consumers may continue reading the
current pitcher fields, but those fields must not become a second source of
truth.

Each snapshot carries source provenance, `sync_run_id`, first-seen timestamp,
and correction metadata. Same-pitcher same-day roster fact changes correct the
snapshot row with correction provenance. Same-pitcher same-day team conflicts
dead-letter and fail closed instead of silently changing identity. Older dated
snapshots remain historical record.

Roster snapshot readiness is internal/admin diagnostics only. Missing snapshots,
stale snapshots, fetch failures, unresolved roster dead letters, missing team
coverage, missing provenance, or cache divergence degrade the
`roster_status_snapshots` source family. Stale roster snapshots must not be
treated as fresh evidence by future consumers.

Two-way eligibility is stored only when sourced. It is not interpreted as a
bullpen role, relief role, health state, or availability claim.

## 0C-05 Transaction And IL Foundation Rules

Transactions are dated explanatory facts. They do not decide current roster
state, availability, bullpen role, health, depth pressure, roster churn, or
public evidence interpretation. The current-state authority remains
`roster_status_snapshots`; the current roster fields on `pitchers` remain a
derived compatibility cache populated from roster snapshots only.

`player_transactions` stores structured fields only: player identity, from/to
team ids where sourced, transaction date, effective/resolution dates where
sourced, source type code, normalized conservative category, typed IL
placement/activation flags, typed IL list type, typed retroactive date, roster
snapshot alignment, source query window, and provenance. It does not store raw
response JSON, free-text injury descriptions, health status, injury severity,
return timetable, IL pressure, roster churn, depth pressure, availability
labels, or public display fields.

Normalized transaction categories are conservative and source-code based:
`recall`, `option`, `il_placement`, `il_activation`,
`roster_activation`, `roster_deactivation`, `trade`, `dfa`, `outright`,
`release`, `contract_selection`, `suspension`, `bereavement`, `paternity`,
`restricted`, and `unknown`. Unknown or unsupported source type codes are
stored as `unknown` and excluded from explanatory linkage.

Each transaction aligns against same-date roster snapshots when possible:
`aligned`, `misaligned`, `unknown`, `no_snapshot`, or `not_applicable`.
Missing roster snapshots, missing team evidence, unknown transaction types,
untracked players, and team mismatches fail closed by making explanatory
linkage ineligible. Stored transaction facts never update pitcher current
roster fields.

Transaction sync is a bounded internal stage. Fetch failures, malformed rows,
missing player identity, and shape surprises dead-letter and degrade the
`player_transactions` readiness family. Empty successful bounded fetches are
represented by sync-window provenance; they are not stored as synthetic
transaction facts. Readiness exposes last attempted/successful fetch,
bounded date range, records fetched/stored, unknown type counts, alignment
counts, unresolved dead letters, reason codes, source, and `sync_run_id` for
internal/admin diagnostics only.
