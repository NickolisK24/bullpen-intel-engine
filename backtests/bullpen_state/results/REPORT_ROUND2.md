# Bullpen backtest, round 2: role-weighted state and save prediction

Tuned on 2024 only. Evaluated once on 2025 and 2026 combined, with the definitions frozen in `FROZEN_SPEC.md`, which was committed before evaluation. No new data requests. Same methods as round 1: within-team gaps, a team-season bootstrap with 2,000 draws, doubleheader game 2 excluded, and position players excluded from bullpen runs per 9.

## Verdicts

| Test | Bar | Result | Verdict |
|---|---|---|---|
| 1. Role-weighted state | Innings 7–9 runs, flagged − unflagged (within-team) ≥ +0.20, CI excludes 0; fires on 5–20% | -0.017 [-0.155, +0.122]; fires 7.2% | **FAIL** |
| 2. Save prediction | Engine top-1 ≥ 50% and ≥ 10 pts over naive, CI excludes 0; needs ≥ 100 cases | 63 cases; engine 33.3%, naive 25.4%, edge +7.9 pts | **INCONCLUSIVE** |

## Summary

**Neither test passed. Under the round 2 ground rules, tuning stops here.**

### Test 1 (role-weighted state): FAIL

- **Result.** Flagging the days when at least one of a team's top 3 late-inning
  arms was Avoid/Unavailable did not separate late-inning runs:
  - Within-team gap: **−0.02 runs per game in innings 7–9** (95% CI −0.16 to
    +0.12).
  - The flag fired on 7.2% of team-games.
  - The upper bound (+0.12) is below the +0.20 bar, so an effect that large is
    ruled out, not just unproven.
- **It doesn't depend on one season.**

  | Season | Innings 7–9 gap |
  |---|---:|
  | 2025 | +0.00 |
  | 2026 | −0.04 |
  | 2024 (tuning) | +0.03 |

- **Secondary outcomes.**
  - Blown leads: +0.3 points.
  - Bullpen runs per 9: −0.18 (CI −0.59 to +0.25).
- **A one-season artifact.** In 2024, the secondary bullpen runs per 9 gap
  looked meaningful: +0.73 (CI +0.05 to +1.50). It reversed in 2025–2026. This
  is the single-season trap the holdout exists for.
- **The role definition made no difference.** Ranking by production usage role
  and ranking by saves + holds gave nearly identical flags and gaps on 2024. The
  2024 data offered no basis to prefer one over the other.
- **Fire rates were extreme for most variants.**
  - "At least 1 of the top 3 is not Available" fires on about 85% of days, so
    late-inning arms almost always carry some recent-work flag.
  - "2 or 3 of the top 3 Avoid/Unavailable" fires on under 1%.
  - Only 2 of the 12 variants landed inside the 5–20% window.

### Test 2 (save prediction): INCONCLUSIVE

- **Case count.** 63 evaluation cases, under the 100-case floor: 29 in 2025 and
  34 in 2026.
- **Accuracy.** The engine's top pick got the save chance **33%** of the time
  (CI 21% to 46%). The naive pick did so 25% of the time.
- **Margin over naive.** +7.9 points (CI 0.0 to +16.4).
- **It would have failed with enough cases.** The verdict is inconclusive only
  because of the case floor. The entire accuracy interval is below 50%, and the
  margin over naive is below the 10-point bar. Nothing here suggests more cases
  would turn it into a pass.
- **Not one-season.** Both seasons are below 50%: 2025 at 38% and 2026 at 29%.
- **The 2024 margin did not hold up.** On 21 cases it was +19 points. In
  evaluation it shrank to +8, as expected from a tie-break chosen on that small
  sample.
- **Why cases are scarce.** Closers are almost never flagged Avoid or
  Unavailable on a day with a save chance: 62 of 63 cases were Avoid.
- **Unwinnable cases.** In 8 of the 63 cases no pick could have been right:
  - 5 times the flagged closer took the chance anyway.
  - 3 times the chance went to another arm outside the pre-game bullpen read.
