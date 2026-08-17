BASEBALLOS  /  REWORKED CANONICAL DIRECTION

# 03 BaseballOS Product Experience Standard

Daily Habit · Team Board · Game Context · Pitcher Depth · Navigation

VERSION 2.0  ·  MARKET-LEADERSHIP EDITION

| Field | Value |
| --- | --- |
| Document | 03 BaseballOS Product Experience Standard |
| Version | VERSION 2.0 |
| Status | MARKET-LEADERSHIP EDITION |
| Owner | Nickolis Kacludis |
| Effective date | August 17, 2026 |
| Product | BaseballOS - MLB Bullpen Command Center |

| EXPERIENCE PROMISE | A user should be able to open BaseballOS, understand the bullpen situation in seconds, and go as deep as they want without leaving the product. |
| --- | --- |

## Part I - Global Experience

### 1. Product Hierarchy

| Layer | Primary question |
| --- | --- |
| Tonight | What do I need to know about MLB bullpens before tonight's games? |
| League | Which bullpens deserve a closer look right now? |
| Team | What is happening inside this bullpen? |
| Pitcher | What has this reliever carried, how is he being used, and what has changed? |
| History | How did this bullpen or reliever get here? |
| Methodology | How is a specific read defined when I want to inspect it? |

### 2. Answer Before Interface

Every major surface should communicate the baseball point before presenting controls, tables, methodology, or product explanation.

### 3. Mobile First, Desktop Dense

Mobile should preserve the answer, names, current workload, and key deltas without horizontal scrolling. Desktop should use the additional width for density and simultaneous context, not decorative empty space.

### 4. Trust Presentation

Freshness belongs near current claims. Full evidence/provenance panels, confidence language, and disclaimers should not repeat on every card. A user who wants to inspect the record can drill down; ordinary use should remain baseball-first.

## Part II - Tonight: Daily Flagship

### 5. Mission

Tonight is the default homepage and the daily habit loop. It is a 60- to 90-second pregame bullpen briefing across MLB.

### 6. Above the Fold

1. Date and game-status context.
2. One lead bullpen development when genuinely meaningful.
3. Tonight's most relevant matchups or team notes.
4. What Changed since the prior trusted date.
5. Direct handoffs into the team pages carrying the story.

### 7. Game Cards

- Matchup and local first-pitch time/status.
- Team State for both clubs.
- Rested/clean-option count.
- Recently used or back-to-back arms.
- Top late-inning role arms and their current rest.
- Recent bullpen innings or rotation-transfer context when meaningful.
- One concise baseball sentence per matchup.
- Tap through to a matchup comparison or either Team Board.

### 8. Quiet Day

If little changed, Tonight gets shorter. It does not manufacture a headline.

## Part III - Dashboard: League Orientation

### 9. Mission

Show all 30 teams once, grouped by Fresh, Stretched, or Vulnerable, with just enough context to choose where to look closer.

### 10. Team Row

A team row should contain full/clear team identity, Team State, two or three compact signals such as clean options, back-to-back count, or movement, and the Team Board link. It is not a mini Team Board.

## Part IV - Team Board: Product Center of Gravity

### 11. Mission

Be the definitive public page for one MLB bullpen. A user should not need a second bullpen site after opening it.

### 12. Team Board Information Architecture

