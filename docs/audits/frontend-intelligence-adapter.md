# Frontend Intelligence Adapter Readiness Audit

> Audit / planning pass only. No frontend implementation, no backend change, no
> COIN change, no contract change, no UI redesign, no new intelligence. The
> question: does BaseballOS need a dedicated frontend intelligence adapter now,
> and what is the safest shape?

Branch: `audit/frontend-intelligence-adapter`
Base commit: `6cbd8e0` (Phase 1A + 1B merged: PR #313 dashboard card copy, PR #315
team operating-state card)

## Summary

**Yes — a lightweight canonical operating-state read-model module is now
warranted, and no backend contract change is required.** The same operating-card
pattern already feeds six consumers through two overlapping transforms, and the
card itself still interprets backend-shaped context in a fallback path and owns
the internal-language guard, the baseball-facing label mapping, and a second copy
of the concern logic. That is the divergence risk to close before more surfaces
are added.

The fix is a **view-model module with one entry point + a `scope` param + shared
helpers** (not a heavy universal adapter, not fully separate league/team
adapters). It consolidates the existing transforms, owns label mapping / concern
derivation / freshness attachment / the language guard, and turns
`BullpenOperatingStateCard` into a pure presenter of a clean read model.

## Current transformation locations

Transformation is split across **three** layers today:

1. `getBoardContextView(board)` — `tonightsBullpenBoardView.js:606`. Normalizes
   `board.context` → `{ hasContext, state, label, reasons, confidence, isDegraded,
   limitations, metrics{total,pct*}, snapshot[rows], tone }`. The de-facto shared
   normalizer.
2. `getTeamOperatingStateContext(board)` — `tonightsBullpenBoardView.js:815`.
   Composes on top of (1), then adds team enrichment: `reasons` (workload + roster
   + starter evidence), `limitations` (team-scope + freshness + roster + rotation),
   `primaryConcern` (workload via `getTeamWorkloadConcern`), `secondaryConcern`
   (roster pressure via `getTeamRosterPressure`). Helpers: `getTeamWorkloadConcern`
   (687), `getTeamWorkloadEvidence` (722), `getTeamRosterPressure` (738),
   `getStarterSupportEvidence` (777), `freshnessIsLimited` (799).
3. `BullpenOperatingStateCard.getBullpenOperatingStateView` — the card *still*
   interprets context: `getConcernRows`/`getCounts` read `context.snapshot` /
   `context.metrics` / `context.state` to compute concerns when the builder did
   not pre-set them (`getConcernRows` line 169 prefers `context.primaryConcern`
   then falls back to recomputing); `STATE_META` maps raw `state` → baseball label
   + tone; `safeText`/`INTERNAL_COPY_PATTERN` scrub internal vocabulary and rewrite
   "snapshot" → "bullpen read"; freshness is taken as a **separate** prop.

## Consumers (six)

- `getBoardContextView`: `Dashboard.jsx:38` (league card), `Home.jsx:575`,
  `FollowMyTeam.jsx:66`, `BullpenContextSummary.jsx:7`.
- `getTeamOperatingStateContext`: `TonightsBullpenBoard.jsx:112` → card at line 187.
- Both Dashboard and TonightsBullpenBoard render `BullpenOperatingStateCard` and
  pass `freshness` separately from `context`.

## Duplication found

- **Two concern derivations**: `getTeamWorkloadConcern` (view module, team) and
  `getConcernRows`/`getCounts` (card, league/fallback) produce similar-but-separate
  concern labels ("Clean options are tight", "Not every arm is cleanly available",
  …). The card now *prefers* an explicit `context.primaryConcern`, so team and
  league take different paths — the league card recomputes inside the card while
  the team card pre-builds in the module. Same intent, two implementations.
- **Label + tone mapping** exists only in the card (`STATE_META`), so the read
  model still carries the raw `state` key (e.g. `manageable`/`elevated`) rather
  than the baseball-facing label.
