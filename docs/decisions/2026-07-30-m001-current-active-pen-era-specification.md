# Decision: M-001 Current Active-Pen ERA Specification

- **Date:** July 30, 2026
- **Owner:** Nickolis Kacludis
- **Status:** Adopted
- **Extends:** D-021 (family contract), D-022 (family versus metric), D-008 (integer outs authority), D-009 (historical appearance ownership)
- **Canonical homes:** Bullpen Intelligence Standard Sections 7A, 7B, 7C, 8 and 16; Product Experience Standard Section 14; Platform Architecture & Operations Manual Section 6; Editorial & Distribution Standard Sections 12 and 12A; Product Roadmap & Decision Ledger D-023 through D-030
- **Governs:** M-001 Current Active-Pen ERA

This record preserves the rationale and the repository evidence behind eight
governed decisions. The canonical documents own the rules. This file does not
restate them as a second manual.

**This package changes no code.** M-001 remains unpublishable until a separate
implementation package sets the approved values in the metric registry entry and
passes the normal trust gates. Approving a threshold is not the same as wiring
one.

## Why these eight decisions now

D-021 established the Current Active-Pen Performance family and deliberately
reserved M-001's own parameters. D-022 separated family from metric so those
parameters could be approved without reopening the family. The reusable
framework then merged in PR #563 with every reserved parameter left explicitly
absent — `minimum_sample = None`, no approved public name, no approved
below-sample wording — and the framework refuses to publish while any of them
holds.

That was the correct terminal state for an implementation package. It is not a
terminal state for the product: the metric now computes correctly and cannot
be shown to anyone. These eight decisions close that gap in the only place it
may be closed, which is governance.

## Discovery: what was unresolved before this record

Read against the canonical library and the merged framework.

| # | Unresolved item | Recorded in | Resolved here |
|---|---|---|---|
| 1 | M-001 minimum sample and its authority | D-021 "deliberately not decided"; BIS 7A sample contract; `performance_metrics.ERA_MINIMUM_SAMPLE = None` | Yes — D-023 |
| 2 | M-001 denominator approval | D-021 "deliberately not decided"; BIS 7B registry note | Yes — D-024 |
| 3 | M-001 formula approval | D-021 "deliberately not decided" | Yes — D-024 |
| 4 | Rounding and display precision | BIS 7B required registry fields; no canonical policy existed | Yes — D-025 |
| 5 | Public wording for a below-sample read | D-021 "deliberately not decided"; BIS 7A sample contract | Yes — D-026 |
| 6 | No-usage call-up membership representation | `performance_intelligence._limitations`; BIS 7A active-group contract | Representation resolved — D-027. Detection remains open, see below |
| 7 | Public metric name | BIS 7B registry carries a working name only | Yes — D-028 |
| 8 | Exact evidence contract for M-001 | BIS 7A evidence levels define the shape, not the fields | Yes — D-029 |
| 9 | What a future metric inherits versus defines | D-022 states the split without enumerating it | Yes — D-030 |

Unresolved before this record and **still unresolved after it**, by scope:

| # | Item | Why it stays open |
|---|---|---|
| A | Whether the bullpen-population authority *finds* a newly active arm with no usage-based role evidence | A bullpen-population question, not a performance-family question. D-027 governs how such an arm is represented once resolved; it cannot make the upstream authority resolve him |
| B | `services/season_era.py` stale limitation string and current-team grouping | A governed migration pinned by `test_season_era_reader_is_not_migrated_in_this_step` |
| C | The `season_era` block reachable in `GET /api/bullpen/dashboard` | Implementation cleanup; it is not M-001 and must never be presented as M-001 |
| D | `services/team_state_card_metrics.py` stale parenthetical | Documentation drift inside code; harmless to behavior |
| E | Public read-label drift between canon and `pitcher_public_labels.READ_PUBLIC_LABELS` | A vocabulary-alignment work package |
| F | `season_bullpen_aggregation_2026._gates` computing `ready_for_review` for `public_reader_gate` | Not opened, not changed; recorded in D-021 and unchanged here |
| G | Concrete storage, routes, payloads, cache keys, and surfaces for M-001 | Implementation-time decisions against the repository |

