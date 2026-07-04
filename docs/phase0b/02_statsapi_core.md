# Phase 0B-03 - MLB Stats API Core Audit

Status: `AUDIT-ONLY-0B`

Categories covered:

- Category 2: MLB Stats API foundation
- Category 3: Boxscore data
- Category 17 source-fact subset: schedule and calendar facts directly
  observable from Stats API core

This audit documents current BaseballOS MLB Stats API usage and read-only probe
evidence for core schedule and boxscore behavior. It does not implement
ingestion, schema, API, UI, public copy, source adoption, or production behavior.

## Scope Guardrails

- Documentation and probe evidence only.
- No production code behavior changes.
- No schema changes or migrations.
- No ingestion changes.
- No frontend changes.
- No play-by-play, transactions, IL, injury, roster-depth, Statcast, pitch-level,
  paid-source, or derived evidence design decisions.
- Probable pitchers are schedule context only. They are not evidence of what
  happened.
- Legal posture remains `needs-legal-review` unless later work cites terms,
  attribution, storage, and public-display rights.

## Evidence

| evidence type | path |
| --- | --- |
| Phase 0B framework | `docs/phase0b/README.md`; `docs/phase0b/templates/source_category_matrix.md`; `docs/phase0b/templates/probe_protocol.md` |
| Existing foundation inventory | `docs/phase0b/01_existing_foundation.md` |
| Current client and config | `backend/services/mlb_api.py`; `backend/config.py` |
| Current schedule ingestion | `backend/services/schedule_ingestion.py`; `backend/models/scheduled_game.py`; `backend/tests/test_schedule_ingestion.py` |
| Current postgame/boxscore ingestion | `backend/services/sync.py`; `backend/models/game_log.py`; `backend/tests/test_postgame_refresh.py`; `backend/tests/test_postgame_marker_lifecycle.py`; `backend/tests/test_stat_correction_propagation.py` |
| Current slate completeness behavior | `backend/services/slate_coverage.py`; `backend/tests/test_slate_coverage.py` |
| Read-only probe record | `docs/phase0b/probes/statsapi_core/2026-07-04_statsapi_core_probe.md` |

## 1. Current Stats API Client Foundation

| area | current behavior | evidence |
| --- | --- | --- |
| Base URL | Default base URL is `https://statsapi.mlb.com/api/v1`, overridable by `MLB_API_BASE`. | `backend/services/mlb_api.py:19`; `backend/config.py:112` |
| Auth posture | Current client comments describe the source as free and no-auth, with a docs URL. This audit does not treat that as a legal conclusion. | `backend/services/mlb_api.py:66-75` |
| User agent | Client sends `BaseballOS/1.0 (Portfolio Analytics Tool)`. | `backend/services/mlb_api.py:78-83` |
| Timeout and retries | Default timeout is 10 seconds, max retries 3, exponential backoff base 1.0, cap 30.0, jitter enabled. Retryable statuses are 429 and 5xx. Other 4xx responses are not retried. | `backend/services/mlb_api.py:20-28`; `backend/services/mlb_api.py:94-263`; `backend/config.py:120-128`; `backend/tests/test_mlb_api_client.py:72-203` |
| Endpoint methods | Current methods cover teams, rosters, pitcher game logs, player info, aggregate pitching stats, schedule, recent schedule, game boxscore, linescore, play-by-play, and extracted game pitching lines. | `backend/services/mlb_api.py:267-416` |
| Current schedule usage | `get_schedule` calls `/schedule` with `sportId=1` and `hydrate=team`; schedule ingestion stores durable schedule facts only. | `backend/services/mlb_api.py:341-358`; `backend/services/schedule_ingestion.py:1-45` |
| Current boxscore usage | Postgame refresh fetches `/game/{gamePk}/boxscore` only for games treated as completed; daily ingest may also fetch extracted pitching lines for leverage-index backfill after a new log insert. | `backend/services/mlb_api.py:366-416`; `backend/services/sync.py:1138-1244`; `backend/services/sync.py:1734-1750` |
| Current pitching-line usage | Pitching lines are extracted from `teams.home/away.pitchers` and `teams.home/away.players.ID{player_id}.stats.pitching`; players with pitching stats outside the pitcher list are also considered. | `backend/services/sync.py:852-902` |
| Current finality assumption | Daily and postgame ingestion both require completed-game status before storing completed-game logs. | `backend/services/sync.py:128-156`; `backend/services/sync.py:1696-1724`; `backend/tests/test_unknown_safe_ingestion.py:92-124` |

