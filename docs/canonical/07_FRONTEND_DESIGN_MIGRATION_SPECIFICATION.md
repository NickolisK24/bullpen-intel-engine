BASEBALLOS  /  REWORKED CANONICAL DIRECTION

# 07 BaseballOS Frontend Design & Migration Specification

Dark Product System · Responsive Density · Team Board · Tonight · Migration

VERSION 2.0  ·  PRODUCT-FIRST UX EDITION

| Field | Value |
| --- | --- |
| Document | 07 BaseballOS Frontend Design & Migration Specification |
| Version | VERSION 2.0 |
| Status | PRODUCT-FIRST UX EDITION |
| Owner | Nickolis Kacludis |
| Effective date | August 17, 2026 |
| Product | BaseballOS - MLB Bullpen Command Center |

| DESIGN INTENT | The interface should feel like serious baseball operations software made approachable for fans: calm, dark, dense when useful, highly legible, and almost completely free of decorative dashboard chrome. |
| --- | --- |

## Part I - Visual Direction

### 1. Character

- Deep charcoal/navy foundation.
- Off-white typography.
- Muted BaseballOS blue and restrained gold accents.
- Semantic state color used sparingly and always with text.
- Strong typography and spacing instead of card overload.
- Rows and tables for records; charts for trends; cards only for independent objects.
- No glassmorphism requirement, neon telemetry, fake team marks, cinematic baseball imagery, or sportsbook styling.

### 2. Layout Principle

Mobile prioritizes one-column clarity. Desktop adds density and parallel context. The desktop product should not be a stretched mobile screen, and mobile should not be a shrunken desktop dashboard.

### 3. Geometry

Use restrained radii or squared sections consistently; avoid every element becoming a rounded card. Section boundaries may rely on spacing, hairlines, tonal surface changes, and typography.

## Part II - Global Shell

| Element | Desktop | Mobile |
| --- | --- | --- |
| Navigation | Today, Dashboard, Bullpens, Stories/Search, Methodology/About as secondary. | Compact menu; Today, Team/search access remain primary. |
| Search | Persistent global search affordance. | Search icon/input quickly reachable. |
| Freshness | Compact date/currentness near claim-bearing page identity. | Same information, never a large trust banner. |
| Width | Dense but readable 1280-1440 shell. | ~390px primary target, no horizontal scrolling. |

## Part III - Team Board 2.0

### 4. Desktop Composition

Use a strong team header, then a compact summary band, followed by the active bullpen and recent usage. Deeper sections flow vertically with selective two-column pairings where comparison helps: workload + rest, roles + performance, rotation + roster. Recent Relief Work can use a full-width data table.

### 5. Mobile Composition

1. Team identity / state / concise summary.
2. Summary counts.
3. Active bullpen rows.
4. Recent usage.
5. Rest status.
6. Workload overview.
7. Roles & deployment.
8. Performance.
9. Rotation impact.
10. Roster/transactions.
11. What Changed.
12. Recent Relief Work.
13. History link/timeline.

### 6. Active Arm Row

Name is dominant. Role and current read are visually distinct but compact. Last used and recent workload appear as concise metadata. Expanded/detail interaction opens the Pitcher destination rather than turning each row into a giant accordion.

### 7. Graph Standard

- No gauge charts.
- No radial fatigue meters.
- Prefer line/bar/area trends with a clear text takeaway.
- Every chart has a meaningful window and direct values available.
- Avoid charting when a row or sentence communicates the fact faster.

## Part IV - Tonight

### 8. Desktop

Lead development and “What Changed” occupy the first viewport, with Tonight's games following in a compact slate. Important games may expand; ordinary games stay concise.

### 9. Mobile

Date, lead, and first relevant game cards appear immediately. Each matchup stacks the two bullpen states, key arms, and one compact contrast. No full league table above the slate.

## Part V - Dashboard

Desktop uses three state groups or a grouped board with every team visible once. Mobile uses vertical grouped sections. Team cards remain compact: identity, state, two signals, movement, open action.

## Part VI - Pitcher

The page opens with identity, current role/read, last use, and workload summary. Recent appearances are a high-priority record. Four primary charts maximum on the initial experience: workload, velocity/pitch trend, usage by inning/leverage, and role/deployment movement.

## Part VII - Matchup

Side-by-side on desktop, stacked on mobile. Align the same fields for both teams. The interface must not visually crown a winner through trophies, arrows, “advantage” colors, or default score comparison.

## Part VIII - System States

| State | Presentation |
| --- | --- |
| Loading | Stable skeleton preserving final hierarchy. |
| Quiet | Shorter page or “no material change”; no filler. |
| Stale | Compact represented date; preserve historical/current distinction. |
| Partial | Hide/mark only affected context; keep independent bullpen information. |
| Unavailable | State exactly what current baseball information is unavailable without turning the page into an incident report. |
| Error | Preserve already loaded independent content; retry only where useful. |

## Part IX - Semantic Ownership

- Team State backend-owned.
- Arm reads backend-owned.
- Role labels and role movement backend-owned/read-model owned.
- What Changed backend-derived from comparable snapshots.
- Frontend does not rewrite baseball meaning for layout.
- Frontend does not manually compose duplicated evidence text when the same fact is already communicated clearly.

## Part X - Migration Sequence

1. Visual foundation and shell tokens.
2. Team Board answer block and summary.
3. Active bullpen + recent usage.
4. Rest + workload.
5. Roles/deployment + performance.
6. Rotation + roster.
7. What Changed + relief ledger.
8. Team Board responsive/performance closeout.
9. Dashboard rebuild from the same team read model.
10. Tonight daily experience.
11. Pitcher redesign.
12. Matchup/search/history.
13. Retire duplicated legacy summaries/cards/styles only after replacement proof.

## Part XI - Acceptance

- A cold fan understands a Team Board in ten seconds.
- A returning fan sees what changed without rereading the page.
- A creator can find named arms and recent usage immediately.
- Desktop feels dense and professional, not card-heavy.
- Mobile feels native and fast, not compressed.
- No user-facing trust boilerplate competes with the bullpen answer.
- All deeper methodology/evidence remains reachable when deliberately requested.
