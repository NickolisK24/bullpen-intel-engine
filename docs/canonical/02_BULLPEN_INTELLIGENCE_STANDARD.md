# BaseballOS Bullpen Intelligence Standard

| Field | Value |
|---|---|
| Status | Canonical - intelligence, data, evidence, methodology, and publication authority |
| Version | 1.1 |
| Effective date | July 29, 2026 |
| Owner | Nickolis Kacludis |
| Supersedes | Intelligence, metric, vocabulary, evidence, freshness, and trust rules spread across prior master documents |
| Update rule | Revise when a source authority, data domain, public term, method, evidence contract, freshness rule, suppression rule, or publication gate changes |
| Review cadence | Monthly during the MLB season; quarterly in the offseason; immediately after a material trust incident |

> **Governing question:** What must be true before BaseballOS is allowed to say something publicly?

## 1. Definition of BaseballOS Intelligence

BaseballOS intelligence is an evidence-backed interpretation of observable bullpen reality.

It is not a raw data row, dashboard tile, unexplained score, prediction, manager recommendation, private-health conclusion, or opinion dressed as a metric.

Every meaning-bearing claim follows:

```text
Authoritative Source
-> Canonical Baseball Record
-> Deterministic Derivation
-> Evidence Item
-> Observation
-> Public Read or Story
-> Trusted Publication
-> Permanent Memory
```

Every layer must be inspectable. No downstream layer may silently repair, reinterpret, or replace an upstream fact.

## 2. Four-Class Data Model

| Class | Definition | Permitted public use |
|---|---|---|
| Observed | Recorded fact from an authoritative public source | May be stated with source and timestamp |
| Derived | Deterministic computation over observed facts | May be stated when method, inputs, version, and window are reproducible |
| Contextual | Observed environment or schedule fact | May frame a read; may not be presented as a proven cause |
| Unobservable | Real, relevant fact outside the public record | May not be asserted or estimated as known; must appear in limitations when material |

Unobservables include bullpen warm-ups without game entry, medical status or soreness, private manager or coach plans, personal availability not reflected in a transaction, bullpen sessions, side work, and effort level not represented by tracked data.

## 3. Observation Ladder

A fact is not automatically intelligence. Interpretation earns each higher rung with additional evidence.

| Rung | Example | Minimum evidence |
|---|---|---|
| Fact | A reliever threw 28 pitches Tuesday | Official completed appearance |
| Accumulation | He has thrown 86 pitches in five appearances over seven days | Complete window, dates, counts, denominator |
| Comparison | That is his heaviest seven-day pitch load this season | Reproducible baseline and complete comparison window |
| Structure | Three arms carried 72% of high-leverage work | Named arms, leverage method, share, and window |
| Direction | Concentration rose across three consecutive weekly windows | Versioned series and change method |
| Consequence | A game that reaches this bullpen finds fewer clean late-inning paths | Current state, named evidence, and conditional descriptive language only |

The consequence rung describes what a game encounters. It does not forecast what will happen.

## 4. Public Read Contract

Every claim-bearing public output follows:

```text
State -> Why -> Evidence -> Freshness -> Limitations
```

A public read must answer:

1. What is BaseballOS saying?
2. Why is it saying it?
3. Which facts support it?
4. As of when is it true?
5. What can BaseballOS not see or verify?

No layer may disappear merely because a smaller surface is inconvenient. Compression may reduce quantity, not meaning.

## 5. Source Authority

Authority is explicit, deterministic, versioned, applied before interpretation, and fail-closed under conflict.

A source being official does not make every field in every response authoritative for every question. BaseballOS assigns authority by baseball meaning.

### Official game identity and finality

- `game_pk` is the durable game key.
- A scheduled, delayed, suspended, postponed, in-progress, or unresolved game is not final.
- Duplicate source rows are deduplicated only after identity and core facts agree.
- Contradictory finality records create conflict state; they do not authorize a convenient answer.
- A pregame read shown after first pitch must transition to the correct context or be withdrawn from pregame presentation.

### Official starter authority

For a completed game, the official pitching line or box-score starter designation owns who started.

A pitcher is not identified as the starter merely because he was the first stored pitcher, started elsewhere in the season, appeared in probable-starter data, or has a starter-shaped role profile.

