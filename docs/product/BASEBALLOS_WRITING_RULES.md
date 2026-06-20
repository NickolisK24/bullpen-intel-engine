# BaseballOS Writing Rules & Narrative Standards

Version: 1.0

Status: Foundational Product Governance Document

Source of truth: This document governs all user-facing BaseballOS language.

Purpose: Define how BaseballOS communicates with users across the entire platform.

---

# Mission

BaseballOS exists to explain bullpen reality.

The platform's purpose is not to predict games, recommend bets, rank teams, or generate hot takes.

BaseballOS helps users understand:

* Which bullpens are carrying the heaviest workloads
* How bullpen usage is evolving
* Where workload concentration is developing
* Which teams have flexibility
* Which teams are losing flexibility
* Why those changes matter

BaseballOS turns bullpen data into baseball understanding.

---

# Core Principle

BaseballOS does not describe metrics.

BaseballOS describes baseball.

Every piece of language should answer:

1. What is happening?
2. Why is it happening?
3. Why does it matter?

If a sentence only answers #1, it is incomplete.

---

# The BaseballOS Voice

BaseballOS should sound like:

* A bullpen analyst
* A baseball operations observer
* A knowledgeable baseball fan

BaseballOS should NOT sound like:

* A spreadsheet
* A statistics report
* A betting model
* An engineering dashboard
* A generic status blurb

---

# What BaseballOS Actually Observes

BaseballOS does not observe scores.

BaseballOS does not observe wins.

BaseballOS does not observe standings.

BaseballOS observes bullpen conditions.

Examples:

* Workload concentration
* Leverage concentration
* Bullpen flexibility
* Bullpen coverage
* Reliever availability
* Trust distribution
* Bullpen stability
* Bullpen stress
* Rotation support
* Injury-related pressure
* Emerging workload trends

The story should always originate from one of these observations.

---

# Translation Layer Requirement

Every story must pass through three layers.

Layer 1: Data

Raw numbers.

Example:

* Three relievers pitched four of the last five days

Layer 2: Baseball Meaning

Interpretation.

Example:

* Workload is becoming concentrated

Layer 3: Story

Human explanation.

Example:

* The bullpen is becoming increasingly dependent on the same small group of trusted relievers.

Stories should NEVER skip Layer 2.

---

# Metrics Are Not Stories

Bad:

"The bullpen has a stress score of 74."

Bad:

"Coverage Safety is Thin."

Bad:

"The bullpen has three Limited relievers."

These are product outputs.

They are not observations.

Good:

"The bullpen still has enough arms available, but fewer trustworthy options for high-leverage situations."

Good:

"The workload burden is increasingly falling on a small group of relievers."

Good:

"Recent usage patterns are reducing the team's flexibility late in games."

---

# Baseball First Language

Always explain baseball consequences.

Instead of:

"The bullpen is stressed."

Use:

"The bullpen may need to spread innings across a wider group of relievers."

Instead of:

"Availability is declining."

Use:

"The manager has fewer trusted options than he had earlier in the week."

Instead of:

"Coverage is weakening."

Use:

"The bullpen's margin for absorbing extra innings is shrinking."

---

# Always Explain The Change

BaseballOS stories should not only describe the current state. They should
explain what is changing, what has changed recently, or what trend is
developing.

Bad:

"The bullpen has limited flexibility."

Better:

"The bullpen has less flexibility than it did earlier in the week because the
same relievers continue absorbing high-leverage innings."

Guidance:

* Prioritize movement over static labels.
* Explain whether flexibility, workload concentration, availability, trust, or
  coverage is improving, worsening, or holding steady.
* Avoid stories that only restate the current condition.

---

# Every Story Needs A Human Managerial Consequence

Every story should make the baseball consequence clear from a manager's
perspective.

Bad:

"The bullpen is becoming concentrated."

Better:

"The bullpen is becoming concentrated, reducing the manager's ability to mix and
match late-game situations."

Guidance:

* Explain how the bullpen condition affects decision-making.
* Focus on available choices, leverage options, coverage, rest, and margin for
  error.
* Make the observation feel like something a manager, bullpen coach, analyst, or
  informed fan would care about.

---

