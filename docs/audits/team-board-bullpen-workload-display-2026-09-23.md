# Team Board Active Bullpen workload display — September 23 2026

Status: display/read-model corrected; no data repair; new trusted publication required.
Surface: Team Board "Active Bullpen" columns `7d App`, `7d P`, `Last P`.

## What was published

Snapshot 3435 (SyncRun 84413, data_through 2026-09-22), San Francisco Giants:

| Arm | Displayed | Contributing rows |
| --- | --- | --- |
| Cesar Perdomo | 1 app / 83 P / 83 last P | 2026-09-18 game 823898, `games_started=1`, 14 outs, 83 P |
| Yunior Marte | 1 app / 97 P / 97 last P | 2026-09-19 game 823899, `games_started=1`, 14 outs, 97 P |
| Anthony Molina | 2 app / 167 P / 85 last P | 2026-09-16 game 823004, `games_started=1`, 17 outs, 82 P; 2026-09-22 game 823166, `games_started=1`, 18 outs, 85 P |

Snapshot 3435 contained 19 starter-flagged workload rows (17 pitchers, 13 teams)
on Active Bullpen arms.

## Root cause

The Active Bullpen columns were projected from the pitcher's `FatigueScore`
(`appearances_last_7`, `pitches_last_7_days`) and from
`last_workload_appearance_from_logs`. Both intentionally count every pitching
line, because they are **physical workload** for fatigue, availability, and Team
State. Mixed-usage pitchers are eligible for the Active Bullpen, so their
conventional starts were shown as bullpen workload.

## Rule

Two workloads are kept separate:

- **Physical workload** — every pitching line. Feeds FatigueScore, availability,
  rest status, and Team State. Unchanged.
- **Bullpen workload (display)** — decided per appearance by
  `services.game_shape.bullpen_workload_appearance_class`, which reuses the
  existing game-level `classify_game_shape` for that team's game:

| Appearance | Class | Counted |
| --- | --- | --- |
| `games_started=0` (including a bulk follower and every line of a bullpen game) | `relief` | yes |
| credited start in an `opener_bulk_game` (starter ≤ 6 outs, a follower ≥ 9 outs) | `opener` | yes |
| credited start in a `normal_start` (≥ 15 outs) or `short_start` game | `rotation_start` | no |
| unknown start flag, unclassifiable game, or a game with an unresolved side | `unknown` | withheld |

No new thresholds were introduced. A credited start of 6 outs or fewer
**without** a follower of 9+ outs is a `short_start` under the existing game-shape
contract, so it stays a rotation start here too (the same way Rotation Support
Pressure reads it).

## Correction

- `team_board_recent_usage_rest_v1` per-arm windows use the governed class and
  carry `appearance_policy = governed_game_shape_bullpen_workload_v1`. Each arm
  also carries `last_bullpen_appearance`: the pitches of the most recent single
  qualifying appearance in the seven-day window. Two qualifying outings on the
  same date withhold it (`same_day_appearance_order_unknown`) because stored
  lines have no in-day order.
- At publication, each Active Bullpen record freezes
  `bullpen_workload_display` (`team_board_active_bullpen_workload_display_v1`)
  from that same carrier. Incomplete facts freeze as `null`, never as the
  FatigueScore total.
- The Active Bullpen projection (`team_board_v2._active_arms`) uses the frozen
  display when present. Publications made before this change keep serving
  exactly what they froze.
- The frontend is unchanged and renders backend-authored values.

## Expected SF values after a fresh publication

With the rows above as the only in-window appearances for the three arms:
0 app / 0 P (7d), with no Last P shown. Their FatigueScore values
(1/83, 1/97, 2/167) and every availability and Team State input stay the same.

## Remaining distinction

Recent Relief Work stays a list of official relief appearances
(`games_started=0`). An opener's line appears there in its game's narrative,
not as a relief row, so for an opener only, Active Bullpen and Recent Usage count one
appearance more than the Recent Relief Work list.
