# Availability Governance Consistency Audit

Generated at: 2026-06-02T00:50:26.969727+00:00
Reference date: 2026-06-01

Status: PASS
Current production Unavailable 3-day threshold: 90

Governance report availability:

| Report | Exists |
| --- | --- |
| threshold_audit | True |
| baseline_report | True |
| adoption_report | True |
| boundary_report | True |
| experiment_report | True |

Consistency checks:

| Check | Result |
| --- | --- |
| Threshold audit distribution matches adopted baseline | True |
| Baseline report references 90 | True |
| Adoption report records 80 -> 90 | True |
| Boundary review preserves historical 80-89 evidence | True |

Current latest-workload snapshot distribution:

| Value | Count |
| --- | --- |
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |
