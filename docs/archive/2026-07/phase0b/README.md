# Phase 0B - Data Source Inventory & Acquisition Strategy

Phase 0B is the audit-and-decision phase for BaseballOS data acquisition. Its
job is to identify which public or permissible sources can support the V4
evidence layer before any new ingestion, schema, sync behavior, API behavior,
UI, evidence surface, product feature, or probe is implemented.

## Phase 0B Thesis

BaseballOS should decide what evidence can safely support public bullpen
intelligence before expanding the data footprint. Every source, field group,
and derived signal must be classified by source authority, update timing,
finality safety, correction behavior, legal posture, reliability, maintenance
burden, bullpen relevance, public-display posture, fail-closed behavior, and
evidence link.

Phase 0B is planning and audit only. It creates the framework for source
inventory, but it does not authorize product-code changes by itself.

## Phase 0A Context

Phase 0A - Pipeline Integrity & Data Trust - is complete. It established:

1. Product timezone authority.
2. Unknown-safe ingestion and final-game gate.
3. Stat correction propagation.
4. Reliable pitcher creation.
5. Honest processed marker lifecycle.
6. Slate completeness and coverage.
7. What Changed trusted baseline gate.
8. Sync run exclusion and atomicity.

Phase 0B starts from that foundation-first, evidence-first posture.

## Bullpen-Lens Rule

BaseballOS should stay strictly bullpen-focused, but use deeper evidence to
become the best public bullpen intelligence source.

## Product Rule

Use as much relevant baseball data as possible.
Interpret it through a bullpen lens.
Show the evidence clearly.
Avoid unsupported claims.

## Seven-Branch Phase 0B Map

- 0B-01 inventory framework and templates.
- 0B-02 existing foundation inventory.
- 0B-03 MLB Stats API core audit.
- 0B-04 MLB Stats API context audit.
- 0B-05 pitch-level source feasibility.
- 0B-06 derived evidence feasibility.
- 0B-07 acquisition strategy and matrix.

## Content Trust Rules

- Every claim must be evidence-linked or marked UNKNOWN.
- Public display defaults to INTERNAL-ONLY.
- Probe evidence must be dated and reproducible.
- Legal conclusions must cite terms or be marked needs-legal-review.
- No predictions.
- No betting language.
- No confidence-score framing.
- No public fatigue-score framing.
- Never say "healthy" or "injury-free" unless injury/IL/depth context
  explicitly supports that claim.

## Scope Guardrails

- No implementation.
- No new ingestion.
- No schema changes.
- No new evidence surfaces.
- No Daily Home.
- No Follow My Team.
- No share cards.
- No digest.
- No creator mode.
- No monetization.
- No generic MLB analytics expansion.

## Phase 0B Templates

- [`templates/source_category_matrix.md`](templates/source_category_matrix.md)
  defines the canonical source/category matrix.
- [`templates/bullpen_question_map.md`](templates/bullpen_question_map.md)
  maps evidence families to the canonical bullpen questions.
- [`templates/classification_taxonomy.md`](templates/classification_taxonomy.md)
  defines priority classes and risk/effort axes.
- [`templates/probe_protocol.md`](templates/probe_protocol.md) defines
  read-only probe rules for later audit branches.

Later Phase 0B branches should fill these templates with dated evidence, keep
unsupported fields UNKNOWN, and preserve INTERNAL-ONLY as the default public
display posture until a row is explicitly approved for public use.
