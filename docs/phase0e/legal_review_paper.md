# Phase 0E Legal Review Paper

## Executive Summary

This paper assembles the Phase 0E legal, editorial, provenance, and governance
record for human founder review. It is not a legal conclusion. It records what
BaseballOS currently knows, what remains unresolved, and what must be answered
before any evidence-backed public read can ship.

The evidence layer stores typed, provenance-carrying facts derived from guarded
source-backed rows. Its purpose is to make a read traceable to cited inputs,
rule definitions, completeness state, reason codes, and limitations instead of
depending on opaque labels or unsupported interpretation.

Composed reads sit above the evidence layer. They bundle stored evidence into
internal-only, componentized pitcher-day and team-day reads. A composed read
describes evidence completeness; it does not conclude health, role, quality,
readiness, manager intent, future usage, betting value, or public status.

Phase 0E defines and tests this internal read package. Its scope includes the
read contract, internal read builders, legacy-read reconciliation audit, QA
fixtures, editorial review guide, decision records, this paper, and the exit
report. Its scope excludes public evidence surfacing.

No public evidence surfacing occurs in Phase 0E.
The Phase 0B legal/source review gate remains CLOSED.
Any public evidence implementation must be a later, explicitly approved
post-0E roadmap phase.

## Current Classification Inventory

Verified live-rule classification counts:

Classification tally confirmation: PC: 44, EL: 9, IO: 4, PI: 8, Total: 65.

| Classification | Count | Meaning |
| --- | ---: | --- |
| PC | 44 | `PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE`: a rule may be considered for public use only after the Phase 0B legal/source review gate, an explicit surface phase, citation exposure, and the required language package all pass. |
| EL | 9 | `ELIGIBLE_PUBLIC_CANDIDATE_LATER`: a rule is not currently public-candidate. It can only be reviewed later if its named preconditions, floors, definitions, and language restrictions remain intact. |
| IO | 4 | `INTERNAL_ONLY_FOR_NOW`: a rule may support internal review, QA, or future analysis, but it is not eligible for public claims without additional production proof and review. |
| PI | 8 | `PERMANENTLY_INTERNAL`: a rule is a diagnostic, proxy, lock, or contract gap that must never become a public claim. |
| Total | 65 | Current registered evidence rules after the 0E-02 read-scoped roster membership rule. |

Separate Phase 0D decision-register items marked `DEFERRED` or `REJECTED` are
not live evidence rules in the 65-rule tally. They remain governance decisions,
not public-claim inventory.

The PC count is not publication approval. PC means "candidate with required
language and gates", not "ready to publish".

## Public Candidate Review

A rule qualifies as `PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE` only when all of
these are true:

- the rule is registered in the Phase 0D evidence registry;
- the classification registry assigns it PC;
- both global gates remain attached:
  `phase0b_legal_source_review` and `explicit_surface_phase`;
- the rule has a required language reference in
  `docs/phase0d/public_language_rules.md`;
- the rule is a descriptive, cited fact with visible definitions, thresholds,
  completeness state, reason codes, and limitations;
- the rule's cited rows are source-provenanced and auditable;
- unknown, withheld, partial, and conflict states remain visible instead of
  being converted into confident prose.

The following do not qualify:

- EL, IO, PI, deferred, or rejected items;
- composed reads themselves;
- headline states, labels, scores, grades, ranks, colors, or tiers;
- legacy public vocabulary rebranded as evidence-read states;
- live or in-progress source data;
- diagnostics, locked bands, source-readiness internals, or reconciliation
  audit findings;
- claims about health, role, team quality, manager intent, future use,
  predictions, betting, fantasy, or private knowledge;
- any claim whose citations cannot be exposed and resolved.

Provenance expectations:

- rule id and rule version are retained;
- cited source family, source table, source primary key, and cited fields are
  retained;
- source, sync run, timestamps, correction counters, and correction source are
  retained where the row family supports them;
- synthetic or missing-source provenance is explicit;
- recompute and supersession paths preserve auditability.

Descriptive language requirements:

- use dated, counted, past-tense facts;
- show thresholds beside flags;
- show window lengths beside counts;
- print required disclaimers;
- name what is unknown and why;
- never convert source absence into an affirmative claim.

Limitations:

- PC status does not clear legal, attribution, storage, redistribution, or
  product-display questions;
- PC rules remain stored with internal posture;
- PC rules cannot appear publicly unless a later surface branch adopts the
  exact language package and passes QA.

