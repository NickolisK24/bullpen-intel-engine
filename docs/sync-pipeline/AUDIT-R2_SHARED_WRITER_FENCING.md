# AUDIT-R2 — Shared Writer Ownership and Fencing

Maintainer: Nikko

Status: implementation under validation; production certification pending.

## 1. Audit finding

F02 identifies overlapping mutable writers without a shared semantic exclusion boundary. The fetched integration base on September 11, 2026 is `d4b1ba54b0046db93912a331ee6d273ce62bb232`. Work is isolated on `fix/audit-r2-writer-fencing`. Publication and atomic reads remain disabled; main and Render configuration are outside the change.

## 2. Writer inventory

This is the pre-change inventory. Sharing a helper does not establish serialization. Manual correction utilities remain governed entry points, not exceptions to ownership.

| Semantic resource | Legacy writers | SP writers | Existing exclusion / authority | Conflict risk |
|---|---|---|---|---|
| ScheduledGame identity, dates, status, matchup | schedule_ingestion.ingest_games, daily/morning/CU | SP-04 via the same helper; SP-06 context fields | Team/game unique key; legacy orchestration guard; no shared source-order fence | An older schedule can replace newer status or context |
| SlateGame schedule projection | schedule_ingestion.ingest_games | SP-04 through the same helper | Same acquisition lineage as ScheduledGame; separate row identity | Included in the common schedule/game database guard |
| GameObservationState | game_change_detection via CU | SP-08 and shadow CU observation | Upstream timestamp and authority comparison against an unlocked ORM read | Concurrent observations can both pass against old accepted state |
| ProvisionalPitchingAppearanceState | No direct legacy writer | SP-08 updates; SP-07 supersedes | Live advisory namespace 508000000000; final namespace 507000000000 | Late live work can pass its earlier state check after Final |
| GameLog and final pitching lines | sync daily/postgame, game_driven_ingestion, historical/backfill wrappers, governed line correction utilities | SP-07 calls process_completed_game_for_postgame_refresh | Unique pitcher/game, shared correction helper; legacy public session lock differs from SP final transaction lock | Valid unique row can receive an older line; same helper is not a fence |
| Final PBP/current appearance projections | play_by_play_foundation from legacy postgame/CU/repair | SP-07 calls foundation | Source-order checks and identities; caller lock differs | Cross-owner compare/write race needs mutation-time exclusion |
| PostgameProcessedGame / PlayByPlayProcessedGame completion markers | Legacy completed-game/PBP writers | SP-07 through the same writers | Previously caller-local ordering | Guarded with the corresponding Final projection so stale work cannot regress completion |
| CompletedGameContext and TeamGamePitchingSplit | completed_game_context_service and team_game_pitching_splits through legacy sync/repair | No direct SP writer | Legacy-derived context and aggregate contract; SP-07 does not call their persistence helpers | No shared mutable SP writer; legacy derivation freshness remains separate from atomic reader certification |
| Pitcher MLB team, assignment and tracking | team_assignment_sync, roster_status_sync, authoritative-line identity resolution, intraday_identity_repair | SP-05 positive roster projection and R1 correction | SP-05 team lock only; legacy assignment overwrites every classified record | Affiliate assignment or older roster evidence can replace governed pitcher organization |
| RosterStatusSnapshot | roster_status_sync and exact-date repair | SP-05 _update_current_and_snapshots | Pitcher/date identity and team-conflict check; no common lock/source winner | Same-day conflict and last-writer correction; old source can erase SP provenance |
| PlayerTransaction/current alignment | transaction_ingestion and exact-roster realignment | SP-05 transaction wrapper | Event key; append-only versions in integration; unlocked read/update | Different windows can race and an old correction can win |
| Team State and fatigue/workload compatibility | Legacy daily/CU/recalculation, `fatigue.recalculate_all` | SP-10 calls incremental calculators | SP-10 calculators return candidate dictionaries and SimpleNamespace overrides; Team State is embedded in legacy publication/read models rather than a shared SP-updated current TeamState table | Explicit non-overlapping persistence ownership |
| Mutable read-model/cache projections | Legacy serving/builders and CU | SP-10 reuses builders with a copied snapshot | `incremental_read_model_rebuild` calls direct builders, not cached serving/publication entrypoints; candidate payload is persisted only in cohort snapshots | No shared mutable serving-generation write; candidate input closure is outside R2 |
| FinalGameVersion / FinalPitchingAppearanceVersion | None | SP-07 | Current-version uniqueness and final advisory lock | Delayed source bundle can create a new version from older evidence without version comparison |
| RosterMembershipInterval | None | SP-05 / SP-13 through SP-05 | R1 scoped uniqueness and club ownership | Cross-system overlap is in Pitcher/snapshot projections, not legacy interval writes |

