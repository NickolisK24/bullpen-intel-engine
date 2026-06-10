# What Changed Since Yesterday — MVP Plan

> **Type:** Planning and specification only. No code, schema, migration, branch,
> commit, or PR is produced by this document.
> **Feature:** "What Changed Since Yesterday" — the next approved Roadmap 2.0 item.
> **Goal:** The smallest *trustworthy* daily-change surface that makes a user want
> to come back tomorrow. Not a historical-analytics engine.
> **Grounding:** Verified against the shipped codebase. Release 1 (Live Board
> Discrimination investigation, durable freshness reporting, **Follow My Team**)
> is on `main`: `frontend/src/components/dashboard/FollowMyTeam.jsx`,
> `hooks/useFollowedTeamPreference.js`, `utils/followedTeamPreference.js`
> (storage key `baseballos.followedTeam`). Data substrate verified: `FatigueScore`
> is **append-only** (one row per recalc, keyed `calculated_at`), `GameLog` is
> **immutable**, there is **no** availability-snapshot table, and **no** changes
> endpoint exists yet.

---

## 1. Executive Recommendation

**Ship a team-scoped "What Changed" card directly beneath the Follow My Team card
on the Dashboard, powered by one new read-only endpoint, built entirely on
existing data — no new tables, no migrations, no engine changes.**

The MVP surfaces exactly two classes of change, both descriptive and
boundary-based:

1. **Availability status changes** since the previous completed slate
   (e.g. *"Robertson moved from Available to Limited"*), and
2. **New appearances** in that slate (e.g. *"Strahm pitched last night — 24
   pitches"*),

plus a one-line **team condition** delta (*"Available arms: 4 → 2"*). It compares
**today's data to the previous stored game date** (not literal calendar
yesterday, not last sync), reuses the **existing** Availability classifier without
modifying it, and **fails safe**: when data is stale, the comparison anchor is
missing, or coverage is partial, it shows an honest "updates paused / nothing to
compare yet" state rather than a fabricated delta.

**Why this is right:** it works with data already in the database, it directly
reinforces Follow My Team (the retention primitive just shipped), it stays
strictly descriptive, and it cannot mislead because every surfaced item is either
a discrete event (an appearance) or a crossing of a labeled boundary (a status
change) — never numeric drift.

**Confidence the MVP is buildable as specified: HIGH.** The one genuine
engineering nuance — reconstructing the prior day's status from append-only
history — is deterministic over immutable game logs and is addressed in §6 and §8,
with a tiny snapshot table offered as a fast-follow (not an MVP requirement).

---

## 2. MVP Definition

**In scope (the whole MVP):**
- A **team-scoped** change summary for the **followed team** (falls back to the
  team the user is otherwise viewing).
- **Status changes** between the previous completed game date and now, both
  directions (worsening *and* recovery).
- **New appearances** in that comparison window, with pitch count.
- A single **team-condition line** (Available-count delta and/or bullpen-condition
  label change).
- Backend-composed **plain-language summary lines** (trust language controlled
  server-side).
- Full **fail-safe** behavior for stale / missing / partial / unavailable data.

**Explicitly NOT in the MVP** (see §12): raw fatigue-point deltas, league-wide
feeds, IL/roster-transaction changes, predictive language, a dedicated route, and
any new persistence.

**One-sentence MVP:** *"Since [Team]'s last game, here's who pitched and whose
availability moved — or a clear note that there's nothing new or the data is
paused."*

---

## 3. Meaningful-Change Rules

The governing principle: **a change is meaningful only if it crosses a labeled
boundary or is a discrete event. Numeric drift is never surfaced.**

