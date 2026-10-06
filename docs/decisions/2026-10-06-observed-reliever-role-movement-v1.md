# Observed Reliever Role Movement Authority V1

**Date:** 2026-10-06
**Package:** ML-01 (#906)
**Status:** Candidate authority for the open O-009 role-movement question.
Merging does not by itself authorize a production deploy or reconcile the
roadmap ledger; both remain separate reviewed steps.

## Question answered

Has this reliever's completed deployment, for this team, recently moved toward
later-inning or higher-recorded-leverage work, or away from it, relative to
the week before?

This is a descriptive read of completed games. It does not identify a bullpen
job, predict the next appearance or a save opportunity, infer manager intent,
infer health or readiness, rate performance, rank pitchers, or recommend use.

## Single owner

`backend/services/role_movement.py` owns every role-movement rule: windows,
eligible game types, season phases, minimum evidence, materiality, signal
combination, and public copy. The Team Board deployment-context assembler
(`team_board_public_deployment_context.py`) only counts already-governed
per-appearance evidence into the two windows and hands the counts to that
owner. No other backend layer or the frontend restates a threshold.

## Source authority

| Element | Authority |
| --- | --- |
| Population | Official relief appearances (`games_started == 0`) with resolved `GameLog.appearance_team_id` equal to the represented team. |
| Historical team | The appearance's own team. Current roster membership never reassigns an old appearance; another club's games are never in the windows. |
| Game types | Regular season `R` plus the MLB postseason rounds `F`, `D`, `L`, `W` (the existing `schedule_absence.POSTSEASON_GAME_TYPES` authority). Spring training, exhibition, All-Star, and unknown types never count. |
| Entry inning | The same TB-05 rule as the 14-day context: first contiguous segment in a `fully_processed` play-by-play game only. Unknown entry stays unknown. |
| Leverage | The recorded appearance-level `GameLog.leverage_index` only, banded high at the existing public boundary (`>= 1.5`). Save, hold, inning, score, and role label never fill a missing index. |

## Windows

For represented date `D`:

- recent window: `[D-6, D]`;
- prior window: `[D-13, D-7]`.

Both windows sit exactly inside the 14 baseball dates already loaded for the
Team Board publication, so movement needs no additional appearance query.

Why calendar weeks rather than "last N appearances": appearance-count windows
reach arbitrarily far back for lightly used arms, silently cross team and
season-phase boundaries, and would need a separate unbounded query. Calendar
weeks are reproducible from the represented date alone and match the existing
seven-day workload vocabulary. The cost is availability: a reliever used fewer
than three times in either week gets no read. That is intended.

## Minimum evidence

- Each window needs at least **three** qualifying relief appearances.
- Each signal additionally needs at least three appearances with **known**
  evidence for that signal in each window. Partial evidence never lets one or
  two known appearances stand in for a whole window.

Three is the smallest count at which one appearance cannot by itself produce a
material shift (see below). Two would let a single outing swing the share by a
half.

## Signals and materiality

Two independent shares are compared:

1. `eighth_or_later_entry` — known entries in the 8th inning or later / known
   entries;
2. `high_recorded_leverage` — recorded index `>= 1.5` / known recorded indexes.

A signal moves when its share changes by **at least one half** between the
prior and recent windows, evaluated exactly in integer arithmetic. With three
appearances in each window that means at least two of three appearances
changed character. Shares are not published as decimals; the windows publish
integer counts.

## Combination and withholding

Evaluated in order; the first matching rule decides:

| Condition | Result |
| --- | --- |
| Recent window has fewer than 3 appearances | unavailable, `insufficient_recent_appearances` |
| Prior window has fewer than 3 appearances | unavailable, `insufficient_prior_appearances` |
| Windows are not both entirely regular season or both entirely postseason | unavailable, `season_phase_boundary` |
| Neither signal meets its known-evidence minimum | unavailable, `insufficient_comparable_deployment_evidence` |
| One comparable signal moved later/higher and the other earlier/lower | unavailable, `mixed_directional_evidence` |
| No comparable signal moved | complete, `stable`, no public sentence |
| Otherwise | complete, `later_or_higher_leverage` or `earlier_or_lower_leverage` |

One comparable signal is enough to publish, because the public sentence names
only the evidenced dimension that moved:

- both moved: "Recent deployment shifted toward later-inning, higher-leverage
  work." (or "earlier-inning, lower-leverage");
- entry only: "...toward later-inning work." / "...earlier-inning work.";
- leverage only: "...toward higher-leverage work." / "...lower-leverage work."

A stable or unavailable result publishes no sentence. BaseballOS never says
"promoted", "closer", "trusted", "moved up", or anything about the next game.

## Team changes

Only appearances made for the represented team enter either window. A pitcher
who joined recently has no prior same-team week and is withheld
(`insufficient_prior_appearances`); the pitcher's previous club's deployment is never
read as this club's. The movement population is the same as the 14-day
context's (the publication's current active bullpen plus any arm with
qualifying team rows); the Team Board renders movement only beside an arm in
the frozen deployment.

