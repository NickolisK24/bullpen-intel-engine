# BaseballOS V4 Roadmap: Foundation Integrity & Bullpen Evidence

This is the canonical execution roadmap for BaseballOS V4. The foundation
sequence starts with Phase 0A — Pipeline Integrity & Data Trust before broader
daily, follow-team, share, digest, creator, or monetization work.

V4 is a foundation-first, evidence-first pass. It replaces the earlier
feature-heavy V4 direction with a stricter product rule:

Use as much relevant baseball data as possible.
Interpret it through a bullpen lens.
Show the evidence clearly.
Avoid unsupported claims.

Trust first. Evidence second. Interpretation third. Retention only after the
read is worth returning to.

V4 is not primarily a Follow My Team, Daily Home, share-card, digest,
creator-mode, or monetization phase. Those product loops remain important, but
they are deferred until the foundation and evidence layer are strong enough to
support them without overclaiming.

BaseballOS should not be smaller because it is focused. BaseballOS should be
deeper because it is focused. BaseballOS should not compete by having fewer
numbers. BaseballOS should compete by making the right bullpen numbers mean
something.

This document records order, boundaries, decision rules, evidence requirements,
and phase gates. It does not authorize product-code changes by itself. Each
implementation phase must still ship through its own scoped branch, review,
validation, and commit.

## Required Reading: Product Vision Specification

[`docs/product/product-vision-specification.md`](../product/product-vision-specification.md)
is the canonical page-level product vision — what each public page exists to
do, what belongs on it, what never belongs on it, and what "finished" means.
This roadmap records WHAT gets built and in what order; the vision records what
each page is becoming. Read it before designing any surface work.

Before implementation begins, every future phase (0I onward, and Phases 1–4)
should be checked against the vision:

- **Page mission** — the work serves the target page's stated mission and does
  not quietly change it.
- **One question per page** — the page still owns exactly one user question,
  and the work does not make two pages answer the same question.
- **Altitude discipline** — the page stays at its single altitude (League /
  Team / Arm / Meta) and links across altitudes instead of mixing them.
- **The read contract** — every claim-bearing surface keeps
  State → Why → Evidence → Freshness → Limitations, in that order.
- **The refusal** — no predictions, no betting language, no rankings, no
  black-box outputs, and no new slot where such a verdict could ever live.

A phase that cannot pass these checks should be redesigned before it is
implemented, not patched after.

## V4 Operating Thesis

BaseballOS should become the best public bullpen intelligence platform by being
narrow in scope and deep in evidence.

The platform should not try to become FanGraphs, Baseball Savant, Baseball
Reference, or a general baseball analytics site. Those platforms cover the
entire sport. BaseballOS should specialize in one area:

What is the real state of every MLB bullpen today, what changed, and what
evidence supports the read?

V4 is no longer primarily a retention-feature roadmap. V4 is a foundation and
evidence roadmap. The goal is not to make BaseballOS flashier. The goal is to
make BaseballOS more trustworthy, more useful, and more baseball-specific.

BaseballOS becomes useful when it can explain bullpen context from enough
relevant public baseball evidence that the read is checkable. V4 should make
the product stronger by improving the data foundation, reliever evidence layer,
pitch-trend feasibility, roster context, starter exposure context, methodology,
and trust posture before broadening into retention or monetization surfaces.

The product should stay descriptive, checkable, and baseball-native. It should
make bullpen context easier to understand without turning into picks,
predictions, fantasy advice, betting advice, private injury claims, or certainty
about manager decisions.

## V4 North Star

V4 should make BaseballOS the clearest public evidence layer for MLB bullpen
context.

The user should be able to inspect a bullpen read and understand:

- what happened recently;
- which relievers carried the work;
- whether the outing was clean, stressful, heavy, efficient, or messy;
- how pitch count, command, strikeouts, walks, velocity, and pitch usage compare
  to recent baseline;
- whether the team is leaning on the same arms repeatedly;
- whether the bullpen state is driven by workload, performance trend, roster
  pressure, starter exposure, or a combination;
