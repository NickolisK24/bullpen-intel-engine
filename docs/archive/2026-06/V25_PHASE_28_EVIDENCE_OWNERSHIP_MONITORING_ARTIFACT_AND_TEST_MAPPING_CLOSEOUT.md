# BaseballOS V2.5 Phase 28 - Evidence Ownership, Monitoring Artifact Format, and Test Mapping Closeout

## Decision

Status:

```text
PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT_COMPLETE
```

BaseballOS V2.5 Phase 28 closes the remaining production evidence-quality gaps
identified in Phase 27 where current documentation and tests support closeout.

Phase 28 focuses on:

- packet-level retention owners
- evidence retention cadence
- monitoring artifact format
- exact production governance test mapping
- remaining evidence that still cannot be mapped without future runtime,
  monitoring, or continuous-integration changes

Phase 28 is documentation-only. It does not change runtime behavior.

## Phase Purpose

The purpose of Phase 28 is to convert the remaining Phase 27 evidence-quality
gaps into a closeout-ready stewardship record.

The guiding question is:

```text
Who owns the evidence, how often is it retained, what does the monitoring
artifact look like, and which tests prove the production governance claims?
```

Phase 28 does not fabricate evidence. Where an owner is assigned by this
governance record, that assignment is marked as a Phase 28 packet-level
assignment. Where a test, assertion, or artifact does not exist, the gap remains
explicit.

## Scope

In scope:

- Dashboard V2 Bullpen Intelligence
- `/api/recommendations/v2/bullpen-state`
- evidence ownership model
- packet-level owner assignment
- evidence retention cadence
- evidence retention responsibility matrix
- monitoring artifact format
- monitoring artifact retention requirements
- exact test-file, test-name, and assertion-group mapping
- Dashboard V2 runbook evidence assessment
- API-to-frontend accessibility field traceability assessment
- governance closeout readiness assessment

Out of scope:

- backend recommendation logic changes
- fatigue formula changes
- API contract changes
- frontend runtime behavior changes
- ranking behavior
- selection behavior
- prediction behavior
- best option behavior
- preferred option behavior
- recommended option behavior
- prototype promotion
- production scope expansion
- new monitoring implementation
- new test implementation

## Relationship To Phases 21-27

Phase relationship:

| Phase | Governance Layer | Phase 28 Relationship |
|-------|------------------|-----------------------|
| Phase 21 | Lifecycle enforcement checklist | Phase 28 preserves checklist enforcement by closing production evidence ownership and test mapping gaps. |
| Phase 22 | Lifecycle review log and adoption audit | Phase 28 gives future review log entries concrete evidence owners, cadence, and artifact requirements. |
| Phase 23 | Evidence backfill and owner assignment plan | Phase 28 uses Phase 23 maintainer and owning-area assignments as the basis for packet-level retention ownership. |
| Phase 24 | Evidence packet template and initial backfill | Phase 28 completes production packet ownership, retention, and monitoring artifact format expectations. |
| Phase 25 | Evidence packet review and backfill execution | Phase 28 closes production packet review gaps that were classified as stewardship work. |
| Phase 26 | Evidence citation backfill and stewardship review | Phase 28 builds on production citation stewardship by assigning retention responsibility. |
| Phase 27 | Section-level citation map | Phase 28 closes the remaining owner, monitoring, and exact test mapping gaps where current tests support mapping. |

Phase 28 does not reopen lifecycle classification, promotion, deprecation, or
removal decisions.

## Evidence Ownership Model

Evidence ownership uses four roles:

| Role | Responsibility |
|------|----------------|
| Maintainer of record | Owns final governance decision, closeout acceptance, and boundary preservation. |
| Owning area | Owns the product or technical surface category. |
| Evidence collection owner | Maintains the evidence packet, test mapping, citation updates, and missing-evidence inventory. |
| Retention owner | Ensures retained evidence remains available, dated, and linked from lifecycle governance records. |

Phase 23 and Phase 24 already identify Nikko as the maintainer of record for
the production V2 surfaces. Phase 28 assigns packet-level retention ownership
for the current certified production evidence packets.

