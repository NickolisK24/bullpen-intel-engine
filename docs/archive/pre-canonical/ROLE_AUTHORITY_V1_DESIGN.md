# Role Authority V1 — Design

> **Type:** Conceptual design only. No code, schema, migration, branch, commit,
> PR, documentation edit, or implementation plan is produced here. Where signal
> bands or windows are mentioned, they are **design rationale, not implementation
> values** — exact thresholds/weights are a calibration decision deferred to build
> time and explicitly out of scope.
> **Objective:** Design *Role Authority V1* — how BaseballOS should decide whether a
> pitcher is a **bullpen arm**, a **starter**, or **ambiguous** — optimizing for
> trust, explainability, determinism, auditability, and long-term maintainability.
> **Builds on:** the Role Authority & Bullpen Population Truth Source investigation
> (decisive finding: MLB `gamesStarted` is authoritative, free, and already flowing
> through ingestion, but unused; role is currently guessed from innings length).

---

## 1. Executive Summary

**Role Authority V1 should be a deterministic, confidence-bearing classifier built
on the authoritative start signal MLB already provides — not a binary, and not a
heuristic.** It replaces "guess role from innings pitched" with "derive role from
whether the pitcher actually starts games," and — critically — it is allowed to say
*"ambiguous"* or *"not enough evidence"* instead of forcing a wrong binary.

The model has three pillars:

1. **A first-class role vocabulary that includes uncertainty:** **Starter,
   Reliever, Ambiguous**, plus an explicit **Unknown** evidence-state. Forcing
   every pitcher into Starter/Reliever is the conceptual root of the current
   contamination; openers and swingmen are *genuinely* dual, and brand-new
   call-ups are *genuinely* undetermined.
2. **An authority hierarchy with a clear spine:** **recency-weighted
   `gamesStarted` (GS/G pattern) is primary;** probable-pitcher designations and
   relief confirmations (saves/holds/games-finished) are secondary; innings
   patterns and cadence are supporting tie-breakers only. **Innings length and the
   generic position field are never primary.**
3. **Explicit, deterministic confidence** attached to every classification, derived
   from evidence quantity and agreement, and **always visible** — consistent with
   BaseballOS's existing "no fake certainty" posture.

This design removes the contamination root cause (it fixes long relievers, rehab
returns, and most rookies outright), it isolates the irreducible hard tail
(openers, swingmen, no-history call-ups) into honest Ambiguous/Unknown states
rather than confident errors, and it is **durable** because it rests on official,
free, stable signals plus an uncertainty model — not on brittle heuristics or a
fragile third-party feed. It is strong enough to be the single shared definition of
"the bullpen" beneath the Board, Follow My Team, Bullpen Stress, and What Changed —
**provided** Ambiguous/Unknown are treated as first-class everywhere and shareable
artifacts surface the role basis.

---

## 2. Role Categories

**Recommendation: three role categories plus one explicit evidence-state.**

| Category | Meaning | Cause | Default bullpen treatment |
| --- | --- | --- | --- |
| **Starter** | Pitches as a member of the rotation | Starts the games he appears in | Excluded from default bullpen population |
| **Reliever** | Pitches out of the bullpen | Appears without starting; relief context | Included in default bullpen population |
| **Ambiguous** | Genuinely dual / unresolved-by-evidence role | Conflicting evidence (opener, swingman, mid-conversion) | Included **with a visible caveat** (they do relieve) |
| **Unknown** *(evidence-state, not a role)* | Insufficient evidence to assert any role | No start history, no probables, no/ә thin logs | **Withheld** from default counts; shown only on explicit request |

**Why not Starter/Reliever only?** Because two real populations break a binary:
- **Conflicting evidence** (openers, swingmen) — the data genuinely points both ways.
- **Absent evidence** (fresh call-ups) — there is no data yet.

A binary forces a confident answer in exactly the cases where confidence is
unwarranted — which is precisely how starters leak in and relievers vanish today.

**Why distinguish Ambiguous from Unknown?** They have *different causes* and should
drive *different behavior*. Ambiguous means "we have evidence and it's mixed" → the
arm *does* relieve, so include-with-caveat. Unknown means "we lack evidence" → we
cannot assert membership, so withhold (fail-closed). Collapsing them would either
hide swing arms or fabricate membership for unknowns. Keeping them separate is the
trust-correct choice. (An optional **Opener** sub-tag within Ambiguous is worth
considering later; conceptually it is a labeled species of Ambiguous.)

---

## 3. Authority Hierarchy

**One spine, with corroboration and tie-breakers layered beneath it.**

