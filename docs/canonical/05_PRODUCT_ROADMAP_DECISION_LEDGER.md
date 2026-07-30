# BaseballOS Product Roadmap & Decision Ledger

| Field | Value |
|---|---|
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 1.2 |
| Effective date | July 29, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `ec636f26153f97231372aba13c54161c643abfc7` |
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

Open decision **O-001** is **resolved** by D-021. What remains open is the first metric definition: **M-001 Current Active-Pen ERA** is reserved as contract-pending and is not published anywhere public. Its exact formula approval, minimum sample, and denominator are the next governed work package.

### Definition of done

- [x] Active-group, sample, date, evidence, and limitation contracts are defined and recorded.
- [x] O-001 is resolved by an explicit Decision Ledger entry.
- [ ] M-001 Current Active-Pen ERA has an approved formula, minimum sample, and denominator.
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

**First scoped item:** Current Active-Pen ERA and Performance Context. The family contract is established (D-021); implementation has not started. The next step is the M-001 metric definition - formula, minimum sample, and denominator - before any public surfacing.

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

## 25. Phase Exit Record

| Phase | Status | Exit evidence required |
|---|---|---|
| Phase 0 - Canonical Trust Closeout | **Complete** (Jul 29, 2026 at `b5e88bb...`) | Met: independent read-only closeout `pass`/exit 0, every governed check present/executed/passed, exact local and official reconciliation across 30 teams, regression coverage merged. Evidence in Section 3A |
| Phase 1 - Evidence Completeness | **Active** - first item's contract established, implementation not started | Public evidence contracts complete and inspected. The Current Active-Pen Performance Contract is recorded (D-021); the M-001 metric definition and its implementation remain outstanding |
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
