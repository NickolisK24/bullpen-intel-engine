BASEBALLOS / ACTIVE SUBSYSTEM SPECIFICATION

# 07 BaseballOS Frontend Design & Migration Specification

Dark Product System · Responsive Density · Team Board · Tonight · Migration

VERSION 2.1 · AUTHORITY-BOUND UX EDITION

| Field | Value |
| --- | --- |
| Document | 07 BaseballOS Frontend Design & Migration Specification |
| Version | 2.1 |
| Status | Active subsystem specification — subordinate authority |
| Owner | Nickolis Kacludis |
| Effective date | August 17, 2026 |
| Product | BaseballOS - Public MLB Bullpen Intelligence |
| Authority | Constitution Section 15 level 7; subordinate to all six canonical documents |
| Sequence owner | Product Roadmap & Decision Ledger |
| Semantic owners | Bullpen Intelligence Standard and Product Experience Standard |

| DESIGN INTENT | The interface should feel like serious baseball operations software made approachable for fans: calm, dark, dense when useful, highly legible, and almost completely free of decorative dashboard chrome. |
| --- | --- |

## 1. Authority Boundary

This specification is not a seventh canonical product authority. It is an active subsystem specification under the authority order established by the BaseballOS Constitution.

It may define frontend composition, responsive behavior, visual tokens, component migration order, and replacement acceptance. It may not redefine product identity, public vocabulary, Team State, arm availability, pitcher reads, evidence requirements, source authority, publication authority, operational modes, editorial rules, or roadmap sequence.

The Product Roadmap & Decision Ledger remains the execution authority. Nothing in this specification changes the current active objective, the current Next Approved Work order, D-051 through D-055, the legacy production writer, game-driven shadow posture, or any publication gate. The migration sequence below becomes executable only when the Roadmap advances work into the corresponding frontend package.

When this document and a higher authority disagree, the higher authority wins and this document must be corrected.

## 2. Protected Existing Contracts

The migration must preserve the existing governed product contracts while changing presentation:

- Team State remains exactly Fresh / Stretched / Vulnerable and stays backend-owned.
- Arm Availability, Pitcher Role, Pitcher Current Read, Read Confidence, Data Status, Workload Data, and named bullpen reads retain their canonical owners and meanings.
- Supporting reads never constitute or imply Team State.
- The frontend renders backend-governed semantic labels verbatim and does not invent fallback meaning.
- Unknown values remain unknown; no unknown-as-zero fallback is introduced.
- Current and historical meaning remain separate.
- Evidence, freshness, limitations, and exact destinations remain reachable when required by the owning standard.
- No betting, fantasy, prediction, private-health inference, manager-intent claim, quality ranking, or unexplained public score is introduced.
- No migration step grants write authority, publication authority, or acquisition authority.

## Part I - Visual Direction

### 3. Character

- Deep charcoal/navy foundation.
- Off-white typography.
- Muted BaseballOS blue and restrained gold accents.
- Semantic state color used sparingly and always with text.
- Strong typography and spacing instead of card overload.
- Rows and tables for records; charts for trends; cards only for independent objects.
- No glassmorphism requirement, neon telemetry, fake team marks, cinematic baseball imagery, or sportsbook styling.

### 4. Layout Principle

Mobile prioritizes one-column clarity. Desktop adds density and parallel context. The desktop product should not be a stretched mobile screen, and mobile should not be a shrunken desktop dashboard.

### 5. Geometry

Use restrained radii or squared sections consistently; avoid every element becoming a rounded card. Section boundaries may rely on spacing, hairlines, tonal surface changes, and typography.

## Part II - Global Shell

| Element | Desktop | Mobile |
| --- | --- | --- |
| Navigation | Preserve the canonical navigation model; improve density and hierarchy without creating a new product lane. | Compact menu with canonical destinations quickly reachable. |
| Search | Persistent global search affordance when the Roadmap activates routed search work. | Search affordance quickly reachable when activated. |
| Freshness | Compact date/currentness near claim-bearing page identity. | Same information, never a large trust banner. |
| Width | Dense but readable 1280-1440 shell. | ~390px primary target, no horizontal scrolling. |

Shell work must not silently activate routes, search capability, personalization, or page missions that the Roadmap has not approved.

## Part III - Team Board Target Composition

### 6. Desktop Composition

Use a strong team header, then a compact summary band, followed by the active bullpen and recent usage. Deeper sections flow vertically with selective two-column pairings where comparison helps: workload + rest, roles + performance, rotation + roster. Recent Relief Work can use a full-width data table.

The existing Team Board evidence chain remains authoritative. Layout may compress repeated presentation, but it may not remove meaning-bearing evidence, freshness, or limitations required by the Product Experience Standard.

### 7. Mobile Composition

When each capability is authorized and available, the target order is:

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

A section whose backend/read-model capability is not yet approved or trustworthy does not receive a frontend-derived substitute.

### 8. Active Arm Row

