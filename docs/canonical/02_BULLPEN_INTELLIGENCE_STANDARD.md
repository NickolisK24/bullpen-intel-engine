# BaseballOS Bullpen Intelligence Standard

| Field | Value |
|---|---|
| Status | Canonical - intelligence, data, evidence, methodology, and publication authority |
| Version | 1.4 |
| Effective date | August 14, 2026 |
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

Public vocabulary is bound by this class. A reader-facing label may not use a word whose ordinary baseball meaning asserts an unobservable - medical status, soreness, injury absence, or private physical condition - even when the value behind it is computed purely from observed workload. Section 8 records the retirement this rule required.

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

Current Active-Pen ERA is the first implemented metric under this family. Its Team Board public reader is approved; it is not itself the family contract and it remains unavailable to Team State and Share Artifact performance consumers.

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

The family owns the mechanism. Each metric registry entry owns its exact threshold, threshold unit, and denominator. No generic threshold is established here, and none may be invented at implementation time.

A metric's minimum sample is stated in **its own denominator's unit**. A rate over innings is gated on recorded outs, never on appearance count: ten one-out appearances is ten outs, and an appearance-count gate would admit a sample the metric cannot support. The threshold, its unit, and its authority travel with the value.

M-001's approved threshold is 108 recorded outs — 36.0 innings — under D-023. See Section 7C.

Below-sample behavior:

- no numeric value is published;
- no zero, prior, league, or estimated value is substituted;
- the result is represented as a limited performance read using the approved public wording;
- the exact machine refusal code belongs to the canonical code registry at implementation time.

A zero denominator is a **separate** refusal, evaluated before any sample check and reported as the governed reason `era_denominator_zero`. "This group has not pitched" and "this group has not pitched enough" are different facts, and a reader inspecting a refusal must be able to tell them apart.

Public wording is subordinate to this contract and may not create a second vocabulary. `Limited Read` and `Unavailable` are governed **arm-read** labels in the canonical public-label authority and have never been authorized as team-level performance labels; `Monitor` is an internal availability state that stays internal. The approved public wording for a below-sample performance read is **Not Enough Innings Yet**, under D-026, and it is never rendered without the group's current count and the required count beside it.

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

The exact required fields at each level are filled per metric. M-001's filled contract is in Section 7C and is the template every later metric under this family fills. A metric may add fields at Levels 2 and 3. It may not add a level, rename a level, reorder the chain, or make a required field optional. **A value whose evidence cannot reach Level 4 is not publishable.**

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

| ID | Registry name | Public name | Family | Status |
|---|---|---|---|---|
| M-001 | Current Active-Pen ERA | Active Bullpen ERA | Current Active-Pen Performance | Implemented for Team Board — see Section 7C |
| M-002 | Current Active-Pen WHIP | Active Bullpen WHIP | Current Active-Pen Performance | Implemented for Team Board — see Section 7D |

M-001's formula, denominator, minimum sample, precision, public name, below-sample wording, evidence contract, and membership rule **are** established by D-023 through D-030 and recorded in Section 7C. M-002's separately approved authority is recorded in Section 7D. Both are public only on the Team Board and remain subject to the normal trust gates.

No other metric may be added to this registry as implemented, approved for public use, or production-ready.

Candidate later entries — K%, BB%, K-BB%, HR/9, LOB%, inherited-runner outcomes, and FIP/xFIP/SIERA — remain candidates only. Each requires its own approved source, formula, sample, and publication contract before it becomes a registry entry. What each inherits automatically and what it must define for itself is fixed by D-030 and recorded immediately below.

### What a metric inherits and what it defines

A metric under an established family **inherits unchanged** and may not redefine: the governing question and scope; the active-group authority and its resolution date; the window contract and its exclusions; appearance-team authority with no current-team fallback; integer recorded outs as the innings authority; fail-closed publication with typed refusal codes; the prohibition on unknown-as-zero and the rule that one unusable qualifying row refuses the whole read; date and freshness stamps; the four evidence levels and their required fields; the family limitation; the rounding mechanics in Section 7C; the gate model, since no metric opens its own gate; and the canonical public home, since no surface recalculates.

