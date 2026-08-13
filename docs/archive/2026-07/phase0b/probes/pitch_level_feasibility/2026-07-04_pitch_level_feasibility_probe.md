# Pitch-Level Feasibility Probe - 2026-07-04

Status: `READ-ONLY-PROBE`

This probe records point-in-time observations for Phase 0B-05. It did not
import BaseballOS production code, write to the production database, schedule a
job, or change production behavior. Observations are source facts from inspected
repo files, public documentation, and read-only HTTP requests; interpretations
are audit conclusions only.

## Probe Method

| item | value |
| --- | --- |
| probe date | 2026-07-04 |
| probe time | 13:20-13:36 America/Indianapolis |
| source host | `https://baseballsavant.mlb.com` |
| production code imported | no |
| production database touched | no |
| raw response persisted | no |
| helper libraries installed | no |

## Source References Checked

| source | reference | observed fact |
| --- | --- | --- |
| Baseball Savant CSV docs | `https://baseballsavant.mlb.com/csv-docs` | Public CSV documentation describes Statcast pitch, movement, spin, extension, and related field families. |
| Baseball Savant Statcast search | `https://baseballsavant.mlb.com/statcast_search` | Search page describes querying Statcast by pitch, game, player, team, and season. |
| pybaseball docs | `https://github.com/jldbc/pybaseball/blob/master/docs/statcast.md` | `statcast(start_dt, end_dt, team, verbose, parallel)` returns a pandas DataFrame with one entry per pitch and points field definitions to Baseball Savant. |
| baseballr docs | `https://billpetti.github.io/baseballr/reference/index.html` | baseballr exports Baseball Savant / Statcast functions such as `statcast`, `statcast_search`, `statcast_search_batters`, and `statcast_search_pitchers`. |

## Repo-Local Dependency Check

| file | observation |
| --- | --- |
| `backend/requirements.txt` | Backend dependencies include Flask, SQLAlchemy, requests, APScheduler, and pytest. No `pybaseball`, R, baseballr, Statcast, or Savant dependency is listed. |
| `frontend/package.json` | Frontend dependencies are React/Vite/UI packages. No pitch-level retrieval dependency is listed. |
| repo search | Searches for `pybaseball`, `baseballr`, `statcast`, and `savant` in production backend/frontend paths found no local retrieval helper usage. |

## Baseball Savant CSV Probe

Initial minimal CSV query:

`https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C&game_date_gt=2026-07-01&game_date_lt=2026-07-01&player_type=pitcher&type=details&min_pitches=0&min_results=0`

Observation: PowerShell exposed this response as a very large, poorly bounded
download shape and did not produce a clean CSV header. It was not used as field
evidence. Interpretation: future probes should use the fuller Baseball Savant
search parameter shape and strict date windows.

Clean CSV query:

`https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones=&hfGT=R%7C&hfC=&hfSea=2026%7C&hfSit=&player_type=pitcher&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA=&game_date_gt=2026-07-01&game_date_lt=2026-07-01&hfInfield=&team=&position=&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1=&hfInn=&min_pitches=0&min_results=0&group_by=name&sort_col=pitches&player_event_sort=h_launch_speed&sort_order=desc&min_abs=0&type=details&`

| observation | value |
| --- | --- |
| HTTP status | 200 |
| content type | `application/download; charset=utf-8` |
| query window | one date: 2026-07-01 |
| rows observed | 4,091 data rows |
| columns observed | 119 fields |
| raw response persisted | no |

## Observed Field Families

The clean query returned these field families in the CSV header.

