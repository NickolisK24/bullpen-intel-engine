# BaseballOS Product Roadmap & Decision Ledger

| Field | Value |
|---|---|
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 3.0 |
| Effective date | August 5, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `8a528efec1affcdaf98fa1e87f9090d105db4248` |
| Decision basis | Decision Ledger through D-046 |
| Supersedes | Prior current-state wording through August 4, 2026 while preserving all durable decisions and evidence |
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

BaseballOS is a live public MLB bullpen-intelligence platform with a mature trust foundation, a defensible canonical appearance record, governed publication gates, immutable historical claims, and unusually strong production evidence for a solo-built product.

The platform currently provides:

- a daily front door, full-league Dashboard, Team Boards, comparison, reliever discovery, and pitcher detail;
- workload and availability intelligence with active-roster separation and official appearance evidence;
- backend-owned Team State and arm-read authorities;
- trusted league snapshots and team-progressive publication;
- immutable Share Artifacts with integrity, lifecycle, and permanent historical pages;
- read-only incident, correction, completeness, and qualification audits;
- daily and postgame game-driven ingestion lanes operating in shadow;
- a four-shard PostgreSQL CI confidence gate plus lockfile-faithful frontend test/build validation;
- canonical Team State delivery to live reader surfaces, merged and awaiting production-state coverage proof.

The central problem is no longer whether BaseballOS can build trustworthy baseball infrastructure. The current problem is completing production-evidence closeout, removing the remaining public-contract contradictions, and then making the platform's existing intelligence more visible and portable.

## 3. Current Repository and Authority State

