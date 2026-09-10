# Phase 0B-07 - Acquisition Strategy And Matrix

Status: `AUDIT-ONLY-0B`

Branch: `phase-0b/07-acquisition-strategy-and-matrix`

Phase 0B is now a closed audit-and-decision phase. This document consolidates
the Phase 0B source audits into a final acquisition strategy, acceptability
grid, source/category matrix summary, Q1-Q10 bullpen evidence map,
implementation priority classification, and Phase 0B exit checklist.

This branch does not implement ingestion, schemas, APIs, UI, evidence engines,
public copy, source adoption, paid-provider adoption, or product behavior.

## Audit Categories

- Category 20: Source/legal/maintenance review
- Category 21: Product evidence mapping
- Category 22: Implementation priority classification

## Evidence Inputs

| input | role |
| --- | --- |
| `docs/phase0b/README.md` | Phase 0B thesis, guardrails, templates, and branch map. |
| `docs/phase0b/01_existing_foundation.md` | Existing BaseballOS data foundation, provenance, public claims, and internal gaps. |
| `docs/phase0b/02_statsapi_core.md` | MLB Stats API core schedule, game identity, finality, boxscore, and correction audit. |
| `docs/phase0b/03_statsapi_context.md` | MLB Stats API context audit for play-by-play, live feed, rosters, transactions, and injuries/IL. |
| `docs/phase0b/04_pitch_level_feasibility.md` | Baseball Savant / Statcast pitch-level, contact-quality, batter-context, and helper-library audit. |
| `docs/phase0b/05_derived_evidence_feasibility.md` | Derived-evidence feasibility map and Q1-Q10 evidence mapping. |
| `docs/phase0b/templates/source_category_matrix.md` | Canonical matrix columns and source posture values. |
| `docs/phase0b/templates/bullpen_question_map.md` | Canonical Q1-Q10 mapping structure. |
| `docs/phase0b/templates/classification_taxonomy.md` | Priority classes and risk/effort axes. |
| `docs/phase0b/templates/probe_protocol.md` | Read-only probe rules. |

## 1. Phase 0B Exit Thesis

Phase 0B did not adopt new sources into production. It created a decision record
for source acquisition so later work can advance deliberately instead of
expanding BaseballOS by momentum.

Public display remains conservative. A source can be technically available,
historically useful, or baseball-relevant without becoming safe public evidence.
Every public-facing expansion still needs legal/source review, finality safety,
correction behavior, maintenance expectations, testability, and a fail-closed
product rule.

BaseballOS stays bullpen-focused. Source abundance does not equal product scope.
Pitch-level fields, transactions, roster depth, and play-by-play context matter
only when they explain bullpen evidence. They should not pull the product into
generic MLB analytics, prediction, betting, fantasy, health certainty, or
manager-intent claims.

Implementation priority is based on:

- bullpen evidence value;
- legal/source safety;
- finality and correction behavior;
- maintainability;
- testability;
- public-language safety;
- ability to fail closed when evidence is missing, stale, partial, or unclear.

## 2. Consolidated Source Posture

### A. Existing BaseballOS Internal Data

Current status: BaseballOS already stores a substantial completed-game and
publication foundation: pitcher identity, team assignment, roster status,
pitching game logs, nullable pitch counts, fatigue/workload scores, postgame
processing markers, sync run state, sync failures, scheduled games, completed
game context, dashboard snapshots, and intelligence snapshots.

What it can support now:

- internal workload/rest/usage derivations from final game logs;
- unknown-safe pitch-count handling;
- correction provenance for stored game-log fields;
- postgame marker lifecycle and retry visibility;
- slate coverage metadata;
- trusted published-snapshot baselines;
- current internal board and What Changed guardrails.

Current limitations:

- public score and fatigue framing remains disallowed;
- role labels remain usage inference, not manager intent;
- health wording is risky unless explicit roster/IL evidence supports it;
- existing source terms, attribution, storage, and redistribution posture remain
  `needs-legal-review`;
- current storage is game-level and appearance-level, not pitch-level.

Public/internal posture: continued guarded internal use is acceptable. Public
display of richer derived reads remains conservative and decision-pending.

Correction/provenance posture: strong foundation for existing stored rows,
including unknown preservation, safe correction propagation, dead-letter
behavior, postgame marker lifecycle, sync metadata, and snapshot authority.