---

## D-023 — Minimum sample

### Approved

> **M-001 publishes only when the qualifying appearance set totals at least
> 108 recorded outs (36.0 innings) of official completed relief work for the
> represented team.**

The threshold is expressed in **recorded outs**, the metric's own denominator
unit, not in appearances or in pitchers.

Authority string carried with the value: `D-023`.

### Why this threshold exists

The threshold is derived from the formula, not chosen from a table.

M-001 is `earned_runs * 27 / outs`. One additional earned run moves the
published value by exactly `27 / outs`. The rule is:

> A single earned run may not move the published value by more than 0.25.

Solving `27 / outs <= 0.25` gives `outs >= 108`. One hundred eight outs is
exactly 36.0 innings, and 108 is the smallest whole-out sample satisfying the
rule.

A quarter of a run is the smallest difference between two bullpens that a
baseball reader would treat as meaningful. Below 108 outs, the second decimal
place BaseballOS publishes is an artifact of one swing of one inning rather
than a property of the group, and the number would claim a precision the
sample cannot support.

This derivation is durable. It depends only on the formula and on a stated
sensitivity rule, so it does not need revision when a season, a run
environment, or a roster convention changes.

### Why the sample is counted in outs and not in appearances

Appearances are the wrong unit for a rate over innings. Ten relief appearances
of one out each is ten outs — three and a third innings — where a single
earned run produces a published value of 2.70 on ten outs and 27.00 on one
inning. An appearance-count threshold would let a bullpen of one-out
specialists clear a sample gate it has not earned, and would hold back a
bullpen that has thrown real innings in fewer outings.

This also keeps the sample unit aligned with D-008: integer recorded outs are
the innings authority, so the sample, the denominator, and the evidence all
count in the same units and cannot drift.

### Why a lower threshold was rejected

| Rejected | Effect of one earned run | Why rejected |
|---|---|---|
| 27 outs (9.0 innings) | 1.00 | One inning of relief work would move the value a full run. Publishing two decimals over that sample would be the "unexplained number" the Constitution prohibits |
| 54 outs (18.0 innings) | 0.50 | Half a run per earned run. Two bullpens shown at 3.80 and 4.20 would differ by less than one swing of one inning; readers would compare noise |
| 90 outs (30.0 innings) | 0.30 | Close, and defensible, but chosen for its roundness in innings rather than derived. It fails the stated sensitivity rule, and a threshold that cannot be derived cannot be explained on the Methodology surface without an unexplained number |

### Why a higher threshold was rejected

| Rejected | Effect of one earned run | Why rejected |
|---|---|---|
| 162 outs (54.0 innings) | 0.17 | Buys a sharper number at the cost of silence through most of April, and permanent silence for a bullpen substantially rebuilt at the trade deadline |
| 270 outs (90.0 innings) | 0.10 | Suppresses the metric for a heavily rebuilt pen for the remainder of a season. That is the exact situation in which a reader most needs to know what today's group has actually done |

Silence is valid under the Constitution when evidence is weak. It is not a
free action when evidence is sufficient: refusing to publish true, official,
checkable results is itself a trust cost, because it teaches a reader that the
platform withholds. The threshold must be the smallest sample that supports
the number, not the largest sample that would feel safe.

### Constitutional justification

- **Permanent guardrail — "a product that converts unknowns into zero or
  plausible values."** Below 108 outs the group's rate is not unknown in the
  sense of missing; it is known but unstable. Publishing it would present
  instability as precision, which is the same failure in a different costume.
- **"Evidence outranks engagement."** A number is more shareable than a
  refusal. That is not a reason to lower the threshold.
- **"Silence is valid."** The platform gets quieter under uncertainty, never
  wronger.
- **"Unexplained thresholds" are prohibited on the Methodology surface**
  (Product Experience Standard Section 15). A derived threshold survives that
  rule; a picked one does not.

### Trust justification

The threshold is explainable in one sentence to a fan — *one earned run can't
move this number more than a quarter of a run* — and reproducible by an
analyst from the formula alone. Both audiences can check it. Neither has to
take it on faith.

### Interaction with existing behavior

