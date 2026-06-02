# Recommendation Engine V2 Implementation Plan

## 1. Executive Summary

Recommendation Engine V2 is ready for implementation planning, but this
document does not implement V2 and does not authorize runtime behavior changes.
It converts the approved V2 governance package into a phased roadmap for future
implementation work.

The plan preserves the certified Recommendation Engine V1 trust boundary:

```text
ranking_applied = false
selection_made = false
```

V2 implementation must remain descriptive, deterministic, explainable,
auditable, governance-driven, and fail-closed. It must not introduce ranking,
selection, prediction, opaque scores, hidden weights, or unsupported baseball
opinions.

The first implementation milestone after this planning document is now
complete:

```text
Recommendation Engine V2 Phase 1 Backend Domain Object Foundation
```

That milestone may begin only after explicit user approval for implementation.

## 2. Relationship to V2 Readiness Review

The implementation-readiness review concluded:

```text
READY_FOR_IMPLEMENTATION
```

That determination means the governance package is complete enough to support
implementation planning. It does not mean V2 is implemented, certified, or
production-ready.

This plan adopts the readiness review findings:

- no remaining governance blockers were identified
- implementation risks must be actively controlled
- V1 behavior must remain unchanged
- V2 must preserve no-ranking and no-selection guarantees
- implementation should proceed incrementally through auditable phases

The readiness review remains the admission evidence for creating this plan.

## 3. Relationship to V2 Governance Package

