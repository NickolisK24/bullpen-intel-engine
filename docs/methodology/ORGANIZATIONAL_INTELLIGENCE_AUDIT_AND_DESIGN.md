# Organizational Intelligence — Audit & Design

Status: **Audit / Design proposal (no behavior change in this document).**
Scope: The next authoritative subsystem after Roster Authority — modeling a club's
**organizational bullpen flexibility** from deterministic roster facts.
Principle: **Roster Authority says who is where today. Organizational Intelligence says what
the organization can still do about it — described from facts, never predicted.**

Companion: `docs/methodology/ROSTER_AUTHORITY_V1.md` (the foundation this extends),
`docs/methodology/CANONICAL_ROSTER_CONTEXT_AUDIT_AND_DESIGN.md` (the audit/design precedent).

This phase is audit and design only. No production code is changed, no schema is altered, no
UI or API is added, and Roster Authority is untouched. Everything below is a proposal.

---

## 1. Why this exists

The Canonical Roster Context initiative is complete: Roster Authority is the single source of
roster truth, every consumer reads it, and the board ships one roster-context payload. Roster
Authority answers **"who is on the active roster, who is off it, and who is unconfirmed — with
evidence."** It is a *snapshot of state*.

A baseball operations department does not stop at state. Once it knows the bullpen is two arms
short tonight, it asks a different question:

> **"What options does this organization actually have?"**

Not *what will they do* (that is a guess), not *who should they call up* (that is a
recommendation), but *what options exist today*. That question is **organizational**, not
per-pitcher: it is about the shape of the whole org's pitching depth and the room the roster
rules leave to move it around. BaseballOS already owns every roster fact needed to begin
answering it. **Organizational Intelligence** is the subsystem that turns those facts into a
description of organizational flexibility — deterministically, with evidence, and without ever
crossing into prediction.

The product line stays consistent. BaseballOS's signature question is *"What bullpen story did
everyone miss?"* Organizational Intelligence adds *"What options does this organization actually
have?"* — and answers it the same way the rest of the product does: from facts a reader can open
and verify.

---

## 2. Vision

Organizational Intelligence is a **canonical, deterministic, evidence-backed description of a
club's bullpen flexibility**: how complete our understanding of the org is, which arms are
*rules-eligible* to reinforce the bullpen, who specifically could appear quickly, how the
roster's arms relate to one another, and how much room the org has left to reshape the bullpen
if it keeps absorbing workload.

It is to *organizational flexibility* what Roster Authority is to *roster state*: one builder,
one object, one definition per field, evidence behind every claim, invariant across views, and
**owned in exactly one place** so no consumer re-derives org truth.

It is explicitly **not** a forecasting engine, a recommendation engine, a ranking engine, or a
prospect-evaluation engine. It describes the present option space. The manager and the front
office decide what to do with it.

---

## 3. Product philosophy

Three rules, inherited from Roster Authority and sharpened for this domain:

1. **Describe options, never choices.** "These five arms are roster-eligible to be added today"
   is a fact. "They will call up X" is a prediction. "They should call up X" is a
   recommendation. Only the first belongs here.
2. **Everything is evidence-backed.** Every count, tier, relationship, and flexibility read
   ships with the named arms (and, where relevant, the roster record) behind it. A number a
   reader cannot open does not exist.
3. **Everything is deterministic and explainable.** Identical inputs always produce an identical
   object. Every field traces to a roster fact or an explicit limitation. No clock, no
   randomness, no model weights, no projection.

A fourth rule is specific to this subsystem and load-bearing:

4. **Completeness gates assertion.** The org picture is only as trustworthy as our knowledge of
   it. Organizational Intelligence measures its own completeness *first*, and every downstream
   read carries that completeness so a sparse picture can never masquerade as a confident one.

---

## 4. Think like a baseball operations department

The task's instruction is to ask *what organizational facts matter when understanding a bullpen*,
not *what data we already have*. So we start from the front-office question and only then check
what is deterministically knowable.

When a baseball ops department looks at a stressed bullpen, the organizational facts it reaches
for are:

- **How sure are we of the picture?** Which arms' statuses are confirmed by the league vs.
  stale or unknown. You do not plan a roster move on a picture you do not trust.
