# 🛠️ BaseballOS — Setup Guide

Follow this start to finish and you'll have the full app running locally. Every
command below has been verified against the current repository.

> BaseballOS is a baseball analytics platform whose flagship, fully-implemented
> module is the **Bullpen Intelligence Engine**. The Prospect Pipeline is an
> early prototype (sample data); the Methodology page documents how every number
> is computed. See the README for full positioning.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| PostgreSQL | 14+ | `psql --version` |
| pip | latest | `pip --version` |
| npm | 9+ | `npm --version` |

PostgreSQL must be installed and running. The app is written for PostgreSQL
(it uses a `postgresql://` connection string and Postgres-oriented queries).

---

## Step 1 — Create the database

```bash
# Open a psql shell as the postgres user, then:
psql -U postgres
CREATE DATABASE baseballos;
\q
```

Note the username, password, host, port, and database name — you'll put them in
`DATABASE_URL` in the next step.

---

## Step 2 — Backend setup

```bash
cd backend

# 1) Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows (PowerShell/cmd)

# 2) Install dependencies
pip install -r requirements.txt

# 3) Create your .env from the template, then edit DATABASE_URL
cp .env.example .env
# Open .env and set DATABASE_URL to match the database you created, e.g.:
#   DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/baseballos

# 4) Apply the existing database migrations
#    (Do NOT run `flask db init` — the migrations/ folder already exists.)
flask db upgrade

# 5) Seed data from the MLB Stats API (rosters, game logs, fatigue scores,
#    plus a small set of sample prospects). This makes live network calls and
#    can take a few minutes.
python seed.py

# 6) Start the backend
flask run
# Backend runs at http://localhost:5000
```

Why `flask db upgrade` (and not `flask db init` / `flask db migrate`)?
The repository already ships Alembic migrations under `backend/migrations/`.
`flask db upgrade` applies them to your database. `flask db init` would try to
re-create the migrations folder and fail, and `flask db migrate` is only for
generating *new* migrations after you change a model — not part of first-time
setup.

> `FLASK_APP=app.py` is set in `.env`, so the `flask` CLI finds the app
> automatically. If you skipped the `.env` step, export it manually:
> `export FLASK_APP=app.py`.

---

## Step 3 — Frontend setup

```bash
# In a NEW terminal tab
cd frontend

# Install dependencies
npm install

# Start the dev server (proxies /api to http://127.0.0.1:5000 — see vite.config.js)
npm run dev
# Frontend runs at http://localhost:5173
```

For local development you do **not** need a frontend `.env`: the Vite dev server
proxies API calls to the backend on port 5000. Only set `VITE_API_BASE_URL`
(see `frontend/.env.example`) when the backend is hosted somewhere else.

To produce a production build:

```bash
npm run build       # outputs static assets to frontend/dist/
npm run preview     # optional: preview the production build locally
```

---

## Step 4 — Open the app

Navigate to **http://localhost:5173**. You should see the BaseballOS dashboard.
If you ran `python seed.py`, the bullpen views will be populated; otherwise the
dashboard renders with empty states until data is synced.

---

## Step 5 — Run the tests

The backend has a focused test suite for the fatigue scoring engine.

```bash
cd backend
python -m pytest
# Expected: 43 passed
```

These tests are pure unit/integration tests of the scoring logic. They do **not**
require a database, a running Flask server, or any MLB Stats API access — they
use small in-memory stand-ins and run in well under a second.

---

## Environment Variables

All backend variables live in `backend/.env` (template: `backend/.env.example`).
The one optional frontend variable lives in `frontend/.env`
(template: `frontend/.env.example`).

