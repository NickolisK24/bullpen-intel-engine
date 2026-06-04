# Dashboard Operational Readiness Consolidation

## Purpose

This pass consolidates the Dashboard's governed V2 Bullpen State and V3 Team Operations Bullpen Readiness surfaces into one compact Operational Readiness section. The goal is to keep the Dashboard focused on current operational state instead of presenting two large report-style readiness sections.

## What Changed

- Added a single Operational Readiness section that summarizes V2 bullpen state and V3 team readiness together.
- Replaced the separate always-visible V2 and V3 dashboard regions with one summary-first surface.
- Kept readiness status, workload stress, availability distribution, freshness state, and governance protection visible in the primary view.
- Added embedded detail rendering for the existing V2 and V3 panels so their evidence remains accessible without dominating the dashboard.
- Grouped Risk Distribution, Exploratory Fatigue Insight, High Fatigue Snapshot, and Pipeline Snapshot under an Operational Insights area.

## Details Preserved Behind Disclosure

The following remain available through dashboard detail controls:

- V2 trust metadata
- V2 freshness metadata
- V2 fail-closed and refusal details
- V2 inventory and neutral group evidence
- V3 readiness context details
- V3 constraint and coverage details
- V3 trust, freshness, refusal, fail-closed, route, and governance metadata
- Exploratory Fatigue-to-ERA insight details

No governance, certification, rollout, or evidence content was deleted.

## Governance Preservation

The Dashboard continues to display these invariants:

```text
ranking_applied === false
selection_made === false
```

This pass does not add:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

The consolidated section states that the output is team-level context only and that the user remains responsible for bullpen decisions.

## UX-Only Confirmation

This was a frontend UX consolidation only.

No backend behavior, API behavior, fatigue calculation, availability calculation, Recommendation Engine V2 behavior, Team Operations readiness behavior, trust/freshness logic, governance logic, certification meaning, or rollout meaning changed.

## Validation

Required frontend validation:

```text
cd frontend
npm test
npm run build
```

Repository validation:

```text
git diff --check
git diff --cached --check
```