- **Exploratory: Limited closers included.**
  - Limited closers took the save chance themselves in 49% of the 583 cases.
  - The engine (14%) did no better than the naive pick (15%).
  - For closers, Limited does not mean "won't close".

### Data note

- **How the inning was derived.** "Save or blown save in the 9th or later"
  needs the inning of each appearance, which the boxscore does not record. It
  was derived exactly from pitcher order and outs recorded.
- **Check.** Every 2024–2026 team-game of 9 or more innings reconciled with the line score.
- **The one judgment call.** Blown saves by a pitcher who entered before the 9th
  and pitched into it count only if his team still led when its defensive 9th
  began. That rule decided 10 blown saves in 2024 and 44 in 2025–2026.


## Frozen definitions

Summary (full text in `FROZEN_SPEC.md`):

- **Test 1.**
  - Top 3 late-inning arms: ranked by saves + holds over the prior 30 days, then production usage role, then relief appearances.
  - Flag: at least 1 of those 3 is flagged Avoid or Unavailable.
- **Test 2.**
  - Closer: most saves over the prior 30 days, minimum 3.
  - Case: the closer is flagged Avoid/Unavailable and the team had a 9th-inning-or-later save chance.
  - Engine pick: among Available/Monitor arms, rank by usage role, then saves + holds (30d), then saves, then holds.
  - Naive pick: the same ranking with flags ignored and the closer excluded.

## Test 1: role-weighted state

### Every 2024 variant (tuning season)

All gaps are within-team: flagged days minus the same team-season's unflagged days.

| Top-3 definition | N of 3 | "Not clean" | Fire rate | In 5–20%? | Innings 7–9 runs gap | 95% CI | Blown-lead gap | 95% CI | Bullpen R/9 gap | 95% CI |
|---|---:|---|---:|:---:|---:|---:|---:|---:|---:|---:|
| Role authority | 1 | not Available | 84.8% | no | +0.046 | [-0.073, +0.155] | -0.017 | [-0.061, +0.025] | +0.11 | [-0.22, +0.44] |
| Role authority | 1 | Avoid/Unavailable | 6.7% | yes | +0.015 | [-0.230, +0.292] | -0.001 | [-0.065, +0.066] | +0.64 | [-0.07, +1.46] |
| Role authority | 2 | not Available | 61.8% | no | -0.037 | [-0.145, +0.069] | -0.022 | [-0.052, +0.008] | -0.08 | [-0.38, +0.21] |
| Role authority | 2 | Avoid/Unavailable | 0.5% | no | — | — | — | — | — | — |
| Role authority | 3 | not Available | 32.1% | no | -0.009 | [-0.108, +0.092] | -0.007 | [-0.045, +0.030] | -0.02 | [-0.30, +0.25] |
| Role authority | 3 | Avoid/Unavailable | 0.0% | no | — | — | — | — | — | — |
| Saves + holds (30d) | 1 | not Available | 84.8% | no | +0.051 | [-0.068, +0.169] | -0.023 | [-0.066, +0.016] | +0.14 | [-0.17, +0.45] |
| Saves + holds (30d) **← frozen** | 1 | Avoid/Unavailable | 6.7% | yes | +0.025 | [-0.206, +0.288] | +0.027 | [-0.042, +0.098] | +0.73 | [+0.05, +1.50] |
| Saves + holds (30d) | 2 | not Available | 62.1% | no | -0.027 | [-0.129, +0.080] | -0.025 | [-0.055, +0.004] | -0.01 | [-0.30, +0.29] |
| Saves + holds (30d) | 2 | Avoid/Unavailable | 0.5% | no | — | — | — | — | — | — |
| Saves + holds (30d) | 3 | not Available | 32.2% | no | -0.009 | [-0.103, +0.087] | -0.005 | [-0.044, +0.032] | +0.00 | [-0.25, +0.27] |
| Saves + holds (30d) | 3 | Avoid/Unavailable | 0.0% | no | — | — | — | — | — | — |

When a variant fires on almost no team-games, no team-season has 5 flagged games, so the gap is blank.

### Evaluation: 2025 + 2026 (frozen variant)

Flag fired on 688 of 9,612 team-games (7.2%).

