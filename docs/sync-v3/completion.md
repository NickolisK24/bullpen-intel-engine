# Sync v3 acceptance ledger

## Decision on November 24, 2026

**NO-GO for production promotion.** The reviewed integration revision is `81d53550ef0e9924c6e85e27b3ef6e48ac2b5989`. PRs #947 and #948 merged there. Main at `dee721f0895e021fb07a7155f3c9db55682ff885` pins that revision for the scheduled shadow. The shadow runs at 12:47 UTC. Its private candidate database and selection are separate from trusted dashboard publication.

The public League response identified snapshot **5847**, sync **98739**, workload through October 28 and availability reference October 29. Publication time was November 24 at 10:08:39 UTC. Both public identity blocks agreed. Production PostgreSQL reported 17.6 and Alembic head `e241f709cd36`. These are observations of the existing public system.

| Render component | Live deploy ID | Revision |
|---|---|---|
| API | dep-dc1cru6417fc73bdkjm0 | 79a8ac93 |
| Daily primary | dep-dc2peiqvcj2c73fjgph0 | dee721f0 |
| Morning primary | dep-dc2pejavcj2c73fjgpm0 | dee721f0 |
| Postgame primary | dep-dc2pej2vcj2c73fjgpjg | dee721f0 |
| Continuous updates | dep-dc2peiavcj2c73fjgp00 | dee721f0 |
| Historical shadow detector | dep-dan8mp6q1p3s73c7gpc0 | 617ab650 |

A live cron deployment identifies installed code. Each execution needs its own receipt. The latest completed scheduled GitHub shadow observed here was run 45296642435 on main revision 37f53593, artifact 14877580648. It predates the new pin. The artifact delivery endpoint returned HTTP 403 during this check. A PR run cannot certify scheduled execution.

## Package evidence

Implemented means code or a contract exists. Isolated verified means there is a bounded local replay or test. Shadow verified requires evidence from the hosted shadow for the scope in question. Production verified requires the replacement exercising the responsibility in production. Blocked identifies an unmet prerequisite. Complete requires all acceptance obligations for that package. The table records the strongest evidence cited here and the outstanding obligation separately.

Module paths below are relative to `backend/sync_v3/`. The [rehearsal record](README.md), [coverage registry](coverage.csv) and [production census](../audits/NP-00-existing-pipeline-census.md) carry the underlying evidence and scope.

| Package | Evidence level | Implementation and evidence | Outstanding acceptance or dependency |
|---|---|---|---|
| NP-00 census | Blocked | Production census, physical relations, trigger and workflow inventories | Attribute all shared writer accounts and historical obligations |
| NP-01 coverage | Implemented | coverage.csv identifies source, retention, qualification and consumers | Verify adapter coverage and supported eras for each required field |
| NP-02 isolation | Isolated verified | rehearse.py creates socket-only candidate DB and distinct worker/reviewer grants | Verify equivalent hosted writer and reader isolation for the proposed primary |
| NP-03 discovery | Isolated verified | discovery.py and capture_day.py, regular and postseason replay | Measure ongoing live schedule, roster and correction discovery |
| NP-04 orchestration | Isolated verified | queue.sql, queue.py, lease loss and stale settlement tests | Recover a representative hosted interruption within budget |
| NP-05 acquisition | Isolated verified | sources.py and capture_day.py pin request identity and retrieval time | Verify complete required adapter and source outage coverage |
| NP-06 retention | Isolated verified | evidence.sql, evidence.py, immutable replay inputs | Demonstrate durable hosted retention beyond temporary Actions artifacts |
| NP-07 identities | Isolated verified | canonical.py, public_identities.py, game and pitcher reconciliation | Certify full public identity coverage and real source corrections |
| NP-08 rosters | Isolated verified | rosters.py and membership_usage.py, dated club populations | Resolve current roster, transaction and writer coverage |
| NP-09 corrections | Isolated verified | canonical revisions, dependencies.py and correction tests | Demonstrate end-to-end historical correction propagation to every dependent surface |
| NP-10 workload | Isolated verified | workload.py, readiness.py, August rest comparison below | Verify all rolling windows under hosted workload |
| NP-11 deployment | Isolated verified | deployment.py and season_deployment.py, dated role samples | Resolve named-arm comparisons with matched 45-day evidence |
| NP-12 performance | Isolated verified | group_performance.py and pitch_measurements.py, qualified historical samples | Certify performance and pitch coverage across required eras and consumers |
| NP-13 rotation and context | Isolated verified | rotation.py, schedule_context.py, depth.py, complete games below | Freeze source-equivalent splits in a new full handoff receipt |
| NP-14 state and arm reads | Isolated verified | readiness.py and postseason_arm_comparison.py, August state comparison | Certify availability-date population, eligibility and suppression across seasons |
| NP-15 history | Isolated verified | history.sql, intelligence_history.py, dependency rebuilds | Prove correction and replay across the complete accepted cohort |
| NP-16 changes | Isolated verified | change_history.py, readiness_history.py, team_history_reads.py | Match previous edition, methodology and event references on both sides |
| NP-17 candidate build | Isolated verified | generation.py and cohort.py, selected 30-club generation | Verify full primary acquisition through candidate publication |
| NP-18 promotion and recovery | Isolated verified | selection.py, handoff.py and selected-publication rehearsal | Verify exclusive hosted promotion and rollback against the approved configuration |
| NP-19 product delivery | Isolated verified | product_reads.py, history_delivery.py, editorial_reads.py, archived_share_pages.py, historical browser rehearsals | Certify equivalent generations across Tonight, League, Board, Pitcher, Matchup, Search, Changes, History, Stories, Share and Trust |
| NP-20 operations | Isolated verified | rehearse.py diagnostics, source trace and worker recovery | Demonstrate hosted end-to-end recovery and failure visibility |
| NP-21 cost and performance | Isolated verified | Timed offline replay and storage measurements in README | Collect hosted workload latency, peak memory, DB use, storage, cost and approved thresholds |
| NP-22 parity | Implemented | Hosted shadow and paired full-slate comparator | Obtain equivalent live cohorts and resolve material differences |
| NP-23 cutover | Blocked | Private selection, postcommit comparison and rollback rehearsals | Exclusive-writer handoff, owner approvals, observation duration, healthy observation and separate retirement authorization |

