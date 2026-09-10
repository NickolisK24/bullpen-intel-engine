# Canonical Roster Context — Audit & Design

Status: Audit / Design proposal (no behavior change in this document)
Scope: Roster-context counts and copy across Story, Digest, Today, Bullpen Board, Team Board
Principle: **Filters change which cards are visible. Filters never change roster reality.**

---

## 1. Why this exists

BaseballOS has reached the same trust/coherence problem the Story system had
before canonical stories existed: roster-context numbers are computed in several
places, over several different populations, and some of them change when only the
UI filter changes. A number that moves when the user flips a view — without the
underlying roster changing — reads as "the product is guessing," which is exactly
the credibility failure canonical stories were created to end.

### Observed incoherence (New York Yankees)

| Field | Active view | Active + Unavailable | Unavailable Only |
|---|---|---|---|
| Bullpen Arms | 8 | 8 | 8 |
| Unavailable Pitchers | 0 | 6 | 6 |
| Off Roster (not shown) | 10 | 2 | 2 |

`Bullpen Arms` is stable, but `Unavailable Pitchers` and `Off Roster (not shown)`
both move, and their **sum** moves too (10 → 8). The roster did not change; only
the filter did. This violates the product principle.

---

## 2. Current-state findings

### 2.1 Root cause (code-confirmed)

The board's roster-context summary is computed **per request, parameterized by the
same `include_stale` flag the UI toggles between views.**

