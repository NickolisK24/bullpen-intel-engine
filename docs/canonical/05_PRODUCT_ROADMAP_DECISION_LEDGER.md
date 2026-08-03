# BaseballOS Product Roadmap & Decision Ledger

| Field | Value |
|---|---|
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 1.3 |
| Effective date | July 30, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `f2017105` |
| Supersedes | Prior strategic operating manual, standalone current roadmap, phase proposals, and competing master roadmaps as execution authority |
| Update rule | Update when priority changes, work merges, a phase exits, a material decision is made, a risk changes, or current-state assessment becomes false |
| Review cadence | Weekly founder review; immediate update after a material production or product decision |

> **One active objective. One canonical roadmap. Every durable decision recorded.**

## 1. How to Use This Roadmap

- Work from the active objective downward.
- Do not begin a lower-priority item while a higher-priority trust item is open unless it is genuinely blocked or explicitly deferred in the Decision Ledger.
- Every significant completed item receives a branch/PR/commit record.
- Every philosophy-level or contract-level decision receives a Decision Ledger entry.
- New ideas enter the backlog; they do not create a new competing roadmap.
- Historical implementation plans remain useful evidence but do not override this document.

## 2. Current Product Position

BaseballOS is a live public MLB bullpen-intelligence platform with a strong trust and evidence foundation.

Current capabilities include:

- daily front door;
- league Dashboard;
- team bullpen boards;
- two-team comparison;
- search-first reliever discovery and pitcher detail;
- current workload/availability reads with roster separation;
- Stories, Methodology, Data & Trust, About, and How to Read;
- deterministic public Team State and pitcher role/read vocabulary;
- trusted league snapshots and appearance-ledger publication gates;
- immutable Team State Share Artifacts;
- automatic batch and team-progressive artifact generation;
- public immutable historical share page;
- internal artifact coverage, integrity, publication, distribution, and source-authority operations;
- substantial backend/frontend test and production-guard infrastructure.

The central strategic problem is no longer whether BaseballOS can engineer a bullpen product. It must convert trustworthy data into stronger baseball understanding and consistent public distribution without relaxing trust.

## 3. Active Objective

> **Foundation 3B / Phase 1 - Evidence Completeness: use more of the trustworthy data BaseballOS already holds.**

Foundation 3A / Phase 0 - Canonical Trust Closeout is **complete**. The official appearance record is now indisputable and independently verified in production; see Section 3A. Evidence Completeness is the sole active objective.

### First scoped work item

> **Current Active-Pen ERA and Performance Context**

**The contract is established; implementation has not started.** The Current Active-Pen Performance Contract now governs the active-group, window, sample, date, evidence, and limitation requirements for this item and for every later approved performance metric. It lives in the Bullpen Intelligence Standard, Section 7A:

- **active-group definition** - membership resolves from the canonical current roster, team-assignment, and bullpen-membership authorities for the represented baseball date; never assumed, and never a current-team fallback for a historical appearance;
- **window contract** - qualifying official completed relief appearances in the current regular season, made for the represented team by that team's current active-bullpen pitchers; other-organization appearances and starts are excluded;
- **sample contract** - the family fails closed below a metric's approved minimum sample; the mechanism is the family's, the exact threshold and denominator belong to each metric registry entry;
- **date contract** - represented baseball date, data-through date, season, method version, active-group authority date, and freshness travel with every value;
- **evidence contract** - every value is inspectable back to official completed pitching lines through named pitchers and qualifying appearances;
- **limitation contract** - the family limitation is stated where material and not repeated as boilerplate.

Open decision **O-001** is **resolved** by D-021. The reusable framework is merged as an unwired production-internal foundation, and **M-001 is now fully specified** by D-023 through D-030 — formula, denominator, minimum sample, precision, public name, below-sample wording, membership rule, and evidence contract. It is still not public. What remains is implementation: setting the approved parameters in the metric registry entry, migrating the sample comparison to the metric's declared unit, adding the contributing-arm count, and wiring a surface through the normal trust gates.

### Definition of done

- [x] Active-group, sample, date, evidence, and limitation contracts are defined and recorded.
- [x] O-001 is resolved by an explicit Decision Ledger entry.
- [x] M-001 Current Active-Pen ERA has an approved formula, minimum sample, and denominator.
- [x] M-001 has an approved public name, rounding policy, below-sample wording, membership rule, and evidence contract.
- [ ] The approved parameters are set in the metric registry entry and the sample comparison uses the declared unit.
- [ ] Team and arm surfaces show the correct group, sample, date, evidence, and limits.
- [ ] Every published performance number is inspectable back to official lines.
- [ ] Regression coverage exists for the group, window, and below-sample behavior.
- [ ] No public performance number ships before its contract is written.

### Why this is now the top priority

The trust foundation is finished, so the binding constraint has changed. BaseballOS already holds trustworthy performance data that users cannot see; the gap is no longer correctness, it is completeness. This is the highest-value public evidence gap in Section 7.

## 3A. Foundation 3A Closeout Evidence

Foundation 3A / Phase 0 - Canonical Trust Closeout is complete and independently verified in production.

| Field | Value |
|---|---|
| Production commit | `b5e88bba75f6648d38676b6b453b8a81aaa82976` |
| Closeout capability | `official_pitching_line_repair_closeout_2026_v1` |
| Result / exit code | `pass` / `0` |
| Decision reason | `foundation_3a_repair_closeout_ready_for_review` |
| Database writes performed | `false` |
| Repair reapplied | `false` |
| Failed checks | none |
| Unresolved issues | none |

Every governed check was **present, executed, passed, and not skipped** - four separate facts, each recorded separately:

- `execution_ledger_proves_the_approved_repair`
- `reviewed_amendment_row_matches_the_approved_result`
- `official_pitching_line_completeness_2026`
- `canonical_season_bullpen_aggregation_local_only`
- `canonical_season_bullpen_aggregation_official_validation`

### Original repair ledger

Execution ledger id `1`, status `completed`, approved and regenerated fingerprint both
`3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b`, 70 identity actions,
445 insertions, 160 updates, 675 total, season 2026, as of 2026-07-25, accepted baseline `v2`,
`committed_at` populated.

### Final completeness

Missing local lines 0, extra local lines 0, duplicate local lines 0, stat mismatches 0,
role mismatches 0, appearance-team mismatches 0.

### Final canonical local-only aggregation

`pass`, exit code 0, 30 teams complete, 0 partial, 0 unavailable, every locally applicable
reconciliation true. `all_mandatory_metrics_match` is explicitly **non-applicable** in
local-only mode - local-only cannot evaluate an official-validation reconciliation, and it does
not pretend to.

### Final official validation

`pass`, exit code 0, 30 teams complete, 30 matched, 0 mismatched, 0 mandatory metric mismatches,
0 unavailable official evidence, 0 official games missing a unique starter, 0 official games
with multiple starters, every applicable reconciliation true.

### Reviewed amendment row

GameLog `43765`, stable key `825058:805299:109`, `hits_allowed` 0, `stat_correction_count` 1,
correction source `official_pitching_line_repair`, correction timestamp populated, governed
operation id populated.

## 3B. Matt Festa Targeted Apply - Terminal Status

The dedicated one-action Matt Festa apply is **closed** and **must not be dispatched again**.

- It was dispatched once.
- It performed **zero writes**.
- It opened **no transaction**.
- It created **no execution-ledger row**.
- The regenerated planner found **zero actions**.
- The current population already had **zero stat mismatches**.

Fingerprint `903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b` is **obsolete for
the current production population**. The capability refused correctly: it is fingerprint-locked
to a manifest that the current record no longer produces, which is the designed outcome when a
reviewed correction is no longer needed.

**Historical causation remains unprovable.** No claim is made that any particular sync, ingestion
run, or process corrected the Matt Festa row. The retained evidence establishes what the current
official record says, not how the local record came to agree with it.

Any future recurrence requires **fresh diagnostic evidence and a new reviewed contract**. The
existing workflow is not a retry mechanism and must not be treated as one.

## 4. Next Three Approved Moves

After the active objective closes:

1. **Complete portable intelligence** - finish canonical image/metadata/action behavior so immutable intelligence can circulate without losing evidence or meaning.
2. **Daily habit and consequence layer** - ship trusted change tracking and game-aware starter/bullpen context without forecasting outcomes.
3. **Offseason intelligence depth** - add pitch, leverage, and organizational-depth domains in governed order.

Sequence may change only through an explicit Decision Ledger entry.

## 5. Founder Constraints

- One founder with a full-time job and family responsibilities.
- Planning assumption: approximately 10 to 12 focused development hours per week unless changed.
- Public MLB source availability, terms, rate limits, and response quality constrain acquisition.
- No budget assumption for paid commercial baseball-data providers.
- No product assumption exists for paid commercial baseball data before rights review.
- Scope must preserve trust, documentation, tests, and runbooks through a slow month.

## 6. Current Surface Assessment

| Surface | Current state | Main gap | Governing next move |
|---|---|---|---|
| Today | Live daily front door with watch/league context | Stronger lead and game-aware consequence | Daily-habit phase |
| Dashboard | Live full-league board | More discrimination, movement, complete named evidence | Evidence expansion |
| Team Board | Current flagship; roster-aware read groups and recent work | More performance, starter, concentration, and schedule evidence | Immediate post-trust work |
| Compare | Differentiated descriptive comparison | Stronger named differences and later slate pairing | After comparability/habit |
| Reliever Finder | Search-first utility direction | Final consistency and fast evidence handoff | Maintain, do not overbuild |
| Pitcher Detail | De-scored; recent-work evidence | Performance and pitch-trend depth | Evidence now; pitch work offseason |
| Stories | Live narrative feed | Voice/evidence consolidation and stronger non-obviousness | Ongoing quality work |
| Methodology | Live trust surface | Canonical worked example and current public vocabulary | Foundation closeout |
| Data & Trust | Strong public trust differentiation | Current correction/method history and scoped degradation | Foundation closeout |
| Share Artifact page | Immutable historical page implemented | Canonical rendered image/OG/actions/current comparison | Portable-intelligence phase |
| Internal Product Intelligence | Traffic and artifact operations exist | Unified operator navigation and refusal diagnostics | Maintain/expand when needed |

## 7. Intelligence Capability Assessment

| Capability | State | Assessment |
|---|---|---|
| Workload/appearance evidence | Production and publication-critical | Strongest core asset; current repair hardening increases defensibility |
| Active roster/team authority | Production | Strong, with fail-closed unknown/conflict behavior |
| Public arm reads and roles | Production | Canonical code-owned labels now separate public language from internal state |
| Team State | Production | Canonical labels established; evidence depth must catch up to label strength |
| Trusted snapshots | Production | Strong league authority with fail-closed publication gate |
| Team-progressive publication | Production | Prevents unrelated late games from blocking complete teams |
| Immutable Share Artifacts | Production foundation | Domain, generation, audit, and public history are real |
| Current active-pen performance | Family contract established; no metric implemented or public | Contract closed the governance gap; the first metric definition is now the binding step |
| Starter/rotation context | Partial | Source authority hardened; full consequence layer remains incomplete |
| What Changed | Internal/comparability foundation | High retention value after current trust proof |
| Leverage/concentration | Partial | Important differentiation; method/evidence still incomplete |
| Pitch characteristics | Feasibility/experimental | Strong offseason depth build after core product/distribution |
| Organizational depth | Partial/planned | Strong differentiator after active roster/transaction foundation |
| Historical timeline/archive | Snapshot/artifact foundation | Authority asset, not immediate habit blocker |

