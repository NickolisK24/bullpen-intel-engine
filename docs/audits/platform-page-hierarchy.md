# Platform Page Hierarchy Audit

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. Goal: align the current page hierarchy to the intended product lane —
> the daily operating picture for MLB bullpens — and eliminate duplicate/misplaced
> sections. Product language stays State → Why → Evidence → Freshness → Limitations.

Branch: `audit/platform-page-hierarchy`
Base commit: `ba774f6` (latest main)

## 1. Executive decision

The page set is close to the intended hierarchy, with three real problems to fix
(all frontend-only):

1. **Duplicate Operational Backtest** — the same backtest card renders on both
   Methodology and Data & Trust. **Data & Trust owns it** (it is empirical
   reliability evidence); Methodology keeps a one-line description and links to it.
2. **Duplicate exploratory ERA study** — appears on both Methodology ("Insights")
   and Data & Trust ("Secondary Exploratory ERA Study"). **Methodology owns it**
   (it explains a finding and what is/isn't claimed); remove the copy on Data &
   Trust.
3. **Data & Trust scope creep** — it hosts current team/operational analysis
   (`OperationalReadinessSection` → a "Recommendation V2" bullpen-state panel + a
   Team Operations readiness panel) and a Digest Preferences settings card. These
   do not belong on a data-trust page (and "V2" is an internal label). Move the
   operational readiness to Dashboard (or remove); move/defer Digest Preferences to
   account settings.

Plus two hygiene items: reorder the sidebar to match the product hierarchy
(Stories moves below Bullpen), and retire dead legacy code in `Home.jsx` (Home now
only renders the intelligence surface). No backend, COIN, or contract changes.

## 2. Current page inventory

Routes (`App.jsx`): `/`→Home, `/stories`→Stories, `/dashboard`→Dashboard,
`/bullpen`→Bullpen, `/prospects`→Prospects, `/methodology`→Methodology,
`/trust`→Data & Trust (+ signin/admin/private). Sidebar NAV order today: **Today,
Stories, Dashboard, Bullpen, Methodology, Data & Trust** (`Sidebar.jsx:14-20`).
`/prospects` exists but is **not in the sidebar** (orphan, outside the bullpen lane).

- **Today** (`Home.jsx` → returns `<IntelligenceSurfacePage/>`; `IntelligenceSurface.jsx`):
  What BaseballOS Sees, Today's Story, Tonight, Today's Bullpen Picture, Around
  Baseball (fallback), Explore. **Note:** `Home.jsx` also defines legacy sections
  (League Context, follow-team Tonight's Picture, What Changed) that are **never
  rendered** — dead code.
- **Stories** (`Stories.jsx`): "What Else BaseballOS Is Seeing", "The Story Feed"
  (filterable; from dashboard stories).
- **Dashboard** (`Dashboard.jsx`): Orientation, Tonight's Bullpen Landscape (+
  Tonight's Storylines), Bullpen Availability Context, League-Wide Bullpen Read,
  League-Wide Bullpen State (operating card), League-Wide Usage Roles, Quick
  Actions, freshness summary pill (+ link to Data & Trust).
- **Bullpen** (`Bullpen.jsx`): tabs — Team Board (`TonightsBullpenBoard`), Compare
  Bullpens, All Pitchers, All Teams.
- **Methodology** (`Methodology.jsx`): Operational Backtest (`AvailabilityBacktestCard`),
  Workload Read, Insights ("Secondary Exploratory Insight"), Data Sources & Stack.
- **Data & Trust** (`DataTrust.jsx`): Operational Backtest (`AvailabilityBacktestCard`),
  Freshness & Sync, Digest Preferences, Pitcher Workload Inventory, Operational
  Readiness (`OperationalReadinessSection`: Recommendation V2 panel + Team
  Operations readiness panel), Secondary Exploratory ERA Study (`FatigueInsightCard`).

## 3. Desired page hierarchy (target)

Today (front door) → Dashboard (league board) → Bullpen (deep dive) → Stories
(feed) → Methodology (definitions) → Data & Trust (freshness + reliability). Each
page keeps a single, distinct job; freshness summary may appear anywhere but the
full freshness/reliability surface is owned by Data & Trust and other pages link
to it.

## 4. Page-by-page ownership table (single source of truth)

| Content type | Owner | Other pages |
| --- | --- | --- |
| Single lead bullpen story | **Today** | Stories links to the feed |
| Browseable story feed | **Stories** | Today shows one lead + link |
| Tonight pregame bullpen cards | **Today** | — |
| League-wide bullpen state / landscape / usage roles | **Dashboard** | Today shows a compact "Today's Bullpen Picture" teaser + link |
| Team operating report (board, clean options, coverage safety, workload concentration, roster pressure, starter support) | **Bullpen → Team Board** | Dashboard/Today link in |
| Compare bullpens / pitcher details / all teams | **Bullpen** (tabs) | — |
| Definitions, availability labels, workload windows, clean-options / coverage-safety / roster-pressure / freshness methodology, "what we don't claim" | **Methodology** | — |
| Latest sync, bullpen data through, page checked, source/sync health, stale/unavailable warnings, reliability backtest | **Data & Trust** | Dashboard + sidebar show a freshness summary + link |
| Operational/availability backtest (reliability evidence) | **Data & Trust** | Methodology describes + links |
| Exploratory ERA / secondary insight | **Methodology** | (removed from Data & Trust) |

## 5. Duplicate / misplaced content findings (live)

1. **Operational Backtest — DUPLICATED.** Same `AvailabilityBacktestCard`
   (`getAvailabilityBacktest`) on Methodology (`Methodology.jsx:46-51`, framed "how
   availability/workload reads are computed") and Data & Trust
   (`DataTrust.jsx:110-121`, framed "evidence behind the bullpen picture"). Same
   component, same data, different surrounding copy.
2. **Exploratory ERA study — DUPLICATED.** Methodology "Insights / Secondary
   Exploratory Insight" (`Methodology.jsx:144`) and Data & Trust "Secondary
   Exploratory ERA Study" (`FatigueInsightCard`, `DataTrust.jsx:212`) cover the same
   exploratory finding.
3. **Data & Trust scope creep — MISPLACED.** `OperationalReadinessSection`
   (`DataTrust.jsx:190`) renders current operational/team analysis (a
   "Recommendation V2" bullpen-state panel via `getRecommendationV2BullpenState`,
   and a Team Operations readiness panel). This is team/operating analysis on a
   data-trust page, and "Recommendation V2" is an internal label. `Digest
   Preferences` (`DataTrust.jsx:175`) is a settings card, not data trust.
4. **Dead legacy "Today" code — CLEANUP.** `Home.jsx` only returns
   `<IntelligenceSurfacePage/>` (`Home.jsx:49-50`); its League Context / follow-team
   "Tonight's Bullpen Picture" / "What Changed" sections are never rendered. (So the
   apparent Home-vs-IntelligenceSurface duplications are dead code, not live.)
5. **Correctly scoped (no change):** Freshness/sync is summary on Dashboard/sidebar
   vs full diagnostic on Data & Trust (intended); Methodology definitions do not
   appear on Data & Trust; Stories feed vs Today's single lead story are distinct
   uses of the same source.
6. **Orphan:** `/prospects` is outside the bullpen lane and not in the sidebar —
   leave out of the hierarchy (defer).

## 6. Operational Availability Backtest ownership decision

**Owner: Data & Trust.** The backtest shows live availability-tier hit rates
against real usage windows — that is empirical proof of *system/data reliability*
("is BaseballOS current and dependable?"), which is Data & Trust's job. Methodology
should explain *that* the tiers are validated and what the backtest measures
(one or two sentences within the relevant section) and **link** to the live
backtest on Data & Trust, rather than re-rendering the same card. This satisfies
the rule "no duplicate sections unless one page owns it and another only links."
(If the team later decides the card is purely a model-evaluation explainer with no
reliability claim, Methodology could own it instead — but as rendered today it is
operational evidence, so Data & Trust.)

## 7. Recommended sidebar order

**Today → Dashboard → Bullpen → Stories → Methodology → Data & Trust.**
(Move Stories from position 2 to position 4, below Bullpen.) Rationale: the front
door, then the league board, then the team deep-dive, then the story feed, then the
explainer and trust surfaces. The current order elevates the story feed above the
core operating surfaces.

## 8. Recommended content moves / removals / links

- **Methodology**: remove the live `AvailabilityBacktestCard`; replace with a brief
  methodology description of the backtest + a link to Data & Trust. Keep the
  exploratory ERA/Insights section (sole owner). Keep Workload Read + Data Sources.
- **Data & Trust**: remove the duplicate exploratory ERA card (`FatigueInsightCard`)
  — Methodology owns it. Remove `OperationalReadinessSection` (Recommendation V2 +
  Team Operations readiness) from this page — move the team-operations readiness to
  Dashboard if kept, otherwise remove; do not surface internal "V2" naming. Move or
  defer `Digest Preferences` to an account/settings surface. Keep Operational
  Backtest (owner), Freshness & Sync (owner). Pitcher Workload Inventory may stay as
  a data-coverage artifact, or move to Bullpen → All Pitchers (lower priority).
- **Today**: retire the dead legacy sections in `Home.jsx`; keep only the
  intelligence surface. Keep "Today's Bullpen Picture" as a compact teaser that
  links to Dashboard for the full landscape.
- **Sidebar**: reorder per §7.
- **Prospects**: leave out of the bullpen-lane hierarchy (defer).

## 9. Recommended Codex implementation plan

- **Branch 1 — `chore/page-hierarchy-dedupe` (frontend-only, low risk):**
  - Remove the backtest card from Methodology; add a one-line description + link to
    Data & Trust.
  - Remove the exploratory ERA card from Data & Trust (Methodology keeps it).
  - Remove `OperationalReadinessSection` + Digest Preferences from Data & Trust
    (relocate readiness to Dashboard only if product wants it; otherwise drop).
  - Reorder the sidebar (Stories → position 4).
  - Tests: assert each duplicated section renders on exactly one page; assert no
    internal labels ("V2", "Recommendation V2", "backend", "snapshot") render;
    assert the sidebar order; assert Methodology links to Data & Trust for the
    backtest.
- **Branch 2 — `chore/today-legacy-cleanup` (frontend-only):** delete the dead
  legacy sections in `Home.jsx` (keep `Home` → `IntelligenceSurfacePage`); no
  behavior change. Optional; can be folded into Branch 1.

Keep both small, frontend-only, with before/after screenshots; no backend/contract
work.

## 10. Risks if not cleaned up

- The duplicate backtest means a single data change updates two pages and blurs
  which page "owns" reliability — users learn an inconsistent mental model.
- Data & Trust carrying current team/operational analysis (and an internal "V2"
  label) dilutes the trust surface and leaks internal naming into the product.
- The exploratory ERA study on two pages reads as two different studies.
- Sidebar elevating Stories above Dashboard/Bullpen misframes the product as a feed
  rather than an operating tool.
- Dead legacy Home code is a maintenance hazard (accidental divergence / confusion
  about which "Today" is live).

## 11. Out of scope (do not build yet)

- No page redesigns, no new sections, no new endpoints, no backend/COIN/data
  changes.
- Do not merge Stories into Today (keep distinct: one lead vs the feed).
- Do not build `/prospects` into the bullpen lane.
- Do not add per-card freshness or new trust widgets; Data & Trust already owns the
  full freshness surface.
- Do not rename internal model versions in the backend; only ensure no internal
  label renders in the UI.

## Validation / status checks

- Branch starts from latest main (`ba774f6`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

Consolidate ownership: Data & Trust owns the Operational Backtest and the full
freshness/reliability surface; Methodology owns definitions and the exploratory
study; Dashboard owns the league board; Bullpen owns the team deep-dive; Today owns
the lead story + Tonight + a landscape teaser; Stories owns the feed. Remove the
duplicate backtest and exploratory cards (replace with links to the owner), move
operational/settings content off Data & Trust, reorder the sidebar (Stories below
Bullpen), and retire dead legacy Home code. Frontend-only; no backend, COIN, or
contract changes.

ready for Codex implementation: YES (frontend-only cleanup; two small branches).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
