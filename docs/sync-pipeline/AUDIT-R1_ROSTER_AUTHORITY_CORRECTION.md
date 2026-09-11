# AUDIT-R1 — MLB Roster Authority Isolation & Governed Historical Correction

Maintainer: Nikko

## 1. Audit finding

F01 is a confirmed P0 authority defect. Read-only inspection of the fetched integration baseline `09823f6ce9c2d1cf3603a4f43fb0f2c3816085eb` found 50 MLB 40-man intervals closed by affiliate observations and 277 affiliate intervals incorrectly carrying MLB membership types. The affected population is 150 players across eight MLB organizations. This census covers all 1,466 retained intervals, 136 roster observations, 1,517 membership mutations, 522 plans, 515 cohorts, one publication, one repair request, and zero closure rows at collection time on 2026-09-11. Counts are a dated snapshot, not a claim that production stopped progressing.

The original full audit is an uncommitted input document. AUDIT-R1 rechecked its assertions against code and production evidence; the four Pittsburgh intervals are only one subset.

## 2. Baseball authority model

Only an official complete MLB-club endpoint may establish, retain, or remove that club's `active_roster` or `forty_man_roster` membership. Complete-empty is an authoritative empty set. Partial, unknown, failed, or conflicting scope cannot change membership. A different club's inclusion does not prove the original club's removal.

An affiliate roster answers assignment questions. `parentTeamId=134` on an Indianapolis record identifies Pittsburgh as parent; it does not turn Indianapolis inclusion into Pittsburgh absence. The same player may belong to Pittsburgh's 40-man roster and play for Indianapolis. Affiliate observations remain immutable source evidence; assignment interval population is still deferred rather than guessed.

## 3. Root cause

`execute_transaction_job` sent raw from/to team IDs into `reconcile_team_roster`. That owner accepted any numeric team, projected `organization_id=team_id`, and closed a globally exclusive prior player/type interval. A global uniqueness index made the false transfer structurally valid. The ordinary unchanged-source shortcut then prevented repeated unchanged parent evidence from correcting canonical state.

## 4. Team classification

`services/mlb_club_directory.py` remains the single 30-club registry. `roster_authority_scope.py` uses it with retained `parentTeamId` and season-scoped official metadata (`sport_id`, `parent_org_id`). MLB club, affiliate, and unknown source scope are explicit. Parent organization is an identified relationship, not a separate roster membership inferred from a numeric request.

A read-only official `/teams?season=2026&hydrate=sport` response confirmed all eight affected affiliates are Triple-A, with the parent mappings below. A current Indianapolis check found 28 active records and 30 `40Man` records, both containing the same 13 pitchers. The two record sets are not asserted identical; the observed pitcher overlap demonstrates why a similar endpoint label cannot establish parent MLB 40-man exclusivity.

## 5. Old invariant

One open current `(pitcher_id, membership_type)` globally. Inclusion anywhere closed membership elsewhere, including an MLB parent when an affiliate used the same endpoint label.

## 6. New invariant

One open, current, non-void `(pitcher_id, team_id, membership_type)`. Each MLB endpoint owns its own set. Distinct membership semantics can coexist without a uniqueness conflict. PostgreSQL team locks remain; affiliate evidence never enters the MLB mutation transaction. Migration `d2e5f8a1b4c7` adds `is_void=false` and replaces the partial unique index. It performs no baseball-data correction.

A void version is an explicit retraction of an invalid claim, not a new assignment fact. It points to its predecessor and preserves all prior dates and provenance. Current membership, pregame membership checks, and SP-10 watermarks exclude void versions. Downgrade refuses to discard void correction history.

## 7. Transaction routing

Raw transaction from/to IDs remain in retained/canonical transaction evidence. Confirmation work resolves official affiliate metadata to the MLB parent, deduplicates parent clubs, and leaves unknown/conflicting routes explicit in the outcome. It never enqueues an affiliate as an MLB roster owner. An already queued affiliate job can still acquire evidence but returns zero canonical mutations and zero downstream MLB work.

## 8. Blast radius

The exact interval ledger and 150-player census appear below. There are 327 incorrect mutations: 277 affiliate membership openings and 50 parent closures. Counting all mutations attached to the affected intervals gives 377 because that includes 50 legitimate earlier parent openings. Those baseline openings must not be mislabeled corruption.

Sixteen directly affected impact plans are 492–507, with cohorts 485–500. Eight older baseline plans (42, 44, 45, 58, 60, 61, 69, 86) are also linked to the original parent intervals; their association is historical lineage, not proof they were built from the later incorrect closure. No repair or closure directly descended from the incorrect plans at the census. Existing repair 1 is the unrelated final-game repair and remains outside this remediation.


| MLB parent | Affiliate | False parent closures | Invalid affiliate claims |
|---|---|---:|---:|
| 115 Colorado Rockies | 342 Albuquerque Isotopes | 6 | 36 |
| 133 Athletics | 400 Las Vegas Aviators | 7 | 36 |
| 134 Pittsburgh Pirates | 484 Indianapolis Indians | 4 | 26 |
| 147 New York Yankees | 531 Scranton/Wilkes-Barre RailRiders | 5 | 36 |
| 120 Washington Nationals | 534 Rochester Red Wings | 11 | 43 |
| 118 Kansas City Royals | 541 Omaha Storm Chasers | 8 | 34 |
| 142 Minnesota Twins | 1960 St. Paul Saints | 5 | 32 |
| 117 Houston Astros | 5434 Sugar Land Space Cowboys | 4 | 34 |

## 9. Pittsburgh evidence

Intervals 622 (Evan Sisk / MLB 681895), 624 (Hunter Barco / 682995), 633 (Noah Murdock / 668716), and 635 (Thomas Harrington / 802419) were closed by observation 1112 (`484:40Man`, job 3922). Parent observation 1077 (`134:40Man`, job 3871) contains all four with `parentTeamId=134`. These retained sources agree on organization and describe different memberships. The correction must append restored parent versions and void the invalid affiliate MLB claims; it must not delete 622/624/633/635 or edit 1077/1112.

## 10. Other affected clubs

Colorado, Houston, Kansas City, Washington, Athletics, Minnesota, and New York Yankees also have missing 40-man members. Every player and interval is listed in the census below. Repairs are bounded to these seven clubs plus Pittsburgh, not all 30 MLB teams.

## 11. Code changes

- Central official roster scope and parent confirmation routing.
- Fail-closed SP-05 owner guard; affiliate evidence cannot mutate MLB membership or current compatibility fields.
- Scoped uniqueness and explicit void correction versions.
- Applied SP-13 request identity carried into SP-05; unchanged-source canonical correction is allowed only there.
- Retained dated MLB proof required before superseding false closure; conflicting independent stints stop for review.
- Correction impact is parent-scoped and deduped by exact mutation IDs, with one repair-date cohort. No publication, closure, or replay behavior is changed.
- Roster health compares source and canonical sets, validates boundary ownership and organization identity, and reports missing/extra IDs. Certification blocks those mismatches.

## 12. Governed repair

PR #831 merged into feat/sync-pipeline at 9df21a4724d5fa2298042d171c46c790aeb5a072 on 2026-09-11 at 13:38:12 UTC. Render deploy dep-dai08hp5efls738hpfu0 reached live on that exact SHA at 13:38:41 UTC. The reviewed additive migration moved c9d4e6f8a1b2 to d2e5f8a1b4c7; its immediate post-check showed zero void rows. A subsequent read-only check confirmed the unchanged 327-interval blast radius before repair. SP-13 request 2 dispatched Pittsburgh job 4094; request 3 dispatched jobs 4099-4105 for the other seven affected clubs. The recurring Render worker performed all SP-05 corrections and SP-09 impact processing. No direct SQL fact update or manual interval reopening was used. Publication and atomic reads remain disabled.

The SP-05 correction primitive preserves original interval records, appends corrected versions, and records request identity in correction reason plus SyncRun/job ancestry. Affiliate claims become void versions. Current compatibility projections pointing to the affected affiliate use the retained official parent organization; valid MLB roster inclusion continues to own positive MLB roster projection. Active tracking flags retain their existing product contract. This does not redesign legacy assignment synchronization.

## 13. Before/after exact source parity

Before: **30/30 active exact; 22/30 40-man exact; 50 missing 40-man pitchers; zero extra MLB members.** Denominator is the canonical MLB registry. Member sets contain official pitcher and two-way entries, not every position player. Source identity, represented date, and retained payload are required; a nonempty canonical count is insufficient.

After, measured at 2026-09-11 13:46:18 UTC: **30/30 active exact; 30/30 40-man exact; zero missing, extra, or current authority-ownership violations.** All 150 affected compatibility projections point to their official MLB parent. Appendix C records all 60 exact source and interval sets. The check covers the currently retained complete source for each club/date; it does not assert future source freshness.

## 14. Downstream impact

Directly incorrect plans 492–507 and cohorts 485–500 remain untouched. Parent correction and affiliate void versions change their roster manifests through normal authoritative inputs. Focused tests verify the original parent manifest changes after correction and affiliate observation-only changes do not alter it. Read-only production validation after repair confirmed all 16 old manifests differ. Every old complete cohort fails with cohort_input_watermark_drifted; the eight old partial cohorts fail cohort_not_complete. Historical plan/cohort rows were not edited. Corrected plans 523–530 are parent-scoped and reached normal SP-10 processing; no publication job was created.

Publication 1 (cohort 330, plan 337) remains immutable with fingerprint `45c5d0957c8296e9e5b1cd045fd6eb930a74f711ba3670cea67644a0482f27c2`. It predates the September 11 invalid claims and is not descended from the 16 incorrect plans. It is not reader-complete and cannot certify corrected current roster authority. No pointer movement is part of AUDIT-R1.

## 15. Production proof

The eight-club repair appended 327 correction versions: 50 restored MLB intervals and 277 void affiliate claims. Every old interval fact field compared equal to the pre-repair census; only current-version lifecycle markers and update timestamps changed. Publication 1 compared equal across every stored column. All 150 affected pitcher projections now identify the correct MLB parent. Pittsburgh successors 1493, 1494, 1495, and 1496 supersede 622, 624, 633, and 635 respectively, retaining the September 10 start and reopening under official observation 1077. Appendix D contains every old-to-new correction identity. Three consecutive completed Render runs reported the deployed fix SHA and 30/30 active, 30/30 40-man, zero current violations: repair-drain run nf5c4 completed at 13:59:23 UTC, automatic follow-up fvmhr at 13:59:44 UTC, and scheduled run nrdpc at 14:01:28 UTC. Their health measurements were 13:59:19, 13:59:40, and 14:01:12 UTC. These are natural scheduled/backlog runs, not manually triggered source mutations. No new affiliate-ownership closure was observed; this bounded window does not simulate a future affiliate transaction, which is covered by regression and PostgreSQL tests.

## 16. Remaining limitations

Affiliate active/40Man records remain source evidence; this package does not certify general historical assignment intervals, option eligibility, or minor-league workload. Date-only roster evidence cannot recover unavailable intra-day timing. Unknown parent metadata remains an explicit unresolved route. Independent later stints or missing dated evidence fail closed for further bounded review. A broader compatibility census also found five non-pitching legacy Pitcher rows with affiliate projections and no SP-05 intervals: Tyler Callihan (802/682997, LF, 484), Max Schuemann (999/680474, LF, 531), Buddy Kennedy (992/671083, 3B, 534), César Salazar (984/663967, C, 5434), and Jake Meyers (997/676694, CF, 5434). Their assignment source is legacy team_assignment_sync at 10:05 UTC. They are excluded from the governed pitcher/two-way membership set and were not changed by this repair. Their retained affiliate IDs may still seed legacy polling; broad legacy assignment behavior is not certified by this fix. The existing legacy public roster-readiness gate still withholds Pittsburgh because of eight unresolved same-player/date roster conflict failures (13335–13338, 13385–13388), created at 04:06 and 10:06 UTC before this remediation. They describe incoming Indianapolis ownership against retained Pittsburgh snapshots. Corrected cohort 516 is partial because that legacy gate withholds roster_composition and organizational_depth; dependent team/What Changed artifacts are withheld. Exact SP-05 parity and SP-13 job completion therefore do not certify public readiness or a publishable replacement cohort. This package does not mark legacy dead letters resolved or alter the broader repair-checker coverage. Broad legacy-writer coexistence, CR-04, publication readiness, closure, and replay semantics remain outside AUDIT-R1.

## 17. Validation

Initial focused PostgreSQL run: 36 passed. Expanded PostgreSQL run: 114 passed, including correction history, parent/affiliate concurrency, scoped uniqueness, transaction routing, interval lookup, migration preservation, and downgrade protection. The retained-production-source PostgreSQL rehearsal reproduced all 327 incorrect claims, applied bounded SP-13/SP-05 correction for all eight clubs, and reached 30/30 active, 30/30 40-man, zero unresolved authority violations, 327 correction mutations, and 277 void versions. It exposed and corrected a queue dedupe-key length issue; dedupe now hashes exact mutation IDs while preserving the IDs in the payload. Resuming the already-corrected Pittsburgh request produced zero mutations. Full PR CI run 34602537380 passed on fix HEAD 063993258630284c9e9ee34deb13cd021f9bf8d4: 9,885 backend tests passed and four skipped, plus frontend, browser (20 passed), migrations, dependency audit, and collection accounting. Duplicate push run 34602531637 hit the existing 25-minute timeout in shard 4; the corresponding PR shard passed. The integration merge tree equals the tested fix tree. Post-merge CI run 34605445199 also hit the existing 25-minute limit in shard 1 on its first attempt; only that timed-out job was selected for rerun. No test assertion failure was reported in either timeout. These workflow timing limits are retained as an operational limitation, separate from the fully passing PR validation. Tests used an isolated local PostgreSQL 16 container; production census connections enforced read-only transactions and a statement timeout.

## 18. Verdict

**PASS for AUDIT-R1 roster authority isolation and the identified historical correction.** All 327 affected claims are superseded through governed owners; all 150 affected pitcher projections identify their MLB parent; active and 40-man retained-source membership parity are each 30/30; current affiliate ownership violations are zero; recurring runs preserve that result; focused PostgreSQL concurrency/invariant tests and full implementation CI pass. Publication and atomic reads remain disabled, publication 1 is immutable, and main remains untouched. This is not a PASS for CR-04, legacy public readiness, atomic publication activation, or broad writer coexistence. Replacement cohorts remain partial for the explicitly recorded legacy dependency, and five legacy non-pitching affiliate projections remain outside the SP-05 membership population.

## Evidence appendix A — all affected players and intervals

Each row is one retained prior interval. `A` means active roster; `40` means forty-man roster. The source subject records the requested endpoint team, independently of parent organization. Mutation IDs include all linked history; incorrect mutations are precisely those whose source observation is an affiliate. Plans/cohorts show lineage, including legitimate baseline openings.

| Interval | Player / MLB ID / internal ID | Team / organization | Type | Start / end | Opening / closing observation (subjects) | Jobs / runs (open; close) | Mutation IDs | Plans / cohorts |
|---:|---|---|---|---|---|---|---|---|

