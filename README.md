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
- **MLB Stats API ingestion** — pulls rosters and game-by-game pitching logs; idempotent
  (skips duplicates, enforced at the database level).
- **Pitcher detail workflow** — per-pitcher view with score, risk tier, weighted component
  breakdown, component radar, fatigue trend, and recent appearances — on desktop **and**
  mobile.
- **Team bullpen views** — per-team bullpen overview and team-vs-team workload rankings.
- **Sync freshness visibility** — the dashboard pill shows the real state: last synced,
  failed, historical snapshot, or no data.
- **Current-season coverage transparency** — the dashboard distinguishes total tracked
  pitchers, pitchers with computed workload data, and pitchers refreshed in the latest sync,
  so coverage gaps are visible rather than hidden.
- **External scheduled sync** — a GitHub Actions workflow refreshes data daily via the
  protected backend endpoint.
- **Protected operational endpoints** — sync and fatigue-recalculation are admin-token
  gated; all read endpoints stay public.
- **Methodology page** — public, in-app documentation of the model, weights, and limitations.
- **Backend test coverage** — unit + integration tests for the scoring engine, the
  admin-token guard, the game-log uniqueness constraint, and the sync-status endpoint.
- **Data integrity** — a database unique constraint makes duplicate game logs impossible.
- **Production config hardening** — environment-driven config with fail-fast checks before a
  hosted launch.

## Trust & Transparency

BaseballOS is built to earn a reviewer's trust rather than ask for it:

- **Methodology page** documents the model, the exact component weights, and — importantly —
  what it does **not** measure (e.g. leverage index is deliberately excluded, not faked).
- **Honest framing:** the score is a workload heuristic; the retrospective fatigue→ERA
  analysis is presented as an exploratory, correlational finding with sample sizes and
  limitations, never as causation or validation.
- **Freshness is always visible** — you can see when data was last synced (or that it's a
  historical snapshot) instead of guessing.
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

- Bullpen **availability engine** (who is usable today, and at what workload cost)
- Usage **simulator** and bullpen **planning dashboard**
- **Role-aware** fatigue (separating starters from relievers)
- A **recommendation** layer for staff decisions
- Trust infrastructure (a DB-backed sync ledger for durable freshness history)
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
│   ├── models/                  # SQLAlchemy models (pitcher, game_log, fatigue_score, prospect)
│   ├── services/                # mlb_api · fatigue (scoring engine) · sync
│   ├── utils/                   # db.py · auth.py (admin-token guard)
│   ├── analysis/                # Out-of-band retrospective fatigue→ERA analysis
│   ├── migrations/              # Alembic migrations (incl. game-log uniqueness)
│   └── tests/                   # pytest: fatigue, auth, game-log constraint, sync status
├── frontend/                    # React + Vite app
│   ├── .env.example             # Frontend env template
│   └── src/
│       ├── components/          # dashboard · bullpen · prospects · methodology · UI
│       ├── hooks/
│       └── utils/               # API client, formatters, shared fatigue-model definitions
└── docs/
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

- [`docs/SETUP.md`](docs/SETUP.md) — local setup, environment variables, troubleshooting,
  deployment notes, and the automated-sync guide.
- **In-app Methodology page** — how the fatigue model works, its weights, and its limitations.

## Roadmap

Near-term focus is depth on the bullpen engine and hardening for a public hosted demo. Beyond
that, see **Product Direction** above — availability/usage intelligence, role-aware fatigue,
decision support, durable freshness history, and exports/API — pursued in honest order, with
prototype features labeled as such until they're real.

## Author

Built and maintained by **Nikko** ([NickolisK24](https://github.com/NickolisK24)).
