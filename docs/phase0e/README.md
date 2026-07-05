# Phase 0E - Composed Read Contract

## Charter

Phase 0E builds internal reads only. The Phase 0B legal/source gate blocks all
public evidence surfacing. Public label replacement waits for a later
post-gate surface phase. Public payloads, API, UI, and copy are untouched by
every 0E branch.

This phase defines composed reads: per-subject, per-product-day bundles of
typed components. Each component cites stored Phase 0D evidence objects, and
each read derives completeness from its required components.

## Binding Rules

- QA, renderer, decision records, and exit preparation only.
- No migrations in 0E-05.
- No new evidence rules in 0E-05.
- No headline-state implementation before an explicit post-0E-06 decision by
  Nickolis.
- No member-read rollup contract extension unless the closed decision is
  reopened under the named preconditions in
  `docs/phase0e/member_read_rollup_decision.md`.
- No read-citation mechanism.
- No public labels, public copy, payload fields, route behavior, API behavior,
  UI behavior, or product behavior changes.
- Legacy modules stay untouched.
- Classification tallies stay fixed at 44 PC, 9 EL, 4 IO, and 8 PI over 65
  rules.
- Alembic head stays unchanged from the 0E-04 audit head.

## Ratified Decisions

Exit-criterion reframe: Phase 0E exits with internal reads, QA, reconciliation,
and legal paper inside 0E. Public surfacing is post-gate work after the Phase
0B legal/source review and a later explicitly approved surface phase.

0E-04 reconciliation escalation policy: material divergence rows become
recommendations to Nickolis for legacy-engine defect review, never silent fixes,
freezes, or rushed swaps.

0E-05 headline-state ruling: DEFER-WITH-STRUCTURE. See
`docs/phase0e/headline_state_decision.md`.

0E-05 member-read rollup ruling: REJECT-AND-CLOSE. See
`docs/phase0e/member_read_rollup_decision.md`.

## Branch Map

| Branch | Notes |
| --- | --- |
| 0E-01 | Complete: read contract and registry. |
| 0E-02 | Complete: reliever daily read. |
| 0E-03 | Complete: team daily read. |
| 0E-04 | Complete: legacy reconciliation audit. |
| 0E-05 | This branch: read QA, editorial harness, renderer, and decision records. |
| 0E-06 | Next: legal paper and exit. |

## 0E-06 Inputs Inventory

The legal paper consumes these 0E-05 and carry-forward inputs:

- QA harness results.
- `docs/phase0e/headline_state_decision.md`.
- `docs/phase0e/member_read_rollup_decision.md`.
- `docs/phase0e/editorial_review_guide.md`.
- `backend/scripts/render_read_review_packet.py`.
- Reconciliation audit tables from the production observation window.
- Evidence classification registry and unchanged tallies.
- Phase 0D public-language packages.

## Source Documents

Phase 0E consumes these Phase 0D and Phase 0E source-of-truth documents:

- `docs/phase0d/evidence_layer_report.md`
- `docs/phase0d/public_language_rules.md`
- `docs/phase0d/language_rules.md`
- `docs/phase0d/decision_register.md`
- `docs/phase0d/phase0d_09_decision_register.md`
- `backend/services/evidence_classification.py`
- `docs/phase0e/read_contract.md`
- `docs/phase0e/reliever_daily_read.md`
- `docs/phase0e/team_daily_read.md`
- `docs/phase0e/legacy_read_reconciliation_audit.md`
- `docs/phase0e/qa_fixture_corpus.md`
- `docs/phase0e/editorial_review_guide.md`
- `docs/phase0e/headline_state_decision.md`
- `docs/phase0e/member_read_rollup_decision.md`
