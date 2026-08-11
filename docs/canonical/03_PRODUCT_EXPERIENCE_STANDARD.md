# BaseballOS Product Experience Standard

| Field | Value |
|---|---|
| Status | Canonical - public surface, navigation, interaction, accessibility, and end-state authority |
| Version | 1.4 |
| Effective date | August 11, 2026 |
| Owner | Nickolis Kacludis |
| Supersedes | BaseballOS Product Vision Specification and overlapping surface descriptions in prior strategy documents |
| Update rule | Revise when a page mission, navigation model, information hierarchy, primary user question, public route, failure behavior, or surface acceptance test changes |
| Review cadence | At every material public-surface change; full review before each season |

> **Every surface answers one baseball question, then shows the receipt.**

## 1. Purpose

This Standard defines what a person should understand, feel, inspect, and do on every BaseballOS surface.

It owns page missions, one-question contracts, surface hierarchy, navigation, mobile behavior, loading/empty/stale/error behavior, accessibility, and acceptance tests.

It is not an implementation plan. The Roadmap controls sequence. The Architecture Manual controls technical delivery. The Bullpen Intelligence Standard controls what claims and evidence the experience may present.

## 2. Product Experience Promise

A BaseballOS visit should produce one of two honest outcomes:

1. The user learns one true, specific, non-obvious thing about a bullpen and can inspect why it is true.
2. The user clearly understands why a trustworthy read is not currently available.

The product must never make the user perform the final interpretation alone merely because data exists.

## 3. Universal Experience Principles

### One question per page

Every public page owns one primary user question. If two pages answer the same question, narrow, merge, or retire one.

### One canonical home per fact

| Fact or job | Canonical home |
|---|---|
| Daily lead | Today / The Slate |
| Complete league state | Dashboard |
| One team's current bullpen picture | Team Board |
| One team's current active-pen performance | Team Board |
| Two-team difference | Compare |
| Find a reliever | Reliever Finder |
| One arm's current workload | Pitcher Detail |
| Deeper current story feed | Stories |
| Historical published claim | Share Artifact / future Archive |
| Definitions and computation | Methodology |
| Reader-facing public vocabulary map | About and How to Read |
| Currentness, coverage, and validation | Data & Trust |
| Product orientation | Start Here / About and How to Read |
| Operational coverage and refusals | Internal Product Intelligence |

Other surfaces may inherit, summarize, or link. They must not independently recalculate or redefine.

### Altitude discipline

BaseballOS has six user altitudes:

- daily edition;
- league;
- game/comparison;
- team;
- arm;
- meta/trust.

A page may link across altitudes, but its primary answer stays at one altitude.

### Answer before data

The default hierarchy is:

```text
Plain answer
-> Why it matters
-> Named evidence
-> Freshness
-> Limitations
-> Deeper inspection
```

A table may support the answer. It is not the answer unless the page's explicit job is search or reference.

### Evidence is the destination

Every claim should eventually reach real events: game date, opponent, appearance, pitches, outs, batters faced, rest, roster transaction, official starter, source, and method.

### Names are content

Team-level reads should name the relievers carrying the relevant workload or structure whenever the evidence supports it. Generic labels alone are orientation, not complete understanding.

### Freshness is ambient

The reader should immediately know which baseball date is represented, when the product updated, whether a game is upcoming/in progress/final, and whether the read is current, historical, partial, or stale.

### Mobile is the primary daily context

Tier 1 surfaces must provide plain answers without horizontal scrolling, readable team and arm names, visible freshness, one-gesture evidence access, 44-by-44-pixel practical touch targets, and no essential hover-only behavior.

### Quiet is designed

A quiet day may show fewer stories, a compact league state, an honest no-material-change message, or a limited/unavailable read with the reason. It must not manufacture drama or fill space with generic observations.

### Trust language must not overpower baseball

Trust should be visible and accessible, but the hierarchy is:

1. say the baseball thing;
2. show the receipt;
3. state the material limitation;
4. link to methodology and boundaries.