| 284 | Blake Adams / 687060 / 1067 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 284,1210 | 42,492 / 37,485 |
| 288 | Eiberson Castellano / 682769 / 181 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 288,1212 | 42,492 / 37,485 |
| 290 | Hayden Harris / 802686 / 637 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 290,1216 | 42,492 / 37,485 |
| 292 | Jeff Criswell / 676105 / 184 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 292,1221 | 42,492 / 37,485 |
| 304 | Sean Sullivan / 807743 / 194 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 304,1228 | 42,492 / 37,485 |
| 305 | TJ Shook / 669298 / 196 | 115 / 115 | 40 | 2026-09-10 / 2026-09-11 | 99 (115:40Man); 1108 (342:40Man) | 497/6888; 3920/10752 | 305,1230 | 42,492 / 37,485 |
| 365 | Alimber Santa / 695001 / 229 | 117 / 117 | 40 | 2026-09-10 / 2026-09-11 | 103 (117:40Man); 1122 (5434:40Man) | 499/6888; 3927/10752 | 365,1497 | 44,506 / 39,499 |
| 375 | Jason Alexander / 669920 / 239 | 117 / 117 | 40 | 2026-09-10 / 2026-09-11 | 103 (117:40Man); 1122 (5434:40Man) | 499/6888; 3927/10752 | 375,1505 | 44,506 / 39,499 |
| 377 | Kai-Wei Teng / 678906 / 242 | 117 / 117 | 40 | 2026-09-10 / 2026-09-11 | 103 (117:40Man); 1122 (5434:40Man) | 499/6888; 3927/10752 | 377,1509 | 44,506 / 39,499 |
| 378 | Logan VanWey / 701121 / 244 | 117 / 117 | 40 | 2026-09-10 / 2026-09-11 | 103 (117:40Man); 1122 (5434:40Man) | 499/6888; 3927/10752 | 378,1511 | 44,506 / 39,499 |
| 403 | Ben Kudrna / 695667 / 256 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 403,1417 | 45,502 / 40,495 |
| 404 | Carlos Duran / 679922 / 1045 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 404,1420 | 45,502 / 40,495 |
| 407 | Connor Seabold / 657756 / 259 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 407,1422 | 45,502 / 40,495 |
| 414 | Lucas Erceg / 668674 / 266 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 414,1429 | 45,502 / 40,495 |
| 416 | Luke Little / 681432 / 123 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 416,1431 | 45,502 / 40,495 |
| 417 | Mason Black / 696131 / 268 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 417,1433 | 45,502 / 40,495 |
| 419 | Mitch Spence / 687765 / 271 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 419,1436 | 45,502 / 40,495 |
| 430 | Tony Gonsolin / 664062 / 1046 | 118 / 118 | 40 | 2026-09-10 / 2026-09-11 | 105 (118:40Man); 1118 (541:40Man) | 500/6888; 3925/10752 | 430,1440 | 45,502 / 40,495 |
| 492 | Carson Palmquist / 687223 / 315 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 492,1368 | 58,500 / 53,493 |
| 494 | Cole Henry / 669371 / 317 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 494,1371 | 58,500 / 53,493 |
| 496 | DJ Herz / 687792 / 318 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 496,1373 | 58,500 / 53,493 |
| 499 | Gus Varland / 681402 / 320 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 499,1376 | 58,500 / 53,493 |
| 502 | Jake Bird / 656234 / 718 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 502,1381 | 58,500 / 53,493 |
| 505 | Josiah Gray / 680686 / 323 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 505,1384 | 58,500 / 53,493 |
| 507 | Kyle Nicolas / 693312 / 66 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 507,1387 | 58,500 / 53,493 |
| 513 | Paxton Schultz / 687606 / 331 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 513,1391 | 58,500 / 53,493 |
| 514 | Richard Lovelady / 663992 / 332 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 514,1393 | 58,500 / 53,493 |
| 517 | Wyatt Mills / 670090 / 309 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 517,1397 | 58,500 / 53,493 |
| 519 | Zak Kent / 687849 / 336 | 120 / 120 | 40 | 2026-09-10 / 2026-09-11 | 142 (120:40Man); 1116 (534:40Man) | 502/6888; 3924/10752 | 519,1399 | 58,500 / 53,493 |
| 577 | Drew Rom / 680723 / 740 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 577,1252 | 60,494 / 55,487 |
| 582 | Hayden Juenger / 696522 / 562 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 582,1255 | 60,494 / 55,487 |
| 589 | Joe Rock / 697812 / 663 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 589,1261 | 60,494 / 55,487 |
| 592 | Kade Morris / 695034 / 380 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 592,1263 | 60,494 / 55,487 |
| 594 | Luis Morales / 806960 / 382 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 594,1265 | 60,494 / 55,487 |
| 597 | Mason Barnett / 686930 / 385 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 597,1267 | 60,494 / 55,487 |
| 600 | Taylor Rashi / 688497 / 600 | 133 / 133 | 40 | 2026-09-10 / 2026-09-11 | 146 (133:40Man); 1110 (400:40Man) | 504/6888; 3921/10752 | 600,1272 | 60,494 / 55,487 |
| 622 | Evan Sisk / 681895 / 396 | 134 / 134 | 40 | 2026-09-10 / 2026-09-11 | 148 (134:40Man); 1112 (484:40Man) | 505/6888; 3922/10752 | 622,1295 | 61,496 / 57,489 |
| 624 | Hunter Barco / 682995 / 398 | 134 / 134 | 40 | 2026-09-10 / 2026-09-11 | 148 (134:40Man); 1112 (484:40Man) | 505/6888; 3922/10752 | 624,1297 | 61,496 / 57,489 |
| 633 | Noah Murdock / 668716 / 1017 | 134 / 134 | 40 | 2026-09-10 / 2026-09-11 | 148 (134:40Man); 1112 (484:40Man) | 505/6888; 3922/10752 | 633,1302 | 61,496 / 57,489 |
| 635 | Thomas Harrington / 802419 / 405 | 134 / 134 | 40 | 2026-09-10 / 2026-09-11 | 148 (134:40Man); 1112 (484:40Man) | 505/6888; 3922/10752 | 635,1304 | 61,496 / 57,489 |
| 938 | Eric Orze / 679358 / 588 | 142 / 142 | 40 | 2026-09-10 / 2026-09-11 | 164 (142:40Man); 1120 (1960:40Man) | 513/6888; 3926/10752 | 938,1461 | 69,504 / 64,497 |
| 939 | Garrett Acton / 670183 / 589 | 142 / 142 | 40 | 2026-09-10 / 2026-09-11 | 164 (142:40Man); 1120 (1960:40Man) | 513/6888; 3926/10752 | 939,1463 | 69,504 / 64,497 |
| 940 | Jack Anderson / 681252 / 86 | 142 / 142 | 40 | 2026-09-10 / 2026-09-11 | 164 (142:40Man); 1120 (1960:40Man) | 513/6888; 3926/10752 | 940,1466 | 69,504 / 64,497 |
| 943 | Kendry Rojas / 696070 / 593 | 142 / 142 | 40 | 2026-09-10 / 2026-09-11 | 164 (142:40Man); 1120 (1960:40Man) | 513/6888; 3926/10752 | 943,1469 | 69,504 / 64,497 |
| 945 | Marco Raya / 694397 / 595 | 142 / 142 | 40 | 2026-09-10 / 2026-09-11 | 164 (142:40Man); 1120 (1960:40Man) | 513/6888; 3926/10752 | 945,1471 | 69,504 / 64,497 |
| 1128 | Angel Chivilli / 683409 / 706 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1128,1324 | 86,498 / 81,491 |
| 1129 | Bradley Hanner / 690440 / 1042 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1129,1326 | 86,498 / 81,491 |
| 1130 | Brendan Beck / 694341 / 707 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1130,1328 | 86,498 / 81,491 |
| 1136 | Elmer Rodríguez / 695684 / 715 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1136,1335 | 86,498 / 81,491 |
| 1149 | Yerry De los Santos / 660787 / 727 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1149,1344 | 86,498 / 81,491 |
| 1190 | Andrew Baker / 687900 / 1098 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1191 | 493 / 486 |
| 1191 | Blake Adams / 687060 / 1067 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1192 | 493 / 486 |
| 1192 | Eiberson Castellano / 682769 / 181 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1193 | 493 / 486 |
| 1193 | Evan Shawver / 686900 / 1099 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1194 | 493 / 486 |
| 1194 | Hayden Harris / 802686 / 637 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1195 | 493 / 486 |
| 1195 | Jack Mahoney / 694968 / 1100 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1196 | 493 / 486 |
| 1196 | Jake Brooks / 694860 / 1101 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1197 | 493 / 486 |
| 1197 | Jarrod Cande / 686662 / 1102 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1198 | 493 / 486 |
| 1198 | Jeff Criswell / 676105 / 184 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1199 | 493 / 486 |
| 1199 | Keegan Thompson / 624522 / 971 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1200 | 493 / 486 |
| 1200 | Mason Green / 679057 / 1103 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1201 | 493 / 486 |
| 1201 | Parker Mushinski / 656786 / 1032 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1202 | 493 / 486 |
| 1202 | Patrick Weigel / 622256 / 1104 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1203 | 493 / 486 |
| 1203 | Ryan Miller / 668943 / 1105 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1204 | 493 / 486 |
| 1204 | Sean Sullivan / 807743 / 194 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1205 | 493 / 486 |
| 1205 | TJ Shook / 669298 / 196 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1206 | 493 / 486 |
| 1206 | Valente Bellozo / 678368 / 998 | 342 / 342 | A | 2026-09-11 / open | 1107 (342:active); - (-) | 3920/10752; -/- | 1207 | 493 / 486 |
| 1207 | Adam Laskey / 669445 / 1106 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1208 | 493 / 486 |
| 1208 | Andrew Baker / 687900 / 1098 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1209 | 493 / 486 |
| 1209 | Blake Adams / 687060 / 1067 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1211 | 493 / 486 |
| 1210 | Eiberson Castellano / 682769 / 181 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1213 | 493 / 486 |
| 1211 | Evan Justice / 687145 / 1107 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1214 | 493 / 486 |
| 1212 | Evan Shawver / 686900 / 1099 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1215 | 493 / 486 |
| 1213 | Hayden Harris / 802686 / 637 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1217 | 493 / 486 |
| 1214 | Jack Mahoney / 694968 / 1100 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1218 | 493 / 486 |
| 1215 | Jake Brooks / 694860 / 1101 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1219 | 493 / 486 |
| 1216 | Jarrod Cande / 686662 / 1102 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1220 | 493 / 486 |
| 1217 | Jeff Criswell / 676105 / 184 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1222 | 493 / 486 |
| 1218 | Keegan Thompson / 624522 / 971 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1223 | 493 / 486 |
| 1219 | Mason Green / 679057 / 1103 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1224 | 493 / 486 |
| 1220 | Parker Mushinski / 656786 / 1032 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1225 | 493 / 486 |
| 1221 | Patrick Weigel / 622256 / 1104 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1226 | 493 / 486 |
| 1222 | Ryan Miller / 668943 / 1105 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1227 | 493 / 486 |
| 1223 | Sean Sullivan / 807743 / 194 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1229 | 493 / 486 |
| 1224 | TJ Shook / 669298 / 196 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1231 | 493 / 486 |
| 1225 | Valente Bellozo / 678368 / 998 | 342 / 342 | 40 | 2026-09-11 / open | 1108 (342:40Man); - (-) | 3920/10752; -/- | 1232 | 493 / 486 |
| 1226 | Andrew Bash / 687856 / 1108 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1233 | 495 / 488 |
| 1227 | Ben Bowden / 641386 / 1026 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1234 | 495 / 488 |
| 1228 | Drew Rom / 680723 / 740 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1235 | 495 / 488 |
| 1229 | Hayden Juenger / 696522 / 562 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1236 | 495 / 488 |
| 1230 | Jackson Finley / 686533 / 1109 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1237 | 495 / 488 |
| 1231 | Jake Garland / 687195 / 1110 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1238 | 495 / 488 |
| 1232 | James Gonzalez / 686857 / 1111 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1239 | 495 / 488 |
| 1233 | Joe Rock / 697812 / 663 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1240 | 495 / 488 |
| 1234 | Kade Morris / 695034 / 380 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1241 | 495 / 488 |
| 1235 | Luis Morales / 806960 / 382 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1242 | 495 / 488 |
| 1236 | Mason Barnett / 686930 / 385 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1243 | 495 / 488 |
| 1237 | Matt Sauer / 669422 / 1112 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1244 | 495 / 488 |
| 1238 | Nick Hernandez / 663321 / 1113 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1245 | 495 / 488 |
| 1239 | Ryan Magdic / 678163 / 1114 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1246 | 495 / 488 |
| 1240 | Taylor Rashi / 688497 / 600 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1247 | 495 / 488 |
| 1241 | Wander Suero / 593833 / 1115 | 400 / 400 | A | 2026-09-11 / open | 1109 (400:active); - (-) | 3921/10752; -/- | 1248 | 495 / 488 |
| 1242 | Andrew Bash / 687856 / 1108 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1249 | 495 / 488 |
| 1243 | Ben Bowden / 641386 / 1026 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1250 | 495 / 488 |
| 1244 | Blake Beers / 676275 / 1116 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1251 | 495 / 488 |
| 1245 | Drew Rom / 680723 / 740 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1253 | 495 / 488 |
| 1246 | Gustavo Rodriguez / 683020 / 1117 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1254 | 495 / 488 |
| 1247 | Hayden Juenger / 696522 / 562 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1256 | 495 / 488 |
| 1248 | Jackson Finley / 686533 / 1109 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1257 | 495 / 488 |
| 1249 | Jake Garland / 687195 / 1110 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1258 | 495 / 488 |
| 1250 | James Gonzalez / 686857 / 1111 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1259 | 495 / 488 |
| 1251 | Jamie Arnold / 701364 / 1118 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1260 | 495 / 488 |
| 1252 | Joe Rock / 697812 / 663 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1262 | 495 / 488 |
| 1253 | Kade Morris / 695034 / 380 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1264 | 495 / 488 |
| 1254 | Luis Morales / 806960 / 382 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1266 | 495 / 488 |
| 1255 | Mason Barnett / 686930 / 385 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1268 | 495 / 488 |
| 1256 | Matt Sauer / 669422 / 1112 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1269 | 495 / 488 |
| 1257 | Nick Hernandez / 663321 / 1113 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1270 | 495 / 488 |
| 1258 | Ryan Magdic / 678163 / 1114 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1271 | 495 / 488 |
| 1259 | Taylor Rashi / 688497 / 600 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1273 | 495 / 488 |
| 1260 | Wander Suero / 593833 / 1115 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1274 | 495 / 488 |
| 1261 | Wei-En Lin / 827734 / 1119 | 400 / 400 | 40 | 2026-09-11 / open | 1110 (400:40Man); - (-) | 3921/10752; -/- | 1275 | 495 / 488 |
| 1262 | Beau Burrows / 663366 / 1120 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1276 | 497 / 490 |
| 1263 | Brandon Neeck / 677957 / 1121 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1277 | 497 / 490 |
| 1264 | CD Pelham / 641962 / 1122 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1278 | 497 / 490 |
| 1265 | Connor Wietgrefe / 809733 / 1123 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1279 | 497 / 490 |
| 1266 | Cy Nielson / 686951 / 1124 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1280 | 497 / 490 |
| 1267 | Derek Diamond / 682981 / 1125 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1281 | 497 / 490 |
| 1268 | Evan Sisk / 681895 / 396 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1282 | 497 / 490 |
| 1269 | Hunter Barco / 682995 / 398 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1283 | 497 / 490 |
| 1270 | Michael Darrell-Hicks / 690382 / 1126 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1284 | 497 / 490 |
| 1271 | Nick Dombkowski / 694298 / 1127 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1285 | 497 / 490 |
| 1272 | Noah Davis / 663562 / 1128 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1286 | 497 / 490 |
| 1273 | Noah Murdock / 668716 / 1017 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1287 | 497 / 490 |
| 1274 | Thomas Harrington / 802419 / 405 | 484 / 484 | A | 2026-09-11 / open | 1111 (484:active); - (-) | 3922/10752; -/- | 1288 | 497 / 490 |
| 1275 | Beau Burrows / 663366 / 1120 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1289 | 497 / 490 |
| 1276 | Brandon Neeck / 677957 / 1121 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1290 | 497 / 490 |
| 1277 | CD Pelham / 641962 / 1122 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1291 | 497 / 490 |
| 1278 | Connor Wietgrefe / 809733 / 1123 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1292 | 497 / 490 |
| 1279 | Cy Nielson / 686951 / 1124 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1293 | 497 / 490 |
| 1280 | Derek Diamond / 682981 / 1125 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1294 | 497 / 490 |
| 1281 | Evan Sisk / 681895 / 396 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1296 | 497 / 490 |
| 1282 | Hunter Barco / 682995 / 398 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1298 | 497 / 490 |
| 1283 | Michael Darrell-Hicks / 690382 / 1126 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1299 | 497 / 490 |
| 1284 | Nick Dombkowski / 694298 / 1127 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1300 | 497 / 490 |
| 1285 | Noah Davis / 663562 / 1128 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1301 | 497 / 490 |
| 1286 | Noah Murdock / 668716 / 1017 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1303 | 497 / 490 |
| 1287 | Thomas Harrington / 802419 / 405 | 484 / 484 | 40 | 2026-09-11 / open | 1112 (484:40Man); - (-) | 3922/10752; -/- | 1305 | 497 / 490 |
| 1288 | Adam Kloffenstein / 680572 / 1129 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1306 | 499 / 492 |
| 1289 | Alexander Cornielle / 529017 / 1130 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1307 | 499 / 492 |
| 1290 | Bradley Hanner / 690440 / 1042 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1308 | 499 / 492 |
| 1291 | Brendan Beck / 694341 / 707 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1309 | 499 / 492 |
| 1292 | Chris Kean / 815454 / 1131 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1310 | 499 / 492 |
| 1293 | Danny Watson / 702130 / 1132 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1311 | 499 / 492 |
| 1294 | Eli Morgan / 669212 / 261 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1312 | 499 / 492 |
| 1295 | Elmer Rodríguez / 695684 / 715 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1313 | 499 / 492 |
| 1296 | Eric Reyzelman / 801432 / 1133 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1314 | 499 / 492 |
| 1297 | Hayden Merda / 675296 / 1134 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1315 | 499 / 492 |
| 1298 | Justin Topa / 623437 / 967 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1316 | 499 / 492 |
| 1299 | Kyle Carr / 694805 / 1135 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1317 | 499 / 492 |
| 1300 | Travis MacGregor / 669740 / 1136 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1318 | 499 / 492 |
| 1301 | Xavier Rivas / 814392 / 1137 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1319 | 499 / 492 |
| 1302 | Yerry De los Santos / 660787 / 727 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1320 | 499 / 492 |
| 1303 | Zach Messinger / 684725 / 1138 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1321 | 499 / 492 |
| 1304 | Adam Kloffenstein / 680572 / 1129 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1322 | 499 / 492 |
| 1305 | Alexander Cornielle / 529017 / 1130 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1323 | 499 / 492 |
| 1306 | Angel Chivilli / 683409 / 706 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1325 | 499 / 492 |
| 1307 | Bradley Hanner / 690440 / 1042 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1327 | 499 / 492 |
| 1308 | Brendan Beck / 694341 / 707 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1329 | 499 / 492 |
| 1309 | Brian Hendry / 809137 / 1139 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1330 | 499 / 492 |
| 1310 | Carlos Lagrange / 801739 / 1140 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1331 | 499 / 492 |
| 1311 | Chris Kean / 815454 / 1131 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1332 | 499 / 492 |
| 1312 | Danny Watson / 702130 / 1132 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1333 | 499 / 492 |
| 1313 | Eli Morgan / 669212 / 261 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1334 | 499 / 492 |
| 1314 | Elmer Rodríguez / 695684 / 715 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1336 | 499 / 492 |
| 1315 | Eric Reyzelman / 801432 / 1133 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1337 | 499 / 492 |
| 1316 | Hayden Merda / 675296 / 1134 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1338 | 499 / 492 |
| 1317 | Justin Topa / 623437 / 967 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1339 | 499 / 492 |
| 1318 | Kyle Carr / 694805 / 1135 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1340 | 499 / 492 |
| 1319 | Travis MacGregor / 669740 / 1136 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1341 | 499 / 492 |
| 1320 | Will Brian / 684608 / 1141 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1342 | 499 / 492 |
| 1321 | Xavier Rivas / 814392 / 1137 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1343 | 499 / 492 |
| 1322 | Yerry De los Santos / 660787 / 727 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1345 | 499 / 492 |
| 1323 | Zach Messinger / 684725 / 1138 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1346 | 499 / 492 |
| 1324 | Andry Lara / 691251 / 1142 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1347 | 501 / 494 |
| 1325 | Ben Grable / 695066 / 1143 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1348 | 501 / 494 |
| 1326 | Chandler Champlain / 669441 / 1144 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1349 | 501 / 494 |
| 1327 | DJ Herz / 687792 / 318 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1350 | 501 / 494 |
| 1328 | Erick Mejia / 625510 / 1145 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1351 | 501 / 494 |
| 1329 | Gus Varland / 681402 / 320 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1352 | 501 / 494 |
| 1330 | Holden Powell / 676026 / 1146 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1353 | 501 / 494 |
| 1331 | Isaac Lyon / 805214 / 1147 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1354 | 501 / 494 |
| 1332 | Jack Cebert / 701411 / 1148 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1355 | 501 / 494 |
| 1333 | Jake Bird / 656234 / 718 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1356 | 501 / 494 |
| 1334 | Joe Glassey / 812521 / 1149 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1357 | 501 / 494 |
| 1335 | Josiah Gray / 680686 / 323 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1358 | 501 / 494 |
| 1336 | Justin Lawrence / 664875 / 592 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1359 | 501 / 494 |
| 1337 | Kyle Nicolas / 693312 / 66 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1360 | 501 / 494 |
| 1338 | Matt Krook / 640454 / 771 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1361 | 501 / 494 |
| 1339 | Max Kranick / 668820 / 326 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1362 | 501 / 494 |
| 1340 | Paxton Schultz / 687606 / 331 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1363 | 501 / 494 |
| 1341 | Richard Lovelady / 663992 / 332 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1364 | 501 / 494 |
| 1342 | Tom Cosgrove / 676680 / 783 | 534 / 534 | A | 2026-09-11 / open | 1115 (534:active); - (-) | 3924/10752; -/- | 1365 | 501 / 494 |
| 1343 | Andry Lara / 691251 / 1142 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1366 | 501 / 494 |
| 1344 | Ben Grable / 695066 / 1143 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1367 | 501 / 494 |
| 1345 | Carson Palmquist / 687223 / 315 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1369 | 501 / 494 |
| 1346 | Chandler Champlain / 669441 / 1144 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1370 | 501 / 494 |
| 1347 | Cole Henry / 669371 / 317 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1372 | 501 / 494 |
| 1348 | DJ Herz / 687792 / 318 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1374 | 501 / 494 |
| 1349 | Erick Mejia / 625510 / 1145 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1375 | 501 / 494 |
| 1350 | Gus Varland / 681402 / 320 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1377 | 501 / 494 |
| 1351 | Holden Powell / 676026 / 1146 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1378 | 501 / 494 |
| 1352 | Isaac Lyon / 805214 / 1147 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1379 | 501 / 494 |
| 1353 | Jack Cebert / 701411 / 1148 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1380 | 501 / 494 |
| 1354 | Jake Bird / 656234 / 718 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1382 | 501 / 494 |
| 1355 | Joe Glassey / 812521 / 1149 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1383 | 501 / 494 |
| 1356 | Josiah Gray / 680686 / 323 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1385 | 501 / 494 |
| 1357 | Justin Lawrence / 664875 / 592 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1386 | 501 / 494 |
| 1358 | Kyle Nicolas / 693312 / 66 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1388 | 501 / 494 |
| 1359 | Matt Krook / 640454 / 771 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1389 | 501 / 494 |
| 1360 | Max Kranick / 668820 / 326 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1390 | 501 / 494 |
| 1361 | Paxton Schultz / 687606 / 331 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1392 | 501 / 494 |
| 1362 | Richard Lovelady / 663992 / 332 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1394 | 501 / 494 |
| 1363 | Tom Cosgrove / 676680 / 783 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1395 | 501 / 494 |
| 1364 | Tyler Baum / 666121 / 1150 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1396 | 501 / 494 |
| 1365 | Wyatt Mills / 670090 / 309 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1398 | 501 / 494 |
| 1366 | Zak Kent / 687849 / 336 | 534 / 534 | 40 | 2026-09-11 / open | 1116 (534:40Man); - (-) | 3924/10752; -/- | 1400 | 501 / 494 |
| 1367 | Ben Sears / 700786 / 1151 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1401 | 503 / 496 |
| 1368 | Carlos Duran / 679922 / 1045 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1402 | 503 / 496 |
| 1369 | Connor Seabold / 657756 / 259 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1403 | 503 / 496 |
| 1370 | Henry Williams / 689275 / 1152 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1404 | 503 / 496 |
| 1371 | Hunter Owen / 694818 / 1153 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1405 | 503 / 496 |
| 1372 | Hunter Patteson / 687593 / 1154 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1406 | 503 / 496 |
| 1373 | John Means / 607644 / 1155 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1407 | 503 / 496 |
| 1374 | Lucas Braun / 814351 / 1156 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1408 | 503 / 496 |
| 1375 | Lucas Erceg / 668674 / 266 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1409 | 503 / 496 |
| 1376 | Luke Little / 681432 / 123 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1410 | 503 / 496 |
| 1377 | Mason Black / 696131 / 268 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1411 | 503 / 496 |
| 1378 | Matt Moore / 519043 / 1157 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1412 | 503 / 496 |
| 1379 | Ryan Ramsey / 687547 / 1158 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1413 | 503 / 496 |
| 1380 | Scott Alexander / 518397 / 1159 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1414 | 503 / 496 |
| 1381 | Tony Gonsolin / 664062 / 1046 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1415 | 503 / 496 |
| 1382 | Vince Velasquez / 592826 / 950 | 541 / 541 | A | 2026-09-11 / open | 1117 (541:active); - (-) | 3925/10752; -/- | 1416 | 503 / 496 |
| 1383 | Ben Kudrna / 695667 / 256 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1418 | 503 / 496 |
| 1384 | Ben Sears / 700786 / 1151 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1419 | 503 / 496 |
| 1385 | Carlos Duran / 679922 / 1045 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1421 | 503 / 496 |
| 1386 | Connor Seabold / 657756 / 259 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1423 | 503 / 496 |
| 1387 | Henry Williams / 689275 / 1152 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1424 | 503 / 496 |
| 1388 | Hunter Owen / 694818 / 1153 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1425 | 503 / 496 |
| 1389 | Hunter Patteson / 687593 / 1154 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1426 | 503 / 496 |
| 1390 | John Means / 607644 / 1155 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1427 | 503 / 496 |
| 1391 | Lucas Braun / 814351 / 1156 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1428 | 503 / 496 |
| 1392 | Lucas Erceg / 668674 / 266 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1430 | 503 / 496 |
| 1393 | Luke Little / 681432 / 123 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1432 | 503 / 496 |
| 1394 | Mason Black / 696131 / 268 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1434 | 503 / 496 |
| 1395 | Matt Moore / 519043 / 1157 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1435 | 503 / 496 |
| 1396 | Mitch Spence / 687765 / 271 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1437 | 503 / 496 |
| 1397 | Ryan Ramsey / 687547 / 1158 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1438 | 503 / 496 |
| 1398 | Scott Alexander / 518397 / 1159 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1439 | 503 / 496 |
| 1399 | Tony Gonsolin / 664062 / 1046 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1441 | 503 / 496 |
| 1400 | Vince Velasquez / 592826 / 950 | 541 / 541 | 40 | 2026-09-11 / open | 1118 (541:40Man); - (-) | 3925/10752; -/- | 1442 | 503 / 496 |
| 1401 | Aaron Rozek / 702065 / 1160 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1443 | 505 / 498 |
| 1402 | Alejandro Hidalgo / 691576 / 1161 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1444 | 505 / 498 |
| 1403 | C.J. Culpepper / 690217 / 1162 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1445 | 505 / 498 |
| 1404 | Eric Orze / 679358 / 588 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1446 | 505 / 498 |
| 1405 | Garrett Acton / 670183 / 589 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1447 | 505 / 498 |
| 1406 | Germán Márquez / 608566 / 414 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1448 | 505 / 498 |
| 1407 | Jack Anderson / 681252 / 86 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1449 | 505 / 498 |
| 1408 | Julian Merryweather / 657240 / 1163 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1450 | 505 / 498 |
| 1409 | Marco Raya / 694397 / 595 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1451 | 505 / 498 |
| 1410 | Matt Bowman / 621199 / 1164 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1452 | 505 / 498 |
| 1411 | Paulshawn Pasqualotto / 695308 / 1165 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1453 | 505 / 498 |
| 1412 | Ricky Castro / 690462 / 1166 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1454 | 505 / 498 |
| 1413 | Ryan Gallagher / 801594 / 1167 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1455 | 505 / 498 |
| 1414 | Trent Baker / 694536 / 1168 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1456 | 505 / 498 |
| 1415 | Aaron Rozek / 702065 / 1160 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1457 | 505 / 498 |
| 1416 | Alejandro Hidalgo / 691576 / 1161 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1458 | 505 / 498 |
| 1417 | C.J. Culpepper / 690217 / 1162 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1459 | 505 / 498 |
| 1418 | Cody Laweryson / 689520 / 584 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1460 | 505 / 498 |
| 1419 | Eric Orze / 679358 / 588 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1462 | 505 / 498 |
| 1420 | Garrett Acton / 670183 / 589 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1464 | 505 / 498 |
| 1421 | Germán Márquez / 608566 / 414 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1465 | 505 / 498 |
| 1422 | Jack Anderson / 681252 / 86 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1467 | 505 / 498 |
| 1423 | Julian Merryweather / 657240 / 1163 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1468 | 505 / 498 |
| 1424 | Kendry Rojas / 696070 / 593 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1470 | 505 / 498 |
| 1425 | Marco Raya / 694397 / 595 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1472 | 505 / 498 |
| 1426 | Matt Bowman / 621199 / 1164 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1473 | 505 / 498 |
| 1427 | Matt Canterino / 683764 / 1169 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1474 | 505 / 498 |
| 1428 | Paulshawn Pasqualotto / 695308 / 1165 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1475 | 505 / 498 |
| 1429 | Ricky Castro / 690462 / 1166 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1476 | 505 / 498 |
| 1430 | Ruddy Gomez / 803276 / 1170 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1477 | 505 / 498 |
| 1431 | Ryan Gallagher / 801594 / 1167 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1478 | 505 / 498 |
| 1432 | Trent Baker / 694536 / 1168 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1479 | 505 / 498 |
| 1433 | Alex Santos II / 691012 / 1171 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1480 | 507 / 500 |
| 1434 | Alimber Santa / 695001 / 229 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1481 | 507 / 500 |
| 1435 | Brandon McPherson / 835483 / 1172 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1482 | 507 / 500 |
| 1436 | Bryce Mayer / 809343 / 1173 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1483 | 507 / 500 |
| 1437 | Christian Roa / 685005 / 108 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1484 | 507 / 500 |
| 1438 | Jackson Nezuh / 694545 / 1174 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1485 | 507 / 500 |
| 1439 | Jason Alexander / 669920 / 239 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1486 | 507 / 500 |
| 1440 | Josh Hendrickson / 681973 / 1175 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1487 | 507 / 500 |
| 1441 | Julio Rodriguez / 680588 / 1176 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1488 | 507 / 500 |
| 1442 | Kai-Wei Teng / 678906 / 242 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1489 | 507 / 500 |
| 1443 | Logan VanWey / 701121 / 244 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1490 | 507 / 500 |
| 1444 | Michael Knorr / 681077 / 1177 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1491 | 507 / 500 |
| 1445 | Nic Swanson / 702462 / 1178 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1492 | 507 / 500 |
| 1446 | Roddery Muñoz / 682610 / 1007 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1493 | 507 / 500 |
| 1447 | Ryan Weiss / 680802 / 1003 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1494 | 507 / 500 |
| 1448 | Trey McLoughlin / 694381 / 1179 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1495 | 507 / 500 |
| 1449 | Alex Santos II / 691012 / 1171 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1496 | 507 / 500 |
| 1450 | Alimber Santa / 695001 / 229 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1498 | 507 / 500 |
| 1451 | Brandon Bielak / 656232 / 1180 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1499 | 507 / 500 |
| 1452 | Brandon McPherson / 835483 / 1172 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1500 | 507 / 500 |
| 1453 | Bryce Mayer / 809343 / 1173 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1501 | 507 / 500 |
| 1454 | Christian Roa / 685005 / 108 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1502 | 507 / 500 |
| 1455 | Cody Bolton / 675989 / 995 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1503 | 507 / 500 |
| 1456 | Jackson Nezuh / 694545 / 1174 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1504 | 507 / 500 |
| 1457 | Jason Alexander / 669920 / 239 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1506 | 507 / 500 |
| 1458 | Josh Hendrickson / 681973 / 1175 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1507 | 507 / 500 |
| 1459 | Julio Rodriguez / 680588 / 1176 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1508 | 507 / 500 |
| 1460 | Kai-Wei Teng / 678906 / 242 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1510 | 507 / 500 |
| 1461 | Logan VanWey / 701121 / 244 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1512 | 507 / 500 |
| 1462 | Michael Knorr / 681077 / 1177 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1513 | 507 / 500 |
| 1463 | Nic Swanson / 702462 / 1178 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1514 | 507 / 500 |
| 1464 | Roddery Muñoz / 682610 / 1007 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1515 | 507 / 500 |
| 1465 | Ryan Weiss / 680802 / 1003 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1516 | 507 / 500 |
| 1466 | Trey McLoughlin / 694381 / 1179 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1517 | 507 / 500 |