| Area | Current state | Meaning |
|---|---|---|
| Repository main | `8a528efec1affcdaf98fa1e87f9090d105db4248` | PR #611 merged August 5, 2026 |
| Game-driven daily lane | Shadow | Observation only; no automated baseball-data writes |
| Game-driven postgame lane | Shadow | Exact-cycle observation after the legacy postgame writer |
| Backfill lane | Off | No automatic game-driven backfill authority |
| Production writer | Legacy sync/postgame path | Remains authoritative for baseball-data mutation |
| Automated write mode | Unapproved | Manual one-game qualification machinery grants no broader authority |
| Game-driven publication authority | Unapproved | Publication authority has not transferred |
| D-044 blocker scope | Implemented | Shadow bookkeeping backlog is observational; real baseball deficits remain fail-closed |
| PROD-001 (#592) | Complete | Scheduled production run proved full Tonight provenance persistence and readback |
| OPS-001 (#593) | Implemented; observation pending | Job separation exists; required scheduled observation window remains open |
| UX-001 (#590) | Merged; production evidence pending | Canonical Team State contract is live-code ready; Fresh/Stretched/Vulnerable production triad still must be captured |
| CI-001 (#599) | Complete | Frontend CI uses the lockfile and requires tests plus the production build |

## 4. Active Objective

> **Production evidence closeout**

The active objective has two parallel evidence tracks. Both are blocked by production time or naturally occurring state coverage rather than by missing implementation.

### Track A - Sync and authority evidence

1. Continue scheduled daily and postgame observation after D-044 and PR #602.
2. Prove `public-sync` and `shadow-activation-health` remain separately meaningful across the required observation window.
3. Confirm genuine finality, schedule-authority, appearance-row, and material-correction deficits still withhold publication.
4. Complete the bounded read-only no-op candidate path or record the explicit no-candidate decision.
5. Keep daily/postgame shadow, backfill off, legacy writer authoritative, and automated write/authoritative modes unapproved.

### Track B - Canonical Team State production proof

PR #611 is merged and automated validation is complete. Issue #590 remains open until production captures:

- one Fresh team;
- one Stretched team;
- one Vulnerable team;
- matching backend `team_state.public_state` and `team_state.public_label` values;
- rendered frontend text equal to the backend label;
- data-through context and screenshots;
- one governed fail-closed example with no invented fourth Team State.

### Exit evidence

- Scheduled runs prove publication success or failure independently from shadow-observer health.
- The observation backlog may remain incomplete without becoming a publication blocker in shadow mode.
- Real baseball deficits remain blocking in every mode.
- No closeout audit mutates GameLog, work-item, checkpoint, snapshot, marker, or dead-letter rows.
- Fresh, Stretched, and Vulnerable are each proven in production through payload and rendered evidence.
- #590 and #593 close only after their remaining evidence requirements are satisfied.

## 5. Nightly Operating State

At the August 4–5 closeout, no additional implementation package should begin. The current work is cleanly merged and waiting on external evidence.

Stopping is intentional:

- #591 overlaps the same reader adapters and should not obscure #590 production validation.
- #594 consumes the same Team State and freshness path in static/routed previews.
- #600 touches the same `/bullpen` surfaces used for #590 validation.
- Sync authority must not be inferred from green tests or from a short observation window.

## 6. Next Approved Work

After the current evidence checkpoint is reviewed, work proceeds in this order unless a Decision Ledger entry changes it:

1. **#595 - Public raw fatigue-score containment.** Remove or protect unauthenticated composite scores, component scores, risk tiers, and internal identifiers. This is the next independent trust package because it does not require changing Team State presentation or sync authority.
2. **#591 - Backend-owned Why copy.** Remove frontend regex rewriting, filtering, fallback invention, or silent dropping of governed public explanation text.
3. **#594 - Routed/static team metadata and freshness.** Give the 30 team preview routes a canonical owner, canonical vocabulary, named evidence, and data-through context.
4. **#600 - `/bullpen` H1 and accessibility structure.** Complete the semantic page contract after the #590 production check.
5. **Portable Intelligence.** Canonical raster renderer, artifact-specific Open Graph/X metadata, share actions, and evidence-inspection funnel.
6. **Resume M-001 Active Bullpen ERA.** Finish registry parameters, group/contributor evidence, Team Board delivery, and full trust gates.
7. **Daily Habit and Consequence.** Public What Changed, team movement, Today lead authority, game-aware slate, and quiet-day behavior.

## 7. Current Capability Assessment

### Product surfaces

| Surface | Current state | Main gap | Governing next move |
|---|---|---|---|
| Today | Live daily front door | Stronger lead, status-aware context; no independent Team State currently rendered | Daily Habit after higher-priority work |
| Dashboard | Live league board; canonical per-team Team State implementation merged | Production proof for all three states; stronger named evidence | #590 closeout, then evidence expansion |
| Team Board | Flagship team surface with arm groups and recent work | #590 production proof; Why-copy ownership; performance/starter evidence | #590, #591, then M-001 |
| Compare | Descriptive two-team comparison; canonical state passed through per side | Production proof, H1, stronger named differences | #590, #600 |
| Reliever Finder | Search-first utility | H1/accessibility and faster evidence handoff | #600; do not overbuild |
| Pitcher Detail | De-scored, evidence-first recent work | Active-group performance and later pitch-trend depth | M-001; offseason trends |
| Stories | Live narrative feed | Specificity, named arms, evidence, suppression | Ongoing quality work |
| Methodology | Teaches canonical public language | Live product must continue matching it | Maintain through public-contract work |
| Data & Trust | Strong public differentiator | Current incident/method history and scope degradation clarity | Ongoing trust alignment |
| Share Artifact | Immutable historical page implemented | Canonical image, crawler-visible claim metadata, complete actions | Portable Intelligence |
| Routed team previews | Thirty static routes exist | No final route owner; metadata vocabulary and freshness incomplete | #594 |
| Internal Product Intelligence | Artifact, traffic, and operations views exist | Unify incident, observer, refusal, and publication signals when actionability improves | Maintain, do not expand speculatively |

### Intelligence and operations

| Capability | State | Assessment |
|---|---|---|
| Official appearance ledger | Production / publication-critical | Canonical recorded outs, starter distinction, and appearance-team authority are the strongest asset |
| Active roster/team authority | Production | Unknown and conflict states fail closed; historical appearance ownership stays separate |
| Arm reads and roles | Production | Backend-owned public labels exist |
| Team State authority | Production implementation merged | Exactly Fresh / Stretched / Vulnerable; production triad evidence pending |
| Trusted league snapshots | Production | Whole-slate authority and appearance gate remain fail-closed |
| Team-progressive publication | Production | Eligible teams may publish independently after team-scoped proof |
| Game-driven ingestion | Shadow / qualification | Daily and postgame observe; legacy writer remains authoritative |
| Active Bullpen ERA | Contract complete; implementation paused | D-021 through D-030 fully specify M-001; it remains non-public |
| Starter/rotation transfer | Partial | Official starter authority is hardened; consequence layer incomplete |
| Immutable Share Artifacts | Production foundation | Artifact, lifecycle, integrity, audit, and public history are real; travel layer incomplete |
| Leverage/concentration | Partial | Requires a published method, named evidence, and suppression |
| Pitch characteristics | Experimental / planned | Offseason depth after product correctness and distribution |

## 8. Canonical Priority Matrix

### Critical - production authority and public trust

| Status | Work item | Exit evidence |
|---|---|---|
| Evidence pending | D-044 and OPS-001 scheduled proof | Independent public-sync and observer verdicts across the required window |
| Evidence pending | No-op candidate determination | Read-only candidate report or governed no-candidate decision |
| Complete | PROD-001 (#592) | Run `30921186222`; full source persisted/read back; Tonight and dashboard verification passed |
| Merged; production pending | UX-001 (#590) | Fresh, Stretched, Vulnerable, and fail-closed production evidence |
| Next | SEC-001 (#595) | Public scored/internal fields removed or explicitly protected |
| Maintain | Official appearance record | Ledger, starter, outs, appearance-team, and official-line checks stay green |
| Maintain | Canonical documentation cutover | Current documents contain no false execution authority |

### High - public correctness and freshness

| Status | Work item | Definition of done |
|---|---|---|
| Open | FE-001 (#591) | Backend owns Why copy; frontend renders without rewriting or dropping it |
| Open | DIST-003 (#594) | Static/routed descriptions use canonical state, evidence, and data-through date |
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
| Paused | M-001 Active Bullpen ERA | Approved sample, group, contributors, evidence, surface, and regression coverage ship |
| Planned | Named-arm evidence expansion | Every material team read names relevant arms and receipts |
| Planned | Starter-exposure context | Official recent starter ranges appear as history with exact games/windows |

## 9. Phased Roadmap

### Phase 0 - Canonical Trust Closeout

**Status:** Complete - July 29, 2026.

Official pitching-line completeness, starter authority, recorded-outs authority, appearance-team history, dependent evidence, and read-only production closeout were proven. The six-document canonical library became execution authority.

### Phase 1 - Evidence Completeness

**Status:** In progress; implementation paused.

The Current Active-Pen Performance family and M-001 decisions are complete. Public implementation resumes after authority closeout and public-contract remediation.

### Phase 1A - Game-Driven Ingestion Authority Qualification

**Status:** Active evidence closeout.

Foundation 3C bootstrap and shadow activation are complete. Current work proves scheduled signal separation and determines a valid no-op qualification path. Automated write and authoritative modes remain unapproved.

### Phase 1B - Public Vocabulary and Freshness Reconciliation

**Status:** In progress.

- #590 implementation merged; production evidence pending.
- #591 open.
- #594 open.
- #595 open and next independent trust package.
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
| Game-driven publication authority | Scheduled shadow proof + correct blocker scope + write-path qualification + explicit founder authority-transfer decision |
| No-op write qualification | Completed durable work item + exact one-game unchanged plan + source revision/fingerprint + positive readback + zero baseball-data mutation |
| M-001 Active Bullpen ERA | Official pitching lines + canonical active group + 108-out sample + group/contributor counts + four evidence levels |
| Live Team State closure | Backend authority + deployed payload + Fresh/Stretched/Vulnerable state coverage + rendered-text equality |
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
- game-driven baseball-data writes while in shadow: target zero;
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
| R-13 | Live product vocabulary contradicts canonical promise | Critical | #590 backend contract; production evidence before closure |
| R-14 | Observer health obscures publication truth | High | Separate public-sync and shadow-health jobs; independent verdicts |
| R-15 | Shadow bookkeeping absence is treated as a baseball deficit | High | D-044 dual-view classification and authority-aware blocker projection |
| R-16 | Public raw score endpoint violates black-box boundary | High | #595 removal/protection and public contract tests |
| R-17 | Shared links lose claim, evidence, and date | High | Canonical image and artifact-specific crawler metadata |
| R-18 | Routed team previews drift without a canonical owner | High | O-005, #594, canonical copy and freshness |
| R-19 | Frontend rewrites backend-owned meaning | Critical | #591 and backend public-copy contract |
| R-20 | Generated commits bypass repository CI | High | #598 generated-content publication correction |

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

- #590 production state-triad evidence and closure;
- #593 scheduled observation and closure;
- read-only no-op candidate audit and explicit next decision;
- #595 raw score/internal-id containment;
- #591 backend-owned Why copy;
- #594 routed/static freshness and ownership;
- #600 H1/accessibility corrections;
- #598 generated-content CI validation;
- #601 dependency remediation;
- canonical renderer, Open Graph/X metadata, and share actions;
- M-001 Active Bullpen ERA implementation;
- named-arm evidence expansion;
- creator seeding and evidence-led outreach.

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
| D-040 | Aug 2, 2026 | Trusted public-sync and experimental shadow-health are separate jobs; neither publication nor observer gates are weakened | Adopted; observation window open |
| D-041 | Aug 3, 2026 | Manual exact-one-game no-op write qualification machinery exists and authorizes no real mutation or broader mode | Adopted |
| D-042 | Aug 4, 2026 | First qualification refused on missing durable work item; candidate selection belongs to a bounded read-only audit | Adopted |
| D-043 | Aug 4, 2026 | The August 3 failed publication cycle is handled by a manual exact-scope read-only incident audit; shadow is not assumed to be the failure | Adopted |
| D-044 | Aug 4, 2026 | Shadow observation backlog and publication blockers are separate views; missing work-item proof blocks only in authoritative mode | Adopted |
| D-045 | Aug 4, 2026 | Backend CI is partitioned across four deterministic, file-balanced shards with separate PostgreSQL databases and exact collection accounting | Adopted |
| D-046 | Aug 4, 2026 | Trust-critical CI receives full Git history; frontend CI uses the committed lockfile and requires tests plus the production build | Adopted |
| D-047 | Aug 5, 2026 | The game 824487 source-revision mismatch is investigated by a manual exact-scope read-only audit that will not guess a field delta from a SHA-256 digest | Adopted; production audit not yet executed |

## 17. Open Decisions

| ID | Decision required | Gate | Current default |
|---|---|---|---|
| O-001 | Resolved by D-021 | Closed | Performance family established; M-001 remains unimplemented and non-public |
| O-002 | Current-versus-shared comparison contract | Trusted comparability and public UX | Historical page remains frozen only |
| O-003 | Canonical server renderer technology and storage | Artifact contract, hosting cost, performance | Transitional browser renderer only |
| O-004 | Public leverage calculation and table | Complete source coverage and reproducible method | Legacy/partial claims remain bounded |
| O-005 | Routed team URL shape and surface ownership | Product route and SEO plan | Team Board remains canonical live destination |
| O-006 | Whether account/sign-in remains after Follow My Team review | Demonstrated retention value | Keep internal auth substrate; no broad account push |
| O-007 | First valid no-op qualification path when no completed durable candidate exists | Read-only candidate audit plus exact-scope creation/initialization contract | No guessed target; no automatic work-item creation |
| O-008 | Game-driven automated write and later publication-authority transfer | No-op proof, real-mutation proof, scheduled stability, rollback, observability, explicit founder approval | Daily/postgame shadow; backfill off; legacy writer authoritative |

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
| Aug 4, 2026 | Operations | PROD-001 production closure (#592) | Run `30921186222` | Full source persisted/read back; Tonight verified; ledger 120/120 and 1,029/1,029; dashboard cache verified |
| Aug 2, 2026 | Operations | Public-sync separated from shadow-health | PR #602 | Publication-dependent jobs no longer depend on observer verdict; #593 observation window remains open |
| Aug 3, 2026 | Phase 1A | Manual no-op write qualification machinery | PR #604 | Exact one-game, main-only, fingerprinted path; first production execution refused safely |
| Aug 4, 2026 | Phase 1A | No-op candidate audit | PR #605 | First run proved missing durable work item; bounded read-only selection added |
| Aug 4, 2026 | Phase 1A | Postgame publication incident audit and runtime repair | PRs #606–#607 | Read-only staged evidence and real-PostgreSQL completion proof; no mutation authorized |
| Aug 4, 2026 | Phase 1A | Observation backlog separated from publication blockers | PR #608 / `d746471...` | 105 expected, 42 work-item complete, 63 shadow-only backlog, zero real baseball deficits |
| Aug 4, 2026 | CI | Four-shard PostgreSQL confidence gate | PR #609 | 7,254 collected; 7,249 passed, 5 skipped; exact ownership and separate databases |
| Aug 4, 2026 | CI | CI-001 closure (#599) | PR #610 / `ebe2db4...` / run `30957543371` | `npm ci`, 864 frontend tests, required production build, mutation-tested contract |
| Aug 5, 2026 | Phase 1B | UX-001 canonical Team State implementation (#590) | PR #611 / `8a528ef...` | 7,315 backend tests, 864 frontend tests, build success, docs updated; production triad evidence pending |
| Aug 5, 2026 | Governance cleanup | Obsolete simulation README issue #5 closed | Issue #5 | Closed as not planned; no longer matches bullpen-intelligence product identity |
| Aug 5, 2026 | Phase 1A | Game 824487 source-revision audit package | Branch `audit/game-824487-source-revision` | Pending read-only investigation: package implemented, production audit NOT executed, no conclusion reached, no repair authorized |

## 20. Phase Exit Record

| Phase | Status | Exit evidence / remaining work |
|---|---|---|
| Phase 0 - Canonical Trust Closeout | Complete | Independent official-line, starter, outs, appearance-team, and aggregation proof |
| Phase 1 - Evidence Completeness | In progress / paused | M-001 contract complete; implementation resumes after higher-priority trust work |
| Phase 1A - Authority Qualification | Active evidence closeout | D-044 merged; #593 observation and valid no-op path remain |
| Phase 1B - Vocabulary and Freshness | In progress | #590 merged/pending production; #591, #594, #595, and #600 remain |
| Phase 2 - Portable Intelligence | Foundation complete / final distribution not started | Renderer, raster assets, metadata, actions, funnel |
| Phase 3 - Daily Habit and Consequence | Not started | What Changed, lead, slate, quiet day |
| Phase 4 - Offseason Intelligence Depth | Not started | Pitch, leverage, depth, routes, archive |
| Phase 5 - Opening Day 2027 | Not started | Complete daily relaunch |
| Phase 6 - Growth and Validation | Not started | Behavior and rights evidence choose direction |

## 21. Source Basis

This current-state edition consolidates:

- the repository's prior canonical Roadmap and detailed Decision Ledger through D-046;
- the August 4, 2026 current-state Roadmap DOCX;
- repository main `8a528efec1affcdaf98fa1e87f9090d105db4248`;
- merged pull requests through #611;
- scheduled production evidence through run `30921186222`;
- GitHub issue status for #5 and #589–#601;
- the August 2 Full Platform Audit;
- the current Constitution, Bullpen Intelligence Standard, Product Experience Standard, Architecture and Operations Manual, and Editorial and Distribution Standard.

The archived predecessor file preserves the verbose rationale and evidence language for D-001 through D-046. Git history, pull requests, workflow artifacts, and runbooks remain the exact implementation and operational evidence.

## 22. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0–2.9 | Jul 29–Aug 4, 2026 | Nickolis Kacludis | Established the canonical execution roadmap and appended detailed decisions through D-046. The full verbose predecessor is preserved in the August 2026 archive and Git history. |
| 3.0 | Aug 5, 2026 | Nickolis Kacludis | Reconciled current state through PR #611 and main `8a528ef`; recorded #592 and #599 complete, #593 observation pending, #590 merged with production triad evidence pending, the current authority modes, next approved work, updated phases, priorities, risks, backlog, open decisions, completion log, and phase exits. Preserved the detailed predecessor ledger in the archive without changing any durable decision. |
