# Recommendation Engine V2 Phase 2 Context Assembly

## Status

Recommendation Engine V2 Phase 2 Backend Context Assembly Layer is complete.

This phase created backend-only assembly logic that maps existing BaseballOS
availability, workload, and trust evidence into the V2 domain objects created
in Phase 1. It does not expose V2 API behavior, create frontend behavior,
modify routes, rank pitchers, select pitchers, predict outcomes, or change
Recommendation Engine V1.

## Scope Completed

Implemented backend assembly surfaces:

- `assemble_v2_context`
- `V2ContextAssembly`

Implementation location:

- `backend/recommendation/v2_assembly.py`

Test coverage location:

- `backend/tests/test_recommendation_v2_context_assembly.py`

The assembler produces:

- `RecommendationContext`
- `BullpenState`
- `TeamBullpenContext`
- `CandidateGroup` collections

## Source Evidence Used

The assembly layer uses existing backend evidence already present in
BaseballOS:

- pitcher identity
- team identity
- availability status
- availability confidence
- availability data state
- availability reasons
- availability limitations
- workload input availability
- latest game date when supplied
- data-through metadata when supplied
- last successful sync metadata when supplied
- latest sync status when supplied
- high-leverage evidence flag when supplied

If evidence is not supplied, the assembler records that absence through
limitations, degraded data state, or refusal metadata instead of inventing
context.

## Objects Assembled

### RecommendationContext

The assembler creates trust context with:

- confidence
- data state
- freshness metadata
- limitations
- explanations
- refusal reasons
- generated timestamp when supplied

### BullpenState

The assembler creates bullpen state with:

- total bullpen inventory
- availability status counts
- candidate group count
- confidence distribution
- data-state distribution
- workload evidence summary
- descriptive stress indicators

### TeamBullpenContext

The assembler creates team context with:

- leverage evidence inventory when supplied
- workload distribution summary
- readiness distribution summary
- descriptive stress indicators
- leverage evidence limitations when unavailable

### CandidateGroup

The assembler creates neutral candidate groups by availability status.

Ordering remains neutral:

- groups use availability status as the grouping dimension
- candidates preserve input order within each group
- ordering is documented as input-order preservation, not preference

## Governance Compliance

The completed assembly layer preserves the required V2 guarantees:

```text
ranking_applied = false
selection_made = false
```

The assembler does not create:

- ranked candidate lists
- selected pitcher fields
- recommended pitcher fields
- winner fields
- priority fields
- score ordering
- automated decisions

Source evidence containing forbidden ranking or selection fields causes the
assembler to fail closed and emit refusal metadata rather than silently
assembling unsafe context.

## Fail-Closed Behavior

The assembler fails closed or degrades context when:

- no candidate evidence is supplied
- source evidence contains forbidden ranking or selection fields
- data state is missing, stale, incomplete, historical, or unknown
- trust metadata is insufficient to support current context

Fail-closed output preserves V2 object shape and keeps:

```text
ranking_applied = false
selection_made = false
```

## V1 Preservation

Recommendation Engine V1 remains unchanged.

This phase did not modify:

- V1 recommendation engine behavior
- V1 recommendation API routes
- V1 candidate evaluation semantics
- V1 category assignment semantics
- V1 frontend behavior

The V1 guarantees remain active:

```text
ranking_applied = false
selection_made = false
```

## Explicit Non-Claims

This phase does not claim:

- V2 API support exists
- V2 frontend support exists
- user-facing V2 recommendation behavior exists
- pitcher ranking exists
- pitcher selection exists
- performance prediction exists
- injury prediction exists
- save prediction exists
- game outcome prediction exists

## Phase 3 Readiness Boundary

Future V2 Phase 3 work may build on the context assembly layer only if it
preserves the same governance rules and remains backend-only unless separately
approved. Any future grouping expansion must remain neutral and must not create
ranking, selection, or user-visible recommendation behavior.