## Evidence appendix B — exact before source/canonical sets

| MLB club | Type | Date / observation | Source MLB IDs | Current interval MLB IDs | Missing | Extra | Exact |
|---|---|---|---|---|---|---|---|
| 108 LAA | active | 2026-09-11 / 1045 | 579328, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 690829, 696270, 696519, 700712, 815083, 820862 | 579328, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 690829, 696270, 696519, 700712, 815083, 820862 | none | none | True |
| 108 LAA | 40Man | 2026-09-11 / 1046 | 579328, 596112, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 686799, 690829, 691946, 691951, 694680, 695049, 696147, 696270, 696519, 700712, 702674, 815083, 820862 | 579328, 596112, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 686799, 690829, 691946, 691951, 694680, 695049, 696147, 696270, 696519, 700712, 702674, 815083, 820862 | none | none | True |
| 109 AZ | active | 2026-09-11 / 1047 | 518876, 571882, 593958, 642528, 642701, 647336, 656464, 664199, 666661, 668678, 669203, 679885, 694297, 805299 | 518876, 571882, 593958, 642528, 642701, 647336, 656464, 664199, 666661, 668678, 669203, 679885, 694297, 805299 | none | none | True |
| 109 AZ | 40Man | 2026-09-11 / 1048 | 518876, 571882, 593958, 640462, 642528, 642701, 647336, 656464, 657044, 664199, 666661, 668678, 669194, 669203, 669704, 672629, 679885, 683352, 684442, 685314, 686228, 686753, 686796, 691009, 691441, 694297, 703615, 805299 | 518876, 571882, 593958, 640462, 642528, 642701, 647336, 656464, 657044, 664199, 666661, 668678, 669194, 669203, 669704, 672629, 679885, 683352, 684442, 685314, 686228, 686753, 686796, 691009, 691441, 694297, 703615, 805299 | none | none | True |
| 110 BAL | active | 2026-09-11 / 1049 | 552640, 605135, 664991, 666974, 669358, 669432, 670329, 676742, 677020, 680694, 687064, 689296, 695380, 801725 | 552640, 605135, 664991, 666974, 669358, 669432, 670329, 676742, 677020, 680694, 687064, 689296, 695380, 801725 | none | none | True |
| 110 BAL | 40Man | 2026-09-11 / 1050 | 552640, 605135, 621107, 642585, 664854, 664991, 666974, 669211, 669358, 669432, 670329, 671382, 676051, 676742, 677020, 680694, 681882, 682274, 687064, 689296, 691172, 694346, 695380, 700249, 801725 | 552640, 605135, 621107, 642585, 664854, 664991, 666974, 669211, 669358, 669432, 670329, 671382, 676051, 676742, 677020, 680694, 681882, 682274, 687064, 689296, 691172, 694346, 695380, 700249, 801725 | none | none | True |
| 111 BOS | active | 2026-09-11 / 1051 | 543243, 547973, 624133, 663558, 663776, 669062, 669711, 670103, 676477, 678394, 681544, 687562, 687941, 801139 | 543243, 547973, 624133, 663558, 663776, 669062, 669711, 670103, 676477, 678394, 681544, 687562, 687941, 801139 | none | none | True |
| 111 BOS | 40Man | 2026-09-11 / 1052 | 543243, 547973, 594027, 624133, 656557, 663558, 663776, 669062, 669711, 670103, 670912, 676477, 676710, 676979, 677161, 678394, 681544, 686580, 687562, 687941, 699151, 700842, 701719, 801139 | 543243, 547973, 594027, 624133, 656557, 663558, 663776, 669062, 669711, 670103, 670912, 676477, 676710, 676979, 677161, 678394, 681544, 686580, 687562, 687941, 699151, 700842, 701719, 801139 | none | none | True |
| 112 CHC | active | 2026-09-11 / 1053 | 571510, 573204, 592332, 605280, 607067, 650644, 656849, 657097, 663423, 665871, 666171, 669020, 684007, 694037 | 571510, 573204, 592332, 605280, 607067, 650644, 656849, 657097, 663423, 665871, 666171, 669020, 684007, 694037 | none | none | True |
| 112 CHC | 40Man | 2026-09-11 / 1054 | 571510, 571946, 573204, 592332, 605280, 607067, 621053, 640451, 650644, 656849, 657006, 657097, 663423, 664208, 665795, 665871, 666129, 666171, 668970, 669020, 676962, 681151, 681520, 681799, 684007, 687863, 690990, 694037, 696136, 702303 | 571510, 571946, 573204, 592332, 605280, 607067, 621053, 640451, 650644, 656849, 657006, 657097, 663423, 664208, 665795, 665871, 666129, 666171, 668970, 669020, 676962, 681151, 681520, 681799, 684007, 687863, 690990, 694037, 696136, 702303 | none | none | True |
| 113 CIN | active | 2026-09-11 / 1055 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668933, 670062, 671096, 682227, 682825, 695076, 695505 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668933, 670062, 671096, 682227, 682825, 695076, 695505 | none | none | True |
| 113 CIN | 40Man | 2026-09-11 / 1056 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668881, 668933, 670062, 671096, 682227, 682825, 683175, 683742, 685112, 686678, 687209, 687924, 695076, 695505, 695534 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668881, 668933, 670062, 671096, 682227, 682825, 683175, 683742, 685112, 686678, 687209, 687924, 695076, 695505, 695534 | none | none | True |
| 114 CLE | active | 2026-09-11 / 1057 | 656492, 668909, 670036, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 800048 | 656492, 668909, 670036, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 800048 | none | none | True |
| 114 CLE | 40Man | 2026-09-11 / 1058 | 542888, 656492, 668909, 670036, 670059, 671106, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 689958, 691414, 800048, 804926 | 542888, 656492, 668909, 670036, 670059, 671106, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 689958, 691414, 800048, 804926 | none | none | True |
| 115 COL | active | 2026-09-11 / 1059 | 605447, 608372, 623474, 657514, 663372, 675848, 677955, 680604, 685299, 687312, 688642, 690279, 693308, 815081 | 605447, 608372, 623474, 657514, 663372, 675848, 677955, 680604, 685299, 687312, 688642, 690279, 693308, 815081 | none | none | True |
| 115 COL | 40Man | 2026-09-11 / 1060 | 500779, 605447, 607536, 608372, 623474, 657514, 663372, 669298, 675848, 676105, 677955, 680604, 682769, 685299, 685326, 687060, 687312, 688642, 690279, 693308, 700327, 701487, 801403, 802686, 807743, 815081 | 500779, 605447, 607536, 608372, 623474, 657514, 663372, 675848, 677955, 680604, 685299, 685326, 687312, 688642, 690279, 693308, 700327, 701487, 801403, 815081 | 669298, 676105, 682769, 687060, 802686, 807743 | none | False |
| 116 DET | active | 2026-09-11 / 1061 | 445276, 621097, 623454, 640448, 641755, 663947, 664285, 672456, 675512, 676428, 689225, 695549, 700270, 805427 | 445276, 621097, 623454, 640448, 641755, 663947, 664285, 672456, 675512, 676428, 689225, 695549, 700270, 805427 | none | none | True |
| 116 DET | 40Man | 2026-09-11 / 1062 | 434378, 445276, 572143, 621097, 623454, 640448, 641755, 656427, 663947, 664285, 669724, 672456, 675512, 676428, 676684, 680744, 681857, 687830, 689225, 689981, 690544, 695549, 700270, 805427, 805725, 808825 | 434378, 445276, 572143, 621097, 623454, 640448, 641755, 656427, 663947, 664285, 669724, 672456, 675512, 676428, 676684, 680744, 681857, 687830, 689225, 689981, 690544, 695549, 700270, 805427, 805725, 808825 | none | none | True |
| 117 HOU | active | 2026-09-11 / 1063 | 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 686613, 687911, 699044, 805123, 814490, 837227 | 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 686613, 687911, 699044, 805123, 814490, 837227 | none | none | True |
| 117 HOU | 40Man | 2026-09-11 / 1064 | 595345, 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 669920, 678906, 681347, 686613, 687888, 687911, 695001, 699044, 701121, 805123, 814490, 837227 | 595345, 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 681347, 686613, 687888, 687911, 699044, 805123, 814490, 837227 | 669920, 678906, 695001, 701121 | none | False |
| 118 KC | active | 2026-09-11 / 1065 | 518886, 543238, 607625, 608379, 621016, 656638, 663738, 663878, 668834, 671162, 674444, 676510, 677976, 702070 | 518886, 543238, 607625, 608379, 621016, 656638, 663738, 663878, 668834, 671162, 674444, 676510, 677976, 702070 | none | none | True |
| 118 KC | 40Man | 2026-09-11 / 1066 | 518886, 543238, 607625, 608032, 608379, 621016, 656638, 657756, 663568, 663704, 663738, 663878, 664062, 666142, 668674, 668834, 671162, 674444, 676510, 677976, 679525, 679883, 679922, 681432, 683232, 686632, 686701, 687765, 694360, 695667, 696131, 702070 | 518886, 543238, 607625, 608032, 608379, 621016, 656638, 663568, 663704, 663738, 663878, 666142, 668834, 671162, 674444, 676510, 677976, 679525, 679883, 683232, 686632, 686701, 694360, 702070 | 657756, 664062, 668674, 679922, 681432, 687765, 695667, 696131 | none | False |
| 119 LAD | active | 2026-09-11 / 1067 | 592779, 595014, 605483, 607192, 623465, 656945, 660271, 669373, 676263, 678020, 680736, 681911, 683618, 686218, 808967 | 592779, 595014, 605483, 607192, 623465, 656945, 660271, 669373, 676263, 678020, 680736, 681911, 683618, 686218, 808967 | none | none | True |
| 119 LAD | 40Man | 2026-09-11 / 1068 | 592779, 595014, 605483, 607192, 621242, 623465, 641778, 656945, 660271, 660813, 663460, 664776, 669165, 669373, 676263, 676272, 676508, 678020, 680736, 681911, 683618, 686218, 689017, 691947, 694361, 694813, 801434, 808963, 808967 | 592779, 595014, 605483, 607192, 621242, 623465, 641778, 656945, 660271, 660813, 663460, 664776, 669165, 669373, 676263, 676272, 676508, 678020, 680736, 681911, 683618, 686218, 689017, 691947, 694361, 694813, 801434, 808963, 808967 | none | none | True |
| 120 WSH | active | 2026-09-11 / 1070 | 663623, 672442, 674841, 676917, 678868, 680899, 683000, 688692, 690925, 691384, 695378, 695418, 702021, 800600 | 663623, 672442, 674841, 676917, 678868, 680899, 683000, 688692, 690925, 691384, 695378, 695418, 702021, 800600 | none | none | True |
| 120 WSH | 40Man | 2026-09-11 / 1071 | 656234, 663362, 663623, 663992, 669371, 670090, 672442, 674841, 676571, 676917, 678868, 680686, 680730, 680899, 681402, 683000, 686610, 687223, 687377, 687606, 687792, 687849, 688692, 690925, 691384, 693312, 695378, 695418, 702021, 800600, 813349 | 663362, 663623, 672442, 674841, 676571, 676917, 678868, 680730, 680899, 683000, 686610, 687377, 688692, 690925, 691384, 695378, 695418, 702021, 800600, 813349 | 656234, 663992, 669371, 670090, 680686, 681402, 687223, 687606, 687792, 687849, 693312 | none | False |
| 121 NYM | active | 2026-09-11 / 1072 | 476594, 606965, 640455, 650960, 668964, 673380, 673540, 681035, 681320, 681810, 690997, 702752, 804267, 804636 | 476594, 606965, 640455, 650960, 668964, 673380, 673540, 681035, 681320, 681810, 690997, 702752, 804267, 804636 | none | none | True |
| 121 NYM | 40Man | 2026-09-11 / 1073 | 476594, 606965, 640455, 642207, 642376, 650960, 656731, 657585, 663795, 668964, 672335, 673380, 673540, 674073, 675540, 681035, 681320, 681810, 687721, 690997, 694646, 697811, 702752, 804267, 804636 | 476594, 606965, 640455, 642207, 642376, 650960, 656731, 657585, 663795, 668964, 672335, 673380, 673540, 674073, 675540, 681035, 681320, 681810, 687721, 690997, 694646, 697811, 702752, 804267, 804636 | none | none | True |
| 133 ATH | active | 2026-09-11 / 1074 | 605488, 656240, 663687, 664129, 665622, 665660, 669620, 678022, 682052, 683155, 686751, 688297, 695611, 814305 | 605488, 656240, 663687, 664129, 665622, 665660, 669620, 678022, 682052, 683155, 686751, 688297, 695611, 814305 | none | none | True |
| 133 ATH | 40Man | 2026-09-11 / 1075 | 605488, 621139, 622663, 643410, 656240, 663687, 664129, 665622, 665660, 669372, 669620, 678022, 680684, 680723, 682052, 683155, 686751, 686930, 686993, 688297, 688497, 692013, 695034, 695611, 696522, 697812, 804556, 806960, 814305 | 605488, 621139, 622663, 643410, 656240, 663687, 664129, 665622, 665660, 669372, 669620, 678022, 680684, 682052, 683155, 686751, 686993, 688297, 692013, 695611, 804556, 814305 | 680723, 686930, 688497, 695034, 696522, 697812, 806960 | none | False |
| 134 PIT | active | 2026-09-11 / 1076 | 596133, 642397, 666808, 669199, 669387, 670990, 682254, 683003, 685126, 694753, 694973, 696062, 696149, 699008 | 596133, 642397, 666808, 669199, 669387, 670990, 682254, 683003, 685126, 694753, 694973, 696062, 696149, 699008 | none | none | True |
| 134 PIT | 40Man | 2026-09-11 / 1077 | 489446, 596133, 642397, 656605, 666808, 668716, 669199, 669387, 670990, 676755, 677952, 681895, 682254, 682995, 683003, 685126, 694753, 694973, 696062, 696149, 699008, 802419 | 489446, 596133, 642397, 656605, 666808, 669199, 669387, 670990, 676755, 677952, 682254, 683003, 685126, 694753, 694973, 696062, 696149, 699008 | 668716, 681895, 682995, 802419 | none | False |
| 135 SD | active | 2026-09-11 / 1078 | 592662, 593974, 601713, 606996, 621111, 650633, 656288, 663554, 670970, 673513, 681190, 688158, 695243, 699134 | 592662, 593974, 601713, 606996, 621111, 650633, 656288, 663554, 670970, 673513, 681190, 688158, 695243, 699134 | none | none | True |
| 135 SD | 40Man | 2026-09-11 / 1079 | 592094, 592662, 593974, 601713, 605397, 606996, 608337, 621111, 650633, 656288, 663554, 663773, 666745, 669093, 670970, 673513, 676664, 676702, 678184, 681190, 688158, 689690, 695243, 699134 | 592094, 592662, 593974, 601713, 605397, 606996, 608337, 621111, 650633, 656288, 663554, 663773, 666745, 669093, 670970, 673513, 676664, 676702, 678184, 681190, 688158, 689690, 695243, 699134 | none | none | True |
| 136 SEA | active | 2026-09-11 / 1080 | 571948, 621074, 622554, 642100, 660825, 662253, 669302, 669923, 672841, 678606, 681867, 682243, 693433, 807739 | 571948, 621074, 622554, 642100, 660825, 662253, 669302, 669923, 672841, 678606, 681867, 682243, 693433, 807739 | none | none | True |
| 136 SEA | 40Man | 2026-09-11 / 1081 | 571948, 621074, 622554, 642100, 660825, 662253, 666374, 669302, 669923, 672841, 673662, 676106, 677961, 678606, 681006, 681867, 681890, 682243, 688138, 689546, 693433, 700187, 807739 | 571948, 621074, 622554, 642100, 660825, 662253, 666374, 669302, 669923, 672841, 673662, 676106, 677961, 678606, 681006, 681867, 681890, 682243, 688138, 689546, 693433, 700187, 807739 | none | none | True |
| 137 SF | active | 2026-09-11 / 1082 | 657277, 665665, 669270, 671345, 681916, 683363, 683627, 691769, 693313, 694738, 694918, 702885, 805074, 805345 | 657277, 665665, 669270, 671345, 681916, 683363, 683627, 691769, 693313, 694738, 694918, 702885, 805074, 805345 | none | none | True |
| 137 SF | 40Man | 2026-09-11 / 1083 | 592858, 605288, 656529, 657277, 657424, 663941, 664141, 665665, 666711, 669270, 671345, 675920, 676130, 676254, 676775, 678495, 681916, 683363, 683627, 686790, 687931, 691769, 693313, 694738, 694820, 694918, 700280, 701474, 702885, 805074, 805345, 806185 | 592858, 605288, 656529, 657277, 657424, 663941, 664141, 665665, 666711, 669270, 671345, 675920, 676130, 676254, 676775, 678495, 681916, 683363, 683627, 686790, 687931, 691769, 693313, 694738, 694820, 694918, 700280, 701474, 702885, 805074, 805345, 806185 | none | none | True |
| 138 STL | active | 2026-09-11 / 1084 | 592773, 666277, 669461, 669467, 676617, 677865, 681517, 685464, 687273, 687309, 700241, 700669, 703725, 802408 | 592773, 666277, 669461, 669467, 676617, 677865, 681517, 685464, 687273, 687309, 700241, 700669, 703725, 802408 | none | none | True |
| 138 STL | 40Man | 2026-09-11 / 1085 | 592773, 657265, 666277, 669461, 669467, 676617, 677865, 681517, 681676, 684516, 685464, 687273, 687309, 690916, 690928, 691008, 694335, 694358, 700241, 700669, 703725, 802408 | 592773, 657265, 666277, 669461, 669467, 676617, 677865, 681517, 681676, 684516, 685464, 687273, 687309, 690916, 690928, 691008, 694335, 694358, 700241, 700669, 703725, 802408 | none | none | True |
| 139 TB | active | 2026-09-11 / 1086 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 656876, 668984, 669330, 687330, 693855, 694494, 702047 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 656876, 668984, 669330, 687330, 693855, 694494, 702047 | none | none | True |
| 139 TB | 40Man | 2026-09-11 / 1087 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 655889, 656876, 663556, 664076, 668984, 669169, 669330, 669438, 669947, 670955, 671212, 675627, 686752, 687330, 693855, 694494, 702047 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 655889, 656876, 663556, 664076, 668984, 669169, 669330, 669438, 669947, 670955, 671212, 675627, 686752, 687330, 693855, 694494, 702047 | none | none | True |
| 140 TEX | active | 2026-09-11 / 1088 | 592866, 594798, 596001, 615698, 641302, 656641, 656756, 669022, 671936, 674003, 676395, 677958, 681217, 695239 | 592866, 594798, 596001, 615698, 641302, 656641, 656756, 669022, 671936, 674003, 676395, 677958, 681217, 695239 | none | none | True |
| 140 TEX | 40Man | 2026-09-11 / 1089 | 543135, 592866, 594798, 596001, 615698, 641302, 656222, 656641, 656756, 668390, 669022, 671936, 674003, 676395, 677958, 681217, 682608, 683004, 686560, 687239, 691945, 692030, 692437, 693713, 695239, 699214, 699314 | 543135, 592866, 594798, 596001, 615698, 641302, 656222, 656641, 656756, 668390, 669022, 671936, 674003, 676395, 677958, 681217, 682608, 683004, 686560, 687239, 691945, 692030, 692437, 693713, 695239, 699214, 699314 | none | none | True |
| 141 TOR | active | 2026-09-11 / 1090 | 453286, 547179, 573009, 623149, 643511, 656302, 663893, 667755, 680755, 681293, 686973, 689254, 693686, 694357 | 453286, 547179, 573009, 623149, 643511, 656302, 663893, 667755, 680755, 681293, 686973, 689254, 693686, 694357 | none | none | True |
| 141 TOR | 40Man | 2026-09-11 / 1091 | 453286, 547179, 554340, 571578, 573009, 592791, 621244, 623149, 643511, 656302, 663893, 664074, 667755, 669310, 669456, 670102, 676454, 680755, 681293, 686973, 689149, 689254, 693686, 694357, 695445, 702056, 804619, 814005 | 453286, 547179, 554340, 571578, 573009, 592791, 621244, 623149, 643511, 656302, 663893, 664074, 667755, 669310, 669456, 670102, 676454, 680755, 681293, 686973, 689149, 689254, 693686, 694357, 695445, 702056, 804619, 814005 | none | none | True |
| 142 MIN | active | 2026-09-11 / 1092 | 573124, 621345, 641927, 656546, 657746, 665152, 667297, 671737, 672782, 681892, 687570, 701519, 702193, 805673 | 573124, 621345, 641927, 656546, 657746, 665152, 667297, 671737, 672782, 681892, 687570, 701519, 702193, 805673 | none | none | True |
| 142 MIN | 40Man | 2026-09-11 / 1093 | 573124, 607455, 621345, 641154, 641927, 656546, 657746, 663485, 665152, 667297, 670183, 671737, 672782, 679358, 681252, 681892, 687570, 690953, 694397, 696070, 701519, 701581, 702193, 702474, 805673 | 573124, 607455, 621345, 641154, 641927, 656546, 657746, 663485, 665152, 667297, 671737, 672782, 681892, 687570, 690953, 701519, 701581, 702193, 702474, 805673 | 670183, 679358, 681252, 694397, 696070 | none | False |
| 143 PHI | active | 2026-09-11 / 1094 | 548384, 554430, 605400, 621237, 641835, 650911, 661395, 663767, 666200, 680742, 680880, 686934, 689147, 691725 | 548384, 554430, 605400, 621237, 641835, 650911, 661395, 663767, 666200, 680742, 680880, 686934, 689147, 691725 | none | none | True |
| 143 PHI | 40Man | 2026-09-11 / 1095 | 548384, 554430, 605400, 621237, 621383, 641482, 641745, 641835, 650911, 660604, 661395, 663767, 666200, 668873, 676661, 679775, 680742, 680880, 686934, 689147, 691330, 691725, 694851 | 548384, 554430, 605400, 621237, 621383, 641482, 641745, 641835, 650911, 660604, 661395, 663767, 666200, 668873, 676661, 679775, 680742, 680880, 686934, 689147, 691330, 691725, 694851 | none | none | True |
| 144 ATL | active | 2026-09-11 / 1096 | 519242, 527048, 608718, 625643, 628452, 641816, 656550, 663559, 669276, 678061, 682989, 689266, 700363, 800311 | 519242, 527048, 608718, 625643, 628452, 641816, 656550, 663559, 669276, 678061, 682989, 689266, 700363, 800311 | none | none | True |
| 144 ATL | 40Man | 2026-09-11 / 1097 | 519242, 527048, 608718, 625643, 628452, 641729, 641816, 656550, 663158, 663559, 666214, 669276, 675911, 675916, 676568, 678061, 680885, 682989, 686628, 689266, 691548, 693821, 694462, 700363, 700413, 702275, 702566, 800311 | 519242, 527048, 608718, 625643, 628452, 641729, 641816, 656550, 663158, 663559, 666214, 669276, 675911, 675916, 676568, 678061, 680885, 682989, 686628, 689266, 691548, 693821, 694462, 700363, 700413, 702275, 702566, 800311 | none | none | True |
| 145 CWS | active | 2026-09-11 / 1098 | 607200, 622491, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 680732, 691799, 696146, 805326 | 607200, 622491, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 680732, 691799, 696146, 805326 | none | none | True |
| 145 CWS | 40Man | 2026-09-11 / 1099 | 607200, 622491, 623211, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 672860, 673929, 678024, 680732, 681066, 681343, 686563, 689672, 689818, 691799, 696146, 699823, 701780, 702273, 805326 | 607200, 622491, 623211, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 672860, 673929, 678024, 680732, 681066, 681343, 686563, 689672, 689818, 691799, 696146, 699823, 701780, 702273, 805326 | none | none | True |
| 146 MIA | active | 2026-09-11 / 1100 | 645261, 656848, 663969, 664126, 667652, 676083, 676534, 676604, 680767, 687473, 690978, 691587, 694795, 806188 | 645261, 656848, 663969, 664126, 667652, 676083, 676534, 676604, 680767, 687473, 690978, 691587, 694795, 806188 | none | none | True |
| 146 MIA | 40Man | 2026-09-11 / 1101 | 645261, 656848, 663969, 664126, 667652, 669622, 676083, 676534, 676604, 676974, 677053, 678692, 680767, 682790, 684049, 687134, 687287, 687473, 687531, 687985, 690978, 691587, 694350, 694795, 702281, 800049, 806188 | 645261, 656848, 663969, 664126, 667652, 669622, 676083, 676534, 676604, 676974, 677053, 678692, 680767, 682790, 684049, 687134, 687287, 687473, 687531, 687985, 690978, 691587, 694350, 694795, 702281, 800049, 806188 | none | none | True |
| 147 NYY | active | 2026-09-11 / 1102 | 543037, 605242, 607074, 608331, 621112, 642232, 657612, 661563, 670167, 670280, 687396, 693645, 701542 | 543037, 605242, 607074, 608331, 621112, 642232, 657612, 661563, 670167, 670280, 687396, 693645, 701542 | none | none | True |
| 147 NYY | 40Man | 2026-09-11 / 1103 | 518585, 543037, 605242, 607074, 608331, 621112, 642232, 657376, 657612, 660787, 661563, 665645, 670167, 670280, 677960, 683409, 687396, 690440, 693645, 694341, 695684, 701542 | 518585, 543037, 605242, 607074, 608331, 621112, 642232, 657376, 657612, 661563, 665645, 670167, 670280, 677960, 687396, 693645, 701542 | 660787, 683409, 690440, 694341, 695684 | none | False |
| 158 MIL | active | 2026-09-11 / 1104 | 622608, 656730, 668941, 669084, 669160, 675660, 676879, 682842, 687075, 688107, 690986, 694477, 694819, 701656 | 622608, 656730, 668941, 669084, 669160, 675660, 676879, 682842, 687075, 688107, 690986, 694477, 694819, 701656 | none | none | True |
| 158 MIL | 40Man | 2026-09-11 / 1105 | 605540, 622608, 642239, 656730, 657649, 668831, 668941, 669060, 669084, 669160, 672582, 675660, 676467, 676879, 681982, 682842, 682990, 687075, 688107, 689441, 690986, 694477, 694819, 701656, 702153 | 605540, 622608, 642239, 656730, 657649, 668831, 668941, 669060, 669084, 669160, 672582, 675660, 676467, 676879, 681982, 682842, 682990, 687075, 688107, 689441, 690986, 694477, 694819, 701656, 702153 | none | none | True |


