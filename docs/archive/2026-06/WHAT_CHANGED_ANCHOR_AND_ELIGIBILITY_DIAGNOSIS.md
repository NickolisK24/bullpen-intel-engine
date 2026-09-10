# What Changed — Anchor & Eligibility Diagnosis

> **Type:** Diagnosis only. No fixes implemented; no application code, schema,
> migration, threshold, or classification logic changed.
> **Reported symptoms:** (1) the "What Changed Since Last Game" card shows *"Since
> Friday's Game"* even though the dashboard reports latest completed MLB data of
> **Jun 7, 2026 (Sunday)**; (2) the card surfaces **starters** — Cam Schlittler,
> Gerrit Cole, Carlos Rodón.
> **Question:** Is the date anchor wrong, is bullpen eligibility being bypassed,
> or both?
> **Code under examination:** `backend/services/team_changes.py`,
> `backend/api/bullpen.py:935-946` (`GET /api/bullpen/teams/<id>/changes`), as
> shipped on `origin/dev` (`feat: add what changed card`).

---

## 0. Verdict (one line)

**Both issues are real, but they are different in kind: the eligibility bypass is
a *definite, unconditional bug*; the date anchor is *structurally mis-scoped and
mislabeled* and is wrong in at least the way the user is seeing it, though whether
the underlying date is "incorrect" depends on one fact we must read from the
payload.** The eligibility bypass is also the higher-confidence, higher-severity
finding.

| Issue | Status | Confidence |
| --- | --- | --- |
| **Bullpen eligibility bypassed** (starters surfacing) | **Confirmed bug** | **HIGH** |
| **Date anchor / "Since Friday"** | **Mis-scoped + mislabeled** (true defect is team-local vs. global "current" mismatch and an ambiguous label) | **MEDIUM-HIGH** |

---

## 1. How the Implemented Logic Actually Works

The changes endpoint does **not** reuse the board's pitcher set or its date logic.
It builds everything from scratch in `team_changes.py`:

**Anchor / comparison dates** — `_team_game_dates(team_id)` +
`build_team_changes_payload`:
```
SELECT DISTINCT game_date
FROM game_logs JOIN pitchers ON pitchers.id = game_logs.pitcher_id
WHERE pitchers.team_id = :team_id
ORDER BY game_date DESC
LIMIT 2
```
- `current_date = dates[0]` — the team's **most recent** game date in the DB.
- `anchor_date = dates[1]` — the team's **second-most-recent** game date.
- Label: `f"since {anchor_date.strftime('%A')}'s game"` — **weekday of the anchor
  only** (no date, no year, no current-date context).

**Pitcher set** — `_active_team_pitchers(team_id)`:
```
Pitcher.query.filter(Pitcher.team_id == team_id, Pitcher.active == True)
             .order_by(Pitcher.full_name).all()
```
…and `_appearance_changes` joins `GameLog → Pitcher` filtered only by
`team_id` + `active == True` + the date window.

**What is conspicuously absent** (compared to the board path in `bullpen.py`):
- No `bullpen_eligibility` (starter exclusion).
- No `roster_status` / `allows_default_board` (IL / optioned / non-roster gating).
- No `_recent_pitcher_ids_subquery` (the board's freshness/active filter).
- No reconciliation against the durable freshness `latest_game_date`.

`team_changes.py` imports exactly: `FatigueScore`, `GameLog`, `Pitcher`,
`availability.classify_availability`, `bullpen_board.{BOARD_GROUP_ORDER,
build_team_context}`, `db`. **None of the eligibility/roster/recency modules the
board relies on are imported or called.**

---

## 2. Issue A — Bullpen Eligibility Is Bypassed (Confirmed Bug)

**This is unambiguous.** The changes service selects pitchers with nothing more
than `team_id == … AND active == True`, and lists appearances for the same
unfiltered set. Starters are *active* pitchers on the team, so:

- **Appearance changes** (`_appearance_changes`): any starter who threw in the
  window appears (e.g. *"Gerrit Cole — Pitched Saturday — 98 pitches"*). This is
  exactly the Schlittler / Cole / Rodón symptom — starters pitch in the team's
  most recent games, so they dominate the appearance list.
- **Status changes** (`_status_changes`): the loop iterates over **all** active
  pitchers (including starters), classifies each with `classify_availability`, and
  emits any status transition — so a starter's day-after-start workload swing can
  also surface.

**Contrast with the board**, which deliberately excludes clear starters via
`services/bullpen_eligibility.py` (a "clear starter pattern → ineligible" rule
keyed on ≥3 IP average) and gates on roster status through
`roster_status.allows_default_board`. The board path runs every team pitcher
through `_eligible_records_for_rows`; **the changes path runs them through
nothing.**

**Root cause:** the changes service was built as an independent data path and
**never wired to the bullpen-eligibility / roster filtering that defines "a
bullpen arm."** It treats "active pitcher on the team" as the population, whereas
the product's definition of the bullpen is "active *bullpen-eligible* arms,
roster-permitting." The filter isn't mis-tuned — **it is absent.**

**Severity: HIGH.** It directly contradicts the product's core surface (the
board), it is the more jarring of the two symptoms, and it makes the card look
untrustworthy on first glance — a starter throwing 95 pitches is the *opposite* of
a bullpen-availability signal.

