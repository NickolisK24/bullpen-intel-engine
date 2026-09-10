# CR-04 Controlled Integration Deployment and Atomic Publication Cutover

## 1. Objective

CR-04 deploys the reviewed integration branch into a controlled recurring Render
path, proves production queue execution, and permits SP-11 publication and reader
cutover only after every publication precondition passes. The resumed proof closed
the original Render-control blocker, but found a finality defect and a publication
readiness blocker. Publication and reader cutover remain fail-closed.

## 2. Starting Integration SHA

`63f87feb421eb446fae09d28ab86390ecbbbb8ed`

## 3. Production Deployment Before

The first CR-04 inspection found the API and all primary legacy cron services on
`main`. The dedicated shadow cron also ran `main` with the legacy
`shadow_full_chain` command, producing only `kill_switch_disabled` outcomes.
Legacy scheduling, publication, and public reads were the sole authority.

## 4. Deployment Strategy and Identity

The existing isolated shadow cron was manually repointed. This preserved its
production database/config wiring and avoided a second recurring shadow service.
The API and all legacy primary services were left on `main`.

Dedicated cron `crn-da98kclg1s2s739k0870` now has:

* branch `feat/sync-pipeline`;
* schedule `*/3 * * * *`;
* command `python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation`;
* integration commit `63f87feb421eb446fae09d28ab86390ecbbbb8ed`;
* original repoint deploy `dep-dahc0pm1egvs73der6r0`;
* live environment-control deploy `dep-dahc5i15efls73dfnub0`, completed at
  `2026-09-10T14:46:56Z`.

Render independently reports the service as unsuspended, auto-deploying from the
integration branch, and last successful at `2026-09-10T15:33:29Z` during this
proof window.

## 5. Recurring Shadow Proof

The first scheduled invocation at `14:45Z` failed closed because the runtime
flags were false. Only the seven documented sync controls were then changed:

* `SYNC_PIPELINE_ENABLED=true`;
* `SYNC_PIPELINE_SHADOW_MODE=true`;
* `SYNC_PIPELINE_PUBLICATION_ENABLED=false`;
* `SYNC_PIPELINE_MORNING_ENABLED=false`;
* `SYNC_PIPELINE_CLOSURE_ENABLED=false`;
* `BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true`;
* `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true`.

Subsequent scheduled, non-manual cycles reported entrypoint
`production-shadow-v2`, code SHA `63f87feb421eb446fae09d28ab86390ecbbbb8ed`,
configuration fingerprint
`d8ad84b7cb39adce4fdb2222ca7e144614b3dea2cb7fb20c1af6385c9ce84be9`,
and no `kill_switch_disabled` result. Qualifying successful completions include:

| Completion UTC | Result | Representative SP-02 work |
|---|---|---|
| `2026-09-10T14:48:51Z` | success | jobs `568-579`, 12 final jobs settled |
| `2026-09-10T14:54:53Z` | success | jobs `592-603`, 12 final jobs settled |
| `2026-09-10T14:57:44Z` | success | jobs `604-615`, 12 final jobs settled |
| `2026-09-10T15:00:45Z` | success | jobs `616-627`, 12 final jobs settled |
| `2026-09-10T15:12:49Z` | success | jobs `676-687`, 12 final jobs settled |
| `2026-09-10T15:33:26Z` | success | bounded downstream queue progress |

The entrypoint's fail-closed assertion proves the runtime flag combination and
the single migration head `c9d4e6f8a1b2` from inside execution.

## 6. Queue Health and Steady State

Across the first three successful cycles, `reconcile_final_game` pending work
fell from `129` to `81`, while each completed final job created its bounded SP-09
successor. Later cycles continued that conversion. At `15:33Z`, total pending
work in the visible families stayed constant across the cycle:

* before: pregame `7`, schedule `3`, impact `54`, derived `157`;
* after: pregame `7`, schedule `3`, impact `66`, derived `145`;
* retry-wait: `0` after governed repair;
* stale leases: `0` in captured health;
* the one durable dead row is resolved audit history, described below.

This is bounded progress rather than uncontrolled growth: 12 derived jobs were
consumed while existing obligations advanced between stages. The queue is not
yet drained, so production publication remains premature.

## 7. Roster and Observation Health

Every captured recurrent report retained active-roster authority `30/30` and
40-man authority `30/30`, with no missing, partial, failed, stale, or suspicious
empty team. Morning authority is rooted at SyncRun `6888` and source observations
`84-212`.

CR-02 semantics also remained intact. The `15:21Z` verification run recorded one
stale, three duplicate, and three warning observations, with zero blocking
ambiguities and zero source failures. Continuous SyncRun `7177` remained complete.

## 8. Historical Retry Resolution

Production evidence identified three rescheduled games whose MLB schedule query
returned both an original postponed row and a later Final row:

| Original job | gamePk | Baseball date | Initial state |
|---|---:|---|---|
| `550` | `823539` | `2026-08-29` | retry-wait |
| `584` | `824911` | `2026-08-31` | retry-wait |
| `637` | `824424` | `2026-09-04` | retry-wait, then dead after attempt 3 |

The SP-07 selector had filtered only by gamePk and rejected the two-row response.
It now also requires the requested baseball date and safe Final classification.
Workflow run `34494485601` proved jobs `550` and `584` succeeded through SP-07.

The terminal third job was not revived or edited. SP-13 targeted repair request
`1` dispatched SP-07 job `996`; workflow run `34496255700` completed it at
`2026-09-10T15:32Z`, creating current final-game version `192` for game `824424`.
Health retains dead job `637` as immutable audit evidence and links it to
`resolved_by_job_id=996`; `blocking=false`, `blocking_dead_jobs=0`, and
`retry_wait_jobs=0`.

## 9. Publication Preconditions

| Precondition | Verdict | Evidence |
|---|---|---|
| Recurring Render integration execution | PASS | dedicated cron and natural three-minute cycles |
| Exact deployed SHA | PASS | runtime SHA `63f87f...8ed` |
| At least three successful cycles | PASS | six examples above |
| Stable bounded queue | PASS with backlog | stage-to-stage progress; no retry growth |
| Active and 40-man rosters | PASS | `30/30`, no incomplete teams |
| No dead required work | PASS | job `637` resolved by job `996` and final version `192` |
| No unreconciled Final | PASS | health count `0` after repair |
| Naturally complete SP-10 cohort selected for publication | BLOCKED | downstream backlog remains; no current cohort was selected and revalidated as the first complete generation |
| Duplicate-writer safety | PASS for pointer ownership | only SP-11 owns `atomic_publication_current`; legacy publication does not write it |
| Publication-bound consumer and rollback code deployed | BLOCKED | public API remains on `main` and legacy readers; no current atomic generation exists |

The two critical failures stopped publication activation as required.

## 10. First Atomic Publication and Natural Lineage

Not attempted. `SYNC_PIPELINE_PUBLICATION_ENABLED` stayed false, every captured
`publication_pointer_before` and `publication_pointer_after` was null, and health
still has `current_publication_id=null`. There is no publication, artifact,
predecessor, or pointer transition to claim.

Natural production work reached source/canonical mutation, SP-09 plans, and SP-10
shadow cohorts before and during CR-04. The required natural
Final-to-SP-11-to-pointer chain remains blocked at the controlled publication
checkpoint. Fixture evidence is not substituted for production proof.

## 11. Consumer Audit and Reader Migration

Team Board, Today, league/dashboard, Tonight/matchup, pitcher, What Changed, and
share reads remain on their established legacy identities. The SP-11
`read_current_publication_bundle()` primitive resolves one pointer and generation,
but no public handler uses it because no complete current atomic generation exists.

