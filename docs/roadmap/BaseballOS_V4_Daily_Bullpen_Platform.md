# BaseballOS V4 Roadmap: Daily Bullpen Platform

This is the canonical execution roadmap for BaseballOS V4. It is a living
roadmap for building BaseballOS into a daily bullpen platform: a product people
can return to before games, understand quickly, share clearly, and trust.

This document records order, boundaries, decision rules, and review cadence. It
does not authorize product-code changes by itself. Each implementation phase
must still ship through its own scoped branch, review, validation, and commit.

## V4 Operating Thesis

BaseballOS becomes useful when it becomes a daily read, not only a reference
tool. V4 should make the product worth opening every day by answering a small
set of durable baseball questions:

- Which bullpens are fresh tonight?
- Which bullpens are stretched?
- Which teams have late-game margin?
- What changed since yesterday?
- Which team should I follow first?

The product should stay descriptive, checkable, and baseball-native. It should
make bullpen context easier to understand without turning into picks,
predictions, private injury claims, or certainty about manager decisions.

## V4 North Star

V4 should make BaseballOS the clearest daily public read on MLB bullpen context.

The user should be able to open BaseballOS before the slate and understand:

- the league-wide bullpen picture;
- the team they care about;
- what changed since yesterday;
- why each read exists;
- how current the data is;
- what BaseballOS cannot know.

## What V4 Is

V4 is the Daily Bullpen Platform pass.

It is:

- a daily home experience;
- a team-following experience;
- a clearer change-detection loop;
- a shareable team-context layer;
- a weekly content and digest foundation;
- a measured path toward creator, analyst, and paid beta validation.

V4 should make the current bullpen intelligence easier to return to, easier to
understand, and easier to share.

## What V4 Is Not

V4 is not:

- a betting product;
- a fantasy product;
- a prediction product;
- a private injury product;
- a live play-by-play product;
- a manager-intent product;
- a new backend scoring rewrite;
- a new route architecture rewrite;
- a place to broaden product promises before trust and usage prove demand.

## Product Loop

V4 should strengthen this loop:

1. A user opens BaseballOS before the slate.
2. They understand the daily bullpen picture.
3. They follow or inspect a team.
4. They see what changed since yesterday.
5. They share a clean team card or story.
6. They return through the next daily read or weekly digest.

Each roadmap item should either improve the loop, measure the loop, or protect
trust inside the loop.

## Non-Negotiable Guardrails

- BaseballOS remains descriptive, not predictive.
- No picks.
- No betting advice.
- No fantasy positioning.
- No private injury claims.
- No certainty about manager decisions.
- No hidden scoring terms in public copy.
- No internal terminology in user-facing product surfaces.
- No sample, fallback, or stale state may appear as current live data.
- Freshness, data-through dates, and limitations must stay visible.
- New surfaces must fail closed when data is missing, stale, or unsafe.
- Roadmap work must not broaden API, data, scoring, or route behavior unless
  that phase explicitly authorizes it.

## Audience Priority

V4 should optimize in this order:

1. Baseball-curious fans who want a clear pregame bullpen read.
2. Analysts, writers, and creators who need fast, checkable context.
3. Team-focused users who want one club's daily bullpen picture.
4. Power users who may later want alerts, digests, exports, or premium workflow.

The first user should never need to understand BaseballOS internals. The power
user should be able to inspect evidence and freshness when they need it.

## V4 Roadmap Order

1. Canon V4 roadmap document
2. Analytics / event tracking
3. Launch foundation cleanup
4. Follow My Team
5. Daily Bullpen Home
6. What Changed Since Yesterday
7. Team pages
8. Shareable team cards
9. In-product weekly content system
10. Injury / IL / depth pressure context
11. Starter exposure context
12. Personalized email digest
13. Creator / analyst mode
14. Feedback and correction loop
15. Pro beta waitlist
16. Monetization validation

## Detailed Phase Plan

### 1. Canon V4 roadmap document

Goal: establish the official V4 execution order, product thesis, guardrails,
authorship rules, and living status table.

Scope:

- Add this canonical roadmap document.
- Link it from the existing docs index pattern.
- Do not change product code.

Exit criteria:

- The roadmap exists at
  `docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md`.
- The title and roadmap order are preserved.
- Lightweight documentation validation passes.

### 2. Analytics / event tracking

Goal: measure whether users understand and return to the product loop.

Scope:

- Track product events for daily home use, team inspection, follow intent,
  share intent, feedback, and digest interest.
- Keep event names stable and readable.
- Avoid sensitive personal data.
- Do not let analytics drive user-facing claims.

