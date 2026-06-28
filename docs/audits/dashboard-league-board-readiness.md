# Dashboard League-Board Readiness Audit

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. Goal: does **Dashboard** work as the league-wide operating board — can a
> user, in ~30 seconds, see which bullpens are stable / thin / constrained / worth
> watching, where roster pressure sits, how fresh the read is, and where to deep
> dive? Product language stays State → Why → Evidence → Freshness → Limitations.

Branch: `audit/dashboard-league-board-readiness`
Base commit: `b0f1c5f` (latest main)

## 1. Executive decision

**Dashboard already works as a league operating board** — it is not a pile of
disconnected cards. It leads (after a hero + orientation) with a team-grouped
landscape (Thinnest late-inning margins / Most room to maneuver / Workload watch
groups), each team linking to its board, plus a Storylines recap; then league
roster-pressure context, the canonical league operating-state card, aggregate
availability/role counts, and CTAs. Internal language is clean, overclaiming is
low, page-level freshness is clear, and "What Changed Since Yesterday" is correctly
absent.

The gaps are **polish, not structure**, and frontend-only:
1. The landscape group titles do not use the canonical product vocabulary
   (Constrained / Stable / Worth Watching) — they read as evocative phrases, which
   slightly weakens 30-second scannability.
2. Roster pressure and clean-options/coverage-safety appear as league **context /
   proxies**, not as scannable per-team **groups** — and turning them into ranked
   groups would require a backend ranking, so **defer** (do not invent in the UI).
3. Minor: the operating-state summary card sits below the count sections; lifting
   it nearer the landscape would tighten the read.

No backend, COIN, contract, or data changes are needed for the board to function
honestly.

## 2. Current Dashboard inventory

Route `/dashboard` → `Dashboard.jsx` → `DashboardView` (data: `getBullpenDashboard`).
Rendered order:

1. **Hero** — "League-Wide Bullpen Overview" / BASEBALLOS / one-paragraph framing +
   `SeasonBanner` + `FreshnessPill` (provenance, latest data update, Workload Read
   confidence) + "Data & Trust details →" link.
2. **DashboardOrientation** — "what BaseballOS is / what to do next" (always shown).
3. **Tonight's Bullpen Landscape** (`BullpenLandscape`) — Storylines recap + three
   team-grouped columns (the league-board heart).
4. **Bullpen Availability Context** (`InjuryIlContextSection`) — league IL/inactive
   roster context (On Injured List, Inactive Roster, Clubs With 2+) + followed team.
5. **League-Wide Bullpen Read** — five availability count cards (Available / Monitor
   / Limited / Avoid / Unavailable).
6. **League-Wide Bullpen State** — `BullpenOperatingStateCard` via the operating-state
   read-model adapter (`scope: 'league'`).
7. **League-Wide Usage Roles** — role-distribution counts.
8. **Quick Actions** — Team Bullpen Board, Compare Bullpens, Pitcher Details,
   Methodology.
9. `FeedbackCTA` (testing-phase feedback prompt).
   `StaleDataNotice` renders above the body when stale-with-error.

(Not rendered on Dashboard: WhatChangedCard, OperationalReadinessSection,
FatigueInsightCard, AvailabilityDashboardSummary, SyncStatus — those live elsewhere.)

## 3. Dashboard page purpose assessment

Dashboard reads as a coherent league board: orient → scan the team groups → league
roster context → league state summary → supporting counts → drill in. The 30-second
test is met: a user can see which pens are thin/stable/worth-watching (landscape
columns), where roster pressure concentrates (Availability Context), the overall
league state (operating card), the freshness (hero pill), and where to go deeper
(landscape rows + Quick Actions). It does not duplicate Today, Stories, Methodology,
Data & Trust, or the team deep-dive.

## 4. Section-by-section findings

- **Hero** — page-level freshness pill + Data & Trust link; product-facing copy. Good.
- **DashboardOrientation** — orientation, not methodology depth. Keep concise.
- **Tonight's Bullpen Landscape** — three columns from the landscape payload, each
  row linking to that team's board; Storylines recap with an empty fallback; per-column
  empty states. This is the board's core and it works.
- **Bullpen Availability Context** — honest league roster-pressure context with an
  explicit "Explanatory Only" / "workload-based; roster status is separate" caveat.
- **League-Wide Bullpen Read** — aggregate availability counts (supporting context).
- **League-Wide Bullpen State** — the canonical card (full State → Why → Evidence →
  Freshness → Limitations) via the adapter, `scope: 'league'`.
