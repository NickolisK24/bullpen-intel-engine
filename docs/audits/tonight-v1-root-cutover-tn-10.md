# Tonight v1 root cutover (TN-10)

Status: Tonight v1 is the BaseballOS home. `/` and `/tonight` render the same
`TonightPage`, and `/today` redirects to `/`. The legacy Home composition is
unrouted and dormant.

There are no backend changes, no migration and no v5 retirement. TN-11 owns
the retirement work.

## Routing

| Path | Behavior |
| --- | --- |
| `/` | `TonightPage`: the TN-08/TN-09 page, with one `tonight_v1` request. |
| `/tonight` | The same `TonightPage` component (same `APP_ROUTES` Component), not a second implementation. |
| `/today` | Client `<Navigate to="/" replace>` plus the existing Vercel 308 `^/today/?$` → `/`. One hop, no loop. |
| `/tonight/` | The existing 308 to `/tonight` (unchanged). |

### `/today` target

`/today` targets `/` rather than `/tonight`. The repo's alias convention
redirects straight to the canonical path:

- `/today` → `/` already existed as a 308;
- trailing-slash redirects go to the canonical path.

`/` now renders Tonight, so `/today` reaches Tonight in one hop, and no legacy
Home is reachable through it.

## Legacy Home

- `App.jsx` no longer imports `components/home/Home`. No route renders `Home`
  or `IntelligenceSurface`, so the Daily Edition, Since Yesterday, legacy
  Tonight rail, bullpen picture, Explore and signup sections are unreachable.
- The root is not a hybrid: it renders only the Tonight page.
- The files are kept. Existing unit tests still import them, and TN-11 decides
  deletion.
- Dormant, frontend-only-for-Home code, for TN-11:
  - components: `src/components/home/Home.jsx` and
    `src/components/home/IntelligenceSurface.jsx`;
  - API clients in `utils/api.js`: `getHomeProjection`, `getTodayIntelligence`
    and `getTonightIntelligence` (the legacy v5 client);
  - view builders used only by `IntelligenceSurface`: `getDailyEditionView`,
    `getSinceYesterdayView`, `getBullpenPictureView`, `getTonightCards` and
    `getTonightGames`.
- Because nothing routes to Home, the production bundle tree-shakes it out. JS
  drops from 766.47 kB to 701.04 kB raw (−65.43 kB) and from 207.35 kB to
  191.40 kB gzip (−15.95 kB). CSS is unchanged.

## Navigation

- The primary nav's first item `Today → /` becomes `Tonight → /`, with alias
  `/tonight`.
  - `isNavDestinationActive` marks it active (`aria-current="page"`, plus the
    existing `.active` styling) on `/` and `/tonight` only.
  - There is no Home + Tonight duplicate, and no other nav item changed (League
    Board, Team Bullpens, Compare, Search, Stories, and the supporting pages).
- The Sidebar brand block is now a `Link` to `/` (`aria-label="BaseballOS
  home"`, visible focus ring). It is not a nav destination and never carries
  `aria-current`.

## Metadata, canonical, sitemap, hosting

- `ROOT_TITLE` is "BaseballOS | Tonight in MLB Bullpens".
- `ROOT_DESCRIPTION` is "See how every MLB bullpen enters tonight's games:
  published Team State, rest, recent usage, and what changed, with the data
  date always shown." It has no predictions, edges, rankings, betting,
  fantasy, "gassed", or mutable counts.
- Both values are shared by:
  - `metadataForLocation('/')`;
  - the `tonight` route-entry;
  - `index.html` (title, description, og and twitter tags).
- Canonical:
  - `/` → `https://baseballos.app/`;
  - `/tonight` → `https://baseballos.app/`, both at runtime and in the static
    `route-entry/tonight.html`. The existing route-entry `canonical` field
    expresses this directly.
- The sitemap is unchanged: it lists `/` once, and neither `/tonight` nor
  `/today`.
- Vercel is unchanged. The root is served by the filesystem `index.html`,
  `/tonight` by its route entry, and the `/today` 308 is kept.

## Analytics

Pageviews are route-based through `canonicalPage`, and there is no new
infrastructure:

- `/` keeps its existing `today` surface (the backend-governed vocabulary), so
  root Tonight is tracked naturally.
- `/tonight` is not mapped (unchanged from TN-08), so one navigation never
  double-fires.
- Renaming the surface would need a backend vocabulary change, so it is left
  for a later package.

## Guarantees carried over from TN-08/TN-09

At `/`:

- one request per page load:
  `GET /api/bullpen/intelligence/tonight?contract=tonight_v1`;
- no v5, Today, Team Board, Matchup, Fatigue, sync or per-game requests, and
  no polling;
- no v5 fallback: a v5 body never renders;
- unavailable, error/retry (focus returns to the h1), quiet day, lead,
  featured, slate, What Changed and handoffs all behave exactly as on
  `/tonight`;
- the source-of-truth guard is unchanged.

## Verification

- `frontend/tests/tonightRootCutover.test.mjs` (16 SSR tests) covers:
  - the shared component, the `/today` client and host redirect with no loop,
    and Home unrouted but kept;
  - unchanged Matchup, Pitcher, Team Board and History routes;
  - the root rendering the full Tonight page with no legacy Home markers;
  - `/` and `/tonight` rendering equivalent content (lead, featured, slate,
    changes, links);
  - root unavailable, error and v5 states;
  - nav: Tonight first, a single daily item, `aria-current` on `/` and
    `/tonight` only, and the brand link;
  - shared title, description and canonical;
  - `index.html` and the route-entry canonical;
  - the sitemap, host routing and pageview mapping;
  - the source-of-truth check.
- `frontend/tests/browser/tonightRoot.spec.mjs` (8 Playwright tests) covers:
  - `/` at 390, 768 and 1440: Tonight content, title, canonical, no legacy
    Home, Tonight `aria-current`, no overflow, axe-clean, exactly one request,
    no app errors;
  - `/` vs `/tonight` equivalence;
  - `/today` → `/` once;
  - direct refresh of `/` and `/tonight`;
  - brand and nav return to `/`;
  - reaching Tonight from the mobile menu by keyboard;
  - root unavailable, quiet day and error/retry with focus on the h1.
- Existing tests updated to the TN-10 decision:
  - `mobileNavigation.test.mjs`: labels, the alias active state, and the Tonight
    item matched by class because the brand also links to `/`;
  - `navigationRoutes.test.mjs`: root title and description, `/` →
    `TonightPage`, and nav labels;
  - `tonightV1Page.test.mjs` and `tonightV1Hardening.test.mjs`: root routing,
    and the `/tonight` canonical is now `/`;
  - `browser/publicJourneys.spec.mjs`: the shared fixtures answer
    `tonight_v1`, and the "cold Home Daily Edition" check became "cold root
    renders Tonight, not the Daily Edition".