### No dead ends and no loops

Every page has an obvious deeper evidence step and an obvious next baseball destination. A specific claim links to its specific evidence destination, never only to the homepage.

## 4. Public Page Map

| Surface | Current route pattern | Altitude | One question |
|---|---|---|---|
| Today | `/` | Daily edition | What is the bullpen story today, and what deserves attention tonight? |
| Dashboard | `/dashboard` | League | Across MLB, which bullpens are Fresh, Stretched, or Vulnerable, and where should I look closer? |
| Team Board | current bullpen team view | Team | What is this bullpen's observable current state, which arms are carrying it, and why? |
| Compare | current bullpen comparison view | Game / two teams | How do these two bullpen pictures differ right now? |
| Reliever Finder | current bullpen pitcher finder | Arm utility | How do I find a reliever and inspect his current BaseballOS record? |
| Pitcher Detail | current detail route/drawer | Arm | What has this reliever recently carried, what is his public read, and what supports it? |
| Stories | `/stories` | League narrative | Beyond today's lead, which supported bullpen storylines remain live? |
| Share Artifact | `/share/{public_id}` | Historical claim | What exactly did BaseballOS publish at that time, why, and on what evidence? |
| Team Preview | `/team/{ABBR}` | Distribution entry | What did BaseballOS know about this bullpen, through what baseball date, and where is the current board? |
| Methodology | `/methodology` | Meta | How does BaseballOS compute and govern what it shows? |
| Data & Trust | `/trust` | Meta | Is the current picture complete and trustworthy enough to use? |
| About / How to Read | current support routes | Meta | What is BaseballOS, what does it show, and what do the recurring terms mean? |
| Internal Product Intelligence | authenticated internal routes | Operator | Are publication, evidence coverage, refusal, and distribution systems working as designed? |

Future routed team URLs may replace current selectors. The page question does not change when the route changes.

## 5. Navigation Model

The public navigation should expose a small number of clear lanes:

- Today
- Dashboard
- Bullpen / Team Board
- Stories
- Methodology
- Data & Trust

Start Here/About/How to Read may support first-time understanding from header, footer, or onboarding rather than competing as another primary lane.

Internal tools are absent from public navigation and protected server-side.

Navigation behavior:

- the logo returns to Today;
- league views drill to teams;
- team views link to arms and Dashboard;
- Compare links to both teams;
- Share pages link to the current team destination, Methodology, and Data & Trust;
- evidence links reach exact receipts or the closest governed evidence section.

## 6. Public Vocabulary Presentation

The public vocabulary is defined by the Bullpen Intelligence Standard and canonical code owners. This Standard governs how those labels reach a reader: which family the reader is being shown, how families stay apart, and who may change a word.

### One semantic owner per family

Every public vocabulary family has exactly one semantic owner. The owner decides what the words mean and which word applies. No second surface, adapter, view module, or presentation layer may hold a competing dictionary for the same family, and no family may borrow a word that already belongs to another family.

### Backend-governed labels render verbatim

A backend-authored public label is final reader-facing wording, not an input to further wording. Presentation renders the supplied string exactly as supplied.

Presentation owns layout, density, ordering within a governed order, tone, icons, color, interaction, and accessibility treatment. Presentation does not own meaning: it may not translate, paraphrase, abbreviate, re-case, substitute, or derive a governed label, and it may not supply a fallback label where the authority supplies none. A surface with no supported label shows the governed absent-value message for that family.

### Team State

- Fresh
- Stretched
- Vulnerable

Dashboard, Today where Team State appears, Team Board, and Compare all consume the same backend-authored public Team State fields. Presentation may render the supplied label, choose layout and density, and attach a non-semantic tone keyed by the supplied canonical state. Presentation may not derive a Team State, reinterpret an internal availability or readiness value, infer one from counts, lanes, stress, or freshness, or substitute a fallback label. A surface with no supported Team State shows a governed non-state message; it never shows Unknown, Neutral, or any other fourth state.

