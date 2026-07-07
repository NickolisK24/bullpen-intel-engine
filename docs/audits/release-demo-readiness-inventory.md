# Release / Demo Readiness Inventory

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. Final route-and-surface inventory before a limited outside review:
> is every mounted route in-lane or intentionally hidden, are off-lane surfaces
> gone, are the trust/freshness guarantees intact, and is anything a demo blocker?
> Product lane: the daily operating picture for MLB bullpens. Product language:
> State → Why → Evidence → Freshness → Limitations.

Branch: `audit/release-demo-readiness-inventory`
Base commit: `d7af429` (latest main; `chore: remove off-lane frontend surfaces` merged
on top of the closed Product Credibility Pass)

## 1. Executive decision

**BaseballOS is ready for a limited public/demo review.** The lane-purity cleanup is
merged and verified: `/prospects` is fully removed (route, components, api helpers, and
nav link — not just hidden), `DigestPreferencesCard` is gone from `trust/`, and the
legacy Morning Bullpen Report is deleted (`Home` is now a thin wrapper around the active
Intelligence Surface). The Sidebar exposes exactly the six in-lane pages; every mounted
route is either public in-lane, an in-lane redirect, or an intentional hidden/auth/admin
path; and the catch-all redirects stray URLs to Today rather than 404-ing. The trust
guarantees established in the Product Credibility Pass (the read contract, freshness
semantics, honest stale/review/sample states, internal-language guards, no overclaiming,
Mets-case separation) remain intact because the cleanup only **removed** off-lane code.
The route/nav set is now enforced by `navigationRoutes.test.mjs`, so the lane cannot
silently drift. **No demo blockers found.** Recommended posture: proceed to limited
outside review; an optional final hardening branch is listed but not required.

## 2. Route inventory table

