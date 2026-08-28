# CU-02I — Main Integration & Regression Proof

## 1–5. Repository state

- Branch: `feat/game-change-detection`
- Starting/accepted CU-02 HEAD: `4d1dfc9a4b5790ea0ae2f9255b4f47a267ec4ed3`
- Current `origin/main`: `bef64ea2e837d868f220b26627feaf00bd2013e0`
- Merge commit: **not applicable**. Main has not advanced since CU-02 began, so
  creating an empty/unnecessary merge would add no integration evidence.
- Pre-report relationship: one commit ahead, zero behind.
- The accepted CU-02 commit is an ancestor of HEAD. The only pre-existing
  worktree item was untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md`;
  it remained untouched.

## 6. Upstream commit audit

There are **zero** commits on `origin/main` after `bef64ea2`. Therefore there are
no upstream file changes to classify and no Render, workflow, sync, schedule,
finality, feed, marker, fingerprint, ordering, model, migration, database,
shadow, publication, snapshot, Team State, fixture or environment interactions.

Classification: **NO INTERACTION**.

## 7. Conflict resolutions

None. No merge was required or performed.

## 8. Current Render execution map

The accepted Render-era map is unchanged:

| Authority | UTC schedule | Command |
|---|---:|---|
| Render daily | `5 10 * * *` | `run_due_sync.py --mode daily ... --days-back 7 --public-only` |
| Render postgame | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` |
| Render morning | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` |

`run_due_sync.py` validates the durable schedule window, invokes the existing
daily/postgame/morning acquisition and canonical-write paths, then existing
derivation/publication gates. GitHub Actions retains delayed fallback and
reconciliation schedules using the same due-window authority; game-driven
ingestion remains `shadow` where configured. CU-02 changed none of these files.

## 9. CU-02 invocation map

Production search found CU-02 references only in:

`scripts/detect_game_changes.py` -> `detect_active_slate_changes` ->
`observe_game_change` -> `GameObservationState` -> structured result -> **STOP**.

The script disables `AUTO_SYNC` before importing the application. No Render
command, GitHub workflow, `run_due_sync.py`, or `services/sync.py` references the
detector. The detector does not import CU-01, GameLog reconciliation, workload,
read-model, cache or publication services. Result contracts retain empty affected
pitcher/team lists and `downstream_work_triggered=false`.

## 10–11. Alembic integration

No upstream migration exists to merge. The graph has one head,
`c6d8e1f3a5b7`. CU-01 (`b4e7c9d2a1f6`) and CU-02 observation schema are both
preserved. Isolated head-only upgrade, downgrade to `b4e7c9d2a1f6`, and
re-upgrade passed. The known older full-SQLite-chain ALTER limitation was not
modified.

## 12. Exact 15-game replay

The exact 2026-08-25 slate was reacquired from MLB in an isolated SQLite proof
database. All 15 games returned `NEW_GAME` first and `UNCHANGED` on exact replay.
All 15 identities matched gamePk, all persisted an MLB feed timestamp, and all
remained `final_pending_data` under canonical `game_finality` without boxscore
evidence. Persisted row count was 15. No source correction or classification
drift was observed.

GamePks: 824233, 823826, 822693, 823505, 822773, 823585, 824881,
824556, 823016, 823989, 825042, 823259, 824962, 823098, 823181.

## 13. Five-game restart replay

After disposing the engine/application connection and recreating it against the
same proof database, 824233, 823826, 822693, 823505 and 822773 all returned
`UNCHANGED`. Each fingerprint was identical and each upstream ordering timestamp
remained persisted. No in-memory state was required.

## 14. Controlled transition proofs

The focused suite repeated scheduled/new state, out and inning progression,
pitcher change, pitch-event growth, finality transition, newer post-final
correction, stale replay before/after restart, equal/missing-order ambiguity,
weaker authority, delayed/postponed/suspended status, and irrelevant payload
noise. Accepted taxonomy remained unchanged: material non-final `CHANGED`, safe
final transition `FINALIZED`, newer final correction `CORRECTED`, exact/noise
replay `UNCHANGED`, destructive stale/ambiguous/weaker inputs rejected.

## 15. Natural versus controlled evidence

Natural evidence remains limited to finalized-game acquisition and stable source
truth. Exact and restart replay used captured natural payloads. Live progression,
suspension-style states, post-final correction and adverse ordering sequences
remain controlled real-shape proof only. CU-02I does not upgrade those claims.

## 16. Observation-order proof

Same-authority strictly newer MLB `metaData.timeStamp` may replace accepted
material state. Identical fingerprint is a no-op. Older, equal-with-different,
missing-order, incomparable, and weaker-authority evidence cannot overwrite the
accepted row. Local acquisition time is absent from ordering. Restart proof
confirmed persisted ordering.

## 17. Fingerprint proof

The canonical fingerprint still includes baseball identity/status/finality,
inning/count/score/current matchup and stable play-event information. It excludes
local timestamps, response ordering, copyright, `metaData.wait`, notification
arrays and unrelated payload noise. Mapping reorder and noise tests remained
`UNCHANGED`.

## 18. Active-slate selection proof

Candidate tests still select the reference-date slate plus final games inside the
two-day correction window and supported suspended candidates. A game outside the
bounded window was excluded. The detector contains no historical/season scan,
loop, daemon or polling interval.

## 19–20. Zero downstream mutation and sentinels

Before/after tests retained zero changes to GameLog, GamePitchEvent and
ShareArtifact. Call-graph and scheduler searches found no automatic CU-01 handoff.
No Pitcher/team/roster/workload/Team State/read model/snapshot/share artifact/
publication pointer/What Changed/cache state changed. The proof database contained
only 15 CU-02 observation rows. Historical and publication boundaries therefore
remained unchanged.

## 21. Scheduling regression proof

The feature diff against current main contains no `.github` workflow,
`run_due_sync.py`, `services/sync.py`, `SYNC_PIPELINE.md`, Render configuration,
cron expression, worker, daemon or polling change. No existing command is routed
through CU-02.

## 22. Source-efficiency measurements

- Games checked: 15
- First changed/new: 15; exact unchanged: 15
- Source requests: 16 (one schedule plus 15 feeds)
- Redundant acquisition requests: zero in the cycle; replay used captured feeds
- Serialized payload: 12,362,182 bytes total; 824,145.5 bytes/game average
- Detector normalization/reconciliation: 10.03 ms/game average after acquisition

No integration-induced performance difference was observed.

## 23. Focused tests

- CU-02 focused: **19 passed**
- CU-02 plus MLB client and accepted CU-01/shared acquisition/finality/PBP/
  planner/shadow/provenance/scheduling/publication selection: **299 passed**
- Migration upgrade/downgrade/re-upgrade: **PASS**
- CI shard verification: **PASS**, 394 files and 8,990 node IDs exactly once
- Python compilation: **PASS**
- `git diff --check`: **PASS**

## 24. Expanded tests

The accepted schedule/postgame/daily/authority/snapshot/publication group passed:
**519 passed**, with four existing `datetime.utcnow()` deprecation warnings.

## 25. Broader diagnostic

Qualified disposable-SQLite full run: **FAIL (unrelated broader baseline)** —
8,864 passed, 73 skipped, 53 failed in 258.24 seconds. A cached-failure rerun
reproduced the same 53 failures. Clusters were Windows-to-bash temporary-path
handling, CORS/runtime-platform assumptions, historical source-hash and
branch-diff freeze assertions, read-only incident-audit baseline assumptions,
and `/proc` behavior unavailable on Windows. None imports or exercises CU-02;
all 19 focused, 299 shared and 519 expanded governed selections remained green.
No newly consistent CU-02 integration regression was found. These failures were
not fixed because doing so would widen this task.

## 26. Remaining known gaps

- Natural live, suspension/resumption and post-final correction transitions are
  still unobserved.
- Hosted PostgreSQL validation remains a later PR gate.
- Production cadence, automatic CU-01 handoff and downstream impact routing are
  deliberately absent.
- The broader Windows diagnostic retains 53 unrelated failures described above.

## 27. Proven claims

Current main introduces no integration delta. CU-02 retains durable restart-safe
observation state, source-aware partial ordering, stable material fingerprints,
bounded selection, exact real-game replay, controlled transition safety, zero
downstream mutation, zero publication/history mutation and zero scheduling change.

## 28. Unproven claims

Natural live/correction edge cases, production recurring operation, hosted
PostgreSQL behavior and CU-03 impact orchestration remain unproven/unimplemented.

## 29. Final verdict

**PASS — READY FOR MAIN**

## 30. Recommended repository integration action

Run a separate merge task: push `feat/game-change-detection`, open a PR to
`main`, require hosted PostgreSQL and required CI, audit the final diff, and merge
with a normal merge commit while preserving `4d1dfc9a`. Do not deploy manually or
change scheduling as part of that repository merge.

## 31. Exact next slice after repository merge

Only after CU-02 is safely merged: **CU-03 — Change-to-Impact Orchestration**, as
a separate shadow/non-authoritative slice. It is not started here.