Team State is never inferred from supporting reads, arm availability, board group counts, tier adjectives, or Read Confidence.

### Arm Availability

- Available
- On Watch
- Limited
- Unavailable

Arm Availability is the current availability classification for one arm.

### Pitcher Role

- Trusted Arm
- Setup Arm
- Coverage Arm
- Middle Relief Arm
- Role Unclear

Pitcher Role describes observed bullpen usage shape. It is not current availability and it is not pitcher quality. `Trusted Arm` belongs to this family alone.

### Pitcher Current Read

- Clean Option
- Watch Arm
- Limited Rest
- Unavailable
- Limited Read

Pitcher Current Read describes the current workload and availability evidence for one arm.

Pitcher Role and Pitcher Current Read answer different questions. They are presented as separate values, and neither is derived from the other.

Arm Availability and Pitcher Current Read may be related — both speak to current usability — but they are separate vocabularies and are never interchangeable. A surface renders the family it was given.

### The Limited family

Three public labels share the word `Limited`, and a fourth is routinely read as part of the same ladder. They answer four different questions:

| Label | Family | Meaning |
|---|---|---|
| Limited | Arm Availability | Recent workload materially narrows how fully the pitcher can be used. |
| Limited Rest | Pitcher Current Read | Recent workload leaves materially less rest than a Clean Option. |
| Limited Read | Pitcher Current Read / evidence limitation | BaseballOS does not have enough current evidence for a clear pitcher read. |
| Role Unclear | Pitcher Role | Observed usage does not support a reliable public bullpen-role classification. |

These are four different dimensions, not four severity levels of one concept: how much of the arm is usable, how rested it is, how much evidence exists, and what kind of arm it is. No surface may ladder, order, or style them as degrees of the same thing.

### Read Confidence

- High
- Medium
- Low
- Unavailable

Read Confidence describes how clear or complete the evidence behind a read is. It is an evidence-quality presentation family, not a baseball conclusion: it is not Team State, not Arm Availability, not Pitcher Role, not pitcher quality, not a ranking, and not a prediction. It always appears under its own field label, so a bare High or Low can never be read as a baseball verdict.

### Board group presentation

Reader-facing board group headings:

- Available Arms
- On-Watch Arms
- Limited Arms
- Unavailable — Heavy Workload
- Unavailable — Severe Workload

These headings name workload groups. The underlying engine statuses — Available, Monitor, Limited, Avoid, Unavailable — are unchanged, and the headings change no classification, membership, count, or ordering behavior. A group heading is a presentation label for a workload group; it is not a pitcher's public read label and is never presented as one.

### Bullpen supporting reads

Canonical supporting concepts:

- Late-Inning Availability
- Rested Options
- Late-Inning Pressure
- Workload Concentration
- Coverage Safety
- Depth Safety
- Late-Inning Options

Rested Options tiers: Deep Rested Options, Stable Rested Options, Thin Rested Options, Very Thin Rested Options.

Each supporting read explains one dimension of a bullpen. Supporting reads are not Team State. No supporting read, tier adjective, count, or combination of them constitutes, implies, or overrides a Team State, and a surface without a supported Team State never assembles one from them.

`Trusted Arms` is retired as a team-level concept; `Trusted Arm` now belongs exclusively to the Pitcher Role family. `Healthy Rested Bullpen` is retired: BaseballOS observes public workload, never player health.

### Freshness

- **Data through** - the latest completed baseball date the public read represents.
- **Last data update** - when BaseballOS last successfully wrote new baseball data.
- **Last checked** - when BaseballOS most recently attempted or observed a refresh.

These are three separate reader-facing temporal concepts. No surface collapses them into one stamp or uses one to stand for another.

### Data Status

- Current
- Partial Data
- Stale
- Data Unavailable

Data Status describes the state of the data, never a bullpen or an arm, and so it borrows no baseball word. `Healthy`, `Limited`, and `Not Current` are not Data Status labels. `Limited` remains valid Arm Availability vocabulary.

