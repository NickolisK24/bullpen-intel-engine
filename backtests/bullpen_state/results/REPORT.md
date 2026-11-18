# Bullpen state backtest: does "Vulnerable" mean worse bullpen results?

Seasons 2024, 2025 and 2026, all regular-season games. Every pre-game state is a day-by-day replay of the current production engine, unchanged and untuned. Internal research only (MLB Stats API terms).

## Pass / fail (bars fixed before results)

| Bar | Result | Estimate | 95% CI | Verdict |
|---|---|---:|---:|---|
| Vulnerable bullpens allow **≥ 0.4 more runs per 9** than Fresh (within-team), CI excludes 0 | Vulnerable − Fresh | +0.05 | [-0.19, +0.27] | **FAIL** |
| Unavailable relievers pitch at **≤ half** the Available rate, CI excludes equal rates | Unavailable ÷ Available pitch rate | 0.0012 | [0.0000, 0.0037] | **PASS** |

Unavailable flags in the primary sample: **1,620**.

## Three strongest findings

1. **Vulnerable bullpens did not allow meaningfully more runs.**
   - On a team's own Vulnerable days, its bullpen allowed **+0.05 runs per 9** more than on its own Fresh days (95% CI −0.19 to +0.27).
   - The fixed-effects regression agrees: **+0.06** (CI −0.16 to +0.29).
   - Both upper bounds are below 0.4, so the data rule out an effect as large as the bar. This is a clear miss, not an underpowered one.
   - Fresh and Stretched bullpens were indistinguishable: 4.45 vs 4.45 runs per 9.

2. **The state predicts how the bullpen gets used, not how it performs.**
   - On Vulnerable days, starters went **0.25 innings deeper** (CI +0.19 to +0.32) and bullpens covered **0.23 fewer innings** (CI −0.29 to −0.16) than on the same team's Fresh days.
   - Starter innings fall steadily as clean arms rise, from 5.48 with 0 clean arms to 5.04 with 5 or more.
   - Combined with finding 3, the likely reason is that managers adapt: tired arms sit and starters stay in, so the relievers who do pitch on Vulnerable days are mostly rested ones.
   - Late-inning damage rose slightly but not reliably:
     - Runs allowed in innings 7–9: +0.08 per game (CI 0.00 to +0.15).
     - Blown-lead rate: +1.6 points (CI −0.8 to +4.1).

3. **The reliever-level flags are highly accurate about who will not pitch.** Same-day pitch rates step down cleanly through the five flags:

   | Flag | Same-day pitch rate |
   |---|---:|
   | Available | 52.4% |
   | Monitor | 33.6% |
   | Limited | 23.1% |
   | Avoid | 1.2% |
   | Unavailable | 0.06% (1 of 1,620) |

   - The availability bar passes by a wide margin.
   - Avoid and Unavailable flag heavy recent workloads, the cases a manager rests anyway, so this bar mostly confirms the obvious cases are right.
   - The information is in the middle tiers: Monitor and Limited arms pitch at 64% and 44% of the Available rate.

**Single-season results are not stable.**
- 2024 alone would have passed: +0.40 runs per 9 (CI +0.04 to +0.75).
- 2025 (−0.18) and 2026 (−0.08) reverse it.
- This is why the result uses all three seasons with the untuned engine, and why any threshold change must be tuned on one season and judged on the others.

## Weak spots and refinements, ranked by expected impact (not implemented)

1. **Weight clean arms by role, not just count them.** *(highest expected impact on runs)*
   - The state counts Available arms, so a mop-up arm counts the same as the closer.
   - Runs allowed depend on who pitches the leveraged innings.
   - Test a variant where Vulnerable means the top-leverage arms (Trusted/Setup roles, or the save/hold history before the game) are not clean.
   - Tune it on 2024 and evaluate it on 2025–2026.