- how current the evidence is;
- what changed from the prior trusted state;
- which roster or starter-context signals matter;
- which pitch-level or pitch-trend signals are available;
- what BaseballOS cannot know.

V4 should move BaseballOS from label-first bullpen availability to
evidence-first bullpen intelligence.

## Core Product Philosophy

BaseballOS should compete by being narrow and deep. Every piece of data should
be evaluated through bullpen questions:

- Did this reliever work recently?
- Was the outing clean or stressful?
- Was the pitch count light, normal, or heavy?
- Did command look sharp or shaky?
- Did velocity hold, dip, or jump?
- Did pitch mix change?
- Did strikeout/walk profile shift?
- Is he being leaned on repeatedly?
- Is he fresh but not trusted?
- Is he available but not sharp?
- Is the team thin because of workload, injuries, roster churn, starter
  exposure, or late-game concentration?
- What changed since yesterday?
- What evidence supports that change?

BaseballOS should not compete by having fewer numbers. It should compete by
organizing the right numbers around bullpen questions.

## What V4 Is

V4 is:

- a foundation integrity pass;
- a data completeness pass;
- a reliever evidence pass;
- a pitch-trend feasibility and integration pass;
- a bullpen read quality pass;
- a team bullpen context pass;
- a data trust and methodology pass;
- a measured step toward a stronger daily product.

V4 should make the current bullpen intelligence more complete, more
explainable, more honest about missing evidence, and more useful as the base for
future daily product loops.

## What V4 Is Not

V4 is not:

- a betting product;
- a prediction product;
- a fantasy advice product;
- a broad MLB analytics dashboard;
- a generic player stat site;
- a social product;
- a newsletter product;
- a monetization product;
- a pro workflow product;
- a visual polish sprint;
- a share-card sprint;
- a follow-team retention sprint.

## Non-Negotiable Guardrails

- No betting advice.
- No picks.
- No fantasy start/sit claims.
- No prediction claims.
- No manager-intent certainty.
- No private injury claims.
- No unsupported health claims.
- No unknown values converted into zeros or plausible values.
- No stale, sample, fallback, partial, or unsafe data shown as current.
- No complete-sounding reads from incomplete slates.
- Freshness, data-through dates, slate coverage, and limitations must stay
  visible.
- Roadmap work must not broaden API, data, scoring, or route behavior unless
  that phase explicitly authorizes it.

Allowed and encouraged evidence includes:

- last outing results;
- pitch count;
- outs recorded;
- batters faced;
- hits, runs, walks, strikeouts, and home runs;
- strike rate;
- K/BB;
- pitch mix;
- average velocity by pitch type;
- last outing vs last 7 comparison;
- command trend;
- velocity trend;
- workload trend;
- roster context;
- starter exposure context;
- usage concentration;
- clean, messy, heavy, or efficient outing labels, when evidence-backed.

## Audience Priority

V4 should optimize in this order:

1. Users who want a clear public bullpen read backed by visible evidence.
2. Analysts, writers, and creators who need fast, checkable bullpen context.
3. Team-focused users who want one club's bullpen picture.
4. Power users who may later want alerts, digests, exports, or premium
   workflow.

The first user should never need to understand BaseballOS internals. The power
user should be able to inspect evidence, freshness, and limitations when they
need them.

## Must-Have Data Categories

These categories define the minimum evidence direction for V4. They do not
claim that every source is already present, licensed, complete, or safe to show.
Unknown values stay unknown until validated.

### Appearance Data

- game date
- team
- opponent
- pitcher
- inning entered
- outs
- batters faced
- pitches
- strikes
- balls if derivable
- hits
- runs
- earned runs
- walks
- strikeouts
- home runs
- inherited runners if available
- inherited runners scored if available

### Workload Data

- last outing pitch count
- last 3 days usage
- last 7 days usage
- last 14 days usage
- back-to-back usage
- 3-in-4
- 4-in-6
- multi-inning appearances
- high-pitch outings
- repeated leverage usage if safely derivable

### Performance / Command Data

- K
- BB
- K/BB
- strike percentage
- walks last outing vs last 7
- strikeouts last outing vs last 7
- baserunners allowed
- clean vs traffic-heavy appearance

