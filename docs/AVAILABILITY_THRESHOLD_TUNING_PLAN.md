# Availability Threshold Tuning Plan

## Purpose

This document defines the governance process for future Availability Engine
threshold tuning. BaseballOS should tune bullpen availability from repeatable
evidence, not from one-off impressions or local visual checks.

The plan answers:

- Which status buckets dominate current output?
- Which rules appear most influential?
- Which thresholds deserve investigation?
- What evidence would justify changing a threshold?
- How should tuning branches prove that public trust improves?

## Scope

This plan covers deterministic Availability Engine thresholds used to assign:

- Available
- Monitor
- Limited
- Avoid
- Unavailable

It covers fatigue score thresholds, pitch-count thresholds, appearance
compression thresholds, rest rules, back-to-back rules, and data-state handling
for stale, missing, or incomplete workload inputs.

## Non-Goals

This governance branch does not:

- Change thresholds.
- Change fatigue scoring.
- Change availability statuses.
- Change confidence logic.
- Change API behavior.
- Change snapshot validation mode.
- Change dashboard or frontend behavior.
- Introduce injury, news, private team, Statcast, Hawk-Eye, or paid data inputs.
- Create an automated manager recommendation engine.

## Tuning Philosophy

Availability labels are trust-first decision-support signals. The system should
prefer clear, explainable workload caution over aggressive claims that imply
private team knowledge BaseballOS does not have.

Threshold tuning should follow these principles:

- Tune from audit evidence and reviewed examples.
- Change one variable at a time.
- Preserve the distinction between current availability and latest-workload
  snapshot validation.
- Treat stale, missing, and incomplete data as trust-state signals, not workload
  proof.
- Require before/after distributions for every proposed threshold change.
- Keep explanations stable enough for users to understand what changed.

## Current Threshold Baseline

The authoritative implementation lives in
`backend/services/availability.py` in `AvailabilityThresholds` and the
precedence logic in `_evaluate_workload`. The values below are the baseline for
future tuning branches.

### Fatigue Score Thresholds

| Status effect | Current value |
|---|---:|
| Monitor fatigue score | >= 40.0 |
| Limited fatigue score | >= 60.0 |
| Avoid fatigue score | >= 75.0 |
| Unavailable fatigue score | >= 85.0 with >= 35 pitches yesterday |

### Pitch-Count Thresholds

| Input | Monitor | Limited | Avoid | Unavailable |
|---|---:|---:|---:|---:|
| Pitches yesterday | >= 15 | >= 25 | >= 35 | >= 50 |
| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= 80 |
| Pitches in 5 days | n/a | >= 60 | >= 75 | n/a |

Unavailable can also trigger when `appearances_last_5_days >= 4` and
`pitches_last_5_days >= 75`.

### Appearance Thresholds

| Input | Monitor | Limited | Avoid | Unavailable |
|---|---:|---:|---:|---:|
| Appearances in 3 days | n/a | >= 2 | >= 3 | n/a |
| Appearances in 5 days | >= 2 | >= 3 | >= 4 | >= 4 with >= 75 pitches in 5 days |

### Rest Thresholds

| Rule | Current behavior |
|---|---|
| `days_rest <= 1` | Monitor |
| `days_rest <= 1` with fatigue score >= 50 | Limited |
| Rest alone | Does not produce Avoid or Unavailable |

### Back-to-Back Rules

| Rule | Current behavior |
|---|---|
| Any back-to-back appearances | Limited |
| Back-to-back appearances with >= 35 pitches in 3 days | Avoid |
| Back-to-back alone | Does not produce Unavailable |

### Data-State Handling

| Data state | Current behavior |
|---|---|
| Fresh | Classifies from workload thresholds; confidence defaults to high |
| Stale | Returns Monitor, low confidence |
| Missing | Returns Monitor, low confidence |
| Incomplete | Evaluates available workload, promotes Available to Monitor, low confidence |

The active freshness window is 14 days.

## Current Audit Evidence

Baseline artifacts:

- `backend/reports/availability_threshold_audit.md`
- `backend/reports/availability_explanation_audit.md`
- `backend/reports/availability_threshold_baseline.md`

