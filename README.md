# BaseballOS

Trust-first bullpen availability and workload intelligence.

## What BaseballOS Is

BaseballOS is a full-stack bullpen availability and workload intelligence
platform. It ingests MLB Stats API data, computes transparent fatigue,
roster-adjusted availability, and freshness signals, and presents descriptive
bullpen intelligence with visible trust, roster, explanation, and governance
metadata.

BaseballOS is explainable and trust-first. It is not a betting product, a
black-box prediction system, a pitcher ranking surface, or an automated
recommendation engine. It does not tell the user who to use, rank pitchers,
predict outcomes, or hide source freshness. The user remains the decision
maker.

**Stack:** React + TailwindCSS, Flask + Python, PostgreSQL, MLB Stats API.

## Current Platform Status

Status words below describe **implementation and governance maturity**, not a
claim that every surface is live on real-time data. The "Data" column states
what each surface actually runs on today. Rollout/certification labels are
governance milestones recorded by the project's own ledger, not third-party
audits.

| Surface | Governance status | Data today |
| --- | --- | --- |
| V1 Fatigue + Availability Engine | Implemented, tested | Live MLB game-log data (via sync) |
| Bullpen Board roster-aware availability | Implemented, tested | MLB roster authority plus live workload data |
| Player Detail final availability | Implemented, tested | Same roster-adjusted final availability semantics as Bullpen Board |
| Pitcher Search V1 | Implemented, tested | Database-backed pitcher discovery from stored BaseballOS records |
| V2 Recommendation Engine | Implemented, tested | Live workload data; presents **governed context/evidence only — it does not rank, select, or name a pitcher** |
| V3 Team Operations Readiness | Controlled rollout approved | Live workload data |
| V4 Explanation Platform | Production rollout approved | Derived from live availability/readiness payloads |
| V5 Bullpen Intelligence Surface | Governance-certified foundation | **Deterministic sample state — not yet wired to live MLB data** |

Legend: *Implemented* = code exists and is exercised by tests; *Tested* = covered
by the automated suites; *Controlled/Production rollout approved* = governance
milestone in the certification ledger; *Sample state* = the surface currently
returns fixed deterministic data, pending separately-authorized live runtime
integration.

Detailed certification, rollout, and historical phase state is maintained in
[docs/README.md](docs/README.md),
[docs/current/PROJECT_STATE_2026_06.md](docs/current/PROJECT_STATE_2026_06.md),
[docs/governance/CERTIFICATION_LEDGER.md](docs/governance/CERTIFICATION_LEDGER.md),
and
[docs/archive/2026-06/V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVAL.md](docs/archive/2026-06/V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVAL.md).

## Core Capabilities

- Deterministic fatigue scoring from pitch-count load, rest days, appearance
  frequency, and innings load.
- Availability Engine V1 statuses: `Available`, `Monitor`, `Limited`, `Avoid`,
  and `Unavailable`.
- Roster-status authority from MLB Stats API roster endpoints, normalized into
  BaseballOS labels such as `Active MLB`, `IL-15`, `IL-60`, `Minors`,
  `40-Man Only`, `Optioned`, `DFA`, `Non-Roster`, and `Roster Unknown`.
- Team-assignment authority from MLB team rosters plus player current-team and
  status fallback, with stale ownership cleared fail-closed when a pitcher has
  no resolved organization.
- Bullpen Board default view for active bullpen-relevant arms. Clear starters
  are excluded from default bullpen planning, and unavailable pitchers are
  separated from bullpen arms with roster reasons.
- Final availability is roster-status-adjusted. Workload signal remains visible
  separately, and Player Detail uses the same final availability semantics as
  Bullpen Board cards.
- Pitcher Search V1 for team-agnostic pitcher discovery by name, backed by
  stored BaseballOS pitcher records, current team assignment, roster status,
  and final availability. It does not introduce rankings, recommendations, or
  predictions.
- Explainable availability output with confidence, data state, reasons,
  limitations, and deterministic inputs.
- Dashboard trust strip for platform status, sync freshness, baseball
  data-through date, and refresh coverage.
- Recommendation Engine V1 candidate-level evaluation with visible refusal,
  confidence, freshness, limitations, and governance metadata.
- Recommendation Engine V2 governed bullpen-state intelligence with team-level
  context, fail-closed behavior, trust metadata, freshness metadata, and
  refusal metadata. It surfaces context and evidence only; it does not rank,
  select, or name a pitcher to use.
- Team Operations Readiness as a team-level surface for workload pressure,
  constraints, availability distribution, coverage visibility, and operational
  context.
- V4 explanation surfaces for certified Availability and Team Operations
  Readiness APIs, using compact progressive disclosure and fail-closed display.
- V5 read-only observation API and frontend Bullpen Intelligence panel for
  governed descriptive observations from deterministic supplied state.
- Protected operational endpoints for sync and recalculation.
- Scheduled sync support through GitHub Actions.

## Current Trust State

- Roster authority is active from MLB Stats API roster endpoints.
- Team assignment authority is active before roster-status sync.
- Stale team ownership correction is active and clears no-organization or
  unresolved ownership fail-closed.
- Unavailable-pitcher separation is active on Bullpen Board.
- Player Detail and Bullpen Board use the same roster-adjusted final
  availability semantics.
- Transaction-event lineage is not yet persisted; reality can move between
  syncs; role inference remains usage-based where explicit bullpen-role
  authority is unavailable.

## Sync Responsibilities

The current production sync path is:

```text
team assignment sync
-> roster status sync
-> game log and workload sync
-> fatigue and availability calculation
-> trust and freshness reporting
```