### Pitch-Level / Trend Data

- pitch type
- average velocity by pitch type
- last outing velocity by pitch
- last 7 velocity baseline
- velocity delta
- pitch mix
- pitch mix delta
- strike rate
- whiff/swinging-strike proxy if available

### Roster Data

- active roster
- IL
- 40-man
- optioned
- inactive
- promoted
- activated
- traded
- claimed
- unknown status

### Starter Exposure Data

- starter innings last 7
- starter innings last 14
- starts under 5 innings
- bullpen innings burden
- short-start pressure

## V4 Roadmap Order

1. Canon roadmap revision
2. Phase 0A — Pipeline Integrity & Data Trust
3. Phase 0B — Data Source Inventory & Acquisition Strategy
4. Phase 0C — Reliever Appearance Evidence Layer
5. Phase 0D — Pitch-Level / Pitch-Trend Feasibility Layer
6. Phase 0E — Bullpen Read Quality Model
7. Phase 0F — Pitcher Detail Evidence Surface
8. Phase 0G — Team Bullpen Evidence Surface
9. Phase 0H — Trusted Snapshot + What Changed Foundation
10. Phase 0I — Roster Availability Context
11. Phase 0J — Starter Exposure Context
12. Phase 0K — Methodology, Limitations, and Data Trust Rewrite
13. Phase 0L — Analytics Event Alignment
14. Phase 1 — Daily Bullpen Home
15. Phase 2 — Follow My Team
16. Phase 3 — Shareable Cards
17. Phase 4 — Digest / Creator / Pro Validation

Only items 1 through 13 are true V4 must-do work. Items 14 through 17 are
allowed only after the foundation is sound.

## Detailed Phase Plan

### 1. Canon roadmap revision

Goal: replace the earlier feature-heavy V4 roadmap with the foundation-first,
evidence-first V4 direction.

Scope:

- Preserve this canonical roadmap path:
  `docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md`.
- Establish the new V4 product rule, scope, guardrails, data categories, phase
  gates, and deferred features.
- Update existing documentation index labels without creating a new navigation
  system.
- Do not change product code.

Exit criteria:

- The roadmap exists at the canonical path.
- The title is `BaseballOS V4 Roadmap: Foundation Integrity & Bullpen Evidence`.
- The product rule appears verbatim.
- Phase 0A appears before Daily Bullpen Home, Follow My Team, Shareable Cards,
  Digest, Creator Mode, and Monetization.
- Lightweight documentation validation passes.

### 2. Phase 0A - Pipeline Integrity & Data Trust

Goal: make the data pipeline trustworthy enough to support stronger public
bullpen evidence.

Scope:

- Audit freshness, data-through dates, slate coverage, and write timing.
- Confirm stale, sample, fallback, partial, and unsafe states fail closed or
  visibly degrade.
- Ensure unknown values remain unknown.
- Confirm correction paths can update stored data without creating hidden
  contradictions.
- Fix or fail-close critical pipeline risks:
  - stat corrections not propagating;
  - new pitchers not created by sync;
  - missing pitch counts stored as zero;
  - data-through dates without slate completeness checks;
  - partial syncs appearing healthy or current;
  - no final-status filter on daily game-log paths;
  - empty final boxscores marked processed forever;
  - manual sync overlap risk;
  - non-atomic daily sync stages;
  - What Changed using partial-day baselines;
  - mixed-day or partial league states appearing complete;
  - host-local date handling instead of product timezone.
- Add pipeline validation rules, snapshot completeness checks, sync health
  states, correction propagation strategy, new pitcher detection, partial sync
  degraded states, standardized product timezone handling, and an internal
  pipeline health report.

Exit criteria:

- Public reads are backed by validated data.
- Unknown values stay unknown.
- Partial states visibly degrade or fail closed.
- No complete-sounding read can appear from an incomplete slate.
- Every public read can explain what games are included and whether validations
  passed.
- No green or healthy trust state appears for incomplete data.

### 3. Phase 0B - Data Source Inventory & Acquisition Strategy

Goal: identify which public or permissible data sources can support the V4
evidence layer.

Scope:

- Inventory existing data fields, source authority, refresh cadence, gaps, and
  licensing or access constraints.
- Decide which appearance, workload, pitch-level, roster, and starter-exposure
  fields are available now, derivable later, unavailable, or unsafe.
- Document acquisition strategy before adding broad new surfaces.
- Inventory MLB Stats API game logs, boxscores, play-by-play, probable
  pitchers, transactions, rosters, injuries/IL, pitch-level data, pitch type,
  velocity, pitch usage, strike/ball events, whiff or swinging-strike
  indicators, inning or appearance context, inherited runners, leverage proxy
  if available, public roster status, and starter workload.
- For each category record source, endpoint or retrieval path, availability,
  update timing, historical coverage, reliability, legal or usage concern, cost,
  implementation complexity, and whether it belongs in V4, post-V4, or backlog.

Exit criteria:

- Each must-have data category has a source-status decision.
- Unsafe or unavailable fields are explicitly marked as unavailable.
- Future acquisition work is prioritized by bullpen evidence value.
- The written acquisition matrix answers what can be ingested now, what can be
  derived from current data, what requires pitch-level ingestion, what should
  wait, what is unavailable or unsafe, and what is most valuable for bullpen
  intelligence.

### 4. Phase 0C - Reliever Appearance Evidence Layer

Goal: give BaseballOS reliable reliever-level evidence for what happened in
recent appearances.

Scope:

- Ingest and normalize reliever appearance fields.
- Track last outing evidence and recent appearance baselines.
- Make new reliever ingestion automatic.
- Preserve corrections and updates.
- Store and expose, when available and validated: game date, opponent, team,
  pitcher, game status, inning entered, outs recorded, batters faced, pitches,
  strikes, balls if derivable, hits, runs, earned runs, walks, strikeouts, home
  runs, inherited runners, inherited runners scored, rest days before outing,
  back-to-back status, 3-in-4 status, 4-in-6 status, outing leverage proxy, and
  appearance role proxy.
- Create evidence-backed descriptors such as clean outing, traffic-heavy
  outing, command-stress outing, heavy workload, efficient outing, short
  appearance, multi-inning coverage, back-to-back usage, repeated usage,
  leverage-used, and mop-up or low-pressure proxy if safely derivable.

Exit criteria:

- New relievers are ingested automatically.
- Corrections can update stored data.
- Last outing evidence is available for relievers.
- Recent appearance baselines are available.
- For every reliever in the public bullpen view, BaseballOS can answer what he
  did last time out, how heavy the outing was, whether it was clean or messy,
  whether command was an issue, whether he was used recently or repeatedly, and
  what evidence supports the current read.

### 5. Phase 0D - Pitch-Level / Pitch-Trend Feasibility Layer

Goal: determine which pitch-level and pitch-trend signals can safely support
bullpen reads.

Scope:

- Evaluate pitch type, velocity, pitch mix, strike rate, and whiff or
  swinging-strike proxy availability.
- Compare last outing signals against recent baselines only when the sample and
  source are safe.
- Document what cannot be supported yet.
- Investigate and, where feasible, implement pitch type, average velocity by
  pitch type, max velocity, velocity last outing, velocity last 7 appearances,
  velocity delta, pitch mix last outing, pitch mix last 7 appearances, pitch
  usage delta, strike rate, ball rate, swinging strikes or whiffs if available,
  called strikes if available, first-pitch strike rate if derivable, and zone,
  chase, or contact only if reliable and available.
- Prioritize average velocity by pitch type, last outing velocity vs last 7,
  pitch mix last outing vs last 7, strike rate last outing vs last 7, K/BB last
  outing vs last 7, and whiff or swinging-strike proxy if available.

Exit criteria:

- Pitch-level feasibility is documented.
- Safe pitch-trend fields have source, cadence, sample, and limitation notes.
- Unsupported pitch claims remain absent from public reads.
- Each pitch-trend category is classified as supported now, derivable now,
  supported later, unsupported or unavailable, or not worth V4.
- Implemented pitch trends show source, sample window, last outing value, last 7
  appearance baseline, direction of change, and whether the sample is too small.

### 6. Phase 0E - Bullpen Read Quality Model

