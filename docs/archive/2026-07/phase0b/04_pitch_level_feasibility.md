# Phase 0B-05 - Pitch-Level Source Feasibility Audit

Status: `AUDIT-ONLY-0B`

Categories covered:

- Category 11: Pitch-level / Statcast data
- Category 12: Batted-ball and contact-quality data
- Category 13: Plate appearance and batter-context data

This audit evaluates whether pitch-level, batted-ball, contact-quality, and
batter-context sources can later support BaseballOS bullpen intelligence. It
does not implement ingestion, schema, API, frontend, public copy, source
adoption, helper-library integration, evidence engines, or product behavior.

## Scope Guardrails

- Documentation and probe evidence only.
- No production code behavior changes.
- No schema changes or migrations.
- No ingestion changes.
- No frontend changes.
- No leverage proxy design or implementation.
- No matchup-prediction feature.
- No Statcast ingestion, pybaseball integration, baseballr integration, or paid
  provider adoption.
- Do not use FanGraphs, Baseball Reference, Stathead, or other restricted or
  scraped sources as ingestion candidates in this branch.
- A library is not a license. Helper libraries can reduce retrieval work, but
  Baseball Savant / Statcast source terms still govern use.

## Evidence Method

Current repository usage was inspected before external source conclusions. The
external probe is dated, read-only, summary-only, and separate from production
code.

| evidence type | path or source |
| --- | --- |
| Phase 0B framework | `docs/phase0b/README.md`; `docs/phase0b/templates/source_category_matrix.md` |
| Existing foundation inventory | `docs/phase0b/01_existing_foundation.md` |
| Stats API core audit | `docs/phase0b/02_statsapi_core.md` |
| Stats API context audit | `docs/phase0b/03_statsapi_context.md` |
| Current stored game-log model | `backend/models/game_log.py` |
| Current fatigue/workload posture | `backend/services/fatigue.py` |
| Current dependencies | `backend/requirements.txt`; `frontend/package.json` |
| V4 roadmap pitch-level intent | `docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md` |
| Read-only probe record | `docs/phase0b/probes/pitch_level_feasibility/2026-07-04_pitch_level_feasibility_probe.md` |
| External source docs | `https://baseballsavant.mlb.com/csv-docs`; `https://github.com/jldbc/pybaseball/blob/master/docs/statcast.md`; `https://billpetti.github.io/baseballr/reference/index.html` |

## 1. Existing Repo Pitch-Level Usage

| question | current answer | evidence |
| --- | --- | --- |
| Does BaseballOS currently ingest pitch-level data? | No. Current ingestion stores game-level pitching lines and derived completed-game context, not one row per pitch. | `backend/models/game_log.py:31-71`; `docs/phase0b/03_statsapi_context.md:70-74` |
| Does BaseballOS currently store Statcast fields? | No. Searches found no `release_speed`, `pitch_type`, `launch_speed`, `launch_angle`, `estimated_woba`, or equivalent Statcast fields in models, migrations, services, or tests. | repo search; `backend/models/game_log.py:41-65` |
| Does BaseballOS currently store pitch type, velocity, whiff, CSW, contact quality, or batter-context fields? | No. It stores appearance-level pitches thrown, strikes, innings/outs, line stats, inherited runners, save/hold/outcome flags, and correction metadata. | `backend/models/game_log.py:41-71` |
| Does BaseballOS currently use pybaseball or baseballr? | No. Backend dependencies do not include pybaseball, R, or baseballr; frontend dependencies are UI/runtime only. | `backend/requirements.txt:1-12`; `frontend/package.json:1-27` |
| Do current public claims imply pitch-level evidence? | Current public surfaces are based on workload, availability, roster, schedule, and completed-game context. Existing Phase 0B docs keep pitch-level evidence out of scope until this audit. | `docs/phase0b/01_existing_foundation.md:154-178`; `docs/phase0b/03_statsapi_context.md:91-102` |
| Are there existing roadmap intents for pitch-level evidence? | Yes. The roadmap lists pitch type, average velocity, pitch mix, strike rate, whiff/swinging-strike proxy, zone/chase, contact, and trend ideas as future work. | `docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md:243-254`; `docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md:437-450` |

### Current Gap

