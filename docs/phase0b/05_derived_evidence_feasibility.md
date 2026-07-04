# Phase 0B-06 - Derived Evidence Feasibility Audit

Status: `AUDIT-ONLY-0B`

Branch: `phase-0b/06-derived-evidence-feasibility`

This document audits which bullpen intelligence can be derived from BaseballOS
evidence already identified in Phase 0B, which evidence must wait for Phase 0C
foundation work, which evidence needs Phase 0D evidence design, and which
claims must remain internal-only, out of scope, or unknown.

This branch does not add ingestion, storage, schema, API, frontend, scoring, or
source-adoption behavior. It is a documentation-only feasibility map.

## Scope

Phase 0B-06 covers derived evidence across these bullpen source categories:

- `5_reliever_appearance`
- `6_workload_recovery`
- `7_starter_rotation_exposure`
- `14_game_leverage_pressure`
- `15_bullpen_role_intelligence`
- `16_team_bullpen_structure`
- `17_schedule_calendar_context`
- `18_historical_baselines`

It also records how these evidence families could answer the canonical
BaseballOS bullpen questions Q1-Q10, without approving public display.

## Source Evidence Used

| evidence | role in this audit |
| --- | --- |
| `docs/phase0b/01_existing_foundation.md` | Baseline for existing stored tables, correction provenance, freshness, current public language, and gaps. |
| `docs/phase0b/02_statsapi_core.md` | Baseline for game identity, schedule status, boxscore finality, pitching-line fields, correction handling, and current storage gaps. |
| `docs/phase0b/03_statsapi_context.md` | Baseline for final play-by-play, roster, transaction, injury, schedule-context, and fail-closed posture. |
| `docs/phase0b/04_pitch_level_feasibility.md` | Baseline for pitch-level and contact-quality feasibility, source posture, sample-size guardrails, and public-language limits. |
| `docs/phase0b/templates/source_category_matrix.md` | Canonical matrix columns, value lists, and advancement rules. |
| `docs/phase0b/templates/bullpen_question_map.md` | Canonical Q1-Q10 mapping format and default internal-only posture. |

## Decision Vocabulary

| classification | meaning |
| --- | --- |
| `DERIVABLE-NOW` | Can be computed from already documented BaseballOS stored evidence, subject to current freshness, completeness, and correction rules. |
| `AFTER-0C` | Needs Phase 0C foundation work before it can be trusted as stable evidence. |
| `REQUIRES-0D` | Needs Phase 0D evidence design, thresholds, product framing, and tests before use in recommendations or public reads. |
| `INTERNAL-ONLY` | May support internal classification, triage, or QA, but must not be displayed as a public product claim yet. |
| `OUT-OF-SCOPE` | Must not be inferred in V4 from the documented evidence set. |
| `UNKNOWN` | Must fail closed when required evidence is missing, stale, legally unclear, incomplete, partial, or not finality-safe. |

## Current Derivable Evidence From Stored Data

BaseballOS already stores enough completed-game evidence to derive limited
workload and usage context, but not enough to safely derive complete role,
traffic, leverage, command, injury, or manager-intent claims.

| evidence family | feasibility | current inputs | public posture | fail-closed behavior |
| --- | --- | --- | --- | --- |
| Pitcher/team/game identity | `DERIVABLE-NOW` | Pitcher identity, team assignment, game date, game id, opponent, game type. | Internal foundation only. | Unknown when identity, team, date, or game id is missing. |
| Completed appearance date | `DERIVABLE-NOW` | Final completed-game logs and game dates. | Internal foundation only. | Exclude non-final, partial, stale, or correction-unsafe games. |
| Innings and outs burden | `DERIVABLE-NOW` | Innings pitched and outs-derived workload fields. | Internal-only until 0B-07. | Unknown when innings or outs are missing or inconsistent. |
| Pitch count burden | `DERIVABLE-NOW` where present | Nullable pitch counts and pitch-count correction behavior. | Internal-only until 0B-07. | Preserve unknown instead of imputing missing pitch counts. |
| Rolling workload windows | `DERIVABLE-NOW` | Recent appearances, pitches, innings, and outs over 3, 5, 7, and 14-day windows. | Internal-only until 0B-07. | Unknown when any required window is incomplete or not finality-safe. |
| Rest days | `DERIVABLE-NOW` | Most recent completed appearance date by pitcher. | Internal-only until 0B-07. | Unknown when last appearance cannot be proven from final data. |
| Back-to-back and dense usage | `DERIVABLE-NOW` | Appearance dates and rolling windows. | Internal-only until 0B-07. | Unknown when recent completed-game coverage is incomplete. |
| High-pitch or multi-inning usage | `DERIVABLE-NOW` | Pitch counts where present, innings pitched, outs. | Internal-only until 0B-07. | High-pitch reads withheld when pitch count is missing. |
| Team workload concentration | `DERIVABLE-NOW` | Recent team bullpen appearance distribution and pitcher-level burden. | Internal-only until 0B-07. | Unknown when team slate coverage or pitcher rows are incomplete. |
| Adjacent-day change context | `DERIVABLE-NOW` when trusted snapshots are comparable | Published snapshots and comparable prior-day baselines. | Current public wording may mention only supported changes. | Withhold when snapshots are stale, partial, or incomparable. |
| Correction provenance | `DERIVABLE-NOW` as metadata | Sync run id, snapshot id, correction status, hash, and correction timestamps where available. | Supportive trust metadata only. | Mark evidence unknown when correction state cannot be verified. |

