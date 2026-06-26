# Roster Authority V1 — Foundation

Status: **Foundation (CRC Phase 1).** The authority object and its pure builder exist;
no consumer reads from it yet. This document is the governance contract for the object.

Companion audit: `docs/methodology/CANONICAL_ROSTER_CONTEXT_AUDIT_AND_DESIGN.md`.

Module: `backend/services/roster_authority.py`
Tests: `backend/tests/test_roster_authority.py`

---

## 1. Purpose

Roster Authority is to roster context what the canonical story is to stories: **one
authoritative, deterministic description of a team's roster reality** that every surface
can eventually read from. Today, roster-context numbers are computed in several places
over several different populations, and some change when only a UI filter changes
(documented in the audit). Roster Authority is the single model those consumers will
migrate to, so that no consumer ever calculates its own roster truth again.

This phase establishes the model only. It does not query the database, render anything,
attach to any payload, or change any existing behavior.

---

## 2. Architecture guarantees

- **Pure.** `build_roster_authority(records, *, team=None, reference_date=None)` depends
  only on its inputs. No database, no clock, no globals.
- **Deterministic.** Identical inputs always produce an identical object; input order is
  irrelevant (evidence lists are sorted by name then pitcher id).
- **Transport-neutral.** Returns plain JSON-serializable primitives only — no ORM
  objects, no Flask, no rendering concepts. It round-trips through `json.dumps`.
- **Invariant.** Every published count is computed over the full canonical population,
  never a UI-filtered subset, so no field can change when only a view changes.
- **No parallel definitions.** Per-pitcher roster classification is read from
  `services.roster_status.classify_roster_status` (`is_active_mlb`,
  `is_inactive_context`, `is_authoritative`); availability reads use the canonical
  `services.availability` status constants. The authority introduces **no new predicate**
  for on/off the active roster.

---

## 3. The canonical population

The population is defined **once**, independent of any UI view or filter: the full
**bullpen-eligible** set for a team — relievers and bullpen-eligible swing arms (starters
and position players excluded, per the existing Role Authority rules in
`bullpen_population`) — **including** off-roster (inactive) arms and unknown-status arms.

`CANONICAL_POPULATION_FLAGS = {'include_stale': True, 'include_inactive_context': True}`
declares the fixed flags a future database-backed caller will pass to
`eligible_bullpen_pitcher_contexts` to assemble this population. They live in one place so
the population is described once and is never bound to a request. **Callers must pass the
full population and never a view-filtered subset** — the invariance guarantee depends on
it.

Each candidate falls in exactly one roster bucket (a partition of the population):

| Bucket | Predicate (canonical fields) | Count field |
|---|---|---|
| On the active roster | `roster_status.is_active_mlb is True` | `bullpen_arms` |
| Off the active roster | `roster_status.is_inactive_context is True` | `inactive_roster_context_count` |
| Roster status unconfirmed | otherwise (`is_authoritative is False`) | `roster_unknown_count` |

Tonight's availability read is a sub-classification of the **active roster only**.

---

## 4. Object shape

```
{
  "capability": "roster_authority_v1",
  "version": "<date>.foundation",
  "source": "backend",
  "invariant": true,
  "reference_date": "YYYY-MM-DD" | null,
  "team": { "team_id", "team_name", "team_abbreviation" } | null,
  "population": {
    "total_candidates": int,
    "known_count": int,
    "unknown_count": int,
    "roster_status_coverage": float   // known_count / total_candidates, 0..1
  },
  "counts": { <field>: int, ... },
  "evidence": { <field>: [ <evidence entry>, ... ], ... },
  "field_invariance": { <field>: true, ... },
  "limitations": [ string, ... ]
}
```

Evidence entry:

```
{ "pitcher_id", "name", "roster_status", "roster_status_label", "availability", "reason" }
```

---

## 5. Field contract

Every published count is **invariant** across UI filters/views and is backed by an
evidence list of the same length.

