# Availability Explanation Quality Audit

Generated at: 2026-06-02T00:29:25.376441+00:00
Current reference date: 2026-06-01

This report audits Availability Engine explanation text using existing classified records.
It is evidence for wording consistency and review only; it does not change thresholds,
status outcomes, fatigue scoring, or API response structure.

Trust note: reasons describe deterministic workload or data-state facts. Limitations
describe context BaseballOS does not know, such as injuries or team-reported availability.

## Current Availability Explanations

Total pitchers evaluated: 704
Total reasons observed: 704
Unique reasons observed: 2
Total limitations observed: 2112
Unique limitations observed: 4

### Reason Category Distribution

| Category | Count |
|---|---:|
| data_state | 704 |

### Observed Reason Frequencies

| Category | Text | Count |
|---|---|---:|
| data_state | Latest workload data is outside the 14-day freshness window | 640 |
| data_state | Missing workload history or fatigue score | 64 |

### Limitation Category Distribution

| Category | Count |
|---|---:|
| data_state | 704 |
| limitation | 1408 |

### Observed Limitation Frequencies

| Category | Text | Count |
|---|---|---:|
| data_state | Stale workload data must not be treated as current availability | 640 |
| data_state | Availability confidence is low because workload inputs are missing | 64 |
| limitation | No injury data available | 704 |
| limitation | No team-reported availability data available | 704 |

### Possible Reason Catalog

| Category | Rule | Template | Example |
|---|---|---|---|
| pitch_count | Yesterday pitch volume | {n} pitches yesterday | 42 pitches yesterday |
| pitch_count | Three-day pitch volume | {n} pitches in 3 days | 54 pitches in 3 days |
| pitch_count | Five-day pitch volume | {n} pitches in 5 days | 75 pitches in 5 days |
| appearance_frequency | Three-day appearance compression | {n} appearances in 3 days | 2 appearances in 3 days |
| appearance_frequency | Four-day appearance compression | 3 appearances in 4 days | 3 appearances in 4 days |
| appearance_frequency | Five-day appearance compression | {n} appearances in 5 days | 4 appearances in 5 days |
| appearance_frequency | Back-to-back appearances | Back-to-back appearances | Back-to-back appearances |
| rest | No rest | No rest since last appearance | No rest since last appearance |
| rest | One rest day | Only 1 day of rest | Only 1 day of rest |
| fatigue | Fatigue score | Fatigue score is {score} | Fatigue score is 55.3 |
| data_state | Missing workload data | Missing workload history or fatigue score | Missing workload history or fatigue score |
| data_state | Incomplete workload data | Incomplete workload inputs | Incomplete workload inputs |
| data_state | Stale workload data | Latest workload data is outside the {days}-day freshness window | Latest workload data is outside the 14-day freshness window |
| fallback | Unmapped restriction | Availability restriction rule matched without a displayable workload input | Availability restriction rule matched without a displayable workload input |

## Latest-Workload Snapshot Explanations

Total pitchers evaluated: 704
Total reasons observed: 2474
Unique reasons observed: 404
Total limitations observed: 1472
Unique limitations observed: 3

### Reason Category Distribution

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Observed Reason Frequencies