## Reliever Appearance Evidence Feasibility

| evidence | feasibility | notes |
| --- | --- | --- |
| Did a reliever appear in a completed game? | `DERIVABLE-NOW` | Supported by final pitching-game rows after finality and correction checks. |
| How many recent appearances did a reliever make? | `DERIVABLE-NOW` | Supported by rolling final-game windows. |
| Did the reliever pitch on consecutive days? | `DERIVABLE-NOW` | Supported by final appearance dates. |
| Did the reliever pitch 3-in-4 or 4-in-6? | `DERIVABLE-NOW` | Supported by final appearance dates and complete game coverage. |
| How many pitches, innings, and outs were recorded? | `DERIVABLE-NOW` where present | Pitch counts remain nullable and must not be imputed. |
| Batters faced | `AFTER-0C` | Identified as available in core boxscore evidence but not currently stored as a stable field. |
| Appearance order | `AFTER-0C` or `REQUIRES-0D` | Boxscore pitcher order may support coarse order after storage design; precise entry context needs final play-by-play. |
| Entry inning and exit inning | `REQUIRES-0D` | Needs final play-by-play evidence design and correction rules. |
| Clean inning versus inherited traffic | `REQUIRES-0D` | Needs final play-by-play or stored inherited-runner context with explicit finality rules. |
| Entered with lead, tie, deficit, or save context | `REQUIRES-0D` | Needs inning, score, base/out, and official scoring context tied to final evidence. |
| Long-relief, opener, bulk, or bridge appearance | `REQUIRES-0D` | Can only be inferred from usage pattern and game context, not official role labels. |

## Bullpen Workload And Recovery Feasibility

| evidence | feasibility | public-language posture |
| --- | --- | --- |
| Recent pitch workload | `DERIVABLE-NOW` where pitch counts exist | Use descriptive workload language only; no public fatigue-score framing. |
| Recent innings and outs workload | `DERIVABLE-NOW` | Use descriptive burden language only. |
| Days of rest | `DERIVABLE-NOW` | State only when supported by final appearance history. |
| Back-to-back usage | `DERIVABLE-NOW` | State only from final completed-game evidence. |
| 3-in-4 and 4-in-6 density | `DERIVABLE-NOW` | Internal thresholding until 0B-07. |
| High-pitch appearance flag | `DERIVABLE-NOW` where pitch count exists | Unknown when pitch count is absent. |
| Multi-inning appearance flag | `DERIVABLE-NOW` | Supported by innings and outs. |
| Batters-faced burden | `AFTER-0C` | Requires stored batters-faced field. |
| High-stress inning burden | `REQUIRES-0D` | Needs transparent pressure proxy from final context. |
| Long inning or extended traffic burden | `REQUIRES-0D` | Needs final play-by-play and base/out context. |
| Team relievers used per game | `DERIVABLE-NOW` with complete team rows | Unknown when team pitching rows are incomplete. |
| Team workload concentration | `DERIVABLE-NOW` | Internal-only until public-display decision. |
| Rested but not trusted | `REQUIRES-0D` | Needs role/trust inference guardrails before product use. |
| Trusted but rest-restricted | `REQUIRES-0D` | Needs role/trust inference plus workload restrictions; no intent claim. |

## Starter And Rotation Exposure Feasibility