## 2. Existing Storage Compared With Available Core Fields

| group | currently stored | observed available but not currently stored | notes |
| --- | --- | --- | --- |
| Schedule identity | `game_pk`, `team_id`, opponent team id, home/away side | venue id/name, team abbreviation/name fields from hydrated team objects | Current table intentionally stores one row per team/game. Evidence: `backend/models/scheduled_game.py:5-68`. |
| Schedule dates | `game_date` from `officialDate` with `gameDate` fallback; `game_datetime` as naive UTC | date bucket from schedule response, timezone detail not observed in current schedule probe | Product day should prefer `officialDate`, but postponed rows can shift official date away from the queried date bucket. |
| Schedule status | raw `statusCode`; normalized `status_state` | `abstractGameState`, `codedGameState`, `detailedState`, `abstractGameCode`, `reason`, `rescheduleDate`, `resumedFrom`, `resumedFromDate` | Current schedule ingestion preserves raw status code but not all status fields. |
| Doubleheader/series | `doubleheader`, `gameNumber`, `seriesGameNumber`, `gamesInSeries` | date-bucket relation and reschedule linkage beyond these fields | Doubleheaders count as separate game rows when game pks differ. |
| Probable pitchers | not stored | `teams.home.probablePitcher`, `teams.away.probablePitcher` when hydrated | Forward-looking schedule context only. Never evidence of actual usage. |
| Boxscore pitcher identity | pitcher/player id, name, team id/name/abbreviation during extraction; stored logs link to local `Pitcher` | `boxscoreName`, position code/name/type, side/order | Current resolver can create/reactivate pitchers from authoritative final boxscore lines. |
| Boxscore workload | innings pitched, outs, pitch count from `numberOfPitches`, strikes | `outs`, `pitchesThrown`, `balls`, `battersFaced`, `summary` | `outs` and `pitchesThrown` are available but current code derives outs from innings and uses `numberOfPitches`. |
| Boxscore outcomes | hits, runs, earned runs, walks, strikeouts, home runs, holds, saves, blown saves, wins, losses, save opportunities | games finished, inherited runners, inherited runners scored, hit batsmen, wild pitches, balks | Some fields may matter later but require schema and correction propagation. |
| Team pitching totals | not stored | team totals for pitches, strikes, batters faced, runs, earned runs, innings, outs, WHIP, ERA, pitches per inning | Candidate for aggregate evidence only after schema, correction, and public-display review. |
| Non-final boxscores | not used as completed-game evidence | in-progress boxscores can return partial pitching lists | Must remain excluded from completed-game evidence. Probe observed partial in-progress boxscore shape. |

## 3. Schedule Endpoint Dossier

