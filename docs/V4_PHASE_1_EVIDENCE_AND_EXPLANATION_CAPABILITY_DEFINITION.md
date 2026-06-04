# BaseballOS V4 Phase 1 - Evidence And Explanation Capability Definition

## Phase Status

Phase status:

```text
V4_PHASE_1_EVIDENCE_AND_EXPLANATION_CAPABILITY_DEFINITION_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
PLANNING_ONLY
```

This phase defines the BaseballOS V4 Evidence and Explanation Layer before any
implementation begins. It does not authorize backend changes, frontend changes,
database changes, API changes, runtime behavior changes, or product behavior
changes.

## 1. Capability Overview

V4 is the Evidence and Explanation Layer for BaseballOS.

It exists to help users understand why an existing BaseballOS state, label,
distribution, limitation, refusal, or readiness summary appears. It turns
already-governed output into explainable context without making a decision for
the user.

The core product question is:

```text
Why?
```

Examples:

- Why is availability `Monitor`?
- Why is readiness `Degraded`?
- Why is workload pressure elevated?
- What evidence contributes to this distribution?
- What freshness or trust limitation affects confidence?

V4 solves a usability and trust problem: BaseballOS already exposes governed
availability, recommendation, and readiness surfaces, but users need a more
consistent way to inspect the evidence behind those states without scrolling
through raw audit material or inferring meaning from metadata on their own.

V4 may explain.

V4 may not decide.

## 2. Product Goals

V4 should define an explanation framework that can answer:

- Why is this availability state assigned?
- Why is this readiness state assigned?
- Why is this workload state assigned?
- What evidence supports the current output?
- What limitations affect confidence?
- What freshness state affects the output?
- What trust state affects the output?
- What coverage state affects the output?
- What data inputs were missing, stale, degraded, or refused?
- What did BaseballOS consider when producing the current context?

The product goals are:

- make evidence discoverable without overwhelming the operational Dashboard
- preserve user agency by explaining context instead of issuing instructions
- connect output states to documented contributors and limitations
- show freshness, trust, refusal, and fail-closed factors in plain language
- make degraded and refused states understandable
- support future certification through auditable evidence attribution
- keep all explanation output within the existing no-ranking and no-selection
  governance model

## 3. Allowed Outputs

V4 may produce explanation outputs that describe evidence, contributors,
limitations, and data state.

Allowed output categories include:

- evidence summaries
- explanation summaries
- availability contributors
- readiness contributors
- workload contributors
- freshness contributors
- trust contributors
- coverage contributors
- limitation contributors
- refusal contributors
- fail-closed contributors
- data-quality contributors
- source visibility notes
- metadata visibility notes
- traceability references to existing governed inputs

Allowed examples:

```text
Availability is Monitor because recent workload is elevated and rest recovery is incomplete.
```

```text
Readiness is Degraded because freshness protection is active and coverage evidence is incomplete.
```

```text
This distribution reflects two available arms, one monitor arm, and one limited arm.
```

```text
Confidence is limited because the latest source evidence is stale.
```

These examples are explanatory only. They do not rank, select, recommend, or
instruct.

## 4. Prohibited Outputs

V4 must never become a decision-making, selection, ranking, recommendation, or
prediction layer.

Prohibited outputs include:

- recommended pitcher
- preferred pitcher
- best option
- best arm
- use this arm
- avoid this arm as an instruction
- matchup recommendation
- selection guidance
- ranking output
- priority ordering
- hidden prioritization
- game outcome prediction
- injury prediction
- save prediction
- performance prediction
- pitcher-level advice
- automated decision instruction
- manager-intent inference
- medical or private clubhouse inference

Prohibited examples:

```text
Use Pitcher A.
```

```text
Pitcher B is the best option.
```

```text
Prefer the left-handed arm for this matchup.
```

```text
Pitcher C is likely to perform better.
```

```text
Avoid Pitcher D tonight.
```

V4 explanations must not imply that BaseballOS has selected a pitcher, ranked a
bullpen, predicted performance, or determined the final decision.

## 5. Governance Definition

V4 remains governed by the existing BaseballOS trust-first rules.

Mandatory invariants:

```text
ranking_applied === false
selection_made === false
```

V4 differs from recommendation behavior because it explains existing state. It
does not create a new choice, order candidates, compare pitcher quality, advise
who to use, or automate a baseball decision.

Explanation is allowed when it:

- describes evidence already used by a governed output
- identifies limitations affecting the output
- exposes trust, freshness, refusal, or fail-closed context
- stays team-level, context-level, or state-level unless explaining a
  one-candidate certified V1 surface
- avoids preference language and instruction language
- preserves existing metadata boundaries

Decision-making remains prohibited because BaseballOS does not have private
team context, medical data, warm-up state, manager intent, pitch-quality
projection, matchup model authority, or authorization to choose on behalf of
the user.

V4 must confirm:

- no ranking behavior
- no selection behavior
- no prediction behavior
- no recommendation behavior
- no best/preferred/recommended behavior for bullpen choice
- no hidden priority ordering
- no pitcher-level advice
- no matchup advice

## 6. Candidate Product Surfaces