Exit criteria:

- Core events are named and documented.
- Product surfaces can report usage without changing baseball reads.
- The metrics plan can distinguish curiosity from repeat behavior.

### 3. Launch foundation cleanup

Goal: remove launch friction before building retention features.

Scope:

- Clean obvious copy drift.
- Confirm footer, docs, trust links, and onboarding pages are coherent.
- Fix small visual or navigational issues that distract from the daily read.

Exit criteria:

- First-session product path is clear.
- Trust and methodology paths are easy to find.
- No launch-critical copy contradicts the descriptive product boundary.

### 4. Follow My Team

Goal: let a user make one team the default daily lens.

Scope:

- Add a lightweight follow/preferred-team flow.
- Store the preference in the safest existing frontend or auth pattern.
- Use the preference to orient daily reads and team links.

Exit criteria:

- A user can choose and change a followed team.
- The product can highlight that team's daily bullpen context.
- The feature does not imply personalized advice.

### 5. Daily Bullpen Home

Goal: make the home page a true daily bullpen read.

Scope:

- Prioritize the league-wide bullpen picture.
- Surface followed-team context when available.
- Show upcoming games only when a reliable slate source is available.
- Keep freshness and limitations visible.

Exit criteria:

- The home page answers what matters today before sending users deeper.
- Empty states are honest and useful.
- No sample or stale state can look current.

### 6. What Changed Since Yesterday

Goal: show the daily movement that creates a reason to return.

Scope:

- Compare current trusted reads against the prior trusted read.
- Explain meaningful availability, workload, and team-state changes.
- Withhold change reads when data is stale, missing, or not comparable.

Exit criteria:

- The user can see what changed without reading every team board.
- Change copy is descriptive and evidence-backed.
- The comparison fails closed when confidence is not warranted.

### 7. Team pages

Goal: create a clean team-level destination for each MLB bullpen.

Scope:

- Present team bullpen state, availability, recent workload, freshness, and
  story context in one shareable place.
- Use existing team/bullpen data contracts where practical.
- Keep team pages readable for first-time visitors.

Exit criteria:

- Each team has a clear bullpen read.
- The page explains evidence and limits.
- Team pages do not require sidebar navigation to be understandable.

### 8. Shareable team cards

Goal: make BaseballOS context easy to share without losing trust.

Scope:

- Create a compact team-card view for fresh, stretched, or vulnerable reads.
- Include data freshness and BaseballOS branding.
- Avoid sensational framing.

Exit criteria:

- A shared card communicates the team read, evidence cue, and freshness.
- The card links back to the fuller team context.
- The shared artifact remains descriptive.

### 9. In-product weekly content system

Goal: create a repeatable editorial surface inside BaseballOS.

Scope:

- Publish weekly bullpen notes using existing descriptive reads.
- Keep content inside the product rather than creating a separate publication
  workflow too early.
- Reuse story and trust patterns where possible.

Exit criteria:

- Weekly content has a consistent format.
- The product can point users from daily reads to weekly context.
- Editorial copy stays within BaseballOS guardrails.

### 10. Injury / IL / depth pressure context

Goal: explain public roster pressure without making private health claims.

Scope:

- Use public roster and IL flags only.
- Explain depth pressure created by unavailable or inactive arms.
- Keep absence of public flags separate from health certainty.

Exit criteria:

- Users can understand public depth constraints.
- The product never implies private medical knowledge.
- Depth pressure is clearly tied to public evidence.

### 11. Starter exposure context

Goal: explain how starter workload or short starts can affect bullpen context.

Scope:

- Use completed-game and recent-start context where data supports it.
- Show when a bullpen may be carrying extra innings because starters have not
  provided length.
- Avoid projecting tonight's starter performance.

Exit criteria:

- Starter exposure is explained as recent context, not a prediction.
- The read helps users understand why a bullpen may be stretched.
- Evidence and freshness remain visible.

### 12. Personalized email digest

Goal: test whether users want BaseballOS delivered to them.

Scope:

- Build a narrow digest around followed teams and daily/weekly bullpen context.
- Keep copy descriptive.
- Include clear unsubscribe and privacy expectations.

Exit criteria:

- Users can opt in.
- The digest can summarize followed-team context without new baseball logic.
- Engagement can be measured without expanding product claims.

### 13. Creator / analyst mode

Goal: support people who turn BaseballOS context into analysis or content.

Scope:

- Provide cleaner copyable summaries, citations, and share paths.
- Emphasize freshness, evidence, and limits.
- Avoid creating an export product before demand is proven.

Exit criteria:

- Analysts can reuse BaseballOS context accurately.
- Shared context points back to the source read.
- The mode does not add advice, ranking, or prediction behavior.

### 14. Feedback and correction loop

Goal: make trust repair visible and operational.

Scope:

- Give users a clear way to report stale, wrong, or confusing reads.
- Track corrections or clarifications internally.
- Preserve product credibility without overpromising response time.

Exit criteria:

- Users can report issues from relevant surfaces.
- Feedback can be triaged by type and affected team/date.
- Corrections do not bypass data or governance rules.

### 15. Pro beta waitlist

Goal: test paid or power-user demand without committing to a paid product.

Scope:

- Create a simple waitlist for users who want deeper workflow.
- Collect only necessary contact and interest context.
- Make clear that pro features are not yet a shipped product.

Exit criteria:

- Demand can be measured.
- User segments and requested workflows are visible.
- No paid promise is made before validation.

### 16. Monetization validation

Goal: decide whether BaseballOS has a viable path beyond a free public product.

Scope:

- Review usage, return rate, follows, shares, digest interest, waitlist demand,
  and qualitative feedback.
- Identify which capabilities create willingness to pay.
- Keep public trust surfaces intact.

Exit criteria:

- A clear go/no-go recommendation exists for the next monetization step.
- The decision is evidence-based.
- Any paid direction preserves the public descriptive trust posture.

## Metrics and Review Cadence

V4 should be reviewed through product behavior, not optimism.

Primary metrics:

- daily active readers;
- returning readers;
- followed-team adoption;
- team-page visits;
- What Changed engagement;
- share-card clicks;
- weekly content opens;
- digest opt-ins;
- feedback submissions;
- waitlist conversion.

Review cadence:

- Review metrics after each shipped phase.
- Review the full roadmap order after each major product loop milestone.
- Keep this document current when scope, order, status, or guardrails change.
- Do not skip trust review for speed.

## Claude vs. Codex Execution Rules

Execution work must stay scoped to the branch and phase being requested.

Use Claude for:

- founder-facing product narrative;
- roadmap and strategy drafting;
- copy direction and editorial framing;
- high-level product critique.

Use Codex for:

- repository edits;
- implementation branches;
- tests and validation;
- git hygiene;
- commit and push execution.

Execution rules:

- Do not mix planning and implementation unless the branch explicitly asks for
  both.
- Do not broaden a scoped phase because later roadmap items depend on it.
- Do not add product code on documentation-only branches.
- Do not treat roadmap language as authorization to ship unplanned behavior.

## Commit/Authorship Rules

- Nickolis Kacludis is the sole author and maintainer.
- Commits must use `Nickolis Kacludis <nickoliskacludis@gmail.com>` as author
  and committer unless Nickolis explicitly directs otherwise.
- Do not add co-author trailers.
- Do not add tooling attribution.
- Do not work directly on `main`.
- Feature branches must be scoped, named clearly, validated, committed, and
  pushed before review.
- Merges must preserve Nickolis as the sole author/committer unless Nickolis
  explicitly directs otherwise.

## Living Roadmap Status Table

| Order | Phase | Status | Notes |
| --- | --- | --- | --- |
| 1 | Canon V4 roadmap document | In progress | Adds this canonical roadmap and docs links. |
| 2 | Analytics / event tracking | Complete | Owned V4 event catalog, helper, and current-surface instrumentation are in place. |
| 3 | Launch foundation cleanup | Not started | Small trust, copy, and launch-readiness cleanup. |
| 4 | Follow My Team | Not started | First personalization loop. |
| 5 | Daily Bullpen Home | Not started | Make Today the daily read. |
| 6 | What Changed Since Yesterday | Not started | Main return habit loop. |
| 7 | Team pages | Not started | Dedicated team-level destinations. |
| 8 | Shareable team cards | Not started | Shareable daily team context. |
| 9 | In-product weekly content system | Not started | Repeatable editorial system. |
| 10 | Injury / IL / depth pressure context | Not started | Public roster pressure context only. |
| 11 | Starter exposure context | Not started | Recent starter-length context, not projection. |
| 12 | Personalized email digest | Not started | Opt-in delivery test. |
| 13 | Creator / analyst mode | Not started | Copyable, citeable analysis workflow. |
| 14 | Feedback and correction loop | Not started | Trust repair and correction intake. |
| 15 | Pro beta waitlist | Not started | Demand validation before paid scope. |
| 16 | Monetization validation | Not started | Evidence-based business decision. |

## Final Operating Principle

BaseballOS should become a daily habit because it makes bullpen context easier
to understand, not because it overclaims what it can know.
