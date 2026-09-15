# Final-plan authorization ordering remediation

## Scope and provenance

Branch: `fix/plan-authorization-ordering`. Integration base: `e6b8c6f00d2482b9cb67fd9a23d7d0e76b303e05` (`feat/sync-pipeline`). Production comparison: `d318aae706b83d360d78b30e31dc424f8f614877` (`main`). This is an integration PR, not a production promotion or authorization to merge.

Run 32803 recorded four `plan_fingerprint_derivation_failed` RuntimeErrors for games 822683, 822762, 822849 and 822925. All four job IDs were null. No canonical mutation or publication occurred; Dashboard 2777 stayed unchanged. Stored observations captured by the read-only audit are retained as regression fixtures. The incoming main v1 shape is reconstructed from that capture. Original production exception messages, full plans and stacks were not retained; reconstructed traces must not be presented as historical stacks.

## Exact execution chain before this change

1. `continuous_execution.run_continuous_cycle` invokes `_execute_cycle` under the existing cycle and writer ownership controls.
2. CU-02 detection accepts/classifies observations. `continuous_game_work.ensure_obligations` creates durable work only for accepted finalized/corrected observations in `final_pending_data` or `final_and_usable`. Other changed observations can enter the transient pipeline with no job.
3. `_execute_cycle` defaults transient work to `canonical_pending`. It checks budgets/mode/allowlists before deriving the final plan. Integration additionally claims production durable work before derivation; deployed main derives before claiming.
4. `persist_accepted_final_schedule_authority` runs for applicable durable work, preserving exact accepted-observation, final result, pitching evidence and schedule identity checks.
5. `change_impact_orchestration.derive_current_plan_fingerprint` resolves the accepted observation's official date, then calls `game_driven_ingestion.run_game_driven_ingestion` in `MODE_SHADOW` with `only_game_pks=[game_pk]`.
6. `game_ingestion_planner` checks ledger finality using shared `game_finality` semantics. Non-final requested games are excluded. CU-01 independently recomputes executing versus requested scope before source fetch/write; a missing requested game produces `scope_mismatch`. The bridge raises rather than returning an authorization fingerprint.
7. Only later would `orchestrate_game_change` call `decide_game_change`. For these non-final schema differences, that decision is `no_action / no_final_canonical_action`.
8. For genuinely applicable final/correction work, CU-01 write recomputes the complete reconciliation fingerprint, compares the reviewed fingerprint and enforces existing ownership, finality, correction lineage and mutation fences before canonical persistence. Publication remains downstream and separately gated.

The defect is step 5 preceding step 7. The planner's scope rejection itself is correct.

## Main/shadow semantic comparison

| Concern | Production main | Integration/shadow | Consequence |
|---|---|---|---|
| Non-final normalized observation | v1, no live-pitching projection | v2 with live-pitching appearance/completeness projection | Observation shape/digest can differ without a finality transition. |
| Captured values | Reconstructed omitted section | `appearances=[]`, `completeness=complete_for_observation` | Omitted and empty are different material observation values, not synonyms for finality. |
| Difference paths | `schema_version`, `live_pitching.appearances`, `live_pitching.completeness` | Same paths in reverse projection direction | A `changed` classification is not permission to reconcile a final game. |
| Finality | Shared `game_finality` enum | Same implementation | Both captured shapes resolve `not_final`, stored schedule `scheduled/S`. Neither supplies final pitching evidence. |
| Final/correction scope | CU-03 finalized/corrected decision; exact-one-game CU-01 scope | Same decision and scope | Observation schema metadata cannot broaden canonical scope. |
| Fingerprint | CU-01 complete reconciliation identity | Same reconciliation and pitcher-identity implementations | No hash normalization or fingerprint contract changes in this patch. |
| Source persistence | Legacy observation row | Additional source-observation/outcome metadata and live projection | Metadata IDs and optional live fields are not authorization inputs. |
| Date fallback | Accepted observation official date required | Existing durable job product-date fallback | Existing branch difference preserved, not silently promoted to main. Missing date/evidence still cannot authorize a write. |
| Failure handling | Unclaimed obligation deferred | Claimed integration obligation consumes its governed retry attempt | Existing branch behavior retained for eligible failures; ineligible transient changes reach neither path. |

