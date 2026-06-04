# BaseballOS

Trust-first bullpen intelligence for workload, availability, freshness, and
governed pitching-staff decision support.

BaseballOS is a full-stack baseball intelligence platform focused on
relief-pitcher workload. It ingests MLB Stats API data, computes transparent
fatigue and availability signals, and presents bullpen intelligence with visible
trust, freshness, refusal, and governance metadata.

The platform is not a black-box prediction system. It does not tell the user who
to use, rank pitchers, predict outcomes, or hide source freshness. The user
remains the decision maker.

**Stack:** React + TailwindCSS, Flask + Python, PostgreSQL, MLB Stats API.

## Current Platform Status

| Surface | Status |
| --- | --- |
| Bullpen Intelligence | Complete |
| Fatigue Engine | Complete |
| Availability Engine V1 | Complete |
| Recommendation Engine V1 | Certified / production ready |
| Recommendation Engine V2 / Dashboard V2 | Certified / production rollout approved for implemented scope |
| Team Operations Bullpen Readiness | Certified with non-blocking operational gaps / controlled rollout approved |
| V4 Evidence and Explanation Layer | Availability, Team Operations readiness explanations, and explanation API layer certified with non-blocking observations / no frontend or dashboard exposure |
| Prospect Pipeline | Prototype |

Current V3 rollout state:

```text
CONTROLLED_ROLLOUT_APPROVED
READY_FOR_CONTROLLED_ROLLOUT_OBSERVATION
FULL_PRODUCTION_ROLLOUT_NOT_APPROVED
```

Current V4 implementation state:

```text
V4_PHASE_18_EXPLANATION_API_FRONTEND_INTEGRATION_PLANNING_COMPLETE
AVAILABILITY_EXPLANATION_INTEGRATION_CERTIFIED_WITH_NON_BLOCKING_OBSERVATIONS
TEAM_OPERATIONS_READINESS_EXPLANATIONS_CERTIFIED_WITH_NON_BLOCKING_OBSERVATIONS
EXPLANATION_API_LAYER_CERTIFIED_WITH_NON_BLOCKING_OBSERVATIONS
FRONTEND_EXPLANATION_INTEGRATION_PLANNED
READY_FOR_V4_PHASE_19_FRONTEND_EXPLANATION_SURFACE_IMPLEMENTATION
```

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
- Team Operations Bullpen Readiness as a team-level readiness surface for
  operational context, workload pressure, constraints, availability
  distribution, and coverage visibility.
- Governed V4 explanation API routes for certified Availability and Team
  Operations Readiness explanations, with internal route status and no
  frontend or dashboard exposure.
- Protected operational endpoints for sync and recalculation.
- Scheduled sync support through GitHub Actions.

## Governance Boundaries

Certified recommendation and readiness surfaces preserve:

```text
ranking_applied === false
selection_made === false
```

V4 explanation surfaces additionally preserve:

```text
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

BaseballOS does not authorize:

- pitcher ranking
- pitcher selection
- pitcher recommendation beyond certified candidate-level V1 evaluation
- best/preferred/recommended labels for bullpen choice
- hidden priority ordering
- matchup advice
- game outcome prediction
- injury prediction
- save prediction
- performance prediction

Detailed governance, certification, rollout, and monitoring evidence is in
[docs/INDEX.md](docs/INDEX.md).

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

## Data Sources

- MLB Stats API: `https://statsapi.mlb.com/api/v1/`
- PostgreSQL for local and hosted persistence.

BaseballOS is an independent project and is not affiliated with or endorsed by
MLB.

## Documentation

- [Documentation index](docs/INDEX.md) - full documentation map.
- [Project state snapshot](docs/PROJECT_STATE_2026_06.md) - canonical June
  2026 state record.
- [Setup guide](docs/SETUP.md) - local setup, deployment, environment
  variables, and scheduled sync.
- [Roadmap](docs/ROADMAP.md) - current direction and historical roadmap
  context.
- [Changelog](docs/CHANGELOG.md) - major milestones.
- [Certification ledger](docs/governance/CERTIFICATION_LEDGER.md) -
  certification, production, rollout, and governance state by surface.
- [Operational reviews](docs/operations/OPERATIONAL_REVIEWS.md) - deployment
  review, remediation, verification, and rollout evidence summaries.
- [V4 Phase 18 explanation API frontend integration planning](docs/V4_PHASE_18_EXPLANATION_API_FRONTEND_INTEGRATION_PLANNING.md)
  - governed frontend integration plan for certified explanation APIs, with
    progressive disclosure, fail-closed UI, governance display, and dashboard
    anti-regression rules.
- [V4 Phase 17 explanation API formal certification](docs/V4_PHASE_17_EXPLANATION_API_FORMAL_CERTIFICATION_REVIEW.md)
  - certified internal backend API layer for Availability and Team Operations
    Readiness explanations.
  - formal certification review for certified scope exposure, route coverage,
    response contracts, fail-closed behavior, governance, determinism, testing,
    and behavior preservation.
