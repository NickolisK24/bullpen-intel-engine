BASEBALLOS  /  REWORKED CANONICAL DIRECTION

# 02 BaseballOS Bullpen Intelligence Standard

Baseball Domains · Derived Reads · Game Context · Product Contracts

VERSION 2.0  ·  PRODUCT-DEPTH EDITION

| Field | Value |
| --- | --- |
| Document | 02 BaseballOS Bullpen Intelligence Standard |
| Version | VERSION 2.0 |
| Status | PRODUCT-DEPTH EDITION |
| Owner | Nickolis Kacludis |
| Effective date | August 17, 2026 |
| Product | BaseballOS - MLB Bullpen Command Center |

| GOVERNING QUESTION | What does BaseballOS need to know in order to explain a bullpen more completely than any other public product? |
| --- | --- |

## Part I - Intelligence Model

### 1. Intelligence Definition

BaseballOS intelligence is the assembled current picture of a bullpen: who is active, who has worked, how much work they carried, how they are being deployed, how the group has performed, what the rotation has transferred to the bullpen, what changed, and how the current game context changes the importance of those facts.

### 2. Product Layers

| Layer | Purpose |
| --- | --- |
| Observed record | Games, appearances, pitches, outs, roster status, schedule, transactions, pitch tracking. |
| Derived bullpen facts | Rolling workload, rest patterns, role/deployment patterns, group performance, rotation transfer. |
| Current reads | Team State, arm read, workload class, role description, concentration, recovery, roster context. |
| Game context | What each bullpen brings into an upcoming game without forecasting the outcome. |
| Change and history | What changed since the prior trusted date and how the season timeline evolved. |

### 3. Public Team State

| State | Meaning |
| --- | --- |
| Fresh | Comparatively strong rested coverage and operating room across the active bullpen. |
| Stretched | Recent workload or coverage has meaningfully narrowed the bullpen's clean options. |
| Vulnerable | The active bullpen carries a materially constrained current operating picture with limited margin for additional work. |

Team State is a team-level summary, not perfection-versus-defect. It must reflect the shape of the active bullpen rather than “worst arm wins.” Calibration should consider counts, proportions, concentration, recency, and severity across the group.

### 4. Arm Read Vocabulary

| Read | Meaning |
| --- | --- |
| Clean Option | No major current workload restriction is visible in the governed record. |
| Watch Arm | Usable, but recent work deserves context. |
| Limited Rest | Recent work materially narrows the arm's clean-rest picture. |
| Unavailable | Public roster/status authority places the arm outside the current active set. |
| Limited Read | The platform does not have enough current information for a stronger read. |

## Part II - Required Intelligence Domains

### 5. Workload and Rest

Production-critical: Appearances, pitches, outs, batters faced, days rest, back-to-back, three straight, 3-in-4, 4-in-6, multi-inning work, pitch spikes, 3/5/7/14/30-day accumulation.

### 6. Deployment and Role

Core product: Entry inning, game state, saves/holds, high-leverage use, multi-inning frequency, inning distribution, role movement, recent deployment versus season baseline.

### 7. Active Bullpen Composition

Core product: Active bullpen membership, off-active arms, recent additions/removals, churn, handedness, role balance, usable group size.

### 8. Performance

Core supporting context: Active bullpen ERA, WHIP, K-BB%, HR rate, inherited runners, recent versus season windows, group definition and sample.

### 9. Rotation Load Transfer

Core product: Starter innings/pitches, short-start frequency, bullpen innings transferred, recent series burden, opener/bullpen-game context.

### 10. Schedule and Recovery

Core product: Off-days, consecutive games, doubleheaders, extra innings, travel/time-zone context where reliable, upcoming recovery runway.

### 11. Pitch Characteristics

Expansion domain: Velocity, pitch mix, movement, release, extension, within-outing and rolling change. Observed change only; never health inference.

### 12. Organizational Depth