## 8. Distribution Assessment

Current strengths:

- clear niche positioning;
- trust pages and validation evidence that differentiate publicly;
- experimental and positive external interest, including Closer Monkey contact;
- immutable artifact foundation suitable for citation;
- founder story and technical credibility.

Current weaknesses:

- inconsistent cadence;
- share image/metadata not yet complete;
- limited owned audience/newsletter proof;
- outreach is not yet systematic;
- public copy can still underuse the available evidence;
- product trust/disclaimer language can become louder than the baseball insight.

The distribution goal is not maximum volume. It is repeatable evidence-bearing publication that makes BaseballOS a source.

## 9. Priority Rule

Work top to bottom. A lower tier may proceed only when the higher tier is complete, genuinely blocked, or explicitly deferred.

## 10. Critical - Trust and Source Authority

| Status | Work item | Why it matters | Definition of done |
|---|---|---|---|
| Complete / maintain | Official pitching-line repair closeout | Every workload/performance read depends on the canonical record | Read-only closeout passes; downstream evidence current. Closed at `b5e88bb...`; see Section 3A |
| Complete / maintain | Starter and relief classification authority | Prevents a reliever from being described as a starter or vice versa | Completed-game fixtures and production sample pass. Zero missing unique starters and zero multiple-starter contradictions in official validation |
| Complete / maintain | Appearance-team and historical ownership integrity | Trades/current assignments must not rewrite game history | Audit and regression tests pass. Zero appearance-team mismatches at closeout |
| Complete / maintain | Canonical integer-outs authority | Prevents decimal differences from becoming false baseball repair | Innings derived from outs; no false repair warnings |
| Complete / maintain | Appearance-ledger publication gate | Blocks incomplete final games from publishing | Deep audit and workflow gate remain green |
| Complete / maintain | Trusted snapshot and artifact integrity | Prevents unverified state from serving | Operation coverage and integrity checks pass |
| In progress | Canonical documentation cutover | Stops conflicting master documents from directing work | Six canonical docs and GitHub index/PR adopted |

No product expansion begins ahead of an unresolved canonical-record trust incident.

## 11. High - Evidence the User Can See

| Status | Work item | User problem | Definition of done |
|---|---|---|---|
| **Active - contract established, implementation not started** | **Current active-pen ERA and performance context** | Users cannot judge results beside workload without leaving BaseballOS | Contract recorded and O-001 resolved (done, D-021); M-001 formula, minimum sample, and denominator approved; then team/arm surfaces show the correct group, sample, date, evidence, and limits |
| Next | Named-arm evidence expansion | Team labels can feel generic without who and which games | Every material team read names relevant arms and receipts |
| Next | Starter-exposure context | Users need to understand how rotation length shifted innings | Official starter ranges appear as history, not forecast |
| Next | Methodology alignment | Public pages and code vocabulary have outgrown older documents | One worked example and current labels/methods render canonically |
| Planned | Roster-depth/churn evidence | Thin is weak without the observable roster constraint | Current authority and reinforcement limits visible |
| Planned | Leverage/concentration evidence | Total workload alone misses dependency | Versioned method, named arms, windows, and suppression ship |

## 12. High - Portable Intelligence

| Status | Work item | Why it matters | Definition of done |
|---|---|---|---|
| Foundation complete | Immutable artifact domain and public history | Shared claims must remain checkable | Production artifact resolves through integrity-verified page |
| Next | Canonical server-side Team State renderer | Transitional browser image path is not durable | Frozen 1080x1350 image generated from artifact contract |
| Next | Open Graph/X metadata and crawler delivery | Specific links must preview correctly | Exact artifact supplies title, description, image, alt text |
| Next | Copy link, native share, image download | Founder/user needs a simple workflow | Actions work with fallbacks and deep link |
| Next | Product Intelligence funnel | Reach alone does not show value | Generation -> landing -> evidence -> team/arm journey measurable |
| Planned | Creator seeding and citation workflow | Product needs borrowed distribution and reference behavior | Sustainable outreach tied to live artifacts/evidence |

## 13. High - Daily Habit

| Status | Work item | Why it matters | Definition of done |
|---|---|---|---|
| Gated | Public What Changed | Returning users need continuity | Trusted comparable days show factual movement; invalid days show silence |
| Planned | Team Board since-last-game movement | Team fans need a nightly reason to return | Two or three evidence-backed changes with dates |
| Planned | Today lead authority | Daily edition needs a true lede | One selected/generated lead passes quality and trust gates |
| Planned | Game-aware slate/consequence layer | State becomes useful when attached to tonight's game | Upcoming/in-progress/final state correct; starter ranges historical |
| Planned | Quiet-day design | Habit should not create filler | Today becomes intentionally shorter when no strong story exists |

## 14. Phased Roadmap

### Phase 0 - Canonical Trust Closeout - COMPLETE

**Window:** closed July 29, 2026 at `b5e88bba75f6648d38676b6b453b8a81aaa82976`.  
**Exit met:** BaseballOS can explain, field by field, why a recent official game appears exactly as it does in the Team Board, Pitcher Detail, performance metrics, stories, and artifacts. The independent read-only closeout passes with every governed check present, executed, and passed; local and official metrics reconcile exactly. Evidence in Section 3A.

### Phase 1 - Evidence Completeness - ACTIVE

**Purpose:** use more of the trustworthy baseball data already held.

**First scoped item:** Current Active-Pen ERA and Performance Context. The family contract is established (D-021), the reusable framework is merged and unwired, and the M-001 metric definition is approved (D-023 through D-030). The next step is implementation: set the approved parameters, migrate the sample comparison to the declared unit, add the contributing-arm count, and wire the Team Board component - before any public surfacing.

Scope:

- current active-pen ERA and core performance;
- named-arm evidence expansion;
- starter/rotation-transfer context;
- roster depth/churn evidence;
- leverage/concentration;
- Methodology and Data & Trust alignment;
- evidence-inspection analytics.

Non-goals: prediction, broad Statcast clone, redesign delaying evidence, new public score, or full organizational-depth system before source contracts are ready.

### Phase 2 - Portable Intelligence

**Purpose:** turn BaseballOS from a destination into a source.

Scope: canonical server-side card renderer, frozen image persistence/checksum, OG/X metadata, copy/native share/download, Product Intelligence, controlled circulation, and supersede/withdraw production proof.

### Phase 3 - Daily Habit and Consequence

**Purpose:** give returning users a reason to check before games.

Scope: Public What Changed, team since-last-game movement, Today lead authority, game-aware slate, official starter ranges/rotation transfer, story-strength selection with inspectable non-ranking method, and quiet-day behavior.

### Phase 4 - Offseason Intelligence Depth

Candidate order:

1. pitch-characteristic ingestion and trends;
2. leverage/concentration/dependency;
3. organizational depth and roster mechanics;
4. routed team pages and search discovery;
5. state timeline/archive;
6. story-engine consolidation;
7. accessibility/technical-debt window;
8. Follow My Team only if returning-user demand justifies account value.

### Phase 5 - Opening Day 2027

Relaunch the complete daily product with a full-season runway: daily edition/Slate v2, share artifacts/images v2, proven digest or newsletter only after manual evidence, creator round two, routed discovery, current media/trust proof, performance/reliability reset.

### Phase 6 - 2027 Growth and Validation

Let behavior choose the business direction: premium public, creator/media workflow, professional/coach beta, sponsorship, free trust asset, or public API/embeds only on written demand and rights support.

## 15. Dependency Map

```text
Official source identity/finality
-> complete appearance ledger
-> correct arm/team state
-> evidence objects
-> trusted snapshot/team authority
-> public story/share artifact
-> distribution and returning use
```

Key dependencies:

```text
Current Active-Pen ERA
  = official pitching lines + canonical active-group authority
  + approved family window + approved M-001 sample and denominator

Starter exposure
  = unique official starters + completed-start history + current probable context

What Changed
  = adjacent/comparable trusted states + same method/vocabulary

Share image
  = immutable artifact + render version + frozen asset

Observation archive
  = immutable publication + evidence snapshot + method version

Follow My Team
  = audience worth retaining + stable team routes + meaningful account value
```

## 16. Success Metrics

### Product quality

- percentage of public claims with inspectable evidence;
- percentage of team stories naming relevant arms;
- evidence-inspection rate;
- time for first-time user to identify state and reason;
- quiet-day suppression/intentional silence;
- public/current vocabulary defects: target zero;
- unexplained public numbers: target zero.

### Trust

- silent stale incidents: target zero;
- final-game ledger defects reaching publication: target zero;
- official starter mismatches reaching public copy: target zero;
- artifact integrity mismatches served publicly: target zero;
- unknown-as-zero defects: target zero;
- trusted snapshot/team-publication coverage and reasons;
- method-version and correction-history completeness.

### Habit

- weekly returning users;
- direct/referral traffic;
- team-page return rate;
- Today-to-Team handoff;
- What Changed engagement;
- newsletter subscribers/open rate only after manual cadence proof.

### Distribution

- generated/reused/refused artifact accounting;
- copy/native-share/image-download actions;
- human share-page views separated from crawlers;
- evidence inspection from share pages;
- downstream Team Board/Pitcher Detail opens;
- external citations, backlinks, and creator mentions;
- freshness stamp retained in external screenshots/posts.

## 17. Risk Register

| ID | Risk | Severity | Standing control |
|---|---|---|---|
| R-01 | Canonical game data is wrong/incomplete | Critical | Source authority, ledger gate, repair manifest, independent closeout |
| R-02 | Foundation perfectionism prevents public learning | High | Phase exits, active-objective rule, evidence-first user outcomes |
| R-03 | Generic stories fail to surprise | High | Named-arm rule, story shapes, suppression, editorial review |
| R-04 | Trust warnings overpower the baseball insight | High | State first, evidence second, limitation only when material |
| R-05 | Single-founder capacity fragments work | High | One active objective, branch discipline, sustainable cadence |
| R-06 | Transitional share renderer becomes permanent duplicate architecture | High | Canonical renderer phase; no new legacy composition |
| R-07 | MLB source terms/availability change | High | Attribution, polite ingestion, provenance, pre-commercial review |
| R-08 | A public label overclaims availability/health/intent | High | Backend public mappings, language guards, Unobservable Ledger |
| R-09 | Multiple documents create conflicting authority | High | Six-document library and archive policy |
| R-10 | Competitor copies the surface | Medium | Trust history, evidence depth, immutable memory, creator workflow |
| R-11 | SEO remains weak | Medium | Routed team pages and server/static metadata offseason |
| R-12 | Burnout reduces cadence | High | Three-post ceiling, life-first planning, manual proof before automation |

## 18. Stop Conditions

Stop the current branch/phase when required baseline is absent from `origin/main`, source authority is unresolved, a public term has two owners, implementation requires prediction/intent/health inference, migration cannot preserve history, production smoke cannot complete safely, a dangerous write lacks read-only plan and confirmation, or change silently expands scope beyond the approved objective.