Starter exposure can explain bullpen pressure only when it is grounded in
completed-game starter evidence or clearly labeled schedule context. Probable
pitchers are not evidence of what happened.

| evidence | feasibility | notes |
| --- | --- | --- |
| Actual starter identity in completed games | `DERIVABLE-NOW` | Supported when pitching lines include starter flags or games started. |
| Starter innings and outs | `DERIVABLE-NOW` | Can support short-start pressure from final lines. |
| Starter pitch count | `DERIVABLE-NOW` where present | Nullable pitch counts remain unknown when absent. |
| Starter batters faced | `AFTER-0C` | Requires stored boxscore field. |
| Short-start frequency | `DERIVABLE-NOW` | Can be derived from starter innings over completed-game windows. |
| Bullpen innings following short starts | `DERIVABLE-NOW` with complete team pitching rows | Unknown when team rows or starter rows are incomplete. |
| Opener, bulk, piggyback, and bullpen-game flags | `REQUIRES-0D` | Usage-pattern inference only; must not be stated as official manager intent. |
| Rotation gaps from schedule and roster | `AFTER-0C` | Requires schedule, probable-starter, roster, transaction, and status foundation. |
| Starter injury or IL pressure | `AFTER-0C` | Public roster/IL evidence must be explicit; absence of a flag is not health evidence. |
| Upcoming starter exposure | `AFTER-0C` as context only | Schedule and probable starters can describe context, not completed evidence. |

## Game Leverage And Pressure Context Feasibility

BaseballOS can later build an internal, transparent pressure proxy from final
game context. It must not be framed as win probability, betting probability,
odds, or an official leverage model unless a later branch explicitly adopts and
validates such a source.

| pressure input | feasibility | rules |
| --- | --- | --- |
| Inning and outs at entry | `REQUIRES-0D` | Needs final play-by-play and stable entry/exit derivation. |
| Score differential at entry | `REQUIRES-0D` | Needs final play-by-play or equivalent final context. |
| Base/out state | `REQUIRES-0D` | Must fail closed when runners or outs are missing. |
| Inherited runners | `REQUIRES-0D` | Needs audited source behavior and correction handling. |
| Save or hold situation | `REQUIRES-0D` | May be supported by boxscore scoring plus final context. |
| Tie or one-run late-game context | `REQUIRES-0D` | Descriptive only; not a prediction. |
| Extra innings and runner rule context | `REQUIRES-0D` | Unknown until final context can identify rule-affected innings safely. |
| Mop-up or low-pressure context | `REQUIRES-0D` | Infer only from transparent score/inning rules. |
| Official leverage index | `OUT-OF-SCOPE` unless a legal, stable source is adopted | Do not fabricate or infer as if official. |
| Internal pressure proxy | `REQUIRES-0D` and `INTERNAL-ONLY` | Needs formula documentation, tests, confidence bounds, and fail-closed behavior. |

## Bullpen Role Intelligence Feasibility

No audited source in Phase 0B provides official current bullpen roles or
manager intent. Role intelligence can only be inferred from usage patterns after
evidence design.

| role read | feasibility | allowed language | disallowed language |
| --- | --- | --- | --- |
| Frequently used late in close games | `REQUIRES-0D` | "has been used late in close games" | "the manager trusts him" without evidence. |
| Protected on short rest | `REQUIRES-0D` | "was not used after recent workload" | "was unavailable due to fatigue" without explicit support. |
| Rested but rarely used in pressure | `REQUIRES-0D` | "rested with limited recent pressure usage" | "not trusted" as a certain public claim. |
| Trusted but rest-restricted | `REQUIRES-0D` | "recent high-usage arm with pressure usage history" | "will not be available tonight." |
| Closer/setup/long relief usage pattern | `REQUIRES-0D` | "usage pattern resembles late-inning or length role" | "official closer" unless an official source supports it. |
| Role quotes from public articles | `OUT-OF-SCOPE` for this branch | May need a later legal/source audit. | Do not ingest or summarize unaudited quote sources. |

## Team Bullpen Structure Feasibility

