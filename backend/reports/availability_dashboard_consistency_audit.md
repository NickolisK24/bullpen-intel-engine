# Availability Dashboard Consistency Audit

Generated at: 2026-06-02T00:50:26.969727+00:00
Reference date: 2026-06-01

Status: PASS
Dashboard summary reconciles with classifier output: True

Dashboard status distribution:

| Value | Count |
| --- | --- |
| Available | 0 |
| Avoid | 0 |
| Limited | 0 |
| Monitor | 704 |
| Unavailable | 0 |

Dashboard confidence distribution:

| Value | Count |
| --- | --- |
| high | 0 |
| low | 704 |
| medium | 0 |

Dashboard data-state distribution:

| Value | Count |
| --- | --- |
| fresh | 0 |
| incomplete | 0 |
| missing | 64 |
| stale | 640 |

Dashboard notes:

- Most pitchers are classified from stale or missing workload data.
- Stale workload data must not be treated as current availability
- Missing workload history reduces availability confidence.
