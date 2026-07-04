# Phase 0D-03 - Appearance Entry And Exit Context

## Scope

This document defines the internal-only appearance entry/exit context evidence
family for Phase 0D-03.

The family derives evidence only from stored final play-by-play foundation rows
and stored `game_logs` rows. It does not read raw play-by-play JSON, does not
reconstruct base state, and does not publish any public API, payload, UI, or
copy behavior.

## Registered Rules

All rules are version `v1`, use `required_input_families` of
`final_play_by_play` and `game_logs`, and default to `internal_only`.

### RULE 1 - appearance_entry_context v1

Definition:
For a relief appearance in a fully processed final game: the inning and
half-inning of the pitcher's first stored play-by-play event, the outs at entry
from the preceding same-half event's post-play outs or zero at a half-inning
start, and the score margin at entry from the pitcher's team's perspective.

Score margin:

- fielding team score minus batting team score
- positive = leading
- negative = trailing
- zero = tied
- at the game's first event, use 0-0

Runners on base at entry are not stored and are always UNKNOWN.

Mid-inning entry is derived as:

- outs at entry > 0 OR
- the entry event is not the first event of its half-inning

### RULE 2 - appearance_exit_context v1

Definition:
For the same appearance: the inning and half-inning of the pitcher's last stored
event, the post-play outs at that final event, and the exit boundary type.

Boundary types:

- relieved: a later event for the same fielding team shows a different pitcher
- finished_game: the pitcher's last event is his team's final pitching event of
  the game

Removed mid-inning:

- true when the team's next pitcher first appears in the same half-inning

### RULE 3 - appearance_order_in_game v1

Definition:
The pitcher's position in his team's pitching sequence for the game, based on
the rank of his entry event index among distinct pitchers for that fielding
team.

Starter:

- order 1

First relief appearance:

- order 2

Each team sequence must contain exactly one order-1 pitcher and strictly
increasing, contiguous entry indexes.

Any inconsistency is CONFLICT, not guessed.

### RULE 4 - appearance_innings_spanned v1

Definition:
The count of distinct innings the appearance touched:

exit inning - entry inning + 1

This is a span of innings touched, not outs recorded.

Outs recorded remain the stored game-log fact, cited only for reconciliation.

### RULE 5 - appearance_game_phase v1

Definition:
A descriptive tag for the entry inning:

- early: innings 1-3
- middle: innings 4-6
- late: innings 7-9
- extras: inning 10 or later

The tag carries no pressure, importance, leverage, or role meaning.

Thresholds:

- early_max: 3
- middle_max: 6
- late_max: 9

### RULE 6 - appearance_pbp_reconciliation v1

Definition:
Agreement state between the appearance's play-by-play span and stored game-log
row.

Matched when:

- pitcher appears in both sources
- span is contiguous
- team ordering is consistent
- stored outs recorded are plausible for the span
- entry/exit outs are positionally consistent when known

Mismatch kinds:

- pbp_appearance_missing
- game_log_row_missing
- non_contiguous_pitcher_span
- outs_implausible
- order_inconsistent

Important:

- pbp_appearance_missing is UNKNOWN, not CONFLICT, because a legitimate
  zero-batter/injury substitution can exist.
- game_log_row_missing is CONFLICT and dead-lettered.
- non_contiguous_pitcher_span is CONFLICT and dead-lettered.
- outs_implausible is CONFLICT and dead-lettered.
- order_inconsistent is CONFLICT and dead-lettered.
- Reconciliation never silently prefers PBP or game_logs.

### RULE 7 - appearance_entry_base_state v1

Definition:
Runners on base when the pitcher entered.

Stored final play-by-play events do not carry base-runner state, so this
evidence is UNKNOWN for every appearance by design.

This rule exists so the gap itself is citable.

No BaseballOS read may treat an entry as traffic-free or traffic-laden from
play-by-play.

Inherited-runner facts, where known, live in the boxscore-backed game-log fields
and are interpreted by 0D-04, not this rule.

Resolution of this gap - future base-state foundation addendum or permanent
acceptance of boxscore-only inherited attribution - is a Phase 0D-09 decision.

## Derivation Semantics

A game is eligible only when its `play_by_play_processed_games.processing_status`
is `fully_processed`. Other marker states emit no appearance context evidence.

An appearance span is the contiguous run of stored
`game_play_by_play_events` rows for the same `pitcher_mlb_id` and
`fielding_team_id`, ordered by `event_index`.

- Entry event: the lowest `event_index` in the span.
- Exit event: the highest `event_index` in the span.
- Non-contiguous reuse of the same pitcher for one fielding team is a data
  anomaly and forces `CONFLICT`.
- Doubleheaders remain separate because `subject_id` includes `mlb_game_pk`.
- Suspended/resumed games emit once on the 0C-attributed product day and carry
  the resumed-game limitation.

