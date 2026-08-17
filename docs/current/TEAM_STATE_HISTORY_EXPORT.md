# Team State History Export — Runbook

## Purpose

Lift the Team State evidence production already froze at publication time into a
JSON artifact that can be analysed offline, so Team State calibration work is
grounded in historical evidence rather than in re-derived current data.

This export changes no product semantics. It does not touch the Team State
vocabulary, thresholds, classifier, publication authority, or any historical
record.

## Read-only guarantee

The exporter issues `SELECT` queries only. It never inserts, updates, deletes,
commits, publishes, recalculates, repairs, warms a cache, or calls a source API.
The script asserts the ORM session stayed clean and rolls back before writing
its output; if anything staged a change it aborts with a non-zero exit instead
of producing an artifact.

The GitHub workflow that runs it against production is `workflow_dispatch` only.
It declares no schedule, requests `contents: read`, reads no admin token, and
uploads an artifact as its only output.

## Historical authority

Two frozen sources are read. Neither is recomputed.

| Evidence | Source |
| --- | --- |
| Published Team State, trust, freshness, constraints, summary | `share_artifacts` rows of type `team_state` (`services.team_state_payload`) |
| Per-arm board records and the governed board population | `dashboard_snapshots.payload['trusted_team_boards']` (`services.public_serving_authority`) |

Only published, `ready` bullpen-dashboard snapshots with a `published_at` stamp
are considered, paired with `published` Team State artifacts pinned to the same
`source_snapshot_id`.

## What history does not preserve

The Team State component vectors — `availability_distribution`,
`workload_pressure`, `coverage_inventory`, `handedness_coverage` — are assembled
at generation time by `team_operations.bullpen_readiness` and consumed as a
governed input. Only the resulting status reaches the immutable artifact.

Those fields are therefore exported as `null` on every row, listed in the
artifact under `unpreserved_team_level_fields`. Per-arm `workload_category`,
`throwing_hand`, and `has_current_workload` are likewise `null`, listed under
`unpreserved_arm_fields`.

**A field history did not keep is always `null`. It is never filled from current
tables.** `null`, `0`, and "absent" stay distinguishable.

Where the frozen board package is present, a `derived_partition` block gives the
clean / moderate / severe / unknown tally taken directly from the frozen per-arm
`availability_status`, with an explicit denominator and guarded shares. It is
marked `"derived": true` and names its source. It is a tally of frozen values,
not a classification.

## Required inputs

A bounded range is required; there is no unbounded default.

- `--snapshot-id`, or
- `--snapshot-id-from` / `--snapshot-id-to`, or
- `--date-from` / `--date-to` (on `data_through`)

## Local usage

```
cd backend
python -m scripts.export_team_state_history \
  --snapshot-id-from 380 --snapshot-id-to 424 \
  --output /tmp/team_state_calibration_history.json
```

Exit codes: `0` success, `2` invalid/missing range or no matching trusted
authority, `3` the session unexpectedly staged ORM changes.

## Production execution

1. Actions → **Team State History Export** → *Run workflow*.
2. Supply a snapshot id range or a date range. Omitting both fails the run.
3. Download the `team-state-calibration-history` artifact (14-day retention).

The workflow fails loudly — never with an empty "successful" dataset — when the
range is missing or invalid, database configuration is absent, no trusted
snapshots match, or no Team State authority exists in the range.

## Output fields

Top level: `export_version`, `generated_at`, `repository_sha`, `read_only`,
`filters`, `source_contract`, `unpreserved_team_level_fields`,
`unpreserved_arm_fields`, `snapshot_count`, `team_classification_count`, `rows`.

Each row: `snapshot_id`, `sync_run_id`, `published_at`, `product_date`,
`data_through`, `contract_version`, `team_id`, `team_abbreviation`,
`readiness_status_code`, `public_team_state`, `trust_confidence`,
`trust_data_state`, `freshness_state`, `published_why_text`, `constraint_ids`,
`frozen_board_present`, `arms[]`, `derived_partition`, `integrity`, plus the
unpreserved team-level fields as `null`.

`public_team_state` is `null` for `data_limited` and `refused`. Those are
publication conditions and are never converted into Fresh / Stretched /
Vulnerable.

`integrity` reports partition problems and never repairs them. A row with a
mismatch is emitted with its flags so the problem stays visible.

## Prohibited uses

- Do not use this artifact to rewrite, republish, or reinterpret historical
  Team State. Historical states remain bound to the method that produced them.
- Do not fill a `null` with a current value.
- Do not treat `derived_partition` as a published metric or a proposed state.
- Do not wire the exporter into sync, publication, or any scheduled job.
