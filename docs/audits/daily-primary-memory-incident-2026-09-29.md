# Daily Primary OOM during publication (2026-09-29)

## Incident

On 2026-09-29, Render's **BaseballOS Daily Primary** cron (0.5 CPU, 512 MiB) was
killed with `Out of memory (used over 512Mi)`. The run started at 10:05 UTC as
SyncRun 92990.

- Ingestion, the API calls and fatigue recalculation all completed normally.
- The run then entered `sync_completion_snapshot_publish`.
- Dashboard payload assembly finished in about 40.6 s.
- The process died shortly after that.

The SyncRun was later reclaimed as abandoned
(`failed_stage=fatigue_recalculation`, `published_dashboard_snapshot_id=null`).
That record is a secondary effect:

- `set_sync_stage(fatigue_recalculation)` is the last stage that was committed.
- The publication step writes its stage with `commit=False`.
- The publication transaction never committed, so the process died **before**
  the publication commit.

## Call path from the end of ingestion to process exit

```
run_due_sync -> sync_due._run_daily -> sync.run_daily_sync
  recalculate_all_fatigue                       (commit; stage=fatigue_recalculation)
  sync_completion_snapshot_publish
    sync.complete_sync_run_with_snapshot        (finish_sync_run commit=False)
      dashboard_snapshot.build_bullpen_dashboard_snapshot
        public_serving_authority.trusted_dashboard_builder
          api.bullpen.build_bullpen_dashboard_payload
            _served_score_cutoff x1, _dashboard_capacity/_stability (stale_history per team)
          attach_frozen_team_boards -> build_frozen_team_board_package (30 teams)
        dashboard_snapshot.store_dashboard_snapshot
          _json_payload (json.loads(json.dumps(payload)))     full copy #2
          INSERT dashboard_snapshots (payload ~16.5 MB)        serialization #1
          publish_dashboard_snapshot
            bind_comparison_identity (deepcopy(payload))      full copy #3   <- fixed
            require_transactional_publication_proof           (30 teams)
              resolve_team_readiness_payload
                -> build_team_roster_authority (api layer)
                     _served_score_cutoff (full row, 16.5 MB)  x~66  <- fixed
                     _reliever_population_rows -> stale_history
              updated_payload (receipts)
              attach_frozen_what_changed (3 nested deepcopies) full copies #4-6 <- fixed
              autoflush UPDATE dashboard_snapshots payload     serialization #2   [PEAK]
      db.session.commit()                          <- never reached on 2026-09-29
      run_post_commit_snapshot_publication
        capture_publication_proof -> generate_team_state_artifacts_batch (30 teams)
        generate_tonight_v1_after_publication
      league_team_state_artifact_recovery.require_complete_artifact_set
```

## Measurement

`backend/scripts/daily_publication_memory_harness.py` seeds a disposable
Postgres database with a production-shaped fixture:

- 30 MLB teams, 960 pitchers (5 SP, 9 RP and 18 depth arms per organization)
- 36,264 GameLogs across two seasons
- 3,858 scheduled or final games
- a week of fatigue history (6,720 rows)

It then runs the real Daily path twice (`recalculate_all_fatigue`, then
`complete_sync_run_with_snapshot` under production publication config):

- The first run creates the prior trusted publication.
- The second is the measured publication.

Peak RSS is VmHWM, reset per run. The trusted Dashboard payload is 16.5 MB of
JSON, about 40 MB as Python objects. The Team Board package is 15.1 MB of it
(about 500 KB per team).

An RSS timeline sampled every 20 ms located the peak inside the publication
transaction, at the proof-tail UPDATE flush. In a fresh process on `main`:

| Phase (fresh process, main) | RSS |
| --- | --- |
| before publication | 134 MB |
| payload assembled + 30 Team Boards | 170 MB (+36) |
| JSON round-trip copy | 194 MB (+24) |
| INSERT flush of the 16.5 MB payload | 298 MB (+104, retained) |
| `bind_comparison_identity` deepcopy | 324 MB (+26) |
| Team State proof per-team loop (30 teams) | 327 MB (+3, flat) |
| proof tail: `attach_frozen_what_changed` (3 deepcopies) + UPDATE flush | **406-414 MB** |

The per-team proof loop is flat and the SQLAlchemy identity map stays at 2
objects, so neither stale_history nor per-team ORM growth drives the peak.

## Root cause

Several full copies of the multi-megabyte Dashboard payload were alive at the
same time inside the publication transaction. On top of that, the payload was
serialized twice, and glibc kept each freed serialization buffer resident.

