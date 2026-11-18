### Withheld states and missing pitch counts

- **Withheld states never occurred.** Every replayed team-game received Fresh, Stretched or Vulnerable, with high coverage confidence. The replay has complete completed-game data and a complete roster for every date. Production withholds a state when freshness, trust or coverage gates fail. Those gates were exercised, but they never fired here, so this backtest says nothing about withheld days.
- **The production missing-pitch-count rate is unmeasured.** The replay reads pitch counts from boxscores, which carried a count for every appearance: 0 of 121,005 reliever-days were scored with a missing count. Production reads the MLB gameLog endpoint. How often that endpoint lacks a count, and so scores the pitch component as 0, cannot be measured here.

### How the replay reproduces production

- **Engine.** The replay calls the current production code unchanged:
  - `classify_role`
  - `calculate_fatigue`
  - `classify_availability`
  - `_readiness_record`
  - `assess_team_coverage`
  - `_build_trust_metadata`
  - `_team_operations_freshness_metadata`
  - `assemble_bullpen_readiness`
  - `INTERNAL_TO_PUBLIC_STATE`

  No thresholds were tuned.
- **Timing.** A game on date D uses appearances dated before D, and the MLB active roster as of D−1. This matches the nightly run, which scores as of D with data through D−1, and production's slate-day roster convention. The no-lookahead test proves that same-day and later data cannot change any pre-game output.
- **Population.** The active roster is restricted to pitching positions. Two-way players (`TWP`) are excluded, as production's role authority does. The role authority then reads each pitcher's last 10 appearances. Only regular-season appearances count. Spring training and postseason are not in the workload history, and 2023 is used only as history for early 2024.
- **Fatigue window.** The fatigue score uses the last 14 days and availability uses the last 4, as in production. Every reliever is scored each day, including those with no appearance in 14 days. Production keeps their last stored score, but such arms are classified Available whatever the score, so the state is the same.
- **Team fatigue score.** The team-level score is the mean of the active relievers' 0–100 scores. Production has no team-level score; this column is reporting context only and is not used in pass/fail.

### Outcome definitions

- **Bullpen.** Every pitcher after the first one listed in the team's boxscore.
- **Position players.** Classified by day-before roster position, falling back to the position the player entered the game at. The boxscore `position` field holds the end-of-game position, so it reads `P` for position players who finish on the mound. 352 team-games included position-player pitching, which allowed 437 runs. The primary runs-per-9 figure excludes them, and the figure including them is reported alongside it.
- **Bullpen runs.** Runs charged to bullpen pitchers. By scoring rules, runners a starter leaves on base who later score are charged to the starter.
- **Blown lead.** Ahead after six complete innings and lost. Only games that led after six and reached the 7th count.
- **Runs in innings 7–9 and 7+.** Runs scored by the opponent in those innings, counted only for games that reached the 7th. An unplayed bottom 9th counts as 0.
- **Starter and bullpen innings.** Outs recorded divided by 3. Bullpen innings are pitchers only.
- **Same-day pitch rate.** The share of reliever-days on which that reliever made any appearance in that game.

### Analysis choices (fixed before results were viewed)

- **Primary sample.** Excludes doubleheader game 2, because its state is a game staler than its first pitch. Game 2 is reported separately.
- **Within-team comparison.** The unit is a team-season. A team-season enters only if it has at least 5 games in both states compared. Blown leads also need at least 3 led-after-six games in both states. Gaps are averaged with equal weight.
- **Intervals.** 95% percentile bootstrap, resampling whole team-seasons, 2,000 draws, fixed seed.
- **Regression.** Weighted least squares on game-level bullpen runs per 9 (pitchers only). Weights are bullpen outs. Controls:
  - team-season and ballpark fixed effects
  - opponent offense: season-to-date runs per game from earlier dates only, shrunk toward the league average with 20 phantom games, the league average itself seeded with the prior season
  - a home indicator

  Team-games with zero bullpen outs are dropped from the regression only.
- **Opener game.** The starting pitcher was in his team's pre-game bullpen population. That is known at first pitch, so the exclusion does not select on the game's own result.

### Data and source

- **Data.** MLB Stats API schedules (with linescores and venues), boxscores, and day-before active rosters for 2023–2026. That is 24,130 requests at no more than 4 per second, all cached, with no failures and no missing data.
- **Terms.** Every response carries MLB Advanced Media's copyright notice. This work is internal, non-commercial research. Do not publish or redistribute the cache or the row-level CSVs.