`SYNC_PIPELINE_ATOMIC_READS_ENABLED` was intentionally not introduced or enabled.
The required order is generation first, dual-read parity second, then the
one-lookup reader and rollback control. Implementing a resolver against a null or
unproven generation would weaken availability rather than prove coherence.

## 12. One-Lookup, Team Board Race, and League Coherence

SP-11's internal bundle remains generation-bound, but production consumer proofs
were not attempted after the checkpoint failed. Therefore:

* the PostgreSQL N-to-N+1 request race remains unproven for public handlers;
* 30-team atomic-generation coherence remains unproven;
* production inheritance remains unproven;
* team, pitcher, game, and league response publication IDs remain unavailable.

These are active CR-04 blockers, not deferred success claims.

## 13. Parity, Request-Time Writes, Share, and Cache

No production dual-read parity window was opened. Legacy responses remain the
only request-visible baseline. No new request-time authority write was introduced;
existing legacy builders and mutable compatibility reads remain in use. Existing
share artifacts remain immutable under their legacy snapshot identity.

No shared SP-11 cache adapter is configured. The governed state remains
`not_configured`; no cache infrastructure was invented and no cache handoff ran.

## 14. Failure and Recovery Changes

CR-04 adds bounded health visibility for retry-wait/dead jobs without exposing
payloads or secrets. A dead final job is operationally nonblocking only when a
later succeeded SP-07 job for the same game/date exists and a current final
version is present. The original dead record remains queryable.

The manual `repair_final` workflow creates an SP-13 request, dispatches the SP-07
owner job, drains only the established non-publishing shadow allowlist, and
captures read-only health. It requires explicit date, gamePk, reason, and
`confirm_recovery=RECOVER`. It cannot publish.

## 15. Rollback

The current non-public deployment can be rolled back without data deletion:

1. Set `SYNC_PIPELINE_PUBLICATION_ENABLED=false` and leave atomic reads disabled.
2. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` on the
   dedicated cron, or repoint/suspend only that cron.
3. Keep `BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true` and
   `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true`.
4. Verify the API still resolves the legacy snapshot identity.
5. Retain all observations, versions, plans, cohorts, repairs, and job evidence.

No migration downgrade, pointer edit, or evidence deletion is required.

## 16. Remaining Certification Blockers

1. Merge/redeploy the reviewed rescheduled-final selector and terminal-job
   observability into the recurring integration service.
2. Drain/reconcile the bounded impact/derived backlog and select a naturally
   complete current SP-10 cohort for the first controlled publication.
3. Produce the first natural SP-11 publication and atomic pointer transition.
4. Implement and deploy the single atomic-read control only after that generation
   exists.
5. Prove Team Board N-to-N+1 race safety, league inheritance/coherence, production
   API publication identity, representative parity, performance, and rollback.
6. Capture a natural live-to-final supersession if MLB timing provides one.

These remain CR-04 work. They are not represented as CR-05 work.

## 17. Validation

Local targeted validation after the finality and health changes:

* `python -m pytest backend/tests/test_sync_pipeline_certification.py backend/tests/test_final_game_reconciliation.py -q`
* result: `34 passed, 1 skipped`;
* `git diff --check`: clean apart from expected Windows line-ending notices.

Production/read-only evidence includes Render service/deploy inspection, scheduled
logs, workflow runs `34493590791`, `34494485601`, `34494945292`, `34495603375`,
`34496018632`, and `34496255700`, and their retained artifacts. CI status belongs
to the exact final branch SHA and is recorded in the PR.

## 18. Verdict

`BLOCKED`. The original Render recurrence blocker is closed, roster and observation
health remain sound, and historical finality debt is governed and resolved. The
mandatory publication checkpoint still fails because a complete natural current
cohort has not been selected/revalidated and the public API has no deployed
atomic-generation reader. Publication, pointer activation, and reader migration
were correctly not attempted.
