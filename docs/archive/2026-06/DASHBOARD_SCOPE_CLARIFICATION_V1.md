# Dashboard Scope Clarification — V1

## Purpose

A scope-clarification and copy-polish pass. The Dashboard Realignment V1 made the
landing baseball-focused, but a first-time user could still briefly wonder
*"which bullpen?"* when reading "Bullpen Health" or "Several relievers require
monitoring." This pass makes the scope explicit:

- **Dashboard = league-wide.** *"What is happening across tracked MLB bullpens?"*
- **Bullpen = team-specific.** *"What does this specific bullpen look like tonight?"*
- **Compare = team vs team.** *"How do two bullpens compare?"*

No features, engines, analytics, role logic, comparison logic, governance, or
trust systems were added or changed — copy and labels only.

## Why both views exist

- The **Dashboard** answers the broad question first: across every tracked MLB
  bullpen tonight, how many arms are available, how stressed are pens overall,
  and what usage mix exists. It is an orientation layer.
- The **Bullpen** workflow answers the specific question: for one team, who is
  available, how stressed is that pen, who compares, and what each arm's usage
  looks like. It is the working layer.

Keeping them separate is intentional. The dashboard is the league lens; the
bullpen section is the team lens. Neither should absorb the other.

## Scope audit — findings

| Surface | Before | Ambiguity | After |
| --- | --- | --- | --- |
| Hero eyebrow | "Tonight's Bullpen Overview" | Scope unstated | "League-Wide Bullpen Overview" + chip "League-Wide · All tracked MLB bullpens" |
| Hero subtitle | "across tracked teams" | Soft | "across all tracked MLB bullpens tonight … Open Bullpen for a single team's pen." |
| Snapshot | "Bullpen Snapshot" / "across tracked bullpens" | Could read as one pen | "League-Wide Bullpen Snapshot" / "across all tracked MLB bullpens" |
| Health | "Bullpen Health" + singular statement | Reads as a specific pen | "League-Wide Bullpen Health" + subtitle "not a single team" + inline "League-Wide ·" on the statement |
| Usage Roles | "Usage Roles" / "across tracked bullpens" | Mild | "League-Wide Usage Roles" / "across all tracked MLB bullpens — not a single team" |
| Quick Actions | descriptions scope-neutral | Mild | subtitle "drill into a single team…"; cards say "One team's bullpen", "Two teams", "One pitcher's…" |
| Bullpen section | "Who's available tonight…" | Didn't contrast with dashboard | "Team-specific bullpen analysis — …a team's pen" |

The shared Team Context Layer health statements (e.g. "Several relievers require
monitoring.") were **not** reworded — they are reused verbatim by the
team-specific board, where they correctly describe one pen. Instead, the
**dashboard frames** them as league-wide via the section title, subtitle, and an
inline "League-Wide ·" qualifier. Same words, unambiguous context.

## Information hierarchy (reinforced, not changed)

```
Dashboard      League-wide MLB bullpen overview     "what's happening across MLB?"
  → Bullpen    One team's bullpen tonight           "what does this pen look like?"
  → Compare    Two teams side-by-side               "how do two pens compare?"
  → Pitcher    One pitcher's fatigue & workload     "what about this arm?"
  → Methodology  How the numbers are computed
  → Data & Trust  Freshness, confidence, governance, evidence
```

Quick Actions and the hero copy now make this league → team → pitcher drill-down
explicit.

## Changes made

Copy/label only, all in the frontend:

- `frontend/src/components/dashboard/Dashboard.jsx` — hero eyebrow, scope chip,
  hero subtitle, and the four section titles/subtitles ("League-Wide …"), an
  inline "League-Wide ·" qualifier on the health statement, a Quick Actions
  subtitle, and team/pitcher-scoped action descriptions.
- `frontend/src/components/bullpen/Bullpen.jsx` — subtitle now reads
  "Team-specific bullpen analysis …" to contrast with the league dashboard.

## Changes intentionally not made

- **No conversion of the Dashboard to a team-specific view** and no team
  selector added — the dashboard stays league-wide by design.
- **No backend changes.** The dashboard endpoint already aggregates across all
  tracked pitchers; only presentation copy needed clarifying.
- **Shared Team Context Layer statements left verbatim** so the team board keeps
  its correct per-pen wording.
- **Navigation labels left as-is.** "Dashboard" vs "Bullpen" already reads as
  overview vs workflow, and the hero now states league-wide scope. Renaming
  "Dashboard" to "MLB Overview" was considered but rejected — it risks implying
  full, live 30-team coverage, whereas the data is a tracked sample.
- **No "Compare"/"Data & Trust" added as separate items beyond what exists** —
  Compare is a Bullpen tab + Quick Action; Data & Trust is already a nav item and
  hero link.

## Remaining ambiguities

- The dashboard is a tracked **sample** of MLB, not all 30 live bullpens. Copy
  says "tracked MLB bullpens" to stay honest, but a viewer expecting full live
  coverage may still need the data-through/freshness context (shown in the hero
  pill and on Data & Trust).
- "League-Wide" is repeated across sections for clarity; if it ever reads as
  heavy, a single hero-level scope banner could replace the per-section prefixes.
