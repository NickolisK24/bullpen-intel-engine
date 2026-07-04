# Phase 0B-04 - MLB Stats API Context Audit

Status: `AUDIT-ONLY-0B`

Categories covered:

- Category 4: Play-by-play / live feed data
- Category 8: Roster, eligibility, and depth context
- Category 9: Injuries and IL data
- Category 10: Transactions

This audit documents currently unused or underused MLB Stats API context
families that may support future BaseballOS bullpen intelligence. It does not
implement ingestion, schema, API, frontend, public copy, source adoption, or
production behavior.

## Scope Guardrails

- Documentation and probe evidence only.
- No production code behavior changes.
- No schema changes or migrations.
- No ingestion changes.
- No frontend changes.
- No leverage proxy design or implementation.
- No Statcast, Baseball Savant, FanGraphs, Baseball Reference, paid-source, or
  pitch-level feasibility decisions.
- Live/in-progress data is non-final by definition.
- Legal posture remains `needs-legal-review` unless later work cites terms,
  attribution requirements, storage rights, redistribution rights, and SLA.

## Evidence Method

Current repository usage was inspected before making source conclusions. Probe
evidence is dated, read-only, summary-only, and separated from interpretation.

| evidence type | path |
| --- | --- |
| Phase 0B framework | `docs/phase0b/README.md`; `docs/phase0b/templates/source_category_matrix.md`; `docs/phase0b/templates/probe_protocol.md` |
| Existing foundation inventory | `docs/phase0b/01_existing_foundation.md` |
| Stats API core audit | `docs/phase0b/02_statsapi_core.md` |
| Current Stats API client | `backend/services/mlb_api.py` |
| Completed-game context path | `backend/services/sync.py`; `backend/services/completed_game_context_payload_adapter.py`; `backend/services/completed_game_context_service.py` |
| Roster and team assignment paths | `backend/services/team_assignment_sync.py`; `backend/services/roster_status_sync.py`; `backend/services/roster_status.py`; `backend/services/roster_authority.py` |
| Injury and IL context paths | `backend/services/injury_il_context.py`; `backend/services/injury_context.py` |
| Transaction conflict tests | `backend/tests/test_roster_status.py`; `backend/tests/test_bullpen_stability.py` |
| Public wording guard tests | `backend/tests/test_tonight_candidate_selection.py`; `backend/tests/test_tonight_intelligence_service.py`; `backend/services/context_explanation_editorial_review.py` |
| Read-only probe record | `docs/phase0b/probes/statsapi_context/2026-07-04_statsapi_context_probe.md` |

## 1. Existing Repo Context Usage