BaseballOS can currently explain workload and appearance context, but it cannot
claim pitch-shape, pitch-mix, whiff, command, velocity-trend, contact-quality,
or batter-context evidence from stored data. Any public wording that implies a
reliever's stuff, command, arsenal, whiff ability, velocity trend, contact
quality allowed, or batter difficulty must remain unsupported until a later
phase adds legally cleared, correction-aware, sample-size-safe evidence.

## 2. Pitch-Level Field Feasibility

The read-only Baseball Savant CSV probe returned 4,091 rows and 119 fields for
one regular-season date, using the Baseball Savant Statcast search CSV export.
Field names and completeness are point-in-time observations, not an adoption
decision.

| field group | observed fields | availability | 0B-05 assessment |
| --- | --- | --- | --- |
| Game identifier mapping | `game_pk`, `game_date`, `game_year`, `home_team`, `away_team` | available | Strong technical candidate for mapping to existing MLB game ids, but legal and correction posture remain open. |
| Pitcher/batter identifiers | `pitcher`, `batter`, `player_name` | available | Strong technical candidate for MLBAM id joins; BaseballOS still needs player-resolution and stale-name handling. |
| Event sequence | `at_bat_number`, `pitch_number`, `sv_id`, `inning`, `inning_topbot` | available | Supports sequence reconstruction; must fail closed on missing or duplicate sequence fields. |
| Pitch type/name | `pitch_type`, `pitch_name` | available | Good internal candidate for pitch mix and usage; public language needs sample-size and legal clearance. |
| Velocity | `release_speed`, `effective_speed` | available | Useful internal candidate for last-outing vs baseline reads; one dip must not become a decline claim. |
| Release traits | `release_extension`, `release_pos_x`, `release_pos_y`, `release_pos_z`, `arm_angle` | available | Internal-only unless later evidence design proves stable and explainable baseball value. |
| Spin and movement | `release_spin_rate`, `spin_axis`, `pfx_x`, `pfx_z`, `api_break_*` fields | available | Internal-only; high correction and explanation burden. |
| Location/zone/count | `plate_x`, `plate_z`, `zone`, `sz_top`, `sz_bot`, `balls`, `strikes` | available | Candidate for strike, zone, chase, and command proxies, but exact definitions and thresholds belong to 0D design. |
| Description/result | `description`, `type`, `events`, `des` | available/partial | Pitch result is available; `events` is plate-appearance-specific and partial by design. |
| Swing/take/whiff/CSW | derivable from `description`, `type`, count, and event fields | derivable | Good internal candidate, but rules must be explicit and tested against source values. |
| Chase | likely derivable from swing descriptions plus zone/plate fields | partial | Do not build until zone definitions and edge cases are audited. |
| First-pitch strike | derivable from `pitch_number`, `description`, and count | derivable | Candidate after rule design; public use needs sample-size guardrails. |
| Pitch mix/usage | derivable from pitch type/name by pitcher/date/window | derivable | Valuable bullpen evidence candidate, internal-first. |
| Velocity and movement trends | derivable from pitch-level time windows | derivable | Useful but high overclaim risk; no public trend without sample sufficiency and comparable context. |
| Command/location proxies | derivable from location, zone, count, and outcome | derivable | High interpretation risk; keep internal until 0D defines evidence rules. |

## 3. Batted-Ball And Contact-Quality Feasibility

Contact-quality fields are only present when the pitch produces relevant contact
or a resolved plate-appearance outcome. In the first 500 sampled rows, many
contact fields were intentionally sparse.

| field group | observed fields | classification | 0B-05 posture |
| --- | --- | --- | --- |
| Exit velocity | `launch_speed` | INTERNAL-ONLY | Valuable for contact quality allowed, but only on balls in play and sample-size-sensitive. |
| Launch angle | `launch_angle` | INTERNAL-ONLY | Valuable with exit velocity; not meaningful on all pitches. |
| Batted-ball type | `bb_type` | INTERNAL-ONLY | Useful for ground ball / line drive / fly ball / popup context; sparse by design. |
| Hard-hit indicators | derivable from `launch_speed` after threshold design | INTERNAL-ONLY | Do not choose thresholds in 0B-05. |
| Barrel indicators | likely derivable from `launch_speed`, `launch_angle`, and/or `launch_speed_angle` | UNKNOWN | Needs exact source definition, threshold design, and legal review. |
| Expected batting average | `estimated_ba_using_speedangle` | INTERNAL-ONLY | High interpretation risk; avoid public score-like framing. |
| Expected wOBA | `estimated_woba_using_speedangle` | INTERNAL-ONLY | Useful for internal context, but public use risks generic analytics creep. |
| Actual wOBA value | `woba_value`, `woba_denom` | INTERNAL-ONLY | Plate-appearance outcome field; not pitch-by-pitch on every row. |
| Contact quality allowed by relievers | derived aggregate | INTERNAL-ONLY | Candidate only after sample-size, correction, and legal posture are resolved. |
| Bad results vs bad contact quality | derived comparison | INTERNAL-ONLY | Valuable explanatory idea, but must not imply prediction or pitcher diagnosis. |