A metric **defines for itself**: its stable key and version; its public rendered name; the question it answers at Level 1; its formula, numerator, and denominator; the source fields it cannot be computed without; its displayed precision; its minimum sample value, unit, and authority; its denominator-zero refusal code; any metric-specific limitation; its approved surfaces; and its deterministic fixtures.

A metric may be registered before its minimum sample is approved. It will compute and refuse to publish. Before it may publish it needs an approved formula, an approved minimum sample with its authority, an approved public name, and a declared precision.

**Standing rule:** a metric whose required source domain is Experimental, Partial, or Deferred in the capability registry of Section 16 may not be registered until that domain reaches Production. Registering it earlier creates a governed metric that can never satisfy evidence Level 4.

## 7C. M-001 Current Active-Pen ERA - Metric Specification

Approved July 30, 2026 by D-023 through D-030. Public name **Active Bullpen ERA**. Registry name and stable identity unchanged.

**M-001 is published only on the Team Board.** The Team Board reader gate is open under the August 21, 2026 implementation decision. `team_state_performance_gate` and `share_card_performance_gate` remain blocked.

### Formula and denominator authority

| Field | Value |
|---|---|
| Formula | `earned_runs * 27 / recorded_outs` |
| Numerator | total earned runs over the qualifying appearance set, multiplied by 27 |
| Denominator | total **integer recorded outs** over the qualifying appearance set |
| Unit | earned runs per nine innings |
| Zero denominator | refuse with `era_denominator_zero`, before any sample check |

Integer outs are the denominator because decimal MLB innings notation does not sum — `2.1` is seven outs, and adding the notation as decimals is arithmetically wrong — because float accumulation is not reproducible across recomputation or inside a frozen artifact, and because the Level 3 evidence must add up to the Level 2 denominator with no remainder. Decimal innings are derived for display and never participate in the calculation. This preserves D-008 unchanged.

### Minimum sample

| Field | Value |
|---|---|
| Threshold | **108 recorded outs (36.0 innings)** |
| Unit | recorded outs |
| Authority | D-023 |
| Below threshold | publish no number; render the approved below-sample read |

The threshold is derived, not chosen. One additional earned run moves the published value by exactly `27 / outs`; 108 outs is the smallest whole-out sample at which a single earned run cannot move the value by more than 0.25 — the smallest difference between two bullpens a baseball reader would treat as meaningful. The derivation depends only on the formula, so the threshold does not need revision when a season or a run environment changes.

### Rounding and precision

These mechanics are family-wide. Each metric declares only its own displayed precision.

| Layer | Rule |
|---|---|
| Internal | exact integers only; no floating-point type participates at any stage |
| Ratio | exact `Decimal` quotient of the two integers, never `float` division |
| Rounding | `ROUND_HALF_UP`, applied exactly once, at the declared precision |
| Stored | exact integer numerator, exact integer denominator, and the rounded value as a fixed-precision decimal string |
| Displayed | the stored string verbatim, trailing zeros preserved; the frontend never rounds, re-rounds, truncates, or reformats |

M-001's declared displayed precision is **two decimal places, always**.

Half-up rather than round-half-to-even, because a reader must be able to reproduce the value by hand and because baseball has published ERA half-up for a century. Rounded once, because a value rounded at computation, again at storage, and again at display can differ from the exact value by more than the published increment.

| Earned runs | Outs | Innings shown | Numerator | Exact quotient | Published |
|---|---|---|---|---|---|
| 31 | 289 | 96.1 | 837 | 2.896193... | **2.90** |
| 12 | 108 | 36.0 | 324 | 3.0 | **3.00** |
| 0 | 130 | 43.1 | 0 | 0.0 | **0.00** |
| 1 | 216 | 72.0 | 27 | 0.125 | **0.13** |
| 8 | 66 | 22.0 | 216 | 3.272727... | refused - below sample |
| 4 | 0 | 0.0 | 108 | undefined | refused - `era_denominator_zero` |

A real zero is published as `0.00`. A group that has allowed no earned runs over 43.1 innings has an observed, checkable value of zero, and it is never rendered as missing, as a dash, or as an unavailable read.

### Below-sample public read

> **Not Enough Innings Yet**

Rendered only with its own numbers adjacent:

> **Not Enough Innings Yet** - this group has thrown 22.0 relief innings for Cincinnati; 36.0 are required.

