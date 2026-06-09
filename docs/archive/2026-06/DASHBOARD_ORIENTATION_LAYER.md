# Dashboard Orientation Layer

## Decision

Add a compact, always-visible **orientation layer** to the top of the dashboard
that states what BaseballOS is and what to do next.

## Reason

Real user feedback: a first-time visitor did not immediately understand what the
product does, why they were seeing a specific team, or how to navigate. Recent
work (Tonight's Bullpen Landscape, team drilldown, Today's Game Context) improved
the workflow; the missing piece was making the product's *purpose* obvious within
a few seconds of landing.

## Outcome

Directly under the hero, a single quiet strip now answers, at a glance:

- **What it is:** "Bullpen Availability & Workload Intelligence."
- **What it provides:** "BaseballOS helps you understand bullpen availability,
  workload, readiness, and constraints across Major League Baseball bullpens —
  transparently, with the data date and confidence always shown."
- **What to do next:** a short "Start by" list — explore Tonight's Bullpen
  Landscape (the section just below), select a team bullpen
  (`/bullpen?view=board`), or compare bullpen conditions
  (`/bullpen?view=compare`).

## Design notes

- **Lightweight, not a hero.** One bordered strip, one-line description, a short
  guidance list — it reads as "this is what this product does," never "Welcome to
  BaseballOS." No giant banner, no marketing paragraphs.
- **Always visible.** Rendered outside the data conditional so it orients
  first-time users even while the dashboard data loads.
- **Reuses existing patterns.** The guidance links reuse the existing
  `/bullpen?view=` deep links; no new routing or navigation system.
- **Mobile.** Stacks vertically, stays concise, adds minimal vertical space; the
  dashboard remains information-dense.

## Guardrail

The orientation layer explains the product only. It introduces **no**
recommendations, predictions, rankings, matchup advice, onboarding flows,
tutorials, or product tours, and **no** hype/marketing language (no
"revolutionary", "cutting edge", "AI-powered", "smartest", "best"). It reinforces
the trust-first identity — transparent, availability, workload, readiness,
constraints, context — and changes no analytics, trust, freshness, or governance
behavior.

## Tests

`frontend/tests/dashboardOrientation.test.mjs` — product description rendering,
next-step guidance rendering, deep-link reuse, always-visible (renders while the
dashboard is loading), a marketing/hype-language regression, a
recommendation/ranking/prediction regression, and a check that the trust-first
vocabulary is present. Existing dashboard tests remain green.
