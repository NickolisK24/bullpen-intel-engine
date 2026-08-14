BASEBALLOS  CANONICAL DOCUMENT LIBRARY

05

Product Roadmap & Decision Ledger

Condensed Canonical Edition · Visual Audit Integrated

One active objective. One canonical roadmap. Every durable decision recorded.

VERSION 4.0  ·  DOCUMENT-AUTHORITY CURRENT-STATE EDITION

Owner: Nickolis Kacludis

Effective August 14, 2026

# Contents

This edition keeps the Product Roadmap & Decision Ledger as the sole canonical execution authority and integrates only the important, non-duplicative findings from the August 5 visual audit.

01  Document Control

02  Part I - Executive State

03  Part II - Integrated Priority Matrix

04  Part III - Phased Roadmap

05  Part IV - Dependencies and Success Metrics

06  Part V - Risks and Controls

07  Part VI - Backlog and Stop Conditions

08  Part VII - Decision Ledger

09  Part VIII - Founder Operating System

10  Appendix A - Completion Log

11  Appendix B - Phase Exit Record

12  Appendix C - Source Basis

13  Appendix D - Revision History

# Document Control

| Field | Value |
| --- | --- |
| Document | BaseballOS Product Roadmap and Decision Ledger |
| Status | Canonical - current platform state, priority, sequence, decision, risk, and completion authority |
| Version | 4.0 |
| Effective date | August 14, 2026 |
| Owner | Nickolis Kacludis |
| Repository basis | Production/main: NickolisK24/bullpen-intel-engine main at b2f0e90718321857f3f631cda3c81c1175af85de after PR #659. No in-flight implementation branch. |
| Decision basis | Decision Ledger through D-053; Version 4.0 reconciles current execution state and records the D-013 scope amendment required by D-053, without adding, weakening, or renumbering a durable authority decision |
| Audit basis | Production closeout for #595, #591, #600, #594, and VOC-001 (#638); DEP-001 (#601) complete and verified on main by CI run 31729458591; CI-003 (#598) gated publication commit `2e83fa0` on main from scheduled run 31794183367; H-5 through H-12 documentation and public-surface closeouts through PR #659 |
| Supersedes | Version 3.9 current-state wording while preserving all durable prior decisions and completion evidence |
| Update rule | Update after a priority change, material merge, phase exit, production incident, authority decision, risk change, or false current-state statement |
| Review cadence | Weekly founder review; immediate update after a material production or product decision |