| area | current behavior | evidence |
| --- | --- | --- |
| Client foundation | Current client defaults to `https://statsapi.mlb.com/api/v1`, uses a 10-second timeout, 3 retries, and retryable 429/5xx handling. The client comment describes Stats API as free/no-auth, but this audit does not treat that as a legal conclusion. | `backend/services/mlb_api.py:19-28`; `backend/services/mlb_api.py:66-75` |
| Current roster endpoint support | `get_team_roster` calls `/teams/{team_id}/roster` with `rosterType`, optional season/date, and optional hydrate. Current code names `active`, `40Man`, `fullRoster`, and `nonRosterInvitees` as roster views. | `backend/services/mlb_api.py:274-291`; `backend/services/roster_status_sync.py:26-36` |
| Current player/team assignment support | Team assignment sync builds a team roster index across roster types, falls back to `/people/{player_id}` currentTeam/status, and clears stale team assignment when authority is missing or ambiguous. | `backend/services/team_assignment_sync.py:178-300`; `backend/services/team_assignment_sync.py:314-347` |
| Current roster status support | Roster status sync merges active, 40-man, full-roster, and non-roster evidence. Active roster membership wins as `ACTIVE`; explicit status text can classify IL, optioned/minors, DFA, bereavement, paternity, suspended, restricted, or unknown. | `backend/services/roster_status_sync.py:188-229`; `backend/services/roster_status.py:15-82`; `backend/services/roster_status.py:248-289` |
| Current roster authority | Roster Authority owns the active/off-active/unknown predicates and canonical roster categories, including injured list, optioned/minors, 40-man not active, restricted/special list, non-roster depth, and unknown. | `backend/services/roster_authority.py:111-220` |
| Current injuries/IL usage | BaseballOS derives injury/IL context from current roster/status data only. It explicitly does not diagnose injuries, infer severity, predict return dates, scrape news, alter availability, or change workload scoring. | `backend/services/injury_context.py:1-6`; `backend/services/injury_context.py:67-81`; `backend/services/injury_il_context.py:117-122` |
| Current play-by-play usage | Completed-game context fetches linescore and play-by-play only after a completed-game path is already active. Raw responses are normalized transiently and never persisted. Missing context endpoints lower confidence instead of failing game-log refresh. | `backend/services/mlb_api.py:371-388`; `backend/services/sync.py:1247-1283`; `backend/services/sync.py:1297-1338` |
| Current play-by-play storage | The payload adapter keeps only normalized inning, half, cumulative score, and pitcher id. It fails closed when play fields are missing or cumulative score is non-monotonic. The service persists derived context only, never raw play-by-play. | `backend/services/completed_game_context_payload_adapter.py:139-184`; `backend/services/completed_game_context_payload_adapter.py:187-234`; `backend/services/completed_game_context_service.py:1-20`; `backend/services/completed_game_context_service.py:470-515` |
| Current live feed usage | No current client method calls `/api/v1.1/game/{gamePk}/feed/live`. Existing production code uses `/api/v1/game/{gamePk}/playByPlay`, `/linescore`, and `/boxscore` for completed-game context. | `backend/services/mlb_api.py:366-388`; repository search for `feed/live` in `backend/services` and `backend/tests` returned no production usage. |
| Current transaction usage | No current MLB API client method calls `/transactions`. Existing tests use historical `mlb_stats_api:transactions:*` source labels as stale-label fixtures, and assert current assignment/roster evidence overrides those labels. | `backend/tests/test_roster_status.py:93-130`; `backend/tests/test_roster_status.py:173-190`; `backend/tests/test_roster_status.py:237-255` |
| Current public transaction guard | Bullpen stability output is tested not to claim recall, option, DFA, or call-up language without a source. | `backend/tests/test_bullpen_stability.py:261-273` |
| Current public wording gaps | Existing Phase 0B inventory already flags health wording risk. Tonight public-copy tests ban `healthy` and `injury-free`; editorial review disclaimers state that readiness is not injury or medical information. | `docs/phase0b/01_existing_foundation.md:169-173`; `backend/tests/test_tonight_candidate_selection.py:35-41`; `backend/tests/test_tonight_intelligence_service.py:16-21`; `backend/services/context_explanation_editorial_review.py:151-156` |

### Current Gaps Between Available Context And Stored Data

| context family | available or observed context | currently stored or derived | gap |
| --- | --- | --- | --- |
| Final play-by-play | `allPlays`, at-bat index, inning/half, cumulative score, matchup pitcher/batter, runner events, pitch events. | Completed-game context stores derived team context only. | No raw play storage, no per-play table, no correction latency model, no public evidence design. |
| Live feed | `gameData`, `liveData`, live linescore, current offense/defense, boxscore, decisions, leaders, mound-visit key. | Not used in production. | Non-final and not approved for public evidence. |
| Roster snapshots | Active, 40-man, full roster, non-roster views; entry status, position, person identity. | Pitcher rows store team assignment, roster status, raw status code/description, source, and timestamps. | No explicit two-way player policy, no full depth history, no public roster-source legal clearance. |
| Injuries/IL | IL status can be represented through roster status and transaction text; direct injury endpoint was not confirmed by this probe. | Injury context counts IL and non-IL inactive bullpen arms from roster status. | No direct injury feed, no severity or return-date authority, no health clearance language. |
| Transactions | Transactions endpoint returned date, effective date, resolution date, type, person/team, and description. | No transaction ingestion or storage. | No parsing rules, no precedence rules beyond current tests, no latency/correction model. |

## 2. Play-By-Play / Live Feed Dossier

### Observed Source Shape

