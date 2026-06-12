# Trust-Weighted Bullpen Pressure

Controlled rollout of the weighting foundation into its first public consumer:
**Bullpen Pressure**. One read, one validation cycle. Pressure now accounts for
*which* arms are stressed rather than treating every reliever as an equal unit.
No new labels, no exposed weights, no scores, no rankings — only how the existing
label is derived.

## Product principle

A Rest-Restricted Trust Arm does not create the same pressure as a Rest-Restricted
Depth Arm. Pressure is now derived from role-weighted stress, consuming the
internal influence hierarchy from `teamWeighting.js`:

| Role | Influence weight | Pressure when restricted/unavailable |
| --- | --- | --- |
| Trust Arm | 3 | 3.0 |
| Bridge Arm | 2 | 2.0 |
| Coverage Arm | 2 | 2.0 |
| Depth Arm | 1 | 1.0 |

Watch Arms carry half load (read usability 0.5); Clean Options and Limited Reads
carry none. Bridge Arms are now tallied at the team layer for the first time
(previously invisible), so bridge stress can register.

## How the label is derived (replacing the role-blind model)

Inputs: per-role today-read counts (Trust / Bridge / Coverage / Depth ×
Clean / Watch / Rest-Restricted / Unavailable), high-fatigue arms, and the board
stress state. From these:

- `trustPressure`, `bridgePressure`, `coveragePressure`, `depthPressure` —
  role weight × stressed-read load.
- `pressureShare` — total weighted pressure ÷ total role influence (size-stable).
- `noUsableTrust` — no clean or watch Trust Arm remains.

Derivation (first match wins):
- **High** — `trustPressure ≥ 4.5` (≈ a Trust Arm pair lost), or
  `pressureShare ≥ 0.45`, or board state constrained.
- **Elevated** — `trustPressure ≥ 2.5` (≈ one Trust Arm restricted), or a Bridge
  or Coverage Arm fully lost (`≥ 2`), or `pressureShare ≥ 0.25`, or
  `noUsableTrust`, or ≥3 Watch Arms, or ≥2 high-fatigue arms, or board state
  elevated/monitoring.
- **Low** — nothing restricted or unavailable, ≤1 Watch Arm, no high-fatigue
  arms, **and** at least one usable Trust Arm.
- **Manageable** — everything else.
- **Limited Read** — sparse data (unchanged gate).

The `noUsableTrust` floor is the "meaningful options" principle made concrete: a
bullpen with no trusted option to lean on cannot read Low no matter how many
rested Depth Arms remain.

## Pressure audit — before vs after

Same bullpens, old role-blind model vs new weighted model (labels computed from
the module; "before" reflects the prior count-only thresholds).

| Bullpen | Before | After | Why the change is correct |
| --- | --- | --- | --- |
| 2 Trust restricted/unavailable + 5 clean Depth | Elevated | **High** | The lost arms are the ones that close games. |
| No Trust Arms, 5 clean Depth + 1 clean Bridge (all rested) | Low | **Elevated** | Rested, but no trusted option — pressure reflects the gap. |
| 2 clean Trust + 4 Rest-Restricted Depth | High | **Elevated** | Old model overreacted on raw count; intact trust core holds it down. |
| 2 Trust Rest-Restricted + healthy rest | Elevated | **High** | Trust loss should rise significantly. |
| 2 Coverage Unavailable + healthy Trust | Elevated | Elevated | Coverage loss is felt... |
| 2 Trust Unavailable + healthy Coverage | Elevated | **High** | ...but the identical loss among Trust Arms reads heavier. The old model rated these two identically; the new model separates them. |
| 1 Bridge Rest-Restricted (else clean) | Manageable | **Elevated** | Bridge stress matters more than depth stress... |
| 1 Depth Rest-Restricted (else clean) | Manageable | Manageable | ...and a single tired Depth Arm does not. The old model rated these two identically; the new model separates them. |
| Deep pen, healthy Trust group, 1 Watch Depth | Low | Low | Unchanged — genuinely low pressure. |
| Sparse / mostly Limited Read | Limited Read | Limited Read | Unchanged gate. |

## Validation examples (required set)

- **Trust-heavy bullpen** (2 clean Trust, rest clean): Low. The arms that matter
  are available; pressure stays low even with light depth fatigue.
- **Depth-heavy bullpen** (clean Trust core, several tired Depth): Elevated, not
  High. Depth fatigue is real but does not panic a pen whose trust core is
  intact — the central correction of this branch.
- **Coverage-heavy bullpen** (Coverage Arms unavailable, Trust intact): Elevated.
  Coverage loss raises pressure, but a matching trust loss raises it to High.
- **Constrained bullpen** (Trust Arms restricted/unavailable): High. Trust-arm
  loss is the dominant pressure driver.

## Explainability

Pressure stays fully explainable through arm conditions, never a black box. The
read's `supportingCounts` carry clean/restricted/unavailable Trust Arm counts,
stressed Bridge and Coverage Arm counts, high-fatigue arms, and the
`noUsableTrust` flag; the explanation string names the trust, bridge, coverage,
and workload conditions that produced the label. No weight value, band, or score
is exposed.

## Scope and constraints

- Changed only `bullpenPressure` (and added a Bridge crosstab in
  `summarizePitchers`) in `frontend/src/utils/teamBullpenScoring.js`.
- Trust Arm Availability, Clean Options, Coverage Safety, and Depth Safety are
  untouched.
- No backend, schema, sync, availability/fatigue engine, or page-structure
  changes. Public labels and concept vocabulary preserved.

## Recommendation — extend the model, or stay pressure-only?

**Extend deliberately, one read at a time — do not convert the others at once.**

Trust-weighted pressure is the right model and should become the template, but
each remaining read needs its own validation cycle because the correct weighting
differs by read:

- **Clean Options** — the strongest next candidate. The raw count should remain
  an honest count, but its *interpretation* should weight clean Trust Arms above
  clean Depth Arms (a depth-led "Deep Clean Options" can coexist with Limited
  Trust Arm Availability today). Convert next.
- **Trust Arm Availability** — already trust-scoped; weighting adds little.
  Lowest priority.
- **Coverage Safety / Depth Safety** — already role-scoped to the arms that
  should dominate them. Weighting would mostly add cross-role nuance (e.g.,
  partial depth fallback for coverage). Convert only after Clean Options has been
  observed against real slates.

Rationale: this branch deliberately ships one weighted read so its behavior can
be watched in production before the pattern spreads. A simultaneous conversion of
all five reads would forfeit that controlled-rollout safety and risk shifting
several public labels at once. Land pressure, observe, then convert Clean Options.
