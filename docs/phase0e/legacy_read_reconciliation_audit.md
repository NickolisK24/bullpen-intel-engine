# Phase 0E-04 Legacy Read Reconciliation Audit

## Scope

This branch adds an internal audit that compares published legacy dashboard
labels and fields against stored Phase 0E composed reads for the same product
date.

The audit quantifies divergence only. It fixes nothing, replaces nothing,
edits nothing, and surfaces nothing. Public payloads, API routes, UI, board
payloads, dashboard snapshots, What Changed, Tonight, frontend code, copy,
labels, and methodology remain unchanged. The Phase 0B legal gate still blocks
public surfacing.

Legacy code is untouched. Capture helpers live only in the audit service and
read stored/published artifacts: the published dashboard snapshot payload,
opaque stored engine-row provenance, and internal composed-read rows.

## Neutral-Language Guardrail

The audit may record "divergence from evidence-backed internal read," but it
must not call a public label wrong, incorrect, broken, defective, or misleading
in row/report content. Any live label freeze, flag, copy change, or defect
ticket remains a separate scoped decision after review. Escalations are
RECOMMENDATIONS to Nickolis only - no auto-defects, no auto-freezes, no silent
fixes, no backdoor evidence-read swap. Neither side of a divergence is "truth."

## Tables

Exactly one migration adds exactly two audit tables:

- `legacy_read_divergences`
- `legacy_read_audit_runs`

Aligned subject pairs are not stored per subject. Run rows carry denominators
and category counts. Re-running a date replaces that date and subject type's
audit rows transactionally.

## Capture Semantics

Legacy capture reads the published dashboard snapshot for the product date.
Availability status, confidence, public role/read labels, and published factual
fields are quoted verbatim in `legacy_capture` and marked as legacy. Stored
engine rows such as `fatigue_scores` are provenance only; score values are
captured opaquely and never compared numerically.

Read capture reads `reliever_daily_read` and `team_daily_read` rows for the
product date. It records read identity, completeness, required-component states,
key reason codes, and targeted fact-check values from cited evidence:

- roster membership state from `pitcher_roster_membership_context`
- last-final-appearance recency from `workload_last_final_appearance` and
  `workload_days_of_rest`
- team composition count from `team_relief_contributor_basis`

Pitcher-day subjects are the union of reliever-read subjects and pitchers with
captured legacy labels. Team-day subjects are the snapshot-authority teams for
the product date.

## Neutral Mapping

| Legacy string | Mapping |
| --- | --- |
| "Available" | `decisive_positive` |
| "Monitor" | `decisive_caution` |
| "Limited" | `decisive_caution` |
| "Avoid" | `decisive_negative` |
| "Unavailable" | `decisive_negative` |
| "Trust Arm" | `informational_role_display` |
| "Bridge Arm" | `informational_role_display` |
| "Coverage Arm" | `informational_role_display` |
| "Depth Arm" | `informational_role_display` |
| "Limited Read" | `informational_degraded_display` |
| "fresh" usage strings | `informational` |

Actionable means mapped `decisive_*`. Informational displays still participate
in presence categories and roster-membership material checks.

## Category Codes

- `legacy_label_present_read_missing`
- `read_present_legacy_label_missing`
- `legacy_actionable_label_on_degraded_read`
- `legacy_confident_on_stale_inputs`
- `legacy_state_contradicts_stored_fact`
- `legacy_team_aggregate_on_degraded_team_read`
- `legacy_team_count_contradicts_composition`
- `legacy_vocabulary_blocked_for_evidence_reads`

The vocabulary category is structural. It is recorded once per run in
`structural_findings`, not as per-subject divergence rows.

## Materiality

`is_material=True` and `escalation_state='escalation_recommended'` are used only
for:

- `legacy_state_contradicts_stored_fact`
- `legacy_actionable_label_on_degraded_read` when the read degradation is
  `conflict`
- displayed pitcher labels where roster-membership evidence says the pitcher is
  not on the active roster

Unknown-driven divergence is never material by itself. Such rows carry a fixed
neutral note that absence of evidence does not adjudicate the legacy label.

## Escalation Policy

Escalations are recommendations to Nickolis only. They do not create automatic
defects, freezes, fixes, flags, swaps, label changes, copy changes, or public
behavior changes. Any live-label action is a separate scoped decision.

## Report Rules

The report renderer writes markdown and JSON to a caller-specified path outside
the repository. It is never auto-committed and is not exposed through any route.

Reports include:

- counts by category, subject type, and day
- denominators stated separately
- no percentages
- no per-subject leaderboards
- no trend framing beyond dated counts
- up to three examples per category, selected deterministically by earliest
  product date and lowest row id
- material rows with both captures and the phrase "candidate for legacy-engine
  defect review"
- structural vocabulary findings
- an internal-only watermark

## Skip Semantics

The sync audit stage runs after composed reads. It is controlled by
`PHASE0E_RECONCILIATION_AUDIT`, default enabled.

If composed reads are missing for the date, or the read build was disabled, the
audit records `run_status='skipped_reads_missing'` and does not fabricate input.
If no published dashboard snapshot exists for the date, it records
`run_status='skipped_legacy_missing'`. Audit exceptions are dead-lettered and
sync continues.

## Downstream Inputs

These audit tables are named inputs to the Phase 0E-06 legal paper and to the
Phase 0D-09 EL production-observation preconditions. They are not public
evidence surfaces.
