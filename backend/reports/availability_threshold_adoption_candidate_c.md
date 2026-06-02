# Availability Threshold Adoption: Candidate C

Reference date: 2026-06-01

This report records the first governed production threshold change for the
BaseballOS Availability Engine.

## Adopted Change

| Threshold | Previous value | Adopted value |
|---|---:|---:|
| Unavailable pitches in 3 days | >= 80 | >= 90 |

No other thresholds changed.

## Reason For Adoption

Candidate C was evaluated through the threshold audit, unavailable-threshold
experiment, and boundary-review process. The change addresses threshold
compression between Avoid and Unavailable without weakening other Unavailable
rules.

The boundary review found that all moved pitchers had:

- 80-89 pitches in 3 days.
- No pitches yesterday.
- No 4+ appearances in 5 days.
- No remaining Candidate C Unavailable severe signal.

This supports treating those cases as Avoid unless another Unavailable rule
fires.

## Before Distribution

Latest-workload snapshot before Candidate C adoption:

| Status | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 99 |
| Unavailable | 163 |

## After Distribution

Latest-workload snapshot after Candidate C adoption:

| Status | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

Current freshness-aware mode remains stale/missing dominated in local data:

| Status | Count |
|---|---:|
| Monitor | 704 |

## Moved Pitcher Count

| Transition | Count |
|---|---:|
| Unavailable -> Avoid | 57 |

Candidate C affected 35.0% of the pre-adoption Unavailable bucket.

## Boundary Review Summary

Representative moved cases:

| Pitcher | 3-day pitches | Transition |
|---|---:|---|
| Andrew Painter | 80 | Unavailable -> Avoid |
| DJ Herz | 81 | Unavailable -> Avoid |
| Max Fried | 89 | Unavailable -> Avoid |

Representative retained Unavailable case:

| Pitcher | 3-day pitches | Transition |
|---|---:|---|
| Anthony Kay | 90 | Unavailable -> Unavailable |

Supporting artifacts:

- `backend/reports/availability_threshold_audit.md`
- `backend/reports/availability_unavailable_threshold_experiment.md`
- `backend/reports/availability_unavailable_boundary_review.md`
- `backend/reports/availability_threshold_baseline.md`

## Risks

- The local current-mode dataset remains stale/missing dominated, so adoption is
  based on latest-workload snapshot evidence rather than current live bullpen
  availability.
- The change reduces Unavailable classifications driven only by 80-89 pitches
  in 3 days. Other workload signals may still justify Unavailable through
  separate rules.
- Future data syncs may change distribution counts and should be audited against
  the adopted baseline before any additional threshold changes.
- BaseballOS still does not include injury, clubhouse, medical, or team-reported
  availability data. Unavailable remains workload-unavailable only.

## Adoption Decision

Candidate C is adopted into production Availability Engine thresholds.

The effective production rule is:

```text
Unavailable when pitches_last_3_days >= 90
```

This adoption does not change fatigue scoring, yesterday pitch thresholds,
five-day thresholds, appearance thresholds, confidence logic, stale/missing data
handling, API response shape, frontend behavior, dashboard behavior, or snapshot
mode.