`game_finality.py`, `game_ingestion_planner.py`, `game_log_reconciliation.py` and `pitcher_identity_reconciliation.py` are byte-identical between the compared base revisions. The CU-03 decision is also identical; the pre-existing bridge difference is the date fallback. Integration's v1-to-v2 equal-revision adoption rule verifies common facts before adopting the live projection; this patch does not weaken that rule, rewrite observation hashes, erase live data, or force both deployments to persist one schema.

## New execution order

`changed candidate / validated obligation -> shared CU-03 final_reconciliation_scope -> existing decision -> eligible exact-game scope -> existing budgets / allowlists / claim -> accepted schedule authority -> plan derivation -> fingerprint -> reviewed authorization -> fenced canonical reconciliation -> existing downstream/publication gates`.

`final_reconciliation_scope` reuses `decide_game_change` and the shared finality enum. Its result is an immutable one-game tuple for applicable final/correction work, or no final scope for existing no-action/deferred/rejected decisions. Missing or unknown finality on a changed accepted observation raises an unavailable error; malformed final scope raises an invalid-scope error. `final_pending_data` remains final-but-unavailable-for-write until existing evidence gates pass, rather than being silently classified as non-final.

Continuous execution resolves this before final-plan reads, source reservation, claims, schedule writes, or retry rotation. The same helper guards standalone fingerprint derivation and orchestration. Downstream/publication checkpoint resumptions retain their existing paths. Shadow-detect still does not authorize/write. A caller-supplied fingerprint cannot bypass the early eligibility boundary.

## Regression coverage

- All four captured observations, reconstructed v1 and retained v2 directions, repeated twice: normal no-action outcome; no fingerprint call, source reservation, claim, canonical writer, mutation, publication, or durable retry amplification.
- Scheduled, live, delayed, suspended, postponed and cancelled status decisions: no final plan; direct misuse of the fingerprint API fails before any plan read.
- Every active runtime mode: same non-final scope result, including when a reviewed fingerprint is supplied.
- Eligible finalized/corrected and pending/usable finality: shared exact-game identity independent of optional schema metadata.
- Real CU-01 planner with an eligible change but incompatible schedule scope: `scope_mismatch` still raises before fetch or mutation.
- Missing finality/date and malformed scope: explicit failure, not success or non-final default.
- Real final-correction plan: bridge fingerprint equals direct CU-01 fingerprint and is deterministic across repeated derivation. Reviewed reconciliation succeeds; subsequent reconciliation is a canonical no-op. This represents run 32702's correction-check behavior, not an invented byte-identical replay of its unavailable full plan.
- Existing canonical-write, correction, shadow/write parity and publication tests remain enabled. Existing P0 history bound, build-scoped baseline, capacity/stability cutoff reuse and durable unchanged-blocker admission tests are unchanged.

## Observability

The existing failure list persisted with cycle metadata now includes run/job/game IDs, classification/finality, eligibility, exact normalized game scope, exception class, authorization stage, safe reason code and actual throw-site file/function/line. The same bounded object is emitted as `plan_authorization_failure` through the existing logger. Known internal errors map to fixed reason codes; arbitrary exception messages, SQL, connection strings, source payloads and serialized plans are not logged. A regression test verifies sensitive-looking exception text is excluded.

## Validation and release boundary

Final focused backend plus egress/finality/reconciliation/parity run: 328 passed, 2 skipped. Earlier authorization/continuous run: 152 passed, 1 skipped. Full local Windows/SQLite run recorded 9,909 passed, 163 skipped and 51 failures; all 51 failing IDs reproduce on the unchanged integration base. CI shard collection accounting passed; no new test module or migration is required. Exact final PR-head CI results are reported with the PR checks and delivery report; passing focused tests alone does not certify release readiness. There is no configured Python lint/type-check tool in this repository; whitespace and Python compilation are checked, alongside the repository's CI jobs.

No egress production implementation, query selector, admission receipt, migration, frontend contract, ownership fence or publication gate is changed. The original unrelated workspace drift is preserved.

Do not merge automatically. After integration review and full green CI, use a dedicated main-owned promotion and rerun CI against that actual production base. Preserve main's existing claim/date behavior when applying this narrow patch. No migration is needed. Do not manually retry jobs or touch exhausted obligations. Verify natural non-final short-circuits and eligible final/correction authorization after deployment, while continuing separate egress billing and publication proof. The later game 824465 ValueError, which recovered naturally, is not explained or claimed fixed by this ordering change.
