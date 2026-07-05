# Phase 0E - Composed Read Contract

## Charter

Phase 0E builds internal reads only. The Phase 0B legal/source gate blocks all
public evidence surfacing. Public label replacement waits for a later
post-gate surface phase. Public payloads, API, UI, and copy are untouched by
every 0E branch.

This phase defines composed reads: per-subject, per-product-day bundles of
typed components. Each component cites stored Phase 0D evidence objects, and
each read derives completeness from its required components.

## Ratified Decisions

Exit-criterion reframe: Phase 0E exits with internal reads, QA, reconciliation,
and legal paper inside 0E. Public surfacing is post-gate work after the Phase
0B legal/source review and a later explicitly approved surface phase.

0E-04 reconciliation escalation policy: materially misleading legacy labels
become a deliberate legacy-engine defect decision for Nickolis, never a silent
fix and never a rushed swap.

Headline states are deferred to the 0E-05 decision record. The 0E-01 contract
contains no successor to Fresh/Stretched vocabulary and no headline, state,
label, grade, score, or rank field beyond `completeness_state`.

## Branch Map

| Branch | Scope |
| --- | --- |
| 0E-01 | Read contract and registry |
| 0E-02 | Reliever daily read |
| 0E-03 | Team daily read - in progress |
| 0E-04 | Legacy reconciliation audit |
| 0E-05 | Read QA, editorial harness, and headline decision |
| 0E-06 | Legal paper and exit |

## Binding Rules Carried Forward

- Composed reads are `internal_only`.
- No public surfaces, payload fields, UI copy, or API behavior change in 0E.
- Every component cites stored evidence rows.
- Required components control read completeness through the weakest-component
  rule.
- Optional components never degrade read completeness.
- Locked entry-band evidence stays excluded from composed reads.
- Forbidden vocabulary remains governed by Phase 0D language rules and public
  language packages.
- Public surfacing remains blocked by the legal/source gate.

## Source Documents

Phase 0E consumes these Phase 0D source-of-truth documents:

- `docs/phase0d/evidence_layer_report.md`
- `docs/phase0d/public_language_rules.md`
- `docs/phase0d/language_rules.md`
- `docs/phase0d/decision_register.md`
- `docs/phase0d/phase0d_09_decision_register.md`
- `backend/services/evidence_classification.py`
- `docs/phase0e/reliever_daily_read.md`
- `docs/phase0e/team_daily_read.md`