| Field | Meaning | Source / predicate | Evidence | Baseball-facing label (for consumers) |
|---|---|---|---|---|
| `bullpen_arms` | Relievers on the active MLB roster (the club's current bullpen) | `is_active_mlb is True` | the active-roster arms | **Bullpen Arms** |
| `active_bullpen_arms` | Active-roster arms with a usable tonight read (Available/Monitor/Limited/Avoid) — excludes Unavailable and arms with no current read | usable-availability subset of `bullpen_arms` | the usable arms | **Available to pitch tonight** |
| `available_count` | Active-roster arms read Available | availability = Available over `bullpen_arms` | those arms | **Available** |
| `monitor_count` | Active-roster arms read Monitor | availability = Monitor | those arms | **On Watch** |
| `limited_count` | Active-roster arms read Limited | availability = Limited | those arms | **Limited** |
| `avoid_count` | Active-roster arms read Avoid | availability = Avoid | those arms | **Avoid** |
| `unavailable_count` | Active-roster arms read Unavailable for **workload/rest** (on the roster, should not pitch) | availability = Unavailable over `bullpen_arms` | those arms | **Needs Rest / Unavailable tonight** |
| `availability_unknown_count` | Active-roster arms with no current availability read | active arms lacking an availability status | those arms | (internal completeness; not surfaced) |
| `inactive_roster_context_count` | Bullpen arms off the active roster (IL, optioned/minors, 40-man-not-active, DFA, etc.) | `is_inactive_context is True` | the off-roster arms + roster status | **Off the active roster** |
| `roster_unknown_count` | Bullpen candidates whose roster status is not authoritative | `is_authoritative is False` | the unconfirmed arms | **Roster status pending** |

`population.roster_status_coverage` = `known_count / total_candidates`. Its backing is the
`bullpen_arms` + `inactive_roster_context_count` evidence (known) versus
`roster_unknown_count` evidence (unknown).

### Invariants (asserted by tests)

- `total_candidates == bullpen_arms + inactive_roster_context_count + roster_unknown_count`
  (the three roster buckets partition the population).
- `bullpen_arms == available_count + monitor_count + limited_count + avoid_count + unavailable_count + availability_unknown_count`.
- `active_bullpen_arms == available_count + monitor_count + limited_count + avoid_count`.
- `known_count == bullpen_arms + inactive_roster_context_count`; `unknown_count == roster_unknown_count`.
- For every field: `len(evidence[field]) == counts[field]`.
- Off-roster arms are never counted in `unavailable_count` — roster Off-the-roster and
  workload Unavailable are distinct facts.

### Not part of the authority (view-dependent, by design)

`visible_bullpen_cards` and `unavailable_visible_count` from the audit are **display
numbers** — how many cards a filter renders right now. They are derived by consumers at
render time from the evidence lists intersected with the active filter, and are
deliberately absent from the authority so a UI choice can never move a roster number.

---

## 6. Evidence expectations

- Every displayed count must be inspectable: each count ships with an evidence list whose
  length equals the count.
- Evidence entries are plain, baseball-facing, and free of engine jargon: a name, the
  roster status and its human label, the availability read, and a short reason.
- Evidence is deterministically ordered (name, then pitcher id), so two builds of the same
  population produce byte-identical evidence.

---

## 7. Intended future consumers (migrate one at a time)

The audit inventory lists today's producers/consumers. Planned migration order:

1. **Tonight's Bullpen Board banner** — read `bullpen_arms`,
   `inactive_roster_context_count`, coverage, unknown from the authority; derive the
   view-only "shown in this view" number locally. Removes the include_stale-driven
   instability.
2. **Capacity / Resource Health / Stability** — replace the three duplicated
   `_is_roster_unavailable` copies with the authority's off-roster evidence/predicate.
3. **Story / Digest / Today** — read `bullpen_arms` / `inactive_roster_context_count`
   from the authority instead of `injury_context`'s separate counts.
4. **Team Board / Comparison** — same fields as the board banner.

No consumer is migrated in this phase. Each later phase migrates exactly one consumer,
diffs its output against the authority, and keeps existing tests green until the legacy
path is retired.

---

## 8. Out of scope for this phase

No UI consumption, no payload wiring, no API change, no schema change, no removal of
existing code, and no change to Story, Digest, Board, Capacity, or Resource Health
behavior. A thin database-backed entrypoint that assembles the canonical population and
calls `build_roster_authority` (then an additive `roster_authority` payload key) is the
first task of the next phase.

---

## 9. Phase 2 — board payload (parallel/additive)

Status: **done.** The canonical authority is now exposed on the bullpen board payload
alongside the legacy `roster_status`. Nothing is migrated; the board behaves exactly as
before.

What was added (additive only):
- `api/bullpen.py::build_team_roster_authority(team_id, reference_date=None)` — the
  database-backed entrypoint. It assembles the full bullpen-eligible population once via
  the existing board helpers (`_team_bullpen_rows` + `_eligible_records_for_rows`) with
  the fixed `CANONICAL_POPULATION_FLAGS`, then calls `build_roster_authority`. It never
  reads the request's `include_stale`, so its output is invariant across views.
- `services/bullpen_board.py::build_board_payload` — a new optional `roster_authority`
  parameter rendered as a `"roster_authority"` key parallel to `"roster_status"`.
- `api/bullpen.py::_build_team_board` — builds the authority from the full-population
  records it already assembles (`capacity_records`, `include_stale=True`) and passes it
  through. Reuses existing assembly; no roster population logic is duplicated.

`roster_status` is unchanged; the comparison (Team Board) output is unaffected because it
reads only `team` / `context` / `freshness` from board payloads.

### Observed parity (verification, not fixed in this phase)

For a seeded team across the Active and Active+Unavailable/Unavailable board views:

| Field | Authority | Legacy `roster_status` | Notes |
|---|---|---|---|
| `bullpen_arms` ↔ `active_mlb_count` | invariant | invariant (active arms are in every view) | **agree** in all views |
| `inactive_roster_context_count` ↔ `inactive_context_count` | invariant | **view-dependent** (0 in Active, full in expanded) | agree only in the expanded view; the legacy number moves with `include_stale` — the defect the authority removes |
| `roster_unknown_count` ↔ `unknown_count` | `0` at Phase 2 | `>= number of unknown-roster arms` | **was a gap at Phase 2; resolved in CRC-3 (§10).** The roster gate dropped unknown-roster pitchers before they reached the records. |
| `roster_status_coverage` | `1.0` at Phase 2 | `< 1.0` when unknown arms exist | same gap; resolved in CRC-3 |
| `total_candidates` | active + off-roster at Phase 2 | active + off-roster + unknown | same gap; resolved in CRC-3 |

Root of the Phase 2 `unknown` divergence: the canonical population was sourced through
`eligible_bullpen_pitcher_contexts`, whose roster gate dropped unknown-roster arms before
they became records. This is reconciled in CRC-3 (§10) by surfacing bullpen-eligible
unknown-roster candidates into the authority population — without changing the legacy path.

---

## 10. Phase 3 — completeness (unknown-roster population)

Status: **done.** The authority is now both invariant across views (CRC-2) and complete
over the canonical bullpen-eligible population (CRC-3). The legacy `roster_status`, the
board cards, capacity, resource health, story, digest, and the frontend are all unchanged.

### How unknown-roster candidates enter the population

`services/bullpen_population.py::eligible_bullpen_pitcher_contexts` gained an additive
`include_unknown_roster` flag (default `False`, so every existing caller — board, What
Changed, Follow My Team, injury context, availability population — is byte-identical).
When `True`, a pitcher whose roster status is **not yet authoritative** is no longer
dropped at the roster gate; instead the existing **role filter alone** decides bullpen
eligibility:

- Reliever / Ambiguous (bullpen-eligible by role) → **included** as an unknown-roster
  candidate.
- Starter → **excluded** (BaseballOS can already tell this arm is not a bullpen option).
- Unknown role → surfaced only in expanded mode, exactly as for active/off-roster arms.

The Roster Authority population is assembled through one shared helper,
`api/bullpen.py::_roster_authority_records`, which calls `_eligible_records_for_rows`
with the canonical `include_stale=True` and `include_unknown_roster=True`. Both the board
payload and the standalone `build_team_roster_authority` entrypoint use this one helper,
so they produce the same snapshot. (The board no longer reuses `capacity_records` for the
authority, because the capacity population must not include unknown-roster arms; capacity
behavior is therefore unchanged.)

### What `roster_unknown_count` means

The number of **bullpen-eligible** candidates whose roster status is not authoritative
(`is_authoritative is False`, i.e. an unconfirmed / `UNKNOWN` roster state). It is part of
the three-way partition of the population: `bullpen_arms` (on the active roster) +
`inactive_roster_context_count` (off the active roster) + `roster_unknown_count` =
`total_candidates`. `roster_status_coverage = known_count / total_candidates` therefore
drops below 1.0 whenever unknown candidates exist.

### Why included or excluded

- **Included:** a candidate BaseballOS can identify as bullpen-eligible *by role* belongs
  in the bullpen picture even before its roster status is confirmed — hiding it would
  understate the bullpen and erase a real arm.
- **Excluded (documented):** a candidate that is not bullpen-eligible by role (a clear
  starter) is not added just because its roster status is unknown. The role filter is the
  one authority for "is this a bullpen arm", and it is not bypassed.

This is why the authority's `roster_unknown_count` can be **smaller** than the legacy
`roster_status.unknown_count`: the legacy summary counts the unknown roster status of
*every active-roster pitcher on the team*, including starters, while the authority counts
only bullpen-eligible candidates. Over the same bullpen-eligible population the two agree
(tested); when the team has unknown-roster starters they differ for this documented,
intended reason.

### Trust and evidence visibility

Every unknown candidate maps to evidence. `evidence['roster_unknown_count']` lists each
arm as `{ pitcher_id, name, roster_status, roster_status_label, availability, reason }`
with the reason "Roster status not yet confirmed." The unknown-roster signal is surfaced,
never hidden: a reader can open the count and see exactly which arms are awaiting roster
confirmation, with the availability read BaseballOS already has for them. The authority
remains byte-identical across board views, so this completeness never reintroduces
filter-driven movement.

---

## 11. Phase 4 — first consumer migration (Bullpen Board banner)

Status: **done.** Tonight's Bullpen Board is the first consumer to read Roster Authority.
The board now *displays* roster truth; it no longer *computes* it. The legacy
`roster_status` object remains in the payload for parity and rollback.

### What migrated

The board's roster-context banner (`frontend/.../board/BullpenBoardView.jsx` →
`RosterStatusBanner`) previously read the legacy `board.roster_status` through
`getRosterStatusSummaryView`. It now reads `board.roster_authority` through a new
`getRosterAuthorityView` (`frontend/.../board/tonightsBullpenBoardView.js`). Every
roster-context value on the board is sourced from the authority:

| Banner element | Source field (Roster Authority) |
|---|---|
| Bullpen Arms | `counts.bullpen_arms` |
| Off the Active Roster | `counts.inactive_roster_context_count` |
| Roster Status Coverage | `population.roster_status_coverage` |
| Roster Status Pending | `counts.roster_unknown_count` |
| Evidence (who is off the roster / pending) | `evidence.inactive_roster_context_count`, `evidence.roster_unknown_count` |

`getRosterStatusSummaryView` (legacy) is retained and still exported/tested for rollback;
the banner simply no longer calls it.

### The board no longer owns roster truth

The only view-dependent value the banner now computes is **how many off-roster arms are
rendered as cards in the current filter** ("showing X of N here"), derived from the
rendered card list — never from the canonical counts. The canonical counts are
byte-identical across Active / Active+Unavailable / Unavailable, because they come from
`roster_authority`, which the backend already guarantees is invariant across views.
Filters change presentation; they can no longer change a roster number.

### Wording (baseball language)

- "Unavailable Pitchers" + "Off Roster (not shown)" → one invariant **"Off the Active
  Roster"** count with an expandable evidence list and a view-only "showing X of N here".
  This removes the legacy "(not shown)" framing, which fused a roster fact with a UI state.
- "Roster Unknown" → **"Roster Status Pending"** (an arm awaiting confirmation, not an
  error).
