# Team Page Operating-State Readiness Audit

> Audit / planning pass only. No implementation, no UI redesign, no COIN change,
> no new intelligence layer. The question: can BaseballOS safely reuse the
> bullpen operating-state card pattern on a team surface using only trusted data
> that already exists?

Branch: `audit/team-page-operating-state`
Base commit: `eab7463`

## Summary

**Yes — a team operating-state card is safe to ship, frontend-only, with no
backend contract change**, as long as it shows only what the existing per-team
board already supports and *omits* the rows it does not. The per-team board
endpoint (`GET /api/bullpen/teams/<id>/board`, frontend `getTeamBullpenBoard`)
already returns the same `context` shape the dashboard card consumes, plus the
roster-authority, starter-support, and freshness data needed to tell an honest
team story — including the active-workload-vs-roster-pressure separation that
avoids the "nobody is hurt" mistake.

The card component (`BullpenOperatingStateCard`) is already scope-agnostic
(`scope` / `teamLabel` / `context` / `freshness` / `ctaHref`) and already strips
internal vocabulary (COIN/V2/snapshot/etc.) and uses baseball-facing state words
(Stable / Usable / Worth Watching / Thin / Constrained / Stressed / Recovering).

## Row-by-row readiness (against `/teams/<id>/board`)

| Row | In `/board` today? | Field(s) | First-rollout decision |
| --- | --- | --- | --- |
| Current Bullpen State | ✅ | `context.health.state` (manageable/monitoring/elevated/constrained/no_data) | **Show** |
| Primary / Secondary Concern | ✅ | `context.metrics.{available,monitor,limited,avoid,unavailable,total_relievers}` | **Show** (card derives) |
| Why BaseballOS Sees This | ✅ | `context.health.label`, `context.health.reasons` | **Show** |
| Evidence | ✅ | `context.health.reasons` + counts; roster + rotation facts | **Show** |
| Roster Pressure (IL / inactive) | ✅ | `roster_authority.category_counts.injured_list`, `roster_authority.counts.{active_bullpen_arms,inactive_roster_context_count,roster_unknown_count}` | **Show as evidence / secondary concern** (critical — see below) |
| Starter Support Pressure | ✅ | `rotation_support_pressure.{status,starter_avg_innings,short_start_rate,summary,limitations}` | **Show only if `games_analyzed` is sufficient**, else omit |
| Freshness | ✅ | `freshness.{data_through,last_successful_sync,freshness_state,is_current,is_stale,fail_closed,limitations}` | **Show (card-level, from board)** |
| Limitations | ✅ | board `limitations` + `roster_authority.limitations` + `freshness.limitations` + standard caveats | **Show** |
| CTA | ✅ | route to the team bullpen board | **Show** |
| Clean Options | ❌ not in `/board` | only `build_team_bullpen_context` (`clean_workload_options`, `optionality_band`) — not a public route | **Omit** (honest omission) or backend follow-up |
| Coverage Safety | ⚠️ inputs only | `capacity_intelligence` is in `/board`; the coverage-safety *label* is synthesized elsewhere, not in the payload | **Omit** for v1 or backend follow-up |
| Workload Concentration | ❌ not in `/board` | `concentration_band` / `top_three_workload_share_10d` live in `build_team_bullpen_context` only | **Omit** (do not invent) |
| Trend Since Yesterday | ⚠️ separate, descriptive | `/teams/<id>/changes` is descriptive change detection, **not** a trusted day-over-day *state* delta | **Omit** for v1 (no "better/worse than usual") |

## Active workload vs roster pressure (the critical separation)

The board carries **two complementary layers in the same payload**:

- **Active workload** — `context.health.state` and `context.metrics.*` are
  workload-based availability lanes (Available / Monitor / Limited / Avoid /
  Unavailable). This drives the headline state and the concern rows.
- **Roster pressure / depth** — `roster_authority.category_counts.injured_list`,
  `optioned_or_minors`, `forty_man_not_active`, and the counts
  `active_bullpen_arms` / `inactive_roster_context_count` / `roster_unknown_count`.

Because these are distinct, the page **can** honestly say something like:

> "Active bullpen workload looks usable, but roster pressure is elevated — N arms
> are on the injured list or otherwise off the active roster."

It must **never** imply "nobody is hurt." The card's concern logic today reads
only the *workload* lanes, where the "Unavailable" lane is workload-based and is
**not** the same as IL/inactive roster status. So the team view-layer transform
must additionally surface `roster_authority` IL/inactive counts (as an evidence
line and, when roster pressure is elevated while workload is fine, as the
secondary concern). This is a frontend view-model change using data already in
`/board` — no backend change.

## Freshness assessment

