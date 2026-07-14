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
(`ROLE_WINDOW_DAYS` in `backend/services/pitcher_role.py` — unchanged;
staleness is flagged against the separate 14-day active freshness window).

Within that window, only **confirmed regular-season relief appearances**
qualify for the observed role (`qualifying_relief_logs` in
`backend/services/pitcher_role_authority.py`): a row must have a valid
`game_date`, `game_type == 'R'`, and `games_started == 0`.

- Starts (`games_started == 1`) are excluded — they belong to the
  bullpen-population Role Authority, which continues to receive the complete
  start/relief record.
- Rows with unknown `games_started` are **not assumed to be relief**; they are
  excluded and disclosed through limitations.
- Spring-training and postseason games are excluded from the current-season
  public role read.

Qualifying rows feed these fields:

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

## Deterministic rules

The **45-day** stability window is unchanged. Inside it, a **21-day
recent-confirmation window** (`ROLE_SIGNAL_RECENCY_DAYS`) decides whether a
role signal is still current enough to define the role: the classifier
describes the pitcher's *primary recent* relief usage, not the most prestigious
event anywhere in the window.

1. **Insufficient Data** — no usable appearances (0 outings, or no innings data).
2. **Low Recent Usage / Unclear** — fewer than **2** recent appearances.
3. **Sustained categorical (save/hold) role** — a save-based (Late) or
   hold-based (Setup) role qualifies only when ALL hold
   (`MIN_CATEGORICAL_ROLE_EVENTS` / `MIN_CATEGORICAL_ROLE_SHARE` /
   `MIN_RECENT_CATEGORICAL_ROLE_EVENTS`):
   - at least **2** corresponding events in the 45-day window,
   - those events are at least **15%** of qualifying relief appearances,
   - at least **1** corresponding event inside the latest **21 days**.
   One isolated save or hold never establishes a role. A `save_situation`
   appearance without a recorded save is supporting evidence only.
   When BOTH save and hold patterns qualify, they are **compared** — the larger
   sustained pattern wins, recent event counts break ties, and a genuine tie
   fails closed (rule 6) rather than forcing a role. Saves never outrank a
   larger hold pattern merely by prestige-first ordering.
4. **Recent leverage role** — leverage index defines a concrete role only with
   at least **3** qualifying relief appearances carrying leverage values inside
   the 21-day window (`MIN_RECENT_LEVERAGE_APPEARANCES`): recent average ≥
   **1.5** supports Late; ≥ **1.0** and < 1.5 supports Setup; below 1.0
   establishes neither. One isolated leverage value never defines a role.
   Full-window leverage remains visible as context only.
5. **Reconciliation** — categorical and leverage candidates are derived
   independently: if only one produces a concrete role, it is used; if both
   agree, it is used; if they disagree (one Late, one Setup), the result fails
   closed (rule 6) and both evidence sources are disclosed.
6. **Low Recent Usage / Unclear (conflict)** — tied sustained save/hold
   patterns with no decisive recent leverage, or a leverage/categorical
   disagreement, return Low/Unclear at **low** confidence with the conflict
   explained. The public authority maps this to **Limited Read**.
7. **Long Relief / Multi-Inning** — average recent IP ≥ **1.5**, or ≥ 2 outings
   of ≥ 1.5 IP making up at least half of recent outings.
8. **Middle Relief** — the default: regular, shorter outings with no sustained
   late/setup evidence.

A *sustained* late/setup pattern still outranks innings length; isolated
save/hold evidence that fails the thresholds no longer blocks a strong
long-relief read. Old role events demote before they leave the 45-day window:
without recent confirmation they remain visible as evidence but stop defining
the current role. These thresholds are deterministic product rules, not
validated predictions of manager intent.

## Confidence

`high` → `medium` → `low` → `none`. Starts `high` and degrades:

- `< 3` recent appearances → capped at **medium** (small sample).
- some outings missing innings data → capped at **medium**.
- latest outing outside the 14-day freshness window → capped at **low** (stale).
- late/setup established from save/hold frequency without confirming recent
  leverage coverage (no leverage data at all, or fewer than 3 recent
  leverage-bearing appearances) → capped at **medium**.
- conflict-based Low/Unclear results are always **low**, with the conflicting
  evidence disclosed — never described as a concrete role.
- strong recent leverage coverage (≥ 3 recent leverage-bearing appearances, no
  categorical contradiction) may support **high** confidence, subject to the
  sample/completeness/staleness caps above. One save or hold alone never makes
  a result high-confidence.
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
- **One public conclusion per card:** the backend-authored public role read
  (`author_public_role_read` in `backend/services/pitcher_role_authority.py`,
  emitted as `public_role_read` on each card) owns BOTH the role chip and the
  disclosure headline. When the public authority confirms a concrete role, the
  disclosure headlines the matching observed pattern; when the public result is
  guarded to **Limited Read**, the disclosure headlines Limited Read with a
  generic uncertainty explanation — a rejected concrete classifier role can
  never publicly headline the card. The raw classifier result remains available
  as diagnostic evidence, and the recorded appearances, innings, saves, holds,
  and limitations stay visible below the final conclusion.
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
| Relief-log qualification + public role read | `backend/services/pitcher_role_authority.py` (`qualifying_relief_logs`, `author_public_role_read`) |
| Card + endpoint wiring | `backend/services/bullpen_board.py`, `backend/api/bullpen.py` |
| View helper | `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` (`getPublicRoleReadView`, `getRoleView` fallback) |
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