# Stories Must Be Specific

Avoid generic statements that could apply to any team.

Bad:

"The bullpen is under pressure."

Better:

"The bullpen has leaned heavily on three relievers this week while the rotation
has struggled to consistently cover six innings."

Guidance:

* Use concrete baseball context when available.
* Reference the source of pressure: repeated usage, short starts, injuries, thin
  trust group, unavailable arms, extra innings, or high-leverage concentration.
* If a sentence could appear in a generic national baseball article without
  BaseballOS, rewrite it.

---

# Never Expose Internal Systems

Users should never see internal product terminology.

Avoid:

* Fatigue Score
* Stress Score
* Coverage Safety
* Trust Arm Availability
* Depth Safety
* Availability Engine
* Recommendation Engine
* Model Outputs
* Internal Labels

Translate everything into baseball language.

The user should understand the baseball reality, not the machinery behind it.

---

# Focus On Consequences

Every observation should answer:

"So what?"

Example:

Weak:

"The Dodgers have used six relievers heavily."

Better:

"The Dodgers have relied heavily on six relievers, reducing flexibility if games remain close throughout the series."

The second sentence explains why the observation matters.

---

# Preferred BaseballOS Concepts

These concepts should appear frequently.

* Workload concentration
* Bullpen flexibility
* Bullpen depth
* Trusted options
* Leverage innings
* Coverage
* Workload burden
* Relief corps
* High-leverage options
* Multi-inning coverage
* Bullpen stability
* Bullpen pressure
* Rotation support
* Relief workload
* Margin for error

These concepts are part of the BaseballOS identity.

---

# Concepts To Avoid

Avoid generic sports media language.

Examples:

* Dominating
* Clutch
* Choking
* Elite
* Garbage
* Amazing
* Terrible
* Hottest team
* Cold streak
* Momentum

These terms are emotional.

BaseballOS is observational.

---

# Avoid Predictions

BaseballOS explains.

BaseballOS does not predict.

Never write:

* Will win
* Will lose
* Expected to win
* Likely to win
* Lock
* Safe bet

Instead:

"The bullpen enters tonight with more flexibility than it had earlier this week."

That is factual.

---

# Avoid Certainty

BaseballOS deals with changing conditions.

Prefer:

* Appears
* Suggests
* Indicates
* Developing
* Emerging
* Increasingly
* Becoming

Avoid:

* Guaranteed
* Certain
* Definitive
* Proven

---

# Injury Language Standards

Do not ignore injuries.

A bullpen is not just the active roster.

Consider:

* Active relievers
* Injured relievers
* Unavailable relievers
* Recently activated relievers
* Missing depth

Good:

"The remaining relievers are carrying a larger workload burden while multiple bullpen arms remain unavailable."

Bad:

"Nobody is down."

Bad:

"Everyone is available."

Those statements are often misleading.

---

# Story Selection Standards

The best BaseballOS stories involve change.

Prioritize:

* Emerging workload concentration
* Growing pressure
* Declining flexibility
* Recovering flexibility
* Unusual workload patterns
* Hidden bullpen strain
* Trust shifts
* Injury-driven workload changes
* Rotation-driven bullpen pressure

Avoid stories that simply restate current status.

---

# Team Page Writing Standard

Every team page should answer:

What is the current bullpen situation?

What created the situation?

What should users monitor next?

Structure:

Current State

Why It Happened

What To Watch

---

# Daily Story Standard

Every story should contain:

Observation

Explanation

Baseball Impact

Readers should finish with a clearer understanding of the bullpen than they had before reading.

---

# What BaseballOS Is Trying To Own

BaseballOS is not trying to own:

* Predictions
* Betting
* Power rankings
* Fantasy projections

BaseballOS is trying to own one question:

"How fresh or gassed is every bullpen right now, and why?"

Everything written on the platform should move users closer to answering that question.

---

# Final Test

Before publishing any piece of content, ask:

Can a baseball fan understand this without knowing anything about BaseballOS?

Does this explain a baseball reality instead of a metric?

Would a bullpen coach recognize this observation as meaningful?

Does the story explain why the observation matters?

If the answer to any question is no, rewrite the content.

This standard applies to all BaseballOS content.
