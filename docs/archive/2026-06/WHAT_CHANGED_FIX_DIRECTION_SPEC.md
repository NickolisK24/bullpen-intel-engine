# What Changed — Fix-Direction Spec (Planning Only)

> **Type:** Planning / specification only. No code, schema, migration, threshold,
> classification, or engine change is produced here. This is the implementation
> direction for the two defects diagnosed in
> [WHAT_CHANGED_ANCHOR_AND_ELIGIBILITY_DIAGNOSIS.md](WHAT_CHANGED_ANCHOR_AND_ELIGIBILITY_DIAGNOSIS.md).
> **Narrow by design.** Four changes only: (1) reuse the Bullpen Board's
> eligibility filtering, (2) reconcile team-local current date vs. global
> freshness, (3) improve the comparison label, (4) define validation tests.
> Everything else is explicitly out of scope.

---

## 1. Scope & Non-Goals

**In scope (the entire change):**
1. Make the `/changes` population the **same eligible bullpen set the board uses**
   (fixes starters surfacing).
2. **Reconcile** the team-local "current game" against the global
   `latest_game_date` the dashboard trusts, and surface — not hide — any lag.
3. Replace the **weekday-only label** with an unambiguous, date-bearing comparison
   label that names both ends of the window.
4. Add **validation tests** that lock all of the above and prevent regression.

**Non-goals (do NOT touch):**
- The Availability classifier, thresholds, fatigue scoring, or risk tiers.
- The reconstruction approach (as-of-anchor classification stays as built).
- The freshness *blocker* semantics for genuinely stale **global** data.
- Any new table, migration, league-wide feed, notification, or roster-transaction
  signal.
- The date-**inference** query `_team_game_dates` (see §5 — it stays unfiltered on
  purpose).

All work is confined to `backend/services/team_changes.py` plus a small shared
helper (§2) and the frontend label rendering (§4). The engine is not implicated.

---

## 2. Fix 1 — Reuse the Bullpen Board's Eligibility Filtering

**Defect recap.** `team_changes._active_team_pitchers` selects on `team_id +
active == True` only; `_appearance_changes` does the same. None of the board's
filtering is applied, so clear starters (Cole, Rodón, Schlittler) and roster-
inactive arms (IL/optioned) appear.

**The board's filter is three service-level calls** (already used in
`bullpen.py:_eligible_records_for_rows`, lines ~783–826):
- `classify_roster_status(pitcher)` → roster status,
- `allows_default_board(roster_status)` → roster gate (drops IL/optioned/minors/
  non-roster), with `allows_inactive_context` only when stale is explicitly
  requested,
- `evaluate_bullpen_eligibility(pitcher, logs, reference_date, respect_local_active=…)`
  → `.eligible` (drops clear starters via the ≥3 IP-average rule).

All three live in **services** (`services/roster_status.py`,
`services/bullpen_eligibility.py`), so `team_changes` can call them without an
api→service inversion.

**Recommended approach — extract one shared helper (prevents the exact drift that
caused this bug).**
- Introduce a single service function — conceptually
  `eligible_bullpen_pitchers(team_id)` — that returns the team's **active,
  roster-permitted, bullpen-eligible** pitchers (the same population the board
  renders). Place it where both consumers can call it (e.g. a board/eligibility
  service module), and have **both** `bullpen.py`'s board path and
  `team_changes.py` consume it.
- `team_changes` then iterates this set in `_status_changes`, and
  `_appearance_changes` restricts its `GameLog` join to these pitcher ids.
- **Why a shared helper, not an inline copy:** the root cause here was *two
  divergent definitions of "the bullpen."* Duplicating the gate inline in
  `team_changes` fixes the symptom but recreates the drift risk. One shared
  definition is the durable fix and is still narrow.

**Minimal alternative (if a refactor is undesirable now):** import
`classify_roster_status` + `allows_default_board` + `evaluate_bullpen_eligibility`
into `team_changes` and apply the identical gate inline. Acceptable, but add a
parity test (§6) so the two definitions cannot silently diverge.

**Edge cases to preserve:**
- Use the board's **default** (non-stale) gating for this followed-team card —
  `include_stale = False` semantics — matching what the user sees on the board.
- A reliever with no fatigue score is already handled (coverage limitation);
  eligibility filtering happens *before* that and should not change the limitation
  behavior.
