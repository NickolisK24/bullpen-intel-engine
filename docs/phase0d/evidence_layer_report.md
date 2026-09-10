# Phase 0D Evidence Layer Report

## Summary

Phase 0D exits with an internal evidence layer, a classification registry, and
public-language packages. This report is the Phase 0E+ handoff. It does not
authorize public rendering, posture changes, new evidence emission, sync-stage
changes, or schema changes.

Every Phase 0D evidence rule remains `internal_only`.

Classification tally:

- PC: 43
- EL: 9
- IO: 4
- PI: 8

## Global Gates

Every PC/EL item below is blocked by both gates:

- `phase0b_legal_source_review`
- `explicit_surface_phase`

## Misuse-Prevention Tags

Every PC/EL item carries the full misuse-prevention tag set:

- `no_health_inference`
- `no_availability_inference`
- `no_role_assignment`
- `no_manager_intent`
- `no_team_quality_labels`
- `no_pressure_leverage_public`
- `no_scores_ranks_grades`
- `no_prediction_betting`

## Shown Vs Supporting Contract

A public claim is showable only when the public surface can expose the rule
text, thresholds, cited rows, completeness state, and reason codes. A claim
whose citations cannot resolve must not render.

## Diagnostics Vs Trust Surfaces

Permanently internal diagnostics may inform Phase 0K aggregate trust surfaces,
but they are never public claims. Phase 0K should not relitigate this boundary.

## Capability Cap

The base-state decision accepts boxscore-only inherited attribution for V4 and
records this cap:

- no per-inning clean/traffic granularity
- no bequeathed traffic
- no entry-band traffic axis

The cap remains until a future base-state addendum is deliberately reopened.

## PC Inventory

| Rule id | Required language ref | Preconditions |
| --- | --- | --- |
| `workload_last_final_appearance` | `#workload-recovery` | past-tense date only |
| `workload_days_of_rest` | `#workload-recovery` | never renders availability |
| `workload_window_appearances` | `#workload-recovery` | window and count both shown |
| `workload_window_pitches` | `#workload-recovery` | unknown-subtotal language |
| `workload_window_outs` | `#workload-recovery` | window and count both shown |
| `workload_window_batters_faced` | `#workload-recovery` | unknown-subtotal language |
| `usage_back_to_back` | `#workload-recovery` | threshold displayed beside flag |
| `usage_three_in_four` | `#workload-recovery` | threshold displayed beside flag |
| `usage_four_in_six` | `#workload-recovery` | threshold displayed beside flag |
| `outing_multi_inning` | `#workload-recovery` | threshold displayed beside flag |
| `outing_high_pitch` | `#workload-recovery` | count always rendered beside threshold |
| `appearance_short_rest` | `#workload-recovery` | threshold displayed beside flag |
| `appearance_entry_context` | `#appearance-entry-exit` | base-state limitation always rendered |
| `appearance_exit_context` | `#appearance-entry-exit` | play-granularity note |
| `appearance_order_in_game` | `#appearance-entry-exit` | sequence-fact-only phrasing |
| `appearance_innings_spanned` | `#appearance-entry-exit` | span-not-outs language |
| `appearance_game_phase` | `#appearance-entry-exit` | inning-band-only |
| `appearance_inherited_runners` | `#inherited-traffic-clean-outing` | boxscore-source language |
| `appearance_inherited_runners_scored` | `#inherited-traffic-clean-outing` | boxscore-source language |
| `appearance_inherited_traffic_outcome` | `#inherited-traffic-clean-outing` | boxscore-source language |
| `outing_clean` | `#inherited-traffic-clean-outing` | full definition display incl. HBP/ROE exclusion verbatim |
| `outing_traffic` | `#inherited-traffic-clean-outing` | threshold plus counts rendered |
| `team_bullpen_share_of_outs` | `#starter-exposure-calendar-density` | both sums shown |
| `team_bullpen_outs_window` | `#starter-exposure-calendar-density` | window and count both shown |
| `team_bullpen_pitches_window` | `#starter-exposure-calendar-density` | known-subtotal language |
| `team_reliever_appearances_window` | `#starter-exposure-calendar-density` | appearances-not-distinct-arms disclaimer verbatim |
| `team_short_start_count_window` | `#starter-exposure-calendar-density` | 14-outs definition display |
| `team_consecutive_game_days` | `#starter-exposure-calendar-density` | componentized counts only |
| `team_doubleheader_today` | `#starter-exposure-calendar-density` | schedule fact only |
| `team_recent_doubleheader` | `#starter-exposure-calendar-density` | componentized counts only |
| `team_off_day_yesterday` | `#starter-exposure-calendar-density` | schedule fact only |
| `team_off_day_tomorrow` | `#starter-exposure-calendar-density` | schedule-subject-to-change disclaimer mandatory |
| `team_calendar_density` | `#starter-exposure-calendar-density` | componentized counts only |
| `team_active_pitcher_census` | `#roster-depth-churn` | pitchers-not-relievers note |
| `pitcher_il_placement_context` | `#roster-depth-churn` | exact safe phrasing only |
| `pitcher_il_activation_context` | `#roster-depth-churn` | exact safe phrasing only |
| `team_public_il_count` | `#roster-depth-churn` | counts presence only; never statements about non-IL pitchers |
| `team_transaction_churn_window` | `#roster-depth-churn` | coverage caveat |
| `team_transaction_category_counts_window` | `#roster-depth-churn` | category definitions shown |
| `team_option_recall_churn` | `#roster-depth-churn` | coverage caveat |
| `team_roster_movement_churn` | `#roster-depth-churn` | coverage caveat |
| `appearance_finish_context` | `#entry-context-bands-usage-observations` | legacy under-fire caveat |
| `pitcher_save_hold_window` | `#entry-context-bands-usage-observations` | counts only, never rates |

