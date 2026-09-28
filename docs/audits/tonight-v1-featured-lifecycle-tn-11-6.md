# Tonight v1 featured games lifecycle presentation (TN-11.6)

Status: Games to Watch now shows only featured games whose served
`game.state` is not `final`.

This is a presentation change only:

- The frozen featured selection (`featured_game_pks`, TN-06), each game's
  `featured` marker and reason codes, the TN-03 overlay, and publication
  immutability are all unchanged.
- No backend change, migration, routing change or navigation change.

## Rule

`getVisibleFeaturedGames(games, featuredGamePks)` in `tonightView.js`:

1. Walks `featured_game_pks` in backend order.
2. Resolves each pk to its served game and skips any pk with no game.
3. Hides a game only when `state === 'final'`.
4. Keeps every other state: `scheduled`, `uncertain`, `live`, `suspended`,
   `postponed`, and any unknown or missing state.

The helper:

- makes one pass (O(f), f ≤ 4);
- does no sorting, scoring or replacement;
- reads no other field;
- returns the served game objects unchanged.

Unknown states fail open: `final` is the only state known to be complete, so
nothing else is hidden silently. Postponed and suspended games stay visible
because they are unresolved and incomplete.

## Rendering (`FeaturedGames.jsx`)

- Zero visible games: the section is absent. There is no heading, no
  container, and no "No featured games" or "previously featured" copy.
- One visible game: a single column capped at `max-w-3xl`, so desktop does
  not leave an empty half row.
- Two to four visible games: the existing grid, two columns from 1280 px.
- Page order is unchanged: Header, Lead, Games to Watch (when non-empty),
  Tonight's Slate, What Changed, Go Deeper.
- There is no new user state: no toggle, storage, URL state or polling.

## Nothing is lost

- Final featured games stay in Tonight's Slate under Completed Games (TN-11.5)
  and can be inspected when that section is expanded.
- Those cards keep `featured: true` in the served data, plus their Team Board
  and Matchup links.
- The lead (with its `pregame_context` marker) and What Changed are unchanged.

## Page-height impact

Measured with the late-night fixture (15 games, 14 final, featured =
[final, uncertain, final, final]), with Completed Games collapsed:

| Viewport | Before TN-11.6 (4 featured cards) | After (1 card) | Reduction |
| --- | --- | --- | --- |
| 390 px | 4,484 px | 2,874 px | 35.9% |
| 768 px | 3,122 px | 2,250 px | 27.9% |
| 1440 px | 2,464 px | 2,155 px | 12.5% |

Bundle impact: JS +0.09 kB (703.65 kB → 703.74 kB); CSS unchanged.

## Verification

- `frontend/tests/tonightFeaturedLifecycle.test.mjs` (14 SSR tests) covers:
  - each state's visibility;
  - unknown states fail open;
  - missing pks are skipped;
  - the ordering proof `[8, 3, 12, 5]` → `[3, 12]`;
  - the all-final, 3 final + 1 live, and 2 final + scheduled + postponed
    cases;
  - no replacement, and non-featured games never enter;
  - the late-night fixture: one card, Upcoming, and Completed Games (14);
  - final featured games in Completed with `featured: true`, and the helper
    returning the served objects unchanged;
  - the all-final fixture: section absent, no manufactured copy, Completed
    Games (15) with all 15 cards;
  - lead, slate, What Changed and section order unchanged;
  - handoff links;
  - the all-unfinished production fixture unchanged;
  - single-card layout;
  - a guard against sort, score, rank, weight, recommendation, `first_pitch`,
    `Date`, standings, Team State or workload inspection, toggles and fetches.
- `frontend/tests/browser/tonightFeaturedLifecycle.spec.mjs` (6 Playwright
  tests) runs cases A (1 non-final + 3 final) and B (all 4 final) at 390, 768
  and 1440 px. It checks:
  - the Games to Watch card count, or that the section is absent;
  - Upcoming and Completed contents;
  - expanding Completed, which includes the final featured games;
  - Team Board and Matchup links;
  - no overflow and axe clean;
  - one Tonight request;
  - no app errors.
- Two TN-11.5 assertions that pinned "Games to Watch keeps final featured
  games" were updated to the TN-11.6 rule, in `tonightSlateLifecycle.test.mjs`
  and `browser/tonightLifecycle.spec.mjs`.