- The **team summary** (`_team_summary`) needs no separate fix: once the iterated
  population is filtered, its status maps and Available-count/condition deltas are
  automatically computed over the eligible set.

---

## 3. Fix 2 — Reconcile Team-Local Current Date vs. Global Freshness

**Defect recap.** `current_date` is the team's most recent game log; the
dashboard's "Jun 7" is the **global** `latest_game_date`. They are never compared,
and `_freshness_blocker` gates only on global freshness — so a team whose latest
game lags the league date clears the gate and silently compares an older window.

**Direction — keep the team-local anchor, but make the lag explicit (never
silent, never blocking for legitimate off-days):**
1. Read the global `latest_game_date` from the freshness block already passed into
   `build_team_changes_payload` (the same durable value the dashboard shows).
2. Compute `team_latest_game_date = dates[0]` (already available).
3. Compare:
   - **`team_latest == global_latest`** → the team played the latest slate;
     proceed normally; no lag annotation.
   - **`team_latest < global_latest`** → the team did not (or not-yet) record the
     latest slate. **Do not block** — off-days are normal baseball — but:
     - set an explicit, structured signal (e.g. a `team_data_behind_league`
       reason code) and a plain-language limitation: *"Your team last played
       {team_latest}; league data is current through {global_latest}."*
     - surface both dates in the payload so the UI can show the real "current"
       game date rather than implying "today."
4. Keep the existing **global** stale gate unchanged (genuinely stale league data
   still short-circuits to `STATE_STALE`).

**Why not just force `current = global_latest`?** Because the team may not have
played that date; forcing it would fabricate a comparison window with no team
game in it. The correct baseball unit is the team's own last game — the fix is to
**name it honestly and flag when it trails the league**, not to overwrite it.

**Distinguishing off-day vs. ingestion lag (note, not a blocker):** with only game
logs we cannot perfectly tell "team was off" from "team's latest slate not yet
ingested." The conservative, trust-preserving behavior is identical for both:
proceed, but annotate the lag so the user is never misled. (A schedule-aware
distinction is a possible *later* enhancement, explicitly out of scope here.)

---

## 4. Fix 3 — Improve the Comparison Label

**Defect recap.** `label = f"since {anchor_date:%A}'s game"` exposes only the
anchor weekday — no date, no current-date context — so "Since Friday's Game" reads
ambiguously next to the dashboard's "Jun 7."

**Direction:**
- The label (and/or the card) must **name both ends of the window with
  unambiguous dates**, not a bare weekday. For example a backend-composed string of
  the form *"Changes since {anchor: Fri, Jun 5} → through {current: Sun, Jun 7}"*
  (exact copy at implementer's discretion; the requirement is *both dates,
  unambiguous, month+day*).
- The card should **render `current_game_date`** (the payload already carries it),
  so the user can see what the card treats as "current."
- When Fix 2 flags `team_data_behind_league`, the UI should show the lag note
  alongside the label.
- Keep the language descriptive and past-tense (no "today," no prediction); when
  `team_latest == global_latest` a relative phrase ("since your team's last game")
  is fine *in addition to* the explicit dates, never instead of them.

This is presentation-only and touches the label string in `team_changes` and the
`WhatChangedCard` rendering — no data-path change.

---

## 5. Important: Keep Date Inference and Output Population Decoupled

A subtle but load-bearing point for the implementer:

- **Date inference** (`_team_game_dates`) should remain **unfiltered** (all team
  pitchers). A team's game dates are defined by when it *played*; relievers and
  starters log on the same game days, and an unfiltered query correctly captures
  complete-game days where only a starter logged. Filtering this query to bullpen-
  only could drop legitimate game dates.
- **Output population** (status changes, appearance changes, team summary) must be
  **filtered** to the eligible bullpen set (Fix 1).

In short: **decide *when the team played* from all pitchers; decide *who to show*
from bullpen-eligible pitchers only.** Do not conflate the two.

---

## 6. Validation Tests

> Deterministic fixtures over `pitchers` + `game_logs` + `fatigue_scores` + a
> stubbed freshness block. Each test asserts payload contents from
> `build_team_changes_payload`. Engine internals are not re-tested.