- **Who can we add, by rule, today?** Not "who is good" — *who is roster-eligible to be on the
  active roster today*: optioned arms in the system, 40-man arms not currently up. Distinct from
  arms who are off the roster for reasons that make them unavailable for weeks (60-day IL,
  restricted list).
- **Who specifically, and how fast?** The named arms behind that eligibility — an optioned
  reliever at Triple-A is a phone call away; a non-roster arm needs a 40-man move first.
- **How are these arms related?** A bullpen is a chain of moves. Arm A is up because Arm B went
  on the IL. Arm C is optioned "behind" Arm D. The 40-man spot Arm E occupies was opened when
  Arm F was designated. These relationships are how a front office actually reasons about depth.
- **How much room is left?** If the bullpen keeps absorbing innings, how many more moves can the
  org even make — open active-roster spots, open 40-man spots, optionable depth — before it is
  out of levers. This is a *structural* property of the org, not a score.

Those five facts are exactly the five reads this subsystem proposes:
**Authority Completeness, Replacement Readiness, Immediate Reinforcements, Organizational
Relationships, Bullpen Elasticity.** Section 7 specifies each. Section 6 first establishes,
honestly, which of these facts BaseballOS can assert deterministically *today* and which require
a new deterministic fact source — because a design that pretends to know what it cannot is the
opposite of this product.

---

## 5. Relationship to Roster Authority

Organizational Intelligence **extends Roster Authority; it never bypasses or re-derives it.**

- It **consumes** the Roster Authority object as its primary input: the categories
  (`active`, `injured_list`, `optioned_or_minors`, `forty_man_not_active`,
  `restricted_or_special_list`, `non_roster_depth`, `unknown`), the predicates
  (`is_on_active_roster`, `is_off_active_roster`, `is_roster_status_unknown`), the `category_counts` /
  `category_evidence`, and `population.roster_status_coverage`. Roster status is read, never
  reclassified.
- It is a **layer above**, in the same way the editorial Story consumes Roster Authority: Roster
  Authority owns *roster classification*; Organizational Intelligence owns *organizational
  flexibility derived from that classification*. The boundary is strict — if a question is "what
  roster status is this arm," it is Roster Authority's; if it is "what can the org do given these
  statuses," it is Organizational Intelligence's.
- Where Organizational Intelligence needs facts Roster Authority does not model (roster-move
  history, roster-size limits, affiliate structure — see §6), those are **new deterministic
  ingest layers** that classify a fact once and expose it like `roster_status` does — never
  inferred inside this subsystem.

Roster Authority's `ROSTER_AUTHORITY_V1.md` §16 already names these five reads as the natural
next expansion and sets the guardrail: *"reads over roster facts — not predictions, rankings, or
recommendations."* This document is the realization of that note.

---

## 6. The deterministic substrate: what we can assert today vs. what is missing

Determinism is non-negotiable here, so before designing the reads we audit, per fact, what
BaseballOS deterministically stores today. (Sources: `models/pitcher.py`,
`services/roster_status.py`, `services/roster_authority.py`, `services/team_assignment_sync.py`,
`services/roster_status_sync.py`, `services/role_authority.py`.)

### 6.1 Facts BaseballOS deterministically owns today

| Fact | Where |
|---|---|
| Normalized roster status (14 statuses) + raw code/description + source + `updated_at` | `Pitcher.roster_status*`, `classify_roster_status` |
| Roster category + predicates + per-category evidence | Roster Authority |
| `is_authoritative` (league-confirmed vs. fallback) per arm | `classify_roster_status` |
| `roster_status_coverage` (known / total over the bullpen-eligible population) | Roster Authority `population` |
| Current org ownership: `team_id`, `team_name`, `team_assignment_status` (ASSIGNED / NO_ORGANIZATION / UNKNOWN) + source + `updated_at` | `Pitcher.team_assignment_*`, `team_assignment_sync` |
| Current 40-man membership (indirectly, via `40_MAN_ONLY` and the `active`/`fullRoster`/`40Man`/`nonRosterInvitees` precedence) | `roster_status_sync`, `_ASSIGNMENT_SOURCE_STATUSES` |
| Role (Reliever / Starter / Ambiguous / Unknown) from `games_started` | `role_authority`, `classify_role` |
| Bullpen eligibility (role + roster) | `bullpen_population` |
| Capacity / Resource Health / Stability fields (workload pressure, churn, depth state) | the capacity family |