2. **Replace the clean-arm count with expected capacity.**
   - About 99% of Vulnerable days come from one rule: "2 or fewer clean arms".
   - Monitor and Limited arms are excluded from "clean", yet they pitch at 64% and 44% of the Available rate.
   - Vulnerable is effectively "≤ 2 Available arms", and it fires on 26% of team-games.
   - An availability-weighted capacity, such as the sum of each arm's flag pitch rate, would use the gradient that finding 3 shows exists.

3. **Merge or redefine Stretched.**
   - Stretched is half of all team-games and matches Fresh on every outcome, with gaps near zero.
   - As defined it does not separate. Either merge it with Fresh or move its boundary, using a tuning season and a separate evaluation season.

4. **Drop or recalibrate the "a third or more severe" rule.**
   - It decided only 47 primary team-games across three seasons (0.3%).
   - Those games had lower bullpen runs per 9 (3.97 vs 4.57 for the clean-arm-floor group).
   - There is no evidence it adds signal. It mostly adds a rule to maintain.

5. **Handle opener games explicitly.**
   - Fresh days had nearly twice as many opener games as Vulnerable days (388 vs 207).
   - The planned opener is counted in the bullpen population, and his innings count as bullpen innings.
   - Excluding openers moved the main gap from +0.05 to −0.00. That is small for runs, but openers distort any bullpen-innings comparison.
   - Leave the probable starter out of the population when he is known before the game.

6. **Measure the production missing-pitch-count rate.**
   - The replay reads boxscores, which never lacked pitch counts (0 of 121,005 reliever-days).
   - Production reads the gameLog endpoint, where a missing count makes that pitch component score as 0 and lowers the fatigue score.
   - Its frequency in production is unmeasured; a direct query of production `game_logs` would settle it.

7. **Refresh the state between doubleheader games.** *(lowest impact)*
   - Game 2 uses a state computed before game 1. Only 164 team-games are affected.
   - Game-2 results show no clear pattern.


## Sample

| Season | Team-games | Fresh | Stretched | Vulnerable | Withheld | Reliever-days | Missing pitch counts scored as 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024 | 4,858 | 1,285 | 2,366 | 1,207 | 0 | 40,804 | 0 |
| 2025 | 4,860 | 1,209 | 2,397 | 1,254 | 0 | 40,182 | 0 |
| 2026 | 4,858 | 1,148 | 2,366 | 1,344 | 0 | 40,019 | 0 |
| **All** | 14,576 | 3,642 | 7,129 | 3,805 | 0 | 121,005 | 0 |

Primary sample: 14,412 team-games, excluding 164 doubleheader game-2 team-games (reported separately below). 90 team-seasons. 80 primary team-games had zero bullpen outs; they drop out of the runs-per-9 regression but stay in pooled ratios.

## Outcomes by Team State (primary sample)

| Outcome | Fresh | Stretched | Vulnerable |
|---|---:|---:|---:|
| Team-games | 3,538 | 7,077 | 3,797 |
| Games led after 6 | 1,560 | 3,063 | 1,653 |
| Bullpen runs per 9 (pitchers only) [primary] | 4.45 | 4.45 | 4.56 |
| Bullpen runs per 9 (incl. position players) | 4.48 | 4.49 | 4.61 |
| Blown lead rate (led after 6, lost) | 0.127 | 0.136 | 0.139 |
| Runs allowed, innings 7-9 | 1.28 | 1.32 | 1.38 |
| Team runs allowed, 7th inning on (incl. extras) | 1.41 | 1.43 | 1.50 |
| Starter innings | 5.09 | 5.10 | 5.31 |
| Bullpen innings (pitchers only) | 3.75 | 3.73 | 3.56 |

**Ordering check (Fresh < Stretched < Vulnerable, pooled values):**

