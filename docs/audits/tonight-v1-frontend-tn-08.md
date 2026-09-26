# Tonight v1 frontend page (TN-08)

Status: a new `/tonight` route renders the stored tonight_v1 edition. `/` is
still Home, and `/today` still redirects to `/`. The legacy default Tonight
response (`tonight_v5`) and its homepage rail are unchanged. No backend change
was needed.

## Data path

- The only request is `getTonightV1()`
  (`frontend/src/utils/api.js`), which calls
  `GET /api/bullpen/intelligence/tonight?contract=tonight_v1`.
  - It has a 12 s timeout and no `cachePolicy`, so no client response cache
    is used. In-flight GET dedupe is shared with every other request.
  - It never falls back to v5.
- The page issues one request per load. It makes no Team Board, Matchup,
  Fatigue, sync, Today or legacy Tonight calls, and does no polling. Retry
  re-issues the same single request.
- The backend is the sole owner of every baseball fact.
  `frontend/src/components/tonight/tonightView.js` only:
  - classifies the response;
  - turns already-decided values into strings;
  - keeps backend order.

  It does no sorting, arithmetic, ranking or inference. `null` is never shown
  as `0`. Team State goes through the shared fail-closed
  `readPublicTeamState` adapter.

## Response classification

| Condition | Page |
| --- | --- |
| Not an object, `contract` is not `tonight_v1`, `status` is `unavailable`, or `edition` is null | Unavailable: "Tonight's trusted bullpen edition isn't available yet." plus `Latest publication: <date>` when `current_publication` carries one |
| `summary.game_count == 0` with no games | Quiet day: header, then "No MLB games are on tonight's slate." |
| Request error with no data | "Tonight's bullpen view couldn't be loaded." with a Try again button (`role="alert"`) |
| Loading with no data | Heading plus skeletons (`role="status"`, `aria-busy`) |
| Otherwise | Full page |

A v5-shaped body is classified as unavailable and never rendered.

## Page order

1. **Header** (`TonightHeader`): the h1 "Tonight in MLB Bullpens", the edition
   date, and a subtle "Data through …" line. The compact summary is built
   only from:
   - `game_count`;
   - `team_state_counts` (Fresh / Stretched / Vulnerable / withheld);
   - `clubs_with_back_to_back_arms`;
   - `change_count`.

   Zero and non-integer values are omitted.
2. **Lead** (`LeadDevelopment`): nothing when `lead` is null. Otherwise it
   shows the frozen headline and detail verbatim. A subtle "Pregame context"
   label appears when `reason_codes` contains `pregame_context`.
3. **Games to Watch** (`FeaturedGames`): games in `featured_game_pks` order,
   using the same `TonightGameCard` as the slate. A pk with no game is skipped,
   and no section renders when the list is empty.
4. **Tonight's Slate** (`TonightSlate`): every game, in backend order.
5. **What Changed** (`LeagueChanges`): for each change, the team abbreviation,
   headline, optional detail, optional `occurred_on`, and a Team Board link
   (`buildTeamBoardHref`). `change_id` and `source_ref` are never rendered.
   The section is omitted when there are no changes.
6. **Go deeper**: a Team Boards link. Every card carries its two Team Board
   links and its Matchup link.

## Game card (`TonightGameCard` + `TonightTeamSide`)

- Status by state:

  | State | Label |
  | --- | --- |
  | scheduled | first pitch in ET, or "Start time not confirmed" |
  | uncertain, or any unknown value | "Status not confirmed" |
  | live | "In progress" |
  | final | "Final" |
  | postponed | "Postponed" |
  | suspended | "Suspended" |

- Team State is the primary element on each side. It shows the canonical
  label text; color is decoration only, and an sr-only "Team State:" prefix
  is added.
  - A withheld or non-canonical state shows "Team State withheld".
  - An unavailable side also shows "Bullpen read unavailable for this club."
- Rest line:
  - "N rested" whenever rest is available and the count is an integer (a known
    0 is shown);
  - "N B2B" only when greater than 0;
  - "N in 3-in-4" only when greater than 0.
  - Unavailable rest shows "Rest read unavailable".
- Key arms: name · role label · pattern (B2B / 3-in-4).
- Rotation appears only when non-null: "1 recent short start · 6.0 bullpen
  IP". `bullpen_innings` is shown exactly as frozen.
- Context: `context.sentence` verbatim when non-null, plus a "Pregame context"
  marker when `pregame_context` is present. A hidden sentence renders nothing.
- Links are the backend-authored `links.away_team_board`,
  `links.home_team_board` and `links.matchup`.

## Routing and hosting

- `APP_ROUTES` gains `{ path: '/tonight', Component: TonightPage }`.
- `ROUTE_ENTRY_METADATA` gains a `tonight` entry:
  - title "Tonight in MLB Bullpens | BaseballOS";
  - canonical `/tonight`;
  - a description with no mutable claims.
- `vercel.json` gains:
  - the `^/tonight$` → `/route-entry/tonight.html` rewrite;
  - `tonight` in the trailing-slash 308 set.
- `/tonight` is not added to the sitemap or the sidebar. Navigation is
  unchanged until the cutover (TN-09).
- `TonightsBullpenBoard.jsx` (Team Board shell) is untouched and not reused.

## Accessibility and layout

- The page has one h1, h2 sections, and an h3 per game card, with no level
  skips.
- Every link and button is at least 44 px tall and has a visible focus ring.
  Matchup links have a descriptive accessible name ("Open the NYY at BOS
  Matchup").
- Layout:
  - team sides stack at 390 px and sit side by side from 768 px;
  - cards form two columns from 1280 px;
  - there is no horizontal overflow at 390, 768 or 1440 px.

## Verification

- `frontend/tests/tonightV1Page.test.mjs` (SSR, 43 tests) covers:
  - items 1–40: route and API contract, no v5 fallback, header and summary,
    lead, featured order, slate order, every game state label, Team State
    (canonical, withheld, fail-closed), rest/B2B/3-in-4 null handling, key
    arms, rotation, context and pregame marker, backend links, What Changed
    fields and hidden ids, and the quiet, unavailable, error and loading
    states;
  - a production-shaped 15-game edition (section order and heading levels);
  - a source-of-truth check: rendered facts equal the backend fields, the
    tonight sources contain no sort/arithmetic/other-API/timer usage, and
    there is exactly one `getTonightV1` call;
  - route-entry metadata.
- `frontend/tests/browser/tonightV1.spec.mjs` (Playwright) covers:
  - at 390/768/1440: the 15-game fixture, featured and slate order, no
    overflow, zero axe violations, no page errors, and exactly one request
    (`/api/bullpen/intelligence/tonight?contract=tonight_v1`);
  - quiet and unavailable states;
  - network error, then retry with no fallback request;
  - card link targets and keyboard focus.
- Fixture: `frontend/tests/fixtures/tonightV1Fixtures.mjs` mirrors
  `tonight_read_model` and `tonight_v1_serving`.
