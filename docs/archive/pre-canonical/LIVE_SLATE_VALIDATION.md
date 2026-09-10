# Live Slate Validation

## The honest headline: live validation could not be performed here

This branch's mandate is to validate BaseballOS reads against **real current MLB
bullpens**. This execution environment cannot do that:

- Outbound network is blocked. `statsapi.mlb.com` returns HTTP 403 (so does
  `google.com`) — there is no path to current rosters or schedules.
- No seeded database is present, and the app's expected Postgres is not running,
  so there is no stored slate to read either.
- Today's day-of availability (Clean / Watch / Rest-Restricted / Unavailable) is
  unknowable without that feed, and the branch's first rule is to not invent
  findings.

So this report does **not** claim to read the actual June 2026 Dodgers, Mets, or
any club, and it asserts no specific reliever's current status as fact. Doing so
would be fabrication.

What it *does* do, honestly: exercise the fully-reconciled engine over each
club's **known bullpen construction** (how the pen is built — role composition is
stable baseball knowledge through early 2026) at a **rested baseline** where every
arm is a Clean Option. That isolates the construction-sensitive reads — Trust Arm
Availability, Clean Options, Coverage Safety, Depth Safety — and tests whether the
engine reads each construction sensibly, without fabricating a workload. Bullpen
Pressure and the entire Clean/Watch/Rest-Restricted read layer are workload-driven
and are therefore **out of scope for validation here** — they require a live slate.

Harness: `frontend/scripts/liveSlateValidation.mjs`. Reproduce with
`node scripts/liveSlateValidation.mjs`.

## Teams reviewed (construction archetypes, rested baseline)

| Team | Trust Avail | Clean Options | Pressure | Coverage | Depth |
| --- | --- | --- | --- | --- | --- |
| Dodgers (strong) | Strong | Deep | Low* | Thin | Strong |
| Yankees (strong) | Strong | Deep | Low* | Thin | Stable |
| Mariners (strong) | Strong | Deep | Low* | Thin | Stable |
| Guardians (strong) | Strong | Deep | Low* | Thin | Stable |
| Rockies (weak) | Thin | Healthy | Low* | Thin | Strong |
| Athletics (weak) | Thin | Healthy | Low* | Thin | Stable |
| Brewers (interesting) | Strong | Deep | Low* | Thin | Stable |
| Mets (top-heavy) | Thin | Healthy | Low* | Thin | Stable |
| Rays (coverage-rich) | Thin | Healthy | Low* | Strong | Stable |
| Marlins (mixed) | Thin | Healthy | Low* | Strong | Stable |

`*` Pressure is Low for every club because the baseline is fully rested — this
column is not a validation result, only confirmation that Pressure is
workload-driven and needs a real slate.

### Per-team reading (construction level only)

- **Strong pens (Dodgers, Yankees, Mariners, Guardians, Brewers):** ✓ Trust Arm
  Availability Strong and Clean Options Deep, driven by a genuine two-or-three
  trusted-arm core. This is the correct read for a deep, trust-rich build.
- **Weak pens (Rockies, Athletics):** ✓ Trust Arm Availability Thin and Clean
  Options held to Healthy (not Deep) despite a full count of clean arms — the
  weighting correctly refuses to call a trust-thin, depth-heavy build "Deep."
- **Mets (top-heavy / elite single closer):** ⚠ reads **Thin Trust Arm
  Availability**. A one-trusted-arm construction cannot clear the two-arm bar for
  Strong/Stable, so an elite-closer-but-thin-setup pen is labeled the same as a
  pen with one mediocre late arm. The count is honest; the *quality* of that one
  arm is not represented.
- **Rays / Marlins (coverage-rich):** ✓ the only clubs reading **Strong Coverage
  Safety**, correctly reflecting multi-inning/long-relief construction.
- **Pitcher label taxonomy:** ✓ the role-key → label mapping reproduced each
  constructed role exactly (closer/leverage → Trust, setup/bridge → Bridge,
  long/multi-inning → Coverage, low-leverage → Depth). The label *taxonomy* is
  sound; whether the live role-authority engine assigns the right role-key to
  each real pitcher is a separate question that needs the live pipeline.

## Deliverable #2 — Misclassification report (only real, observed issues)

**Team Read Issues — count-gating understates quality-concentrated pens.**
Trust Arm Availability requires two-plus trusted arms for Strong/Stable, so a pen
anchored by one elite closer reads "Thin Trust Arm Availability" (Mets). This is
the most concrete logic finding and it is structural, not data-dependent.

