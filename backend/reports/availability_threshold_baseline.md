# Availability Threshold Baseline

Generated from the current Availability Engine V1 thresholds and audit outputs
on 2026-06-01.

This artifact is a comparison baseline for future threshold tuning branches. It
does not change thresholds, fatigue scoring, API behavior, snapshot mode,
dashboard behavior, or frontend behavior.

## Source Artifacts

- Threshold implementation: `backend/services/availability.py`
- Threshold audit: `backend/reports/availability_threshold_audit.md`
- Explanation audit: `backend/reports/availability_explanation_audit.md`
- Governance plan: `docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`

## Current Thresholds

### Fatigue Score

| Status effect | Current value |
|---|---:|
| Monitor fatigue score | >= 40.0 |
| Limited fatigue score | >= 60.0 |
| Avoid fatigue score | >= 75.0 |
| Unavailable fatigue score | >= 85.0 with >= 35 pitches yesterday |

### Pitch Counts

| Input | Monitor | Limited | Avoid | Unavailable |
|---|---:|---:|---:|---:|
| Pitches yesterday | >= 15 | >= 25 | >= 35 | >= 50 |
| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= 80 |
| Pitches in 5 days | n/a | >= 60 | >= 75 | n/a |

Unavailable also triggers when `appearances_last_5_days >= 4` and
`pitches_last_5_days >= 75`.

### Appearance Frequency

| Input | Monitor | Limited | Avoid | Unavailable |
|---|---:|---:|---:|---:|
| Appearances in 3 days | n/a | >= 2 | >= 3 | n/a |
| Appearances in 5 days | >= 2 | >= 3 | >= 4 | >= 4 with >= 75 pitches in 5 days |

### Rest and Back-to-Back Rules

| Rule | Current behavior |
|---|---|
| `days_rest <= 1` | Monitor |
| `days_rest <= 1` with fatigue score >= 50 | Limited |
| Any back-to-back appearances | Limited |
| Back-to-back appearances with >= 35 pitches in 3 days | Avoid |
| Rest alone | Does not produce Avoid or Unavailable |
| Back-to-back alone | Does not produce Unavailable |

### Data State

| Data state | Current behavior |
|---|---|
| Fresh | Classifies from workload thresholds; confidence defaults to high |
| Stale | Monitor, low confidence |
| Missing | Monitor, low confidence |
| Incomplete | Evaluates available workload, promotes Available to Monitor, low confidence |

The active freshness window is 14 days.

## Current-Mode Baseline

Current mode is freshness-aware current availability.

| Metric | Count |
|---|---:|
| Total pitchers | 704 |
| Monitor | 704 |
| High confidence | 0 |
| Medium confidence | 0 |
| Low confidence | 704 |
| Fresh | 0 |
| Stale | 640 |
| Missing | 64 |
| Incomplete | 0 |

### Current-Mode Top Reasons

| Reason | Count |
|---|---:|
| Latest workload data is outside the 14-day freshness window | 640 |
| Missing workload history or fatigue score | 64 |

Current mode is not workload-informative for threshold tuning while local data
is entirely stale or missing.

## Latest-Workload Snapshot Baseline

Latest-workload snapshot output is validation-only and not current bullpen
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

### Fresh Snapshot Statuses

| Status | Count |
|---|---:|
| Monitor | 204 |
| Limited | 174 |
| Avoid | 99 |
| Unavailable | 163 |

### Snapshot Workload Input Summary

| Input | Count | Min | Median | Max |
|---|---:|---:|---:|---:|
| fatigue_score | 704 | 6 | 48.5 | 85.9 |
| pitches_yesterday | 704 | 0 | 0 | 35 |
| pitches_last_3_days | 704 | 0 | 33.5 | 114 |
| pitches_last_5_days | 704 | 0 | 43 | 114 |

### Snapshot Appearance Distributions

| Appearances in 3 days | Count |
|---:|---:|
| 0 | 64 |
| 1 | 492 |
| 2 | 140 |
| 3 | 8 |

| Appearances in 5 days | Count |
|---:|---:|
| 0 | 64 |
| 1 | 372 |
| 2 | 192 |
| 3 | 69 |
| 4 | 7 |

### Snapshot Top Reasons

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

### Snapshot Reason Categories

| Category | Count |
|---|---:|
| Appearance frequency | 1170 |
| Pitch count | 671 |
| Fatigue | 569 |
| Data state | 64 |

## Baseline Observations

- Current mode is entirely Monitor because local data is stale or missing.
- Current mode has 704 low-confidence classifications.
- Latest-workload snapshot has no Available bucket.
- Latest-workload snapshot has more Unavailable classifications than Avoid
  classifications.
- Limited, Avoid, and Unavailable together account for 436 of 640 fresh
  latest-workload snapshot pitchers.
- Appearance-frequency reasons are the most common reason category.
- `No rest since last appearance` appears for all 640 fresh snapshot pitchers
  because snapshot mode evaluates each pitcher at their latest workload date.
  This is a validation-mode artifact, not current rest evidence.
- Missing workload history remains visible as low-confidence Monitor.

## Use In Future Tuning

Future tuning branches should compare against this baseline with:

- One changed variable.
- Rerun threshold audit.
- Rerun explanation audit.
- Before/after status distribution.
- Before/after confidence and data-state distribution.
- Before/after reason frequencies.
- Representative near-threshold examples.

No threshold change should be reviewed without a comparison back to this
baseline.