A self-corrected historical incident in which Ferguson was described as the starter while the official box score listed Burns established this rule as publication-critical.

### Official pitching-line authority

The completed official pitching line owns recorded outs, batters faced, pitches, strikes, hits, runs, walks, strikeouts, home runs, and inherited-runner outcomes where available.

Semantic innings are derived from canonical outs:

```text
innings_pitched_outs = canonical_authority
innings_pitched = derived companion = innings_pitched_outs / 3.0
```

Decimal innings never become a separate baseball truth when outs already agree.

### Appearance team authority

An appearance belongs to the team for which the pitcher appeared in that game. Current roster membership does not rewrite historical appearance ownership.

### Player identity authority

Stable MLB identifiers own identity. Names are display values, not identity keys. Ambiguous or unresolved identity fails closed.

### Roster and team-assignment authority

Canonical roster and team-assignment services own current active-roster membership, current organization/team, transaction evidence, historical appearance ownership, and known/unknown status.

Absence from an active roster is not automatically an inferred IL, option, DFA, release, or health state.

### Probable starter authority

Probable starter is contextual until completed-game evidence confirms the starter. Stale or unresolved probable-starter context may be suppressed without suppressing independent bullpen workload evidence.

### Conflict policy

When authorities disagree:

1. identify the exact field and authority class;
2. determine whether one source is explicitly superior under this Standard;
3. if not, mark the field unresolved;
4. suppress only the claims dependent on that field;
5. record the conflict and affected scope;
6. never choose the answer that produces the better story.

## 6. Capability Status Vocabulary

| Status | Meaning |
|---|---|
| Production | Canonical acquisition and public or production-facing use exist |
| Production - internal | Canonical use exists but is not generally public |
| Partial | Some governed fields or surfaces exist; the complete contract does not |
| Planned | Approved direction, not production capability |
| Experimental | Research or feasibility work; not public authority |
| Deferred | Deliberately outside the current build horizon |
| Prohibited | Conflicts with the Constitution |

The presence of an API field does not make a capability Production.

## 7. Data Domains

### Workload and usage - Production

Per-appearance target fields include game, date, team, opponent, home/away, relief designation, inning entered and exited, recorded outs, batters faced, pitches, strikes, inherited runners, leverage/situation where governed, and sequence position.

Rolling arm windows should include 2, 3, 5, 7, 14, and 30 days; appearances, pitches, batters faced, days since use, consecutive-day streaks, back-to-back and dense multi-day patterns, multi-inning use, and season/personal-baseline comparisons when complete.

**Appearances measure frequency. Pitches and batters faced measure cost.** Appearance count may not stand alone when richer workload evidence exists.

### Pitch characteristics - Experimental / Partial

Approved fields include pitch type, release speed, spin, movement, release point, extension, arm angle, location, and result. Approved derivations include velocity, release, extension, and pitch-mix changes against versioned baselines.

A pitch-characteristic change is evidence of change, never evidence of injury.

### Leverage and situation - Partial

Approved fields include entry situation, published leverage methodology or governed situational method, high-leverage appearances, leverage-weighted batters faced, save/hold/blown-save events, inherited runners, and concentration/dependency windows.

A third-party leverage value may be cited only with source and definition. The preferred end state is a versioned, reproducible BaseballOS computation.

### Roster mechanics and transactions - Production for active/off-active authority; Partial for advanced mechanics

Production authority includes active membership, off-active separation, current team assignment, canonical status categories, recent transactions, and fail-closed unknown/conflict state.

Approved expansion includes 40-man status, options remaining, option dates and minimum-stay implications, IL dates and eligible return, rehab assignment, paternity/bereavement, DFA/waiver state, roster churn, and rested eligible reinforcements.

Roster language must not convert absence into a private health conclusion.

### Schedule, calendar, and travel pressure - Production for identity/finality/slate dates/off-days; Partial for travel modeling

Required production fields include schedule rows with game identity, official date and first pitch, venue, teams, home/away, status/finality, doubleheaders, nearby slate windows, completed-game alignment, and upcoming off-day context where exposed.

Game-time awareness is a correctness requirement.