### Provenance

- Generated at
- Published at

These are provenance timestamps for historical and distribution artifacts. They are not synonyms for Data through or Last data update.

Internal engine codes never appear as public labels.

## 7. Standard Claim Component

Every substantial claim component contains:

1. team or arm identity;
2. public state or read label;
3. one plain-language why sentence;
4. two to four named or event-level receipts;
5. data-through or updated time;
6. compact trust or coverage indicator when material;
7. specific limitation only when it changes interpretation;
8. exact evidence or destination link.

The component may shrink on small surfaces, but it may not become a naked label.

## 8. Loading, Empty, Stale, Error, and Integrity States

### Loading

- stable skeleton matching final hierarchy;
- no fake numbers, placeholder teams, or guessed labels;
- avoid layout shifts that move the main claim.

### Empty / quiet

- explain whether nothing meaningful was found or no data exists;
- offer the most relevant next destination;
- do not present quiet as an error.

### Stale / partial

- state the represented data-through date;
- name the affected scope;
- preserve independent valid sections;
- do not use a full-page alarm when one evidence family is unavailable.

### Error

- say what could not be loaded;
- preserve already verified independent historical content;
- provide retry only when retry is meaningful;
- never fall back to unverified cached meaning.

### Integrity failure

- display no meaning-bearing artifact content;
- state that verification failed;
- do not show the claim with a warning badge.

## 9. Accessibility and Visual Character

Every public surface must provide one clear H1, logical heading order, semantic lists and tables, keyboard-accessible controls, visible focus, text-and-structure state cues rather than color alone, sufficient contrast, reduced-motion respect, explicit dates/time zones, alt text for images that carry meaning, and plain-language equivalents for charts.

BaseballOS should feel like a compact intelligence report and serious baseball product:

- deep navy/charcoal foundation;
- high-contrast off-white text;
- restrained blue and muted gold accents;
- semantic state accents used with text;
- strong condensed/display headlines;
- highly readable body and evidence type;
- photo-free by default for system-generated intelligence artifacts;
- no fake team logos, AI player likenesses, cinematic tunnels, smoke, sparks, or sportsbook styling.

## 10. Surface Priority

| Tier | Surfaces | Investment rule |
|---|---|---|
| Tier 1 | Today/Slate, Team Board, Dashboard, Methodology, Data & Trust | Highest quality and reliability; may block lower-tier work |
| Tier 2 | Pitcher Detail, Stories, State Timeline, Observation Archive | Deepen understanding and authority after Tier 1 is healthy |
| Tier 3 | Compare, Reliever Finder, creator/share tools | Support exploration and distribution without becoming the center |
| Internal | Product Intelligence and operations | Protect trust, observability, and sustainable operation |

## 11. Today - Daily Edition

**Mission:** be the page a baseball fan can open once each day and quickly understand the most important supported bullpen development and relevant pregame context.

**One question:** What is the bullpen story today, and what deserves attention tonight?

Above the fold:

1. dated edition identity and data-through line;
2. one lead read in plain baseball language;
3. named teams/arms and strongest receipt;
4. two or three watch items or slate notes;
5. destination to the team board and evidence.

Required supporting sections include What Changed when trusted comparability is valid, a compact Dashboard teaser, trustworthy slate notes when schedule/game status is authoritative, and a quiet state when no observation deserves a lead.

Never on Today: full 30-team tables, competing scorecards, more than a handful of equal-weight leads, black-box scores, a second league summary, stale pregame framing after first pitch, or a selected lead merely because it is dramatic.

**End state:** a finite 60- to 90-second daily edition with one lead, a few notes, movement context, receipts, direct team links, visible game status, and no requirement to scan the entire league.

## 12. The Slate - End-State Daily Flagship

The Slate is the approved evolution of Today's game-aware section, not a competing homepage.

