# Phase 0E QA Fixture Corpus

## Purpose

The 0E-05 QA fixtures are synthetic only. They construct real rows in the test
database and return typed handles with row ids, product dates, read ids,
evidence ids, audit row ids, and an expected-state map. Tests assert the
expected-state map instead of asserting full rendered text, except for mandated
disclaimers and limitation strings.

The package lives at `backend/tests/qa_scenarios/`.

## Shared Handle

Each builder returns `ScenarioHandle`:

- `name`
- `product_date`
- `sync_run_id`
- `pitcher_ids`
- `team_ids`
- `evidence_object_ids`
- `composed_read_ids`
- `audit_run_ids`
- `divergence_ids`
- `row_ids`
- `expected_state_map`

Every stored evidence object has a provenance-carrying citation. Builders use
game logs, roster snapshots, transactions, transaction windows, scheduled
games, play-by-play events, evidence rows, composed reads, dashboard snapshots,
and reconciliation audit rows where the scenario requires them.

## Builders

| Builder | Expected state focus |
| --- | --- |
| `opening_week_small_samples` | Partial workload/rest components with opening-week reason codes. |
| `off_day_team` | Complete team read with absent optional calendar component. |
| `doubleheader` | Complete team read with calendar and appearance-count limitations. |
| `suspended_resumed_game` | Complete reliever read with resumed-game and entry-context limitations. |
| `incomplete_slate` | Partial contributor component from incomplete slate coverage. |
| `postponed_game` | Complete team read with schedule-change limitation. |
| `trade_deadline_churn` | Complete roster-churn component with trade transaction provenance. |
| `option_recall_churn` | Complete roster-churn component with option/recall provenance. |
| `il_placement_activation_timing` | Complete roster/IL component with public-event limitation. |
| `september_call_up` | Complete roster-churn component with recall provenance. |
| `roster_snapshot_stale` | Unknown roster component and unknown reliever read. |
| `transaction_coverage_gap` | Partial roster-churn component from transaction coverage gap. |
| `idle_team_trailing_windows` | Complete exposure component for a covered zero-game window. |
| `relief_history_missing_membership` | Unknown roster membership on an otherwise present reliever read. |
| `rostered_cold_arm_gap` | Rostered pitcher has no reliever read because the trailing relief window is empty. |
| `missing_contributor_basis` | Team read remains present; contributor component is unknown. |
| `legacy_snapshot_missing` | Typed audit skip row for missing published legacy snapshot. |
| `composed_reads_missing` | Typed audit skip row for missing composed reads. |
| `conflict_state_evidence` | Conflict read plus material actionable-on-degraded audit category. |
| `mid_window_correction_recompute` | Evidence -> read -> audit-skip cascade after recompute marking. |
| `locked_band_consumption_attempt` | Locked evidence consumption fails before a read is staged. |
| `legacy_factual_field_contradiction` | Material factual-field contradiction category. |
| `covered_window_zero_transactions` | Complete roster-churn component for a covered zero-transaction window. |

## Assertion Contract

The QA modules assert:

- component states;
- read completeness from the required-component severity calculus;
- reason codes;
- citation resolvability;
- row counts and category counts;
- typed skip rows;
- materiality categories;
- no percent output in audit reports;
- deterministic renderer sampling;
- no ordered, ranked, or filtered subject path based on `completeness_state`.
