# AUDIT-R1 â€” MLB Roster Authority Isolation & Governed Historical Correction

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

Sixteen directly affected impact plans are 492â€“507, with cohorts 485â€“500. Eight older baseline plans (42, 44, 45, 58, 60, 61, 69, 86) are also linked to the original parent intervals; their association is historical lineage, not proof they were built from the later incorrect closure. No repair or closure directly descended from the incorrect plans at the census. Existing repair 1 is the unrelated final-game repair and remains outside this remediation.


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

Production repair has not yet been applied at this review checkpoint. Required sequence: reviewed integration merge â†’ additive migration â†’ exact deployed code verification â†’ read-only refresh â†’ bounded SP-13 request â†’ SP-05 correction â†’ SP-09 impact â†’ SP-10 replacement cohorts â†’ exact parity and natural recurrence proof. Publication and atomic reads remain disabled.

The SP-05 correction primitive preserves original interval records, appends corrected versions, and records request identity in correction reason plus SyncRun/job ancestry. Affiliate claims become void versions. Current compatibility projections pointing to the affected affiliate use the retained official parent organization; valid MLB roster inclusion continues to own positive MLB roster projection. Active tracking flags retain their existing product contract. This does not redesign legacy assignment synchronization.

## 13. Before/after exact source parity

Before: **30/30 active exact; 22/30 40-man exact; 50 missing 40-man pitchers; zero extra MLB members.** Denominator is the canonical MLB registry. Member sets contain official pitcher and two-way entries, not every position player. Source identity, represented date, and retained payload are required; a nonempty canonical count is insufficient.

After: pending governed production repair. The complete before sets are recorded below; the final production receipt must contain the same per-club comparison.

## 14. Downstream impact

Directly incorrect plans 492â€“507 and cohorts 485â€“500 remain untouched. Parent correction and affiliate void versions change their roster manifests through normal authoritative inputs. Focused tests verify the original parent manifest changes after correction and affiliate observation-only changes do not alter it. Current candidate revalidation must reject the old manifests after repair; stored historical status need not be rewritten.

Publication 1 (cohort 330, plan 337) remains immutable with fingerprint `45c5d0957c8296e9e5b1cd045fd6eb930a74f711ba3670cea67644a0482f27c2`. It predates the September 11 invalid claims and is not descended from the 16 incorrect plans. It is not reader-complete and cannot certify corrected current roster authority. No pointer movement is part of AUDIT-R1.

## 15. Production proof

Pending at this review checkpoint. The integration service was rechecked on the audited SHA with its existing three-minute shadow command. No Render flags, public authority, or production data have been changed during implementation and census. Exact repair receipts and recurring-cycle evidence will be appended only after execution.

## 16. Remaining limitations

Affiliate active/40Man records remain source evidence; this package does not certify general historical assignment intervals, option eligibility, or minor-league workload. Date-only roster evidence cannot recover unavailable intra-day timing. Unknown parent metadata remains an explicit unresolved route. Independent later stints or missing dated evidence fail closed for further bounded review. Broad legacy-writer coexistence, CR-04, publication readiness, closure, and replay semantics remain outside AUDIT-R1.

## 17. Validation

Initial focused PostgreSQL run: 36 passed. Expanded PostgreSQL run: 114 passed, including correction history, parent/affiliate concurrency, scoped uniqueness, transaction routing, interval lookup, migration preservation, and downgrade protection. The retained-production-source PostgreSQL rehearsal reproduced all 327 incorrect claims, applied bounded SP-13/SP-05 correction for all eight clubs, and reached 30/30 active, 30/30 40-man, zero unresolved authority violations, 327 correction mutations, and 277 void versions. It exposed and corrected a queue dedupe-key length issue; dedupe now hashes exact mutation IDs while preserving the IDs in the payload. Resuming the already-corrected Pittsburgh request produced zero mutations. Full PR CI remains required for the final verdict. Tests used an isolated local PostgreSQL 16 container; production census connections enforced read-only transactions and a statement timeout.

## 18. Verdict

**PENDING â€” implementation review checkpoint, not AUDIT-R1 PASS.** Code and fixture proof do not substitute for governed production correction, 30/30 exact parity, natural recurrence, and green full CI. Main remains untouched.

## Evidence appendix A â€” all affected players and intervals

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
| 1136 | Elmer RodrÃ­guez / 695684 / 715 | 147 / 147 | 40 | 2026-09-10 / 2026-09-11 | 210 (147:40Man); 1114 (531:40Man) | 518/6888; 3923/10752 | 1136,1335 | 86,498 / 81,491 |
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
| 1295 | Elmer RodrÃ­guez / 695684 / 715 | 531 / 531 | A | 2026-09-11 / open | 1113 (531:active); - (-) | 3923/10752; -/- | 1313 | 499 / 492 |
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
| 1314 | Elmer RodrÃ­guez / 695684 / 715 | 531 / 531 | 40 | 2026-09-11 / open | 1114 (531:40Man); - (-) | 3923/10752; -/- | 1336 | 499 / 492 |
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
| 1406 | GermÃ¡n MÃ¡rquez / 608566 / 414 | 1960 / 1960 | A | 2026-09-11 / open | 1119 (1960:active); - (-) | 3926/10752; -/- | 1448 | 505 / 498 |
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
| 1421 | GermÃ¡n MÃ¡rquez / 608566 / 414 | 1960 / 1960 | 40 | 2026-09-11 / open | 1120 (1960:40Man); - (-) | 3926/10752; -/- | 1465 | 505 / 498 |
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
| 1446 | Roddery MuÃ±oz / 682610 / 1007 | 5434 / 5434 | A | 2026-09-11 / open | 1121 (5434:active); - (-) | 3927/10752; -/- | 1493 | 507 / 500 |
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
| 1464 | Roddery MuÃ±oz / 682610 / 1007 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1515 | 507 / 500 |
| 1465 | Ryan Weiss / 680802 / 1003 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1516 | 507 / 500 |
| 1466 | Trey McLoughlin / 694381 / 1179 | 5434 / 5434 | 40 | 2026-09-11 / open | 1122 (5434:40Man); - (-) | 3927/10752; -/- | 1517 | 507 / 500 |

## Evidence appendix B â€” exact before source/canonical sets

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