Team assignment resolves current ownership first so stale team rows do not
survive into team-scoped boards. Roster status then determines active MLB,
injured list, minors, optioned, DFA, non-roster, 40-man-only, or unknown state.
Game-log sync and fatigue calculation supply the workload signal. Availability
surfaces combine roster status and workload signal into final availability.

## Known Limitations

- Transaction feed lineage is not yet persisted, so BaseballOS records current
  status and ownership rather than a claim/release/status-change history.
- Real-world roster changes can occur between syncs before BaseballOS refreshes.
- Bullpen eligibility still uses role and usage evidence where explicit bullpen
  role authority is unavailable.
- Starters are intentionally excluded from default bullpen planning, but future
  transparency counters should separate active MLB pitchers, bullpen arms, and
  excluded starters more explicitly.

## Next Priorities

- Mobile review.
- Active MLB pitchers versus bullpen arms transparency.
- Competitive positioning versus Rotowire.
- Optional transaction lineage/history later.

## Governance Boundaries

Certified recommendation, readiness, and explanation surfaces preserve:

```text
ranking_applied === false
selection_made === false
```

Certified V4 explanation surfaces additionally preserve:

```text
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

BaseballOS does not authorize:

- no ranking
- no selection
- no prediction
- no best/preferred arm behavior
- no pitcher advice
- no matchup advice
- no automated decision-making
- hidden priority ordering
- pitcher recommendation beyond certified candidate-level V1 evaluation
- injury prediction, save prediction, or performance prediction

Detailed governance, certification, rollout, and monitoring evidence is in
[docs/README.md](docs/README.md) and
[docs/governance/CERTIFICATION_LEDGER.md](docs/governance/CERTIFICATION_LEDGER.md).

## Architecture Overview

| Layer | Technology / location |
| --- | --- |
| Frontend | React + Vite + TailwindCSS |
| Backend | Flask + Python |
| Database | PostgreSQL |
| Data source | MLB Stats API |
| Hosted frontend | Vercel static build |
| Hosted backend | Render Flask service |
| Scheduled sync | GitHub Actions calling protected backend endpoint |

Daily sync is driven externally by `.github/workflows/baseballos-sync.yml`.
Health checks do not perform sync. Protected write endpoints require the
configured admin token in production.

BaseballOS is an independent project and is not affiliated with or endorsed by
MLB.

## Quick Start

Backend:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python seed.py
python app.py
```

Frontend, in a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend dev server proxies API calls to the backend during local
development. See [docs/current/SETUP.md](docs/current/SETUP.md) for full local
and hosted setup details.

## Environment Variables

Backend:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string; required in production |
| `FLASK_APP` | Flask CLI entry point, usually `app.py` |
| `APP_ENV` | Runtime environment; use `production` for hosted production |
| `SECRET_KEY` | Flask secret key; must be non-default in production |
| `MLB_API_BASE` | Optional MLB Stats API base URL override |
| `AUTO_SYNC` | Enables local in-process scheduler when set to true-like value |
| `ADMIN_API_TOKEN` | Gates protected operational endpoints |

Frontend:

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Backend origin when hosted separately |
| `VITE_ADMIN_API_TOKEN` | Optional operator token; avoid public production bundles when possible |

GitHub Actions scheduled sync:

| Secret | Purpose |
| --- | --- |
| `BASEBALLOS_SYNC_URL` | Protected backend sync endpoint URL |
| `BASEBALLOS_ADMIN_API_TOKEN` | Token matching backend `ADMIN_API_TOKEN` |

## Testing

Backend:

```powershell
.\backend\venv\Scripts\python.exe -m pytest backend\tests
```

Frontend:

```powershell
cd frontend
npm test
```

Frontend production build:

```powershell
cd frontend
npm run build
```

No frontend or backend tests are required for README-only documentation edits
unless implementation files change.

## Documentation Entry Points

See [docs/README.md](docs/README.md) for the full documentation map. Primary
entry points:

- [Documentation Index](docs/README.md) - folder guide and authoritative docs.
- [Project State](docs/current/PROJECT_STATE_2026_06.md) - canonical June 2026
  state record.
- [Setup Guide](docs/current/SETUP.md) - local setup, deployment, environment
  variables, and scheduled sync.
- [Roadmap](docs/current/ROADMAP.md) - current direction and historical roadmap
  context.
- [Certification Ledger](docs/governance/CERTIFICATION_LEDGER.md) -
  certification, production, rollout, and governance state by surface.
- [Operational Reviews](docs/governance/OPERATIONAL_REVIEWS.md) - deployment
  review, remediation, verification, and rollout evidence summaries.

Detailed per-version phase records (Recommendation Engine V1/V2, V2.5 lifecycle
hardening, V3 Team Operations readiness, V4 evidence/explanation, and the V5
Bullpen Intelligence Surface, including the
[V5 Phase 12 full production rollout approval](docs/archive/2026-06/V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVAL.md))
are retained under [docs/archive/2026-06/](docs/archive/2026-06/).

## Current V5 Boundary

V5 Phase 12 full production rollout approval is complete. The certified
contracts, builders, read-only API, frontend panel, documentation, tests,
manual API evidence, frontend rendering evidence, governance-copy evidence,
accessibility smoke evidence, fail-closed evidence, controlled rollout
observation, and preserved governance flags support full production rollout
for the certified V5 Bullpen Intelligence Surface.

V5 Phase 12 records:

```text
V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVED
FULL_PRODUCTION_ROLLOUT_APPROVED
```

V5 Phase 12 does not authorize backend decision logic, database migrations,
live runtime integration, runtime observation generation from MLB data, ranking,
selection, prediction, pitcher recommendations, matchup advice, best-arm
language, role advice, manager advice, or automated decision-making.

## Author

Built and maintained by **Nikko**
([NickolisK24](https://github.com/NickolisK24)).