| Variable | Where | Required? | Default | Purpose / Example |
|----------|-------|-----------|---------|-------------------|
| `DATABASE_URL` | backend | **Yes** | `postgresql://postgres:password@localhost/baseballos` | PostgreSQL connection string. Example: `postgresql://postgres:pw@localhost:5432/baseballos` |
| `FLASK_APP` | backend | Recommended | (none) | Entry point for the `flask` CLI. Set to `app.py`. |
| `SECRET_KEY` | backend | Recommended | `dev-secret-key` | Flask secret. Fine to leave default locally; set a strong value anywhere shared/hosted. |
| `MLB_API_BASE` | backend | No | `https://statsapi.mlb.com/api/v1` | MLB Stats API base URL. The default is correct for everyone. |
| `AUTO_SYNC` | backend | No | off | `1`/`true`/`yes` enables the in-process daily sync scheduler (06:00 ET). Leave off for dev/tests. |
| `CORS_ORIGINS` | backend | No | (none) | Extra comma-separated allowed origins, added to the built-in localhost + Vercel demo origins. |
| `VITE_API_BASE_URL` | frontend | No | (uses dev proxy) | Backend origin for the frontend to call (no trailing `/api`). Only needed when the backend is hosted separately. |

> Note: the app currently always loads `DevelopmentConfig` (debug enabled). There
> is a `ProductionConfig` defined in `config.py`, but no environment switch is
> wired to select it yet — see "Deployment notes" below.

---

## Troubleshooting

**`flask db upgrade` fails to connect / "could not connect to server"**
→ PostgreSQL isn't running, or `DATABASE_URL` is wrong. Confirm Postgres is up
(`psql -U postgres -l`) and that the user/password/host/port/dbname in your
`.env` match the database you created in Step 1.

**"relation does not exist" from Flask**
→ Migrations haven't been applied. Run `flask db upgrade` (from `backend/`,
with your venv active and `.env` present).

**`flask: command not found` or "Could not locate a Flask application"**
→ Your virtualenv isn't active (`source venv/bin/activate`), or `FLASK_APP`
isn't set. Ensure `.env` contains `FLASK_APP=app.py`, or `export FLASK_APP=app.py`.

**No data showing in the dashboard**
→ The database is empty. Run `python seed.py` to pull initial data from the MLB
Stats API. (Seeding makes live network calls and can take a few minutes.)

**CORS error in the browser console**
→ Make sure the backend is running on port 5000 and you're using the Vite dev
server (`npm run dev`) so `/api` is proxied. If the frontend is hosted
elsewhere, add its origin to `CORS_ORIGINS` in the backend `.env`.

**Frontend can't reach the API in a production build**
→ A built frontend doesn't use the dev proxy. Set `VITE_API_BASE_URL` to the
backend origin (e.g. `https://your-backend.example.com`) and rebuild.

**"Port already in use"**
→ `flask run --port 5001` (and update the proxy target in `vite.config.js` if
you change it), or stop whatever is using the port.

**Scheduler confusion / no automatic syncs**
→ The daily scheduler only runs when `AUTO_SYNC=true`. With it unset/false you
must trigger syncs manually. This is intentional so tests and migrations don't
kick off background jobs.

---

## Deployment notes

This section documents current expectations only — BaseballOS is **not** yet
configured for one-command production deployment.

- **Frontend:** `npm run build` produces static assets in `frontend/dist/`,
  suitable for a static host (Vercel, Netlify). Set `VITE_API_BASE_URL` to the
  deployed backend origin before building.
- **Backend:** a standard Flask app. `gunicorn` is already in `requirements.txt`
  (e.g. `gunicorn app:app`). It needs `DATABASE_URL` pointing at a hosted
  PostgreSQL instance, and `flask db upgrade` must be run against that database
  on deploy.
- **Scheduler:** `AUTO_SYNC=true` starts an in-process APScheduler job (06:00
  ET). In-process scheduling is not reliable on hosts that sleep idle instances
  or run multiple web workers; a separate scheduled job (e.g. a platform cron
  hitting the sync endpoint) is the more dependable pattern for hosted use.
- **Config / debug:** as noted above, the app currently always runs
  `DevelopmentConfig` (debug enabled). Wiring an environment switch to
  `ProductionConfig` is a prerequisite before any real public deployment.
