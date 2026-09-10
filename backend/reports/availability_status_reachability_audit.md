# Availability Status Reachability Audit

Generated at: 2026-06-02T00:50:26.969727+00:00
Reference date: 2026-06-01

Status: PASS

| Expected | Actual | Confidence | Data state | Reasons |
| --- | --- | --- | --- | --- |
| Available | Available | high | fresh | none |
| Monitor | Monitor | high | fresh | 16 pitches yesterday; Only 1 day of rest |
| Limited | Limited | high | fresh | 28 pitches yesterday; Only 1 day of rest |
| Avoid | Avoid | high | fresh | 80 pitches in 3 days; 80 pitches in 5 days |
| Unavailable | Unavailable | high | fresh | 90 pitches in 3 days; 90 pitches in 5 days |

Boundary result:

- 80 pitches in 3 days reaches Avoid.
- 90 pitches in 3 days reaches Unavailable.
- No status branch is dead in deterministic sample coverage.