## Evidence appendix C — exact production parity after correction

Measured 2026-09-11 13:46:18 UTC. IDs are MLB player IDs; the governed source population includes pitchers and two-way players.

| MLB club | Type | Retained complete observation | Source set | Canonical interval set | Missing | Extra | Exact |
|---:|---|---:|---|---|---|---|---|
| 108 | Active | 1045 | 579328, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 690829, 696270, 696519, 700712, 815083, 820862 | 579328, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 690829, 696270, 696519, 700712, 815083, 820862 | ∅ | ∅ | True |
| 108 | 40-man | 1046 | 579328, 596112, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 686799, 690829, 691946, 691951, 694680, 695049, 696147, 696270, 696519, 700712, 702674, 815083, 820862 | 579328, 596112, 642048, 670245, 671111, 672282, 676620, 680570, 684665, 686799, 690829, 691946, 691951, 694680, 695049, 696147, 696270, 696519, 700712, 702674, 815083, 820862 | ∅ | ∅ | True |
| 109 | Active | 1047 | 518876, 571882, 593958, 642528, 642701, 647336, 656464, 664199, 666661, 668678, 669203, 679885, 694297, 805299 | 518876, 571882, 593958, 642528, 642701, 647336, 656464, 664199, 666661, 668678, 669203, 679885, 694297, 805299 | ∅ | ∅ | True |
| 109 | 40-man | 1048 | 518876, 571882, 593958, 640462, 642528, 642701, 647336, 656464, 657044, 664199, 666661, 668678, 669194, 669203, 669704, 672629, 679885, 683352, 684442, 685314, 686228, 686753, 686796, 691009, 691441, 694297, 703615, 805299 | 518876, 571882, 593958, 640462, 642528, 642701, 647336, 656464, 657044, 664199, 666661, 668678, 669194, 669203, 669704, 672629, 679885, 683352, 684442, 685314, 686228, 686753, 686796, 691009, 691441, 694297, 703615, 805299 | ∅ | ∅ | True |
| 110 | Active | 1049 | 552640, 605135, 664991, 666974, 669358, 669432, 670329, 676742, 677020, 680694, 687064, 689296, 695380, 801725 | 552640, 605135, 664991, 666974, 669358, 669432, 670329, 676742, 677020, 680694, 687064, 689296, 695380, 801725 | ∅ | ∅ | True |
| 110 | 40-man | 1050 | 552640, 605135, 621107, 642585, 664854, 664991, 666974, 669211, 669358, 669432, 670329, 671382, 676051, 676742, 677020, 680694, 681882, 682274, 687064, 689296, 691172, 694346, 695380, 700249, 801725 | 552640, 605135, 621107, 642585, 664854, 664991, 666974, 669211, 669358, 669432, 670329, 671382, 676051, 676742, 677020, 680694, 681882, 682274, 687064, 689296, 691172, 694346, 695380, 700249, 801725 | ∅ | ∅ | True |
| 111 | Active | 1051 | 543243, 547973, 624133, 663558, 663776, 669062, 669711, 670103, 676477, 678394, 681544, 687562, 687941, 801139 | 543243, 547973, 624133, 663558, 663776, 669062, 669711, 670103, 676477, 678394, 681544, 687562, 687941, 801139 | ∅ | ∅ | True |
| 111 | 40-man | 1052 | 543243, 547973, 594027, 624133, 656557, 663558, 663776, 669062, 669711, 670103, 670912, 676477, 676710, 676979, 677161, 678394, 681544, 686580, 687562, 687941, 699151, 700842, 701719, 801139 | 543243, 547973, 594027, 624133, 656557, 663558, 663776, 669062, 669711, 670103, 670912, 676477, 676710, 676979, 677161, 678394, 681544, 686580, 687562, 687941, 699151, 700842, 701719, 801139 | ∅ | ∅ | True |
| 112 | Active | 1053 | 571510, 573204, 592332, 605280, 607067, 650644, 656849, 657097, 663423, 665871, 666171, 669020, 684007, 694037 | 571510, 573204, 592332, 605280, 607067, 650644, 656849, 657097, 663423, 665871, 666171, 669020, 684007, 694037 | ∅ | ∅ | True |
| 112 | 40-man | 1054 | 571510, 571946, 573204, 592332, 605280, 607067, 621053, 640451, 650644, 656849, 657006, 657097, 663423, 664208, 665795, 665871, 666129, 666171, 668970, 669020, 676962, 681151, 681520, 681799, 684007, 687863, 690990, 694037, 696136, 702303 | 571510, 571946, 573204, 592332, 605280, 607067, 621053, 640451, 650644, 656849, 657006, 657097, 663423, 664208, 665795, 665871, 666129, 666171, 668970, 669020, 676962, 681151, 681520, 681799, 684007, 687863, 690990, 694037, 696136, 702303 | ∅ | ∅ | True |
| 113 | Active | 1055 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668933, 670062, 671096, 682227, 682825, 695076, 695505 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668933, 670062, 671096, 682227, 682825, 695076, 695505 | ∅ | ∅ | True |
| 113 | 40-man | 1056 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668881, 668933, 670062, 671096, 682227, 682825, 683175, 683742, 685112, 686678, 687209, 687924, 695076, 695505, 695534 | 572955, 622088, 641941, 656271, 663574, 663903, 666157, 668881, 668933, 670062, 671096, 682227, 682825, 683175, 683742, 685112, 686678, 687209, 687924, 695076, 695505, 695534 | ∅ | ∅ | True |
| 114 | Active | 1057 | 656492, 668909, 670036, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 800048 | 656492, 668909, 670036, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 800048 | ∅ | ∅ | True |
| 114 | 40-man | 1058 | 542888, 656492, 668909, 670036, 670059, 671106, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 689958, 691414, 800048, 804926 | 542888, 656492, 668909, 670036, 670059, 671106, 671922, 676282, 676440, 677944, 680916, 681870, 682120, 682982, 683769, 684974, 689958, 691414, 800048, 804926 | ∅ | ∅ | True |
| 115 | Active | 1059 | 605447, 608372, 623474, 657514, 663372, 675848, 677955, 680604, 685299, 687312, 688642, 690279, 693308, 815081 | 605447, 608372, 623474, 657514, 663372, 675848, 677955, 680604, 685299, 687312, 688642, 690279, 693308, 815081 | ∅ | ∅ | True |
| 115 | 40-man | 1060 | 500779, 605447, 607536, 608372, 623474, 657514, 663372, 669298, 675848, 676105, 677955, 680604, 682769, 685299, 685326, 687060, 687312, 688642, 690279, 693308, 700327, 701487, 801403, 802686, 807743, 815081 | 500779, 605447, 607536, 608372, 623474, 657514, 663372, 669298, 675848, 676105, 677955, 680604, 682769, 685299, 685326, 687060, 687312, 688642, 690279, 693308, 700327, 701487, 801403, 802686, 807743, 815081 | ∅ | ∅ | True |
| 116 | Active | 1061 | 445276, 621097, 623454, 640448, 641755, 663947, 664285, 672456, 675512, 676428, 689225, 695549, 700270, 805427 | 445276, 621097, 623454, 640448, 641755, 663947, 664285, 672456, 675512, 676428, 689225, 695549, 700270, 805427 | ∅ | ∅ | True |
| 116 | 40-man | 1062 | 434378, 445276, 572143, 621097, 623454, 640448, 641755, 656427, 663947, 664285, 669724, 672456, 675512, 676428, 676684, 680744, 681857, 687830, 689225, 689981, 690544, 695549, 700270, 805427, 805725, 808825 | 434378, 445276, 572143, 621097, 623454, 640448, 641755, 656427, 663947, 664285, 669724, 672456, 675512, 676428, 676684, 680744, 681857, 687830, 689225, 689981, 690544, 695549, 700270, 805427, 805725, 808825 | ∅ | ∅ | True |
| 117 | Active | 1063 | 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 686613, 687911, 699044, 805123, 814490, 837227 | 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 686613, 687911, 699044, 805123, 814490, 837227 | ∅ | ∅ | True |
| 117 | 40-man | 1064 | 595345, 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 669920, 678906, 681347, 686613, 687888, 687911, 695001, 699044, 701121, 805123, 814490, 837227 | 595345, 623352, 650556, 656986, 660853, 663567, 664299, 669713, 669854, 669920, 678906, 681347, 686613, 687888, 687911, 695001, 699044, 701121, 805123, 814490, 837227 | ∅ | ∅ | True |
| 118 | Active | 1065 | 518886, 543238, 607625, 608379, 621016, 656638, 663738, 663878, 668834, 671162, 674444, 676510, 677976, 702070 | 518886, 543238, 607625, 608379, 621016, 656638, 663738, 663878, 668834, 671162, 674444, 676510, 677976, 702070 | ∅ | ∅ | True |
| 118 | 40-man | 1066 | 518886, 543238, 607625, 608032, 608379, 621016, 656638, 657756, 663568, 663704, 663738, 663878, 664062, 666142, 668674, 668834, 671162, 674444, 676510, 677976, 679525, 679883, 679922, 681432, 683232, 686632, 686701, 687765, 694360, 695667, 696131, 702070 | 518886, 543238, 607625, 608032, 608379, 621016, 656638, 657756, 663568, 663704, 663738, 663878, 664062, 666142, 668674, 668834, 671162, 674444, 676510, 677976, 679525, 679883, 679922, 681432, 683232, 686632, 686701, 687765, 694360, 695667, 696131, 702070 | ∅ | ∅ | True |
| 119 | Active | 1067 | 592779, 595014, 605483, 607192, 623465, 656945, 660271, 669373, 676263, 678020, 680736, 681911, 683618, 686218, 808967 | 592779, 595014, 605483, 607192, 623465, 656945, 660271, 669373, 676263, 678020, 680736, 681911, 683618, 686218, 808967 | ∅ | ∅ | True |
| 119 | 40-man | 1068 | 592779, 595014, 605483, 607192, 621242, 623465, 641778, 656945, 660271, 660813, 663460, 664776, 669165, 669373, 676263, 676272, 676508, 678020, 680736, 681911, 683618, 686218, 689017, 691947, 694361, 694813, 801434, 808963, 808967 | 592779, 595014, 605483, 607192, 621242, 623465, 641778, 656945, 660271, 660813, 663460, 664776, 669165, 669373, 676263, 676272, 676508, 678020, 680736, 681911, 683618, 686218, 689017, 691947, 694361, 694813, 801434, 808963, 808967 | ∅ | ∅ | True |
| 120 | Active | 1070 | 663623, 672442, 674841, 676917, 678868, 680899, 683000, 688692, 690925, 691384, 695378, 695418, 702021, 800600 | 663623, 672442, 674841, 676917, 678868, 680899, 683000, 688692, 690925, 691384, 695378, 695418, 702021, 800600 | ∅ | ∅ | True |
| 120 | 40-man | 1071 | 656234, 663362, 663623, 663992, 669371, 670090, 672442, 674841, 676571, 676917, 678868, 680686, 680730, 680899, 681402, 683000, 686610, 687223, 687377, 687606, 687792, 687849, 688692, 690925, 691384, 693312, 695378, 695418, 702021, 800600, 813349 | 656234, 663362, 663623, 663992, 669371, 670090, 672442, 674841, 676571, 676917, 678868, 680686, 680730, 680899, 681402, 683000, 686610, 687223, 687377, 687606, 687792, 687849, 688692, 690925, 691384, 693312, 695378, 695418, 702021, 800600, 813349 | ∅ | ∅ | True |
| 121 | Active | 1072 | 476594, 606965, 640455, 650960, 668964, 673380, 673540, 681035, 681320, 681810, 690997, 702752, 804267, 804636 | 476594, 606965, 640455, 650960, 668964, 673380, 673540, 681035, 681320, 681810, 690997, 702752, 804267, 804636 | ∅ | ∅ | True |
| 121 | 40-man | 1073 | 476594, 606965, 640455, 642207, 642376, 650960, 656731, 657585, 663795, 668964, 672335, 673380, 673540, 674073, 675540, 681035, 681320, 681810, 687721, 690997, 694646, 697811, 702752, 804267, 804636 | 476594, 606965, 640455, 642207, 642376, 650960, 656731, 657585, 663795, 668964, 672335, 673380, 673540, 674073, 675540, 681035, 681320, 681810, 687721, 690997, 694646, 697811, 702752, 804267, 804636 | ∅ | ∅ | True |
| 133 | Active | 1074 | 605488, 656240, 663687, 664129, 665622, 665660, 669620, 678022, 682052, 683155, 686751, 688297, 695611, 814305 | 605488, 656240, 663687, 664129, 665622, 665660, 669620, 678022, 682052, 683155, 686751, 688297, 695611, 814305 | ∅ | ∅ | True |
| 133 | 40-man | 1075 | 605488, 621139, 622663, 643410, 656240, 663687, 664129, 665622, 665660, 669372, 669620, 678022, 680684, 680723, 682052, 683155, 686751, 686930, 686993, 688297, 688497, 692013, 695034, 695611, 696522, 697812, 804556, 806960, 814305 | 605488, 621139, 622663, 643410, 656240, 663687, 664129, 665622, 665660, 669372, 669620, 678022, 680684, 680723, 682052, 683155, 686751, 686930, 686993, 688297, 688497, 692013, 695034, 695611, 696522, 697812, 804556, 806960, 814305 | ∅ | ∅ | True |
| 134 | Active | 1076 | 596133, 642397, 666808, 669199, 669387, 670990, 682254, 683003, 685126, 694753, 694973, 696062, 696149, 699008 | 596133, 642397, 666808, 669199, 669387, 670990, 682254, 683003, 685126, 694753, 694973, 696062, 696149, 699008 | ∅ | ∅ | True |
| 134 | 40-man | 1077 | 489446, 596133, 642397, 656605, 666808, 668716, 669199, 669387, 670990, 676755, 677952, 681895, 682254, 682995, 683003, 685126, 694753, 694973, 696062, 696149, 699008, 802419 | 489446, 596133, 642397, 656605, 666808, 668716, 669199, 669387, 670990, 676755, 677952, 681895, 682254, 682995, 683003, 685126, 694753, 694973, 696062, 696149, 699008, 802419 | ∅ | ∅ | True |
| 135 | Active | 1078 | 592662, 593974, 601713, 606996, 621111, 650633, 656288, 663554, 670970, 673513, 681190, 688158, 695243, 699134 | 592662, 593974, 601713, 606996, 621111, 650633, 656288, 663554, 670970, 673513, 681190, 688158, 695243, 699134 | ∅ | ∅ | True |
| 135 | 40-man | 1079 | 592094, 592662, 593974, 601713, 605397, 606996, 608337, 621111, 650633, 656288, 663554, 663773, 666745, 669093, 670970, 673513, 676664, 676702, 678184, 681190, 688158, 689690, 695243, 699134 | 592094, 592662, 593974, 601713, 605397, 606996, 608337, 621111, 650633, 656288, 663554, 663773, 666745, 669093, 670970, 673513, 676664, 676702, 678184, 681190, 688158, 689690, 695243, 699134 | ∅ | ∅ | True |
| 136 | Active | 1080 | 571948, 621074, 622554, 642100, 660825, 662253, 669302, 669923, 672841, 678606, 681867, 682243, 693433, 807739 | 571948, 621074, 622554, 642100, 660825, 662253, 669302, 669923, 672841, 678606, 681867, 682243, 693433, 807739 | ∅ | ∅ | True |
| 136 | 40-man | 1081 | 571948, 621074, 622554, 642100, 660825, 662253, 666374, 669302, 669923, 672841, 673662, 676106, 677961, 678606, 681006, 681867, 681890, 682243, 688138, 689546, 693433, 700187, 807739 | 571948, 621074, 622554, 642100, 660825, 662253, 666374, 669302, 669923, 672841, 673662, 676106, 677961, 678606, 681006, 681867, 681890, 682243, 688138, 689546, 693433, 700187, 807739 | ∅ | ∅ | True |
| 137 | Active | 1082 | 657277, 665665, 669270, 671345, 681916, 683363, 683627, 691769, 693313, 694738, 694918, 702885, 805074, 805345 | 657277, 665665, 669270, 671345, 681916, 683363, 683627, 691769, 693313, 694738, 694918, 702885, 805074, 805345 | ∅ | ∅ | True |
| 137 | 40-man | 1083 | 592858, 605288, 656529, 657277, 657424, 663941, 664141, 665665, 666711, 669270, 671345, 675920, 676130, 676254, 676775, 678495, 681916, 683363, 683627, 686790, 687931, 691769, 693313, 694738, 694820, 694918, 700280, 701474, 702885, 805074, 805345, 806185 | 592858, 605288, 656529, 657277, 657424, 663941, 664141, 665665, 666711, 669270, 671345, 675920, 676130, 676254, 676775, 678495, 681916, 683363, 683627, 686790, 687931, 691769, 693313, 694738, 694820, 694918, 700280, 701474, 702885, 805074, 805345, 806185 | ∅ | ∅ | True |
| 138 | Active | 1084 | 592773, 666277, 669461, 669467, 676617, 677865, 681517, 685464, 687273, 687309, 700241, 700669, 703725, 802408 | 592773, 666277, 669461, 669467, 676617, 677865, 681517, 685464, 687273, 687309, 700241, 700669, 703725, 802408 | ∅ | ∅ | True |
| 138 | 40-man | 1085 | 592773, 657265, 666277, 669461, 669467, 676617, 677865, 681517, 681676, 684516, 685464, 687273, 687309, 690916, 690928, 691008, 694335, 694358, 700241, 700669, 703725, 802408 | 592773, 657265, 666277, 669461, 669467, 676617, 677865, 681517, 681676, 684516, 685464, 687273, 687309, 690916, 690928, 691008, 694335, 694358, 700241, 700669, 703725, 802408 | ∅ | ∅ | True |
| 139 | Active | 1086 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 656876, 668984, 669330, 687330, 693855, 694494, 702047 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 656876, 668984, 669330, 687330, 693855, 694494, 702047 | ∅ | ∅ | True |
| 139 | 40-man | 1087 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 655889, 656876, 663556, 664076, 668984, 669169, 669330, 669438, 669947, 670955, 671212, 675627, 686752, 687330, 693855, 694494, 702047 | 571927, 592155, 607259, 641329, 642121, 642547, 643377, 655889, 656876, 663556, 664076, 668984, 669169, 669330, 669438, 669947, 670955, 671212, 675627, 686752, 687330, 693855, 694494, 702047 | ∅ | ∅ | True |
| 140 | Active | 1088 | 592866, 594798, 596001, 615698, 641302, 656641, 656756, 669022, 671936, 674003, 676395, 677958, 681217, 695239 | 592866, 594798, 596001, 615698, 641302, 656641, 656756, 669022, 671936, 674003, 676395, 677958, 681217, 695239 | ∅ | ∅ | True |
| 140 | 40-man | 1089 | 543135, 592866, 594798, 596001, 615698, 641302, 656222, 656641, 656756, 668390, 669022, 671936, 674003, 676395, 677958, 681217, 682608, 683004, 686560, 687239, 691945, 692030, 692437, 693713, 695239, 699214, 699314 | 543135, 592866, 594798, 596001, 615698, 641302, 656222, 656641, 656756, 668390, 669022, 671936, 674003, 676395, 677958, 681217, 682608, 683004, 686560, 687239, 691945, 692030, 692437, 693713, 695239, 699214, 699314 | ∅ | ∅ | True |
| 141 | Active | 1090 | 453286, 547179, 573009, 623149, 643511, 656302, 663893, 667755, 680755, 681293, 686973, 689254, 693686, 694357 | 453286, 547179, 573009, 623149, 643511, 656302, 663893, 667755, 680755, 681293, 686973, 689254, 693686, 694357 | ∅ | ∅ | True |
| 141 | 40-man | 1091 | 453286, 547179, 554340, 571578, 573009, 592791, 621244, 623149, 643511, 656302, 663893, 664074, 667755, 669310, 669456, 670102, 676454, 680755, 681293, 686973, 689149, 689254, 693686, 694357, 695445, 702056, 804619, 814005 | 453286, 547179, 554340, 571578, 573009, 592791, 621244, 623149, 643511, 656302, 663893, 664074, 667755, 669310, 669456, 670102, 676454, 680755, 681293, 686973, 689149, 689254, 693686, 694357, 695445, 702056, 804619, 814005 | ∅ | ∅ | True |
| 142 | Active | 1092 | 573124, 621345, 641927, 656546, 657746, 665152, 667297, 671737, 672782, 681892, 687570, 701519, 702193, 805673 | 573124, 621345, 641927, 656546, 657746, 665152, 667297, 671737, 672782, 681892, 687570, 701519, 702193, 805673 | ∅ | ∅ | True |
| 142 | 40-man | 1093 | 573124, 607455, 621345, 641154, 641927, 656546, 657746, 663485, 665152, 667297, 670183, 671737, 672782, 679358, 681252, 681892, 687570, 690953, 694397, 696070, 701519, 701581, 702193, 702474, 805673 | 573124, 607455, 621345, 641154, 641927, 656546, 657746, 663485, 665152, 667297, 670183, 671737, 672782, 679358, 681252, 681892, 687570, 690953, 694397, 696070, 701519, 701581, 702193, 702474, 805673 | ∅ | ∅ | True |
| 143 | Active | 1094 | 548384, 554430, 605400, 621237, 641835, 650911, 661395, 663767, 666200, 680742, 680880, 686934, 689147, 691725 | 548384, 554430, 605400, 621237, 641835, 650911, 661395, 663767, 666200, 680742, 680880, 686934, 689147, 691725 | ∅ | ∅ | True |
| 143 | 40-man | 1095 | 548384, 554430, 605400, 621237, 621383, 641482, 641745, 641835, 650911, 660604, 661395, 663767, 666200, 668873, 676661, 679775, 680742, 680880, 686934, 689147, 691330, 691725, 694851 | 548384, 554430, 605400, 621237, 621383, 641482, 641745, 641835, 650911, 660604, 661395, 663767, 666200, 668873, 676661, 679775, 680742, 680880, 686934, 689147, 691330, 691725, 694851 | ∅ | ∅ | True |
| 144 | Active | 1096 | 519242, 527048, 608718, 625643, 628452, 641816, 656550, 663559, 669276, 678061, 682989, 689266, 700363, 800311 | 519242, 527048, 608718, 625643, 628452, 641816, 656550, 663559, 669276, 678061, 682989, 689266, 700363, 800311 | ∅ | ∅ | True |
| 144 | 40-man | 1097 | 519242, 527048, 608718, 625643, 628452, 641729, 641816, 656550, 663158, 663559, 666214, 669276, 675911, 675916, 676568, 678061, 680885, 682989, 686628, 689266, 691548, 693821, 694462, 700363, 700413, 702275, 702566, 800311 | 519242, 527048, 608718, 625643, 628452, 641729, 641816, 656550, 663158, 663559, 666214, 669276, 675911, 675916, 676568, 678061, 680885, 682989, 686628, 689266, 691548, 693821, 694462, 700363, 700413, 702275, 702566, 800311 | ∅ | ∅ | True |
| 145 | Active | 1098 | 607200, 622491, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 680732, 691799, 696146, 805326 | 607200, 622491, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 680732, 691799, 696146, 805326 | ∅ | ∅ | True |
| 145 | 40-man | 1099 | 607200, 622491, 623211, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 672860, 673929, 678024, 680732, 681066, 681343, 686563, 689672, 689818, 691799, 696146, 699823, 701780, 702273, 805326 | 607200, 622491, 623211, 641743, 656794, 663436, 663542, 663855, 664353, 669684, 670950, 672860, 673929, 678024, 680732, 681066, 681343, 686563, 689672, 689818, 691799, 696146, 699823, 701780, 702273, 805326 | ∅ | ∅ | True |
| 146 | Active | 1100 | 645261, 656848, 663969, 664126, 667652, 676083, 676534, 676604, 680767, 687473, 690978, 691587, 694795, 806188 | 645261, 656848, 663969, 664126, 667652, 676083, 676534, 676604, 680767, 687473, 690978, 691587, 694795, 806188 | ∅ | ∅ | True |
| 146 | 40-man | 1101 | 645261, 656848, 663969, 664126, 667652, 669622, 676083, 676534, 676604, 676974, 677053, 678692, 680767, 682790, 684049, 687134, 687287, 687473, 687531, 687985, 690978, 691587, 694350, 694795, 702281, 800049, 806188 | 645261, 656848, 663969, 664126, 667652, 669622, 676083, 676534, 676604, 676974, 677053, 678692, 680767, 682790, 684049, 687134, 687287, 687473, 687531, 687985, 690978, 691587, 694350, 694795, 702281, 800049, 806188 | ∅ | ∅ | True |
| 147 | Active | 1138 | 543037, 605242, 607074, 608331, 621112, 642232, 657612, 661563, 670167, 670280, 687396, 693645, 701542 | 543037, 605242, 607074, 608331, 621112, 642232, 657612, 661563, 670167, 670280, 687396, 693645, 701542 | ∅ | ∅ | True |
| 147 | 40-man | 1139 | 518585, 543037, 605242, 607074, 608331, 621112, 642232, 657376, 657612, 660787, 661563, 665645, 670167, 670280, 677960, 683409, 687396, 690440, 693645, 694341, 695684, 701542 | 518585, 543037, 605242, 607074, 608331, 621112, 642232, 657376, 657612, 660787, 661563, 665645, 670167, 670280, 677960, 683409, 687396, 690440, 693645, 694341, 695684, 701542 | ∅ | ∅ | True |
| 158 | Active | 1104 | 622608, 656730, 668941, 669084, 669160, 675660, 676879, 682842, 687075, 688107, 690986, 694477, 694819, 701656 | 622608, 656730, 668941, 669084, 669160, 675660, 676879, 682842, 687075, 688107, 690986, 694477, 694819, 701656 | ∅ | ∅ | True |
| 158 | 40-man | 1105 | 605540, 622608, 642239, 656730, 657649, 668831, 668941, 669060, 669084, 669160, 672582, 675660, 676467, 676879, 681982, 682842, 682990, 687075, 688107, 689441, 690986, 694477, 694819, 701656, 702153 | 605540, 622608, 642239, 656730, 657649, 668831, 668941, 669060, 669084, 669160, 672582, 675660, 676467, 676879, 681982, 682842, 682990, 687075, 688107, 689441, 690986, 694477, 694819, 701656, 702153 | ∅ | ∅ | True |

