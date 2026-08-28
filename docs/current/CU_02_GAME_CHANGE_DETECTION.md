# CU-02 — Game Change Detection

## 1. Branch

`feat/game-change-detection`

## 2. Starting main SHA

`bef64ea2e837d868f220b26627feaf00bd2013e0` (CU-01 merge commit, PR #767).
The pre-existing untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` was
not touched. PR #768 was not touched.

## 3. Current game-observation infrastructure audit

- `ScheduledGame` is a two-row-per-game rolling schedule ledger. It stores raw
  status code, conservative status state, game/team/date/doubleheader and
  suspended/resumed linkage. It does not store inning, score, current matchup,
  event count, live-feed revision, or a material fingerprint.
- `game_finality` is the sole finality authority. Its precedence rejects
  postponed, suspended, cancelled, abstract-only final, and unknown states; a
  final status without a usable boxscore remains `final_pending_data`.
- `MLBApiClient` already acquires schedule, boxscore, linescore and PBP with
  bounded timeout, typed failure, retry/backoff, Retry-After support and endpoint
  metrics. CU-02 adds only the official v1.1 full-live-feed acquisition method.
- `PlayByPlayProcessedGame` is a final-game PBP persistence marker. Its accepted
  sequence is caller-governed because the PBP-only endpoint has no revision.
  Reusing it for live detection would conflate observation with pitch mutation.
- `GameIngestionWorkItem` is the final-game appearance-ingestion checkpoint. Its
  `source_revision` is an extracted appearance-set fingerprint, not live-game
  state. Its correction window remains downstream and authoritative only through
  existing scheduled paths.
- `PostgameProcessedGame` is likewise final/postgame-specific.
- The game-driven shadow planner reads the schedule ledger, proves finality,
  acquires final-game data and invokes CU-01 only in configured shadow mode.
- No existing service answers “last accepted material live-feed observation.”
  There is no polling loop or event bus to reuse.
- Schedule ingestion and slate finality refresh mutate `ScheduledGame`; CU-02's
  standalone detector does not call either and therefore cannot mutate schedule
  authority while observing.

The safe seam is a small observation state beside—not inside—final ingestion
markers, returning a game-scoped result without invoking CU-01.

## 4. Current Render execution map

Render dashboard-managed Cron is primary; no root `render.yaml` defines jobs.

| Job | UTC schedule | Command/path |
|---|---:|---|
| Daily | `5 10 * * *` | `run_due_sync.py --mode daily ... --days-back 7 --public-only` |
| Postgame | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` |
| Morning | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` |

`run_due_sync.py` performs durable due-window arbitration and invokes the
existing daily/postgame/morning authority. `.github/workflows/baseballos-sync.yml`
retains delayed fallback/reconciliation schedules at minutes 17, 11 and 23 and
uses the same due-window runner. Daily and postgame set
`GAME_DRIVEN_INGESTION_MODE=shadow`; backfill uses `off`. CU-02 changes none of
these files, commands, modes or schedules. `detect_game_changes.py` is an
independent manual/future-job entrypoint and is referenced by no production
scheduler.

## 5. Chosen observation model

`GameObservationState` stores one latest accepted normalized observation per
`mlb_game_pk`: SHA-256 fingerprint, compact canonical JSON, source authority and
endpoint, upstream observation timestamp, finality, prior fingerprint, last
classification/diff, and local accepted timestamps for observability. It is not
a Game, GameLog, PBP, snapshot or publication record.

Raw feeds are not stored. The 15-game proof averaged about 824 KB per full feed;
persisting unlimited raw JSON would be disproportionate. The normalized object
retains every field used by detection and is deterministic for reprocessing.

## 6. Change-classification contract

| Classification | Meaning | Accepted/write? | Emits work? |
|---|---|---:|---:|
| `new_game` | First valid observation | yes | changed game result only |
| `unchanged` | Material fingerprint matches | no | no |
| `changed` | Newer non-final material state | yes | changed game result only |
| `finalized` | Newer transition into canonical safe final status | yes | changed game result only |
| `corrected` | Newer material observation after accepted final | yes | changed game result only |
| `stale_observation` | Older or weaker-authority evidence | no | no |
| `ambiguous_observation` | Differing content lacks comparable order | no | no |
| `source_failure` | Acquisition/shape failure | no | no |

All results hard-code `downstream_work_triggered=false`,
`canonical_mutation_performed=false`, and empty affected pitchers/teams.

## 7. Observation-ordering contract

The full feed exposes MLB `metaData.timeStamp` in `YYYYMMDD_HHMMSS` form. CU-02
persists it as upstream observation evidence and compares it only within the
same source authority. Source authority ranks first. Identical fingerprints are
no-ops regardless of timestamp. Differing content is accepted only when its
same-authority upstream timestamp is strictly newer. Older is stale; equal,
missing, malformed or cross-authority ordering is ambiguous and rejected. A
weaker authority is stale. A stronger but incomparable source also fails closed.
Local acquisition/detection time never participates in ordering.

This is deliberately a partial order, not a claim that MLB supplies a universal
event revision sequence.

## 8. Fingerprint contract

The sorted canonical JSON includes only baseball-relevant fields:

- game identity/date/start/type/doubleheader/number, clubs and probable pitchers;
- raw status fields plus the canonical `game_finality` decision;
- inning/half/state, scheduled innings, count/outs, score/hits/errors;
- current linescore pitcher/batter;
- play and pitch-event counts, current at-bat/pitcher/batter/completion/result;
- last play/event stable identity and event codes.

It excludes MLB copyright, response ordering, `metaData.wait`, event-notification
arrays, raw embedded records, and local timestamps. A compact flattened diff is
returned/stored only for accepted material changes.

## 9. Persisted-state design

Migration `c6d8e1f3a5b7` creates `game_observation_states`, unique by gamePk, with
indexes on finality and upstream observed time. Exact replay does not update even
`updated_at`. State therefore survives worker restart/redeploy and is sufficient
to reject an older capture after restart.

## 10. Files changed

- `backend/models/game_observation_state.py`
- `backend/services/game_change_detection.py`
- `backend/services/mlb_api.py`
- `backend/scripts/detect_game_changes.py`
- `backend/migrations/versions/c6d8e1f3a5b7_add_game_observation_states.py`
- `backend/app.py`
- `backend/tests/test_game_change_detection.py`
- `backend/tests/test_mlb_api_client.py`
- `backend/tests/test_phase0e_exit_docs.py`
- `backend/tests/ci_shard_manifest.json`
- this report

## 11. Schema changes

One additive table; no existing table or historical row is rewritten. The
Alembic graph has one head, `c6d8e1f3a5b7`. Head-only upgrade, downgrade to
`b4e7c9d2a1f6`, and re-upgrade passed in isolated SQLite. A clean full SQLite
chain remains blocked at the pre-existing `c7f1b408d93a` ALTER syntax; CU-02 did
not widen into that unrelated repair.

## 12. Real-game proof dataset

Natural source capture: the complete 15-game MLB slate for 2026-08-25. Every
feed reported Final and supplied an upstream timestamp.

| gamePk | Away at home | MLB feed timestamp |
|---:|---|---|
| 824233 | Rays at Tigers | `20260826_010754` |
| 823826 | Red Sox at Marlins | `20260826_020649` |
| 822693 | Rockies at Nationals | `20260826_013433` |
| 823505 | Astros at Yankees | `20260826_021432` |
| 822773 | Royals at Blue Jays | `20260826_020513` |
| 823585 | Brewers at Mets | `20260826_021119` |
| 824881 | Dodgers at Braves | `20260826_015854` |
| 824556 | Rangers at White Sox | `20260826_025754` |
| 823016 | Orioles at Cardinals | `20260826_024037` |
| 823989 | Guardians at Angels | `20260826_050143` |
| 825042 | Cubs at Diamondbacks | `20260826_041620` |
| 823259 | Pirates at Padres | `20260826_040312` |
| 824962 | Twins at Athletics | `20260826_040801` |
| 823098 | Phillies at Mariners | `20260826_041030` |
| 823181 | Reds at Giants | `20260826_040618` |

## 13. Natural vs controlled observations

- **Natural:** one schedule response and 15 live feeds; real identity, status,
  final state, full plays, tracking and upstream timestamps. Two consecutive
  natural fetches of game 823826 produced the same timestamp and fingerprint.
- **Controlled replay of natural capture:** exact second observation for all 15
  and post-restart observation for five.
- **Controlled real-shape sequence based on game 823826:** live outs/inning,
  pitcher and event-count progression; delayed/postponed/suspended status;
  final transition; post-final correction; stale/equal/missing-order replay.
  These are not claimed as naturally observed historical revisions.

No suitable natural post-final correction or reconstructable suspended live
capture was found in the bounded slate; those claims remain controlled proof.

## 14. Replay results

All 15 first observations returned `new_game`; all 15 exact replays returned
`unchanged`. Fifteen rows remained. No GameLog, pitch-event, snapshot, artifact,
affected entity or downstream-work output was created.

## 15. Restart results

The SQLite engine/application connection was disposed and recreated against the
same proof database. Exact replay of gamePks 824233, 823826, 822693, 823505 and
822773 returned `unchanged`; all five fingerprints were stable.

## 16. Stale/ambiguous behavior

Controlled A -> newer B -> A produced accepted A, accepted B, stale A. After
session/application restart, A remained stale and B's fingerprint remained
canonical. Equal timestamp with different content, absent timestamp with
different content, and weaker authority were rejected with zero affected
entities/downstream implication.

## 17. Live-state transition proof

Controlled real-shape changes independently proved: outs 1 -> 2, inning 8 -> 9,
pitcher 687941 -> 641729, and pitch-event count 2 -> 3. Each strictly newer feed
returned `changed` and a deterministic field-level diff; exact replay returned
`unchanged`.

## 18. Finality transition proof

Live (`I`) -> Final (`F`) returned `finalized`. The stored decision was
`final_pending_data`, exactly as `game_finality` requires when no boxscore is
provided. CU-02 does not upgrade that to usable finality or invoke final-game
ingestion.

## 19. Post-final correction proof

Controlled newer final content returned `corrected`; exact corrected replay was
`unchanged`. Older pre-correction evidence was rejected before and after restart.
Natural post-final correction remains unproven in this dataset.

## 20. Source-efficiency measurements

The proof used one schedule request plus 15 live-feed requests. Serialized feed
volume totaled 12,362,182 bytes (average 824,146/game; range about 708–998 KB).
Detector normalization/reconciliation after acquisition averaged 10.1 ms/game
in the isolated run. A bounded cycle reports candidates, expected requests,
changed/unchanged/failure counts and elapsed time. There is no polling loop.

The obvious cost is the N live-feed requests; the one schedule response is
shared for selection. Future scheduling should select a narrow active slate and
must measure source pressure before changing cadence.

## 21. Zero downstream mutation

Focused sentinels prove GameLog, GamePitchEvent and ShareArtifact counts remain
unchanged. Production sync/schedule files contain no CU-02 call. The detector
does not import CU-01, workload, Team State, read-model, cache or publication
services.

## 22. Zero publication

No publication pointer, snapshot, share artifact, What Changed path, cache or
frontend file is read or written by CU-02. `downstream_work_triggered` is always
false. Render and GitHub schedules are unchanged.

## 23. Test results

- CU-02 focused: **19 passed**; MLB client suite: **14 passed** (including the
  configured-host v1.1 source-path contract).
- Final CU-02/CU-01/finality/PBP/planner/shadow/provenance/scheduling/publication
  selection: **299 passed**.
- Expanded schedule/postgame/daily/authority/snapshot/publication selection:
  **519 passed after environment qualification**. Its first run was 518 passed,
  1 failed because the shell exposed a remote production `DATABASE_URL` to a
  test creating `create_app('test')`; the fail-closed config refused the remote
  host. Rerun with explicit disposable `TEST_DATABASE_URL=sqlite:///:memory:`
  passed. This was not a CU-02 regression.
- Migration head-only upgrade/downgrade/re-upgrade: **PASS**; one head.
- CI shard verification: **PASS**; 394 files and 8,990 node IDs assigned
  exactly once.
- Clean full SQLite chain: **INCOMPLETE/PRE-EXISTING BLOCKER** at
  `c7f1b408d93a`; CU-02 head migration itself passed.
- Python compilation: **PASS**. Final `git diff --check`: **PASS** (only
  repository line-ending conversion warnings were emitted).

## 24. Remaining risks

- MLB `metaData.timeStamp` is useful upstream feed evidence but not a universal
  event revision sequence; incomparable observations intentionally fail closed.
- Natural live timing, suspension/resumption and post-final corrections were not
  captured during this bounded deterministic run.
- Full feeds are relatively large; cadence/source-pressure policy is explicitly
  deferred.
- No hosted PostgreSQL proof was available in this local slice; the migration is
  additive and uses portable SQLAlchemy types, but hosted CI remains an eventual
  PR gate.
- Candidate selection is intentionally simple (today plus recent final correction
  window and suspended rows). Production cadence and orchestration are deferred.

## 25. Proven claims

- Persistent deterministic material fingerprints distinguish meaningful state
  from payload noise.
- First/change/final/correction/no-op/stale/ambiguous/failure classifications
  behave safely and survive restart.
- Live inning, out, pitcher and event progression is detectable.
- Finality delegates to the existing authority.
- One bounded slate cycle has explicit request accounting and no loop.
- No canonical reliever, historical, publication, scheduler or frontend state is
  mutated.

## 26. Unproven claims

- Naturally observed live transitions, suspended/resumed transition and official
  post-final correction.
- Production polling cadence, automatic routing to CU-01, impacted-domain
  orchestration, recomputation and publication.
- Long-duration source pressure and operational latency under an actual recurring
  production job.

## 27. Final verdict

**PASS — CU-02 ACCEPTED**

The evidence supports the CU-02 acceptance statement within its bounded
non-authoritative scope. Controlled proofs are labeled and are not presented as
natural historical observations.

## 28. Exact recommended next slice

**CU-03 — Change-to-Impact Orchestration:** consume accepted changed-game results
and decide which canonical/derived domains require work, initially in shadow.
It must not be started as part of CU-02, and scheduling/cadence remains a separate
explicit production decision.