### Primary (the spine)
- **Recency-weighted `gamesStarted` / GS-over-appearances pattern.** Per-appearance
  `gamesStarted` is the atomic truth ("did he start *this* game?"); the
  recency-weighted ratio over recent appearances is the role read. Recency weighting
  is essential so **role conversions** are caught quickly and a stale label doesn't
  persist. This is *the* authority.

### Secondary (resolve and confirm)
- **Probable-pitcher designation** (forward-looking, MLB-published). Resolves the
  case the spine cannot: a **call-up with no GS history** who is **named to start
  tonight** → Starter, even at zero prior MLB starts. The decisive resolver for
  rookies.
- **Relief confirmations** — saves, holds, games-finished. Positively confirm
  **Reliever**, especially for middle relievers who accumulate no saves/holds but
  reliably finish/enter mid-game with `gamesStarted = 0`.

### Supporting (corroboration / tie-breakers only)
- **Innings-per-outing patterns** and **appearance cadence** (every-~5-days vs.
  irregular) — used *only* to corroborate or break a near-tie, **never** to assert
  role on their own. This is the demotion of today's primary signal to its correct
  rank.
- **Roster status** (active/IL/optioned) — an **activity/eligibility** gate that is
  **orthogonal to role**. A pitcher's role doesn't change because he's on the IL;
  roster status governs whether he's *available*, not *what he is*.

### Never primary
- **Innings-pitched length** — the current mistake; a lossy proxy that cannot tell a
  3-IP relief outing from a 3-IP start.
- **The `position` field** — generically `"P"` in production; carries no SP/RP
  information.

**Decision order (conceptual):** start from the recency-weighted GS pattern →
let a known probable-start override a thin/conflicting read → confirm Reliever via
relief context when GS=0 → use innings/cadence only to break ties → never let
innings length or position originate the decision. Roster status filters activity
in parallel, not role.

---

## 4. Confidence Model

**Yes — expose confidence, deterministically, and always.** A role without a
confidence is a claim without a caveat, which is exactly what BaseballOS's trust
posture forbids.

**Confidence is confidence *in the stated classification*** — including Ambiguous.
A swingman can be **Ambiguous (High)** — we are *confident he is a swing arm*. This
reframing matters: uncertainty about *binary role* is not the same as low confidence
about *the classification we actually made*.

| Confidence | When | Example |
| --- | --- | --- |
| **High** | Ample sample **and** signals agree | Starts all recent games (GS/G ≈ 1) → Starter High; GS=0 with saves/holds over many games → Reliever High; clean ~0.5 split over a real sample → Ambiguous (swing) High |
| **Medium** | Moderate sample, or a recent role transition still settling, or single strong source | Converted reliever with a short new run of starts; probable-only rookie start |
| **Low** | Thin sample, conflicting signals, or one weak source | One spot start against a relief history; opener read |
| **None** | No usable evidence | Unknown evidence-state |

**Properties the confidence model must hold:**
- **Deterministic:** identical inputs → identical role + confidence (auditable,
  reproducible, testable).
- **Explainable:** every classification cites its evidence in plain baseball terms
  ("11 of 12 recent appearances were starts"; "named the probable starter Tuesday";
  "no starts in 30 days, 6 relief appearances").
- **Auditable:** the inputs and the rule that fired are recorded, so any
  classification can be defended after the fact.

Confidence is the mechanism that lets the product be **useful and honest at the same
time** — it can show a best read while flagging how sure it is.

---

## 5. Special-Case Handling

For each: likely classification · confidence implication · trust implication.