| field group | observed/repo behavior | classification |
| --- | --- | --- |
| `gamePk` / game ID | Present on usable schedule rows and used as the durable game id. Current ingestion skips rows missing `gamePk`. Probe observed the same `gamePk` on a postponed row and its rescheduled final row. | Available, but product-day/status must be interpreted with the row status. |
| `officialDate` | Current parser prefers `officialDate` for stored `game_date`. Probe observed postponed row queried in one date bucket with a later `officialDate`. | Available and product-day relevant, but reschedule behavior creates denominator risk. |
| `gameDate` | Current parser stores UTC start time as `game_datetime`; falls back to first 10 chars for date only if `officialDate` is absent. | Available. Use as timestamp, not product-day authority by itself. |
| Team identifiers | Current parser stores home/away team ids from `teams.home.team.id` and `teams.away.team.id`. | Available and already stored. |
| Venue fields | Probe observed venue id/name/link on schedule. Timezone was not observed in the schedule probe. | Partial. Venue id/name are available; timezone remains `UNKNOWN` from this branch's probe. |
| Game type | Current code stores `gameType`; comments list examples such as regular season, spring training, and postseason. Probe observed `R` and `S`. | Available. Future public evidence should explicitly filter game types. |
| Season filtering | Current client schedule method accepts date range, not season-only filtering. Probe used date windows. | Available by date range; season behavior not fully audited. |
| Schedule hydration | Current repo uses `hydrate=team`. Probe used `hydrate=team,venue,probablePitcher` and observed probable pitchers. | Available, but current app stores only team-derived schedule facts. |
| Probable pitchers | Probe observed probable pitcher id/name/link on schedule rows, including a final historical row. | Partial and forward-looking only; not happened evidence. |
| Actual starters | Boxscore pitching lines expose `gamesStarted`; current code also falls back to first pitcher order when missing. | Available from boxscore/game logs, not schedule-only proof. |
| Doubleheader indicators | Current storage preserves `doubleHeader`, `gameNumber`, `seriesGameNumber`, `gamesInSeries`; tests show doubleheader games stay separate by `gamePk`. Probe observed `doubleHeader=S` and separate game numbers. | Available and already partially stored. |
| Postponed indicators | Current schedule ingestion checks `detailedState` for postponed before final. Probe observed `statusCode=DR`, `detailedState=Postponed`, `reason=Rain`, and `rescheduleDate`. | Available, but raw finality helper has an ambiguity risk if it trusts `abstractGameState=Final`. |
| Suspended/resumed indicators | Current schedule ingestion maps `detailedState` containing suspended to `suspended`. Probe observed final games with `resumedFrom` and `resumedFromDate`; those fields are not stored. | Partial. Treat as first-class slate risk until stored and tested. |
| Final/completed status | Current final status constants are `F`, `O`, `FR`, and `FT`; detailed states include final, game over, completed early, final: tied. | Available but must be interpreted with postponed/suspended precedence. |
| `abstractGameState` | Current `is_completed_game` accepts `abstractGameState=final`. Probe observed a postponed row with `abstractGameState=Final`. | Unsafe alone. Do not use as sole finality authority. |
| `detailedState` | Current schedule ingestion uses detailed postponed/suspended/cancelled checks before final. | Stronger than abstract alone, but still source-specific. |
| `statusCode` | Current code treats selected status codes as final and preserves raw code in schedule rows. Probe observed `DR` for postponed. | Useful with precedence rules. |

## 4. Game Status Lifecycle And Finality Authority

Current BaseballOS finality handling:

- `sync.is_completed_game` returns true when `gamePk` exists and any of these
  are true: final status code, `abstractGameState=final`, detailed state in the
  final set, or detailed state starts with final.
- Schedule ingestion normalizes status more conservatively: postponed,
  suspended, and cancelled checks run before final checks.
- Daily game-log ingestion skips non-final and statusless splits.
- Postgame refresh fetches boxscores only for games treated as completed.
- Slate coverage is not complete enough to publish when final games lack fully
  processed markers, when markers are incomplete/failed, or when suspended games
  are not final.

Finality classification for future audits:

| source signal | safe as finality authority? | reason |
| --- | --- | --- |
| `gamePk` | no | Identity only; does not prove the game happened. |
| `abstractGameState=Final` | no | Probe observed it on a postponed row. |
| `statusCode` in `F`, `O`, `FR`, `FT` | partial | Current code treats these as final, but postponed/suspended/cancelled states need precedence. |
| `detailedState=Final` or `Game Over` | partial | Strong signal when not contradicted by postponed/suspended fields. |
| `statusCode=DR` or detailed postponed | no | Must not count as a completed game. |
| detailed suspended or resumed fields | partial | Must be handled as slate denominator risk until resumed/final row is understood. |
| final schedule plus usable boxscore pitching lines | strongest current core path | This is the best current evidence path for completed-game pitching logs. |
| final schedule without usable boxscore | no | Existing marker lifecycle treats empty/partial boxscores as incomplete or failed. |

Recommendation for later source work: finality should be classified by
precedence, not by any one field. Postponed, suspended, cancelled, empty
boxscore, missing game id, and missing pitcher identity must override final-ish
abstract status.

## 5. Boxscore Dossier

