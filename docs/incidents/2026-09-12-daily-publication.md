# September 12 production currentness incident

Maintainer: Nikko. Severity: P1. Investigation checkpoint: September 12, 2026, evening EDT. Recovery is not yet proven.

## Root cause and distinct failures

The public MLB directory inferred valid clubs from every active pitcher's stored team ID. The shared database also contains affiliate assignments. Production had all 30 canonical MLB clubs plus IDs 484, 531, 534, and 5434, with 56 active pitcher rows across those four extra IDs. The mandatory Team State publication proof correctly rejected this 34-team universe. The error occurred after acquisition and fatigue processing, during the transactional publication boundary; it was not an upstream API outage or a migration-startup failure.

The two failed Daily Primary executions were on consecutive mornings, not two September 12 attempts:

| Intended UTC window | Render instance | Schedule attempt / SyncRun | First actionable failure |
|---|---|---|---|
| September 11 10:05 (06:05 EDT) | crn-da8f605g1s2s73983o1g-b7k95 | 116 / 11073 | 10:06:11.305496 UTC: `Roster snapshot team conflict for same pitcher/date`; 42 records dead-lettered |
| September 12 10:05 (06:05 EDT) | crn-da8f605g1s2s73983o1g-vxw4q | 124 / 18263 | 10:09:18.128 UTC: `team_state_publication_proof_requires_exactly_30_teams` |

Render reports September 11 duration 5m53s and September 12 duration 6m04s. Exit-status-1 messages occurred at 10:11:03.914704 UTC and 10:11:14.470544 UTC respectively. The connector and Runs UI expose instance IDs/time ranges, not a separate stable cron-execution job ID; log event IDs are not execution IDs.

The first September 11 conflict is failure 13372, pitcher 194 / MLB 807743, existing team 115 versus incoming team 342. These are competing MLB/affiliate scopes for the same pitcher/date. The 42 original failures are now resolved; that does not retrospectively make their daily run successful.

September 12 GitHub fallback run [34696922430](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/34696922430), public-sync job 103561874375, reproduced the team-count failure at 13:57:06 UTC. Its durable attempt is 125 / SyncRun 18456. It started at 13:37 UTC, over three hours after its intended 10:17 UTC fallback window. The downstream missing-proof-artifact error was secondary.

## Deployment and change correlation

Daily Primary is `crn-da8f605g1s2s73983o1g`, repository `NickolisK24/bullpen-intel-engine`, branch `main`. Its September 12 deployed commit is `04adf7932416136bb220ffcb207f84c6e6e17acc`, deploy `dep-dai71thsrm7s738ddnvg`, live September 11 at 21:22:23 UTC. September 11 ran the earlier `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65` deployment.

The integration shadow service is `crn-da98kclg1s2s739k0870`, branch `feat/sync-pipeline`. The relevant integration changes were:

- [PR 831](https://github.com/NickolisK24/bullpen-intel-engine/pull/831), roster authority isolation/corrections, merged September 11 13:38:12 UTC at `9df21a4724d5fa2298042d171c46c790aeb5a072`.
- [PR 833](https://github.com/NickolisK24/bullpen-intel-engine/pull/833), shared writer fencing, merged September 11 18:00:39 UTC at `fbaff1fb903fb82a98372cda589630d70e519a00`.
- [PR 837](https://github.com/NickolisK24/bullpen-intel-engine/pull/837), publication reader admission, merged September 12 09:48:23 UTC at `f6d493aacb95fd62ff064c14e810ab1d45186d20`.

Those fixes landed on integration, not on the deployed production runtime. Before roster isolation, `roster_transaction_authority._get_or_create_pitcher` assigned every roster subject's team directly to the shared pitcher projection. The legacy `RunRosterEvidence` also overlays stored pitcher-team identities into its roster acquisition universe, and the legacy directory admits every active stored team. This establishes the scope-interaction mechanism; it does not establish that PR 837 introduced the Daily Primary exception. PR 836 restored migration history/ownership and did not promote the integration runtime wholesale. The publication proof's exact-30 check is protective and remains unchanged.

## Observed blast radius

At the investigation checkpoint:

- The sole published league Dashboard snapshot is **2640**, data-through **September 10**, availability **September 11**, published September 11 02:17:55.877604 UTC. Dashboard and sampled Team Board 145 return this authority. Daily Edition returns September 10, status empty. This is league publication staleness.
- Canonical game logs contain September 11's 15 games / 133 pitching appearances. September 12 has 9 games / 78 appearances at the sampled checkpoint. Continuous acquisition is advancing; these counts alone do not certify every upstream statistic or the current day's complete slate.
- September 12 daily ingestion reported 801 unchanged logs, zero errors, zero unresolved finality, and 484 fatigue recalculations before publication failed. Canonical stages committed separately from the failed publication transaction.
- Transactions were reconciled through September 12: window 176 succeeded at 13:43:00 UTC with 199 stored records. September 12 has 997 roster snapshot rows across 34 team IDs, 769 carrying governed observation lineage. Fresh timestamps do not certify MLB scope correctness.
- Tonight is September 12, two cards, generated 14:05:51 UTC by schedule coherence. Morning Primary attempt 126 and fallback attempt 127 succeeded only in that limited schedule/Tonight sense.
- Pending snapshot 2692 preserves its original 14-of-15 final September 11 coverage; snapshot 2718 records 9-of-15 September 12 coverage. Neither is an admissible replacement, and neither was force-published. New candidate timestamps are not publication progress.
- Dashboard freshness still reports `is_current=true`, age 0, and September 10 as its reference date; Dashboard adds `latest_sync_failed_serving_previous_published_view`. The sampled frozen Team Board omits that failure warning. These frozen fields do not prove currentness relative to the incident date.
- The public response's cache serves the same database publication identity. Cache eviction cannot create a missing trusted publication. Static distribution was skipped in the failed fallback. The last inspected generated-route commit identifies snapshot 2604 / September 9; live crawler output still requires separate verification.

## Narrow remediation and validation

Branch `fix/daily-publication-team-authority` starts at the exact production commit above in an isolated checkout. It restricts both team-directory queries to the existing canonical MLB club registry while requiring actual active-pitcher evidence. It does not fill missing clubs, mutate affiliate rows, change classifiers, weaken the exact-30 proof, or advance integration/schema authority. Existing batch/operations fixtures now use actual MLB IDs. The new regression demonstrates that active affiliates with misleading MLB labels cannot enter the directory and that a missing canonical club stays missing.

Focused and dependent regression validation: **214 passed**, covering team following/directory, transactional Team State proof, share batch generation/operations, progressive publication, Team State history, league listing, and bullpen comparison. Existing deprecation warnings remain. CI and deployment are separate acceptance steps.

A read-only diagnostic inspected pending snapshot 2692 using the patched directory. It cleared the team-universe check but was rejected for reference alignment because its frozen slate coverage is incomplete and therefore cannot supply trusted date authority. That diagnostic is not a fresh candidate build or recovery proof. Database sessions enforced PostgreSQL read-only mode; no publication or roster row was repaired by hand.

## Recovery acceptance

An unchanged-code rerun is not a supported restoration: it would encounter the known directory failure again. The existing incident recovery workflow requires genuine GitHub `workflow_dispatch` on production `main`, `mode=recovery_daily`, intended window `2026-09-12T10:05:00Z`, confirmation `RECOVER`, and an incident reason. It acquires the public writer lock, checks durable prior success, and verifies publication plus Tonight before marking success. Do not spoof execution context or bypass the production-ref requirement.

After the reviewed patch is promoted and deployed, dispatch that supported recovery and retain its run/attempt/SyncRun IDs. Inspect all publication gates, including the now-active September 12 slate. A green no-op, expected pending active slate, or successful ingestion is insufficient. Acceptance requires a newly admitted publication covering the completed-game obligation, 30-team proof, exact served snapshot/date identity on Dashboard and Team Board, coherent Today/Tonight dates, and distribution verification. Until that evidence exists, **BaseballOS is not proven current again**.