| Order | Section | Purpose |
| --- | --- | --- |
| 1 | Team Header | Team identity, current Team State, one concise summary, date/update context. |
| 2 | Bullpen Summary | Active arms, clean/rested options, recently used arms, off-active count, 7-day bullpen workload. |
| 3 | Active Bullpen | Every active reliever with current read, role, last used, recent workload, and quick open. |
| 4 | Recent Usage | Yesterday / last 3 days / last 7 days by named arm. |
| 5 | Rest Status | Days rest, back-to-back, 3-in-4, 4-in-6, multi-inning and pitch-spike context. |
| 6 | Workload Overview | Team 3/7/14/30-day pitches, outs, appearances, concentration, trend. |
| 7 | Roles & Deployment | Closer/setup/high-leverage/coverage usage plus observed role movement. |
| 8 | Performance | Active bullpen ERA, WHIP, K-BB%, HR, inherited-runner context with window/sample. |
| 9 | Rotation Impact | Starter innings, short starts, bullpen innings transferred, recent series burden. |
| 10 | Recent Transactions | Adds, removals, recalls, options, IL/public roster changes affecting the active group. |
| 11 | What Changed | Material changes since the previous trusted team state. |
| 12 | Recent Relief Work | Game-by-game appearance ledger and source-level detail. |
| 13 | History | State timeline and major workload/roster/deployment events. |

### 13. Active Bullpen Row

Each arm row shows: name; current public role; current read; days since last appearance; last-game pitches; appearances/pitches over 7 days; key multi-day pattern; and a direct Pitcher page open.

### 14. Visual Hierarchy

State and names dominate. Tables and rows are preferred for records. Cards are reserved for genuinely independent objects. Graphs are used only for trends that are easier to understand visually than textually.

## Part V - Pitcher

### 15. Mission

Give one reliever a complete current workload and deployment record without becoming a generic player-stat profile.

### 16. Pitcher Page

- Identity, team, active roster status.
- Current role and role movement.
- Current arm read.
- Last appearance.
- 3/7/14/30-day workload.
- Rest and consecutive-day patterns.
- Recent appearance ledger.
- Usage by inning and leverage.
- Multi-inning frequency.
- Recent performance.
- Velocity and pitch mix trends when governed.
- Published observations and historical role/read changes.

### 17. Core Charts

- 30-day workload trend.
- Season velocity/pitch-characteristic trend.
- Usage by inning / leverage distribution.
- Role or deployment movement over time.

## Part VI - Matchup / Compare

### 18. Mission

Show how two bullpens differ now, usually in the context of an upcoming game.

### 19. Comparison Set

- Team State.
- Clean/rested arms.
- Worked-yesterday/back-to-back counts.
- 7-day bullpen innings and pitches.
- Closer/setup rest.
- Rotation-transfer burden.
- Recent active-pen performance.
- Named arms driving the difference.

## Part VII - What Changed and History

### 20. What Changed

This is a first-class retention surface, not a footer. It should summarize only material state/read/workload/roster/rotation/deployment changes since the previous comparable date.

### 21. Team Timeline

A season timeline shows daily Team State plus major observable events. Users should be able to identify when the bullpen changed and inspect the games or roster events around that change.

## Part VIII - Search and Personalization

### 22. Global Search

One search box should find teams, relievers, and games. Results are fast, current, and direct to the canonical destination.

### 23. Follow My Team

After the core daily product is strong, users may follow teams and receive a personalized Tonight view and optional notifications for material bullpen changes. Personalization must amplify a great product, not compensate for a weak one.

## Part IX - Supporting Surfaces

| Surface | Role |
| --- | --- |
| Stories | Finite feed of the strongest current bullpen observations beyond Tonight. |
| Methodology | Reference definitions and calculation detail on demand. |
| Data & System Status | Compact currentness/source-health page for inspection; not a primary navigation destination unless useful. |
| Share Artifact | Permanent historical citation for a specific published observation. |
| Start Here / About | Short orientation for first-time visitors; baseball value before project biography. |

## Part X - Experience Acceptance

1. Ten-second test: a new user can state the bullpen situation quickly.
2. Bookmark test: a team fan has a reason to return to the Team Board tomorrow.
3. Pregame test: Tonight is genuinely useful 60-90 minutes before first pitch.
4. Depth test: a creator or analyst can inspect names, appearances, usage, and context without leaving BaseballOS.
5. Change test: returning users can see what is different rather than rereading yesterday.
6. Mobile test: all Tier 1 use works naturally around 390px.
7. Desktop test: density increases without turning into a wall of cards.
8. Trust test: the product is current and checkable without sounding defensive.