**One question:** What do tonight's games ask of these bullpens, and what observable condition will each bullpen bring if the game reaches it?

Each game card includes matchup, local first pitch, explicit status, one plain-language bullpen sentence per side, two to four named arms per side, recent starter-length history rather than forecast, structural note when authoritative, and freshness/evidence links.

Ordering by story strength is allowed only when the method is inspectable and not a hidden quality ranking. Games between ordinary, fully supported bullpens may be collapsed rather than assigned manufactured storylines.

**Ten-second test:** ninety minutes before first pitch, a knowledgeable fan can read one card and repeat one true, non-obvious bullpen fact without interpreting a model score.

## 13. Dashboard - League Board

**Mission:** provide the single full-league orientation surface.

**One question:** Across MLB, which bullpens are Fresh, Stretched, or Vulnerable, and where should I look closer?

Primary hierarchy: league freshness line, all 30 teams grouped/organized by canonical Team State, compact counts/evidence per team, one league-level sentence when supported, and direct team links.

Keep roster/off-active context separate from workload, movement annotation only when trusted comparison exists, current state versus historical labeling clear, and first-time explanation compact.

Never on Dashboard: another league leaderboard in different vocabulary, sortable quality rankings, composite team scores, full roster/appearance logs, or generic disclaimers louder than the state.

## 14. Team Board - Product Center of Gravity

**Mission:** be the definitive public page for one MLB bullpen.

**One question:** What is this bullpen's observable current state, which arms are carrying it, and why?

Above the fold:

1. full team identity;
2. current Fresh/Stretched/Vulnerable state;
3. plain-language why sentence;
4. named supporting arms/evidence;
5. current arm groups under the canonical board group headings;
6. data-through and trust state.

Required evidence includes recent relief work, appearance dates/opponents/outs or innings/pitches/rest, current active-roster context, current performance context when approved, official starter/rotation-transfer context when complete, What Changed since the last comparable trusted date, schedule/recovery runway when current, and explicit limits.

Role and read remain separate. The official starter is never inferred from first appearance order or role shape. Historical appearances remain assigned to the team represented at that game.

### Current active-pen performance ownership

The Team Board is the **canonical public home** for current active-pen performance: it owns the complete presentation and the evidence path. It is not the computational owner. Every surface, including the Team Board, consumes the same backend-owned canonical performance authority defined by the Current Active-Pen Performance Contract in the Bullpen Intelligence Standard.

The Team Board's one question does not change. Performance is added evidence inside the existing question, never a second page mission and never a competing team score.

Placement rule, within the page hierarchy that already exists:

```text
Current state (Fresh / Stretched / Vulnerable)
-> Why sentence
-> Named arms and recent relief work
-> Current active-pen performance
-> Roster, starter, and schedule context
-> Freshness
-> Material limitation
```

State and Why stay above performance. A performance value never becomes the page's headline answer and never replaces the state label.

A performance component must show, at minimum, the value or its explicit below-sample read, the group size and sample, the represented baseball date, and a route to its evidence. Below its approved minimum sample it shows the approved below-sample read with the reason — never a zero, a prior value, or a blank.

For M-001, specified in Bullpen Intelligence Standard Section 7C, that resolves to:

- **Public name:** Active Bullpen ERA. Never paraphrased, never abbreviated to "Bullpen ERA," never rewritten as a caption.
- **Value:** two decimal places, always, rendered exactly as the backend supplies it. `0.00` is a real value and is rendered as a number, never as a dash or a missing state. The frontend never rounds, re-rounds, or reformats.
- **Below sample:** **Not Enough Innings Yet**, with the group's current relief innings and the required innings beside it. A bare label is not permitted — Section 15 prohibits unexplained thresholds, and this is one.
- **Group:** both the group size and the contributing-arm count. When they differ, the component says so in one sentence. A difference is normal information and is never styled as a warning, an error, or a degraded state.

A performance component is never the page's headline answer and never replaces the state label, whatever its value.