Recommended priority class: `AUDIT-ONLY-0B` for current inventory rows,
`FOUNDATION-0C` where additional stored fields are source-safe enough to plan,
and `EVIDENCE-0D` where derived public reads need evidence design.

### B. MLB Stats API Core

Current status: Stats API core is already used as a free/no-auth HTTP source in
the repo, but this audit does not treat that as legal clearance.

Schedule/game identity:

- `gamePk`, teams, dates, game type, doubleheader fields, and schedule status
  are available.
- `gamePk` is identity only. It does not prove the game happened.
- `officialDate` is product-day relevant, but postponed/rescheduled rows can
  create denominator risk.

Finality/status:

- `abstractGameState=Final` is unsafe alone because a postponed row can carry
  it.
- Finality should be interpreted by precedence: postponed, suspended,
  cancelled, missing game id, empty boxscore, missing pitcher identity, and
  partial boxscore must override final-ish signals.
- Final schedule status plus usable boxscore pitching lines is the strongest
  current core path.

Boxscores/pitching lines:

- Final boxscore pitching lines support pitcher identity, innings/outs, pitch
  counts where present, strikes, run-prevention stats, holds, saves, blown
  saves, wins, losses, and starter flags.
- Batters faced, raw outs, pitches thrown, balls, inherited runners, games
  finished, and team pitching totals are available candidates but need schema,
  correction propagation, and public-display review.
- In-progress boxscores can be partial and must not power completed-game
  evidence.

Correction behavior:

- Existing stored game-log fields have safe correction behavior.
- New fields must not be stored until correction-sensitive behavior is designed
  and tested.

Doubleheader/postponed/suspended risks:

- Doubleheaders can be represented by separate game ids and game-number fields.
- Postponed and suspended/resumed games are first-class denominator risks.
- Resumed-game linkage needs storage and tests before public evidence.

Legal/source posture: `needs-legal-review` for terms, attribution, storage,
reuse, redistribution, and SLA.

Recommended priority class: `FOUNDATION-0C` for finality/status hardening and
final boxscore field expansion; `AUDIT-ONLY-0B` for existing guarded use;
`LATER-V4` for lower-value boxscore totals until higher-priority foundation is
complete.

### C. MLB Stats API Context

Final play-by-play:

- Final play-by-play appears promising for pitcher changes, entry/exit context,
  score state, inning state, inherited traffic, clean versus traffic innings,
  and pressure inputs.
- It is not approved for ingestion or public display in Phase 0B.
- It should move first as a foundation/evidence-design candidate, not as public
  copy.

Live/in-progress feed:

- Live and in-progress feed data is non-final and partial by nature.
- It remains `NEVER` for public evidence.
- Live base/out state, current play state, and partial live boxscores should be
  `DO-NOT-USE` for public claims.

Rosters:

- Active, 40-man, full-roster, non-roster, position, active/inactive, and
  roster-status fields are strong candidates for Phase 0C foundation.
- Roster snapshots should remain current-state authority.

Transactions:

- Transactions can explain roster churn only when typed fields, identities,
  dates, and roster snapshots align.
- They should not override current roster state.
- Free-text parsing remains risky.

Injuries/IL:

- BaseballOS currently has roster/IL status context, not medical context.
- Direct injury endpoint shape remains `UNKNOWN`.
- IL placements and activations can be candidates when supported by explicit
  public source evidence and legal/source review.

Roster versus transaction precedence:

- Current roster snapshot wins current-state classification.
- Transaction explanation becomes `UNKNOWN` when dates, identity, team, or
  current roster state disagree.

Injury/health wording guardrail:

- Absence of a public IL or injury flag is not proof of health.
- Do not say healthy, injury-free, available, unavailable, or protected without
  explicit supporting evidence for that exact claim.

Legal/source posture: `needs-legal-review`, especially for final
play-by-play storage, transaction descriptions, public injury descriptions, raw
cache retention, and redistribution.

Recommended priority class: `FOUNDATION-0C` for roster/status foundation and
selected final play-by-play foundation; `EVIDENCE-0D` for entry/exit, inherited
traffic, and role/pressure derivations; `DO-NOT-USE` for live public evidence;
`UNKNOWN-UNTIL-LEGAL` for public injury descriptions and unclear raw context
storage.

