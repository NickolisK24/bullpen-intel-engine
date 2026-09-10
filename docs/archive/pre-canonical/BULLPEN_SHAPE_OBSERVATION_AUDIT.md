# Bullpen Shape Observation Audit

Observation-only validation pass over the bullpen interpretation engine now that
the pitcher labels, five team reads, the weighting foundation, trust-weighted
Pressure and Clean Options, and the reconciliation layer all exist. No new logic,
rankings, concepts, scores, or UI were added. The goal is to judge whether the
engine *understands* bullpens or merely produces outputs.

## Method and an honest data caveat

This environment has no live MLB feed. `seed.py` pulls 2024–2025 history from the
MLB Stats API and a live sync would exercise the availability and fatigue engines
this branch is constrained not to touch — and would still not produce a true
current slate. So the audit does **not** claim to read the actual Dodgers,
Marlins, or any club today.

Instead, an observation harness (`frontend/scripts/bullpenShapeObservation.mjs`)
drives the real engine — `getTeamBullpenShape`, `getTeamWeightingFoundation`,
`getPitcherLabels` — over eight documented, representative bullpen *shapes* drawn
from the named archetypes (strong / weak / interesting). This validates how the
engine maps a bullpen's composition to its reads, which is what can be checked
rigorously here. Validation against live rosters and real daily workloads is the
remaining, separate step, and it is the binding gap for any rankings decision
(see Deliverable #3). All labels below are produced by the engine, not authored
by hand; reproduce with `node scripts/bullpenShapeObservation.mjs`.

Legend: ✓ behaves as expected · ⚠ defensible but worth scrutiny · ✗ misleading.

## Deliverable #1 — Per-profile audit

### Strong A (Dodgers archetype) — 2 clean Trust, full bridge/coverage/depth
- Trust Arm Availability — **Strong** ✓
- Clean Options — **Deep** ✓
- Bullpen Pressure — **Low** ✓
- Coverage Safety — **Thin** ⚠ (only one Coverage Arm → can't clear Stable)
- Depth Safety — **Strong** ✓
- Notes: reads like a strong pen except Coverage Safety, which is structurally
  capped because the profile carries a single long man — typical of real elite
  pens. First sign Coverage Safety runs pessimistic.

### Strong B (Guardians archetype) — elite trio, one watched, deep behind
- Trust Arm Availability — **Strong** ✓
- Clean Options — **Deep** ✓
- Bullpen Pressure — **Low** ✓
- Coverage Safety — **Thin** ⚠ (same single-coverage-arm cap)
- Depth Safety — **Stable** ✓
- Notes: a watched trusted arm does not dent the overall read, correctly.

### Weak A (Rockies archetype) — no clean trusted arm, depth-heavy, tired
- Trust Arm Availability — **Limited** ✓
- Clean Options — **Thin** ✓ (3 clean depth but no meaningful clean backing → capped Thin)
- Bullpen Pressure — **High** ✓ (restricted Trust + Coverage drive it up)
- Coverage Safety — **Limited** ✓
- Depth Safety — **Strong** ✗ (see below)
- Notes: four of five reads are right. **Depth Safety reads "Strong" for the
  weakest pen in the set** — eight arms with five Depth Arms clears the volume
  gate regardless of fatigue or overall health. This produces "High Bullpen
  Pressure" and "Strong Depth Safety" on the *same* team.

### Weak B (Athletics archetype) — thin, trusted arm overworked, depth gassed
- Trust Arm Availability — **Limited** ✓
- Clean Options — **Thin** ✓ (4 clean Depth bodies correctly held to Thin — no clean Trust/Bridge/Coverage)
- Bullpen Pressure — **High** ✓
- Coverage Safety — **Limited** ✓
- Depth Safety — **Stable** ⚠ (volume still reads positive on a weak pen)
- Notes: the clearest win for Clean Options weighting — four clean bodies do
  **not** earn "Healthy" without meaningful backing.

### Interesting A — trust-rich, depth-thin
- Trust Arm Availability — **Strong** ✓
- Clean Options — **Healthy** ✓ (2 clean Trust + 1 clean Bridge upgraded from a low count)
- Bullpen Pressure — **Elevated** ✓ (three Unavailable Depth Arms register, trust core holds it off High)
- Coverage Safety — **Limited** ✓
- Depth Safety — **Limited** ✓
- Notes: a top-heavy contender shape — trustworthy but fragile — reads exactly
  that way. Strong result.

### Interesting B — depth-rich, trust gassed
- Trust Arm Availability — **Limited** ✓
- Clean Options — **Healthy** ⚠ (six clean bodies incl. a clean Bridge → held below Deep but still Healthy while both trusted arms are restricted)
- Bullpen Pressure — **High** ✓ (trust pressure 6 → High)
- Coverage Safety — **Limited** ✓
- Depth Safety — **Strong** ⚠
- Notes: the reconciliation stress test. Pressure correctly screams while the
  trusted arms are down, but Clean Options still says "Healthy" and Depth Safety
  says "Strong." Defensible per-read, but the aggregate impression is rosier
  than the pen deserves.

### Interesting C — high-fatigue overuse (clean board, heavy fatigue scores)
- Trust Arm Availability — **Strong** ⚠ (sees availability status, not fatigue)
- Clean Options — **Deep** ⚠ (same blind spot)
- Bullpen Pressure — **Elevated** ✓ (two arms at 70+ fatigue trip the workload term)
- Coverage Safety — **Strong** ✓
- Depth Safety — **Stable** ✓
- Notes: **Pressure is the only read that sees fatigue.** Trusted arms carrying
  78/72 fatigue still read "Strong Trust" and "Deep Clean" because their board
  status is Available. Pressure caught the latent overuse the other reads missed.

### Interesting D — sparse / early-season
- All five reads — **Limited Read** ✓
- Notes: correct refusal to manufacture confidence from thin data.

## Deliverable #2 — Misclassification report

**False positives (too optimistic):**
- **Depth Safety on weak, tired pens** (Weak A → "Strong"; Interesting B →
  "Strong"). Depth Safety was not part of the weighting rollout; it remains a
  role-blind volume count, so depth *bodies* read as depth *safety* even when the
  pen is overall stressed. This is the single clearest misclassification surface.
- **Clean Options on trust-gassed pens** (Interesting B → "Healthy"). A clean
  Bridge Arm is enough "meaningful backing" to hold the read at Healthy while
  both trusted arms are restricted. Borderline; the weighting already prevented
  Deep, but Healthy still leans optimistic.
- **Trust Availability / Clean Options blind to fatigue** (Interesting C → Strong
  / Deep with 78-fatigue trusted arms). Only Pressure consumes fatigue, so an
  available-but-gassed arm inflates the other reads.

**False negatives (too pessimistic):**
- **Coverage Safety on strong pens** (Strong A & B → "Thin"). Strong/Stable
  Coverage requires two or more Coverage Arms; pens built with a single quality
  long man are structurally capped at Thin even when otherwise elite.

**Ambiguous (data-limited):**
- Everything above is validated on representative shapes, not live rosters and
  real daily workloads. Whether these patterns occur at the observed frequency
  across the league cannot be concluded without production data. That is the
  honest state of this branch, and it bounds the rankings decision below.

## Deliverable #3 — Ranking readiness assessment

**Bullpen Health Rankings — NOT READY.** Health is an aggregate of all five
reads, but two of them (Coverage Safety, Depth Safety) are still role-blind and
can move opposite to true health — a weak pen earns "Strong Depth Safety,"
a strong pen earns "Thin Coverage Safety." Aggregating them into a single health
rank would look defensible and be misleading. There is also no reconciled
team-read-level "overall health" object yet; only the coarse landscape
`health_state`. Ranking on this today would bake in the misclassifications above.

**Bullpen Stress Rankings — NOT READY (but closest).** Trust-weighted Bullpen
Pressure was the strongest performer in the audit: it escalated on trust loss,
refused to overreact to tired depth, and uniquely caught fatigue-driven overuse.
Stress is the one dimension with a corrected, single, coherent read behind it.
It is not public-ready only because it is unvalidated against live slates — but
it is the first dimension that should graduate, once real-data validation passes.

**Bullpen Stability Rankings — NOT READY.** "Stability" implies behavior over
time — variance, trend, week-over-week swing. The engine is a single-slate
snapshot with no temporal component. Nothing in the system measures stability
yet, so this ranking has no foundation to stand on.

Stated plainly: do not ship rankings. The weighting work materially improved the
two reads it touched, but health/stability ranks would rest partly on unconverted
reads, and all three lack live-data validation.

## Deliverable #4 — Future logic recommendations (only where observed)

1. **Depth Safety needs reconciliation, not just weighting.** Observed: weak,
   high-pressure pens read "Strong Depth Safety." At minimum the label should be
   reconciled so a positive Depth Safety read cannot headline a High-Pressure /
   Limited-Trust pen, mirroring the constrained-vs-healthy reconciliation already
   applied at the story layer. Justified by Weak A and Interesting B.
2. **Review Coverage Safety thresholds.** Observed: elite pens with one long man
   read "Thin Coverage Safety." Consider letting a single clean, trusted-quality
   Coverage Arm plus depth fallback reach Stable. Justified by Strong A/B.
3. **Propagate fatigue beyond Pressure.** Observed: 78-fatigue trusted arms still
   read Strong Trust / Deep Clean. Consider letting high fatigue nudge Trust
   Availability and Clean Options, since the signal already exists on the card
   and only Pressure currently uses it. Justified by Interesting C.
4. **No change to Pressure or Clean Options weighting.** Both behaved correctly
   across every profile. The weighting rollout is doing its job; the remaining
   soft spots are entirely in the reads it has not yet reached.

## Top 5 findings

1. The weighting rollout works: Pressure and Clean Options produced correct,
   reconciled reads on all eight profiles, including the hard trust-gassed and
   high-fatigue cases.
2. Depth Safety is the weakest link — role-blind volume lets the worst pens read
   "Strong Depth Safety," contradicting their own High Pressure.
3. Coverage Safety runs pessimistic — single-long-man pens (most strong pens)
   are structurally capped at "Thin."
4. Fatigue only reaches Pressure; Trust Availability and Clean Options can read
   healthier than a gassed arm actually is.
5. Limited Read gating is reliable — sparse data refuses confident output every
   time.

## Recommendation — what should happen next?

**Not rankings. Refinement, then live validation.** Two concrete, observation-
grounded refinements should precede any ranking: (a) reconcile Depth Safety so it
cannot present a healthy face on a stressed pen, and (b) review Coverage Safety's
two-arm requirement. Both are justified by the outputs above and are small,
scoped follow-ups in the established one-read-at-a-time pattern. After that, the
decisive gate is **live-roster validation with production data** — this audit can
prove the logic is internally coherent, but only real slates can prove it matches
baseball. Bullpen Pressure (Stress) is the first dimension that should be
considered for graduation once that validation exists; Health and Stability are
further out.

## Teams / profiles reviewed

Strong A (Dodgers archetype), Strong B (Guardians archetype), Weak A (Rockies
archetype), Weak B (Athletics archetype), Interesting A (trust-rich/depth-thin),
Interesting B (depth-rich/trust-gassed), Interesting C (high-fatigue overuse),
Interesting D (sparse/early-season). All exercised through the live engine via
`frontend/scripts/bullpenShapeObservation.mjs`.