Flow (Tonight's Bullpen Board):

1. `frontend .../board/TonightsBullpenBoard.jsx:91-92` sets the fetch param:
   `bullpenViewModeRequiresUnavailableContext(boardViewMode) ? { include_stale: true } : {}`.
   - `Active` view → `include_stale` omitted (false).
   - `Active + Unavailable` and `Unavailable Only` → `include_stale: true`.
2. `backend/api/bullpen.py` `get_team_bullpen_board` → `_build_team_board(team_id, include_stale)`.
3. `_build_team_board` (`api/bullpen.py:1479-1484`) →
   `_eligible_records_for_rows(context_rows, ..., include_stale=include_stale)`.
4. `_eligible_records_for_rows` (`api/bullpen.py:1317-1324`) calls
   `eligible_bullpen_pitcher_contexts(..., include_stale=True, include_inactive_context=include_stale)`.
   **`include_inactive_context` is bound to the request's `include_stale`.**
5. `eligible_bullpen_pitcher_contexts` (`bullpen_population.py:120-150`) returns
   `roster_status_summary(roster_statuses, contexts)`, where `contexts` (the
   "included records") is gated by `include_inactive_context`.
6. `roster_status_summary` (`roster_status.py:633-689`) derives:
   - `active_mlb_count`, `inactive_context_count` from **`included_records`** (view-dependent input)
   - `excluded_inactive_count` from `statuses` minus `included_records`
   - `known_count`, `unknown_count`, `total_candidates` from the full `statuses`.
7. The summary is attached to the board payload as `roster_status`
   (`api/bullpen.py:1552`) and rendered by
   `frontend .../board/tonightsBullpenBoardView.js:getRosterStatusSummaryView`
   → `BullpenBoardView.jsx:RosterStatusBanner`.

**Consequence:** in the `Active` view, no inactive pitcher is in `included_records`,
so `inactive_context_count = 0` and every roster-inactive arm falls into
`excluded_inactive_count` ("Off Roster (not shown) = 10"). In the expanded views,
the eligible inactive arms move into `included_records`, so `inactive_context_count`
jumps to 6 and `excluded_inactive_count` drops. The number the banner calls
"Unavailable Pitchers" is therefore a **function of the request**, not of the roster.

The sum also drifting (10 → 8) indicates the candidate population / classification
that feeds the summary is itself not held stable across the two requests, so even
the "total roster-inactive" figure is not currently guaranteed invariant. The
canonical model must fix the *population definition*, not just the shown/not-shown
split.

### 2.2 Multiple definitions of "roster unavailable / inactive" (canonical drift)

There is **no single source of truth.** At least three distinct predicates exist:

| # | Definition | Predicate | Population | File | Consumed by |
|---|---|---|---|---|---|
| A | `roster_status_summary` | inactive = `is_inactive_context`; active = `is_active_mlb is True` | included_records + full statuses (request-dependent) | `roster_status.py:633-689` | Board banner, Team Board, Changes, Home(board) |
| B | `_is_roster_unavailable` (×3 identical copies) | `is_inactive_context is True OR is_active_mlb is False` | the records passed in (capacity uses an `include_stale=True` set) | `bullpen_capacity.py:111-116`, `bullpen_resource_health.py:166-170`, `bullpen_stability.py:182-188` | capacity %, resource-health counts, stability |
| C | `build_injury_context` | `INACTIVE_STATUSES` membership + `is_active_mlb is False`, **bullpen-role filtered** (excludes starters/position players), split IL vs non-IL | all team pitchers vs the active set | `injury_context.py:261-379` | Story → (Digest, Today via canonical story) |

Definition B is duplicated three times verbatim (drift waiting to happen).
Definition C deliberately differs (bullpen-eligible, role-filtered) and is what the
Story/Digest read. So "how many arms are unavailable/off-roster" can legitimately
return different numbers depending on which surface asks — the canonical-story
problem, re-created for roster context.

### 2.3 Where roster context changes with the UI view/filter

- `include_stale` is set from the view mode and changes the backend summary (§2.1).
- `frontend tonightsBullpenBoardView.js:filterBoardForViewMode` re-filters cards and
  **recomputes** `group.count` and `total_pitchers` on the client (it derives display
  numbers from the filtered card set).
- `getRosterStatusSummaryView` then renders whatever (view-dependent) `roster_status`
  payload arrived, so the banner inherits the view-dependence.

### 2.4 Counts without clean evidence

`roster_status_summary` is **counts-only** — it carries no pitcher identities. So:

- `Off Roster (not shown)` shows a number with **no expandable list** of who those
  arms are. The user cannot inspect the evidence behind the count.
- `Roster Unknown` and `Roster Status Coverage` are numbers with no drill-down.
- `inactive_context_count` arms do have cards (evidence) — but only in the views
  where `include_stale` happened to include them.

This violates the product rule that every user-facing count must map to visible or
expandable evidence.

### 2.5 Do the five surfaces share definitions?

**No.** Story/Digest/Today (via the canonical story) read Definition C
(`injury_context`); the Bullpen Board / Team Board banner reads Definition A
(`roster_status_summary`); capacity/health/stability reads Definition B. They are
not reconciled, and only A is request-parameterized.

### 2.6 Naming / baseball-language problems

- **"Unavailable Pitchers"** is overloaded. The board already has an *availability*
  status "Unavailable" (workload/rest based) **and** a *roster* "Unavailable"
  (IL/optioned/40-man). The banner's "Unavailable Pitchers" actually means
  *roster-inactive arms shown as cards*, which is a third meaning. Three different
  "unavailable"s on one screen.
- **"Off Roster (not shown)"** fuses a **roster fact** ("off the active roster")
  with a **UI state** ("not shown"). Because "not shown" depends on the view, the
  label guarantees the number will look unstable.
- **"Bullpen Arms" = `active_mlb_count`** is invariant *by luck* (active arms are in
  every view's `included_records`); it is still computed from the view-dependent
  input and is one filter change away from moving.
- Internal engine phrasing (`inactive_context`, `is_active_mlb`, "stale") is concept-
  leaking into user-facing meaning even where the literal words are hidden.

---

## 3. Proposed Canonical Roster Context contract

### 3.1 Design rules (mirroring canonical stories)

1. **One source of truth.** Exactly one backend builder computes roster context for a
   team: `build_canonical_roster_context(team_id, reference_date)`.
2. **One definition per field.** Every count is defined once, with one predicate.
3. **Computed over a fixed population**, independent of any request flag, view mode,
   `include_stale`, or which cards render.
4. **Every surface consumes the same object.** Story, Digest, Today, Bullpen Board,
   Team Board read these fields; none recompute their own roster truth.
5. **Filters are display-only.** A filter selects which cards render. It may compute a
   *view-dependent display* number (`visible_bullpen_cards`) but may never change any
   canonical roster count.
6. **Every displayed count carries an evidence list** (pitcher identities + reason),
   so any number is inspectable.

### 3.2 Canonical population (the invariant universe)

`roster_context.population` = the team's **bullpen-eligible pitchers** (relievers and
bullpen-eligible swing arms; starters and position players excluded, per the Role
Authority rules already in `bullpen_population` / `injury_context`), each carrying:
- canonical `roster_status` (`classify_roster_status`)
- tonight's availability read (the existing availability classification)

This universe is the same regardless of view. Membership does **not** depend on
`include_stale`.

### 3.3 Field contract

Legend — **Inv** = invariant across filters; **View** = may change with the view.

| Field | Meaning | Source / predicate | Inv | View | Surfaces | Evidence | Baseball-facing label |
|---|---|---|:--:|:--:|---|---|---|
| `bullpen_arms` | Relievers on the **active MLB roster** (the club's current bullpen), regardless of tonight's read | canonical population where `roster_status.is_active_mlb is True` | ✅ | ❌ | Board, Team Board, Story, Today | list of active-roster relievers | **Bullpen Arms** |
| `active_bullpen_arms` | `bullpen_arms` that are **usable tonight** (availability read not Unavailable) | `bullpen_arms` minus `unavailable_count` | ✅ | ❌ | Board, Story, Today | the usable arms | **Available to pitch tonight** |
| `available_count` | Active-roster arms read **Available** | availability read = Available over `bullpen_arms` | ✅ | ❌ | Board snapshot, Dashboard, Compare | arms in Available | **Available** |
| `monitor_count` | Active-roster arms read **Monitor** | availability read = Monitor | ✅ | ❌ | same | arms in Monitor | **On Watch** |
| `limited_count` | Active-roster arms read **Limited** | availability read = Limited | ✅ | ❌ | same | arms in Limited | **Limited** |
| `avoid_count` | Active-roster arms read **Avoid** | availability read = Avoid | ✅ | ❌ | same | arms in Avoid | **Avoid** |
| `unavailable_count` | Active-roster arms read **Unavailable** for workload/rest reasons (on the roster but should not pitch) | availability read = Unavailable over `bullpen_arms` | ✅ | ❌ | Board, Story | arms in Unavailable + reason | **Needs Rest / Unavailable tonight** |
| `inactive_roster_context_count` | Bullpen arms **off the active roster** (IL, optioned/minors, 40-man-not-active, DFA, etc.) — roster reality, independent of any view | canonical population where `roster_status.is_inactive_context is True` (single shared predicate) | ✅ | ❌ | Board, Team Board, Story, Today | list of off-roster arms + roster status | **Off the active roster** |
| `roster_status_coverage` | Share of bullpen-eligible candidates with an authoritative roster status | `known_count / total_candidates` over the canonical population | ✅ | ❌ | Board | candidates with/without authority | **Roster status coverage** |
| `roster_unknown_count` | Bullpen-eligible candidates whose roster status is not authoritative | `is_authoritative is False` over the canonical population | ✅ | ❌ | Board | unknown-status arms | **Roster status pending** |
| `unavailable_visible_count` | **Display only** — how many Unavailable/off-roster cards are rendered in the current view | derived on the client from the canonical evidence list ∩ current filter | ❌ | ✅ | Board only | the rendered cards | **Shown in this view** |
| `visible_bullpen_cards` | **Display only** — total cards rendered given the current filter | derived on the client from canonical population ∩ current filter | ❌ | ✅ | Board only | the rendered cards | **Cards shown** |

`evidence` lists: each *count* field above is accompanied in the canonical object by
an `evidence` array of `{ pitcher_id, name, roster_status_label, availability_label,
reason }`. The UI renders the count and, on expand, the list. The "(not shown in this
view)" qualifier is computed at render time by intersecting the evidence list with the
active filter — it is **never** a separate roster number.

### 3.4 What changes for the Yankees example

Under the canonical contract, for every view:

- `bullpen_arms = 8`, `inactive_roster_context_count = N` (one stable number),
  `roster_status_coverage`/`roster_unknown_count` stable.
- The banner shows those invariant numbers in all three views.
- Switching to `Active + Unavailable` / `Unavailable Only` changes only
  `visible_bullpen_cards` (and which cards appear), with copy like
  "Showing 6 of N off-roster arms." The roster numbers do not move.

### 3.5 Naming / copy recommendations

- Replace the banner's **"Unavailable Pitchers"** with **"Off the active roster"**
  (the roster fact) and reserve the word *Unavailable* for the workload/rest
  availability read only.
- Drop **"(not shown)"** from any roster count. Show one invariant
  **"Off the active roster: N"** with an expandable list; annotate visibility as
  "Showing X of N here," which is clearly a view statement, not a roster statement.
- Keep **"Bullpen Arms"** but source it from the canonical invariant field.
- Do **not** surface engine words (`inactive_context`, `is_active_mlb`, `stale`,
  `include_stale`) anywhere user-facing.

---

## 4. Recommended implementation phases

> Each phase is independently shippable and additive; no phase removes roster context.

- **Phase 0 — Audit & design (this document).** No behavior change.
- **Phase 1 — Canonical builder (backend, additive).** Add
  `services/roster_context.py::build_canonical_roster_context(team_id, reference_date)`
  computing the §3.3 fields + evidence over the fixed population (no `include_stale`).
  Attach it to the board payload as a new `roster_context` key **alongside** the
  existing `roster_status` (no removals). Pure addition; existing tests untouched.
- **Phase 2 — Board banner consumes canonical (frontend).** Point
  `getRosterStatusSummaryView` / `RosterStatusBanner` at `roster_context`; render the
  invariant counts identically across views; compute `visible_bullpen_cards` from the
  active filter for display only; add expandable evidence lists. Apply §3.5 copy.
- **Phase 3 — Unify backend predicates.** Replace the three duplicated
  `_is_roster_unavailable` copies (capacity/resource-health/stability) and the
  `injury_context` inactive logic with the single shared predicate / canonical object,
  so Definitions A/B/C collapse into one. Behavior-preserving where numbers already
  agree; reconcile where they do not.
- **Phase 4 — Surfaces consume canonical.** Story, Digest, Today read
  `roster_context` fields (or the story keeps its bullpen-role-filtered view but
  derives it from the canonical population). Remove per-surface recomputation.
- **Phase 5 — Decouple `include_stale` from counts.** `include_stale` controls only
  which cards the board returns; it no longer parameterizes any roster-context count.
  Remove `roster_status` once all consumers are migrated.

---

## 5. Risks & test strategy

### Risks
- **Number shifts on release.** Making counts invariant will change at least one view's
  displayed number (by definition). Frame as a correctness fix; capture before/after
  per team.
- **Definition reconciliation (Phase 3/4).** A/B/C differ today; unifying may move
  Story/capacity numbers. Each must be diffed against current output with rationale.
- **Population definition is load-bearing.** "Bullpen-eligible" must be pinned to the
  existing Role Authority rules so the canonical universe matches what the board
  already considers a reliever.
- **Evidence volume.** Off-roster lists can be long; expandable/collapsed by default.
- **Snapshot/freshness interaction.** The canonical builder must use the same
  data-derived reference date as the board (do not reintroduce a wall-clock gate).

### Test strategy
- **Invariance contract test (new, central):** for a seeded team, request the board in
  all three view modes and assert every canonical roster-context field is byte-identical
  across views; only `visible_bullpen_cards` / rendered cards differ.
- **Evidence-maps-to-count test:** each displayed count equals the length of its
  evidence list.
- **Single-definition test:** capacity / resource-health / stability / story roster-
  unavailable counts all equal the canonical field for the same team.
- **Cross-surface parity test:** Story, Digest, Today, Board, Team Board read the same
  `inactive_roster_context_count` / `bullpen_arms` for one team.
- **Frontend view tests:** extend `frontend/tests/tonightsBullpenBoard.test.mjs` to
  assert the banner counts do not change across `filterBoardForViewMode` modes and that
  `visible_bullpen_cards` is the only view-varying number.
- **Regression guard:** keep existing `roster_status` tests green until Phase 5 removal.

---

## 6. Files likely to change in later phases

Backend
- `backend/services/roster_context.py` — **new** canonical builder (Phase 1)
- `backend/services/roster_status.py` — single shared inactive/active predicate; keep `roster_status_summary` until Phase 5 (Phase 1/3/5)
- `backend/services/bullpen_population.py` — stop binding `include_inactive_context` to request flags for the *summary*; feed the canonical population (Phase 1/5)
- `backend/api/bullpen.py` — `_build_team_board`, `_eligible_records_for_rows`, `_team_bullpen_rows`: attach `roster_context`; decouple `include_stale` from counts (Phase 1/5)
- `backend/services/bullpen_capacity.py`, `backend/services/bullpen_resource_health.py`, `backend/services/bullpen_stability.py` — remove the three `_is_roster_unavailable` copies; consume the shared predicate/object (Phase 3)
- `backend/services/injury_context.py`, `backend/services/injury_il_context.py` — derive inactive counts from the canonical population (Phase 3/4)
- `backend/services/bullpen_board.py` — thread `roster_context` into the payload (Phase 1)
- Story/Digest/Today data assembly (`backend/services/story_intelligence_service_v1.py`, `bullpen_context.py`, digest composition) — consume canonical fields (Phase 4)

Frontend
- `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js` — `getRosterStatusSummaryView` reads `roster_context`; `filterBoardForViewMode` stops feeding banner counts; add `visible_bullpen_cards` (Phase 2)
- `frontend/src/components/bullpen/board/BullpenBoardView.jsx` — `RosterStatusBanner` renders invariant counts + evidence; §3.5 copy (Phase 2)
- `frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx` — `include_stale` becomes card-visibility only (Phase 5)
- `frontend/src/components/bullpen/board/BullpenContextSummary.jsx`, `components/dashboard/*` (`Dashboard.jsx`, `injuryIlContextView.js`, `bullpenLandscapeView.js`, `FollowMyTeam.jsx`), `components/home/Home.jsx`, comparison views — consume canonical per-status/roster fields (Phase 2/4)

Tests (added/updated, not weakened)
- `backend/tests/test_roster_context.py` — **new** invariance + evidence + single-definition + cross-surface parity
- `frontend/tests/tonightsBullpenBoard.test.mjs` — banner invariance across view modes; `visible_bullpen_cards` only view-varying field
- Existing `roster_status` / board / story / capacity tests kept green through Phase 4

---

## 7. This phase's change footprint

Audit/design only. No source or test behavior was changed in this commit, so there are
no tests to run for it; the test strategy above lands with Phase 1+. The single
recommended wording change ("Off the active roster" / drop "(not shown)") is documented
here and intentionally deferred to Phase 2, where it ships together with the invariance
fix so the relabel never lands without the underlying number becoming stable.
