# Team Bullpen Comparison — V1

## Purpose

The Bullpen Board answers *"what does Team A's bullpen look like?"*

This feature adds the natural next question:

> **"How do Team A and Team B compare — which bullpen appears more available
> tonight?"**

It is **descriptive comparison, not decision recommendation**. It aggregates two
existing board payloads (V1 groups + V2 team context) into transparent count
comparisons. It never declares a "better", "stronger", or "best" bullpen.

## Workflow

```
Bullpen → Compare Bullpens → pick Team A and Team B → side-by-side comparison
```

## Visual hierarchy

```
1. Team selectors
2. Freshness information (both teams)
3. Side-by-side snapshot (counts + percentages)
4. Context comparison observations (with Why?)
5. Team A bullpen board   (V1/V2, reused as-is)
6. Team B bullpen board   (V1/V2, reused as-is)
```

The comparison enhances the boards; it does not replace them.

## Comparison metrics (descriptive only)

Per team, taken straight from the V2 context metrics — no new math:

`total_relievers`, `available`, `monitor`, `limited`, `avoid`, `unavailable`,
`restricted` (avoid + unavailable), `pct_available`, `pct_unavailable`.

**Not allowed (and absent):** bullpen grade, team score, readiness/composite
score, team ranking, win probability, matchup/leverage advice.

## Comparison rules (deterministic)

Three fixed dimensions are compared, each by raw count:

| Dimension | Count compared | Descriptor |
| --- | --- | --- |
| `available` | Available Tonight | "classified Available Tonight" |
| `restricted` | Avoid + Unavailable | "marked Avoid or Unavailable" |
| `monitor` | Monitor | "in the Monitor group" |

For each dimension, `leader` is **A**, **B**, or **tie** purely by which count is
larger:

- A > B → "*Team A* currently has more relievers *{descriptor}*."
- A < B → "*Team B* currently has more relievers *{descriptor}*."
- A = B → "Both bullpens currently have the same number of relievers
  *{descriptor}* (*n*)."

`leader` means "has more of this count" — **not** better, preferred, or
recommended.

Overall summary:

- all three tie → **similar**: "Both bullpens currently show similar
  availability distributions."
- both empty → **no_data**: "Neither bullpen has relievers in the current
  freshness window."
- otherwise → **differ**: "These bullpens currently show different availability
  profiles."

## Transparency

Every observation carries its two numbers. Example:

> **Aces currently has more relievers classified Available Tonight.**
> Why?
> - Aces Available Tonight: 6.
> - Bears Available Tonight: 3.

Nothing hidden; everything reproducible from the counts.

## Freshness & confidence

- Each team's freshness is shown (current vs stale, data-through date).
- Overall confidence is the weaker of the two teams: `high` only when both are
  current; `low` if either is stale; `none` when both bullpens are empty.
- Stale teams are flagged and their limitations surfaced. The comparison never
  implies current information over degraded freshness.

## Governance boundaries

- No team ranking, grading, scoring, matchup, win-probability, or
  recommendation. `ranking_applied` / `selection_made` stay `false` and are
  never rendered.
- Observations contain no score/rank fields (asserted by tests); `leader` is the
  only directional field and is a plain count comparison.
- Plain baseball language only — no governance/contract jargon on the surface.

## Reuse (no duplication)

- The endpoint builds each side with the **same `_build_team_board` path** the
  single-team board uses (shared `_team_bullpen_rows` query + Availability
  Engine V1 + V2 context) — no second bullpen evaluation system.
- The comparison service consumes those two board payloads; it performs only
  count comparisons.
- Both full boards ride along in the response so the UI renders them with the
  existing `BullpenBoardView`.

## Surface map

| Layer | File |
| --- | --- |
| Comparison service (pure) | `backend/services/bullpen_comparison.py` |
| API | `GET /api/bullpen/teams/compare?team_a=&team_b=` (`backend/api/bullpen.py`) |
| API client | `getTeamBullpenComparison` (`frontend/src/utils/api.js`) |
| View helper | `frontend/src/components/bullpen/board/teamBullpenComparisonView.js` |
| Presentation | `frontend/src/components/bullpen/board/BullpenComparisonView.jsx` |
| Container (selectors + fetch) | `frontend/src/components/bullpen/board/TeamBullpenComparison.jsx` |
| Tests | `backend/tests/test_bullpen_comparison.py`, `frontend/tests/teamBullpenComparison.test.mjs` |

## Known limitations (V1)

- Compares availability **counts** only — not role, handedness, or matchup (by
  design).
- "Tonight" is bounded by data freshness; stale data is flagged, not hidden.
- `leader` ties on equal counts; magnitude is left to the reader via the shown
  numbers (no significance threshold is asserted).
- Two teams at a time; no league-wide comparison.
