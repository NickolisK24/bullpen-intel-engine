# Homepage Freshness / Date-Label Semantics Audit

> Audit / planning pass only. No frontend implementation, no backend change, no
> COIN/contract/data-generation/schedule/Tonight-selection change, no homepage
> redesign. The question: do the homepage "Data through" labels mean the same
> thing across surfaces, and what is the safest user-facing language?

Branch: `audit/home-freshness-date-semantics`
Base commit: `d8f5c58` (Phase 0B/1A/1B/2 merged)

## Summary

**The confusion is real and confirmed.** The homepage stamps the same label —
"Data through" — onto two semantically different dates that sit next to each
other:

- **Tonight** stamps `tonight.reference_date`, which is `product_current_date()`
  — the **pregame slate date** (e.g. Jun 27), not completed-game data.
- **Today's Bullpen Picture / Around Baseball / Sidebar** stamp `data_through`,
  which is the **latest completed game date** (e.g. Jun 26) — the real
  completed-game bullpen-workload basis.

A normal user reading "Tonight: Data through Jun 27" beside "Data through Jun 26"
reasonably infers that newer (Jun 27) bullpen workload data exists. It does not —
Jun 27 games have not been played; the Tonight cards' bullpen reads are based on
completed games through Jun 26. **The fix is frontend label selection from
existing payload fields; no backend contract change is required.** Both dates are
already present in the payloads.

## Current freshness/date sources

The homepage (`IntelligenceSurface.jsx`) fetches three intelligence endpoints
(`getTodayIntelligence`, `getTonightIntelligence`, `getBullpenLandscape`) plus the
dashboard (`getBullpenDashboard`) for shared page freshness
(`dashboardFreshness = dashboard.freshness`, `IntelligenceSurface.jsx:219`).

Backend date meanings (confirmed):
- `dashboard.freshness.data_through` = `latest_game_date` = latest **completed**
  game date (`board_freshness.py:37`). This is the completed-game workload basis.
- `tonight.reference_date` = `product_current_date()` = the **slate / pregame
  current day** (`tonight_intelligence_service.py:_resolve_reference_date`).