The count and the requirement are mandatory. `Limited Read`, `Unavailable`, and `Monitor` are forbidden here: the first two are governed arm-read labels with established meanings about a single pitcher, and the third is an internal availability state carrying an implied instruction. The wording states insufficient evidence without implying poor performance, hidden data, or system failure.

### Active-group membership with no qualifying usage

A reliever resolved into the active bullpen who has no qualifying relief appearances for this team is **included in the group and contributes zero qualifying appearances**. His zero outs and zero earned runs enter no numerator and no denominator, because M-001 is a ratio over recorded work and not an average of per-pitcher rates.

This is not unknown-as-zero. An unknown is a value that exists and is missing from the record; a no-usage member has an **observed** count of zero appearances for this team. Substituting a league rate, a prior-club rate, or a zero rate for him would be imputation and is prohibited.

Every read therefore reports two counts - **group size** and **contributing arms**. Where they differ, Level 2 discloses the difference in one sentence. A difference is normal information, never an error state. Because the sample threshold is evaluated in outs, a group padded with non-contributing members cannot cross the sample gate on membership alone.

His appearances for a prior organization stay with that organization. D-009 is unchanged.

### Evidence contract

| Level | Required for M-001 |
|---|---|
| 1 Summary | public name; the published value, or the below-sample read with its counts, or the typed refusal; represented baseball date; freshness state |
| 2 Context | group size and contributing-arm count; qualifying appearance count; total recorded outs and derived display innings; exact numerator and exact denominator; minimum sample, its unit, and its authority; method version and effective date; the material limitation where it applies |
| 3 Evidence | every group member named with his qualifying appearance count and outs, including members with zero; every qualifying appearance as a row carrying game identifier, game date, opponent, appearance-team identifier, recorded outs, and earned runs; the reason any line was excluded where material |
| 4 Official record | the named source authority for each appearance; appearance-team authority status and source per row; schedule and finality authority per game; method version and effective date |

Optional at any level: opponent branding, doubleheader game number, rest and usage context, and per-arm rate values. A per-arm rate publishes only against that arm's own approved sample.

Prohibited at every level: league averages, prior-period values, projections, rankings, quality adjectives, and any value presented without its group and sample.

### Limitation

The family limitation applies unchanged. One metric-specific limitation is added while it holds:

> Active-bullpen membership resolves from the governed bullpen population as of the represented date and is not yet guaranteed complete for a newly active arm with no usage-based role evidence.

## 7D. M-002 Current Active-Pen WHIP - Metric Specification

Approved August 21, 2026 for the Team Board only. Public name **Active Bullpen WHIP**; method version `1.0.0`.

| Field | Value |
|---|---|
| Formula | `(walks + hits_allowed) * 3 / recorded_outs` |
| Required inputs | official `baseOnBalls`, official hits allowed, integer recorded outs on every qualifying line |
| Population/window | inherited unchanged from Current Active-Pen Performance |
| Zero denominator | refuse with `whip_denominator_zero` |
| Precision | two decimal places, using the Section 7C single `ROUND_HALF_UP` boundary |

`baseOnBalls` is the official walk total. Intentional walks remain walks for official record-keeping and therefore remain inside this input. Hit batsmen, errors, and fielder's-choice reaches are not inputs. The numerator and denominator are pooled exact integers; pitcher WHIP values and displayed innings are never aggregated.

### Completeness and sample

Every qualifying row must carry non-null, non-negative hits, walks, and recorded outs. One missing or malformed required value refuses M-002; the row is never dropped and the value is never replaced by zero. The canonical writer preserves an omitted hit or walk as null so the metric can enforce this rule. M-001 remains independently usable when only a WHIP input is unavailable.

M-002 independently adopts **108 recorded outs (36.0 innings)** as its minimum sample. This is not inherited from ERA: it is a separate M-002 decision over the same innings denominator and family window. At 108 outs one added hit or walk moves exact WHIP by `3 / 108 = 0.027777...`, bounding a single-event movement below 0.03 before display rounding. Below the threshold no numeric WHIP is published, and the existing **Not Enough Innings Yet** read carries the current and required innings.

Evidence adds exact hit and walk totals and the three required row inputs to M-002's existing four-level family chain. Team State, Share Artifact, historical comparison, rankings, and every non-Team-Board surface remain blocked.

