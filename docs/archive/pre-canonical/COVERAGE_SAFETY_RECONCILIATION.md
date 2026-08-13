# Coverage Safety Reconciliation

Targeted reconciliation of the read three review passes identified as answering
a different question than users hear: **Coverage Safety**. The read was
internally consistent but coverage-construction-led — a bullpen whose designated
long man was degraded fell to the **Limited** floor even when several usable
Bridge Arms could chain the innings. Live validation produced exactly this
disagreement on three clubs (Brewers, Mets, Marlins) while agreeing everywhere
construction and tonight-flexibility coincided. This branch adds a single
substitute-coverage guardrail so the floor label is reserved for genuine innings
emergencies. One read changed; the public labels are unchanged.

## What Coverage Safety should answer

> Can this bullpen absorb unexpected innings tonight?

Designated Coverage Arms remain the most valuable coverage asset and the only
path to Strong or Stable. But a pen with usable Bridge Arms behind a degraded
long man is not in an innings emergency — it has substitute capacity, and the
read should say so without overstating it.

## Audit — prior behavior

Tier gates (unchanged by this branch except the floor):

- Strong — `≥2` Coverage Arms, `≥2` clean, none Rest-Restricted/Unavailable.
- Stable — `≥2` Coverage Arms, `≥2` available (clean+watch), none Unavailable.
- Thin — `≥1` Coverage Arm with `≥1` available.
- Limited — otherwise, including every "no available designated coverage" case
  regardless of the rest of the pen.

League behavior (30-club construction archetypes × day-of states, via the
impact-review harness): with one long man degraded, **24 of 30 clubs fell to
Limited** — the red-toned floor — purely on that single arm's status. "Stable"
was structurally unreachable at a rested baseline (0 of 30).

## Logic change

A single guardrail on the floor tier:

- When the read would otherwise classify **Limited** and meaningful substitute
  capacity exists — **at least one clean Bridge Arm, or two Bridge Arms on
  watch** (a watched arm is half-usable, matching the established
  read-usability semantics) — the read is **Thin** instead, with an explanation:
  substitute capacity can chain emergency innings; it is not designated length.
- The lift is one step only. Substitute capacity can never produce Stable or
  Strong. Strong/Stable/Thin gates are untouched, so designated Coverage Arms
  remain the only source of every tier above the floor.
- Depth Arms earn nothing (no depth-credit expansion). Trust Arms earn nothing
  (a clean closer adds no multi-inning coverage).
- The sparse-data Limited Read gate is untouched and is never promoted.

## Before vs after

Labels from the live engine.

| Bullpen | Before | After | Why |
| --- | --- | --- | --- |
| Mets-style — long man down, 4 clean Bridge Arms | Limited | **Thin** | Substitute capacity exists; not an emergency. |
| Marlins-style — both long men down, 2 clean Bridge Arms | Limited | **Thin** | Same, with thinner margin honestly kept at Thin. |
| Brewers-style — long man on watch, 3 clean Bridge Arms | Thin | Thin | Unchanged — a watched long man already reads Thin. |
| Rockies archetype (Weak A) — 1 watched bridge only | Limited | Limited | One watched bridge is below the substitute bar. |
| Athletics archetype (Weak B) — bridge Rest-Restricted | Limited | Limited | No usable substitute; clean depth earns nothing. |
| Coverage-rich (Rays-style, 2-3 clean long men) | Strong | Strong | Untouched. |
| Sparse data | Limited Read | Limited Read | Untouched gate. |

League impact (same 30-club × 3-state harness): every change is
**Limited → Thin**. Strong counts identical (6 rested / 1 watched / 0 down);
Stable counts identical (0 / 5 / 1). At the "long man down" state the floor
empties (24 → 0 Limited) into Thin — the precise failure mode the validation
flagged, and nothing else moves.

Two observation-harness profiles change with the rule, both because a clean
Bridge Arm stands behind zero available designated coverage: Interesting A
(trust-rich, depth-thin) and Interesting B (depth-rich, trust gassed) now read
Thin rather than Limited. Weak A and Weak B remain Limited.

## Validation scenarios

- **A — no Coverage Arms, no substitute capacity:** Limited. ✓
- **B — Coverage Arm down, meaningful substitutes:** Thin, explanation names the
  bridge fallback. ✓
- **C — Coverage Arm down, five clean bridges:** Thin, never Stable. ✓
- **D — coverage-rich pen:** Strong, unchanged. ✓
- **E — weak pen, no usable substitutes:** Limited, unchanged. ✓
- **F/G — Mets-style and Marlins-style:** Limited → Thin. ✓
- **H/I — Rockies-style and Athletics-style:** unchanged. ✓
- Guardrail never fires when a designated Coverage Arm is available. ✓
- Two watched bridges clear the bar; one does not. ✓

## Explainability

The read carries `cleanBridgeArms`, `watchBridgeArms`, and a
`substituteCoverageApplied` flag in `supportingCounts`. A lifted read states
plainly that Bridge Arms are covering emergency innings and that this is
substitute capacity, not designated length; the bullpen-shape strip appends the
same caveat. No score, weight value, or band is exposed.

## Scope and constraints

- Changed `coverageSafety` in `frontend/src/utils/teamBullpenScoring.js` and the
  coverage line of `shortShapeExplanation` in
  `frontend/src/components/bullpen/board/teamBullpenStoryView.js` (so a lifted
  read explains itself).
- Trust Arm Availability, Clean Options, Bullpen Pressure, and Depth Safety are
  untouched (verified by their existing tests).
- No backend, schema, sync, availability/fatigue engine, or page-structure
  changes. Public labels and concept vocabulary preserved.
- The broader flexibility models from the impact review (always-on bridge
  credit, multi-inning capability weighting, depth fallback credit) are
  intentionally **not** implemented. Capability-aware credit remains gated on a
  per-arm multi-inning signal that does not exist yet.

## Recommendation — was Coverage Safety flawed, or misread?

**Misread, by design.** The read faithfully measured designated-long-man
availability, but every surface around it (a strip titled "Today's Bullpen
Shape," tonight-state sibling reads, game-state vocabulary) promised a day-of
answer, so the Limited floor read as an innings emergency it did not mean. The
guardrail reserves the floor for pens that genuinely have no usable length —
designated or substitute — which is the only claim a baseball reader was ever
going to take from it. Re-validate against live slates before any further
flexibility evolution.