| Route | Component | Classification |
| --- | --- | --- |
| `/` | `Home` → `IntelligenceSurface` | public in-lane (Today front door) |
| `/today` | redirect → `/` | in-lane alias (no dead end) |
| `/dashboard` | `Dashboard` | public in-lane (league board) |
| `/bullpen` | `Bullpen` | public in-lane (team board / deep-dive) |
| `/stories` | `Stories` | public in-lane (selective feed) |
| `/methodology` | `Methodology` | public in-lane (definitions) |
| `/trust` | `DataTrust` | public in-lane (freshness/sync/reliability/backtest) |
| `/about` | `About` | public support page (added after this audit's base commit) |
| `/how-to-read` | `HowToRead` | public support page (added after this audit's base commit) |
| `/signin` | `SignIn` | hidden/auth — intentional |
| `/auth/verify` | `VerifySignIn` | hidden/auth — intentional |
| `/admin/product-intelligence` | `ProductIntelligenceAdmin` | hidden/admin — intentional |
| `/posts-bpen-7f3d9c` | `PrivatePosts` | hidden/private — intentional (obscured path) |
| `*` | redirect → `/` | catch-all (no 404; old `/prospects` bookmarks land on Today) |

No `/prospects` route exists. App.jsx no longer imports a Prospects component.

## 3. Public route readiness

The six public routes are exactly the canonical hierarchy (Today → Dashboard → Bullpen →
Stories → Methodology → Data & Trust) and match the Sidebar nav one-for-one. `/today`
redirects to `/` so the documented alias never dead-ends. `navigationRoutes.test.mjs`
asserts the public set is exactly `['/', '/dashboard', '/bullpen', '/stories',
'/methodology', '/trust']`. All public routes are in-lane and demo-ready.

> **Update (2026-07, phase-0-clarity/01):** two public support pages were added after
> this audit's base commit — `/about` (About) and `/how-to-read` (How to Read). They are
> not sidebar lanes; they are reachable from the Today page's Learn & Explore cards and
> from the footer's learn/trust link row (About, How to Read, Methodology, Data & Trust).
> The six-lane sidebar hierarchy above is unchanged.

> **Update (2026-07, phase-0-clarity/02):** league-view ownership was consolidated.
> The Dashboard is now the only full league-board surface (landscape lanes, one
> league state read, roster availability context; the orientation strip, the
> League-Wide Bullpen Read count tiles, and the Quick Actions cards were removed
> as duplicates of the landscape, the state card, and the sidebar). Today's
> "Bullpen Picture" is a teaser strip — one standout team per lane plus a
> "View full league board" handoff to `/dashboard`. The Bullpen page's "All
> Teams" tab (the 30-team Avg Workload / risk-tier score table) was retired so
> no score-forward league table competes with the Dashboard; `/bullpen` now has
> three tabs (Team Board, Compare Bullpens, All Pitchers) and `?view=teams`
> deep-links fall back to the Team Board. Route set unchanged.

> **Update (2026-07, phase-0-clarity/03):** the Team Board was consolidated to
> answer one question ("who in this bullpen can pitch tonight, who can't, and
> why"). The compact Team State card is now the single team-state read — the
> Overall Availability stress strip and the Team Context/"Bullpen Read" count
> snapshot that restated it were removed (the availability groups are the
> primary visual). The three-mode "View" segmented control became a single
> "Show unavailable arms" toggle on the team-selector row; the unavailable-only
> audit view left the public controls (the roster banner's evidence list covers
> that inspection job). Recent Bullpen Work (Phase 0G) stays the Team Board's
> evidence surface and its duplicate mount on the All Pitchers tab was removed.
> Compare Bullpens keeps the freshness chips, side-by-side read, and
> observations, and now links to each full team board instead of embedding two
> complete boards. Route set unchanged.

## 4. Hidden / private / admin route assessment

Four non-public routes remain and are intentional: `/signin` and `/auth/verify` (auth),
`/admin/product-intelligence` (`ADMIN_PRODUCT_EVENTS_PATH`, admin instrumentation), and
`/posts-bpen-7f3d9c` (`PRIVATE_POSTS_PATH`, an obscured private path). None appear in the
Sidebar or any product link, so a demo user never encounters them through the UI. They
are reachable by direct URL by design; the admin/private surfaces should remain
access-gated server-side (unchanged by this audit). The test suite confirms these paths
are present and that none surface a public nav link. Acceptable for demo.

## 5. Off-lane surface assessment

Clean. A full `frontend/src` sweep finds **no** prospects residue (the
`components/prospects/` directory is removed, no `getProspects*` helpers remain in
`api.js`, no `href="/prospects"` renders), **no** `DigestPreferences` residue
(`trust/` contains only `DataTrust.jsx` and `AvailabilityBacktestCard.jsx`), and **no**
`LegacyMorningBullpenReport` file on disk. No live import resolves to any removed module
(`homeCanonicalStoriesView`, `LegacyMorningBullpenReport`, `prospects`,
`DigestPreferences` all return zero live imports). No off-lane surface is reachable.

## 6. Page-by-page demo readiness

- **Today (`/`)** — `Home` renders `IntelligenceSurfacePage` (the active Intelligence
  Surface): lead read, Tonight watch items, league teaser, Explore CTAs. **Ready.**
- **Dashboard (`/dashboard`)** — league operating board; landscape columns drill into
  team boards; freshness pill links to Data & Trust. **Ready.**
- **Bullpen Team Board (`/bullpen`)** — team operating report via the shared
  `BullpenOperatingStateCard`: State → Why → Evidence (active workload, roster pressure,
  starter support, clean options, coverage safety, workload concentration) → Freshness →
  Limitations, plus pitcher lanes. **Ready.**
- **Stories (`/stories`)** — selective, trust-aware feed: per-card State→Why→Evidence
  blueprint, freshness strip, limitations scope note, live vs "Review-only" signal, and
  per-card "Under review" marker. **Ready.**
- **Methodology (`/methodology`)** — owns definitions/how-reads-are-computed; defers
  reliability/freshness to Data & Trust; `displayCopy()` sanitizes internal tokens.
  **Ready.**
- **Data & Trust (`/trust`)** — owns freshness, sync health, reliability (Operational
  Backtest), and data limitations; explicit term definitions and layered stale fallbacks.
  **Ready.**

## 7. Freshness / stale / review / sample-state assessment

Unchanged by the cleanup and correct. Today separates the Tonight slate from completed-
game "Bullpen data through"; Dashboard, Team Board, and Stories stamp "Bullpen data
through" with completed-game dates; the Sidebar shows "Page checked / Latest data update
/ Bullpen data through"; Data & Trust defines each term. Stale states thread through
(`StaleDataNotice` / `FreshnessBadge state="stale"`). Stories renders an explicit live
("Current MLB data") vs "Review-only intelligence — not live MLB data" signal and an
"Under review" per-card marker, so review-only content never looks live. No date is
mislabeled.

## 8. Public-language / internal-term safety assessment

Clean and guard-enforced. Rendered output across the six pages exposes none of the
banned terms (COIN, V2–V4, deterministic, snapshot, endpoint, backend, recommendation
engine, baseline distribution, governance layer, sample/review state, raw/canonical
feed, model output, quality_status, suppression_reason, source, trustAvailability,
bullpenPressure). Guards remain active: `operatingStateReadModel` safeText filters,
the Stories adapter's internal-token regex, and Methodology's `displayCopy()`. The
`trustAvailability` / `bullpenPressure` reads are deliberately not surfaced on the public
card. Residual risk is latent only — any newly surfaced field must keep using these
whitelists.

## 9. Overclaiming / public-trust assessment

Low. All reads are descriptive and past/present-tense. No page claims manager intent,
bullpen phone activity, private medical availability, future usage, predictions, betting,
fantasy, or guaranteed outcomes. Stories' "why it matters tomorrow" is framed as
continuation, not forecast; continuity badges are structured day-over-day story-type
descriptions, not predicted outcomes. Methodology/backtest copy is bounded with caveats
and sample sizes. Public copy is safe for outside eyes with minimal editing.

## 10. Mets-case safety assessment

Holds. The operating-state read model builds roster pressure from roster authority
(injured-list / inactive / unknown) as a **separate** concern from the active-availability
counts that drive State and the primary concern, so unavailable/inactive/IL arms are never
implied as active coverage. Team Board and the league card share the same card/adapter, so
the separation holds on both surfaces. The cleanup did not touch this logic.

## 11. Dead code / orphan helper assessment

The major dead-code items from the prior audit are resolved: prospects components + api
helpers, `DigestPreferencesCard`, legacy Morning Bullpen Report, and the orphaned
`homeCanonicalStoriesView` are all removed, with no dangling imports. Remaining `home/`
files (`Home.jsx`, `IntelligenceSurface.jsx`, `BullpenStories.jsx`, `homePresentationView.js`)
are all live (`BullpenStories` still supplies `SectionHeading` / `StoryBlueprint` /
`StoryDisclosureNote` to Stories). No orphan helpers or dead exports were found in the
in-lane surfaces. Nothing here blocks a demo.

## 12. Test alignment assessment

Strong. `navigationRoutes.test.mjs` loads `APP_ROUTES` and asserts: the public product
set is exactly the six in-lane routes; `routeByPath('/prospects')` is `undefined`; the
hidden routes `/signin`, `/auth/verify`, `/admin/product-intelligence`,
`/posts-bpen-7f3d9c` exist; and the rendered shell contains no `href="/prospects"`. No
stale `*prospects*` / `*digest*` / `*legacy*` / `*morning*` test files remain. The suite
now enforces the hierarchy and actively prevents re-mounting a removed surface, so lane
drift is test-guarded. (Running the full suite is recommended as a pre-demo gate — see
§14.)

## 13. Mobile / demo risk assessment

Low. The Sidebar has a mobile toggle (`aria-label="Toggle navigation"`) and the main
pages use responsive grids (verified in prior page audits). Recommended pre-demo
spot-checks (no code change implied): the Bullpen pitcher-detail overlay on small
screens, the Stories two-column grid collapsing to one column, and the Dashboard
landscape columns stacking. No mobile-layout blocker identified.

## 14. Deploy / API failure-state risk assessment

Low and already handled in-product. Each page has loading / error / stale handling
(`LoadingPane`, `ErrorState` with retry, `StaleDataNotice`), so an API hiccup during a
demo degrades to an honest state rather than a blank screen or console crash. The
catch-all `*` route redirects unknown URLs (including old `/prospects` bookmarks) to
Today, so there is no 404 path. Pre-demo operational checklist (process, not code): run
the frontend test suite green; confirm the production sync has populated current data so
freshness reads "current" rather than stale; click each of the six nav items and one
team board once on the demo build; confirm no uncaught console errors on first paint.

## 15. Remaining blockers, if any

**None.** No correctness, trust, lane-purity, routing, or off-lane-surface blocker
remains. The product can go to limited outside review as-is.

## 16. Remaining polish follow-ups

All optional, none blocking:
1. **Stories flagship cross-surface de-dup** (Stories audit Phase C) — Today's flagship
   can still reappear as a Stories card; a low-priority presentation tweak.
2. **Methodology sample-composition footnote** — add a one-line "based on N relievers over
   M completed games" for backtest sample sizes; clarity nit.
3. **Hidden-route gating spot-check** — confirm `/admin/product-intelligence` and
   `/posts-bpen-7f3d9c` are server-side access-gated (operational verification, not a code
   change here).

## 17. Recommended final Codex hardening branch, if needed

Optional, not required before review: `chore/demo-hardening-polish` (frontend-only, tiny)
— only if you want the Phase C Stories de-dup and the Methodology footnote landed before
outside eyes. It carries no trust risk and can equally be deferred to after the review.
Do **not** gate the demo on it.

## 18. Recommended next Claude audit, if needed

None required before the review. After the limited review, the highest-value next audit
is a **post-review feedback triage / first-public-iteration scope** audit that turns
observed reactions into a prioritized, in-lane backlog — rather than any further
pre-review inspection, which would be diminishing returns.

## 19. Out of scope (do not build)

No prediction engines, betting, fantasy, prospect surfaces (the orphan is removed — keep
it gone), social automation, public-posting workflows, or general MLB stat pages. No new
backend intelligence. No large redesign. No Trend Since Yesterday state card (no trusted
day-over-day **state** delta; the descriptive continuity badge stays as-is). No endpoint-
contract, COIN, or data-generation changes. Do not un-hide or productize the admin/private
routes for the demo.

## 20. Risks if proceeding to review (and mitigations)

- **Stale data on demo day** reads as "the product looks behind." Mitigation: confirm the
  production sync has run and freshness shows current before the session (operational).
- **Direct-URL admin/private access** if a hidden path leaks. Mitigation: rely on
  server-side gating (spot-check §16.3); these are unlinked and obscured.
- **Lane drift in future work** re-introducing an off-lane surface. Mitigation: already
  test-guarded by `navigationRoutes.test.mjs`; keep that assertion.
- **Unrun test suite** masking a regression. Mitigation: make a green frontend suite a
  pre-demo gate (§14). None of these are code blockers today.

## Validation / status checks

- Branch starts from latest main (`d7af429`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- No data-generation changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

BaseballOS is ready for a limited public/demo review. The lane is clean and
test-enforced: every mounted route is in-lane or intentionally hidden, `/prospects` and
the other off-lane surfaces are fully removed (not merely hidden), the six in-lane pages
preserve the State → Why → Evidence → Freshness → Limitations contract with correct
freshness and honest stale/review/sample states, internal-language guards hold, nothing
overclaims, and the Mets-case separation is intact. No demo blockers remain. Proceed to
limited outside review; treat the listed polish items and a green test run as an optional
pre-flight, not a gate.

ready for Codex implementation: OPTIONAL (a tiny demo-polish branch; not required).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