| Signal | MVP? | Rule |
| --- | --- | --- |
| **Availability status change** (Available/Monitor/Limited/Avoid/Unavailable) | ✅ Include | Surface only when the *label* changes between anchor and now. Both worsening and recovery. The headline signal. |
| **New appearance** since the anchor | ✅ Include | Discrete, exact event from `GameLog`. Show pitcher + pitch count. Zero ambiguity. |
| **Team availability-count change** | ✅ Include (one line) | e.g. "Available: 4 → 2." Derived from the same grouped counts the board already computes. |
| **Team bullpen-condition change** | ✅ Include (folded into the team line) | e.g. "manageable → elevated." Reuses `classify_bullpen_health` output; no new logic. |
| **Risk-tier crossing** (LOW/MOD/HIGH/CRITICAL) | ⚠️ Optional, low priority | Only as supporting color *if* a status change isn't already saying the same thing. Easy to defer. |
| **Raw fatigue-score points** (e.g. 43 → 45) | ❌ Ignore | Noise. Never displayed as a number. |
| **Sub-boundary workload-window wiggle** | ❌ Ignore | Not a labeled crossing → not shown. |
| **Recovery micro-movement** that doesn't cross a status line | ❌ Ignore | Must cross Available/Monitor/etc. to count. |
| **Roster / IL / option transactions** | ❌ Defer (Later) | Compelling, but a different data path; out of MVP. |

