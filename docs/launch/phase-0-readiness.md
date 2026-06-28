# Phase 0 Launch Readiness

## Analytics

- Vercel Analytics is installed and mounted in the frontend app.
- No additional analytics provider or secret-bearing config was added in Phase 0.
- Search Console ownership, sitemap submission, and any GA4 or PostHog decision should be handled as deployment/account work outside this branch.

## Weekly Notes Interest

- The homepage uses a mailto-based interest CTA for weekly bullpen notes.
- The CTA asks interested users to include a favorite team, but it does not claim that a full newsletter system exists.
- A future provider integration should define consent copy, unsubscribe behavior, storage ownership, and team preference fields before replacing the placeholder.

## Public Boundaries

- BaseballOS is positioned as descriptive MLB bullpen intelligence from public data.
- Public copy should not claim manager intent, private medical availability, final game-day decisions, betting advice, or future outcomes.
- Injury and injured-list context should be described only as public roster/injury signals unless the page shows a more specific modeled source.
