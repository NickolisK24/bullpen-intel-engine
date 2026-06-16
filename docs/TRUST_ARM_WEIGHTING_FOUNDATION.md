# Trust Arm Weighting Foundation

Logic-foundation branch. This document audits how the current team reads weight
relievers, proposes a role-influence hierarchy, evaluates each team read against
it, and walks several example bullpens. The current implementation lives in
`backend/services/team_bullpen_shape.py`; the frontend only consumes the
backend-authored public reads. It exposes no public score, ranking, leaderboard,
or grade, and changes no public label.

The question this branch teaches the system to ask is the difference between
"how many arms are available?" and "how many meaningful options are available?"

---

## Deliverable #1 — Weighting Audit

Source of truth: `backend/services/team_bullpen_shape.py` (team reads) and
`backend/services/pitcher_public_labels.py` (role + read labels).

### Trust Arm Availability (`trustAvailability`)
- **Current weighting:** already role-scoped — only Trust Arms are counted.
  Thresholds: ≥2 trust arms all clean → Strong; ≥2 available (clean+watch), no
  unavailable → Stable; ≥1 available → Thin; else Limited.
- **Implicit assumptions:** every Trust Arm is equal to every other Trust Arm;
  a Watch trust arm counts as "available" for Stable but not Strong.
- **Equal-treatment situations:** none across roles — this read is correctly
  trust-only.
- **Where role importance should matter:** it already does. No change needed.

### Clean Options (`cleanOptions`)
- **Current weighting:** pure count of Clean Options across the whole pen.
  ≥6 (or ≥5 of an active 7+) → Deep; ≥4 → Healthy; ≥2 → Thin; else Very Thin.
- **Implicit assumption:** **a clean Depth Arm is worth exactly as much as a
  clean Trust Arm.** This is the central role-blind read.
- **Consequence (verified by simulation):** a pen with 5 clean depth arms and
  both trust arms down reads *Healthy/Deep Clean Options*, while a pen with 2
  clean trust arms + 1 clean bridge arm reads *Thin Clean Options*. Raw volume
  beats usable quality.
- **Where role importance should matter:** the count is honest as a count, but
  it cannot stand alone as a health signal.

### Bullpen Pressure (`bullpenPressure`)
- **Current weighting:** pressureLoad = watch + 2·restricted + 2·unavailable +
  high-fatigue arms; thresholds plus the board stress state.
- **Implicit assumption:** **pressure is role-blind** — a Rest-Restricted Trust
  Arm contributes the same 2 units as a Rest-Restricted Depth Arm. A pen that
  lost both trust arms can show identical pressure to one that lost two mop-up
  arms.
- **Where role importance should matter:** restriction on Trust Arms should
  register as more pressure than the same restriction on Depth Arms.

### Coverage Safety (`coverageSafety`)
- **Current weighting:** role-scoped to Coverage Arms. ≥2 clean, none
  restricted/unavailable → Strong; ≥2 available, none unavailable → Stable;
  ≥1 available → Thin; else Limited.
- **Implicit assumptions:** Coverage Arms are the only source of length; depth
  arms contribute zero fallback coverage.
- **Where role importance should matter:** largely correct already; depth arms
  arguably deserve partial fallback credit for length, which the internal
  foundation models at 0.5×.

### Depth Safety (`depthSafety`)
- **Current weighting:** role-scoped to Depth Arms with total-size gates
  (8+ arms & 3+ depth & 2+ available → Strong, etc.).
- **Implicit assumptions:** depth is a volume question. That is the correct
  frame for this read.
- **Where role importance should matter:** it should not — Depth Safety is the
  one read where depth arms *should* matter most. No change needed.

### Cross-cutting findings
1. **Bridge Arms are invisible at the team layer.** `summarizePitchers` builds
   role×read crosstabs only for trust, coverage, and depth. Bridge Arms are
   counted in `roleCounts` but influence no role-scoped read; their clean/watch
   condition surfaces nowhere except the global Clean Options count and
   pressure totals. A pen whose entire setup corps is Rest-Restricted shows no
   bridge-specific signal.