## 3. Existing lock map

Legacy public orchestration uses a session advisory lock `820260801`; internal enrichment uses `820260802`. SP-05 uses transaction lock `505000000 + team_id`. SP-07 uses `507000000000 + gamePk`; SP-08 uses `508000000000 + gamePk`. Source-subject version locks and queue claim locks protect different resources. A queue settlement fence does not establish baseball source precedence.

Read-only Render inspection at approximately 14:38 UTC confirmed the integration service is live on the exact base SHA, deploy `dep-dai0tjlg1s2s73dbmom0`. All four legacy crons still deploy `main@aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65`. Continuous primary and integration shadow both run every three minutes. Morning is 14:05 UTC; daily 10:05 UTC; postgame 02:05/04:05/06:05 UTC. None is suspended. Updating integration Python alone cannot make those existing legacy binaries acquire a new lock.

## 4. Root concurrency risks

The mutable comparison must be repeated after exclusion is acquired. Existing ORM objects can also survive a lock query: SP-02 `_owned_job` currently lacks `populate_existing`, so a fresh database lock is not necessarily fresh in-memory lease identity. Final source fingerprints identify content but are not orderable upstream revision numbers. The implementation must not invent upstream order from arrival timestamps.

## 5. New ownership model

The implementation under validation uses persistent canonical ownership, not a
process-name convention. Once SP final authority exists, it owns the shared
GameLog/PBP projection. Once governed MLB membership exists, SP-05 owns that
pitcher's organization/status projection. Versioned transaction events are owned
by the event reconciliation path. Older deployed binaries are subject to database
guards; changing integration Python alone would leave the main-based cron
processes outside the exclusion boundary.

| Semantic resource | Current authority | Legacy role | SP role | Fence | Retirement condition |
|---|---|---|---|---|---|
| GameLog and final PBP | SP-07 for games with current Final; legacy before that | Populate unowned games; consume owned projection | Reconcile Final and corrections | Game advisory lock plus database guards | Later governed cutover; no retirement here |
| Current provisional appearances | SP-08 until SP-07 Final | No direct writer | Live owner or Final supersession | Same game lock and mutation-time Final check | Retain live owner |
| Game observation projection | Accepted upstream revision; Final cannot regress to live | Acquire evidence through shared comparison | Same comparison and retained source lineage | Game lock and database compare/previous-fingerprint guard | Retain acquisition as needed |
| MLB pitcher organization/status | SP-05 for governed pitchers | Consume SP truth; retain separate non-governed assignment contract | Project complete official MLB source | Pitcher row plus database protected-field guard | Later roster-owner transition |
| Same-day roster snapshot | SP complete active/40-man pair over legacy evidence | Consume an SP snapshot if present | Compare retained subject versions | Pitcher then snapshot row; older-binary no-wait guard | Retain dated history |
| Versioned transaction event | Current event version | Populate unowned events; consume owned projection | Compare captured event version; append corrections | Event advisory key and database guard | Retain event history |
| Mutable Team State/fatigue | Legacy publication path | Current public computation | Candidate calculations only | No shared mutable SP writer identified | Retain until reader cutover |

