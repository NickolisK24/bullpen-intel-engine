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