- The zero-denominator refusal (`era_denominator_zero`) **precedes** the
  sample check and is not replaced by it. A read with zero outs refuses as a
  mathematical impossibility, not as a governance decision.
- The below-sample refusal applies only to a value that is computable.
- The framework's current sample comparison is against **appearance count**.
  Implementing D-023 requires migrating that comparison to the metric's
  declared sample unit. That migration is not performed here and is listed in
  Consequences.

---

## D-024 — Denominator authority

### Approved

> **M-001's denominator is the total integer recorded outs over the qualifying
> appearance set. Its numerator is total earned runs multiplied by 27. Decimal
> innings are display-only and never participate in the calculation.**

Formula: `earned_runs * 27 / recorded_outs`.

This is the convention already in production-internal use in
`services/season_bullpen_aggregation_2026._era_components`. It is reused
verbatim rather than restated, so the two cannot drift.

### Why integer outs remain the canonical authority

D-008 already makes integer recorded outs the semantic innings authority.
Three independent reasons keep it that way for M-001:

1. **Decimal innings do not sum.** MLB innings notation puts outs after the
   decimal point: `2.1` is seven outs, not two and one tenth. Adding `2.1` and
   `2.2` as decimals yields `4.3`, which is not a legal innings value; adding
   the outs yields fifteen, which is `5.0`. Any denominator built by summing
   the display notation is arithmetically wrong.
2. **Floats are not reproducible.** Every appearance would contribute a
   repeating binary fraction, and the accumulated denominator would depend on
   summation order. The repository has already absorbed one float-readback
   precision incident on official pitching lines; a published rate must be
   byte-identical on every recomputation and inside every frozen artifact.
3. **The evidence chain must reconcile exactly.** A reader who adds the outs
   in the Level 3 evidence must arrive at the Level 2 denominator with no
   remainder. That is only possible in integers.

### Why decimal innings remain display-only

Readers read innings, not outs. `96.1` is baseball; `289` is bookkeeping. The
display value is **derived from** the authority at render time and is never an
input. A surface may show `96.1`; no surface may compute with it.

### Interaction with zero-denominator refusal

| Outs | Behavior |
|---|---|
| 0 | Refuse with `era_denominator_zero`. This is division by zero, not a governance judgment, and it is reported before any sample evaluation |
| 1 to 107 | Value is computable and is **not** published. Refuse below sample per D-023 |
| 108 or more | Value is computable and publishable, subject to the remaining gates |

The two refusals are never merged into one code. A reader inspecting a refusal
must be able to tell "this group has not pitched" from "this group has not
pitched enough."

### Permanence

This settles denominator authority for M-001 permanently. A future metric
under the family declares its own denominator, but any denominator measured in
innings inherits integer outs unchanged (D-030).

---

## D-025 — Rounding and precision

### Approved

This is a **family-wide mechanics policy**. Each metric declares its own
displayed precision; none of them redefines how rounding works.

| Layer | Rule |
|---|---|
| Internal | Exact integers only. The numerator and denominator are integers at every stage. No floating-point type participates in the calculation at any point |
| Ratio | Computed as an exact `Decimal` quotient of the two integers. Never `float` division |
| Rounding | `ROUND_HALF_UP`, applied **exactly once**, at the metric's declared precision, to the exact rational value |
| Stored | The exact integer numerator, the exact integer denominator, and the rounded value as a fixed-precision decimal string. Never a float |
| Displayed | The stored string verbatim, with trailing zeros preserved. The frontend never rounds, re-rounds, truncates, or reformats |

M-001's declared displayed precision is **two decimal places, always**.

### Why half-up and not banker's rounding

Banker's rounding — round-half-to-even, Python's `float` default — is correct
for large aggregations where rounding bias must cancel. It is wrong here for
two reasons: it produces a value a reader cannot reproduce by hand, and it
makes two adjacent values round in opposite directions for no reason the
reader can see. ERA has been published half-up in baseball for a century.
BaseballOS matches the convention its readers already hold.

### Why rounding happens once

A value rounded at computation, rounded again for storage, and formatted with
a third rounding can differ from the exact value by more than the published
increment. Rounding exactly once, at the metric boundary, makes the published
number a pure function of two integers.