Recommended posture: internal-first. No contact-quality field should become a
public candidate until it is legally/source-safe, stable, explainable, corrected,
and sample-size-safe.

## 4. Plate Appearance And Batter-Context Feasibility

BaseballOS explains bullpen usage. It should not become a matchup-prediction
product.

| context topic | observed fields | helpful usage boundary | risk |
| --- | --- | --- | --- |
| Batter handedness | `stand` | Explain platoon exposure faced by relievers. | Can drift into matchup prediction if framed as expected future outcome. |
| Pitcher handedness | `p_throws` | Explain same-side/opposite-side exposure. | Must not replace role or manager-intent evidence. |
| Platoon context | derivable from `stand` and `p_throws` | Explain why an outing was difficult or specialized. | Avoid "better matchup" or future-use recommendations. |
| Batter sequence faced | `batter`, `at_bat_number`, `pitch_number`, `inning` | Explain who a reliever faced and in what sequence. | Needs identity joins and small-sample caution. |
| Order exposure | `n_thruorder_pitcher`, `n_priorpa_thisgame_player_at_bat` | Contextual game-flow explanation only. | No direct lineup slot was observed; do not invent top/middle/bottom order. |
| Batter lineup position | no direct `batting_order` field observed | UNKNOWN. Could require lineup source beyond this CSV. | Generic analytics creep and source expansion risk. |
| Batter quality proxy | no source-safe field audited here | Out of scope. | Would turn BaseballOS toward matchup prediction. |

Safe future public language, if legal and sample-size conditions are met:

- "He faced mostly left-handed batters."
- "Most of his traffic came with two strikes or after deep counts."
- "The contact he allowed was mostly on balls in play with measured exit data."

Unsafe public language:

- "He is a bad matchup for lefties."
- "The manager should avoid him against the middle of the order."
- "His stuff is declining."
- "His command is broken."
- "This pitcher is likely to get hit."

## 5. Legal / Terms / Attribution / Storage Posture

| topic | posture |
| --- | --- |
| Baseball Savant / Statcast public data | Technically accessible through public CSV export and documented fields, but legal posture remains `needs-legal-review`. |
| Internal research | Plausible as audit/probe activity, but not cleared for production storage or automated ingestion. |
| Stored derived aggregates | Potentially lower risk than raw feed storage, but still `needs-legal-review`. |
| Public display | Not approved in 0B-05. Keep `INTERNAL-ONLY` or `UNKNOWN-UNTIL-LEGAL`. |
| Raw cache/storage | `raw-cache-risk`; do not store raw pitch rows without explicit legal, retention, and correction decisions. |
| Redistribution | Unknown and not approved. |
| Paid/commercial use | Unknown and not approved. |
| Attribution requirements | UNKNOWN. Must be resolved before public display. |
| Rate limit / access stability | UNKNOWN. The minimal query shape produced an uncontrolled large response; future work needs strict windows and backoff. |
| pybaseball | Retrieval helper only. It can return pitch-level Statcast data, but it is not installed, not adopted, and not a license. |
| baseballr | Retrieval helper only. It exposes Baseball Savant / Statcast functions, but it is not installed, not adopted, and not a license. |

## 6. Correction And Finality Behavior

Pitch-level evidence should be final-only until proven otherwise. Statcast
fields may be late, missing, reprocessed, or corrected after initial
availability; exact latency was not measured in this branch.

Future implementation would need Phase 0A-style provenance before any public
display:

- source query window and endpoint/helper version
- row identity based on `game_pk`, `at_bat_number`, `pitch_number`, pitcher id,
  and batter id
- first seen timestamp and last corrected timestamp
- correction count and changed-field tracking
- raw-vs-derived storage policy
- dead-letter behavior for partial or ambiguous corrections
- requery plan for final games and late Statcast updates

Missing, late, changed, or partial data must withhold affected pitch-level
evidence rather than filling from assumptions.