| Category | Text | Count |
|---|---|---:|
| pitch_count | 36 pitches in 3 days | 11 |
| pitch_count | 40 pitches in 3 days | 11 |
| pitch_count | 90 pitches in 3 days | 11 |
| pitch_count | 90 pitches in 5 days | 11 |
| pitch_count | 95 pitches in 3 days | 11 |
| pitch_count | 95 pitches in 5 days | 11 |
| pitch_count | 31 pitches in 3 days | 10 |
| pitch_count | 33 pitches in 3 days | 10 |
| pitch_count | 34 pitches in 3 days | 10 |
| pitch_count | 50 pitches in 3 days | 10 |
| pitch_count | 85 pitches in 3 days | 10 |
| pitch_count | 85 pitches in 5 days | 10 |
| pitch_count | 94 pitches in 3 days | 10 |
| pitch_count | 94 pitches in 5 days | 10 |
| pitch_count | 32 pitches in 3 days | 9 |
| pitch_count | 38 pitches in 3 days | 9 |
| pitch_count | 42 pitches in 3 days | 9 |
| pitch_count | 91 pitches in 5 days | 9 |
| pitch_count | 93 pitches in 3 days | 9 |
| pitch_count | 93 pitches in 5 days | 9 |
| pitch_count | 17 pitches yesterday | 8 |
| pitch_count | 68 pitches in 5 days | 8 |
| pitch_count | 79 pitches in 3 days | 8 |
| pitch_count | 79 pitches in 5 days | 8 |
| pitch_count | 82 pitches in 3 days | 8 |
| pitch_count | 82 pitches in 5 days | 8 |
| pitch_count | 91 pitches in 3 days | 8 |
| pitch_count | 97 pitches in 3 days | 8 |
| pitch_count | 97 pitches in 5 days | 8 |
| pitch_count | 30 pitches in 3 days | 7 |
| pitch_count | 39 pitches in 3 days | 7 |
| pitch_count | 41 pitches in 3 days | 7 |
| pitch_count | 68 pitches in 3 days | 7 |
| pitch_count | 86 pitches in 3 days | 7 |
| pitch_count | 86 pitches in 5 days | 7 |
| pitch_count | 87 pitches in 5 days | 7 |
| pitch_count | 88 pitches in 3 days | 7 |
| pitch_count | 88 pitches in 5 days | 7 |
| pitch_count | 92 pitches in 3 days | 7 |
| pitch_count | 92 pitches in 5 days | 7 |
| pitch_count | 43 pitches in 3 days | 6 |
| pitch_count | 44 pitches in 3 days | 6 |
| pitch_count | 60 pitches in 5 days | 6 |
| pitch_count | 62 pitches in 5 days | 6 |
| pitch_count | 70 pitches in 5 days | 6 |
| pitch_count | 74 pitches in 5 days | 6 |
| pitch_count | 80 pitches in 3 days | 6 |
| pitch_count | 80 pitches in 5 days | 6 |
| pitch_count | 87 pitches in 3 days | 6 |
| pitch_count | 96 pitches in 3 days | 6 |
| pitch_count | 96 pitches in 5 days | 6 |
| pitch_count | 98 pitches in 5 days | 6 |
| pitch_count | 19 pitches yesterday | 5 |
| pitch_count | 22 pitches yesterday | 5 |
| pitch_count | 35 pitches in 3 days | 5 |
| pitch_count | 37 pitches in 3 days | 5 |
| pitch_count | 67 pitches in 5 days | 5 |
| pitch_count | 76 pitches in 3 days | 5 |
| pitch_count | 77 pitches in 5 days | 5 |
| pitch_count | 84 pitches in 3 days | 5 |
| pitch_count | 84 pitches in 5 days | 5 |
| pitch_count | 98 pitches in 3 days | 5 |
| pitch_count | 102 pitches in 3 days | 4 |
| pitch_count | 102 pitches in 5 days | 4 |
| pitch_count | 105 pitches in 5 days | 4 |
| pitch_count | 15 pitches yesterday | 4 |
| pitch_count | 46 pitches in 3 days | 4 |
| pitch_count | 47 pitches in 3 days | 4 |
| pitch_count | 49 pitches in 3 days | 4 |
| pitch_count | 55 pitches in 3 days | 4 |
| pitch_count | 60 pitches in 3 days | 4 |
| pitch_count | 61 pitches in 5 days | 4 |
| pitch_count | 70 pitches in 3 days | 4 |
| pitch_count | 72 pitches in 5 days | 4 |
| pitch_count | 73 pitches in 3 days | 4 |
| pitch_count | 73 pitches in 5 days | 4 |
| pitch_count | 76 pitches in 5 days | 4 |
| pitch_count | 77 pitches in 3 days | 4 |
| pitch_count | 99 pitches in 3 days | 4 |
| pitch_count | 99 pitches in 5 days | 4 |
| pitch_count | 103 pitches in 3 days | 3 |
| pitch_count | 103 pitches in 5 days | 3 |
| pitch_count | 104 pitches in 3 days | 3 |
| pitch_count | 104 pitches in 5 days | 3 |
| pitch_count | 105 pitches in 3 days | 3 |
| pitch_count | 106 pitches in 5 days | 3 |
| pitch_count | 26 pitches yesterday | 3 |
| pitch_count | 45 pitches in 3 days | 3 |
| pitch_count | 53 pitches in 3 days | 3 |
| pitch_count | 54 pitches in 3 days | 3 |
| pitch_count | 57 pitches in 3 days | 3 |
| pitch_count | 58 pitches in 3 days | 3 |
| pitch_count | 61 pitches in 3 days | 3 |
| pitch_count | 62 pitches in 3 days | 3 |
| pitch_count | 64 pitches in 5 days | 3 |
| pitch_count | 69 pitches in 5 days | 3 |
| pitch_count | 74 pitches in 3 days | 3 |
| pitch_count | 75 pitches in 3 days | 3 |
| pitch_count | 75 pitches in 5 days | 3 |
| pitch_count | 81 pitches in 3 days | 3 |
| pitch_count | 81 pitches in 5 days | 3 |
| pitch_count | 83 pitches in 3 days | 3 |
| pitch_count | 83 pitches in 5 days | 3 |
| pitch_count | 100 pitches in 3 days | 2 |
| pitch_count | 100 pitches in 5 days | 2 |
| pitch_count | 101 pitches in 3 days | 2 |
| pitch_count | 101 pitches in 5 days | 2 |
| pitch_count | 106 pitches in 3 days | 2 |
| pitch_count | 114 pitches in 5 days | 2 |
| pitch_count | 16 pitches yesterday | 2 |
| pitch_count | 18 pitches yesterday | 2 |
| pitch_count | 20 pitches yesterday | 2 |
| pitch_count | 52 pitches in 3 days | 2 |
| pitch_count | 56 pitches in 3 days | 2 |
| pitch_count | 63 pitches in 3 days | 2 |
| pitch_count | 63 pitches in 5 days | 2 |
| pitch_count | 67 pitches in 3 days | 2 |
| pitch_count | 69 pitches in 3 days | 2 |
| pitch_count | 71 pitches in 5 days | 2 |
| pitch_count | 72 pitches in 3 days | 2 |
| pitch_count | 78 pitches in 3 days | 2 |
| pitch_count | 89 pitches in 3 days | 2 |
| pitch_count | 89 pitches in 5 days | 2 |
| pitch_count | 107 pitches in 3 days | 1 |
| pitch_count | 107 pitches in 5 days | 1 |
| pitch_count | 109 pitches in 3 days | 1 |
| pitch_count | 109 pitches in 5 days | 1 |
| pitch_count | 113 pitches in 3 days | 1 |
| pitch_count | 113 pitches in 5 days | 1 |
| pitch_count | 114 pitches in 3 days | 1 |
| pitch_count | 24 pitches yesterday | 1 |
| pitch_count | 25 pitches yesterday | 1 |
| pitch_count | 29 pitches yesterday | 1 |
| pitch_count | 31 pitches yesterday | 1 |
| pitch_count | 32 pitches yesterday | 1 |
| pitch_count | 35 pitches yesterday | 1 |
| pitch_count | 48 pitches in 3 days | 1 |
| pitch_count | 51 pitches in 3 days | 1 |
| pitch_count | 59 pitches in 3 days | 1 |
| pitch_count | 65 pitches in 5 days | 1 |
| pitch_count | 71 pitches in 3 days | 1 |
| pitch_count | 78 pitches in 5 days | 1 |
| appearance_frequency | No rest since last appearance | 640 |
| appearance_frequency | 2 appearances in 5 days | 192 |
| appearance_frequency | 2 appearances in 3 days | 140 |
| appearance_frequency | Back-to-back appearances | 80 |
| appearance_frequency | 3 appearances in 5 days | 69 |
| appearance_frequency | 3 appearances in 4 days | 34 |
| appearance_frequency | 3 appearances in 3 days | 8 |
| appearance_frequency | 4 appearances in 5 days | 7 |
| fatigue | Fatigue score is 85.5 | 42 |
| fatigue | Fatigue score is 85.1 | 31 |
| fatigue | Fatigue score is 45.9 | 8 |
| fatigue | Fatigue score is 42.4 | 7 |
| fatigue | Fatigue score is 44.3 | 6 |
| fatigue | Fatigue score is 44.9 | 6 |
| fatigue | Fatigue score is 45.1 | 6 |
| fatigue | Fatigue score is 45.5 | 6 |
| fatigue | Fatigue score is 46.8 | 6 |
| fatigue | Fatigue score is 49.2 | 6 |
| fatigue | Fatigue score is 42.7 | 5 |
| fatigue | Fatigue score is 44.5 | 5 |
| fatigue | Fatigue score is 46.3 | 5 |
| fatigue | Fatigue score is 47 | 5 |
| fatigue | Fatigue score is 47.5 | 5 |
| fatigue | Fatigue score is 40.9 | 4 |
| fatigue | Fatigue score is 42.2 | 4 |
| fatigue | Fatigue score is 43.6 | 4 |
| fatigue | Fatigue score is 43.8 | 4 |
| fatigue | Fatigue score is 45.4 | 4 |
| fatigue | Fatigue score is 45.8 | 4 |
| fatigue | Fatigue score is 46.4 | 4 |
| fatigue | Fatigue score is 47.9 | 4 |
| fatigue | Fatigue score is 48.3 | 4 |
| fatigue | Fatigue score is 49 | 4 |
| fatigue | Fatigue score is 51.2 | 4 |
| fatigue | Fatigue score is 54.7 | 4 |
| fatigue | Fatigue score is 57.8 | 4 |
| fatigue | Fatigue score is 58.9 | 4 |
| fatigue | Fatigue score is 60.2 | 4 |
| fatigue | Fatigue score is 65.4 | 4 |
| fatigue | Fatigue score is 41.3 | 3 |
| fatigue | Fatigue score is 41.4 | 3 |
| fatigue | Fatigue score is 41.7 | 3 |
| fatigue | Fatigue score is 41.8 | 3 |
| fatigue | Fatigue score is 41.9 | 3 |
| fatigue | Fatigue score is 42.1 | 3 |
| fatigue | Fatigue score is 43.2 | 3 |
| fatigue | Fatigue score is 43.5 | 3 |
| fatigue | Fatigue score is 43.9 | 3 |
| fatigue | Fatigue score is 44.4 | 3 |
| fatigue | Fatigue score is 45.7 | 3 |
| fatigue | Fatigue score is 46.6 | 3 |
| fatigue | Fatigue score is 47.3 | 3 |
| fatigue | Fatigue score is 47.4 | 3 |
| fatigue | Fatigue score is 47.8 | 3 |
| fatigue | Fatigue score is 48 | 3 |
| fatigue | Fatigue score is 49.1 | 3 |
| fatigue | Fatigue score is 49.4 | 3 |
| fatigue | Fatigue score is 49.9 | 3 |
| fatigue | Fatigue score is 50.5 | 3 |
| fatigue | Fatigue score is 51.3 | 3 |
| fatigue | Fatigue score is 51.4 | 3 |
| fatigue | Fatigue score is 53 | 3 |
| fatigue | Fatigue score is 53.3 | 3 |
| fatigue | Fatigue score is 54.3 | 3 |
| fatigue | Fatigue score is 55.5 | 3 |
| fatigue | Fatigue score is 55.8 | 3 |
| fatigue | Fatigue score is 58.1 | 3 |
| fatigue | Fatigue score is 60.6 | 3 |
| fatigue | Fatigue score is 62.4 | 3 |
| fatigue | Fatigue score is 66.1 | 3 |
| fatigue | Fatigue score is 66.2 | 3 |
| fatigue | Fatigue score is 67.4 | 3 |
| fatigue | Fatigue score is 68 | 3 |
| fatigue | Fatigue score is 68.4 | 3 |
| fatigue | Fatigue score is 69.6 | 3 |
| fatigue | Fatigue score is 72 | 3 |
| fatigue | Fatigue score is 72.6 | 3 |
| fatigue | Fatigue score is 40 | 2 |
| fatigue | Fatigue score is 40.1 | 2 |
| fatigue | Fatigue score is 40.3 | 2 |
| fatigue | Fatigue score is 40.4 | 2 |
| fatigue | Fatigue score is 40.8 | 2 |
| fatigue | Fatigue score is 41.6 | 2 |
| fatigue | Fatigue score is 42 | 2 |
| fatigue | Fatigue score is 42.6 | 2 |
| fatigue | Fatigue score is 42.8 | 2 |
| fatigue | Fatigue score is 43 | 2 |
| fatigue | Fatigue score is 43.1 | 2 |
| fatigue | Fatigue score is 43.3 | 2 |
| fatigue | Fatigue score is 44 | 2 |
| fatigue | Fatigue score is 44.6 | 2 |
| fatigue | Fatigue score is 44.8 | 2 |
| fatigue | Fatigue score is 45 | 2 |
| fatigue | Fatigue score is 45.3 | 2 |
| fatigue | Fatigue score is 46.2 | 2 |
| fatigue | Fatigue score is 46.7 | 2 |
| fatigue | Fatigue score is 46.9 | 2 |
| fatigue | Fatigue score is 47.2 | 2 |
| fatigue | Fatigue score is 47.7 | 2 |
| fatigue | Fatigue score is 48.5 | 2 |
| fatigue | Fatigue score is 48.6 | 2 |
| fatigue | Fatigue score is 49.7 | 2 |
| fatigue | Fatigue score is 50.1 | 2 |
| fatigue | Fatigue score is 50.3 | 2 |
| fatigue | Fatigue score is 51.8 | 2 |
| fatigue | Fatigue score is 51.9 | 2 |
| fatigue | Fatigue score is 52.3 | 2 |
| fatigue | Fatigue score is 52.9 | 2 |
| fatigue | Fatigue score is 53.5 | 2 |
| fatigue | Fatigue score is 53.7 | 2 |
| fatigue | Fatigue score is 53.9 | 2 |
| fatigue | Fatigue score is 55.6 | 2 |
| fatigue | Fatigue score is 55.9 | 2 |
| fatigue | Fatigue score is 56.6 | 2 |
| fatigue | Fatigue score is 58.5 | 2 |
| fatigue | Fatigue score is 59.1 | 2 |
| fatigue | Fatigue score is 59.5 | 2 |
| fatigue | Fatigue score is 59.8 | 2 |
| fatigue | Fatigue score is 60 | 2 |
| fatigue | Fatigue score is 60.3 | 2 |
| fatigue | Fatigue score is 62.3 | 2 |
| fatigue | Fatigue score is 63 | 2 |
| fatigue | Fatigue score is 63.5 | 2 |
| fatigue | Fatigue score is 64.2 | 2 |
| fatigue | Fatigue score is 64.6 | 2 |
| fatigue | Fatigue score is 65.1 | 2 |
| fatigue | Fatigue score is 65.2 | 2 |
| fatigue | Fatigue score is 65.3 | 2 |
| fatigue | Fatigue score is 65.5 | 2 |
| fatigue | Fatigue score is 65.6 | 2 |
| fatigue | Fatigue score is 66.7 | 2 |
| fatigue | Fatigue score is 67.2 | 2 |
| fatigue | Fatigue score is 67.8 | 2 |
| fatigue | Fatigue score is 70.3 | 2 |
| fatigue | Fatigue score is 71.5 | 2 |
| fatigue | Fatigue score is 40.2 | 1 |
| fatigue | Fatigue score is 40.6 | 1 |
| fatigue | Fatigue score is 41 | 1 |
| fatigue | Fatigue score is 41.1 | 1 |
| fatigue | Fatigue score is 41.5 | 1 |
| fatigue | Fatigue score is 42.3 | 1 |
| fatigue | Fatigue score is 42.5 | 1 |
| fatigue | Fatigue score is 42.9 | 1 |
| fatigue | Fatigue score is 43.4 | 1 |
| fatigue | Fatigue score is 43.7 | 1 |
| fatigue | Fatigue score is 44.1 | 1 |
| fatigue | Fatigue score is 44.2 | 1 |
| fatigue | Fatigue score is 45.2 | 1 |
| fatigue | Fatigue score is 46 | 1 |
| fatigue | Fatigue score is 46.5 | 1 |
| fatigue | Fatigue score is 47.6 | 1 |
| fatigue | Fatigue score is 48.1 | 1 |
| fatigue | Fatigue score is 48.2 | 1 |
| fatigue | Fatigue score is 48.4 | 1 |
| fatigue | Fatigue score is 48.7 | 1 |
| fatigue | Fatigue score is 49.5 | 1 |
| fatigue | Fatigue score is 49.6 | 1 |
| fatigue | Fatigue score is 50 | 1 |
| fatigue | Fatigue score is 50.2 | 1 |
| fatigue | Fatigue score is 50.4 | 1 |
| fatigue | Fatigue score is 50.6 | 1 |
| fatigue | Fatigue score is 50.8 | 1 |
| fatigue | Fatigue score is 50.9 | 1 |
| fatigue | Fatigue score is 51 | 1 |
| fatigue | Fatigue score is 51.1 | 1 |
| fatigue | Fatigue score is 51.5 | 1 |
| fatigue | Fatigue score is 51.6 | 1 |
| fatigue | Fatigue score is 51.7 | 1 |
| fatigue | Fatigue score is 52.1 | 1 |
| fatigue | Fatigue score is 52.4 | 1 |
| fatigue | Fatigue score is 52.5 | 1 |
| fatigue | Fatigue score is 52.6 | 1 |
| fatigue | Fatigue score is 52.7 | 1 |
| fatigue | Fatigue score is 53.1 | 1 |
| fatigue | Fatigue score is 53.2 | 1 |
| fatigue | Fatigue score is 53.8 | 1 |
| fatigue | Fatigue score is 54.2 | 1 |
| fatigue | Fatigue score is 54.4 | 1 |
| fatigue | Fatigue score is 54.5 | 1 |
| fatigue | Fatigue score is 54.9 | 1 |
| fatigue | Fatigue score is 55.1 | 1 |
| fatigue | Fatigue score is 55.2 | 1 |
| fatigue | Fatigue score is 55.3 | 1 |
| fatigue | Fatigue score is 55.4 | 1 |
| fatigue | Fatigue score is 55.7 | 1 |
| fatigue | Fatigue score is 56.5 | 1 |
| fatigue | Fatigue score is 56.8 | 1 |
| fatigue | Fatigue score is 56.9 | 1 |
| fatigue | Fatigue score is 57 | 1 |
| fatigue | Fatigue score is 57.1 | 1 |
| fatigue | Fatigue score is 57.2 | 1 |
| fatigue | Fatigue score is 57.3 | 1 |
| fatigue | Fatigue score is 57.5 | 1 |
| fatigue | Fatigue score is 57.6 | 1 |
| fatigue | Fatigue score is 57.7 | 1 |
| fatigue | Fatigue score is 57.9 | 1 |
| fatigue | Fatigue score is 58 | 1 |
| fatigue | Fatigue score is 58.2 | 1 |
| fatigue | Fatigue score is 58.8 | 1 |
| fatigue | Fatigue score is 59.3 | 1 |
| fatigue | Fatigue score is 59.6 | 1 |
| fatigue | Fatigue score is 59.9 | 1 |
| fatigue | Fatigue score is 60.4 | 1 |
| fatigue | Fatigue score is 60.9 | 1 |
| fatigue | Fatigue score is 61.1 | 1 |
| fatigue | Fatigue score is 61.2 | 1 |
| fatigue | Fatigue score is 61.3 | 1 |
| fatigue | Fatigue score is 61.5 | 1 |
| fatigue | Fatigue score is 61.6 | 1 |
| fatigue | Fatigue score is 61.8 | 1 |
| fatigue | Fatigue score is 61.9 | 1 |
| fatigue | Fatigue score is 62 | 1 |
| fatigue | Fatigue score is 62.5 | 1 |
| fatigue | Fatigue score is 63.2 | 1 |
| fatigue | Fatigue score is 63.3 | 1 |
| fatigue | Fatigue score is 63.4 | 1 |
| fatigue | Fatigue score is 63.8 | 1 |
| fatigue | Fatigue score is 64 | 1 |
| fatigue | Fatigue score is 64.1 | 1 |
| fatigue | Fatigue score is 64.8 | 1 |
| fatigue | Fatigue score is 65 | 1 |
| fatigue | Fatigue score is 65.8 | 1 |
| fatigue | Fatigue score is 66 | 1 |
| fatigue | Fatigue score is 66.4 | 1 |
| fatigue | Fatigue score is 66.6 | 1 |
| fatigue | Fatigue score is 66.8 | 1 |
| fatigue | Fatigue score is 67 | 1 |
| fatigue | Fatigue score is 67.3 | 1 |
| fatigue | Fatigue score is 68.1 | 1 |
| fatigue | Fatigue score is 68.3 | 1 |
| fatigue | Fatigue score is 68.6 | 1 |
| fatigue | Fatigue score is 68.7 | 1 |
| fatigue | Fatigue score is 68.9 | 1 |
| fatigue | Fatigue score is 69 | 1 |
| fatigue | Fatigue score is 69.1 | 1 |
| fatigue | Fatigue score is 69.9 | 1 |
| fatigue | Fatigue score is 70 | 1 |
| fatigue | Fatigue score is 70.2 | 1 |
| fatigue | Fatigue score is 70.6 | 1 |
| fatigue | Fatigue score is 71.1 | 1 |
| fatigue | Fatigue score is 71.3 | 1 |
| fatigue | Fatigue score is 71.6 | 1 |
| fatigue | Fatigue score is 72.3 | 1 |
| fatigue | Fatigue score is 72.4 | 1 |
| fatigue | Fatigue score is 72.5 | 1 |
| fatigue | Fatigue score is 73.1 | 1 |
| fatigue | Fatigue score is 73.2 | 1 |
| fatigue | Fatigue score is 73.8 | 1 |
| fatigue | Fatigue score is 74.7 | 1 |
| fatigue | Fatigue score is 74.8 | 1 |
| fatigue | Fatigue score is 75.2 | 1 |
| fatigue | Fatigue score is 75.4 | 1 |
| fatigue | Fatigue score is 75.5 | 1 |
| fatigue | Fatigue score is 76.6 | 1 |
| fatigue | Fatigue score is 78.5 | 1 |
| fatigue | Fatigue score is 79 | 1 |
| fatigue | Fatigue score is 80.3 | 1 |
| fatigue | Fatigue score is 81.4 | 1 |
| fatigue | Fatigue score is 82.1 | 1 |
| fatigue | Fatigue score is 82.5 | 1 |
| fatigue | Fatigue score is 85.9 | 1 |
| data_state | Missing workload history or fatigue score | 64 |