### Worked examples

| Earned runs | Outs | Innings shown | Exact numerator | Exact quotient | Published |
|---|---|---|---|---|---|
| 31 | 289 | 96.1 | 837 | 2.896193... | **2.90** |
| 12 | 108 | 36.0 | 324 | 3.0 exactly | **3.00** |
| 0 | 130 | 43.1 | 0 | 0.0 exactly | **0.00** |
| 1 | 216 | 72.0 | 27 | 0.125 exactly | **0.13** |
| 8 | 66 | 22.0 | 216 | 3.272727... | *refused — below sample (D-023)* |
| 4 | 0 | 0.0 | 108 | undefined | *refused — `era_denominator_zero`* |

Two of these carry the whole policy:

- **`0.00` is published as a value.** A group that has allowed no earned runs
  over 43.1 innings has a real, observed, checkable ERA of zero. It is never
  rendered as missing, as a dash, or as an unavailable read. A real zero and
  an absent value are different facts and must look different.
- **`0.125` publishes as `0.13`.** Half-up. Banker's rounding would give
  `0.12`, and a reader dividing 27 by 216 by hand would not arrive there.

### Future metrics

A future metric declares its precision in its registry entry — one decimal
place, a percentage with one decimal, whatever its convention requires — and
inherits every rule in the table above unchanged. No metric may introduce a
second rounding mode, round more than once, or round in the frontend.

---

## D-026 — Below-sample public wording

### Approved

> **"Not Enough Innings Yet"**

Rendered with its own numbers immediately adjacent, never alone:

> **Not Enough Innings Yet** — this group has thrown 22.0 relief innings for
> Cincinnati; 36.0 are required.

The count and the requirement are mandatory. Product Experience Standard
Section 15 prohibits unexplained thresholds, and Editorial Section 12A
prohibits a performance claim without its group and sample beside it. A bare
"Not Enough Innings Yet" satisfies neither.

### Why this wording

It is tested against the four requirements:

| Requirement | How the wording satisfies it |
|---|---|
| Accurately communicates insufficient evidence | Names the exact deficiency — innings — in the same unit as the threshold |
| Never implies poor performance | Contains no evaluative word. A bullpen with a 1.50 rate over 20 innings gets the identical read |
| Never implies hidden data | "Yet" places the cause in time, not in a withholding decision. Nothing is being kept back; the innings have not been thrown |
| Never implies system failure | No error register. Nothing is broken, unavailable, or unreachable |

It is also plain baseball language, which the Constitution requires: a fan
says "not enough innings," not "insufficient sample."

### Rejected alternatives

| Rejected | Why |
|---|---|
| **Limited Read** | Forbidden. It is a governed **arm-read** label under D-005 with an established meaning about one pitcher's current workload evidence. Reusing it for a team-level performance metric would give one public term two meanings — the exact vocabulary drift BIS Section 8 exists to prevent |
| **Unavailable** | Forbidden. Also a governed arm-read label under D-005, meaning a roster or state authority has removed an arm from the available set. Applied to a metric it would read as a system outage |
| **Monitor** | Forbidden. An internal availability state that BIS Section 8 explicitly keeps internal, and it carries an implied instruction — the platform does not tell readers what to watch for on the basis of a rate |
| Insufficient Sample | Analyst register. The Constitution requires the voice of a careful baseball person, not a data-science paper. It also names a statistical construct rather than the baseball fact |
| Not Yet Published | Implies an editorial withholding decision and invites the question of what is being withheld |
| Sample Building / Building Sample | Product-speak, and it describes an internal process rather than a baseball condition |
| Early Sample | Wrong in the common case. A bullpen rebuilt at the July deadline is below sample in August, and nothing about that is early |
| Too Few Innings | Accurate but reads as a complaint about the bullpen, and drops the "will resolve" signal that "Yet" carries |
| No Qualifying Innings | Only correct at zero outs, which is a different refusal (D-024) |

### Scope

This wording covers the below-sample refusal only. It is not a fourth Team
State, not an arm-read label, and not a role label. The zero-denominator
refusal, the unresolved-authority refusal, and the invalid-row refusal each
keep their own machine codes and are not given this wording.