| source path | directly observed fields | derived candidates | public posture |
| --- | --- | --- | --- |
| `/api/v1/game/{gamePk}/playByPlay` on final game | `allPlays`, `currentPlay`, `scoringPlays`, `playsByInning`; complete plays had `result`, `about`, `count`, `matchup`, `runners`, and `playEvents`. | Pitcher changes, score at entry/exit, inning entry/exit, lead size, tie/lead context, late-game margin, clean inning vs traffic inning. | `INTERNAL-ONLY` until legal, correction, and evidence design are complete. |
| `/api/v1.1/game/{gamePk}/feed/live` on final game | `gameData` and `liveData`; live data included `plays`, `linescore`, `boxscore`, `decisions`, and `leaders`; game data included `moundVisits`. | Same as final play-by-play plus broader game metadata. | `INTERNAL-ONLY` for final rows; no adoption decision here. |
| `/api/v1.1/game/{gamePk}/feed/live` on in-progress game | Status was `Live` / `In Progress`; live linescore included current inning, balls, strikes, outs, offense, and defense; boxscore pitcher lists were partial at probe time. | Real-time state only; could support future internal monitors if finality rules exist. | `NEVER` for public evidence in Phase 0B-04 posture. |

### Directly Available Vs Derivable

| topic | source status | 0B-04 assessment |
| --- | --- | --- |
| Play sequence | Directly available in final `allPlays`. | Candidate for later Phase 0D evidence design. |
| At-bat sequence | Directly available via `atBatIndex` and play order. | Candidate after correction and lifecycle testing. |
| Pitch sequence availability | Pitch events were observed inside `playEvents`. | Audit only here; pitch-level feasibility belongs to 0B-05. |
| Pitcher changes | Derivable from changes in `matchup.pitcher.id` and inning/half. | Must fail closed when pitcher identity is missing, duplicated, or out of order. |
| Substitutions | Potentially represented through action events, but not validated in this probe. | UNKNOWN until a substitution-focused probe is done. |
| Mound visits | `gameData.moundVisits` key observed in live feed. | UNKNOWN for completeness and public relevance. |
| Inning entry/exit | Derivable from play order, inning/half, and pitcher changes. | Candidate only after suspended/resumed and extra-inning cases are tested. |
| Score at entry/exit | Cumulative `result.awayScore` and `result.homeScore` were observed. | Candidate; existing completed-game context already derives score state conservatively. |
| Base-out state at entry/exit | Live feed exposed balls/strikes/outs and offense/defense; play data includes count and runners. | Derivable but not yet proven deterministic across all game types. |
| Runners inherited / inherited runners scored | Boxscore can expose inherited-runner fields; play/runners data may allow reconstruction. | Candidate for Phase 0D only; do not claim until deterministic reconstruction and correction behavior are proven. |
| Save, hold, tie, and lead-size context | Lead size and tie state are derivable from score and inning; official saves/holds are boxscore outcomes. | Needs evidence design and correction propagation before public use. |
| Extra innings / ghost runner | Not observed in this probe. | UNKNOWN. |
| Leverage proxy inputs | Some inputs exist, but this branch does not design a proxy. | Out of scope for implementation; inputs remain audit-only. |

### Play-By-Play Safety Conclusion

Final play-by-play appears strong enough for later internal evidence design
around bullpen entry state, pitcher-change sequence, and inherited traffic. It
is not approved for new ingestion or public display here. Live and in-progress
feeds are non-final and must not power public claims. They should remain
`NEVER` for public display unless a later phase proves finality, correction,
staleness, legal, and product-language safety.

## 3. Roster, Eligibility, And Depth Dossier

### Current And Candidate Roster Context

