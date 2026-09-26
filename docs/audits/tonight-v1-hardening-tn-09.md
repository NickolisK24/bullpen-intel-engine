# Tonight v1 hardening (TN-09)

Status: `/tonight` is hardened for layout, accessibility, resilience and
performance. It adds no baseball information, no endpoint and no backend
change. `/` is still Home, `/today` still redirects, and legacy Tonight v5 is
untouched. TN-10 owns the cutover.

## Audit before editing

The audit rendered a production-shaped stress edition at 390, 430, 768, 1024,
1280, 1440 and 1920 px. The fixture is `stressPayload()` in
`frontend/tests/fixtures/tonightV1Fixtures.mjs`:

- 17 games covering every served state, plus one scheduled game with no first
  pitch;
- 4 featured games and 12 changes;
- a 37-character team name and 40+ character player names;
- a 120-character lead headline and a 140-character lead detail;
- a long context sentence and long change copy;
- one withheld side, one zero-rested side and one rest-limited side;
- double-digit B2B and 3-in-4 counts;
- three key arms and a partial rotation.

What already held before editing:

- no horizontal overflow at any width;
- every Tonight tap target was at least 44 px. The only smaller targets are the
  shared footer links, which are outside Tonight.

Defects found:

| # | Defect | Fix |
| --- | --- | --- |
| D1 | Full team names appear in the card heading and again in each side, so long names wrap twice. | Each side now shows `AWAY · CRM`; the full names stay in the h3. |
| D2 | Each card had three action rows: two per-side Team Board buttons at different heights plus a separate Matchup row. They were misaligned at 768 px and up and made cards long on mobile. | One action row per card (away Team Board, home Team Board, Matchup), pinned to the card bottom so rows align across a desktop row. |
| D3 | Supporting facts (`text-chalk200`) competed with Team State. | Facts, rotation and role labels drop to `chalk300`/`chalk400`. Team State stays the only badge. |
| D4 | The lead was a full-width banner (1088 px of 3xl display text) with no handoff. | The box is capped at `max-w-4xl`, text at `max-w-3xl`, and the size stepped down. It gains a Matchup link resolved from the lead game's backend `links.matchup`. |
| D5 | What Changed stacked a bordered button under every item (1469 px for 12 items at 390 px), and lines ran 1088 px wide on desktop. | The team, date and Team Board link now share a quiet meta row, with the headline leading. The list is capped at `max-w-3xl`. |
| D6 | The context sentence was uncapped (about 930 px lines at 1024 px) and visually close to the facts. | Capped at `max-w-3xl` and set off with a left rule. |
| D7 | Unavailable and error looked identical. | Unavailable is a calm `role=status` with no button. Error is a `role=alert` with an amber edge and one retry. |
| D8 | Retry unmounted the h1 and the button, so keyboard focus fell to `<body>`. | `TonightHeader` (with the h1, `tabIndex=-1`) renders at a fixed tree position in every state. Retry moves focus to it before refetching. |
| D9 | The skeleton did not mirror the final layout. | Header skeleton lines sit inside the persistent header, and the card skeletons mirror the card structure. Skeletons are shapes only. |
| D10 | Found during testing: two activations in one task both passed the `useState` guard. The second refetch aborted the first, and the page fell through to the unavailable view. | A synchronous `useRef` guard allows one retry per activation. |

Page height with the 17/4/12 stress edition:

| Viewport | Before | After |
| --- | --- | --- |
| 390 px | 17,832 px | 14,665 px |
| 768 px | 11,166 px | 9,318 px |
| 1440 px | 7,246 px | 6,309 px |

## Layout decisions

- **390 / 430 px:** sides stack in reading order: identity, Team State,
  rest/usage, key arms, rotation. Context follows, then the action row.
- **768 / 1024 px:**
  - Cards are one column. Sides sit side by side from 768 px (`tablet`).
  - At 1024 px a two-column grid would leave each side about 210 px wide, so
    the page stays one column there.
  - Long lines are capped instead.