---

## D-027 — No-usage call-up rule

### The question

A reliever is resolved into a team's active bullpen for the represented
baseball date and has no qualifying relief appearances for that team — a
call-up, a waiver claim, a deadline acquisition, or an arm returning from the
injured list.

### Approved: Option B, with mandatory disclosure

> **He is included in the active group and contributes zero qualifying
> appearances. The group therefore reports two counts — group size and
> contributing arms — and the evidence names him among the members who have
> not yet pitched for this team.**

His zero outs and zero earned runs enter no numerator and no denominator,
because M-001 is a ratio over recorded work and not an average of per-pitcher
rates. Including him changes the group description and changes nothing about
the number.

### Why this is not unknown-as-zero

This is the distinction the Constitution's guardrail turns on, and it must be
stated precisely.

- An **unknown** is a value that exists in the world and is missing from our
  record. The framework already refuses the whole read when one qualifying row
  carries a missing or malformed component.
- A **no-usage member** has an **observed** count of zero relief appearances
  for this team. Nothing is missing. The zero is the fact.

Counting an observed zero is not imputation. Substituting a league rate, a
prior-club rate, or a zero *rate* for him would be, and all three are
prohibited.

### Why the alternatives were rejected

| Option | Why rejected |
|---|---|
| **A — Exclude him from the group** | Silently changes the question. The family asks how *the pitchers who make up this bullpen* have performed; dropping the ones without history answers how *the pitchers with history* have performed, which is a different and less honest question. It also makes the published group size disagree with the roster a reader can see, and it hides the very fact that most changes how the number should be read — that two of eight arms are new |
| **C — Represent him separately** | Creates a second group and invites a second number, violating one canonical home per fact. It also implies the platform has something to say about a pitcher who has not pitched, which it does not |
| **D — Alternatives considered** | *Include him only after his first appearance* is Option A with a delay and the same defect. *Include his prior-organization line* directly violates D-009 and the family's no-current-team-fallback rule. *Publish a per-arm average instead of a group rate* replaces the metric with a different metric to avoid a disclosure problem |

### Alignment

- **Current Active-Pen Performance Contract:** membership and appearance
  ownership stay separate. He is a member; he owns no appearances for this
  team. Both statements are true simultaneously, which is exactly what the
  contract's two-authority split is for.
- **Bullpen Population:** membership resolution is unchanged. This decision
  consumes that authority and does not alter it.
- **Appearance Authority / Foundation 1 / D-009:** his prior-club appearances
  stay with his prior club. No current-team fallback is introduced.

### Downstream effects

1. Every read reports `group_size` and `contributing_pitchers`. When they
   differ, the Level 2 context discloses the difference in one sentence.
2. A difference between the two counts is normal information, never an error
   state, and no surface may render it as a warning.
3. The sample threshold (D-023) is evaluated on **outs**, so a group padded
   with non-contributing members cannot cross the gate on membership alone.
   This is a second reason the sample unit is outs and not appearances.
4. Frozen Share Artifacts store both counts as published and never recompute
   either from live membership.
5. Compare requires the same group contract on both sides. Two teams with
   different non-contributing shares remain comparable, because the rate is
   over recorded work; the counts travel with each side so the reader can see
   the difference.
6. Editorial copy that cites the value cites the group size. Where the
   contributing count is materially smaller, copy says so.

### What this decision does not do

It does not make the bullpen-population authority resolve an arm it currently
misses. The framework's standing limitation — that active-bullpen membership
is not yet guaranteed complete for a newly active arm with no usage-based role
evidence — is a population question and remains open (discovery item A).
D-027 governs representation once membership resolves.

---

## D-028 — Public name

### Approved

> **Public rendered name: "Active Bullpen ERA".**
>
> **Stable registry identity: `M-001`. Governed internal metric name:
> Current Active-Pen ERA. Governed family name: Current Active-Pen
> Performance.**

The split follows the pattern D-005 already established for arm reads: backend
keys own semantic identity, and the public catalog owns rendered language. No
prior decision is reversed — D-021 and D-022 named the metric for the registry
and explicitly reserved the public label.

Required adjacent context, per Editorial Section 12A:

> **Active Bullpen ERA 3.41** — the eight arms in Cincinnati's bullpen as of
> July 30, over 96.1 relief innings for the Reds this season.

### Why this name

- "Bullpen" is what a baseball person says. "Pen" is what a baseball person
  says out loud and rarely writes as a label, and "Active-Pen" is a hyphenated
  compound that reads like a schema field.
- "Active" carries the as-of-today sense of the group without a second word.
- "ERA" is the most widely understood rate in baseball and needs no gloss.
- Three words fit a mobile component, which is the primary daily context.

### Rejected alternatives

| Rejected | Why |
|---|---|
| **Current Active-Pen ERA** | Precise and consistent with the family name, but reads as internal vocabulary. "Active-Pen" is not natural baseball speech, and the hyphen makes it look like a system term. It is retained as the governed internal name so no canonical text has to be rewritten |
| **Current Bullpen ERA** | "Current" attaches to the wrong noun. A reader parses it as *the bullpen's ERA lately* — a recent-form window — rather than *the current bullpen's season ERA*. That is a real misread of the actual window and disqualifies it |
| **Season ERA (Active Bullpen)** | A caption, not a name. Names are content under the Product Experience Standard, and a parenthetical qualifier does not survive a share artifact, a chart axis, or a sentence in a post |
| **Today's Bullpen ERA** | Implies tonight's game and drifts toward prediction |
| **Active Pen Season ERA** | Accurate and unreadable |
| **Bullpen ERA** | Drops the group qualifier entirely and would be confused with the team's full-season bullpen line, which is a different number that already exists internally in `season_bullpen_aggregation_2026`. Publishing both under one name is the drift this decision exists to prevent |

### Consequence

"Active Bullpen ERA" joins the Established Public Language table in the
Editorial & Distribution Standard. It is the only approved public performance
term. No surface, caption, or post may paraphrase it.

---

## D-029 — Evidence contract for M-001

### Approved

The family's four evidence levels are filled for M-001 as follows. This is the
**template** every future metric under the family fills.

#### Level 1 — Summary (all required)

- public metric name (D-028);
- the published value at declared precision, **or** the below-sample read
  (D-026) with its count and requirement, **or** the typed refusal;
- represented baseball date;
- freshness state.

#### Level 2 — Context (all required)

- group size and contributing-arm count (D-027);
- qualifying appearance count;
- total recorded outs and the derived display innings;
- exact integer numerator and exact integer denominator;
- approved minimum sample, its unit, and its authority string (D-023);
- method version and effective date;
- the material limitation where it applies.

#### Level 3 — Evidence (all required)

- every group member named, each with his qualifying appearance count and
  outs, including members with zero (D-027);
- every qualifying appearance as a row: game identifier, game date, opponent,
  appearance-team identifier, recorded outs, earned runs;
- the reason any line was excluded, where material.

#### Level 4 — Official record (all required)

- the named source authority for each appearance — the official completed
  pitching line;
- appearance-team authority status and source for each row;
- schedule and finality authority for each game;
- method version and its effective date.

#### Optional at any level

Opponent branding, game number for a doubleheader, rest and usage context,
and per-arm rate values. A per-arm rate is publishable only against that arm's
own approved sample; it is never derived by the reader from a Level 3 row.

#### Prohibited at every level

League averages, prior-period values, projections, rankings, quality
adjectives, and any value presented without its group and sample.

### The binding rule

> A value whose evidence cannot reach Level 4 is not publishable.

Not every surface renders all four levels. Every substantive value provides a
route that reaches them. A compact rendering may show less; it may never
become a naked number.

### Future extensibility

A future metric may add its own numerator and denominator names at Level 2 and
its own required source fields at Level 3. It may not add a level, rename a
level, reorder the chain, or make a required field optional.

---

## D-030 — Future metric inheritance

### Inherited unchanged — a metric may not redefine these

1. the family's governing question and scope;
2. the active-group authority and its resolution date;
3. the window contract — official completed relief appearances, this team's
   side, current regular season — and its exclusions;