| roster topic | current support | 0B-04 assessment |
| --- | --- | --- |
| Active MLB roster / 26-man roster | Active roster endpoint is already used as authoritative active membership. Probe observed 26 active rows for team 147 on 2026-07-04. | Strong candidate for Phase 0C foundation work, still `INTERNAL-ONLY` pending legal/source review. |
| 40-man roster | Current sync uses `40Man`; probe observed a 40-man response with 41 rows. | Useful for depth context, but not active bullpen availability. |
| Full roster / minors | Current sync uses `fullRoster` and maps full-roster-only evidence to minors. Probe observed 284 rows. | Useful for depth and not-currently-MLB-bullpen context; public wording must avoid overclaiming proximity. |
| Non-roster invitees | Current sync supports `nonRosterInvitees`. | Contextual depth only; not current active roster evidence. |
| Player position eligibility | Roster entries expose position and hydrated person primary position. | Supports pitcher-vs-non-pitcher filtering, but role authority still needs BaseballOS role logic. |
| Active vs inactive status | Current code normalizes active, IL, minors, optioned, DFA, 40-man-only, bereavement, paternity, suspended, restricted, non-roster, and unknown. | Strong current-state foundation, but legal/source review remains open. |
| Two-way players | No explicit 0B-04 source decision exists. | Treat as a source/context ambiguity. Do not infer bullpen role from position alone; require pitching evidence or role authority. |
| Rehab assignment context | `fullRoster` and transaction descriptions may expose rehab context. | UNKNOWN for consistency and legal posture. |
| Roster churn | Transactions can explain churn; roster snapshots show current state. | Current-state authority should remain roster snapshot first. |

### Later Vocabulary BaseballOS Can Support

The audited sources and existing authority model can support these future
vocabulary buckets after legal/source review and product copy review:

- `active`
- `not on active roster`
- `depth`
- `not currently in MLB bullpen`
- `unknown`

The sources should not support these claims without more evidence:

- A player is healthy.
- A bullpen is injury-free.
- No one is hurt.
- A player is available to pitch because no public IL flag exists.
- A manager intends to use a player.
- A depth player is about to be recalled.

## 4. Injuries / IL Dossier

BaseballOS currently has an IL and inactive-roster foundation through roster
status. It does not have direct injury ingestion, medical context, severity,
return timeline, or private availability context.

| injury / IL topic | current or observed support | 0B-04 posture |
| --- | --- | --- |
| 10-day IL, 15-day IL, 60-day IL | Current roster-status normalization supports `IL_10`, `IL_15`, and `IL_60`. Transactions probe observed an IL transfer row. | Candidate for later public roster-fact language only after legal/source review. |
| 7-day IL | Not currently represented as a dedicated normalized status in `roster_status.py`; not confirmed by this probe. | UNKNOWN. Add only after source shape is observed and classified. |
| IL activations | Transaction endpoint can expose activation-style descriptions; current tests use stale activated labels to prove roster snapshots override them. | Explanatory only; current-state authority remains roster snapshot. |
| Retroactive IL dates | Not confirmed in this probe. | UNKNOWN. |
| Public injury descriptions | Transaction descriptions can include public injury text. Direct injury endpoint candidate returned HTTP 404. | High copy/legal risk. Do not expose raw descriptions without legal and editorial review. |
| Rehab assignment signals | May appear in roster or transaction context but was not validated. | UNKNOWN. |
| Replacement burden / IL depth pressure | Derivable from roster status, bullpen role filtering, and active/inactive counts. | Internal candidate; public language must say roster/IL facts, not health conclusions. |

### Required Injury/Health Wording Guardrail

BaseballOS may later say public roster/IL facts such as:

- "on IL"
- "activated"
- "no public IL flag found"
- "not on active roster"
- "currently unavailable by public roster/IL status"

BaseballOS must not say:

- "healthy"
- "injury-free"
- "nobody is hurt"
- "fully healthy bullpen"

Absence of a public IL or injury flag is absence of a public flag, not proof of health.
Public copy must never turn missing IL data into medical clearance.

## 5. Transactions Dossier

The Stats API transactions endpoint was observed as available for a date range
probe and returned rows with date, effective date, resolution date, person/team,
type code, type description, and free-text description. BaseballOS does not
currently ingest transactions.