Name is dominant. Role and current read are visually distinct but compact. Last used and recent workload appear as concise metadata. Expanded/detail interaction should hand off to the governed arm destination rather than turning every row into a giant accordion.

### 9. Graph Standard

- No gauge charts.
- No radial fatigue meters.
- Prefer line/bar/area trends with a clear text takeaway.
- Every chart has a meaningful window and direct values available.
- Avoid charting when a row or sentence communicates the fact faster.
- A chart never creates a new classification, score, or public semantic family.

## Part IV - Tonight Target

### 10. Desktop

When Daily Habit / Today work is activated by the Roadmap, lead development and What Changed may occupy the first viewport, with the day’s games following in a compact slate. Important games may expand; ordinary games stay concise.

### 11. Mobile

Date, lead, and first relevant game cards should appear immediately. Each matchup may stack the two governed bullpen pictures, key arms, and one compact descriptive contrast. No matchup presentation selects a winner or declares an edge.

This section does not rename the canonical Today surface or independently authorize a new Tonight route. Route and page-mission changes remain owned by the Product Experience Standard and Roadmap.

## Part V - Dashboard Target

Desktop uses the existing canonical Team State groups with every eligible team represented according to the Product Experience Standard. Mobile uses vertical grouped sections. Team objects remain compact: identity, backend-authored state, a small number of governed signals, movement when available, and the team destination.

The Dashboard is not a mini Team Board and does not derive Team State from counts or supporting reads.

## Part VI - Pitcher Target

When Pitcher work is activated, the page should open with identity, current governed role/read, last use, and workload summary. Recent appearances remain a high-priority record. Initial chart count should stay bounded; workload, pitch-characteristic trend, usage distribution, and role/deployment movement are candidates only when their source and semantic contracts are approved.

## Part VII - Compare / Matchup Target

Side-by-side on desktop, stacked on mobile. Align the same governed fields for both teams. The interface must not visually crown a winner through trophies, arrows, advantage colors, score-style comparison, or other predictive framing.

## Part VIII - System States

| State | Presentation |
| --- | --- |
| Loading | Stable skeleton preserving final hierarchy. |
| Quiet | Shorter page or no-material-change treatment; no filler. |
| Stale | Compact represented date; preserve historical/current distinction. |
| Partial | Hide/mark only affected context; keep independent valid bullpen information. |
| Unavailable | State exactly what current baseball information is unavailable without turning the page into an incident report. |
| Error | Preserve already loaded independent content; retry only where useful. |
| Integrity failure | Preserve the higher-standard fail-closed rule; do not render meaning-bearing content as merely warned. |

## Part IX - Semantic Ownership

- Team State is backend-owned.
- Arm availability and public arm reads keep their canonical owners.
- Role labels are backend-owned; future role movement requires its own approved reproducible contract before presentation.
- What Changed must be backend-derived from comparable governed snapshots before the frontend presents it as semantic truth.
- Frontend does not rewrite baseball meaning for layout.
- Frontend does not manually compose duplicated semantic evidence when a canonical backend structure already exists.
- Presentation changes may alter density, hierarchy, typography, color, interaction, and component composition; they may not alter what a governed field means.

## Part X - Migration Sequence Within an Authorized Frontend Package

Once the Roadmap activates the relevant frontend initiative, implementation should proceed in this internal order:

1. Visual foundation and shell tokens.
2. Team Board answer block and summary.
3. Active bullpen + recent usage.
4. Rest + workload.
5. Roles/deployment + performance.
6. Rotation + roster.
7. What Changed + relief ledger.
8. Team Board responsive/performance closeout.
9. Dashboard rebuild from the same governed team read models.
10. Daily/Today experience work when separately authorized.
11. Pitcher redesign when separately authorized.
12. Compare/search/history when separately authorized.
13. Retire duplicated legacy summaries/cards/styles only after replacement proof.

This is a dependency order inside authorized work, not a replacement for the canonical Next Approved Work table.

## Part XI - Acceptance

- A cold fan can understand the main Team Board answer quickly.
- A returning fan can identify material change without rereading the full page once What Changed is governed and available.
- A creator can find named arms and recent usage immediately.
- Desktop feels dense and professional rather than card-heavy.
- Mobile feels native and fast rather than compressed.
- Public trust language supports the baseball answer instead of overwhelming it, while required evidence and limitations remain available.
- No canonical semantic family is redefined or derived in presentation.
- No existing authority, publication gate, source boundary, or historical contract is weakened by migration.

## Revision History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 2.0 | August 17, 2026 | Nickolis Kacludis | Established the product-first visual target and responsive Team Board migration concept. |
| 2.1 | August 17, 2026 | Nickolis Kacludis | Reclassified the document as a Constitution level-7 active subsystem specification, bound every target to the six canonical authorities and current Roadmap sequence, preserved existing semantic and operational contracts, and clarified that its migration order applies only inside work already activated by the canonical Roadmap. |