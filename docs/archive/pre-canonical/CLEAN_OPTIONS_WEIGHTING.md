# Clean Options Weighting

Second controlled rollout of the weighting foundation, following trust-weighted
pressure. Clean Options stays an honest, visible, count-based concept — the raw
number of clean arms is unchanged and still shown — but its *interpretation* now
understands that some clean options matter more than others. One read changed;
the public labels are unchanged.

## Product principle

Five clean Depth Arms is not the same Clean Options read as two clean Trust Arms
plus a clean Bridge Arm, even though both are "available relievers." The raw
count answers "how many clean arms exist?" The interpretation now answers "how
many clean options actually matter?"

## What stayed honest

- The raw clean count (`cleanOptionCount`) is unchanged, still computed the same
  way, still in `supportingCounts`, and still named first in the explanation.
- No score, percentage, weight value, band, or ranking is exposed.
- The four public labels are unchanged: Deep / Healthy / Thin / Very Thin Clean
  Options, plus the existing sparse-data Limited Read gate.

## How the interpretation changed

The raw count sets an honest **base tier** (you can never read deeper than your
body count supports). Three weighting adjustments, consuming the clean
composition by role from the foundation's influence hierarchy (Trust 3, Bridge 2,
Coverage 2, Depth 1):

1. **Trust-backed upgrade** — two clean Trust Arms lift a low body count up to
   Healthy. Two trusted options matter more than the count alone suggests.
2. **Deep requires a trust core** — the strongest tier (Deep) is reserved for a
   bullpen with at least two clean Trust Arms. Depth volume alone cannot reach
   it; such a pen caps at Healthy.
3. **Meaningful-backing floor** — a bullpen whose only clean arms are Depth Arms
   (no clean Trust, Bridge, or Coverage Arm) cannot exceed Thin, regardless of
   how many rested bodies it has.

Bridge and Coverage Arms count as meaningful clean backing; Depth Arms alone do
not.

## Before vs after audit

Labels computed from the module ("before" = prior count-only thresholds; raw
count shown to confirm it is preserved).

| Bullpen | Raw clean | Before | After | Why |
| --- | --- | --- | --- | --- |
| 5 clean Depth, trust restricted/unavailable (A) | 5 | Healthy | **Thin** | Bodies, not meaningful options; count still shows 5. |
| 2 clean Trust + 1 clean Bridge (B) | 3 | Thin | **Healthy** | A real trusted core outweighs a lower body count. |
| 1 clean Trust + 5 clean Depth (C) | 6 | Deep | **Healthy** | Genuine middle ground; one trust arm is not a Deep core. |
| 3 clean Trust + Bridge + Coverage + Depth (D) | 7 | Deep | Deep | Strongest read, earned by a real trust core. |
| 2 Trust Unavailable + 6 clean others (E) | 6 | Deep | **Healthy** | Lost trust core downgrades a six-deep clean group. |
| Pure 6 clean Depth | 6 | Deep | **Thin** | High depth alone cannot manufacture the strongest read. |
| Sparse / mostly Limited Read (F) | — | Limited Read | Limited Read | Unchanged gate. |

The key inversion: before, the depth-rich Scenario A (Healthy) outranked the
trust-led Scenario B (Thin). After, B (Healthy) correctly outranks A (Thin) — the
raw counts are untouched, only the interpretation is corrected.

## Validation scenarios

- **A — 5 clean Depth, 0 clean Trust:** raw count stays 5; reads Thin, not overly
  healthy.
- **B — 2 clean Trust + 1 clean Bridge:** reads Healthy, stronger than A.
- **C — 1 clean Trust + many clean Depth:** reads Healthy — middle ground.
- **D — several clean Trust:** reads Deep — strongest.
- **E — many clean arms, trust group unavailable:** downgraded from a raw-count
  Deep to Healthy.
- **F — sparse data:** Limited Read.

## Explainability

Each read carries the raw clean count plus the clean composition by role
(`cleanTrustArms`, `cleanBridgeArms`, `cleanCoverageArms`, `cleanDepthArms`) and a
`meaningfulCleanBacking` flag. The explanation names the count and the role split,
so a user can see why a six-clean bullpen reads Healthy instead of Deep without
any hidden math.

## Scope and constraints

- Changed only `cleanOptions` in `frontend/src/utils/teamBullpenScoring.js`.
- Trust Arm Availability, Bullpen Pressure, Coverage Safety, and Depth Safety are
  untouched.
- No backend, schema, sync, availability/fatigue engine, or page-structure
  changes. Public labels and concept vocabulary preserved.

## Recommendation — weight Coverage Safety, Depth Safety, or Trust Availability next?

**Hold the line; do not convert the remaining three now.** Pressure and Clean
Options were the two role-blind reads — the ones that genuinely treated all
relievers as equal. With both corrected, the system now distinguishes "how many
arms" from "how many that matter" on its two aggregate reads. The remaining reads
do not have the same defect:

- **Trust Arm Availability** is already trust-scoped — it only ever counts Trust
  Arms. Weighting would add nothing. Leave unchanged.
- **Coverage Safety** is already scoped to Coverage Arms, the arms that should
  dominate it. A future refinement could grant clean Depth Arms partial fallback
  coverage credit (the foundation models this at 0.5×), but that is a coverage
  nuance, not an equal-units defect. Low priority.
- **Depth Safety** is the one read where Depth Arms *should* matter most;
  weighting it down would be wrong. Leave unchanged.

Recommended next step is not more weighting but **observation**: watch the two
converted reads against real slates before touching the role-scoped reads. If an
aggregate "overall bullpen shape" is built later, it should consume the corrected
Pressure and Clean Options reads rather than re-deriving from raw counts.