### D. Baseball Savant / Statcast Pitch-Level Data

Technical feasibility:

- Baseball Savant / Statcast CSV data is technically accessible and
  field-rich.
- The 0B-05 probe observed pitch identity, sequence, game ids,
  pitcher/batter ids, pitch type/name, velocity, release traits, movement,
  location, count, result/description, batted-ball fields, expected metrics,
  and batter context.

Pitch-level fields:

- Pitch identity/sequence, pitch type/name, velocity/effective velocity,
  release/spin/movement traits, location/zone/count, pitch result, whiff/CSW,
  pitch mix, and trend candidates are valuable internal candidates.

Batted-ball/contact-quality fields:

- Exit velocity, launch angle, batted-ball type, hard-hit/barrel candidates,
  expected outcome fields, and contact-quality summaries are sparse,
  sample-size-sensitive, and interpretation-heavy.

Batter-context fields:

- Batter/pitcher handedness and batter sequence can explain exposure.
- Batter-quality scores and matchup prediction are out of scope.

Storage/redistribution risk:

- Raw pitch-row storage is `raw-cache-risk`.
- Derived aggregates may be lower risk, but still need legal review.
- Redistribution and public display are not approved.

Legal/source posture: `needs-legal-review` and often
`UNKNOWN-UNTIL-LEGAL` before raw storage, public display, automated ingestion,
or commercial use.

Correction/reprocessing concern:

- Pitch-level data can arrive late, be sparse, or be reprocessed.
- Any later design needs row identity, first-seen and last-corrected metadata,
  correction counts, and requery policy.

Sample-size risk:

- One outing, a few pitches, or a small ball-in-play sample must not become a
  public trend claim.
- Minimum-sample policy belongs to Phase 0D.

Recommended priority class: `EVIDENCE-0D` only after legal/source review and
correction/finality design; `LATER-V4` for public pitch-level and contact
quality evidence; `UNKNOWN-UNTIL-LEGAL` for raw storage, redistribution, and
expected-outcome public display.

### E. pybaseball/baseballr Helpers

Current status: pybaseball and baseballr are retrieval helpers over underlying
sources such as Baseball Savant / Statcast. They are not installed, not adopted,
and not required by current BaseballOS.

Helper status only:

- A helper can reduce retrieval friction.
- A helper does not change the legal posture of the underlying source.
- A helper does not provide source adoption, attribution clearance, storage
  rights, redistribution rights, or SLA.

Maintenance risk:

- Helper behavior can change independently from source behavior.
- Dependency drift, language/runtime footprint, scraping fragility, and
  upstream changes add maintenance burden.

Recommended priority class: `UNKNOWN-UNTIL-LEGAL` for any production use;
`AUDIT-ONLY-0B` as helper references; do not adopt in Phase 0B.

### F. Restricted/Reference Sources

FanGraphs, Baseball Reference, and Stathead remain reference-reading only. Do
not use them for scraping or production ingestion unless a future legal review
or licensed path explicitly clears them.

Recommended priority class: `DO-NOT-USE` for raw scraping or production
ingestion; reference-reading only for human research.

### G. Paid/Optional Future Sources

Optional future sources include:

- Sportradar
- SportsDataIO
- TruMedia
- BaseballCloud
- Rapsodo/TrackMan-style institutional sources

No paid source is required for current V4. No paid source is adopted in Phase
0B. Paid-source evaluation belongs later if free/public sources cannot support a
needed evidence category or if BaseballOS moves toward institutional products.

Recommended priority class: `OPTIONAL-PAID-FUTURE`.

## 3. Acceptability Grid

