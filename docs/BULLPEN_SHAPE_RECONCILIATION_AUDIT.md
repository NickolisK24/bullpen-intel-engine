# Bullpen Shape Reconciliation — Audit and Reconciliation

Validation pass over every team-level bullpen interpretation, with the goal of
guaranteeing that public-facing reads stay logically consistent. This is not a
rankings effort. It is a logic-validation effort: a user must never be able to
reasonably ask, "How can this bullpen be one of the healthiest and one of the
most stressed at the same time?"

## Summary

The foundation is sound. Every team carries a single, deterministic
`health_state` (`classify_bullpen_health` in `services/bullpen_board.py`) that
already reconciles available / monitor / restricted counts in a fixed priority
order. The contradiction the team observed did not come from that classifier —
it came from the public **Tonight's Bullpen Landscape**, which selected its
"most available" and "most constrained" columns by raw counts and ignored each
team's own reconciled shape. As a result the same club could headline both
columns at once. The fix elevates the existing per-team `health_state` to be the
authority that gates those columns, so the two opposing reads are now mutually
exclusive. No new public score was introduced; none is needed.

## Vocabulary note

The vision vocabulary (Trust Arm Availability, Clean Options, Coverage Safety,
Depth Safety; pitcher-level Trust / Bridge / Coverage / Depth arms) is a
conceptual model. The shipped implementation expresses these ideas through:

- **Pitcher availability** (`services/availability.py`): Available · Monitor ·
  Limited · Avoid · Unavailable.
- **Team bullpen shape** (`classify_bullpen_health`): manageable · monitoring ·
  elevated · constrained · no_data.
- **Team readiness** (`team_operations/bullpen_readiness.py`):
  operationally_stable · operationally_constrained · operationally_stressed ·
  data_limited.
- **Public landscape** (`services/game_context.py`): constrained · available ·
  monitoring columns.

"Clean Options" maps to the count of Available arms; "Trust Arm Availability"
has no separate model today — all relievers are pooled. That pooling is itself
relevant to the audit and is discussed under Reconciliation Strategy.

---

## Deliverable #1 — Audit

For each public team-level interpretation: inputs, weighting, output labels, and
the contradiction surface.

### Tonight's Bullpen Landscape — `services/game_context.py` (`build_landscape`)
- **Inputs:** per-team availability counts → `_landscape_entry` → `build_team_context`.
- **Weighting (before this change):**
  - `constrained_bullpens`: sort by `-restricted`, `-pct_restricted`, name; keep `restricted > 0`.
  - `available_bullpens`: sort by `-available`, `-pct_available`, name; **no filter**.
  - `monitoring_concentration`: sort by `-monitor`, name; keep `monitor > 0`.
- **Output labels:** "[Team] appears to have the most constrained bullpen
  tonight." / "[Team] currently has the largest group of available relievers." /
  "[Team] shows the highest concentration of Monitor arms."
- **Contradiction (primary):** the available column was selected on raw count
  and ignored each team's reconciled shape. A deep, genuinely constrained pen
  (many available arms in absolute terms *and* a heavy restricted block) could
  top "most available" while a single restricted arm placed it in "most
  constrained." A healthy pen with one Avoid arm could likewise leak into the
  constrained column purely because `restricted > 0`. This is the exact
  "healthiest and most constrained at the same time" read.

### Team Bullpen Shape / Scoring Foundation — `classify_bullpen_health`, `build_team_context`
- **Inputs:** Available / Monitor / Limited / Avoid / Unavailable counts; freshness.
- **Weighting:** priority order, first match wins — no_data → constrained
  (restricted ≥ 40% or available == 0) → monitoring (monitor ≥ 40% or dominant)
  → elevated (restricted ≥ 20% or available < 40%) → manageable.
- **Output labels:** the five HEALTH_LABELS strings.
- **Contradiction:** none internally. This already produces exactly one
  reconciled state per team. It is the authority the other surfaces should defer
  to. Its only weakness is the pooling noted in Deliverable #2.

### Team Bullpen Stress — `services/bullpen_stress.py`
- **Inputs:** the team context `health.state`; freshness override.
- **Weighting:** maps health state to a stress label; stale data forces "No Read."
- **Output labels:** Manageable · Monitoring · Elevated · Constrained · No Read.
- **Contradiction:** consistent with shape because it is derived from the same
  `health_state`. Safe.

### Team Operations Bullpen Readiness — `team_operations/bullpen_readiness.py`
- **Inputs:** availability distribution, workload pressure (presence checks),
  coverage/handedness inventory, trust + freshness metadata.