| structure read | feasibility | evidence path |
| --- | --- | --- |
| Number of recently used relievers | `DERIVABLE-NOW` | Final team pitching rows over completed-game windows. |
| Workload concentration across relievers | `DERIVABLE-NOW` | Recent usage distribution by pitcher. |
| Recently heavy-burdened arms | `DERIVABLE-NOW` | Workload windows, pitch counts where present, innings, outs, and appearance density. |
| Clean rested options | `REQUIRES-0D` | Needs workload, role, recent traffic, and possibly pitch-level evidence design. |
| Late-inning coverage | `REQUIRES-0D` | Needs role inference and final pressure context. |
| Long-relief coverage | `REQUIRES-0D` | Needs usage-pattern inference and starter-exposure context. |
| Left/right balance | `AFTER-0C` | Requires stable handedness and active roster foundation. |
| IL and depth pressure | `AFTER-0C` | Requires roster/IL/transaction foundation and public-language guardrails. |
| Active versus unavailable distinction | `AFTER-0C` | Requires public roster status, staleness handling, and unknown-safe status mapping. |
| Team shape label | `REQUIRES-0D` | Must be based on transparent evidence, not a black-box score. |

## Schedule And Calendar Context Feasibility

Calendar context is valuable for bullpen reads, but it must remain context
unless tied to completed evidence.

| calendar context | feasibility | rules |
| --- | --- | --- |
| Off day before or after a game | `AFTER-0C` | Requires stable schedule coverage and postponement handling. |
| Consecutive game days | `AFTER-0C` | Must handle doubleheaders, postponed games, and makeups. |
| Doubleheader context | `AFTER-0C` | Requires explicit doubleheader identifiers and game sequencing. |
| Day game after night game | `AFTER-0C` | Descriptive schedule context only. |
| Series length and getaway day | `AFTER-0C` | Context only; no usage prediction. |
| Suspended or resumed game pressure | `AFTER-0C` then `REQUIRES-0D` | Needs game identity, status, and resumed-game linkage before use. |
| Travel pressure | `UNKNOWN` | No audited source or rules in Phase 0B-06. |
| Calendar-rest advantage | `REQUIRES-0D` | Needs product framing and tests before any public comparison. |

## Historical Baselines And Comparisons

Historical comparisons are only useful when the comparison windows are complete,
final, comparable, and correction-aware.

| comparison | feasibility | rules |
| --- | --- | --- |
| Yesterday versus today workload state | `DERIVABLE-NOW` when trusted snapshots exist | Withhold when either snapshot is stale, partial, or incomparable. |
| 3, 7, and 14-day workload baselines | `DERIVABLE-NOW` | Compare only complete final windows. |
| Season-to-date team bullpen usage | `DERIVABLE-NOW` with complete stored rows | Internal-only until source completeness is proven. |
| Team self-baseline | `REQUIRES-0D` | Needs definition of normal range and sample minimums. |
| League baseline | `REQUIRES-0D` | Needs source completeness, season coverage, and comparison guardrails. |
| Pitch-level trend baseline | `REQUIRES-0D` after legal/source clearance | Needs Statcast/Savant legal posture and storage design. |
| Role usage baseline | `REQUIRES-0D` | Needs role inference design and drift handling. |
| What Changed eligibility | `DERIVABLE-NOW` for existing snapshot-backed deltas | Must not compare partial days or different coverage windows. |

## Q1-Q10 Data-To-Bullpen-Question Map