### A. Eligibility (Fix 1)
1. **Starter excluded — appearance:** a clear starter (≥3 IP-avg pattern) who
   pitched in the window → **absent** from `pitcher_changes` (no `appearance`
   item).
2. **Starter excluded — status:** same starter with a status transition across
   anchor/current → **no `status_change`** item emitted.
3. **Reliever included:** a bullpen-eligible reliever who pitched → **present** as
   an `appearance`.
4. **Roster gate:** an IL/optioned reliever → **excluded** (`allows_default_board`
   false), even with workload in window.
5. **Board parity (anti-drift):** for a fixed team + date, the set of
   `pitcher_id`s eligible in `/changes` **equals** the set the board renders for
   that team (default, non-stale). This is the regression lock that prevents the
   two definitions diverging again.
6. **Team summary follows population:** Available-count and condition deltas are
   computed over the eligible set only (a starter's status does not move the team
   line).

### B. Anchor reconciliation (Fix 2)
7. **Team played latest slate:** `team_latest == global_latest` →
   `comparison.current_game_date == global_latest`; **no** `team_data_behind_league`
   reason code/limitation.
8. **Team behind league (off-day/lag):** `team_latest < global_latest` →
   payload still `STATE_CHANGES`/`NO_CHANGES` (not blocked); `current_game_date ==
   team_latest`; `team_data_behind_league` reason code **and** a limitation naming
   both dates present.
9. **Global stale unchanged:** genuinely stale global freshness → still
   `STATE_STALE` (Fix 2 does not weaken the existing gate).
10. **Non-consecutive anchor (off-day between games):** anchor and current span a
    gap → window and dates reflect the true span; appearances across the gap are
    all captured.

### C. Label (Fix 3)
11. **Label carries both dates:** the composed label/`comparison` includes the
    anchor **and** current dates with month+day; assert it is **not** a bare
    weekday-only string.
12. **Behind-league note rendered:** when reason code from test 8 is present, the
    card surfaces the lag note (frontend test).

### D. Fail-safe regressions (must still hold)
13. `<2` team game dates → `STATE_NO_BASELINE` (unchanged).
14. Missing current/anchor score for a pitcher → coverage limitation, that
    pitcher skipped (unchanged).
15. Freshness metadata missing → `STATE_STALE` (unchanged).

---

## 7. Recommended Sequencing

1. **Fix 1 first** (eligibility) — it is the highest-severity, unconditional bug
   and the most visible. Land the shared helper + parity test (test 5) before
   anything else so the population is correct.
2. **Fix 2** (anchor reconciliation) — add the global-vs-team comparison and the
   `team_data_behind_league` signal; verify it does not weaken the global stale
   gate (test 9).
3. **Fix 3** (label) — backend label string + card rendering of both dates and the
   lag note.
4. **Tests** alongside each step; finish with the full suite (§6) green.

---

## 8. Risks & Fail-Safe Preservation

| Risk | Mitigation |
| --- | --- |
| Eligibility helper extraction subtly changes board output | Parity test (test 5) pins `/changes` to the board's set; run board tests unchanged. |
| Over-blocking on team lag (hiding legitimate off-day comparisons) | Fix 2 **annotates, does not block**; only global staleness blocks (test 8 vs 9). |
| Label change leaks prediction/relative-time ambiguity | Descriptive, past-tense, explicit dates required (tests 11–12). |
| Scope creep into schedule-awareness or roster transactions | Explicitly out of scope (§1); off-day vs. lag handled identically. |
| Engine accidentally touched | No classifier/threshold/scoring edits permitted; reconstruction unchanged. |

---

## 9. Handoff Guidance

- **Surface area:** `services/team_changes.py` (population + reconciliation +
  label string), one shared eligibility helper reused by the board route, and
  `WhatChangedCard` (render both dates + lag note). Nothing else.
- **Definition of done:** starters/IL arms never appear in `/changes`; the card's
  current date matches the dashboard's `latest_game_date` whenever the team played
  it, and clearly says so when it didn't; the label names both dates; §6 tests
  pass, including the board-parity lock.
- **Owner note:** whoever implements this owns the "never mislead on
  stale/behind-league data" contract — the lag annotation (Fix 2) is the trust-
  critical piece and must not be dropped for brevity.

---

*Planning produced read-only. No application code, schema, migration, threshold,
classification, recommendation, or engine behavior was created or modified. This
document specifies direction only.*
