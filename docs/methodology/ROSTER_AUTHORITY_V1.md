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
