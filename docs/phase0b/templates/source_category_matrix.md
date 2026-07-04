# Source Category Matrix Template

This template is the canonical Phase 0B source/category matrix. Later audit
branches should copy or extend rows from this structure, but the column names
must stay stable unless a later Phase 0B decision explicitly revises the
template.

Default public display posture: `INTERNAL-ONLY`.

`evidence_link` is mandatory. Rows without evidence cannot advance beyond
`UNKNOWN` / `INTERNAL-ONLY` / `AUDIT-ONLY-0B`.

## Matrix

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | none_found | TBD | UNKNOWN | UNKNOWN | UNKNOWN | TBD | TBD | TBD | needs-legal-review | TBD | do-not-store | UNVERIFIED | medium | contextual | INTERNAL-ONLY | TBD before advancement | AUDIT-ONLY-0B | REQUIRED | 0B-xx |

## Legal Value Lists

Use only these values for enumerated columns.

### `source`

- `statsapi_v1`
- `statsapi_v11_live`
- `savant_statcast`
- `derived_internal`
- `none_found`
- `paid_optional:<name>`

### `availability`

- `available`
- `derivable`
- `partial`
- `unavailable`
- `UNKNOWN`

### `update_timing`

- `live`
- `at-final`
- `final+lag(observed)`
- `daily`
- `UNKNOWN`

### `finality_safe`

- `yes`
- `no(live)`
- `corrected-after-final`
- `UNKNOWN`

### `legal_posture`

- `terms-cited-ok`
- `tolerated-undocumented`
- `restricted`
- `needs-legal-review`
- `paid-only`

### `storage_risk`

- `derived-aggregate-ok`
- `raw-cache-risk`
- `do-not-store`

### `reliability_grade`

- `A(probe-verified stable)`
- `B`
- `C`
- `UNVERIFIED`

### `maintenance_burden`

- `low`
- `medium`
- `high`

### `bullpen_relevance`

- `core`
- `supporting`
- `contextual`
- `out-of-lens`

### `public_display`

- `PUBLIC-CANDIDATE`
- `INTERNAL-ONLY`
- `NEVER`
- `UNKNOWN`

### `priority_class`

- `AUDIT-ONLY-0B`
- `FOUNDATION-0C`
- `EVIDENCE-0D`
- `LATER-V4`
- `OPTIONAL-PAID-FUTURE`
- `DO-NOT-USE`
- `UNKNOWN-UNTIL-LEGAL`

## Advancement Rules

- A row must keep `public_display` as `INTERNAL-ONLY` until evidence, legal
  posture, storage risk, and fail-closed behavior are explicitly reviewed.
- A row with missing or placeholder `evidence_link` must keep `availability` as
  `UNKNOWN`, `public_display` as `INTERNAL-ONLY`, and `priority_class` as
  `AUDIT-ONLY-0B`.
- A row with `legal_posture` of `needs-legal-review`, `restricted`, or
  `paid-only` cannot become `PUBLIC-CANDIDATE` during Phase 0B.
- A row with missing fail-closed behavior cannot advance beyond
  `AUDIT-ONLY-0B`.
