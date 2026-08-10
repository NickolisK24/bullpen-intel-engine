# BaseballOS Product Roadmap & Decision Ledger

| Field | Value |
|---|---|
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 3.6 |
| Effective date | August 10, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `b328c917c6813831db167f4f70a57fd1ff3aa847`; Phase 1A closeout evidence through runs `31393177954` and `31395294655`; closeout recorded by PR #628 |
| Decision basis | Decision Ledger through D-052 |
| Supersedes | Version 3.5 current-state wording while preserving every durable prior decision and its repository evidence |
| Detailed predecessor archive | `docs/archive/2026-08/PRODUCT_ROADMAP_DECISION_LEDGER_PRE_V3.md` |
| Update rule | Update after a priority change, material merge, phase exit, production incident, authority decision, risk change, or false current-state statement |
| Review cadence | Weekly founder review; immediate update after a material production or product decision |

> **One active objective. One canonical roadmap. Every durable decision recorded.**

## 1. How to Use This Roadmap

- Work from the active objective downward.
- Do not begin a lower-priority item while an unblocked higher-priority trust item is open.
- A lower-priority package may proceed only when the higher item is genuinely blocked by time, external evidence, or an explicit Decision Ledger deferment.
- Every significant completed item receives a branch, pull request, commit, test record, and production-evidence record where applicable.
- Every durable product, intelligence, architecture, authority, or operating decision receives a Decision Ledger entry.
- New ideas enter the backlog here; they do not create a competing roadmap.
- Historical plans, audits, and archived verbose ledger entries remain evidence but do not override this document.

The Roadmap decides sequence. It cannot weaken the Constitution, Bullpen Intelligence Standard, Product Experience Standard, Platform Architecture and Operations Manual, or Editorial and Distribution Standard.

## 2. Executive State

BaseballOS is a live public MLB bullpen-intelligence platform with a mature trust foundation, a defensible canonical appearance record, governed publication gates, immutable historical claims, and production evidence strong enough to close the game-driven ingestion authority-qualification phase without granting production write authority.

The platform currently provides:

- a daily front door, full-league Dashboard, Team Boards, comparison, reliever discovery, and pitcher detail;
- workload and availability intelligence with active-roster separation and official appearance evidence;
- backend-owned Team State and arm-read authorities;
- trusted league snapshots and team-progressive publication;
- immutable Share Artifacts with integrity, lifecycle, and permanent historical pages;
- read-only incident, correction, completeness, and qualification audits;
- daily and postgame game-driven ingestion lanes operating in shadow;
- a four-shard PostgreSQL CI confidence gate plus lockfile-faithful frontend test/build validation;
- canonical Team State delivery to live reader surfaces;
- schedule-only, first-attempt-only production daily execution with Team Board, Compare, and Tonight bound to trusted publication authority;
- proven manual one-game entry into the governed write-capable game-driven lane with zero baseball-data mutation.

