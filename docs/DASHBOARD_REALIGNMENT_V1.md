# Dashboard Realignment — V1

## Rationale

The Trevor Demo Readiness Audit found that the strongest product area is now the
**bullpen workflow** (Tonight's Board, Team Context, Compare, usage roles), but
the **landing Dashboard still led with operations/governance language and
panels** — "Operational Readiness," "Bullpen State," "Trust Status," "Bullpen
Intelligence." A baseball person landed on what looked like an internal
monitoring console instead of a bullpen tool.

This realignment makes the Dashboard about **baseball**, and moves the trust /
governance / diagnostic depth to a dedicated **Data & Trust** page. Trust still
supports the product; it no longer *is* the first impression.

## Before / after goals

| | Before | After |
| --- | --- | --- |
| First words | "Operational Readiness Dashboard" / "governed recommendation context… team operations readiness" | "Tonight's Bullpen Overview" — availability, workload, usage |
| Landing content | V2 recommendation state, team-ops readiness, V5 observations, risk diagnostics | Snapshot · Health · Usage Roles · Quick Actions |
| Trust depth | Exposed inline on the landing | Summarized on the landing, full depth on **Data & Trust** |
| Feel | System Operations | Baseball Operations |

## Information hierarchy (new Dashboard)

1. **Hero** — "Tonight's Bullpen Overview" with a season banner, a compact
   freshness pill (data-through date, current/stale, confidence), and a link to
   **Data & Trust details →**.
2. **Bullpen Snapshot** — five availability count cards (Available Tonight,
   Monitor, Limited, Avoid, Unavailable).
3. **Bullpen Health** — the Team Context Layer (V2) statement, its *Why?*, and
   confidence — visible immediately.
4. **Usage Roles** — high-level role composition counts (Late / Setup / Middle /
   Long / Low / Insufficient). Counts only — no per-pitcher detail.
5. **Quick Actions** — Tonight's Bullpen Board, Compare Bullpens, Pitcher
   Details, Methodology (deep-linked into the right Bullpen tab).

All of it is league-wide, aggregated across tracked bullpens, and reuses
existing systems — no new availability/health/role logic was written.

## Backend

One lightweight endpoint, **`GET /api/bullpen/dashboard`**, that *aggregates
existing outputs* (no parallel evaluation system):

- Availability Engine V1 → availability summary counts.
- V2 Team Context Layer (`build_team_context`) → league-wide bullpen health.
- Usage-role classifier (`classify_usage_role`) → role-composition counts.
- Shared freshness block → data-through / confidence for the hero.

`ranking_applied` / `selection_made` stay `false`; no scores or rankings.

## Trust relocation strategy

A new **Data & Trust** page (`/trust`, nav item 🛡) hosts the depth that used to
crowd the landing — **nothing was deleted or reduced**, only moved:

- Freshness & sync detail (shared `SyncStatusContent`).
- Availability confidence breakdown (full `AvailabilityDashboardSummary`).
- Governance protections & operational context (`OperationalReadinessSection`:
  V2 bullpen state + team-operations readiness).
- Bullpen intelligence observations (V5 `BullpenIntelligencePanel`).
- Exploratory fatigue insight (the correlation study).

The Dashboard keeps the **summary** (freshness pill + health confidence) and
**links** to the page. Depth lives behind intentional navigation.

The old Dashboard's High-Fatigue Snapshot and Pipeline Snapshot were not
duplicated here — that detail already lives on the **Bullpen** (Pitchers tab) and
**Pipeline** pages respectively, reachable from Quick Actions and the nav.

## Navigation

- Added **Data & Trust** (`/trust`) to the sidebar.
- **Compare** remains a Bullpen tab and a Quick Action (deep-linked via
  `/bullpen?view=compare`) rather than a separate nav item, to avoid two nav
  entries resolving to the same `/bullpen` path (which would both render active).
- Bullpen now reads a `?view=` query param so Quick Actions land on the intended
  tab (board / compare / pitchers).

## Language cleanup

Removed from the landing: "Operational Readiness Dashboard," "governed
recommendation context," "team operations readiness," "Operational Insights,"
"Operational readiness partially unavailable." Replaced with: bullpen,
availability, workload, usage, health, freshness, confidence. The governance
vocabulary still exists — on the Data & Trust page, where it belongs.

## Constraint honored

No governance or trust system was deleted, and transparency was not reduced.
Summary information stays visible on the Dashboard; depth moved to Data & Trust.

## Surface map

| Layer | File |
| --- | --- |
| Dashboard endpoint | `GET /api/bullpen/dashboard` (`backend/api/bullpen.py`) |
| Role-order constant | `backend/services/pitcher_role.py` (`ROLE_KEYS`) |
| API client | `getBullpenDashboard` (`frontend/src/utils/api.js`) |
| Dashboard | `frontend/src/components/dashboard/Dashboard.jsx` (`DashboardView`) |
| Roles-summary helper | `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` (`getRolesSummaryView`) |
| Data & Trust page | `frontend/src/components/trust/DataTrust.jsx` |
| Routing / nav | `frontend/src/App.jsx`, `frontend/src/components/Sidebar.jsx` |
| Bullpen deep-link | `frontend/src/components/bullpen/Bullpen.jsx` (`?view=`) |

## Known concerns

- The Dashboard is **league-wide aggregate**; a single team's health reads best
  on the Bullpen Board itself. A future "feature a team" selector on the
  Dashboard could add per-team focus.
- On sparse sample data, the league-wide health usually reads "manageable" —
  accurate, but low-drama until richer/live data is loaded.
