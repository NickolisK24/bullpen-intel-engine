# Pitcher Usage Role Separation — V1

## Purpose

The bullpen board groups pitchers by *availability*. This adds a second read:

> **"What kind of usage does this pitcher appear suited for?"**

Each pitcher card gets an **observed usage role** — a description of how the
pitcher has recently been used — with confidence, a short reason, evidence, and
limitations.

It is **descriptive, never advisory**. It classifies observed usage; it does not
prescribe usage. It never recommends, ranks, selects, or predicts, and it never
tells anyone who to pitch or where.

Allowed framing: "Observed role", "Usage profile", "Recent usage pattern",
"Appears used as". Forbidden framing (use this pitcher / best option /
recommended role / should pitch / deploy here / closer recommendation) does not
appear and is guarded by tests.

## Data inputs (this repo only)

Per pitcher, from recent `GameLog` rows in a **45-day** window
(`ROLE_WINDOW_DAYS` in `backend/services/pitcher_role.py`; staleness is flagged
against the separate 14-day active freshness window):

| Field | Used for |
| --- | --- |
| `game_date` | appearances, recency/staleness |
| `innings_pitched` | average IP, multi-inning detection |
| `save` | late-inning / high-leverage signal |
| `hold` | setup / bridge signal |
| `save_situation` | supporting evidence |
| `leverage_index` | late/setup signal **when present** |

No data is invented. `games_finished` exists in the schema (nullable on
`GameLog`) but is **not currently consumed by the role classifier**; no
`inning_entered` field exists. `leverage_index` is often null (it is only
populated by live sync, not the seed); when missing, late/setup are read from
save/hold flags only and confidence is capped — this is stated in the limitations.

> Innings note: `innings_pitched` is read as a decimal innings count
> (1.0 = one inning, 2.0 = two). MLB box-score notation (.1 = ⅓, .2 = ⅔) is a
> close approximation under this reading and only slightly understates fractional
> innings, keeping the multi-inning rules conservative.

## Role categories

| Key | Label |
| --- | --- |
| `late_high_leverage` | Late-Inning / High-Leverage Pattern |
| `setup_bridge` | Setup / Bridge Pattern |
| `middle_relief` | Middle Relief Pattern |
| `long_multi_inning` | Long Relief / Multi-Inning Pattern |
| `low_unclear` | Low Recent Usage / Unclear Pattern |
| `insufficient_data` | Insufficient Data |

## Deterministic rules (priority order, first match wins)

1. **Insufficient Data** — no usable appearances (0 outings, or no innings data).
2. **Low Recent Usage / Unclear** — fewer than **2** recent appearances.
3. **Late-Inning / High-Leverage** — `saves ≥ 1`, or (leverage present and
   average leverage ≥ **1.5**). Requires real supporting fields — never faked
   from fatigue score.
4. **Setup / Bridge** — `holds ≥ 1`, or (leverage present and average leverage ≥
   **1.0**).
5. **Long Relief / Multi-Inning** — average recent IP ≥ **1.5**, or ≥ 2 outings
   of ≥ 1.5 IP making up at least half of recent outings.
6. **Middle Relief** — the default: regular, shorter outings with no late/setup
   evidence.

Save/hold/leverage evidence (a *defined* late/setup usage) intentionally
outranks innings length; the multi-inning rule then catches long relievers who
lack that evidence.

## Confidence

`high` → `medium` → `low` → `none`. Starts `high` and degrades:

- `< 3` recent appearances → capped at **medium** (small sample).
- some outings missing innings data → capped at **medium**.
- latest outing outside the 14-day freshness window → capped at **low** (stale).
- late/setup read from save/hold flags with no leverage data → capped at
  **medium**.
- insufficient data → **none**; low/unclear → **low**.

## Explanation (every pitcher)

- **role label**, **confidence**, **short reason**
- **evidence** — e.g. "3 appearances in the recent window", "Average recent IP:
  1.9", "2 of 3 outings above 1.0 IP", "1 hold recorded", "Average leverage
  index: 1.80"
- **limitations** — always includes "Role is inferred from recent workload
  patterns only.", "Does not include manager intent.", "Does not include matchup
  context.", plus any data caveats (small sample, missing innings, stale,
  missing leverage/save/hold).

## Board integration

- **Pitcher cards (priority):** a compact, neutral role chip (role + confidence)
  plus an expandable **Usage role** section (reason, evidence, limitations). The
  chip styling is intentionally uniform so a role never reads as "better".
- **Team Context Layer / Team Comparison:** intentionally **not** changed in V1
  to avoid clutter and noise. Because the comparison reuses the same board
  builder, both teams' cards carry roles automatically wherever the board
  renders.

## API

No new endpoint. The role is classified **once** in `_build_team_board`
(`backend/api/bullpen.py`) and embedded on each card in the existing
`GET /api/bullpen/teams/<id>/board` response, so the single board and the
comparison (which renders two boards) both consume it.

## Governance boundaries

- No rankings, recommendations, selection, matchup, win/save probability,
  leverage advice, hidden priority, or "best arm" labels.
- `leader`/`ranking_applied`/`selection_made` semantics are untouched; the board
  stays `ranking_applied=false`, `selection_made=false`.
- Role is read only from in-repo data — never reputation, name, or external
  knowledge.

## Surface map

| Layer | File |
| --- | --- |
| Classifier (pure) | `backend/services/pitcher_role.py` |
| Card + endpoint wiring | `backend/services/bullpen_board.py`, `backend/api/bullpen.py` |
| View helper | `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` (`getRoleView`) |
| Card UI | `frontend/src/components/bullpen/board/BullpenBoardView.jsx` (role chip + disclosure) |
| Tests | `backend/tests/test_pitcher_role.py`, `frontend/tests/pitcherUsageRole.test.mjs` |

## Known limitations

- Role reflects **observed** recent usage, not manager intent, matchup, or
  planned deployment.
- `leverage_index` is frequently null (seed data has none); without it, late/setup
  rely on save/hold flags and confidence is capped.
- `games_finished` exists in the schema but is not consumed by the classifier,
  and no `inning_entered` field exists, so "closer vs setup" is approximated
  via saves vs holds and leverage.
- Small samples and stale data degrade confidence rather than forcing a label.
- The decimal-innings reading slightly understates fractional MLB-notation
  innings (conservative for the multi-inning rules).