### Rotation dependency - Partial

Official starter authority and completed starter-length evidence are governed. Approved expansion includes probable starter confirmation state, recent starter innings and pitch-count ranges, short-start share, bullpen innings transferred from the rotation, opener/bullpen-game designation, and direction over rolling windows.

Permitted: "His last five starts ranged from 3.0 to 5.2 innings."

Prohibited: "He is likely to go five tonight."

### Handedness and matchup structure - Partial

Pitcher handedness and some coverage evidence exist. Future structural-flexibility claims require posted lineup authority, sample-size thresholds, and named arms. Splits without adjacent sample size do not publish.

### Environment - Deferred / contextual only

Venue, elevation, roof, weather, and park/run-environment facts may qualify a read but may never be a load-bearing explanation of workload, availability, or roster state.

### Deployment patterns - Partial

Completed-game history may describe where and how an arm has been used. Every sentence remains past tense. BaseballOS never claims how the manager will use the arm next.

### Organizational depth - Partial / Planned

Approved fields include 40-man relief depth outside the active roster, recent workload of potential reinforcements, option/recall history, taxi-squad status where observable, and rested/eligible reinforcement availability.

A future reinforcement read must distinguish observable roster eligibility from any claim that the club intends to make a move.

## 7A. Current Active-Pen Performance Contract

This is a **family contract**, not a metric. Every approved metric that describes how a team's current active bullpen has performed inherits it. Adding a metric under this family does not reopen the family contract. Changing the family contract does.

Current Active-Pen ERA is the first planned metric under this family. It is not itself the contract, and it is not implemented or public.

### Governing question

> How have the pitchers who make up this team's active bullpen as of the represented baseball date performed in official completed games?

The family does not answer how rested the bullpen is, whether an arm should pitch, what will happen next, whether the bullpen is good or bad, what a manager intends, or whether a pitcher is healthy.

**State is not performance.** A bullpen may be Fresh with poor performance results. A bullpen may be Vulnerable with strong performance results. Neither combination is a contradiction, and no surface may present one as if it were.

### Active-group contract

Membership derives from the canonical current roster, team-assignment, and bullpen-membership authorities for the represented baseball date. A pitcher belongs to the group only when canonical authority resolves him as part of that team's current active bullpen for that date.

The contract preserves:

- current membership versus historical appearance ownership;
- the official starter/reliever distinction;
- off-active-roster separation;
- explicit unknown and conflict states;
- no current-team fallback for historical appearances.

Current membership decides **who is in the group**. It never decides **which team owns an appearance**. Historical pitching lines remain assigned to the team side for which the pitcher appeared.

The performance group and the Team State group must resolve from one **common canonical active-bullpen-membership authority** consumed by both domains. This Standard does not declare the two groups identical, because no single wired authority currently owns that membership for both: the public availability population composes bullpen eligibility, roster status, and role authority, while the intended canonical roster-context authority is still an unwired foundation. Until one owner is wired for both, a metric under this family must name the authority it consumed and its resolution date.

### Window contract

The default family window is:

> All qualifying official completed relief appearances in the current MLB regular season, made for the represented team by pitchers who belong to that team's current active bullpen on the represented baseball date.

Two separate questions must remain separate:

| Question | Authority | Evaluated as of |
|---|---|---|
| Who is in the group? | Current roster / team-assignment / bullpen-membership authority | The represented baseball date |
| Which appearances qualify? | Official completed pitching line + appearance-team authority | The game in which the appearance occurred |

The window excludes:

- appearances those pitchers made for another organization;
- starts, which are never counted as relief performance;
- postseason, spring-training, exhibition, suspended-unresolved, non-final, and unsupported game types, none of which may be included silently.

A later metric may require an additional rolling window. It may not redefine the family's active-group authority.

### Sample contract

The family **fails closed** below a metric's approved minimum sample.

The family owns the mechanism. Each metric registry entry owns its exact threshold and denominator. No generic threshold is established here, and none may be invented at implementation time: the only below-sample behavior currently authorized by canonical code is refusal at a zero denominator, which the canonical season aggregation reports as the governed reason `era_denominator_zero`.

Below-sample behavior:

