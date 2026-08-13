# Bullpen Question Map Template

This template maps data families to the canonical BaseballOS bullpen questions.
It should be filled only from evidence-linked rows in the Phase 0B source
category matrix.

Do not assign a public answer until the referenced matrix rows are supported by
dated evidence and an explicit public-display decision. Default public posture
remains `INTERNAL-ONLY`.

## Question Map

| question | evidence_family | matrix_rows_used | answers_it_how | public_evidence | internal_only | unknown_behavior | guardrails | earliest_phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1: Which bullpens are fresh tonight? | Workload, rest, recent appearances | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when workload evidence is missing, stale, partial, or not finality-safe. | Descriptive only; no predictions, betting, fantasy, or confidence-score framing. | TBD in 0B-07 |
| Q2: Which bullpens are stretched? | Workload concentration, recent usage, multi-day burden | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when recent usage windows are incomplete or correction behavior is unverified. | Descriptive only; no public fatigue-score framing. | TBD in 0B-07 |
| Q3: Which teams have late-game margin? | Trusted arms, rest state, clean options, role context | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when role or trust context is unsupported by evidence. | Avoid manager-intent certainty and ranking claims. | TBD in 0B-07 |
| Q4: Which teams lack clean options? | Outing quality, traffic, command stress, roster depth | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when clean/messy appearance evidence is absent or unsupported. | Do not turn incomplete evidence into a complete-sounding read. | TBD in 0B-07 |
| Q5: Which arms are being leaned on too heavily? | Repeated usage, pitch counts, appearance frequency | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when workload thresholds or recent windows are incomplete. | Descriptive usage context only; no injury or performance prediction. | TBD in 0B-07 |
| Q6: Which arms are rested but not trusted? | Rest state, role usage, leverage proxy if safe | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when rest and role evidence cannot both be supported. | Avoid certainty about manager intent. | TBD in 0B-07 |
| Q7: Which arms are trusted but rest-restricted? | Role usage, recent workload, back-to-back and 3-in-4 context | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when trusted-role evidence or rest restriction evidence is missing. | No public fatigue-score framing; use evidence-backed usage language. | TBD in 0B-07 |
| Q8: Which teams are being pressured by short starts? | Starter innings, short-start frequency, bullpen innings burden | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when completed-game starter exposure evidence is incomplete. | Recent-context only; no upcoming starter projection. | TBD in 0B-07 |
| Q9: Which teams are pressured by injuries/IL/depth loss? | Public roster status, IL, transactions, depth context | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Mark UNKNOWN when public roster or IL evidence is missing, stale, or legally unclear. | No private injury claims; never say "healthy" or "injury-free" without explicit support. | TBD in 0B-07 |
| Q10: What changed since yesterday? | Trusted snapshots, comparable baselines, roster/workload deltas | TBD: source_category_matrix rows | TBD after source audit | TBD; default INTERNAL-ONLY | TBD | Withhold change reads when snapshots are partial, stale, incomparable, or not finality-safe. | No comparison against partial days or incompatible game windows. | TBD in 0B-07 |

## Fill Rules

- `matrix_rows_used` must cite row identifiers or anchors from the source
  category matrix.
- `answers_it_how` must explain the evidence path, not just restate the
  question.
- `public_evidence` must list what a user can inspect if the answer becomes
  public.
- `internal_only` must list evidence that may support internal classification
  but should not be displayed publicly.
- `unknown_behavior` must describe how the product fails closed when required
  evidence is unavailable.
- `earliest_phase` must remain `TBD in 0B-07` until the acquisition strategy
  branch decides priority.