- **Weighting:** freshness/trust/coverage gates → data_limited; any elevated
  workload or any unavailable → operationally_stressed; any
  monitor/limited/avoid/moderate → operationally_constrained; else
  operationally_stable.
- **Output labels:** Operationally Stable / Constrained / Stressed / Limited Visibility.
- **Contradiction (secondary):** this uses **binary presence checks**, while
  shape uses **percentage thresholds**. A team can read operationally_stressed
  here (one unavailable arm present) yet manageable on the board (that arm is a
  small fraction of the pool). These are different questions surfaced on
  different panels; the divergence is explainable but worth narrowing later. Out
  of scope for this branch — the readiness/availability engines are change-frozen.

### Team comparison — `services/bullpen_comparison.py`
- **Inputs:** two board payloads. **Weighting:** raw count observation per
  dimension; weaker of the two confidences wins. **Output:** similar / differ /
  no_data. **Contradiction:** none; it reports raw differences, makes no health claim.

### Hero Story / "What BaseballOS Sees Today" / Most Rested / Bullpen To Watch / Story Feed
- **Status:** not implemented as named surfaces. They exist only in product
  strategy docs. The shipped equivalents are the three landscape columns above
  ("most available" ≈ rested/healthy, "most constrained" ≈ stressed,
  "monitoring concentration" ≈ to watch). The audit therefore concentrates on
  the landscape, which is where the contradiction actually reaches the public.

---

## Deliverable #2 — Reconciliation Strategy

**Principle.** The system should answer *"how usable is this bullpen today?"* not
*"how many rested arms exist?"* Each team's reconciled `health_state` already
answers the usability question. It must be the hierarchy that governs every
opposing public read.

**Rule applied (this branch):** a team's `health_state` gates the landscape.
- A bullpen may headline **"most constrained"** only if its own shape is
  `constrained`.
- A bullpen may headline **"most available"** only if its own shape is **not**
  `constrained`.

These two sets are now provably disjoint, which directly closes the
"healthiest AND most stressed" question. The change lives entirely in the
interpretation layer (`build_landscape`); the availability engine, fatigue
engine, schema, trust architecture, and page structure are untouched.

**Trust Arm Availability vs Clean Options.** The vision's concern — that five
clean depth arms with zero clean trust arms is not truly "healthy," and two
elite trust arms with no depth is not truly "rested" — is real, but the shipped
model pools all relievers and has no trust/depth tier today. Encoding
trust-over-depth weighting would require a new per-pitcher tier signal feeding
`classify_bullpen_health`. That is a deliberate, separate piece of work that
touches the scoring foundation and should not be smuggled into a validation
branch. **Recommendation:** capture it as the next step; do not implement here.
The reconciliation gate above already removes the public contradiction without
it.

---

## Deliverable #3 — Overall Bullpen Shape: needed?

**Recommendation: No new public "Overall Bullpen Shape" score. Yes to a single
reconciliation authority — which already exists as `health_state`.**

The need behind the request is legitimate: outputs were measuring rest, trust,
depth, and pressure independently without reconciling them. But the correct
remedy is to *enforce* the existing reconciled state, not to introduce a
parallel Strong/Stable/Mixed/Stressed/Constrained/Limited-Read scoring system.
A second scoring layer would (a) duplicate `classify_bullpen_health`, (b) create
a fresh opportunity for the new score and the existing state to disagree —
reintroducing the very contradiction class we are closing — and (c) drift toward
the scorecard this branch is explicitly constrained against. The existing five
shape states already span the intended outcomes (manageable ≈ Strong/Stable,
monitoring/elevated ≈ Mixed, constrained ≈ Constrained/Stressed, no_data ≈
Limited Read). Elevating that one state to govern all public reads is the
reconciliation layer. If rankings are built later, they should rank on this
single authority.

---

## Deliverable #4 — Code Changes

- **Branch:** see commit metadata.
- **Files modified:**
  - `backend/services/game_context.py` — `build_landscape` now gates the
    "most available" and "most constrained" columns by each team's reconciled
    `health_state`, guaranteeing the two opposing reads are mutually exclusive;
    imports `HEALTH_CONSTRAINED`.
  - `backend/tests/test_game_context.py` — added two invariant tests: a
    constrained-shape club with the most available arms never headlines the
    available frame, and a manageable club with one restricted arm never
    headlines the constrained frame; both assert the frames are disjoint.
- **Tests run:** full backend suite (592 passed) and full frontend suite
  (280 passed).
- **Build:** `vite build` succeeded (pre-existing chunk-size advisory only).
</content>