**Coverage Safety Issues — structurally pessimistic (confirmed twice).** Coverage
Safety requires two-plus Coverage Arms for Strong/Stable. Every club built with a
single long man reads "Thin Coverage Safety," including all four strong pens. Only
multi-inning-heavy builds (Rays, Marlins) reach Strong. The prior observation
audit flagged this; this pass confirms it across ten constructions. It is the same
count-gating pattern as Trust Arm Availability.

**Depth Safety Issues — reconciliation is unobservable at rest.** The trust-anchor
guardrail added last branch only fires when the trusted arms are actually
unavailable, which is a workload condition. At a rested baseline the Rockies'
single trusted arm is usable, so its five-deep build reads "Strong Depth Safety."
That is correct for a rested day, but it means the depth reconciliation's real
value — capping weak pens whose trust core is down — cannot be validated without a
live slate.

**Pitcher Label Issues — none observed at the taxonomy level** (mapping is exact);
live role-assignment accuracy is untested here.

**Story Narrative Issues — not reviewable.** The story panel / narrative and the
landscape story layer draw from live availability and the backend; with no slate
and no database, they could not be exercised. No findings either way.

## Deliverable #3 — Ranking readiness assessment

Per read (basis: this pass plus the prior audits):
- **Trust Arm Availability — Not Ready.** Structurally sound and discriminates
  trust-rich vs trust-thin, but count-gating mislabels elite-single-arm pens as
  Thin. Quality is not represented.
- **Clean Options — Not Ready (closest).** The role weighting validated cleanly
  (trust-thin pens correctly held below Deep). But its day-of value rides on the
  read layer, which is unvalidated here.
- **Bullpen Pressure — Not Ready (unvalidatable here).** Entirely workload-driven;
  reads Low for everyone at rest. Cannot be judged without a live slate.
- **Coverage Safety — Not Ready.** Confirmed structurally pessimistic; understates
  most real pens.
- **Depth Safety — Not Ready.** Reconciliation cannot be exercised without
  workload; volume still leads at rest.

Per ranking category:
- **Bullpen Health Rankings — Not Ready.** Would aggregate two count-gated reads
  (Trust, Coverage) that understate quality-concentrated pens, on top of having no
  live validation.
- **Bullpen Stress Rankings — Not Ready.** Rests entirely on Bullpen Pressure,
  which could not be validated here at all.
- **Bullpen Stability Rankings — Not Ready.** No temporal/variance component exists
  anywhere in the system, and no live history was available to build one.

Honest summary: nothing is ranking-ready, and the binding reason is that the
validation this branch was meant to perform could not be run in this environment.
Secondary reasons (Coverage/Trust count-gating, no stability dimension) would
remain even with data.

## Deliverable #4 — Recommended next step

**D — Additional Validation.** The decisive gap is that live-slate validation was
not performable here; it must be run in an environment with a real MLB feed (or a
seeded production database) before any ranking discussion is credible. This is not
a stall — it is the precondition the previous branch already named, now confirmed
unmet by the execution environment.

Bundle one evidence-backed logic refinement with that validation:
**B — Coverage Safety Review**, extended to the identical count-gating in Trust
Arm Availability. Both reads label a pen "Thin" whenever it has only one arm of a
role, conflating "one excellent arm" with "weak." That pattern appeared in every
relevant construction in this pass and was independently flagged in the prior
audit, so it is the one refinement with real evidence behind it.

Do **not** choose A (Proceed to Rankings): no read is validated against live data,
two reads are count-gated, and stability has no foundation. Do not choose C
(Pitcher Label Refinement): the label taxonomy mapped correctly and no label issue
was actually observed.

## Major findings (top 5)

1. Live-slate validation is impossible in this environment (network blocked, no
   database) — so no live conclusion can be drawn, only construction-level logic
   behavior.
2. Trust Arm Availability and Clean Options correctly separate trust-rich from
   trust-thin builds; the Clean Options weighting holds (trust-thin pens stay
   below Deep).
3. Count-gating is the recurring logic limitation: Trust Arm Availability and
   Coverage Safety both label single-elite-arm pens "Thin," understating quality.
4. Coverage Safety is confirmed structurally pessimistic across ten constructions.
5. Bullpen Pressure and the Depth Safety reconciliation are workload-conditional
   and cannot be validated without a real slate — the strongest argument that
   live validation, not more logic, is the true next step.
