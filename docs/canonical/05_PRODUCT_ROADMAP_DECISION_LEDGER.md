# BaseballOS Product Roadmap & Decision Ledger

| Field | Value |
|---|---|
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 3.2 |
| Effective date | August 6, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `5be94b7c0640e763308a50bab93298638368f150`, with the Version 3.2 documentation closeout recorded through PR #618 |
| Decision basis | Decision Ledger through D-049 |
| Supersedes | Prior current-state wording through August 6, 2026 while preserving all durable decisions and evidence |
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
- canonical Team State delivery to live reader surfaces, proven in corrected production.

The central problem is no longer whether BaseballOS can build trustworthy baseball infrastructure. The current problem is completing the remaining sync and authority evidence closeout, removing the remaining public-contract contradictions, and then making the platform's existing intelligence more visible and portable.

## 3. Current Repository and Authority State

| Area | Current state | Meaning |
|---|---|---|
| Repository main | `5be94b7c0640e763308a50bab93298638368f150` | PR #617 merged August 6, 2026 at `d5ddb5fd56651203edf75de40d7f3f0d2630fa4b`, followed by generated team story preview pages; includes PR #615's game 824487 repair evidence and PR #616's retirement of that capability |
| Game 824487 source-revision checkpoint | Terminally closed | Verified, applied, and independently re-observed as already applied |
| Game 824487 repair capability | Retired | PR #616 merged August 6, 2026; the single-purpose repair workflow no longer exists on main and must never be reintroduced or dispatched (D-048) |
| Game-driven daily lane | Shadow | Observation only; no automated baseball-data writes |
| Game-driven postgame lane | Shadow | Exact-cycle observation after the legacy postgame writer |
| Backfill lane | Off | No automatic game-driven backfill authority |
| Production writer | Legacy sync/postgame path | Remains authoritative for baseball-data mutation |
| Automated write mode | Unapproved | Manual one-game qualification machinery grants no broader authority |
| Game-driven publication authority | Unapproved | Publication authority has not transferred |
| D-044 blocker scope | Implemented | Shadow bookkeeping backlog is observational; real baseball deficits remain fail-closed |
| PROD-001 (#592) | Complete | Scheduled production run proved full Tonight provenance persistence and readback |
| OPS-001 (#593) | Implemented; observation pending | Job separation exists; required scheduled observation window remains open |
| UX-001 (#590) | **Complete** | Closed August 6, 2026. PR #611 established backend-owned Team State with frontend passthrough; PR #617 corrected the readiness population to the canonical active bullpen after production proved a population mismatch. Corrected production run `31097712768` published and served snapshot `360` through August 5, and Team Board, Dashboard, and Compare rendered naturally occurring `Stretched` and `Vulnerable` plus a governed fail-closed case. No team naturally qualified as Fresh; closed under the D-049 natural-observability exception without manufacturing evidence |
| CI-001 (#599) | Complete | Frontend CI uses the lockfile and requires tests plus the production build |

## 4. Active Objective

> **Production evidence closeout**

Track B closed on August 6, 2026. The remaining objective is Track A: the scheduled sync and authority evidence for #593 and the governed no-op-candidate decision. It is blocked by production time rather than by missing implementation.

### Track A - Sync and authority evidence

1. Continue scheduled daily and postgame observation after D-044 and PR #602.
2. Prove `public-sync` and `shadow-activation-health` remain separately meaningful across the required observation window.
3. Confirm genuine finality, schedule-authority, appearance-row, and material-correction deficits still withhold publication.
4. Complete the bounded read-only no-op candidate path or record the explicit no-candidate decision.
5. Keep daily/postgame shadow, backfill off, legacy writer authoritative, and automated write/authoritative modes unapproved.

### Track B - Canonical Team State production proof - COMPLETE

Closed August 6, 2026 with issue #590. PR #611 established backend-owned Team State delivery; PR #617 corrected the readiness population to the canonical active bullpen after production exposed a population mismatch that collapsed supported teams toward `Vulnerable`. Corrected production run `31097712768` published and served snapshot `360` through August 5, and Team Board, Dashboard, and Compare rendered naturally occurring `Stretched` and `Vulnerable` alongside a governed fail-closed case with no invented fourth Team State.

No team naturally qualified as Fresh after all 30 clubs played on August 5. Under D-049 that absence is not an implementation defect, Fresh evidence is never manufactured, and the automated contracts remain the proof that `operationally_stable` maps to `Fresh`.

### Exit evidence

- Scheduled runs prove publication success or failure independently from shadow-observer health.
- The observation backlog may remain incomplete without becoming a publication blocker in shadow mode.
- Real baseball deficits remain blocking in every mode.
- No closeout audit mutates GameLog, work-item, checkpoint, snapshot, marker, or dead-letter rows.
- #593 closes only after its remaining scheduled-observation requirement is satisfied.

## 5. Nightly Operating State

At the August 6 closeout, no additional implementation package should begin. The current work is cleanly merged and waiting on external evidence.

Stopping is intentional:

- #591 overlaps the same reader adapters that #590 just stabilised and deserves its own clean evidence.
- #594 consumes the same Team State and freshness path in static/routed previews.
- #600 touches the same `/bullpen` surfaces and should follow the public-contract packages.
- Sync authority must not be inferred from green tests or from a short observation window.

## 6. Next Approved Work

After the current evidence checkpoint is reviewed, work proceeds in this order unless a Decision Ledger entry changes it:

1. **#595 - Public raw fatigue-score containment.** Remove or protect unauthenticated composite scores, component scores, risk tiers, and internal identifiers. This is the next independent trust package because it does not require changing Team State presentation or sync authority.
2. **#591 - Backend-owned Why copy.** Remove frontend regex rewriting, filtering, fallback invention, or silent dropping of governed public explanation text.
3. **#594 - Routed/static team metadata and freshness.** Give the 30 team preview routes a canonical owner, canonical vocabulary, named evidence, and data-through context.
4. **#600 - `/bullpen` H1 and accessibility structure.** Complete the semantic page contract.
5. **Portable Intelligence.** Canonical raster renderer, artifact-specific Open Graph/X metadata, share actions, and evidence-inspection funnel.
6. **Resume M-001 Active Bullpen ERA.** Finish registry parameters, group/contributor evidence, Team Board delivery, and full trust gates.
7. **Daily Habit and Consequence.** Public What Changed, team movement, Today lead authority, game-aware slate, and quiet-day behavior.

## 7. Current Capability Assessment

### Product surfaces

| Surface | Current state | Main gap | Governing next move |
|---|---|---|---|
| Today | Live daily front door | Stronger lead, status-aware context; no independent Team State currently rendered | Daily Habit after higher-priority work |
| Dashboard | Live league board; canonical per-team Team State proven in production | Stronger named evidence per team | Named-arm evidence expansion |
| Team Board | Flagship team surface with arm groups, recent work, and canonical Team State | Why-copy ownership; performance/starter evidence | #591, then M-001 |
| Compare | Descriptive two-team comparison; canonical state passed through per side and proven in production | H1, stronger named differences | #600 |
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
| Team State authority | Production | Exactly Fresh / Stretched / Vulnerable, backend-owned and derived from the canonical active bullpen; `Stretched`, `Vulnerable`, and a governed fail-closed case proven in production |
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
| Complete | UX-001 (#590) | Run `31097712768`, snapshot `360`, data through August 5; `Stretched`, `Vulnerable`, and a governed fail-closed case observed; Fresh closed under the D-049 natural-observability exception |
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

- #590 complete.
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
| R-13 | Live product vocabulary contradicts canonical promise | Critical | #590 is complete and protected by backend ownership, the canonical active-bullpen population, contract tests pinning the exact three-state set and mapping, and corrected production evidence. Remains listed as an ongoing regression risk |
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
| D-047 | Aug 5, 2026 | The game 824487 source-revision mismatch is investigated by a manual exact-scope read-only audit that will not guess a field delta from a SHA-256 digest | Adopted; production audit executed August 5, 2026 as run `31044299167` |
| D-048 | Aug 6, 2026 | Game 824487's source-revision checkpoint was corrected through the reviewed one-row workflow, terminally re-observed as already applied with zero additional writes, and the single-purpose repair capability is retired. The workflow must not be dispatched again. This grants no broader game-driven write or publication authority | Permanent |
| D-049 | Aug 6, 2026 | UX-001 closes after corrected production proved backend-owned `Stretched` and `Vulnerable` states across Team Board, Dashboard, and Compare plus a governed fail-closed case. A naturally qualifying Fresh team was not present after all 30 clubs played; Fresh evidence must never be manufactured. The exact three-state mapping remains contract-pinned, and a future natural Fresh capture is supplemental unless it reveals a real defect. This decision changes no sync, write, backfill, writer, or publication authority | Permanent |

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
| Aug 5, 2026 | Phase 1B | UX-001 canonical Team State implementation (#590) | PR #611 / `8a528ef...` | 7,315 backend tests, 864 frontend tests, build success, docs updated; production triad evidence pending. **Superseded by the Aug 6 production-validation failure below: the vocabulary authority was correct, the population feeding it was not** |
| Aug 5, 2026 | Governance cleanup | Obsolete simulation README issue #5 closed | Issue #5 | Closed as not planned; no longer matches bullpen-intelligence product identity |
| Aug 5, 2026 | Phase 1A | Game 824487 source-revision audit package | PR #613 / `cb4ec4a...` / run `31044299167` | Read-only audit executed: verdict `COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE`, exit 0, no failed or unproven reasons; root condition `official_appearance_set_changed`; checkpoint stale relative to current source; no repair authorized by the audit itself |
| Aug 6, 2026 | Phase 1A | Game 824487 source-revision checkpoint repair and retirement | PR #615 / merge `b29b1f0e41fffb0a58db9d276a506ae6613dfcce` / runs `31065643787`, `31065894573`, `31066123772` | Terminally complete. Verify run `31065643787` returned `VERIFIED_REPAIR_REQUIRED_AND_SAFE`, exit 0, mutation performed false (artifact `8953731050`, `sha256:e6fdd499867eaab3e13a364ac700daf6502257f4a344a86dcfb8d6cc8795ee3c`). Apply run `31065894573` returned `REPAIR_APPLIED`, exit 0, mutation performed true (artifact `8953812423`, `sha256:fa0f8c1caa9d44aed478aa6ff137beb1335bb73ef580752730c205844f5cc50e`): `game_ingestion_work_items` row `id = 103`, `mlb_game_pk = 824487`, `source_revision` moved from `90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0` to `a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4`, exactly one row affected, one target-table UPDATE issued, `source_revision` and the automatic `updated_at` the only changed columns, post-commit verification in a positively proven read-only transaction. Run `31066123772` **selected operation `apply`** and returned `REPAIR_NOT_REQUIRED`, exit 0, apply gate open false, apply attempted false, commits performed 0, zero durable write attempts (artifact `8953882289`, `sha256:860ca09c65c9d74372b93d54f8e9cf2d042caf3391da7875a303568901a4cf6e`) — the already-applied safety gate resolved it before the writable path opened. Zero GameLog changes; no other work item, governed scope, or out-of-scope digest moved. No migration, no mode change, no authority transfer. Temporary package retired by the cleanup PR |
| Aug 6, 2026 | Phase 1B | **UX-001 production validation FAILED; Team State population corrected (#590)** | `team-fans/issue-590-state-discrimination-fix` | Repository change only; no workflow dispatch, no production execution, no production database session, no row mutation, no snapshot rebuild, no artifact generation or mutation, no threshold change, no migration, no mode change. Production published Vulnerable for every supported team across materially different Dashboard lanes — Detroit read Vulnerable while showing eight rested and available arms — while Athletics correctly failed closed. Root cause is population, not vocabulary: readiness distributions were built from every pitcher carrying a fatigue score filtered only by `Pitcher.active` (starters, injured-list arms, off-active depth), while the trust metadata authorizing the same read used the canonical current active bullpen. `Avoid`/`Unavailable` maps to elevated workload, and either an unavailable count or an elevated count returns `operationally_stressed`, so one starter who worked yesterday collapsed a whole club. Membership is now resolved once in the readiness-coverage domain and used for both the distributions and the coverage check. Reproduced end-to-end on the real resolver before the fix and pinned by regression. No threshold, status meaning, public mapping, fail-closed behavior, publication authority, sync mode, writer, roster authority, or baseball-data change, and no new decision — D-003 and D-004 stand. Revalidation against the corrected build was outstanding at the time of this entry; it completed the same day and is recorded in the closeout row below |
| Aug 6, 2026 | Phase 1B | **UX-001 canonical Team State production closeout — issue #590 complete** | Issue #590; PR #611 / merge `8a528efec1affcdaf98fa1e87f9090d105db4248`; PR #617 / merge `d5ddb5fd56651203edf75de40d7f3f0d2630fa4b` | Production recovery and evidence run `31097712768` (`workflow_dispatch`, run SHA `d5ddb5fd56651203edf75de40d7f3f0d2630fa4b`, success): published, selected, and served snapshot `360`, data through August 5, 2026; publication-critical completion 418 / 418; best-effort completion 443 / 443; appearance ledger 124 / 124 completed games and 1,049 / 1,049 appearances with zero mismatches; dashboard snapshot ready/published/selected/served with cache verification passed. Reader-visible evidence: Team Board showed Los Angeles Dodgers `Stretched`, Houston Astros `Stretched`, and New York Mets `Vulnerable`, with Colorado Rockies rendering the governed unavailable presentation and no invented fourth Team State; Compare showed Atlanta Braves `Stretched` beside New York Mets `Vulnerable`, both `Published View Current` through August 5. **Fresh natural-observability exception (D-049):** all 30 clubs played August 5 and no team naturally qualified as Fresh, so no current Fresh screenshot exists and none was manufactured — the automated contracts remain the proof that `operationally_stable` maps to `Fresh` and that the public set contains exactly three labels. The daily lane remained shadow with zero GameLog writes, zero commits, zero checkpoint advances, and zero publication authority; no sync mode, writer authority, backfill setting, publication gate, threshold, formula, mapping, schema, or baseball-data row changed |

## 20. Phase Exit Record

| Phase | Status | Exit evidence / remaining work |
|---|---|---|
| Phase 0 - Canonical Trust Closeout | Complete | Independent official-line, starter, outs, appearance-team, and aggregation proof |
| Phase 1 - Evidence Completeness | In progress / paused | M-001 contract complete; implementation resumes after higher-priority trust work |
| Phase 1A - Authority Qualification | Active evidence closeout | D-044 merged; #593 observation and valid no-op path remain |
| Phase 1B - Vocabulary and Freshness | In progress | #590 complete (run `31097712768`, snapshot `360`); #591, #594, #595, and #600 remain |
| Phase 2 - Portable Intelligence | Foundation complete / final distribution not started | Renderer, raster assets, metadata, actions, funnel |
| Phase 3 - Daily Habit and Consequence | Not started | What Changed, lead, slate, quiet day |
| Phase 4 - Offseason Intelligence Depth | Not started | Pitch, leverage, depth, routes, archive |
| Phase 5 - Opening Day 2027 | Not started | Complete daily relaunch |
| Phase 6 - Growth and Validation | Not started | Behavior and rights evidence choose direction |

## 21. Source Basis

This current-state edition consolidates:

- the repository's prior canonical Roadmap and detailed Decision Ledger through D-046;
- the August 4, 2026 current-state Roadmap DOCX;
- repository main `5be94b7c0640e763308a50bab93298638368f150`, with the Version 3.2 documentation
  closeout recorded through PR #618;
- merged pull requests through #617;
- scheduled production evidence through run `30921186222`, and manual production recovery
  evidence from run `31097712768` with published snapshot `360`;
- manual game 824487 production evidence: audit run `31044299167` and checkpoint-repair runs
  `31065643787`, `31065894573`, and `31066123772`, with their retained artifacts;
- GitHub issue status for #5 and #589–#601;
- the August 2 Full Platform Audit;
- the current Constitution, Bullpen Intelligence Standard, Product Experience Standard, Architecture and Operations Manual, and Editorial and Distribution Standard.

The archived predecessor file preserves the verbose rationale and evidence language for D-001 through D-046. Git history, pull requests, workflow artifacts, and runbooks remain the exact implementation and operational evidence.

## 22. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0–2.9 | Jul 29–Aug 4, 2026 | Nickolis Kacludis | Established the canonical execution roadmap and appended detailed decisions through D-046. The full verbose predecessor is preserved in the August 2026 archive and Git history. |
| 3.0 | Aug 5, 2026 | Nickolis Kacludis | Reconciled current state through PR #611 and main `8a528ef`; recorded #592 and #599 complete, #593 observation pending, #590 merged with production triad evidence pending, the current authority modes, next approved work, updated phases, priorities, risks, backlog, open decisions, completion log, and phase exits. Preserved the detailed predecessor ledger in the archive without changing any durable decision. |
| 3.1 | Aug 6, 2026 | Nickolis Kacludis | Recorded the terminal game 824487 source-revision checkpoint closeout: corrected the repository basis to main `b29b1f0` and PR #615, corrected D-047's status and the audit completion row to reflect that read-only audit run `31044299167` was executed, added D-048 retiring the single-purpose repair capability and prohibiting any further dispatch, and logged all three production runs with their artifact identities and digests. No prior decision was changed or removed, no authority moved, no roadmap order changed, and no Phase 1A gate was closed. |
| 3.2 | Aug 6, 2026 | Nickolis Kacludis | Recorded the UX-001 production closeout: issue #590 is complete through PR #611 and PR #617 with corrected-production evidence from run `31097712768` and snapshot `360`, and Track B of the active objective is closed. Added D-049 recording the founder-approved Fresh natural-observability exception — no naturally qualifying Fresh team existed after all 30 clubs played August 5, and Fresh evidence is never manufactured. Corrected the repository basis from `b29b1f0` to current main `5be94b7`, recorded PR #616 as merged and the game 824487 repair capability as retired rather than pending, and updated the surface, capability, priority, phase, risk, and backlog wording that still described #590 as pending. Preserved Track A: #593 scheduled observation and the governed no-op-candidate decision remain the active objective, daily and postgame lanes remain shadow, backfill remains off, the legacy writer remains authoritative, and automated write and game-driven publication authority remain unapproved. No durable decision was changed or removed; D-003 and D-004 are untouched. |