The current audit reference date is 2026-06-01.

### Current Mode

Current mode is freshness-aware current availability. It should not be used to
tune workload thresholds while the local dataset is stale/missing dominated.

| Metric | Result |
|---|---:|
| Total pitchers | 704 |
| Monitor | 704 |
| Low confidence | 704 |
| Stale | 640 |
| Missing | 64 |
| Fresh | 0 |
| Incomplete | 0 |

Top current reasons:

| Reason | Count |
|---|---:|
| Latest workload data is outside the 14-day freshness window | 640 |
| Missing workload history or fatigue score | 64 |

Observation: current mode shows data-state dominance, not workload-threshold
dominance.

### Latest-Workload Snapshot

Latest-workload snapshot anchors each pitcher to their latest known workload
date for validation. It is useful for threshold study, but it is not current
availability.

| Status | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 99 |
| Unavailable | 163 |

| Confidence | Count |
|---|---:|
| High | 640 |
| Low | 64 |

| Data state | Count |
|---|---:|
| Fresh | 640 |
| Missing | 64 |

Fresh snapshot statuses:

| Status | Count |
|---|---:|
| Monitor | 204 |
| Limited | 174 |
| Avoid | 99 |
| Unavailable | 163 |

Top snapshot reasons:

| Reason | Count |
|---|---:|
| No rest since last appearance | 640 |
| 2 appearances in 5 days | 192 |
| 2 appearances in 3 days | 140 |
| Back-to-back appearances | 80 |
| 3 appearances in 5 days | 69 |
| Missing workload history or fatigue score | 64 |
| Fatigue score is 85.5 | 42 |
| 3 appearances in 4 days | 34 |
| Fatigue score is 85.1 | 31 |

Reason-category snapshot totals from the explanation audit:

| Category | Count |
|---|---:|
| Appearance frequency | 1170 |
| Pitch count | 671 |
| Fatigue | 569 |
| Data state | 64 |

## Observations

- Current mode is not workload-informative for tuning because all 704 pitchers
  are Monitor due to stale or missing data.
- Latest-workload snapshot output has no Available bucket in the local dataset.
- Unavailable classifications are more common than Avoid classifications in
  latest-workload snapshot output.
- Limited, Avoid, and Unavailable together account for 436 of 640 fresh
  latest-workload snapshot pitchers.
- Appearance-frequency reasons are the most common reason category in the
  explanation audit.
- `No rest since last appearance` appears for all 640 fresh latest-workload
  snapshot pitchers because snapshot mode evaluates each pitcher at their latest
  workload date. That is a validation-mode artifact and should not be treated as
  current-day rest evidence.
- The 64 missing pitchers remain low-confidence Monitor in both current and
  snapshot views.

## Threshold Pressure Signals

These are evidence prompts, not tuning decisions.

Potentially aggressive signals to investigate:

- Latest-workload snapshot has no Available bucket.
- Unavailable classifications outnumber Avoid classifications.
- Limited, Avoid, and Unavailable together represent most fresh snapshot rows.
- Appearance-frequency reasons dominate the explanation audit.
- Any back-to-back appearance currently produces at least Limited.
- `days_rest <= 1` produces Monitor, and snapshot mode makes all fresh snapshot
  rows appear as no-rest examples by construction.

Potentially lenient signals to investigate:

- The current local audit does not provide clear evidence that thresholds are
  too lenient because current mode is entirely stale or missing.
- The snapshot `pitches_yesterday` max is 35, so the 50-pitch Unavailable
  yesterday threshold is not exercised by this local snapshot.
- Fresh snapshot Monitor remains a large bucket, but many Monitor rows are
  affected by snapshot rest semantics, so additional evidence is needed before
  concluding that Monitor thresholds are too lenient.

The correct next step is comparison testing, not immediate tuning.

## Candidate Investigation Areas

These areas are candidates for later study. They are not approved changes.

### Fatigue Threshold Review

Investigate whether fatigue score thresholds, especially 75 and 85, align with
the observed status distribution and reason examples.