## Packet-Level Owner Assignment

Production packet assignments:

| Surface | Maintainer Of Record | Owning Area | Evidence Collection Owner | Packet-Level Retention Owner | Assignment Status |
|---------|----------------------|-------------|---------------------------|------------------------------|-------------------|
| Dashboard V2 Bullpen Intelligence | Nikko | Recommendation governance and frontend governance | Frontend governance | Documentation governance under Nikko | Assigned in Phase 28 |
| `/api/recommendations/v2/bullpen-state` | Nikko | Recommendation governance and backend governance | Backend governance | Documentation governance under Nikko | Assigned in Phase 28 |

Assignment boundaries:

- The assignments apply to evidence stewardship only.
- The assignments do not authorize runtime behavior changes.
- The assignments do not authorize new production scope.
- The assignments do not change code ownership.
- Future lifecycle movement must still use the Phase 21 checklist and Phase 22
  review log.

## Evidence Retention Cadence

Production evidence retention cadence:

| Trigger | Required Action | Owner |
|---------|-----------------|-------|
| Each production lifecycle review | Refresh evidence packet status, citation status, test mapping, and missing-evidence inventory. | Evidence collection owner |
| Each certified production behavior change proposal | Re-run governance review before implementation approval. | Maintainer of record |
| Each certification, rollout, or monitoring review | Link new source document sections from the packet. | Retention owner |
| Each backend or frontend test rename affecting mapped evidence | Update exact test mapping within the packet. | Evidence collection owner |
| Monthly while V2.5 governance closeout remains active | Confirm retained documents and missing-evidence inventory still exist. | Retention owner |
| Before product capability planning resumes from the V2.5 governance track | Confirm closeout readiness and remaining operational risks. | Maintainer of record |

Cadence classification:

```text
CURRENT_CADENCE = monthly_during_active_closeout_and_before_lifecycle_movement
```

## Evidence Retention Responsibility Matrix

| Evidence Area | Dashboard V2 Bullpen Intelligence Owner | `/api/recommendations/v2/bullpen-state` Owner | Retention Requirement | Status |
|---------------|------------------------------------------|-----------------------------------------------|----------------------|--------|
| Certification evidence | Frontend governance | Backend governance | Retain formal certification sections and update packet citations if superseded. | Assigned |
| Rollout evidence | Frontend governance | Backend governance | Retain Phase 16 rollout scope, recommendation, and boundary sections. | Assigned |
| Post-rollout monitoring evidence | Frontend governance | Backend governance | Retain Phase 17 monitoring expectation sections and future monitoring artifacts. | Assigned; artifact pending |
| Governance boundary evidence | Recommendation governance | Recommendation governance | Preserve ranking, selection, prediction, and decision-language boundary evidence. | Assigned |
| Test evidence | Frontend governance | Backend governance | Retain exact test file, test name, and assertion-group mapping. | Assigned |
| Accessibility evidence | Frontend governance | Backend governance for API-to-frontend field traceability | Retain Dashboard accessibility anchors and API field-to-render mapping. | Partially assigned; field traceability partial |
| Evidence packet retention | Documentation governance under Nikko | Documentation governance under Nikko | Keep packet records in `docs/` and update them when evidence is added, renamed, superseded, or invalidated. | Assigned |

## Monitoring Artifact Format

Future production monitoring artifacts should use a retained Markdown or
structured text record with this format:

```text
Artifact ID:
Artifact Date:
Reviewer:
Surface:
Lifecycle Tier:
Evidence Packet:
Source Commit:
Validation Window:

Production Scope:
- Dashboard V2 Bullpen Intelligence:
- /api/recommendations/v2/bullpen-state:

Governance Boundary Check:
- ranking_applied === false:
- selection_made === false:
- no ranking behavior:
- no selection behavior:
- no prediction behavior:
- no best/preferred/recommended behavior:

API Contract Check:
- endpoint:
- response status:
- trust metadata present:
- freshness metadata present:
- refusal metadata present:
- fail-closed metadata present:
- forbidden output fields absent:

Dashboard Rendering Check:
- V2 panel renders:
- trust metadata visible:
- freshness metadata visible:
- refusal/fail-closed state visible:
- accessibility anchors present:
- prohibited decision language absent:

Monitoring Observations:
- endpoint latency:
- error rate:
- fail-closed/refusal count:
- stale or missing data count:
- warning count:
- user-facing incident count:

Validation Commands:
- backend tests:
- frontend tests:
- repository checks:

Decision:
- accepted:
- follow-up required:
- next review date:
```