V4 may eventually appear in several BaseballOS surfaces. This phase does not
choose implementation, placement, endpoint design, component design, or release
order.

Candidate surfaces include:

- availability detail views
- readiness detail views
- risk distribution detail views
- workload pressure detail views
- data freshness detail views
- trust metadata detail views
- refusal and fail-closed detail views
- evidence panels
- explanation drawers
- context dialogs
- Dashboard disclosure sections
- one-candidate V1 detail surfaces
- V2 bullpen-state context surfaces
- V3 Team Operations Bullpen Readiness context surfaces

Surface-selection criteria should include:

- user-facing clarity
- metadata visibility
- evidence traceability
- accessibility
- mobile usability
- governance risk
- implementation cost
- certification effort

## 7. Data Requirements

V4 may need access to already-governed evidence inputs. It must not introduce
new external data sources in the capability definition phase.

Potential data requirements include:

- availability reasoning inputs
- fatigue and workload inputs
- rest-day evidence
- recent appearance evidence
- pitch-count evidence
- innings-load evidence
- freshness reasoning inputs
- trust reasoning inputs
- coverage reasoning inputs
- role or coverage inventory inputs where already available
- handedness coverage inputs where already available
- refusal metadata
- fail-closed metadata
- limitation metadata
- source timestamps
- sync metadata
- data-through metadata
- contract identity metadata

V4 should distinguish:

- source evidence
- derived metadata
- explanation text
- limitation text
- refusal state
- fail-closed state

V4 must not use or imply access to:

- private medical data
- clubhouse status
- warm-up activity
- bullpen phone activity
- team travel context
- manager intent
- non-integrated injury feeds
- performance projection models
- matchup prediction models

## 8. API Considerations

V4 may require future API support, but this phase does not design or authorize
an API.

Potential future API considerations include:

- explanation payload structure
- evidence-attribution structure
- contributor categories
- source reference identifiers
- limitation references
- freshness and trust metadata passthrough
- refusal and fail-closed metadata passthrough
- governance metadata passthrough
- explanation status vocabulary
- degraded and unavailable explanation states
- contract identity for explanation surfaces
- versioned explanation contract planning

Any future API contract must prove:

- explanations are derived from governed source evidence
- missing or unsafe evidence fails closed or degrades visibly
- governance metadata remains present and valid
- prohibited query intent is refused where applicable
- no recommendation engine is created indirectly
- no pitcher ranking or hidden priority ordering is introduced

Potential route or schema work must wait for a separate V4 API planning phase.

## 9. Certification Requirements

V4 certification must prove that explanations are accurate, traceable,
governed, and non-decisional.

Certification must include:

- no recommendation behavior
- no ranking behavior
- no selection behavior
- no prediction behavior
- no best/preferred/recommended behavior
- no hidden priority ordering
- no pitcher-level advice
- no matchup advice
- correct evidence attribution
- correct explanation attribution
- correct limitation attribution
- correct freshness attribution
- correct trust attribution
- correct refusal attribution
- correct fail-closed attribution
- visible governance metadata
- visible freshness metadata when applicable
- visible trust metadata when applicable
- visible refusal and fail-closed metadata when applicable
- deterministic explanation assembly for identical inputs
- safe degraded behavior when evidence is incomplete
- fail-closed behavior when required evidence is missing or unsafe
- frontend language review before public display
- accessibility review for explanation disclosure controls
- V1, V2, and V3 regression safety

Certification evidence should include:

- backend tests if explanation assembly is implemented
- frontend tests if explanation rendering is implemented
- contract tests if an API is implemented
- language review for prohibited terms
- evidence traceability review
- governance invariant review
- retained certification record
- retained rollout or observation record if exposed to users

## 10. Success Criteria

V4 succeeds when:

- users understand why a state exists
- users understand what evidence supports a state
- users understand what limitations affect a state
- users understand what freshness and trust conditions affect confidence
- users can inspect evidence without receiving advice
- users can distinguish explanation from recommendation
- degraded and refused states are clear
- governance metadata remains visible
- `ranking_applied === false` remains true
- `selection_made === false` remains true
- no new runtime surface implies best, preferred, selected, predicted, or
  recommended bullpen choice
- certification can trace each explanation to source evidence and metadata

## Recommended V4 Phase 2 Milestone

Recommended next milestone:

```text
V4 Phase 2 - Evidence And Explanation Architecture And Contract Planning
```

Phase 2 should define the architecture, data flow, contract shape, evidence
attribution model, failure modes, and test strategy for V4 without implementing
runtime behavior unless separately authorized.

Phase 2 should also decide whether V4 explanations are best modeled as:

- an extension of existing governed payloads
- a separate explanation service
- a separate explanation endpoint
- frontend-only formatting over existing metadata
- a hybrid approach with explicit certification gates

## Final Boundary

This document authorizes V4 capability definition only.

It does not authorize:

- backend implementation
- frontend implementation
- API contract changes
- database schema changes
- fatigue calculation changes
- availability calculation changes
- recommendation behavior changes
- readiness calculation changes
- trust logic changes
- freshness logic changes
- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- full production rollout