| question | evidence_family | matrix_rows_used | answers_it_how | public_evidence | internal_only | unknown_behavior | guardrails | earliest_phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q1: Which bullpens are fresh tonight? | Workload, rest, recent appearances, schedule rest | DER-01, DER-02, DER-03, DER-18 | Uses final recent appearances, rest days, dense-usage windows, and calendar context to identify lower recent burden. | Candidate only after 0B-07; final appearance dates and workload summaries may be inspectable later. | Fatigue scores, confidence flags, and threshold internals. | Mark UNKNOWN when workload windows, rest dates, pitch counts, or calendar context are missing, stale, partial, or not finality-safe. | Descriptive only; no availability prediction, injury inference, betting, fantasy, or confidence-score framing. | TBD in 0B-07 |
| Q2: Which bullpens are stretched? | Workload concentration, recent usage, multi-day burden | DER-01, DER-03, DER-04, DER-05 | Uses dense usage, team concentration, and recent burden to flag groups carrying heavy completed-game workload. | Candidate only after 0B-07; recent appearances, innings, and pitch counts where present. | Public fatigue scores, hidden thresholds, and internal prioritization. | Mark UNKNOWN when recent windows are incomplete, correction behavior is unresolved, or pitch counts are unavailable for pitch-based claims. | Descriptive burden only; do not publish fatigue-score framing. | TBD in 0B-07 |
| Q3: Which teams have late-game margin? | Role usage, pressure context, rested clean options | DER-08, DER-09, DER-15, DER-16, DER-17 | Combines late-game usage history, pressure context, current rest state, and team structure to estimate coverage margin. | Candidate only after 0B-07; usage evidence may be shown if final and explainable. | Role inference model, pressure proxy, and internal confidence. | Mark UNKNOWN when role, pressure, rest, or active-roster evidence cannot all be supported. | Avoid manager-intent certainty and ranking claims. | TBD in 0B-07 |
| Q4: Which teams lack clean options? | Traffic, workload, command stress, depth pressure | DER-07, DER-08, DER-12, DER-13, DER-15, DER-20 | Requires final traffic context, workload burden, roster/depth context, and later pitch-level support for command stress. | Candidate only after 0B-07; evidence must show final workload and supported traffic or depth signals. | Pitch-level stress metrics, role model, and pressure proxy. | Mark UNKNOWN when clean/messy appearance evidence, roster status, or pitch-level support is absent or legally unclear. | Do not turn incomplete evidence into a complete-sounding read. | TBD in 0B-07 |
| Q5: Which arms are being leaned on too heavily? | Repeated usage, pitch counts, appearance density, role context | DER-01, DER-02, DER-03, DER-05, DER-16 | Uses repeated final appearances and burden windows to identify arms with high recent usage relative to teammates. | Candidate only after 0B-07; recent usage counts and burden summaries. | Threshold internals and fatigue scoring. | Mark UNKNOWN when workload thresholds, windows, correction state, or pitch counts are incomplete for the specific claim. | Usage context only; no injury or performance prediction. | TBD in 0B-07 |
| Q6: Which arms are rested but not trusted? | Rest state, role usage, pressure usage history | DER-02, DER-15, DER-16 | Compares rest evidence with pressure/role usage history to detect rested arms with limited pressure use. | Candidate only after 0B-07; only evidence-backed usage history may be shown. | Trust model, pressure proxy, and confidence. | Mark UNKNOWN when both rest evidence and role/pressure evidence are not supported. | Avoid certainty about manager intent; prefer usage-pattern language. | TBD in 0B-07 |
| Q7: Which arms are trusted but rest-restricted? | Role usage, recent workload, dense usage windows | DER-01, DER-03, DER-15, DER-16 | Combines pressure usage history with recent workload restrictions to identify likely high-value arms carrying rest risk. | Candidate only after 0B-07; show recent workload and usage-pattern evidence only. | Internal trust classification and rest thresholds. | Mark UNKNOWN when role evidence or rest-restriction evidence is missing. | No public fatigue-score framing; use evidence-backed usage language. | TBD in 0B-07 |
| Q8: Which teams are being pressured by short starts? | Starter innings, bullpen innings burden, schedule context | DER-10, DER-11, DER-18 | Uses actual starter workload and bullpen follow-on burden to explain completed short-start pressure. | Candidate only after 0B-07; final starter innings and bullpen usage summaries. | Opener/bulk inference, rotation-gap model, and pressure thresholds. | Mark UNKNOWN when starter rows, team rows, or completed-game coverage are incomplete. | Recent-context only; no upcoming starter projection. | TBD in 0B-07 |
| Q9: Which teams are pressured by injuries/IL/depth loss? | Roster status, IL, transactions, active depth, handedness | DER-12, DER-13, DER-14, DER-17 | Uses public roster, IL, transaction, and structure evidence to describe depth pressure. | Candidate only after 0B-07 and legal review; only explicit public status evidence. | Depth-pressure thresholds and internal confidence. | Mark UNKNOWN when public roster or IL evidence is missing, stale, conflicting, legally unclear, or inferred from absence. | No private injury claims; never say healthy or injury-free without explicit support. | TBD in 0B-07 |
| Q10: What changed since yesterday? | Trusted snapshots, comparable baselines, workload/roster deltas | DER-01, DER-05, DER-12, DER-14, DER-19 | Compares trusted snapshots and comparable windows to show evidence-backed deltas only. | Candidate only after 0B-07; snapshot-backed changes and supporting evidence. | Change ranking, confidence, and internal suppression reasons. | Withhold change reads when snapshots are partial, stale, incomparable, or not finality-safe. | No comparison against partial days, incompatible windows, or unsupported roster changes. | TBD in 0B-07 |