### Pitch-Count Threshold Review

Investigate whether 3-day and 5-day pitch-count thresholds drive too many heavy
classifications in latest-workload snapshot mode.

### Appearance-Frequency Review

Investigate whether `2 appearances in 3 days`, `2 appearances in 5 days`, and
`3 appearances in 5 days` are appropriately weighted relative to pitch volume.

### Back-to-Back Workload Review

Investigate whether any back-to-back appearance should always produce Limited,
or whether pitch volume and role context should carry more weight.

### Unavailable Bucket Review

Investigate why Unavailable is more common than Avoid in latest-workload
snapshot output and whether that reflects valid workload severity or threshold
compression.

An initial experiment is documented in
`backend/reports/availability_unavailable_threshold_experiment.md`. It compares
baseline Unavailable rules against one-variable candidate adjustments and a
separate multi-signal gate. The report recommendation is `Needs more data`.
Candidate C, raising the 3-day Unavailable pitch threshold from 80 to 90, is the
only one-variable candidate in that report that materially changes the
Unavailable bucket. It moves 57 pitchers from Unavailable to Avoid in
latest-workload snapshot mode.

This experiment is not production approval. Any candidate threshold still
requires human review, near-boundary example review, and a production tuning
branch before adoption.

Candidate C boundary review is documented in
`backend/reports/availability_unavailable_boundary_review.md`. The required
workflow for material threshold movements is:

```text
Threshold experiment
|
v
Boundary review
|
v
Human review
|
v
Potential adoption
```

Boundary review is evidence gathering only. It should identify moved pitchers,
threshold sensitivity, and a review category. It must not approve a threshold
change by itself.

### Confidence Assignment Review

Investigate whether confidence should distinguish missing workload history,
stale current data, and fresh-but-snapshot validation more explicitly in reports
and UI.

### Stale-Data Handling Review

Investigate whether local development workflows need clearer sync guidance, not
threshold tuning, when current mode is entirely stale/missing.

## Evidence Requirements

Future threshold changes require:

- A baseline report from the current thresholds.
- A single proposed variable adjustment.
- A rerun of threshold and explanation audits.
- Before/after status distribution comparison.
- Before/after confidence and data-state comparison.
- Before/after top reason frequency comparison.
- Representative pitcher examples near the changed threshold.
- A written explanation of why the change improves decision support.
- Explicit confirmation that stale/missing data handling remains truthful.

Optional but recommended evidence:

- Historical spot checks against known real bullpen usage patterns.
- Team-level distribution review to detect skew.
- Manual review of at least 10 near-threshold examples.

## Tuning Rules

- No threshold changes without audit evidence.
- No threshold changes based on intuition alone.
- Change one variable at a time.
- Do not combine fatigue, pitch-count, and appearance adjustments in one tuning
  branch.
- Every threshold change requires before/after comparison.
- Every threshold change must preserve explainability.
- Public trust takes priority over aggressive classifications.
- Stale data must not be tuned away or hidden.
- Missing data must not be converted into high-confidence availability.
- Snapshot validation must not be presented as current availability.
- Distribution shifts must be measured before merge review.
- Any threshold change must include regression tests for affected statuses.

## Future Experiment Framework

Future tuning branches should use this workflow:

```text
Baseline
|
v
Single variable adjustment
|
v
Audit rerun
|
v
Comparison report
|
v
Review
|
v
Approval
```

Each experiment should create or update a comparison artifact that includes:

- Branch name.
- Changed threshold.
- Reason for investigation.
- Before distribution.
- After distribution.
- Top changed reason frequencies.
- Near-threshold examples.
- Recommendation: keep, revise, or reject.

Avoid multi-variable tuning until individual variables have been measured and
reviewed.

## Acceptance Criteria For Future Tuning Branches

A future tuning branch is reviewable only when:

- It states exactly which threshold changed.
- It includes before/after reports.
- It preserves stale/missing trust semantics.
- It updates tests for expected behavior.
- It documents the evidence behind the proposed change.
- It avoids unrelated frontend, API, dashboard, or fatigue-scoring changes.