Drill-down expectation: the component satisfies Level 1 and Level 2 of the family's evidence levels in place, and provides one interaction that reaches Levels 3 and 4 — named pitchers, qualifying appearances, and the official pitching lines behind them. A compact rendering may show less; it may not become a naked number.

Aligned inheritance by other surfaces:

- **Pitcher Detail** may show arm-specific performance evidence for one reliever.
- **Compare** may show aligned team values only when product date, method version, freshness, and group contract are comparable on both sides. Otherwise it shows neither side.
- **Today, Dashboard, Stories, and Share Artifacts** may inherit or link to an approved value.
- No surface independently recalculates the metric or paraphrases its meaning.

Historical Share Artifacts freeze the metric, group, method, sample, date, evidence, and limitation that existed at publication. They never recalculate from live membership.

## 15. Methodology and Limits - Tier 1 Trust Surface

Methodology is Tier 1 because it makes every other surface credible.

It must explain the public promise, a worked example from official appearance to public read, public Team State and arm-read definitions, named-read definitions, derived metrics and methods, source authorities, freshness/suppression behavior, the complete Unobservable Ledger, corrections and historical immutability, and version history/change log.

Never show internal implementation prose without translation, unexplained thresholds, legal disclaimers replacing product limitations, or duplicate definitions that drift from canonical code.

## 16. Compare

**Mission:** make observable differences between two bullpen pictures easy to understand without selecting a winner.

**One question:** How do these two bullpen pictures differ right now?

Require current trusted state for both teams, complete product date and freshness context, aligned definitions/method versions, and no mixing of historical and live claims without explicit labeling.

Never use edge, lean, recommendation, pick, hidden composite score, head-to-head history as prediction bait, or stale data on one side presented as equal to current data on the other.

## 17. Reliever Finder

**Mission:** provide a search-first utility for finding a reliever and reaching the evidence, not a workload leaderboard.

Search by name, optionally team/role filters, show team/public role/public read/freshness, link directly to Pitcher Detail, and keep results keyboard-accessible.

Never default sort by score, best/worst tables, giant workload tables that replace search, hidden starters mixed into the reliever universe, or stale values presented without status.

## 18. Pitcher Detail

**Mission:** give one reliever a complete evidence-first current workload record.

Above the fold: full identity/current team authority, public role, current read, one why sentence, latest appearance/recent workload, freshness and roster status.

Required evidence: appearance ledger, pitches/outs/batters faced/rest, multi-day patterns, role sample and ambiguity, inherited-runner context, performance and pitch-characteristic trends when approved, and historical observations when an archive exists.

Never use naked 0-100 scores, radar/threshold chrome that turns an internal index into the product, health conclusions, mixed starter/reliever roles forced into unsupported labels, or current-team history that silently rewrites past appearances.

## 19. Stories

**Mission:** provide a finite, browsable feed of supported bullpen observations beyond Today's lead.

Every story contains story shape/family, named team/arms, plain-language observation, evidence receipts, window/data-through date, limitation where material, exact destination, and no duplicate of Today's lead unless Stories is the deeper destination.

The feed may group workload, recovery, concentration, roster/coverage, role/deployment, rotation transfer, pitch signature, and league context. Organization may not imply a quality ranking.

## 20. Immutable Share Artifact Page

**Mission:** serve as the permanent citation destination for one historical BaseballOS publication.

It displays historical-snapshot label, artifact identity and generated/published time, original read, ordered evidence, freshness/source authority, trust profile, limitations, methodology/Data & Trust links, current live Team Board link clearly labeled as current, supersede/withdraw handling, and future current-versus-shared comparison only when governed comparability ships.

Published artifacts remain unchanged. A current-state panel never rewrites the historical artifact. Integrity failure serves no claim.

## 21. Routed Team Preview Pages

**Mission:** give a shared team link a truthful, self-dating entry representation that hands the reader to the current Team Board.