The artifact format is defined in Phase 28, but no dated monitoring artifact is
created by this phase.

## Monitoring Artifact Retention Requirements

Monitoring artifact retention requirements:

- retain the artifact under `docs/` or a future governed monitoring evidence
  path
- include the source commit reviewed
- include the validation commands used
- preserve the production surface names
- preserve governance boundary confirmations
- preserve observed or explicitly unavailable monitoring metrics
- distinguish test validation from production telemetry
- link the artifact from the current lifecycle evidence packet
- keep failed or degraded monitoring records rather than overwriting them

Current monitoring retention status:

| Requirement | Current Status |
|-------------|----------------|
| Artifact format defined | Complete in Phase 28 |
| Retention owner assigned | Complete in Phase 28 |
| First dated monitoring artifact retained | Missing |
| Runtime telemetry feed available for artifact population | Missing |
| Continuous-integration artifact publication available | Missing |

## Test Mapping Methodology

Test mapping uses this method:

1. Identify the production evidence claim.
2. Locate the exact test file that exercises the claim.
3. Record the exact test name where available.
4. Record the assertion group rather than copying every assertion.
5. Mark evidence as partial when the test covers only part of the claim.
6. Mark evidence as missing when no exact test exists.
7. Avoid claiming coverage from a broad test suite if a direct assertion is not
   present.

Mapping quality levels:

| Level | Meaning |
|-------|---------|
| Exact | File, test name, and assertion group are identified. |
| Partial | File and test name exist, but assertion coverage is incomplete for the packet claim. |
| Suite-Level | File or suite category exists, but exact test mapping is not available. |
| Missing | No current test evidence found. |

## Exact Test-File/Test-Name/Assertion Mapping Where Available

Backend exact mappings for `/api/recommendations/v2/bullpen-state`:

| Evidence Claim | Test File | Exact Test Name | Assertion Group | Mapping |
|----------------|-----------|-----------------|-----------------|---------|
| Successful endpoint response matches certified contract shape. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_successful_v2_api_response_matches_contract_shape` | HTTP 200, `scope`, confidence/data state, freshness, limitations, explanations, empty refusal list, `fail_closed.state`, bullpen state, inventory, candidate groups, team context, `ranking_applied === false`, `selection_made === false`, trust metadata governance checks. | Exact |
| Candidate groups preserve neutral ordering rather than ranking. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_candidate_groups_preserve_neutral_ordering` | `ordering` suffix `_non_ranking`, input order preserved, V2 governance helper passes. | Exact |
| Forbidden ranking, selection, and prediction fields are absent. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_response_contains_no_forbidden_ranking_selection_or_prediction_fields` | Forbidden output keys are absent; `ranked_candidates` absent; V2 governance helper passes. | Exact |
| Public route avoids full internal context serialization. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_v2_route_avoids_full_internal_context_serialization` | Public API uses lean serialization, keeps `ranking_applied === false`, `selection_made === false`, and candidate groups. | Exact |
| Missing evidence returns fail-closed API response. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_missing_evidence_returns_fail_closed_api_response` | `bullpen_state` withheld, fail-closed state and critical failure set, `missing_inputs` reason, freshness warning, limitation/explanation/refusal metadata, governance helper passes. | Exact |
| Stale evidence returns explicit refusal metadata. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_stale_evidence_returns_explicit_refusal_metadata` | stale data state/freshness, degraded fail-closed metadata, `data_state_stale` reason, refusal metadata, governance helper passes. | Exact |
| Unsafe request fields fail closed. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_unsafe_request_fields_return_fail_closed_api_response` | `bullpen_state` withheld, fail-closed critical state, unsafe source reason code, unsupported-field refusal, governance helper passes. | Exact |
| V1 candidate API behavior remains unchanged. | `backend/tests/test_recommendation_v2_api_contract.py` | `test_v1_candidate_api_behavior_remains_unchanged` | V1 recommendation route still returns candidate-level response and preserves V1 no-ranking/no-selection metadata. | Exact |

Frontend exact mappings for `/api/recommendations/v2/bullpen-state` client normalization:

| Evidence Claim | Test File | Exact Test Name | Assertion Group | Mapping |
|----------------|-----------|-----------------|-----------------|---------|
| Successful V2 bullpen-state response normalizes without ranking or selection. | `frontend/tests/recommendationV2Api.test.mjs` | `normalizes a successful V2 bullpen-state response without ranking or selection` | endpoint route, available contract state, governance flags false, trust/freshness/refusal metadata retained, non-ranking ordering, forbidden public fields absent. | Exact |
| Fail-closed refusal metadata remains contract-safe. | `frontend/tests/recommendationV2Api.test.mjs` | `preserves fail-closed refusal metadata as a contract-safe state` | fail-closed state, governance flags false, refusal metadata retained, bullpen state withheld. | Exact |
| Structured fail-closed metadata is accepted. | `frontend/tests/recommendationV2Api.test.mjs` | `accepts structured fail-closed metadata from the V2 bullpen-state contract` | structured fail-closed object retained, freshness retained, refusal metadata retained, governance flags false. | Exact |
| Missing governance fields become unavailable without defaults. | `frontend/tests/recommendationV2Api.test.mjs` | `marks responses with missing governance fields unavailable without defaults` | unavailable contract state, missing field diagnostics for `ranking_applied` and `trust_metadata.selection_made`, bullpen state withheld. | Exact |
| Forbidden ranking and selection response fields are rejected. | `frontend/tests/recommendationV2Api.test.mjs` | `rejects forbidden ranking and selection response fields` | forbidden paths identify `bullpen_state.selected_pitcher` and `ranked_candidates`; unsafe public fields absent from view model. | Exact |
| Frontend client fetches the approved V2 endpoint. | `frontend/tests/recommendationV2Api.test.mjs` | `fetches the approved V2 bullpen-state endpoint and returns normalized contract data` | fetch URL is `/api/recommendations/v2/bullpen-state`, GET semantics, normalized available contract state, governance flags false, trust metadata retained. | Exact |
| Concurrent identical V2 GET requests are de-duplicated. | `frontend/tests/recommendationV2Api.test.mjs` | `deduplicates concurrent identical V2 bullpen-state GET requests` | one fetch call for concurrent identical requests, governance flags false in normalized responses. | Exact |

Dashboard exact mappings:

| Evidence Claim | Test File | Exact Test Name | Assertion Group | Mapping |
|----------------|-----------|-----------------|-----------------|---------|
| Dashboard V2 panel renders governed bullpen intelligence. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders governed V2 bullpen intelligence in available state` | V2 heading, contract state, trust/freshness/limitations/explanations, inventory, team context, neutral candidate groups, non-ranking source order, no automated decision made. | Exact |
| Inventory summary remains compact with visible metadata. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders inventory summary cards collapsed by default with counts and metadata visible` | collapsed inventory cards, counts, confidence, freshness, `aria-expanded="false"`, details withheld until expansion. | Exact |
| Expanded inventory preserves evidence, trust, and freshness. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders expanded inventory membership, evidence, trust, and freshness on demand` | expanded state, evidence visibility, member visibility, data-through and sync timestamps. | Exact |
| Candidate groups remain collapsed with neutral metadata visible. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders candidate groups collapsed by default with summaries and metadata visible` | group count, description, neutral ordering, confidence, freshness, hidden members and eligibility until expansion. | Exact |
| Expanded candidate groups expose evidence, freshness, and refusal metadata. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders expanded candidate group membership, evidence, freshness, and refusal metadata on demand` | member detail, eligibility basis, freshness, data-through/sync timestamps, explanation, limitation, and refusal metadata. | Exact |
| Team context summarizes by default and expands details on demand. | `frontend/tests/recommendationV2Rendering.test.mjs` | `summarizes team context by default and expands distributions and indicators on demand` | collapsed category/summary visibility, detailed distribution and indicator visibility after expansion. | Exact |
| High-volume inventory remains compact until expanded. | `frontend/tests/recommendationV2Rendering.test.mjs` | `keeps high-volume inventory short until mobile users expand details` | initial text reduction, details withheld until expansion, large inventory members visible only after expansion. | Exact |
| High-volume intelligence surfaces remain compact until expanded. | `frontend/tests/recommendationV2Rendering.test.mjs` | `keeps high-volume intelligence surfaces short until mobile users expand details` | initial text reduction, candidate and team detail withheld until expansion, long refusal/detail lists gated. | Exact |
| Dashboard V2 layout remains container-aware. | `frontend/tests/recommendationV2Rendering.test.mjs` | `uses container-aware V2 layout classes for desktop readability` | governed panel classes present and fixed grid breakpoint classes absent. | Exact |
| Dashboard V2 accessibility anchors are rendered. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders mobile and accessibility anchors for governed V2 metadata` | `aria-labelledby`, `aria-describedby`, section IDs, contract-state aria label, live region, atomic region, focus-visible CSS, metadata-grid child constraints. | Exact |
| Fail-closed state renders refusal metadata visibly. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders fail-closed state with refusal metadata visible` | fail-closed state, missing/stale warning, `role="alert"`, assertive live region, refusal message, inventory and groups unavailable. | Exact |
| Unsafe/unavailable contract state withholds bullpen details. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders unavailable state without rendering withheld bullpen details` | unavailable state, alert role, diagnostics, withheld output, example pitcher and inventory absent. | Exact |
| Unsafe display language makes the view unavailable. | `frontend/tests/recommendationV2Rendering.test.mjs` | `view model with unsafe display language becomes unavailable` | unsafe group label causes unavailable contract state, unsafe language marker, withheld bullpen state. | Exact |
| Negative governance disclaimers remain allowed. | `frontend/tests/recommendationV2Rendering.test.mjs` | `view model allows negative governance disclaimers in metadata` | non-forecast and no-ranking/no-selection disclaimers render without making view unavailable. | Exact |
| Rendered V2 panel avoids prohibited decision language. | `frontend/tests/recommendationV2Rendering.test.mjs` | `rendered V2 panel avoids prohibited decision language` | visible rendered text is scanned against prohibited decision-language terms. | Exact |
| Loading and error states avoid unsafe claims. | `frontend/tests/recommendationV2Rendering.test.mjs` | `renders loading and error states without exposing unsafe claims` | loading status, busy state, safe error copy, raw network detail withheld. | Exact |
| Dashboard imports with the governed V2 panel dependency. | `frontend/tests/recommendationV2Rendering.test.mjs` | `Dashboard imports cleanly with the governed V2 panel dependency` | Dashboard module import remains valid with governed V2 dependency. | Exact |

## Production Surface Test Mapping

| Surface | Exact Backend Mapping | Exact Frontend Mapping | Remaining Mapping Gap |
|---------|-----------------------|------------------------|-----------------------|
| Dashboard V2 Bullpen Intelligence | Not directly a backend surface. Backend V2 API tests support the data contract consumed by Dashboard. | `frontend/tests/recommendationV2Rendering.test.mjs` exact tests listed above. `frontend/tests/recommendationV2Api.test.mjs` exact normalization tests support the client-side contract feeding Dashboard. | End-to-end browser or deployed monitoring artifact is not retained. |
| `/api/recommendations/v2/bullpen-state` | `backend/tests/test_recommendation_v2_api_contract.py` exact endpoint contract tests listed above. Related V2 assembly and trust suites provide internal support. | `frontend/tests/recommendationV2Api.test.mjs` exact client normalization tests listed above. | No runtime telemetry or continuous-integration artifact publication is retained. |

Supporting backend internal suites:

| Test File | Evidence Supported | Mapping Status |
|-----------|--------------------|----------------|
| `backend/tests/test_recommendation_v2_context_assembly.py` | V2 context assembly, neutral grouping, trust/freshness/refusal propagation, fail-closed behavior, unsafe source field handling, V1 behavior preservation. | Exact test names identified; endpoint contract mapping remains primary. |
| `backend/tests/test_recommendation_v2_inventory_visibility.py` | Inventory summaries, input-order preservation, trust/freshness/refusal metadata, missing evidence fail-closed behavior, unsafe field handling. | Exact test names identified; supports Dashboard inventory evidence. |
| `backend/tests/test_recommendation_v2_neutral_intelligence.py` | Neutral bullpen-wide categories, non-ranked group ordering, metadata propagation, missing evidence fail-closed behavior, unsafe selection field handling. | Exact test names identified; supports Dashboard neutral intelligence evidence. |
| `backend/tests/test_recommendation_v2_team_bullpen_context.py` | Team context summaries, non-ranked order, trust/freshness/refusal metadata, missing evidence fail-closed behavior, unsafe ranking/selection field handling. | Exact test names identified; supports Dashboard team context evidence. |
| `backend/tests/test_recommendation_v2_trust_metadata_integration.py` | Trust metadata propagation, missing trust/freshness/refusal metadata fail-closed behavior, unsafe ranking/selection field handling, deterministic safe serialization. | Exact test names identified; supports trust metadata evidence. |
| `backend/tests/test_recommendation_v2_refusal_fail_closed.py` | Explicit refusal/fail-closed metadata, stale and malformed evidence handling, unsafe ranking/selection/prediction fields, deterministic safe serialization. | Exact test names identified; supports fail-closed evidence. |

## Dashboard V2 Runbook Evidence Assessment

Current Dashboard V2 runbook evidence:

| Runbook Area | Evidence Status | Current Evidence | Remaining Gap |
|--------------|----------------|------------------|---------------|
| Production scope | Complete | Phase 16 rollout decision and Phase 17 boundary review identify Dashboard V2 as current production scope. | None for current certified scope. |
| Governance boundary | Complete | Phase 27 section-level citation map plus exact frontend tests preserve no ranking, selection, prediction, and decision-language behavior. | None for current certified scope. |
| Rendering and accessibility checks | Complete for test evidence | `frontend/tests/recommendationV2Rendering.test.mjs` exact tests map rendering, accessibility anchors, fail-closed display, unavailable display, and prohibited-language checks. | No manual operating runbook exists for non-test review steps. |
| Incident or monitoring review steps | Partial | Phase 28 defines the monitoring artifact format. | First dated monitoring artifact and incident-review process are not retained. |
| Evidence retention owner | Complete | Documentation governance under Nikko assigned in Phase 28. | Future owner change process is not separately documented. |

Dashboard runbook closeout:

```text
DASHBOARD_RUNBOOK_EVIDENCE = PARTIAL_WITH_TEST_AND_ARTIFACT_FORMAT_CLOSEOUT
```

The remaining runbook gap requires a future operating checklist or first
retained monitoring artifact. It does not block current documentation
governance closeout for certified scope.

## API-To-Frontend Accessibility Field Traceability Assessment

API-to-frontend traceability:

| API Evidence Field Or State | Frontend Rendering Evidence | Exact Test Mapping | Status |
|-----------------------------|-----------------------------|-------------------|--------|
| `ranking_applied === false` | Governance metadata and safe disclaimer behavior remain rendered without selection. | `frontend/tests/recommendationV2Api.test.mjs :: normalizes a successful V2 bullpen-state response without ranking or selection`; `frontend/tests/recommendationV2Rendering.test.mjs :: view model allows negative governance disclaimers in metadata` | Exact |
| `selection_made === false` | Governance metadata and safe disclaimer behavior remain rendered without selection. | `frontend/tests/recommendationV2Api.test.mjs :: normalizes a successful V2 bullpen-state response without ranking or selection`; `frontend/tests/recommendationV2Rendering.test.mjs :: view model allows negative governance disclaimers in metadata` | Exact |
| `trust_metadata` | Trust section and metadata anchors remain visible. | `frontend/tests/recommendationV2Api.test.mjs :: fetches the approved V2 bullpen-state endpoint and returns normalized contract data`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders governed V2 bullpen intelligence in available state`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders mobile and accessibility anchors for governed V2 metadata` | Exact |
| `freshness` | Freshness section, data-through values, sync values, and stale/missing warnings render. | `frontend/tests/recommendationV2Rendering.test.mjs :: renders expanded inventory membership, evidence, trust, and freshness on demand`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders fail-closed state with refusal metadata visible` | Exact |
| `refusal_reasons` | Refusal section and refusal message render in fail-closed state. | `frontend/tests/recommendationV2Api.test.mjs :: preserves fail-closed refusal metadata as a contract-safe state`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders fail-closed state with refusal metadata visible` | Exact |
| `fail_closed` | Fail-closed alert state renders and withholds unsafe bullpen details. | `frontend/tests/recommendationV2Api.test.mjs :: accepts structured fail-closed metadata from the V2 bullpen-state contract`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders fail-closed state with refusal metadata visible`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders unavailable state without rendering withheld bullpen details` | Exact |
| forbidden output fields | Unsafe ranked/selected fields make output unavailable or withheld. | `frontend/tests/recommendationV2Api.test.mjs :: rejects forbidden ranking and selection response fields`; `frontend/tests/recommendationV2Rendering.test.mjs :: view model with unsafe display language becomes unavailable` | Exact |
| accessibility landmarks and live regions | Dashboard renders labelled/described panel sections, live regions, and focus-visible safeguards. | `frontend/tests/recommendationV2Rendering.test.mjs :: renders mobile and accessibility anchors for governed V2 metadata`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders fail-closed state with refusal metadata visible`; `frontend/tests/recommendationV2Rendering.test.mjs :: renders unavailable state without rendering withheld bullpen details` | Exact |

