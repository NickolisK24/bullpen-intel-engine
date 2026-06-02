# Availability Snapshot Safety Audit

Generated at: 2026-06-02T00:50:26.969727+00:00
Reference date: 2026-06-01

Status: PASS

Snapshot endpoint:

- `GET /api/bullpen/fatigue/snapshot`
- Decorated with `require_admin_token`.
- Production is protected by admin-token configuration.
- Development may allow access without a token only when no token is configured.

Response metadata:

| Field | Value |
| --- | --- |
| active_window_days | 14 |
| filters | {'risk_level': None, 'team_id': None} |
| is_current_availability | False |
| mode | latest_workload_snapshot |
| reference_strategy | per_pitcher_latest_game_date |
| returned_pitchers | 5 |
| snapshot_date | 2026-03-12 |
| total_pitchers | 5 |
| warning | Historical workload snapshot for validation only. Do not treat as current bullpen availability. |

Response headers:

| Header | Value |
| --- | --- |
| X-BaseballOS-Data-Mode | latest_workload_snapshot |
| X-BaseballOS-Current-Availability | false |