| Case | Likely classification | Confidence | Trust implication |
| --- | --- | --- | --- |
| **Long / multi-inning relievers** | **Reliever** | **High** (GS=0 + relief usage) | The clearest *win* — fixes today's biggest false negative (excluded as "starter"). |
| **Converted starter → reliever** | **Reliever** once recent GS→0 | Medium rising to High as the new role accrues | Recency weighting prevents a stale "Starter" label; brief transition is honestly Medium. |
| **Converted reliever → starter** | **Starter** once recent GS→1, probables corroborate | Medium→High | Same, mirrored. |
| **Rehabbing starter returning** | **Starter** (season GS history + probables) | Medium–High | A single short rehab/return outing must **not** flip him into the pen — fixes a key false positive. |
| **Rookie call-up (named to start)** | **Starter** via probable-pitcher | Low–Medium (single source) | Probables resolve the no-history case honestly. |
| **Rookie call-up (no start, no probable)** | **Unknown** → likely Reliever as relief logs appear | None → Low | Withhold until evidence exists; do not guess. |
| **Spot start by a reliever** | **Reliever** or **Ambiguous** briefly | Low–Medium | One start against a relief history shouldn't flip a clear reliever; sample-size guards matter. |
| **Swingmen** | **Ambiguous (swing)** | Can be **High** (confident it's swing) | Include on the board **with caveat**; never a confident binary. |
| **Openers** | **Ambiguous** (optionally an *Opener* tag) | Low–Medium | The hardest case: MLB credits the opener a *start* (GS=1) though he's a reliever by role. Honesty = Ambiguous, **not** Starter. |
| **Bullpen games** | Opener → Ambiguous; bulk arm → **Reliever** | Mixed | Mostly resolves cleanly; only the opener stays ambiguous. |

**Pattern:** the authoritative signal resolves the *majority* cleanly (long relief,
conversions, rehab, most rookies). The residue — **openers and swingmen** — is
*genuinely* ambiguous and is handled by saying so, not by forcing a label.

---

## 6. Trust Philosophy

**When should BaseballOS say "I don't know" rather than force Starter/Reliever?**

- **Say Ambiguous** when evidence is **conflicting** — GS says one thing while
  usage/relief context says another (opener), or the evidence is genuinely split
  (swingman). The arm has a real, mixed role; the honest label is "ambiguous /
  swing," and it should still appear in the bullpen population *with a caveat*
  because it does relieve.
- **Say Unknown** when evidence is **absent or insufficient** — no start history, no
  probable designation, no/thin logs. The honest behavior is **fail-closed**:
  withhold from default bullpen counts rather than fabricate membership.
- **Never force a binary** on either case. Forcing is the conceptual root of the
  current contamination (starters in, relievers out).

**Uncertainty must be visible.** A role chip should carry its confidence, and
Ambiguous/Unknown should read plainly ("swing role," "role not yet established") —
mirroring how BaseballOS already surfaces freshness and limitations. The brand
promise is *no fake certainty*; Role Authority must embody it at the population
level.

**Fail-safe default:** when in doubt about *membership*, prefer **withholding
(Unknown)** over a false include, and prefer **include-with-caveat (Ambiguous)**
over a confident mislabel. A missing arm a user can add back is less damaging than
a starter confidently presented as the closer.

---

## 7. Bullpen Board Implications (conceptual)

**Role Authority becomes the single, shared definition of "who is a bullpen arm,"
consumed identically by every surface.** This directly applies the anti-drift lesson
from the What Changed defect: one authority, many consumers — never re-derived per
surface.

- **Three orthogonal axes, kept separate:** **Role** (Starter/Reliever/Ambiguous/
  Unknown) · **Roster status** (active/IL/optioned/…) · **Availability** (workload
  state). The codebase already separates availability and roster; Role becomes the
  third independent pillar. A pitcher is on the board only if Role admits him AND
  roster status permits AND (for availability display) workload data exists.
- **Bullpen Board:** include **Reliever**; include **Ambiguous** with a visible
  caveat; exclude **Starter**; **withhold Unknown** from the default view (available
  on request). This replaces the innings-heuristic gate.
- **Follow My Team:** the followed team's board inherits the same population — no
  separate logic, no drift.
- **Bullpen Stress:** computed over the Role-authoritative population, so the stress
  story is no longer contaminated by starters. **Ambiguous arms should count with a
  confidence discount or be shown distinctly**, so swing pieces don't silently
  inflate perceived bullpen depth.
- **What Changed:** reports changes only for the Role-authoritative bullpen
  population, so rotation names stop leaking into the daily-change surface.

**Net:** every downstream surface gets correct membership *for free* because they all
read one authority. Role Authority is upstream of all of them.

---

## 8. Future-Proofing Assessment

Would this design survive real-world churn? **Yes, by construction — because it rests
on official, stable, player-level signals plus an explicit uncertainty model.**

| Pressure | Survives? | Why |
| --- | --- | --- |
| **Roster churn / call-ups** | ✅ | New arms are **Unknown** until evidence appears; **probables** resolve named starters immediately; relief logs resolve relievers within a game or two. Honest interim, fast convergence. |
| **Trades** | ✅ | Role derives from the pitcher's **own appearance history**, which is player-level and team-agnostic. Changing teams reassigns the *team*, not the *role*. |
| **Role conversions** | ✅ | **Recency weighting** is purpose-built for this — the label tracks the new role as recent games accumulate, with confidence honestly Medium during transition. |
| **Future MLB seasons** | ✅ (with a known seam) | `gamesStarted` and probables are decades-stable official stats, not a scraped feed. **Season boundaries** need handling — early-season thin samples should lean on prior-season GS + probables with confidence reflecting the transition — a *calibration consideration*, not a breakage. |
| **MLB API changes** | ✅ (low risk) | Depends only on long-standing official fields already in the ingested payload; no third-party fragility. |

The design is durable precisely because it does **not** depend on brittle heuristics
or a third-party role label that can change format or terms. The one permanent
limitation — openers — is a property of baseball, not of the design, and is handled
honestly via Ambiguous.

---

## 9. Risks & Tradeoffs

| Risk / tradeoff | Severity | Notes |
| --- | --- | --- |
| **Openers are irreducible** | Med | GS credits them a start; no signal cleanly resolves. Mitigated only by Ambiguous/Opener treatment — never perfectly. Accept and disclose. |
| **Recency-weighting introduces calibration surface** (window/weights) | Med | A tuning decision (deferred to build). Mitigate with determinism, auditability, and conservative transitions; never let one outing flip a clear role. |
| **Early-season / thin samples** | Med | Reliance on probables + prior-season GS; confidence must visibly reflect the transition. |
| **Ambiguous/Unknown add UX complexity** | Med | Must be communicated *simply* or they erode trust instead of building it. The states are only valuable if their copy is plain. |
| **Ambiguous arms can inflate bullpen depth** | Low–Med | Mitigate via caveat + confidence discount in stress counts. |
| **New dependency: probable-pitcher ingestion** | Low | Official and free, but forward-looking data is a new input class to maintain. |
| **Determinism vs. accuracy tension** | Low | A deterministic rule will occasionally trail reality (a just-announced role change). Acceptable and honest if confidence reflects it; the override path (future) covers the rest. |

**Core tradeoff:** a pure binary is *simpler to build and explain* but *dishonest*
on the hard tail; the three-roles-plus-Unknown model is *more honest* but requires
the product to **communicate uncertainty well**. For a trust-first product that
tradeoff is correct — the complexity buys the exact credibility the product sells.

---

## 10. Founder Guidance (brutally honest)

**1. What role categories should BaseballOS support?**
**Starter, Reliever, Ambiguous — plus an explicit Unknown evidence-state.** Three
roles for what a pitcher *is*, and a distinct "we don't have evidence yet" state for
when we can't say. Anything less forces confident wrong answers on openers,
swingmen, and fresh call-ups.

**2. Is an Ambiguous role necessary?**
**Yes — it is the linchpin.** Without it, every opener and swingman becomes a coin
flip presented as fact, which is the exact failure that started this whole
investigation chain. Ambiguous is what lets the product be honest instead of
confidently wrong.

**3. What should be the primary authority signal?**
**Recency-weighted `gamesStarted` (the GS/appearance pattern).** It is authoritative,
official, free, already in the ingested payload, player-level (survives trades), and
recency weighting handles conversions.

**4. What should be the secondary authority signal?**
**Probable-pitcher designations** (to resolve no-history call-ups and confirm
scheduled starts) and **relief confirmations** (saves/holds/games-finished) to
positively confirm relievers. Innings patterns and cadence are *supporting
tie-breakers only*.

**5. What should never be used as the primary authority signal?**
**Innings-pitched length** (the current mistake) and **the generic `position`
field** (always `"P"`). Both may corroborate; neither may originate a role.

**6. What is the biggest trust risk?**
**Openers** — MLB calls them starters (GS=1) but they pitch as relievers, so a
naive GS-only rule would confidently mislabel them. More broadly: **presenting
low-confidence or genuinely-ambiguous roles as confident binaries**, and **letting
role drift across surfaces** instead of using one shared authority. All three are
mitigated by the Ambiguous/Unknown states, visible confidence, and a single upstream
authority.

**7. Is this design strong enough to support Bullpen Stress and future shareable
reports?**
**Yes — conditionally.** It removes the contamination *root cause* and is durable
against churn/trades/conversions/seasons. The conditions: **(a)** Ambiguous and
Unknown must be first-class in every consuming surface (not flattened back to a
binary), **(b)** stress counts must respect confidence so swing arms don't inflate
depth, and **(c)** shareable artifacts must surface the role basis/confidence so a
public card is defensible to a skeptical expert. Meet those, and Role Authority V1 is
a solid enough foundation to build and amplify on. Skip them, and you will have moved
the contamination one layer downstream into the most public surfaces.

---

*Design only. No code, schema, migration, branch, commit, PR, documentation edit, or
implementation plan was produced. Signal bands and windows referenced are design
rationale; exact thresholds and weights are deferred calibration decisions outside
this conceptual model.*
