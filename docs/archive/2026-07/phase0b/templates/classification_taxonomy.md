# Classification Taxonomy

This taxonomy defines how Phase 0B rows should be classified before later work
can decide implementation order. It does not adopt any source by itself.

## Priority Classes

| priority_class | Definition |
| --- | --- |
| `AUDIT-ONLY-0B` | Evidence belongs in Phase 0B documentation only. It cannot drive ingestion, API behavior, UI, or public claims yet. |
| `FOUNDATION-0C` | Evidence may be a candidate for the reliever appearance foundation after source, legal, finality, correction, and fail-closed questions are resolved. |
| `EVIDENCE-0D` | Evidence may be a candidate for pitch-level or pitch-trend feasibility work after Phase 0B source review is complete. |
| `LATER-V4` | Evidence may matter to V4, but it should wait until higher-priority foundation and evidence phases are complete. |
| `OPTIONAL-PAID-FUTURE` | Evidence appears useful but depends on a paid source or optional future acquisition path. |
| `DO-NOT-USE` | Evidence should not be used because it is out of scope, unreliable, legally restricted, unsafe to store, or not bullpen-relevant. |
| `UNKNOWN-UNTIL-LEGAL` | Evidence cannot advance until terms, attribution, storage, and public-display rights are reviewed. |

## Risk And Effort Axes

Each axis must be scored as `low`, `medium`, or `high`.

| Axis | What it measures | Scores |
| --- | --- | --- |
| `difficulty` | Expected engineering and operational complexity after Phase 0B. | `low`, `medium`, `high` |
| `public_trust_value` | How much the evidence would improve public trust in a bullpen read. | `low`, `medium`, `high` |
| `bullpen_relevance` | How directly the evidence answers bullpen questions. | `low`, `medium`, `high` |
| `legal_source_risk` | Terms, attribution, paid-access, storage, and redistribution risk. | `low`, `medium`, `high` |
| `freshness_risk` | Risk that update timing creates stale or misleading reads. | `low`, `medium`, `high` |
| `correction_risk` | Risk that post-final changes or source corrections create hidden contradictions. | `low`, `medium`, `high` |
| `maintenance_burden` | Ongoing cost to keep the source reliable and explainable. | `low`, `medium`, `high` |
| `testability` | How easily the source behavior and fail-closed rules can be verified. | `low`, `medium`, `high` |

## Classification Row Template

| field_group | priority_class | difficulty | public_trust_value | bullpen_relevance | legal_source_risk | freshness_risk | correction_risk | maintenance_burden | testability | required_fail_closed_behavior | evidence_link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TBD | AUDIT-ONLY-0B | medium | medium | medium | high | medium | medium | medium | medium | TBD before advancement | REQUIRED |

## Required Fail-Closed Rule

Every row must name its required fail-closed behavior. If fail-closed behavior
is missing or TBD, the row cannot advance past `AUDIT-ONLY-0B`.

Fail-closed behavior should say what BaseballOS does when evidence is missing,
stale, partial, legally unclear, not finality-safe, or contradicted by a later
correction. Acceptable outcomes include marking the field `UNKNOWN`,
withholding the read, keeping the row `INTERNAL-ONLY`, or assigning
`DO-NOT-USE`.