| transaction topic | observed or current support | 0B-04 assessment |
| --- | --- | --- |
| Endpoint availability | Probe returned 1,556 rows for 2026-06-01 through 2026-07-04. | Available for audit; legal/source review still required. |
| Date/effective/resolution dates | Observed keys include `date`, `effectiveDate`, and `resolutionDate`. | Candidate for later historical context if missing dates fail closed. |
| Recall/option | Endpoint likely contains transaction types/descriptions; current tests model transaction labels. | Do not parse free text into product claims until type taxonomy is audited. |
| IL moves / activations | Probe sample included an IL transfer; activation language is represented in current stale-label tests. | Explanatory only; current roster snapshot decides current state. |
| Trades, DFA, outright, release, contract selection | Likely covered by transactions feed but not individually probed here. | UNKNOWN until type-specific probe rows are collected. |
| Roster churn | Transactions can explain recent additions/removals. | Candidate for later internal context, not current public evidence. |
| Latency vs roster snapshot | Not measured. | UNKNOWN. |
| Free-text parsing | Descriptions can include injury wording, transaction semantics, and abbreviations. | High risk. Prefer typed fields; fail closed on ambiguous text. |

### Recommended Precedence Rule

When transactions and roster snapshots disagree, the current roster snapshot
should be treated as the current-state authority for "active", "not on active
roster", and "unknown". Transactions should be historical or explanatory
evidence only after the event type, effective date, player identity, and team
identity align with roster evidence. If they conflict or dates are missing,
mark the explanatory claim UNKNOWN and do not use the transaction to override
current roster status.

This recommendation matches existing roster-status behavior: current assignment
and roster-sync evidence override stale transaction labels, and unresolved
current assignment does not fall back to stale active labels.

## 6. Source Category Matrix Rows

