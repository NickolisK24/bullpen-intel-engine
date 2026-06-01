# Availability Threshold Audit

Generated at: 2026-06-01T22:54:12.674737+00:00
Current reference date: 2026-06-01

This report audits current Availability Engine output using the existing classifier.
It is evidence for later threshold review only; it does not change thresholds.

Trust note: current classifications keep fresh, stale, missing, and incomplete data separate.
Stale or missing Monitor counts should not be read as workload-driven Monitor counts.
Latest-workload snapshot output anchors each pitcher to their latest game date to inspect
historical workload windows; it is not current bullpen availability.

## Current Availability Output

Total pitchers evaluated: 704

### Status Distribution

| Value | Count |
|---|---:|
| Monitor | 704 |

### Confidence Distribution

| Value | Count |
|---|---:|
| low | 704 |

### Data State Distribution

| Value | Count |
|---|---:|
| stale | 640 |
| missing | 64 |

### Status By Data State

| Data state | Status | Count |
|---|---|---:|
| stale | Monitor | 640 |
| missing | Monitor | 64 |

### Top Reason Frequencies

| Reason | Count |
|---|---:|
| Latest game log is older than 14 days | 640 |
| Missing workload history or fatigue score | 64 |

### Workload Input Summary

| Input | Count | Min | Median | Max |
|---|---:|---:|---:|---:|
| fatigue_score | 704 | 6 | 48.5 | 85.9 |
| pitches_yesterday | 704 | 0 | 0 | 0 |
| pitches_last_3_days | 704 | 0 | 0 | 0 |
| pitches_last_5_days | 704 | 0 | 0 | 0 |

### Appearance Distributions

#### appearances_last_3_days

| Appearances | Count |
|---:|---:|
| 0 | 704 |

#### appearances_last_5_days

| Appearances | Count |
|---:|---:|
| 0 | 704 |

### Stale/Incomplete/Missing Counts

| Value | Count |
|---|---:|
| stale | 640 |
| missing | 64 |
| incomplete | 0 |

### Near-Threshold Examples

| Pitcher | Team | Status | Data state | Boundary | Value | Threshold | Distance | Reasons |
|---|---|---|---|---|---:|---:|---:|---|
| Connor Prielipp | MIN | Monitor | stale | Limited fatigue | 60 | 60 | 0 | Latest game log is older than 14 days |
| Keegan Thompson | COL | Monitor | stale | Monitor fatigue | 40 | 40 | 0 | Latest game log is older than 14 days |
| Max Lazar | PHI | Monitor | stale | Monitor fatigue | 40 | 40 | 0 | Latest game log is older than 14 days |
| Tyler Mahle | SF | Monitor | stale | Limited fatigue | 60 | 60 | 0 | Latest game log is older than 14 days |
| Bailey Ober | MIN | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Brady Singer | CIN | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Bryan Woo | SEA | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Bryce Elder | ATL | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Carson Whisenhunt | SF | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Cole Ragans | KC | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Colin Rea | CHC | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |
| Eury Pérez | MIA | Monitor | stale | Unavailable fatigue | 85.1 | 85 | 0.1 | Latest game log is older than 14 days |

## Latest-Workload Snapshot Output

Total pitchers evaluated: 704

### Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 99 |
| Unavailable | 163 |

### Confidence Distribution

| Value | Count |
|---|---:|
| high | 640 |
| low | 64 |

### Data State Distribution

| Value | Count |
|---|---:|
| fresh | 640 |
| missing | 64 |

### Status By Data State

| Data state | Status | Count |
|---|---|---:|
| fresh | Monitor | 204 |
| fresh | Limited | 174 |
| fresh | Avoid | 99 |
| fresh | Unavailable | 163 |
| missing | Monitor | 64 |

### Top Reason Frequencies

| Reason | Count |
|---|---:|
| 0 days rest | 640 |
| 2 appearances in last 5 days | 192 |
| 2 appearances in last 3 days | 140 |
| Back-to-back usage | 80 |
| 3 appearances in last 5 days | 69 |
| Missing workload history or fatigue score | 64 |
| Fatigue score 85.5 | 42 |
| 3 appearances in 4 days | 34 |
| Fatigue score 85.1 | 31 |
| 40 pitches over last 3 days | 11 |
| 90 pitches over last 3 days | 11 |
| 90 pitches over last 5 days | 11 |
| 36 pitches over last 3 days | 11 |
| 95 pitches over last 3 days | 11 |
| 95 pitches over last 5 days | 11 |