## EL Inventory

| Rule id | Required language ref | Preconditions |
| --- | --- | --- |
| `pitcher_finish_usage_observation` | `#entry-context-bands-usage-observations` | band-derived components re-rendered as plain inning/margin facts; mechanical cell names never public; k=0 language review; floors intact and displayed |
| `pitcher_multi_inning_usage_observation` | `#entry-context-bands-usage-observations` | k=0 review; floors intact |
| `pitcher_first_reliever_usage_observation` | `#entry-context-bands-usage-observations` | k=0 review; floors intact; sequence-fact-only phrasing re-verified |
| `team_relief_contributor_basis` | `#team-relief-contributor-composition` | denominator disclaimer travels verbatim; production season-segment of attribution-exclusion rates |
| `team_relief_rest_distribution` | `#team-relief-contributor-composition` | basis preconditions inherited |
| `team_relief_density_usage_count` | `#team-relief-contributor-composition` | basis preconditions inherited |
| `team_relief_workload_concentration` | `#team-relief-contributor-composition` | basis preconditions inherited; corroboration-mismatch rate observed low |
| `team_relief_outing_context_mix` | `#team-relief-contributor-composition` | basis preconditions inherited; 0D-04 emission-policy coupling documented at any surface |
| `team_relief_finish_spread` | `#team-relief-contributor-composition` | basis preconditions inherited |

## Audit Results

The 0D-09 test suite validates:

- every live Phase 0D rule has exactly one classification
- no classification entry is orphaned
- no registered rule carries DEFERRED or REJECTED
- PC/EL language anchors resolve
- PC/EL entries carry both global gates and the full misuse-prevention tag set
- stored evidence rows resolve to registered rule definitions
- citations resolve to provenance-carrying rows or explicit synthetic/missing
  provenance records
- public modules do not import `evidence_classification`

## Phase 0E+ Handoff

Phase 0E+ can consume this report as an eligibility boundary. It must not move
any evidence into a public surface until the global gates pass and the selected
surface branch explicitly adopts the required language package.
