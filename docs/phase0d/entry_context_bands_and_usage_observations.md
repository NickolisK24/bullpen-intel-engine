# Phase 0D-07 - Entry-Context Bands And Usage Observations

## Scope

This document defines the internal-only entry-context band and
usage-observation evidence family for Phase 0D-07.

The family writes through `evidence_objects` and `evidence_citations`. It adds
no tables, no public API fields, no frontend behavior, and no public copy.

Roadmap reference: this family implements what the Phase 0D master plan called
the internal pressure-context proxy; implementation vocabulary is
entry-context band.

## Inputs

This family consumes stored rows only:

- `game_logs`
- `slate_coverage`
- stored 0D-02 `outing_multi_inning` evidence objects
- stored 0D-03 `appearance_entry_context` evidence objects
- stored 0D-03 `appearance_order_in_game` evidence objects

It never imports play-by-play models, never reads raw play-by-play JSON, never
reconstructs runner state, and never recomputes facts owned by 0D-02 or 0D-03.

## Qualifying Relief Appearance

A qualifying relief appearance is a `game_logs` row with:

- `games_started = 0`
- finality-certified game context

Rows with `games_started = NULL` are excluded and cited with
`appearance_role_unknown`. Rows with `games_started = 1` are excluded except for
finish-context contradiction detection.

This is a per-appearance stored fact, not a roster partition. No
reliever/starter partition is created.

## Registered Rules

All rules are version `v1` and default to `internal_only`.

1. `appearance_entry_band v1`
2. `appearance_finish_context v1`
3. `pitcher_save_hold_window v1`
4. `pitcher_entry_band_distribution v1`
5. `pitcher_finish_usage_observation v1`
6. `pitcher_multi_inning_usage_observation v1`
7. `pitcher_first_reliever_usage_observation v1`

Rules 1 and 4 are permanently internal and posture-locked:

- `appearance_entry_band`
- `pitcher_entry_band_distribution`

## RULE 1 - appearance_entry_band v1

Evidence type: `appearance_entry_band`

Subject: `pitcher_appearance`

Subject id:

`{pitcher_id}:{mlb_game_pk}`

Product date: game date.

Definition:

For a qualifying relief appearance, the cell of a printed 12-cell table
crossing the entry-inning phase with the entry margin band from the pitcher's
team perspective.

Thresholds:

- `one_run_max: 1`
- `two_three_max: 3`
- `early_max: 3`
- `middle_max: 6`
- `late_max: 9`

Entry-inning phase:

- early: innings 1-3
- middle: innings 4-6
- late: innings 7-9
- extras: innings 10+

Margin band:

- `one_run`: margin magnitude <= 1, including tied
- `two_three`: margin magnitude 2-3
- `four_plus`: margin magnitude >= 4

The claim restates inning, margin, and cell. Runners at entry remain unknown.
The limitation text rides every object:

`The band classifies inning and margin only; runners at entry remain unknown.`

0D-07 consumes the stored 0D-03 `appearance_entry_context` object. It cites the
0D-03 object with `citation_role = derived_from_evidence` and passes through its
underlying citations where present. If the 0D-03 object is missing or not
complete, Rule 1 emits UNKNOWN with one of:

- `entry_context_unavailable`
- `entry_context_incoherent`

## 12-Cell Table

| Entry phase | one_run | two_three | four_plus |
| --- | --- | --- | --- |
| early | `early_one_run` | `early_two_three` | `early_four_plus` |
| middle | `middle_one_run` | `middle_two_three` | `middle_four_plus` |
| late | `late_one_run` | `late_two_three` | `late_four_plus` |
| extras | `extras_one_run` | `extras_two_three` | `extras_four_plus` |

Cell names are mechanical compounds. They carry no quality, intent, or
availability meaning.

## RULE 2 - appearance_finish_context v1

Evidence type: `appearance_finish_context`

Subject: `pitcher_appearance`

Definition:

For a qualifying relief appearance, the stored boxscore finishing facts as
sourced:

- save opportunity
- save
- hold
- blown save
- win
- loss
- games finished

This is a flag restatement only. It never creates a conversion value, quality
label, or usage label.

If `games_finished` is NULL, the object is UNKNOWN with
`games_finished_unknown`.

Rows with `batters_faced` NULL carry:

- limitation: legacy boolean finish flags can undercount unset false values
- reason code: `legacy_row_default_false_caveat`

Contradiction guard:

- save and blown save both set -> CONFLICT and dead-letter
- hold set with `games_started = 1` -> CONFLICT and dead-letter

## RULE 3 - pitcher_save_hold_window v1

Evidence type: `pitcher_save_hold_window`

Subject: `pitcher`

Windows:

- trailing 7 days
- trailing 14 days

Definition:

Trailing 7- and 14-day counts of:

- save opportunities
- saves
- holds
- blown saves
- games finished