| field group | observed availability | currently stored? | finality safety | correction behavior | public_display | future priority |
| --- | --- | --- | --- | --- | --- | --- |
| pitcher person id/name | available | local pitcher identity linked/created | corrected-after-final | resolver can retry/dead-letter failures | INTERNAL-ONLY | FOUNDATION-0C |
| innings pitched | available | yes, normalized to outs and decimal innings | corrected-after-final | correction propagation exists | INTERNAL-ONLY | FOUNDATION-0C |
| outs recorded | available as `outs`; derivable from `inningsPitched` | stored as derived `innings_pitched_outs` | corrected-after-final | correction propagation exists through innings | INTERNAL-ONLY | FOUNDATION-0C |
| pitches thrown | available as `numberOfPitches` and `pitchesThrown` | yes, from `numberOfPitches` | corrected-after-final | nullable and correction-safe; missing becomes unknown | INTERNAL-ONLY | FOUNDATION-0C |
| strikes | available | yes | corrected-after-final | correction propagation exists | INTERNAL-ONLY | FOUNDATION-0C |
| batters faced | available | no | corrected-after-final | would need future schema and correction propagation | INTERNAL-ONLY | FOUNDATION-0C |
| balls | available | no | corrected-after-final | would need future schema and correction propagation | INTERNAL-ONLY | LATER-V4 |
| runs, earned runs, hits, walks, strikeouts, home runs | available | yes | corrected-after-final | correction propagation exists | INTERNAL-ONLY | FOUNDATION-0C |
| holds, saves, blown saves, wins, losses, save opportunities | available | yes as boolean flags when present | corrected-after-final | optional correction propagation exists when source key is present | INTERNAL-ONLY | FOUNDATION-0C |
| games started | available | yes | corrected-after-final | correction propagation exists when source value is present; boxscore fallback uses first pitcher order | INTERNAL-ONLY | FOUNDATION-0C |
| inherited runners and inherited runners scored | available | model has fields but current authoritative value mapping does not populate them | corrected-after-final | would need future mapping and correction propagation | INTERNAL-ONLY | FOUNDATION-0C |
| games finished | available | no | corrected-after-final | would need future schema and correction propagation | INTERNAL-ONLY | LATER-V4 |
| team pitching totals | available | no | corrected-after-final | would need future schema or derived aggregate policy | INTERNAL-ONLY | LATER-V4 |
| in-progress boxscore pitching lines | available partially | no completed-game use | no(live) | not safe for final evidence | NEVER | DO-NOT-USE |
| empty/partial final boxscore | partial | marker records incomplete/failed state, not public evidence | UNKNOWN until retried | retries then visible failure marker | INTERNAL-ONLY | AUDIT-ONLY-0B |

## 6. Correction Behavior

Current stored fields with Phase 0A correction propagation:

- `game_date`
- `game_type`
- `innings_pitched`
- `innings_pitched_outs`
- `pitches_thrown`
- `strikes`
- `hits_allowed`
- `runs_allowed`
- `earned_runs`
- `walks`
- `strikeouts`
- `home_runs_allowed`
- `opponent`
- `opponent_abbreviation`
- `games_started`
- `save_situation`
- `hold`
- `blown_save`
- `win`
- `loss`
- `save`
- `leverage_index` when included from boxscore

Current safety behavior:

- Existing row identity is `(pitcher_id, mlb_game_pk)`, backed by a unique
  database constraint.
- Identical re-ingest is safe because unchanged fields return `unchanged`.
- Safe changed values increment correction provenance.
- Partial correction sources are dead-lettered and do not overwrite existing
  good data.
- A complete source without `numberOfPitches` can correct pitch count to
  unknown, preserving the missing-vs-zero distinction.
- Empty final boxscore data remains retryable, then becomes a visible failed
  marker after the retry limit.

Available but not currently stored fields needing future correction propagation
before public use:

- `battersFaced`
- `balls`
- `pitchesThrown` if chosen over or alongside `numberOfPitches`
- raw `outs` if stored directly instead of deriving from innings
- `inheritedRunners`
- `inheritedRunnersScored`
- `gamesFinished`
- team pitching totals
- resumed/postponed linkage fields such as `rescheduleDate`, `resumedFrom`, and
  `resumedFromDate`

UNKNOWNs:

- Exact correction latency for final boxscore fields.
- Whether every candidate field has stable key shape across game types.
- Whether team totals are corrected on the same cadence as player pitching
  lines.
- Whether postponed/resumed rows always preserve the same `gamePk` in every
  relevant case.

## 7. Core Source, Legal, And Reliability Posture

| topic | posture |
| --- | --- |
| Cost/auth | Current repo uses Stats API as a free/no-auth HTTP source. |
| Documentation | Current client comment points to `https://statsapi.mlb.com/docs/`, and probe requests succeeded. This is not a contract or SLA. |
| Legal terms | `needs-legal-review`; this branch did not verify source terms, attribution requirements, storage rights, or redistribution rights. |
| SLA | No contracted SLA is implied. |
| Reliability | Good enough for continued internal audit and existing guarded use, with known operational risks. |
| Operational risks | schema drift, endpoint changes, rate limiting, timeouts, empty/partial responses, in-progress partial boxscores, delayed boxscore availability, correction latency, ambiguous status fields, postponed/rescheduled rows, suspended/resumed denominator behavior. |

