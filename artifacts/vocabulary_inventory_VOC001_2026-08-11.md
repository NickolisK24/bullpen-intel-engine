# VOC-001 Public Vocabulary Inventory — 2026-08-11

Status: read-only audit artifact
Repository basis: `main` at `5e79c3caabda8fac1fb52112bb390765d8308e82`
Issue: #638

This artifact inventories the current public vocabulary architecture before implementation. It records present ownership, collisions, and proposed dispositions. It does not authorize or implement semantic/model changes.

## Executive finding

The core Team State contract is already clean and backend-owned. The main remaining drift is below Team State:

1. pitcher read labels are defined three different ways across the canonical Product Experience Standard, backend `pitcher_public_labels.py`, and frontend `pitcherLabels.js`;
2. the frontend still rewrites backend-authored pitcher labels, which is the exact ownership pattern #591 removed from the governed State → Why → Evidence path;
3. `Limited Read` currently belongs to both pitcher role and pitcher read families, so one literal label has two meanings;
4. `Trusted Arm` is a pitcher role, while `Trusted Arms` is separately defined as a team-level supporting concept meaning rested/unrestricted late-inning options — similar words, different semantics;
5. the legacy/team-shape public-label family (`TEAM_BULLPEN_PUBLIC_LABELS`) is a separate semantic layer from Team State and is still broad enough to look state-like;
6. freshness currently mixes `Data through`, `Updated`, `Last data update`, `Last checked`, `Healthy`, `Limited`, and `Not Current`, causing data-status language to reuse words from baseball-status families;
7. `bullpenConcepts.js` still contains a complete frontend-derived tier engine for Pressure / Recovery Window / Workload Concentration / Clean Options even though the derivation helpers appear to be unused by production callers and duplicate backend-owned team-shape concepts.

## Inventory and proposed disposition

| Current public term(s) | Family | Level | Current owner(s) | Collision / concern | Proposed disposition |
|---|---|---|---|---|---|
| Fresh / Stretched / Vulnerable | Team State | Team | backend `team_state_public_vocabulary.py`; canonical docs | Clean | PRESERVE exactly |
| Available / On Watch / Limited / Unavailable | Availability status | Pitcher | backend `public_bullpen_copy.py`; frontend fallback config | `Limited` is visually close to Limited Rest / Limited Read; frontend still carries fallback mapping | PRESERVE labels; backend remains sole semantic owner; frontend only style/fallback during migration |
| Clean Option / Watch Arm / Limited Rest / Unavailable / Limited Read | Pitcher read | Pitcher | canonical Product Experience Standard + frontend `pitcherLabels.js` | Backend currently emits Rested / Watch Arm / Rest-Restricted / Unavailable / Limited Read instead | ADOPT canonical doc set as backend output; remove frontend rewrite |
| Rested / Rest-Restricted | Pitcher read aliases | Pitcher | backend `pitcher_public_labels.py` and team-shape internals | Contradicts canonical doc set | RETIRE from reader-facing output; internal keys may stay |
| Trusted Arm / Setup Arm / Coverage Arm / Middle Relief Arm / Limited Read | Pitcher role | Pitcher | backend + frontend catalog + canonical Product Experience Standard | `Limited Read` duplicates pitcher-read meaning | PRESERVE first four; RENAME role-level `Limited Read` to a role-specific non-claim term (recommended: `Role Unclear`) |
| Trusted Arms | Supporting bullpen concept | Team | frontend `bullpenConcepts.js` | Sounds like plural of pitcher role but definition adds current rest/availability semantics | RENAME to `Late-Inning Options` (or another explicit team-level term) |
| Strong Read / Partial Read / Unclear Read / No Read / Unknown Read | Read-confidence display | Pitcher/meta | frontend `availabilityView.js` | Another “Read” family beside `Limited Read`; labels derived from internal confidence in browser | REFRAME as explicit `Read confidence` values; recommended values `High / Medium / Low / Unavailable` with the family name visible, or move public wording backend-side if claim-bearing |
| Strong/Stable/Thin/Limited Late-Inning Availability | Team-shape read | Team | backend `team_bullpen_shape.py` | `Limited` reappears at team concept level; may be mistaken for Team State or pitcher availability | PRESERVE concept only if surfaced as `Late-Inning Availability: <tier>`; avoid naked tier labels |
| Deep/Healthy/Thin/Very Thin Rested Bullpen | Team-shape read | Team | backend `team_bullpen_shape.py` | “Healthy” can imply health; “Thin” is generic state-like language | RENAME display family around explicit concept (`Rested Options`) and avoid `Healthy`; exact final tiers to be chosen in implementation review |
| High/Elevated/Manageable/Low Late-Inning Pressure | Team-shape read | Team | backend `team_bullpen_shape.py` | Mostly clear when full phrase shown | PRESERVE as concept-qualified labels; never surface naked `High/Elevated/...` |
| Heavily Concentrated / Concentrated / Some / No Workload Concentration | Team-shape read | Team | backend `team_bullpen_shape.py` | Clear when full phrase shown | PRESERVE concept-qualified labels |
| Strong/Stable/Thin/Limited Coverage Safety | Team-shape read | Team | backend `team_bullpen_shape.py` | State-like adjective family | PRESERVE only with concept name always attached; consider future simplification but not required for VOC-001 |
| Strong/Stable/Thin/Limited Depth Safety | Team-shape read | Team | backend `team_bullpen_shape.py` | State-like adjective family | PRESERVE only with concept name always attached; consider future simplification but not required for VOC-001 |
| Limited Read (team-shape fallback) | Read quality | Team concept | backend `team_bullpen_shape.py` | Same phrase also used for pitcher role/read today | PRESERVE as the ONE generic insufficient-evidence label after role collision is removed |
| Available / On Watch / Limited / Unavailable / Unavailable Pitchers | Board group headers | Group | backend `bullpen_board.py` | Group headers reuse status labels; Avoid and Unavailable collapse into two similarly named groups | CHANGE to explicit noun phrases (e.g. `Available Arms`, `On-Watch Arms`, `Limited Arms`, `Unavailable — Workload`, `Unavailable — Roster`) while preserving underlying engine groups |
| Data through | Freshness | Meta | frontend concept glossary; static preview metadata | Clear | PRESERVE |
| Updated | Freshness | Meta | frontend glossary | Ambiguous vs generated/published/checked | RETIRE as standalone glossary term; use specific timestamp labels |
| Last data update | Freshness | Meta | `syncStatusView.js` | Clear but distinct from represented date | PRESERVE |
| Last checked | Freshness | Meta | `syncStatusView.js` | Clear operational timestamp | PRESERVE where useful, secondary to data-through |
| Healthy / Limited / Not Current | Data-health badge | Meta | `syncStatusView.js` | `Limited` collides with pitcher availability; `Healthy` reads like baseball/health state | RENAME family to explicit data status labels: recommended `Current`, `Partial Data`, `Stale`, `Data Unavailable` |
| Recovery Window / Limited Recovery Window | Legacy frontend concept | Team | `bullpenConcepts.js` | Frontend derives tiers independently; duplicates backend rested/clean concepts | RETIRE frontend derivation path unless a confirmed production consumer requires it; keep glossary only after mapping to backend concept authority |
| Deep/Enough/Thin/Very Thin Clean Options | Legacy frontend concept | Team | `bullpenConcepts.js` | Duplicates backend clean-options read with different tier names | RETIRE frontend-derived tier vocabulary |
| High/Elevated/Manageable/Low Bullpen Pressure | Legacy frontend concept | Team | `bullpenConcepts.js` | Duplicates backend pressure read with similar but not identical labels | RETIRE frontend-derived tier vocabulary; glossary concept may remain |
| Concentrated / Some Concentration / Spread-Out Workload | Legacy frontend concept | Team | `bullpenConcepts.js` | Duplicates backend workload concentration labels | RETIRE frontend-derived tier vocabulary; glossary concept may remain |