2. **The two role-blind reads (Clean Options, Bullpen Pressure) are exactly
   where the "5 clean depth arms ≠ healthy" failure lives.** The role-scoped
   reads (Trust, Coverage, Depth) are individually sound; the gap is that
   nothing weighs them against each other.
3. **Limited Read gating is consistent and good:** tiny pens (<4 arms) or <50%
   labeled arms collapse every read to Limited Read. The foundation preserves
   this exactly.

---

## Deliverable #2 — Weighting Proposal

Recommended influence hierarchy, implemented in `ROLE_INFLUENCE`:

| Role | Influence | Weight | Rationale |
| --- | --- | --- | --- |
| Trust Arm | Highest | 3 | Tonight's usable shape depends first on whether late/high-leverage arms can pitch. Losing them removes the innings that decide games. |
| Bridge Arm | Medium | 2 | Sits between Trust and Depth, as the vision suggests: bridge work protects trust arms from overexposure and converts leads to them. |
| Coverage Arm | Medium, context-specific | 2 (contextual) | Coverage influence is situational: decisive for length/coverage questions, modest for late-inning availability. The foundation routes it through a separate coverage view rather than letting it inflate the general read. |
| Depth Arm | Lowest | 1 | Real, but fungible. Depth volume matters for Depth Safety, not for "is this bullpen healthy tonight." |
| Limited Read | None | 0 | An arm we cannot read is not a meaningful option and must not add confidence. |

Read usability multipliers (`READ_USABILITY`): Clean Option 1.0 · Watch Arm 0.5
· Rest-Restricted 0 · Unavailable 0 · Limited Read 0. Pressure is the inverse
(1 − usability) scaled by role weight, so a lost Trust Arm contributes 3 units
of weighted pressure versus 1 for a lost Depth Arm.

Two reconciliation guards on the internal "meaningful options" band:
- **Trust floor:** a pen with zero usable trust influence cannot band better
  than *narrow*, regardless of clean depth volume.
- **Trust shield:** a pen whose trust arms are all clean cannot band worse than
  *workable* on depth fatigue alone (public Bullpen Pressure still reports the
  fatigue honestly).

Internal band vocabulary (deliberately distinct from public labels):
`broad · workable · narrow · minimal · limited_read`.

---

## Deliverable #3 — Team Read Impact