- Bullpen runs per 9 (pitchers only) [primary]: Fresh 4.452, Stretched 4.451, Vulnerable 4.559 → **not ordered**
- Bullpen runs per 9 (incl. position players): Fresh 4.482, Stretched 4.491, Vulnerable 4.615 → ordered
- Blown lead rate (led after 6, lost): Fresh 0.1269, Stretched 0.1361, Vulnerable 0.1391 → ordered
- Runs allowed, innings 7-9: Fresh 1.284, Stretched 1.316, Vulnerable 1.377 → ordered
- Team runs allowed, 7th inning on (incl. extras): Fresh 1.414, Stretched 1.432, Vulnerable 1.499 → ordered
- Starter innings: Fresh 5.089, Stretched 5.103, Vulnerable 5.306 → ordered
- Bullpen innings (pitchers only): Fresh 3.751, Stretched 3.730, Vulnerable 3.557 → **not ordered**

For starter and bullpen innings, the order shows direction only. Neither is a "worse" outcome.

## Gaps with 95% bootstrap intervals

A within-team gap is each team-season's own Vulnerable (or Stretched) days minus its own Fresh days, averaged with equal weight across team-seasons that have at least 5 games in both states. Blown leads require at least 3 led-after-six games in both states. The pooled gap compares all team-games together. Intervals resample whole team-seasons, with 2,000 draws.

### Vulnerable − Fresh

| Outcome (V − F) | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |
|---|---:|---:|---:|---:|---:|
| Bullpen runs per 9 (pitchers only) [primary] | +0.05 | [-0.19, +0.27] | +0.11 | [-0.13, +0.35] | 90 |
| Bullpen runs per 9 (incl. position players) | +0.07 | [-0.17, +0.29] | +0.13 | [-0.11, +0.37] | 90 |
| Blown lead rate (led after 6, lost) | +0.016 | [-0.008, +0.041] | +0.012 | [-0.011, +0.036] | 90 |
| Runs allowed, innings 7-9 | +0.08 | [+0.00, +0.14] | +0.09 | [+0.02, +0.16] | 90 |
| Team runs allowed, 7th inning on (incl. extras) | +0.07 | [-0.01, +0.14] | +0.09 | [+0.01, +0.16] | 90 |
| Starter innings | +0.25 | [+0.19, +0.32] | +0.22 | [+0.15, +0.29] | 90 |
| Bullpen innings (pitchers only) | -0.22 | [-0.29, -0.16] | -0.19 | [-0.26, -0.13] | 90 |

### Stretched − Fresh

| Outcome (S − F) | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |
|---|---:|---:|---:|---:|---:|
| Bullpen runs per 9 (pitchers only) [primary] | -0.04 | [-0.25, +0.17] | -0.00 | [-0.21, +0.21] | 90 |
| Bullpen runs per 9 (incl. position players) | -0.03 | [-0.24, +0.17] | +0.01 | [-0.21, +0.22] | 90 |
| Blown lead rate (led after 6, lost) | +0.011 | [-0.008, +0.031] | +0.009 | [-0.011, +0.029] | 90 |
| Runs allowed, innings 7-9 | +0.02 | [-0.05, +0.09] | +0.03 | [-0.04, +0.10] | 90 |
| Team runs allowed, 7th inning on (incl. extras) | +0.01 | [-0.06, +0.07] | +0.02 | [-0.06, +0.09] | 90 |
| Starter innings | +0.05 | [-0.01, +0.11] | +0.01 | [-0.04, +0.07] | 90 |
| Bullpen innings (pitchers only) | -0.05 | [-0.11, +0.01] | -0.02 | [-0.08, +0.04] | 90 |

### Vulnerable − Stretched

| Outcome (V − S) | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |
|---|---:|---:|---:|---:|---:|
| Bullpen runs per 9 (pitchers only) [primary] | +0.09 | [-0.11, +0.30] | +0.11 | [-0.08, +0.31] | 90 |
| Bullpen runs per 9 (incl. position players) | +0.10 | [-0.09, +0.32] | +0.12 | [-0.06, +0.33] | 90 |
| Blown lead rate (led after 6, lost) | +0.005 | [-0.014, +0.024] | +0.003 | [-0.014, +0.020] | 90 |
| Runs allowed, innings 7-9 | +0.05 | [-0.01, +0.12] | +0.06 | [+0.01, +0.12] | 90 |
| Team runs allowed, 7th inning on (incl. extras) | +0.06 | [-0.00, +0.13] | +0.07 | [+0.01, +0.13] | 90 |
| Starter innings | +0.21 | [+0.15, +0.26] | +0.20 | [+0.14, +0.26] | 90 |
| Bullpen innings (pitchers only) | -0.17 | [-0.24, -0.11] | -0.17 | [-0.24, -0.11] | 90 |

