# BaseballOS Product Experience Standard

| Field | Value |
|---|---|
| Status | Canonical - public surface, navigation, interaction, accessibility, and end-state authority |
| Version | 1.1 |
| Effective date | July 29, 2026 |
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

The public vocabulary is defined by the Bullpen Intelligence Standard and canonical code owners.

### Team State

- Fresh
- Stretched
- Vulnerable

### Arm read

- Clean Option
- Watch Arm
- Limited Rest
- Unavailable
- Limited Read

### Public role

- Trusted Arm
- Setup Arm
- Coverage Arm
- Middle Relief Arm
- Limited Read

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
5. current arm groups using public read labels;
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

A performance component must show, at minimum, the value or its explicit unavailable read, the group size and sample, the represented baseball date, and a route to its evidence. Below its approved minimum sample it shows a limited or unavailable read with the reason — never a zero, a prior value, or a blank.

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

## 21. Future Historical Surfaces

### State Timeline

Shows how one bullpen's state changed across the season, annotated with workload events, off-days, transactions, extra innings, roster changes, and published observations.

### Observation Archive

Preserves every published observation as a permanent record with URL, timestamp, frozen evidence, method version, correction/supersession history, and observable follow-up.

A six-month-old observation must reproduce the original evidence and method.

## 22. Data & Trust

**Mission:** make currentness, provenance, validation, and limitations inspectable without forcing the user through operational jargon.

Required sections: data-through date, latest successful sync/update, source coverage by domain, trusted snapshot publication status, appearance-ledger completeness, public usage/backtest samples with clear framing, known limitations, recent material corrections/method changes, independent non-affiliation statement, and direct Methodology links.

Avoid alarming complete-page language when only one evidence family is unavailable. State the exact affected scope.

## 23. Start Here / About and How to Read

A unified future Start Here experience may replace duplicate support pages.

It should contain one-sentence positioning, difference between state and performance, Team State definitions, arm-read labels, public role labels, named reads, evidence/freshness contract, one concise boundary statement, and links to Today, Dashboard, and Methodology.

A first-time visitor should explain BaseballOS in one sentence and correctly interpret the canonical state, arm-read, and Limited Read vocabulary.

## 24. Internal Product Intelligence and Operations

**Mission:** give the founder a secure, read-only view of publication, evidence coverage, artifact status, refusal diagnostics, and user-journey health.

Current internal surfaces include artifact generation/coverage, traffic/distribution intelligence, trusted snapshot/generation audits, refusal/failure reason review, and operational diagnostics.

Security requirements: absent from public navigation, noindex/nofollow, authenticated server-side, no admin token in browser, no private routes cached, founder/allowlist protection, read-only by default, and explicit confirmation for mutation.

## 25. Universal Acceptance Tests

Every public surface must pass:

- **Question test:** owns one clear user question.
- **Ten-second test:** primary answer is understandable quickly.
- **Receipt test:** every substantive claim reaches real evidence.
- **Freshness test:** represented date/status is visible.
- **Stranger test:** first-time visitor understands what BaseballOS is doing.
- **Skeptic test:** hostile reader can check method and limits.
- **Vocabulary test:** public labels match canonical authority.
- **Refusal test:** no prediction, betting, fantasy, health, ranking, or manager-intent claim.
- **Quiet-day test:** no story is manufactured.
- **Mobile test:** primary answer works without horizontal scrolling.
- **Accessibility test:** meaning does not depend on color, hover, or sight alone.
- **Failure test:** missing/stale domains reduce scope without inventing values.
- **Navigation test:** next evidence step and broader return path are obvious.
- **Consistency test:** evidence and claim cannot disagree.

## 26. Surface Change and Retirement

Before changing a page, state the existing one-question contract, name the user who notices, identify the canonical fact owner for every new value, preserve altitude, define loading/quiet/stale/partial/error behavior, define mobile/accessibility, define the evidence destination, and update this Standard if the mission changes.

Retire or merge a surface when it no longer owns a unique question, another page answers better, it exists mainly because code already exists, it repeatedly needs explanatory navigation, it creates vocabulary drift, or it does not end in evidence.

## Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | July 29, 2026 | Nickolis Kacludis | Established the permanent page map, experience principles, surface missions, current/end-state boundaries, mobile/accessibility standards, failure behavior, and acceptance tests for BaseballOS. |
| 1.1 | July 29, 2026 | Nickolis Kacludis | Established the Team Board as the canonical public home for current active-pen performance, with placement below State and Why, minimum component requirements, evidence drill-down expectations, and aligned inheritance rules for Pitcher Detail, Compare, Today, Dashboard, Stories, and Share Artifacts. The Team Board owns presentation, not computation. One question per page and one canonical home per fact are preserved. |
