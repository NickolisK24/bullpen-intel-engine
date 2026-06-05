# BaseballOS

Trust-first bullpen intelligence for workload, availability, freshness, and
governed pitching-staff decision support.

## What BaseballOS Is

BaseballOS is a full-stack baseball intelligence platform focused on
relief-pitcher workload. It ingests MLB Stats API data, computes transparent
fatigue and availability signals, and presents bullpen intelligence with visible
trust, freshness, refusal, explanation, and governance metadata.

BaseballOS is not a black-box prediction system. It does not tell the user who
to use, rank pitchers, predict outcomes, or hide source freshness. The user
remains the decision maker.

**Stack:** React + TailwindCSS, Flask + Python, PostgreSQL, MLB Stats API.

## Current Platform Status

| Surface | Status |
| --- | --- |
| V1 Availability Engine | Production Ready |
| V2 Recommendation Engine | Production Ready |
| V3 Team Operations Readiness | Controlled Rollout Approved |
| V4 Explanation Platform | Full Production Rollout Approved |
| V5 Bullpen Intelligence Surface | Controlled Rollout Approved / Production Rollout Not Approved |

Detailed certification, rollout, and historical phase state is maintained in
[docs/INDEX.md](docs/INDEX.md),
[docs/PROJECT_STATE_2026_06.md](docs/PROJECT_STATE_2026_06.md),
[docs/governance/CERTIFICATION_LEDGER.md](docs/governance/CERTIFICATION_LEDGER.md),
and
[docs/V5_PHASE_9_CONTROLLED_ROLLOUT_REVIEW.md](docs/V5_PHASE_9_CONTROLLED_ROLLOUT_REVIEW.md).

## Core Capabilities

- Deterministic fatigue scoring from pitch-count load, rest days, appearance
  frequency, and innings load.
- Availability Engine V1 statuses: `Available`, `Monitor`, `Limited`, `Avoid`,
  and `Unavailable`.
- Explainable availability output with confidence, data state, reasons,
  limitations, and deterministic inputs.
- Dashboard trust strip for platform status, sync freshness, baseball
  data-through date, and refresh coverage.
- Recommendation Engine V1 candidate-level evaluation with visible refusal,
  confidence, freshness, limitations, and governance metadata.
- Recommendation Engine V2 governed bullpen-state intelligence with team-level
  context, fail-closed behavior, trust metadata, freshness metadata, and
  refusal metadata.
- Team Operations Readiness as a team-level surface for workload pressure,
  constraints, availability distribution, coverage visibility, and operational
  context.
- V4 explanation surfaces for certified Availability and Team Operations
  Readiness APIs, using compact progressive disclosure and fail-closed display.
- V5 read-only observation API and frontend Bullpen Intelligence panel for
  governed descriptive observations from deterministic supplied state.
- Protected operational endpoints for sync and recalculation.
- Scheduled sync support through GitHub Actions.

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
[docs/INDEX.md](docs/INDEX.md) and
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
development. See [docs/SETUP.md](docs/SETUP.md) for full local and hosted setup
details.

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

- [Documentation Index](docs/INDEX.md) - full documentation map.
- [Project State](docs/PROJECT_STATE_2026_06.md) - canonical June 2026 state
  record.
- [Setup Guide](docs/SETUP.md) - local setup, deployment, environment
  variables, and scheduled sync.
- [Roadmap](docs/ROADMAP.md) - current direction and historical roadmap
  context.
- [Certification Ledger](docs/governance/CERTIFICATION_LEDGER.md) -
  certification, production, rollout, and governance state by surface.
- [Operational Reviews](docs/operations/OPERATIONAL_REVIEWS.md) - deployment
  review, remediation, verification, and rollout evidence summaries.
- [V4 Production Rollout Review](docs/V4_PHASE_26_PRODUCTION_ROLLOUT_REVIEW.md)
  - full production rollout approval record for certified V4 explanation
    surfaces.
- [V5 Phase 1 Capability Definition](docs/V5_PHASE_1_BULLPEN_INTELLIGENCE_SURFACE_CAPABILITY_DEFINITION.md)
  - governed Bullpen Intelligence Surface capability boundary and Phase 2
    taxonomy entry point.
- [V5 Phase 2 Observation Taxonomy](docs/V5_PHASE_2_BULLPEN_INTELLIGENCE_SURFACE_OBSERVATION_TAXONOMY.md)
  - authorized observation families, language rules, input boundaries,
    output expectations, and fail-closed requirements.
- [V5 Phase 3 Architecture Definition](docs/V5_PHASE_3_BULLPEN_INTELLIGENCE_SURFACE_ARCHITECTURE_DEFINITION.md)
  - governed observation lifecycle, domain architecture, builder architecture,
    evidence architecture, trust architecture, severity architecture,
    fail-closed architecture, frontend surface architecture, governance
    protection layer, and Phase 4 boundary.
- [V5 Phase 4 Observation Domain And Contracts](docs/V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS.md)
  - backend observation enums, dataclass contracts, serialization helpers,
    contract validators, prohibited-language safeguards, and focused tests.
- [V5 Phase 5 Observation Builder Foundation](docs/V5_PHASE_5_OBSERVATION_BUILDER_FOUNDATION.md)
  - deterministic backend observation builders, static supplied-state
    contracts, fail-closed suppression, evidence propagation, and focused
    builder tests.
- [V5 Phase 6 Observation API Surface](docs/V5_PHASE_6_OBSERVATION_API_SURFACE.md)
  - read-only backend observation API route, preview route, response contract,
    fail-closed behavior, governance tests, and Phase 7 frontend boundary.
- [V5 Phase 7 Frontend Intelligence Surface](docs/V5_PHASE_7_FRONTEND_INTELLIGENCE_SURFACE.md)
  - read-only Dashboard panel consuming `GET /api/observations`, frontend
    contract guard, evidence, limitations, trust, freshness, confidence, and
    governance display.
- [V5 Phase 8 Governance Certification](docs/V5_PHASE_8_GOVERNANCE_CERTIFICATION.md)
  - full V5 governance certification across contracts, builders, API,
    frontend surface, fail-closed behavior, trust, freshness, confidence, and
    prohibited behavior review.
- [V5 Phase 9 Controlled Rollout Review](docs/V5_PHASE_9_CONTROLLED_ROLLOUT_REVIEW.md)
  - controlled rollout approval for the certified V5 Bullpen Intelligence
    Surface, while keeping full production rollout unapproved.

## Next Phase: V5 Bullpen Intelligence Surface

V5 Phase 9 controlled rollout review is complete. The certified contracts,
builders, read-only API, frontend panel, documentation, and tests have been
reviewed for controlled rollout, with evidence, limitations, trust, freshness,
confidence, explanation references, and preserved governance flags.

V5 Phase 9 approves controlled rollout only. It does not authorize full
production rollout, backend decision logic, database migrations, live runtime
integration, runtime observation generation from MLB data, ranking, selection,
prediction, pitcher recommendations, matchup advice, best-arm language, role
advice, or automated decision-making.

Next milestone:

```text
V5_PHASE_10_PRODUCTION_ROLLOUT_REVIEW
```

## Author

Built and maintained by **Nikko**
([NickolisK24](https://github.com/NickolisK24)).