## 19. Backlog

### Near term

- current-pen performance evidence;
- starter exposure/rotation transfer;
- named-arm evidence expansion;
- Methodology worked example;
- Data & Trust domain completeness;
- canonical renderer/OG/actions;
- Public What Changed;
- team movement strip;
- creator seeding and evidence-led outreach.

### Offseason

- pitch trends;
- leverage/dependency;
- organizational depth;
- routed team pages/SEO;
- state timeline/archive;
- story-engine consolidation;
- Start Here merge;
- accessibility pass;
- debt work only when large modules are touched;
- CI false-confidence/freeze-guard cleanup.

### Parked until demand

- Follow My Team/account expansion;
- automated newsletter digest;
- game pages beyond the Slate;
- embeddable partner widgets;
- public API/exports;
- push notifications;
- professional/team-sales tooling;
- sponsorship/monetization tests.

### Never backlog

Predictions, betting/odds, game-outcome projections, injury prediction, fantasy start/sit, manager-intent claims, generic rankings, black-box scores, general prospect/draft/trade product inside BaseballOS, paid resale without rights authority, and user-editable baseball claims inside immutable artifacts.

## 20. Decision Ledger Rules

- Entries are append-only.
- Reversals require a new entry referencing the original.
- Every entry has date, decision, rationale, status, affected canonical documents/code owners, and implementation references where applicable.
- Implementation detail belongs in branch/PR; this ledger records durable meaning.

## 21. Permanent and Standing Decisions

| ID | Date | Decision | Status |
|---|---|---|---|
| D-001 | Prior to Jul 2026 | BaseballOS is trust-first | Permanent |
| D-002 | Prior to Jul 2026 | Predictions, betting, fantasy advice, private injury claims, and manager-intent certainty are prohibited | Permanent |
| D-003 | Jul 24, 2026 | BaseballOS publishes the public Team State labels Fresh, Stretched, Vulnerable | Adopted |
| D-004 | Jul 24, 2026 | Team State is exactly three labels; internal states remain internal | Standing |
| D-005 | Jul 2026 | Public pitcher read labels are Clean Option, Watch Arm, Limited Rest, Unavailable, and Limited Read; backend/public keys own semantic identity | Standing |
| D-006 | Jul 2026 | Immutable Share Artifact, not image/browser component, is source of truth | Permanent |
| D-007 | Jul 29, 2026 | Team-progressive publication may publish an eligible team artifact before full-league slate completion | Adopted |
| D-008 | Jul 29, 2026 | Integer recorded outs are semantic innings authority; decimal innings are derived | Permanent data rule |
| D-009 | Jul 29, 2026 | Historical appearance team derives from game side, not current organization | Permanent data rule |
| D-010 | Jul 24, 2026 | Meaning-bearing Share Artifact copy is deterministic, backend-owned, and not free-form AI analysis | Permanent |
| D-011 | Jul 2026 | Published artifacts are immutable; corrections supersede/withdraw rather than rewrite | Permanent |
| D-012 | Jul 2026 | Current and historical state remain separate objects | Permanent |
| D-013 | Prior to Jul 2026 | Nickolis Kacludis is sole author/committer of repository record; no AI attribution is added | Permanent |
| D-014 | Prior to Jul 2026 | One question per page and one canonical home per fact | Permanent |
| D-015 | Prior to Jul 2026 | Manual proof precedes automation for newsletter/distribution workflows | Standing |
| D-016 | Prior to Jul 2026 | Follow My Team waits for audience evidence | Standing |
| D-017 | Jul 29, 2026 | Six living canonical documents replace recurring master documents | Adopted |
| D-018 | Jul 29, 2026 | Foundation 3A / Phase 0 Canonical Trust Closeout is formally complete. The independent read-only closeout at `b5e88bb...` returned `pass` / exit 0 with every governed check present, executed, and passed, zero failed checks, zero unresolved issues, and no database writes. Local and official metrics reconcile exactly across all 30 teams. Foundation 3B / Phase 1 Evidence Completeness becomes the sole active objective, with Current Active-Pen ERA and Performance Context as the first scoped item | Adopted |
| D-019 | Jul 29, 2026 | The dedicated Matt Festa one-action apply is closed and must never be dispatched again. It ran once, wrote nothing, opened no transaction, and created no ledger row, because the regenerated planner found zero actions against a population that already had zero stat mismatches. Fingerprint `903766c4...` is obsolete for the current production population. Historical causation remains unprovable; no sync or process is credited with the correction. Any recurrence requires fresh diagnostic evidence and a new reviewed contract | Permanent |
| D-020 | Jul 29, 2026 | A one-action governed apply that refuses because its reviewed manifest no longer regenerates is a correct terminal outcome, not a failure to retry. Fingerprint-locked capabilities are never re-dispatched to "make them succeed" | Permanent |
| D-021 | Jul 29, 2026 | **O-001 is resolved.** BaseballOS establishes one reusable performance-intelligence family, the Current Active-Pen Performance Contract, for metrics describing how the pitchers currently comprising a team's active bullpen have performed in official completed games. The family owns the active-group authority, window, fail-closed sample mechanism, date and freshness stamps, evidence chain to official completed pitching lines, and material limitation. Membership resolves from the canonical current roster, team-assignment, and bullpen-membership authorities for the represented baseball date; historical appearances remain owned by the team side for which the pitcher appeared, with no current-team fallback. The window is qualifying official completed relief appearances in the current regular season made for the represented team, excluding other-organization appearances, starts, and unapproved game types. The Team Board is the canonical public home; every surface, including the Team Board, consumes the same backend-owned canonical performance authority. Current Active-Pen ERA is the first planned metric under this contract and is not itself the contract | Adopted |
| D-022 | Jul 29, 2026 | A **metric family** and a **metric definition** are separate governed objects. A family owns one baseball question and one common authority contract; individually versioned metric registry entries inherit it and define their own key, formula, numerator, denominator, sample, evidence, refusal behavior, method version, approved surfaces, and fixtures. Adding an approved metric under an established family does not reopen the family decision. Public surfaces consume governed intelligence families and never create local interpretations of them. The registry reserves **M-001 Current Active-Pen ERA** with status contract pending implementation / not public; no other performance metric is approved, implemented, or public | Adopted |

