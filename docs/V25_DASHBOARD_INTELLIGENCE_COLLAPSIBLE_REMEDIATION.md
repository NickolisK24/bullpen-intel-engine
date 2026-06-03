# Dashboard V2 Intelligence Collapsible Remediation

## Status

Complete.

This is a corrective production UX defect fix for the Dashboard page under
`V2 Bullpen Intelligence`. It is not a new roadmap phase and does not expand
the Recommendation Engine V2 scope.

The remediation is frontend presentation-only. It does not change backend
behavior, API contracts, recommendation logic, trust logic, freshness logic,
refusal logic, ranking behavior, selection behavior, prediction behavior, or
fatigue formulas.

## Defect Found

BaseballOS V2.5 Phase 14 and Phase 15 reduced the first-pass V2 Dashboard
inventory and intelligence footprint, but the live Dashboard still had
high-volume structures that were not fully governed by member-specific or
detail-specific expansion controls.

The most important live payload characteristics were:

- inventory summaries with production-volume membership behind categories
- ten neutral candidate group summaries, including 704-member groups
- structured Team Context readiness and stress indicator objects
- long limitation and explanation arrays
- refusal and fail-closed metadata that must remain visible

The defect was presentation density, not engine correctness.

## Root Cause

The Phase 14 and Phase 15 rendering changes optimized the outer sections, but
some expanded cards still exposed several internal structures at once:

- inventory detail expansion could reveal membership, evidence, freshness, and
  limitations together
- candidate group detail expansion could reveal members, eligibility basis,
  explanations, limitations, refusal metadata, and freshness together
- Team Context readiness and stress indicators only handled array-shaped
  payloads, so structured live indicator objects were not summarized

The live Dashboard needed nested summary-first controls for each high-volume
detail family, not only a single outer control.

## Sections Audited

The Dashboard V2 Bullpen Intelligence panel was audited end to end:

| Section | Finding | Remediation |
|---------|---------|-------------|
| Header and contract state | Good summary UX | No change |
| Fail-Closed alert | Good summary UX | No change |
| State | Good summary UX | No change |
| Governance | Good summary UX | No change |
| Trust | Good summary UX | No change |
| Freshness | Good summary UX | No change |
| Inventory | Needed nested detail controls | Added member, evidence, and limitation detail disclosure |
| Team Context distributions | Already collapsible | Kept summary-first distribution controls |
| Team Context indicators | Structured objects rendered as unavailable | Added structured summary and indicator disclosure |
| Neutral Candidate Groups | Needed nested detail controls | Added member, eligibility, explanation, limitation, and refusal disclosure |
| Limitations | Summary-first with detail control | Validated with live long-list payload |
| Explanations | Summary-first with detail control | Validated with live long-list payload |
| Refusal | Summary-first and visible | Preserved visible single-entry refusal metadata |
| Contract unavailable state | Good summary UX | No change |

## Sections Fixed

Inventory details now disclose progressively:

- outer category summary remains default
- `View Details` opens category detail summaries
- `View Members` reveals full membership
- `View Evidence` reveals evidence entries
- `View Limitations` reveals limitation entries when present

Neutral Candidate Group details now disclose progressively:

- outer group summary remains default
- `View Details` opens group detail summaries
- `View Members` reveals full group membership
- `View Eligibility` reveals eligibility basis
- `View Explanations` reveals explanation entries
- `View Limitations` reveals limitation entries
- `View Refusal` reveals refusal metadata
- group freshness rows remain visible inside the expanded detail view

Team Context now supports live structured readiness and stress objects:

- count-object summaries render as indicator summaries
- full structured indicator rows remain hidden behind `View Indicators`
- availability and workload distributions remain hidden behind
  `View Distribution`

## Transparency Preserved

No intelligence was removed.

Users can still inspect:

- full inventory members
- full candidate group members
- evidence entries
- eligibility basis
- Team Context distribution rows
- Team Context readiness and stress indicators
- limitations
- explanations
- refusal metadata
- trust metadata
- freshness metadata
- fail-closed state

The corrected behavior is:

```text
summary first
expand details on demand
expand members on demand
```

not:

```text
hide information permanently
```

## Governance Preserved

The V2 guarantees remain:

```text
ranking_applied === false
selection_made === false
```

This remediation does not introduce:

- ranking UI
- selection UI
- prediction UI
- preferred pitcher UI
- final pitcher choice UI
- quality ordering
- automated decision behavior

All controls use neutral inspection language such as `View Details`,
`Hide Details`, `View Members`, and `Hide Members`.

## Manual Dashboard Validation

Manual validation used the live Dashboard route with the local frontend dev
server on port `5173` and the local backend on port `5000`.

Live V2 payload characteristics observed:

- 704 total active pitchers
- six inventory summary categories
- ten neutral candidate group summaries
- two Team Context distribution controls
- two Team Context indicator controls
- nine limitation entries
- three explanation entries
- one refusal entry

Default Dashboard V2 panel validation:

- no pitcher names were rendered by default
- inventory categories showed counts and metadata with `View Details`
- candidate groups showed counts and metadata with `View Details`
- Team Context distributions showed counts with `View Distribution`
- structured readiness and stress indicators showed counts with
  `View Indicators`
- limitations and explanations showed counts with `View Details`
- fail-closed and refusal metadata remained visible

Expansion validation:

- opening inventory details did not reveal pitcher names immediately
- `View Members` revealed full inventory membership
- `Hide Members` hid inventory membership again
- opening candidate group details did not reveal pitcher names immediately
- `View Members` revealed full candidate membership
- `Hide Members` hid candidate membership again
- limitation details expanded and collapsed correctly

Mobile validation:

- mobile default V2 panel text remained summary-first
- no pitcher names were rendered by default
- inventory, candidate group, distribution, indicator, limitation, and
  explanation controls remained available
- expanded sections may still be long, but only after explicit user action

## Test Coverage

Frontend coverage was updated in:

- `frontend/tests/recommendationV2Rendering.test.mjs`

Coverage now verifies:

- high-volume inventory members remain collapsed by default
- high-volume candidate group members remain collapsed by default
- outer detail expansion does not dump member names
- nested member expansion reveals full membership
- nested eligibility, explanation, limitation, and refusal detail remains
  inspectable
- structured Team Context indicator objects summarize without dumping all rows
- limitation, explanation, and refusal visibility remains preserved
- no prohibited ranking, selection, or prediction UI appears

Validation:

```text
npm test
```

Result:

```text
78 passed, 0 failed
```

Backend tests were not required because no backend files were touched.

## Remaining UX Risks

Future V2 contract additions could introduce new high-volume nested structures.
Any future Dashboard V2 intelligence surface should be added with:

- count-first summary
- collapsed details by default
- explicit expansion controls
- trust, freshness, refusal, and fail-closed visibility
- regression tests proving high-volume values are not rendered by default

## Recommended Next Milestone

Add a recurring V2 Dashboard UX regression audit that renders the live
production-volume fixture and fails if member names, large arrays, or raw
internal structures appear in the default collapsed panel.