---

## 3. Issue B — The Date Anchor Is Mis-Scoped and Mislabeled

This one is subtler. The date computation is **internally self-consistent** but is
**scoped and labeled in a way that produces the reported mismatch.** There are two
distinct defects bundled here.

### B1 — "Current" is team-local, never reconciled with the dashboard's freshness date
The dashboard's "latest completed MLB data: **Jun 7**" comes from the **durable,
league-wide** `latest_game_date` in the freshness block (`_board_freshness_block`,
global max game date). The card's `current_date` comes from **this team's** most
recent game log (`_team_game_dates`). **These are two different notions of
"current" and are never reconciled.** When the followed team's latest game predates
the league-wide latest date — because of an **off-day** or **per-team ingestion
lag** — the card's entire comparison window sits a slate (or more) behind the
dashboard, with no indication to the user.

Critically, the **global freshness gate passes anyway**: `_freshness_blocker`
checks only the league-wide `is_current` / `freshness_state == 'current'`. A team
whose own logs lag Jun 7 still clears the gate and is compared on stale-for-that-
team data. **The freshness authority is global; the comparison is team-local; the
two are never cross-checked.**

### B2 — The label exposes only the anchor weekday
`label = "since {anchor_date:%A}'s game"` shows **only the anchor's weekday** —
no date, no year, and it never surfaces `current_game_date`. So:
- A user comparing the card to the dashboard's "Jun 7" has no way to see that the
  card thinks "current" is, say, Jun 6.
- A multi-day gap (an off-day between anchor and current) collapses to a bare
  weekday ("Friday") that *looks* like "yesterday" but may be two or three days
  back.

### Is the underlying date actually wrong? It depends on one readable fact.
`Jun 7 2026` is a **Sunday**; `Jun 6` = Saturday, `Jun 5` = Friday. "Since
Friday's game" means **anchor = Friday, Jun 5**. Two scenarios fit:

| Scenario | `current_game_date` in payload | Team schedule implied | Is the anchor "correct"? |
| --- | --- | --- | --- |
| **B-i** | **Jun 7 (Sun)** | Team played Fri + Sun, **off Saturday** | **Yes** — previous game *was* Friday; only the *label* is confusing, and Issue A is the sole real bug |
| **B-ii** | **Jun 6 (Sat)** | Team's latest log is Saturday; **no Jun 7 log for this team** (off Sunday, or Jun 7 not yet ingested for this team) | **No in effect** — the card lags the dashboard by a slate; the team-local-vs-global mismatch (B1) is the live defect |

**The single disambiguating datum is `comparison.current_game_date` in the
`/changes` payload** (the service sets it but the card may not render it). Read it:
- If it is **Jun 7** → the date computation is *correct*; the problem is purely the
  ambiguous weekday-only **label** (B2) plus the absence of the current date in the
  UI, and the headline defect is Issue A.
- If it is **Jun 6** → the **team-local scoping** (B1) is actively producing a
  comparison window behind the dashboard, and the global freshness gate is failing
  to catch it.

Either way, **"Since Friday's Game" is at minimum a labeling defect**, and quite
possibly a scoping defect — which is why the user perceives the anchor as wrong.

**Note (does Issue A move the dates?):** No. Game dates are derived from *any*
team pitcher's logs, and relievers appear on the same game dates as starters, so
removing starters would not change `current_date` / `anchor_date`. The two issues
are independent on the date dimension. (One edge case: a true complete-game day
with no reliever log would still be captured here because starters are included in
date inference — which is actually desirable for dates, even though their
inclusion in the *output* is the bug.)

---

## 4. Secondary Observations (not the reported symptoms, but adjacent)

- **No `game_type` filter** on `_team_game_dates` or the pitcher/appearance
  queries. If the DB ever holds spring-training, exhibition, or postseason logs,
  they could pollute the "team game dates" and the appearance list. Low risk in
  mid-June regular season, but it is an unguarded assumption.