These rows follow `docs/phase0b/templates/source_category_matrix.md`. They are
audit rows only. `public_display` remains `INTERNAL-ONLY` or `NEVER` because
legal, source, finality, correction, and product-display decisions are not made
in this branch.

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4_play_by_play_live_feed | final_play_by_play_sequence | statsapi_v1 | `/game/{gamePk}/playByPlay` | available | at-final | corrected-after-final | final play rows may be corrected; derived context must be regenerated from source | missing allPlays, incomplete plays, non-monotonic score, game not final | by gamePk when endpoint returns | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | omit play-derived evidence unless final schedule status and usable allPlays are present | EVIDENCE-0D | `docs/phase0b/probes/statsapi_context/2026-07-04_statsapi_context_probe.md`; `backend/services/completed_game_context_payload_adapter.py:139-184` | 0B-04 |
| 4_play_by_play_live_feed | live_in_progress_feed | statsapi_v11_live | `/game/{gamePk}/feed/live` | available | live | no(live) | live rows can change before final and may be partial | live status, stale feed, partial boxscore, current play changing, endpoint timeout | point-in-time only | needs-legal-review | TBD | do-not-store | B | high | contextual | NEVER | never use live or in-progress data for public evidence | DO-NOT-USE | `docs/phase0b/probes/statsapi_context/2026-07-04_statsapi_context_probe.md` | 0B-04 |
| 4_play_by_play_live_feed | pitcher_changes | statsapi_v1 | `/game/{gamePk}/playByPlay` matchup pitcher sequence | derivable | at-final | corrected-after-final | pitcher sequence must be recomputed after source correction | missing pitcher id, unordered plays, scorer correction, suspended/resumed game | by final gamePk when play order is usable | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | mark pitcher-change context UNKNOWN when sequence is ambiguous | EVIDENCE-0D | `backend/services/completed_game_context_payload_adapter.py:176-182`; probe record | 0B-04 |
| 4_play_by_play_live_feed | inning_score_base_out_context | statsapi_v11_live | `feed/live` linescore plus plays | partial | live | no(live) | live count/base/out state can change before final | missing outs, missing runners, partial inning, live correction | point-in-time only until final cases are audited | needs-legal-review | TBD | do-not-store | B | high | core | NEVER | do not publish live base-out or score-state evidence | DO-NOT-USE | `docs/phase0b/probes/statsapi_context/2026-07-04_statsapi_context_probe.md` | 0B-04 |
| 4_play_by_play_live_feed | inherited_runner_context | derived_internal | final plays plus boxscore inherited-runner fields | derivable | at-final | corrected-after-final | derived values must refresh after play or boxscore corrections | ambiguous runner state, missing pitcher change, missing inherited-runner fields | UNKNOWN until multi-game probe and correction tests | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | high | core | INTERNAL-ONLY | mark UNKNOWN unless runner ownership and scoring can be reconstructed deterministically | EVIDENCE-0D | `docs/phase0b/02_statsapi_core.md`; probe record | 0B-04 |
| 4_play_by_play_live_feed | save_hold_tie_lead_size_context | derived_internal | final score state, inning, boxscore outcomes | derivable | at-final | corrected-after-final | derived lead/tie context and boxscore outcomes must be correction-aware | missing score, official hold/save corrections, non-final game, extra-inning ambiguity | stored completed games only after design | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | supporting | INTERNAL-ONLY | suppress claim when final score state or official outcome is missing | EVIDENCE-0D | `backend/services/completed_game_context_service.py:1-20`; `docs/phase0b/02_statsapi_core.md` | 0B-04 |
| 4_play_by_play_live_feed | substitutions_mound_visits | statsapi_v11_live | `feed/live` gameData and play action events | partial | live | no(live) | unknown until event completeness is proven | missing action events, incomplete mound-visit semantics, scorer changes | UNKNOWN | needs-legal-review | TBD | do-not-store | UNVERIFIED | high | contextual | NEVER | do not expose substitutions or mound visits until event taxonomy is audited | AUDIT-ONLY-0B | probe record | 0B-04 |
| 8_roster_eligibility_depth | active_roster | statsapi_v1 | `/teams/{teamId}/roster?rosterType=active` | available | daily | UNKNOWN | roster snapshots can change after transaction corrections | missing roster, stale roster, endpoint timeout, player id missing | current snapshot; historical only if date is requested and retained | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | mark roster state UNKNOWN if active roster cannot be fetched or matched | FOUNDATION-0C | `backend/services/roster_status_sync.py:188-229`; probe record | 0B-04 |
| 8_roster_eligibility_depth | forty_man_roster | statsapi_v1 | `/teams/{teamId}/roster?rosterType=40Man` | available | daily | UNKNOWN | roster snapshots can change after transaction corrections | stale roster, partial team roster, status mismatch | current snapshot; date support requires source review | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | classify as depth only, never active availability | FOUNDATION-0C | `backend/services/roster_status_sync.py:26-36`; probe record | 0B-04 |
| 8_roster_eligibility_depth | full_roster_minor_depth | statsapi_v1 | `/teams/{teamId}/roster?rosterType=fullRoster` | available | daily | UNKNOWN | roster snapshots can change after transaction corrections | minor-league depth ambiguity, huge roster size, player mismatch | current snapshot; historical retention not designed | needs-legal-review | TBD | raw-cache-risk | B | medium | contextual | INTERNAL-ONLY | use as not-currently-MLB-bullpen depth only unless active roster evidence exists | FOUNDATION-0C | `backend/services/roster_status_sync.py:223-229`; probe record | 0B-04 |
| 8_roster_eligibility_depth | non_roster_depth | statsapi_v1 | `/teams/{teamId}/roster?rosterType=nonRosterInvitees` | available | daily | UNKNOWN | roster snapshots can change after transaction corrections | NRI semantics, seasonal availability, source gaps | current snapshot only | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | medium | contextual | INTERNAL-ONLY | classify as depth only, not active bullpen | FOUNDATION-0C | `backend/services/roster_status_sync.py:26-36`; `backend/services/roster_status.py:189-197` | 0B-04 |
| 8_roster_eligibility_depth | player_position_eligibility | statsapi_v1 | roster entry `position`; hydrated person `primaryPosition` | available | daily | UNKNOWN | position can change or be incomplete | two-way ambiguity, non-pitcher on roster, missing primary position | current snapshot only | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | do not treat position alone as bullpen role authority | FOUNDATION-0C | `backend/services/roster_status_sync.py:97-106`; probe record | 0B-04 |
| 8_roster_eligibility_depth | two_way_player_context | derived_internal | roster position plus pitching evidence and role authority | partial | daily | UNKNOWN | role must refresh when pitching evidence or roster status changes | position ambiguity, no pitching logs, starter/reliever ambiguity | UNKNOWN | needs-legal-review | TBD | derived-aggregate-ok | UNVERIFIED | medium | supporting | INTERNAL-ONLY | mark role UNKNOWN unless BaseballOS role authority has evidence | AUDIT-ONLY-0B | `backend/services/injury_context.py:290-316`; `backend/services/roster_authority.py:27-31` | 0B-04 |
| 8_roster_eligibility_depth | roster_status_active_inactive_fields | statsapi_v1 | roster entry status plus person status fields | available | daily | UNKNOWN | raw status text can change; current assignment should override stale labels | unknown status code, stale transaction label, unresolved current team | current snapshot with stored source and timestamp | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | classify UNKNOWN when status cannot be normalized or assignment is unresolved | FOUNDATION-0C | `backend/services/roster_status.py:508-586`; `backend/tests/test_roster_status.py:237-255` | 0B-04 |
| 10_transactions | transaction_events | statsapi_v1 | `/transactions?sportId=1&startDate=&endDate=` | available | daily | corrected-after-final | transaction feed may correct dates, descriptions, or resolution | missing effective date, text ambiguity, team mismatch, endpoint timeout | available by queried date range in probe | needs-legal-review | TBD | raw-cache-risk | B | high | contextual | INTERNAL-ONLY | use transactions as explanation only after typed fields and dates align | LATER-V4 | probe record; `backend/tests/test_bullpen_stability.py:261-273` | 0B-04 |
| 10_transactions | recall_option_events | statsapi_v1 | transaction type and description | partial | daily | corrected-after-final | event text/type may change | free-text parsing, missing player, missing effective date, roster disagreement | UNKNOWN until type taxonomy audit | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | supporting | INTERNAL-ONLY | mark UNKNOWN when event type or roster snapshot does not align | LATER-V4 | probe record; `backend/tests/test_roster_status.py:93-130` | 0B-04 |
| 9_injuries_il | il_placements_activations | statsapi_v1 | roster status plus transaction type/description | partial | daily | corrected-after-final | IL transaction and roster state may correct after publication | missing IL status, stale transaction, missing activation date, 7-day IL unknown | current roster status plus queried transactions | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | say only roster/IL facts; mark UNKNOWN on conflict or missing date | FOUNDATION-0C | `backend/services/roster_status.py:128-158`; probe record | 0B-04 |
| 9_injuries_il | public_injury_descriptions | statsapi_v1 | transaction description text | partial | daily | corrected-after-final | descriptions can change or be legally sensitive | medical overclaim, raw text parsing, missing source terms | point-in-time transaction text | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | contextual | INTERNAL-ONLY | do not expose raw descriptions without legal and editorial approval | UNKNOWN-UNTIL-LEGAL | probe record; `backend/services/injury_context.py:1-6` | 0B-04 |
| 9_injuries_il | rehab_return_signals | statsapi_v1 | transaction descriptions and roster assignment | partial | daily | corrected-after-final | rehab/return labels may lag active roster | ambiguous rehab text, minor-league assignment ambiguity, no activation row | UNKNOWN | needs-legal-review | TBD | raw-cache-risk | UNVERIFIED | high | supporting | INTERNAL-ONLY | mark UNKNOWN unless typed event, date, and roster snapshot agree | LATER-V4 | probe record | 0B-04 |
| 8_9_10_context_conflict | roster_transaction_disagreement_behavior | derived_internal | current roster snapshot compared with transaction history | derivable | daily | UNKNOWN | conflict resolution must recompute when either source updates | stale transaction, missing roster, missing player id, ambiguous team | not stored today | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | current roster snapshot decides state; conflicting transaction explanation becomes UNKNOWN | FOUNDATION-0C | `backend/services/roster_status.py:508-547`; `backend/tests/test_roster_status.py:113-130`; `backend/tests/test_roster_status.py:173-190` | 0B-04 |

