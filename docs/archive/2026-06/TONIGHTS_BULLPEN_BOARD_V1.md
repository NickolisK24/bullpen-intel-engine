# Tonight's Bullpen Board — V1

## Purpose

Answer one baseball question, fast:

> **"What does this bullpen look like tonight?"**

The board groups a team's relievers into the five availability buckets a coach
already reasons in — **Available · Monitor · Limited · Avoid · Unavailable** —
so the picture is readable at a glance, without scanning a fatigue table.

It is a **presentation layer** over systems that already exist. It introduces no
new scoring, no new classification, and no new baseball logic.

## Workflow

```
Bullpen  →  Tonight's Board (view tab)  →  pick a team  →  read the five groups
```

- Lives inside the existing **Bullpen** page as a view tab (no new dashboard
  silo, no new certification surface).
- A single team is selected at a time — the board is always one bullpen.
- Each pitcher card shows: **name, availability status, fatigue score,
  confidence, short reason**, and an expandable **Why?** with the underlying
  reasons and limitations.
- A freshness banner shows **data-through date, sync state, and confidence
  context** at the top. Stale data is surfaced with the existing trust
  messaging — never hidden.

## What it reuses

| Need | Reused system |
| --- | --- |
| Availability status, confidence, reasons, limitations | Availability Engine V1 (`services/availability.py`) |
| Per-team pitcher + fatigue + availability query | `_team_bullpen_rows` (shared with the bullpen overview) |
| Data-through date, sync freshness, trust limitations | `sync_metadata.build_sync_status_payload` |
| Badge styling, data-state copy, date formatting | `availabilityView.js`, `syncStatusView.js` |
| Empty / loading / error states | shared `UI/` primitives |

No availability calculation, status definition, or freshness contract is
duplicated.

## How grouping works

- Pitchers are placed into the group matching their existing
  `availability_status`.
- Groups are shown in a fixed, least-to-most-restricted order. That order is a
  reading convention, **not** a ranking of pitchers.
- **Within a group, pitchers are ordered alphabetically by name.** Position
  never encodes "better", score, or preference.

## Governance boundaries

- `ranking_applied` and `selection_made` are hard-coded **`false`** in the API
  payload and are protected by the existing API contract tests.
- Those raw governance fields are **never rendered** on the board — they remain
  API-level protections, not user-facing copy.
- The surface uses plain baseball language only. No contract/governance jargon,
  no certification panels.

## What it does **not** do

- It does **not** rank pitchers.
- It does **not** select, recommend, or prefer a pitcher.
- It does **not** predict outcomes, performance, saves, or injuries.
- It does **not** sort by fatigue, score, or "best available".
- It does **not** invent new calculations or hidden ordering.

## Surface map

| Layer | File |
| --- | --- |
| Grouping service (pure) | `backend/services/bullpen_board.py` |
| API route | `GET /api/bullpen/teams/<team_id>/board` (`backend/api/bullpen.py`) |
| API client | `getTeamBullpenBoard` (`frontend/src/utils/api.js`) |
| View helpers | `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` |
| Presentation | `frontend/src/components/bullpen/board/BullpenBoardView.jsx` |
| Container (team select + fetch) | `frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx` |
| Tests | `backend/tests/test_bullpen_board.py`, `frontend/tests/tonightsBullpenBoard.test.mjs` |

## Tests

- **Backend** — grouping order/completeness, alphabetical (not score) ordering,
  trust-metadata preservation, short-reason language, governance flags, empty
  teams, team isolation, and that no raw governance flags leak into cards.
- **Frontend** — all five groups render in order, card fields render, the
  **Why?** disclosure surfaces reasons/limitations, empty board and empty-group
  states, stale-data trust messaging, team switching, and a guard asserting no
  governance jargon appears on the surface.

## Known limitations (V1)

- Availability is derived from MLB game-log workload only — no injury reports
  or team-reported availability. Cards say so in their limitations.
- "Tonight" means "the latest workload data we have." When that data is outside
  the freshness window, the board says so rather than implying it is current.
- Defaults to the first team in the list; there is no cross-team board (by
  design — one bullpen at a time).