## 7. Sample-Size And Public-Language Guardrails

Minimum-sample policy belongs to Phase 0D evidence design. 0B-05 does not pick
numeric thresholds because this audit does not contain enough evidence to
justify them.

Guardrails future phases must inherit:

- One outing cannot support a public trend claim.
- One velocity dip cannot support a public decline claim.
- Small pitch samples should be marked as small sample or withheld.
- Pitch-mix changes need enough pitches and comparable context.
- Contact-quality reads need enough balls in play.
- Batter-context reads must explain usage, not predict outcomes.
- Public language should cite evidence and avoid diagnosis, manager intent,
  future availability, future performance, or recommendation framing.
- Expected metrics such as xBA or xwOBA should not become public score framing
  without explicit product-language approval.

## 8. Source Category Matrix Rows

These rows follow `docs/phase0b/templates/source_category_matrix.md`. They are
audit rows only. No row approves ingestion, raw storage, public display, or
source adoption.

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11_pitch_level_statcast | statcast_pitch_identity_sequence | savant_statcast | Baseball Savant Statcast CSV `type=details` | available | final+lag(observed) | corrected-after-final | rows may be late or reprocessed; row identity must be correction-aware | missing sequence, duplicate pitch numbers, ambiguous game id, endpoint timeout | observed one-date CSV; broader history not audited | needs-legal-review | TBD | raw-cache-risk | B | high | core | INTERNAL-ONLY | suppress pitch-level evidence unless game, at-bat, pitch, pitcher, and batter ids are present | EVIDENCE-0D | `docs/phase0b/probes/pitch_level_feasibility/2026-07-04_pitch_level_feasibility_probe.md` | 0B-05 |
| 11_pitch_level_statcast | pitcher_batter_game_identifiers | savant_statcast | CSV fields `game_pk`, `pitcher`, `batter`, `game_date`, teams | available | final+lag(observed) | corrected-after-final | id mapping must be rechecked after source corrections | missing player id, stale player mapping, team mismatch | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | mark row UNKNOWN when identifier mapping fails | FOUNDATION-0C | probe record; `backend/models/game_log.py:31-40` | 0B-05 |
| 11_pitch_level_statcast | pitch_type_name | savant_statcast | CSV fields `pitch_type`, `pitch_name` | available | final+lag(observed) | corrected-after-final | pitch labels can be reclassified | missing pitch type, unknown code, label correction | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | withhold pitch-mix read when pitch type/name is missing or reclassified | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | velocity_effective_velocity | savant_statcast | CSV fields `release_speed`, `effective_speed` | available | final+lag(observed) | corrected-after-final | velocity values may be corrected or missing | missing velocity, non-final row, small sample, sensor gap | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | mark velocity context UNKNOWN when samples are too small or values are missing | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | spin_movement_release_traits | savant_statcast | CSV spin, movement, release, and arm-angle fields | available | final+lag(observed) | corrected-after-final | tracking traits may be reprocessed | missing spin/movement, sensor calibration, schema drift | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | high | supporting | INTERNAL-ONLY | do not expose trait reads when source fields are missing or unexplained | LATER-V4 | probe record | 0B-05 |
| 11_pitch_level_statcast | pitch_location_zone_count | savant_statcast | CSV fields `plate_x`, `plate_z`, `zone`, `balls`, `strikes` | available | final+lag(observed) | corrected-after-final | zone/location fields may be corrected | missing location, unknown zone, count anomaly | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | high | core | INTERNAL-ONLY | withhold command/zone claims until definitions and thresholds are designed | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | pitch_result_description | savant_statcast | CSV fields `description`, `type`, `events`, `des` | available | final+lag(observed) | corrected-after-final | result/event text can correct after scoring updates | missing description, event only on PA-ending pitch, unknown value | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | do not infer outcome when description/type is missing or unknown | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | swing_take_whiff_csw_derivables | derived_internal | derived from `description`, `type`, count, and pitch sequence | derivable | final+lag(observed) | corrected-after-final | derived flags must recompute from corrected rows | unknown description, foul/tip edge case, rule drift | not stored today | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | core | INTERNAL-ONLY | mark UNKNOWN until deterministic value maps are defined and tested | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | pitch_mix_usage | derived_internal | aggregate `pitch_type` / `pitch_name` by pitcher, game, and window | derivable | final+lag(observed) | corrected-after-final | aggregates must recompute after pitch-label corrections | missing pitch type, too few pitches, incomparable windows | not stored today | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | withhold mix read for small or incomparable samples | EVIDENCE-0D | probe record | 0B-05 |
| 11_pitch_level_statcast | velocity_movement_trend_candidates | derived_internal | compare velocity/movement fields across appearances/windows | derivable | final+lag(observed) | corrected-after-final | trend aggregates must recompute after source corrections | one-outing noise, missing fields, role/context mismatch | not stored today | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | supporting | INTERNAL-ONLY | never publish trend claim without sample and comparable-context rules | EVIDENCE-0D | probe record | 0B-05 |
| 12_batted_ball_contact | batted_ball_exit_velocity_launch_angle | savant_statcast | CSV fields `launch_speed`, `launch_angle` | partial | final+lag(observed) | corrected-after-final | contact rows can be late or reprocessed | no ball in play, missing launch data, small contact sample | observed one-date CSV; sparse by design | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | suppress contact-quality read when ball-in-play sample is too small | EVIDENCE-0D | probe record | 0B-05 |
| 12_batted_ball_contact | hard_hit_barrel_contact_quality | derived_internal | derive from contact fields and source definitions | derivable | final+lag(observed) | corrected-after-final | derived contact flags must recompute after source corrections | missing launch fields, undefined barrel threshold, small sample | not stored today | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | supporting | INTERNAL-ONLY | mark UNKNOWN until exact definitions and thresholds are approved | EVIDENCE-0D | probe record; Baseball Savant CSV docs | 0B-05 |
| 12_batted_ball_contact | expected_outcome_xba_xwoba | savant_statcast | CSV fields `estimated_ba_using_speedangle`, `estimated_woba_using_speedangle` | partial | final+lag(observed) | corrected-after-final | expected metrics can be reprocessed | missing expected value, model opacity, score-like framing | observed one-date CSV; sparse by design | needs-legal-review | TBD | raw-cache-risk | B | high | contextual | INTERNAL-ONLY | do not expose expected metrics publicly without legal and product-language approval | UNKNOWN-UNTIL-LEGAL | probe record | 0B-05 |
| 13_batter_context | batter_pitcher_handedness | savant_statcast | CSV fields `stand`, `p_throws` | available | final+lag(observed) | corrected-after-final | handedness can be corrected with player metadata | missing handedness, switch-hitter context, player id mismatch | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | use only descriptive exposure language; no matchup prediction | EVIDENCE-0D | probe record | 0B-05 |
| 13_batter_context | lineup_order_exposure | none_found | no direct `batting_order` field observed in probe CSV | unavailable | UNKNOWN | UNKNOWN | no correction behavior audited | missing lineup slot, unsupported source, generic analytics creep | UNKNOWN | needs-legal-review | TBD | do-not-store | UNVERIFIED | medium | contextual | UNKNOWN | do not infer top/middle/bottom order without a source-safe lineup field | AUDIT-ONLY-0B | probe record | 0B-05 |
| 13_batter_context | batter_context_fields | savant_statcast | CSV fields `batter`, `stand`, `n_thruorder_pitcher`, `n_priorpa_thisgame_player_at_bat` | partial | final+lag(observed) | corrected-after-final | context fields may be corrected with scorer/source updates | missing batter id, source ambiguity, prediction framing | observed one-date CSV | needs-legal-review | TBD | raw-cache-risk | B | high | contextual | INTERNAL-ONLY | explain usage context only; do not predict matchup outcome | LATER-V4 | probe record | 0B-05 |
| 11_pitch_level_statcast | pybaseball_retrieval_helper | savant_statcast | pybaseball `statcast` helper over Baseball Savant data | available | final+lag(observed) | corrected-after-final | helper behavior can change independently from source | dependency drift, scrape fragility, source terms unresolved | external docs only; not installed locally | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | medium | contextual | INTERNAL-ONLY | treat helper failure as source unavailable; never treat library as legal clearance | UNKNOWN-UNTIL-LEGAL | pybaseball docs; `backend/requirements.txt:1-12` | 0B-05 |
| 11_pitch_level_statcast | baseballr_retrieval_helper | savant_statcast | baseballr Statcast search helpers over Baseball Savant data | available | final+lag(observed) | corrected-after-final | helper behavior can change independently from source | R dependency, package drift, source terms unresolved | external docs only; not installed locally | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | medium | contextual | INTERNAL-ONLY | treat helper failure as source unavailable; never treat library as legal clearance | UNKNOWN-UNTIL-LEGAL | baseballr docs; `backend/requirements.txt:1-12` | 0B-05 |
| 11_12_13_source_risk | legal_storage_redistribution_risk | savant_statcast | Baseball Savant CSV export and helper-retrieved payloads | partial | UNKNOWN | UNKNOWN | legal/source posture can change; correction and redistribution unknown | unclear terms, attribution unknown, raw cache risk, rate limits | UNKNOWN | needs-legal-review | TBD | do-not-store | UNVERIFIED | high | core | UNKNOWN | do not store raw pitch rows or display public fields until legal review resolves terms | UNKNOWN-UNTIL-LEGAL | probe record; Baseball Savant CSV docs | 0B-05 |