This paper does not recommend publication.

## Source Review

### MLB Stats API Usage

Known facts from the Phase 0B source audits and current repository:

- BaseballOS uses an MLB Stats API client with default base URL
  `https://statsapi.mlb.com/api/v1`, overridable by `MLB_API_BASE`.
- The client currently sends `BaseballOS/1.0 (Portfolio Analytics Tool)` as its
  HTTP client identifier.
- The client uses timeout and retry behavior for transient errors, including
  retry handling for 429 and 5xx responses.
- Current endpoint coverage includes teams, rosters, pitching game logs, player
  info, aggregate pitching stats, schedule, boxscore, linescore, play-by-play,
  and extracted game pitching lines.
- Completed-game evidence paths require final or usable game status before
  completed-game rows are stored.
- In-progress and live data are not approved for public evidence.

### Acquisition Posture

Phase 0B is an audit-and-decision phase. It did not adopt new sources into
production and did not approve public display. Existing guarded internal use of
Stats API-backed rows may continue, but richer public evidence remains blocked
by legal/source review and a later explicit surface phase.

Baseball Savant / Statcast, helper libraries, restricted/reference sites, and
paid providers are not adopted by Phase 0E.

### Storage Posture

Current storage favors normalized, typed rows rather than raw public payloads.
Source-backed rows carry source/provenance fields where their model supports
them. Correction-sensitive families retain first-seen, last-corrected,
correction count, correction source, sync run, stale or readiness state, and
dead-letter behavior where applicable.

Phase 0E does not add public storage. It adds internal composed-read tables and
internal legacy-read audit tables already introduced by earlier 0E branches.
This 0E-06 branch adds no migration and no storage behavior.

### Caching Posture

Known cache posture:

- dashboard snapshots are stored as internal publication artifacts for current
  public product behavior;
- source-readiness and postgame markers record processing state;
- final play-by-play foundation work normalizes stored facts and does not create
  a raw public-response cache;
- raw source caches remain legal/storage-review risks and are not approved here.

### Redistribution Posture

Redistribution rights for source-backed evidence, raw source rows, rendered
source-derived claims, public citations, screenshots, excerpts, and public API
payloads remain unresolved. Phase 0E does not redistribute source data and does
not expose evidence publicly.

### Attribution Posture

Attribution requirements remain unresolved. The current client identifier is an
operational identifier, not a confirmed public attribution solution. Phase 0E
does not decide whether a future public surface must display source
attribution, link to source terms, identify MLB Stats API, describe derived
storage, or separate BaseballOS analysis from source facts.

### Unresolved Legal Questions

The following questions remain open and are intentionally not answered here:

- What terms govern current and future MLB Stats API use?
- Is production storage of normalized Stats API-derived rows permitted?
- Is raw response storage or caching permitted?
- Is public display of derived claims from Stats API data permitted?
- Is redistribution through public pages, APIs, images, feeds, exports, or
  archives permitted?
- What attribution is required for public source-backed claims?
- Are there rate, caching, commercial-use, retention, or SLA restrictions?
- Are public roster, transaction, IL, and injury-description fields subject to
  additional restrictions?
- Can BaseballOS display cited source rows or source identifiers publicly?
- Can BaseballOS use Baseball Savant / Statcast, pybaseball, baseballr, or
  paid/reference sources for any public evidence path?
- Does a portfolio or commercial posture change any source rights analysis?
- What legal review record is required before any public evidence surface can
  ship?

## Public Claim Standards

Before any public evidence claim may exist, every standard below must pass.

| Standard | Requirement |
| --- | --- |
| Legal/source review | Phase 0B legal/source review must be explicitly reopened, completed, and recorded as approving the exact source family, storage posture, attribution posture, and public-display use. |
| Explicit surface phase | A new post-0E roadmap phase must explicitly authorize the public surface and its scope. |
| Evidence provenance | Every claim must resolve to registered rule id, rule version, cited rows, source family, source table, source key, cited fields, source, sync run, timestamps, and correction metadata where available. |
| Reproducibility | The claim must be deterministic from stored cited inputs and must rebuild after source correction, evidence invalidation, or supersession. |
| Descriptive wording | The claim must use the approved language package for the selected rule and stay descriptive, dated, counted, and past-tense. |
| Uncertainty handling | Unknown, withheld, partial, conflict, stale, missing, below-floor, or legally blocked states must remain visible and must not render as confident claims. |
| Limitations | Required disclaimers and limitations must travel with the claim, including source scope, sample window, threshold definition, and known missing fields. |
| Auditability | A reviewer must be able to trace the public claim to the stored evidence, source rows, computation trace, decision record, and tests. |
| Freshness | The claim must show or inherit product date, data-through date, slate coverage, source readiness, and stale/degraded state. |
| Public isolation | The claim must not add hidden public payload fields, private source payloads, or unsupported citation mechanisms. |