Goal: improve how BaseballOS turns evidence into readable bullpen context.

Scope:

- Review the current fresh, stretched, vulnerable, pressure, recovery, workload,
  and clean-options reads against the new evidence layer.
- Ensure every public read can point to evidence rather than only a label.
- Separate descriptive context from prediction or advice.
- Create evidence-based public read components: workload read, outing quality
  read, recent trend read, command read, velocity read where available, roster
  pressure read, starter exposure read, trust or role context read, and data
  confidence or completeness read.
- Each reliever read should have current state, evidence summary, last outing,
  recent baseline, reason for state, data freshness, and limitations if any.
- Each team read should include bullpen state, key arms, who worked last night,
  who worked clean, who worked messy, who is workload-stretched, who is trending
  down or up where supported, who is available but not necessarily clean,
  roster/depth context, starter exposure context, and slate/data completeness.

Exit criteria:

- Public team reads explain evidence, not only labels.
- Model language avoids unsupported certainty.
- Missing evidence reduces confidence or withholds the read.
- A BaseballOS read can answer what the label is, what happened, what changed,
  what evidence supports it, what is unknown, and why a baseball person should
  care.

### 7. Phase 0F - Pitcher Detail Evidence Surface

Goal: let users inspect what happened for an individual reliever and what
changed.

Scope:

- Present last outing, recent workload, command, traffic, and pitch-trend
  evidence when supported.
- Keep data freshness, source limits, and unknown fields visible.
- Avoid ranking, advice, fantasy, or betting interpretation.
- Surface sections should include Current Read, Why This Read Exists, Last
  Outing, Last 7 Appearances, Workload Trend, Command Trend, Velocity / Pitch
  Mix Trends, Usage Pattern, and Data Trust.

Exit criteria:

- Pitcher detail surfaces explain what happened and what changed.
- Unknown or unavailable fields remain visibly unknown or omitted.
- The surface strengthens trust in team-level reads.
- A user can click any reliever and understand what he did last outing, how it
  compares to recent baseline, whether he looked clean or stressed, whether
  workload is the main issue, whether performance trend is part of the read,
  and what BaseballOS knows and does not know.

### 8. Phase 0G - Team Bullpen Evidence Surface

Goal: make team bullpen context explainable through reliever evidence, roster
context, workload, and starter exposure.

Scope:

- Connect team-level reads to visible reliever evidence.
- Show workload distribution, availability groups, recent appearance pressure,
  and data limitations.
- Keep the surface focused on bullpen context, not broad team analytics.
- The team surface should answer what the bullpen has left today, who carried
  the workload recently, which arms are clean, which arms are stretched, which
  arms are fresh but not necessarily leverage options, whether pressure comes
  from reliever workload, starter exposure, roster depth, or a combination, and
  what changed since yesterday.

Exit criteria:

- Team reads explain evidence, not only labels.
- Team bullpen context remains baseball-readable.
- Missing or partial evidence degrades clearly.

### 9. Phase 0H - Trusted Snapshot + What Changed Foundation

Goal: build change detection on trusted snapshots rather than raw or partial
states.

Scope:

- Compare current trusted reads against the prior trusted read.
- Track availability, workload, roster, starter-exposure, and evidence-layer
  changes only when comparable.
- Withhold change reads when freshness, slate coverage, or source alignment is
  not safe.
- Build trusted daily snapshots, snapshot completeness validation, snapshot
  comparability rules, no comparisons against partial days, no comparisons
  across incompatible game windows, and change detection for workload,
  availability state, outing quality, key reliever usage, velocity or pitch
  trend where supported, roster status, starter exposure, and team-level burden.

Exit criteria:

- What Changed can explain evidence-backed movement.
- Snapshot comparison fails closed when confidence is not warranted.
- Freshness and data-through details stay visible.
- BaseballOS can safely say what changed, why it changed, which data supports
  it, whether the comparison is complete, and whether no meaningful change
  occurred.

### 10. Phase 0I - Roster Availability Context

Status: Complete.

Goal: explain public roster pressure without private injury or health claims.

Scope:

- Use public roster, IL, active, inactive, optioned, promoted, activated,
  traded, claimed, and unknown-status context.
- Separate absence of a public flag from health certainty.
- Keep roster evidence tied to bullpen availability, not general roster
  analysis.
- Explain active roster status, IL status, optioned or inactive status, 40-man
  but not active status, newly promoted status, traded or claimed status,
  activated status, roster status codes, and public depth pressure.

Exit criteria:

- Roster pressure is public-data backed.
- The product never implies private medical knowledge.
- Unknown roster status remains unknown.
- BaseballOS can explain whether the bullpen is carrying depth pressure,
  whether active arms are paying the price for missing depth, when roster data
  is stale or incomplete, and what the product can and cannot know.

### 11. Phase 0J - Starter Exposure Context

Status: Complete.

Goal: explain recent starter-length pressure on bullpen workload without
predicting tonight.

Scope:

- Use starter innings over recent windows, starts under 5 innings, bullpen
  innings burden, and short-start pressure.
- Connect starter exposure to bullpen workload only as recent context.
- Avoid projecting upcoming starter performance.
- Include completed-game and recent-start context such as starter innings last 7
  days, starter innings last 14 days, starts under 5 innings, bullpen innings
  last 7 days, bullpen innings last 14 days, opener or bulk-game indicators if
  safely derivable, and team-level coverage burden.

Exit criteria:

- Starter exposure is recent-context based, not predictive.
- The read helps users understand why a bullpen may be stretched.
- Evidence and freshness remain visible.
- BaseballOS can explain whether bullpen stress is driven by reliever usage,
  starter exposure, roster depth, or a combination.
- Final closeout keeps the Team Board as the canonical public surface, links the
  starter-length read into Recent Bullpen Work receipts, and keeps Today as a
  teaser instead of a complete starter-exposure read.

### 12. Phase 0K - Methodology, Limitations, and Data Trust Rewrite

Goal: make the V4 evidence layer understandable, auditable, and honest.

Scope:

- Rewrite methodology around appearance evidence, workload, pitch-trend
  feasibility, roster context, starter exposure, unknown handling, and
  fail-closed behavior.
- Document limits plainly.
- Keep public copy descriptive and baseball-native.
- Update public pages for data sources, update schedule, corrections, slate
  completeness, pitch count handling, roster status handling, appearance
  evidence, pitch-level trend availability, unknown values, partial sync
  behavior, what BaseballOS does not know, and why BaseballOS is descriptive,
  not predictive.

Exit criteria:

- Methodology explains the evidence layer clearly.
- Limitations describe what BaseballOS does not know.
- Data trust surfaces match the V4 foundation.
- A skeptical user can understand where the data comes from, what BaseballOS
  validates, what metrics are included, what metrics are not included, how
  unknown data is handled, and why a read is safe to trust.

### 13. Phase 0L - Analytics Event Alignment

Goal: align analytics with V4 evidence-first behavior without changing baseball
claims.

Scope:

- Review current event names and properties against the foundation-first V4
  order.
- Measure whether users inspect evidence, freshness, pitcher detail, team
  bullpen context, and trusted change reads.
- Avoid collecting sensitive personal data.
- Track pitcher evidence opens, last outing section views, pitch trend section
  views, team evidence section views, data trust opens, methodology opens,
  stale or partial state interactions, feedback clicks, team read inspections,
  reliever read inspections, and What Changed evidence opens once built.

Exit criteria:

- Analytics measure evidence use and product comprehension.
- Event alignment does not create new product promises.
- Metrics support future daily and follow-team decisions.
- BaseballOS can measure whether users inspect evidence, which evidence
  sections matter, whether users care about pitcher-level trends, whether data
  trust surfaces are used, and which team or reliever reads draw attention.

### 14. Phase 1 - Daily Bullpen Home

Goal: make the home page a daily bullpen read only after the foundation and
evidence layer can support it.

Scope:

- Prioritize league-wide bullpen picture, trusted change reads, and data
  freshness.
- Surface team context when evidence is strong enough.
- Keep empty and degraded states honest.

Exit criteria:

- The home page answers what matters today with evidence-backed context.
- No stale, partial, or unsafe state appears current.
- The home page remains descriptive, not predictive.

### 15. Phase 2 - Follow My Team

Goal: let a user orient the daily read around one club after team bullpen
evidence is strong enough.

Scope:

- Add a lightweight follow or preferred-team flow.
- Use the preference to orient evidence-backed daily and team reads.
- Avoid personalized advice or prediction framing.

Exit criteria:

- A user can choose and change a followed team.
- Followed-team context uses the same evidence and trust rules.
- The feature does not imply personalized betting, fantasy, or roster advice.

### 16. Phase 3 - Shareable Cards

Goal: make BaseballOS context shareable without losing evidence or freshness.

Scope:

- Create compact cards for fresh, stretched, vulnerable, or changed bullpen
  reads only when evidence is strong enough.
- Include evidence cues, freshness, and a path back to fuller context.
- Avoid sensational or unsupported framing.

Exit criteria:

- Shared cards communicate read, evidence cue, freshness, and limitations.
- Cards link back to the fuller BaseballOS context.
- Shared artifacts remain descriptive.

### 17. Phase 4 - Digest / Creator / Pro Validation

Goal: evaluate delivery, creator, and power-user workflows after BaseballOS has
a stronger evidence foundation.

Scope:

- Test digest, creator, analyst, and pro workflows only after foundation gates
  are met.
- Keep demand validation separate from shipped product promises.
- Preserve descriptive trust posture.

Exit criteria:

- Future delivery or pro direction is based on evidence and usage.
- No monetization promise is made before validation.
- Power-user workflows do not weaken public trust.

## Explicit Deferrals

The following are deferred until the foundation and evidence layer are strong:

- full newsletter system;
- pro beta waitlist;
- monetization validation;
- creator/media kit page;
- broad content archive;
- team follow accounts;
- push notifications;
- paid tier;
- player comparison tools;
- leaderboards;
- export products;
- public API;
- general MLB dashboards;
- fantasy-specific tooling;
- betting-adjacent features;
- broad team analytics beyond bullpen context.

## Phase Gate Rules

Do not move past foundation until:

1. Public reads are backed by validated data.
2. Unknown values stay unknown.
3. Partial states visibly degrade or fail closed.
4. New relievers are ingested automatically.
5. Corrections can update stored data.
6. Last outing evidence is available for relievers.
7. Recent appearance baselines are available.
8. Pitch-level feasibility is documented.
9. Team reads explain evidence, not only labels.
10. Pitcher detail surfaces explain what happened and what changed.
11. Roster pressure is public-data backed.
12. Starter exposure is recent-context based, not predictive.
13. Methodology explains the evidence layer clearly.

## Metrics and Review Cadence

V4 should be reviewed through evidence quality and user comprehension before it
is reviewed through retention or monetization.

Primary foundation metrics:

- source coverage by data category;
- freshness and data-through accuracy;
- slate coverage completeness;
- unknown-field preservation;
- fail-closed behavior count and reason;
- reliever appearance coverage;
- recent baseline availability;
- pitch-level feasibility status;
- roster context coverage;
- starter exposure coverage;
- methodology and trust-surface completeness.

Future product metrics, after foundation gates:

- daily active readers;
- returning readers;
- evidence-surface inspection;
- followed-team adoption;
- team-page visits;
- What Changed engagement;
- share-card clicks;
- digest opt-ins;
- feedback submissions;
- pro or creator workflow interest.

Review cadence:

- Review data trust after each foundation phase.
- Review the full roadmap order after each major evidence milestone.
- Keep this document current when scope, order, status, or guardrails change.
- Do not skip trust review for speed.

## Living Roadmap Status Table