## Canonical ownership model recommended for implementation

### 1. Team State
Owner: backend `team_state_public_vocabulary.py`.
Public catalogue: Fresh / Stretched / Vulnerable.
No frontend derivation or synonym mapping.

### 2. Availability status
Owner: backend `public_bullpen_copy.py`.
Public catalogue: Available / On Watch / Limited / Unavailable.
Frontend may key style by engine status but must render supplied public label when present.

### 3. Pitcher role
Owner: backend `pitcher_public_labels.py`.
Recommended catalogue: Trusted Arm / Setup Arm / Coverage Arm / Middle Relief Arm / Role Unclear.
Frontend catalog becomes styling/definition metadata keyed by backend key, not a wording translator.

### 4. Pitcher current read
Owner: backend `pitcher_public_labels.py`.
Canonical catalogue from Product Experience Standard: Clean Option / Watch Arm / Limited Rest / Unavailable / Limited Read.
Retire reader-facing Rested / Rest-Restricted aliases.

### 5. Read confidence
Owner: one declared producer. Prefer backend if published as a meaning-bearing label; otherwise frontend may format a raw confidence field only if the family is explicitly `Read confidence` and wording is not presented as a baseball conclusion.
Recommended display: Read confidence: High / Medium / Low / Unavailable.

### 6. Team-shape supporting reads
Owner: backend `team_bullpen_shape.py`.
These are supporting dimensions, not Team State. Surfaces must always show the concept name with the tier and must not style/position them as a second team-state system.
`TEAM_BULLPEN_PUBLIC_LABELS` remains a supporting-read catalogue only.

### 7. Freshness / publication status
Owner: canonical temporal fields plus one presentation vocabulary.
Recommended visible labels:
- Data through — represented baseball date.
- Last data update — last successful baseball-data write.
- Last checked — last attempted/observed refresh, secondary.
- Data status — Current / Partial Data / Stale / Data Unavailable.
Do not replace generated-at or published-at on historical/distribution artifacts where those timestamps are required receipts.

## Immediate implementation sequence recommended

1. Make backend pitcher read labels match the canonical Product Experience Standard (`Clean Option`, `Limited Rest`) and rename role-level `Limited Read` to `Role Unclear`.
2. Delete semantic rewriting from frontend `pitcherLabels.js`; render backend labels verbatim and keep only keyed style/definitions.
3. Reconcile board group headers into explicit noun phrases while preserving engine statuses and grouping behavior.
4. Reframe confidence labels as an explicit confidence family rather than another arm-read family.
5. Standardize sync/freshness badge wording and update How to Read definitions.
6. Remove unused frontend-derived tier functions/vocabulary from `bullpenConcepts.js` after proving no production consumer; retain only canonical glossary concepts backed by backend authorities.
7. Keep backend team-shape reads as supporting reads, but pin tests so they cannot be surfaced as Team State or naked state-like adjectives.
8. Update canonical Product Experience and Bullpen Intelligence docs to the final owner map and one-line definitions.
9. Add cross-repository contract tests for banned retired aliases and frontend translation functions.
10. Production smoke Team Board, Compare, Dashboard, one limited-data arm, and freshness/data-status display.

## Non-findings / do not change

- Team State is not the problem; it is already correctly centralized.
- Availability thresholds/classification are not part of this work.
- Team-shape thresholds are not being retuned.
- No fatigue/scoring, roster, sync, publication, or recommendation authority change is implied.
- Static `/team/{ABBR}` metadata is already using canonical Team State and should not be moved back to team-shape labels.