## Source Category Matrix Rows

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6_workload_recovery | DER-01 rolling workload windows | derived_internal | Existing pitching game logs and completed-game windows | derivable | daily | corrected-after-final | Recompute from corrected final rows and preserve provenance metadata. | Missing games, stale sync, partial final rows, nullable pitch counts. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | Mark workload UNKNOWN when required final rows or pitch counts for pitch-based claims are missing. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` | 0B-06 |
| 6_workload_recovery | DER-02 days rest | derived_internal | Most recent final pitcher appearance date | derivable | daily | corrected-after-final | Recompute after corrected final appearance rows. | Missing last appearance, incomplete team coverage, date ambiguity. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | low | core | INTERNAL-ONLY | Mark rest UNKNOWN when last final appearance cannot be proven. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md` | 0B-06 |
| 6_workload_recovery | DER-03 back-to-back and dense usage | derived_internal | Final appearance dates over rolling windows | derivable | daily | corrected-after-final | Recompute from corrected final rows. | Missing completed games, doubleheader ambiguity, stale rows. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | Mark density UNKNOWN when any required window is incomplete. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` | 0B-06 |
| 16_team_bullpen_structure | DER-04 same-arm concentration | derived_internal | Recent pitcher-level workload grouped by team | derivable | daily | corrected-after-final | Recompute after corrected pitcher/team rows. | Incomplete team rows, pitcher-team assignment drift, stale snapshots. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | supporting | INTERNAL-ONLY | Mark concentration UNKNOWN when team coverage is incomplete. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md` | 0B-06 |
| 16_team_bullpen_structure | DER-05 bullpen workload distribution | derived_internal | Team bullpen appearance and workload distribution | derivable | daily | corrected-after-final | Recompute from corrected final rows and snapshots. | Missing reliever rows, starter/reliever classification ambiguity, incomplete team totals. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | Mark distribution UNKNOWN when bullpen population or team rows are incomplete. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md` | 0B-06 |
| 5_reliever_appearance | DER-06 appearance order | statsapi_v1 | Final boxscore pitcher order or final play-by-play after storage design | partial | at-final | corrected-after-final | Re-read final source after corrections and preserve source timestamp. | Pitcher order ambiguity, suspended/resumed games, missing final boxscore. | Source-dependent after 0C design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | Mark order UNKNOWN when final source order is absent or ambiguous. | FOUNDATION-0C | `docs/phase0b/02_statsapi_core.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 5_reliever_appearance | DER-07 entry and exit context | statsapi_v1 | Final play-by-play events and pitching changes after evidence design | partial | at-final | corrected-after-final | Recompute from corrected final play-by-play. | Missing event order, suspended/resumed ambiguity, schema drift, partial game feed. | Source-dependent after 0C and 0D design. | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | core | INTERNAL-ONLY | Mark entry/exit UNKNOWN unless final play-by-play can prove it. | EVIDENCE-0D | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 14_game_leverage_pressure | DER-08 inherited traffic context | statsapi_v1 | Final play-by-play base/out state and inherited-runner fields | partial | at-final | corrected-after-final | Recompute after corrected final play-by-play or audited boxscore fields. | Missing base/out state, missing runners, scoring corrections, event ambiguity. | Source-dependent after 0D design. | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | core | INTERNAL-ONLY | Mark traffic UNKNOWN when runners, outs, or entry state are missing. | EVIDENCE-0D | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 14_game_leverage_pressure | DER-09 save hold tie lead context | statsapi_v1 | Final boxscore scoring plus inning and score context | partial | at-final | corrected-after-final | Recompute after corrected final scoring and game context. | Missing score state, official scoring correction, non-final row, suspended game. | Source-dependent after 0C and 0D design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | Mark pressure label UNKNOWN when scoring or score context is incomplete. | EVIDENCE-0D | `docs/phase0b/02_statsapi_core.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 7_starter_rotation_exposure | DER-10 short-start pressure | derived_internal | Starter innings, outs, pitches where present, and bullpen follow-on workload | derivable | daily | corrected-after-final | Recompute from corrected final starter and bullpen rows. | Missing starter flag, incomplete team pitching rows, nullable pitch counts. | Stored completed-game history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | Mark short-start pressure UNKNOWN when starter or team bullpen rows are incomplete. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` | 0B-06 |
| 7_starter_rotation_exposure | DER-11 opener bulk piggyback indicators | derived_internal | Starter duration, reliever sequence, appearance length, and final game context | derivable | daily | corrected-after-final | Recompute after corrected final rows and entry order evidence. | Role ambiguity, appearance order missing, official intent unavailable. | Requires stored history plus 0D evidence design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | supporting | INTERNAL-ONLY | Mark role pattern UNKNOWN when sequence or usage pattern cannot be proven. | EVIDENCE-0D | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 16_team_bullpen_structure | DER-12 roster depth pressure | derived_internal | Public roster status and active bullpen population after 0C foundation | partial | daily | corrected-after-final | Recompute from refreshed roster and status evidence. | Stale roster, missing status, roster/source disagreement, depth ambiguity. | Source-dependent after 0C design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | Mark depth pressure UNKNOWN when roster status is missing, stale, or conflicting. | FOUNDATION-0C | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 16_team_bullpen_structure | DER-13 IL pressure | derived_internal | Public IL or roster-status evidence after 0C legal/source review | partial | daily | corrected-after-final | Recompute when public IL/status evidence changes. | Missing IL source, ambiguous status, absence mistaken as healthy, legal uncertainty. | Source-dependent after 0C design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | Mark IL pressure UNKNOWN when explicit public status evidence is absent or stale. | FOUNDATION-0C | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 16_team_bullpen_structure | DER-14 transaction churn | derived_internal | Public transactions after 0C transaction foundation | partial | daily | corrected-after-final | Recompute from corrected transaction history. | Ambiguous transaction text, missing effective date, roster disagreement, legal uncertainty. | Source-dependent after 0C design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | supporting | INTERNAL-ONLY | Mark churn UNKNOWN when transaction type, date, or roster impact is unclear. | FOUNDATION-0C | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 14_game_leverage_pressure | DER-15 internal pressure proxy | derived_internal | Final inning, score, outs, base state, inherited traffic, save/hold context | derivable | daily | corrected-after-final | Recompute from corrected final context and documented formula. | Missing context, formula drift, sample-size weakness, unsupported public framing. | Requires 0D evidence design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | core | INTERNAL-ONLY | Mark proxy UNKNOWN when any required final context is absent. | EVIDENCE-0D | `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 15_bullpen_role_intelligence | DER-16 inferred role usage | derived_internal | Usage pattern, pressure context, rest state, appearance sequence, and workload | derivable | daily | corrected-after-final | Recompute as corrected final usage and pressure evidence changes. | Manager-intent overclaim, role drift, sparse samples, missing pressure context. | Stored history plus 0D evidence design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | core | INTERNAL-ONLY | Mark role inference UNKNOWN when usage pattern or pressure evidence is insufficient. | EVIDENCE-0D | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 16_team_bullpen_structure | DER-17 team bullpen structure | derived_internal | Active roster, recent workload, handedness, role patterns, and depth context | derivable | daily | corrected-after-final | Recompute after roster, workload, and role evidence corrections. | Missing active roster, handedness unknown, incomplete role evidence, stale workload. | Requires 0C and 0D design for full structure. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | core | INTERNAL-ONLY | Mark team shape UNKNOWN when any required structure component is unsupported. | EVIDENCE-0D | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 17_schedule_calendar_context | DER-18 calendar rest context | derived_internal | Schedule, off days, doubleheaders, day/night sequence, postponed/makeup context | partial | daily | corrected-after-final | Recompute from corrected schedule status and game identity. | Postponed rows, suspended/resumed games, doubleheader ambiguity, missing schedule coverage. | Source-dependent after 0C design. | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | contextual | INTERNAL-ONLY | Mark calendar context UNKNOWN when schedule identity or status is ambiguous. | FOUNDATION-0C | `docs/phase0b/02_statsapi_core.md`; `docs/phase0b/03_statsapi_context.md` | 0B-06 |
| 18_historical_baselines | DER-19 trusted baseline comparisons | derived_internal | Trusted snapshots and comparable completed-game windows | derivable | daily | corrected-after-final | Recompute or suppress after corrected snapshots and coverage changes. | Partial snapshot, stale baseline, incompatible windows, correction mismatch. | Stored snapshot history only. | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | Withhold comparisons when either side is stale, partial, or incomparable. | AUDIT-ONLY-0B | `docs/phase0b/01_existing_foundation.md` | 0B-06 |
| 11_pitch_level_statcast | DER-20 pitch-level trend candidates | savant_statcast | Pitch-level trend evidence after legal/source review and storage design | partial | final+lag(observed) | corrected-after-final | Recompute from corrected pitch-level evidence if adopted. | Legal uncertainty, source terms, sample-size weakness, missing pitch rows, correction lag. | Source-dependent after later design. | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | supporting | INTERNAL-ONLY | Mark pitch-level trend UNKNOWN unless legal posture, sample minimums, and finality are satisfied. | EVIDENCE-0D | `docs/phase0b/04_pitch_level_feasibility.md` | 0B-06 |

## Public Language Guardrails

- Use "recent workload", "recent usage", "rest context", and "final
  completed-game evidence" only when supporting evidence is final and complete.
- Do not publish fatigue scores, pressure scores, trust scores, confidence
  scores, or hidden thresholds during Phase 0B.
- Do not say an arm is healthy, injury-free, available, unavailable, or being
  protected unless explicit public evidence supports that exact claim.
- Do not frame inferred role usage as manager intent.
- Do not frame an internal pressure proxy as official leverage, win
  probability, betting probability, odds, or projection.
- Do not use probable pitchers as evidence of what happened.
- Do not describe pitch mix, command, whiff, velocity, contact quality, or
  expected outcomes from current stored BaseballOS evidence.
- Do not compare today versus yesterday when snapshots or windows are partial,
  stale, incomparable, or correction-unsafe.

## Fail-Closed Rules

| condition | required behavior |
| --- | --- |
| Missing final game identity | Mark derived evidence UNKNOWN. |
| Game not finality-safe | Exclude from public and internal evidence except audit diagnostics. |
| Missing pitcher identity or team assignment | Mark pitcher-level and team-level derivations UNKNOWN. |
| Missing pitch count | Do not impute pitch burden; use innings/outs only if the claim allows it. |
| Missing innings or outs | Mark appearance burden UNKNOWN. |
| Incomplete rolling window | Mark window-based workload UNKNOWN. |
| Stale sync or stale snapshot | Withhold current-state and change reads. |
| Correction provenance unavailable | Withhold comparison and public evidence until provenance is restored. |
| Roster status missing, stale, or conflicting | Mark depth, IL, and active-status evidence UNKNOWN. |
| Transaction text ambiguous | Do not infer depth, injury, or role impact. |
| Final play-by-play missing | Mark entry/exit, traffic, and pressure context UNKNOWN. |
| Schedule identity ambiguous | Mark calendar and doubleheader context UNKNOWN. |
| Legal posture unresolved | Keep public display as INTERNAL-ONLY or UNKNOWN. |
| Evidence source not adopted | Do not use it in product claims. |
| Sample size below later threshold | Suppress trend or baseline comparison. |

## Key Findings

- BaseballOS can already derive a useful internal workload foundation from
  completed-game pitching logs: rest days, recent appearances, dense usage,
  pitches where present, innings, outs, and team workload concentration.
- The current stored foundation is not enough to safely publish clean-option,
  late-game margin, role-trust, inherited-traffic, leverage, IL/depth, or
  pitch-level reads without later foundation and evidence design.
- Final play-by-play is the key unlock for entry/exit context, inherited
  traffic, pressure proxies, clean/messy appearance reads, and role inference.
- Roster, IL, and transaction evidence must wait for 0C foundation and legal
  review before supporting depth-pressure claims.
- Pitch-level trends remain feasible only after legal/source review, storage
  design, sample-size thresholds, and public-language limits.
- Public product language must remain descriptive, evidence-backed, and
  unknown-safe.

## Decision

Phase 0B-06 classifies derived bullpen evidence as feasible in layers:

- `DERIVABLE-NOW`: completed-game workload, rest, dense usage, team
  concentration, short-start pressure from stored final rows, and trusted
  snapshot comparisons.
- `AFTER-0C`: roster/depth/IL/transaction foundation, active bullpen structure,
  batters faced, schedule calendar context, and stable source storage for
  context fields.
- `REQUIRES-0D`: final play-by-play appearance context, traffic context,
  transparent pressure proxy, role inference, clean-option reads, team shape,
  pitch-level trend usage, and public product thresholds.
- `INTERNAL-ONLY`: fatigue scoring, pressure scoring, role confidence, hidden
  thresholds, and decision support that is not ready for direct public display.
- `OUT-OF-SCOPE`: manager intent certainty, health certainty from absence,
  betting/odds/projection claims, unaudited role quotes, and official leverage
  claims without an adopted source.

No new data source is adopted in this branch. No derived evidence is approved
for public display in this branch. Phase 0B-07 should use this map to decide
source-acquisition priorities and the first 0C foundation work.