| Outcome | Unflagged | Flagged | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |
|---|---:|---:|---:|---:|---:|---:|---:|
| Runs allowed, innings 7–9 [primary] | 1.338 | 1.360 | -0.017 | [-0.155, +0.122] | +0.023 | [-0.102, +0.154] | 59 |
| Blown-lead rate | 0.130 | 0.132 | +0.003 | [-0.039, +0.044] | +0.002 | [-0.033, +0.040] | 53 |
| Bullpen runs per 9 (pitchers only) | 4.504 | 4.499 | -0.18 | [-0.59, +0.25] | -0.01 | [-0.33, +0.35] | 59 |

**By season (within-team gaps):**

| Season | Fire rate | Innings 7–9 runs | 95% CI | Blown lead | 95% CI | Bullpen R/9 | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 7.0% | +0.003 | [-0.234, +0.224] | +0.006 | [-0.052, +0.071] | -0.20 | [-0.91, +0.47] |
| 2026 | 7.3% | -0.037 | [-0.194, +0.125] | -0.000 | [-0.051, +0.055] | -0.16 | [-0.62, +0.34] |

## Test 2: save prediction

### Every 2024 tie-break variant (tuning season)

| Sample | Cases | Engine | 95% CI | Naive | 95% CI | Engine − naive | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| saves_then_holds_30d **← frozen** | 21 | 42.9% | [23.5%, 64.7%] | 23.8% | [8.0%, 47.1%] | +19.0 pts | [+4.5, +36.8] |
| most_days_rest | 21 | 38.1% | [20.0%, 58.8%] | 28.6% | [12.0%, 47.6%] | +9.5 pts | [+0.0, +25.0] |
| relief_apps_30d | 21 | 42.9% | [23.5%, 64.7%] | 28.6% | [12.0%, 47.6%] | +14.3 pts | [+0.0, +33.3] |

### Evaluation: 2025 + 2026 (frozen ranking, top-1)

| Sample | Cases | Engine | 95% CI | Naive | 95% CI | Engine − naive | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 + 2026 | 63 | 33.3% | [21.0%, 46.2%] | 25.4% | [15.2%, 36.7%] | +7.9 pts | [+0.0, +16.4] |
| 2025 only | 29 | 37.9% | [19.2%, 55.6%] | 31.0% | [14.3%, 48.4%] | +6.9 pts | [-7.1, +19.4] |
| 2026 only | 34 | 29.4% | [12.8%, 48.6%] | 20.6% | [8.8%, 34.6%] | +8.8 pts | [+0.0, +21.6] |

**Case counts:**

- 63 cases across 38 team-seasons.
- Closer flagged: Avoid 62, Unavailable 1.
- The flagged closer took the save chance himself in 5 cases.
- In 3 more cases, the save chance went to another arm outside the pre-game bullpen read.
- No pick could be right in either situation. Those 8 cases count as misses for the engine and the naive pick alike.

**Save-chance derivation (2025 + 2026):** 2,814 team-games had a 9th-inning-or-later save chance.
- Blown saves counted: 367 where the pitcher entered with 24+ outs, and 44 that needed the 'still led entering the 9th' rule.
- Blown saves excluded as before the 9th: 981.
- Team-games of 9+ innings where pitcher outs failed to reconcile with the line score: 0.

### Exploratory (not part of pass/fail)

| Sample | Cases | Engine | 95% CI | Naive | 95% CI | Engine − naive | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| Top-2, Avoid/Unavailable closers | 63 | 44.4% | [32.8%, 56.9%] | 41.3% | [26.0%, 56.9%] | +3.2 pts | [-8.0, +13.7] |
| Top-1, Limited closers included | 583 | 14.4% | [11.4%, 17.3%] | 15.3% | [12.0%, 18.5%] | -0.9 pts | [-3.4, +1.6] |
| Top-2, Limited closers included | 583 | 22.3% | [18.8%, 26.1%] | 24.2% | [20.4%, 28.2%] | -1.9 pts | [-4.8, +0.9] |

With Limited closers included, the closer took the save chance himself in 283 of 583 cases (49%).