- `today (intelligence).reference_date` = the latest non-future
  completed-game-context date (the lead story's **completed** game date).
- `landscape.reference_date` defaults to `product_current_date()`
  (`game_context._default_reference_date`), but the picture view prefers
  `landscape.games.as_of_date` first.

## Tonight date semantics

`IntelligenceSurface.jsx:913`:
`dataThrough = firstTextValue(tonight.reference_date, freshness.data_through)`
→ rendered via `DataThroughStamp` as "Data through {tonight.reference_date}".
`tonight.reference_date = product_current_date()` = the **slate date** the Tonight
cards evaluate (schedule context + bullpen reads). It is **not** completed-game
data, **not** a workload data-through, **not** the snapshot generation date — it is
the pregame slate (a mix in spirit: schedule keyed on the slate date + bullpen
workload from completed games through an earlier date, surfaced under the slate
date). **Labeling it "Data through" is the core inaccuracy.**

## Today's Story date semantics

`IntelligenceSurface.jsx:601`:
`dataThrough = firstTextValue(intelligence.reference_date, freshness.data_through)`.
`intelligence.reference_date` is a **completed** game date (the lead story's game),
so "Data through" here is defensible — it is a real completed-game date, not a
slate. Mild nuance: it is the story's game date, not strictly the
bullpen-workload-through date, but both are completed-game dates, so user-confusion
risk is low. Recommend wording it consistently ("Bullpen data through …") for
parity with the other surfaces.

## Today's Bullpen Picture date semantics

`IntelligenceSurface.jsx:1017`:
`dataThrough = firstTextValue(landscape.games.as_of_date, landscape.reference_date,
freshness.data_through)`. In practice this resolves to the availability/completed
games date (Jun 26) and describes current availability — accurate. **Latent risk:**
`landscape.reference_date` defaults to `product_current_date()` (the slate), so if
`games.as_of_date` were absent the Picture could fall back to the slate date and
mislabel a slate as "Data through." Recommend pinning this surface to the
completed/availability date and never the bare slate.

## Sidebar freshness semantics

`Sidebar.jsx` `SidebarDataFreshnessCard` already separates **three** rows:
"Page checked" (client check time), "Latest data update" (`last_successful_sync`),
"Data through" (`data_through` = latest completed game date, Jun 26). Sourced from
`getSyncStatus` → `getSyncStatusView`. **This is the correct model** — it
distinguishes when the page was checked, when data last synced, and what
completed-game data it goes through. The only refinement is wording the last row
"Bullpen data through" for clarity.

## Current user-facing risk

- Same "Data through" label means **slate date (Jun 27)** on Tonight and
  **completed-game date (Jun 26)** everywhere else, shown together → users infer
  Jun 27 bullpen workload exists when it does not.
- The Tonight stamp implies the freshest data is on the forward-looking card,
  inverting reality (Tonight is a pregame projection over completed-game workload).
- Latent: Today's Bullpen Picture could fall back to the slate date if
  `games.as_of_date` is missing.

## Recommended language

Use **"Bullpen data through"** for the completed-game workload basis, and a
distinct **slate** label for the pregame date. Never label a
slate/`product_current_date` as "Data through".

- **Tonight**: show BOTH —
  - `Tonight slate: Jun 27` (from `tonight.reference_date`; not "Data through")
  - `Bullpen data through Jun 26` (from `dashboard.freshness.data_through`)
  - `Last synced 11:04 AM ET` (from `last_successful_sync`)
- **Today's Bullpen Picture**:
  - `Bullpen data through Jun 26` (completed/availability date; never the bare slate)
  - `Last synced 11:04 AM ET`
- **Today's Story**:
  - `Bullpen data through {completed game date}` (rename from "Data through" for parity)
  - `Last synced …`
- **Sidebar** (keep the three-row model; minor rename):
  - `Page checked 11:02 AM ET`
  - `Latest data update 11:04 AM ET`
  - `Bullpen data through Jun 26`

This lets a user understand: what slate Tonight is looking at, what completed-game
bullpen data the reads are based on, when it last synced, and whether anything is
stale/unavailable.

## Backend contract changes required

**None.** Both dates already exist in the payloads:
- slate date → `tonight.reference_date` (already returned).
- completed-game workload date → `dashboard.freshness.data_through` (already returned).
The fix is frontend label selection + a small shared-component label distinction.
Optional, deferred: if a per-surface "schedule_through" ever needs to differ from
`product_current_date`, that would be a backend addition — not needed now.

## Frontend implementation guidance for Codex

1. Stop routing `tonight.reference_date` through `DataThroughStamp`. Render it as a
   distinct slate label ("Tonight slate: {date}").
2. On the Tonight section, additionally render `Bullpen data through
   {dashboard.freshness.data_through}` and `Last synced {last_successful_sync}` from
   the already-fetched dashboard freshness.
3. Extend the shared freshness primitives so the distinction is reusable and
   honest: keep `DataThroughStamp` meaning **completed-game data only**, and add a
   small slate/schedule stamp (or a labeled variant) for the slate date — i.e.
   support `dataThrough` vs `slateDate`/`scheduleThrough` vs `lastSynced` as
   separate concepts.
4. Pin Today's Bullpen Picture to the completed/availability date; never fall back
   to the bare `product_current_date` slate.
5. Rename "Data through" → "Bullpen data through" across the operating surfaces and
   the sidebar for one consistent meaning.
6. Do not invent freshness, do not fake per-card freshness, do not show a slate
   date as completed-game data.

## Test guidance

- Tonight renders a slate label from `reference_date` and a separate "Bullpen data
  through" from `data_through`; assert it never renders the slate date under a
  "data through" label.
- When `data_through` (Jun 26) and slate (Jun 27) differ, both are shown distinctly
  and neither is conflated.
- Today's Bullpen Picture never displays the bare `product_current_date` slate as
  "data through" (fixture with `games.as_of_date` absent → falls back to the
  completed/availability date or omits, not the slate).
- Sidebar keeps the three distinct rows with correct sources.
- Stale/unavailable freshness still renders the degraded treatment and surfaces
  limitations; no internal vocabulary leaks.
- No undefined/null date leaks when any field is missing (omit the row, don't render
  "Invalid Date" / "undefined").

## Known risks

- **Migration parity**: the slate-vs-data-through split must be applied to every
  surface that currently uses `DataThroughStamp` on a slate-derived value (Tonight
  primarily; Today's Bullpen Picture's fallback) or the confusion persists on one
  surface.
- **Over-labeling**: adding a slate row everywhere (including completed-game
  surfaces that have no slate) would add noise — only Tonight needs the slate row.
- **Wording drift**: "Tonight slate" vs "Games scheduled" must be chosen once and
  used consistently; recommend "Tonight slate".
- **Latent landscape fallback**: leaving `landscape.reference_date` (= slate) as a
  fallback keeps a path to mislabeling; pin to the completed/availability date.

## Decision

Frontend-only label fix, no backend contract change. Stop labeling Tonight's
`reference_date` (the slate / `product_current_date`) as "Data through"; show it as
"Tonight slate: {date}" alongside "Bullpen data through {data_through}" and "Last
synced". Standardize "Bullpen data through" for the completed-game workload date
across surfaces and the sidebar; extend the shared freshness components to carry a
slate/schedule concept distinct from data-through; pin Today's Bullpen Picture to
the completed/availability date. The sidebar's three-row model is the template.

ready for Codex implementation: YES (frontend-only; no backend contract change).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