| INTEGRATION RULE | Current-state reconciliation only. VOC-001 (#638) and DEP-001 (#601) remain complete. CI-003 (#598) is still the remaining ordered package: this edition records that the gated, tree-exact, machine-attributed generated commit the previous edition said did not exist now does, and that the read-only deployment verification the same requirement names has still not been taken. That is evidence recording, not adjudication — the requirement stands exactly as written and #598 stays open. This edition adds no Decision Ledger ID and changes no authority, publication, or write posture; it records the D-013 scope amendment D-053 already required in practice, and introduces a decision status vocabulary that describes existing entries without altering any of them. |
| --- | --- |

# Part I - Executive State

## 1. Current Product Position

BaseballOS is a live public MLB bullpen-intelligence platform with a mature trust foundation, a defensible canonical appearance record, governed publication gates, immutable historical claims, and production evidence strong enough to close the game-driven ingestion authority-qualification phase without granting production write authority.

The Public Credibility Pass is closed. Raw public scores are contained, governed Why copy is backend-owned, `/bullpen` has one contextual H1 per view, routed team previews are production-verified, and public vocabulary/glossary ownership is production-verified. Attention has moved from public credibility to delivery reliability and supply-chain hygiene: dependency risk on the production request path is remediated and continuously audited, and the remaining ordered package is the generated-content publication gate.

| CURRENT VERDICT | The Public Credibility Pass is closed: #595, #591, #600, #594, and #638 are all complete and production-verified. Dependency risk (#601) is remediated on main and now has a standing CI control, with one time-boxed frontend acceptance expiring 2026-11-13. The remaining ordered package is CI-003 (#598): the naturally authorized scheduled generated-content publication has now occurred and is on main as commit `2e83fa0`, and the recorded closeout still requires read-only deployment proof. |
| --- | --- |

## 2. Current Repository and Authority State

| Area | Current state | Meaning |
| --- | --- | --- |
| Repository main | b2f0e90718321857f3f631cda3c81c1175af85de | Current baseline after PR #659. The August 13 baseline was e3ad8bd after PR #647, verified by CI run 31729458591. |
| In-flight branch | None | No open implementation branch carries product state. |
| Daily game-driven lane | Shadow | Observation only; no automated baseball-data writes. |
| Postgame game-driven lane | Shadow | Exact-cycle observation after the legacy postgame writer. |
| Backfill lane | Off | No automatic backfill authority. |
| Production writer | Legacy sync/postgame path | Remains authoritative for baseball-data mutation. |
| Automated write mode | Unapproved | Manual qualification machinery grants no broader authority. |
| Game-driven publication authority | Unapproved | Publication authority has not transferred. |
| PROD-001 (#592) | Complete | Scheduled production proof retained. |
| OPS-001 (#593) | Complete | Scheduled signal-separation evidence closed August 10. |
| OPS-002 (#620) | Complete | Runtime mitigation production-proven; permanent work reduction remains separate. |
| UX-001 (#590) | Complete | Canonical Team State delivery proven in production. |
| SEC-001 (#595) | Complete | Public score/internal fatigue fields contained and production-verified. |
| FE-001 (#591) | Complete | Backend-owned Why copy production-verified; frontend no longer rewrites or drops it. |
| DIST-003 (#594) | Complete | Routed team previews production-verified August 11, 2026 from trusted snapshot 393; issue closed. See Appendix A. |
| UX-002 (#600) | Complete | One contextual H1 per `/bullpen` view; keyboard, accessibility-tree, and mobile checks passed. |
| VOC-001 (#638) | Complete | Public vocabulary/glossary ownership production-verified August 12, 2026 from trusted snapshot 398; issue closed. |
| DEP-001 (#601) | Complete | Backend runtime audit clean; frontend production advisories reduced to three reviewed, time-boxed React Router acceptances expiring 2026-11-13; standing CI dependency gate added. Issue closed August 13, 2026. |
| CI-003 (#598) | Active; publication evidence recorded, deployment proof outstanding | Repository implementation and the PR #642 result-transport repair are on main. Scheduled run 31794183367 (attempt 1, August 14) produced gated publication commit `2e83fa0` under `BaseballOS Automation`, Validated-Tree `1c9d7dc`, Snapshot-ID 411, data through August 13. The recorded closeout still requires read-only deployment verification. |

## 3. Active Objective

| ACTIVE OBJECTIVE | CI-003 (#598) — generated-content publication closeout |
| --- | --- |

VOC-001 (#638) closed on production proof August 12, 2026, which exits the
Public Credibility Pass. DEP-001 (#601) closed August 13, 2026. CI-003 (#598) is
therefore the next package in the previously approved order, unchanged.

Current state, recorded without adjudicating it:

- The generated-content publication gate (D-053) and the PR #642 result-transport repair are both on main.
- The GitHub issue #598 was closed August 12, 2026 through its linked pull request #641.
- The first scheduled exercise, run 31693516516 on August 13, refused correctly rather than publishing. The repair merged after that run.
- **The gated publication has since occurred.** Scheduled run 31794183367 — `schedule` event, attempt 1, concluded success — produced commit `2e83fa0` on main: `docs: publish generated team preview pages`, authored and committed by `BaseballOS Automation <baseballoshq@gmail.com>`, carrying Workflow-Run 31794183367, Workflow-Run-Attempt 1, Source-SHA `71e0b89`, Validated-Tree `1c9d7dc`, Snapshot-ID 411, and Data-Through 2026-08-13. It is the only machine-authored commit in the repository's history. Version 3.9 recorded that no such commit existed; that statement was true when written and is false now, which is why this edition exists.
- **The remaining closeout evidence is the read-only deployment verification**, which has not been taken.

Remaining work to close the objective:

- Take read-only deployment verification of the published previews from commit `2e83fa0`. Take it; do not force, rerun, or manually dispatch anything to manufacture it.
- Reconcile the issue's recorded state against that evidence.
- Do not treat the closed issue as the proof; the closed issue and the recorded evidence gate are different claims. The publication commit satisfies one half of the recorded requirement, not the whole of it.

Nothing in this edition changes the generated-content publication contract, its
workflow, D-053, or any authority it governs.

## 3A. Preceding Package Outcomes

VOC-001 (#638) outcome, recorded at roadmap altitude only — the Product Experience Standard v1.4 and the Bullpen Intelligence Standard v1.3 own the detail:

- one semantic owner per public vocabulary family, with backend-governed labels rendered verbatim;
- Team State unchanged: Fresh / Stretched / Vulnerable;
- Arm Availability unchanged: Available / On Watch / Limited / Unavailable;
- Pitcher Role: Trusted Arm / Setup Arm / Coverage Arm / Middle Relief Arm / Role Unclear;
- Pitcher Current Read: Clean Option / Watch Arm / Limited Rest / Unavailable / Limited Read;
- Read Confidence: High / Medium / Low / Unavailable;
- board group labels clarified as workload-group headings over unchanged engine statuses;
- supporting-read vocabulary reconciled, and supporting reads never constitute a Team State;
- `Trusted Arms` retired as a team-level concept in favor of `Late-Inning Options`;
- `Healthy Rested Bullpen` retired in favor of `Stable Rested Options`;
- the duplicate frontend tier-derivation engine removed;
- How to Read established as the reader-facing semantic map;
- freshness and Data Status vocabularies separated.

This is public-language ownership work. No model, threshold, classification, source authority, publication gate, or prediction behavior changed.

DEP-001 (#601) outcome, recorded at roadmap altitude only — the current
dependency-security boundary document owns the detail:

- backend runtime dependencies carry no known advisories; the advisory-bearing request-path packages were upgraded in one reviewed pass with CORS behaviour pinned before the upgrade and re-verified after it;
- `pytest` no longer ships to production; `backend/requirements-dev.txt` carries test dependencies and pulls the runtime set in;
- unused frontend packages were removed rather than overridden, which deleted the only high-severity production advisory;
- three React Router advisories remain, accepted as a **time-boxed** risk expiring 2026-11-13 and tracked by #645, bounded by a validated-redirect control and its regression tests;
- a standing `dependency-audit` CI job now refuses new, expired, stale, mismatched, duplicated, or under-documented production dependency risk, and never upgrades anything itself.

This is supply-chain hygiene. No baseball semantics, publication gate, source authority, runtime configuration, or write authority changed.

## 4. Protected Product Assets

| Asset | Preserve |
| --- | --- |
| Three-state canon | Fresh / Stretched / Vulnerable; no fourth state, score, grade, or rank. |
| Freshness discipline | Visible data-through dates and honest distinction between represented baseball date and system update time. |
| Fail-closed UI | Intentional quiet, withheld, stale, and data-limited presentations rather than guessed output. |
| Data & Trust validation | Public next-day-usage validation with sample sizes and explicit non-proof caveats. |
| Team Board evidence chain | State → concern → named reads → evidence → freshness → limitations → arm receipts. |
| Product identity | Bullpen-only scope, descriptive posture, dark visual system, and coherent navigation. |

## 5. Audit Evidence Classification

| Class | Rule | Current examples |
| --- | --- | --- |
| Confirmed visible defect | Rendered text or structure is directly contradictory, malformed, circular, duplicated, or inaccurate for the visible surface. | Resolved #591/#600 defects; future confirmed regressions enter the owning package. |
| Source verification required | The screenshot shows a tension, but thresholds, backend payloads, or source authority are needed before declaring the underlying intelligence wrong. | Workload-concentration headline versus evidence; population/count questions. |
| Runtime verification required | The screenshot captures a state that may be temporary or persistent. | Generated-content publication behaviour on the next naturally authorized scheduled export. |
| Observation only | A potential correctness concern must remain read-only until canonical evidence confirms it. | Reliever eligibility or other source-authority questions. |

## 6. Next Approved Work

The Public Credibility Pass is complete: #595 (public score containment), #591 (backend-owned Why copy), #600 (contextual H1/accessibility structure), #594 (routed team previews), and #638 (public vocabulary/glossary parity) are all complete and production-verified. DEP-001 (#601) is complete on main. The order below is the previously approved sequence with the finished packages removed; nothing was reprioritized.

| Order | Work package | Scope |
| --- | --- | --- |
| 1 | #598 - Generated-content CI validation | Take the outstanding closeout evidence: a naturally authorized scheduled export that produces a gated, tree-exact, machine-attributed generated commit, plus read-only deployment proof. Do not force or rerun a scheduled export to manufacture it. |
| 2 | Permanent daily-sync work reduction | Reduce avoidable upstream/runtime work without weakening D-051 or publication gates. |
| 3 | Portable Intelligence | #597 then #596: canonical raster renderer, artifact-specific crawler metadata, share actions, and evidence-inspection funnel. |
| 4 | Resume M-001 and visible evidence | Active Bullpen ERA, named-arm evidence, starter exposure, then Daily Habit work. |
| 5 | Daily Habit and Consequence | Public What Changed, team movement, Today lead authority, game-aware slate, and quiet-day behavior. |

One dated obligation sits outside this order and does not wait for it: the
React Router acceptance recorded under #645 expires **2026-11-13**, and the
`dependency-audit` CI job refuses the build from that date onward. Either the
migration lands or the acceptance is re-reviewed before then.

# Part II - Integrated Priority Matrix

## 7. Production Evidence Closeout

| Status | Work item | Why | Exit evidence |
| --- | --- | --- | --- |
| Complete | #593 scheduled signal separation | Public-sync and shadow-health remain independently meaningful. | Required scheduled window passed. |
| Complete | #590 production Team State proof | Canonical Team State merged and rendered correctly. | Corrected production proof complete. |
| Complete | Phase 1A authority qualification | Governed write-capable path needed positive no-op qualification. | Candidate audit + no-op PASS + D-052. |

## 8. Public Trust and Correctness

| Sequence | Work package | Integrated evidence | Definition of done |
| --- | --- | --- | --- |
| Complete | #595 - Raw score/internal ID containment | Production verified and issue closed | Unauthenticated scored/internal fatigue fields are not public claims; retained scored access is explicitly admin-only. |
| Complete | #591 - Explanation integrity | Backend-owned public copy | Frontend pass-through is proven; Why cannot be regex-rewritten or silently dropped; representative production surfaces verified. |
| Complete | #600 - Contextual page semantics | One H1 per `/bullpen` view | Team Board, Compare, and Reliever Finder have one contextual H1, logical hierarchy, and successful keyboard/accessibility/mobile smoke. |
| Complete | #594 - Routed team preview delivery | Production closeout August 11, 2026 | All 30 dated previews regenerate from one trusted publication; invalid routes fail closed; issue closed. |
| Complete | VOC-001 (#638) - Public vocabulary and glossary parity | Production closeout August 12, 2026 from trusted snapshot 398 | One public owner per term; in-product team-shape vocabulary reconciled; semantic families cannot be mistaken for Team State; issue closed. |
| Complete | DEP-001 (#601) - Dependency remediation | Verified on main by CI run 31729458591 | Backend runtime audit clean; frontend production risk reduced to three reviewed, expiry-controlled acceptances; standing CI dependency gate with no auto-upgrade path. |
| Verification only | Bounded surface checks | Potential reliever/stale/population concerns remain evidence-first | Open or widen work only when source/runtime evidence proves a defect. |

## 9. Public Surface Semantics

| Status | Owner | Outcome |
| --- | --- | --- |
| Complete | #594 | Routed/static team preview contract production-verified: 30 of 30 dated previews from trusted snapshot 393, 0 withheld, and `/team/INVALID` fail-closed. |
| Complete | #600 | Exactly one contextual H1 per `/bullpen` view; logical heading hierarchy; production keyboard/accessibility/mobile checks passed. |
| Complete | VOC-001 (#638) vocabulary/glossary parity | In-product team-shape labels, semantic families, Team State headers, and freshness terminology reconciled without changing canonical state/read ownership; production-verified August 12, 2026. |

## 10. Reliability, Portable Intelligence, and Evidence

| Lane | Work item | Definition of done |
| --- | --- | --- |
| CI/reliability | #598 | Generated-content commits cannot bypass validation or obscure provenance. Implementation is on main; the recorded closeout evidence is outstanding. |
| Dependencies | #601 - Complete | Known backend/frontend advisories assessed; request-path risk remediated; test dependencies removed from the production runtime; a standing read-only CI gate refuses unreviewed production dependency risk. Residual React Router acceptance expires 2026-11-13 under #645. |
| Permanent runtime work | Daily-sync work reduction | Reduce candidate enumeration and repeated roster/transaction work without weakening D-051. |
| Portable Intelligence | #597 then #596 | Supported raster assets first; then artifact-specific crawler-visible title, description, image, URL, alt text, and actions. |
| Visible evidence | M-001 then named-arm/starter context | Resume approved evidence work only after Public Credibility Pass exit. |
| Daily Habit | Public What Changed and Today lead | Comparable trusted change, receipt-bearing copy, quiet-day suppression, and game-aware status without prediction. |

# Part III - Phased Roadmap

## 11. Dependency Map

| Phase | Status | Exit / remaining work |
| --- | --- | --- |
| Phase 0 - Canonical Trust Closeout | Complete | Maintain official-line, starter, outs, appearance-team, and publication-gate regressions. |
| Phase 1 - Evidence Completeness | In progress / paused | M-001 contract complete; implementation resumes after public-credibility work. |
| Phase 1A - Authority Qualification | Complete - August 10, 2026 | D-052 phase exit; all broader game-driven write/publication/backfill authority remains unapproved. |
| Phase 1B - Public Credibility Pass | Complete - August 12, 2026 | #590, #595, #591, #600, #594, and #638 all complete and production-verified. Maintain the vocabulary, copy-authority, and page-semantics regressions. |
| Phase 2 - Portable Intelligence | Foundation complete / final distribution not started | Raster renderer, immutable asset, crawler metadata, actions, funnel. |
| Phase 3 - Daily Habit and Consequence | Not started | Public What Changed, team movement, Today lead, game-aware slate, quiet-day behavior. |
| Phase 4 - Offseason Intelligence Depth | Not started | Pitch trends, leverage/dependency, organizational depth, routed discovery, timeline/archive. |
| Phase 5 - Opening Day 2027 | Not started | Complete daily relaunch with current trust and reliability proof. |
| Phase 6 - Growth and Validation | Not started | Measured behavior and rights evidence choose direction. |

## 12. Success Metrics

| Metric family | Measures |
| --- | --- |
| Product quality | Public vocabulary drift: 0; malformed or claim/evidence-contradicting explanations: 0; contextual H1/accessibility checks remain green; every public label has glossary coverage. |
| Trust and operations | Silent stale incidents: 0; final-game appearance deficits reaching publication: 0; shadow baseball-data writes: 0; raw public composite-score exposure: 0; observer/publication gates remain separate. |
| Evidence | Every material team read names relevant arms or concrete counts; unexplained public numbers: 0; suppressed-copy reasons are observable. |
| Habit and distribution | Weekly return, Today-to-Team Board handoff, team-page return, evidence inspection, share actions, and external citations increase only after trust gates hold. |

# Part IV - Risks and Controls

| ID | Risk | Severity | Standing control |
| --- | --- | --- | --- |
| R-01 | Canonical game data is wrong or incomplete | Critical | Source authority, appearance gate, reviewed repairs, independent closeout |
| R-02 | Foundation perfectionism prevents public learning | High | Phase exits, one active objective, reader-facing next moves |
| R-03 | Generic stories fail to surprise | High | Named-arm receipts, duplicate-template suppression, quiet-day rules, editorial review. |
| R-04 | Trust warnings overpower the baseball insight | High | State first, evidence second, limitation only where material |
| R-05 | Single-founder capacity fragments work | High | One active objective, small branches, sustainable cadence |
| R-06 | Transitional share renderer becomes permanent | High | Portable Intelligence phase; no new legacy composition |
| R-07 | MLB source terms or availability change | High | Attribution, budgets, provenance, rights review |
| R-08 | Public label overclaims health, intent, or availability | High | Backend mappings, language guards, Unobservable Ledger |
| R-09 | Multiple documents claim authority | High | Six-document library, redirect/archive checks |
| R-10 | Competitor copies the surface | Medium | Trust history, evidence depth, immutable memory, creator workflow |
| R-11 | SEO remains weak | Medium | Routed owner decision and server/static metadata |
| R-12 | Founder burnout ends cadence | High | Quality ceiling, life-first planning, manual proof before automation |
| R-13 | Live product vocabulary contradicts canonical promise | Critical | #590 canonical Team State proof, #591 backend-owned Why, #600 semantic structure, and remaining vocabulary/glossary parity. |
| R-14 | Observer health obscures publication truth | High | Separate public-sync and shadow-health jobs; #593 production evidence |
| R-15 | Shadow bookkeeping absence is treated as a baseball deficit | High | D-044 dual-view classification and authority-aware blocker projection |
| R-16 | Public raw score endpoint violates black-box boundary | High | #595 complete and production-verified; public contract tests and admin-only scored access preserve the black-box boundary. |
| R-17 | Shared links lose claim, evidence, and date | High | Canonical image and artifact-specific crawler metadata |
| R-18 | Routed team previews drift without a canonical owner | Medium | #594 complete and production-verified: one trusted publication, canonical state/non-state, baseball point, data-through, receipt, fail-closed export. |
| R-19 | Frontend rewrites backend-owned meaning | Critical | #591 complete: backend-owned Why copy, frontend pass-through, public-copy contract tests, representative production verification. |
| R-20 | Generated commits bypass repository CI | High | #598 generated-content publication correction |
| R-21 | Daily runtime headroom masks avoidable work | High | D-050 temporary mitigation plus permanent work-reduction backlog |
| R-22 | Manual daily execution becomes de facto authority | Critical | D-051 schedule-only, first-attempt-only production daily execution |
| R-23 | Partial acquisition leaks into public serving | Critical | D-051 binds Team Board, Compare, Tonight to trusted published authority |
| R-24 | Authority qualification is mistaken for authority transfer | Critical | D-052 phase-exit language; O-008 remains open and requires explicit founder approval |
| R-25 | Dependency risk re-enters the production request path, or an accepted advisory quietly becomes permanent | High | #601 remediation; the standing read-only `dependency-audit` CI job; exact advisory/package-bound acceptances with hard expiry, tracking issue, and decision record; a solved advisory's exception must be deleted rather than left behind |

# Part V - Backlog and Stop Conditions

## 13. Near-Term Backlog

- #598 generated-content CI validation: the outstanding closeout evidence from a naturally authorized scheduled export, plus read-only deployment proof.
- React Router v7 migration (#645) before the 2026-11-13 acceptance expiry.
- Permanent daily-sync work reduction.
- Portable Intelligence: canonical raster renderer, artifact metadata, share actions, and evidence-inspection funnel.
- Resume M-001 Active Bullpen ERA after the Public Credibility Pass.
- Named-arm evidence expansion and starter-exposure context after M-001.

## 14. Later and Parked

Later: named-arm evidence, starter exposure, Public What Changed, team movement, pitch trends, leverage/dependency, organizational depth, routed discovery, state timeline, story-engine consolidation, accessibility and technical-debt windows.

Parked until demand: Follow My Team, automated newsletter, game pages beyond the Slate, embeds, public API/exports, push notifications, professional sales tooling, sponsorship, and monetization tests.

Never backlog: predictions, betting/odds, game-outcome projections, injury prediction, fantasy advice, manager-intent claims, generic rankings, black-box public scores, or user-editable claims inside immutable artifacts.

## 15. Stop Conditions

- Required baseline is absent from origin/main.
- Source authority is unresolved or a public term has two competing owners.
- A write or authority-transfer step lacks positive production qualification.
- A rendered claim contradicts its own evidence and source review cannot establish which side owns the correction.
- Implementation requires prediction, manager intent, private health inference, unknown-as-zero behavior, or a fourth Team State.
- A migration cannot preserve history or safely refuse destructive downgrade behavior.
- Production smoke, runtime verification, or required audit cannot complete safely.
- A dangerous write lacks a read-only plan, exact scope, explicit confirmation, and post-write proof.
- Production-evidence capture would be obscured by an overlapping presentation change.
- The change silently expands beyond the approved objective.

# Part VI - Decision Ledger

The current-state reconciliation does not create a new durable semantic or authority decision. D-001 through D-053 remain in force; D-050 through D-053 are included below because they govern the current operating and authority posture.

D-053, added by CI-003 (#598), governs how generated content may be published to the repository. It adds no baseball semantics and changes neither D-051 nor D-052.

DEP-001 (#601) created no Decision Ledger ID. Its time-boxed acceptance of the residual React Router advisories is a dated, revocable security decision recorded in `docs/decisions/2026-08-13-react-router-v7-security-defer.md` and machine-enforced by `.github/dependency-audit-accepted.json` — deliberately not a durable authority decision, because it is designed to expire.

## Decision status vocabulary

The ledger is history and current policy at once, and until Version 4.0 the two looked identical: a decision that had been narrowed read exactly like one still in force. The Status column now uses a defined vocabulary.

| Status | Meaning |
| --- | --- |
| Permanent | In force, and not expected to change without a constitutional-level reason. |
| Standing | In force as an ongoing boundary or trust rule. |
| Adopted | In force as an accepted decision of record. |
| Amended | In force, with its scope narrowed or clarified by a later decision, which the row names. |
| Superseded | No longer in force; a later decision replaces it, and the row names that decision. |
| Historical | Retained as record of a decision whose subject no longer exists. |

Applying the vocabulary changes no decision. A row moves to Amended or Superseded only where a later decision already did that work; nothing here narrows a decision by relabelling it, and no ID is renumbered or removed.

D-013 is the one row this edition amends, and D-053 is what amended it. No other status changed.

| ID | Date | Decision | Status |
| --- | --- | --- | --- |
| D-001 | Prior to Jul 2026 | BaseballOS is trust-first. | Permanent |
| D-002 | Prior to Jul 2026 | Predictions, betting, fantasy advice, private injury claims, and manager-intent certainty are prohibited. | Permanent |
| D-003 | Jul 24, 2026 | Public Team State labels are Fresh, Stretched, and Vulnerable. | Adopted |
| D-004 | Jul 24, 2026 | Team State has exactly three public labels; internal states stay internal. | Standing |
| D-005 | Jul 2026 | Public arm reads are Clean Option, Watch Arm, Limited Rest, Unavailable, and Limited Read; backend keys own meaning. | Standing |
| D-006 | Jul 2026 | The immutable Share Artifact, not an image or browser component, is the source of truth. | Permanent |
| D-007 | Jul 29, 2026 | An eligible team may publish progressively before the full league slate completes. | Adopted |
| D-008 | Jul 29, 2026 | Integer recorded outs are the semantic innings authority; decimal innings are derived. | Permanent |
| D-009 | Jul 29, 2026 | Historical appearance team comes from the game side, not current organization. | Permanent |
| D-010 | Jul 24, 2026 | Meaning-bearing Share Artifact copy is deterministic, backend-owned, and not free-form AI analysis. | Permanent |
| D-011 | Jul 2026 | Published artifacts are immutable; corrections supersede or withdraw rather than rewrite. | Permanent |
| D-012 | Jul 2026 | Current and historical state remain separate objects. | Permanent |
| D-013 | Prior to Jul 2026 | Nickolis Kacludis remains sole repository author/committer; no AI attribution is added. **Amended by D-053, August 12, 2026:** scoped to human-authored engineering work, which remains Nickolis Kacludis only. The single approved exception is the governed generated-content publication job, which commits as `BaseballOS Automation <baseballoshq@gmail.com>` with run provenance. That identity is a machine publisher operating inside D-053's gate, not a second engineering author, and its write authority reaches nothing outside that one job. The no-AI-attribution rule is unchanged and absolute: no AI, Claude, or Anthropic attribution, generated-by footer, session link, or co-author trailer appears in any commit, pull request, or artifact. | Amended by D-053 |
| D-014 | Prior to Jul 2026 | One user question per page and one canonical home per fact. | Permanent |
| D-015 | Prior to Jul 2026 | Manual proof precedes automation for newsletter and distribution workflows. | Standing |
| D-016 | Prior to Jul 2026 | Follow My Team waits for demonstrated retention value. | Standing |
| D-017 | Jul 29, 2026 | Six living canonical documents replace recurring master documents. | Adopted |
| D-018 | Jul 29, 2026 | Foundation 3A closed with independent production proof; Phase 1 Evidence Completeness opened. | Adopted |
| D-019 | Jul 29, 2026 | The Matt Festa one-action apply is terminally closed and must not be dispatched again. | Permanent |
| D-020 | Jul 29, 2026 | A fingerprint-locked apply refusing because its manifest no longer regenerates is a correct terminal outcome. | Permanent |
| D-021 | Jul 29, 2026 | The Current Active-Pen Performance family owns group, window, sample, date, evidence, limits, and Team Board home. | Adopted |
| D-022 | Jul 29, 2026 | Metric family and metric definition are separate governed objects; M-001 is reserved but non-public. | Adopted |
| D-023 | Jul 30, 2026 | M-001 publishes only at 108 recorded outs or more. | Adopted |
| D-024 | Jul 30, 2026 | M-001 formula is earned runs times 27 divided by integer recorded outs; zero denominator refuses first. | Adopted |
| D-025 | Jul 30, 2026 | Performance rates use exact integers and one ROUND_HALF_UP operation at declared precision; M-001 displays two decimals. | Adopted |
| D-026 | Jul 30, 2026 | Below-sample wording is Not Enough Innings Yet with current and required innings adjacent. | Adopted |
| D-027 | Jul 30, 2026 | A no-usage call-up remains in the active group with zero contribution; reads report group size and contributing arms. | Adopted |
| D-028 | Jul 30, 2026 | M-001 public name is Active Bullpen ERA. | Adopted |
| D-029 | Jul 30, 2026 | M-001 uses four evidence levels; a value unable to reach source-level proof is not publishable. | Adopted |
| D-030 | Jul 30, 2026 | Future metrics inherit the performance-family authority, evidence, freshness, failure, and rounding contracts. | Adopted |
| D-031 | Jul 31, 2026 | Foundation 3C bootstrap completed for governed games and rows without granting activation authority. | Adopted |
| D-032 | Jul 31, 2026 | Foundation 3C rollout closed, production replay verified, and temporary rollout workflows retired. | Adopted |
| D-033 | Aug 1, 2026 | The missing postgame integration point was built; postgame write and authoritative modes remain refused. | Adopted |
| D-034 | Aug 1, 2026 | Automated shadow activation approved for daily and postgame only; backfill remains off and writes remain unapproved. | Adopted |
| D-035 | Aug 1, 2026 | First postgame shadow failure was isolated to scope; postgame shadow paused and no repair was guessed. | Adopted |
| D-036 | Aug 1, 2026 | Exact-cycle scope repair accepted and postgame shadow reactivated with stronger validation and diagnostics. | Adopted |
| D-037 | Aug 1, 2026 | GameLog balls authority was declared unresolved; no writer changed; a read-only source-authority audit was added. | Adopted |
| D-038 | Aug 1, 2026 | Completed-game box score is canonical fallback for balls only when the split omits it and the official pitch triple validates. | Adopted |
| D-039 | Aug 2, 2026 | PROD-001 widens Tonight provenance capacity to 128, preserves full source, and requires scheduled production closure. | Adopted; production proof complete |
| D-040 | Aug 2, 2026 | Trusted public-sync and experimental shadow-health are separate jobs; neither publication nor observer gates are weakened. | Adopted; production observation complete |
| D-041 | Aug 3, 2026 | Manual exact-one-game no-op write qualification machinery exists and authorizes no real mutation or broader mode. | Adopted |
| D-042 | Aug 4, 2026 | First qualification refused on missing durable work item; candidate selection belongs to a bounded read-only audit. | Adopted |
| D-043 | Aug 4, 2026 | The August 3 failed publication cycle is handled by a manual exact-scope read-only incident audit; shadow is not assumed to be the failure. | Adopted |
| D-044 | Aug 4, 2026 | Shadow observation backlog and publication blockers are separate views; missing work-item proof blocks only in authoritative mode. | Adopted |
| D-045 | Aug 4, 2026 | Backend CI is partitioned across four deterministic, file-balanced shards with separate PostgreSQL databases and exact collection accounting. | Adopted |
| D-046 | Aug 4, 2026 | Trust-critical CI receives full Git history; frontend CI uses the committed lockfile and requires tests plus the production build. | Adopted |
| D-047 | Aug 5, 2026 | The game 824487 source-revision mismatch is investigated by a manual exact-scope read-only audit that will not guess a field delta from a SHA-256 digest. | Adopted; production audit executed |
| D-048 | Aug 6, 2026 | Game 824487's source-revision checkpoint was corrected through the reviewed one-row workflow, terminally re-observed as already applied with zero additional writes, and the single-purpose repair capability is retired. This grants no broader game-driven write or publication authority. | Permanent |
| D-049 | Aug 6, 2026 | UX-001 closes after corrected production proved backend-owned Stretched and Vulnerable states plus governed fail-closed behavior; naturally absent Fresh evidence is never manufactured. | Permanent |
| D-050 | Aug 6, 2026 | OPS-002 uses temporary runtime headroom while preserving publication gates and all game-driven authority boundaries; permanent work reduction remains separate. | Operational until permanent work-reduction proof supersedes it |
| D-051 | Aug 8, 2026 | Acquisition may advance independently, but public Team Board, Compare, and Tonight authority advances only through trusted publication. Production full-daily execution is scheduled and first-attempt only; generic manual daily execution, local production daily invocation, the legacy admin daily writer route, and GitHub reruns are non-authoritative/refused. | Standing trust boundary |
| D-052 | Aug 10, 2026 | Phase 1A Game-Driven Ingestion Authority Qualification is complete after OPS-002 scheduled reliability proof, OPS-001 scheduled signal-separation proof, read-only candidate audit run 31393177954, and no-op write qualification PASS run 31395294655 for game 823924. The PASS proves safe governed entry into the write-capable path with zero baseball-data mutation and exact lane-ledger movement. It grants no automated/scheduled write authority, no game-driven publication authority, no backfill authority, and no legacy-writer retirement. | Permanent phase-exit decision |
| D-053 | Aug 12, 2026 | Automated generated content may reach `main` only through a self-gating publication job: generate from trusted publication, prove delivery integrity, run the canonical frontend tests and production build against the exact generated tree, record that tree's identity, commit under `BaseballOS Automation <baseballoshq@gmail.com>` with run provenance, prove the commit's tree equals the validated tree, and fast-forward push. Repository write authority is scoped to that one job. The guarantee is tree-exact, not commit-SHA-exact. No baseball semantics move into CI; D-051 and D-052 are unchanged. | Standing publication boundary; production-exercised August 14, 2026 by scheduled run 31794183367, which produced gated commit `2e83fa0` under the machine identity. Deployment verification for the CI-003 closeout remains outstanding. Amends D-013 by scoping it to human-authored engineering work. |

## 16. Open Decisions

| ID | Decision required | Gate | Current default |
| --- | --- | --- | --- |
| O-001 | Resolved by D-021 | Closed | Performance family established; M-001 remains unimplemented and non-public. |
| O-002 | Current-versus-shared comparison contract | Trusted comparability and public UX | Historical page remains frozen only. |
| O-003 | Canonical server renderer technology and storage | Artifact contract, hosting cost, and performance | Transitional browser renderer only. |
| O-004 | Public leverage calculation and table | Complete source coverage and reproducible method | Legacy/partial claims remain bounded. |
| O-005 | Routed team URL shape and surface ownership | Product route and SEO plan | Current Team Board remains canonical live destination. |
| O-006 | Whether account/sign-in remains after Follow My Team review | Demonstrated retention value | Keep internal auth substrate; no broad account push. |
| O-007 | Resolved by D-052 | Closed | A completed durable candidate was found read-only and game 823924 passed the exact no-op qualification contract. |
| O-008 | Game-driven automated write and later publication-authority transfer | Real-mutation proof, scheduled write stability, rollback, observability, and explicit founder approval | Daily/postgame shadow; backfill off; legacy writer authoritative. |

# Part VII - Founder Operating System

## 17. Weekly Review

- Current main commit and production deployment state.
- One active objective and the evidence currently blocking it.
- Open branch, merged work, CI result, and production proof.
- Which audit evidence moved from observation to confirmed defect.
- Which risk changed and which protected asset could be harmed by the next package.
- Next approved work, deliberate deferrals, and documentation alignment.
- Sustainable distribution cadence and whether a lower-priority item began without a recorded reason.

## 18. Founder Principles

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

# Appendix A - Completion Log

| Date | Phase | Item | Branch / PR / commit | Production evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| Jul 29, 2026 | Phase 0 | Canonical Trust Closeout and Phase 1 opening | PR #559 / ec636f2... | Independent closeout passed; six-doc authority recorded | Foundation 3A closed; M-001 became first scoped evidence item. |
| Jul 29-30, 2026 | Phase 1 | Current Active-Pen Performance contract and M-001 governance | D-021 through D-030 / PRs #560-#566 | Group, formula, 108-out sample, name, precision, wording, membership, and evidence contract | Implementation remains non-public. |
| Jul 31, 2026 | Phase 1A | Foundation 3C bootstrap and closeout | PRs #572-#581 | 109 governed final games and 946 appearance rows reconciled; replay and drift checks passed | No activation authority granted by bootstrap. |
| Aug 1, 2026 | Phase 1A | Daily/postgame shadow activation and exact-cycle repair | PRs #582-#585 | Shadow isolated; first scope failure diagnosed; postgame reactivated after exact-scope proof | Automated write and authoritative modes stayed unapproved. |
| Aug 1, 2026 | Phase 1A | GameLog balls authority and fallback | PRs #586-#587 | Production audit proved split omission and official box-score fallback contract | Fallback approved only for balls with pitch-accounting validation. |
| Aug 2, 2026 | Operations | Tonight source-capacity repair | PR #588 / migration c7f1b408d93a | Code and PostgreSQL proof merged | Scheduled production closure completed August 4 through run 30921186222. |
| Aug 2, 2026 | Operations | Public-sync separated from shadow-health observer | PR #602 | Publication-dependent jobs no longer depend on observer verdict | No publication gate or observer gate weakened. |
| Aug 3, 2026 | Phase 1A | Manual no-op write qualification machinery | PR #604 | Exact one-game, main-only, owner-only, fingerprinted and evidence-scanned path | No production execution occurred in implementation. |
| Aug 4, 2026 | Phase 1A | No-op candidate audit | PR #605 | First run refused safely on missing work item; bounded read-only candidate selection added | No target may be guessed. |
| Aug 4, 2026 | Phase 1A | Observation backlog separated from publication blockers | PR #608 / d746471... | Shadow backlog classified separately from real baseball deficits | No authority boundary changed. |
| Aug 4, 2026 | CI | Four-shard PostgreSQL confidence gate | PR #609 | Separate PostgreSQL databases with exact collection accounting | Trust-critical CI hardened. |
| Aug 4, 2026 | CI | CI-001 closure (#599) | PR #610 / ebe2db4... | Lockfile-faithful frontend CI, full tests, production build | Complete. |
| Aug 5-6, 2026 | Phase 1A | Game 824487 audit, repair, and retirement | PRs #613, #615, #616 | Exact-scope source-revision correction terminally closed | Temporary repair capability retired. |
| Aug 6, 2026 | Phase 1B | UX-001 canonical Team State production closeout | PRs #611, #617 / run 31097712768 | Canonical Team State production evidence complete | #590 closed. |
| Aug 6-10, 2026 | Operations | OPS-002 runtime mitigation and trusted-serving correction | PRs #619, #621, #627 / D-050, D-051 | Three scheduled first-attempt daily PASS runs | Issue #620 closed. |
| Aug 3-10, 2026 | Phase 1A | OPS-001 signal-separation observation | PR #602 / issue #593 | Scheduled evidence proved public-sync and observer separation | Issue closed August 10. |
| Aug 10, 2026 | Phase 1A | Read-only no-op candidate production audit | Run 31393177954 | COMPLETE_ELIGIBLE_FOUND; five candidates; zero durable writes | Suggested game 823924. |
| Aug 10, 2026 | Phase 1A | Manual one-game no-op write qualification | Run 31395294655 | PASS; game 823924; zero baseball-data writes; exact lane-ledger delta | Pre/post state identical. |
| Aug 10, 2026 | Phase 1A | Authority Qualification phase exit | PR #628 / D-052 | Phase complete | No automated write/publication/backfill authority granted. |
| Aug 10, 2026 | Phase 1B | SEC-001 public score containment (#595) | PR #630 / main b328c917… | Production verification passed; issue closed. | Public scored/internal fatigue fields contained; admin-only scored access retained. |
| Aug 10, 2026 | Phase 1B | FE-001 backend-owned Why copy (#591) | PR #631 / main f4a23cc… | Production representative-team verification passed; issue closed. | Frontend no longer regex-rewrites or silently drops governed Why copy. |
| Aug 10, 2026 | Phase 1B | DIST-003 routed team preview implementation (#594) | PR #632 / merge d13bf529… | Repository implementation complete. | One trusted publication per representation; fail closed without provable date/authority. |
| Aug 10-11, 2026 | Phase 1B | UX-002 contextual `/bullpen` page identity (#600) | PR #633 / merge 98e452e… | CI green; production keyboard, accessibility-tree, and mobile checks passed; issue closed. | Exactly one contextual H1 per active `/bullpen` view; no answer-first regression. |
| Aug 11, 2026 | Phase 1B | Routed team preview delivery correction | PR #637 "Serve dated team preview pages at public team routes" / merge 5e79c3c… | Public team routes serve the dated static previews rather than the application shell. | Delivery-path repair; the #594 authority and freshness contract is unchanged. |
| Aug 11, 2026 | Phase 1B | DIST-003 production closeout (#594) | Scheduled run 31483859116 / export job 93760656523 | 30 of 30 dated previews from trusted snapshot 393, 0 withheld, data through 2026-08-10; `/team/COL` and `/team/INVALID` verified in production; issue closed. | Complete and production-verified. Evidence below. |
| Aug 12, 2026 | CI | CI-003 generated-content CI gate (#598) | Session 1 read-only audit; repository implementation on `fix/generated-content-ci-gate` / D-053 | Repository implementation only. Delivery gate, canonical frontend tests and production build, tree-exact validation, `BaseballOS Automation` identity, and workflow permission narrowing are implemented and covered by contract tests. | **NOT complete.** Closeout requires the next naturally authorized scheduled run to produce a gated, tree-exact, machine-attributed generated commit, plus read-only Vercel deployment verification. #598 remains open. |
| Aug 13, 2026 | CI | CI-003 first scheduled D-053 exercise (#598) | Scheduled run 31693516516 | The exporter succeeded — 30 of 30 previews from trusted snapshot 404, 0 withheld, data through Aug 12 — and the delivery gate then refused to publish, because the structured result reached it through the exporter's stdout and stdout also carried an application diagnostic line. No generated commit and no push occurred. | **NOT complete.** Correct fail-closed refusal, not a gate defect. Bounded repair underway: the exporter writes its structured result to an explicit file instead of stdout. No trust or authority boundary weakened; the verifier stays strict. #598 remains open pending the next naturally authorized scheduled run and Vercel proof. |

| Aug 12, 2026 | Phase 1B | VOC-001 public vocabulary and glossary parity (#638) | PRs #639, #640 / scheduled run 31589796614 | Trusted snapshot 398, data through 2026-08-11, sync_run_id 695. Production browser smoke verified canonical Team State, pitcher role/read labels, supporting reads, freshness/data-through, and all five board groups rendering independently. Issue closed August 12. | **Complete and production-verified.** PR #640 removed a frontend-only path that collapsed zero-count groups into a manufactured generic heading. No model, threshold, authority, or publication behavior changed; D-051 respected — no manual production daily sync was used for closeout. |
| Aug 13, 2026 | Dependencies | DEP-001 backend request-path remediation (#601) | PR #643 | Flask 3.0.0 → 3.1.3, Flask-CORS 4.0.0 → 6.0.5, gunicorn 21.2.0 → 23.0.0, requests 2.31.0 → 2.34.2, python-dotenv 1.0.0 → 1.2.2. | CORS behaviour pinned by regression tests before the upgrade and re-verified after it. The origin allowlist is unchanged and `supports_credentials` remains disabled. |
| Aug 13, 2026 | Dependencies | DEP-001 test/runtime dependency separation (#601) | PR #644 | `pytest` removed from `backend/requirements.txt`; `backend/requirements-dev.txt` added, pulling the runtime set in. | Production no longer installs test-only packages or their advisories. Nothing under `backend/` imports `pytest` outside `backend/tests/`. |
| Aug 13, 2026 | Dependencies | DEP-001 frontend runtime remediation (#601) | PR #646 | Unused `recharts` and `clsx` removed, which deleted the only high-severity production advisory by removing the package `lodash` entered through; `react-router-dom` patched to 6.30.4. | No override and no direct pin was added. Three React Router advisories remain, accepted time-boxed to 2026-11-13 under #645, bounded by a validated-redirect control and its regression tests. |
| Aug 13, 2026 | Dependencies | DEP-001 standing CI dependency gate and closeout (#601) | PR #647 / main e3ad8bd / CI run 31729458591 | Backend runtime audit clean. `dependency-audit` job refuses new, expired, stale, mismatched, duplicated, or under-documented production dependency risk; dev/build advisories are informational only. | **Complete.** The gate is read-only — it never upgrades, pins, or edits a dependency, and creates no auto-upgrade path. Issue closed August 13. |
| Aug 13-14, 2026 | Human Quality | Repository retirement and freeze narrowing (H-1) | PRs #650, #651 | Dangling and root-level documents archived or classified; byte-freeze policy narrowed to the files that need it. | **Complete.** No public behavior changed. The broad phase-freeze claim survives in no active document.
| Aug 14, 2026 | Human Quality | Public-copy ownership and language quality (H-5 through H-9) | PRs #652, #653, #654, #655, #656, #657 | Backend-owned public copy, generated-copy quality, team-preview claim authority, public language polish, explanation label ownership and envelope language. | **Complete.** Wording and ownership only; no model, threshold, classification, authority, or publication behavior changed. |
| Aug 14, 2026 | Human Quality | UX density and information hierarchy (H-10) | PR #658 / main a049c45 | Today and Team Board hierarchy and density pass. | **Complete.** Presentation only: no semantic change, no new metric, no vocabulary change. |
| Aug 14, 2026 | Human Quality | Public vocabulary and freshness convergence (H-11) | PR #659 / main b2f0e90 | Nine re-audit defects closed: share cards project canonical public state, freshness stamps converge on the five canonical labels, Read Confidence is named everywhere including ARIA, `Clean Options` retired from surfaces in favour of `Rested Options`, unknown values fail closed. | **Complete.** The Workload Data family was introduced here because a pitcher's workload-record status is a different question from platform Data Status; Version 4.0 records its canonical home in the Bullpen Intelligence Standard and Product Experience Standard. |
| Aug 14, 2026 | CI | CI-003 first gated generated-content publication (#598) | Scheduled run 31794183367 (attempt 1) / commit `2e83fa0` | The scheduled daily export published under the D-053 gate: generated from trusted publication, delivery integrity proven, canonical frontend tests and production build run against the exact generated tree, tree identity recorded, committed as `BaseballOS Automation <baseballoshq@gmail.com>` with Source-SHA `71e0b89`, Validated-Tree `1c9d7dc`, Snapshot-ID 411, data through August 13, and fast-forward pushed. | **Not complete.** This is the gated, tree-exact, machine-attributed commit the closeout requires, taken from a naturally authorized scheduled run rather than a forced one. Read-only deployment verification remains outstanding, so #598 stays open. |
| Aug 14, 2026 | Human Quality | Document authority reconciliation (H-12) | This edition | Nine competing-authority defects closed across the canonical library, current subsystem contracts, code-cited document paths, and secondary-document status labelling. | **Complete.** Documentation and documentation-reference reconciliation only. No sync mode, publication gate, write authority, baseball logic, schema, or dependency changed. |

## DIST-003 (#594) Production Closeout Evidence

DIST-003 (#594) is **Complete**, production-verified August 11, 2026.

| Item | Value |
| --- | --- |
| Authorized scheduled production export | GitHub Actions run 31483859116 |
| Static team-preview export job | 93760656523 |
| Previews generated | 30 of 30 dated team previews |
| Previews withheld | 0 |
| Represented baseball data | through 2026-08-10 |
| Trusted export snapshot | 393 |
| Export generated-at | 2026-08-11T11:15:00+00:00 |
| Production routing repair | PR #637 "Serve dated team preview pages at public team routes", merged August 11, 2026 |
| Issue closed | August 11, 2026 |

The trusted export snapshot for this closeout is **393**. An earlier working note recorded 398; that value came from a different observed scheduled-run state and is not the snapshot the verified production pages were generated from. It is recorded here so the wrong number cannot be reintroduced as the closeout basis.

**Valid route proof.** `GET https://baseballos.app/team/COL` returned Colorado-specific dated static HTML carrying: title `Colorado Rockies Bullpen: Vulnerable`; representation `dated_team_read`; Team State `Vulnerable`; the specific baseball point "Two relievers are available from the latest completed workload data."; data-through `2026-08-10`; generated-at `2026-08-11T11:15:00+00:00`; snapshot-id `393`; sync-run-id `684`; authority-contract `trusted_dashboard_publication_v1`; published-at `2026-08-11T11:07:55.967061`; canonical `https://baseballos.app/team/COL`; and handoff `/bullpen?view=board&team=COL&source=share`.

**Invalid route fail-closed proof.** `GET https://baseballos.app/team/INVALID` returned representation `invalid_team` with generic BaseballOS fallback copy and no Team State, no data-through, no snapshot-id, no sync-run-id, no publication timestamp, and no trusted-publication authority; canonical `https://baseballos.app/team/` and handoff `/`.

A third-party social-platform unfurl is not part of this recorded closeout. The literal #594 acceptance criteria were satisfied by the routed static/crawl proof together with the production valid and invalid route evidence above.

# Appendix B - Phase Exit Record

| Phase | Status | Exit date | Evidence | Remaining work |
| --- | --- | --- | --- | --- |
| Phase 0 - Canonical Trust Closeout | Complete | Jul 29, 2026 | Independent official-line, starter, outs, appearance-team, and aggregation closeout | Maintain regression and publication gates |
| Phase 1 - Evidence Completeness | In progress / paused |  | D-021 through D-030 establish M-001 contract | Registry, backend read, Team Board, evidence, tests |
| Phase 1A - Authority Qualification | Complete | Aug 10, 2026 | D-052; #593/OPS-002 closed; candidate audit and no-op PASS | No authority transfer; O-008 remains open |
| Phase 1B - Vocabulary and Freshness | Complete | Aug 12, 2026 | #590, #595, #591, #600, #594, and #638 complete and production-verified; VOC-001 closed on trusted snapshot 398 proof | Maintain vocabulary, copy-authority, and page-semantics regressions |
| Phase 2 - Portable Intelligence | Foundation complete / final distribution not started |  | Immutable artifact and historical page are production | Renderer, metadata, actions, funnel |
| Phase 3 - Daily Habit and Consequence | Not started |  | Comparability and surface foundations exist | What Changed, lead, slate, quiet day |
| Phase 4 - Offseason Intelligence Depth | Not started |  | Candidate domains governed | Pitch, leverage, depth, routes, archive |
| Phase 5 - Opening Day 2027 | Not started |  |  | Complete daily relaunch |
| Phase 6 - Growth and Validation | Not started |  |  | Behavior and rights evidence choose direction |

# Appendix C - Source Basis

- BaseballOS Product Roadmap & Decision Ledger Version 3.9, effective August 13, 2026.
- Repository main b2f0e90718321857f3f631cda3c81c1175af85de after PR #659. The August 13 baseline was e3ad8bd after PR #647, with CI run 31729458591 green on that commit.
- Gated generated-content publication commit `2e83fa0` on main, from scheduled run 31794183367 (attempt 1), Validated-Tree `1c9d7dc`, Snapshot-ID 411, data through August 13, 2026.
- Git authorship on main at this basis: every engineering commit authored by Nickolis Kacludis, plus the one `BaseballOS Automation` publication commit above.
- Decision Ledger through D-053.
- GitHub issue state through August 14, 2026: #595, #591, #600, #594, #638, and #601 closed; #645, #597, #596, and the #589 tracker open. #598's issue is closed while its recorded deployment evidence is outstanding.
- Production evidence retained for #590, #592, #593, #595, #591, #600, #594, #638, OPS-002, and Phase 1A authority qualification.
- Product Experience Standard Version 1.5, Bullpen Intelligence Standard Version 1.4, Platform Architecture & Operations Manual Version 1.6, and Editorial & Distribution Standard Version 1.3.
- Current dependency-security boundary: `docs/current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`.
- Accepted-risk decision record: `docs/decisions/2026-08-13-react-router-v7-security-defer.md`.

## Repository basis

Current main: b2f0e90718321857f3f631cda3c81c1175af85de after PR #659. No open implementation branch carries product state. Phase 1A remains closed under D-052 and Phase 1B closed August 12, 2026.

SEC-001 (#595), FE-001 (#591), UX-002 (#600), DIST-003 (#594), VOC-001 (#638), and DEP-001 (#601) are all closed after verification.

## Active objective

The active objective is CI-003 (#598) generated-content publication closeout — the next package in the previously approved order, reached because VOC-001 and DEP-001 both closed.

Its repository implementation and the PR #642 result-transport repair are on main, and its GitHub issue was closed August 12, 2026 through linked pull request #641. The first scheduled exercise refused correctly rather than publishing, and the repair merged after that run. Scheduled run 31794183367 then produced the gated, tree-exact, machine-attributed commit `2e83fa0` on main. The remaining recorded requirement is read-only deployment verification, which has not been taken.

A closed issue and recorded production proof are different claims. This edition records that distinction and does not resolve it; #598's contract, workflow, and authority are untouched.

## Next approved sequence

1) Take the outstanding #598 read-only deployment proof against the published previews from commit `2e83fa0`; the scheduled-export half of that evidence is recorded, and neither half may be forced or rerun to manufacture it. 2) Continue permanent daily-sync work reduction, preserving D-051 in full. 3) Begin Portable Intelligence — #597 then #596. 4) Resume M-001 and visible evidence. 5) Daily Habit and consequence work.

Running alongside this order, and not gated by it: complete or re-review the React Router acceptance (#645) before it expires 2026-11-13.

# Appendix D - Revision History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0 | July 29, 2026 | Nickolis Kacludis | Established the canonical execution roadmap and durable Decision Ledger. |
| 2.0 | August 4, 2026 | Nickolis Kacludis | Reconciled current state through D-044 and the authority-qualification work. |
| 3.0 | August 5, 2026 | Nickolis Kacludis | Reconciled current state through PR #612 and main a27631d; recorded #592/#599 complete and #590/#593 evidence pending. |
| 3.1 | August 5, 2026 | Nickolis Kacludis | Condensed the canonical roadmap and integrated the important visual-audit evidence without changing the approved sequence or durable decisions. |
| 3.2 | August 6, 2026 | Nickolis Kacludis | Recorded UX-001 production closeout and D-049. |
| 3.3 | August 6, 2026 | Nickolis Kacludis | Recorded OPS-002 runtime-budget incident/mitigation and D-050; paused #593 pending reliable evidence. |
| 3.4 | August 10, 2026 | Nickolis Kacludis | Closed Phase 1A through D-052 after OPS-002/#593 evidence, candidate audit, and governed no-op PASS; made #595 the active public-trust objective without transferring game-driven authority. |
| 3.5 | August 10, 2026 | Nickolis Kacludis | Recorded SEC-001 (#595) implementation and production closeout: public scored/internal fatigue fields contained; retained scored access explicitly admin-only. |
| 3.6 | August 10, 2026 | Nickolis Kacludis | Recorded DIST-003 (#594) implementation: routed team previews use one trusted publication, canonical Team State/non-state, data-through, receipts, and fail-closed output; production verification remained pending. |
| 3.7 | August 11, 2026 | Nickolis Kacludis | Reconciled current state through PR #633/main 98e452e: #595, #591, and #600 complete and production-verified; #594 merged and awaiting the next authorized scheduled export; vocabulary/glossary parity is the next implementation package after #594 closeout. No durable authority decision changed. |
| 3.8 | August 11, 2026 | Nickolis Kacludis | Recorded the DIST-003 (#594) production closeout: authorized scheduled run 31483859116, export job 93760656523, 30 of 30 dated previews with 0 withheld, data through 2026-08-10, trusted snapshot 393, generated-at 2026-08-11T11:15:00+00:00, production `/team/COL` dated-read proof and `/team/INVALID` fail-closed proof, issue closed August 11. Recorded PR #637 "Serve dated team preview pages at public team routes" as the delivery-path correction that made those routes serve the dated previews. Moved the active objective to VOC-001 (#638), whose repository implementation — including Product Experience Standard v1.4 and Bullpen Intelligence Standard v1.3 — is in PR #639, which is open and unmerged and carries no production proof; #638 remains open. The Public Credibility Pass and Phase 1B remain active and exit only after PR #639 merges, deployment completes, read-only production vocabulary smoke passes, and #638 closes; repository CI green is necessary and not sufficient. The downstream sequence is preserved exactly: #598, then #601, then permanent daily-sync work reduction, then Portable Intelligence, then M-001 and visible evidence, then Daily Habit and consequence. No durable authority decision was added, weakened, or renumbered, D-051 and D-052 stand unchanged, and no new Decision Ledger ID was created. |
| 3.9 | August 13, 2026 | Nickolis Kacludis | Reconciled current state through PR #647/main e3ad8bd, verified by CI run 31729458591. Recorded VOC-001 (#638) complete and production-verified August 12, 2026 from trusted snapshot 398, which exits the Public Credibility Pass and closes Phase 1B. Recorded DEP-001 (#601) complete across PRs #643, #644, #646, and #647: backend runtime dependency advisories cleared with CORS behaviour pinned before the upgrade and re-verified after it, `pytest` removed from the production runtime in favour of `backend/requirements-dev.txt`, unused frontend packages removed rather than overridden, `react-router-dom` patched to 6.30.4, and a standing read-only `dependency-audit` CI job added that refuses new, expired, stale, mismatched, duplicated, or under-documented production dependency risk without creating any auto-upgrade path. Recorded the three residual React Router advisories as a time-boxed acceptance expiring 2026-11-13 under tracking issue #645, bounded by a validated-redirect control and its regression tests, and added R-25 for dependency drift and acceptance permanence. Moved the active objective to CI-003 (#598), the next package in the unchanged approved order, and recorded that its GitHub issue is closed while the production-proof evidence this Roadmap requires is still outstanding — without adjudicating, weakening, or advancing that package. No durable authority decision was added, weakened, or renumbered; D-051, D-052, and D-053 stand unchanged; no new Decision Ledger ID was created; and the shadow/backfill/legacy-writer authority posture is untouched. |
| 4.0 | August 14, 2026 | Nickolis Kacludis | Reconciled current state through PR #659/main b2f0e90 and closed the roadmap half of the H-12 document-authority audit. Recorded that the CI-003 (#598) closeout evidence Version 3.9 said did not exist now partly does: scheduled run 31794183367, a `schedule` event on attempt 1, produced gated commit `2e83fa0` on main under `BaseballOS Automation <baseballoshq@gmail.com>` with Source-SHA `71e0b89`, Validated-Tree `1c9d7dc`, Snapshot-ID 411, and data through August 13. That is the gated, tree-exact, machine-attributed commit the requirement names; the read-only deployment verification it also names is still outstanding, so #598 remains open and its recorded requirement is unchanged. Recorded the H-1 and H-5 through H-11 closeouts across PRs #650 through #659 in the Completion Log, and the H-12 reconciliation itself. Introduced a Decision status vocabulary — Permanent, Standing, Adopted, Amended, Superseded, Historical — so a narrowed decision no longer reads identically to one still in force, and applied it only where a later decision had already done that work. Amended D-013 accordingly: sole human authorship is scoped to engineering work, the governed generated-content publication job is its single approved machine exception under D-053, that identity is a publisher rather than a second author, and the no-AI-attribution rule is unchanged and absolute. Updated D-053's status from "not production-verified" to production-exercised on August 14. No Decision Ledger ID was added, weakened, renumbered, or removed; D-051 and D-052 stand unchanged; the approved sequence is preserved exactly; and the shadow, backfill, legacy-writer, and publication authority posture is untouched. |