- **League-Wide Usage Roles** — role distribution; honest "not assigned roles" caveat.
- **Quick Actions** — CTAs into team board / compare / pitcher / methodology.

## 5. League-board grouping assessment

Grouping is present and useful via the landscape columns
(`bullpenLandscapeView.js`):

| Group (column title today) | Source | Maps to |
| --- | --- | --- |
| **Thinnest late-inning margins** (metric: restricted) | `constrained_bullpens` | Most Constrained / Thin |
| **Most room to maneuver** (metric: available) | `available_bullpens` | Most Stable / Most room |
| **Workload watch groups** (metric: monitor) | `monitoring_concentration` | Worth Watching |

Each team row links to its board (deep link works). **Gaps:** (a) the titles do not
use the canonical state words (Constrained / Stable / Worth Watching), and (b) there
is **no per-team "High Roster Pressure" group** and **no league clean-options /
coverage-safety group** — those are surfaced as aggregate context (Availability
Context) or live at the team level (Bullpen board). A "thin" group exists via
"Thinnest late-inning margins". Empty groups render honest per-column empty states.

## 6. State → Why → Evidence → Freshness → Limitations gap analysis

| Element | State | Why | Evidence | Freshness | Limitations |
| --- | --- | --- | --- | --- | --- |
| League Bullpen State card | ✔ | ✔ "Why BaseballOS Sees This" | ✔ | ✔ | ✔ |
| Landscape columns | ✔ group label | ~ subtitle/metric | ✔ team + count | page-level | ~ league caveat |
| Availability Context | ✔ counts | ✔ "Why it matters" | ✔ IL/inactive | page-level | ✔ "workload-based; roster separate" |
| Bullpen Read / Usage Roles | ✔ counts | ~ subtitle | ✔ counts | page-level | ✔ subtitle caveats |

The canonical operating card carries all five legs. The supporting sections lean on
page-level freshness and section subtitles for Why/Limitations — acceptable for
aggregate context. No card overclaims or omits a needed caveat.

## 7. Freshness / date semantics assessment

Page-level freshness is clear and correctly scoped: the hero `FreshnessPill` shows
provenance, "Latest data update", and a "Workload Read" confidence label, with a
"Data & Trust details →" link to the owner of the deep diagnostics; `StaleDataNotice`
renders when stale-with-error; the operating card carries its own read-level
freshness. Dashboard is entirely completed-game data (no pregame slate), so the
Tonight slate-vs-data-through distinction does not apply here. Minor: align the
landscape's date wording to "Bullpen data through" for consistency with the rest of
the product.

## 8. Duplicate / misplaced content findings

- **Landscape (full) vs Today's "Today's Bullpen Picture" (teaser):** intended
  teaser → full; Dashboard owns the full board. Good.
- **"Tonight's Storylines"** is a compact recap of the landscape (a few bullets from
  the constrained/available groups), **not** the Stories feed. Distinct; only a mild
  naming overlap with the Stories page.
