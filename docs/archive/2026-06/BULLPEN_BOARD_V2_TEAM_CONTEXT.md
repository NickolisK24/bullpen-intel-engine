# Bullpen Board V2 — Team Context Layer

## Purpose

V1 answers *"Which pitchers fall into each availability group?"*

V2 adds a **team-level context layer** that answers:

> **"What shape is this bullpen in tonight?"**

It is a **context layer, not a recommendation layer**. It summarizes the shape
of the bullpen from the V1 group counts and explains itself — it never ranks,
selects, recommends, or predicts.

V2 builds on top of V1; it does not replace it. The availability groups remain
the primary feature, with the context summary sitting above them in support.

## Visual hierarchy

```
1. Freshness banner
2. Team Context Summary   ← Bullpen Health statement (self-explaining)
3. Bullpen Snapshot       ← descriptive per-group counts
4. Availability Groups    (V1, unchanged)
```

## What it shows

- **Bullpen Health** — one plain statement (e.g. *"Bullpen workload appears
  manageable."*) with a **Why?** disclosure that lists the counts behind it.
- **Bullpen Snapshot** — the count in each of the five groups, plus total
  relievers and `% available`.
- **Confidence** — `High` normally; `Low` when data is stale (with the reason
  shown); `None` when there are no relievers to summarize.

## Deterministic rules (Bullpen Health)

Computed purely from the group counts, evaluated in a **fixed priority order**
(first match wins). Thresholds are fractions of the total reliever pool and live
as named constants in `services/bullpen_board.py`.

| Priority | State | Rule | Statement |
| --- | --- | --- | --- |
| 1 | `no_data` | total = 0 | "No bullpen availability to summarize tonight." |
| 2 | `constrained` | Avoid+Unavailable ≥ **40%**, or nobody Available | "Availability is constrained tonight." |
| 3 | `monitoring` | Monitor ≥ **40%**, or Monitor is the largest group | "Several relievers require monitoring." |
| 4 | `elevated` | Avoid+Unavailable ≥ **20%**, or Available < **40%** | "Bullpen workload is elevated." |
| 5 | `manageable` | none of the above | "Bullpen workload appears manageable." |

All statements are template strings filled with real counts. **No AI/LLM text,
no opaque scoring.**

## Descriptive metrics only

`total_relievers`, `available`, `monitor`, `limited`, `avoid`, `unavailable`,
`restricted` (= avoid + unavailable), and the percentages `pct_available`,
`pct_unavailable`, `pct_restricted`.

**Not allowed (and not present):** readiness score, recommendation score,
bullpen quality score, composite/ranking score, priority, or any pitcher
ordering.

## Transparency

Every statement explains itself. Example for a manageable pen of 10:

> **Bullpen workload appears manageable.**
> Why?
> - 7 of 10 relievers are Available Tonight.
> - No relievers are marked Avoid or Unavailable.
> - Availability classifications are workload-based only.

## Freshness / degraded confidence

When the freshness block reports the data is **not current**, the context layer:

- sets `confidence: "low"`,
- adds a limitation explaining the data is outside the freshness window, and
- surfaces that caveat inside the Why? explanation.

It never implies certainty over stale data.

## Governance boundaries

- The context layer adds **no** ranking, selection, recommendation, or
  prediction. `ranking_applied` / `selection_made` stay `false` at the payload
  level and are never rendered.
- The context block contains no score/rank/priority fields (asserted by tests).
- Plain baseball language only — no contract/governance jargon on the surface.

## Reuse (no duplication)

- **Availability Engine V1** for classifications.
- **Board V1** group counts as the sole input — no second availability pass.
- The **same `/api/bullpen/teams/<id>/board` response** carries the new
  `context` block (no new parallel endpoint/contract).
- Existing freshness/trust metadata and UI primitives.

## Surface map

| Layer | File |
| --- | --- |
| Context rules + builder (pure) | `backend/services/bullpen_board.py` (`build_team_context`, `classify_bullpen_health`) |
| API | extends `GET /api/bullpen/teams/<id>/board` (adds `context`) |
| View helper | `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` (`getBoardContextView`) |
| Presentation | `frontend/src/components/bullpen/board/BullpenContextSummary.jsx` |
| Tests | `backend/tests/test_bullpen_board_context.py`, `frontend/tests/tonightsBullpenBoardContext.test.mjs` |

## Known limitations (V2)

- Health reflects availability **counts**, not matchup, leverage, or role — by
  design.
- "Tonight" is bounded by data freshness; stale data is flagged, not hidden.
- Thresholds are deliberate, documented heuristics; they describe shape, not a
  quality grade.