- Engine field names (`is_active_mlb`, `is_inactive_context`, status codes) never reach
  the surface — the banner and its evidence use human roster-status labels only.

### Evidence

Every displayed count is inspectable: an expandable "Who is off the active roster?"
section lists each arm (name + roster-status label + availability) straight from the
authority's evidence — the board recomputes nothing. If the banner says "Off the Active
Roster: 7", all seven are discoverable even when only one is rendered as a card.

### The pattern for later consumers

Every later migration follows this shape:
1. Read the needed fields from `roster_authority` (counts / population / evidence); never
   recompute roster truth in the consumer.
2. Keep any genuinely view-dependent presentation number derived locally from what is
   rendered, clearly separated from the canonical counts.
3. Leave the legacy source in place (parity / rollback) until every consumer is migrated.
4. Add tests proving canonical values are invariant across views, evidence matches counts,
   and the legacy payload is still present.

Remaining consumers to migrate (CRC-5+): capacity, resource health, stability, story,
digest, and the team-board / comparison surfaces — one at a time, each diffed against the
authority and kept green until its legacy path is retired. `roster_status` is removed only
after the last consumer migrates.

---

## 12. Phase 5 — capacity family migration (Capacity / Resource Health / Stability)

Status: **done.** The internal Capacity family no longer interprets roster state on its
own; it reads the single canonical roster predicates from Roster Authority. No user-facing
behavior changed (the full backend suite is green and every consumer result is unchanged).