## 9. Fail-Closed Rules

| condition | fail-closed behavior |
| --- | --- |
| Missing pitch-level data | Do not derive pitch-mix, velocity, whiff, CSW, command, or contact-quality evidence. |
| Late pitch-level data | Withhold public and comparison reads until the final query window is complete and trusted. |
| Changed/reprocessed pitch-level data | Recompute derived aggregates and increment correction provenance before use. |
| Ambiguous game/pitcher identifier mapping | Mark pitch-level row and derived player aggregates UNKNOWN. |
| Missing pitch type | Exclude from pitch-mix and pitch-type velocity reads. |
| Missing velocity | Exclude from velocity and effective-velocity reads. |
| Missing batted-ball values | Exclude from contact-quality reads; do not count missing contact as soft contact. |
| Small sample | Withhold trend, mix-change, velocity-change, whiff, CSW, chase, and contact-quality claims. |
| Legal uncertainty | Keep public display `INTERNAL-ONLY` or `UNKNOWN`; do not store raw rows. |
| Raw storage risk | Prefer no raw cache until legal, retention, and correction policy exists. |
| Endpoint timeout/error | Treat source as unavailable for the affected window; do not backfill from assumptions. |
| Schema drift/unknown field shape | Drop the affected field group and fail closed. |
| pybaseball/baseballr helper failure | Treat as retrieval failure, not data absence; do not switch to restricted sources. |