This plan is subordinate to the complete V2 governance package:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`
- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`
- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`
- `docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`
- `docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md`

If this plan conflicts with those documents, the stricter governance boundary
wins. Future implementation work must keep those documents current when an
approved implementation detail clarifies, narrows, or operationalizes the plan.

## 4. Implementation Philosophy

V2 implementation should be:

- incremental
- test-first where practical
- governance-driven
- fail-closed
- documentation-aligned
- behavior-preserving for V1

The implementation sequence should favor narrow, reviewable changes over broad
multi-layer delivery. Each phase should prove one layer before the next layer
depends on it.

This plan does not authorize shortcuts around:

- trust metadata
- explanations
- freshness visibility
- limitations
- refusal behavior
- anti-ranking rules
- anti-selection rules
- V1 regression protection

## 5. Implementation Non-Goals

V2 implementation must not include:

- pitcher ranking
- pitcher ordering by preference
- final pitcher selection
- automated pitcher choice
- recommended pitcher fields
- selected pitcher fields
- "best pitcher" claims
- game outcome prediction
- injury prediction
- save prediction
- performance forecasting
- opaque scoring systems
- hidden decision weights
- unsupported baseball opinions
- UI layouts that imply a recommendation winner
- API responses that imply ranking or selection
- changes to certified Recommendation Engine V1 candidate evaluation behavior

V2 implementation complete does not mean production certified. Production
certification is a separate governed decision.

## 6. Required Preservation of V1 Behavior

Recommendation Engine V1 is complete, certified, and production-ready for
candidate-level evaluation. V2 must not alter certified V1 behavior.

The following guarantees must remain visible and true:

```text
ranking_applied = false
selection_made = false
```

V2 must not alter V1 candidate evaluation behavior, category semantics,
refusal behavior, trust metadata, freshness handling, explanations, limitations,
or API/frontend behavior unless a later approved V1 governance process permits
that change.

Any change that breaks V1 behavior is an implementation stop condition.

## 7. Phase 0: Pre-Implementation Repo Hygiene Check

**Goal**

Establish a clean implementation boundary before any V2 runtime work begins.

**Allowed work**

- Run `git status`.
- Identify unrelated worktree drift.
- Confirm unrelated drift is not staged.
- Confirm the active branch is the approved implementation branch.
- Confirm documentation-only planning work is separated from generated
  frontend artifacts.
- Record the baseline commit used for implementation.

**Forbidden work**

- Do not use broad `git add .` if unrelated drift exists.
- Do not stage `frontend/dist/**`, `frontend/node_modules/**`, or
  `frontend/package-lock.json` drift unless that drift is explicitly part of an
  approved implementation phase.
- Do not reset, delete, or rewrite unrelated drift without explicit approval.
- Do not begin backend, frontend, or API implementation until hygiene is
  confirmed.

**Dependencies**

- Approved implementation plan.
- Explicit user approval to begin implementation.

**Required tests**

- No runtime tests are required in Phase 0.
- Required verification is git hygiene evidence.

**Documentation updates**

- If unrelated drift exists, implementation notes should record that it was
  excluded from staging.

**Exit criteria**

- `git status` has been reviewed.
- Unrelated drift has been identified.
- Unrelated drift is unstaged.
- The implementer confirms no generated frontend artifacts are mixed into V2
  planning or implementation work.

The current repository has unrelated `frontend/dist/**`,
`frontend/node_modules/**`, and `frontend/package-lock.json` drift. That drift
must not be mixed into V2 implementation work.

## 8. Phase 1: Backend Domain Object Foundation

**Implementation status**

Complete.

The backend-only domain object foundation is implemented in:

- `backend/recommendation/v2.py`

The Phase 1 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md`

The implemented foundation does not expose a V2 endpoint, create frontend
behavior, change routes, rank pitchers, select pitchers, predict outcomes, or
modify Recommendation Engine V1 behavior.

**Goal**

Create the backend domain foundation for V2 without exposing runtime behavior
or changing existing V1 recommendation output.

**Allowed work**

- Define backend objects such as `BullpenState`, `CandidateGroup`,
  `TeamBullpenContext`, and `RecommendationContext`.
- Add explicit fields for trust metadata, explanations, freshness,
  limitations, refusal reasons, and data state.
- Establish neutral candidate containers that cannot carry rank, winner, score,
  or selection semantics.
- Add unit tests for object construction and invariant preservation.

**Forbidden work**

- Do not expose a V2 endpoint.
- Do not modify V1 recommendation behavior.
- Do not introduce ranking fields, selection fields, scores, hidden weights, or
  preference ordering.
- Do not create frontend components.

**Dependencies**

- Phase 0 complete.
- Approved architecture and API contract.

**Required tests**

- Backend unit tests for object defaults.
- Tests that `ranking_applied=false` and `selection_made=false` are required.
- Tests that forbidden fields are absent.

**Documentation updates**

- Update implementation notes only if approved objects differ from the
  architecture document.

**Exit criteria**

- Domain objects exist behind internal boundaries.
- No public API behavior changes.
- V1 regression tests still pass.
- No ranking or selection semantics exist.

## 9. Phase 2: Bullpen State Builder

**Goal**

Build descriptive bullpen-level state from existing availability and workload
data.

**Allowed work**

- Create an internal builder that summarizes bullpen status, readiness,
  inventory, limitations, freshness, and trust state.
- Use existing availability and workload evidence as inputs.
- Keep the builder deterministic.
- Add refusal or degraded-confidence paths when required evidence is missing.

**Forbidden work**

- Do not recommend which pitcher to use.
- Do not sort candidates by preference.
- Do not infer private medical, clubhouse, travel, or manager-intent context.
- Do not change existing availability classifications.

**Dependencies**

- Phase 1 domain objects complete.
- Existing availability/workload inputs understood and covered by tests.

**Required tests**

- Backend tests for complete data, stale data, missing data, and degraded data.
- Tests that bullpen state remains descriptive.
- V1 regression tests.

**Documentation updates**

- Document any approved mapping between existing availability evidence and V2
  descriptive state.

**Exit criteria**

- Bullpen state can be built internally.
- It carries trust metadata.
- It refuses or downgrades when evidence is insufficient.
- It does not expose ranking, selection, or prediction.

## 10. Phase 3: Candidate Grouping Layer

**Goal**

Implement grouped eligibility reporting without ranking candidates.

**Allowed work**

- Create neutral groups such as Fresh High-Leverage Arms, Available
  Multi-Inning Arms, Use With Caution, and Bullpen Stress Exposure.
- Preserve deterministic neutral ordering inside groups, such as alphabetic
  order or stable ID order.
- Explain why each group exists and why each candidate appears in the group.
- Support empty and refusal states for groups.

**Forbidden work**

- Do not create ranked lists.
- Do not order candidates by quality, preference, urgency, confidence, or
  hidden priority.
- Do not mark a top option, best option, winner, recommended pitcher, or
  selected pitcher.
- Do not use group placement as a proxy for selection.

**Dependencies**

- Phase 1 domain objects complete.
- Phase 2 bullpen state builder available.

**Required tests**

- Group membership tests.
- Neutral ordering tests.
- Anti-ranking field and language tests.
- Explanation coverage tests.
- V1 regression tests.

**Documentation updates**

- Document approved group labels and eligibility bases when finalized.

**Exit criteria**

- Candidate groups are informational only.
- Candidate ordering is neutral and documented.
- Every group and candidate has explanation support.
- No ranking or selection behavior is present.

## 11. Phase 4: Inventory Visibility Layer

**Goal**

Implement descriptive bullpen inventory summaries.

**Allowed work**

- Summarize high-leverage inventory.
- Summarize multi-inning inventory.
- Summarize emergency coverage inventory.
- Summarize limited availability inventory.
- Include counts, members, evidence, limitations, freshness, and confidence.

**Forbidden work**

- Do not tell the user which inventory member to use first.
- Do not present inventory as a preferred bullpen path.
- Do not assign priority scores or hidden weights.
- Do not convert inventory visibility into selection guidance.

**Dependencies**

- Phase 2 bullpen state builder.
- Phase 3 candidate grouping layer when inventory references grouped
  candidates.

**Required tests**

- Inventory count tests.
- Inventory evidence tests.
- Freshness and limitation propagation tests.
- Anti-selection language tests.

**Documentation updates**

- Document approved inventory labels and evidence sources.

**Exit criteria**

- Inventory output is descriptive.
- Inventory output carries trust metadata.
- Inventory output refuses or downgrades when evidence is incomplete.
- No inventory output implies preference.

## 12. Phase 5: Team Bullpen Context Layer

**Goal**

Implement broader team-level bullpen context without team-level decision
commands.

**Allowed work**

- Summarize leverage inventory.
- Summarize fatigue distribution.
- Summarize availability distribution.
- Summarize readiness indicators.
- Summarize workload concentration and coverage risk.

**Forbidden work**

- Do not produce team-level decision commands.
- Do not forecast outcomes.
- Do not prescribe bullpen paths.
- Do not infer unsupported strategy or manager intent.

**Dependencies**

- Phase 2 bullpen state builder.
- Phase 4 inventory visibility layer.

**Required tests**

- Team context summary tests.
- Workload distribution tests.
- Readiness indicator tests.
- Tests that no decision-command language appears.

**Documentation updates**

- Document approved team context labels and limits.

**Exit criteria**

- Team context is explanatory and descriptive.
- It carries limitations and freshness.
- It does not rank, choose, or decide.

## 13. Phase 6: Trust Metadata Integration

**Goal**

Propagate mandatory trust metadata through all V2 output layers.

**Allowed work**

- Propagate `scope`.
- Propagate `ranking_applied`.
- Propagate `selection_made`.
- Propagate `confidence`.
- Propagate `data_state`.
- Propagate `generated_at`.
- Propagate `freshness`.
- Propagate `limitations`.
- Propagate `explanations`.
- Propagate `refusal_reasons`.

**Forbidden work**

- Do not allow any V2 output without mandatory trust metadata.
- Do not hide degraded confidence, stale freshness, missing data, limitations,
  or refusal reasons.
- Do not permit `ranking_applied` or `selection_made` to become true within V2.

**Dependencies**

- Phases 1 through 5.
- API contract metadata requirements.

**Required tests**

- Trust metadata presence tests across every output type.
- Metadata propagation tests.
- Tests that missing metadata fails closed.
- V1 regression tests.

**Documentation updates**

- Update API or certification docs only if approved metadata details change.

**Exit criteria**

- Every internal V2 output carries mandatory trust metadata.
- Missing metadata blocks output.
- No output can truthfully imply ranking or selection.

## 14. Phase 7: Refusal and Fail-Closed Integration

**Goal**

Ensure V2 refuses, suppresses, or downgrades unsupported output.

**Allowed work**

- Add refusal behavior for stale data.
- Add refusal behavior for incomplete data.
- Add refusal behavior for missing explanations.
- Add refusal behavior for unsupported scope.
- Add refusal behavior for output that would imply ranking or selection.
- Add degraded-confidence behavior where output is still explainable but
  limited.

**Forbidden work**

- Do not fabricate missing evidence.
- Do not fail open when trust metadata is incomplete.
- Do not silently omit material limitations.
- Do not replace refusal with generic empty output.

**Dependencies**

- Phase 6 trust metadata integration.
- Certification requirements for refusal states.

**Required tests**

- Stale-data refusal tests.
- Incomplete-data refusal tests.
- Explanation-failure refusal tests.
- Governance-boundary refusal tests.
- Determinism tests for refusal behavior.

**Documentation updates**

- Document any approved refusal reason codes.

**Exit criteria**

- Fail-closed behavior is deterministic.
- Refusal reasons are visible.
- Unsupported output is not emitted.
- V1 behavior remains unchanged.

## 15. Phase 8: API Endpoint Implementation

**Goal**

Implement the approved V2 API surface after internal layers satisfy governance
requirements.

**Allowed work**

- Implement the provisional endpoint:

```text
GET /api/recommendations/v2/bullpen-state
```

- Return the response shape defined by the V2 API contract.
- Preserve required top-level metadata.
- Return refusal and fail-closed shapes when required.
- Add API contract tests.

**Forbidden work**

- Do not add endpoints beyond approved scope.
- Do not modify existing V1 endpoints except for non-behavioral wiring that is
  explicitly required and regression-tested.
- Do not include forbidden fields such as `rank`, `score`, `priority`,
  `best_candidate`, `recommended_pitcher_id`, or `selected_pitcher_id`.
- Do not return sorted preference lists.

**Dependencies**

- Phases 1 through 7.
- Approved API contract.

**Required tests**

- API contract tests.
- Forbidden-field tests.
- Refusal shape tests.
- Freshness and limitation tests.
- V1 API regression tests.

**Documentation updates**

- Update API documentation after implementation details are verified.

**Exit criteria**

- V2 API response matches contract.
- Refusal responses preserve contract shape.
- V1 API behavior remains unchanged.
- No ranking or selection fields exist.

## 16. Phase 9: Frontend Client Integration

**Goal**

Add future frontend client support for the V2 endpoint without rendering
governance-unsafe UI.

**Allowed work**

- Add API-client calls for the approved V2 endpoint.
- Preserve all trust metadata fields from the backend response.
- Represent refusal and degraded states explicitly in client data.
- Add client tests for successful and refusal responses.

**Forbidden work**

- Do not create or modify React display components in this phase unless
  explicitly scoped.
- Do not discard limitations, explanations, freshness, or refusal reasons.
- Do not transform neutral ordering into preference ordering.
- Do not infer selected or recommended pitchers client-side.

**Dependencies**

- Phase 8 API endpoint implementation.
- Frontend contract.

**Required tests**

- Frontend API-client tests.
- Contract fixture tests.
- Missing-field handling tests.
- Forbidden-field guard tests.

**Documentation updates**

- Update frontend integration notes if client behavior clarifies the contract.

**Exit criteria**

- Client can consume V2 responses.
- Client preserves trust metadata.
- Client exposes refusal data to future rendering layers.
- No UI behavior changes unless separately approved.

## 17. Phase 10: Frontend Rendering Implementation

**Goal**

Render V2 output in governance-safe UI patterns.

**Allowed work**

- Add bullpen context panel.
- Add inventory panels.
- Add candidate group panels.
- Add trust metadata strips.
- Add explanation panels.
- Add limitation panels.
- Add refusal states.
- Use neutral category sections, grouped cards, alphabetic ordering, stable ID
  ordering, and status-based grouping.

**Forbidden work**

- Do not use numbered ranking lists.
- Do not use leaderboard layouts.
- Do not use top-option cards, best-pitcher banners, winner badges, selected
  pitcher callouts, or recommended pitcher callouts.
- Do not use visual hierarchy that implies one candidate is the winner.
- Do not hide material limitations behind cosmetic-only interactions.

**Dependencies**

- Phase 9 frontend client integration.
- Frontend contract.

**Required tests**

- Frontend rendering tests.
- Governance language scans.
- Trust metadata visibility tests.
- Refusal rendering tests.
- Freshness and limitation rendering tests.

**Documentation updates**

- Update frontend contract only if approved rendering details narrow or clarify
  the contract.

**Exit criteria**

- V2 UI renders descriptive context safely.
- Required trust metadata is visible or accessible.
- No forbidden copy or ranking-like presentation appears.
- Refusal states are explicit.

## 18. Phase 11: Mobile and Accessibility Validation

**Goal**

Verify mobile and accessibility behavior preserves governance guarantees.

**Allowed work**

- Validate stacked mobile layouts for neutral ordering.
- Validate visible trust metadata on mobile.
- Validate visible refusal and limitation states on mobile.
- Validate ARIA labels, headings, screen-reader text, and button labels.
- Add accessibility tests or audits where practical.

**Forbidden work**

- Do not allow mobile card stacking to imply rank.
- Do not introduce accessibility labels that say or imply best, top,
  preferred, recommended, selected, should use, or ranks first.
- Do not hide refusal reasons from assistive technology.

**Dependencies**

- Phase 10 frontend rendering implementation.

**Required tests**

- Mobile layout checks.
- Accessibility checks.
- Screen-reader text scans.
- Governance language scans.

**Documentation updates**

- Document any required mobile or accessibility certification evidence.

**Exit criteria**

- Mobile layout remains governance-safe.
- Accessibility text remains governance-safe.
- Trust metadata, limitations, and refusal states remain accessible.

## 19. Phase 12: Test Expansion

**Goal**

Expand test coverage to prove V2 behavior satisfies governance, contract, and
certification requirements.

**Allowed work**

- Add backend unit tests.
- Add API contract tests.
- Add frontend rendering tests.
- Add mobile layout checks.
- Add accessibility checks.
- Add governance language scans.
- Add anti-ranking tests.
- Add anti-selection tests.
- Add freshness tests.
- Add refusal/fail-closed tests.
- Add V1 regression tests.

**Forbidden work**

- Do not weaken existing V1 tests to make V2 pass.
- Do not replace governance assertions with snapshot-only coverage.
- Do not skip refusal, freshness, limitation, or explanation coverage.

**Dependencies**

- Phases 1 through 11.
- Certification requirements.

**Required tests**

- All required V2 test categories.
- Existing V1 tests.
- Any lightweight documentation validation required for updated docs.

**Documentation updates**

- Update certification evidence notes with executed test commands and results.

**Exit criteria**

- Required V2 tests pass.
- V1 regression tests pass.
- Anti-ranking and anti-selection audits pass.
- Fail-closed paths are covered.

## 20. Phase 13: Certification Review

**Goal**

Review the completed implementation against the V2 certification requirements.

**Allowed work**

- Audit backend behavior.
- Audit API response shapes.
- Audit frontend rendering.
- Audit mobile and accessibility behavior.
- Audit documentation.
- Record certification evidence and failure conditions.

**Forbidden work**

- Do not certify with missing trust metadata.
- Do not certify with missing explanations.
- Do not certify with incomplete freshness handling.
- Do not certify with missing refusal behavior.
- Do not certify if ranking or selection appears anywhere.
- Do not certify if V1 behavior changed.

**Dependencies**

- Phase 12 test expansion complete.
- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`

**Required tests**

- Full required certification test set.
- Contract compliance checks.
- Governance language scans.
- V1 regression test set.

**Documentation updates**

- Produce certification evidence before production rollout is considered.

**Exit criteria**

- Certification review is complete.
- All certification requirements pass.
- Any implementation risks or residual limitations are documented.
- V2 is eligible for production rollout decision review.

## 21. Phase 14: Production Rollout Decision

**Goal**

Make a governed production rollout decision after implementation and
certification are complete.

**Allowed work**

- Review certification evidence.
- Confirm documentation is complete.
- Confirm feature visibility is controlled.
- Confirm production risk is acceptable.
- Record rollout decision and approval.

**Forbidden work**

- Do not roll out without implementation completion.
- Do not roll out without certification completion.
- Do not roll out without explicit user approval.
- Do not roll out if V1 regression, ranking, selection, or trust failures
  remain unresolved.

**Dependencies**

- Phase 13 certification review complete.

**Required tests**

- Final verification tests selected from certification evidence.
- Smoke checks appropriate to deployment scope.

**Documentation updates**

- Record production rollout decision.
- Update project state after approval.

**Exit criteria**

- Production rollout is approved, rejected, or deferred with evidence.
- Production status is documented.
- V2 behavior remains within certified scope.

## 22. Dependency Map

Implementation order must remain sequential unless an approved implementation
review explicitly narrows a phase without weakening governance.

```text
Phase 0 Repo Hygiene
  -> Phase 1 Backend Domain Objects
  -> Phase 2 Bullpen State Builder
  -> Phase 3 Candidate Grouping
  -> Phase 4 Inventory Visibility
  -> Phase 5 Team Bullpen Context
  -> Phase 6 Trust Metadata
  -> Phase 7 Refusal and Fail-Closed
  -> Phase 8 API Endpoint
  -> Phase 9 Frontend Client
  -> Phase 10 Frontend Rendering
  -> Phase 11 Mobile and Accessibility
  -> Phase 12 Test Expansion
  -> Phase 13 Certification Review
  -> Phase 14 Production Rollout Decision
```

Backend foundations must exist before API exposure. API contract behavior must
exist before frontend rendering. Frontend rendering must exist before mobile and
accessibility certification. All runtime implementation must pass tests before
certification review.

## 23. Expected File/Module Areas

Future implementation may touch these areas, subject to phase approval:

- `backend/recommendation/`
- `backend/api/recommendations.py`
- `backend/services/availability.py`
- `backend/services/availability_summary.py`
- `backend/services/availability_explanations.py`
- `backend/services/sync_metadata.py`
- `backend/tests/test_recommendation_*.py`
- `backend/tests/test_availability_*.py`
- `frontend/src/utils/api.js`
- `frontend/src/components/recommendations/`
- `frontend/src/components/bullpen/`
- `frontend/src/components/dashboard/`
- `frontend/src/components/UI/`
- `frontend/tests/recommendation*.test.mjs`
- `frontend/tests/availability*.test.mjs`
- `docs/`

Future implementation should not touch generated build output or dependency
directories as part of V2 feature work:

- `frontend/dist/**`
- `frontend/node_modules/**`

If those files appear in `git status`, they must be treated as unrelated drift
unless explicitly approved for a separate maintenance task.

## 24. Testing Plan

Required test categories:

- backend unit tests
- API contract tests
- frontend rendering tests
- mobile layout checks
- accessibility checks
- governance language scans
- anti-ranking tests
- anti-selection tests
- freshness tests
- refusal/fail-closed tests
- V1 regression tests

Testing expectations:

- Every V2 output must include `ranking_applied=false`.
- Every V2 output must include `selection_made=false`.
- No forbidden API fields may exist.
- Candidate ordering must be neutral and deterministic.
- Explanations must exist at candidate, group, bullpen, team-context, and
  refusal levels where applicable.
- Freshness, limitations, confidence, data state, generated timestamp, and
  refusal reasons must be present where required.
- Stale, missing, incomplete, or unsupported evidence must refuse, suppress, or
  downgrade output.
- UI copy, visual hierarchy, mobile layout, and accessibility text must not
  imply ranking or selection.
- V1 tests must continue to pass without weakening assertions.

## 25. Rollout and Visibility Strategy

V2 should roll out only after implementation completion and certification
review. The preferred visibility path is:

1. Internal implementation behind controlled visibility.
2. Contract and governance validation against fixture data.
3. Limited non-production review with explicit trust metadata visible.
4. Production certification review.
5. Recorded production rollout decision.

Rollout must preserve user decision authority. V2 output may organize,
summarize, and explain bullpen information. It must not choose, rank, or decide.

## 26. Feature Flag Strategy

V2 should use a controlled visibility mechanism until production certification
is complete.

Acceptable strategies include:

- disabled-by-default configuration
- environment-gated visibility
- internal-only route exposure
- explicit non-production display mode
- per-view feature toggle after certification evidence exists

The flag or visibility mechanism must not bypass governance checks. Hidden or
disabled V2 code must still preserve no-ranking, no-selection, trust metadata,
freshness, limitations, explanations, and refusal behavior.

## 27. Risk Controls

Scope creep controls:

- Implement phases sequentially.
- Keep each phase reviewable.
- Defer unapproved capabilities to V3+ or later governance.

Accidental ranking controls:

- Ban rank fields, ranking arrays, preference sorting, winner labels, and
  score-like outputs.
- Test neutral ordering.
- Scan API and UI language.

Accidental selection controls:

- Ban recommended pitcher, selected pitcher, use-this-pitcher, best candidate,
  and pitcher choice semantics.
- Keep the user as the final decision maker.

UI hierarchy controls:

- Avoid numbered lists, leaderboards, top-option cards, winner badges, and
  visual emphasis that selects one pitcher.
- Use neutral grouped sections and visible trust context.

Hidden score controls:

- Do not add opaque scores, hidden weights, priority values, or quality sorting.
- Require explanations and limitations for every output.

Freshness controls:

- Make stale, degraded, missing, and unknown data states visible.
- Refuse or downgrade output when freshness cannot support the claim.

Refusal controls:

- Return explicit refusal reasons.
- Do not replace refusal with generic empty states.

V1 regression controls:

- Run V1 regression tests.
- Preserve V1 API and frontend behavior.

Worktree drift controls:

- Review `git status` before staging.
- Stage named files only when unrelated drift exists.
- Keep generated frontend artifacts and dependency drift out of V2 commits.

## 28. Implementation Stop Conditions

Implementation must stop if:

- ranking is introduced
- selection is introduced
- V1 behavior changes
- trust metadata cannot be propagated
- explanations cannot be produced
- freshness cannot be represented
- refusal behavior is missing
- frontend implies a winner
- API contract cannot be satisfied
- certification requirements cannot be met
- unrelated worktree drift is accidentally staged

Stop conditions require review before implementation continues.

## 29. Definition of Implementation Complete

Implementation complete means:

- planned backend layers exist
- planned API exists
- planned frontend integration exists
- tests pass
- trust metadata is present
- explanations are present
- freshness is visible
- limitations are visible
- refusal behavior works
- no ranking exists
- no selection exists
- V1 behavior remains unchanged

Implementation complete does not mean production certified.

## 30. Definition of Production Certified

Production certified requires:

- implementation complete
- certification review completed
- all certification requirements passed
- documentation updated
- user approval granted
- production rollout decision recorded

Production certification must be evidence-based and must preserve the full V2
governance package.

## 31. Next Milestone

The next milestone is:

```text
Recommendation Engine V2 Phase 1 Backend Domain Object Foundation
```

This milestone may begin only after the user explicitly approves
implementation.
