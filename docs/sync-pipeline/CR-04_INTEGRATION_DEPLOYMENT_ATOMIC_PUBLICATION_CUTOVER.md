# CR-04 Controlled Integration Deployment and Atomic Publication Cutover

## 1. Objective

CR-04 was opened to deploy the reviewed integration branch to a controlled Render execution path, prove recurring SP work, publish one natural SP-11 generation, and then move backend current reads to one atomic publication identity. The deployment precondition could not be satisfied with the available production controls, so publication and reader cutover were intentionally not attempted.

## 2. Starting Integration SHA

`63f87feb421eb446fae09d28ab86390ecbbbb8ed`

## 3. Production Deployment Before

Read-only Render inspection on 2026-09-10 found the following BaseballOS services in workspace `tea-d15pjmodl3ps7381ofe0`:

| Service | Render ID | Branch | Live deploy / commit | Schedule | Command |
|---|---|---|---|---|---|
| API | `srv-d7qp8na8qa3s73d149sg` | `main` | `dep-dadq2qh5efls739cp890` / `361d727c8986ea00efec372765eff8ac3d3d8e83` | continuous | `bash scripts/render_start.sh` from `backend` |
| Continuous primary | `crn-daaer0e7bikc7388ghag` | `main` | `dep-dah8719srm7s7397tlrg` / `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65` | `*/3 * * * *` | `cd backend && python scripts/run_continuous_cycle.py` |
| Continuous shadow | `crn-da98kclg1s2s739k0870` | `main` | `dep-dah8711srm7s7397tlmg` / `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65` | `*/3 * * * *` | `python backend/scripts/run_continuous_cycle.py --mode shadow_full_chain` |
| Morning primary | `crn-da8ldm6gekts73ao3a6g` | `main` | main deployment | `5 14 * * *` | legacy `run_due_sync.py --mode morning ... --public-only` |
| Daily primary | `crn-da8f605g1s2s73983o1g` | `main` | main deployment | `5 10 * * *` | legacy daily command |
| Postgame primary | `crn-da8f4mbtqb8s73a1htdg` | `main` | main deployment | `5 2,4,6 * * *` | legacy postgame command |

Legacy scheduling and publication remained authoritative. No Render service deployed the CR-04 base or integration branch.

## 4. Deployment Strategy

The preferred strategy remains repointing the existing dedicated shadow cron to `feat/sync-pipeline` and the reviewed SP shadow command. It preserves the single three-minute shadow schedule and the service's existing production database/environment wiring.

The connected Render API can inspect services, deploys, logs, and update environment values, and can create a new branch-specific cron. It cannot change an existing service's branch or start command. The available create-cron operation cannot attach or clone the existing secret/environment group. Browser control was unavailable, so the Render Dashboard could not be used to perform the guarded repoint.

Creating another cron without the production database/config wiring would neither consume the real SP-02 queue nor prove production behavior. Creating a second fully configured schedule would also duplicate the existing shadow trigger. Both options were rejected.

## 5. Exact Render Services, Deploy IDs, and SHAs

The relevant exact identities are in section 3. There is no Render deploy ID for `feat/sync-pipeline@63f87feb421eb446fae09d28ab86390ecbbbb8ed`; this is the primary CR-04 blocker.

## 6. Recurring Shadow Proof

Render logs from `2026-09-10T13:21:02Z` through `2026-09-10T13:48:25Z` show ten scheduled runs of `crn-da98kclg1s2s739k0870`. Every run executed the legacy `shadow_full_chain` command and returned:

* `status=off`;
* `reason_code=kill_switch_disabled`;
* `sync_run_id=null`;
* `games_checked=0`;
* `source_requests=0`;
* `production_authority_affected=false`.

The cron mechanism is recurring, but the certified SP entrypoint is not. CR-03's recurrence blocker therefore remains open.

## 7. Historical Retry Resolution

The last exact-SHA production shadow artifact, workflow run `34478842541`, still reported one `reconcile_final_game` job in `retry_wait`. The connected Render workspace exposes no BaseballOS PostgreSQL resource, and the Render service cannot be repointed to the integration command that would inspect/consume the governed queue. The job was not direct-edited or relabeled. Its exact owner-path disposition remains unresolved and independently blocks the publication preconditions.

## 8. Publication Preconditions

The following required preconditions did not pass:

* recurring exact-integration Render execution;
* stable recurrent SP queue drain;
* resolution of the historical finality retry;
* naturally completed, deployed SP-10 cohort eligible for publication;
* production parity of publication-bound consumers.

Accordingly, `SYNC_PIPELINE_PUBLICATION_ENABLED` was not enabled and no SP-11 worker was activated.

## 9. First Atomic Publication

Not attempted. The last read-only production evidence still had `atomic_publication_current = null`. No publication row, artifact, predecessor, or pointer transition is claimed by CR-04.

## 10. Publication Lineage

CR-01 through CR-03 proved natural source, final mutation, impact-plan, and derived-cohort lineage in the manual production shadow lane. CR-04 did not extend that lineage to SP-11 because the required reviewed Render deployment did not exist.

## 11. Consumer Audit

