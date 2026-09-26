# Tonight v1 slate lifecycle presentation (TN-11.5)

Status: Tonight's Slate now groups games by the served `game.state`. Completed
games sit behind a disclosure that is collapsed on every load.

This is a frontend presentation change only. It makes no backend, serving,
overlay, publication, routing or navigation change, and adds no migration.

## Mapping (the only derivation)

| Served `game.state` | Bucket |
| --- | --- |
| `live`, `suspended` | In Progress |
| `scheduled`, `uncertain`, `postponed` | Upcoming |
| `final` | Completed Games |
| anything else (unknown, missing) | Upcoming |

- An unknown state falls to Upcoming, the conservative unfinished bucket. This
  matches the card's existing "Status not confirmed" label and never reads as
  complete. No new visible label is added.
- `groupGamesByLifecycle(games)` in `tonightView.js`:
  - makes one pass in backend order and appends each game to its bucket, so
    the served order is kept inside every bucket;
  - does no sort, reverse, Math, score, rank, weight or time logic.

## Rendering (`TonightSlate.jsx`)

Section order:

1. **Tonight's Slate** (h2)
2. **In Progress** (h3), when non-empty
3. **Upcoming** (h3), when non-empty
4. **Completed Games (N)** (h3), when non-empty

Behavior:

- Empty buckets render no heading. On a quiet day (`game_count` 0) the slate
  is not rendered, so there is never a "Completed Games (0)".
- **All-final slate:** "All of tonight's games are complete." appears, followed
  by Completed Games (17), collapsed. Header, Lead, Games to Watch, What
  Changed and Go Deeper render as before.
- **Disclosure:** a `<button>` with `aria-expanded` and `aria-controls` that
  points to `#tonight-completed-games`. The target region is always in the DOM
  and carries `hidden` while collapsed.
  - Labels: "Show completed games" / "Hide completed games".
  - Enter and Space toggle it, and focus stays on the button.
- **Collapsed:** completed cards are not mounted, so there is no hidden DOM and
  no tab stops.
- **Expanded:** cards use the same `TonightGameCard` with an h4 heading, under
  the h3 group. They keep status "Final", Team State, rest, key arms, rotation,
  and the Team Board and Matchup links. Context is exactly as served.
- **Toggle:** local `useState` only. It makes no request and changes no URL.
  It never uses localStorage, sessionStorage or cookies, and never
  auto-expands. When a new payload arrives on a mounted page, it regroups the
  buckets and keeps the user's current expanded or collapsed choice.
- **Hierarchy:** In Progress uses `chalk100`, Upcoming `chalk200`, and
  Completed `chalk300` with a top rule. There are no new colors, and Completed
  is not styled as disabled.
- `TonightPageView` accepts `completedInitiallyExpanded` for server-rendered
  inspection in tests. The routed page never sets it.

## Unchanged

- Games to Watch still lists every featured game, final ones included.
- The lead (including its served `pregame_context` marker), What Changed, the
  header, Go Deeper and all handoff links are unchanged.
- One request per load: `GET /api/bullpen/intelligence/tonight?contract=tonight_v1`.
  There are no per-game, legacy or v5 requests, and no polling.

## Measurements

The all-final 17-game fixture was measured in Playwright, comparing page height
with Completed Games collapsed and then expanded:

| Viewport | Collapsed | Expanded | Reduction |
| --- | --- | --- | --- |
| 390 px | 4,816 px | 14,095 px | 65.8% |
| 768 px | 3,671 px | 8,812 px | 58.3% |
| 1440 px | 3,059 px | 5,957 px | 48.6% |

The remaining collapsed height is mostly Games to Watch (four featured cards)
and What Changed (12 items). Neither is in scope for this package.

Bundle size compared with TN-10:

| Asset | Raw | Gzip |
| --- | --- | --- |
| JS | +2.61 kB (701.04 → 703.65 kB) | +0.62 kB |
| CSS | unchanged | unchanged |

## Verification

- `frontend/tests/tonightSlateLifecycle.test.mjs` (14 SSR tests) covers:
  - mapping 1–6, postponed and suspended, and unknown fails safe;
  - order inside buckets, fixed bucket order, and reverse-input proof;
  - empty headings omitted, and quiet day unchanged;
  - mixed slate collapsed with Completed Games (7) and no completed cards
    mounted;
  - all-final helper text, Completed Games (17), and zero cards before
    expansion;
  - expanded cards: same component, status Final, links;
  - `aria-expanded` and a valid `aria-controls`, with no completed links while
    collapsed;
  - toggle is local state only;
  - lead, featured, What Changed and links unchanged;
  - h2 → h3 → h4 order with no empty headings;
  - the lifecycle source-of-truth guard.
- `frontend/tests/browser/tonightLifecycle.spec.mjs` (7 Playwright tests) runs
  at 390, 768 and 1440 for both the mixed slate (2 live, 1 suspended,
  5 scheduled, 1 uncertain, 1 postponed, 7 final) and the all-final slate. It
  checks:
  - lifecycle groups and order;
  - the collapsed default with no completed cards;
  - keyboard disclosure (Enter, then Space) with focus kept on the toggle;
  - card counts after expanding;
  - no overflow and axe clean, collapsed and expanded;
  - one request and no app errors;
  - `/` and `/tonight`;
  - handoff links and navigation;
  - page height.
  A separate check confirms the only tab stop in a collapsed Completed section
  is the toggle.
- Existing tests were updated for the new structure, which regroups the slate
  and mounts only unfinished cards by default:
  - TN-08 slate order and same-card test;
  - TN-08 production and source-of-truth tests, which now render expanded and
    look cards up by `game_pk`;
  - TN-09 hardening card lookups;
  - TN-09 and TN-10 browser card counts and order;
  - TN-10 root equivalence slicing.