- **`active == True` is the only roster gate.** Beyond starters, this also admits
  IL / optioned / non-roster pitchers that the board would suppress via
  `roster_status`, since `active` is BaseballOS's coarse activity flag, not the
  roster-status authority. The same missing-filter root cause as Issue A.
- **The team-summary** (`_team_summary`) is built from the same unfiltered status
  maps, so its "Available arms: X → Y" and condition deltas are also computed over
  starters-included counts — i.e. the team-level numbers inherit the eligibility
  bug, not just the per-pitcher list.

---

## 5. Root-Cause Assessment

| Candidate | Confidence | Supporting evidence | Contradictory evidence |
| --- | --- | --- | --- |
| **Eligibility filtering is absent** (Issue A) | **HIGH** | `_active_team_pitchers` / `_appearance_changes` filter only `team_id + active`; `team_changes.py` imports no `bullpen_eligibility` / `roster_status`; board path does the opposite | None |
| **Anchor mis-scoped to team-local "current"** (B1) | **MEDIUM-HIGH** | `current_date` from `_team_game_dates` (team max) vs. dashboard's global `latest_game_date`; global-only freshness gate | Resolves to "correct date, bad label" if payload `current_game_date == Jun 7` |
| **Ambiguous weekday-only label** (B2) | **HIGH** | `label = "since {anchor:%A}'s game"`; no date, no current-date context | None — this is a defect regardless of B1's outcome |
| Fatigue/availability engine wrong | VERY LOW | — | Classifier reused unchanged; not implicated |
| Threshold issue | VERY LOW | — | Not touched; not implicated |
| Frontend collapsing/altering data | LOW | Card may simply not render `current_game_date` (a display gap, not a data bug) | Data defects are in the service, not the card |

**Answer to the posed question — "anchor wrong, eligibility bypassed, or both?":
Both, with eligibility being the unconditional, higher-severity bug, and the
anchor being a scoping-plus-labeling defect whose data-level severity hinges on the
team's actual Jun 7 schedule.**

---

## 6. Evidence Needed to Close the Anchor Question

One cheap read fully resolves B1 vs. B2 — **no code change required:**

1. **`GET /api/bullpen/teams/<followed_team_id>/changes` → read
   `comparison.current_game_date`.**
   - `2026-06-07` ⇒ anchor date correct; fix is label/UX (B2) only.
   - `2026-06-06` ⇒ team-local scoping defect (B1) confirmed.
2. **Cross-check:** `SELECT MAX(game_date) FROM game_logs gl JOIN pitchers p ON
   p.id = gl.pitcher_id WHERE p.team_id = <id>` vs. the global
   `latest_game_date` from `/api/bullpen/sync/status`. Divergence confirms the
   team-local-vs-global mismatch directly.
3. **Confirm Issue A independently:** inspect the `pitcher_changes[]` and verify
   the flagged names (Cole, Rodón, Schlittler) carry starter usage — already
   evident from the symptom; the query shape proves the cause.

---

## 7. Where the Defects Live (diagnostic conclusion — not a fix)

For whoever implements the correction, the defects are localized and the engine is
not implicated:

- **Issue A (eligibility):** `team_changes._active_team_pitchers` and
  `team_changes._appearance_changes` — the pitcher population is selected without
  the bullpen-eligibility / roster filtering that the board applies
  (`services/bullpen_eligibility.py`, `services/roster_status.allows_default_board`,
  and the board's `_recent_pitcher_ids_subquery`). The changes path needs to draw
  from the **same eligible-bullpen population the board already computes**, rather
  than re-deriving an unfiltered one.
- **Issue B1 (scope):** `team_changes._team_game_dates` /
  `build_team_changes_payload` define "current" from team-local logs without
  reconciling against the durable global `latest_game_date`, and
  `_freshness_blocker` gates only on global freshness — so a team lagging the
  league date is neither blocked nor flagged.
- **Issue B2 (label):** the `label` string and the (likely unrendered)
  `current_game_date` — the comparison window is not communicated with enough
  precision to match the dashboard's date.

**Do not touch** the Availability classifier, thresholds, or fatigue scoring — none
are implicated. Both defects are in the new `team_changes` data-assembly layer and
its endpoint wiring, exactly where the feature departed from the board's existing,
correct filtering.

---

*Diagnosis produced read-only. No fixes were implemented; no application code,
schema, migration, threshold, classification, or engine behavior was modified.*