Traceability closeout:

```text
API_TO_FRONTEND_ACCESSIBILITY_TRACEABILITY = COMPLETE_FOR_CURRENT_TESTED_FIELDS
```

Remaining traceability gaps are limited to future API fields or future UI
surfaces not present in the certified production scope.

## Required Production Surface Closeout

| Surface | Owner | Retention Cadence | Monitoring Artifact Expectations | Test Evidence Mapping | Accessibility Mapping | Remaining Unmapped Evidence |
|---------|-------|-------------------|----------------------------------|-----------------------|-----------------------|-----------------------------|
| Dashboard V2 Bullpen Intelligence | Nikko as maintainer of record; frontend governance as evidence collection owner; documentation governance under Nikko as retention owner. | Monthly while V2.5 closeout remains active; before lifecycle movement; after certification, rollout, monitoring, or test mapping changes. | Use Phase 28 artifact format; include rendering state, trust/freshness/refusal visibility, accessibility anchors, prohibited-language check, validation commands, and follow-up decision. | Exact frontend rendering tests and frontend API normalization tests mapped in Phase 28. | Complete for current tested fields and anchors. | First dated monitoring artifact; manual operating checklist; future owner-change process. |
| `/api/recommendations/v2/bullpen-state` | Nikko as maintainer of record; backend governance as evidence collection owner; documentation governance under Nikko as retention owner. | Monthly while V2.5 closeout remains active; before lifecycle movement; after certification, rollout, monitoring, contract, or test mapping changes. | Use Phase 28 artifact format; include endpoint status, latency if available, error rate if available, trust/freshness/refusal/fail-closed metadata, forbidden field absence, validation commands, and follow-up decision. | Exact backend API contract tests and frontend API normalization tests mapped in Phase 28. | Complete through Dashboard rendering of current tested fields. | First dated monitoring artifact; runtime telemetry feed; continuous-integration artifact publication. |