## Evidence appendix D — appended correction ledger

Prior rows remain retained. A void successor retracts the false MLB membership claim without asserting an affiliate assignment.

| Prior interval | Successor | MLB player | Prior endpoint team | Correct MLB organization | New state | Correction mutation | Owner run |
|---:|---:|---:|---:|---:|---|---:|---:|
| 1262 | 1467 | 663366 | 484 | 134 | Void claim | 1518 | 11260 |
| 1263 | 1468 | 677957 | 484 | 134 | Void claim | 1519 | 11260 |
| 1264 | 1469 | 641962 | 484 | 134 | Void claim | 1520 | 11260 |
| 1265 | 1470 | 809733 | 484 | 134 | Void claim | 1521 | 11260 |
| 1266 | 1471 | 686951 | 484 | 134 | Void claim | 1522 | 11260 |
| 1267 | 1472 | 682981 | 484 | 134 | Void claim | 1523 | 11260 |
| 1268 | 1473 | 681895 | 484 | 134 | Void claim | 1524 | 11260 |
| 1269 | 1474 | 682995 | 484 | 134 | Void claim | 1525 | 11260 |
| 1270 | 1475 | 690382 | 484 | 134 | Void claim | 1526 | 11260 |
| 1271 | 1476 | 694298 | 484 | 134 | Void claim | 1527 | 11260 |
| 1272 | 1477 | 663562 | 484 | 134 | Void claim | 1528 | 11260 |
| 1273 | 1478 | 668716 | 484 | 134 | Void claim | 1529 | 11260 |
| 1274 | 1479 | 802419 | 484 | 134 | Void claim | 1530 | 11260 |
| 1275 | 1480 | 663366 | 484 | 134 | Void claim | 1531 | 11260 |
| 1276 | 1481 | 677957 | 484 | 134 | Void claim | 1532 | 11260 |
| 1277 | 1482 | 641962 | 484 | 134 | Void claim | 1533 | 11260 |
| 1278 | 1483 | 809733 | 484 | 134 | Void claim | 1534 | 11260 |
| 1279 | 1484 | 686951 | 484 | 134 | Void claim | 1535 | 11260 |
| 1280 | 1485 | 682981 | 484 | 134 | Void claim | 1536 | 11260 |
| 1281 | 1486 | 681895 | 484 | 134 | Void claim | 1537 | 11260 |
| 1282 | 1487 | 682995 | 484 | 134 | Void claim | 1538 | 11260 |
| 1283 | 1488 | 690382 | 484 | 134 | Void claim | 1539 | 11260 |
| 1284 | 1489 | 694298 | 484 | 134 | Void claim | 1540 | 11260 |
| 1285 | 1490 | 663562 | 484 | 134 | Void claim | 1541 | 11260 |
| 1286 | 1491 | 668716 | 484 | 134 | Void claim | 1542 | 11260 |
| 1287 | 1492 | 802419 | 484 | 134 | Void claim | 1543 | 11260 |
| 622 | 1493 | 681895 | 134 | 134 | Open MLB membership | 1544 | 11260 |
| 624 | 1494 | 682995 | 134 | 134 | Open MLB membership | 1545 | 11260 |
| 633 | 1495 | 668716 | 134 | 134 | Open MLB membership | 1546 | 11260 |
| 635 | 1496 | 802419 | 134 | 134 | Open MLB membership | 1547 | 11260 |
| 1190 | 1497 | 687900 | 342 | 115 | Void claim | 1548 | 11264 |
| 1191 | 1498 | 687060 | 342 | 115 | Void claim | 1549 | 11264 |
| 1192 | 1499 | 682769 | 342 | 115 | Void claim | 1550 | 11264 |
| 1193 | 1500 | 686900 | 342 | 115 | Void claim | 1551 | 11264 |
| 1194 | 1501 | 802686 | 342 | 115 | Void claim | 1552 | 11264 |
| 1195 | 1502 | 694968 | 342 | 115 | Void claim | 1553 | 11264 |
| 1196 | 1503 | 694860 | 342 | 115 | Void claim | 1554 | 11264 |
| 1197 | 1504 | 686662 | 342 | 115 | Void claim | 1555 | 11264 |
| 1198 | 1505 | 676105 | 342 | 115 | Void claim | 1556 | 11264 |
| 1199 | 1506 | 624522 | 342 | 115 | Void claim | 1557 | 11264 |
| 1200 | 1507 | 679057 | 342 | 115 | Void claim | 1558 | 11264 |
| 1201 | 1508 | 656786 | 342 | 115 | Void claim | 1559 | 11264 |
| 1202 | 1509 | 622256 | 342 | 115 | Void claim | 1560 | 11264 |
| 1203 | 1510 | 668943 | 342 | 115 | Void claim | 1561 | 11264 |
| 1204 | 1511 | 807743 | 342 | 115 | Void claim | 1562 | 11264 |
| 1205 | 1512 | 669298 | 342 | 115 | Void claim | 1563 | 11264 |
| 1206 | 1513 | 678368 | 342 | 115 | Void claim | 1564 | 11264 |
| 1207 | 1514 | 669445 | 342 | 115 | Void claim | 1565 | 11264 |
| 1208 | 1515 | 687900 | 342 | 115 | Void claim | 1566 | 11264 |
| 1209 | 1516 | 687060 | 342 | 115 | Void claim | 1567 | 11264 |
| 1210 | 1517 | 682769 | 342 | 115 | Void claim | 1568 | 11264 |
| 1211 | 1518 | 687145 | 342 | 115 | Void claim | 1569 | 11264 |
| 1212 | 1519 | 686900 | 342 | 115 | Void claim | 1570 | 11264 |
| 1213 | 1520 | 802686 | 342 | 115 | Void claim | 1571 | 11264 |
| 1214 | 1521 | 694968 | 342 | 115 | Void claim | 1572 | 11264 |
| 1215 | 1522 | 694860 | 342 | 115 | Void claim | 1573 | 11264 |
| 1216 | 1523 | 686662 | 342 | 115 | Void claim | 1574 | 11264 |
| 1217 | 1524 | 676105 | 342 | 115 | Void claim | 1575 | 11264 |
| 1218 | 1525 | 624522 | 342 | 115 | Void claim | 1576 | 11264 |
| 1219 | 1526 | 679057 | 342 | 115 | Void claim | 1577 | 11264 |
| 1220 | 1527 | 656786 | 342 | 115 | Void claim | 1578 | 11264 |
| 1221 | 1528 | 622256 | 342 | 115 | Void claim | 1579 | 11264 |
| 1222 | 1529 | 668943 | 342 | 115 | Void claim | 1580 | 11264 |
| 1223 | 1530 | 807743 | 342 | 115 | Void claim | 1581 | 11264 |
| 1224 | 1531 | 669298 | 342 | 115 | Void claim | 1582 | 11264 |
| 1225 | 1532 | 678368 | 342 | 115 | Void claim | 1583 | 11264 |
| 284 | 1533 | 687060 | 115 | 115 | Open MLB membership | 1584 | 11264 |
| 288 | 1534 | 682769 | 115 | 115 | Open MLB membership | 1585 | 11264 |
| 290 | 1535 | 802686 | 115 | 115 | Open MLB membership | 1586 | 11264 |
| 292 | 1536 | 676105 | 115 | 115 | Open MLB membership | 1587 | 11264 |
| 304 | 1537 | 807743 | 115 | 115 | Open MLB membership | 1588 | 11264 |
| 305 | 1538 | 669298 | 115 | 115 | Open MLB membership | 1589 | 11264 |
| 1433 | 1539 | 691012 | 5434 | 117 | Void claim | 1590 | 11264 |
| 1434 | 1540 | 695001 | 5434 | 117 | Void claim | 1591 | 11264 |
| 1435 | 1541 | 835483 | 5434 | 117 | Void claim | 1592 | 11264 |
| 1436 | 1542 | 809343 | 5434 | 117 | Void claim | 1593 | 11264 |
| 1437 | 1543 | 685005 | 5434 | 117 | Void claim | 1594 | 11264 |
| 1438 | 1544 | 694545 | 5434 | 117 | Void claim | 1595 | 11264 |
| 1439 | 1545 | 669920 | 5434 | 117 | Void claim | 1596 | 11264 |
| 1440 | 1546 | 681973 | 5434 | 117 | Void claim | 1597 | 11264 |
| 1441 | 1547 | 680588 | 5434 | 117 | Void claim | 1598 | 11264 |
| 1442 | 1548 | 678906 | 5434 | 117 | Void claim | 1599 | 11264 |
| 1443 | 1549 | 701121 | 5434 | 117 | Void claim | 1600 | 11264 |
| 1444 | 1550 | 681077 | 5434 | 117 | Void claim | 1601 | 11264 |
| 1445 | 1551 | 702462 | 5434 | 117 | Void claim | 1602 | 11264 |
| 1446 | 1552 | 682610 | 5434 | 117 | Void claim | 1603 | 11264 |
| 1447 | 1553 | 680802 | 5434 | 117 | Void claim | 1604 | 11264 |
| 1448 | 1554 | 694381 | 5434 | 117 | Void claim | 1605 | 11264 |
| 1449 | 1555 | 691012 | 5434 | 117 | Void claim | 1606 | 11264 |
| 1450 | 1556 | 695001 | 5434 | 117 | Void claim | 1607 | 11264 |
| 1451 | 1557 | 656232 | 5434 | 117 | Void claim | 1608 | 11264 |
| 1452 | 1558 | 835483 | 5434 | 117 | Void claim | 1609 | 11264 |
| 1453 | 1559 | 809343 | 5434 | 117 | Void claim | 1610 | 11264 |
| 1454 | 1560 | 685005 | 5434 | 117 | Void claim | 1611 | 11264 |
| 1455 | 1561 | 675989 | 5434 | 117 | Void claim | 1612 | 11264 |
| 1456 | 1562 | 694545 | 5434 | 117 | Void claim | 1613 | 11264 |
| 1457 | 1563 | 669920 | 5434 | 117 | Void claim | 1614 | 11264 |
| 1458 | 1564 | 681973 | 5434 | 117 | Void claim | 1615 | 11264 |
| 1459 | 1565 | 680588 | 5434 | 117 | Void claim | 1616 | 11264 |
| 1460 | 1566 | 678906 | 5434 | 117 | Void claim | 1617 | 11264 |
| 1461 | 1567 | 701121 | 5434 | 117 | Void claim | 1618 | 11264 |
| 1462 | 1568 | 681077 | 5434 | 117 | Void claim | 1619 | 11264 |
| 1463 | 1569 | 702462 | 5434 | 117 | Void claim | 1620 | 11264 |
| 1464 | 1570 | 682610 | 5434 | 117 | Void claim | 1621 | 11264 |
| 1465 | 1571 | 680802 | 5434 | 117 | Void claim | 1622 | 11264 |
| 1466 | 1572 | 694381 | 5434 | 117 | Void claim | 1623 | 11264 |
| 365 | 1573 | 695001 | 117 | 117 | Open MLB membership | 1624 | 11264 |
| 375 | 1574 | 669920 | 117 | 117 | Open MLB membership | 1625 | 11264 |
| 377 | 1575 | 678906 | 117 | 117 | Open MLB membership | 1626 | 11264 |
| 378 | 1576 | 701121 | 117 | 117 | Open MLB membership | 1627 | 11264 |
| 1367 | 1577 | 700786 | 541 | 118 | Void claim | 1628 | 11264 |
| 1368 | 1578 | 679922 | 541 | 118 | Void claim | 1629 | 11264 |
| 1369 | 1579 | 657756 | 541 | 118 | Void claim | 1630 | 11264 |
| 1370 | 1580 | 689275 | 541 | 118 | Void claim | 1631 | 11264 |
| 1371 | 1581 | 694818 | 541 | 118 | Void claim | 1632 | 11264 |
| 1372 | 1582 | 687593 | 541 | 118 | Void claim | 1633 | 11264 |
| 1373 | 1583 | 607644 | 541 | 118 | Void claim | 1634 | 11264 |
| 1374 | 1584 | 814351 | 541 | 118 | Void claim | 1635 | 11264 |
| 1375 | 1585 | 668674 | 541 | 118 | Void claim | 1636 | 11264 |
| 1376 | 1586 | 681432 | 541 | 118 | Void claim | 1637 | 11264 |
| 1377 | 1587 | 696131 | 541 | 118 | Void claim | 1638 | 11264 |
| 1378 | 1588 | 519043 | 541 | 118 | Void claim | 1639 | 11264 |
| 1379 | 1589 | 687547 | 541 | 118 | Void claim | 1640 | 11264 |
| 1380 | 1590 | 518397 | 541 | 118 | Void claim | 1641 | 11264 |
| 1381 | 1591 | 664062 | 541 | 118 | Void claim | 1642 | 11264 |
| 1382 | 1592 | 592826 | 541 | 118 | Void claim | 1643 | 11264 |
| 1383 | 1593 | 695667 | 541 | 118 | Void claim | 1644 | 11264 |
| 1384 | 1594 | 700786 | 541 | 118 | Void claim | 1645 | 11264 |
| 1385 | 1595 | 679922 | 541 | 118 | Void claim | 1646 | 11264 |
| 1386 | 1596 | 657756 | 541 | 118 | Void claim | 1647 | 11264 |
| 1387 | 1597 | 689275 | 541 | 118 | Void claim | 1648 | 11264 |
| 1388 | 1598 | 694818 | 541 | 118 | Void claim | 1649 | 11264 |
| 1389 | 1599 | 687593 | 541 | 118 | Void claim | 1650 | 11264 |
| 1390 | 1600 | 607644 | 541 | 118 | Void claim | 1651 | 11264 |
| 1391 | 1601 | 814351 | 541 | 118 | Void claim | 1652 | 11264 |
| 1392 | 1602 | 668674 | 541 | 118 | Void claim | 1653 | 11264 |
| 1393 | 1603 | 681432 | 541 | 118 | Void claim | 1654 | 11264 |
| 1394 | 1604 | 696131 | 541 | 118 | Void claim | 1655 | 11264 |
| 1395 | 1605 | 519043 | 541 | 118 | Void claim | 1656 | 11264 |
| 1396 | 1606 | 687765 | 541 | 118 | Void claim | 1657 | 11264 |
| 1397 | 1607 | 687547 | 541 | 118 | Void claim | 1658 | 11264 |
| 1398 | 1608 | 518397 | 541 | 118 | Void claim | 1659 | 11264 |
| 1399 | 1609 | 664062 | 541 | 118 | Void claim | 1660 | 11264 |
| 1400 | 1610 | 592826 | 541 | 118 | Void claim | 1661 | 11264 |
| 403 | 1611 | 695667 | 118 | 118 | Open MLB membership | 1662 | 11264 |
| 404 | 1612 | 679922 | 118 | 118 | Open MLB membership | 1663 | 11264 |
| 407 | 1613 | 657756 | 118 | 118 | Open MLB membership | 1664 | 11264 |
| 414 | 1614 | 668674 | 118 | 118 | Open MLB membership | 1665 | 11264 |
| 416 | 1615 | 681432 | 118 | 118 | Open MLB membership | 1666 | 11264 |
| 417 | 1616 | 696131 | 118 | 118 | Open MLB membership | 1667 | 11264 |
| 419 | 1617 | 687765 | 118 | 118 | Open MLB membership | 1668 | 11264 |
| 430 | 1618 | 664062 | 118 | 118 | Open MLB membership | 1669 | 11264 |
| 1324 | 1619 | 691251 | 534 | 120 | Void claim | 1670 | 11264 |
| 1325 | 1620 | 695066 | 534 | 120 | Void claim | 1671 | 11264 |
| 1326 | 1621 | 669441 | 534 | 120 | Void claim | 1672 | 11264 |
| 1327 | 1622 | 687792 | 534 | 120 | Void claim | 1673 | 11264 |
| 1328 | 1623 | 625510 | 534 | 120 | Void claim | 1674 | 11264 |
| 1329 | 1624 | 681402 | 534 | 120 | Void claim | 1675 | 11264 |
| 1330 | 1625 | 676026 | 534 | 120 | Void claim | 1676 | 11264 |
| 1331 | 1626 | 805214 | 534 | 120 | Void claim | 1677 | 11264 |
| 1332 | 1627 | 701411 | 534 | 120 | Void claim | 1678 | 11264 |
| 1333 | 1628 | 656234 | 534 | 120 | Void claim | 1679 | 11264 |
| 1334 | 1629 | 812521 | 534 | 120 | Void claim | 1680 | 11264 |
| 1335 | 1630 | 680686 | 534 | 120 | Void claim | 1681 | 11264 |
| 1336 | 1631 | 664875 | 534 | 120 | Void claim | 1682 | 11264 |
| 1337 | 1632 | 693312 | 534 | 120 | Void claim | 1683 | 11264 |
| 1338 | 1633 | 640454 | 534 | 120 | Void claim | 1684 | 11264 |
| 1339 | 1634 | 668820 | 534 | 120 | Void claim | 1685 | 11264 |
| 1340 | 1635 | 687606 | 534 | 120 | Void claim | 1686 | 11264 |
| 1341 | 1636 | 663992 | 534 | 120 | Void claim | 1687 | 11264 |
| 1342 | 1637 | 676680 | 534 | 120 | Void claim | 1688 | 11264 |
| 1343 | 1638 | 691251 | 534 | 120 | Void claim | 1689 | 11264 |
| 1344 | 1639 | 695066 | 534 | 120 | Void claim | 1690 | 11264 |
| 1345 | 1640 | 687223 | 534 | 120 | Void claim | 1691 | 11264 |
| 1346 | 1641 | 669441 | 534 | 120 | Void claim | 1692 | 11264 |
| 1347 | 1642 | 669371 | 534 | 120 | Void claim | 1693 | 11264 |
| 1348 | 1643 | 687792 | 534 | 120 | Void claim | 1694 | 11264 |
| 1349 | 1644 | 625510 | 534 | 120 | Void claim | 1695 | 11264 |
| 1350 | 1645 | 681402 | 534 | 120 | Void claim | 1696 | 11264 |
| 1351 | 1646 | 676026 | 534 | 120 | Void claim | 1697 | 11264 |
| 1352 | 1647 | 805214 | 534 | 120 | Void claim | 1698 | 11264 |
| 1353 | 1648 | 701411 | 534 | 120 | Void claim | 1699 | 11264 |
| 1354 | 1649 | 656234 | 534 | 120 | Void claim | 1700 | 11264 |
| 1355 | 1650 | 812521 | 534 | 120 | Void claim | 1701 | 11264 |
| 1356 | 1651 | 680686 | 534 | 120 | Void claim | 1702 | 11264 |
| 1357 | 1652 | 664875 | 534 | 120 | Void claim | 1703 | 11264 |
| 1358 | 1653 | 693312 | 534 | 120 | Void claim | 1704 | 11264 |
| 1359 | 1654 | 640454 | 534 | 120 | Void claim | 1705 | 11264 |
| 1360 | 1655 | 668820 | 534 | 120 | Void claim | 1706 | 11264 |
| 1361 | 1656 | 687606 | 534 | 120 | Void claim | 1707 | 11264 |
| 1362 | 1657 | 663992 | 534 | 120 | Void claim | 1708 | 11264 |
| 1363 | 1658 | 676680 | 534 | 120 | Void claim | 1709 | 11264 |
| 1364 | 1659 | 666121 | 534 | 120 | Void claim | 1710 | 11264 |
| 1365 | 1660 | 670090 | 534 | 120 | Void claim | 1711 | 11264 |
| 1366 | 1661 | 687849 | 534 | 120 | Void claim | 1712 | 11264 |
| 492 | 1662 | 687223 | 120 | 120 | Open MLB membership | 1713 | 11264 |
| 494 | 1663 | 669371 | 120 | 120 | Open MLB membership | 1714 | 11264 |
| 496 | 1664 | 687792 | 120 | 120 | Open MLB membership | 1715 | 11264 |
| 499 | 1665 | 681402 | 120 | 120 | Open MLB membership | 1716 | 11264 |
| 502 | 1666 | 656234 | 120 | 120 | Open MLB membership | 1717 | 11264 |
| 505 | 1667 | 680686 | 120 | 120 | Open MLB membership | 1718 | 11264 |
| 507 | 1668 | 693312 | 120 | 120 | Open MLB membership | 1719 | 11264 |
| 513 | 1669 | 687606 | 120 | 120 | Open MLB membership | 1720 | 11264 |
| 514 | 1670 | 663992 | 120 | 120 | Open MLB membership | 1721 | 11264 |
| 517 | 1671 | 670090 | 120 | 120 | Open MLB membership | 1722 | 11264 |
| 519 | 1672 | 687849 | 120 | 120 | Open MLB membership | 1723 | 11264 |
| 1226 | 1673 | 687856 | 400 | 133 | Void claim | 1724 | 11264 |
| 1227 | 1674 | 641386 | 400 | 133 | Void claim | 1725 | 11264 |
| 1228 | 1675 | 680723 | 400 | 133 | Void claim | 1726 | 11264 |
| 1229 | 1676 | 696522 | 400 | 133 | Void claim | 1727 | 11264 |
| 1230 | 1677 | 686533 | 400 | 133 | Void claim | 1728 | 11264 |
| 1231 | 1678 | 687195 | 400 | 133 | Void claim | 1729 | 11264 |
| 1232 | 1679 | 686857 | 400 | 133 | Void claim | 1730 | 11264 |
| 1233 | 1680 | 697812 | 400 | 133 | Void claim | 1731 | 11264 |
| 1234 | 1681 | 695034 | 400 | 133 | Void claim | 1732 | 11264 |
| 1235 | 1682 | 806960 | 400 | 133 | Void claim | 1733 | 11264 |
| 1236 | 1683 | 686930 | 400 | 133 | Void claim | 1734 | 11264 |
| 1237 | 1684 | 669422 | 400 | 133 | Void claim | 1735 | 11264 |
| 1238 | 1685 | 663321 | 400 | 133 | Void claim | 1736 | 11264 |
| 1239 | 1686 | 678163 | 400 | 133 | Void claim | 1737 | 11264 |
| 1240 | 1687 | 688497 | 400 | 133 | Void claim | 1738 | 11264 |
| 1241 | 1688 | 593833 | 400 | 133 | Void claim | 1739 | 11264 |
| 1242 | 1689 | 687856 | 400 | 133 | Void claim | 1740 | 11264 |
| 1243 | 1690 | 641386 | 400 | 133 | Void claim | 1741 | 11264 |
| 1244 | 1691 | 676275 | 400 | 133 | Void claim | 1742 | 11264 |
| 1245 | 1692 | 680723 | 400 | 133 | Void claim | 1743 | 11264 |
| 1246 | 1693 | 683020 | 400 | 133 | Void claim | 1744 | 11264 |
| 1247 | 1694 | 696522 | 400 | 133 | Void claim | 1745 | 11264 |
| 1248 | 1695 | 686533 | 400 | 133 | Void claim | 1746 | 11264 |
| 1249 | 1696 | 687195 | 400 | 133 | Void claim | 1747 | 11264 |
| 1250 | 1697 | 686857 | 400 | 133 | Void claim | 1748 | 11264 |
| 1251 | 1698 | 701364 | 400 | 133 | Void claim | 1749 | 11264 |
| 1252 | 1699 | 697812 | 400 | 133 | Void claim | 1750 | 11264 |
| 1253 | 1700 | 695034 | 400 | 133 | Void claim | 1751 | 11264 |
| 1254 | 1701 | 806960 | 400 | 133 | Void claim | 1752 | 11264 |
| 1255 | 1702 | 686930 | 400 | 133 | Void claim | 1753 | 11264 |
| 1256 | 1703 | 669422 | 400 | 133 | Void claim | 1754 | 11264 |
| 1257 | 1704 | 663321 | 400 | 133 | Void claim | 1755 | 11264 |
| 1258 | 1705 | 678163 | 400 | 133 | Void claim | 1756 | 11264 |
| 1259 | 1706 | 688497 | 400 | 133 | Void claim | 1757 | 11264 |
| 1260 | 1707 | 593833 | 400 | 133 | Void claim | 1758 | 11264 |
| 1261 | 1708 | 827734 | 400 | 133 | Void claim | 1759 | 11264 |
| 577 | 1709 | 680723 | 133 | 133 | Open MLB membership | 1760 | 11264 |
| 582 | 1710 | 696522 | 133 | 133 | Open MLB membership | 1761 | 11264 |
| 589 | 1711 | 697812 | 133 | 133 | Open MLB membership | 1762 | 11264 |
| 592 | 1712 | 695034 | 133 | 133 | Open MLB membership | 1763 | 11264 |
| 594 | 1713 | 806960 | 133 | 133 | Open MLB membership | 1764 | 11264 |
| 597 | 1714 | 686930 | 133 | 133 | Open MLB membership | 1765 | 11264 |
| 600 | 1715 | 688497 | 133 | 133 | Open MLB membership | 1766 | 11264 |
| 1401 | 1716 | 702065 | 1960 | 142 | Void claim | 1767 | 11264 |
| 1402 | 1717 | 691576 | 1960 | 142 | Void claim | 1768 | 11264 |
| 1403 | 1718 | 690217 | 1960 | 142 | Void claim | 1769 | 11264 |
| 1404 | 1719 | 679358 | 1960 | 142 | Void claim | 1770 | 11264 |
| 1405 | 1720 | 670183 | 1960 | 142 | Void claim | 1771 | 11264 |
| 1406 | 1721 | 608566 | 1960 | 142 | Void claim | 1772 | 11264 |
| 1407 | 1722 | 681252 | 1960 | 142 | Void claim | 1773 | 11264 |
| 1408 | 1723 | 657240 | 1960 | 142 | Void claim | 1774 | 11264 |
| 1409 | 1724 | 694397 | 1960 | 142 | Void claim | 1775 | 11264 |
| 1410 | 1725 | 621199 | 1960 | 142 | Void claim | 1776 | 11264 |
| 1411 | 1726 | 695308 | 1960 | 142 | Void claim | 1777 | 11264 |
| 1412 | 1727 | 690462 | 1960 | 142 | Void claim | 1778 | 11264 |
| 1413 | 1728 | 801594 | 1960 | 142 | Void claim | 1779 | 11264 |
| 1414 | 1729 | 694536 | 1960 | 142 | Void claim | 1780 | 11264 |
| 1415 | 1730 | 702065 | 1960 | 142 | Void claim | 1781 | 11264 |
| 1416 | 1731 | 691576 | 1960 | 142 | Void claim | 1782 | 11264 |
| 1417 | 1732 | 690217 | 1960 | 142 | Void claim | 1783 | 11264 |
| 1418 | 1733 | 689520 | 1960 | 142 | Void claim | 1784 | 11264 |
| 1419 | 1734 | 679358 | 1960 | 142 | Void claim | 1785 | 11264 |
| 1420 | 1735 | 670183 | 1960 | 142 | Void claim | 1786 | 11264 |
| 1421 | 1736 | 608566 | 1960 | 142 | Void claim | 1787 | 11264 |
| 1422 | 1737 | 681252 | 1960 | 142 | Void claim | 1788 | 11264 |
| 1423 | 1738 | 657240 | 1960 | 142 | Void claim | 1789 | 11264 |
| 1424 | 1739 | 696070 | 1960 | 142 | Void claim | 1790 | 11264 |
| 1425 | 1740 | 694397 | 1960 | 142 | Void claim | 1791 | 11264 |
| 1426 | 1741 | 621199 | 1960 | 142 | Void claim | 1792 | 11264 |
| 1427 | 1742 | 683764 | 1960 | 142 | Void claim | 1793 | 11264 |
| 1428 | 1743 | 695308 | 1960 | 142 | Void claim | 1794 | 11264 |
| 1429 | 1744 | 690462 | 1960 | 142 | Void claim | 1795 | 11264 |
| 1430 | 1745 | 803276 | 1960 | 142 | Void claim | 1796 | 11264 |
| 1431 | 1746 | 801594 | 1960 | 142 | Void claim | 1797 | 11264 |
| 1432 | 1747 | 694536 | 1960 | 142 | Void claim | 1798 | 11264 |
| 938 | 1748 | 679358 | 142 | 142 | Open MLB membership | 1799 | 11264 |
| 939 | 1749 | 670183 | 142 | 142 | Open MLB membership | 1800 | 11264 |
| 940 | 1750 | 681252 | 142 | 142 | Open MLB membership | 1801 | 11264 |
| 943 | 1751 | 696070 | 142 | 142 | Open MLB membership | 1802 | 11264 |
| 945 | 1752 | 694397 | 142 | 142 | Open MLB membership | 1803 | 11264 |
| 1288 | 1753 | 680572 | 531 | 147 | Void claim | 1804 | 11264 |
| 1289 | 1754 | 529017 | 531 | 147 | Void claim | 1805 | 11264 |
| 1290 | 1755 | 690440 | 531 | 147 | Void claim | 1806 | 11264 |
| 1291 | 1756 | 694341 | 531 | 147 | Void claim | 1807 | 11264 |
| 1292 | 1757 | 815454 | 531 | 147 | Void claim | 1808 | 11264 |
| 1293 | 1758 | 702130 | 531 | 147 | Void claim | 1809 | 11264 |
| 1294 | 1759 | 669212 | 531 | 147 | Void claim | 1810 | 11264 |
| 1295 | 1760 | 695684 | 531 | 147 | Void claim | 1811 | 11264 |
| 1296 | 1761 | 801432 | 531 | 147 | Void claim | 1812 | 11264 |
| 1297 | 1762 | 675296 | 531 | 147 | Void claim | 1813 | 11264 |
| 1298 | 1763 | 623437 | 531 | 147 | Void claim | 1814 | 11264 |
| 1299 | 1764 | 694805 | 531 | 147 | Void claim | 1815 | 11264 |
| 1300 | 1765 | 669740 | 531 | 147 | Void claim | 1816 | 11264 |
| 1301 | 1766 | 814392 | 531 | 147 | Void claim | 1817 | 11264 |
| 1302 | 1767 | 660787 | 531 | 147 | Void claim | 1818 | 11264 |
| 1303 | 1768 | 684725 | 531 | 147 | Void claim | 1819 | 11264 |
| 1304 | 1769 | 680572 | 531 | 147 | Void claim | 1820 | 11264 |
| 1305 | 1770 | 529017 | 531 | 147 | Void claim | 1821 | 11264 |
| 1306 | 1771 | 683409 | 531 | 147 | Void claim | 1822 | 11264 |
| 1307 | 1772 | 690440 | 531 | 147 | Void claim | 1823 | 11264 |
| 1308 | 1773 | 694341 | 531 | 147 | Void claim | 1824 | 11264 |
| 1309 | 1774 | 809137 | 531 | 147 | Void claim | 1825 | 11264 |
| 1310 | 1775 | 801739 | 531 | 147 | Void claim | 1826 | 11264 |
| 1311 | 1776 | 815454 | 531 | 147 | Void claim | 1827 | 11264 |
| 1312 | 1777 | 702130 | 531 | 147 | Void claim | 1828 | 11264 |
| 1313 | 1778 | 669212 | 531 | 147 | Void claim | 1829 | 11264 |
| 1314 | 1779 | 695684 | 531 | 147 | Void claim | 1830 | 11264 |
| 1315 | 1780 | 801432 | 531 | 147 | Void claim | 1831 | 11264 |
| 1316 | 1781 | 675296 | 531 | 147 | Void claim | 1832 | 11264 |
| 1317 | 1782 | 623437 | 531 | 147 | Void claim | 1833 | 11264 |
| 1318 | 1783 | 694805 | 531 | 147 | Void claim | 1834 | 11264 |
| 1319 | 1784 | 669740 | 531 | 147 | Void claim | 1835 | 11264 |
| 1320 | 1785 | 684608 | 531 | 147 | Void claim | 1836 | 11264 |
| 1321 | 1786 | 814392 | 531 | 147 | Void claim | 1837 | 11264 |
| 1322 | 1787 | 660787 | 531 | 147 | Void claim | 1838 | 11264 |
| 1323 | 1788 | 684725 | 531 | 147 | Void claim | 1839 | 11264 |
| 1128 | 1789 | 683409 | 147 | 147 | Open MLB membership | 1840 | 11264 |
| 1129 | 1790 | 690440 | 147 | 147 | Open MLB membership | 1841 | 11264 |
| 1130 | 1791 | 694341 | 147 | 147 | Open MLB membership | 1842 | 11264 |
| 1136 | 1792 | 695684 | 147 | 147 | Open MLB membership | 1843 | 11264 |
| 1149 | 1793 | 660787 | 147 | 147 | Open MLB membership | 1844 | 11264 |