## 7. Fail-Closed Rules For Context Data

| condition | fail-closed behavior |
| --- | --- |
| Missing play-by-play | Do not derive play-level bullpen evidence. Degrade to linescore or boxscore context only when those inputs are safe. |
| Live or non-final feed | Never publish as evidence. Treat as `NEVER` public display until finality and correction safety are proven. |
| Ambiguous pitcher change | Mark pitcher-change, entry/exit, inherited-runner, and score-at-entry context UNKNOWN. |
| Ambiguous inherited-runner reconstruction | Do not infer inherited traffic, inherited runners scored, clean inning, or damage timing. |
| Missing roster | Mark current roster state UNKNOWN and do not infer active bullpen membership from workload history. |
| Stale roster | Do not treat stale roster state as current; require source timestamp and current assignment evidence. |
| Roster/transaction disagreement | Current roster snapshot remains current-state authority; transaction explanation is UNKNOWN unless dates and identities align. |
| Unknown player status | Classify as `UNKNOWN`; do not upgrade from local active flag, workload evidence, or stale transaction text. |
| Missing IL data | Say no public IL flag was found only if the query itself is trusted; never say healthy. |
| Absence of injury flag | Treat as absence of a public flag, not proof of health. |
| Ambiguous transaction text | Do not parse into recall, option, IL, activation, DFA, trade, release, or health claims. |
| Missing effective date | Do not use the transaction for current-state or recent-change claims. |
| Endpoint timeout or error | Preserve prior trusted state only if existing product guardrails allow it; otherwise mark context UNKNOWN or unavailable. |
| Schema drift or unknown field shape | Drop the affected context family and keep public display withheld. |