## Remaining Unmapped Evidence

Remaining evidence that cannot be fully mapped in Phase 28:

| Evidence Gap | Surface | Why It Remains Unmapped | Required Future Work |
|--------------|---------|--------------------------|----------------------|
| First dated monitoring artifact | Both production surfaces | Phase 28 defines the format but does not create monitoring output. | Capture and retain the first artifact after a real monitoring review. |
| Runtime telemetry feed | `/api/recommendations/v2/bullpen-state` | No current retained runtime telemetry feed is documented. | Add telemetry or documented manual collection before claiming runtime monitoring evidence. |
| Continuous-integration artifact publication | Both production surfaces | Test execution is run locally for this phase; no retained CI artifact is added. | Add CI artifact retention if persistent build evidence is required. |
| Manual Dashboard operating checklist | Dashboard V2 Bullpen Intelligence | Existing tests cover rendering/governance, but no human operating checklist exists. | Create a runbook section only if manual operating review becomes required. |
| Future owner-change process | Both production surfaces | Phase 28 assigns current retention owner, but no succession process exists. | Add owner-change procedure if governance ownership changes. |

## Governance Closeout Readiness Assessment

Production evidence closeout assessment:

| Closeout Area | Status | Rationale |
|---------------|--------|-----------|
| Packet-level retention owner | Complete | Phase 28 assigns documentation governance under Nikko as retention owner for both production packets. |
| Retention cadence | Complete | Phase 28 defines monthly active-closeout cadence, lifecycle-trigger cadence, and evidence-change cadence. |
| Monitoring artifact format | Complete | Phase 28 defines the retained artifact schema and required fields. |
| First monitoring artifact | Not Complete | Artifact format exists, but no dated operational monitoring artifact is retained. |
| Exact test mapping | Complete for current certified scope | Backend API contract, frontend API normalization, and Dashboard rendering/accessibility tests are mapped by file and test name. |
| API-to-frontend accessibility field traceability | Complete for current tested fields | Current trust, freshness, refusal, fail-closed, governance, and accessibility anchor fields are mapped to exact tests. |
| Governance boundaries | Complete | `ranking_applied === false`, `selection_made === false`, and no ranking/selection/prediction/best/preferred/recommended behavior remain documented and tested. |