### 6.2 Facts a baseball ops department uses that BaseballOS does NOT yet store

These are **deterministic facts** (the league publishes them; they are not predictions) that
simply are not in our model yet. Honesty about this gap is what keeps the subsystem deterministic.

| Missing fact | Why it matters | Read it gates |
|---|---|---|
| **Roster-move history** (who was optioned/recalled/activated/designated, and when) — we store only the current snapshot | Required to assert *relationships* ("A replaced B", "E optioned behind F") from fact rather than guess | Organizational Relationships (rich form) |
| **Roster-size facts**: active-roster count vs. the day's limit (26, with known exceptions), 40-man count vs. 40 | Required to compute *headroom* (open active spots, open 40-man spots) | Bullpen Elasticity (headroom form) |
| **Affiliate / parent-club structure** (which AAA/AA club an optioned arm is at; the org's level map) | Required to place an optioned arm where it actually is | Organizational Relationships (location form) |
| **Rehab-vs-option distinction** — the API's "REHAB ASSIGNMENT" is normalized to `MINORS` | A rehabbing 40-man arm and a optioned depth arm are *different* reinforcement stories | Immediate Reinforcements (precision) |
| **Option years remaining / out-of-options / service time** | Front offices use it heavily, but it is *not required* for any read here if we are disciplined about describing eligibility-by-status, not timeline | (Deliberately out of scope — §17) |

### 6.3 The design consequence

The reads split cleanly by what they need:

- **Derivable deterministically today (from Roster Authority alone):** Authority Completeness,
  Replacement Readiness, Immediate Reinforcements. These can ship first.
- **Partially derivable today, completed by a new deterministic ingest:** Bullpen Elasticity
  (depth today; headroom once roster-size facts are ingested), Organizational Relationships
  (current parent-club/affiliate placement today; "A replaced B" once a move-history substrate
  is ingested).

Crucially, the missing facts are **deterministic data we could ingest**, not predictions. The
design therefore proposes new *fact sources* (a roster-move log, roster-size facts, an affiliate
map) classified once and consumed like `roster_status` — and **explicitly defers** any read whose
facts are absent rather than inferring them. This is the difference between "we don't know yet"
and "we guessed."

---

## 7. The five reads

Each read is a description over roster facts. None ranks, recommends, or predicts. Each is gated
by Authority Completeness so a thin picture is never dressed up as a confident one.

### 7.1 Authority Completeness — "how complete is our understanding?"

**Question:** How completely does BaseballOS know this organization's bullpen picture? This is
**completeness, not confidence** — not "how sure is the model" but "how much of the roster reality
is actually resolved by authoritative data."

**Deterministic basis (today):** Roster Authority already exposes `roster_status_coverage`,
`known_count`/`unknown_count`, and per-arm `is_authoritative` / `source` / `updated_at`.
Completeness extends these into a first-class read:

- **Status coverage** — share of the bullpen-eligible population with an authoritative roster
  status (from Roster Authority).
- **Category resolution** — share whose status resolves to a *specific* category vs. `unknown`.
- **Source mix** — how many arms are league-confirmed (`mlb_stats_api:*`) vs. fallback
  (`stored_roster_status`, `local_active_flag`, `unavailable`).
- **Freshness** — oldest and newest `updated_at` across the population; a deterministic staleness
  flag against a *passed-in* reference date (never a wall clock).
- **Completeness grade** — a deterministic descriptor (`complete` / `partial` / `sparse`), defined
  by fixed thresholds over the above, with evidence: which arms are unconfirmed/stale and why.

**Role:** Completeness is the **gate**. Every other read carries the completeness grade and an
explicit limitation when the picture is partial or sparse, so "0 reinforcements" can never be
confused between "the org has none" and "we don't know yet."

### 7.2 Replacement Readiness — "who is roster-eligible to reinforce, today?"

**Question:** Which pitchers are realistically *rules-eligible* to reinforce the active bullpen
today? **Classify only — do not rank, do not recommend.**

**Deterministic basis (today):** purely the Roster Authority categories. Off-roster arms are
partitioned into readiness **tiers** defined by what the roster rules permit *today*, not by how
good the arm is:

| Tier | Categories | Baseball meaning |
|---|---|---|
| `active_eligible` | `optioned_or_minors`, `forty_man_not_active` | On the 40-man (or optionable within it); can be added to the active roster by a routine move |
| `roster_blocked` | `injured_list`, `restricted_or_special_list` | Off the roster for reasons that make them unavailable to reinforce today (esp. 60-day IL) |
| `non_roster_depth` | `non_roster_depth` (NON_ROSTER, DFA) | Depth that would require a 40-man addition/clearance first |
| `unconfirmed` | `unknown` | Status not yet resolved — cannot be classified |

Output is **counts + evidence per tier**, with **no ordering inside a tier** and **no
"best option" marker**. The product states *what the rules allow*; the front office judges talent.

**Honest limitations carried on the read:** rehab is not distinguished from option (both
`optioned_or_minors`), and option-years are unmodeled, so `active_eligible` means
"eligible by roster status," not "guaranteed available tomorrow." These ship as limitations, not
silent assumptions.

### 7.3 Immediate Reinforcements — "who specifically, and how quickly?"

**Question:** Which rostered (or near-rostered) pitchers could realistically appear quickly?

**Deterministic basis (today):** the **named evidence** behind the `active_eligible` tier — the
specific optioned/minors and 40-man-not-active **relievers** (role-filtered), each with its
roster status, current team, and a plain reason. This is the "who could step in" list, expressed
as roster facts:

- An `optioned_or_minors` reliever on the 40-man → a recall (fast).
- A `forty_man_not_active` reliever → a selection to the active roster (fast).
- A `non_roster_depth` arm is **not** here — it needs a 40-man move first, so it is *depth*, not
  *immediate*.

This is the strongest "new" read that is **fully deterministic today**: it is a filtered,
evidence-backed view of data Roster Authority already produces. The only precision gap is
rehab-vs-option (§6.2), surfaced as a limitation. No timeline is asserted ("how quickly" is
described categorically — recall vs. selection vs. 40-man move — never as a date).

### 7.4 Organizational Relationships — "how are these arms related?"

**Question:** Can BaseballOS explain the relationships between arms — *A replaced B*, *C occupies
the spot created by D*, *E is optioned behind F*, *G is currently replacing H* — with **no
prediction and no speculation, only explainable relationships**?

**This is the read where determinism discipline matters most**, and the honest finding is a
split:

- **Deterministic from the snapshot today (Phase-1 relationships):** *placement* and
  *co-location* relationships that follow from current state alone — each off-roster arm tied to
  its current `team_id`/affiliate, and arms grouped by shared category ("these three are all on
  the 60-day IL"). These are facts now.
- **NOT deterministic today (Phase-2 relationships):** *causal/sequential* relationships — "A
  replaced B," "E is optioned behind F," "the 40-man spot G holds was opened when H was
  designated." These are **transaction-derived**: they require knowing the *sequence of moves*
  (who came up when someone went down, who was added when someone was removed). BaseballOS stores
  only the current snapshot — `team_assignment_sync` and `roster_status_sync` overwrite state and
  keep no history. **Asserting "A replaced B" from a snapshot is speculation**, and speculation is
  forbidden by this subsystem's philosophy.

**The design's answer:** relationships *belong* in Organizational Intelligence (a front office
reasons in exactly these terms), but the rich, causal relationships require a **new deterministic
substrate — a roster-move log** that records each move (pitcher, from-status, to-status,
move-type, date, source) as it is observed, append-only. With that log, "A replaced B on
2026-06-20" becomes a *fact with a record behind it*, not an inference. Until that substrate
exists, Organizational Relationships ships **only the snapshot relationships** and explicitly
scopes out the causal ones (§17). This is the baseball-first answer (relationships are central)
made determinism-honest (we assert only what we can evidence).

### 7.5 Bullpen Elasticity — "how much room is left to reshape the bullpen?"

**Question:** How much organizational flexibility remains if the bullpen keeps absorbing
workload? **A structural property — not a score, not a prediction.**

**Deterministic basis:** Elasticity is the room the org has to make moves, and it has two parts:

- **Reinforcement depth (deterministic today):** the count of `active_eligible` reinforcements
  (§7.2) — the arms the org can add by rule. Available now from Roster Authority categories.
- **Roster headroom (needs a new fact):** open active-roster spots (limit − active count) and
  open 40-man spots (40 − 40-man count). These require **roster-size facts** BaseballOS does not
  store (§6.2). They are deterministic (countable from the roster), just not yet ingested.

Elasticity is expressed as a **structural descriptor with evidence**, not a number:
`ample` / `constrained` / `rigid`, defined by fixed thresholds over (reinforcement depth +
headroom), each backed by the arms and the spot counts behind it. Examples: a club with three
optioned relievers and two open active spots is *elastic* (can absorb more); a club with a full
40-man, no open active spot, and only 60-day-IL depth is *rigid* (out of routine levers — the
next move costs a DFA). Until roster-size facts are ingested, Elasticity ships the
**depth half** with an explicit "headroom unmeasured" limitation rather than guessing the limits.

---

## 8. Canonical object proposal

A single builder, mirroring `build_roster_authority`, returns one deterministic,
JSON-serializable object. Working module name: `services/organizational_intelligence.py`;
capability `organizational_intelligence_v1`.

```
build_organizational_intelligence(roster_authority, *, team=None, reference_date=None,
                                  move_log=None, roster_limits=None, affiliate_map=None)
```

It takes the **already-built Roster Authority object** (never the raw records — it reads roster
truth, it does not reclassify) plus the optional new fact sources (absent until their ingest
phases land). Proposed shape:

```
{
  "capability": "organizational_intelligence_v1",
  "version": "<date>.design",
  "source": "backend",
  "deterministic": true,
  "reference_date": "YYYY-MM-DD" | null,
  "team": { "team_id", "team_name", "team_abbreviation" } | null,

  "completeness": {                 // §7.1 — gates everything below
    "status_coverage": float,       // from roster_authority.population
    "category_resolution": float,
    "authoritative_share": float,
    "freshest_as_of": "YYYY-MM-DD" | null,
    "stalest_as_of": "YYYY-MM-DD" | null,
    "grade": "complete" | "partial" | "sparse",
    "evidence": { "unconfirmed": [entry...], "stale": [entry...] }
  },

  "replacement_readiness": {        // §7.2 — classify, never rank
    "tiers": {
      "active_eligible":   { "count": int, "evidence": [entry...] },
      "roster_blocked":    { "count": int, "evidence": [entry...] },
      "non_roster_depth":  { "count": int, "evidence": [entry...] },
      "unconfirmed":       { "count": int, "evidence": [entry...] }
    }
  },

  "immediate_reinforcements": {     // §7.3 — the named active_eligible relievers
    "count": int,
    "arms": [ { ...evidence entry, "move_type": "recall" | "selection" } ]
  },

  "relationships": {                // §7.4 — snapshot now; causal when the move log exists
    "placement": [ { "pitcher_id", "name", "current_team", "category", "reason" } ],
    "co_location": [ { "category", "members": [entry...] } ],
    "sequence": [],                 // EMPTY until the roster-move-log substrate exists
    "limitations": [ string... ]
  },

  "elasticity": {                   // §7.5 — structural descriptor
    "reinforcement_depth": int,     // = active_eligible count
    "active_headroom": int | null,  // null until roster-size facts are ingested
    "forty_man_headroom": int | null,
    "descriptor": "ample" | "constrained" | "rigid" | "unmeasured",
    "evidence": { "depth": [entry...], "headroom_basis": {...} | null }
  },

  "field_provenance": { <field>: "roster_authority" | "move_log" | "roster_limits" | "affiliate_map" },
  "limitations": [ string... ]      // every absent fact source surfaces a limitation here
}
```

Every count maps to an `evidence` list of the same length (the Roster Authority invariant,
inherited). Every read carries the `completeness.grade`. Every field declares its provenance so a
reader can see exactly which fact source it came from.

---

## 9. Core fields

| Field | Meaning | Deterministic source | Available |
|---|---|---|---|
| `completeness.status_coverage` | Share of bullpen-eligible arms with authoritative status | `roster_authority.population.roster_status_coverage` | **Now** |
| `completeness.authoritative_share` | Share league-confirmed vs. fallback | per-arm `is_authoritative` / `source` | **Now** |
| `completeness.grade` | `complete`/`partial`/`sparse` over fixed thresholds | the completeness inputs | **Now** |
| `replacement_readiness.tiers.active_eligible` | Arms roster-eligible to be added today | categories `optioned_or_minors` + `forty_man_not_active` | **Now** |
| `replacement_readiness.tiers.roster_blocked` | Off-roster but not addable today | `injured_list` + `restricted_or_special_list` | **Now** |
| `immediate_reinforcements.arms` | Named eligible relievers + move type | `active_eligible` evidence, role-filtered | **Now** (rehab caveat) |
| `relationships.placement` | Each off-roster arm at its current org/affiliate | `team_id`/`team_name`; affiliate map for level | Partial now / **affiliate map** for level |
| `relationships.sequence` | "A replaced B", "E behind F" | **roster-move log** | **Deferred** (needs substrate) |
| `elasticity.reinforcement_depth` | Count of addable arms | `active_eligible` count | **Now** |
| `elasticity.active_headroom` / `forty_man_headroom` | Open active / 40-man spots | **roster-size facts** | **Deferred** (needs substrate) |
| `elasticity.descriptor` | `ample`/`constrained`/`rigid`/`unmeasured` | depth (+ headroom when present) | Depth **now**; full when headroom lands |

---

## 10. Evidence model

Organizational Intelligence reuses Roster Authority's evidence entry and extends it only with
fields that are themselves facts:

```
{ "pitcher_id", "name",
  "roster_status", "roster_status_label",
  "roster_status_category", "roster_status_category_label",   // from Roster Authority
  "current_team", "current_team_id",                          // current org placement (fact)
  "readiness_tier",                                           // derived classification
  "reason" }                                                  // plain-language, fact-derived
```

- **Counts → evidence parity:** every published count equals the length of its evidence list
  (Roster Authority's core invariant, carried forward).
- **Relationships carry their own evidence:** a `sequence` relationship, when the move log exists,
  ships the move record(s) behind it (pitcher, from→to status, move-type, date, source). A
  `placement` relationship ships the assignment fact.
- **Reasons are fact-derived and baseball-language:** "On the 40-man, not active — selectable to
  the active roster" is allowed; "likely to be recalled this week" is not (that is a prediction).
- **No engine internals leak:** `is_active_mlb`, `is_inactive_context`, status codes, and source
  prefixes never reach a user-facing reason — only human roster-status and category labels, as in
  Roster Authority.

---

## 11. Determinism guarantees

Identical to Roster Authority's contract, with one addition:

- **Pure.** `build_organizational_intelligence` depends only on its inputs (the Roster Authority
  object and the optional fact sources). No database, no clock, no globals, no network.
- **Reference-date-driven, never wall-clock.** Any "stale / as-of" read uses the passed-in
  `reference_date` (the same data-derived date Roster Authority uses), so freshness is reproducible.
- **Deterministic & order-independent.** Identical inputs always produce an identical object;
  evidence lists are sorted (name, then pitcher id) exactly as Roster Authority sorts.
- **No prediction surface.** The object contains no probability, projection, score, rank, or
  recommendation field. Descriptors (`grade`, `descriptor`, `readiness_tier`) are deterministic
  functions of fixed thresholds over facts.
- **Graceful, explicit degradation (the addition).** When a fact source is absent, the dependent
  fields are `null`/empty and a corresponding entry appears in `limitations` with the field's
  `field_provenance` — the object never substitutes a guess for a missing fact.
- **Invariant across views.** Like Roster Authority, the object describes org reality and does not
  change with any UI filter or board view.

---

## 12. Governance

- **One owner.** Organizational Intelligence owns the org-flexibility reads (completeness,
  readiness, reinforcements, relationships, elasticity). No consumer re-derives them, exactly as
  no consumer re-derives roster truth today.
- **Strict layering.** It consumes Roster Authority and never reclassifies roster status. If a
  question is "what status / category is this arm," it is escalated to Roster Authority, not
  answered here.
- **New facts are classified once, elsewhere.** The roster-move log, roster-size facts, and
  affiliate map are **separate deterministic ingest layers** (each its own sync/classifier,
  modeled on `roster_status_sync` / `team_assignment_sync`). Organizational Intelligence *reads*
  them; it does not infer them. This keeps a single source of truth per fact.
- **Completeness is mandatory.** Every build computes completeness first and stamps every read
  with it; a read may not be published without it.
- **Documentation contract.** Like `ROSTER_AUTHORITY_V1.md`, an `ORGANIZATIONAL_INTELLIGENCE_V1.md`
  governance doc accompanies the first implementation phase and records each subsequent phase.

---

## 13. Future consumers

None are built in this phase; the object is designed so they *read* it and never recompute:

- **Story / Digest (editorial).** A new beat — *"the options this org has"* — naturally follows
  the existing depth-pressure story: "the bullpen is two arms short; the org has three
  roster-eligible reinforcements and two open active spots" — every number openable. The
  editorial layer narrates; it does not own org truth (same contract as the roster-context
  migration).
- **Tonight's Bullpen Board / a future "Organizational Picture" surface.** Displays completeness,
  the reinforcement tiers, and the elasticity descriptor alongside the existing roster banner.
- **The Capacity family.** Bullpen Elasticity is the natural organizational complement to Capacity
  / Resource Health / Stability (which describe *tonight's* pool); Elasticity describes the *room
  to refill it*. A future read can pair them without recomputing either.

---

## 14. Implementation phases

Each phase is independently shippable, additive, evidence-backed, and gated by completeness.
Phases follow the Roster Authority precedent: pure builder first, parallel exposure, then
consumers.

- **Phase 0 — Audit & design (this document).** No behavior change.
- **Phase 1 — Authority Completeness (foundation).** Pure builder over the Roster Authority object
  computing the completeness read (§7.1) and the object skeleton. Derivable entirely from today's
  data. Gates every later read. Ships with tests (determinism, coverage math, grade thresholds,
  evidence parity) and `ORGANIZATIONAL_INTELLIGENCE_V1.md`.
- **Phase 2 — Replacement Readiness + Immediate Reinforcements.** The deterministic tiering and the
  named reinforcement list (§7.2–7.3) — fully derivable from Roster Authority categories today.
  No new data. Tests: tier mapping per category, role-filtering, counts↔evidence, rehab limitation
  surfaced.
- **Phase 3 — Bullpen Elasticity (depth half).** The `reinforcement_depth` and a depth-only
  `descriptor` with an explicit `headroom unmeasured` limitation. Derivable today.
- **Phase 4 — Roster-size ingest → Elasticity (full).** A new deterministic ingest of roster-size
  facts (active count / day's limit, 40-man count) classified once; Elasticity gains real headroom
  and the full descriptor. New fact source, not inference.
- **Phase 5 — Affiliate map → Organizational Relationships (placement/location).** Ingest the
  org/affiliate structure; `placement` relationships gain real level/location.
- **Phase 6 — Roster-move-log substrate → Organizational Relationships (sequence).** The
  append-only move log (§7.4) lands as a deterministic ingest; only then do causal relationships
  ("A replaced B") become *facts with records* and populate `relationships.sequence`. Deferred
  deliberately to last because it is the only read that cannot be made deterministic without new
  history.
- **Phase 7 — Consumers.** Editorial / board surfaces read the object (one at a time, diffed,
  tests green), never recomputing org truth.

The ordering is deliberate: everything derivable from today's deterministic data ships first
(Phases 1–3); each new *fact source* is a self-contained ingest (Phases 4–6); consumers come last.
No phase predicts, ranks, or recommends.

---

## 15. Potential risks

- **Determinism erosion (the central risk).** Pressure to answer "who *will* they call up" or
  "who *should* they." Mitigation: the object has no prediction/score/rank field by construction;
  every descriptor is a fixed-threshold function of facts; reviews reject any field that cannot be
  traced to a fact or a limitation.
- **Incompleteness masquerading as emptiness.** "0 reinforcements" could mean *none exist* or *we
  don't know*. Mitigation: completeness gates every read and is stamped on each; sparse pictures
  carry explicit limitations.
- **Relationship speculation.** Asserting "A replaced B" from a snapshot. Mitigation: causal
  relationships are *deferred* to the move-log substrate and explicitly out of scope until then;
  the snapshot only ever asserts placement/co-location, which are facts.
- **Rehab-vs-option conflation.** `MINORS` absorbs rehab assignments, so `active_eligible` can
  overstate "immediate" reinforcements. Mitigation: ship the limitation now; resolve it when a
  rehab-distinct ingest lands; never silently assume.
- **Roster-limit drift.** The active-roster limit is not a constant (26, with September/doubleheader
  exceptions). Mitigation: ingest the day's limit as a *dated fact*, never hardcode 26.
- **Snapshot staleness.** Org state changes daily; a stale sync yields a stale picture.
  Mitigation: completeness freshness reads + `reference_date` discipline make staleness visible,
  not hidden.
- **Scope creep into projection.** Elasticity especially invites a "flexibility score." Mitigation:
  it is a structural descriptor with evidence, not a number; this is stated in the governance doc.

---

## 16. Baseball examples

- **A short, well-known bullpen.** Team with 7 active relievers (1 read Unavailable), 2 on the
  60-day IL, 1 optioned to Triple-A, 1 on the 40-man not active. Organizational Intelligence:
  completeness `complete` (all league-confirmed, fresh); Replacement Readiness — `active_eligible`
  = 2 (the optioned arm + the 40-man arm), `roster_blocked` = 2 (the 60-day IL arms);
  Immediate Reinforcements names the optioned reliever (move_type `recall`) and the 40-man reliever
  (move_type `selection`); Elasticity — reinforcement_depth 2, descriptor `ample` if active spots
  are open. The story: *"down two tonight, but two roster-eligible arms behind them."*
- **A rigid org.** Full 40-man, no open active spot, the only off-roster relief depth is two
  60-day-IL arms and a DFA'd arm. Replacement Readiness — `active_eligible` = 0,
  `non_roster_depth` = 1 (needs a 40-man move), `roster_blocked` = 2; Elasticity descriptor `rigid`
  with evidence: the next reinforcement costs a designation. *"Out of routine levers."*
- **An unconfirmed picture.** Mid-season sync gap: 4 of 9 bullpen-eligible arms `unknown`.
  Completeness `sparse`; every read carries the limitation "roster picture incomplete — 4 arms
  unconfirmed"; Replacement Readiness reports the 5 known arms and lists the 4 unconfirmed in
  `unconfirmed`, never asserting "no reinforcements."
- **A relationship the snapshot cannot prove.** Arm A was recalled the day Arm B hit the IL. A
  front office reads "A replaced B." BaseballOS, with only a snapshot, **does not assert it** —
  `relationships.sequence` is empty and the limitation says "move history not modeled." Once the
  move log exists, the same scenario yields the fact "A recalled 2026-06-20; B → IL_10 2026-06-20"
  with both records attached.

---

## 17. Things explicitly out of scope

- **Predictions of any kind** — who will be called up, return dates, injury timelines, future
  availability, "likely" moves.
- **Recommendations / "who should"** — the product describes the option space; it does not choose.
- **Rankings** — no "best reinforcement," no ordering within a readiness tier, no flexibility score.
- **Talent / prospect evaluation** — readiness is by roster *rule*, not by how good an arm is; the
  prospect pipeline is not modeled.
- **Inferred causal relationships without a move record** — "A replaced B" is asserted only from a
  move log, never from a snapshot (deferred to Phase 6).
- **Option-years / out-of-options / service-time / contract / waiver inference** — useful to a
  front office but not required for any read here; deliberately excluded to avoid modeling facts we
  cannot deterministically source.
- **Any implementation in this phase** — no production code, no schema, no UI, no API, and **no
  change to Roster Authority** (the design only *consumes* it).

---

## 18. This phase's change footprint

Audit/design only. This document is the sole artifact; no source, test, schema, UI, or API was
changed, and Roster Authority is untouched. There are no tests to run for it — the test strategy
(determinism, completeness gating, tier mapping, counts↔evidence parity, graceful degradation when
fact sources are absent) lands with Phase 1. The single working name recommended here —
**Organizational Intelligence**, capability `organizational_intelligence_v1` — and the phase
ordering in §14 are the proposals to ratify before Phase 1 begins.