| D-023 | Jul 30, 2026 | **M-001 minimum sample.** Current Active-Pen ERA publishes only when its qualifying appearance set totals at least **108 recorded outs (36.0 innings)** of official completed relief work for the represented team. The threshold is stated in the metric's own denominator unit, never in appearance count, because ten one-out appearances is ten outs and an appearance gate would admit a sample the rate cannot support. It is derived, not chosen: one earned run moves the value by `27 / outs`, and 108 outs is the smallest whole-out sample at which a single earned run cannot move the published value by more than 0.25. The derivation depends only on the formula, so the threshold does not require seasonal revision. A lower threshold would publish a second decimal place that one inning can dictate; a higher threshold would suppress true, checkable results for a bullpen rebuilt at the deadline, which is when a reader most needs them. The zero-denominator refusal is evaluated first and is not replaced by this check | Adopted |
| D-024 | Jul 30, 2026 | **M-001 formula and denominator authority.** The approved formula is `earned_runs * 27 / recorded_outs`, reusing the convention already in production-internal use rather than restating it. The denominator is total **integer recorded outs**; the numerator is total earned runs times 27. Decimal innings are display-only and never participate in the calculation, because MLB innings notation does not sum, because float accumulation is not reproducible across recomputation or inside a frozen artifact, and because the evidence rows must add exactly to the published denominator. A zero denominator refuses as `era_denominator_zero` before any sample evaluation. D-008 is preserved unchanged | Adopted |
| D-025 | Jul 30, 2026 | **Rounding and precision policy for the performance family.** Numerator and denominator are exact integers; no floating-point type participates at any stage; the ratio is an exact decimal quotient rounded `ROUND_HALF_UP` exactly once at the metric's declared precision; the value is stored as a fixed-precision string beside its exact integer numerator and denominator; and the frontend never rounds, re-rounds, truncates, or reformats. M-001's declared precision is two decimal places, always. Half-up rather than round-half-to-even so a reader can reproduce the value by hand and so adjacent values do not round in opposite directions. A real zero publishes as `0.00` and is never rendered as missing. Each future metric declares only its own precision and inherits every mechanic unchanged | Adopted |
| D-026 | Jul 30, 2026 | **Below-sample public wording.** The approved read is **Not Enough Innings Yet**, always rendered with the group's current relief innings and the required innings adjacent, because an unexplained threshold is prohibited on public surfaces. It states insufficient evidence without implying poor performance, hidden data, or system failure, and it is plain baseball language. `Limited Read` and `Unavailable` are refused because they are governed arm-read labels under D-005 with established meanings about a single pitcher; `Monitor` is refused because it is an internal availability state carrying an implied instruction. Insufficient Sample, Not Yet Published, Sample Building, Early Sample, Too Few Innings, and No Qualifying Innings were each considered and rejected | Adopted |
| D-027 | Jul 30, 2026 | **No-usage call-up rule.** A reliever resolved into a team's active bullpen who has no qualifying relief appearances for that team is **included in the group and contributes zero qualifying appearances**. His zero outs and zero earned runs enter no numerator and no denominator, because the metric is a ratio over recorded work and not an average of per-pitcher rates. This is not unknown-as-zero: his count of appearances for this team is observed, not missing. Substituting a league rate, a prior-club rate, or a zero rate is prohibited, and his prior-organization appearances stay with that organization under D-009. Every read reports both **group size** and **contributing arms**, and discloses the difference in one sentence when they differ; a difference is normal information, never an error state. Excluding him was rejected because it silently answers a different question and hides the fact that most changes how the number should be read; representing him separately was rejected because it creates a second group and a second number. Because the sample threshold is evaluated in outs, a group padded with non-contributing members cannot cross the gate on membership alone. This decision governs representation once membership resolves; whether the bullpen-population authority finds a newly active arm with no usage-based role evidence remains a separate open population question | Adopted |
| D-028 | Jul 30, 2026 | **M-001 public name.** The public rendered name is **Active Bullpen ERA**. The stable registry identity `M-001`, the governed internal metric name Current Active-Pen ERA, and the governed family name Current Active-Pen Performance are unchanged, following the pattern D-005 established in which backend keys own semantic identity and the public catalog owns rendered language. No prior decision is reversed; D-021 and D-022 explicitly reserved the public label. Current Active-Pen ERA was rejected for public use as internal-sounding; Current Bullpen ERA was rejected because "Current" attaches to the wrong noun and reads as recent form; Season ERA (Active Bullpen) was rejected as a caption rather than a name; Today's Bullpen ERA was rejected as implying tonight's game; and bare Bullpen ERA was rejected because it names a different, already-existing internal number | Adopted |
| D-029 | Jul 30, 2026 | **M-001 evidence contract.** The family's four evidence levels are filled for M-001 and become the template every later metric fills. Level 1 requires the public name, the value or the below-sample read or the typed refusal, the represented baseball date, and freshness. Level 2 requires group size and contributing-arm count, qualifying appearance count, total recorded outs with derived display innings, the exact integer numerator and denominator, the minimum sample with its unit and authority, the method version and effective date, and the material limitation where it applies. Level 3 requires every group member named with his appearance count and outs including zeros, every qualifying appearance as a row carrying game, date, opponent, appearance-team identifier, outs, and earned runs, and any material exclusion reason. Level 4 requires the named source authority per appearance, appearance-team authority status and source, schedule and finality authority, and the method version. **A value whose evidence cannot reach Level 4 is not publishable.** League averages, prior-period values, projections, rankings, quality adjectives, and any value without its group and sample are prohibited at every level. A metric may add fields at Levels 2 and 3; it may not add, rename, or reorder a level, or make a required field optional | Adopted |
| D-030 | Jul 30, 2026 | **Future metric inheritance.** A metric under an established family inherits unchanged, and may not redefine, the governing question and scope, the active-group authority and its resolution date, the window contract and exclusions, appearance-team authority with no current-team fallback, integer outs as the innings authority, fail-closed publication with typed refusals, the unknown-as-zero prohibition and the one-invalid-row-refuses-the-read rule, date and freshness stamps, the four evidence levels, the family limitation, the rounding mechanics of D-025, the gate model, and the canonical public home. It defines for itself its key and version, public name, Level 1 question, formula, numerator, denominator, required source fields, displayed precision, minimum sample value with unit and authority, denominator-zero refusal code, metric-specific limitation, approved surfaces, and deterministic fixtures. A metric may be registered before its minimum sample is approved; it computes and refuses to publish. **A metric whose required source domain is Experimental, Partial, or Deferred in the capability registry may not be registered until that domain reaches Production**, because it could never satisfy evidence Level 4 | Adopted |
| D-031 | Jul 31, 2026 | **Foundation 3C bootstrap is complete, and completing it grants no activation authority.** All 109 governed final games are reconciled and checkpointed, 946 appearance rows are reconciled, and publication completeness is satisfied for the governed window. The bootstrap was performed by explicit manual dispatch across six reviewed increments (R1-R6, PRs #572-#579), never by enabling the lane. `GAME_DRIVEN_INGESTION_MODE` remains `off` and authoritative mode remains **unapproved**; each is a separate decision requiring its own reviewed change and its own evidence, because a completed bootstrap is a precondition for considering activation rather than an argument for it. D-008 (integer recorded outs are the semantic innings authority) and D-009 (historical appearance ownership) are unchanged and permanent; parity contract version 4, which fingerprints the pitcher-identity decision by value, is likewise permanent. R6 wrote 99 work items, so the accurate claim is that only governed ingestion control state changed and no baseball-data row changed - not that no database writes occurred. R6 created no new dead letters; the pre-existing global count of 1,389 at closeout belongs to unrelated work and is not a Foundation 3C claim. The 14 false GameLog provenance events and the first-write Pitcher forensics remain open and outside this closeout | Adopted |
| D-032 | Jul 31, 2026 | **The Foundation 3C rollout is closed.** Stage E1 independently verified the completed bootstrap in production at repository SHA `bd7e610...`, workflow run `30673146173`: 109 completed / 0 unresolved, 946 reconciled appearance rows, a full 109-game read-only replay returning 946 rows unchanged and 323 decimal-only differences safely ignored, zero mutations on every target, zero database drift, zero governed-bootstrap dead letters, and the global dead-letter count unchanged at 1,389. Stage E2 then retired the Stage E workflow and the remaining temporary scope, inspection, validation, manifest, and workflow-test support; **no Foundation 3C rollout workflow remains**. The final full-bootstrap fingerprint `9f0fe983...e2c6` and full-scope digest `e8cde57b...a804` are **historical closeout identities and never authorization for a future write**. D-008, D-009, parity contract 4, planner authority, fail-closed completeness, per-game transactional checkpoints, and the permanent regression coverage all remain. `profile_daily_ingestion_readonly.py` is retained as activation operations support and `inspect_first_write_pitcher_identity.py` as unresolved forensic support. **No decision was made to enable shadow, write, or authoritative automation.** The next decision is automated game-driven ingestion shadow activation, which requires its own reviewed change and production observation | Adopted |
| D-033 | Aug 1, 2026 | **Automated shadow activation was halted at its baseline gate, and the missing postgame integration point was built instead.** Foundation 3C wired the game-driven lane into `run_daily_sync` only; `run_postgame_refresh` — the cycle that ingests completed games overnight and therefore produces most of the lane's candidates — had **no integration point at all**. Wiring `GAME_DRIVEN_INGESTION_MODE: shadow` into the production workflow in that state would have produced a postgame activation artifact describing a lane that never ran, which is worse than no evidence, so the activation was stopped and this repair delivered in its place. Three properties are now permanent. **(1) One integration point per cycle.** Each of daily and postgame reaches the lane through exactly one `run_game_driven_ingestion` service call; there is no second ingestion command, no second comparator, and no duplicate planning pass. **(2) The postgame lane reads after its cycle's writer, not before it.** The postgame sweep commits per game, so a lane placed ahead of it would project every row the sweep is about to insert — noise, not evidence, and a projection no clean-cycle contract could ever accept. The daily ordering stays the opposite because there the game lane is the one that becomes authoritative. **(3) Writing modes are refused on the postgame cycle.** The daily sync can host a writing game lane because `skip_game_pks` prevents its demoted pitcher loop from rewriting a game the lane just reconciled; the postgame sweep has no equivalent, so `write` and `authoritative` are refused there before any MLB request and before any write, and a refused lane is forced non-authoritative. Lifting that refusal requires building postgame conflict prevention in its own reviewed change. The postgame lane is bounded by `POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS` (default 600s) so it can never consume the 20-minute postgame command timeout; reaching the bound is a clean resumable stop, exceeding the timeout would kill the whole refresh. **Nothing was activated.** `GAME_DRIVEN_INGESTION_MODE` remains `off`, `.github/workflows/baseballos-sync.yml` is unchanged, no schedule or cadence moved, publication authority is unchanged, and automated write and authoritative modes both remain **unapproved**. Automated shadow activation remains the next decision and is now unblocked for both cycles | Adopted |
| D-034 | Aug 1, 2026 | **Automated game-driven ingestion shadow activation is approved for the daily and postgame production cycles.** `GAME_DRIVEN_INGESTION_MODE: 'shadow'` is set on the two runner steps in the existing sync workflow and nowhere else; the explicit backfill step sets `'off'` because it invokes the same postgame runner and would not inherit the default; morning schedule-only, Tonight, and intraday remain off. The reviewed workflow source is the activation authority — there is no workflow input and no repository variable that could move the lane to a writing mode without code review. **The two cycles are governed by deliberately different contracts, because they observe different moments.** Daily projects BEFORE the legacy pitcher writer, so projected inserts, updates, appearance-team changes, minimal identity creations, and statistical corrections are legitimate; a daily cycle that failed merely for finding work would fail on every day the lane is useful. Daily is instead judged by a read-only **realization proof** taken after that writer: each plan row carries the fields it intends to determine and a digest of the values it intends them to hold, and the same encoder digests the same fields read back from the stored row, so equal digests prove the writer realized the projected target. The proof calls no MLB endpoint, re-plans nothing, and writes nothing. Postgame projects AFTER the existing completed-game writer, so a healthy cycle must **converge to zero** — zero projected inserts, updates, blocked rows, and mutation targets including minimal identity creation; any nonzero projection means the postgame writer left canonical work behind and fails activation health without triggering any automatic game-driven write. **Projected reconciliation actions are never reported as database writes performed by shadow.** Actual effects are counted separately in `execution_effects`, at the write sites themselves rather than derived from the mode name, so a zero there is a measurement. The current sync and publication path remains authoritative; `publication_critical` still reads the game lane only in authoritative mode. Activation validation, credential scanning, summary, and artifact upload all run after the established production gates under `always()`, with the health gate last, so a shadow defect can fail the Actions run but can never preempt or withhold production data the current authority would publish. Artifacts retain 30 days and every one records `write_approved: false` and `future_write_authorized: false`. Rollback is a focused change of those two step environments back to `'off'`, requiring no database cleanup because shadow performs no writes. **Promotion to automated write may not be proposed** until at least one clean scheduled daily PASS, two clean scheduled postgame PASS cycles, one cycle with planned work, one daily cycle with projected work and complete realization parity where such work occurred, and at least 24 hours of clean production observation — 48 hours maximum — with no activation failure, unresolved or divergent daily target, nonzero postgame projection, shadow write, work-item or checkpoint change, game-driven dead letter, or publication regression. **No decision was made to enable write or authoritative mode**; both remain unapproved and each requires its own reviewed change | Adopted |
| D-035 | Aug 1, 2026 | **The first automated postgame shadow cycle failed safely, and postgame shadow is temporarily disabled while its scope is repaired.** The activation gate returned FAILED; the production path was untouched — postgame sync `success`, runner exit `0`, publication verified with snapshot `324`, and **zero shadow writes on every counter**. That is the isolation contract behaving exactly as designed: the observer failed and production did not. **The cause was scope, not speed or safety.** The lane was given a reference date and no scope, so the canonical planner swept its rolling seven-day correction horizon — 112 games, 87 of them corrected-final from earlier dates — while the postgame refresh had already resolved the only set that cycle governs. It completed 98 of 112 within its 150-second allocation and left 14 remaining. **Repair:** the postgame lane now runs under exclusive scope over its own cycle's completed games, resolved AFTER the writer because eligibility depends on what that writer finished; only fully-processed games are eligible, every excluded game carries a named reason (`incomplete_after_writer`, `failed_marker`, `no_processing_marker`), and the scope costs no MLB request and no second planning pass. Daily keeps its correction-horizon behaviour — the seven-day observation still happens, under the cycle it belongs to. **Diagnostics:** every non-unchanged projected row is now identified by game, pitcher, canonical field names, a closed-vocabulary difference classification, source revision, fingerprint, and target/stored digests, all derived from the canonical plan with no second comparator and with no values ever serialized. **Budget reporting** now names the configured cap, the lane share, and the effective allocation separately, because a 600-second cap beside a 150-second allocation read as 600 seconds available; **neither the cap nor the share was raised**, since a larger budget would hide a scope defect rather than fix it. **Game 824488 is diagnosed to a class, not to a cause**: a GameLog update on one of nine appearances whose changed fields include a statistical field, definitively not canonical-outs, appearance-team, identity, provenance-only, or decimal representation drift. The pitcher, field, and values are absent from the artifact, which predates the diagnostic. **No repair was made, because no cause is proven** — both the postgame writer and the shadow projection reach the same canonical planner, so this is not a second-comparator defect, and guessing would risk mutating real baseball data to match a projection whose authority is unestablished. Postgame shadow reactivation is a separate reviewed decision. **Daily shadow remains enabled. Automated write and authoritative modes both remain unapproved** | Adopted |
| D-036 | Aug 1, 2026 | **The exact-cycle scope repair is accepted and automated postgame shadow is reactivated.** The postgame runner step returns to `shadow`; daily remains `shadow` and backfill remains `off`, all three as reviewed literals in the workflow source with no input and no repository variable able to move them. Activation validation, credential scanning, job summary, artifact upload, and the final health gate cover both eligible cycles again, still after the established production gates, still under `always()`, and still never a prerequisite for a publication step. **The scope itself is now validated, not merely the projection.** The validator checks `scope_source`, deterministic and unique requested identifiers, the planner's own `execution_scope_exact_match`, absence of missing requested games and unexpected planned games, a planned count never exceeding the request, a requested count never exceeding the cycle, complete request-plus-exclusion accounting against the cycle game count, and a named reason on every exclusion — so a repeat of the first cycle's seven-day fan-out fails on `postgame_scope_fan_out` rather than only on the budget it exhausted. **A nonzero projection must additionally be attributable**: the validator refuses to pass any projected change that lacks one safe diagnostic per non-unchanged row carrying game, pitcher, changed field names, difference classification, source revision, fingerprint, and both digests, and refuses any diagnostic carrying `before`, `after`, `field_changes`, or `values`. The first cycle reported one projected update and nothing about which row; that is now impossible to pass. Postgame still runs after its writer, still refuses `write` and `authoritative` with `write_mode_unsupported_for_cycle`, still requires zero projected mutations on every target for a clean cycle, and still performs zero actual writes. Neither the 600-second cap nor the 0.25 lane share was raised. Current sync and publication remain authoritative. **Postgame observation restarts from this reactivation** — cycles observed before it do not count — and requires one clean scheduled daily PASS, two clean scheduled postgame PASS cycles, at least one postgame PASS with planned work, and at least 24 hours, to a 48-hour maximum. **No decision was made to enable write or authoritative mode; both remain unapproved** | Adopted |
| D-037 | Aug 1, 2026 | **GameLog `balls` field authority is UNRESOLVED, and no writer was changed.** A persistent parity discrepancy was isolated exactly — game `824488`, pitcher `668716`, field `balls`, projected as one `statistical_correction` update, recurring across a postgame and a daily shadow cycle at the **same source revision** (`af7729c3…13549`) and the **same plan fingerprint** (`74b67781…921969`), stored digest `3ab06ef31018f9694a6faebac8d595c5` against target `939546c2f2c43a9db2a455613fac36ec`. The surrounding daily cycle was healthy: sync success, runner exit 0, publication verified at snapshot `326`, 97/97 games, 814 of 815 rows unchanged, **zero shadow writes on every counter**, and the legacy writer reporting `logs_corrected: 0`. **The code proves the mechanism; it does not prove the authority.** There is one canonical values builder and one planner, both shared by the box-score and player-game-log paths, so this is not a second comparator and not a planner defect. `correctable_fields` appends an optional statistic only when the source dict carries its key with a **non-null, non-empty** value, so a lane whose source omits the field never compares it and can never correct it — it is not found equal, it is never looked at, and the stored value is correctly preserved rather than clobbered. Compounding it, the postgame writer processes only games without a fully-processed marker and therefore never revisits a complete row, leaving the daily lane — which reads the player game-log split — as the only lane that re-examines an appearance inside the correction horizon. **What remains unproven** is whether the real split carries `balls` at all, whether box-score `balls` and split `balls` are the same statistic, which source produced the stored value, and whether box-score `balls` is authoritative for the GameLog contract. Resolving those requires the two live source payloads and the stored row, and this work had **no MLB access and no production access**. **Decision: Outcome E — unresolved.** No writer changed, no correction vocabulary changed, `balls` neither added to nor removed from the governed set, no contract version moved, no migration. The shadow failure stays active because it reports something real: silencing it would make the lane green while leaving a canonical field permanently uncorrectable, and blessing it would authorize a production write to real baseball data on an unestablished value. **Added instead:** `uncomparable_fields` on every canonical plan and every projected difference, naming the governed optional fields a source shape could not evaluate — turning an invisible asymmetry into evidence; and `backend/scripts/inspect_gamelog_field_authority.py`, a read-only audit that collects the box-score line, the split, and the stored row, runs both shapes through the canonical planner, opens a read-only transaction, proves a write is refused, fingerprints the row before and after, and rolls back, reporting exact values only for `balls`, `strikes`, and `pitches_thrown`. **No production data was changed. Daily and postgame shadow remain observation-only. Automated write and authoritative modes remain unapproved** | Adopted |
| D-038 | Aug 1, 2026 | **The completed-game box score is canonical for GameLog `balls`, and the daily lane may now fall back to it for that one field.** The D-037 audit was run against production and returned the three values that settle it: completed-game box score `balls 19, strikes 26, numberOfPitches 45` (19 + 26 = 45, internally coherent); player game-log split carrying strikes and pitches but **no `balls` key at all**; stored row `balls 20, strikes 26, pitches_thrown 45` (20 + 26 = 46, internally incoherent) already carrying `last_stat_correction_source: daily_game_log` and `stat_correction_count: 1`. Both source shapes were run through the canonical planner: the box-score shape planned `update` with `changed_fields: ['balls']` and target 19; the split shape planned `unchanged` with `uncomparable_fields: ['balls']`. The audit performed zero writes, its write probe was refused, and the row fingerprint was identical before and after. **Outcome A: the split never contradicted the box score — it had nothing to say — and the correction-horizon writer cannot realize the field**, because the daily lane is the only lane that revisits an existing appearance inside the horizon and the daily lane reads the split. The stored value was uncorrectable, not disputed. **Repair:** `services/gamelog_source_authority.py` declares field authority in one place under the contract `player_split_primary_with_boxscore_fallback` (version `1`): a field the split supplies is reconciled from the split exactly as before and a fallback **never** overrides evidence that exists; a field the split omits or nulls is still reported through `uncomparable_fields`, so absence is never treated as agreement; and only for an **explicitly approved** field may the completed-game box score supply it. **The approved set has exactly one member, `balls`**, with required companions `strikes` and `numberOfPitches` and the validation rule `balls + strikes == numberOfPitches` — a **validation** of the official triple, never a derivation, so a line carrying strikes and pitches but no `balls` supplies nothing and a line whose accounting does not add up is refused rather than reconciled. Widening the approved set requires its own production audit, semantic rule, and validation. **No second comparator and no second writer**: an approved value is merged into a copy of the split's stats and flows through the same `_game_log_values_from_stats` → `plan_row` → `_upsert_game_log_from_authoritative_values` path as every other field, with no direct row assignment anywhere; every upstream safety rule stays upstream — a non-final game is skipped before any fetch, a partial source line is still blocked, and game-driven conflict prevention is unchanged. **Every refusal is named** (`field_not_approved_for_fallback`, `split_supplies_field`, `game_not_final`, `boxscore_unavailable`, `no_boxscore_pitching_line`, `field_absent_in_boxscore`, `required_companion_absent`, `boxscore_values_inconsistent`, `source_revision_missing`, `pitcher_identity_ambiguous`), and two box-score lines claiming one pitcher refuse rather than choose. **Cost is bounded**: one box-score read per game per run, cached and shared with the existing leverage-index backfill, only when an approved field is genuinely uncomparable, under a fetch cap whose exhaustion is counted and reported; **the daily ingestion budget was not raised**. **Provenance names the authority for the values that actually moved**: a correction the fallback enabled records `completed_game_boxscore_fallback`, not `daily_game_log`, while a correction the split itself drove keeps `daily_game_log`. **Observability is unconditional** — every run reports eligible, fetched, applied, corrected, inserted, already-matching, refused, cap-reached, and per-reason refusal counts plus a bounded record set naming game, pitcher, fields, classification, source authority and version, source revision, plan fingerprint, applied target digest, and outcome, and carrying no source payload. **Impact is enumerated before any correction**: `scripts/plan_boxscore_balls_fallback_impact.py` narrows the horizon in two bounded stages (one box-score fetch per game, then one game-log fetch per candidate pitcher), runs the real planner over each candidate, reports any proposed change outside the approved field, and reports what it could not confirm rather than quietly narrowing — under a read-only transaction, a refused write probe, before/after horizon fingerprints, and an explicit rollback, performing zero writes. **No production correction was executed. No contract version moved and no migration was added. Daily and postgame shadow remain observation-only, backfill remains off, and automated write and authoritative modes remain unapproved** | Adopted |
| D-039 | Aug 2, 2026 | **PROD-001: the 14:00 UTC schedule/Tonight lane was failing on column capacity, and the repair is capacity — not a shorter provenance value.** The lane failed on every scheduled run. It was **not** an MLB outage, a missing secret, a timeout, a schedule-finality failure, an appearance-ledger failure, a shadow-ingestion failure, or a publication-authority failure; the appearance-ledger audit over the same period reported 127/127 completed games, 1,082/1,082 stored appearances, zero latest-appearance mismatches, zero players affected, no missing game_pks, and **publish eligible: YES**. The lane reached MLB successfully — `/schedule` returned **HTTP 200** at 2026-08-02T14:33:58Z and the schedule rows committed — and then died at 14:35:04Z persisting the Tonight snapshot with `psycopg2.errors.StringDataRightTruncation: value too long for type character varying(40)` on `UPDATE tonight_intelligence_snapshots SET response_json = ..., source = ...`. The composed provenance is `github_actions_morning:schedule_coherence`, **41 characters against a VARCHAR(40) column** — deterministic, and therefore permanent until schema and composition agreed. **The defect was structural, not caused by one workflow input**: the service's own default composes to `morning_slate_schedule:schedule_coherence`, also 41 characters, so every caller of this path was one character over and shortening the workflow source would have moved the failure one caller down. **Decision: widen the column to VARCHAR(128) through reviewed migration `c7f1b408d93a` (down revision `b9d4e17c3a80`, one head), and preserve the complete provenance.** The migration reads no row, rewrites nothing, and leaves nullability, defaults, indexes, and every unrelated column untouched; its **downgrade refuses** rather than corrupting, counting rows longer than 40 first and failing with a clear message instead of silently truncating. 128 was sized from real composition: it keeps the full 41-character value, leaves bounded room for foreseeable `source:purpose` composition, and keeps the field finite and governed — an unbounded `TEXT` column would trade one silent failure for an unbounded one, and 41 or 42 would leave the next composed purpose to rediscover this incident. `TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH` in `models/tonight_intelligence_snapshot.py` is the single owner of the width; the model column, both validators, and a PostgreSQL test asserting the **live** column all read it, so schema and application cannot drift silently. **Validation moved ahead of the transaction**: `compose_tonight_snapshot_source(base_source, purpose)` is now the one composer, requiring both parts, preserving both whole across the existing `:` separator, and raising `TonightSnapshotSourceError` with reason `tonight_snapshot_source_too_long`, the observed length, the maximum, and the affected field **before any database work** — so the lane fails on a named application condition rather than on a driver truncation raised mid-transaction; `write_snapshot` re-validates as defense in depth. **Nothing truncates, abbreviates, or hashes**, and the CLI's prior `source[:40]` clip was removed because it silently rewrote provenance and could not prevent the failure anyway. **CI-002 closed**: the lane's existing tests monkeypatched the snapshot writer, so every test passed while production failed on every run — a mocked writer cannot observe a column width. A PostgreSQL integration suite now uses the real model, writer, transaction, and commit, stubbing only the MLB request; it seeds an existing row and drives the **UPDATE** production failed on, reads the value back from PostgreSQL, asserts all 41 characters survive, and proves the identical real path raises `StringDataRightTruncation` again when the live column is narrowed to 40. A separate migration suite proves the pre-revision shape rejects the value on insert and update, the upgraded shape accepts it, existing short values survive, nullability and indexes are preserved, and the downgrade refuses when a row would be truncated — in isolated PostgreSQL schemas, never SQLite. **A focused length audit of the adjacent path found no other confirmed mismatch**: `scheduled_games.source` (22/40, no composition), `intelligence_surface_snapshots.source` (30/40), `snapshot_version` (10/40), `status` (5/20), and `empty_reason` (34/60) are all within capacity, so no other column was changed. **Unchanged:** the 14:00 UTC schedule, the `github_actions_morning` source argument, `SLATE_SCHEDULE_COMMAND_TIMEOUT`, workflow permissions and concurrency, publication gates, the appearance-ledger contract and exit-code semantics, dashboard cache verification, schedule and game-status fail-closed authority, daily and postgame shadow, backfill off, and the unapproved write and authoritative modes. **No production mutation was performed during implementation**, and **PROD-001 is not closed**: the migration reaches production only through the normal reviewed deployment process, and closure requires a governed 14:00 UTC run that stores the complete value and verifies its readback | Adopted |
| D-040 | Aug 2, 2026 | **OPS-001: trusted publication success and experimental shadow activation health are now separate jobs, and neither gate was weakened to do it.** `public-sync` ended with the game-driven activation validator and its health gate, so a shadow-only defect — failed parity, missing evidence, a validator that could not run, an unsafe artifact — turned the **publication** job red. A red `public-sync` therefore meant two entirely different things: trusted synchronization failed, or publication succeeded completely and an observer failed. Because `internal-enrichment` and `static-team-story-preview` both depend on `public-sync`, the second case **skipped them too**, withholding enrichment and static page publication from data whose sync, snapshot publication, appearance-ledger proof, and dashboard verification had all succeeded. **Decision: move observation into its own job and leave publication alone.** `public-sync` retains every publication-critical responsibility — the daily and postgame runners, the 14:00 UTC morning slate refresh, both Tonight refreshes, explicit backfill, the appearance-ledger audit and artifact, and dashboard cache verification — none of them `continue-on-error`, and no shadow verdict can exit non-zero inside it. The new `shadow-activation-health` job runs `needs: public-sync` under `always()`, covering **only** daily and postgame and excluding the 14:00 UTC morning schedule, backfill, and intraday. It runs even when `public-sync` failed, because a public failure occurring after the runner wrote its summary still leaves real evidence worth validating and preserving. **It holds no production credential** (no `DATABASE_URL`, `SECRET_KEY`, `ADMIN_API_TOKEN`, `BASEBALLOS_ADMIN_API_TOKEN`, `BASEBALLOS_SYNC_URL`, and no `secrets.` reference at all), invokes no production command, writes no baseball data, publishes nothing, and never sets `GAME_DRIVEN_INGESTION_MODE` — it validates retained evidence rather than running the lane. **Evidence crosses the job boundary through a deliberate handoff** (`game-driven-shadow-handoff-<run id>`, 7-day retention) carrying the cycle summary plus safe metadata (`schema_version`, `run_id`, `repository_sha`, `cycle_kind`, `runner_exit_code`, `expected_summary_filename`, `summary_present`, `preupload_scan_safe`, `handoff_status`) and no credential, URL, exception text, or payload. **The staging rule is the safety property: nothing is uploaded from the directory the runner wrote to** — the raw summary is scanned first and copied into an empty staging directory only if it passes, so a scanner bug yields an empty handoff rather than a leaked artifact. Both handoff steps are `continue-on-error` transport only and cannot turn a green publication red; a failed handoff becomes UNPROVEN activation health in the observer instead. **One scanner and one pattern list** now govern both the pre-handoff and final scans, replacing two shell greps with two independently drifting copies; it reports a filename and a category and never the matched content, treats an unreadable file as unsafe, and quarantines rather than uploading. **The final gate passes only when all ten conditions hold** — handoff downloaded, metadata present and valid, status `ready`, pre-upload scan safe, expected summary present, cycle kind daily or postgame, runner exit code a real integer, validator exit 0, final scan safe, final upload succeeded — with the vocabulary fixed at exactly `PASS`, `FAILED`, and `UNPROVEN`. **UNPROVEN is never a skip, a warning, or a pass**, because absent evidence is the state most easily mistaken for success. `internal-enrichment` and `static-team-story-preview` each depend on `public-sync` alone and now state `needs.public-sync.result == 'success'` explicitly; neither references observer health, and no job depends on the observer. **Nothing publication-critical changed**: the appearance-ledger command, deep window, exit-code semantics, artifact, and fail-closed behaviour; dashboard cache verification with its assertions and retries; schedules, manual modes, permissions, concurrency, timeouts, production commands, source values, and secrets. Daily remains `shadow`, postgame remains `shadow`, backfill remains `off`, and automated write and authoritative modes remain unapproved. **No migration was added; the Alembic head remains `c7f1b408d93a`.** The shadow-failure dependency behaviour is proven by deterministic CI tests rather than by manufacturing a production failure, and roughly one week of scheduled observation is required before the operational red-signal quality is declared fully proven. **CI-003 remains deferred** | Adopted |
| D-041 | Aug 3, 2026 | **A manual, exactly-one-game no-op write qualification exists; it proves the write-capable path can be entered with zero baseball-data mutation, and it authorizes nothing further.** The game-driven lane has completed shadow qualification, but every proof so far was obtained with writes disabled. Entering `write` had never been exercised in production at all, so the step from a proven projection to a proven write was untested. **Decision: qualify the write-capable path on a single completed game whose rows already match, before any real correction.** The qualification is manual-only: one workflow with `workflow_dispatch` and nothing else — no schedule, push, pull request, `workflow_run`, or repository dispatch — requiring three exact inputs (one positive-integer `game_pk`, a full 40-character `expected_head_sha` that must equal the resolved commit, and the confirmation `QUALIFY_NOOP_GAME_<game_pk>`), restricted to `refs/heads/main` and to the repository owner, and sharing the `baseballos-sync` concurrency lane with `cancel-in-progress: false` so it can never race or be killed mid-transaction. Every gate is re-validated inside the script, which trusts none of them. **No second writer was created**: the qualification runs `run_game_driven_ingestion` twice — `shadow` exclusive to the requested game to obtain the reviewed reconciliation-plan fingerprint, then `write` exclusive and authorized by that fingerprint — so the canonical planner, canonical writer, D-009 identity governance, source-revision logic, realization validator, and production writer guard are all reused unchanged. Drift is caught by the lane's own `_authorize_reviewed_plan`, which re-fetches and re-plans immediately before the first mutation and refuses on a moved source revision or plan; it is not re-implemented. **The write phase is never entered on a plan that proposes work** — any insert, update, delete, block, canonical-outs correction, appearance-team mutation, identity creation, reactivation, metadata change, provenance write, or unrecognized action refuses first. **The no-op contract is deliberately split, because the literal one could not be honestly met.** Measured against the canonical lane, an exclusive write over an already-matching game writes zero GameLog, pitcher, appearance-team, correction-provenance, and dead-letter rows — and still records `work_items_updated 1`, `work_items_completed 1`, `checkpoints_advanced 1`, `commits_performed 1`, because `_process_one_game` claims and completes the lane's own work item whenever writes are enabled, independently of whether the plan mutates anything. PASS therefore requires every **baseball-data** counter to be zero and enforces that strictly, while the **lane completion ledger** is reported with its real non-zero values and explicitly labelled as not baseball data. Neither zeroing those counters nor making the ledger conditional was acceptable: the first would falsify the artifact, the second would change canonical completion and resume semantics to make a qualification easier. **PASS additionally requires** exact one-game requested and planned scope, proven finality via the canonical planner, an available and unchanged source revision, an available and unchanged plan fingerprint, every planned row already matching, successful pre- and post-execution readback, identical before/after canonical state digests over the governed field vocabulary (provenance and derived decimal companions excluded per D-008, so a representation difference can never read as a change), a realization proof with zero divergent, missing, duplicate, and unresolved rows, and an evidence artifact that was built, scanned by the single shared forbidden-content scanner, and uploaded. **`FAILED` and `UNPROVEN` are both non-zero and `UNPROVEN` is never softened into `PASS`**; a fetch count of two is not a scope violation, because an authorized exclusive write legitimately re-fetches the same single game for drift re-validation. **A fingerprint remains evidence and never becomes reusable write authorization.** This package creates machinery only: it performs no production execution, dispatches no workflow, mutates no production row, and adds no migration — the Alembic head remains `c7f1b408d93a`. Daily and postgame remain `shadow`, backfill remains `off`, publication authority is unchanged, the legacy sync writer remains production-authoritative, and automated write and authoritative modes both remain unapproved. The first real qualification run requires separate explicit operator approval, and a genuine mutation will require its own separately reviewed package | **Review correction (same package):** six production-safety blockers were found in the first patch and fixed before merge. (1) Workflow inputs were interpolated into `run:` scripts as `${{ inputs.* }}`; because GitHub substitutes expressions before bash parses them, a crafted operator note could have executed shell commands in the step holding production credentials, and the Python-side sanitiser ran far too late to help. Every user-controlled value now crosses the shell boundary through step-level `env:` only and is read as a quoted variable; tests execute the real preflight with hostile input and assert a canary file never appears. (2) The permitted lane-ledger movement is now governed rather than merely reported: an existing durable work item is required (a first qualification does not create lane state), the exact measured delta is enforced with exact integers rather than `>= 1`, every changed work-item field must fall inside the measured permitted set, and every unrelated work item and checkpoint row is fingerprinted before and after under the writer guard. (3) Plan-fingerprint equality is now positive proof — an absent authorized fingerprint is UNPROVEN and an unequal one is FAILED, neither inferred from a lane status code. (4) Source-revision equality is likewise positive for BOTH phases: exactly one non-null revision for exactly the requested game on each side, with absence UNPROVEN rather than silently matched. (5) The before/after baseball-state digest now covers the complete canonical vocabulary including `GAME_METADATA_FIELDS`, still excluding provenance and the derived decimal companion; PostgreSQL independently enforces companion/authority agreement via `ck_game_logs_innings_pitched_matches_outs`. (6) Writer-guard release is reported from what happened — the evidence document is built only after the release attempt, acquisition/attempt/success are tracked separately, and a failed or unattempted release is UNPROVEN instead of a hardcoded true | Adopted |

## 22. Open Decisions

| ID | Decision required | Gate | Current default |
|---|---|---|---|
| O-001 | **Resolved Jul 29, 2026 by D-021** - current active-pen performance family contract and public ownership | Closed | Contract established; Team Board is the canonical public home; M-001 remains unimplemented and non-public |
| O-002 | Current-versus-shared comparison contract | Trusted comparability and public UX | Historical page remains frozen only |
| O-003 | Canonical server renderer technology/storage | Artifact contract + hosting cost/performance | Transitional browser renderer only |
| O-004 | Public leverage calculation/table | Complete source and reproducible method | Legacy/partial claims remain bounded |
| O-005 | Routed team URL shape | Product route/SEO plan | Current team view remains destination |
| O-006 | Whether account/sign-in remains after Follow My Team review | Demonstrated retention value | Keep internal auth substrate; no broad account push |

## 23. Founder Operating System

Weekly review records current main commit, active objective, branch/blocker, merged work, production evidence, which risk changed, next three approved items, deferred items, content sustainability, and whether work began on a lower priority.

Branch names identify the user/operator who notices the work. Examples:

- `trust/official-starter-authority`
- `team-fans/current-pen-era-evidence`
- `creators/canonical-share-renderer`
- `operators/artifact-refusal-diagnostics`

Never work directly on `main`.

Founder principles:

1. Every feature must justify its hours.
2. No feature without a user problem.
3. Trust before growth; growth before monetization.
4. Season is scheduling constraint, not permission to lower quality.
5. Never sacrifice explainability for impressiveness.
6. Never build merely because a competitor did.
7. Compression may reduce ceremony, not trust.
8. Two focused hours that ship beat an exhausted six-hour detour.
9. Deletion and deferral are progress.
10. Write durable decisions once.
11. Life comes first; the system should survive absence.
12. One active objective is the default.

## 24. Completion Log

Append one row for every material completed item.

| Date | Phase | Item | Branch / PR / commit | Production evidence | Notes |
|---|---|---|---|---|---|
| Jul 29, 2026 | Phase 0 | Canonical innings authority hardened | PR #556 / `c4a0b3e4...` | Regression fixtures; no false repair from decimal representation | Decimal innings no longer operate independently of recorded outs |
| Jul 29, 2026 | Phase 0 | Six-document canonical library established | `docs/canonical-operating-library` | Document render/QA and GitHub PR | Replaces competing master documents as authority |
| Jul 29, 2026 | Phase 0 | Governed 675-action official pitching-line repair applied | PR #540 / execution ledger id 1 | Fingerprint `3ee2ea06...`; 70 identity / 445 insert / 160 update / 675 total; season 2026 as of 2026-07-25 | Atomic, fingerprint-locked, single completed execution |
| Jul 29, 2026 | Phase 0 | Independent read-only closeout verification | PR #555 / `b5e88bb...` | `pass` / exit 0; all five governed checks present, executed, passed; zero writes | Verifier is separate from the apply it verifies |
| Jul 29, 2026 | Phase 0 | Derived-innings planner semantics corrected | PR #556 | Integer outs are the sole workload authority; derived float never proposed alone | Removed a representation difference presented as a repair action |
| Jul 29, 2026 | Phase 0 | Targeted Matt Festa apply capability built and dispatched once | PR #557 / `b5e88bb...` | Zero writes, no transaction, no ledger row, zero planned actions | Became unnecessary before dispatch; closed permanently, see D-019 |
| Jul 29, 2026 | Phase 0 | **Foundation 3A / Phase 0 formally closed** | `operators/foundation-3a-closeout` | Section 3A closeout evidence at `b5e88bb...` | Phase 1 Evidence Completeness becomes the sole active objective |
| Jul 29, 2026 | Phase 1 | Current Active-Pen Performance Contract established; O-001 resolved | `team-fans/current-active-pen-performance-contract` | Documentation and governance only; no code, migration, workflow, production action, or public surface changed; all blocked gates remain blocked | Governance work package. D-021 and D-022 adopted; M-001 reserved as contract-pending and non-public |
| Jul 30, 2026 | Phase 1 | Reusable Current Active-Pen Performance framework merged; M-001 registered | PR #563 / `f201710` | Three new backend files, nothing modified; unwired with no route, payload, or surface consumer; every gate blocked; `minimum_sample` left explicitly `None` so the metric computes and refuses to publish | Implementation of the framework only. No metric parameter was invented at implementation time |
| Jul 30, 2026 | Phase 1 | M-001 Current Active-Pen ERA specified | `governance/m001-current-active-pen-era-specification` | Documentation and governance only; no code, test, route, payload, migration, workflow, production action, or public surface changed; all blocked gates remain blocked | Governance work package. D-023 through D-030 adopted: minimum sample, denominator authority, rounding, below-sample wording, no-usage rule, public name, evidence contract, and inheritance. M-001 remains non-public |
| Jul 31, 2026 | Foundation 3C | **109-game governed ingestion bootstrap completed** | PRs #572-#579 / `81271e0...` | R6 workflow run `30664706174`; fingerprint `40659a40...9343`; 99 games written, 865 rows unchanged, 0 mutations on every target; completeness 10/99 -> 109/0; 946 appearance rows reconciled; publication complete; immediate replay reproduced the approved fingerprint with zero drift | Only governed ingestion control state changed. No baseball-data row changed. Lane remains off; authoritative mode unapproved. See D-031 |
| Jul 31, 2026 | Foundation 3C | Stage E1: rollout workflows retired, closeout verification added | `operators/foundation-3c-stage-e-closeout` | Repository change only; the Stage E production verification has not been executed | Seven temporary Foundation 3C workflows removed; one read-only Stage E workflow added; permanent regression coverage consolidated; historical record at `docs/archive/2026-07/FOUNDATION_3C_BOOTSTRAP_CLOSEOUT.md` |
| Jul 31, 2026 | Foundation 3C | **Stage E1 verified the bootstrap in production** | `bd7e610` / run `30673146173` | PASS: 109/0, 946 reconciled rows, 109-game replay with 946 unchanged and 323 ignored decimal differences, zero mutations, zero drift, zero governed dead letters, global count unchanged at 1,389 | Read-only. No database write. Final fingerprint `9f0fe983...e2c6` is historical evidence only |
| Jul 31, 2026 | Foundation 3C | **Stage E2: rollout closed** | `chore/foundation-3c-e2-closeout` | Repository closure only; no production operation, no configuration change, no migration | Stage E workflow and six temporary support files removed; permanent runtime assertions relocated into the permanent ingestion suite; no Foundation 3C rollout workflow remains. Lane off; authoritative unapproved. See D-032 |
| Aug 1, 2026 | Activation | **Automated shadow activation halted at baseline; postgame integration point built** | `ops/game-driven-shadow-activation` | Repository change only; no production operation, no workflow change, no configuration change, no migration | The lane had no `run_postgame_refresh` integration point, so shadow could not have been activated honestly on that cycle. One service call per cycle; postgame reads after its own writer; `write` and `authoritative` refused on the postgame cycle for lack of conflict prevention; bounded postgame lane budget. Lane still off; write and authoritative both unapproved. See D-033 |
| Aug 1, 2026 | Activation | **Automated game-driven shadow activated for daily and postgame** | `ops/automated-shadow-activation` | Repository change only; no production execution during implementation, no Render/Vercel change, no secret or variable change, no migration; shadow begins with the first scheduled cycle after merge | Shadow on the two runner steps only; backfill explicitly off. Daily judged by a post-writer realization proof, postgame by zero-projection convergence. Projected actions distinguished from actual `execution_effects`. Durable `--output` summaries, activation validator, scanned artifacts, health gate after upload. Write and authoritative both remain unapproved. See D-034 |
| Aug 1, 2026 | Activation | **First postgame shadow cycle failed safely; postgame observer disabled pending scope repair** | `fix/postgame-shadow-scope` | Production untouched: postgame sync success, publication verified (snapshot 324), zero shadow writes. Activation FAILED on scope: 112 planned / 98 completed / 14 remaining in a 150s allocation | Exact-cycle postgame scope, safe difference diagnostics, and distinct budget-cap/allocation reporting added. Postgame shadow off; daily shadow on; backfill off. Game 824488 diagnosed to a class, not a cause — no repair guessed. See D-035 |
| Aug 1, 2026 | Activation | **Postgame shadow reactivated on exact-cycle scope** | `ops/postgame-shadow-reactivation` | Repository change only; no production execution during implementation, no Render/Vercel/secret/variable change, no migration; postgame observation restarts with the first scheduled cycle after merge | Postgame runner back to shadow with activation handling restored for both cycles. Validator now enforces the exact scope itself and refuses any nonzero projection it cannot attribute to a safe diagnostic. Daily untouched; backfill off; cap and share unraised. Write and authoritative both remain unapproved. See D-036 |
| Aug 1, 2026 | Trust | **GameLog `balls` authority audited; unresolved, no repair guessed** | `fix/gamelog-balls-authority` | Repository change only; no production execution, no production read (no access), no MLB call, no Render/Vercel/secret change, no migration; the target row was not touched | Mechanism proven from code: comparability follows the source shape, so a field one endpoint omits is never corrected by the lane reading it. Authority unproven without live payloads. No writer, vocabulary, or contract version changed. Added `uncomparable_fields` diagnostics and a read-only production audit tool. Shadow failure intentionally left active. See D-037 |
| Aug 1, 2026 | Trust | **Box-score fallback added for the uncorrectable GameLog `balls` field** | `fix/boxscore-balls-fallback` | Repository change only; no production execution, no production correction, no MLB call during implementation, no Render/Vercel/secret/variable change, no migration; the impact planner performs zero writes and must be run and reviewed before any correction | Authority resolved as Outcome A: the completed-game box score is canonical for `balls` and the split does not carry the key, so the correction-horizon writer could never realize it. Split stays primary; the box score supplies exactly one approved field, validated against `balls + strikes == numberOfPitches` and never derived. Same values builder, same planner, same writer — no second comparator. Named refusals, bounded fetch cost on the shared cache, fallback-specific provenance, and unconditional run reporting. Shadow modes, budgets, and mode-off rollback unchanged. See D-038 |
| Aug 2, 2026 | Reliability | **Morning Tonight snapshot source persistence repaired** | `fix/tonight-snapshot-source-width` | Repository change only; no production execution, no production migration, no workflow dispatch, no manual snapshot correction, no Render/Vercel/secret/variable change; migration reaches production through normal reviewed deployment | PROD-001 root cause: the 14:00 UTC lane acquired its schedule successfully (HTTP 200) and failed persisting Tonight, because `github_actions_morning:schedule_coherence` is 41 characters against a VARCHAR(40) column. Widened to VARCHAR(128) via `c7f1b408d93a`, one head, downgrade refuses rather than truncating. One shared width constant, one validated composer failing before commit, no truncation or abbreviation. CI-002 closed with a real PostgreSQL writer regression on the failing UPDATE path. Production validation still required. See D-039 |
| Aug 2, 2026 | Operations | **Publication success separated from shadow activation health** | `fix/separate-shadow-activation-health` | Repository change only; no workflow dispatch, no production execution, no database write, no Render/Vercel/secret/variable change, no migration, no mode change | A shadow-only failure used to fail `public-sync` and skip internal enrichment and static preview even when publication and every proof succeeded. Observation now lives in `shadow-activation-health`: no credentials, no production command, `always()` on daily and postgame only. Evidence crosses via a scanned, staged handoff artifact; one shared scanner governs both scans; the final gate's ten conditions are executed in tests rather than merely described. Ledger, dashboard verification, schedules, timeouts, and all three modes unchanged. See D-040 |
| Aug 3, 2026 | Activation | **Manual exact-scope no-op write qualification built (not executed)** | `feat/manual-noop-write-qualification` | Repository change only; no workflow dispatch, no production execution, no production row mutated, no Render/Vercel/secret/variable change, no migration, no mode change | Manual-only workflow (`workflow_dispatch` only), exactly one `game_pk`, exact SHA and confirmation, main-only, owner-only, sharing the sync concurrency lane. Reuses `run_game_driven_ingestion` for both the shadow and write phases — no second writer, no second comparator. Refuses before the writer on any proposed mutation, source-revision drift, or plan drift. PASS requires zero baseball-data writes, identical before/after digests, realization all-matching, and a scanned uploaded artifact; the lane's own completion ledger is reported honestly as non-zero. Daily/postgame shadow, backfill off, write and authoritative unapproved. See D-041 |

## 25. Phase Exit Record

| Phase | Status | Exit evidence required |
|---|---|---|
| Phase 0 - Canonical Trust Closeout | **Complete** (Jul 29, 2026 at `b5e88bb...`) | Met: independent read-only closeout `pass`/exit 0, every governed check present/executed/passed, exact local and official reconciliation across 30 teams, regression coverage merged. Evidence in Section 3A |
| Phase 1 - Evidence Completeness | **Active** - first item fully specified, framework merged and unwired, no public surface | Public evidence contracts complete and inspected. The family contract is recorded (D-021), the framework is merged (PR #563), and the M-001 definition is approved (D-023 through D-030). Wiring the approved parameters and a public surface remains outstanding |
| Phase 2 - Portable Intelligence | Foundation complete; final distribution not started | Canonical renderer, actions, metadata, analytics, external smoke |
| Phase 3 - Daily Habit | Not started | Trusted change/consequence loop and quiet-day behavior |
| Phase 4 - Offseason Intelligence Depth | Not started | At least one major evidence advantage beyond workload/roster |
| Phase 5 - Opening Day 2027 | Not started | Complete daily product and relaunch proof |
| Phase 6 - Growth and Validation | Not started | Measured path or explicit defer decision |

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Established the only canonical execution roadmap, current capability assessment, active objective, phased sequence, dependency map, success metrics, risks, backlog, founder operating rules, and consolidated Decision Ledger. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Closed Foundation 3A / Phase 0 Canonical Trust Closeout and recorded its terminal production evidence; recorded the Matt Festa targeted apply as closed and non-retriable; opened Foundation 3B / Phase 1 Evidence Completeness as the sole active objective with Current Active-Pen ERA and Performance Context as the first scoped item; added decisions D-018 through D-020 and the Phase 0 completion-log entries. |
| 1.2 | July 29, 2026 | Nickolis Kacludis | Resolved O-001 with D-021, the Current Active-Pen Performance Contract, and recorded the metric-family / metric-registry distinction as D-022. Updated the active objective from contract unresolved to contract established with the M-001 metric definition next; Current Active-Pen ERA remains uncompleted, unimplemented, and non-public. Foundation 3B / Phase 1 remains the sole active objective and is not complete. Refreshed the repository basis to the verified baseline and logged this governance work only. |
| 1.3 | July 30, 2026 | Nickolis Kacludis | Specified M-001 Current Active-Pen ERA through decisions D-023 to D-030: the derived 108-recorded-out minimum sample stated in the denominator's unit, integer-outs denominator authority, family rounding and precision policy, the approved below-sample read Not Enough Innings Yet, the no-usage call-up membership rule with two group counts, the public name Active Bullpen ERA, the filled four-level evidence contract, and the inheritance split for future metrics. Updated the active objective, definition of done, Phase 1 scope, completion log, and phase exit record. Governance only; M-001 remains unimplemented and non-public with every gate blocked. |
| 1.4 | July 31, 2026 | Nickolis Kacludis | Recorded the completion of the Foundation 3C 109-game governed ingestion bootstrap and added D-031; confirmed D-008, D-009, and parity contract version 4 as permanent; recorded that no decision was taken to enable automated or authoritative mode; added the R6 production and Stage E1 completion-log entries. |
| 1.5 | July 31, 2026 | Nickolis Kacludis | Recorded the Stage E1 production verification and the Stage E2 rollout closure as D-032; confirmed no Foundation 3C rollout workflow remains and that the final fingerprints are historical evidence rather than authorization; recorded that no shadow, write, or authoritative activation decision was taken and that automated shadow activation is the next decision. |
| 1.6 | August 1, 2026 | Nickolis Kacludis | Recorded D-033: automated shadow activation was halted at its baseline gate because the game-driven lane had no postgame integration point, and the missing integration point was built instead. Fixed one service call per cycle, postgame reading after its own writer rather than ahead of it, refusal of writing modes on the postgame cycle for lack of conflict prevention, and a bounded postgame lane budget. No mode, workflow, schedule, or publication authority changed; automated write and authoritative modes both remain unapproved. |
| 1.7 | August 1, 2026 | Nickolis Kacludis | Recorded D-034: automated game-driven ingestion shadow activation approved for the daily and postgame production cycles, with backfill explicitly off. Established the cycle-semantics correction as governance — daily projects before its writer and is judged by a post-writer realization proof, postgame projects after its writer and must converge to zero — and the separation of projected reconciliation actions from actual execution effects. Recorded the activation artifact contract, the failure-isolation ordering, the rollback contract, and the 24-48 hour observation gate. Current sync and publication remain authoritative; automated write and authoritative modes both remain unapproved. |
| 1.8 | August 1, 2026 | Nickolis Kacludis | Recorded D-035: the first automated postgame shadow cycle failed safely on scope while the production path completed and published normally with zero shadow writes. Recorded the exact-cycle postgame scope contract, the safe difference diagnostics, the separated budget cap and effective allocation, and the temporary postgame rollback with daily shadow retained. Recorded that game 824488 is diagnosed to a defect class but not to a proven cause, and that no repair was guessed. Automated write and authoritative modes both remain unapproved. |
| 1.9 | August 1, 2026 | Nickolis Kacludis | Recorded D-036: the exact-cycle scope repair accepted and automated postgame shadow reactivated, with activation handling restored for both eligible cycles. Recorded that the validator now enforces the postgame scope itself — source, determinism, exact match, missing and unexpected games, fan-out, cycle accounting, and named exclusions — and that any nonzero projection must be attributable to a safe per-row diagnostic carrying no raw values. Recorded that postgame observation restarts from reactivation, that neither the budget cap nor the lane share was raised, and that automated write and authoritative modes both remain unapproved. |
| 2.0 | August 1, 2026 | Nickolis Kacludis | Recorded D-037: the GameLog `balls` field-authority audit. Established that comparability follows the source shape — an optional statistic is compared only when the source carries its key with a non-null value — and that the postgame writer never revisits a completed game, together leaving a field uncorrectable while every lane reports no difference. Recorded that authority remains unproven without live source payloads and production access, that no writer, correction vocabulary, or contract version was changed, and that the shadow failure was deliberately left active. Recorded the `uncomparable_fields` diagnostic and the read-only field-authority audit tool. Automated write and authoritative modes remain unapproved. |
| 2.1 | August 1, 2026 | Nickolis Kacludis | Recorded D-038: the GameLog `balls` authority resolved as Outcome A from the production audit — the completed-game box score is canonical and the player game-log split does not carry the key, leaving the field uncorrectable by the only lane that revisits an appearance inside the correction horizon. Recorded the declared `player_split_primary_with_boxscore_fallback` authority contract, its single approved field, its validation-not-derivation rule, its named refusal vocabulary, and that the enriched source flows through the existing values builder, planner, and writer with no second comparator. Recorded fallback-specific correction provenance, unconditional run reporting, the bounded shared-cache fetch cost with the budget unraised, and the read-only impact planner that must enumerate and be reviewed before any production correction. No production data was changed; shadow modes, backfill, and the unapproved write and authoritative modes are unchanged. |
| 2.2 | August 2, 2026 | Nickolis Kacludis | Recorded D-039: PROD-001, the persistent 14:00 UTC schedule/Tonight failure, root-caused to column capacity rather than to MLB, secrets, timeouts, or any trust gate — the lane acquired its schedule successfully and failed persisting a 41-character provenance value into a VARCHAR(40) column, on the UPDATE of an existing snapshot row. Recorded that the defect was structural, since the service default composed to the same length. Recorded migration `c7f1b408d93a` widening the column to VARCHAR(128) with a downgrade that refuses rather than truncating, the single shared width constant consumed by the model and both validators, and construction-time validation that fails before any database work with a named reason. Recorded CI-002 closed by a real PostgreSQL writer regression exercising the failing update path with no mocked writer, plus a migration regression proving the old schema rejects and the new schema accepts the same value. Recorded that no provenance was truncated, abbreviated, or hashed, that no workflow schedule, timeout, gate, ledger, or shadow mode changed, and that PROD-001 remains open until a governed production run proves it. |
| 2.3 | August 2, 2026 | Nickolis Kacludis | Recorded D-040: OPS-001, separating trusted publication success from experimental shadow activation health. Recorded that the activation gate inside `public-sync` made one red signal mean two different things and skipped `internal-enrichment` and `static-team-story-preview` on shadow-only failures. Recorded the new credential-free `shadow-activation-health` job, its `always()` daily/postgame-only condition, the scanned staging handoff that prevents an unscanned raw artifact from leaving the runner, the single shared forbidden-content scanner replacing two drifting copies, and the ten-condition final gate whose PASS/FAILED/UNPROVEN vocabulary treats absent evidence as failure rather than as a skip. Recorded that both downstream jobs depend on `public-sync` alone and state that requirement explicitly, that no publication-critical gate, schedule, timeout, command, or mode changed, that no migration was added and the Alembic head remains `c7f1b408d93a`, and that roughly one week of scheduled observation is required before the operational red-signal quality is declared proven. |
| 2.4 | August 3, 2026 | Nickolis Kacludis | Recorded D-041: the manual exact-scope no-op write qualification. Recorded that the lane's shadow qualification never exercised entering `write`, and that the qualification closes that gap on a single already-matching completed game before any real correction. Recorded the manual-only trigger, the three exact inputs, the main-only and owner-only restrictions, the shared sync concurrency lane, and the re-validation of every gate inside the script. Recorded that no second writer or comparator was created — both phases run `run_game_driven_ingestion`, and drift is caught by the lane's own reviewed-plan authorization. Recorded the split no-op contract and why the literal contract could not be met honestly: an exclusive write over an already-matching game mutates no baseball row but unavoidably advances the lane's own work item, checkpoint, and commit, so PASS enforces zero baseball-data writes strictly while the completion ledger is reported with its real non-zero values rather than zeroed or suppressed. Recorded the full PASS requirement set, the non-zero `FAILED` and `UNPROVEN` exits, the exclusion of provenance and derived decimal companions from the state digest under D-008, and that a fingerprint remains evidence rather than reusable authorization. Recorded that this package builds machinery only: no production execution, no dispatch, no row mutated, no migration, Alembic head unchanged at `c7f1b408d93a`, daily and postgame still shadow, backfill off, legacy writer still authoritative, and automated write and authoritative modes both still unapproved pending separate explicit approval. Recorded the pre-merge review correction of six production-safety blockers: the workflow shell-injection boundary, governed lane-ledger shape and scope with a required pre-existing work item and exact measured delta, positive fingerprint proof, positive two-phase source-revision proof, the completed baseball-state digest vocabulary, and honest writer-guard release reporting. |
