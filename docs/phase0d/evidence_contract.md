# Phase 0D Evidence Contract

## Evidence Object

An evidence object is the only allowed output shape for Phase 0D interpretation
work. It must contain:

- `evidence_type`
- `subject_type`
- `subject_id` or `subject_key`
- `product_date`
- `claim_template_id`
- `rendered_claim`
- `rule_id`
- `rule_version`
- `typed_cited_inputs`
- `computation_trace`
- `completeness_state`
- `reason_codes`
- `limitations`
- `posture`
- source provenance
- correction and recompute metadata

The object does not contain a generic score, grade, rank, or color field.

## Subjects

The subject fields support pitcher, team, team-game, and product-date subjects:

- pitcher: `subject_type=pitcher`, `subject_id=<pitcher id>`
- team: `subject_type=team`, `subject_id=<team id>`
- team-game: `subject_type=team_game`, `subject_key=<team id>:<game pk>`
- product-date: `subject_type=product_date`, `subject_key=<date>`

## Citations

Every claim needs typed citations. A citation points to a stored source row and
records:

- source family
- source table
- source row identity
- cited fields
- cited values
- provenance

The citation list is copied onto the evidence object and also stored as
`evidence_citations` rows so upstream source corrections can find dependent
evidence in bounded batches.

## Readiness Gates

Before emitting evidence, the builder checks the rule's required source
families against internal source readiness. Missing or non-ready families create
a withheld evidence object with a reason code.

Fail-closed behavior:

- no registered rule -> no evidence
- unready input family -> withheld object with reason
- null required input -> unknown object with reason
- contradictory inputs -> conflict object with citations
- uncleared source posture -> withheld object with reason

## Rule Versioning

The evidence row stores both `rule_version` and a rule definition hash. A later
rule version creates new visible evidence history; it must not silently rewrite
older objects.

## Recompute Hooks

The 0D-01 implementation provides a bounded recompute marker:

1. Find citations that reference a corrected source table and row.
2. Mark dependent evidence rows `recompute_needed`.
3. Preserve invalidation source table, source row, reason code, timestamp,
   correction source, correction count, and sync run when available.

Full family-specific recompute orchestration is intentionally deferred to later
0D branches.

## Public Isolation

Evidence objects are internal storage and diagnostics only in Phase 0D. Public
payloads, boards, snapshots, What Changed, frontend UI, and public copy must
not consume `evidence_objects`, `evidence_citations`, or evidence services in
0D-01.