1. **Whole-payload deep copies that were never needed.**
   - `bind_comparison_identity` deep-copied the entire payload to rewrite one
     comparison block.
   - `attach_frozen_what_changed` deep-copied the payload, then the Team Board
     package again, then the team map a third time, just to add one key per
     team.
   - Together these held about 110 MB of simultaneous copies at the peak.
2. **Served-score-cutoff lookups parsed the full payload.**
   - `api.bullpen._served_score_cutoff` loaded the whole `DashboardSnapshot`
     ORM row.
   - The Team State proof resolves Roster Authority through the API-layer
     `build_team_roster_authority` about twice per team, which is 67 lookups
     per publication.
   - 60 of those returned the in-transaction candidate, so psycopg2 parsed
     its 16.5 MB payload 60 times inside the peak window.
   - Each parse cost up to about 55 MB transient, plus about 16 s of CPU.
3. **Allocator retention.**
   - Each 16.5 MB write builds about 66 MB of transient buffers (`json.dumps`
     str, then psycopg2's encoded, escaped and interpolated copies).
   - After the first large free, glibc's dynamic mmap threshold moves such
     buffers onto the main heap. There the freed space stays resident and
     fragments.
   - As a result the INSERT's buffers (+104 MB) were still resident when the
     UPDATE needed its own.

Production's larger history and pre-publication heap from ingestion put the
same growth (+280 MB in the harness) over 512 MiB.

## Fix

No baseball semantics, publication gates, Team State, Tonight v1, schedule
authority or trust rules changed. The digest-pinned `dashboard_snapshot.py`
(and every other `INCIDENT_CANONICAL_MODULE_DIGESTS` module) is byte-identical
to `main`.

| Change | File | Effect |
| --- | --- | --- |
| Payload-free cutoff | `services/dashboard_source_cutoff.py` (new), `api/bullpen.py` | Same query, filters and ordering as `get_latest_dashboard_snapshot`. Selects metadata plus `payload->'freshness'` and applies the same `snapshot_current_enough`. Same `SQLAlchemyError` behavior: rollback, warn, `None`. |
| Structural sharing in comparison binding | `services/what_changed_comparison_identity.py` | Copies only the containers it writes. Output is equal to the deep-copy version. |
| Structural sharing in frozen What Changed | `services/team_board_what_changed.py` | Copies only the payload, package, team map and team entries it writes. Output is equal. Malformed entries still fail the same way. |
| Allocator policy | `services/process_memory.py` (new), `scripts/run_due_sync.py` | `mallopt(M_MMAP_THRESHOLD, 256 KiB)` once at the due-sync entrypoint, so large buffers are unmapped on free. No data effect. `BASEBALLOS_MALLOC_MMAP_THRESHOLD=off` disables it. No-op off glibc. |
| Memory telemetry | `services/sync.py`, `services/public_serving_authority.py` | Seven concise checkpoint lines per Daily run (below). |

The API-layer `build_team_roster_authority` stays the Roster Authority
primitive used by the proof. Moving that recipe into a pure service is a
larger refactor with semantic risk, and it is not needed once its cutoff
lookup stops reading the payload.

### Measured result (same fixture, same machine)

| | main | fix | change |
| --- | --- | --- | --- |
| Peak RSS, fresh process (fatigue + publication) | 411-412 MB | **274 MB** | -138 MB (-33.5%) |
| Peak RSS, warm process (second publication) | 428-429 MB | **286-291 MB** | -140 MB (-32.5%) |
| Publication growth over starting RSS (fresh) | +279 MB | +143 MB | -49% |
| End RSS after publication (warm) | 364 MB | 218 MB | -146 MB |
| Publication wall time | 63-67 s | 42-45 s | -21 s |
| SQL statements | 5,160 | 5,160 | 0 |
| Full-payload `dashboard_snapshots` SELECTs | 133 | 66 | -67 |
| Source-snapshot lookups (count) | 67 | 67 | same rows, 16.5 MB → ~1.4 KB each |
| stale_history reads (rows) | 148 (50,544) | 148 (50,544) | unchanged; not a peak driver |
| Dashboard payload writes | 2 | 2 | unchanged; pinned module |

Decomposition (fresh / warm peak):

| Variant | Fresh peak | Warm peak |
| --- | --- | --- |
| main | 412 MB | 429 MB |
| code fixes only | 312 MB | 329 MB |
| code fixes + allocator policy | 274 MB | 286-291 MB |

## Parity

On the same fixture, `main` and the fix produced byte-identical normalized
dumps of:

- the Dashboard payload (all domains except the Team Board package)
- the Team State publication proof

They also produced identical digests of:

- every per-team Team Board
- Team State receipts and per-team state
- rest status and recent usage
- rotation context
- What Changed (league and per-team frozen carriers)
- all 30 Team State artifact payloads
- the tonight_v1 payload

`data_through` matched as well.

Normalization drops only wall-clock and identity fields:

- `*_at`
- `last_*sync`
- ids
- the proof's per-run artifact inventory digest, which hashes random public
  ids and timestamps

The 67 cutoff lookups resolved to the same snapshot ids before and after.

## Regression guards (CI)

`tests/test_daily_publication_memory.py` (shard 3, 32 tests):

- **Cutoff matrix (11 scenarios).** The projection selects exactly the
  snapshot the full-row ORM path selects:
  - valid, latest-of-two, incomplete coverage, coverage-date mismatch
  - data-through mismatch, missing freshness, fail-closed stale
  - unpublished or pending newer candidates, version mismatch
- **Cutoff edge cases.**
  - An in-session unflushed candidate is seen identically (autoflush parity).
  - A database error still rolls back and yields `None`.
  - The cutoff SQL never selects the payload column.
- **Structural sharing.** `bind_comparison_identity` and
  `attach_frozen_what_changed` equal the verbatim deep-copy reference
  implementations across all branches. They leave their inputs and the
  previous snapshot unmutated, and share untouched domains.
- **Allocator policy and telemetry.**
  - The policy is applied once and can be disabled.
  - It never raises without mallopt.
  - The entrypoint applies it before the app import.
  - Checkpoint lines have the expected format.
- **End-to-end guard.** A small fixture runs the real Daily completion path
  twice with proof, artifacts and tonight_v1. It asserts:
  - a trusted publication with 30 boards, 30 artifacts, proof and tonight_v1
  - exactly 2 Dashboard payload writes
  - full-payload SELECTs ≤ 70; `main` does 130
  - all six publication telemetry phases present

Every structural guard was run against the reverted pre-fix code and failed
there.

## Production telemetry

Each Daily run now logs:

```
daily_sync memory checkpoint phase=daily_start rss_mb=… peak_rss_mb=…
daily_sync memory checkpoint phase=publication_before rss_mb=… peak_rss_mb=… sync_run_id=…
dashboard_snapshot memory checkpoint phase=dashboard_payload_after rss_mb=… peak_rss_mb=…
dashboard_snapshot memory checkpoint phase=team_boards_after rss_mb=… peak_rss_mb=…
daily_sync memory checkpoint phase=publication_committed rss_mb=… peak_rss_mb=… snapshot_id=…
daily_sync memory checkpoint phase=post_publication_hooks_after rss_mb=… peak_rss_mb=… snapshot_id=…
daily_sync memory checkpoint phase=artifact_gate_after rss_mb=… peak_rss_mb=… snapshot_id=…
daily_sync memory checkpoint phase=daily_final rss_mb=… peak_rss_mb=… status=…
process memory allocator policy mmap_threshold_bytes=262144 applied=True reason=none
```

`peak_rss_mb` at `publication_committed` is the publication high-water mark.
Postgame runs through the same completion path, so it logs the publication
checkpoints under `job=postgame_refresh`.

## Render plan decision

**512 MiB is sufficient after the fix (A).** No plan change is made in code.

- On `main` the harness grows +279 MB through publication. Production exceeded
  512 MiB with that growth.
- The fix removes about 138-140 MB of peak and halves publication growth.
- The removed copies scale with payload size, so production's larger payload
  benefits at least proportionally.
- The allocator policy also lowers the resident heap carried in from
  ingestion.

Confirm on the next natural Daily Primary. If `peak_rss_mb` at
`publication_committed` exceeds about 430 MB, treat 512 MiB as marginal (B)
and move to 1 GiB.

## Remaining limitations

- `dashboard_snapshot.py` (digest-pinned) still keeps the builder's payload and
  a JSON round-trip copy alive together, and writes the payload twice (INSERT,
  then the pre-trust UPDATE). Removing that needs a governed canonical-module
  change.
- After commit, the Team State artifact batch refreshes the expired publication
  row once per team: 30 full-payload reads, about 20 s. Each read is transient
  and stays below the pre-commit peak.
- stale_history is unchanged:
  - 148 reads per publication, including 4 league-wide ones.
  - Neither peak-relevant nor semantically safe to batch without a Roster
    Authority service extraction.
- The 67 cutoff lookups still run, now metadata-only. Collapsing them needs a
  publication-scoped cutoff whose value may legitimately change when the
  candidate is flushed.
- Harness RSS is local-machine RSS, not Render cgroup accounting. Relative
  before/after is the reliable signal. The natural-run telemetry is the
  production proof.