`/team/{ABBR}` is a regenerating distribution surface, not an immutable historical Share Artifact. It is rebuilt on the publication cadence, it has no supersession lifecycle, and it is never a citation destination - `/share/{public_id}` remains the only permanent citation. It cites current truth; it never becomes current truth.

A generated team preview carries team identity, canonical public Team State or the governed non-state, one backend-authored baseball point, the baseball data-through date the claim describes, the time the representation was generated, the trusted publication identity it was generated from, and an explicit link to the current Team Board. The same claim is readable in the social preview, in machine-readable metadata, and in the page body.

One publication per representation. The story copy and the team state on a single generated page come from the same trusted published snapshot. A board that resolved from a different publication is not combined with that story, and the live builder is never a source for a public preview.

Publication time is not the baseball date. Generated time, trusted-snapshot publication time, and data-through are three separate values and are published as three separate values. A representation generated on one day legitimately describes baseball data through an earlier day; that is correct, and it is only correct because the page states both.

If the trusted publication authority or the data-through value cannot be established, the page publishes no present-tense team claim. It keeps team identity and the current Team Board link and states plainly that it has no dated read.

The state vocabulary is the canonical public Team State dictionary. Internal team-shape read labels are not public state terms on this surface.

Presentation and runtime code do not reinterpret this metadata. The values are backend-authored; the page renders them, and no frontend derives, re-dates, or restates them.

## 22. Future Historical Surfaces

### State Timeline

Shows how one bullpen's state changed across the season, annotated with workload events, off-days, transactions, extra innings, roster changes, and published observations.

### Observation Archive

Preserves every published observation as a permanent record with URL, timestamp, frozen evidence, method version, correction/supersession history, and observable follow-up.

A six-month-old observation must reproduce the original evidence and method.

## 23. Data & Trust

**Mission:** make currentness, provenance, validation, and limitations inspectable without forcing the user through operational jargon.

Required sections: data-through date, latest successful sync/update, source coverage by domain, trusted snapshot publication status, appearance-ledger completeness, public usage/backtest samples with clear framing, known limitations, recent material corrections/method changes, independent non-affiliation statement, and direct Methodology links.

Avoid alarming complete-page language when only one evidence family is unavailable. State the exact affected scope.

## 24. Start Here / About and How to Read

A unified future Start Here experience may replace duplicate support pages.

How to Read is the canonical reader-facing semantic map. It is organised by the Section 6 families - Team State, Arm Availability, Pitcher Role, Pitcher Current Read, Read Confidence, bullpen supporting reads, and the freshness, Data Status, and provenance stamps - and it names each family alongside its labels so a reader always knows which question a word answers. It renders the canonical definitions; it holds no vocabulary of its own.

It must state the difference between the similar terms explicitly rather than leave it to inference, including `Limited`, `Limited Rest`, `Limited Read`, and `Role Unclear`, each shown with its family. It must also record that supporting reads are not Team State and that Read Confidence is not a baseball conclusion.

It should contain one-sentence positioning, difference between state and performance, Team State definitions, Arm Availability labels, Pitcher Role labels, Pitcher Current Read labels, named reads, evidence/freshness contract, one concise boundary statement, and links to Today, Dashboard, and Methodology.

A first-time visitor should explain BaseballOS in one sentence, correctly interpret the canonical Team State, Arm Availability, Pitcher Role, and Pitcher Current Read vocabulary, and tell the four Limited-family terms apart.

## 25. Internal Product Intelligence and Operations

**Mission:** give the founder a secure, read-only view of publication, evidence coverage, artifact status, refusal diagnostics, and user-journey health.

Current internal surfaces include artifact generation/coverage, traffic/distribution intelligence, trusted snapshot/generation audits, refusal/failure reason review, and operational diagnostics.

Security requirements: absent from public navigation, noindex/nofollow, authenticated server-side, no admin token in browser, no private routes cached, founder/allowlist protection, read-only by default, and explicit confirmation for mutation.

## 26. Universal Acceptance Tests

Every public surface must pass:

- **Question test:** owns one clear user question.
- **Ten-second test:** primary answer is understandable quickly.
- **Receipt test:** every substantive claim reaches real evidence.
- **Freshness test:** represented date/status is visible.
- **Stranger test:** first-time visitor understands what BaseballOS is doing.
- **Skeptic test:** hostile reader can check method and limits.
- **Vocabulary test:** public labels match canonical authority, render verbatim, and stay inside their declared semantic family.
- **Refusal test:** no prediction, betting, fantasy, health, ranking, or manager-intent claim.
- **Quiet-day test:** no story is manufactured.
- **Mobile test:** primary answer works without horizontal scrolling.
- **Accessibility test:** meaning does not depend on color, hover, or sight alone.
- **Failure test:** missing/stale domains reduce scope without inventing values.
- **Navigation test:** next evidence step and broader return path are obvious.
- **Consistency test:** evidence and claim cannot disagree.

## 27. Surface Change and Retirement

Before changing a page, state the existing one-question contract, name the user who notices, identify the canonical fact owner for every new value, preserve altitude, define loading/quiet/stale/partial/error behavior, define mobile/accessibility, define the evidence destination, and update this Standard if the mission changes.

Retire or merge a surface when it no longer owns a unique question, another page answers better, it exists mainly because code already exists, it repeatedly needs explanatory navigation, it creates vocabulary drift, or it does not end in evidence.

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Established the permanent page map, experience principles, surface missions, current/end-state boundaries, mobile/accessibility standards, failure behavior, and acceptance tests for BaseballOS. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Established the Team Board as the canonical public home for current active-pen performance, with placement below State and Why, minimum component requirements, evidence drill-down expectations, and aligned inheritance rules for Pitcher Detail, Compare, Today, Dashboard, Stories, and Share Artifacts. The Team Board owns presentation, not computation. One question per page and one canonical home per fact are preserved. |
| 1.2 | July 30, 2026 | Nickolis Kacludis | Recorded the approved M-001 presentation contract on the Team Board: the public name Active Bullpen ERA, fixed two-decimal rendering with a real zero shown as a number, the below-sample read Not Enough Innings Yet rendered only with its counts, and the required group-size and contributing-arm disclosure. The frontend renders and never recalculates or re-rounds. No gate is opened. |
| 1.3 | August 10, 2026 | Nickolis Kacludis | Recorded the routed team preview surface (`/team/{ABBR}`) as a regenerating distribution entry representation rather than an immutable historical artifact, and fixed its authority and freshness contract: one trusted publication per representation, canonical Team State or the governed non-state, a named baseball point, a published data-through date kept distinct from generated and publication time, a snapshot receipt, an explicit current Team Board handoff, and no present-tense team claim when authority or data-through cannot be established. No page mission, vocabulary catalogue, or computation changes. |
| 1.4 | August 11, 2026 | Nickolis Kacludis | Reconciled public vocabulary ownership after VOC-001: one semantic owner per public family, and backend-governed labels rendered verbatim by a presentation layer that owns layout, density, tone, icons, color, interaction, and accessibility treatment but never meaning. Separated the public families explicitly - Team State, Arm Availability, Pitcher Role, Pitcher Current Read, and Read Confidence - and recorded that Pitcher Role and Pitcher Current Read answer different questions, that Arm Availability and Pitcher Current Read are not interchangeable, and that Read Confidence is an evidence-quality family rather than a baseball conclusion. Recorded the board group headings as presentation labels for workload groups over unchanged engine statuses, and the bullpen supporting reads as single explanatory dimensions that never constitute a Team State. Recorded the Limited / Limited Rest / Limited Read / Role Unclear distinction with each term's family, retired `Trusted Arms` and `Healthy Rested Bullpen`, and clarified the freshness, Data Status, and provenance stamps as separate concepts. Named How to Read the canonical reader-facing semantic map. No model, threshold, classification, capability, authority, or prediction behavior changes. |