This is a temporary coexistence contract. The table does not authorize CR-05 or
legacy retirement. Database ownership must not be undone merely by turning off
the pipeline flag: rollback requires an explicit ownership/recovery decision.

## 6. Shared lock/fence design

`semantic_write_fencing.py` defines transaction-scoped game locking at
`507000000000 + gamePk`, immutable worker claim capture, and pre-commit lease
validation using fresh database columns. SP-04/SP-06/SP-07/SP-08 and the shared
GameLog compatibility helper enter that game domain. Transaction events use the
two-integer advisory namespace `509000000` and the event key hash. Unrelated games
remain independently lockable.

Migration `e3f6a9b2c5d8` is under validation. It adds an append-only operational
event table and guards to shared compatibility tables. Scoped transaction-local
owner markers are set only by validated owner functions. They are PostgreSQL
transaction settings, not Render environment changes. Older binaries that enter
through a row update use a non-waiting advisory check: contention fails retryably
instead of waiting in the reverse lock order. Conflicting updates retain the
authoritative fields and record suppression; unauthorized insertions that could
invent an appearance fail closed.

The migration has **not** been applied to production. Its protection must be
tested against whole caller behavior, including ORM identity-map and completion
marker effects, before it is eligible for deployment.

## 7. Authority precedence

Required: live < final < corrected final. A correction requires retained source lineage; timestamps alone are insufficient. A stale claim cannot authorize a semantic commit.

## 8. Game writer changes

SP-07 now compares retained subject versions after taking the common lock. A
delayed earlier Final cannot install a new current version over corrected Final.
The acquisition path also captures the current Final identity before fetching;
if authority changes during acquisition, differing input requires a fresh bounded
reconciliation instead of assuming arrival order is source order. SP-08 repeats
the Final-owner check at the actual projection mutation boundary.

When an older detector accepts a newer upstream revision, the database guard
clears its inherited SP-03 observation link. The SP detector can reattach that
link only after retaining the exact matching fact set. A newer legacy projection
therefore cannot falsely cite an older source observation.

## 9. Roster projection changes

The governed population is official pitcher/two-way membership. R1's five non-pitching legacy records remain separate evidence: Tyler Callihan 802, Max Schuemann 999, Buddy Kennedy 992, César Salazar 984, Jake Meyers 997. This package does not assume those records should be deleted or reassigned merely because their table is named Pitcher.

SP-05 projects organization, registry-backed club labels and status only
after its complete-source membership reconciliation. Legacy assignment refreshes
prefetch the governed population once and leave those fields to SP-05. Database
guards cover direct utilities and older deployed callers as well.

Official MLB roster endpoints do not expose a comparable upstream revision.
The existing club lock therefore covers this owner's active/40-man acquisition
pair through commit. Same-club calls cannot fetch an earlier response and resume
after a newer owner commits. This intentionally bounds parallelism within one
club's two-request reconciliation; affiliate evidence and other MLB clubs remain
independent. Game acquisition remains outside the game mutation lock.

For one player/date, complete SP active/40-man evidence outranks a legacy
snapshot. A receiving MLB club may correct a same-day SP snapshot after the prior
club's complete negative evidence and closed membership establish removal. Two
contradictory positive MLB claims remain an explicit conflict. Negative evidence
from one club cannot replace another club's positive player/date projection.
Retained older subject versions/dates cannot reassert current membership, and
older dated snapshots cannot overwrite a newer current pitcher projection.

## 10. Transaction changes

Transaction acquisition captures the current event versions before source reads.
Reconciliation locks by event identity, refreshes the current row, and suppresses
an incoming event whose captured predecessor no longer matches. The SP worker
schedules bounded reacquisition for suppressed event versions. Exact-roster
alignment repair refreshes its bounded transaction/snapshot batch under the same
event locks. Versioned events append a new version; pre-SP rows without retained
source observations keep the existing compatibility provenance contract rather
than fabricating source-backed history.

