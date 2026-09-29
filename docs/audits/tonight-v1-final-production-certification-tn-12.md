# Tonight v1 final production certification (TN-12)

## Scope

TN-12 certifies the Tonight v1 system as it runs in production after TN-11.8. It
is an audit, not a feature package:

- no schema, scheduler, plan or publication changes;
- no production sync, recovery or writes.

| Item | Value |
| --- | --- |
| System under test | `main` at `36c197536f44b7765b4746579450f715ab52785f` (merge of #893, TN-11.8) |
| Production deploy evidence | Runs #737 (`recovery_daily`) and #738 (`recovery_morning`) on `36c1975` |
| Code changes | None to production code. One new certification test module and its shard-manifest entry. |
| Certification defects found | None. Three first-draft authoring errors were fixed in the new tests themselves (see "Test authoring notes"). |

## Architecture certified

| Concern | Authority |
| --- | --- |
| Bullpen state | The current trusted (published, ready) Dashboard snapshot. |
| Presented baseball day | The ET product day: `product_current_date()` for serving, `scheduled_for` in ET for governed runs. |
| Edition identity | `(reference_date, dashboard_snapshot_id, contract='tonight_v1')`, unique. Guarded by `TonightPublicationImmutable` on update. |
| Serving | `services/tonight_v1_serving.py`. It selects `(current date, trusted snapshot)`, fails closed, and never builds or writes. |
| Live game state | A read-only overlay from `slate_games`, limited to the permitted fields. Terminal states never regress. |
| Production | Daily and Postgame ensure the publication edition and the current-date edition. Morning and `recovery_morning` ensure the current-date edition. Production is reported only and never gates sync success. |
| Legacy `tonight_v5` | An explicit, deprecated public compatibility surface. It has no internal, scheduler, publication, frontend or static-generator consumers. |

## Certification matrix

Test counts are collected test functions. Parametrized cases expand further at
run time.

| Row | Requirement | Evidence | Result |
| --- | --- | --- | --- |
| A | Authority: the trusted snapshot supplies bullpen state; the ET product day supplies the date | `test_tonight_v1_serving.py::test_serving_selects_the_current_date_edition`, `test_no_trusted_publication_fails_closed`, `test_same_date_multiple_snapshots_serve_only_the_trusted_one`; `test_tonight_v1_date_rollover.py::test_lane_reference_date_is_the_intended_eastern_date` | PASS |
| B | Publication identity is complete and self-consistent | `test_tonight_v1_production_certification.py::test_b_publication_time_edition_identity_is_complete`, `test_b_rolled_forward_edition_identity_is_complete` (contract, dates, snapshot and sync IDs, recomputed `content_sha256`, ETag, identity headers, body equals the stored payload) | PASS |
| C | Immutability | `test_tonight_v1_date_rollover.py::test_stored_edition_refuses_in_place_updates`, `test_ensure_for_date_creates_then_reuses_and_never_overwrites`; `test_tonight_v1_read_model.py::test_storage_is_immutable_and_publication_bound` | PASS |
| D | The overlay changes only permitted fields; terminal states never regress | `test_tonight_v1_production_certification.py::test_d_overlay_changes_only_permitted_fields`, `test_d_terminal_states_never_regress`; `test_tonight_v1_serving.py::test_newer_regressing_source_keeps_the_frozen_state_as_a_conflict`, `test_stale_source_never_regresses_the_frozen_state`, `test_game_moved_to_another_date_is_not_overlaid`, `test_new_unrelated_game_pk_is_never_inserted` | PASS |
| E | Normal slate | `test_tonight_v1_read_model.py` (77), `test_tonight_v1_serving.py::test_current_v1_hit_serves_the_stored_row` | PASS |
| F | Mixed lifecycle (scheduled, live, final and postponed on one slate) | `test_d_overlay_changes_only_permitted_fields` (live, final and postponed transitions on one edition); `test_tonight_v1_serving.py::test_each_state_transition_changes_the_etag`, `test_summary_recounts_only_games_by_state`; frontend `tonightSlateLifecycle.test.mjs`, `tonightFeaturedLifecycle.test.mjs` | PASS |
| G | All final | `test_d_terminal_states_never_regress`; frontend `tonightSlateLifecycle.test.mjs` | PASS |
| H | Off-day | `test_tonight_v1_read_model.py::test_off_day_is_an_empty_slate`; `test_tonight_v1_serving.py::test_off_day_payload_serves_normally`, `test_off_day_performs_no_schedule_query` | PASS |
| I | Off-day → game-day rollover | `test_tonight_v1_date_rollover.py::test_off_day_to_wild_card_day_rolls_forward_without_republishing`; production run #738 (below) | PASS |
| J | Game-day → off-day rollover | `test_tonight_v1_date_rollover.py::test_wild_card_day_to_off_day_gets_an_empty_edition`, `test_multi_day_jump_creates_only_the_requested_date` | PASS |
| K | Postseason | The rollover suite uses the Wild Card slate shape; production run #738 created the four-game Wild Card edition. | PASS |
| L | Cancelled or postponed game | `test_slate_coverage_cancelled.py` (17); `test_tonight_v1_serving.py::test_postponed_and_doubleheader_pass_through_unchanged`; the postponed transition in `test_d_overlay_changes_only_permitted_fields` | PASS |
| M | A publication failure creates no edition and changes nothing | `test_tonight_v1_production_certification.py::test_m_withheld_publication_creates_no_edition_and_changes_nothing`; `test_tonight_v1_date_rollover.py::test_ensure_for_date_skips_without_a_trusted_publication_or_date`, `test_ensure_for_date_never_raises` | PASS |
| N | A missing current-date row fails closed with no yesterday fallback | `test_tonight_v1_serving.py::test_current_v1_missing_fails_closed`, `test_stale_row_for_an_older_snapshot_is_never_current`, `test_v1_missing_writes_nothing`; `test_tonight_v1_date_rollover.py::test_identity_check_rejects_a_row_for_another_date` | PASS |
| O | Daily lane | `test_continuous_production_publication.py`, `test_trusted_publication_rehearsal.py` (publication-edition ensure plus date ensure); production run #737 | PASS |
| P | Morning lane | `test_tonight_v1_date_rollover.py::test_lane_reference_date_is_the_intended_eastern_date`; morning result `tonight_edition` | PASS |
| Q | `recovery_morning` | `test_recovery_morning_is_idempotent_and_never_ingests_or_publishes`, `test_recovery_morning_runs_after_a_satisfied_natural_morning`, `test_recovery_morning_keeps_recovery_governance`, `test_workflow_dispatches_recovery_morning_on_the_morning_path_only`; production run #738 | PASS |
| R | Postgame lane | `test_postgame_*` suites (incident audit, marker lifecycle, progressive readiness, refresh, shadow scope); lane dates in `test_lane_reference_date_is_the_intended_eastern_date` | PASS |
| S | `recovery_daily` | `test_postgame_incident_audit_runtime_recovery.py`, `test_league_team_state_artifact_recovery.py`, `test_workload_recovery_evidence.py`; production run #737 | PASS |
| T | Legacy isolation | `test_tonight_v1_production_certification.py::test_t_legacy_isolation_counts_are_zero` (internal, scheduler, publication, frontend and static-generator consumer counts are all 0), `test_t_public_v5_compatibility_stays_explicit_and_deprecated`; `test_tonight_legacy_backend_retirement.py` | PASS |
| U | Frontend | `npm test`: 1284/1284, including `tonightV1Page`, `tonightV1Hardening`, `tonightRootCutover`, `tonightSlateLifecycle` and `tonightFeaturedLifecycle` | PASS |
| V | Performance: serving is read-only and query-bounded | `test_tonight_v1_production_certification.py::test_v_serve_is_read_only_and_query_bounded` (at most 4 SELECTs, zero writes, no full Dashboard payload read); `test_tonight_v1_serving.py::test_if_none_match_returns_304_without_building`, `test_v1_hit_reads_no_baseball_tables_and_writes_nothing` | PASS |
| W | Memory | `test_daily_publication_memory.py` (15); production allocator policy line in run #738 (below) | PASS (see limitation 1) |

## Local results

| Suite | Result |
| --- | --- |
| `test_tonight_v1_production_certification.py` | 8/8 passed |
| Backend, four CI shards (local Postgres) | Running; see the hosted CI on this PR |
| `scripts/ci_shard.py verify` | PASS (no duplicated or missing files or node IDs) |
| Frontend `npm test` | 1284/1284 passed |
| `git diff --check` | clean |

## Production read-only proof

The sandbox egress policy blocks `baseballos.app`,
`baseballos-api.onrender.com` and the proof blob store (HTTP 403). The proof
below therefore comes from the hosted GitHub Actions logs of production runs,
read without dispatching anything. TN-12 triggered no sync, recovery or write.

### Run #738, `recovery_morning`, 2026-09-29 17:41Z, head `36c1975`

- `process memory allocator policy mmap_threshold_bytes=262144 applied=True reason=none`
- `tonight_v1 date ensure source=incident_recovery snapshot_id=4094 reference_date=2026-09-29 status=created tonight_publication_id=13 game_count=4 data_through=2026-09-27 legacy_tonight_v5=not_generated`
- Attempt 277:
  - intended window `morning:2026-09-29`;
  - outcome `executed`;
  - publication outcome `verified`;
  - `snapshot_before_id` equals `snapshot_after_id` (no republish).
- Schedule: 12 games, window 2026-09-28..2026-10-02, `slate_games_updated=12`.
- The Daily, Postgame and backfill steps were skipped. The recovery never ingested or published.
- Ledger audit: 105/105 games and 942/942 appearances. Publish eligible.
- Dashboard verification: snapshot 4094, `data_through` 2026-09-27.

### Run #737, `recovery_daily`, 2026-09-29 17:31Z

- Daily was already satisfied: the artifact gate reported `already_complete` for 30 artifacts on snapshot 4094 (sync run 92993).
- Team State proof was exported, and the forbidden-content scan passed.
- Team State vNext proof: `PASS_WITH_INCONCLUSIVE`:
  - 30 teams, postcommit `proof_valid`;
  - distribution: 6 Fresh, 13 Stretched and 11 Vulnerable;
  - the only inconclusive invariant is `no_false_cross_version_change`, because this was not a cross-version publication.
- The only failed job was the observational shadow-activation-health job, which does not change the publication-critical result.

### Consistency

- Tonight identity is `(2026-09-29, 4094, tonight_v1)`: 4 games, `data_through` 2026-09-27.
- The Sep 28 row `(2026-09-28, 4094)` was left unchanged. Creation never overwrites (row C).
- The trusted Dashboard snapshot 4094 was not republished or re-dated.

## Limitations (non-blocking, not expanded here)

1. **Memory.** CI cannot measure the production cgroup RSS, so TN-12 reports no RSS number. The certified evidence is the allocator policy being applied in production and the bounded payload reads and writes proven in `test_daily_publication_memory.py`.
2. **Live endpoint, ETag/304 and frontend.** These were not fetched from production because the sandbox network policy blocks the hosts. The behaviors are certified by the serving and frontend suites (rows B, U and V). A live spot check needs the hosts allowed in the environment's network settings.
3. **Midnight gap (from TN-11.8).** Between ET midnight and the first run of the new day, serving fails closed rather than showing yesterday. This lasts about five minutes in daylight time and up to about an hour in standard time.
4. **Rolled-forward bullpen state.** A rolled-forward edition presents the new day's schedule with the trusted publication's frozen bullpen state, labelled by its `data_through`.
5. **Observational job.** The shadow-activation-health job failure on run #737 is observational and outside the publication-critical path.

## Test authoring notes

Three first-draft errors in the new module were test mistakes, not system defects:

- The overlay test used `'final'` as a `SlateGame.normalized_state`. The vocabulary is `completed`, and serving maps it to `final`.
- The withheld-publication test left its forced slate-coverage gate patched during serving, which invalidated every snapshot. The patch is now scoped to candidate construction only.
- The legacy-isolation scan counted comment lines that record retirements, in `render_start.sh` and `api.js`. It now reads executable lines only.

## Verdict

PASS. Tonight v1 is certified for production on `36c1975`. No certification defect was found, and no production code changed.