## Evidence appendix E — governed downstream completion

Requests 2 and 3 completed through the SP-13 check owner at 13:48:56 and 14:00:16 UTC respectively. Root SyncRuns are 11260 and 11264. Only these request IDs were checked; unrelated repair 1 was not advanced. Existing queued check jobs 4095 and 4106 remain redundant no-op follow-ups for completed requests because broad checker-worker coverage is outside this package. SP-13 completion records successful owner-job termination, not publishable derived completeness.

| MLB club | SP-13 request | SP-05 job | Correction mutations | SP-09 plan | SP-10 job / cohort | Cohort state | Snapshots | Watermark current | Publication job |
|---:|---:|---:|---:|---:|---|---|---:|---|---|
| 134 | 2 | 4094 | 30 | 523 | 4097 / 516 | Partial | 1299 | Yes | None |
| 115 | 3 | 4099 | 42 | 524 | 4114 / 517 | Partial | 1301 | Yes | None |
| 117 | 3 | 4100 | 38 | 525 | 4115 / 518 | Partial | 1301 | Yes | None |
| 118 | 3 | 4101 | 42 | 526 | 4116 / 519 | Partial | 1301 | Yes | None |
| 120 | 3 | 4102 | 54 | 527 | 4117 / 520 | Partial | 1301 | Yes | None |
| 133 | 3 | 4103 | 43 | 528 | 4118 / 521 | Partial | 1303 | Yes | None |
| 142 | 3 | 4104 | 37 | 529 | 4119 / 522 | Partial | 1302 | Yes | None |
| 147 | 3 | 4105 | 41 | 530 | 4120 / 523 | Partial | 1304 | Yes | None |