- **Snapshot row mapping** (`SNAPSHOT_ROWS`) and **counts** are derived twice
  (once into `context.snapshot` in the module, again in the card's `getCounts`).

## Backend-shaped frontend leaks

- The card reads `context.snapshot[].status/count`, `context.metrics.total`, and
  `context.state` directly — backend-derived shapes interpreted in the
  presentation component.
- The **internal-language guard lives only in the card** (`INTERNAL_COPY_PATTERN`,
  the "snapshot" rewrite). Any future surface that builds a read model and bypasses
  the card would lose the guard. The guard belongs in the adapter so every
  read-model string is already safe.
- Freshness is passed as a separate prop everywhere, so each consumer must know to
  thread `board.freshness` alongside the context — easy to forget on a new surface.

## Recommended adapter shape

A **lightweight view-model module** (e.g. `bullpenOperatingState` read model) with:

- One entry point: `toOperatingStateReadModel(payload, { scope, team, cta })`.
- A `scope` param (`'league' | 'team'`) selecting shared helpers, not separate
  divergent adapters.
- Shared helpers reused across scopes: normalize state → baseball label + tone +
  summary; build workload concerns; build roster pressure; build evidence; build
  limitations; attach + classify freshness; scrub internal vocabulary.
- It **owns**: the `STATE_META` label/tone mapping, the single concern derivation,
  the internal-language guard, freshness attachment, and the evidence/limitations
  separation — all moved out of the card.
- `BullpenOperatingStateCard` becomes a **pure presenter** of the read model (no
  `getConcernRows`/`getCounts`/`safeText` fallback interpretation).

Not recommended: a single universal multi-intelligence adapter (Tonight and
Today's Story have different shapes — see scope note); fully separate league/team
adapters (re-creates today's duplication).

## Recommended UI read model

The proposed shape is sound; this refines it (all strings pre-scrubbed):

```
{
  scope,                 // 'league' | 'team'
  teamId, teamName, teamAbbreviation,   // null for league
  stateLabel,            // baseball-facing: Stable/Usable/Worth Watching/Thin/Constrained/Stressed/Recovering
  stateSummary,          // the "Why BaseballOS Sees This" line
  stateTone,             // { borderColor, backgroundColor, color, dot }
  isUnavailable,         // true => render the no-data state, never a null leak
  primaryConcern,        // { label, body } | null  (workload only)
  secondaryConcern,      // { label, body } | null  (roster pressure when elevated)
  rosterPressure,        // { evidence:[], concern:{label,body}|null } built ONLY from roster_authority
  starterSupportPressure,// { evidence:[], limitations:[] } | null  (gated on sample)
  evidence,              // string[]  (factual; separate from limitations)
  freshness,             // attached object: { dataThrough, lastSync, isStale, isSample, failClosed, limitations[] }
  limitations,           // string[]  (separate from evidence)
  cta,                   // { href, label } | null
  unsupportedFields,     // string[] names omitted (telemetry/debug only — never rendered)
}
```

## Fields safe to standardize now

`scope`, `teamId/teamName/teamAbbreviation`, `stateLabel`, `stateSummary`,
`stateTone`, `isUnavailable`, `primaryConcern` (workload), `secondaryConcern`
(roster when elevated), `rosterPressure` (from `roster_authority`), `evidence`,
`freshness` (attached), `limitations`, `cta`. All come from the existing `/board`
and `/dashboard` payloads.

## Fields that must remain optional / omitted

- `starterSupportPressure` — **optional**, only when `rotation_support_pressure`
  has `games_analyzed >= 3` and a real status (not `limited_read`/`no_data`); the
  team builder already gates this. Omit otherwise.
- Clean Options, Coverage Safety, Workload Concentration, Trend Since Yesterday —
  **omit** (not in trusted `/board`). They go in `unsupportedFields` (names only,
  for telemetry); never render a `null` placeholder, fallback prose, or "unknown".

## Freshness model recommendation

One freshness object **attached by the adapter** into the read model (stop passing
it as a separate prop). Derive `isStale` / `isSample` / `failClosed` / `dataThrough`
/ `lastSync` / `limitations` from the board freshness block. The card renders one
freshness section; no per-row freshness; when `failClosed`/`isStale`, surface
`freshness.limitations` and the degraded treatment.

## Roster pressure model recommendation

A dedicated `rosterPressure` field built **only** from `roster_authority`
(`category_counts.injured_list`, `counts.inactive_roster_context_count`,
`counts.roster_unknown_count`) — never merged with the workload lanes. Workload
concerns come from `context.metrics` (Available/Monitor/Limited/Avoid/Unavailable);
roster pressure is a separate axis. When roster pressure is elevated while workload
is usable, the adapter sets it as the `secondaryConcern`. The read model must never
let workload "looks fine" imply "nobody is hurt."

## Evidence model recommendation

`evidence` is a `string[]` of factual statements only (counts, roster facts,
starter-support summary when shown), deduped, with empty-Monitor noise dropped
(already handled), and internal vocabulary scrubbed **in the adapter**. Kept
strictly separate from `limitations`.

## Limitations model recommendation

`limitations` is a separate `string[]`: team-scope caveat (no manager intent /
phone activity / private medical / unreported injuries / final game-day decisions)
+ `freshness.limitations` + `roster_authority.limitations` +
`rotation_support_pressure.limitations`, deduped and scrubbed. League scope gets
the league caveat instead of the team caveat.

## Implementation plan for Codex

1. Create the read-model module with `toOperatingStateReadModel(payload, {scope,
   team, cta})` consolidating `getBoardContextView` + `getTeamOperatingStateContext`
   + the card's `STATE_META` mapping + `getConcernRows`/`getCounts` +
   `safeText`/guard + freshness attachment. Output the canonical read model above.
2. Reduce `BullpenOperatingStateCard` to a pure presenter of the read model
   (delete its interpretation/fallback concern logic and inline guard once the
   adapter owns them).
3. Migrate all six consumers (Dashboard, TonightsBullpenBoard, Home, FollowMyTeam,
   BullpenContextSummary, and any other operating-card usage) to the adapter,
   scope-tagged; pass freshness through the adapter, not as a separate prop.
4. Keep behavior identical (golden-master the current rendered text per surface
   before/after).
5. No backend change.

## Backend contract changes required

**None.** The adapter is pure frontend reshaping of payloads that already exist
(`/teams/<id>/board`, `/bullpen/dashboard`). Optional, deferred follow-ups (only if
those rows are ever wanted): expose team bullpen-context for Clean Options /
Workload Concentration, surface a Coverage Safety label, add a trusted day-over-day
state delta for Trend. None block this adapter.

## Test guidance

- Adapter unit tests with league + team fixtures: correct baseball-facing
  `stateLabel` per `state`; roster pressure built only from `roster_authority` and
  never merged with workload; unsupported fields **absent** (not null / not
  "unknown"); freshness attached with stale/sample/failClosed derived; evidence vs
  limitations separation; internal vocabulary scrubbed **in the read model output**
  (not only at render); `null`/`undefined`/empty payloads → safe no-data read model
  (`isUnavailable: true`, no undefined leaks).
- Card tests collapse to presentation of a fixed read model.
- Keep the existing dashboard/team operating-card fixtures; assert no regression in
  rendered text.

## Known risks

- **Migration churn**: six consumers; migrate incrementally behind the adapter with
  before/after text snapshots.
- **Residual divergence**: if the card keeps any fallback interpretation, league and
  team drift again — the logic must move fully into the adapter.
- **Guard bypass**: the internal-language guard lives only in the card today; until
  it moves to the adapter, a new read-model consumer could leak internal terms.
- **Over-generalization**: do NOT fold Tonight cards (`/intelligence/tonight`:
  headline/summary/evidence/schedule_context shape) or Today's Story (`lead_story`
  shape) into this read model. They are separate shapes that already follow the
  same State → Why → Evidence → Freshness → Limitations principle; a universal
  adapter now would couple unrelated contracts.

## Decision

Build a **lightweight canonical operating-state read-model module now** (one entry
point + `scope` param + shared helpers) that consolidates the existing transforms,
owns label mapping / concern derivation / freshness attachment / the
internal-language guard, and turns the card into a pure presenter. Standardize the
supported fields; keep unsupported intelligence omitted (named in
`unsupportedFields`, never null/placeholder/prose). No backend contract change.
Scope the adapter to bullpen operating cards only — leave Tonight and Today's Story
on their own shapes.

ready for Codex implementation: YES (frontend-only, no backend contract change).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