## Editorial Standards

Source references:

- `docs/phase0e/editorial_review_guide.md`
- `docs/phase0e/headline_state_decision.md`
- `docs/phase0e/member_read_rollup_decision.md`
- `docs/phase0d/public_language_rules.md`
- `docs/phase0d/language_rules.md`

Allowed wording summary:

- cite the rule and stored facts first;
- use dated and counted facts;
- use "recorded", "stored", "listed", "appeared", "entered", "exited",
  "used", "flagged", "not flagged", "unknown", and "withheld" only when the
  cited rule supports that wording;
- render exact roster membership forms from the public language rules;
- state what is missing or withheld;
- preserve required disclaimers verbatim.

Forbidden wording summary:

- betting, odds, fantasy, projection, or prediction framing;
- health certainty or private injury interpretation;
- manager-intent certainty;
- public fatigue, confidence, trust, or pressure scores;
- score, grade, rank, percentile, color, tier, or headline-state framing;
- role-title assertions unless a later branch explicitly approves sourced
  official metadata;
- availability, readiness, quality, depth, and team-quality conclusions from
  evidence completeness.

Quoted legacy wording:

- "Fresh"
- "Stretched"
- "Vulnerable"
- "Available"
- "Monitor"
- "Limited"
- "Avoid"
- "Unavailable"
- "Trust Arm"
- "Bridge Arm"
- "Coverage Arm"
- "Depth Arm"
- "Limited Read"

The terms above may be quoted as legacy display vocabulary for audit and
decision records. They are not evidence-read states and are not approved public
evidence wording.

Structural rules:

- component-first remains the architecture of record;
- no headline state may be implemented before an explicit post-0E-06 founder
  decision;
- the only possible post-0E headline family is single-axis, printed-threshold,
  registered-definition descriptive states in the `outing_clean` mold;
- member-read rollup is closed unless every named reopening precondition exists;
- components cite evidence objects only, not other composed reads;
- no read-citation table, read foreign key, or `allowed_read_types` registry
  support exists in Phase 0E.

## Risk Review

| Risk | Description | Current mitigation | Remaining open questions |
| --- | --- | --- | --- |
| Legal | Source rights for storage, public display, public citations, and redistribution are unresolved. | Phase 0B legal/source gate remains CLOSED; Phase 0E adds no public surface. | What exact source terms, rights, attribution, retention, and public-display permissions apply? |
| Licensing | External source families may have use limits or attribution requirements that are not documented in the repo. | Source rows remain internal; public display posture remains blocked. | Which sources, if any, can support commercial or public product use? |
| Provenance | A public claim without exposed citations would be hard to audit. | Evidence objects store rule ids, citations, computation trace, completeness, and limitations; composed reads cite evidence internally. | What citation shape is legally safe and user-readable for public surfaces? |
| Stale data | Public claims can mislead if source data, slate coverage, or snapshots are stale or partial. | Source readiness, slate coverage, marker lifecycle, and unknown handling fail closed where implemented. | Which freshness display and stale-state rules are mandatory for future public claims? |
| Attribution | Public source attribution requirements are unknown. | No public evidence attribution is shipped in Phase 0E. | What attribution text, links, placement, and source separation are required? |
| Ambiguity | Schedule status, roster state, transactions, inherited traffic, and source corrections can be ambiguous. | Unknown, partial, conflict, and withheld states are represented rather than guessed. | Which ambiguity classes must suppress public claims completely? |
| Editorial misuse | Descriptive evidence can be rewritten into prediction, health, role, or manager-intent claims. | Language rules, editorial guide, and QA harness ban overclaiming patterns. | What human review workflow is required before publishing any future wording? |
| Headline misuse | A single headline state can hide component limitations and turn completeness into meaning. | Headline-state decision is DEFER-WITH-STRUCTURE; no implementation exists. | Should any single-axis headline family exist after 0E, and under what thresholds? |
| Completeness misuse | Complete internal reads could be mistaken for public conclusions. | Read definitions state that completeness is evidence completeness only; no public payload changes occur. | How should future UI explain completeness without implying status, quality, or use-state? |

