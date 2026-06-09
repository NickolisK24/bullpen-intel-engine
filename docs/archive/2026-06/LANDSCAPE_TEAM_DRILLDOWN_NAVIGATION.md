# Landscape Team Drilldown Navigation

## Decision

Make the team rows in **Tonight's Bullpen Landscape** (Most constrained / Most
available bullpen situations, and Monitoring concentration) clickable, deep-
linking into that team's bullpen board.

## Reason

The landscape cards naturally create curiosity — users immediately notice the
teams surfaced and want to investigate them. Previously a team row was a dead
end (Dashboard → landscape card → team listed → no action).

## Outcome

The dashboard becomes a **discovery workflow** rather than a static information
view:

```
Dashboard → Landscape card → click team → Tonight's Bullpen Board, focused on that team
```

Example: clicking **SF** opens the bullpen board focused on San Francisco;
clicking **LAD** opens it focused on the Dodgers — with no extra click.

## Guardrail

This is **navigation only**. It introduces no rankings, recommendations, matchup
advice, or predictions, and changes no availability / fatigue / trust / freshness
/ comparison / classification logic. The landscape's descriptive, deterministic
sorting is unchanged; rows simply become links into existing bullpen intelligence.

## How it works (reusing existing architecture)

- Reuses the existing `/bullpen?view=` deep-link pattern already used by the
  dashboard Quick Actions. Each landscape row links to
  `/bullpen?view=board&team=<ABBR>&source=landscape` (built by
  `buildLandscapeTeamHref`). `source=landscape` is passed for later UX analytics.
- `Bullpen.jsx` reads the existing `?view=` plus a new `?team=` param and passes
  `requestedTeam` to `TonightsBullpenBoard`.
- `TonightsBullpenBoard.resolveTeamId` resolves the param against the loaded team
  list by abbreviation (case-insensitive), numeric id, or name, and preselects
  that team **once** — a later manual team click is never overridden, and the
  default-to-first behavior is suppressed only while a resolvable deep link is
  pending (no flash). No second routing system was introduced.

## Visual affordance

Rows gain a lightweight interactive affordance — cursor pointer, a subtle hover
highlight, a hover underline on the team name, an arrow that appears on hover,
and a keyboard focus ring. They render as accessible `<a>` links (keyboard
reachable) and intentionally remain informational rows, not buttons.

## Tests

`frontend/tests/landscapeTeamDrilldown.test.mjs` — each callout team (constrained
/ available / monitoring) links to its board; rows are accessible anchors with
aria-labels; the affordance is present but not button-like; `buildLandscapeTeamHref`
and `resolveTeamId` (abbreviation/id/name/miss) are unit-tested; and a guardrail
check confirms no advisory/ranking language was introduced. Existing dashboard,
landscape, and game-context tests remain green (no regression).