## 8. Public Vocabulary

Internal engine states may remain granular. They do not automatically become public language.

### Semantic families and their owners

Public language is organized into semantic families. A family owns one question, one catalogue of labels, and one semantic owner in code. The owner decides what the words mean and which word applies. Nothing downstream may hold a second dictionary for the same family.

| Public family | Question it answers | Semantic owner |
|---|---|---|
| Team State | What is this bullpen's canonical high-level current condition? | `backend/services/team_state_public_vocabulary.py` |
| Arm availability | Is this arm currently available, and how fully? | `backend/services/public_bullpen_copy.py` |
| Pitcher role | How has this arm been used? | `backend/services/pitcher_public_labels.py` |
| Pitcher current read | What does this arm's current workload evidence say? | `backend/services/pitcher_public_labels.py` |
| Bullpen supporting reads | What does one dimension of this bullpen look like? | `backend/services/team_bullpen_shape.py` |
| Workload Data | How complete and how recent is the workload record behind this one arm's read? | Backend `availability.data_state`; public label catalogue in `frontend/src/components/bullpen/availabilityView.js` |

Team State is not arm availability, is not pitcher role, is not pitcher current read, is not read confidence, and is not a bullpen supporting read. These are not synonyms. No family may serve as a fallback or a substitute for another, and a surface that cannot resolve one family fails closed inside that family rather than borrowing a label from a neighbor.

- **Team State** - the canonical high-level descriptive team conclusion, produced through the governed Team State authority.
- **Arm availability** - the governed current availability classification for one arm, produced by the approved availability methodology over current authority inputs.
- **Pitcher role** - a public classification of observed bullpen usage shape. It describes how the pitcher has been used. It is not current availability, talent, quality, manager intent, or a recommendation.
- **Pitcher current read** - a public description of the current workload and availability evidence for one pitcher. It answers a current-context question and does not replace pitcher role.
- **Read confidence** - a presentation of how clear or complete the evidence behind a read is. It is not Team State, not availability, not pitcher role, not pitcher quality, not a ranking, and not a prediction.
- **Bullpen supporting read** - a deterministic explanatory dimension of the current bullpen picture. A supporting read may explain why a team picture is understandable. It does not itself become Team State.

### Backend-governed labels and the frontend boundary

For governed public vocabulary the backend decides the semantic label, and the frontend renders the label it was supplied.

Presentation may own non-claim presentation metadata: layout, tone, style, iconography, and accessibility treatment. It may not translate, paraphrase, substitute, reclassify, or invent a fallback semantic label for a governed family. The frontend semantic-substitution path that once rewrote pitcher role and pitcher current-read labels on the way to the screen is retired. The label a reader sees is the label the owner emitted.

This rule is scoped to governed semantic vocabulary. Genuinely frontend-owned, non-claim presentation copy is unaffected by it.

### Team State

The canonical public Team State vocabulary is exactly:

| Public state | Meaning |
|---|---|
| Fresh | Current read with comparatively stronger rested coverage and operating room |
| Stretched | Recent work or coverage has narrowed the bullpen's clean options |
| Vulnerable | Current state is materially constrained or operating with limited margin if more work is required |

`data_limited`, refused, stale, incomplete, and unknown are fail-closed outcomes, not a fourth Team State.

**Implementation ownership.** `backend/services/team_state_public_vocabulary.py` is the sole semantic owner of the internal-to-public mapping and of the projection from a governed Team Operations readiness result into the reader-facing `public_state` and `public_label` fields. Every live reader surface carries that backend-authored block; no route handler, serializer, board builder, comparison builder, frontend adapter, component, or static-preview script holds a second mapping. A fail-closed outcome carries no public state and no label, only a governed non-state message. Team State is a team-level read, so a league-wide surface carries the non-state block rather than a league-shaped pseudo-state.

Only that authority may publish a Team State. No supporting-read tier, tier adjective, group count, availability label, pitcher current read, or read-confidence value may be translated into one, and no surface may assemble a Team State from them.

### Arm availability

The public availability catalog is exactly:

| Public label | Meaning |
|---|---|
| Available | Recent workload leaves the arm inside the normal availability range |
| On Watch | The arm remains usable, and recent workload deserves visible context |
| Limited | Recent workload materially narrows how fully the arm can be used |
| Unavailable | Governed workload or roster authority removes the arm from the currently available set |

