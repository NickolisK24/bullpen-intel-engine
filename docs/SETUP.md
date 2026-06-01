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

### Bullpen data freshness in local development

The Bullpen list defaults to active/current workload data: pitchers whose latest
game log is within the current 14-day freshness window. This protects the page
from presenting old workload as current availability intelligence.

Local seed data can be a valid historical snapshot while still falling outside
that active window. In that case the dashboard can honestly show tracked
pitchers and game logs while the Bullpen default view says no current pitchers
match the freshness filter. Use **Show inactive pitchers** to inspect all
tracked pitchers from the local snapshot. If the dashboard itself shows no game
logs, the database is empty and needs to be seeded or synced.

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
| `APP_ENV` | backend | No | `development` | Selects the config: `development` (debug on, safe local defaults) or `production` (debug off, fails fast on unsafe config). |
| `DATABASE_URL` | backend | **Yes** (required in production) | `postgresql://postgres:password@localhost/baseballos` | PostgreSQL connection string. A `postgres://` URL is auto-normalized to `postgresql://`. Example: `postgresql://postgres:pw@localhost:5432/baseballos` |
| `FLASK_APP` | backend | Recommended | (none) | Entry point for the `flask` CLI. Set to `app.py`. |
| `SECRET_KEY` | backend | Recommended (required in production) | `dev-secret-key` | Flask secret. Fine to leave default locally; with `APP_ENV=production` the app refuses to start on the dev default. |
| `MLB_API_BASE` | backend | No | `https://statsapi.mlb.com/api/v1` | MLB Stats API base URL. The default is correct for everyone. |
| `AUTO_SYNC` | backend | No | off | `1`/`true`/`yes` enables the in-process daily sync scheduler (06:00 ET). Leave off for dev/tests. |
| `CORS_ORIGINS` | backend | No | (none) | Extra comma-separated allowed origins, added to the built-in localhost + Vercel demo origins. |
| `ADMIN_API_TOKEN` | backend | No (required in production) | (none) | Token gating admin endpoints (`POST /api/bullpen/sync`, `POST /api/bullpen/fatigue/recalculate`, `GET /api/bullpen/fatigue/snapshot`) via the `X-Admin-Token` header. Unset locally -> those routes are allowed in development (with a warning). |
| `VITE_API_BASE_URL` | frontend | No | (uses dev proxy) | Backend origin for the frontend to call (no trailing `/api`). Only needed when the backend is hosted separately. |
| `VITE_ADMIN_API_TOKEN` | frontend | No | (none) | Sends `X-Admin-Token` from the frontend for the operator "Recalculate" action. Usually unset — it ends up in the public bundle, so prefer curl for protected calls. |

### Protected admin endpoints

These endpoints mutate data, trigger expensive MLB pulls, or expose
validation-only historical workload data and are gated by `ADMIN_API_TOKEN`:

- `POST /api/bullpen/sync`
- `POST /api/bullpen/fatigue/recalculate`
- `GET /api/bullpen/fatigue/snapshot`

The snapshot endpoint is admin/dev validation only. It returns
`mode: latest_workload_snapshot`, `is_current_availability: false`, and a
historical warning; public UI must use current-mode endpoints such as
`GET /api/bullpen/fatigue` and `GET /api/bullpen/stats/overview`.

All other read-only `GET`s stay public. Behavior:

- **Token unset (development):** the protected routes are allowed (a warning is
  logged) so local work isn't painful.
- **Token set:** requests must include a matching `X-Admin-Token` header, or they
  get `401 Unauthorized`.
- **`APP_ENV=production`:** `ADMIN_API_TOKEN` is **required** — the app fails fast
  at startup if it's missing, so production can't silently expose these routes.

Call a protected endpoint manually:

```bash
curl -X POST http://localhost:5000/api/bullpen/sync \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-token-here" \
  -d '{"days_back": 7}'
```

> Note: config is selected by `APP_ENV` (`development` by default, or `production`).
> `development` enables debug and the safe local defaults; `production` disables
> debug and fails fast if `SECRET_KEY` (non-default) and `DATABASE_URL` aren't set.
> See "Deployment notes" below.

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