- no numeric value is published;
- no zero, prior, league, or estimated value is substituted;
- the result is represented as a limited or unavailable performance read;
- the exact machine refusal code belongs to the canonical code registry at implementation time.

Public wording is subordinate to this contract and may not create a second vocabulary. `Limited Read` exists today as a governed **arm-read** label in the canonical public-label authority. It has never been authorized as a team-level performance label. Final public wording for a below-sample performance read is an implementation-time decision owned by the canonical public-label authority, not by a surface or a caption.

### Date and freshness contract

Every result carries:

- represented baseball date;
- data-through date or timestamp;
- season;
- metric method/version;
- active-group authority date;
- freshness/currentness state.

The represented baseball date is never interchangeable with generation time, publication time, sync completion time, or browser request time. Roster membership and pitching-line evidence must align to one reproducible represented date.

### Evidence contract

Every published performance value must be inspectable back to official completed pitching lines. The reusable chain is:

```text
Metric summary
-> Group and sample context
-> Named pitchers
-> Qualifying team-side relief appearances
-> Official completed pitching lines
-> Source and method authority
```

The chain must be able to supply active-group size, included pitcher identities, qualifying appearance count, canonical integer outs, innings derived from outs for display, metric-specific numerator and denominator, represented games and dates, excluded-line reason where material, source references, method version, and limitations.

Not every compact surface renders the full chain. Every substantive value must provide a route or interaction that reaches it.

### Evidence levels

These are semantic inspection depths. They are not four pages, four components, or four database tables.

| Level | Name | Content |
|---|---|---|
| 1 | Summary | The governed metric value and its currentness |
| 2 | Context | Group size, sample, numerator, denominator, innings/outs, limitation |
| 3 | Evidence | Named pitchers, games, dates, qualifying relief appearances |
| 4 | Official record | Canonical official pitching lines and source authority |

### Limitation contract

The standard material limitation is:

> Current Active-Pen Performance describes recorded results by today's active bullpen group over the approved window. It does not measure current rest, predict future performance, establish manager intent, or include private health and warm-up information.

State it where it is material. Do not repeat a large defensive disclaimer on every small component.

## 7B. Metric Families and the Metric Registry

A **metric family** owns one baseball question and one common authority contract. **Individual metric definitions** inherit the family contract and are versioned separately. Public surfaces consume governed intelligence families; they do not create local interpretations of them.

Current Active-Pen Performance is a governed metric family. Recording it here does not redesign the wider BaseballOS ontology.

### Required metric registry fields

Every metric entry under a family must define:

stable metric key; public name; question answered; observed/derived classification; source fields; formula; numerator; denominator; unit; qualifying appearance rules; game-type rules; minimum sample; rounding and display behavior; evidence fields; freshness dependencies; refusal/suppression behavior; limitation; method version; effective date; change history; approved surfaces; deterministic fixtures.

This extends the methodology-versioning requirements in Section 13; it does not replace them.

### Registry

| ID | Metric | Family | Status |
|---|---|---|---|
| M-001 | Current Active-Pen ERA | Current Active-Pen Performance | Contract pending implementation / not public |

M-001's exact formula approval, minimum sample, and denominator are **not** established by this contract. Approving them is a separate work package. No other metric may be added to this registry as implemented, approved for public use, or production-ready.

Candidate later entries — WHIP, K%, BB%, K-BB%, HR/9, inherited-runner outcomes, and FIP/xFIP/SIERA — remain candidates only. Each requires its own approved source, formula, sample, and publication contract before it becomes a registry entry.

## 8. Public Vocabulary

Internal engine states may remain granular. They do not automatically become public language.

### Team State

The canonical public Team State vocabulary is exactly:

| Public state | Meaning |
|---|---|
| Fresh | Current read with comparatively stronger rested coverage and operating room |
| Stretched | Recent work or coverage has narrowed the bullpen's clean options |
| Vulnerable | Current state is materially constrained or operating with limited margin if more work is required |

`data_limited`, refused, stale, incomplete, and unknown are fail-closed outcomes, not a fourth Team State.

### Public arm read labels

The public catalog is:

| Label | Meaning |
|---|---|
| Clean Option | Governed current workload read resolves as a clean option |
| Watch Arm | Usable in the model, but recent work deserves visible context |
| Limited Rest | Recent work creates a governed restriction |
| Unavailable | Governed state or roster authority removes the arm from the current available set |
| Limited Read | Current, trusted evidence is insufficient for a stronger public conclusion |

Internal availability states such as Available, Monitor, Limited, Avoid, and Unavailable may remain calculation inputs. Transitional backend wording may not create a second public vocabulary. Canonical public keys and frontend catalog own the final rendered language.

### Public role labels

- Trusted Arm
- Setup Arm
- Coverage Arm
- Middle Relief Arm
- Limited Read

Role and read are separate chips. A Trusted Arm can carry Limited Rest; a Coverage Arm can be a Clean Option.

### Named bullpen reads

- Bullpen Pressure
- Recovery Window
- Workload Concentration
- Clean Options
- Coverage Safety
- Trusted Arms

Every named read requires a versioned method, public definition, evidence contract, and suppression rule. A read name is not advice.

## 9. Evidence Architecture

Every evidence item contains:

- stable identity;
- governed kind;
- human label;
- machine value where applicable;
- frozen display value;
- unit;
- exact window;
- as-of timestamp;
- source type and durable references;
- method version;
- public route when available;
- explanation of why it supports the claim;
- evidence-specific limitations.

Public prose, evidence panels, share artifacts, alt text, and metadata must resolve from the same canonical facts. No renderer or caption writer may retype or recalculate a meaning-bearing value when the canonical object owns it.

Evidence is selected by explanatory value, not visual convenience. A team read should prefer recent workload, active/available distribution, named concentration, multi-day use, starter/rotation context when authoritative, current performance context when complete, and roster/reinforcement constraints.

Confidence is a profile of what was verified, not a percentage that hides multiple failure modes.

## 10. Freshness and Failure Scope

Every data domain has an expected cadence and a failure consequence. The governing rule is:

> Staleness degrades scope. It never silently degrades accuracy.

Examples:

- missing probable starter -> suppress starter exposure; preserve independent workload;
- missing pitch data -> suppress velocity/movement observations; preserve appearance evidence;
- unresolved active roster -> suppress active-option and current-availability counts; preserve historical appearances;
- incomplete appearance ledger -> suppress every downstream workload read dependent on that game.

Yesterday's value may remain visible only when explicitly labeled historical. A stale value is never presented as current.

## 11. Observation and Story Governance

Every observation must be meaningful, specific, evidence-backed, explainable, reproducible, freshness-aligned, limitation-aware, non-predictive, and tied to a governed observation family.

A team story should name the relevant relievers when evidence supports it. A bullpen state with no names is incomplete when the underlying arms can be identified.

Approved internal story shapes include heavy workload, concentrated, thin, recovering, contrast, churn, transfer, and signature change. Shape selection occurs before copy. If no shape qualifies, the correct output is silence.

Suppress when a required domain is stale, sample is too small, claim is obvious or repetitive, evidence cannot name the relevant entity, candidate observations conflict, vocabulary guard fails, or a material limitation would make the claim misleading.

Every suppression should record candidate identity, team/arm/date scope, reason code, required and observed source state, failed trust rule, and whether failure was data, freshness, novelty, conflict, or language.

## 12. Trusted Publication and Memory

### Trusted snapshots

A trusted snapshot preserves source provenance, product date and data-through date, required slate coverage, appearance-ledger completeness, freshness, publication status, and typed refusal reason when a gate fails.

### Team-progressive publication

An individual team may publish after that team's final game and team-scoped evidence pass even while unrelated games remain unfinished. A late unrelated game must not block a trustworthy team artifact.

The team-progressive authority proves finality, resolved participants, committed appearance ledger, current team data-through date, team-specific active-bullpen coverage, unique immutable source identity, and correction-sensitive evidence revision.

### Share Artifact

A Share Artifact is a permanent, versioned record of a BaseballOS public claim at one exact time. It stores team identity, public state and explanation, ordered evidence, freshness, trust profile, limitations, approved routes, copy, source authority, schema/render/payload versions, and integrity/deduplication identity.

