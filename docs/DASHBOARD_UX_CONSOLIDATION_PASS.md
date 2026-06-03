# Dashboard UX Consolidation Pass

## Purpose

This pass refactors the BaseballOS Dashboard from a long certification and audit-style page into a denser operational readiness dashboard. The work keeps the current product capabilities intact while improving hierarchy, reducing repeated messaging, and moving secondary evidence behind progressive disclosure.

## Scope

Included:

- Dashboard layout density improvements.
- Summary-first rendering for operational readiness surfaces.
- Progressive disclosure for secondary evidence, metadata, and detailed inventories.
- Focused frontend tests for compact rendering and governance visibility.

Excluded:

- Backend behavior changes.
- API contract changes.
- Fatigue or availability calculation changes.
- Recommendation Engine V2 behavior changes.
- Team Operations Bullpen Readiness behavior changes.
- Governance logic changes.

## Major Changes Made

- Reworked the dashboard header into a compact operational status area with sync state shown in the first viewport.
- Reduced oversized page spacing, repeated section gaps, and audit-style vertical separation.
- Converted Availability Dashboard evidence into a compact summary with expandable details.
- Converted Recommendation Engine V2 evidence and metadata into a compact panel with governance flags still visible by default.
- Converted Team Operations Bullpen Readiness into a summary-first operational snapshot with workload, availability, freshness, and governance surfaced immediately.
- Moved exploratory Fatigue-to-ERA insight content behind a collapsed dashboard disclosure by default.
- Tightened embedded fatigue insight spacing when rendered inside the dashboard.

## Sections Consolidated

- Sync status is now displayed in the top dashboard status area instead of a separate full-width block below the hero.
- Availability confidence, data-state, limited-data notes, and source notes are grouped as secondary evidence.
- Recommendation Engine V2 trust, freshness, inventory, team context, candidate groups, explanations, limitations, and refusal metadata are grouped as evidence and metadata.
- Team Operations detailed count grids are summarized into a smaller operational snapshot while preserving expandable details.

## Sections Collapsed

Collapsed by default:

- Availability evidence details.
- Recommendation Engine V2 evidence and metadata.
- Exploratory Fatigue-to-ERA insight.

Expandable in-place:

- Team Operations Bullpen Readiness context details.
- Team Operations evidence, metadata, and governance details.

## Page-Length Reduction Approach

The page-length reduction comes from:

- Smaller dashboard shell padding.
- Smaller hero typography and tighter status presentation.
- Removal of repeated standalone status sections.
- Summary cards that expose key operational answers first.
- Collapsible metadata and evidence sections for audit-oriented details.
- Compact embedded rendering for secondary insight content.

The first viewport is now focused on the current operational state: sync status, overall counts, risk distribution, availability state, V2 bullpen state, and Team Operations readiness summary.

## Governance Preservation

Governance visibility remains concise and explicit. The following invariants remain visible and unchanged:

```text
ranking_applied === false
selection_made === false
```

This pass does not add:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- pitcher-level advice
- matchup advice
- hidden priority ordering

The Dashboard continues to present readiness as operational context, not as a decision instruction.

## Validation

Frontend validation:

```text
cd frontend
npm test
```

Result:

```text
104 tests passed
```

Backend tests were not required because this pass did not modify backend code, backend contracts, or runtime data behavior.

## Screenshot Notes

Before screenshots were not retained for this pass because the branch was already in-progress when visual verification was attempted. The local frontend dev server responded successfully at `http://127.0.0.1:5173`, but browser screenshot capture was not practical in this environment because the local browser controller failed to attach during setup. After-state browser review should be captured during review if a live backend or representative mock data environment is available.