- [V4 Phase 15 explanation API route implementation](docs/V4_PHASE_15_EXPLANATION_API_ROUTE_IMPLEMENTATION.md)
  - governed backend API routes for certified V4 Availability and Team
  Operations Readiness explanations, with fail-closed envelopes and no
  frontend or dashboard exposure.
- [V4 Phase 14 explanation API contract planning](docs/V4_PHASE_14_EXPLANATION_API_CONTRACT_PLANNING.md)
  - governed API contract plan for exposing certified V4 Availability and Team
  Operations Readiness explanations without implementing routes or UI.
- [V4 Phase 13 Team Operations readiness explanation formal certification](docs/V4_PHASE_13_TEAM_OPERATIONS_READINESS_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md)
  - official certification record for internal backend Team Operations
  Readiness Explanations.
- [V4 Phase 12 Team Operations readiness explanation certification readiness](docs/V4_PHASE_12_TEAM_OPERATIONS_READINESS_EXPLANATION_CERTIFICATION_READINESS_REVIEW.md)
  - readiness review for Team Operations explanation scope coverage, reason
  mapping, evidence attribution, limitations, governance, determinism, testing,
  and readiness-engine preservation before formal certification review.
- [V4 Phase 11 Team Operations readiness explanation implementation](docs/V4_PHASE_11_TEAM_OPERATIONS_READINESS_EXPLANATION_IMPLEMENTATION.md)
  - internal backend adapter that maps existing Team Operations readiness
  payloads into governed deterministic V4 explanations without API or UI
  exposure.
- [V4 Phase 10 Team Operations readiness explanation architecture](docs/V4_PHASE_10_TEAM_OPERATIONS_READINESS_EXPLANATION_ARCHITECTURE.md)
  - technical architecture for future readiness explanation generation,
  evidence mapping, reason code strategy, limitation strategy, builder reuse,
  testing, certification, and Phase 11 implementation readiness.
- [V4 Phase 9 Team Operations readiness explanation definition](docs/V4_PHASE_9_TEAM_OPERATIONS_READINESS_EXPLANATION_CAPABILITY_DEFINITION.md)
  - planning record for future readiness explanations, candidate scopes,
  evidence sources, reason codes, governance boundaries, certification
  requirements, and readiness for Phase 10 architecture.
- [V4 Phase 8 availability explanation formal certification](docs/V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md)
  - official certification record for internal backend Availability
  Explanation Integration.
- [V4 Phase 7 availability explanation certification readiness](docs/V4_PHASE_7_AVAILABILITY_EXPLANATION_CERTIFICATION_READINESS_REVIEW.md)
  - readiness review for availability explanation coverage, reason mapping,
  evidence attribution, limitations, governance, determinism, testing, and
  Availability Engine preservation.
- [V4 Phase 6 availability explanation integration](docs/V4_PHASE_6_AVAILABILITY_EXPLANATION_INTEGRATION.md)
  - internal backend adapter that builds governed V4 explanations from existing
  Availability Engine outputs without changing status behavior.
- [V4 Phase 5 evidence and explanation deterministic builder](docs/V4_PHASE_5_EVIDENCE_AND_EXPLANATION_DETERMINISTIC_BUILDER.md)
  - deterministic builders, evidence helpers, limitation helpers, governance
  defaults, stable IDs, serialization support, and tests.
- [V4 Phase 4 evidence and explanation backend domain foundation](docs/V4_PHASE_4_EVIDENCE_AND_EXPLANATION_BACKEND_DOMAIN_FOUNDATION.md)
  - internal backend domain contracts, reason codes, limitations, governance
  payloads, validation, serialization, and tests.
- [V4 Phase 3 evidence and explanation implementation plan](docs/V4_PHASE_3_EVIDENCE_AND_EXPLANATION_IMPLEMENTATION_PLAN.md)
  - implementation roadmap, backend plan, frontend plan, testing, certification,
  and rollout strategy.
- [V4 Phase 2 evidence and explanation architecture](docs/V4_PHASE_2_EVIDENCE_AND_EXPLANATION_ARCHITECTURE_AND_CONTRACT_PLANNING.md)
  - architecture, scope, object-shape, evidence, contract, and certification planning.
- [V4 Phase 1 evidence and explanation definition](docs/V4_PHASE_1_EVIDENCE_AND_EXPLANATION_CAPABILITY_DEFINITION.md)
  - capability definition for the explanation-focused platform layer.
- [V3 Phase 20 controlled rollout observation readiness](docs/V3_PHASE_20_CONTROLLED_ROLLOUT_OBSERVATION_READINESS_REVIEW.md)
  - current controlled rollout observation readiness record.
- [V3 Phase 19 controlled rollout approval](docs/V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md)
  - controlled rollout approval record.
- [Phase 19 monitoring artifact](docs/monitoring/team_operations_bullpen_readiness/PHASE_19_CONTROLLED_ROLLOUT_APPROVAL_ARTIFACT.md)
  - retained controlled rollout evidence artifact.

## Author

Built and maintained by **Nikko**
([NickolisK24](https://github.com/NickolisK24)).