Use **card-level freshness fed from `board.freshness`** (the same pattern the
dashboard card uses). The board freshness block already provides
`data_through`, `last_successful_sync`, `freshness_state`, `is_current`,
`is_stale`, `fail_closed`, `data_age_days`, and `limitations`. When
`fail_closed` / `is_stale` is true, degrade to the stale/limited treatment the
existing freshness components already render; surface `freshness.limitations`.
Do not invent per-row freshness — one freshness section per card.

## Evidence candidates (factual, already available)

- "X of Y relievers are classified Available" (and Monitor / Limited / Avoid /
  Unavailable) — from `context.metrics`.
- "N bullpen arms are on the injured list" / "M arms are off the active roster" —
  from `roster_authority.category_counts` / `counts` (only when > 0).
- Starter-support read (e.g. average starter length / short-start rate) — from
  `rotation_support_pressure`, only when `games_analyzed` clears its minimum.

## Limitations candidates (what BaseballOS does not know)

- Availability is workload-based only; it does not include manager intent,
  bullpen phone activity, or private medical availability.
- It does not reflect unreported injuries or final game-day availability
  decisions.
- Carry through `freshness.limitations` (stale/outside-active-window),
  `roster_authority.limitations` (unconfirmed roster status / no current read),
  and `rotation_support_pressure.limitations` (small / incomplete sample).
- The card already blocks internal vocabulary and rewrites "snapshot" → "bullpen
  read"; keep that guard.

## Recommended first frontend integration (Phase 1B)

1. Add a team operating-state card to an **existing** team bullpen surface (the
   team bullpen board view) — no new route required, no layout redesign.
2. Data: reuse `getTeamBullpenBoard(teamId)` (already fetched on that surface) →
   reuse the existing board→context transform → pass to
   `BullpenOperatingStateCard` with `scope="team"`, `teamLabel={team name}`,
   `freshness={board.freshness}`, and a team-scoped `ctaHref`.
3. Extend the team view-model (frontend only) to append roster-pressure evidence
   from `roster_authority` and, when roster pressure is elevated while workload
   is usable, set that as the secondary concern.
4. **Omit** Clean Options, Coverage Safety, Workload Concentration, and Trend
   Since Yesterday for v1 (not supported honestly by `/board`). Gate Starter
   Support on sufficient sample.
5. Replace the league-scope limitation with a team-scope limitation (the card
   only auto-adds the league caveat when `scope === 'league'`).

## Backend contract changes required

**None for Phase 1B.** Everything the first team card shows is already in the
`/teams/<id>/board` payload.

Optional, deferred follow-ups (only if later product wants those rows as
first-class):

- Expose a public team bullpen-context read so Clean Options
  (`clean_workload_options` / `optionality_band`) and Workload Concentration
  (`concentration_band`) can be shown honestly.
- Surface the synthesized Coverage Safety label in the board payload.
- A trusted day-over-day *state* delta if Trend Since Yesterday is ever wanted.

None of these block Phase 1B; until they exist, the corresponding rows are
omitted rather than invented.

## Test guidance (for the implementation phase)

- Card renders State / Why / Evidence / Freshness / Limitations from a team board
  fixture; omitted rows (Clean Options, Coverage Safety, Concentration, Trend)
  are absent, not blank-filled.
- Roster pressure: when `injured_list`/inactive counts > 0, the card shows a
  roster-pressure evidence line and never implies "no injuries"; when workload is
  manageable but roster pressure is elevated, the secondary concern reflects the
  roster, not the workload.
- Stale / `fail_closed` / unavailable freshness states render the degraded
  treatment and surface `freshness.limitations`.
- No internal vocabulary leaks (COIN/V2/V3/V4/deterministic/snapshot/endpoint/
  backend/recommendation engine/baseline distribution/governance layer/sample
  state) — assert against the rendered card text.
- Starter Support is omitted when sample is insufficient.

## Known risks

- **Roster-pressure under-statement**: if the team view-model is *not* extended to
  read `roster_authority`, the card would describe workload only and could read as
  "fine" while IL depth is thin (the Mets mistake). Mitigation is the required
  view-model addition above.
- **Sample-thin starter support**: `rotation_support_pressure` can be low-sample;
  gate on `games_analyzed` and carry its limitations.
- **Freshness honesty**: must respect `fail_closed` / `is_stale` so a stale team
  read is not presented as current.
- **Scope copy**: ensure the league-wide limitation is not shown on a team card.

## Decision

Ready for a **frontend-only Phase 1B**: a team operating-state card on the team
bullpen board surface, built from the existing `/teams/<id>/board` payload, that
shows State → Why → Evidence → Freshness → Limitations plus an honest
active-workload-vs-roster-pressure read, and omits the rows the data does not yet
support. No backend contract work is required to begin.