## Postseason

All four postseason rounds are one phase. A Wild Card week can be compared
with a Division Series week, and an LCS week with a World Series week.
Regular-season deployment is never compared with postseason deployment:
off-days, short series, and starters pitching in relief make the two
distributions different questions. When either window crosses the boundary,
or one window is regular season and the other postseason, movement is
withheld as `season_phase_boundary`. Sparse postseason weeks fall below the
three-appearance minimum and are withheld rather than relaxed.

The existing regular-season-only 14-day deployment profile
(`team_board_public_deployment_context_v1` `profiles`) is unchanged.
Postseason rows reach only the separately versioned movement sub-contract.

## Contract

`role_movement` occupies the slot the deployment context reserved for it
(previously the fixed `{status: unavailable, reason_code: not_published}`
marker). It carries its own version so the parent contract is not redefined:

```
role_movement: {
  contract / method_version: observed_role_movement_v1,
  status: complete | partial | unavailable,
  reason_code, population_basis, game_types: [D, F, L, R, W], data_through,
  profiles: [{
    pitcher_id, contract, method_version, status, reason_code,
    movement: later_or_higher_leverage | earlier_or_lower_leverage | stable | null,
    public_label: string | null,
    season_phase, signals: [{name, status, reason_code, direction}],
    recent_window / prior_window: {
      start_date, through_date, window_days, appearances, season_phase,
      eighth_or_later_appearances, known_entry_appearances,
      high_leverage_appearances, known_leverage_appearances
    }
  }]
}
```

## Publication and reader boundary

Movement is authored once per team while the trusted Team Board publication
is assembled, from the same bounded rows and the same two set-based
play-by-play queries the 14-day context already uses. It is deep-copied into
the frozen Roles & Deployment carrier. Public requests serve the stored copy
and never recompute it.

The frontend validates the frozen carrier's structure and identity (contract,
represented date, game-type scope, count consistency) and renders the
backend sentence and the two window appearance counts. It performs no share,
threshold, minimum, direction, or materiality logic. A malformed movement
carrier withholds movement only; the rest of the deployment section still
renders.

Older immutable publications are not rewritten or replayed. Their
`not_published` marker, or a missing field, reads as "no movement" and the
board stays quiet.

## Explicitly not authorized

- closer/setup/fireman, promotion/demotion, or depth-chart language;
- manager-intent, future-usage, save-opportunity, health, or readiness claims;
- rankings, grades, scores, or recommendations;
- What Changed participation (needs its own change-event materiality contract);
- Team State, Arm Read, or Share Artifact input;
- Pitcher 2.0 surfacing in this package (Pitcher has no frozen per-team
  publication carrier yet; it must consume this same authority, not a copy);
- historical replay or backfill;
- production deploy merely because this document exists.