Expansion domain: 40-man relief depth, options/recalls, rested eligible reinforcements, minor-league workload where public and governed.

### 13. Handedness and Matchup Structure

Expansion domain: Pitcher handedness, role coverage, observed platoon context with samples, posted-lineup structure when official.

## Part III - Derived Product Reads

| Read | User question | Primary inputs |
| --- | --- | --- |
| Team State | What is the bullpen's operating condition now? | Group workload, arm reads, active coverage, concentration, roster structure, recovery. |
| Clean Options | How many current active arms enter the read without major workload restriction? | Arm reads + active membership. |
| Workload Concentration | Is recent work spread across the pen or clustered? | Pitches/outs/appearances by arm over rolling windows. |
| Recovery Window | Has schedule/runway opened meaningful recovery? | Rest days, off-days, recent workload decay, upcoming schedule. |
| Rotation Transfer | How much burden has the rotation moved to the bullpen? | Starter innings and team bullpen innings. |
| Role Movement | Has a reliever's observed deployment meaningfully changed? | Entry inning, leverage, save/hold contexts, frequency, recency. |
| Bullpen Churn | How much has the active group changed? | Transactions, roster movement, additions/removals. |
| Active Bullpen Performance | How has the current active group performed? | Official lines for the current group and declared window. |

## Part IV - Dynamic Role Model

### 14. Role Is Observed Deployment, Not a Static Depth Chart

BaseballOS should continuously describe how each reliever has actually been used. A public role label may remain concise, but deeper role evidence should show inning distribution, high-leverage share, save/hold history, multi-inning frequency, and recent movement.

### 15. Role Movement

A role shift may be published when a reproducible recent window differs materially from a stable baseline. Example: a reliever handling five of the club's last seven highest-leverage pre-ninth situations. The statement describes completed deployment, not the next managerial decision.

## Part V - Game-Aware Intelligence

### 16. Matchup Read

For each upcoming game, BaseballOS assembles the two current bullpen pictures side by side: Team State, rested arms, recently used arms, back-to-back patterns, recent bullpen innings, top role arms, and rotation workload context. It describes the contrast without selecting a winner.

### 17. Starter Context

Probable starters are contextual only. Recent starter-length ranges may explain how much bullpen work the club has recently absorbed, but BaseballOS does not forecast tonight's starter length.

## Part VI - What Changed

### 18. Daily Delta Contract

- Team State movement.
- Arm read movement.
- Last appearance and new pitch/outs workload.
- Change in rested/clean-option counts.
- 7-day and 14-day workload movement.
- Rotation-transfer change.
- Roster additions/removals.
- Role/deployment movement when the evidence threshold is met.

What Changed should prioritize material differences rather than restating the entire team page.

## Part VII - Historical Memory

### 19. Team State Timeline

Store one reproducible daily team state plus the key observable events around state movement: games, extra innings, short starts, off-days, transactions, major arm workloads, and role shifts.

### 20. Pitcher Timeline

Preserve recent and historical role/read changes, workloads, appearances, and major pitch/performance trends so a user can understand how the current reliever picture developed.

## Part VIII - Reliability Boundary

### 21. Trust Stays Under the Hood

Source authority, freshness, suppression, method versions, corrections, and immutable history remain required. They should be exposed when they materially affect the baseball meaning or when the user deliberately inspects methodology. They are not the default headline of the product.

### 22. Unknowns

Missing data may reduce a claim or remove a dependent section. It is never converted to zero, guessed, or filled from an unrelated fallback. The user-facing wording should be concise and specific to the missing baseball context.

### 23. Intelligence Admission Test

1. Does the capability answer a real bullpen question?
2. Can the meaning be explained in ordinary baseball language?
3. Does it add information unavailable from the current product spine?
4. Can it be computed reproducibly from public data?
5. Can it be presented descriptively without becoming a prediction or private-intent claim?
6. Will it improve Tonight, Team Board, Pitcher, or historical understanding?