| Public family | Current authority | Classification | CR-04 decision |
|---|---|---|---|
| Team Board core/details/full | one selected legacy `DashboardSnapshot`, with deferred reads pinned by `team_board_publication_identity_v1` | legacy snapshot-bound and internally pinned, not SP-11-bound | retain; no cutover before deployed publication proof |
| League/dashboard | guarded/latest legacy dashboard snapshot through `league_team_state_listing` and dashboard API services | legacy snapshot-bound | retain |
| Today | `intelligence_surface_snapshot` bound to a trusted legacy dashboard publication | legacy snapshot-bound | retain |
| Tonight/matchup | legacy trusted snapshot plus current schedule/game context builders | legacy snapshot-bound with request-time synthesis | retain |
| Pitcher/fatigue/recent work | current fatigue/game-log services and legacy snapshot projections | mutable/current compatibility reads | blocker for atomic migration |
| What Changed | comparison identity tied to the selected legacy dashboard snapshot | legacy snapshot-bound | retain |
| Share artifacts | immutable `ShareArtifact` records and their existing frozen source snapshot | independently immutable, not SP-11-linked | retain; no historical rewrite |
| SP-11 bundle | `read_current_publication_bundle()` resolves `atomic_publication_current` once and follows generation-local inherited artifacts | publication-bound substrate | dormant because current pointer is absent |

No endpoint currently uses the SP-11 bundle as public authority.

## 12. Reader Migration

Not performed. Moving readers before a real, complete atomic generation exists would convert a known legacy authority into an unavailable or incomplete public source. The required migration remains: resolve the SP-11 publication once at request entry, pass that identity through team/pitcher/game/league reads, preserve the current response schema, and keep the legacy resolver behind one rollback control until parity passes.

## 13. One-Lookup Contract

The code-proven SP-11 primitive already resolves `atomic_publication_current` once and loads only artifacts associated with that publication. CR-04 did not claim production consumer proof because no public handler invokes it and no production atomic current row exists.

## 14. Team Board Race Proof

The existing Team Board protects its legacy generation by selecting one dashboard snapshot for the core and requiring the same identity for deferred details. This avoids an internal legacy Team Board split, but it does not prove SP-11 generation coherence. The required PostgreSQL N to N+1 atomic-reader race test was not added because reader migration was correctly stopped at the failed deployment gate.

## 15. League Coherence

Not proven for SP-11. Current league reads remain on the legacy guarded dashboard snapshot. A first atomic generation must contain or inherit all required team artifacts before a 30-team reader cutover can pass.

## 16. Inheritance Proof

SP-11 fixture coverage proves generation-local inheritance. No production inheritance proof was attempted because there was no first production atomic publication.

## 17. Natural Final to Publication Proof

Blocked at SP-11. The manual lane has natural Final-to-SP-10 evidence, but no exact integration deployment could recurrently create and consume publication work in Render.

## 18. Live to Final Proof

No new natural proof was claimed. Existing CR-01 through CR-03 evidence remains intact.

## 19. API Publication Identity Proof

Not performed. Public APIs continue to expose their established legacy identities. No response is represented as atomic-publication-bound.

## 20. Legacy vs Atomic Parity

No production dual-read parity window was opened. Fixture parity remains useful but cannot authorize public cutover without a naturally produced complete atomic generation.

## 21. Request-Time Write Audit

The audit confirmed several legacy builders and latest-snapshot resolvers remain in request-facing paths. No new request-time write was introduced. Because consumer migration was stopped, CR-04 does not certify the repository-wide request-time authority-write ban; those paths remain a cutover blocker rather than being silently accepted.

## 22. Share Artifact Proof

Existing share artifacts remain immutable under their legacy source-snapshot contract. No SP-11 linkage or preview regeneration was attempted, so historical share meaning was not changed.

## 23. Cache Handoff

The repository still has no shared SP-11 cache adapter. The governed state remains `not_configured`; no new cache infrastructure was introduced.

## 24. Queue Health

The latest exact-SHA workflow artifact (`34478842541`) reported `221` pending, `1` retry-wait, `1` running, `528` succeeded, `27` historical failed, `0` dead, and `0` stale leases. It also reported 30/30 active-roster authority and no unreconciled Final games. These are historical point-in-time measurements, not proof of recurrent Render drain.

## 25. Performance

No atomic-read or publication performance measurement was made because those paths were not activated. Recording fixture timing as production performance would be misleading.

## 26. Rollback

No production change occurred, so the current rollback is a no-op. For the next authorized attempt:

1. Repoint only `crn-da98kclg1s2s739k0870` back to `main` and its legacy command, or suspend that dedicated shadow trigger.
2. Set `SYNC_PIPELINE_PUBLICATION_ENABLED=false` and the future atomic-read flag false.
3. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` for the new service.
4. Keep legacy publication and scheduler controls true.
5. Retain all additive SP evidence; do not downgrade or delete data.

## 27. Remaining Certification Blockers

1. An authorized Render control capable of repointing the existing shadow cron's branch and command while retaining its secret/environment wiring.
2. Three successful recurring SP cycles at an exact integration SHA with stable queue drain.
3. Governed resolution of the one retrying historical finality job.
4. A naturally eligible SP-10 cohort published through SP-11.
5. A complete first atomic artifact generation suitable for team, pitcher, game, and league readers.
6. Publication-bound consumer migration, PostgreSQL race proof, parity, performance, and rollback proof.

These remain CR-04 work; they are not suitable to defer to CR-05 because publication/read authority has not been established.

## 28. Validation

Validation for this blocked closeout consists of exact git ancestry, read-only Render service/deploy/log inspection, read-only GitHub workflow artifact inspection, targeted repository reader tracing, and documentation whitespace checks. No production mutation, deployment, environment change, publication, pointer switch, reader cutover, scheduler change, or main change occurred.

## 29. Verdict

`BLOCKED`. CR-04 cannot pass until an authorized Render branch/command update preserves the existing production environment wiring. The precondition failure correctly stopped publication and consumer cutover before either could affect public authority.