## 8. Fail-Closed Rules For Stats API Core

| case | required behavior |
| --- | --- |
| missing game id | Skip row or withhold read; never invent identity. |
| missing or ambiguous final status | Treat as not completed; withhold completed-game evidence. |
| non-final game | Do not ingest as completed-game evidence; do not use in public completed-game claims. |
| postponed game | Exclude from completed-game denominator until rescheduled/final row is available; do not trust `abstractGameState=Final` alone. |
| suspended/resumed ambiguity | Treat as incomplete denominator risk until final/resumed relationship is understood and stored. |
| missing boxscore | Do not create completed-game evidence; mark processing incomplete/retryable where relevant. |
| empty/partial boxscore | Retry without duplicating logs; fail to visible marker after retry limit. |
| missing pitcher identity | Dead-letter resolution failure and keep slate incomplete. |
| missing pitch count | Store `NULL`; keep missing distinct from zero; exclude from pitch-count concentration reads. |
| correction-sensitive field without correction pathway | Keep internal-only or do not store until future correction propagation exists. |
| endpoint timeout/error | Retry only transient failures; if exhausted, raise typed fetch failure and do not imply an empty successful result. |
| schema drift or unknown field shape | Treat as partial/unknown, dead-letter if correction safety is affected, and do not overwrite good stored data. |

## 9. Source Category Matrix Rows