| Order | Phase | Status | Notes |
| --- | --- | --- | --- |
| 1 | Canon roadmap revision | Complete | Replaces the feature-heavy V4 roadmap with the foundation-first, evidence-first direction. |
| 2 | Phase 0A - Pipeline Integrity & Data Trust | Complete | Branches phase-0a/01 through phase-0a/08 have been merged via PRs #354-#359 and #364-#365; follow-up slate-coverage publish, slate diagnostics, and postgame blocker fixes merged via PRs #360-#363. |
| 3 | Phase 0B - Data Source Inventory & Acquisition Strategy | Complete | Branches 0B-01 through 0B-07 completed; acquisition strategy and matrix added; Phase 0C sequencing plan is the next step. |
| 4 | Phase 0C - Reliever Appearance Evidence Layer | Complete | Branches 0C-01 through 0C-08 completed; foundation report added and source readiness coverage integrated before public evidence interpretation. |
| 5 | Phase 0D - Pitch-Level / Pitch-Trend Feasibility Layer | Complete | Evidence contract, families, classification registry, decision register, language packages, and exit report completed via PRs #381-#388 plus PR #389. |
| 6 | Phase 0E - Bullpen Read Quality Model | Complete | Read contract, reliever/team daily reads, legacy-read reconciliation audit, read QA, editorial decisions, and 0E-06 legal review paper and exit report are the internal-only Phase 0E package; public surfacing remains blocked by legal/source review and a later surface phase. |
| 7 | Phase 0F - Pitcher Detail Evidence Surface | Complete | Internal pitcher evidence review, public backend recent-work endpoint, public Recent Work panel, and exit audit completed without public evidence surfacing. |
| 8 | Phase 0G - Team Bullpen Evidence Surface | Complete | Complete after the Phase 0G exit audit branch passes; internal team evidence review, public team relief-work endpoint, public Recent Bullpen Work panel, and source-separation audit are recorded. |
| 9 | Phase 0H - Trusted Snapshot + What Changed Foundation | Complete | Production ratified July 12, 2026: 11 historically published snapshots, 11 trusted published snapshots, six trusted adjacent pairs, two fully comparable adjacent pairs, four unsuitable pairs withheld, zero non-adjacent comparisons, recent rows not truncated, incomplete candidate did not replace the last valid publication, Decisions 4/5 ratified, D-15 closed, and public What Changed technically unblocked. Recent partial scheduled syncs remain an operational monitoring concern but did not invalidate Phase 0H because the system failed closed correctly. |
| 10 | Phase 0I - Roster Availability Context | Complete | Public roster-readiness contract added; Team Board and dashboard fail closed by withholding current roster-depth counts when official roster snapshot evidence is stale, missing, partial, or inconsistent; postgame cache writes no longer override official roster evidence. |
| 11 | Phase 0J - Starter Exposure Context | Complete | Backend contract verification and frontend closeout are complete: Team Board renders factual seven-day starter-length context, links to Recent Bullpen Work receipts, shows limited states honestly, and Today remains a teaser to the Team Board. |
| 12 | Phase 0K - Methodology, Limitations, and Data Trust Rewrite | Complete | Completed across two public-surface branches. The Methodology page was rewritten public-first (feat/methodology-public-first-rewrite, PR #503, commit 7a1bf39): evidence examined, how an arm read and a team read are formed, one fixed illustrative worked example, freshness and publication safeguards, and limitations. The Data & Trust page was rewritten reader-first (feat/data-trust-reader-first-rewrite) to lead with the current public-data answer from served dashboard freshness, explain freshness and coverage (data-through vs updated vs last-checked), and present the retrospective next-day usage check with unknown-versus-zero-honest formatting; the scored-pitcher inventory diagnostic was removed and Methodology and How to Read are linked. Presentation-layer only: no availability, usage-check, threshold, sync, snapshot, or API changes. |
| 13 | Phase 0L - Analytics Event Alignment | Not started | Measure evidence use and comprehension without changing baseball claims. |
| 14 | Phase 1 - Daily Bullpen Home | Deferred | Begins after foundation gates support a stronger daily product. |
| 15 | Phase 2 - Follow My Team | Deferred | Begins after team evidence is strong enough. |
| 16 | Phase 3 - Shareable Cards | Deferred | Begins after shareable reads can preserve evidence and freshness. |
| 17 | Phase 4 - Digest / Creator / Pro Validation | Deferred | Begins after foundation and evidence layers support broader validation. |

## Final Operating Principle

BaseballOS should become more useful by making bullpen evidence clearer, not by
claiming more than the data can support.