The immediate objective is no longer authority qualification. **Phase 1A is complete.** The next trust blocker is SEC-001 (#595): remove raw fatigue scores, component scores, internal risk tiers, and sequential internal identifiers from unauthenticated public API responses.

No game-driven production authority moves with this phase exit. Daily and postgame remain shadow, backfill remains off, the legacy sync/postgame writer remains authoritative, automated game-driven writes remain unapproved, and game-driven publication authority remains unapproved.

## 3. Current Repository and Authority State

| Area | Current state | Meaning |
|---|---|---|
| Repository main | `b328c917c6813831db167f4f70a57fd1ff3aa847` | Current baseline used for the Phase 1A closeout audits and qualification |
| OPS-002 (#620) | Complete | Three consecutive scheduled first-attempt daily runs passed after D-051: `31252933643`, `31308567552`, `31382023524` |
| Daily-sync runtime headroom | Proven temporary mitigation | Runtime-budget mitigation is production-proven; permanent work reduction remains separate follow-up |
| Trusted public serving | D-051 active | Team Board and Compare serve trusted Dashboard publication authority; Tonight cannot live-build publicly from unpublished mutable acquisition state |
| Production daily trigger | Scheduled, first attempt only | Production manual full-daily dispatch, local production daily invocation, the legacy admin daily route, and GitHub reruns are not authoritative execution paths |
| Game-driven daily lane | Shadow | Observation only; no automated baseball-data writes |
| Game-driven postgame lane | Shadow | Exact-cycle observation after the legacy postgame writer |
| Backfill lane | Off | No automatic game-driven backfill authority |
| Production writer | Legacy sync/postgame path | Remains authoritative for baseball-data mutation |
| Automated game-driven write mode | Unapproved | The manual no-op PASS grants no future or scheduled mutation authority |
| Game-driven publication authority | Unapproved | Publication authority has not transferred |
| D-044 blocker scope | Implemented and production-observed | Shadow bookkeeping backlog is observational; real baseball deficits remain fail-closed |
| OPS-001 (#593) | Complete | Closed August 10 after the required scheduled observation window proved useful signal separation |
| No-op candidate audit | Complete | Run `31393177954` found five eligible deterministic targets read-only; suggested game `823924` |
| Manual no-op write qualification | PASS | Run `31395294655` entered write-capable mode for game `823924`, mutated zero baseball rows, and matched the exact governed lane-ledger delta |
| UX-001 (#590) | Complete | Canonical Team State delivery proven in corrected production |
| PROD-001 (#592) | Complete | Scheduled production proof complete |
| CI-001 (#599) | Complete | Frontend CI uses the lockfile and requires tests plus production build |

## 4. Active Objective

> **Product Credibility Pass - SEC-001 (#595): remove raw fatigue scores and internal IDs from the public API**

Phase 1A authority qualification is closed. Work now returns to the public-contract sequence.

### Required direction

1. Identify every unauthenticated endpoint that exposes raw fatigue/composite scores, component scores, internal risk tiers, or database identifiers.
2. Confirm current frontend/public consumers before narrowing the response contract.
3. Replace raw ORM-style serialization with purpose-built public view models, or move scored surfaces behind explicit admin/internal authorization.
4. Add public API contract tests that prohibit raw/composite scores and sequential internal IDs.
5. Verify the deployed unauthenticated response contains only approved public labels, evidence, and freshness fields.
6. Preserve internal scored access only where explicitly authorized and documented.

### Exit evidence

- no unauthenticated public API response exposes `raw_score`, component `*_score` fields, internal `risk_level`, `id`, or `pitcher_id`;
- no public frontend path depends on removed fields;
- production smoke proves the public response matches the approved contract;
- admin/internal scored access, if retained, is positively authorized;
- no naked score remains a BaseballOS public claim.

### Implementation state

Repository work is complete and validated; the deployed proof is not yet taken, so #595 remains open.

#### Recorded identifier scope

The exit-evidence wording above is the original issue language and is preserved verbatim. This is how its identifier clause is being satisfied, recorded transparently so the completion state cannot be read more broadly than the work actually delivered:

- **In scope, delivered.** SEC-001 removes the internal serialization database identifiers exposed by fatigue serialization — `FatigueScore.id` and `FatigueScore.pitcher_id` — from anonymous fatigue-derived payloads. These exist only to correlate score rows and had no public purpose.
- **Out of scope, unchanged.** The platform-wide `Pitcher.id` routing identity is a pre-existing, separate architectural concern. It is not introduced, widened, or resolved by #595.
- **Why it is temporarily unchanged.** Migrating public pitcher identity to `mlb_id` would affect public routes, frontend deep links, persisted Dashboard snapshots, and potentially immutable historical Share Artifacts that already carry the current identifier. That reaches publication and artifact-immutability authority, which this issue explicitly must not change.
- **Not claimed.** #595 does not solve the broader public routing-identifier question. Any future decision to migrate it needs its own issue, its own approval, and its own artifact/snapshot compatibility analysis.

Satisfied in the repository:

- `GET /api/bullpen/fatigue`, `GET /api/bullpen/fatigue/<pitcher_id>`, and `GET /api/bullpen/teams/<team_id>/bullpen` serve a purpose-built public workload view model — counted workload plus the read's freshness stamp — instead of broad `FatigueScore` ORM serialization;
- board cards published by `/teams/<team_id>/board`, `/dashboard`, `/landscape`, `/teams/compare`, and `/intelligence/tonight` no longer carry a composite;
- `/stats/overview` and the dashboard `stats_overview` report scored coverage only, without the league risk-tier breakdown or the league average composite;
- the anonymous availability explanation cites counted workload instead of a "Recent workload index" value;
- `availability.inputs` no longer publishes the composite or the internal tier;
- `risk_level` is no longer a public filter, so the tier cannot be reconstructed by partitioning the public list;
- an application response boundary recursively strips the internal scoring vocabulary from anonymous JSON, including payloads read back from snapshots written before this change;
- contract tests assert absence recursively, and assert it both with and without that boundary installed, so a serializer cannot pass on the backstop alone.

**Internal scored access is retained and explicitly authorized.** `GET /api/bullpen/fatigue/snapshot` keeps the composite, the component sub-scores, the internal tier, and the score row identifiers behind the existing `require_admin_token` guard. It is an internal validation view, not a BaseballOS public claim, and anonymous callers are refused by the established 401 behavior. The response boundary exempts admin-authorized requests only.

**Public pitcher identity is unchanged.** Consistent with the recorded identifier scope above, the removed identifiers are the `FatigueScore` row's primary key and its `pitcher_id` foreign key. How a public surface addresses a pitcher is untouched: identity continues to travel on the pitcher object, and the public deep-link and detail routes are unchanged. `Pitcher.id` therefore remains a sequential identifier on public surfaces, and this work does not claim otherwise.

Outstanding for closure:

- request each affected unauthenticated endpoint against deployed production, inspect the JSON recursively, and confirm the forbidden keys are absent while approved labels, evidence, and freshness remain.

Tracked separately, not blocking #595:

- decide whether the platform-wide `Pitcher.id` public routing identity should migrate to `mlb_id`, including the effect on persisted Dashboard snapshots and immutable historical Share Artifacts.

## 5. Nightly Operating State

The production-evidence closeout that blocked the Product Credibility Pass is complete:

- OPS-002 is closed after three consecutive scheduled first-attempt daily successes;
- OPS-001 (#593) is closed after its scheduled observation requirement;
- the no-op candidate question is resolved by production read-only audit;
- the governed write-capable path is positively qualified by a one-game no-op PASS;
- all Phase 1A evidence preserves the existing authority boundaries.

No additional Phase 1A observation window is required for phase closure. Future scheduled evidence remains ordinary regression/operations evidence unless it exposes a new defect.

The permanent daily-sync work-reduction program remains important but is not a Phase 1A closure blocker: GameLog candidate prefiltering, incremental roster synchronization, and incremental transaction synchronization remain separately sequenced reliability work.

## 6. Next Approved Work

Work proceeds in this order unless a Decision Ledger entry changes it:

1. **#595 - Public raw fatigue-score containment.** Remove or protect unauthenticated composite scores, component scores, risk tiers, and internal identifiers. Repository work is complete; the remaining step is inspecting the deployed unauthenticated responses.
2. **#591 - Backend-owned Why copy.** Remove frontend regex rewriting, filtering, fallback invention, or silent dropping of governed public explanation text.
3. **#594 - Routed/static team metadata and freshness.** Give the 30 team preview routes a canonical owner, canonical vocabulary, named evidence, and data-through context. Repository work is complete; the remaining step is inspecting the deployed pages and one social preview after the next scheduled export.
4. **#600 - `/bullpen` H1 and accessibility structure.** Complete the semantic page contract.
5. **#598 - Generated-content CI validation.** Ensure automated generated-content commits cannot bypass validation.
6. **#601 - Dependency remediation.** Govern vulnerable dependencies and keep visible audit gates.
7. **Permanent daily-sync work reduction.** Add GameLog candidate prefiltering plus incremental roster and transaction synchronization.
8. **Portable Intelligence.** Canonical raster renderer, artifact-specific Open Graph/X metadata, share actions, and evidence-inspection funnel.
9. **Resume M-001 Active Bullpen ERA.** Finish registry parameters, group/contributor evidence, Team Board delivery, and full trust gates.
10. **Daily Habit and Consequence.** Public What Changed, team movement, Today lead authority, game-aware slate, and quiet-day behavior.

## 7. Current Capability Assessment

### Product surfaces

| Surface | Current state | Main gap | Governing next move |
|---|---|---|---|
| Today | Live daily front door, trusted-public serving posture | Stronger lead and game-aware context | Daily Habit after higher-priority work |
| Dashboard | Live league board; canonical per-team Team State | Stronger named evidence per team | Named-arm evidence expansion |
| Team Board | Flagship team surface bound to trusted Dashboard publication authority | Why-copy ownership; performance/starter evidence | #591, then M-001 |
| Compare | Descriptive two-team comparison bound to trusted Dashboard publication authority | H1, stronger named differences | #600 |
| Reliever Finder | Search-first utility | Public scored-field contract; H1/accessibility | #595, then #600 |
| Pitcher Detail | De-scored, evidence-first recent work | Active-group performance and later pitch-trend depth | M-001; offseason trends |
| Stories | Live narrative feed | Specificity, named arms, evidence, suppression | Ongoing quality work |
| Methodology | Teaches canonical public language | Live product must continue matching it | Maintain through public-contract work |
| Data & Trust | Strong public differentiator | Current method/incident history and scope clarity | Ongoing trust alignment |
| Share Artifact | Immutable historical page implemented | Canonical image, crawler-visible claim metadata, complete actions | Portable Intelligence |
| Routed team previews | Thirty routes carry canonical Team State, a data-through date, and the trusted snapshot they were generated from | Deployed verification of the regenerated pages | #594 production closeout |
| Internal Product Intelligence | Artifact, traffic, operations views exist | Keep observer/refusal/publication signals actionable | Maintain; do not expand speculatively |

### Intelligence and operations

| Capability | State | Assessment |
|---|---|---|
| Official appearance ledger | Production / publication-critical | Canonical recorded outs, starter distinction, and appearance-team authority remain core trust assets |
| Active roster/team authority | Production | Unknown and conflict states fail closed; historical appearance ownership stays separate |
| Arm reads and roles | Production | Backend-owned public labels exist |
| Team State authority | Production | Exactly Fresh / Stretched / Vulnerable; backend-owned and derived from the canonical active bullpen |
| Trusted league snapshots | Production | Whole-slate authority and appearance gate remain fail-closed |
| Team-progressive publication | Production | Eligible teams may publish independently after team-scoped proof |
| Game-driven ingestion | Shadow; Phase 1A qualification complete | Daily/postgame observe; no-op write-capable path proven; legacy writer remains authoritative |
| Active Bullpen ERA | Contract complete; implementation paused | D-021 through D-030 fully specify M-001; remains non-public |
| Starter/rotation transfer | Partial | Official starter authority is hardened; consequence layer incomplete |
| Immutable Share Artifacts | Production foundation | Artifact, lifecycle, integrity, audit, and public history are real; travel layer incomplete |
| Leverage/concentration | Partial | Requires a published method, named evidence, and suppression |
| Pitch characteristics | Experimental / planned | Offseason depth after product correctness and distribution |

## 8. Canonical Priority Matrix

### Critical / high trust work

| Status | Work item | Exit evidence |
|---|---|---|
| Complete | OPS-002 (#620) runtime reliability | Three scheduled first-attempt PASS runs: `31252933643`, `31308567552`, `31382023524` |
| Complete | OPS-001 (#593) scheduled separation proof | Required scheduled window plus natural failure/success separation; issue closed |
| Complete | No-op candidate determination | Read-only run `31393177954`, `COMPLETE_ELIGIBLE_FOUND` |
| Complete | Manual no-op write qualification | Run `31395294655`, `PASS`, zero baseball-data mutation |
| Complete | Phase 1A Authority Qualification | D-052 |
| Complete | PROD-001 (#592) | Full source persisted/read back; Tonight and Dashboard verification passed |
| Complete | UX-001 (#590) | Canonical Team State production closeout |
| **Active - implementation complete, deployed verification outstanding** | SEC-001 (#595) | Public scored/internal fields removed or explicitly protected. Repository work is merged-ready: public fatigue routes serve a narrowed workload view model, the board card and league stats overview no longer publish a composite or risk tier, the availability explanation cites counted workload instead of the composite, the internal tier is no longer a public filter, and a response boundary strips the scoring vocabulary from anonymous JSON. Scored access is retained behind the existing `require_admin_token` guard. The identifiers removed are the fatigue-serialization database identifiers (`FatigueScore.id`, `FatigueScore.pitcher_id`); the platform-wide `Pitcher.id` routing identity is a separate pre-existing concern and is unchanged. The issue stays open until the deployed unauthenticated response is inspected. |
| Maintain | Official appearance record | Ledger, starter, outs, appearance-team, and official-line checks stay green |
| Maintain | Canonical documentation | Current documents contain no false execution authority |

### High - public correctness and freshness

| Status | Work item | Definition of done |
|---|---|---|
| Open | FE-001 (#591) | Backend owns Why copy; frontend renders without rewriting or dropping it |
| Repository complete; deployed verification outstanding | DIST-003 (#594) | Static/routed descriptions use canonical state, evidence, and data-through date |
| Open | UX-002 (#600) | Exactly one contextual H1 per `/bullpen` view with logical hierarchy |
| Complete | CI-001 (#599) | `npm ci`, full tests, required production build, mutation-tested contract |
| Open | CI-003 (#598) | Generated-content publication cannot bypass validation or obscure machine origin |
| Open | DEP-001 (#601) | Request-path advisories assessed; upgrades/audits governed and green |

### High - portable intelligence and visible evidence

| Status | Work item | Definition of done |
|---|---|---|
| Foundation complete | Immutable artifact and historical page | Integrity-verified permanent destination resolves publicly |
| Open | DIST-002 (#597) | Supported raster social assets and recorded renderer/storage decision |
| Open | DIST-001 (#596) | Non-JavaScript crawler receives artifact-specific metadata |
| Paused | M-001 Active Bullpen ERA | Approved sample, group, contributors, evidence, surface, regression coverage ship |
| Planned | Named-arm evidence expansion | Material team reads name relevant arms and receipts |
| Planned | Starter-exposure context | Official recent starter ranges appear as history with exact games/windows |

## 9. Phased Roadmap

### Phase 0 - Canonical Trust Closeout

**Status:** Complete - July 29, 2026.

Official pitching-line completeness, starter authority, recorded-outs authority, appearance-team history, dependent evidence, and read-only production closeout were proven. The six-document canonical library became execution authority.

### Phase 1 - Evidence Completeness

**Status:** In progress; implementation paused.

The Current Active-Pen Performance family and M-001 decisions are complete. Public implementation resumes after the Product Credibility Pass.

### Phase 1A - Game-Driven Ingestion Authority Qualification

**Status:** **Complete - August 10, 2026.**

Exit evidence:

- Foundation 3C bootstrap and shadow activation complete.
- D-044 separates observational shadow backlog from real publication blockers.
- OPS-002 production reliability closeout complete after three consecutive scheduled first-attempt daily runs.
- OPS-001 (#593) scheduled signal-separation observation complete and issue closed.
- Read-only candidate audit run `31393177954` returned `COMPLETE_ELIGIBLE_FOUND` with five eligible candidates and zero durable writes.
- Manual qualification run `31395294655` returned `PASS` for game `823924`.
- Qualification proved exact one-game scope, finality, source revision match, plan fingerprint match, 8/8 rows already matching, pre/post readback equality, and zero baseball-data writes.
- The lane ledger moved only by the exact governed delta: one existing work item updated/completed, one checkpoint advanced, one commit, no unrelated bookkeeping movement.
- Writer guard acquisition/release was positively proven.
- No scheduled/automated game-driven write authority or publication authority was granted.

Phase 1A closure proves the path can be governed safely. It does **not** transfer authority.

### Phase 1B - Public Vocabulary and Freshness Reconciliation

**Status:** In progress; active.

- #590 complete.
- #595 active; repository work complete, deployed verification outstanding.
- #591 open.
- #594 active; repository work complete, deployed verification outstanding.
- #600 open.

Exit test: a first-time reader sees backend-owned state and explanation, visible represented date, no raw black-box score, and consistent semantic structure across live and external surfaces.

### Phase 2 - Portable Intelligence

**Status:** Foundation complete; final distribution not started.

Scope: canonical server-side raster renderer, frozen image persistence/checksums, Open Graph/X metadata, copy/native share/download actions, Product Intelligence funnel, controlled circulation, and supersede/withdraw production proof.

### Phase 3 - Daily Habit and Consequence

**Status:** Not started.

Scope: Public What Changed, team since-last-game movement, Today lead authority, game-aware slate status, official starter ranges, rotation load transfer, story-strength governance, and quiet-day behavior.

### Phase 4 - Offseason Intelligence Depth

Candidate order:

1. pitch-characteristic ingestion and trends;
2. leverage, concentration, and dependency;
3. organizational reinforcement depth and roster mechanics;
4. routed team pages and search discovery after O-005;
5. state timeline and observation archive;
6. story-engine consolidation;
7. accessibility and technical-debt window;
8. Follow My Team only if returning-user demand justifies account value.

### Phase 5 - Opening Day 2027

Relaunch the complete daily product with a full-season runway: Daily Edition/Slate v2, governed share artifacts and images v2, only manually proven newsletter automation, creator round two, routed discovery, current trust proof, and a refreshed reliability baseline.

### Phase 6 - 2027 Growth and Validation

Let measured behavior and rights evidence choose the business direction. No monetization path is authorized before trust, habit, audience, and licensing evidence exist.

## 10. Dependency Map

```text
Official source identity and finality
-> complete appearance ledger
-> correct arm and team state
-> evidence objects
-> trusted snapshot or team authority
-> immutable artifact and public story
-> distribution and returning use
```

| Capability | Requires |
|---|---|
| Game-driven automated write authority | Phase 1A no-op proof + real-mutation proof + scheduled stability + rollback + observability + explicit founder approval |
| Game-driven publication authority | Automated write qualification + publication proof + explicit founder authority-transfer decision |
| No-op write qualification | Completed durable work item + exact one-game unchanged plan + source revision/fingerprint + positive readback + zero baseball-data mutation |
| M-001 Active Bullpen ERA | Official pitching lines + canonical active group + 108-out sample + group/contributor counts + four evidence levels |
| Backend-owned Why copy | Governed public copy authority + frontend pass-through + suppression accounting |
| Share image and metadata | Published immutable artifact + renderer version + frozen asset + crawler-visible delivery |
| Public What Changed | Adjacent comparable trusted states + same method + same vocabulary + correct product dates |
| Routed team pages | O-005 route decision + canonical surface owner + backend state/copy authority + server/static freshness |

## 11. Success Metrics

### Product quality

- percentage of public claims with inspectable evidence;
- percentage of team stories naming relevant arms;
- time for a first-time user to identify state and reason;
- public vocabulary drift defects: target zero;
- unexplained public numbers: target zero;
- quiet-day suppression and reasons;
- H1, mobile, and accessibility acceptance-test pass rate.

### Trust and operations

- silent stale incidents: target zero;
- final-game appearance deficits reaching publication: target zero;
- official starter mismatches reaching public copy: target zero;
- artifact integrity mismatches served publicly: target zero;
- unknown-as-zero defects: target zero;
- publication blockers separated from non-authoritative observer backlog;
- scheduled public-sync success and shadow-observer verdict reported independently;
- game-driven baseball-data writes while daily/postgame remain shadow: target zero;
- raw public composite-score exposure: target zero;
- method-version and correction-history completeness.

### Habit and distribution

- weekly returning users;
- Today-to-Team Board handoff;
- team-page return rate;
- What Changed engagement;
- copy, native-share, and image-download actions;
- human share-page views separated from crawlers;
- evidence inspection from share pages;
- external citations, backlinks, and creator mentions;
- freshness retained in external screenshots and previews.

## 12. Risk Register

| ID | Risk | Severity | Standing control |
|---|---|---|---|
| R-01 | Canonical game data is wrong or incomplete | Critical | Source authority, appearance gate, reviewed repairs, independent closeout |
| R-02 | Foundation perfectionism prevents public learning | High | Phase exits, one active objective, reader-facing next moves |
| R-03 | Generic stories fail to surprise | High | Named arms, story shapes, suppression, editorial review |
| R-04 | Trust warnings overpower the baseball insight | High | State first, evidence second, limitation only where material |
| R-05 | Single-founder capacity fragments work | High | One active objective, small branches, sustainable cadence |
| R-06 | Transitional share renderer becomes permanent | High | Portable Intelligence phase; no new legacy composition |
| R-07 | MLB source terms or availability change | High | Attribution, budgets, provenance, rights review |
| R-08 | Public label overclaims health, intent, or availability | High | Backend mappings, language guards, Unobservable Ledger |
| R-09 | Multiple documents claim authority | High | Six-document library, redirect/archive checks |
| R-10 | Competitor copies the surface | Medium | Trust history, evidence depth, immutable memory, creator workflow |
| R-11 | SEO remains weak | Medium | Routed owner decision and server/static metadata |
| R-12 | Founder burnout ends cadence | High | Quality ceiling, life-first planning, manual proof before automation |
| R-13 | Live product vocabulary contradicts canonical promise | Critical | Backend ownership, canonical active-bullpen population, exact mapping tests, production evidence |
| R-14 | Observer health obscures publication truth | High | Separate public-sync and shadow-health jobs; #593 production evidence |
| R-15 | Shadow bookkeeping absence is treated as a baseball deficit | High | D-044 dual-view classification and authority-aware blocker projection |
| R-16 | Public raw score endpoint violates black-box boundary | High | #595 removal/protection and public contract tests; repository work complete, deployed verification outstanding |
| R-17 | Shared links lose claim, evidence, and date | High | Canonical image and artifact-specific crawler metadata |
| R-18 | Routed team previews drift without a canonical owner | Medium | #594 gives every generated page one trusted publication authority, canonical Team State, a data-through date, and a snapshot receipt, with a static contract test; deployed verification outstanding |
| R-19 | Frontend rewrites backend-owned meaning | Critical | #591 and backend public-copy contract |
| R-20 | Generated commits bypass repository CI | High | #598 generated-content publication correction |
| R-21 | Daily runtime headroom masks avoidable work | High | D-050 temporary mitigation plus permanent work-reduction backlog |
| R-22 | Manual daily execution becomes de facto authority | Critical | D-051 schedule-only, first-attempt-only production daily execution |
| R-23 | Partial acquisition leaks into public serving | Critical | D-051 binds Team Board, Compare, Tonight to trusted published authority |
| R-24 | Authority qualification is mistaken for authority transfer | Critical | D-052 phase-exit language; O-008 remains open and requires explicit founder approval |

## 13. Stop Conditions

Stop when:

- required baseline is absent from `origin/main`;
- source authority is unresolved;
- a public term has two competing owners;
- a write or authority-transfer step lacks positive production qualification;
- implementation requires prediction, manager intent, private health inference, or unknown-as-zero behavior;
- a migration cannot preserve immutable history or refuses unsafe downgrade behavior;
- production smoke or a required audit cannot be completed safely;
- a dangerous write lacks a read-only plan, exact scope, explicit confirmation, and post-write proof;
- the change silently expands scope beyond the approved objective;
- production-evidence capture would be obscured by an overlapping presentation change.

## 14. Backlog

### Near term

- #595 raw score/internal-id containment (repository work complete; deployed verification outstanding);
- #591 backend-owned Why copy;
- #594 routed/static freshness and ownership (repository work complete; deployed verification outstanding);
- #600 H1/accessibility corrections;
- #598 generated-content CI validation;
- #601 dependency remediation;
- permanent daily-sync work reduction;
- canonical renderer, Open Graph/X metadata, and share actions;
- M-001 Active Bullpen ERA implementation;
- named-arm evidence expansion;
- creator seeding and evidence-led outreach.

### Authority follow-up

These are not Phase 1A work and are not automatically authorized by its closure:

- real-mutation game-driven qualification;
- automated write-mode decision;
- scheduled write rollout;
- game-driven publication-authority transfer;
- legacy-writer retirement;
- backfill activation.

All require new governed evidence and O-008 / a future explicit Decision Ledger decision.

### Offseason

- pitch trends;
- leverage, concentration, and dependency;
- organizational reinforcement depth and roster mechanics;
- routed team pages and SEO after O-005;
- state timeline and observation archive;
- story-engine consolidation;
- Start Here merge;
- accessibility pass;
- large-module debt only when touched;
- CI false-confidence and freeze-guard cleanup.

### Parked until demand

- Follow My Team and broad account expansion;
- automated newsletter digest;
- game pages beyond the Slate;
- embeddable partner widgets;
- public API and exports;
- push notifications;
- professional or team-sales tooling;
- sponsorship and monetization tests.

### Never backlog

Predictions, betting or odds products, game-outcome projections, injury prediction, fantasy start/sit advice, manager-intent claims, generic team/player rankings, black-box public scores, a general prospect/draft/trade product inside BaseballOS, paid resale without rights authority, and user-editable claims inside immutable artifacts are refusals, not deferred ideas.

## 15. Decision Ledger Rules

- Decisions are append-only.
- A reversal receives a new entry referencing the original.
- Every entry records date, decision, rationale, status, affected canonical owners, and implementation evidence where applicable.
- Detailed pre-Version-3 rationales remain preserved in the archived predecessor ledger and Git history.
- Implementation detail belongs in branches and pull requests; this table records durable meaning.

## 16. Permanent and Standing Decisions

| ID | Date | Decision | Status |
|---|---|---|---|
| D-001 | Prior to Jul 2026 | BaseballOS is trust-first | Permanent |
| D-002 | Prior to Jul 2026 | Predictions, betting, fantasy advice, private injury claims, and manager-intent certainty are prohibited | Permanent |
| D-003 | Jul 24, 2026 | Public Team State labels are Fresh, Stretched, and Vulnerable | Adopted |
| D-004 | Jul 24, 2026 | Team State has exactly three public labels; internal states stay internal | Standing |
| D-005 | Jul 2026 | Public arm reads are Clean Option, Watch Arm, Limited Rest, Unavailable, and Limited Read; backend keys own meaning | Standing |
| D-006 | Jul 2026 | The immutable Share Artifact, not an image or browser component, is the source of truth | Permanent |
| D-007 | Jul 29, 2026 | An eligible team may publish progressively before the full league slate completes | Adopted |
| D-008 | Jul 29, 2026 | Integer recorded outs are the semantic innings authority; decimal innings are derived | Permanent |
| D-009 | Jul 29, 2026 | Historical appearance team comes from the game side, not current organization | Permanent |
| D-010 | Jul 24, 2026 | Meaning-bearing Share Artifact copy is deterministic, backend-owned, and not free-form AI analysis | Permanent |
| D-011 | Jul 2026 | Published artifacts are immutable; corrections supersede or withdraw rather than rewrite | Permanent |
| D-012 | Jul 2026 | Current and historical state remain separate objects | Permanent |
| D-013 | Prior to Jul 2026 | Nickolis Kacludis remains sole repository author/committer; no AI attribution is added | Permanent |
| D-014 | Prior to Jul 2026 | One user question per page and one canonical home per fact | Permanent |
| D-015 | Prior to Jul 2026 | Manual proof precedes automation for newsletter and distribution workflows | Standing |
| D-016 | Prior to Jul 2026 | Follow My Team waits for demonstrated retention value | Standing |
| D-017 | Jul 29, 2026 | Six living canonical documents replace recurring master documents | Adopted |
| D-018 | Jul 29, 2026 | Foundation 3A closed with independent production proof; Phase 1 Evidence Completeness opened | Adopted |
| D-019 | Jul 29, 2026 | The Matt Festa one-action apply is terminally closed and must not be dispatched again | Permanent |
| D-020 | Jul 29, 2026 | A fingerprint-locked apply refusing because its manifest no longer regenerates is a correct terminal outcome | Permanent |
| D-021 | Jul 29, 2026 | The Current Active-Pen Performance family owns group, window, sample, date, evidence, limits, and Team Board home | Adopted |
| D-022 | Jul 29, 2026 | Metric family and metric definition are separate governed objects; M-001 is reserved but non-public | Adopted |
| D-023 | Jul 30, 2026 | M-001 publishes only at 108 recorded outs or more | Adopted |
| D-024 | Jul 30, 2026 | M-001 formula is earned runs times 27 divided by integer recorded outs; zero denominator refuses first | Adopted |
| D-025 | Jul 30, 2026 | Performance rates use exact integers and one ROUND_HALF_UP operation at declared precision; M-001 displays two decimals | Adopted |
| D-026 | Jul 30, 2026 | Below-sample wording is Not Enough Innings Yet with current and required innings adjacent | Adopted |
| D-027 | Jul 30, 2026 | A no-usage call-up remains in the active group with zero contribution; reads report group size and contributing arms | Adopted |
| D-028 | Jul 30, 2026 | M-001 public name is Active Bullpen ERA | Adopted |
| D-029 | Jul 30, 2026 | M-001 uses four evidence levels; a value unable to reach source-level proof is not publishable | Adopted |
| D-030 | Jul 30, 2026 | Future metrics inherit the performance-family authority, evidence, freshness, failure, and rounding contracts | Adopted |
| D-031 | Jul 31, 2026 | Foundation 3C bootstrap completed for governed games and rows without granting activation authority | Adopted |
| D-032 | Jul 31, 2026 | Foundation 3C rollout closed, production replay verified, and temporary rollout workflows retired | Adopted |
| D-033 | Aug 1, 2026 | The missing postgame integration point was built; postgame write and authoritative modes remain refused | Adopted |
| D-034 | Aug 1, 2026 | Automated shadow activation approved for daily and postgame only; backfill remains off and writes remain unapproved | Adopted |
| D-035 | Aug 1, 2026 | First postgame shadow failure was isolated to scope; postgame shadow paused and no repair was guessed | Adopted |
| D-036 | Aug 1, 2026 | Exact-cycle scope repair accepted and postgame shadow reactivated with stronger validation and diagnostics | Adopted |
| D-037 | Aug 1, 2026 | GameLog balls authority was declared unresolved; no writer changed; a read-only source-authority audit was added | Adopted |
| D-038 | Aug 1, 2026 | Completed-game box score is canonical fallback for balls only when the split omits it and the official pitch triple validates | Adopted |
| D-039 | Aug 2, 2026 | PROD-001 widens Tonight provenance capacity to 128, preserves full source, and requires scheduled production closure | Adopted; production proof complete |
| D-040 | Aug 2, 2026 | Trusted public-sync and experimental shadow-health are separate jobs; neither publication nor observer gates are weakened | Adopted; production observation complete |
| D-041 | Aug 3, 2026 | Manual exact-one-game no-op write qualification machinery exists and authorizes no real mutation or broader mode | Adopted |
| D-042 | Aug 4, 2026 | First qualification refused on missing durable work item; candidate selection belongs to a bounded read-only audit | Adopted |
| D-043 | Aug 4, 2026 | The August 3 failed publication cycle is handled by a manual exact-scope read-only incident audit; shadow is not assumed to be the failure | Adopted |
| D-044 | Aug 4, 2026 | Shadow observation backlog and publication blockers are separate views; missing work-item proof blocks only in authoritative mode | Adopted |
| D-045 | Aug 4, 2026 | Backend CI is partitioned across four deterministic, file-balanced shards with separate PostgreSQL databases and exact collection accounting | Adopted |
| D-046 | Aug 4, 2026 | Trust-critical CI receives full Git history; frontend CI uses the committed lockfile and requires tests plus the production build | Adopted |
| D-047 | Aug 5, 2026 | The game 824487 source-revision mismatch is investigated by a manual exact-scope read-only audit that will not guess a field delta from a SHA-256 digest | Adopted; production audit executed |
| D-048 | Aug 6, 2026 | Game 824487's source-revision checkpoint was corrected through the reviewed one-row workflow, terminally re-observed as already applied with zero additional writes, and the single-purpose repair capability is retired. This grants no broader game-driven write or publication authority | Permanent |
| D-049 | Aug 6, 2026 | UX-001 closes after corrected production proved backend-owned `Stretched` and `Vulnerable` states plus governed fail-closed behavior; naturally absent Fresh evidence is never manufactured | Permanent |
| D-050 | Aug 6, 2026 | OPS-002 uses temporary runtime headroom while preserving publication gates and all game-driven authority boundaries; permanent work reduction remains separate | Operational until permanent work-reduction proof supersedes it |
| D-051 | Aug 8, 2026 | Acquisition may advance independently, but public Team Board, Compare, and Tonight authority advances only through trusted publication. Production full-daily execution is scheduled and first-attempt only; generic manual daily execution, local production daily invocation, the legacy admin daily writer route, and GitHub reruns are non-authoritative/refused | Standing trust boundary |
| D-052 | Aug 10, 2026 | Phase 1A Game-Driven Ingestion Authority Qualification is complete after OPS-002 scheduled reliability proof, OPS-001 scheduled signal-separation proof, read-only candidate audit run `31393177954`, and no-op write qualification PASS run `31395294655` for game `823924`. The PASS proves safe governed entry into the write-capable path with zero baseball-data mutation and exact lane-ledger movement. It grants no automated/scheduled write authority, no game-driven publication authority, no backfill authority, and no legacy-writer retirement | Permanent phase-exit decision |

## 17. Open Decisions

| ID | Decision required | Gate | Current default |
|---|---|---|---|
| O-001 | Resolved by D-021 | Closed | Performance family established; M-001 remains unimplemented and non-public |
| O-002 | Current-versus-shared comparison contract | Trusted comparability and public UX | Historical page remains frozen only |
| O-003 | Canonical server renderer technology and storage | Artifact contract, hosting cost, performance | Transitional browser renderer only |
| O-004 | Public leverage calculation and table | Complete source coverage and reproducible method | Legacy/partial claims remain bounded |
| O-005 | Routed team URL shape and surface ownership | Product route and SEO plan | Team Board remains canonical live destination |
| O-006 | Whether account/sign-in remains after Follow My Team review | Demonstrated retention value | Keep internal auth substrate; no broad account push |
| O-007 | Resolved by D-052 | Closed | A completed durable candidate was found read-only and game `823924` passed the exact no-op qualification contract |
| O-008 | Game-driven automated write and later publication-authority transfer | Real-mutation proof, scheduled write stability, rollback, observability, and explicit founder approval | Daily/postgame shadow; backfill off; legacy writer authoritative |

## 18. Founder Operating System

### Weekly review

1. current main commit;
2. sole active objective;
3. current branch and blocker;
4. merged work and production evidence;
5. changed risk;
6. next approved work;
7. deliberately deferred work;
8. documentation alignment;
9. sustainable distribution cadence;
10. whether a lower-priority item began without a recorded reason.

### Branch rule

Branch names identify the user or operator who notices the work. Never work directly on `main`.

### Founder principles

1. Every feature must justify its hours.
2. No feature without a user or operator problem.
3. Trust before growth; growth before monetization.
4. The season is a scheduling constraint, not permission to lower quality.
5. Never sacrifice explainability for impressiveness.
6. Never build merely because a competitor did.
7. Compression may reduce ceremony, not trust.
8. Two focused hours that ship beat an exhausted six-hour detour.
9. Deletion and deferral are progress.
10. Write durable decisions once.
11. Life comes first; the system should survive absence.
12. One active objective is the default.

## 19. Completion Log

| Date | Phase | Item | Branch / PR / commit | Evidence and status |
|---|---|---|---|---|
| Jul 29, 2026 | Phase 0 | Canonical Trust Closeout and Phase 1 opening | PR #559 / `ec636f2...` | Independent closeout passed; six-document authority recorded |
| Jul 29–30, 2026 | Phase 1 | Current Active-Pen Performance contract and M-001 governance | D-021 through D-030 / PRs #560–#566 | Group, formula, 108-out sample, name, precision, wording, membership, and evidence contract; implementation remains non-public |
| Jul 31, 2026 | Phase 1A | Foundation 3C bootstrap and closeout | PRs #572–#581 | 109 governed final games and 946 appearance rows reconciled; no activation authority granted |
| Aug 1, 2026 | Phase 1A | Daily/postgame shadow activation and exact-cycle repair | PRs #582–#585 | Shadow isolated; first scope failure diagnosed; postgame reactivated; writes remained unapproved |
| Aug 1, 2026 | Phase 1A | GameLog balls authority and fallback | PRs #586–#587 | Production audit established box-score fallback contract for balls only |
| Aug 2, 2026 | Operations | Tonight source-capacity repair | PR #588 / migration `c7f1b408d93a` | Code and PostgreSQL proof merged |
| Aug 2, 2026 | Operations | Public-sync separated from shadow-health | PR #602 | Publication-dependent jobs no longer depend on observer verdict |
| Aug 3, 2026 | Phase 1A | Manual no-op write qualification machinery | PR #604 | Exact one-game, main-only, fingerprinted path; first production execution refused safely |
| Aug 4, 2026 | Phase 1A | No-op candidate audit machinery | PR #605 | Bounded read-only deterministic candidate selection added |
| Aug 4, 2026 | Phase 1A | Observation backlog separated from publication blockers | PR #608 / `d746471...` | Shadow backlog classified separately from real baseball deficits |
| Aug 4, 2026 | CI | Four-shard PostgreSQL confidence gate | PR #609 | Separate PostgreSQL databases with exact collection accounting |
| Aug 4, 2026 | CI | CI-001 closure (#599) | PR #610 / `ebe2db4...` | Lockfile-faithful frontend CI, full tests, production build |
| Aug 5–6, 2026 | Phase 1A | Game 824487 audit, repair, and retirement | PRs #613, #615, #616 | Exact-scope source-revision correction terminally closed; temporary repair capability retired |
| Aug 6, 2026 | Phase 1B | UX-001 canonical Team State production closeout | PRs #611, #617 / run `31097712768` | Canonical Team State production evidence complete |
| Aug 6–10, 2026 | Operations | OPS-002 runtime mitigation and trusted-serving correction | PRs #619, #621, #627 / D-050, D-051 | Three scheduled first-attempt daily PASS runs complete production proof; issue #620 closed |
| Aug 3–10, 2026 | Phase 1A | OPS-001 signal-separation observation | PR #602 / issue #593 | Scheduled evidence proved public-sync and observer verdict separation; issue closed August 10 |
| Aug 10, 2026 | Phase 1A | Read-only no-op candidate production audit | Run `31393177954` | `COMPLETE_ELIGIBLE_FOUND`; 109 completed work items found, five evaluated/eligible, zero durable writes, game `823924` suggested |
| Aug 10, 2026 | Phase 1A | Manual one-game no-op write qualification | Run `31395294655` | `PASS`; game `823924`; 8/8 rows unchanged; zero baseball-data writes; exact governed lane-ledger delta; pre/post state identical |
| Aug 10, 2026 | Phase 1A | **Authority Qualification phase exit** | PR #628 / D-052 | Phase complete; no automated write/publication/backfill authority granted |

## 20. Phase Exit Record

| Phase | Status | Exit evidence / remaining work |
|---|---|---|
| Phase 0 - Canonical Trust Closeout | Complete | Independent official-line, starter, outs, appearance-team, and aggregation proof |
| Phase 1 - Evidence Completeness | In progress / paused | M-001 contract complete; implementation resumes after higher-priority public-trust work |
| Phase 1A - Authority Qualification | **Complete - Aug 10, 2026** | OPS-002 and #593 closed; candidate audit `31393177954`; no-op PASS `31395294655`; PR #628 / D-052; all broader game-driven authority remains unapproved |
| Phase 1B - Vocabulary and Freshness | In progress / active | #590 complete; #595 and #594 implementation complete with deployed verification outstanding; #591 open; #600 open; in-product team-shape vocabulary parity still outstanding |
| Phase 2 - Portable Intelligence | Foundation complete / final distribution not started | Renderer, raster assets, metadata, actions, funnel |
| Phase 3 - Daily Habit and Consequence | Not started | What Changed, lead, slate, quiet day |
| Phase 4 - Offseason Intelligence Depth | Not started | Pitch, leverage, depth, routes, archive |
| Phase 5 - Opening Day 2027 | Not started | Complete daily relaunch |
| Phase 6 - Growth and Validation | Not started | Behavior and rights evidence choose direction |

## 21. Source Basis

This current-state edition consolidates:

- the repository's prior canonical Roadmap and detailed Decision Ledger through D-050;
- PR #627 and D-051 trusted-public-serving authority;
- OPS-002 closeout evidence from scheduled first-attempt runs `31252933643`, `31308567552`, and `31382023524`;
- OPS-001 (#593) scheduled observation evidence and August 10 closure;
- read-only no-op candidate audit run `31393177954` and retained artifact;
- manual no-op write qualification run `31395294655` and retained artifact;
- Phase 1A governance closeout PR #628 / D-052;
- repository main `b328c917c6813831db167f4f70a57fd1ff3aa847`;
- GitHub issue status for #589–#601 and #620;
- the August 2 Full Platform Audit;
- the current Constitution, Bullpen Intelligence Standard, Product Experience Standard, Architecture and Operations Manual, and Editorial and Distribution Standard.

The archived predecessor file and Git history preserve the full verbose rationale and exact historical evidence for earlier decisions. Pull requests, workflow artifacts, and runbooks remain the exact implementation and operational evidence.

## 22. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0–2.9 | Jul 29–Aug 4, 2026 | Nickolis Kacludis | Established the canonical execution roadmap and durable decisions through D-046. |
| 3.0 | Aug 5, 2026 | Nickolis Kacludis | Reconciled current state through PR #611 and recorded the audit remediation sequence. |
| 3.1 | Aug 6, 2026 | Nickolis Kacludis | Recorded terminal game 824487 source-revision checkpoint closeout and D-048. |
| 3.2 | Aug 6, 2026 | Nickolis Kacludis | Recorded UX-001 production closeout and D-049. |
| 3.3 | Aug 6, 2026 | Nickolis Kacludis | Recorded OPS-002 runtime-budget incident/mitigation and D-050; paused #593 pending reliable evidence. |
| 3.4 | Aug 10, 2026 | Nickolis Kacludis | PR #628 reconciles production state through OPS-002 closure, PR #627 / D-051, #593 closure, candidate audit `31393177954`, and no-op qualification PASS `31395294655`. Adds D-052 closing Phase 1A without transferring game-driven write/publication/backfill authority, resolves O-007, makes #595 the active objective, and updates the phase exit, completion, risk, backlog, and authority records accordingly. |
| 3.5 | Aug 10, 2026 | Nickolis Kacludis | Records SEC-001 (#595) implementation state: unauthenticated fatigue routes serve a narrowed public workload view model, board cards and the league stats overview no longer publish a composite or risk tier, the availability explanation cites counted workload, the internal tier is no longer a public filter, and an anonymous-response boundary strips the internal scoring vocabulary. Internal scored access remains behind `require_admin_token` and is documented as internal, not a public claim. #595 stays open pending deployed verification; no sync, write, publication, or serving authority changed. |
| 3.6 | Aug 10, 2026 | Nickolis Kacludis | Records DIST-003 (#594) implementation state and the routed team preview surface. The thirty generated `/team/{ABBR}` pages stop publishing an undated present-tense claim in the in-product team-shape vocabulary: every generated page now resolves from ONE trusted dashboard publication, states canonical public Team State or the governed non-state, carries a backend-authored baseball point, publishes its baseball data-through date alongside separate generated and publication times, records the snapshot and sync-run receipt it came from, and keeps its current Team Board handoff in a crawlable body. The export no longer reads the live board builder, and it withholds the claim rather than dating a guess when authority or data-through cannot be established. The historical artifact current-board link now preserves team identity. #594 stays open pending deployed verification. No availability classification, threshold, Team State derivation, freshness field meaning, publication gate, or artifact immutability behavior changed, and the in-product team-shape read vocabulary is deliberately untouched and remains outstanding parity work. |