## 10. Findings And Recommendations

### Valuable For Bullpen Intelligence

- Pitch type, pitch name, velocity, effective velocity, pitch count context, and
  pitch sequence are the strongest technical candidates.
- Whiff, CSW, first-pitch strike, zone rate, pitch mix, and velocity trend are
  useful derived candidates if value maps and sample rules are designed.
- Exit velocity, launch angle, batted-ball type, and expected outcome fields can
  help distinguish bad results from damaging contact, but should start internal.
- Batter handedness and batter sequence can explain usage context without
  becoming a prediction product.

### Internal-First

- All pitch-level and contact-quality data should remain internal-first because
  legal, correction, sample-size, storage, and public-language rules are not yet
  resolved.
- pybaseball and baseballr are feasible research helpers only. They are not
  dependencies, not source adoption, and not legal clearance.

### Could Become Public-Candidate Later

- Descriptive pitch-mix or velocity context may become public-candidate only
  after legal review, correction provenance, sample thresholds, and clear
  language rules exist.
- Contact-quality summaries may become public-candidate only as simple evidence
  statements with enough balls in play and no expected-metric score framing.

### Should Remain Out Of Scope

- Matchup prediction.
- Batter quality scores.
- Manager-intent claims.
- Injury or mechanical diagnosis from velocity, release, spin, or movement.
- Public xBA/xwOBA score framing.
- FanGraphs, Baseball Reference, Stathead, or paid-source adoption in this
  branch.

### Requires Later Work

- Legal/source review for Baseball Savant / Statcast use.
- Phase 0D evidence design for thresholds, sample-size rules, and derivations.
- Correction/finality design before any public display.
- Storage design that prefers derived aggregates over raw feed replication unless
  legal review explicitly approves raw storage.

## 11. Phase 0B-05 Decision

Pitch-level Statcast data is technically feasible and valuable for future
BaseballOS bullpen intelligence, especially for pitch mix, velocity, whiff/CSW,
zone/count, and contact-quality context. It is not approved for ingestion,
storage, public display, or source adoption in this branch.

The recommended next posture is internal-first research and Phase 0D evidence
design only after legal/source review. Public product language must stay
descriptive, evidence-linked, sample-size-aware, and strictly bullpen-focused.