## August 29 full-slate evidence

The verified inputs are workload through August 28, availability August 29, 15 games and 30 clubs. The supplemented candidate generation is `0979b7d27fc71573a2b93102daa7d79ac87257227838bf2e7dc56f769235c022`. The legacy rehearsal served snapshot 6, sync 5. The two postcommit receipts matched with digest `sha256:1f6f0526198a80679a43fde593b51c1607125b88dbd3f3334c4cfb20a21a361e`. Keep this original failing receipt when measuring any improved fixture.

| Domain | Reproduced finding | Disposition |
|---|---|---|
| Rest | Original archive had 14 comparable numeric clubs and 16 matching withholdings. Supplemental dated rosters raised this to 28 numeric clubs. Houston and San Diego withheld. Both comparisons had zero rest disagreements. | Qualified agreement on this slate |
| Rotation | The stored edition omitted rotation on all 30 sides. The candidate supplied 20. The local legacy target had zero split rows in August 22–28. The existing split writer produced 198 rows for 99 games inside one rolled-back transaction. Comparing the actual legacy carrier to the same candidate then produced agreement on 28 sides. | Fixture/input difference explains 18 original discrepancies |
| Complete games | Remaining Boston and Los Angeles differences were in games analyzed, 7 versus 6 and 6 versus 5. MLB recorded exactly one pitcher and 9.0 IP for each visiting club. Legacy split aggregation returns null for the empty reliever list, and the classifier returned bullpen_outs_unknown. Candidate counted the start. Short-start counts and bullpen innings agreed. | Legacy handling of two verified complete games. Preserve the supported zero relief outs. [Boston boxscore](https://statsapi.mlb.com/api/v1/game/491967/boxscore) · [Los Angeles boxscore](https://statsapi.mlb.com/api/v1/game/491985/boxscore) |
| Named key arms | Twelve sides differed in the stored receipt. Re-ranking frozen legacy arms with the retained official player game logs for the 45-day role window, using the legacy author and sorter, reduced the differences to NYY, CIN, HOU and LAA. One SD player lacked a profile in this diagnostic input. | Eight differences reproduced as role-input differences. Four still require matched eligibility, roster and role inputs. This diagnostic did not create a new publication. |
| Change links | Candidate returned nine league events. The stored edition returned zero. Seven sides differed in attached change references. | Previous-edition identity and comparable lineage require proof. A zero count alone cannot adjudicate the nine events. |

The rotation check called `recompute_team_game_pitching_splits_for_game`, `frozen_recent_rotation_games_by_team` and the public Tonight `_rotation` helper on the disposable PostgreSQL target. It verified the original carrier again after rollback. The role comparison used `author_role_read_labels` and Tonight's `_key_arms` with frozen active membership and rest. Neither diagnostic updates the original receipt.

## Production authority and decision gates

The observed roles with DML privileges on all five sampled relations (game logs, pitchers, scheduled games, sync runs and dashboard snapshots) were postgres, service_role, supabase_admin and pg_write_all_data. The latter is a built-in group role. The catalog establishes capability. The Render group and GitHub secret names identify bindings, while shared credentials leave individual caller attribution unresolved. The historical detector is a separate deployment. Its deployment identity alone cannot authorize restart or retirement. Preserve non-baseball application writers and historical provenance when assigning future scope.

An affirmative decision requires effective caller-to-role attribution, a tested hosted handoff and rollback, equivalent live and played-slate evidence, hosted resource measurements, an approved observation duration and thresholds, and resolution or explicit approval of outstanding checks. PR #948 had green PostgreSQL shards, migrations, browser and frontend tests and a failed dependency audit. No owner exception is recorded here. Cutover, observation and retirement have no production receipts.

## Qualified named arms and postcommit retry

The isolated correction freezes eligible arms for the availability-date club and the public role classifier's status and reason. Workload calculations retain their original cutoff. The historical reader resolves those players against the pinned roster for that date and the edition's public identity export. A generation without this evidence withholds named ranks.

With independent 45-day MLB pitching logs and the legacy public role author, **28 of 30 teams agree on the complete ordered named-arm lists**. Cincinnati now includes Wandy Peralta. The mixed-use eligibility of Tim Adleman withholds a concrete role. Houston includes Joe Musgrove. Francisco Liriano's eligibility reason records mixed starting and relief use even though his status is role_reliever. The Angels exclude Bud Norris, who is absent from the dated active roster. These were replacement defects.

* New York's Aroldis Chapman has a recorded official-source conflict for April 30 game 490461. The boxscore reports one game finished and the official player log reports zero. The candidate withholds his qualified deployment profile. The comparison author supplied only with the player log ranks him as a Trust Arm. Preserve source-conflict suppression.
* San Diego's August 29 board population includes MLB player 622766. The selected public identity export has no ID for that pitcher. The candidate withholds the club ranking under the complete identity rule. The independent legacy-side diagnostic also lacks this player's role input. A complete identity export and role observation are required to certify that ranking.

On a clone of the legacy target with 198 source-derived split rows, two invocations of the production-path rehearsal returned identical postcommit observations. Selection revision 2 used generation `d8abe3cbfb279ae049606d7161178f4e87a4de0320e511009ff72740b78f9527`, local snapshot 37, sync 6 and Tonight publication 2. The Tonight content SHA-256 was `44cea485d61397a49de01eb30638ce6bdc60197299e5a48a26a2c1b0b03e5ec8`. The Team State proof receipt digest was `bf2dfbb6afd1c079f11c163357f6cee1ba8708cabca2163bc31639cc28cb5fc8`.

Stored and served comparisons each retained ten named-arm, two rotation and seven change-link differences, with zero rest differences. The ten consist of the eight role-input differences and the two suppressions above. The legacy target's frozen What Changed carriers for all 30 clubs recorded no_prior_trusted_comparison and no previous snapshot ID. The candidate had nine events with earlier candidate history. This establishes differing inputs. It leaves direct equality of event semantics untested until the legacy rehearsal has a comparable trusted predecessor.

Run the isolated suite from backend with `SYNC_V3_TEST_PG_BIN=/path/to/pg17/bin python -m pytest -q tests/test_sync_v3*.py`. The full-slate entry point is `python -m scripts.rehearse_selected_publication --source-socket "$socket" --revision 2 --generation "$generation" --predecessor 6 --sync-run 6 --product-day 2017-08-29` on the described disposable fixture. The command exits unsuccessfully when supporting fields differ, including on retry.

At 14:16 UTC the production catalog had no candidate schema and no pg_cron job relation. Five sampled postgres sessions carried the Supavisor label and one other postgres session had another label. A point-in-time connection count cannot attribute credential holders. Record the owner-approved grant-to-caller mapping before handoff. PR-triggered shadow 45408322187 completed on runner revision 63dcfcd8, artifact 14926364920. Its successful steps do not certify a scheduled run of the new revision. [Hosted resource measurement PR](https://github.com/NickolisK24/bullpen-intel-engine/pull/950)