**Dashboard has pitchers/logs, but the Bullpen page has no current pitchers**
→ Data exists, but every pitcher may be outside the active 14-day freshness
window for the current calendar date. Enable **Show inactive pitchers** to view
the stale/inactive snapshot, or run a fresh sync if you expect current-season
data.

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
  (e.g. `gunicorn app:app`). For a hosted environment set `APP_ENV=production`,
  `SECRET_KEY` (a strong unique value), `DATABASE_URL` (a hosted PostgreSQL
  instance), and `ADMIN_API_TOKEN` (gates the write endpoints); the app fails
  fast at startup if any of those production requirements aren't met. Run
  `flask db upgrade` against that database on deploy.
- **Health check:** `GET /api/health` returns `{ status, environment, debug }`,
  so you can confirm a deploy is actually running `production` (debug `false`).
- **Scheduler:** `AUTO_SYNC=true` starts an in-process APScheduler job (06:00
  ET) — fine for local/dev convenience, but **not** reliable for hosted
  production: it only fires if the web process is alive and un-restarted at the
  scheduled time, which a free Render instance (it spins down when idle) can't
  guarantee. For hosted use, prefer an **external scheduler** that POSTs the
  protected sync endpoint — see "Automated daily sync (production)" below.
- **Config / debug:** `APP_ENV=production` loads `ProductionConfig` (debug off);
  unset/`development` keeps debug on for local work. This branch wires that
  switch and the production safety checks, but full deployment (host setup,
  managed Postgres, a production scheduler) is still future work.

### Automated daily sync (production)

In hosted production (frontend on Vercel, backend on Render), don't rely on the
in-process APScheduler. Use an external scheduler that POSTs the protected sync
endpoint once a day. The endpoint is idempotent (it skips duplicates and the DB
enforces game-log uniqueness), so re-runs are safe.

**Recommended: GitHub Actions** (no dependency on the Render web process being
awake first, and free on public repos). A ready-to-use workflow ships at
`.github/workflows/baseballos-sync.yml`. To enable it:

1. In the GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `BASEBALLOS_SYNC_URL` — e.g. `https://baseballos-api.onrender.com/api/bullpen/sync`
   - `BASEBALLOS_ADMIN_API_TOKEN` — the **same** value as the backend's `ADMIN_API_TOKEN`
2. The workflow runs daily at **10:00 UTC** (≈ 6 AM ET during daylight time —
   most of the MLB season; ≈ 5 AM ET during standard time). Cron is always UTC
   and doesn't observe DST, so the ET clock time shifts by an hour seasonally —
   that's fine for a daily refresh.
3. Trigger a manual run anytime from the **Actions** tab ("Run workflow"). The
   job fails loudly (non-zero exit) on any non-2xx response, and calls out
   401/403 as a token mismatch.

**Manual / equivalent curl** (what the scheduler effectively runs):

```bash
curl -X POST https://baseballos-api.onrender.com/api/bullpen/sync \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_API_TOKEN" \
  -d '{"days_back": 7}'
```

**Alternative: Render Cron Job.** Render can run the same `curl` on a schedule,
but a Cron Job is a separate paid service on most plans — GitHub Actions is
simpler and free for this use, so it's the recommended path.

**UptimeRobot is not a sync.** UptimeRobot (or similar) hitting `HEAD/GET
/api/health` only keeps/wakes the Render instance — it does **not** run a sync.
It's complementary: keep your health monitor, and add the GitHub Actions
workflow for the actual daily sync. (If your UptimeRobot plan supports POST with
custom headers it *could* call `/api/bullpen/sync` directly, but the Actions
workflow is cleaner and easier to audit.)

**Expected dashboard behavior after a successful run:** the sync writes
`sync_status.json`, so the dashboard pill switches from **"Snapshot · through
…"** (seeded historical data, no sync yet) to **"Last synced: …"**. If a run
fails, the pill shows **"Last sync failed"**. (Note: the status file is currently
on the instance's ephemeral disk, so a Render restart can revert the pill to the
snapshot state until the next sync — persisting status in the DB is a sensible
future enhancement.)

The protected endpoint stays protected throughout — the scheduler authenticates
with `X-Admin-Token`; there is no anonymous sync and no public sync button.