| field family | observed fields |
| --- | --- |
| Pitch and game identity | `game_date`, `game_year`, `game_pk`, `at_bat_number`, `pitch_number`, `sv_id` |
| Pitcher and batter identity | `player_name`, `pitcher`, `batter`, `home_team`, `away_team` |
| Pitch type and name | `pitch_type`, `pitch_name` |
| Velocity | `release_speed`, `effective_speed` |
| Spin, movement, and release | `release_spin_rate`, `spin_axis`, `pfx_x`, `pfx_z`, `release_extension`, `release_pos_x`, `release_pos_y`, `release_pos_z`, `api_break_z_with_gravity`, `api_break_x_arm`, `api_break_x_batter_in`, `arm_angle` |
| Location and count | `plate_x`, `plate_z`, `zone`, `sz_top`, `sz_bot`, `balls`, `strikes` |
| Pitch result | `description`, `type`, `events`, `des` |
| Base/out/inning context | `on_3b`, `on_2b`, `on_1b`, `outs_when_up`, `inning`, `inning_topbot` |
| Score context | `home_score`, `away_score`, `bat_score`, `fld_score`, `post_away_score`, `post_home_score`, `post_bat_score`, `post_fld_score` |
| Contact quality | `launch_speed`, `launch_angle`, `bb_type`, `hit_distance_sc`, `launch_speed_angle`, `hc_x`, `hc_y`, `hyper_speed` |
| Expected and actual outcome | `estimated_ba_using_speedangle`, `estimated_woba_using_speedangle`, `estimated_slg_using_speedangle`, `woba_value`, `woba_denom`, `babip_value`, `iso_value` |
| Handedness and batter context | `stand`, `p_throws`, `n_thruorder_pitcher`, `n_priorpa_thisgame_player_at_bat`, `pitcher_days_since_prev_game`, `batter_days_since_prev_game`, `pitcher_days_until_next_game`, `batter_days_until_next_game` |
| Fielding alignment | `if_fielding_alignment`, `of_fielding_alignment` |
| Win/run expectancy | `delta_home_win_exp`, `delta_run_exp`, `delta_pitcher_run_exp`, `home_win_exp`, `bat_win_exp` |
| Swing metrics | `bat_speed`, `swing_length`, `miss_distance`, `attack_angle`, `attack_direction`, `swing_path_tilt` |

## First-500-Row Completeness Profile

This profile sampled only the first 500 CSV data rows from the one-date query.
It is useful for field-shape classification, not population-level data quality.

| field | present | non-empty rows in first 500 | notes |
| --- | --- | --- | --- |
| `pitch_type` | yes | 500 | Sample values included `SI`, `CH`, `SL`, `ST`, `FF`. |
| `release_speed` | yes | 500 | Velocity populated for sampled pitches. |
| `effective_speed` | yes | 500 | Effective velocity populated for sampled pitches. |
| `release_spin_rate` | yes | 500 | Spin rate populated for sampled pitches. |
| `spin_axis` | yes | 500 | Spin axis populated for sampled pitches. |
| `pfx_x` / `pfx_z` | yes | 500 | Movement fields populated for sampled pitches. |
| `plate_x` / `plate_z` | yes | 500 | Plate-location fields populated for sampled pitches. |
| `zone` | yes | 500 | Zone field populated for sampled pitches. |
| `balls` / `strikes` | yes | 500 | Count fields populated for sampled pitches. |
| `description` | yes | 500 | Sample values included `hit_into_play`, `foul`, `ball`, `called_strike`, `swinging_strike`. |
| `type` | yes | 500 | Sample values included `X`, `S`, `B`. |
| `events` | yes | 144 | Event is plate-appearance/result-specific, not every pitch. |
| `launch_speed` | yes | 159 | Contact-quality field populated only for relevant batted balls. |
| `launch_angle` | yes | 160 | Contact-quality field populated only for relevant batted balls. |
| `estimated_ba_using_speedangle` | yes | 94 | Expected outcome field is partial. |
| `estimated_woba_using_speedangle` | yes | 144 | Expected outcome field is partial. |
| `woba_value` / `woba_denom` | yes | 144 | Outcome fields are plate-appearance/result-specific. |
| `bb_type` | yes | 95 | Batted-ball type is partial. |
| `stand` / `p_throws` | yes | 500 | Batter and pitcher handedness populated for sampled pitches. |
| `batting_order` | no | n/a | No direct lineup slot field observed in CSV header. |
| `at_bat_number` / `pitch_number` | yes | 500 | Supports sequence reconstruction inside a game. |
| `game_pk` / `batter` / `pitcher` | yes | 500 | Supports mapping to MLB game and player ids. |

## Observed Helper Feasibility

| helper | current repo status | observed external capability | interpretation |
| --- | --- | --- | --- |
| pybaseball | not installed and not listed in backend dependencies | docs describe `statcast` as returning one row per pitch in a pandas DataFrame | Potential research helper only; not a license and not adopted. |
| baseballr | not installed and no R dependency exists in the repo | docs list Baseball Savant / Statcast search functions | Potential research helper only; not a license and not adopted. |

## Unknowns

- Baseball Savant / Statcast legal terms for internal research, derived storage,
  public display, raw caching, redistribution, and future paid/commercial use.
- Rate limit, access stability, and acceptable automation boundaries.
- Correction latency and reprocessing cadence for pitch-level fields.
- Whether fields remain stable across postponed, suspended, resumed, postseason,
  Spring Training, and unusual scoring cases.
- Whether swing metrics such as bat speed, swing length, and attack angle are
  complete enough for bullpen evidence.
- Whether helper libraries preserve enough source metadata and retry/correction
  behavior for production use.