**Worked examples (the spec's own test cases):**
- Fatigue 43 → 45, status Monitor → Monitor → **show nothing.**
- Status Monitor → Limited → **"Moved to Limited."**
- No prior appearance → appearance of 24 pitches → **"Pitched last night (24 P)."**
- Status Avoid → Monitor (rested two days) → **"Recovered to Monitor."**

---

## 4. Recommended Comparison Window

**Recommendation: compare *now* to the *previous completed MLB game date* for the
team (the prior date that has game logs) — labeled in plain language with the real
date.**

| Candidate | Verdict | Why |
| --- | --- | --- |
| **Previous completed game date** | ✅ **Recommended** | Always well-defined from existing `GameLog` data; baseball-meaningful (movement happens when games are played); robust to off-days and sync timing; honestly labelable ("since Tuesday's games"). |
| "Since yesterday" (literal calendar) | ❌ | Teams have off-days; on an off-day there is no slate to compare, producing confusing empty/again-yesterday results. |
| "Since last sync" | ❌ | Sync cadence ≠ baseball events. Two syncs on one day → empty delta; a missed sync → a two-day jump silently labeled "yesterday." |
| "Since previous stored game date" | ✅ (same as recommended) | This *is* the recommended anchor, stated precisely. |
| "Rolling 24-hour" | ❌ | Same off-day problem; arbitrary cutoffs split a single slate. |

**Honesty requirement:** the UI always names the actual anchor date ("since
**Tue Jun 6**"), so a two-day gap (off-day or missed sync) is never mislabeled as
"yesterday." If the most recent data *is* stale, the feature does not compare at
all (see §8).

---

## 5. Existing Data Audit

| Source | Exists? | Use for this feature |
| --- | --- | --- |
| `game_logs` (immutable; `game_date`, `pitches_thrown`, unique per game) | ✅ | **New appearances** (exact); the workload window needed to reconstruct a prior-day status. |
| `fatigue_scores` (**append-only**; `calculated_at`, `raw_score`, `risk_level`, supporting fields) | ✅ | A historical time series — "the fatigue value as of date D" = the latest row with `calculated_at ≤ D`. |
| Availability **snapshots** (per-day stored status) | ❌ | **Missing.** Prior-day *status* is not persisted → reconstructed via the existing classifier (§6), or added as a fast-follow table (§9 Later). |
| `sync_runs` (durable run metadata: `latest_game_date`, `latest_fatigue_calculated_at`) | ✅ | Freshness gating; the "data through" date for honest labeling. |
| Team board payload (`build_board_payload`, `classify_bullpen_health`) | ✅ | Today's grouped statuses + team condition; reused, not rebuilt. |
| Current APIs (`/teams/<id>/board`, `/fatigue`, `/sync/status`) | ✅ | Today's state + freshness; the new endpoint composes the *delta* on top. |
| Availability classifier (`services/availability.py`, `availability_snapshot.py`) | ✅ | **Reused unchanged** to compute both "now" and "as-of-anchor" statuses identically to the board. |

**Direct answers:**
1. **Can the MVP be built without new tables?** **Yes.** Status deltas are
   reconstructed deterministically from immutable `game_logs` + append-only
   `fatigue_scores` using the existing classifier; appearances come straight from
   `game_logs`.
2. **Without migrations?** **Yes** — none required for the MVP.
3. **What's already stored?** Game logs, append-only fatigue history, durable sync
   metadata, and everything the board already computes for "today."
4. **What's missing?** A persisted per-day **availability status** record. The MVP
   substitutes deterministic reconstruction.
5. **What would require future persistence?** A small `availability_snapshots`
   table to make status-history *exact and cheap* (removes reconstruction) and to
   enable multi-day trends — a recommended **fast-follow**, not an MVP blocker.

---

## 6. Backend / API Recommendation

**One new, read-only, team-scoped endpoint:**

```
GET /api/bullpen/teams/<team_id>/changes
```

| Decision | Recommendation | Rationale |
| --- | --- | --- |
| New endpoint vs. extend `/board`? | **New endpoint** | Keeps the board payload lean; isolates the comparison logic for testability; the change view has its own freshness/anchor semantics. |
| Team-scoped? | **Yes** | Directly serves Follow My Team; matches the board's existing team scoping. |
| League-wide summary? | **No (defer)** | Out of MVP scope; revisit as a "Around the League changed" feed later. |
| Raw deltas or composed summaries? | **Both — structured deltas, each with a backend-composed `summary` string** | Compose the trust-controlled plain-language sentence server-side (consistency + testability), but also return the minimal structured fields so the frontend can group/style without re-deriving meaning. |

**Response shape (illustrative, not prescriptive):**
```jsonc
{
  "team": { "team_id": 1, "team_abbreviation": "PHI", "team_name": "..." },
  "comparison": {
    "anchor_game_date": "2026-06-06",   // previous completed slate
    "current_game_date": "2026-06-07",
    "is_current": true,                  // from durable freshness
    "label": "since Saturday's game"
  },
  "state": "changes",                    // changes | no_changes | stale | no_baseline | unavailable
  "pitcher_changes": [
    { "pitcher_id": 12, "name": "...", "type": "status_change",
      "from": "Available", "to": "Limited",
      "summary": "Moved to Limited after pitching Saturday." },
    { "pitcher_id": 34, "name": "...", "type": "appearance",
      "pitches": 24, "summary": "Pitched Saturday — 24 pitches." }
  ],
  "team_summary": { "available_from": 4, "available_to": 2,
                    "condition_from": "manageable", "condition_to": "elevated",
                    "summary": "Available arms down 4 → 2; bullpen now elevated." },
  "limitations": []
}
```

**How "as-of-anchor" status is computed (no new table):** for each pitcher, run the
**existing** `classify_availability` with `reference_date = anchor_game_date`,
`game_logs` = that pitcher's immutable logs in `[anchor-4, anchor]`, and `score` =
the `fatigue_scores` row with the greatest `calculated_at ≤ anchor`. This yields
exactly the status the board *would have shown* on the anchor date, so the delta is
consistent with the board by construction. **No classifier, threshold, or scoring
change is involved — the engine is reused, not touched.**

**Testability:** the endpoint is a pure function of (immutable logs, append-only
scores, anchor date). Fixtures with two game dates produce deterministic,
assertable output.

---

## 7. Frontend / UX Recommendation

**New components**
- `components/dashboard/WhatChangedCard.jsx` — the card; consumes the new endpoint
  for the followed team; renders the five states (§5/§8).
- `components/dashboard/whatChangedView.js` — light formatting/grouping helpers
  (mirrors the existing `*View.js` pattern, e.g. `bullpenLandscapeView.js`); does
  **not** invent meaning (backend owns the summary text).

**Reused, extended, or referenced**
- `hooks/useFollowedTeamPreference.js` — read `followedTeam`; the card keys off
  `followedTeam.team_id` (and `resolveFollowedTeam` against the team list).
- `hooks/useFetch.js` — fetch `getTeamChanges(teamId)` (new client fn alongside the
  existing API client).
- `components/dashboard/Dashboard.jsx` — mount `WhatChangedCard` **directly below
  `FollowMyTeam`** (the recommended placement, §4 of the prompt's intent: repeat-
  visit value).
- UI primitives `LoadingPane`, `ErrorState`, `EmptyState`, `AvailabilityBadge` —
  reused for states and status chips.

**Placement decision (Q4):** **Dashboard, immediately beneath the Follow My Team
card.** It is the highest repeat-visit surface, it reinforces the followed-team
habit, and it requires no new route. A compact secondary echo atop the team's
Bullpen Board is a *Later* nicety, not MVP. A dedicated route is rejected
(discoverability cost, overbuild).

**State behavior**
- **Loading:** `LoadingPane` ("Checking what changed…").
- **Error:** `ErrorState` with retry; never a partial/ambiguous render.
- **Stale / no-baseline / unavailable:** explicit honest copy (§8), no deltas.
- **Interaction with Follow My Team:** if **no followed team**, the card renders
  the existing "follow your team to see daily changes" prompt (reusing
  `FollowMyTeam`'s follow affordance) instead of fetching.

---

## 8. Trust & Stale-Data Handling

The feature's prime directive: **when in doubt, say less.** A wrong "change" is far
more damaging than a missing one.

| Situation | Behavior |
| --- | --- |
| **Current data is stale** (`/sync/status` `is_current = false`, or latest game outside the freshness window) | **Do not compute deltas.** Show: *"Bullpen updates are paused — latest data is from {date}."* Mirrors the board's freshness posture. |
| **Previous comparison data missing** (only one game date exists; first run) | Show: *"No earlier game to compare yet — check back after the next games."* (`state: no_baseline`.) |
| **Sync metadata unavailable** | Treat as stale; show the neutral "updates unavailable right now" state. Never guess freshness. |
| **Comparison window incomplete / partial coverage** | Surface only what is certain (new appearances are always exact); **suppress** status deltas for pitchers lacking a valid anchor snapshot; add a one-line limitation ("Some arms couldn't be compared yet"). |
| **Partial team data** (some pitchers missing on one side) | Compare only pitchers present on **both** sides; never imply a change for a pitcher that can't be compared. |
| **An off-day / two-day gap** | Allowed, but the anchor date is always named ("since Thu's game") so the gap is never mislabeled as "yesterday." |

**Non-negotiables:** no predictions, no "likely to…", no ranking of "who changed
most," and no numeric fatigue points. Every line is a past-tense, descriptive
statement of something that already happened.

---

## 9. MVP vs Later vs Do-Not-Build

### MVP (build now)
- `GET /teams/<id>/changes` (read-only, team-scoped, existing data, no migration).
- Status changes (both directions) + new appearances + one team-condition line.
- Previous-completed-game-date anchor with honest date labeling.
- Backend-composed plain-language summaries.
- `WhatChangedCard` beneath Follow My Team; all five states; strict fail-safe.

### Later (useful, not now)
- A small **`availability_snapshots`** table written at the end of each sync, to
  make status history exact/cheap and retire reconstruction. *(Recommended fast-
  follow.)*
- **League-wide** "Around the League changed" feed.
- **Risk-tier color**, multi-day trend lines, per-pitcher change history.
- **Roster/IL transition** changes ("landed on the IL").
- **Email/push** "your bullpen changed overnight" digest.
- A compact "what changed" echo atop the Bullpen Board.

### Do Not Build (out of scope or harmful)
- Raw fatigue-**point** deltas as displayed numbers (noise → false signal).
- **Predictive** language of any kind.
- A "**biggest mover**" ranking (crosses into ranking/selection — governance line).
- A new **engine**, new **scoring**, or any **threshold/classification** change.
- Storing the generated **narrative** as authoritative history.
- Governance/certification expansion around this surface.

---

## 10. Implementation Sequence (for the eventual build — not executed here)

1. **Backend, appearances first (zero ambiguity):** `changes` service returns new
   appearances since the previous game date from `game_logs`. Ship behind the new
   endpoint with the freshness gate already wired.
2. **Backend, status reconstruction:** add as-of-anchor classification via the
   existing classifier; diff against today's board statuses; compose summary lines.
3. **Backend, team line + states:** add the Available-count/condition delta and the
   `no_changes / stale / no_baseline / unavailable` states; finalize limitations.
4. **Frontend card:** `WhatChangedCard` + `whatChangedView.js`, wired to
   `useFollowedTeamPreference` and `useFetch`; all five states.
5. **Dashboard mount** beneath Follow My Team; no-followed-team prompt path.
6. **Tests** at each step (see §11).

This order front-loads the most trustworthy, least ambiguous signal (appearances)
and adds reconstruction only once the plumbing and fail-safes are proven.

---

## 11. Validation Strategy

- **Backend unit (deterministic fixtures):** two-game-date fixture → asserts exact
  appearances and exact status transitions; a "43→45, Monitor→Monitor" fixture →
  asserts **no** item emitted; a recovery fixture (Avoid→Monitor) → asserts the
  recovery line.
- **State coverage tests:** stale, no_baseline, unavailable, partial → each returns
  the correct safe state and never a fabricated delta.
- **Consistency test:** as-of-anchor status equals what the board produced for that
  date (reconstruction matches the board by construction).
- **Frontend:** state-by-state rendering (loading/error/stale/no-baseline/changes),
  followed-team vs no-followed-team paths, retry on error.
- **Manual:** follow a team mid-series; confirm next-day card reads truthfully and
  the anchor date label matches the real prior slate (including across an off-day).

---

## 12. Risks & Limitations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Reconstruction drift** (as-of-anchor status differs from what was truly shown) | Med | Reconstruct with the same classifier + immutable logs + as-of fatigue row; add the consistency test; offer the snapshot table as the exact fast-follow. |
| **Sync-gap mislabeling** ("yesterday" was actually two days ago) | Med | Anchor on the previous *game date* and always name it; never hardcode "yesterday." |
| **Stale data producing fake change** | High | Hard freshness gate: no comparison on stale data (§8). |
| **Noise eroding trust** (too many trivial lines) | Med | Boundary-only rule (§3); no numeric deltas; cap items and group sensibly. |
| **Scope creep into trends/league/engine** | High | §9 Do-Not-Build; this is a change *surface*, not an analytics system. |
| **Partial coverage implying false stability** | Low-Med | Compare only pitchers present on both sides; label limitations. |

**Inherent limitations (state honestly in-product where relevant):** the MVP
describes *workload-driven* status movement only — not injuries, roster moves,
manager intent, or warm-up state. It reports what the data shows, since the last
games.

---

## 13. Explicit Non-Goals

- Not a historical-analytics or trend-charting system.
- Not predictive; no forecast of tomorrow's availability.
- Not a ranking of who changed "most."
- No new engine, scoring, thresholds, classification, recommendation, governance,
  or certification work.
- No league-wide feed, no roster/IL transitions, no notifications **in the MVP**.
- No new persistence required to ship the MVP.

---

## Founder Guidance (brutally honest)

**1. Is this feature ready for implementation?** **Yes.** The data exists, the
classifier is reused unchanged, Follow My Team is already shipped to anchor it, and
the trust edges are specified. There is no open design question blocking a build.

**2. Can the MVP be built without new database tables?** **Yes.** New appearances
come straight from immutable `game_logs`; prior-day status is reconstructed
deterministically from append-only `fatigue_scores` + those logs via the existing
classifier. A small `availability_snapshots` table is a worthwhile *fast-follow*
that makes status history exact and cheap — but it is **not required** for the MVP.

**3. What is the safest first implementation?** **New appearances + a hard
freshness gate, shipped first** — it is exact, event-based, and impossible to get
"wrong," and it proves the endpoint, the placement, and the fail-safe states.
Layer reconstructed status changes on top once that spine is in place.

**4. What should NOT be included in the MVP?** Raw fatigue-point deltas, league-wide
summaries, IL/roster-transaction changes, risk-tier coloring, any predictive
language, a dedicated route, notifications, and any new table. Keep it to: *who
pitched, whose status moved, one team line — for your team — or an honest pause.*

**5. Should implementation go to Claude or Codex after this planning task?**
Honestly, either can execute a spec this concrete. **Lean Claude** for the build,
for two specific reasons: (a) the one non-trivial part is the **reconstruction +
trust-edge logic**, where reusing the existing classifier *exactly* and getting the
stale/partial fail-safes right matters more than raw code volume; and (b) it keeps
continuity with the data-flow and freshness context already established in the
Release-1 investigation. Codex is a fine choice for the mechanical frontend card
and test scaffolding if work is split — but the backend `changes` service should be
owned by whoever will guard the "never mislead on stale/partial data" contract.

---

*Planning produced read-only. No application code, schema, migration, engine,
threshold, classification, recommendation, governance, or certification artifact
was created or modified. The deliverable is this specification only.*