| source_family | internal_research | stored_production_dependency | derived_aggregate_storage | raw_cache_storage | public_display | redistribution | legal_posture | priority_class | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Existing BaseballOS internal data | yes | yes | yes | conditional | conditional | needs-legal-review | needs-legal-review | AUDIT-ONLY-0B | Continued guarded use is acceptable; richer public claims remain decision-pending. |
| MLB Stats API core | yes | conditional | conditional | needs-legal-review | conditional | needs-legal-review | needs-legal-review | FOUNDATION-0C | Strongest path is final schedule plus usable final boxscore. |
| MLB Stats API final play-by-play | yes | conditional | conditional | needs-legal-review | conditional | needs-legal-review | needs-legal-review | EVIDENCE-0D | Promising for entry, traffic, and pressure evidence after foundation/design. |
| MLB Stats API live/in-progress feed | conditional | no | no | do-not-use | do-not-use | do-not-use | needs-legal-review | DO-NOT-USE | Never public evidence while live or non-final. |
| MLB Stats API rosters/status | yes | conditional | conditional | needs-legal-review | conditional | needs-legal-review | needs-legal-review | FOUNDATION-0C | Current roster snapshot should remain current-state authority. |
| MLB Stats API transactions | yes | conditional | conditional | needs-legal-review | conditional | needs-legal-review | needs-legal-review | FOUNDATION-0C | Explanatory only when dates, identities, and roster state align. |
| MLB Stats API injury/IL descriptions | conditional | conditional | conditional | needs-legal-review | needs-legal-review | needs-legal-review | needs-legal-review | UNKNOWN-UNTIL-LEGAL | Direct injury endpoint remains unknown; no health certainty from absence. |
| Baseball Savant / Statcast | yes | needs-legal-review | needs-legal-review | needs-legal-review | needs-legal-review | needs-legal-review | needs-legal-review | UNKNOWN-UNTIL-LEGAL | Technically feasible but not adopted for storage or public display. |
| pybaseball helper | conditional | no | no | no | no | no | needs-legal-review | UNKNOWN-UNTIL-LEGAL | Retrieval helper only; not legal clearance. |
| baseballr helper | conditional | no | no | no | no | no | needs-legal-review | UNKNOWN-UNTIL-LEGAL | Retrieval helper only; adds R dependency and maintenance risk. |
| FanGraphs / Baseball Reference / Stathead | conditional | do-not-use | do-not-use | do-not-use | do-not-use | do-not-use | do-not-use | DO-NOT-USE | Reference-reading only unless licensed/legal path is cleared. |
| Paid optional providers | optional/future | optional/future | optional/future | optional/future | optional/future | optional/future | optional/future | OPTIONAL-PAID-FUTURE | Not required for current V4 and not adopted here. |

## 4. Completed Source/Category Acquisition Matrix

This consolidated matrix summarizes the Phase 0B decision record. It links back
to prior evidence docs instead of duplicating every full Phase 0B matrix row.