Rows follow `docs/phase0b/templates/source_category_matrix.md`. Because legal
posture is unresolved, all rows remain `INTERNAL-ONLY` or `NEVER` in this
branch.

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2_statsapi_foundation | schedule_game_identity | statsapi_v1 | `/schedule` `gamePk` | available | live | no(live) | identity can reappear across postponed/rescheduled rows | missing gamePk, duplicate row context, reschedule ambiguity | broad historical schedule windows observed | needs-legal-review | TBD | raw-cache-risk | B | low | core | INTERNAL-ONLY | skip missing game id; do not treat identity as proof of completed game | AUDIT-ONLY-0B | `backend/services/schedule_ingestion.py:96-134`; `docs/phase0b/probes/statsapi_core/2026-07-04_statsapi_core_probe.md` | 0B-03 |
| 17_schedule_facts | schedule_game_date_product_day | statsapi_v1 | `/schedule` `officialDate`, `gameDate` | available | live | no(live) | dates can change through postponement/reschedule | officialDate/date-bucket mismatch, missing date | broad historical schedule windows observed | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | prefer officialDate for product day; withhold when date cannot be parsed | AUDIT-ONLY-0B | `backend/services/schedule_ingestion.py:203-224`; probe record | 0B-03 |
| 17_schedule_facts | schedule_team_identifiers | statsapi_v1 | `/schedule` `teams.home.team.id`, `teams.away.team.id` | available | live | no(live) | team/opponent updates overwrite schedule rows | missing both team ids, team identity drift | broad historical schedule windows observed | needs-legal-review | TBD | raw-cache-risk | B | low | supporting | INTERNAL-ONLY | skip game if both team ids are missing | AUDIT-ONLY-0B | `backend/services/schedule_ingestion.py:112-134`; `backend/tests/test_schedule_ingestion.py:79-99`; probe record | 0B-03 |
| 2_statsapi_foundation | schedule_status_finality_fields | statsapi_v1 | `/schedule` `status` block | available | live | corrected-after-final | status can move from scheduled/postponed/live to final | abstract final on postponed row, status missing, suspended row | status fields observed across season windows | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | postponed/suspended/cancelled must override final-ish abstract state | FOUNDATION-0C | `backend/services/sync.py:57-63`; `backend/services/schedule_ingestion.py:137-163`; probe record | 0B-03 |
| 17_schedule_facts | schedule_game_type_season_fields | statsapi_v1 | `/schedule` `gameType`, date windows | available | live | no(live) | game type stable after schedule publication but can be filtered incorrectly | spring/postseason/exhibition included unintentionally | regular and spring samples observed | needs-legal-review | TBD | raw-cache-risk | B | low | contextual | INTERNAL-ONLY | filter game types explicitly before public claims | AUDIT-ONLY-0B | `backend/models/scheduled_game.py:50-54`; probe record | 0B-03 |
| 17_schedule_facts | doubleheader_game_number_fields | statsapi_v1 | `/schedule` `doubleHeader`, `gameNumber`, `seriesGameNumber`, `gamesInSeries` | available | live | no(live) | rescheduled doubleheaders can update row context | same-day multiple games, postponed makeup, missing flags | doubleheader sample observed | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | count separate game pks; mark denominator incomplete when makeup relation is unclear | FOUNDATION-0C | `backend/models/scheduled_game.py:60-64`; `backend/tests/test_schedule_ingestion.py:132-152`; probe record | 0B-03 |
| 17_schedule_facts | postponed_suspended_resumed_indicators | statsapi_v1 | `/schedule` `status`, `rescheduleDate`, `resumedFrom`, `resumedFromDate` | partial | live | UNKNOWN | status/linkage can change through makeup or resumed completion | abstract final with postponed, missing resumed link, suspended row | postponed and resumed samples observed | needs-legal-review | TBD | raw-cache-risk | C | high | core | INTERNAL-ONLY | exclude postponed; treat suspended/resumed ambiguity as incomplete until final linkage is proven | FOUNDATION-0C | `backend/tests/test_slate_coverage.py:300-330`; probe record | 0B-03 |
| 17_schedule_facts | probable_pitcher_schedule_fields | statsapi_v1 | `/schedule?hydrate=probablePitcher` | partial | live | no(live) | probable designation can change before first pitch | missing probable, stale probable, probable not actual starter | probable fields observed | needs-legal-review | TBD | raw-cache-risk | B | medium | contextual | INTERNAL-ONLY | never classify probable as happened evidence; use only as forward schedule context | AUDIT-ONLY-0B | probe record | 0B-03 |
| 3_boxscore_data | boxscore_pitching_lines | statsapi_v1 | `/game/{gamePk}/boxscore` player pitching stats | available | at-final | corrected-after-final | safe corrections update stored rows | empty boxscore, partial line, unresolved pitcher | final boxscore sample observed | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | require final game and usable pitching lines; retry empty/partial final boxscores | FOUNDATION-0C | `backend/services/sync.py:852-960`; `backend/tests/test_postgame_marker_lifecycle.py:266-443`; probe record | 0B-03 |
| 3_boxscore_data | boxscore_pitch_counts | statsapi_v1 | `stats.pitching.numberOfPitches`, `pitchesThrown` | available | at-final | corrected-after-final | stored pitch count can correct to known value or unknown | missing pitch count, partial correction source | sample observed both fields | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | store NULL when missing and keep missing distinct from zero | FOUNDATION-0C | `backend/services/sync.py:329-371`; `backend/tests/test_unknown_safe_ingestion.py:68-89`; probe record | 0B-03 |
| 3_boxscore_data | boxscore_outs_innings_pitched | statsapi_v1 | `stats.pitching.inningsPitched`, `outs` | available | at-final | corrected-after-final | innings corrections update outs and decimal innings | invalid innings notation, missing line | sample observed both fields | needs-legal-review | TBD | raw-cache-risk | B | low | core | INTERNAL-ONLY | parse MLB innings notation to outs; reject invalid notation | FOUNDATION-0C | `backend/utils/innings.py:12-46`; `backend/models/game_log.py:14-20`; probe record | 0B-03 |
| 3_boxscore_data | boxscore_batters_faced | statsapi_v1 | `stats.pitching.battersFaced` | available | at-final | corrected-after-final | no current propagation because field is not stored | missing key, post-final correction | sample observed field | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | do not public-display until schema and correction propagation exist | FOUNDATION-0C | probe record | 0B-03 |
| 3_boxscore_data | boxscore_strikes | statsapi_v1 | `stats.pitching.strikes` | available | at-final | corrected-after-final | correction propagation exists | partial correction source missing strikes | sample observed field | needs-legal-review | TBD | raw-cache-risk | B | low | core | INTERNAL-ONLY | reject partial correction source rather than overwrite strikes with unsafe data | FOUNDATION-0C | `backend/services/sync.py:75-84`; `backend/tests/test_stat_correction_propagation.py:247-284`; probe record | 0B-03 |
| 3_boxscore_data | boxscore_pitcher_identity | statsapi_v1 | `players.ID*.person`, pitching order | available | at-final | corrected-after-final | resolver can create/reactivate pitcher or dead-letter missing identity | missing/invalid player id, missing name, stale team | sample observed person id/name | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | dead-letter unresolved pitcher identity and keep slate incomplete | FOUNDATION-0C | `backend/services/sync.py:725-852`; `backend/tests/test_postgame_marker_lifecycle.py:329-386`; probe record | 0B-03 |
| 3_boxscore_data | boxscore_team_pitching_totals | statsapi_v1 | `teams.home/away.teamStats.pitching` | available | at-final | corrected-after-final | no current propagation because totals are not stored | missing team totals, correction latency, aggregate mismatch | sample observed totals | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | keep internal-only until aggregate storage and correction policy exist | LATER-V4 | probe record | 0B-03 |
| 3_boxscore_data | boxscore_empty_partial_behavior | statsapi_v1 | empty or partial `/boxscore` response | partial | live | UNKNOWN | retry may later return complete data | delayed availability, in-progress partial lines, empty final section | partial live boxscore observed; empty final behavior covered by tests | needs-legal-review | TBD | raw-cache-risk | C | medium | core | INTERNAL-ONLY | mark incomplete/retryable; stop at visible failed marker after retry limit | AUDIT-ONLY-0B | `backend/tests/test_postgame_marker_lifecycle.py:266-443`; probe record | 0B-03 |
| 3_boxscore_data | correction_sensitive_final_pitching_lines | derived_internal | stored game logs plus correction provenance | derivable | final+lag(observed) | corrected-after-final | changed authoritative fields increment correction provenance | partial correction source, missing required stat key, source shape drift | starts with stored game logs and Phase 0A migrations | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | dead-letter unsafe corrections and preserve prior good data | FOUNDATION-0C | `backend/services/sync.py:374-493`; `backend/tests/test_stat_correction_propagation.py:155-375` | 0B-03 |