## Regression: bullpen runs per 9 (pitchers only)

WLS of game bullpen R/9 (pitchers only) on state dummies (fresh = baseline), team-season fixed effects, ballpark fixed effects, opponent season-to-date R/G (prior dates only, shrunk), home indicator; weights = bullpen outs; team-season cluster bootstrap. n = 14,332 team-games.

| Term | Estimate | 95% CI |
|---|---:|---:|
| Stretched vs Fresh | -0.018 | [-0.228, +0.191] |
| Vulnerable vs Fresh | +0.057 | [-0.165, +0.286] |
| Opponent offense (per 1 R/G) | +0.422 | [+0.219, +0.631] |
| Home | -0.162 | [-0.339, +0.016] |

## Reliever availability: same-day pitch rate by pre-game flag

| Flag | Reliever-days | Pitched | Same-day pitch rate | 95% CI | Did not pitch |
|---|---:|---:|---:|---:|---:|
| Available | 53,934 | 28,282 | 0.524 | [0.517, 0.532] | 0.476 |
| Monitor | 32,906 | 11,047 | 0.336 | [0.327, 0.344] | 0.664 |
| Limited | 26,714 | 6,171 | 0.231 | [0.223, 0.239] | 0.769 |
| Avoid | 4,476 | 54 | 0.012 | [0.009, 0.015] | 0.988 |
| Unavailable | 1,620 | 1 | 0.001 | [0.000, 0.002] | 0.999 |
| Avoid+Unavailable | 6,096 | 55 | 0.009 | [0.006, 0.012] | 0.991 |

- **Unavailable ÷ Available pitch-rate ratio:** 0.0012 (95% CI 0.0000 to 0.0037). Share flagged that did not pitch: 99.938%.

- **Avoid+Unavailable ÷ Available pitch-rate ratio:** 0.0172 (95% CI 0.0124 to 0.0222). Share flagged that did not pitch: 99.098%.

## Sensitivity checks

### By season (bullpen runs per 9, pitchers only)

| Season | Fresh | Stretched | Vulnerable | V − F within-team | 95% CI |
|---|---:|---:|---:|---:|---:|
| 2024 | 4.23 (n=1,251) | 4.44 (n=2,346) | 4.61 (n=1,203) | +0.40 | [+0.04, +0.75] |
| 2025 | 4.65 (n=1,172) | 4.37 (n=2,381) | 4.54 (n=1,251) | -0.18 | [-0.56, +0.22] |
| 2026 | 4.49 (n=1,115) | 4.54 (n=2,350) | 4.53 (n=1,343) | -0.08 | [-0.47, +0.27] |

### Excluding opener games

An opener game is one where the starting pitcher was in his team's pre-game bullpen population (known at first pitch). Opener team-games: Fresh 388, Stretched 860, Vulnerable 207. Without them, bullpen runs per 9 are Fresh 4.49, Stretched 4.43, Vulnerable 4.56. The within-team V − F gap is -0.00 [-0.24, +0.24].

### Doubleheader game 2 (state computed before game 1)

| Outcome | Fresh | Stretched | Vulnerable |
|---|---:|---:|---:|
| Team-games | 104 | 52 | 8 |
| Games led after 6 | 47 | 22 | 3 |
| Bullpen runs per 9 (pitchers only) [primary] | 4.12 | 4.25 | 4.15 |
| Bullpen runs per 9 (incl. position players) | 4.12 | 4.46 | 4.15 |
| Blown lead rate (led after 6, lost) | 0.106 | 0.045 | 0.000 |
| Runs allowed, innings 7-9 | 1.26 | 1.23 | 1.00 |
| Team runs allowed, 7th inning on (incl. extras) | 1.35 | 1.27 | 1.62 |
| Starter innings | 4.59 | 5.25 | 5.33 |
| Bullpen innings (pitchers only) | 4.29 | 3.50 | 3.79 |