### Limitation Category Distribution

| Category | Count |
|---|---:|
| data_state | 64 |
| limitation | 1408 |

### Observed Limitation Frequencies

| Category | Text | Count |
|---|---|---:|
| data_state | Availability confidence is low because workload inputs are missing | 64 |
| limitation | No injury data available | 704 |
| limitation | No team-reported availability data available | 704 |

### Possible Reason Catalog

| Category | Rule | Template | Example |
|---|---|---|---|
| pitch_count | Yesterday pitch volume | {n} pitches yesterday | 42 pitches yesterday |
| pitch_count | Three-day pitch volume | {n} pitches in 3 days | 54 pitches in 3 days |
| pitch_count | Five-day pitch volume | {n} pitches in 5 days | 75 pitches in 5 days |
| appearance_frequency | Three-day appearance compression | {n} appearances in 3 days | 2 appearances in 3 days |
| appearance_frequency | Four-day appearance compression | 3 appearances in 4 days | 3 appearances in 4 days |
| appearance_frequency | Five-day appearance compression | {n} appearances in 5 days | 4 appearances in 5 days |
| appearance_frequency | Back-to-back appearances | Back-to-back appearances | Back-to-back appearances |
| rest | No rest | No rest since last appearance | No rest since last appearance |
| rest | One rest day | Only 1 day of rest | Only 1 day of rest |
| fatigue | Fatigue score | Fatigue score is {score} | Fatigue score is 55.3 |
| data_state | Missing workload data | Missing workload history or fatigue score | Missing workload history or fatigue score |
| data_state | Incomplete workload data | Incomplete workload inputs | Incomplete workload inputs |
| data_state | Stale workload data | Latest workload data is outside the {days}-day freshness window | Latest workload data is outside the 14-day freshness window |
| fallback | Unmapped restriction | Availability restriction rule matched without a displayable workload input | Availability restriction rule matched without a displayable workload input |