Counts come from qualifying relief appearances and stored flags only. Counts
are never conversion values.

Incomplete slate coverage makes counts lower bounds and cites incomplete days.

## RULE 4 - pitcher_entry_band_distribution v1

Evidence type: `pitcher_entry_band_distribution`

Subject: `pitcher`

Window:

- trailing 14 days

Floor:

- minimum 5 qualifying relief appearances

Definition:

The trailing 14-day distribution of Rule 1 cells across qualifying relief
appearances. The object records every cell count, including zeros, plus the
count of band-UNKNOWN appearances.

Below the floor, the object is WITHHELD with `insufficient_sample`.

This rule is permanently internal and posture-locked.

## RULE 5 - pitcher_finish_usage_observation v1

Evidence type: `pitcher_finish_usage_observation`

Subject: `pitcher`

Window:

- trailing 14 days

Floor:

- minimum 5 qualifying relief appearances

Definition:

Of the pitcher's qualifying relief appearances in the trailing 14 days:

- how many he finished
- of those, how many began in late or extras `one_run` cells

Unknown `games_finished` values and unknown band values are counted and cited
separately. The rendered count becomes a lower bound when unknown rows could
satisfy the event.

## RULE 6 - pitcher_multi_inning_usage_observation v1

Evidence type: `pitcher_multi_inning_usage_observation`

Subject: `pitcher`

Window:

- trailing 14 days

Floor:

- minimum 5 qualifying relief appearances

Definition:

Of the pitcher's qualifying relief appearances in the trailing 14 days, at
least how many were multi-inning according to stored 0D-02
`outing_multi_inning` evidence objects.

Complete 0D-02 objects count. Unknown 0D-02 objects are counted and cited as
unassessable. Absence of a 0D-02 flag object means not counted, per the 0D-02
emission policy.

0D-07 never recomputes outs locally.

## RULE 7 - pitcher_first_reliever_usage_observation v1

Evidence type: `pitcher_first_reliever_usage_observation`

Subject: `pitcher`

Window:

- trailing 14 days

Floor:

- minimum 5 qualifying relief appearances

Definition:

Of the pitcher's qualifying relief appearances in the trailing 14 days, how many
were his team's first relief appearance of that game. The source condition is
stored 0D-03 `appearance_order_in_game` value `2`.

Unknown order objects are counted and cited separately with
`order_unknown_in_window`.

The claim is a descriptive sequence fact only. It does not state design,
preference, label, or intent.

## Window Validity

Window validity follows the league-scoped slate coverage precedent from 0D-02.

Any window day that is not complete degrades counts to lower bounds with the day
cited using `citation_role = window_validity`.

## Floors

Pattern rules 4-7 require at least 5 qualifying relief appearances in the
window.

- `n = 4` -> WITHHELD with `insufficient_sample`
- `n = 5` -> emits
- `k = 0` -> emits when the floor is met

## Reason Codes

- `entry_context_unavailable`
- `entry_context_incoherent`
- `insufficient_sample`
- `incomplete_slate_day_in_window`
- `appearance_role_unknown`
- `games_finished_unknown`
- `band_unknown_in_window`
- `order_unknown_in_window`
- `multi_inning_unknown_in_window`
- `legacy_row_default_false_caveat`
- `source_family_not_ready`

## Recompute

Corrections to cited `game_logs` rows mark dependent 0D-07 evidence for bounded
recompute.

Supersession of cited 0D-02 or 0D-03 evidence objects also marks dependent
0D-07 evidence for bounded recompute.

Rebuilds refresh the same evidence key and preserve the superseded prior claim
in computation trace.

## Forbidden Vocabulary

The service lint rejects unsupported terms in claim templates and rendered
claims, including:

- role-title assertions such as closer, setup man, fireman, stopper, long man,
  bullpen ace, and ninth-inning guy
- trust or preference assertions such as trusted, go-to, leans on, prefers, and
  manager's choice
- quality labels such as dominant, reliable, and shaky
- predictive terms such as will, should, expect, and likely
- availability terms such as available and ready
- percentage, rate, score, grade, or rank framing
- any `X-like role` pattern
- the inherited roadmap terms named in the roadmap note above

Negative tests may use forbidden words as input strings solely to prove the
lint rejects them.

## Explicit Non-Claims

0D-07 does not implement or claim:

- handedness exposure
- opener or bulk inference
- reliever/starter partition
- roster role claims
- team bullpen structure composition
- composite indices
- scores, grades, ranks, or rates
- public product surfaces
- frontend UI
- public API changes
- public label or copy changes
- prediction conclusions
- availability conclusions
- fatigue conclusions
- readiness conclusions
- health language
- manager-intent language
- betting or odds language
- pitch-level or Statcast interpretation
- play-by-play runner/base-state reconstruction
- local recomputation of facts owned by 0D-02 or 0D-03
