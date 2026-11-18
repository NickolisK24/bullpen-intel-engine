# Round 2 frozen specification

Frozen 2026-11-18. Chosen on 2024 only. Committed before any 2025 or 2026 data
was read for round 2. The machine-readable copy is
`results/round2_frozen_spec.json`. `round2.py evaluate` reads its parameters
only from that file. Every 2024 variant is in `results/round2_tuning_2024.json`
and in the round 2 report.

## Common rules (unchanged from round 1)

- **Primary sample.** Excludes doubleheader game 2.
- **Bullpen runs per 9.** Pitchers only; position players are excluded.
- **Within-team gaps.** The unit is a team-season. A team-season needs at least
  5 games in each group. Blown leads also need at least 3 led-after-six games in
  each group.
- **Intervals.** 95% percentile bootstrap, resampling whole team-seasons, 2,000
  draws, seed 20261118.
- **Pre-game data only.** Every feature reads appearances dated strictly before
  the game date (`History.view_before`), plus the round 1 pre-game availability
  flags. Those flags come from the replay that the no-lookahead test proves.
- **Population.** The candidate arms for a team-game are its round 1 pre-game
  active-bullpen read.

## Test 1: role-weighted state (frozen)

- **Top 3 late-inning arms (`saves_holds_30d`).** Rank the team's active-bullpen
  arms by:
  1. saves + holds in the 30 days before the game, descending;
  2. then production usage role, in the order late-inning/high-leverage, setup,
     middle, long, low/unclear, insufficient;
  3. then relief appearances in the prior 30 days, descending;
  4. then MLB id.

  The top 3 are the late-inning arms.
- **Usage role.** Production `services.pitcher_role.classify_usage_role`, run on
  the qualifying relief appearances (`qualifying_relief_logs`) from the 45 days
  before the game.
- **Flag.** A team-game is flagged when **at least 1** of the top 3 is flagged
  **Avoid or Unavailable** before the game.
- **Primary outcome.** Runs allowed in innings 7–9: flagged days minus the same
  team-season's unflagged days, averaged across team-seasons.
- **Pass bar (2025 and 2026 combined).**
  - The within-team gap is at least +0.20 runs per game.
  - The 95% interval excludes zero.
  - The flag fires on 5–20% of team-games. If it doesn't, the test fails.
- **Also reported.** Blown-lead rate and bullpen runs per 9 (pitchers only).

**Why this variant.** Only 2 of the 12 variants fired on 5–20% of 2024
team-games. Both use "at least 1 of the top 3 is Avoid/Unavailable", and both
fired 6.7% of the time. I picked the larger 2024 within-team gap in innings 7–9
runs:
- `saves_holds_30d`: +0.025 (CI −0.21 to +0.29)
- `role_authority`: +0.015 (CI −0.23 to +0.29)

These are statistically indistinguishable. Neither definition was shown better
on 2024.

## Test 2: save prediction (frozen)

- **Closer.** The active-bullpen arm with the most saves in the 30 days before
  the game, with at least 3. Ties go to more holds, then the lower MLB id.
- **Case.**
  - The closer is flagged Avoid or Unavailable before the game.
  - His team had a save chance in the 9th inning or later.
  - The game is not doubleheader game 2.
- **Who got the save chance.** The first pitcher, in appearance order, credited
  with a save, or with a blown save that happened in the 9th inning or later.
  The inning is derived; the boxscore does not record it:
  - A team's boxscore lists its pitchers in order, so the outs recorded before a
    pitcher entered is the game's out count when he entered. That count is
    exact. In 2024 the pitcher outs reconciled with the line score in every
    team-game.
  - A save belongs to the pitcher who finished the game, so it is 9th inning or
    later in any game of 9 or more innings.
  - A blown save counts as 9th inning or later if the pitcher entered with 24 or
    more outs recorded. It also counts if his outing reached the 9th and his
    team still led when its defensive 9th began, so the lead was lost in the
    9th or later. In 2024, 10 of 194 counted blown saves needed that second
    rule.
  - Games shorter than 9 innings are excluded.
- **Engine pick.** Among the non-closer arms flagged **Available or Monitor**,
  rank by:
  1. production usage role (order above);
  2. saves + holds in the prior 30 days, descending;
  3. **saves in the prior 30 days, then holds in the prior 30 days**, descending;
  4. MLB id.

  The top-ranked arm is the pick.
- **Naive baseline.** The same ranking over every non-closer active-bullpen
  arm, with flags ignored.
- **A miss.** The pick doesn't match who got the save chance. That includes
  chances that went to an arm outside the pre-game bullpen read, or to the
  closer himself.
- **Pass bar (2025 and 2026 combined).**
  - Engine top-1 accuracy is at least 50%.
  - The engine beats the naive baseline by at least 10 points.
  - The interval on that difference excludes zero.
  - With fewer than 100 evaluation cases, the result is **INCONCLUSIVE**.
- **Exploratory.** Top-2 accuracy, and the same test with Limited closers
  included.

**Why this tie-break.** On 2024's 21 cases, top-1 accuracy was:

| Tie-break | Top-1 accuracy | Lead over naive |
|---|---:|---:|
| saves then holds | 0.429 | +0.19 |
| relief appearances | 0.429 | +0.14 |
| most days of rest | 0.381 | +0.10 |

Two tie-breaks tied on accuracy. I broke the tie by the larger lead over the
naive pick. That second rule was decided after seeing the tie. It rests on 21
cases and should be read as essentially arbitrary.

## Disclosure

- **When the selection rules were set.** The rule for choosing variants (largest
  2024 gap among those with an allowed fire rate, and highest 2024 top-1
  accuracy) was written into the tuning code before the 2024 numbers were seen.
  It was not committed separately before tuning. The Test 2 secondary rule (lead
  over naive) was chosen after seeing the tie.
- **Data.** No new requests were made. Everything comes from the round 1 cache.
