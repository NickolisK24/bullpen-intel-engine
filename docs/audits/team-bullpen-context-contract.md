# Team Bullpen Context Contract Audit — Clean Options, Coverage Safety, Workload Concentration

> Audit / planning pass only. No frontend implementation, no backend logic change,
> no COIN change, no endpoint-contract change, no data-generation change, no UI
> redesign. The question: can Clean Options, Coverage Safety, and Workload
> Concentration be safely exposed to the team board/team page UI from existing
> backend services, or is a minimal backend contract addition needed?

Branch: `audit/team-bullpen-context-contract`
Base commit: `e5d9c1a` (Phase 0B/1A/1B/2 merged; latest main)

## Summary (correction to the prior team-page audit)

**All three reads are already present in `GET /api/bullpen/teams/<id>/board`** —
inside `board.team_shape` — as baseball-facing, public-safe reads with a built-in
honest "Limited Read" fallback. The earlier team-page audit looked only at
`context` and the raw services and concluded these were not in `/board`; it missed
`team_shape`, which is produced by `build_team_bullpen_shape` and returned in the
board payload.

**Therefore no backend contract change is required to expose them.** The remaining
work is frontend: wire `board.team_shape.byKey.{cleanOptions, coverageSafety,
workloadConcentration}` into the operating-state read model, rendering each read's
`label` / `explanation` / `reasons`, omitting on `Limited Read`, and never
rendering the internal `supportingCounts` / `source`. One **optional, additive**
backend hardening is recommended: strip internal keys from the served `team_shape`
so no internal label (`source:'backend'`, `coverageSafetyVersion:'2.0'`,
`capacityState`, `thresholds`) ships in the payload.

Trend Since Yesterday remains omitted — there is no trusted day-over-day state
delta.

## Current backend sources

| Read | Computed by | Also surfaced as a public read by |
| --- | --- | --- |
| Clean Options | `services/bullpen_optionality_context.build_bullpen_optionality_context` (raw, diagnostic) | `services/team_bullpen_shape._clean_options` → `team_shape.cleanOptions` |
| Coverage Safety | `services/bullpen_coverage_safety.build_bullpen_coverage_safety_read` (+ `_legacy_coverage_safety` fallback) | `team_bullpen_shape` → `team_shape.coverageSafety` |
| Workload Concentration | `services/workload_concentration.summarize_recent_relief_workload` (recent window); a separate 10-day top-three share lives in `bullpen_concentration_context` (diagnostic only) | `team_bullpen_shape._workload_concentration` → `team_shape.workloadConcentration` |

`team_shape` is built in `bullpen_board.build_board_payload` via
`build_team_bullpen_shape(groups, context, workload_concentration,
capacity_intelligence, bullpen_environment)` and returned in the board payload;
`_build_team_board` (api/bullpen.py) already computes and passes
`workload_concentration`, `capacity_intelligence`, and `bullpen_environment`.

## Fields currently exposed in `/teams/<id>/board`

`board.team_shape` returns `{ reads[], byKey, trustAvailability, cleanOptions,
bullpenPressure, workloadConcentration, coverageSafety, depthSafety,
supportingCounts, source:'backend' }`. Each read is
`{ key, label, explanation, supportingCounts, reasons[] }`:

- `cleanOptions.label`: tiered (e.g. Deep / Healthy / Thin Clean Options) or
  `Limited Read`; `explanation` + `reasons` describe how many clean options exist;
  `supportingCounts` (cleanOptionCount, activeBullpenArms, …).
- `coverageSafety.label`: Strong / Stable / Thin / Limited Coverage Safety or
  `Limited Read`; `explanation` + `reasons`; `supportingCounts` **carries internal
  fields** (`coverageSafetyVersion:'2.0'`, `capacityState`, `resourceHealthState`,
  `thresholds`).
- `workloadConcentration.label`: Heavily Concentrated / Concentrated / Some / No
  Workload Concentration or `Limited Read`; `explanation` cites top-arm share of
  recent relief pitches; `supportingCounts` (topSharePct, topArmCount, …).

The board also exposes `context` (health/metrics), `groups`, `freshness`,
`roster_authority`, `rotation_support_pressure`, `capacity_intelligence`,
`bullpen_stability`, `bullpen_environment`. A frontend reader already exists:
`frontend/src/utils/teamBullpenScoring.js` reads `team_shape`/`teamShape` and the
three reads with a `limitedRead` fallback — they are simply not yet wired into the
operating-state read model / `BullpenOperatingStateCard`.

## Clean options assessment