### Workload Input Summary

| Input | Count | Min | Median | Max |
|---|---:|---:|---:|---:|
| fatigue_score | 704 | 6 | 48.5 | 85.9 |
| pitches_yesterday | 704 | 0 | 0 | 35 |
| pitches_last_3_days | 704 | 0 | 33.5 | 114 |
| pitches_last_5_days | 704 | 0 | 43 | 114 |

### Appearance Distributions

#### appearances_last_3_days

| Appearances | Count |
|---:|---:|
| 0 | 64 |
| 1 | 492 |
| 2 | 140 |
| 3 | 8 |

#### appearances_last_5_days

| Appearances | Count |
|---:|---:|
| 0 | 64 |
| 1 | 372 |
| 2 | 192 |
| 3 | 69 |
| 4 | 7 |

### Stale/Incomplete/Missing Counts

| Value | Count |
|---|---:|
| stale | 0 |
| missing | 64 |
| incomplete | 0 |

### Near-Threshold Examples

| Pitcher | Team | Status | Data state | Boundary | Value | Threshold | Distance | Reasons |
|---|---|---|---|---|---:|---:|---:|---|
| A.J. Minter | NYM | Avoid | fresh | Limited 3-day appearances | 2 | 2 | 0 | 44 pitches over last 3 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 55.3 |
| A.J. Minter | NYM | Avoid | fresh | Limited 5-day appearances | 3 | 3 | 0 | 44 pitches over last 3 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 55.3 |
| A.J. Puk | AZ | Avoid | fresh | Limited 3-day appearances | 2 | 2 | 0 | 15 pitches yesterday; 36 pitches over last 3 days; 60 pitches over last 5 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 51.7 |
| A.J. Puk | AZ | Avoid | fresh | Limited 5-day appearances | 3 | 3 | 0 | 15 pitches yesterday; 36 pitches over last 3 days; 60 pitches over last 5 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 51.7 |
| A.J. Puk | AZ | Avoid | fresh | Limited 5-day pitches | 60 | 60 | 0 | 15 pitches yesterday; 36 pitches over last 3 days; 60 pitches over last 5 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 51.7 |
| A.J. Puk | AZ | Avoid | fresh | Monitor yesterday pitches | 15 | 15 | 0 | 15 pitches yesterday; 36 pitches over last 3 days; 60 pitches over last 5 days; 2 appearances in last 3 days; 3 appearances in last 5 days; Back-to-back usage; 0 days rest; Fatigue score 51.7 |
| Aaron Ashby | MIL | Limited | fresh | Limited 3-day pitches | 45 | 45 | 0 | 45 pitches over last 3 days; 0 days rest; Fatigue score 65.1 |
| Aaron Bummer | ATL | Limited | fresh | Limited 3-day appearances | 2 | 2 | 0 | 2 appearances in last 3 days; 3 appearances in last 5 days; 0 days rest; Fatigue score 46.0 |
| Aaron Bummer | ATL | Limited | fresh | Limited 5-day appearances | 3 | 3 | 0 | 2 appearances in last 3 days; 3 appearances in last 5 days; 0 days rest; Fatigue score 46.0 |
| Abner Uribe | MIL | Limited | fresh | Limited 3-day appearances | 2 | 2 | 0 | 2 appearances in last 3 days; 2 appearances in last 5 days; Back-to-back usage; 0 days rest |
| Abner Uribe | MIL | Limited | fresh | Monitor 5-day appearances | 2 | 2 | 0 | 2 appearances in last 3 days; 2 appearances in last 5 days; Back-to-back usage; 0 days rest |
| Adrian Morejon | SD | Limited | fresh | Limited 3-day appearances | 2 | 2 | 0 | 43 pitches over last 3 days; 72 pitches over last 5 days; 2 appearances in last 3 days; 3 appearances in last 5 days; 0 days rest; Fatigue score 51.4 |
