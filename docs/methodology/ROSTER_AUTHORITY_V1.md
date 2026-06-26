# Roster Authority V1 — Foundation

Status: **Single source of roster truth — CRC complete (CRC Phase 10).** Introduced as a pure
foundation in CRC-1; every roster/category consumer now reads from it (Bullpen Board, the
Capacity family, the editorial Story/Digest, the public pitcher labels, and the Home page), no
consumer keeps a private roster status set or roster predicate, and the legacy board
`roster_status` summary has been retired (CRC-10) — the board now ships exactly one
roster-context payload. This document is the governance contract for the object; each phase is
recorded in its own section below.

Companion audit: `docs/methodology/CANONICAL_ROSTER_CONTEXT_AUDIT_AND_DESIGN.md`.

Module: `backend/services/roster_authority.py`
Tests: `backend/tests/test_roster_authority.py`,
`backend/tests/test_roster_authority_categories.py` (CRC-6),
`backend/tests/test_editorial_roster_authority_migration.py` (CRC-7),
`backend/tests/test_roster_authority_final_consolidation.py` (CRC-8),
`backend/tests/test_roster_authority_board_payload.py` and
`frontend/tests/homePresentation.test.mjs` (CRC-10 legacy retirement)

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
  "category_counts": { <category>: int, ... },     // CRC-6; one entry per canonical category
  "evidence": { <field>: [ <evidence entry>, ... ], ... },
  "category_evidence": { <category>: [ <evidence entry>, ... ], ... },   // CRC-6
  "field_invariance": { <field>: true, ... },
  "limitations": [ string, ... ]
}
```

Evidence entry (the same shape in `evidence` and `category_evidence`):

```
{ "pitcher_id", "name", "roster_status", "roster_status_label",
  "roster_status_category", "roster_status_category_label",   // CRC-6
  "availability", "reason" }
