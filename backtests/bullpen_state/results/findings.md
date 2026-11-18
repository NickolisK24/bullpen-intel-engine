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