4. appearance-team authority, with no current-team fallback (D-009);
5. integer recorded outs as the innings authority (D-008);
6. fail-closed publication with typed refusal codes;
7. the prohibition on unknown-as-zero, and the rule that one unusable
   qualifying row refuses the entire read;
8. represented date, data-through date, season, and freshness stamps;
9. the four evidence levels and their required fields (D-029);
10. the family limitation;
11. rounding mechanics — exact integers, `Decimal`, `ROUND_HALF_UP`, applied
    once, never in the frontend (D-025);
12. the gate model. No metric opens its own gate;
13. the Team Board as canonical public home, and the rule that no surface
    recalculates.

### Defined by the metric itself

1. stable metric key and version;
2. public rendered name;
3. the question it answers, phrased for Level 1;
4. formula, numerator, and denominator — integer-exact over the shared
   appearance components;
5. the source fields it cannot be computed without;
6. declared displayed precision;
7. minimum sample **value, unit, and authority** — stated in its own
   denominator's unit;
8. its denominator-zero refusal code;
9. any metric-specific limitation beyond the family limitation;
10. approved surfaces;
11. deterministic fixtures.

### Required before registration

A metric may be registered without an approved minimum sample. It will compute
and will refuse to publish, exactly as M-001 did between PR #563 and this
record. Before it may publish it needs an approved formula, an approved
minimum sample with its authority, an approved public name, and a declared
precision.

### Named candidates and what each still needs

| Candidate | Denominator | Blocking requirement beyond the standard four |
|---|---|---|
| WHIP | recorded outs | None known. Walks and hits are already carried on the official line |
| HR/9 | recorded outs | None known |
| K%, BB%, K-BB% | batters faced | Batters faced must be proved complete on every qualifying line; it is carried but has never been validated as publication-critical |
| FIP | recorded outs | Requires hit-by-pitch, and requires an approved constant with a named authority and a stated recomputation cadence. A constant is exactly the kind of unexplained number that needs its own decision |
| xFIP | recorded outs | Requires a fly-ball classification and a league home-run-per-fly-ball rate. Pitch and batted-ball characteristics are Experimental / Partial in the Bullpen Intelligence Standard |
| LOB% | inherited runners | Requires inherited-runner outcomes, listed as Partial |

**Standing rule:** a metric whose required source domain is Experimental,
Partial, or Deferred in the Bullpen Intelligence Standard capability registry
may not be registered until that domain reaches Production. Registering it
earlier would create a governed metric that can never satisfy Level 4.

---

## Consequences

- M-001 has an approved formula, denominator, minimum sample, precision,
  public name, below-sample wording, evidence contract, and membership rule.
  Every parameter D-021 reserved is now decided.
- **M-001 is still not public.** `public_reader_gate`,
  `team_state_performance_gate`, and `share_card_performance_gate` remain
  blocked. This record opens no gate.
- A separate implementation package must set `ERA_MINIMUM_SAMPLE = 108`,
  `ERA_MINIMUM_SAMPLE_UNIT = 'recorded_outs'`, and
  `ERA_MINIMUM_SAMPLE_AUTHORITY = 'D-023'` in the metric registry entry, and
  must **migrate the framework's sample comparison from appearance count to
  the metric's declared sample unit**. The comparison at
  `performance_intelligence._publication_decision` currently tests
  `components.appearances`, which would apply D-023's threshold in the wrong
  unit. No code is changed by this record.
- The same implementation package must add `contributing_pitchers` to the
  group and to the Level 2 context (D-027), and must add the below-sample
  display copy and its adjacent counts (D-026).
- Team Board, Compare, Stories, and Share Artifacts inherit the approved name,
  wording, precision, and evidence contract when the metric is wired. None of
  them recalculates.
- Future metrics under this family inherit D-024 through D-030 and reopen
  none of them.

## Reversal Standard

Reversing any decision in this record requires a new Decision Record naming
the exact decision, demonstrating with worked numbers that the approved value
misrepresents the baseball fact, and stating the replacement together with its
derivation. A threshold, a precision, or a public term may not be changed by
preference, by a redesign, or by a surface that finds it inconvenient.

Reversing D-023 additionally requires showing that the sensitivity rule itself
is wrong — not merely that a different number would be more or less
permissive.