`backend/services/public_bullpen_copy.py` maps the internal availability states into these final reader-facing labels. The internal engine vocabulary - Available, Monitor, Limited, Avoid, Unavailable - remains a calculation input where it is needed. `Monitor` and `Avoid` are internal-only states whose reader-facing forms are `On Watch` and `Unavailable`; neither internal word reaches a reader.

### Pitcher current read - public arm read labels

The public catalog is:

| Label | Meaning |
|---|---|
| Clean Option | Governed current workload read resolves as a clean option |
| Watch Arm | Usable in the model, but recent work deserves visible context |
| Limited Rest | Recent work creates a governed restriction |
| Unavailable | Governed state or roster authority removes the arm from the current available set |
| Limited Read | Current, trusted evidence is insufficient for a stronger public conclusion |

Transitional backend wording may not create a second public vocabulary. `backend/services/pitcher_public_labels.py` owns the final rendered language for this family.

Arm-read labels describe **one pitcher**. None of them may be reused for a team-level performance metric, in either direction.

**Availability and current read are related and not interchangeable.** The same underlying evidence may contribute to both. Availability is the governed current availability classification; the current read is the reader-facing interpretation of current workload and evidence attached to that pitcher. Neither may be substituted for the other merely because some labels carry similar meanings. `Unavailable` legitimately appears in both catalogues, because in both it means the pitcher is not counted as currently available - but the surrounding family still determines which question is being answered.

### Pitcher role - public role labels

- Trusted Arm
- Setup Arm
- Coverage Arm
- Middle Relief Arm
- Role Unclear

Role and read are separate chips. A Trusted Arm can carry Limited Rest; a Coverage Arm can be a Clean Option.

**The two families fail closed separately.** `Role Unclear` means observed usage evidence is insufficient for a reliable public role. `Limited Read` means current evidence is insufficient for a clear pitcher current read. These are different absences answering different questions, and they may not share one public label. The role family's earlier use of `Limited Read` is retired.

`Trusted Arm` belongs to this family alone. The former team-level concept `Trusted Arms` is retired: its team-level definition mixed role with current workload and roster usability context, so one public word carried two hierarchy levels. The team-level supporting concept is now **Late-Inning Options** - current late-inning arms whose workload and roster context leave them usable in the represented read. It describes usability. It never says a manager will use them.

### Bullpen supporting reads - named bullpen reads

The canonical supporting dimensions are:

- Late-Inning Availability
- Rested Options
- Late-Inning Pressure
- Workload Concentration
- Coverage Safety
- Depth Safety

together with **Late-Inning Options**, the team-level late-inning usability concept described above.

Every named read requires a versioned method, public definition, evidence contract, and suppression rule. A read name is not advice.

Each supporting read is tiered inside its own dimension - Strong Late-Inning Availability, Stable Rested Options, High Late-Inning Pressure, Concentrated Workload, Thin Coverage Safety, Limited Depth Safety, and their siblings. The tier adjectives - Strong, Stable, Deep, Thin, Very Thin, Limited, High, Elevated, Manageable, Low - carry no Team State meaning by themselves. Only the Team State authority may publish Fresh, Stretched, or Vulnerable. No surface may translate a supporting-read tier into a Team State, and the frontend may explain or display these concepts but may not independently derive a competing public tier system.

**Retired for private-health language.** `Healthy Rested Bullpen` is retired from the reader-facing supporting vocabulary. `Healthy` can imply medical status, soreness, injury absence, or other private physical-health knowledge that BaseballOS does not observe and that Section 2 classes as Unobservable. That tier is now **Stable Rested Options**, and the family is named for what it actually measures - rested options. This is a wording correction only: tier count, tier order, and every clean-options, workload, availability, and supporting-read boundary are unchanged.

### Read confidence

The public read-confidence scale is exactly High, Medium, Low, and Unavailable.

Read confidence is a public evidence-quality presentation family, not another baseball-state or read classification. It is always rendered under its own field label, so a bare High or Low can never be read as a Team State, an availability label, or a baseball conclusion. The raw internal confidence values are unchanged; only the reader-facing scale is governed here. Read confidence is not a recommendation score and is not a confidence grade about a future outcome.