### Root cause of the duplication

The same predicate — "off the active roster" — was copied verbatim into four engine files
as `_is_roster_unavailable` (`is_inactive_context is True or is_active_mlb is False`):
`bullpen_capacity.py`, `bullpen_resource_health.py`, `bullpen_stability.py`, and
`bullpen_trust_hierarchy.py` (a sub-component of Bullpen Capacity, assembled at
`bullpen_capacity.py` → `build_bullpen_trust_hierarchy`). Resource Health additionally
defined its own `_is_roster_unknown`, and Trust Hierarchy its own `_is_active_mlb`. Each
record-level pass (capacity, health, stability, trust) needed a per-pitcher roster verdict
and, before Roster Authority existed, had nowhere canonical to get it — so each module
re-derived roster truth.

### What was added to Roster Authority (and why it belongs there)

Three canonical predicates now live in `services/roster_authority.py`, exported and used by
the authority's own population partition as well as by the consumers:

- `is_on_active_roster(roster_status)` — `is_active_mlb is True`.
- `is_off_active_roster(roster_status)` — `is_inactive_context is True or is_active_mlb is
  False` (the historical consumer predicate, byte-for-byte; equivalent to the authority's
  off-roster bucket for authoritative data).
- `is_roster_status_unknown(roster_status)` — no authoritative read (`status == UNKNOWN` or
  `is_active_mlb is None` or no roster status).

These belong in Roster Authority, not the consumers, because they ARE the per-pitcher
roster-bucket interpretation the authority already owns: `build_roster_authority` now
partitions its population with the same `is_on_active_roster` / `is_off_active_roster`
predicates, so the count-level authority and the record-level consumers share one
definition. A predicate is the smallest unit of "roster truth"; leaving copies in consumers
is exactly the drift the initiative exists to remove.

### Consumers migrated

- **Bullpen Capacity** — `_capacity_state` and the per-record `roster_unavailable` flag now
  call `is_off_active_roster`.
- **Resource Health** — the roster-unknown / off-roster branches now call
  `is_roster_status_unknown` and `is_off_active_roster`. (It keeps its own IL-vs-non-IL
  split, which is a finer health classification the authority does not yet model — see
  below.)
- **Bullpen Stability** — `_is_fully_unavailable` and the per-record `roster_unavailable`
  flag now call `is_off_active_roster`.
- **Trust Hierarchy** (capacity sub-component) — `_is_active_mlb` → `is_on_active_roster`,
  `_is_roster_unavailable` → `is_off_active_roster`.

All four local predicate functions were removed. A regression guard
(`tests/test_authority_capacity_unification.py`) asserts no consumer still defines its own
roster predicate and that each reads the authority's.

### Remaining consumers / remaining roster logic

- Story, Digest, Today, Team Board, Comparison, and the Bullpen Board still consume their
  own roster context where applicable (the Bullpen Board banner already reads the authority
  per CRC-4); they are out of this phase's scope.
- `roster_status` (legacy summary) remains in the board payload for parity/rollback.
- Resource Health and the injury-context services still classify Injured-List membership
  (`INJURED_LIST_STATUSES`) themselves — a finer sub-classification of "off the active
  roster" the authority does not model yet (a candidate for the extension below).

### Future Roster Authority extensions (design only — not implemented)

Observed while unifying the family; each naturally belongs in the authority because it is a
finer reading of the SAME roster truth the authority already owns:

- **Roster status category / Authority Completeness.** Extend the off-roster bucket with a
  category (injured list vs optioned vs designated vs 40-man-only). Resource Health and the
  injury-context surfaces could then stop maintaining `INJURED_LIST_STATUSES` independently.
- **Immediate Reinforcements / Replacement Readiness.** The authority already enumerates the
  off-roster arms; a future read of which of them are realistically next-up (e.g. optioned
  arms on the 40-man) would let consumers reason about reinforcements without re-deriving
  roster eligibility.
- **Bullpen Elasticity.** Active-roster headroom (open 40-man/active spots) is roster truth
  the authority is well placed to own once that data is available.
- **Organizational Relationships.** Parent-club / affiliate linkage is roster context that,
  if modeled, belongs with the authority rather than in each consumer.

These are recommendations only; none are implemented in this phase.
