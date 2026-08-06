# BaseballOS Setup Guide

**Status:** Current operational setup guide  
**Owner:** Nickolis Kacludis  
**Reviewed:** August 6, 2026

This guide gets the current BaseballOS application running locally. It is a
procedure, not a product or architecture authority. Durable rules live in the
[canonical library](../canonical/README.md); exact dependency and environment
variable values live in the repository manifests and `.env.example` files.

BaseballOS is a public MLB **bullpen intelligence** platform. It is not a general
baseball analytics suite, and the old Prospect Pipeline prototype is not part of
the current public product direction.

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+
- PostgreSQL 14+
- Git

PostgreSQL is the production database authority and should also be used for
meaningful local/integration validation. SQLite-only behavior is not sufficient
proof for production semantics.

## 1. Create a Local Database

Example:

```bash
psql -U postgres
CREATE DATABASE baseballos;
\q
```

Use your own local username/password/host/port as appropriate.

## 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env
```

Set at minimum:

```dotenv
APP_ENV=development
FLASK_APP=app.py
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/baseballos
```

Then apply migrations:

```bash
flask db upgrade
```

Do **not** run `flask db init`. The repository already owns Alembic migration
history under `backend/migrations/`.

Optional live seed:

```bash
python seed.py
```

`seed.py` makes live MLB source calls. It is useful for local exploration but is
not required for normal automated tests.

Start the backend:

```bash
flask run
```

Default local backend: `http://localhost:5000`.

## 3. Frontend Setup

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Default local frontend: `http://localhost:5173`.

The Vite development server proxies API requests to the local Flask backend. Set
`VITE_API_BASE_URL` only when the backend is hosted somewhere else.

Production build:

```bash
npm run build
npm run preview
```

## 4. What You Should See

The current public product centers on bullpen intelligence:

- Today
- Dashboard
- Team Board
- Compare
- Reliever Finder
- Pitcher Detail
- Stories
- Methodology
- Data & Trust
- immutable Share Artifact pages

Public Team State is exactly:

- `Fresh`
- `Stretched`
- `Vulnerable`

Public arm reads are exactly:

- `Clean Option`
- `Watch Arm`
- `Limited Rest`
- `Unavailable`
- `Limited Read`

Internal availability values such as Available / Monitor / Limited / Avoid /
Unavailable are calculation detail and must not be treated as a second public
vocabulary.

## 5. Local Data and Freshness

A local database may contain valid historical records without representing a
current trusted MLB picture.

Keep these concepts separate:

- **Data Through** — latest baseball date represented by the relevant evidence.
- **Sync/update time** — when BaseballOS last wrote or refreshed data.
- **Current trusted read** — a read whose required source/freshness/coverage gates pass.
- **Historical data** — valid past evidence that must not be presented as current.

Missing information is never replaced with zero or a plausible value.

Historical appearance ownership remains attached to the team side for which the
pitcher appeared in that game. Current organization/roster membership is a
separate fact.

Team State is derived from the canonical current active bullpen population. A
starter or off-active arm may remain visible as context but must not determine
Fresh / Stretched / Vulnerable.

## 6. Environment Variables

The exact registries are:

- `backend/.env.example`
- `frontend/.env.example`

Stable backend categories include:

| Variable / category | Purpose |
|---|---|
| `APP_ENV` | Development/test/production behavior. |
| `DATABASE_URL` | PostgreSQL connection; required. |
| `FLASK_APP` | Local Flask CLI entry point. |
| `SECRET_KEY` | Session/signing secret; non-default required in production. |
| `MLB_API_BASE` | Optional MLB source base override. |
| `ADMIN_API_TOKEN` | Protected backend/workflow operations; required in production where configured by the app. Never send to the browser. |
| `CORS_ORIGINS` | Additional approved browser origins. |
| email-provider variables | Magic-link/audience messaging where enabled. |
| internal-email allowlists | Browser-safe internal authorization. |
| sync budget/lookback variables | Bounded source/runtime operation. |

Stable frontend categories include:

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Hosted backend origin. |
| `VITE_SENTRY_DSN` | Optional browser monitoring. |
| `VITE_APP_ENV` | Monitoring environment label. |
| `VITE_RELEASE_SHA` | Release identifier. |

There is no frontend admin-token variable. A production admin secret must never
be embedded in built JavaScript.

## 7. Tests

Backend:

```bash
python -m pytest backend/tests
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

Normal automated tests should not require live MLB access; controlled fixtures
should represent source behavior.

CI uses PostgreSQL-backed backend confidence shards and lockfile-faithful
frontend installation/build validation. Trust-critical CI receives the Git
history it needs for behavior-freeze checks.

A green suite does not replace production smoke, live-source verification, or a
scheduled observation window when those are explicit acceptance criteria.

## 8. Database Migrations

Every model/schema change requires an Alembic migration and a safe production
upgrade path.

Before merging schema work, prove:

- upgrade from current production head;
- PostgreSQL semantics;
- constraints and foreign-key behavior;
- deployment ordering;
- rollback/downgrade behavior or explicit irreversible rationale;
- documentation update when the domain contract changes.

Do not create production tables ad hoc from application startup.

## 9. Production Architecture Boundary

Current operating posture:

- legacy daily/postgame sync remains authoritative for baseball-data mutation;
- game-driven daily and postgame lanes are **shadow** observers;
- backfill is off by default and only runs through explicit governed dispatch;
- automated game-driven write mode is unapproved;
- game-driven publication-authority transfer is unapproved.

Do not infer authority from the existence of a workflow, service, test, or
manual qualification tool.

The game `824487` single-purpose source-revision checkpoint repair has been
completed and retired. Its former mutation path must not be treated as a general
repair tool or reintroduced for convenience.

## 10. Sync and Production Operations

For current sync order, publication gates, shadow/public verdict separation,
runtime-budget behavior, and recovery rules, use:

- [`SYNC_PIPELINE.md`](SYNC_PIPELINE.md)
- [`DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md)
- the canonical [Architecture & Operations Manual](../canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md)
- the canonical [Roadmap & Decision Ledger](../canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md)

Do not run a production mutation merely to make a screenshot or local demo look
current.

## 11. Troubleshooting

### PostgreSQL connection failure

Confirm PostgreSQL is running and that `DATABASE_URL` points at the intended
local database.

### Missing relations

Run:

```bash
flask db upgrade
```

Do not initialize a second migration history.

### Empty public surfaces

If you have not seeded or synced data, empty/quiet states are expected. Do not
interpret an empty local database as a product defect.

### Stale or limited reads

Check the represented baseball date and source coverage. A technically recent
process timestamp does not make stale baseball evidence current.

### Production operation question

Stop and read the relevant current runbook before dispatching anything. If the
procedure is not explicitly documented and bounded, do not improvise a write.