| category_or_group | source | public_display_posture | priority_class | legal_source_posture | fail_closed_behavior | evidence_link |
| --- | --- | --- | --- | --- | --- | --- |
| existing stored game logs | statsapi_v1 | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Exclude non-final games, dead-letter unsafe corrections, and keep unknown fields unknown. | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` |
| unknown-safe pitch counts | statsapi_v1 | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Store missing pitch counts as NULL and withhold pitch-count claims when unknown. | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` |
| correction provenance | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Reject unsafe corrections and preserve prior good rows. | `docs/phase0b/01_existing_foundation.md` |
| postgame marker lifecycle | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Retry incomplete final games without duplicate logs, then stop at visible failed marker. | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/02_statsapi_core.md` |
| sync run state and single-writer protection | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Reject active writer conflict and degrade freshness when metadata is unavailable. | `docs/phase0b/01_existing_foundation.md` |
| slate coverage metadata | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark slate incomplete and withhold complete-sounding reads when coverage is missing. | `docs/phase0b/01_existing_foundation.md` |
| trusted baseline metadata | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Withhold change reads when snapshots are partial, stale, missing, or incomparable. | `docs/phase0b/01_existing_foundation.md`; `docs/phase0b/05_derived_evidence_feasibility.md` |
| Stats API schedule game identity | statsapi_v1 | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Skip missing game id and do not treat identity as proof of completed game. | `docs/phase0b/02_statsapi_core.md` |
| Stats API finality/status fields | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Postponed, suspended, cancelled, and empty-boxscore states override final-ish status. | `docs/phase0b/02_statsapi_core.md` |
| Stats API boxscore pitching lines | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Require final game and usable pitching lines; retry empty or partial final boxscores. | `docs/phase0b/02_statsapi_core.md` |
| Stats API pitch counts | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Preserve missing counts as unknown and suppress pitch-count burden claims. | `docs/phase0b/02_statsapi_core.md` |
| Stats API boxscore empty/partial behavior | statsapi_v1 | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark incomplete/retryable and fail to visible marker after retry limit. | `docs/phase0b/02_statsapi_core.md` |
| Stats API correction-sensitive fields | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Do not store new correction-sensitive fields until propagation exists. | `docs/phase0b/02_statsapi_core.md` |
| final play-by-play | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Do not derive play-level evidence when final play-by-play is missing or ambiguous. | `docs/phase0b/03_statsapi_context.md` |
| live/in-progress feed | statsapi_v11_live | NEVER | DO-NOT-USE | needs-legal-review | Never use live or non-final data for public evidence. | `docs/phase0b/03_statsapi_context.md` |
| pitcher changes | statsapi_v1 | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark pitcher-change context UNKNOWN when sequence is ambiguous. | `docs/phase0b/03_statsapi_context.md`; `docs/phase0b/05_derived_evidence_feasibility.md` |
| entry/exit inning context | statsapi_v1 | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark entry/exit UNKNOWN unless final play-by-play proves it. | `docs/phase0b/03_statsapi_context.md`; `docs/phase0b/05_derived_evidence_feasibility.md` |
| inherited runner context | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark UNKNOWN unless runner ownership and scoring are deterministic. | `docs/phase0b/03_statsapi_context.md`; `docs/phase0b/05_derived_evidence_feasibility.md` |
| active roster | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Mark roster state UNKNOWN if active roster cannot be fetched or matched. | `docs/phase0b/03_statsapi_context.md` |
| 40-man roster | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Classify as depth only and never active availability by itself. | `docs/phase0b/03_statsapi_context.md` |
| transactions | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Use transactions as explanation only after typed fields and dates align. | `docs/phase0b/03_statsapi_context.md` |
| IL placements/activations | statsapi_v1 | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Say only roster/IL facts and mark UNKNOWN on conflict or missing date. | `docs/phase0b/03_statsapi_context.md` |
| public injury descriptions if available/unknown | statsapi_v1 | INTERNAL-ONLY | UNKNOWN-UNTIL-LEGAL | needs-legal-review | Do not expose raw descriptions without legal and editorial approval. | `docs/phase0b/03_statsapi_context.md` |
| roster/transaction disagreement behavior | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Current roster snapshot decides state; conflicting transaction explanation becomes UNKNOWN. | `docs/phase0b/03_statsapi_context.md` |
| Statcast pitch identity/sequence | savant_statcast | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Suppress pitch-level evidence unless game, at-bat, pitch, pitcher, and batter ids are present. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast pitch type/name | savant_statcast | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Withhold pitch-mix reads when type or name is missing or reclassified. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast velocity/effective velocity | savant_statcast | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark velocity context UNKNOWN when samples are too small or values are missing. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast spin/movement/release traits | savant_statcast | INTERNAL-ONLY | LATER-V4 | needs-legal-review | Do not expose trait reads when fields are missing or unexplained. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast pitch result/description | savant_statcast | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Do not infer outcome when description or type is missing or unknown. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast whiff/CSW derivables | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark UNKNOWN until deterministic value maps are defined and tested. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast pitch mix/usage | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Withhold mix read for small or incomparable samples. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast batted-ball/contact-quality fields | savant_statcast | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Suppress contact-quality reads when ball-in-play samples are too small. | `docs/phase0b/04_pitch_level_feasibility.md` |
| Statcast batter-context fields | savant_statcast | INTERNAL-ONLY | LATER-V4 | needs-legal-review | Explain usage context only and do not predict matchup outcome. | `docs/phase0b/04_pitch_level_feasibility.md` |
| pybaseball helper | savant_statcast | INTERNAL-ONLY | UNKNOWN-UNTIL-LEGAL | needs-legal-review | Treat helper failure as source unavailable and never as legal clearance. | `docs/phase0b/04_pitch_level_feasibility.md` |
| baseballr helper | savant_statcast | INTERNAL-ONLY | UNKNOWN-UNTIL-LEGAL | needs-legal-review | Treat helper failure as source unavailable and never as legal clearance. | `docs/phase0b/04_pitch_level_feasibility.md` |
| derived rolling workload | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark workload UNKNOWN when required final rows are missing. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived days rest | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark rest UNKNOWN when last final appearance cannot be proven. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived back-to-back/3-in-4/4-in-6 usage | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark density UNKNOWN when any required window is incomplete. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived same-arm concentration | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark concentration UNKNOWN when team coverage is incomplete. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived starter short-start pressure | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Mark short-start pressure UNKNOWN when starter or team rows are incomplete. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived roster/depth pressure | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Mark depth pressure UNKNOWN when roster status is missing, stale, or conflicting. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived IL pressure | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Mark IL pressure UNKNOWN when explicit public status evidence is absent or stale. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| derived transaction churn | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Mark churn UNKNOWN when transaction type, date, or roster impact is unclear. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| internal leverage proxy candidate | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark proxy UNKNOWN when any required final context is absent. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| inferred role usage | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark role inference UNKNOWN when usage or pressure evidence is insufficient. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| team bullpen structure | derived_internal | INTERNAL-ONLY | EVIDENCE-0D | needs-legal-review | Mark team shape UNKNOWN when any structure component is unsupported. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| calendar rest context | derived_internal | INTERNAL-ONLY | FOUNDATION-0C | needs-legal-review | Mark calendar context UNKNOWN when schedule identity or status is ambiguous. | `docs/phase0b/05_derived_evidence_feasibility.md` |
| historical baselines/comparisons | derived_internal | INTERNAL-ONLY | AUDIT-ONLY-0B | needs-legal-review | Withhold comparisons when either side is stale, partial, or incomparable. | `docs/phase0b/05_derived_evidence_feasibility.md` |

## 5. Final Data-To-Bullpen-Question Map

| question | evidence_families | current_support_level | future_phase_needed | public_evidence_posture | internal_only_support | unknown_behavior | guardrails |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q1: Which bullpens are fresh tonight? | Workload, rest, recent appearances, schedule rest | Partial from final game logs and snapshots | 0C for schedule/roster foundation; 0D for public thresholds | Candidate only after legal/source and public-display decision | Fatigue scores, thresholds, confidence | Mark UNKNOWN when workload windows, rest dates, pitch counts, or calendar context are missing, stale, partial, or not finality-safe. | Descriptive only; no availability prediction, injury inference, betting, fantasy, or confidence-score framing. |
| Q2: Which bullpens are stretched? | Workload concentration, recent usage, multi-day burden | Partial from final rows, concentration, and nullable pitch counts | 0C for expanded stored fields; 0D for thresholds | Candidate only after legal/source and public-display decision | Fatigue scoring and burden thresholds | Mark UNKNOWN when windows are incomplete, corrections are unresolved, or pitch counts are unavailable for pitch-based claims. | Descriptive burden only; no public fatigue-score framing. |
| Q3: Which teams have late-game margin? | Role usage, pressure context, rested clean options | Weak to partial; current role labels are inferential | 0C for final context storage; 0D for pressure/role design | Internal-only until evidence is explainable and source-safe | Role inference model, pressure proxy, confidence | Mark UNKNOWN when role, pressure, rest, or active-roster evidence cannot all be supported. | Avoid manager-intent certainty and ranking claims. |
| Q4: Which teams lack clean options? | Traffic, workload, command stress, depth pressure | Partial workload/depth only; traffic and command not founded | 0C for roster/PBP foundation; 0D for clean/traffic and pitch-level rules | Internal-only until evidence is complete enough | Pitch-level stress metrics, role model, pressure proxy | Mark UNKNOWN when clean/messy appearance evidence, roster status, or pitch-level support is absent or legally unclear. | Do not turn incomplete evidence into a complete-sounding read. |
| Q5: Which arms are being leaned on too heavily? | Repeated usage, pitch counts, appearance density, role context | Partial to strong internally for workload | 0C for boxscore expansion; 0D for public thresholds and role overlay | Candidate only after public-language decision | Fatigue scoring, hidden thresholds | Mark UNKNOWN when workload thresholds, windows, correction state, or pitch counts are incomplete for the claim. | Usage context only; no injury or performance prediction. |
| Q6: Which arms are rested but not trusted? | Rest state, role usage, pressure history | Weak; rest exists but trust inference needs design | 0D evidence design | Internal-only | Trust model, pressure proxy, confidence | Mark UNKNOWN when both rest evidence and role/pressure evidence are not supported. | Avoid certainty about manager intent; prefer usage-pattern language. |
| Q7: Which arms are trusted but rest-restricted? | Role usage, recent workload, dense usage windows | Partial workload; trust inference not ready | 0D evidence design | Internal-only | Internal trust classification and rest thresholds | Mark UNKNOWN when role evidence or rest-restriction evidence is missing. | No public fatigue-score framing; use evidence-backed usage language. |
| Q8: Which teams are being pressured by short starts? | Starter innings, bullpen innings burden, schedule context | Partial from completed-game starter/bullpen rows | 0C for starter exposure foundation; 0D for public read design | Candidate only after final-row completeness and public decision | Opener/bulk inference and pressure thresholds | Mark UNKNOWN when starter rows, team rows, or completed-game coverage are incomplete. | Recent-context only; no upcoming starter projection. |
| Q9: Which teams are pressured by injuries/IL/depth loss? | Roster status, IL, transactions, active depth | Partial from current roster/status; direct injury source unknown | 0C if legal/source posture allows; legal review required | Candidate only for explicit public roster facts after review | Depth-pressure thresholds and internal confidence | Mark UNKNOWN when roster or IL evidence is missing, stale, conflicting, legally unclear, or inferred from absence. | No private injury claims; never say healthy or injury-free without explicit support. |
| Q10: What changed since yesterday? | Trusted snapshots, comparable baselines, workload/roster deltas | Strong guardrails for existing snapshot-backed deltas | 0C for richer source deltas; 0D for ranking/framing | Candidate only when snapshot-backed and comparable | Change ranking, confidence, suppression reasons | Withhold when snapshots are partial, stale, incomparable, or not finality-safe. | No comparison against partial days, incompatible windows, or unsupported roster changes. |

## 6. Implementation Priority Classification

### `FOUNDATION-0C`

| candidate | decision |
| --- | --- |
| Final boxscore field expansion | Candidate for Phase 0C where fields are finality-safe enough and correction propagation can be added. |
| Finality/status precedence hardening | Needed before richer completed-game evidence depends on schedule states. |
| Batters faced, raw outs, pitches thrown, balls, inherited runners, games finished, and selected team totals | Candidate only with schema, correction, and fail-closed rules. |
| Final play-by-play foundation | Candidate for stored final context or derived context foundation, not public display by itself. |
| Roster/status foundation | Strong candidate because current authority already supports active/off-active/unknown classification. |
| Transaction foundation | Candidate as explanatory context only when typed fields, dates, player, team, and roster snapshot align. |
| IL/roster-status foundation | Candidate where source shape is clear; otherwise stays `UNKNOWN-UNTIL-LEGAL` or audit follow-up. |
| Starter exposure foundation | Candidate from final starter/bullpen rows and expanded boxscore fields. |
| Provenance/correction extension | Required for every newly stored field. |
| Schedule/calendar context | Candidate for off days, doubleheaders, postponed/makeup handling, and current denominator safety. |

### `EVIDENCE-0D`

| candidate | decision |
| --- | --- |
| Appearance entry/exit context | Requires final play-by-play evidence design and correction tests. |
| Inherited runner context | Requires deterministic reconstruction or audited boxscore mapping. |
| Clean versus traffic innings | Requires final entry state, runners, outs, scoring, and sample rules. |
| Pressure/leverage proxy design | Internal-only until transparent formula, tests, and public-language review exist. |
| Role inference rules | Usage-pattern only; no manager-intent certainty. |
| Team bullpen structure reads | Needs roster, workload, role, handedness, depth, and evidence rules. |
| Starter short-start pressure reads | Needs foundation plus public read thresholds. |
| Pitch-level trend candidates | Only after legal/source review and correction/finality design. |
| Contact-quality and batter-context explanations | Internal-first and sample-size-safe. |

### `LATER-V4`

| candidate | decision |
| --- | --- |
| Pitch-level public evidence | Wait until 0C/0D foundations, legal review, storage policy, and sample-size rules exist. |
| Contact-quality public evidence | Later only, with simple evidence language and sufficient balls in play. |
| Batter-context usage explanation | Later only, not matchup prediction. |
| Historical trend expansion beyond immediate windows | Later after snapshot and baseline completeness are proven. |
| Lower-value boxscore totals | Later after higher-value foundation work. |
| Paid-source evaluation if needed | Later only if current free/public sources cannot support needed evidence or institutional use emerges. |

### `AUDIT-ONLY-0B`

| candidate | decision |
| --- | --- |
| Current Phase 0B source rows | Complete enough for decision record, not implementation by themselves. |
| Existing internal inventory rows | Continue guarded internal use; no new public display approval. |
| Helper-library references | Useful for audit only; not dependencies or source adoption. |
| Paid-provider notes | Strategy placeholders only. |

### `OPTIONAL-PAID-FUTURE`

| candidate | decision |
| --- | --- |
| Sportradar | Optional/future only. |
| SportsDataIO | Optional/future only. |
| TruMedia | Optional/future only. |
| BaseballCloud | Optional/future only. |
| Rapsodo/TrackMan-style institutional sources | Optional/future only, especially for institutional product direction. |

### `DO-NOT-USE`

| candidate | decision |
| --- | --- |
| Live/in-progress feed for public evidence | Do not use for public evidence. |
| Raw scraped restricted sources | Do not use unless a future licensed/legal path clears them. |
| Unsupported health/injury claims from absence of flags | Do not use. |
| Betting, odds, projection, or fantasy framing | Do not use. |
| Manager-intent certainty | Do not use. |
| Official-role claims without evidence/source | Do not use. |
| Official leverage claims without adopted source | Do not use. |

### `UNKNOWN-UNTIL-LEGAL`

| candidate | decision |
| --- | --- |
| Raw Statcast storage | Unknown until legal/source review. |
| Statcast public display and redistribution | Unknown until legal/source review. |
| Baseball Savant/Statcast commercial/storage posture | Unknown until legal/source review. |
| Stats API attribution/storage/reuse posture | Unknown until legal/source review. |
| Public injury descriptions | Unknown until legal and editorial review. |
| pybaseball/baseballr production use | Unknown until underlying source and dependency posture are reviewed. |

## 7. Phase 0B Exit Checklist

- [x] Every must-have data category has a source-status decision or `UNKNOWN`.
- [x] Unsafe and unavailable fields are explicitly marked, not omitted.
- [x] Acquisition work is prioritized by bullpen evidence value.
- [x] The matrix states what can be used now.
- [x] The matrix states what can be derived now.
- [x] The matrix states what should be founded in 0C.
- [x] The matrix states what requires 0D.
- [x] The matrix states what should wait.
- [x] The matrix states what is unavailable or unsafe.
- [x] The matrix states what needs legal review.
- [x] No implementation was performed.
- [x] No source was adopted by momentum.
- [x] Public-display clearance remains conservative.
- [x] Phase 0B can close.

Phase 0B exit result: passed. BaseballOS has enough audit evidence and
decision posture to close Phase 0B and move to Phase 0C sequencing.

## 8. Phase 0C Recommendation

After 0B-07 merges, ask Claude for a Phase 0C sequencing plan.

Phase 0C should likely focus on source/schema foundation for the safest and
highest-value data categories identified in Phase 0B, especially:

- final boxscore field expansion;
- final play-by-play foundation;
- roster/status foundation;
- transaction/IL foundation if source/legal posture allows;
- starter exposure foundation;
- provenance/correction extension;
- fail-closed source readiness gates.

This document does not generate Phase 0C implementation prompts. Phase 0C
implementation should not start until the sequencing plan is approved.

## 9. Roadmap Status Update

`docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md` should mark Phase 0B
complete now that 0B-01 through 0B-07 are complete, the acquisition strategy and
matrix are added, and Phase 0C sequencing is the next step.

## Final Decision

Phase 0B is complete.

BaseballOS can safely keep using the existing guarded internal foundation and
current Stats API-backed stored game-log paths while preserving current
fail-closed behavior. Phase 0C should not start by adding public reads; it
should start by hardening the highest-value source and schema foundations.

Phase 0D should own evidence design for derived public reads, including
entry/exit context, inherited traffic, pressure proxies, role inference, team
bullpen structure, pitch-level trends, and sample-size rules.

Legal/source review remains required before public display, raw storage,
redistribution, or commercial use advances for Stats API, Baseball Savant /
Statcast, helpers, or public injury/transaction descriptions.

No paid source is required for current V4. No restricted/reference source is
approved for ingestion. No live/in-progress feed is approved for public
evidence.