- **No methodology or trust diagnostics** render on Dashboard (only the hero "Data &
  Trust details →" link and a Methodology Quick Action). Correct — links, not
  duplication.
- `FeedbackCTA` is a testing-phase prompt, not league-board content; acceptable
  during user testing, defer/remove afterward.

## 9. Internal-language / overclaiming findings

- **Internal language: clean.** No user-visible COIN / V2 / deterministic / snapshot
  / backend / baseline / governance / sample-state terms on Dashboard. (Matches for
  "baseline"/"v2"/"governance" are Tailwind classes or code in components **not
  rendered** on Dashboard, e.g. OperationalReadinessSection / FatigueInsightCard.)
- **Overclaiming: low.** Honest disclaimers throughout ("not a game prediction",
  "not assigned roles", "Availability classifications are workload-based",
  "Explanatory Only"); the Storylines are descriptive ("narrowing the late-game
  margin", "more ways through the late innings"), not predictive. No injury,
  manager-intent, future-usage, betting, or fantasy claims.

## 10. Recommended Dashboard ownership model

Dashboard owns the **league-wide operating board**: the league bullpen state card,
the team groups (constrained / stable / worth watching), league roster-pressure
context, aggregate availability/role counts, page-level freshness, and CTAs into team
boards. It **links to, never duplicates** Today (front door), Bullpen (team
deep-dive), Stories (feed), Methodology (definitions), and Data & Trust
(freshness/reliability).

## 11. Recommended content to keep

Hero + freshness pill + Data & Trust link, DashboardOrientation (concise), Tonight's
Bullpen Landscape (groups + Storylines), Bullpen Availability Context, League-Wide
Bullpen State card, League-Wide Bullpen Read, League-Wide Usage Roles, Quick Actions.

## 12. Recommended content to move

Nothing needs to move off Dashboard — it is correctly scoped. (Cross-page placement
was already handled by the page-hierarchy de-dupe.)

## 13. Recommended content to remove / defer

- Defer/remove `FeedbackCTA` once user testing ends (not league-board content).
- **Defer (backend-gated):** a per-team "High Roster Pressure" group and league-wide
  clean-options / coverage-safety groups — these require the landscape payload to
  expose per-team rankings; do not invent them in the UI.
- **Do not add** "What Changed Since Yesterday" — there is no trusted day-over-day
  league state delta; it is correctly absent today.

## 14. Recommended grouping model

Keep the three-column landscape, but lead each column with the canonical state word
and keep the descriptive phrase as the subtitle:

- **Most Constrained** — "thinnest late-inning margins" (restricted).
- **Most Stable** — "most room to maneuver" (rested/available).
- **Worth Watching** — "workload watch" (monitor/concentration).

Optionally surface a fourth read only if/when a trusted per-team ranking exists:
**High Roster Pressure** (from a landscape roster-pressure ranking) — deferred until
the payload supports it. Until then, the league Availability Context covers roster
pressure honestly.

## 15. Recommended CTAs / deeper links

- Landscape rows already deep-link to specific team boards — the key league-board
  behavior. Keep.
- Quick Actions cover Team Board / Compare / Pitcher Details / Methodology; Data &
  Trust is linked in the hero. Optionally add a **Stories** CTA so the board routes
  to the feed.
- Consider a "Today" link for users who want the front-door briefing.

## 16. Recommended next Codex implementation branch

`feature/dashboard-league-board-polish` (frontend-only, small):
- Align the landscape group titles to the canonical state words (Most Constrained /
  Most Stable / Worth Watching), keeping the descriptive subtitles.
- Optional: lift the League-Wide Bullpen State card to just after the landscape so the
  two highest-value league elements sit together.
- Optional: add a Stories CTA to Quick Actions; align landscape date wording to
  "Bullpen data through".
- Tests: group titles render canonical labels; landscape rows link to team boards;
  empty group/storyline states are honest; no internal-language leak; freshness pill +
  Data & Trust link present; "What Changed" absent.

## 17. Suggested implementation phases

- **Phase A (clarity):** canonical group-title alignment.
- **Phase B (flow):** optional reorder (state card after landscape) + a Stories CTA +
  date-wording alignment.
Both ship in one small branch; Phase A first.

## 18. Out of scope (do not build)

No homepage duplicate, team deep-dive, methodology, trust/sync diagnostics, story
feed, or general MLB stats on Dashboard. No predictions, betting, fantasy, prospects.
No "What Changed / Trend Since Yesterday" (no trusted day-over-day state delta). No
new backend intelligence — the board functions honestly on the current payload; the
deferred roster-pressure / clean-options / coverage-safety league groups are
backend-gated and must not be invented in the UI. No UI redesign, no COIN or
data-generation changes.

## 19. Risks if this is not cleaned up

- Without canonical group labels, a first-time user may not immediately map
  "Thinnest late-inning margins" to "constrained", slightly weakening the 30-second
  scan and product-vocabulary consistency.
- Leaving the state-summary card below the count sections buries one of the two
  highest-value league elements.
- Low risk overall — the board is structurally sound; these are polish items, not
  defects.

## Validation / status checks

- Branch starts from latest main (`b0f1c5f`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

Dashboard already functions as the league operating board — team groups with deep
links, league roster-pressure context, the canonical operating-state card, clear
page-level freshness, clean language, low overclaiming, and "What Changed" correctly
absent. Ship a small frontend polish: align the landscape group titles to the
canonical state words and optionally tighten the order and add a Stories CTA. Defer
(backend-gated) per-team roster-pressure and league clean-options/coverage-safety
groups; do not add a day-over-day trend. No backend, COIN, contract, or data changes.

ready for Codex implementation: YES (one small frontend polish branch, Phase A then B).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