All eight new cohorts have failed roster_composition and organizational_depth domains with roster_authority_incomplete:<club>, with dependent domains withheld. This is the existing public roster-readiness dependency, separate from the corrected SP-05 source/interval health. No derived row or historical cohort was manually edited to force completion. The roster correction therefore does not certify CR-04, public atomic authority, or legacy retirement.

All 136 original roster observations and all 1,517 original membership mutations compared equal to the pre-repair census. All 327 prior interval fact records remain unchanged, with current-version lifecycle markers updated through the correction owner. Publication 1 remains identical across all stored columns, with pointer 1 and 1,013 artifacts. No duplicate open current non-void player/team/type grain exists.


## Production controls at the proof checkpoint

The Render environment UI was read after deployment. SYNC_PIPELINE_ENABLED=true, SYNC_PIPELINE_SHADOW_MODE=true, SYNC_PIPELINE_PUBLICATION_ENABLED=false, SYNC_PIPELINE_MORNING_ENABLED=false, SYNC_PIPELINE_CLOSURE_ENABLED=false, BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true, and BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true. SYNC_PIPELINE_ATOMIC_READS_ENABLED is absent from both the complete service and linked-group key lists and resolves to false under the code default. No secret files were present. No environment value, command, schedule, or service configuration was edited. The service remains on feat/sync-pipeline with its original three-minute command.

Local main remains 653d41450c2d09e42044c5848d2eb8ee7ef1b851. The original untracked full audit and unrelated local artifacts were preserved. Implementation commits are 1917fefa7a3420e69580a46bfbeea58ce1183c67 and 063993258630284c9e9ee34deb13cd021f9bf8d4, merged by PR #831 into integration at 9df21a4724d5fa2298042d171c46c790aeb5a072.