## 10. Findings And Recommendations

### Strong Enough To Continue Using Internally

- `gamePk` as game identity, with status/date context.
- Schedule team ids, game date, game datetime, game type, doubleheader, and game
  number fields already stored conservatively.
- Final boxscore pitching lines for pitcher identity, innings/outs, pitch count,
  strikes, runs, earned runs, hits, walks, strikeouts, home runs, saves, holds,
  blown saves, wins, and losses.
- Current correction propagation for stored game-log fields.
- Current marker lifecycle for empty/partial final boxscores.

### Public-Candidate From A Data-Integrity Standpoint, Still Internal Here

The following groups look strong enough to be candidates for future public
evidence after legal/source review and later Phase 0C decisions:

- Final game identity with final schedule status and usable boxscore.
- Final boxscore pitcher identity.
- Final boxscore innings/outs, pitch count, strikes, and basic run-prevention
  fields already covered by correction propagation.
- Doubleheader game count as a slate denominator, when both game rows are
  final or explicitly postponed according to precedence rules.

They remain `INTERNAL-ONLY` in this branch because legal posture is unresolved.

### Should Remain Internal-Only

- Probable pitchers, because they are forward-looking schedule context only.
- Team pitching totals, until storage and correction policy exists.
- Batters faced, balls, inherited runners, games finished, and similar
  available-but-not-stored fields, until schema and correction propagation
  exist.
- Any confidence, score, or prediction framing derived from these fields.

### Should Wait For Phase 0C

- Finality precedence hardening around postponed/suspended/cancelled rows.
- Storage decisions for `battersFaced`, raw `outs`, `pitchesThrown`, balls,
  inherited runners, games finished, and team totals.
- Explicit source contract for product-day authority and rescheduled game
  denominator handling.

### Should Wait For 0B-04

- Play-by-play context beyond naming that completed-game context can consume it
  transiently.
- Transactions, IL, injuries, roster/depth, and richer schedule context.

### Unknown Or Legal-Review Needed

- Terms, attribution, storage, and redistribution rights.
- Any formal SLA or stability commitment.
- Exact correction latency by field.
- Full status-code taxonomy across seasons and game types.
- Venue timezone availability through schedule hydration.
- Whether resumed-game linkage is complete enough without storing additional
  fields.

## 11. Phase 0B-03 Decision

Stats API core schedule and boxscore data is suitable for continued guarded
internal use and later Phase 0C foundation planning. It is not approved here for
new public evidence or new ingestion behavior.

The most important audit finding is finality precedence: `abstractGameState` is
not safe as a sole finality authority because a postponed row can also carry
`abstractGameState=Final`. Future work should classify finality only after
postponed, suspended, cancelled, empty-boxscore, and pitcher-identity failure
states are handled first.