During initial adoption of an unversioned legacy event, the owner also compares
the captured semantic fact fingerprint. Version zero alone cannot detect a
legacy correction committed during acquisition. A changed predecessor requires
reacquisition. Transaction versions remain unique by event/version; repeating a
previous fact fingerprint is permitted as a later correction. A → B → A retains
all three versions. An unattributed pre-SP baseline is explicitly nullable, not
assigned a fabricated source observation.

## 11. Shadow-mode write contract

Existing shadow writes source/run/job records, canonical schedule/roster/live/final state, GameLog and roster compatibility projections, impact plans, cohorts and immutable candidates. It cannot claim publication or closure. Compatibility writes can affect legacy public reads despite the shadow label; each requires an explicit fence or isolation.

## 12. Lock ordering

New game owners acquire sorted game advisory keys before mutable game rows.
Roster owners retain their team boundary, lock pitcher rows in ID order, and
then lock dated snapshots. Older snapshot writers already holding a snapshot row
must acquire the pitcher row without waiting. Transaction batches sort event
keys before locking. The legacy public orchestration lock remains outermost when
legacy orchestration uses it; SP owners do not request that public lock while
holding a game lock.

The immutable worker claim is checked again immediately before transaction
commit. The queue row stays locked through semantic flush/commit, preventing a
replacement claim from becoming owner in that commit window. An expired or
replaced claim raises an ownership error and cannot commit its pending changes.
Cross-resource lock ordering and retry effects remain part of validation.

## 13. Concurrency tests

Focused PostgreSQL results so far:

- Twenty-two shared-writer tests cover delayed legacy GameLog update after
  corrected Final, delayed Final after corrected Final, delayed live after Final,
  unrelated-game parallelism, and reverse-order lock rejection.
- The delayed legacy test reads 18 pitches, allows corrected Final to commit 19,
  then attempts to write 18 through raw SQL. The stored row remains 19.
- The roster/raw-SQL guards reject affiliate overwrite and legacy replacement of
  SP snapshot status.
- The focused roster authority/isolation group passes 39 tests, and bounded
  transaction repair passes six tests after the source-less compatibility fix.

Additional PostgreSQL tests now cover overlapping transaction windows, raw older
transaction writes, A → B → A history, migration upgrade/downgrade safeguards,
same-day MLB transfer followed by delayed historical evidence, and current
health conflicts distinct from expected suppressions. A whole legacy
postgame/PBP call after SP Final reports no false correction or SyncFailure.
SP-02 tests include a real queue reclaim and rejection of the expired owner's
pending semantic commit. Full CI and production recurrence are separate gates.

An additional whole-caller test loads `sync.py` and `play_by_play_foundation.py`
from the actual deployed legacy commit `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65`.
After corrected Final, its attempted earlier pitching line remains suppressed,
its older PBP is rejected by the persisted source-order contract, and no
SyncFailure is created. This directly checks older code rather than assuming all
legacy processes already contain the new helper.

The broader queue/game/roster/transaction/cohort/repair run passed 402 PostgreSQL
tests. A later focused roster/transaction run passed 120 tests. Shard verification
reported zero missing or duplicated files/node IDs. These local results are
reported separately from CI and deployment; they do not authorize publication.
The detector/lineage group passed 117 PostgreSQL tests; the final shared-writer,
roster, R1 isolation and certification group passed 73. Same-club acquisition
ordering and unrelated-club parallelism are both exercised.

## 14. Natural regression proof

Game 823413 is the retained reference. A new read-only production capture at
15:42 UTC retained its official finality/boxscore, seven provisional appearances,
and 22 GameLog rows covering September 4–10. The fixture lives at
`backend/tests/fixtures/audit_r2_game_823413.json`; original database IDs remain
evidence identifiers and test source IDs are local.

The PostgreSQL regression reconstructs that numerical input, reconciles through
SP-07, and proves seven final contributions and zero remaining current
provisional appearances. Optional PBP is deliberately withheld in this test; it
does not claim new PBP certification. Repeated reconciliation does not add rows.