Stored `outs_at_event` and stored scores are post-play state.

Entry state follows these rules:

- entry outs come from the immediately preceding same-half event
- entry outs are `0` when entry opens a half-inning
- if the preceding same-half event is required but has null outs, the entry
  object is `UNKNOWN` with `preceding_event_outs_unknown`
- entry score comes from the immediately preceding stored event
- entry score is `0-0` at the game's first event
- score margin is fielding team score minus batting team score
- entry event pitching-change flags are corroboration, not authority
- missing entry flag on an unexplained mid-inning relief appearance adds
  `entry_flag_missing` while still deriving from sequence order

Exit state follows these rules:

- exit outs come from the span's final event `outs_at_event`
- null exit outs make the exit object `UNKNOWN` with `exit_outs_unknown`
- `relieved` means a later same-fielding-team event has a different pitcher
- `finished_game` means there is no later pitching event for that fielding team
- removed mid-inning is true when the next pitcher first appears in the same
  half-inning

Every entry and exit object carries this limitation:

`Entry and exit boundaries are play-granular; a mid-at-bat change resolves to
the pitcher credited with the completed play.`

Every entry object also carries this limitation:

`Runners on base at entry are not available from stored play-by-play; entry
traffic is unknown here. Inherited-runner facts, where recorded, come from the
boxscore-backed game log.`

## Subject Identity Guard

`subject_type` is `pitcher_appearance`.

`subject_id` is:

`{pitcher_id}:{mlb_game_pk}`

For matched appearances, `pitcher_id` comes from the internal `Pitcher` row tied
to the `game_logs` row.

For a `game_log_row_missing` reconciliation case, PBP may contain a pitcher with
no corresponding `game_logs` row. Phase 0D-03 does not create a new `Pitcher`
from PBP.

- If an internal `Pitcher` row already exists for `pitcher_mlb_id`, the
  reconciliation object uses that internal id.
- If no internal `Pitcher` row exists, the builder writes an
  `appearance_context_reconciliation` dead-letter and skips the evidence object.
- Subject identity is never fabricated.

## Reconciliation Truth Table

| Condition | Completeness | Reason code | Dead-letter | Evidence emitted |
| --- | --- | --- | --- | --- |
| PBP span and game log agree | complete | none | no | all 7 appearance objects |
| Game-log relief row has no PBP span | unknown | `pbp_appearance_missing` | no | reconciliation only |
| PBP span has no game-log row and pitcher identity exists | conflict | `game_log_row_missing` | yes | reconciliation only |
| PBP span has no game-log row and pitcher identity is unknown | none | `game_log_row_missing` | yes | no evidence object |
| Same pitcher has non-contiguous team span | conflict | `non_contiguous_pitcher_span` | yes | reconciliation only |
| Team order is inconsistent | conflict | `order_inconsistent` | yes | reconciliation only |
| Stored outs cannot fit the span | conflict | `outs_implausible` | yes | reconciliation only |
| `games_started` is null | unknown | `appearance_role_unknown` | no | reconciliation only |

## Reason Codes

- `pbp_marker_not_fully_processed`
- `preceding_event_outs_unknown`
- `exit_outs_unknown`
- `appearance_role_unknown`
- `entry_flag_missing`
- `pbp_appearance_missing`
- `game_log_row_missing`
- `non_contiguous_pitcher_span`
- `order_inconsistent`
- `outs_implausible`
- `base_state_unavailable`
- `resumed_game_spans_dates`

## Citations

Every emitted object cites stored normalized rows.

Required citation roles:

- entry event row
- preceding state event row when used
- exit event row
- team's next-pitcher entry event row when used as exit boundary
- `game_logs` row, citing `games_started` and `innings_pitched_outs`
- `play_by_play_processed_games` marker with `citation_role=processing_gate`
- order objects cite every team-sequence entry event
- reconciliation objects cite both source sides when present

`game_log_row_missing` without an internal pitcher id is dead-letter-only by
the subject identity guard.

## Correction And Recompute

Corrections to cited `game_play_by_play_events` or `game_logs` rows mark
dependent appearance context evidence as `recompute_needed` through the shared
Phase 0D recompute hook. Rebuilds refresh the same `evidence_key` and preserve
the superseded prior claim in computation trace.

The family builds inside the existing fail-soft Phase 0D evidence stage and
uses the `PHASE0D_EVIDENCE_BUILD` kill switch.

## Explicit Non-Claims

This branch makes no claims about:

- inherited traffic
- clean/traffic outing or inning context
- pressure/leverage
- role claims
- manager-intent language
- usage-pattern observations
- starter exposure
- public payload/API/UI/copy changes
- scores/ranks/grades
- prediction/availability/fatigue language
- pitch-level/Statcast
- PBP runner/base-state reconstruction
