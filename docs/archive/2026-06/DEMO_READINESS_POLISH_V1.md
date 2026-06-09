# Demo Readiness Polish V1

Polish pass implementing the highest-impact items from the Post-Merge Trevor
Demo Readiness Audit. No new features, engines, analytics, recommendations, or
predictions — clarity and workflow only.

## Improvements made

### Priority 1 — Live vs Sample clarity

A single, consistent **data provenance** helper now drives every surface so a
first-time user instantly knows what they're looking at:

- `getDataProvenance(freshness)` returns one of:
  - **Live data · through `<date>`** — only when a successful sync makes the data
    current (`is_current` and `sync_status` success/ok).
  - **Sample data · through `<date>`** — historical snapshot (the current state of
    the dataset).
  - **No data loaded.**
- "Through `<date>`" now always carries the same plain hint: *"the most recent
  game in the dataset."*

Applied to: the **dashboard hero pill**, the **bullpen board freshness banner**,
the **compare freshness chips** (both teams), and the **Data & Trust** freshness
section. The dashboard season banner ("Live — Season" / "End-of-Season Snapshot")
is unchanged and now reinforced by the explicit provenance label.

Rationale: the audit named this the most important remaining issue — "is this
live or a sample?" was the first question a pro would ask. Wording is honest:
"Live" appears only when the system state truly supports it.

### Priority 2 — Board → Pitcher Detail

Board pitcher cards now have a **"View details →"** affordance that opens the
**existing** `PitcherDetail` panel (fatigue trend, recent logs) as a side panel
on the standalone board. No second pitcher-detail screen was created.

- Wiring is a single optional `onSelectPitcher` prop on `BullpenBoardView`;
  `TonightsBullpenBoard` supplies it and renders `PitcherDetail`.
- The comparison view intentionally does **not** wire it (keeps the two-board
  comparison focused); its cards simply omit the button.

Rationale: the audit flagged a weak path from "I like this arm on the board" to
its history. Now the move from Bullpen Board → Pitcher Detail is natural.

### Priority 3 — Fatigue score legend

The board now states the scale once, plainly: *"Fatigue score: higher = heavier
recent workload."* Each card's fatigue value also carries a tooltip
("0–100 · higher = heavier recent workload"). No thresholds or implementation
detail are exposed (the full risk tiers live on Methodology).

### Priority 4 — Tab workflow

Bullpen tab labels clarified so the four tabs read as a hierarchy and the two
legacy reference tables stop looking like a second comparison surface:

- `Pitchers` → **All Pitchers** (the full searchable fatigue table)
- `Team Summary` → **All Teams** (the 30-team table)
- `Tonight's Board` and `Compare Bullpens` unchanged (the flagship surfaces).

Ordering and grouping were left as-is — the order already leads with the
flagships, and folding the tables under a single sub-affordance would be a larger
redesign, deferred.

### Minor

- Methodology subtitle "How every number on the dashboard was computed" → "How
  every fatigue and availability number is computed" (the product is no longer
  dashboard-only).

## UX walkthrough (post-polish)

Dashboard → Bullpen Board → Pitcher Detail → Compare → Data & Trust:

1. **Dashboard** — provenance pill states Live/Sample + through-date up front.
2. **Bullpen Board** — provenance banner + fatigue legend; cards open detail.
3. **Pitcher Detail** — the existing panel, reached in one click from the board.
4. **Compare** — both teams' freshness now reads Live/Sample consistently.
5. **Data & Trust** — leads with a provenance chip and the through-date meaning,
   then the full freshness/governance depth.

Remaining friction observed (low-risk, deferred): the comparison renders two full
boards (long scroll); a "feature a team" selector on the dashboard would let the
league view drill to one pen inline; on sample data the league health reads
"manageable" (low-drama) — a data/seed concern, not UX.

## Tests

- `frontend/tests/demoReadinessPolish.test.mjs` — provenance (live/sample/none),
  board banner provenance, dashboard pill provenance, View-details affordance
  (present with handler, absent without), fatigue legend, clarified tab labels.
- Existing suites unchanged and green. One backend field (`sync_status`) was
  added to the comparison freshness summary so compare provenance is accurate;
  existing comparison tests remain green.

State: backend 471 pass, frontend 199 pass, build clean.

## Improvements intentionally deferred

- Tab consolidation (folding All Pitchers / All Teams under one affordance) —
  larger redesign than this polish scope.
- Board→detail in the **comparison** view — kept focused on the two-board compare.
- Dashboard "feature a team" selector — useful but a new interaction, not polish.
- Richer demo seed data so league health isn't always "manageable" — data work.

## Remaining open demo concerns

- The dataset is a historical sample; provenance now says so, but a viewer
  expecting full live 30-team coverage still needs that context.
- Comparison page length (two full boards) can feel long in a live demo.
- Pipeline/Prospects remains in the nav as a prototype distraction for a
  bullpen-focused demo.