| Read | Question | Recommendation |
| --- | --- | --- |
| Trust Arm Availability | Should trust arms dominate? | **Yes — and they already do.** The read is trust-scoped. Keep as-is. |
| Clean Options | Should all clean options count equally? | **As a count, yes; as a health signal, no.** Keep the public count honest, but any aggregate interpretation built on it should weight clean trust arms above clean depth arms (the foundation's `usableInfluence` does this). Do not relabel yet. |
| Bullpen Pressure | Should pressure on Trust Arms matter more? | **Yes.** This is the highest-value future change: add trust-weighted pressure (foundation's `weightedPressure` / `trustPressure`) so two lost trust arms read heavier than two lost depth arms. Defer the public wiring. |
| Coverage Safety | Should Coverage Arms matter more than Trust Arms? | **Yes, within this read.** Coverage Safety should stay coverage-led; a clean closer adds no multi-inning coverage. Consider partial (0.5×) depth-arm fallback credit, as modeled. |
| Depth Safety | Should Depth Arms matter most? | **Yes.** This read is the proper home for depth volume. Keep as-is. |
| (gap) Bridge Arms | — | Add a bridge crosstab to `summarizePitchers` when weighting is wired in, so bridge condition can inform pressure and any future aggregate. Until then bridge condition is invisible at the team layer. |

---

## Deliverable #4 — Simulation Examples

Outputs computed from the actual modules (public reads from
`getTeamBullpenShape`, internal view from `getTeamWeightingFoundation`).

### Example A — depth-rich, trust-broken
2 Trust (Rest-Restricted / Unavailable) · 5 Depth (all Clean)
- Public: Limited Trust Arm Availability · **Healthy Clean Options** · Elevated Pressure · Limited Coverage Safety · Stable Depth Safety
- Internal: meaningful options **narrow** (usable share 0.45, trust pressure 6 of 6)
- Interpretation: the pen can eat innings but cannot protect a lead. "Healthy
  Clean Options" alone would mislead; the trust floor corrects the aggregate.

### Example B — trust-led, no depth
2 Trust (Clean) · 1 Bridge (Clean) · 1 Coverage (Rest-Restricted) · 1 Depth (Unavailable)
- Public: Strong Trust Arm Availability · **Thin Clean Options** · Elevated Pressure · Limited Coverage Safety · Limited Depth Safety
- Internal: meaningful options **broad** (usable share 0.73, trust pressure 0)
- Interpretation: tonight, the arms that matter are all usable. The pen is
  fragile over a long week (depth/coverage reads say so) but is not "thin" in
  the way Example A is. A and B must never receive identical aggregate reads —
  and under the foundation they do not (broad vs narrow).

### Example C — balanced healthy pen
2 Trust (Clean/Watch) · 2 Bridge (Clean/Watch) · 1 Coverage (Clean) · 3 Depth (2 Clean, 1 Watch)
- Public: Stable Trust · Deep Clean Options · Elevated Pressure · Thin Coverage · Strong Depth
- Internal: **broad** (usable share 0.80) — weighting agrees with the public reads.

### Example D — trust gassed, everything else clean
2 Trust (both Rest-Restricted) · 2 Bridge (Clean) · 1 Coverage (Clean) · 3 Depth (Clean)
- Public: Limited Trust · **Deep Clean Options** · Elevated Pressure · Thin Coverage · Strong Depth
- Internal: **narrow** (usable share 0.60, trust pressure 6)
- Interpretation: six clean arms, none of them the ones that close games. This
  is the clearest case where the role-blind Clean Options read and the usable
  truth diverge.

### Example E — trust clean, depth fully gassed
2 Trust (Clean) · 1 Bridge (Watch) · 1 Coverage (Rest-Restricted) · 4 Depth (Rest-Restricted)
- Public: Strong Trust · Thin Clean Options · **High Bullpen Pressure** · Limited Coverage · Limited Depth
- Internal: **workable** (trust shield active; usable share 0.50, trust pressure 0)
- Interpretation: a short-game pen. Usable tonight in the innings that matter,
  with pressure honestly flagged for tomorrow.

### Example F — depth-only roster, fully rested
1 Bridge (Clean) · 6 Depth (Clean)
- Public: Limited Trust · **Deep Clean Options · Low Bullpen Pressure** · Limited Coverage · Stable Depth
- Internal: **narrow** (usable share 1.00 but zero trust influence → trust floor)
- Interpretation: the sharpest contrast — every arm rested, no arm trusted.
  "How many rested arms?" answers 7; "how usable tonight?" answers narrow.

### Example G — sparse labels
3 Limited Read roles, 1 Trust, 1 unread Depth
- Public: every read Limited Read. Internal: **limited_read** both views.
- Interpretation: sparse data degrades to Limited Read everywhere, never to a
  confident band.

---

## Recommendation — implement now, later, or partially?

**Partially — exactly what this branch does.**

- **Now:** land the internal weighting foundation (hierarchy, usability
  multipliers, trust floor/shield, weighted pressure, limited-read gating) with
  tests, unwired from any public surface. This gives future ranking work a
  tested, explainable definition of "meaningful options" without destabilizing
  the public vocabulary users are currently learning.
- **Later (next branches, in order of value):**
  1. Trust-weighted Bullpen Pressure — wire `weightedPressure`/`trustPressure`
     into the pressure read's inputs.
  2. Bridge Arm crosstab in `summarizePitchers` so bridge condition exists at
     the team layer.
  3. Any aggregate "overall shape" consumer should read the meaningful-options
     band, not the raw Clean Options count.
- **Not now:** public label changes, scores, rankings, leaderboards, grades.
  The public reads are individually honest; changing their labels before the
  weighting layer has been observed against real slates would trade one
  validation problem for another.