Closeout recommendation:

```text
V2_5_GOVERNANCE_HARDENING_CLOSEOUT = APPROPRIATE_WITH_OPERATIONAL_RETENTION_RISK
```

V2.5 governance hardening is closeout-ready for documentation, ownership,
cadence, citation, and exact test-mapping purposes. Full operational evidence
retention is not complete until the first dated monitoring artifact is captured
and retained.

## Certified V2 Governance Confirmation

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

Phase 28 explicitly confirms:

- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best option behavior exists
- no preferred option behavior exists
- no recommended option behavior exists

Phase 28 does not authorize:

- new API exposure
- fatigue formula change
- API contract change
- frontend runtime behavior change
- backend recommendation behavior change
- certified production scope expansion

## Validation

Validation performed for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-phase-28-evidence-closeout
Result: 278 passed, 0 failed.

cd frontend
npm test
Result: 78 passed, 0 failed.

git diff --check
Result: Passed; reported only LF-to-CRLF warnings, including known unrelated
frontend generated/dependency drift.

git diff --cached --check
Result: Passed after targeted documentation staging.
```

Root `npm test` is not required for Phase 28. If no root `package.json` exists,
that is expected and is not a project failure.

## Remaining Risks

Remaining risks:

- no first dated operational monitoring artifact is retained
- runtime telemetry feed is not documented
- continuous-integration artifact publication is not documented
- Dashboard manual operating checklist remains optional and not retained
- future owner-change process is not documented

These are operational retention risks, not current certified V2 governance
regressions.

## Recommended Next Milestone

Completed follow-up layer:

```text
BaseballOS V2.5 Phase 29 Governance Hardening Closeout and V3 Readiness Decision
```

Phase 29 formally closes the V2.5 governance hardening program, classifies
remaining operational retention gaps as blocking or non-blocking, and records
V3 product capability planning readiness without changing runtime behavior.

Recommended next milestone:

```text
BaseballOS V3 Product Capability Planning
```

V3 product capability planning should use the completed V2.5 governance
hardening records as entry criteria before proposing any new product
capability, runtime behavior, API exposure, recommendation behavior, ranking
behavior, selection behavior, prediction behavior, or production-surface
expansion.