## 8. Findings And Recommendations

### Strong Enough For Future Phase 0C Foundation Work

- Active roster, 40-man roster, full-roster depth, and roster status fields are
  the strongest candidates because BaseballOS already has guarded sync,
  classification, source timestamps, and fail-closed unknown handling.
- Current assignment before roster status is the right foundation order. It
  prevents stale local team labels or stale transaction labels from claiming a
  player is active.
- Roster Authority should remain the owner of active, off-active, and unknown
  predicates.

### Should Remain Internal-Only

- Final play-by-play and final live-feed context should remain `INTERNAL-ONLY`
  until legal posture, correction latency, schema stability, suspended/resumed
  cases, extra innings, and public evidence wording are reviewed.
- Transactions should remain explanatory only. They are useful for roster churn
  and IL-change context, but text parsing and timing disagreements are too risky
  for current public claims.
- Public injury descriptions should remain internal and audit-only until legal
  and editorial review explicitly approve storage and display.

### Should Be Never-Public In This Posture

- Live/in-progress feed evidence.
- Live base-out state, current play state, partial boxscore pitcher lists, or
  any real-time bullpen inference from non-final feed data.

### Should Wait For Phase 0D Evidence Design

- Inherited-runner reconstruction.
- Clean inning vs traffic inning.
- Score at bullpen entry/exit as public evidence.
- Save/hold/tie/lead-size context beyond already stored final boxscore facts.
- Any leverage-proxy input design.

### Should Wait For Legal/Source Review

- Terms, attribution, storage, redistribution, and SLA for all Stats API context
  families.
- Raw transaction descriptions and public injury descriptions.
- Whether final play-by-play or live-feed JSON can be stored, cached, or
  redistributed.

### Remains UNKNOWN

- Direct injury endpoint shape; the tested `/api/v1/injuries` path returned 404.
- 7-day IL representation in current source shape.
- Retroactive IL date availability and consistency.
- Rehab assignment and return-signal consistency.
- Exact correction latency for final play-by-play and transactions.
- Completeness of substitutions and mound visits for bullpen evidence.
- Ghost runner and extra-inning representation across seasons.

## 9. Phase 0B-04 Decision

Stats API roster context is suitable for continued guarded internal use and
later Phase 0C foundation planning, subject to legal/source review. Final
play-by-play appears promising for later Phase 0D evidence design, but it is not
approved here for new ingestion or public evidence. Transactions and IL context
are useful audit candidates, but current roster snapshots should remain the
current-state authority when they disagree with transaction history.

The core product guardrail for all later work is that BaseballOS can describe
public roster and IL facts, but it cannot convert missing public injury evidence
into health claims.