No team-season has 5 game-2s in two states, so only pooled gaps exist. Vulnerable − Fresh pooled bullpen R/9: +0.03 [-2.92, +2.78].

Game-2 same-day pitch rates: Available 0.386 (n=907), Monitor 0.290 (n=207), Limited 0.271 (n=210), Avoid 0.000 (n=21), Unavailable 0.000 (n=10), Avoid+Unavailable 0.000 (n=31).

## Exploratory (not part of pass/fail)

### Every outcome by number of clean (Available) arms

| Outcome | 0 clean | 1 clean | 2 clean | 3 clean | 4 clean | 5+ clean |
|---|---:|---:|---:|---:|---:|---:|
| Team-games | 344 | 1,227 | 2,179 | 2,962 | 3,055 | 4,645 |
| Games led after 6 | 148 | 524 | 957 | 1,321 | 1,279 | 2,047 |
| Bullpen runs per 9 (pitchers only) [primary] | 4.69 | 4.43 | 4.62 | 4.43 | 4.50 | 4.43 |
| Bullpen runs per 9 (incl. position players) | 4.74 | 4.52 | 4.66 | 4.46 | 4.55 | 4.46 |
| Blown lead rate (led after 6, lost) | 0.115 | 0.145 | 0.143 | 0.131 | 0.137 | 0.130 |
| Runs allowed, innings 7-9 | 1.42 | 1.39 | 1.37 | 1.30 | 1.33 | 1.29 |
| Team runs allowed, 7th inning on (incl. extras) | 1.55 | 1.50 | 1.49 | 1.42 | 1.44 | 1.42 |
| Starter innings | 5.48 | 5.37 | 5.25 | 5.19 | 5.10 | 5.04 |
| Bullpen innings (pitchers only) | 3.45 | 3.48 | 3.61 | 3.66 | 3.72 | 3.80 |

Bullpen runs per 9 gaps vs 0 clean arms:

| Clean arms | Within-team gap vs 0 | 95% CI | Pooled gap vs 0 | 95% CI |
|---|---:|---:|---:|---:|
| 1 | +0.02 | [-0.74, +0.78] | -0.25 | [-0.80, +0.29] |
| 2 | +0.09 | [-0.74, +0.90] | -0.06 | [-0.63, +0.49] |
| 3 | -0.07 | [-0.79, +0.64] | -0.26 | [-0.79, +0.28] |
| 4 | +0.18 | [-0.55, +0.93] | -0.18 | [-0.72, +0.35] |
| 5+ | +0.11 | [-0.56, +0.77] | -0.26 | [-0.78, +0.27] |

### Vulnerable by rule: "a third or more severe" vs "2 or fewer clean arms"

| Outcome | ≤ 2 clean arms | ≥ ⅓ severe |
|---|---:|---:|
| Team-games | 3,750 | 47 |
| Games led after 6 | 1,629 | 24 |
| Bullpen runs per 9 (pitchers only) [primary] | 4.57 | 3.97 |
| Bullpen runs per 9 (incl. position players) | 4.62 | 3.95 |
| Blown lead rate (led after 6, lost) | 0.141 | 0.000 |
| Runs allowed, innings 7-9 | 1.38 | 1.09 |
| Team runs allowed, 7th inning on (incl. extras) | 1.50 | 1.24 |
| Starter innings | 5.31 | 5.16 |
| Bullpen innings (pitchers only) | 3.55 | 3.91 |

Pooled bullpen R/9, severe-share minus clean-floor: -0.60 [-1.80, +0.67]. The severe-share group is too small for a within-team comparison.

## Data notes and assumptions

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

