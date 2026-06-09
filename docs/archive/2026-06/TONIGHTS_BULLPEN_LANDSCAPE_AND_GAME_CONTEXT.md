# Tonight's Bullpen Landscape & Today's Game Context

## Decision

Add two contextual surfaces:

1. **Tonight's Bullpen Landscape** — a league-wide orientation section on the
   homepage/dashboard.
2. **Today's Game Context** — a compact card near the top of the team bullpen
   board.

## Reason

Real user feedback: a first-time user did not understand why the app opened into
a specific team view. The product needed stronger initial orientation around
*tonight's league-wide bullpen state*, and a clearer relationship between a
team's bullpen and the games it belongs to.

The dashboard now answers "What does tonight's bullpen landscape look like?"
before users drill into a single team's bullpen.

## Guardrail

This is **contextual schedule/game framing only.** BaseballOS remains a bullpen
availability and workload intelligence product — not a scoreboard, matchup
engine, prediction engine, or recommendation engine. Specifically:

- No rankings, no best/worst, no advantage, no recommendations, no "should use",
  no predictions, no matchup advice, no hidden ordering.
- Any sorted display is **descriptive and deterministic** (by count, then
  percentage, then team name) and is labelled as a *situation*, not a ranking.
- Schedule context is derived only from stored game logs and is labelled
  honestly as **"Stored game-log context"** — never presented as a live schedule.
  Freshness states (live / historical / stale / unavailable) are always shown.

## What was built

### Backend — `services/game_context.py` (no live network)

- `build_team_game_context(team_id, reference_date=None)` — derives a team's most
  recent stored game on/before today from `GameLog`. States: `stored_game_log`
  (a game was found, possibly historical), `no_game_found` (team exists but has no
  stored game), `unavailable` (no team/schedule context). Returns
  `data_source: "game_log"`, a freshness `data_state`, a capped `confidence`, and
  `missing_fields: ["home_away", "scheduled_time"]` — because the stored game log
  does not carry home/away or scheduled time, those are reported missing, never
  fabricated.
- `build_landscape(records=None, ...)` — groups already-classified availability
  records by team and surfaces `constrained_bullpens`, `available_bullpens`, and
  `monitoring_concentration` (top 3 each, descriptive deterministic sort), plus a
  stored `games` anchor (`today_count`, `as_of_date`, `as_of_count`,
  `data_state`), `teams_evaluated`, `reference_date`, and disclaiming `notes`.
  `ranking_applied` / `selection_made` stay `false`.

### API (existing `bullpen` blueprint)

- `GET /api/bullpen/landscape` — the landscape payload.
- `GET /api/bullpen/teams/<team_id>/game-context` — the team game context.
- `GET /api/bullpen/dashboard` now also embeds `landscape` (reusing the records
  it already classified — no extra availability pass).

### Frontend

- `dashboard/BullpenLandscape.jsx` (+ `bullpenLandscapeView.js`) — the "Tonight's
  Bullpen Landscape" section, rendered near the top of the dashboard. Copy makes
  clear: *"This is bullpen context, not a game prediction."*
- `bullpen/board/TeamGameContextCard.jsx` (+ `teamGameContextView.js`) — the
  "Today's Game Context" card, rendered above the team board. Labels the data as
  stored game-log context, states unavailable fields explicitly, and carries the
  helper copy: *"Game context is provided to frame bullpen availability and
  workload. BaseballOS does not provide matchup advice or game predictions."*

## Data limitations (honest)

- Stored `GameLog` provides the opponent and date but **not** home/away or
  scheduled time; those are surfaced as unavailable.
- With the current historical sample, "games today" is typically 0; the landscape
  and card fall back to the latest stored slate and say so.
- A live schedule integration (`mlb_client.get_schedule`) exists but is
  intentionally **not** wired into these request paths — it would add a network
  dependency and would not match the stored sample data. This surface stays
  derived from durable data and testable.

## Tests

- Backend: `backend/tests/test_game_context.py` — team context states
  (stored/no_game_found/unavailable), missing fields, confidence, landscape shape
  and governance flags, deterministic descriptive sorting, stored games anchor,
  endpoint + dashboard integration, and a guardrail-language regression.
- Frontend: `frontend/tests/bullpenLandscapeAndGameContext.test.mjs` — landscape
  rendering + columns + stored-games anchor + dashboard integration, game-context
  card states (present / no_game_found / unavailable / loading / missing), and an
  affirmative-advisory-language regression (the required disclaimers negate
  "prediction"/"matchup advice" and are asserted as disclaimers).