### Workload Data

Workload Data describes the state of the workload record behind **one arm's** read: how complete it is and how recent it is. It is a governed public family, and it is the only family that speaks about evidence coverage for a single pitcher.

The public catalog is exactly:

| Public label | Meaning |
|---|---|
| Current | The arm's latest workload information is inside the active freshness window |
| Outside Freshness Window | Workload history exists, but the latest appearance is older than the active freshness window |
| No Workload Record | No recent workload history is available for this pitcher |
| Incomplete Workload Inputs | Some workload inputs are incomplete, so the read should be treated cautiously |
| Fetch Failed | The latest workload fetch failed, so the read is unresolved until a refresh succeeds |
| Historical | The read is based on an older workload record |
| Unavailable | BaseballOS has no usable workload data state for this pitcher |

**Workload Data is not Data Status.** Data Status - Current, Partial Data, Stale, Data Unavailable, in Section 10 - describes the state of the published platform read. Workload Data describes one arm's underlying workload record. They can disagree honestly: a current published read may still carry an arm whose own workload record is outside the freshness window. A surface may not use one as a fallback for the other, and neither may borrow a baseball word.

**Ownership.** The backend decides the state. `availability.data_state` is emitted by the availability authority, and it is the semantic decision: nothing downstream may derive, infer, or override it. The governed public label catalogue for those states currently resides in shared frontend utilities (`frontend/src/components/bullpen/availabilityView.js`, with the reader glossary in `frontend/src/utils/bullpenConcepts.js`). That is an implementation location, not a transfer of semantic authority: the wording is governed by this Section, the catalogue may not add, rename, or reinterpret a state on its own, and an unrecognised state fails closed to `Unavailable` rather than borrowing a neighbouring label. Relocating the catalogue to a backend or shared semantic owner is a permitted implementation change and requires no change to this contract.

### Public performance vocabulary

| Term | Meaning | Authority |
|---|---|---|
| Active Bullpen ERA | Public name of M-001; earned runs per nine innings over official completed relief work for this team by the arms in its active bullpen on the represented date | D-028 |
| Not Enough Innings Yet | The approved below-sample read for a performance metric, always rendered with the group's current count and the required count | D-026 |

This is the complete approved public performance vocabulary. No surface, caption, or post may paraphrase either term or invent a third.

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

### Reader-facing temporal vocabulary

Freshness reaches a reader through separate stamps that answer separate questions:

| Term | Meaning |
|---|---|
| Data through | The represented completed baseball date. |
| Last data update | The last successful baseball-data write. |
| Last checked | The last refresh or observation attempt. |
| Generated at | Artifact creation provenance. |
| Published at | Trusted publication provenance. |

These are different clocks. No surface collapses them into one value or uses one to stand for another. This restates for reader-facing language the separation Section 7A already requires of the represented baseball date; it establishes no new temporal model.

The reader-facing data-status family - Current, Partial Data, Stale, Data Unavailable - describes the state of the published platform read, never a bullpen or an arm, and therefore borrows no baseball word. `Limited` remains arm-availability vocabulary.

