# Recommendation Engine V1 Candidate Evaluation Layout Remediation

## Status

Recommendation Engine V1 Candidate Evaluation Layout Remediation is complete.

This fix targets the Candidate Evaluation article rendered inside the Bullpen
selected-pitcher detail surface.

It does not change backend behavior, API behavior, recommendation logic,
ranking behavior, selection behavior, prediction behavior, or Recommendation
Engine V1 certification.

## Root Cause

The Candidate Evaluation article previously shared the same responsive layout
path as wider Recommendation Engine surfaces.

That layout could become unsafe when embedded inside the selected-pitcher
detail card because viewport breakpoints do not describe the component's
actual available container width.

The affected embedded article renders:

```text
Recommendation Engine V1 Candidate Evaluation
```

The unsafe behavior came from allowing the embedded result layout to become a
two-column grid inside a constrained parent. The right-side trust/freshness
aside could then compete with the main status, category, explanation, and
limitation sections.

## Fix

The embedded Candidate Evaluation article is now explicitly marked as an
embedded recommendation panel and remains single-column.

The remediation adds:

- an explicit embedded panel class
- an explicit embedded layout class
- `max-width: 100%` and `min-width: 0` safeguards
- CSS rules that reserve two-column recommendation layouts for standalone
  panels only
- test guardrails preventing the embedded Candidate Evaluation panel from
  inheriting the standalone two-column grid

## Preserved Sections

The selected-pitcher Candidate Evaluation surface continues to render:

- Recommendation Status
- Eligible Categories
- Blocked Categories
- Explanation
- Limitation
- Trust And Freshness
- Refusal Reason
- Metadata

## Governance Compliance

The V1 frontend surface continues to preserve:

```text
ranking_applied === false
selection_made === false
```

The remediation does not introduce:

- ranking UI
- selection UI
- prediction UI
- best/preferred/recommended pitcher UI
- score-ordered UI
- winner-style UI
- backend route changes
- API contract changes

## V1 Logic Preservation

Recommendation Engine V1 candidate evaluation logic remains unchanged.

This phase changes layout only. It does not modify:

- V1 recommendation engine behavior
- V1 recommendation API semantics
- V1 candidate evaluation requests
- V1 response parsing
- V1 governance flags

## Test Coverage

Frontend guardrails are covered in:

- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

The test coverage verifies that the selected-pitcher Candidate Evaluation
surface renders required trust, freshness, category, explanation, limitation,
refusal, and metadata sections while keeping the embedded panel on the
single-column layout path.

## Phase 11 Readiness

Phase 11 mobile and accessibility validation may resume after this V1 layout
remediation.

Future Phase 11 work should validate both governed V2 dashboard rendering and
Bullpen selected-pitcher V1 Candidate Evaluation rendering across mobile,
tablet, desktop, keyboard, and assistive technology surfaces while preserving
trust, freshness, refusal, limitation, explanation, no-ranking, and
no-selection guarantees.