The artifact - not the image, browser component, caption, or metadata - is the source of truth.

Published meaning-bearing content is immutable. Corrections create a new authority, replacement, or superseding artifact. Historical and current state remain separate.

Integrity mismatch, stale source, insufficient evidence, conflict, unsupported public state, copy-guard failure, duplicate equivalence, or unavailable renderer produces a typed refusal or fail-closed response, never a partial publication.

## 13. Methodology Versioning and Corrections

Every derived metric and observation family has a stable name, plain-language definition, effective date, source/input requirements, algorithm, minimum sample, suppression behavior, freshness dependencies, and version identifier.

Changing a definition creates a new version. Historical observations remain bound to the method that produced them.

A material correction workflow:

1. detect and bound the discrepancy;
2. identify authoritative source and affected fields;
3. produce a read-only repair plan or manifest;
4. review dependent fields, action counts, and evidence;
5. apply through governed, idempotent write paths;
6. verify storage rollback and semantic authority;
7. reconcile local and official values as applicable;
8. invalidate or rebuild every dependent evidence family;
9. republish through normal trust gates;
10. supersede or withdraw affected immutable artifacts without rewriting them;
11. record incident and prevention rule.

## 14. Public-Copy Rules

Public copy is deterministic, backend-owned where meaning-bearing, and filled from governed evidence.

Never write manager intent, private health conclusions, future certainty, betting/fantasy language, rankings, or unsupported causal claims.

Prefer observed history with a window:

- not "the manager will go to him"; use completed deployment history;
- not "warning sign"; state the observed velocity change;
- not "needs a day off"; state the appearances and pitches in the window;
- not "bullpen edge"; state the observable differences and stop.

Internal terms such as payload, algorithm, constrained inventory, model output, schema expression, confidence percentage, or system-derived intelligence do not belong in reader-facing baseball copy.

## 15. Admission and Review

A metric or observation family becomes public only when it is understandable, deterministic, reproducible, source-authorized, useful, stable, sample-governed, suppressible, versioned, and capable of producing a meaningful observation without crossing constitutional boundaries.

Before publication verify source authority, completeness, currentness, evidence alignment, sample sufficiency, public-copy clarity, limitation materiality, artifact integrity, destination routes, historical/current separation, and no unknown-as-zero or silent fallback.

## 16. Current Capability Registry - July 29, 2026

| Capability | Status |
|---|---|
| Completed-game workload and appearance ledger | Production; publication-critical |
| Canonical recorded-outs authority and derived decimal innings | Production |
| Active roster and team assignment | Production |
| Arm workload/availability engine | Production; internal ladder mapped to public labels |
| Public role and arm-read labels | Production |
| Team State Fresh/Stretched/Vulnerable | Production |
| Team Operations readiness | Production / internal source |
| Trusted league snapshots | Production |
| Team-progressive publication | Production |
| Immutable Share Artifact domain and public historical page | Production foundation |
| Browser PNG renderer | Transitional |
| Current-versus-shared comparison | Planned / gated |
| Starter exposure / rotation load transfer | Partial |
| Canonical season bullpen aggregation - team-side relief totals | Production - internal; official validation reconciled; no public reader |
| Current Active-Pen Performance family contract | Established - see Section 7A; governs every later performance metric |
| Current Active-Pen ERA (M-001) | Planned - contract pending implementation; not public; formula and minimum sample not yet approved |
| Pitch-characteristic trends | Experimental / planned |
| Leverage concentration | Partial / planned |
| Organizational reinforcement depth | Partial / planned |
| Weather/environment | Deferred |

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Consolidated source authority, data domains, vocabulary, evidence, freshness, suppression, trusted publication, immutability, correction, methodology versioning, public-copy rules, and current capability state. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Expanded performance context into the reusable Current Active-Pen Performance family contract (Section 7A): active-group, window, sample, date/freshness, evidence, evidence-level, and limitation contracts. Added the metric-family and metric-registry model with M-001 Current Active-Pen ERA reserved as contract-pending and non-public (Section 7B). Corrected the capability registry to separate the production-internal season bullpen aggregation from the unimplemented public metric. State is not performance, canonical integer outs, and historical appearance-team ownership are preserved unchanged. |
