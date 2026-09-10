# Today's Game Context — Visual Hierarchy

## Decision

Improve the visual hierarchy of the **Today's Game Context** card so the
opponent/matchup is the first thing a user notices, while keeping all trust
metadata visible.

## Reason

The card was technically correct but too data-oriented — the opponent sat in a
small grid field competing with Date / Historical / Status. Users understand the
bullpen faster when the game relationship is immediately obvious: a person should
read *"this bullpen belongs to a game against the Dodgers"* before scanning any
metadata.

## What changed (refinement, not rewrite)

- **Matchup is the hero.** The card now leads with `Team` **vs** `Opponent`,
  with the opponent rendered at display size in the amber gradient — the
  dominant element. The game date sits just under it.
- **Metadata is subordinate.** Data state ("Historical Game Log"), confidence
  ("Medium Confidence"), and status ("Final") moved into a single quiet,
  monospaced line beneath the matchup. Unavailable fields (home/away, scheduled
  time) remain stated. Nothing was hidden — only de-emphasized.
- **Elevated context banner.** The disclaimer is now a subtle left-accent banner:
  *"Game context helps explain bullpen workload and availability. BaseballOS does
  not provide matchup advice or game predictions."*
- **Polished empty states.** `no_game_found` → "No stored game-log context found
  for this date."; `unavailable` / error / null → "Schedule context unavailable.";
  opponent-missing degrades to "Opponent unavailable." No technical/debug wording.
- The view helper now exposes the team name (from the existing payload's `team`),
  a long data-state label, and the status label. No backend, availability,
  fatigue, trust, freshness, or classification logic changed.

## Guardrail

This is **contextual framing only.** The card does not become a scoreboard,
schedule product, matchup engine, or prediction surface. It adds no scores,
standings, records, win probability, betting/odds, projections, expected
outcomes, or matchup recommendations. The data remains stored game-log context,
labelled honestly, with trust transparency intact.

## Tests

- `frontend/tests/gameContextVisualHierarchy.test.mjs` — matchup rendered
  prominently (opponent is the hero element and reads before the metadata), trust
  metadata still visible (data state / confidence / status / missing fields /
  date), context banner + disclaimer present, `no_game_found` / `unavailable` /
  loading / null states, opponent-missing graceful degradation, and a
  scoreboard/advisory/prediction language regression.
- Existing `bullpenLandscapeAndGameContext.test.mjs` remains green (no regression).
- `npm run build` passes; `git diff --check` clean.

## Observations / limitations

- Home/away is not in the stored game log, so the connector is a neutral "vs"
  and the missing-fields note states home/away + scheduled time are unavailable.
- When the payload lacks a team name (older/edge payloads), the hero shows
  "vs Opponent" without the team prefix — still reads as the game relationship.
- Desktop and mobile both lead with the matchup; the metadata line wraps and
  stays readable on narrow widths.