The per-arm Workload Data family in Section 8 answers the neighbouring question - how complete and how recent the workload record behind one arm is. The two are separate stamps about separate subjects, they are rendered under separate field labels, and neither substitutes for the other.

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
| Current Active-Pen Performance framework | Production foundation - reusable group resolution, qualifying-appearance selection, sample evaluation, evidence assembly, and fail-closed surface-specific publication; Team Board consumes only approved M-001 |
| Current Active-Pen ERA / Active Bullpen ERA (M-001) | Production - Team Board public reader; formula, denominator, minimum sample, precision, public name, below-sample wording, evidence contract, and membership rule unchanged; Team State and Share Artifact gates blocked |
| Current Active-Pen WHIP / Active Bullpen WHIP (M-002) | Production - Team Board public reader; complete official hits, walks, and recorded outs required on every qualifying line; Team State and Share Artifact gates blocked |
| Pitch-characteristic trends | Experimental / planned |
| Leverage concentration | Partial / planned |
| Organizational reinforcement depth | Partial / planned |
| Weather/environment | Deferred |

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Consolidated source authority, data domains, vocabulary, evidence, freshness, suppression, trusted publication, immutability, correction, methodology versioning, public-copy rules, and current capability state. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Expanded performance context into the reusable Current Active-Pen Performance family contract (Section 7A): active-group, window, sample, date/freshness, evidence, evidence-level, and limitation contracts. Added the metric-family and metric-registry model with M-001 Current Active-Pen ERA reserved as contract-pending and non-public (Section 7B). Corrected the capability registry to separate the production-internal season bullpen aggregation from the unimplemented public metric. State is not performance, canonical integer outs, and historical appearance-team ownership are preserved unchanged. |
| 1.2 | July 30, 2026 | Nickolis Kacludis | Specified M-001 in a new Section 7C: formula and denominator authority, the derived 108-out minimum sample stated in the denominator's own unit, family-wide rounding mechanics with worked examples, the approved below-sample read Not Enough Innings Yet, the no-usage call-up membership rule with its two group counts, and the filled four-level evidence contract. Added the inheritance split to Section 7B, the public performance vocabulary to Section 8, and corrected the capability registry. No gate is opened; M-001 remains unimplemented and non-public. |
| 1.3 | August 11, 2026 | Nickolis Kacludis | Established public-language authority in Section 8 after VOC-001: the semantic owner of every governed public family is named in code - Team State wording in `team_state_public_vocabulary.py`, arm availability wording in `public_bullpen_copy.py`, pitcher role and pitcher current read in `pitcher_public_labels.py`, and bullpen supporting reads in `team_bullpen_shape.py`. Separated the families explicitly: Team State, arm availability, pitcher role, pitcher current read, read confidence, and bullpen supporting read answer different questions and may never substitute for one another. Recorded the backend-governed pass-through rule - the backend decides the semantic label, the frontend renders it, and the retired frontend semantic-substitution path may not return - scoped to governed vocabulary. Recorded that only the Team State authority may publish Fresh, Stretched, or Vulnerable, and that no supporting-read tier or adjective becomes a Team State. Separated the two fail-closed labels, Role Unclear for missing usage evidence and Limited Read for missing current-read evidence. Retired the team-level concept `Trusted Arms` in favor of `Late-Inning Options`, reserving `Trusted Arm` to the pitcher-role family. Retired `Healthy Rested Bullpen` in favor of `Stable Rested Options` and tied that retirement to the Unobservable class in Section 2, which now forbids reader-facing labels that assert private physical condition. Clarified the reader-facing temporal stamps and the data-status family in Section 10. No model, threshold, source authority, classification, publication, sync/write, recommendation, or prediction behavior changed. |
| 1.5 | August 21, 2026 | Nickolis Kacludis | Activated M-001 Active Bullpen ERA for the Team Board only, preserving the current-season window, represented current active-bullpen group, team-at-appearance ownership, 108-out sample, fixed precision, evidence chain, and fail-closed behavior. Team State and Share Artifact gates remain blocked; unapproved performance metrics remain withheld. |
| 1.6 | August 21, 2026 | Nickolis Kacludis | Added M-002 Active Bullpen WHIP for the Team Board only: exact pooled hits-plus-walks over integer outs, a separately approved 108-out minimum, two-place half-up display, publication-critical null preservation, and metric-local fail-closed behavior. Other Performance candidates and all non-Team-Board gates remain unchanged. |
| 1.4 | August 14, 2026 | Nickolis Kacludis | Gave the Workload Data family a canonical home in Section 8 (H-12). PR #659 shipped the family into the product because pitcher workload-record status is a different question from platform Data Status, but the meaning existed only in shared frontend utilities, so no canonical document defined it. Section 8 now lists Workload Data among the semantic families with its governing question, records its exact seven-label public catalog, states that Workload Data is not Data Status and that the two may honestly disagree about the same screen, and records the ownership split: the backend decides the state through `availability.data_state` and nothing downstream may derive, infer, or override it, while the governed label catalogue currently resides in shared frontend utilities as an implementation location rather than a transfer of semantic authority, fails closed to `Unavailable` on an unrecognised state, and may be relocated to a backend or shared owner without changing this contract. Section 10 now cross-references the family so the two data-state stamps are separated where a reader meets them. No threshold, classification, derivation, availability rule, source authority, publication gate, or freshness computation changed, and no public label was added, renamed, or retired. |
