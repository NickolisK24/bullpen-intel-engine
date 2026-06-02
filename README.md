# ⚾ BaseballOS

> Trust-first bullpen intelligence platform for workload risk, fatigue transparency, and pitching-staff decision support.

## What BaseballOS Is

BaseballOS is a full-stack baseball intelligence platform focused on **relief-pitcher
workload**. It ingests live MLB Stats API data, scores each pitcher's recent workload as a
transparent 0–100 fatigue value, and presents it through a dashboard built around one
principle: **show what the system knows, what it doesn't, and when the data was last
refreshed.**

It is not a general stats clone and not an "analytics command center" that does a little of
everything. It does one thing seriously — bullpen workload and availability intelligence —
and is honest about everything still in progress.

**Stack:** React + TailwindCSS · Flask + Python · PostgreSQL · MLB Stats API

> The fatigue score is a **transparent workload heuristic** — not an injury or performance
> prediction. The in-app Methodology page documents exactly how every number is computed and
> what the model intentionally does not measure.

## Why It Exists

Bullpen management turns on a hard, time-sensitive question: *who is actually available, and
who is carrying too much recent workload?* That signal is usually buried in raw game logs.
BaseballOS surfaces it directly — rest days, pitch-count load, appearance frequency, and
innings load rolled into one explainable score per pitcher — and pairs it with freshness and
coverage visibility so the number can be trusted instead of taken on faith.

## Current Capabilities

Everything here is implemented and runs against real MLB Stats API data:

- **Fatigue scoring engine** — a deterministic 0–100 workload heuristic from four factors the
  MLB Stats API exposes reliably: pitch-count load (35%), rest days (30%), appearance
  frequency (20%), innings load (15%). Continuous and monotonic across thresholds.
- **Availability Engine V1** — deterministic bullpen availability statuses
  (`Available`, `Monitor`, `Limited`, `Avoid`, `Unavailable`) derived from existing
  workload, fatigue, rest, and freshness data.
- **Availability explainability** — every non-Available status carries ordered reasons,
  confidence, data state, limitations, and deterministic inputs; labels are not black boxes.
- **Dashboard availability summary** — current-mode availability distributions, confidence
  counts, and stale/missing-data notes are visible from the dashboard.
- **MLB Stats API ingestion** — pulls rosters and game-by-game pitching logs; idempotent
  (skips duplicates, enforced at the database level).
- **Pitcher detail workflow** — per-pitcher view with score, risk tier, weighted component
  breakdown, component radar, fatigue trend, recent appearances, availability status,
  confidence, reasons, and limitations — on desktop **and** mobile.
- **Team bullpen views** — per-team bullpen overview and team-vs-team workload rankings.
- **Trust strip and sync freshness visibility** — the dashboard separates platform data
  status, last successful sync, baseball data-through date, and refresh coverage.
- **Durable sync metadata** — sync attempts persist in the `sync_runs` table so successful,
  failed, and missing metadata states survive restarts and deployments.
- **Current-season coverage transparency** — the dashboard distinguishes total tracked
  pitchers, pitchers with computed workload data, and pitchers refreshed in the latest sync,
  so coverage gaps are visible rather than hidden.
- **Freshness-aware bullpen visibility** — active/current data is the default; stale or
  inactive pitchers remain inspectable without being presented as current availability.
- **External scheduled sync** — a GitHub Actions workflow refreshes data daily via the
  protected backend endpoint.
- **Protected operational endpoints** — sync and fatigue-recalculation are admin-token
  gated; all read endpoints stay public.
- **Methodology page** — public, in-app documentation of the model, weights, and limitations.
- **Availability governance framework** — threshold audits, snapshot validation, boundary
  review, and adoption reports document how status thresholds are changed.
- **Backend test coverage** — unit + integration tests for the scoring engine, the
  availability engine, admin-token guard, game-log uniqueness constraint, sync-status
  endpoint, and threshold audit tools.
- **Data integrity** — a database unique constraint makes duplicate game logs impossible.
- **Production config hardening** — environment-driven config with fail-fast checks before a
  hosted launch.

## Platform Status

| Capability | Status |
|------------|--------|
| Bullpen Intelligence | ✓ Complete |
| Fatigue Engine | ✓ Complete |
| Availability Engine | ✓ Complete |
| Explainability | ✓ Complete |
| Trust Layer | ✓ Complete |
| Freshness Transparency | ✓ Complete |
| Governance Framework | ✓ Complete |
| Recommendation Engine | Backend foundation |
| Prospect Pipeline | Prototype |

## Trust & Transparency

BaseballOS is built to earn a reviewer's trust rather than ask for it:

- **Methodology page** documents the model, the exact component weights, and — importantly —
  what it does **not** measure (e.g. leverage index is deliberately excluded, not faked).
- **Honest framing:** the score is a workload heuristic; the retrospective fatigue→ERA
  analysis is presented as an exploratory, correlational finding with sample sizes and
  limitations, never as causation or validation.
- **Freshness is always visible** — you can see when data was last synced (or that it's a
  historical snapshot) instead of guessing.
- **Synced and Data Through are distinct** — sync timestamps come from durable sync metadata;
  baseball coverage dates come from workload/game-log data.
- **Availability labels are explainable** — status badges are paired with confidence, data
  state, reasons, and limitations.
- **Threshold changes are governed** — the first adopted change raised the Unavailable
  three-day pitch threshold from 80 to 90 after audit, experiment, and boundary review.
- **Coverage is explicit** — tracked vs. workload-data vs. refreshed counts are labeled
  distinctly so gaps aren't mistaken for bugs.
- **Write operations are protected** — only an admin token can trigger sync/recalculation.
- **Integrity is enforced in the database**, not just in application code.
- **Tested** — the core scoring logic and operational safeguards have automated coverage.

## Production / Hosted Architecture

| Layer | Where |
|-------|-------|
| Frontend | Vercel (static React build) |
| Backend | Render (Flask + gunicorn) |
| Database | Managed PostgreSQL |
| Scheduled sync | GitHub Actions (daily) |
| Data source | MLB Stats API |

Daily sync is driven **externally** rather than by an in-process timer: a GitHub Actions
workflow (`.github/workflows/baseballos-sync.yml`) POSTs the protected sync endpoint each
morning, authenticating with an `X-Admin-Token` header from a repository secret. This avoids
relying on a free web instance happening to be awake at the scheduled moment. An uptime/health
monitor can keep the backend warm via `GET /api/health`, but health checks **do not** perform
a sync — only the scheduled workflow (or a manual admin call) does. See
[`docs/SETUP.md`](docs/SETUP.md) for the full setup, including the DST note on the run time.

## Planned / Experimental Modules

- **Prospect Pipeline — prototype (sample data).** A development-pipeline view wired to a
  working API but populated with a small set of illustrative, hand-entered sample players —
  **not** a live minor-league feed. It's clearly labeled as a prototype in the UI; treat it as
  a roadmap preview, not a data product.

## Product Direction

Direction, not promises — these are where the platform is headed, not features that exist
today:

- **Recommendation Engine V1** — backend foundation work and the
  candidate-level API route are staged for candidate-level decision support
  while keeping recommendation wording bounded by public workload data and
  explicit limitations. Final ranking, multi-candidate selection, and UI remain
  future work. See
  [`docs/RECOMMENDATION_ENGINE_V1_POLICY.md`](docs/RECOMMENDATION_ENGINE_V1_POLICY.md)
  and
  [`docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md).
  The candidate-level API contract is documented, and the route exposes
  one-candidate evaluation only.
- Usage **simulator** and bullpen **planning dashboard**
- **Role-aware** fatigue (separating starters from relievers)
- **Reports / exports** and a documented **API platform**
- Real minor-league prospect ingestion with a defensible grade/ETA source

## Project Structure

```
bullpen-intel-engine/
├── .github/workflows/
│   └── baseballos-sync.yml      # Daily external sync (POSTs the protected endpoint)
├── backend/                     # Flask API server
│   ├── app.py                   # App factory + env-driven config selection
│   ├── config.py                # Dev/prod config + production fail-fast checks
│   ├── requirements.txt
│   ├── .env.example             # Backend env template
│   ├── seed.py                  # Seeds pitchers, game logs, fatigue scores (+ sample prospects)
│   ├── recalculate_fatigue.py   # Recompute fatigue from historical reference dates
│   ├── api/                     # Route blueprints (bullpen, prospects, methodology)
│   ├── models/                  # SQLAlchemy models (incl. sync_run metadata)
│   ├── recommendation/          # Recommendation Engine V1 contracts, gates, category mapping, builder, and engine pipeline
│   ├── services/                # mlb_api · fatigue · availability · sync metadata
│   ├── utils/                   # db.py · auth.py (admin-token guard)
│   ├── analysis/                # Out-of-band retrospective fatigue→ERA analysis
│   ├── migrations/              # Alembic migrations (incl. game-log uniqueness)
│   ├── reports/                 # Audit, threshold, freshness, and readiness reports
│   └── tests/                   # pytest coverage for fatigue, availability, sync, audits
├── frontend/                    # React + Vite app
│   ├── .env.example             # Frontend env template
│   └── src/
│       ├── components/          # dashboard · bullpen · prospects · methodology · UI
│       ├── hooks/
│       └── utils/               # API client, formatters, shared fatigue-model definitions
└── docs/
    ├── PROJECT_STATE_2026_06.md # Current product state and next milestone
    ├── RECOMMENDATION_ENGINE_V1_POLICY.md
    ├── RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md
    ├── RECOMMENDATION_ENGINE_V1_API_CONTRACT.md
    ├── BULLPEN_AVAILABILITY_ENGINE_V1.md
    ├── AVAILABILITY_THRESHOLD_TUNING_PLAN.md
    └── SETUP.md                 # Full setup, env reference, and deployment notes
```

## Quick Start

Full step-by-step setup (prerequisites, troubleshooting, deployment) is in
[`docs/SETUP.md`](docs/SETUP.md).

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # then edit DATABASE_URL
flask db upgrade            # apply existing migrations
python seed.py              # pull data from the MLB Stats API
flask run                   # http://localhost:5000
```

```bash
# Frontend (new terminal)
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

## Environment Variables

Templates: [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example). Full reference in
[`docs/SETUP.md`](docs/SETUP.md). Do not commit real secrets.

**Backend**

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (required) |
| `APP_ENV` | `development` (default) or `production` |
| `SECRET_KEY` | Flask secret; required (non-default) in production |
| `ADMIN_API_TOKEN` | Gates the write endpoints; required in production |
| `AUTO_SYNC` | Enables the in-process scheduler (local convenience; off by default) |
| `CORS_ORIGINS` | Extra allowed frontend origins |

**Frontend**

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend origin (only needed when hosted separately) |
| `VITE_ADMIN_API_TOKEN` | Optional admin token for the operator recalculate action — note it ships in the public bundle, so prefer curl for protected calls |

**GitHub Actions secrets** (for the scheduled sync)

| Secret | Purpose |
|--------|---------|
| `BASEBALLOS_SYNC_URL` | The backend sync endpoint URL |
| `BASEBALLOS_ADMIN_API_TOKEN` | Must match the backend `ADMIN_API_TOKEN` |

## Testing

```bash
# Backend tests (no database or network required)
cd backend
python -m pytest
```

```bash
# Frontend production build
cd frontend
npm install
npm run build
```

## Data Sources

- **MLB Stats API** — `https://statsapi.mlb.com/api/v1/` (free, no auth) — rosters, game logs,
  and box scores.
- **PostgreSQL** — local during development; a managed instance (Render, Railway, Supabase) in
  hosted environments.

BaseballOS is an independent project and is not affiliated with or endorsed by MLB.

## Documentation

- [`docs/PROJECT_STATE_2026_06.md`](docs/PROJECT_STATE_2026_06.md) — current
  product state after the Availability Engine trust foundation.
- [`docs/RECOMMENDATION_ENGINE_V1_POLICY.md`](docs/RECOMMENDATION_ENGINE_V1_POLICY.md)
  — authoritative policy for trust-first recommendation eligibility,
  exclusions, refusal conditions, categories, explanations, limitations, and
  governance boundaries.
- [`docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md)
  — staged engineering plan for translating the approved policy into backend
  boundaries, gates, payloads, tests, API exposure, UI planning, and governance
  validation.
- [`docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md)
  - candidate-level API contract for request and response shapes, trust
  fields, freshness fields, refusal handling, frontend display requirements,
  and no-ranking/no-selection guarantees.
- [`docs/BULLPEN_AVAILABILITY_ENGINE_V1.md`](docs/BULLPEN_AVAILABILITY_ENGINE_V1.md)
  — status definitions, implemented classifier contract, UI presentation, trust
  rules, and non-goals.
- [`docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`](docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md)
  — governance process and current threshold baseline.
- [`docs/SETUP.md`](docs/SETUP.md) — local setup, environment variables, troubleshooting,
  deployment notes, and the automated-sync guide.
- [`frontend/docs/dashboard_trust_strip_polish.md`](frontend/docs/dashboard_trust_strip_polish.md)
  — dashboard trust strip layout and messaging rationale.
- **In-app Methodology page** — how the fatigue model works, its weights, and its limitations.

## Roadmap

Recommendation Engine V1 is progressing in staged backend foundation work:
policy, implementation planning, candidate-level engine integration, API
contract documentation, and candidate route exposure are present. Final ranking,
multi-candidate selection, and UI remain future work. Beyond that, see
**Product Direction** above: usage simulation, role-aware fatigue, exports/API,
and real prospect ingestion - pursued in honest order, with prototype features
labeled as such until they're real.

## Author

Built and maintained by **Nikko** ([NickolisK24](https://github.com/NickolisK24)).
