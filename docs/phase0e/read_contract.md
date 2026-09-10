# Phase 0E Read Contract

## Purpose

A composed read is the layer above the Phase 0D evidence contract. It bundles
stored evidence into internal-only, citable components for one subject and one
product date. It does not conclude health, role, quality, forecast, usage
intent, betting value, or public status.

0E-01 ships the contract and registry only. It registers no production read
type, adds no sync stage, performs no reconciliation, and changes no public
surface.

## Model Semantics

`ComposedRead` stores one internal read instance:

- `read_key`: canonical identity for read type, version, subject, and product
  date.
- `read_type` and `read_version`: registry identity.
- `subject_type`: `pitcher_day` or `team_day`.
- `subject_id`, `subject_key`, and `product_date`: read subject basis.
- `completeness_state`: complete, partial, unknown, conflict, or withheld.
- `reason_codes`, `limitations`, and `component_summary`: derived from
  components.
- `posture`: always `internal_only`.
- provenance and recompute columns mirror the evidence-contract pattern.

`ComposedReadComponent` stores each registered component instance:

- `component_name`
- `required`
- `component_state`: complete, partial, unknown, conflict, withheld, or absent
- component reason codes and limitations

`ComposedReadEvidenceCitation` links a component to a stored evidence object:

- `evidence_object_id`
- `citation_role`
- `cited_completeness_state`

The cited completeness state is captured at composition time so later evidence
supersession can be detected.

## Registry Rules

Every read type is registered as a `ReadType` with:

- `read_type`
- `read_version`
- `subject_type`
- `plain_language_definition`
- component specs
- classification

Every component spec has:

- `name`
- `required`
- `allowed_evidence_types`
- `plain_language_definition`

Registry validation enforces:

- every read type carries exactly one classification
- Phase 0E read classifications can only be `PERMANENTLY_INTERNAL` or
  `INTERNAL_ONLY_FOR_NOW`
- public-facing evidence classifications fail for read types
- allowed evidence types must exist in the Phase 0D evidence-rule registry
- `appearance_entry_band` and `pitcher_entry_band_distribution` are excluded
  from composed reads
- duplicate `(read_type, read_version)` registrations fail
- unregistered read types cannot build reads
- read and component names cannot use forbidden vocabulary from Phase 0D
  language rules or the 0E no-headline rule

The production registry is empty in 0E-01. Later branches register read types
explicitly.

## Degradation Calculus

Read completeness is the weakest required component.

| Component state | Severity |
| --- | ---: |
| complete | 0 |
| partial | 1 |
| unknown | 2 |
| conflict | 3 |
| withheld | 4 |

An absent required component maps to `unknown` and adds
`component_absent`.

Optional components never degrade read completeness. They appear in
`component_summary` and may contribute limitations or notes only.

Conflict in any required component propagates to the read and is never averaged
away.

## Recompute Semantics

Composed reads cite evidence objects through foreign keys. When cited evidence
is superseded or invalidated, dependent reads can be marked
`recompute_needed` by bounded fan-out over those citation rows.

Rebuilding the same canonical read key stages a new current read and marks the
prior read `superseded`, with provenance and `superseded_by_read_id` retained.

No sync stage is added in 0E-01. The recompute helper is contract wiring for
0E-02 and later builders.

## No-Headline-State Rule

The read contract has no field for headline states, state labels, grades,
scores, ranks, or read labels. `completeness_state` is the only state field and
it describes evidence completeness, not public meaning.

Whether evidence-defined headline states should exist is deferred to the 0E-05
decision record.

## Phase 0D Inputs

Phase 0E treats these inputs as binding:

- `docs/phase0d/evidence_layer_report.md`
- `docs/phase0d/public_language_rules.md`
- `docs/phase0d/language_rules.md`
- `docs/phase0d/decision_register.md`
- `docs/phase0d/phase0d_09_decision_register.md`
- `backend/services/evidence_classification.py`

The Phase 0D legal/source gate remains closed for public surfacing.
