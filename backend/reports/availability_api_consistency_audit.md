# Availability API Consistency Audit

Generated at: 2026-06-02T00:50:26.969727+00:00
Reference date: 2026-06-01

Status: PASS

Endpoint status codes:

| Endpoint | Status |
| --- | --- |
| /api/bullpen/stats/overview | 200 |
| /api/bullpen/fatigue?limit=5&include_stale=true&with_meta=true | 200 |
| /api/bullpen/fatigue?limit=5&with_meta=true | 200 |
| /api/bullpen/fatigue/snapshot?limit=5 | 200 |

Availability objects sampled: 10
Missing required availability fields: none

Required availability fields:

- `availability_status`
- `confidence`
- `data_state`
- `inputs`
- `limitations`
- `reasons`

Default freshness-filter metadata remains present for empty current lists:

| Field | Value |
| --- | --- |
| active_window_days | 14 |
| fresh_filtered_pitchers | 0 |
| include_stale | False |
| returned_pitchers | 0 |
| stale_filtered_pitchers | 704 |
| total_scored_pitchers | 704 |