- **1280 / 1440 / 1920 px:**
  - Two-column card grid from 1280 px (`desktop`), unchanged.
  - The existing `max-w-6xl` page container is kept, so 1920 px matches
    1440 px.
  - The lead, context and change lists are line-length capped.
- **Featured:** the same card as the slate, with no rank markers or stronger
  color. The slate and What Changed sections are separated by a top rule and
  larger spacing. Every game stays in the full slate; nothing is hidden or
  collapsed.

## Accessibility

- Each state has exactly one h1, with `tabIndex=-1` so it is stable for focus.
- The heading hierarchy is h1 → h2 → h3, with no empty or skipped headings.
- Sections are labelled regions, and Go deeper is a labelled `nav`.
- Link names are distinct: "Open the {team name} Team Board" and "Open the
  {AWY} at {HOM} Matchup".
- Keyboard order matches DOM and visual order, and every stop shows a focus
  ring. There are no traps, and Tab leaves the page after the last link.
- Loading is a non-assertive `role=status` with `aria-busy` and an sr-only
  label. Unavailable and quiet are statuses. Only a failed request is an
  alert.
- Team State is readable by text alone (with an sr-only "Team State:" prefix).
  It keeps a bordered badge, so it survives forced colors. The existing tone
  palette passes axe contrast.
- Reduced motion: Tonight adds no animation, and the global reduced-motion rule
  already neutralises its `transition-colors`.
- There is no light theme in the app, so theme compatibility is a no-op.

## Performance

- One request per load: `GET /api/bullpen/intelligence/tonight?contract=tonight_v1`.
  There are no per-card, legacy, Team Board, Matchup, Fatigue, Today or sync
  requests, and no polling.
- Measured on the 17-game edition at 390 px:
  - about 66 ms from data arrival to a fully rendered slate;
  - CLS 0.0000 from skeleton to content;
  - zero DOM mutations after the page settles (no rerender loop).
- No memoization was added, since there was no evidence it was needed.
- Bundle impact:

  | Asset | Before (raw / gzip) | After (raw / gzip) | Change (raw / gzip) |
  | --- | --- | --- | --- |
  | JS | 764.77 / 206.83 kB | 766.47 / 207.35 kB | +1.70 / +0.52 kB |
  | CSS | 65.19 / 12.04 kB | 65.43 / 12.09 kB | +0.24 / +0.05 kB |

- No new dependencies.

## Verification

- `frontend/tests/tonightV1Hardening.test.mjs` (SSR, 17 tests) covers:
  - stress order (slate, featured, changes);
  - every state label;
  - long content rendered in full, with no clipping classes in Tonight
    sources;
  - the maximum-length lead and its handoff, including a lead whose game is
    missing;
  - withheld, zero-rested and null-rested sides;
  - large counts, three key arms and rotation;
  - Team State as the only badge;
  - one action row with backend links and distinct names;
  - context spacing and the pregame marker;
  - lead null, no featured, and no changes;
  - quiet day with changes;
  - unavailable vs error roles;
  - a stable h1 and heading integrity in every state;
  - a shape-only skeleton;
  - the expanded source-of-truth guard and root routing.
- `frontend/tests/tonightV1Page.test.mjs`: the TN-08 matrix, still passing. The
  What Changed assertion was updated for the meta-row link.
- `frontend/tests/browser/tonightV1.spec.mjs` (Playwright, 14 tests) covers:
  - at seven widths: no page or element overflow, all targets at least 44 px,
    zero axe violations, backend order preserved, exactly one request, and no
    app errors;
  - aligned action rows;
  - quiet day, quiet day with changes, and unavailable at 390/768/1440;
  - error → retry (two synchronous activations send one request) → keyboard
    retry → focus on the h1 → no re-poll;
  - loading: skeleton, CLS, render time, no mutations;
  - keyboard order and focus rings;
  - 200% zoom and WCAG text-spacing stress;
  - reduced motion;
  - direct entry and refresh;
  - handoff link destinations.
- Screenshots are attached to the Playwright report through `testInfo.attach`,
  with no new framework:
  - full slate at 390, 768 and 1440;
  - unavailable at 390, 768 and 1440;
  - quiet day at 390.