Exposed today at `board.team_shape.cleanOptions` (and `byKey.cleanOptions`). The
`label`/`explanation`/`reasons` are baseball-facing and public-safe ("Clean
Options" is allowed vocabulary). The read has a built-in `Limited Read` fallback
when availability labels are sparse (`dataQuality.readSparse`), so it never
overclaims on thin data. Safe to consume the read; do **not** render
`supportingCounts`.

## Coverage safety assessment

Exposed today at `board.team_shape.coverageSafety`. Uses the V2 capacity-based read
when capacity inputs are present, else a legacy count-based fallback. `label`
(Strong/Stable/Thin/Limited Coverage Safety / Limited Read), `explanation`, and
`reasons` are public-safe and baseball-facing. **Caveat:** its `supportingCounts`
leaks internal labels (`coverageSafetyVersion:'2.0'`, `capacityState`,
`resourceHealthState`, `thresholds`) — these must never be rendered. Consume only
`label`/`explanation`/`reasons`.

## Workload concentration assessment

Exposed today at `board.team_shape.workloadConcentration`, built from the recent
relief-workload window. `label` (Heavily Concentrated / Concentrated / Some / No
Workload Concentration / Limited Read), `explanation` (top-arm share of recent
relief pitches), and `reasons` are public-safe. Built-in `Limited Read` when no
recent workload is available. The 10-day top-three-share variant in
`bullpen_concentration_context` is richer but diagnostic-only (carries `source`,
`baseline_read`, league deltas, exclusion counts) and should NOT be used for UI.

## Trend since yesterday assessment

Still **omit**. `/teams/<id>/changes` is descriptive change detection (status/
appearance changes), not a trusted day-over-day *state* delta, and `team_shape`
has no trend read. Do not present better/worse-than-usual or baseline language.

## Recommended backend contract changes

**None required.** The three reads already ship in `/board` via `team_shape` with
public-safe `label`/`explanation`/`reasons` and an honest `Limited Read` fallback.

**Optional, additive hardening (recommended, non-breaking):** scrub internal keys
from the served `team_shape` so the public payload carries no internal labels —
drop `team_shape.source`, and drop `coverageSafetyVersion` / `capacityState` /
`resourceHealthState` / `thresholds` from `coverageSafety.supportingCounts` (or
omit `supportingCounts` from the served reads entirely). This is defense-in-depth;
it is not required if the frontend whitelists only `label`/`explanation`/`reasons`.

## Recommended frontend read-model fields

Add to `operatingStateReadModel` (optional; omitted when absent or `Limited Read`):

```
cleanOptions:          { label, summary, reasons[] } | null
coverageSafety:        { label, summary, reasons[] } | null
workloadConcentration: { label, summary, reasons[] } | null
```

Source each from `board.team_shape.byKey[key]` (reuse the existing
`teamBullpenScoring.js` reader). Map `explanation` → `summary`, `reasons` →
`reasons`. Render only when `label !== 'Limited Read'`; never include
`supportingCounts` or `team_shape.source` in the read model. Keep them strictly
optional so a missing `team_shape` (e.g. older payload) simply omits the rows.

## Recommended UI copy

Follow State → Why → Evidence → Freshness → Limitations:

- Clean Options — title "Clean options: {label}", body = explanation, evidence =
  reasons.
- Coverage Safety — title "Coverage safety: {label}", body = explanation, evidence
  = reasons. Render the label text only (e.g. "Stable Coverage Safety"); never the
  version/threshold internals.
- Workload Concentration — title "Workload concentration: {label}", body =
  explanation, evidence = reasons.

When a read is `Limited Read`, omit the row (preferred) rather than render a placeholder.

## Limitations / caveats

Keep the existing team-scope limitation: BaseballOS does not know manager intent,
bullpen phone activity, private medical availability, unreported injuries, or final
game-day availability decisions. The reads are workload/role-based; the `Limited
Read` fallback already prevents overclaiming on sparse data. Concentration is a
description of recent pitches, not a forecast. Do not imply future usage or that a
manager will use a specific arm.

## How we avoid overclaiming

- Clean options = availability/role-based count, not a usage prediction.
- Coverage safety = current capacity read, not a game-outcome or win-probability claim.
- Workload concentration = past-window description, not a projection.
- All three degrade to `Limited Read` on thin data (already enforced server-side).
- Render labels/explanations/reasons only; never internal counts/version/thresholds.

## Test guidance

- Read-model unit tests (team board fixture): cleanOptions/coverageSafety/
  workloadConcentration mapped from `team_shape.byKey`; omitted when the read is
  `Limited Read` or `team_shape` is absent (no null/"unknown" placeholder).
- Internal-label safety: assert the read model and rendered text never include
  `source`/`backend`/`coverageSafetyVersion`/`2.0`/`V2`/`capacityState`/`thresholds`.
- Baseball-facing labels only (Clean Options / Coverage Safety / Workload
  Concentration / Strong / Stable / Thin / Limited Read).
- Evidence vs limitations separation preserved; freshness unchanged.
- No undefined/null leaks when `supportingCounts`/`explanation` fields are missing.

## Known risks

- **Internal-label leak**: `team_shape` ships `source:'backend'` and coverage
  `coverageSafetyVersion:'2.0'`; the frontend must whitelist read fields (or the
  optional backend scrub must land) so these never render.
- **Over-labeling**: showing all reads at once could crowd the card; recommend
  surfacing Clean Options + Coverage Safety + Workload Concentration as optional
  rows/evidence, omitting Limited Read.
- **Two concentration definitions**: use the `team_shape` recent-window read (in
  `/board`); do not pull the diagnostic 10-day top-three share.
- **Stale data**: respect existing freshness; a stale board should degrade as today.

## Validation / status checks

- Branch starts from latest main (`e5d9c1a`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed. ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- `git diff` / `git diff --cached --check` clean; only the audit doc is staged. ✔

## Decision

Clean Options, Coverage Safety, and Workload Concentration **can be safely exposed
now from the existing `/teams/<id>/board` payload (`board.team_shape`)** — they are
already public-safe reads with baseball-facing labels and an honest Limited Read
fallback. No backend contract change is required; the work is frontend-only
(wire the three reads into the operating-state read model, render label/
explanation/reasons, omit on Limited Read, never render internal counts). One
optional additive backend hardening (scrub internal keys from served `team_shape`)
is recommended as defense-in-depth. Trend Since Yesterday stays omitted.

ready for Codex implementation: YES (frontend-only; optional additive backend scrub).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