```

`roster_status` / `roster_status_label` are the **fine** status (e.g. `IL_60` / "60-Day
IL"); `roster_status_category` / `roster_status_category_label` are the **coarse** baseball
grouping (e.g. `injured_list` / "Injured list"). See §13.

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

---

## 13. Phase 6 — canonical roster-status categories

Status: **done.** Roster Authority now owns a small set of **roster-status categories** — a
coarse, baseball-language grouping of the fine-grained statuses. This phase **prepares** the
Story / Digest / Today migration (CRC-7); it does **not** migrate any consumer. The change is
**additive only**: existing counts, board behavior, the Capacity family, and the frontend are
all unchanged (full backend suite green).

### Why the category layer belongs in Roster Authority

A category answers "what *kind* of roster state is this arm in?" — injured vs optioned vs
40-man vs a special list. That is the same roster truth the authority already owns at the
status level; the category is just a coarser reading of it. Today several consumers keep
their own private grouping of statuses — most visibly Resource Health's
`INJURED_LIST_STATUSES = {IL_10, IL_15, IL_60}` and the injury-context surfaces — and any
private set drifts the moment a status is added or renamed. Centralizing the grouping in the
authority means there is exactly **one** definition of "which statuses mean injured", so a
future consumer groups by calling `roster_status_category()` instead of re-deriving a set.

The categories are a **strict refinement** of the three roster predicates (§12), never a
second source of truth: every active arm is `active`, every unconfirmed arm is `unknown`, and
every off-roster arm is exactly one off-roster category. A test asserts this agreement across
every status, which is what guarantees the Capacity family (which reads the predicates) cannot
change when categories are added.

### The categories

Owned in `services/roster_authority.py`: the category keys (`ROSTER_STATUS_CATEGORY_*`), their
reading order (`ROSTER_STATUS_CATEGORY_ORDER`), their user-facing labels
(`ROSTER_STATUS_CATEGORY_LABELS`), the status→category map (`_CATEGORY_BY_STATUS`), and the
functions `roster_status_category(roster_status)` / `roster_status_category_label(category)`.

| Category key | Baseball label | Fine statuses it groups | Roster bucket (§3) |
|---|---|---|---|
| `active` | **Active roster** | `ACTIVE` | on the active roster |
| `injured_list` | **Injured list** | `IL_10`, `IL_15`, `IL_60` | off the active roster |
| `optioned_or_minors` | **Optioned to the minors** | `OPTIONED`, `MINORS` | off the active roster |
| `forty_man_not_active` | **40-man, not active** | `40_MAN_ONLY` | off the active roster |
| `restricted_or_special_list` | **Restricted or special list** | `RESTRICTED`, `SUSPENDED`, `BEREAVEMENT`, `PATERNITY` | off the active roster |
| `non_roster_depth` | **Non-roster depth** | `NON_ROSTER`, `DFA` | off the active roster |
| `unknown` | **Roster status pending** | `UNKNOWN` / unconfirmed / none | roster status unconfirmed |

`active` and `unknown` are decided by the roster predicates, not by the status map, so there is
one source of truth for "is this arm active / unknown". An off-roster status with no explicit
mapping falls back to `non_roster_depth` (never to `active` or `unknown`), so the partition
always holds even for a future status.

Labels are **baseball language only** — no internal key, no field name, no status code ever
reaches a label (asserted by test). A surface shows the label; it never invents its own
wording for a category.

### Aggregates and evidence expectations

`build_roster_authority` now publishes:

- `category_counts` — `{ <category>: int }` for **every** category in
  `ROSTER_STATUS_CATEGORY_ORDER` (zero when none), over the full population. A stable shape:
  consumers can read `category_counts['injured_list']` without checking for presence.
- `category_evidence` — `{ <category>: [ evidence entry, ... ] }`, each list the same length
  as its count and sorted deterministically (name, then pitcher id), exactly like the existing
  `evidence`.

Each evidence entry (in both `evidence` and `category_evidence`) now also carries
`roster_status_category` and `roster_status_category_label`, so any surface can group or label
an arm without re-deriving the category. No engine internals (`is_active_mlb`,
`is_inactive_context`) leak into the entry.

The category aggregates **reconcile** with the existing counts by construction (asserted by
tests):

- `category_counts['active'] == counts['bullpen_arms']`
- `category_counts['unknown'] == counts['roster_unknown_count']`
- the five off-roster categories sum to `counts['inactive_roster_context_count']`
- `sum(category_counts.values()) == population.total_candidates`

The aggregates are invariant across board views (same guarantee as every other authority
field) and JSON-serializable.

### Remaining duplicated category logic (intentionally not deleted yet)

`services/bullpen_resource_health.py` still defines `INJURED_LIST_STATUSES = {IL_10, IL_15,
IL_60}` and uses it for its IL-vs-non-IL split. It is **kept** this phase because Resource
Health still depends on it; deleting it now would break a live consumer for no benefit. The
`injured_list` category is the canonical replacement — a test pins `category_counts['injured_list']`
to Resource Health's `injured_reliever_count` over the same population, proving the migration
can swap the private set for the category **without moving a number**. The deletion happens in
CRC-7 when Resource Health (and injury context) migrate. (Per the initiative rule: do not
prematurely delete code while consumers still depend on it.)

### How Story / Digest / Today should consume in CRC-7

The categories exist so these surfaces stop counting statuses themselves:

1. **Group by category, not by status.** Read `category_counts` / `category_evidence` for
   breakdowns like "3 on the injured list, 2 optioned"; never re-derive which statuses mean
   injured. Where a surface previously used a private set (e.g. injury context's IL grouping),
   replace it with `roster_status_category() == 'injured_list'`.
2. **Label from the authority.** Display `roster_status_category_label` (or
   `ROSTER_STATUS_CATEGORY_LABELS`); do not hardcode category wording in a consumer.
3. **Retire the private sets.** Once Resource Health / injury context read the category, delete
   `INJURED_LIST_STATUSES` and any sibling set, so the grouping lives in exactly one place.
4. **Keep the legacy path until parity is proven**, then remove it — the same migration shape
   used for the board (§11) and the Capacity family (§12): diff against the authority, prove
   invariance and count↔evidence, keep tests green, then retire.

### Future expansion (design only — not implemented)

The categories are the substrate several later reads sit on; each is a finer view of the SAME
roster truth, so it belongs with the authority rather than in a consumer:

- **Authority Completeness.** Category coverage (how many arms have a *confirmed* category vs
  `unknown`) is a natural completeness signal alongside `roster_status_coverage`.
- **Replacement Readiness / Immediate Reinforcements — "who replaces who" without predictions.**
  The categories already separate "next-up depth" from "unavailable for the season": an
  `optioned_or_minors` or `forty_man_not_active` arm is a realistic, rules-eligible
  reinforcement, whereas an `injured_list` (especially 60-day) or `restricted_or_special_list`
  arm is not currently available. A future read can therefore enumerate *replacement-eligible*
  off-roster arms **purely from roster facts** — no forecasting, no projection — simply by
  filtering the off-roster categories to the reinforcement-eligible ones. That is the
  foundation for "who could replace this arm" expressed as roster eligibility, not prediction.
- **Bullpen Elasticity.** Combining `forty_man_not_active` / `optioned_or_minors` depth with
  active-roster headroom describes how easily the bullpen can be reshaped — again, roster facts
  the authority is best placed to own.
- **Organizational Relationships.** Parent-club / affiliate linkage would let
  `optioned_or_minors` arms be tied to where they actually are; that linkage is roster context
  and belongs with the authority.

These are recommendations only; none are implemented in this phase.

---

## 14. Phase 7 — editorial system migration (Story / Digest / Today)

Status: **done.** The editorial roster-context family now consumes Roster Authority's
categories instead of keeping its own status sets. Stories explain baseball; the authority
explains roster reality — and the editorial layer no longer redefines roster truth, it reads
it. Story and digest **output is unchanged** (the full backend suite is green); only the
source of the injured-vs-otherwise-off-roster split moved.

### What was migrated

`injury_context` and `injury_il_context` are the editorial layer's roster-context builders;
Story reads `injury_context` (depth-pressure observation), and the Digest and Today/feed
surfaces read the Story. Each builder previously kept a private copy of "which statuses mean
injured" and "which mean otherwise off the roster":

| Module | Removed (private roster sets) | Now reads |
|---|---|---|
| `services/injury_context.py` | `IL_STATUSES`, `NON_IL_INACTIVE_STATUSES` | `roster_status_category_for_status` — IL = `injured_list`; non-IL inactive = every off-roster category except `injured_list` (derived from `ROSTER_STATUS_CATEGORY_ORDER`) |
| `services/injury_il_context.py` | `INJURED_LIST_STATUSES`, `INACTIVE_ROSTER_STATUSES` | `roster_status_category_for_status` — `injured_list` → injured-list group; `active`/`unknown` map across; every other off-roster category → the inactive-roster group |

`bullpen_context` assembles `injury_context` unchanged; Story (`story_observation_engine`
depth-pressure observation), Digest (`digest_composer`), and the Today/feed surfaces carry the
authority-sourced counts through without computing any roster grouping of their own.

### New authority API: `roster_status_category_for_status(status)`

The editorial contexts key off a roster **status code** (and accept partial
`{'status': ...}` dicts), not a fully classified dict, so CRC-7 adds the status-code companion
to `roster_status_category`:

- `roster_status_category(roster_status)` — for a classified dict (predicate-driven); used where
  the full classification is in hand (the board population, the capacity family).
- `roster_status_category_for_status(status)` — for a bare status code. It reads the **same**
  `_CATEGORY_BY_STATUS` table, so the status→category mapping lives in exactly one place; for any
  fully classified status it returns the category `roster_status_category` would. `ACTIVE` is
  `active`; a missing / unrecognized code is `unknown`.

A test asserts the two agree for every status, so the editorial layer and the
count-level authority can never drift.

### Story / Digest now consume the authority (counts match)

Tested in `test_editorial_roster_authority_migration.py`:

- **Injury context ↔ authority.** Over a shared all-reliever population,
  `il_bullpen_arms_count == category_counts['injured_list']`,
  `non_il_inactive_bullpen_arms_count ==` the sum of the other off-roster categories, and
  `inactive_bullpen_arms_count == counts['inactive_roster_context_count']`. The injury-IL
  league `injured_list_count` / `inactive_count` reconcile the same way.
- **Story ↔ authority.** The depth-pressure observation's `cause_inputs` IL / non-IL counts —
  and the full story's `selected_observation` counts — equal the authority's `category_counts`
  over the same population.
- **Digest ↔ authority.** The digest is composed from the authority-sourced story: it carries
  the same `story_type` and passes the story's narrative through unchanged (it computes no
  roster truth of its own).
- **Output stability.** A golden test pins the depth-pressure story's headline and the inactive
  arms named in its cause paragraph — the migration moved the source of roster truth, not the
  story.

### Today surface

There is no dedicated "today" roster builder. The Today/feed and What-Changed surfaces consume
the Story (and team changes); they hold no independent roster grouping, so they inherit the
authority's categories transitively through the migrated Story. Nothing to migrate there beyond
Story/Digest.

### Remaining consumers / remaining duplicated roster logic

Legacy retained because a **live** consumer still depends on it (per the initiative rule — do
not remove duplicated logic while a consumer needs it):

- `services/bullpen_resource_health.py::INJURED_LIST_STATUSES` — the capacity family's IL split,
  not the editorial layer. A CRC-7 test pins `category_counts['injured_list']` to Resource
  Health's `injured_reliever_count`, proving the swap to the `injured_list` category will move no
  number; the deletion belongs to a capacity-family follow-up (CRC-8), not this editorial phase.
- `services/pitcher_public_labels.py::INACTIVE_ROSTER_STATUSES` / `_roster_unavailable` — a
  public-label off-roster **predicate** (the CRC-5 `is_off_active_roster` shape), outside the
  editorial roster-context family. A candidate for the same CRC-8 predicate/category cleanup.

The legacy summary `roster_status` remains on the board payload for parity / rollback, as in
CRC-2..6.

### Future Roster Authority observations (design only — not implemented)

Surfaced while migrating the editorial layer; each is roster truth a Story should *read*, never
*invent*:

- **Replacement Readiness / Immediate Reinforcements — "who replaces who" without predictions.**
  The editorial depth-pressure story already says *how many* arms are off the roster; the
  categories let a future read say *which* off-roster arms are realistically next-up
  (`optioned_or_minors`, `forty_man_not_active`) versus out-of-reach (`injured_list` 60-day,
  `restricted_or_special_list`) — purely from roster eligibility, no forecasting. That belongs
  in the authority so every surface shares one "reinforcement-eligible" definition.
- **Organizational Relationships.** Tying `optioned_or_minors` arms to their current affiliate is
  roster context the Story would narrate but should not own.
- **Bullpen Elasticity / Authority Completeness.** As noted in §12–13; the editorial layer is a
  natural consumer once these land in the authority.

These are recommendations only; none are implemented in this phase.

---

## 15. Phase 8 — final roster-category consolidation

Status: **done.** CRC-8 is the cleanup that makes Roster Authority the **single source of
roster truth** across BaseballOS. The last two consumers holding private roster grouping were
migrated; there are now **no private roster status sets and no private roster predicates** left
in any consumer. No new capability, no UI change, no behaviour change — only the source of
roster truth was unified (the full backend suite is green).

### Remaining duplicated logic removed

| Module | Removed (private roster logic) | Now reads |
|---|---|---|
| `services/bullpen_resource_health.py` | `INJURED_LIST_STATUSES = {IL_10, IL_15, IL_60}` | `roster_status_category(roster_status) == ROSTER_STATUS_CATEGORY_INJURED_LIST` — the injured count is the authority's `injured_list` category (a finer read of off-roster) |
| `services/pitcher_public_labels.py` | `INACTIVE_ROSTER_STATUSES` (12-status set) **and** the private `_roster_unavailable` predicate body | `is_off_active_roster` for a classified status, `roster_status_category_for_status` for a bare status code — `_roster_unavailable` is now a thin adapter over the authority, not its own predicate |

Both migrations are behaviour-preserving: a CRC-8 test pins Resource Health's
`injured_reliever_count` to the authority's `category_counts['injured_list']` (and the non-IL
off-roster count to the sum of the other off-roster categories), and the public label's
`_roster_unavailable` is proven equal to `is_off_active_roster` for every classified status while
still honouring bare status codes exactly as the old set did.

### Roster Authority now owns all roster/category interpretation

There is exactly one canonical interpretation of each of these, all in
`services/roster_authority.py` (over the classification primitives in
`services/roster_status.py`):

| Concept | Canonical owner |
|---|---|
| Active roster | `is_on_active_roster` |
| Off the active roster | `is_off_active_roster` |
| Roster unknown | `is_roster_status_unknown` |
| Roster categories | `roster_status_category` / `roster_status_category_for_status` / `ROSTER_STATUS_CATEGORY_*` |
| Injured list | the `injured_list` category |
| Optioned | the `optioned_or_minors` category |
| 40-man not active | the `forty_man_not_active` category |
| Restricted / special list | the `restricted_or_special_list` category |
| Per-team / per-population counts + evidence | `build_roster_authority` (`counts`, `category_counts`, `evidence`, `category_evidence`) |

Consumers across the board (Bullpen Board, Bullpen Capacity, Resource Health, Bullpen
Stability, Trust Hierarchy, the editorial Story/Digest contexts, and the public pitcher
labels) **read / display / aggregate** the authority. None classify roster status, define
categories, keep a private status set, or redefine off-roster logic.

### Remaining consumers not yet migrated (intentionally out of scope)

- **Team Board / Comparison** — explicitly out of scope for CRC (constraint). They read only
  `team` / `context` / `freshness` from board payloads and do not compute roster counts, so
  there is no private roster logic to migrate; whenever they surface roster context, they should
  read the authority.
- **Frontend** — unchanged by design; the board banner already reads `roster_authority` (CRC-4),
  and other surfaces consume backend-authored fields.

### Legacy retained only where intentionally required

- **`roster_status` legacy summary** on the board payload — **retired in CRC-10 (§18).** It was
  retained through CRC-8/9 (the CRC-9 audit found `Home.jsx` still read it); CRC-10 migrated Home
  to Roster Authority and removed the summary. The board now ships only `roster_authority`.
- **`services/roster_status.py`** — the canonical classification *source* (`classify_roster_status`,
  `INACTIVE_STATUSES`, the `STATUS_*` constants, `STATUS_LABELS`). This is not duplication; it is
  the primitive layer Roster Authority is built on. Reading `INACTIVE_STATUSES` from here, or a
  single classified field (`is_inactive_context`) off an authority-produced dict, is canonical
  consumption, not a private set.

---

## 16. Future Authority Expansion

Observations only — **none implemented.** Each is roster truth that, when BaseballOS is ready
to model it, belongs *inside* Roster Authority so every surface shares one definition and no
consumer re-derives it. Listed here so the next initiative starts from the authority, not from
scattered private logic (the exact failure CRC removed).

- **Authority Completeness.** A first-class read of how completely roster reality is known:
  category coverage (confirmed category vs `unknown`) alongside `roster_status_coverage`, plus
  per-source freshness of the classification. The natural next increment on the authority itself,
  and a prerequisite for trusting any of the reads below.
- **Replacement Readiness.** Which off-roster arms are *rules-eligible* to return to the active
  roster — `optioned_or_minors` and `forty_man_not_active` are realistically next-up;
  `injured_list` (especially 60-day) and `restricted_or_special_list` are not currently
  available. Purely roster eligibility, no forecasting. Belongs in the authority as one shared
  "reinforcement-eligible" predicate over the existing categories.
- **Immediate Reinforcements.** The specific, named arms behind a Replacement-Readiness count —
  the evidence list (who, in which category) for "who could step in", expressed as roster facts,
  not predictions.
- **Organizational Relationships.** Parent-club ↔ affiliate linkage, so an `optioned_or_minors`
  arm is tied to where it actually is. Roster context the Story would narrate but must not own.
- **Bullpen Elasticity.** How easily a bullpen can be reshaped — `forty_man_not_active` /
  `optioned_or_minors` depth combined with active-roster headroom (open 40-man / active spots).
  Roster facts the authority is best placed to own once that data is available.

**Guardrail for all of the above:** these are reads *over* roster facts (categories, eligibility,
counts, evidence) — not predictions, rankings, or recommendations. They extend the authority's
descriptive contract; they do not turn it into a projection engine. Implement none of them in
CRC; document only.

---

## 17. Phase 9 — legacy board `roster_status` retirement audit (RETAINED, then retired in CRC-10)

Status: **retained in CRC-9, retired in CRC-10 (§18).** CRC-9 set out to retire the legacy board
`roster_status` summary now that Roster Authority is the single source of roster truth. The
required pre-deletion audit found **one live production consumer still reading it** (`Home.jsx`),
and no behaviour-preserving way to remove it that phase, so — per the phase's own rule ("if
anything still depends on it, stop and document instead of deleting") — the legacy summary was
**kept** and its removal deferred. CRC-10 (§18) migrated that last consumer and completed the
retirement. Nothing was deleted in CRC-9; no behaviour changed in CRC-9.

### What the legacy path is

A team-level summary built by `roster_status_summary(...)` (`services/roster_status.py`) — note
this is the *summary*, **not** `classify_roster_status` or the `STATUS_*` constants, which are the
canonical classifier source and stay. It is assembled once via
`bullpen_population.eligible_bullpen_pitcher_contexts` (the only caller of `roster_status_summary`)
and attached to the board payload as the top-level `roster_status` key in
`bullpen_board.build_board_payload`, alongside the canonical `roster_authority`. The frontend
view-model `getRosterStatusSummaryView` is the legacy renderer.

### Audit findings (the five required proofs)

| # | Required proof | Result |
|---|---|---|
| 1 | No frontend consumer reads `board.roster_status` | **FAILS.** `frontend/src/components/home/Home.jsx:593` reads `board?.roster_status?.inactive_context_count` to render the Home "Tonight's Bullpen Picture" roster-status line. (The legacy renderer `getRosterStatusSummaryView` is otherwise dead — called only by tests.) |
| 2 | No backend consumer requires the board payload `roster_status` | **Holds.** The summary is output-only; no backend code reads `board['roster_status']` (every other backend `roster_status` read is the per-pitcher classification). |
| 3 | No tests depend on `roster_status` except legacy/parity tests | **Holds.** The assertions live in `test_roster_authority_board_payload.py` / `test_bullpen_board.py` and are parity/structure tests. |
| 4 | Roster Authority fully replaces the board-summary use case | **Partial.** The board *banner* was migrated in CRC-4 (`getRosterAuthorityView`); the Home roster-status line (proof #1) is not yet migrated. |
| 5 | Removing `roster_status` does not break internal API consumers | **FAILS for Home.** Removing the field changes Home's data source. |

### Why no behaviour-preserving removal exists

`Home.jsx` fetches the **default** board (`getTeamBullpenBoard(activeTeamId)`, no `include_stale`).
In that view the legacy `roster_status.inactive_context_count` is **structurally 0** (off-roster
arms are excluded from the legacy "included" set in the Active view — an existing test asserts
this), so the Home line **always** reads 0 → "No roster-status limits". The canonical replacement,
`roster_authority.counts.inactive_roster_context_count`, is **view-invariant** and equal to the
**full** off-roster count (e.g. 2 for the seeded team). So:

- Migrating Home to the canonical field changes the displayed value `0 → N` — a user-facing change
  (in fact the exact "correctness number shift" the CRC audit §5 anticipates), which is **out of
  scope** for this no-behaviour-change cleanup phase.
- Removing the field while leaving Home's defensive `?.… || 0` read keeps the value at 0 but leaves
  a vestigial read of a deleted key — not a clean retirement.

Either path either changes behaviour or leaves a smell, so removal is **not safe** in a phase that
forbids behaviour change. A CRC-9 regression guard
(`test_legacy_board_roster_status_retained_pending_home_migration`) locks this decision and the
exact divergence, so the legacy summary cannot be removed before Home is migrated.

### What stays (canonical sources, never legacy)

`services/roster_status.py` — `classify_roster_status`, `STATUS_*`, `STATUS_LABELS`,
`INACTIVE_STATUSES` — is the classifier source Roster Authority is built on. It is **not** the
legacy board summary and is untouched. Only `roster_status_summary` (the team-level board summary
builder) is the legacy path under review, and it too is retained for now because Home depends on
its output.

### CRC initiative status

Functionally complete: Roster Authority is the single source of roster truth, and no consumer
keeps a private roster status set or predicate (CRC-1..8). One cleanup remains — the board still
ships the legacy `roster_status` summary because `Home.jsx` reads it — so the initiative is **not
fully closed** until that final consumer is migrated.

### Recommended next initiative (CRC-10)

A small, behaviour-aware "retire legacy board roster_status" follow-up:

1. Migrate `Home.jsx:593` to read `board.roster_authority.counts.inactive_roster_context_count`
   (the view-invariant count), explicitly **accepting** the displayed-number change `0 → N` as the
   documented correctness fix (CRC audit §5), captured before/after per team.
2. With no consumer left, delete the board payload `roster_status` key, `roster_status_summary`
   and its now-unused plumbing in `bullpen_population` / `bullpen_board` / `api/bullpen`, the dead
   `getRosterStatusSummaryView` and its fixtures/tests, and the parity tests that exist only to
   guard the legacy summary.
3. Then the board ships exactly one roster-context truth and the CRC initiative is fully closed.

---

## 18. Phase 10 — CRC closeout (Home migrated, legacy board `roster_status` retired)

Status: **done. CRC complete.** CRC-10 migrated the one remaining consumer (`Home.jsx`) to Roster
Authority and retired the legacy board `roster_status` summary path. The board now ships exactly
one roster-context payload (`roster_authority`); there is no parallel roster-context truth. The
canonical classifier sources are untouched.

### Home migrated (the intended correctness fix)

The Home "Tonight's Bullpen Picture" roster line previously read
`board.roster_status.inactive_context_count`. Because Home fetches the **default** board, that
legacy count was structurally **0**, so the line always read "No roster-status limits" regardless
of reality. The line now reads the invariant
`board.roster_authority.counts.inactive_roster_context_count` and renders **"N off the active
roster"** (or "None off the active roster"). This is the correctness fix CRC-9 (§17) identified
and CRC audit §5 anticipated — a view-dependent, always-zero number becomes the true, invariant
off-roster count. The read was extracted into a testable
`homePresentationView.js::getHomeRosterStatusLine(board)` so the migration is unit-tested.

### Legacy board `roster_status` retired

The pre-deletion audit (all six required proofs) passed: no frontend consumer reads
`board.roster_status` (Home migrated; the dead `getRosterStatusSummaryView` was the only other
reader and it was tests-only), no backend consumer reads the board-level summary (it was
output-only), and the tests that depended on it were migrated to the canonical authority or
removed. Removed in CRC-10:

| Removed | Where |
|---|---|
| `roster_status` board payload key | `services/bullpen_board.py::build_board_payload` (param + key) |
| `roster_status_summary` builder | `services/roster_status.py` (the summary function only) |
| Summary plumbing (the 2-tuple return that only carried the summary) | `bullpen_population.eligible_bullpen_pitcher_contexts` / `eligible_bullpen_pitchers` and `api/bullpen.py::_eligible_records_for_rows` now return just the records; the board no longer merges the summary's limitations |
| Dead `getRosterStatusSummaryView` + its fixtures/tests | `frontend/.../tonightsBullpenBoardView.js`, `frontend/tests/fixtures/bullpenBoardFixtures.mjs`, `frontend/tests/tonightsBullpenBoard.test.mjs` |
| Legacy-only / parity assertions | board backend tests migrated to assert `roster_authority` (e.g. `inactive_roster_context_count`, `roster_unknown_count`, `bullpen_arms`); a guard now asserts the board exposes **no** `roster_status` |

Board-level roster-context **limitations** (e.g. the roster-unknown caveat) are now carried by
`roster_authority.limitations`, not the board's top-level `limitations`; the board's top-level
limitations reflect freshness only.

### Canonical classifier sources retained (never legacy)

`services/roster_status.py` — `classify_roster_status`, the `STATUS_*` constants, `STATUS_LABELS`,
`INACTIVE_STATUSES`, and `ROSTER_STATUS_UNAVAILABLE_LIMITATION` — is the classifier layer Roster
Authority is built on. It is untouched; only `roster_status_summary` (the retired board summary
builder) was removed from it. The per-pitcher `roster_status` on each board card (from
`classify_roster_status`) is canonical and remains.

### CRC initiative complete

Roster Authority is the single source of roster truth across BaseballOS. Every consumer reads /
displays / aggregates it; none classify roster status, define categories, keep a private status
set or predicate, or read a parallel board summary. The board ships one roster-context payload.
The CRC audit & design (`CANONICAL_ROSTER_CONTEXT_AUDIT_AND_DESIGN.md`) is fully realized.

### Recommended next initiative

With roster truth unified and the board on one payload, the next initiative is the descriptive,
prediction-free **Authority Completeness + Replacement Readiness** expansion outlined in §16: add
category-coverage/freshness completeness signals, then a single canonical "reinforcement-eligible"
predicate over the existing off-roster categories (with an evidence list), so Story and the board
share one definition of "who could step in" — all as reads over roster facts, never predictions.
Team Board / Comparison, when they next surface roster context, should read the authority too.