## Decision Matrix

No option is selected or endorsed by this paper.

| Option | Advantages | Disadvantages | Dependencies | Unresolved questions |
| --- | --- | --- | --- | --- |
| Option A: Keep evidence internal permanently | Lowest legal and attribution exposure; preserves current public behavior; internal QA and reconciliation can still improve quality. | Public users cannot inspect evidence; product trust may remain limited by opaque labels; future evidence work has less visible payoff. | Continue internal governance, QA, and reconciliation only. | Is internal-only evidence sufficient for BaseballOS product goals? |
| Option B: Expose only selected evidence-backed claims | Stronger public trust for a small set of checked facts; easier to gate and QA; keeps risky families withheld. | Requires legal/source approval, citation design, public copy review, UI work, and support burden; selected claims may feel incomplete. | Legal/source review, explicit surface phase, public citation design, editorial approval, QA, freshness display. | Which PC rules, if any, are legally and editorially safe enough to expose? |
| Option C: Expose broader evidence layer later | Maximum transparency if fully governed; could support deeper public methodology and future user workflows. | Highest legal, licensing, attribution, UX, maintenance, stale-data, and editorial risk; large surface area for misuse. | All Option B dependencies plus broader source clearance, scalable citation UX, expanded QA, and public methodology rewrite. | Can the product explain broad evidence without overwhelming users or creating unsupported conclusions? |

## Founder Decision Checklist

Every item below must be answered YES before public evidence can ship.

- [ ] YES - Legal review approves the exact source families, source terms,
  storage posture, public display, redistribution posture, and commercial/use
  posture for the proposed surface.
- [ ] YES - Source review confirms acquisition path, reliability, correction
  behavior, rate/caching posture, and fail-closed behavior.
- [ ] YES - Provenance review confirms every public claim can expose or trace
  rule id, version, cited rows, source family, source keys, cited fields,
  computation trace, completeness, reason codes, and limitations.
- [ ] YES - Attribution review confirms required public attribution text,
  placement, links, and source/analysis separation.
- [ ] YES - Editorial review approves the exact wording package and confirms no
  forbidden language, role claim, health claim, prediction, betting/fantasy
  claim, score, grade, rank, or manager-intent claim appears.
- [ ] YES - QA completion covers synthetic fixtures, live-like edge cases,
  stale/partial/unknown/conflict/withheld states, source corrections, and public
  rendering behavior.
- [ ] YES - Reproducibility review confirms claims rebuild deterministically
  from stored inputs and react correctly to source correction or supersession.
- [ ] YES - Documentation review updates methodology, limitations, data trust,
  source posture, freshness, and decision records.
- [ ] YES - Product need review confirms the public surface solves a user need
  that cannot be met by internal evidence alone.
- [ ] YES - Founder approval explicitly authorizes a post-0E public evidence
  phase and names the allowed scope.

## Phase 0E Exit Summary

| Branch | Delivered |
| --- | --- |
| 0E-01 | Created the composed-read contract, registry, validation rules, internal-only posture, component/citation tables, completeness calculus, and no-headline-state rule. |
| 0E-02 | Added `reliever_daily_read` v1, its internal read builder, sync integration, recompute behavior, and the read-scoped `pitcher_roster_membership_context` evidence rule. |
| 0E-03 | Added `team_daily_read` v1, team-day population rules, component contract, contributor denominator disclaimer preservation, and explicit member-read rollup deferral. |
| 0E-04 | Added the internal legacy-read reconciliation audit, audit tables, neutral divergence categories, skip semantics, report renderer, sync switch, and escalation policy. |
| 0E-05 | Added synthetic QA scenarios, read review packet renderer, editorial review guide, headline-state decision, member-read rollup decision, decision register, and classification/contract freeze checks. |
| 0E-06 | Adds this legal review paper, the Phase 0E exit report, final README/roadmap notes, and documentation invariant tests. |

Phase 0E exits with internal reads, QA, reconciliation, editorial decisions, and
legal/source governance assembled for human review. It does not exit with public
evidence surfacing approval.

## Remaining Work

Public evidence surfacing is NOT part of Phase 0E.

Any future public evidence implementation should occur only in a new post-0E
roadmap phase after founder approval, legal/source review, attribution review,
editorial approval, QA, public citation design, methodology updates, and product
scope approval.