| Pitcher | Final pitches / outs / BF | Seven-day pitches / appearances |
|---|---:|---:|
| Bennett Sousa | 14 / 3 / 3 | 47 / 3 |
| Bryan Abreu | 10 / 3 / 3 | 62 / 4 |
| Cristian Javier | 79 / 18 / 20 | Starter core checked |
| Josh Hader | 8 / 3 / 3 | 51 / 4 |
| Jhoan Duran | 17 / 3 / 4 | 55 / 4 |
| José Alvarado | 18 / 3 / 5 | 50 / 3 |
| Zack Wheeler | 110 / 21 / 27 | Starter core checked |

## 15. Production coexistence proof

No R2 deployment has occurred. The read-only pre-change census at 14:45:25 UTC
found **19 governed pitchers again assigned to affiliates by legacy
`mlb_stats_api:team_assignment_sync:active`**, after the R1 interval repair. This
is direct production evidence for F02, independent of the earlier audit.

| MLB club | Affiliate | Pitcher database IDs and names |
|---|---|---|
| Yankees (147) | 531 | 707 Brendan Beck; 715 Elmer Rodríguez; 1042 Bradley Hanner; 727 Yerry De los Santos |
| Pirates (134) | 484 | 396 Evan Sisk; 1017 Noah Murdock; 398 Hunter Barco; 405 Thomas Harrington |
| Nationals (120) | 534 | 332 Richard Lovelady; 320 Gus Varland; 66 Kyle Nicolas; 323 Josiah Gray; 331 Paxton Schultz; 718 Jake Bird; 318 DJ Herz |
| Astros (117) | 5434 | 242 Kai-Wei Teng; 239 Jason Alexander; 244 Logan VanWey; 229 Alimber Santa |

The same read-only census found zero current provisional rows for finalized
games and zero duplicate GameLog pitcher/game keys. Game 823413 retained seven
GameLog rows, Final version 196/v2 current, predecessor 195/v1 non-current.
Publication pointer 1 remained unchanged. None of these pre-change observations
proves post-deployment recurrence safety.

A second read-only census at 16:08 UTC found the same 19 projection conflicts,
zero Final/GameLog numerical mismatches, and zero duplicate transaction keys.
The exact roster-set report at 16:10 UTC remained 30/30 active and 30/30 40-man,
with zero affiliate-owned interval violations. This distinguishes preserved R1
membership truth from the recurrent legacy current-pitcher overwrite.

The refreshed Render environment page at 16:13 UTC showed pipeline/shadow true;
publication/morning/closure false; both legacy controls true. Atomic reads were
absent from the complete service and linked-group key lists, retaining the
checked false default. The deployed integration remained at the R1 base SHA.

## 16. Health/observability

Expected stale suppression must remain observable without becoming a SyncFailure. Unresolved authority conflicts must remain distinguishable from harmless suppression.

The proposed health reducer reports current provisional rows for Final games,
governed pitcher/current-team disagreement, Final-vs-GameLog numerical mismatch,
current transaction facts that disagree with their immutable event version,
recent suppression totals, and repeated active-job lock contention. Expected
suppression alone does not block health; unresolved projection disagreement does.

## 17. Remaining limitations

This document does not yet claim PASS. Full CI, exact deployment/migration
verification, bounded governed correction of recurring roster projections, and
natural post-deployment recurrence remain outstanding. Older binaries cannot
interpret new suppression outcomes themselves: a conflicting delete/reinsert or
an attempt to invent a Final appearance fails closed at the database boundary.
Any recurring resulting legacy failure must be investigated before coexistence
can PASS; preserving a row alone is not proof of healthy whole-caller operation.

This package does not certify candidate input closure, publication completeness,
atomic reads, closure/replay behavior or legacy retirement. It preserves the
five non-governed legacy records identified by R1. Privileged manual SQL can
bypass application ownership and is not an authorized recovery path.

## 18. Verdict

NOT CERTIFIED — work in progress.
