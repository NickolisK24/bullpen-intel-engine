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
# DATABASE_URL is required. Local development refuses non-local database hosts.

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

### Bullpen data, roster status, and freshness in local development

The default Bullpen Board shows active bullpen-relevant arms. Clear starters are
excluded from default bullpen planning, and unavailable pitchers are separated
from bullpen arms when the board is configured to show them. Unavailable
pitchers should carry the roster reason, such as IL, minors, optioned, DFA,
non-roster, 40-man-only, released/no-organization, or unknown ownership when
applicable.

Roster status is separate from workload freshness. Local seed data can be a
valid historical snapshot while still falling outside the active workload
freshness window. In that case BaseballOS can honestly show tracked pitchers
and game logs while current workload signals are stale or limited. Use **Show
stale workload pitchers** for the workload list or **Show unavailable pitchers**
on Tonight's Bullpen Board to inspect non-default context. If the dashboard
itself shows no game logs, the database is empty and needs to be seeded or
synced.

The dashboard trust strip separates sync metadata from baseball data coverage:

- **Data Status** describes whether the visible data state is healthy, limited,
  or stale.
- **Synced** is based on explicit sync metadata from durable `sync_runs`
  records when available.
- **Data Through** is based on the latest game-log/workload date represented in
  the database.
- **Refresh Coverage** reports how many pitchers were refreshed by the latest
  sync when that count is available.

Seeded local snapshots may have game logs and fatigue rows without a durable
sync run. In that case BaseballOS should show the data-through date and clearly
state that sync metadata is unavailable rather than implying the database is
empty.

The normal sync sequence is:

```text
team assignment sync
-> roster status sync
-> game log/workload sync
-> fatigue and availability calculation
-> trust/freshness reporting
```

Team assignment runs first so stale ownership is corrected or cleared
fail-closed before roster status and bullpen planning views are assembled.

---

## Step 5 — Run the tests

The backend test suite covers fatigue scoring, availability classification,
freshness behavior, sync metadata, admin protections, audit tooling, and data
integrity checks.

```bash
cd backend
python -m pytest
# Expected: all tests pass
```

These tests do **not** require MLB Stats API access. Database-facing tests use
test-local setup and small fixtures rather than production data.

---

## Environment Variables

All backend variables live in `backend/.env` (template: `backend/.env.example`).
The one optional frontend variable lives in `frontend/.env`
(template: `frontend/.env.example`).

| Variable | Where | Required? | Default | Purpose / Example |
|----------|-------|-----------|---------|-------------------|
| `APP_ENV` | backend | No | `development` | Selects the config: `development` (debug on, explicit local DB required), `test` (test DB only), or `production` (debug off, fails fast on unsafe config). |
| `DATABASE_URL` | backend | **Yes** | (none) | PostgreSQL connection string. Local development must point at a local database, for example `postgresql://postgres:pw@localhost:5432/baseballos`. Hosted URLs are accepted only with `APP_ENV=production`. |
| `FLASK_APP` | backend | Recommended | (none) | Entry point for the `flask` CLI. Set to `app.py`. |
| `SECRET_KEY` | backend | Recommended (required in production) | `dev-secret-key` | Flask secret. Fine to leave default locally; with `APP_ENV=production` the app refuses to start on the dev default. |
| `MLB_API_BASE` | backend | No | `https://statsapi.mlb.com/api/v1` | MLB Stats API base URL. The default is correct for everyone. |
| `AUTO_SYNC` | backend | No | off | `1`/`true`/`yes` enables the in-process daily sync scheduler (06:00 ET). Leave off for dev/tests. |
| `CORS_ORIGINS` | backend | No | (none) | Extra comma-separated allowed origins, added to the built-in localhost + Vercel demo origins. |
| `ADMIN_API_TOKEN` | backend | No (required in production) | (none) | Token gating admin endpoints (`POST /api/bullpen/sync`, `POST /api/bullpen/fatigue/recalculate`, `GET /api/bullpen/fatigue/snapshot`) via the `X-Admin-Token` header. Unset locally -> those routes are allowed in development (with a warning). |
| `EMAIL_PROVIDER` / `EMAIL_API_KEY` / `EMAIL_FROM` | backend | No | `resend` / unset / unset | Optional transactional email config. Audience signups persist when provider config is missing; the welcome email is skipped safely. |
| `VITE_API_BASE_URL` | frontend | No | (uses dev proxy) | Backend origin for the frontend to call (no trailing `/api`). Only needed when the backend is hosted separately. |
| `VITE_SENTRY_DSN` | frontend | No | unset | Optional Sentry browser DSN for production/staging runtime error monitoring. Missing config is a safe no-op. |
| `VITE_APP_ENV` | frontend | No | Vite mode | Optional frontend environment label for error monitoring. Monitoring sends only for `production`, `staging`, or `preview`. |
| `VITE_RELEASE_SHA` | frontend | No | unset | Optional release identifier attached to captured frontend errors. |

There is no frontend admin token. The protected admin endpoints below are
triggered server-side or with curl, never from the browser, so the admin
secret can never reach the public JS bundle.

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
> `development` enables debug but still requires an explicit local `DATABASE_URL`;
> `production` disables debug and fails fast if `SECRET_KEY` (non-default),
> `DATABASE_URL`, or `ADMIN_API_TOKEN` aren't set.
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
window for the current calendar date. Enable **Show stale workload pitchers** to view
the stale workload snapshot, or run a fresh sync if you expect current-season
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
  fast at startup if any of those production requirements aren't met. Database
  migrations are applied automatically before the server starts when the Render
  start command runs `backend/scripts/render_start.sh` (see "Render start
  command" below); that script fails closed if `flask db upgrade` fails, so the
  app never serves traffic against an un-migrated database.
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

### Render start command (apply migrations before startup)

The deployed backend can reference schema added by Alembic migrations — for
example `game_logs.games_started`. If the production database has not run those
migrations, every request that touches the new column fails with a Postgres
`UndefinedColumn` error (HTTP 500). To prevent that, the Render service applies
migrations *before* the web server starts, using a startup script that fails
closed: if `flask db upgrade` fails, the server never starts and the migration
error is visible in the Render logs.

Set the Render service **Start Command** to:

```bash
bash backend/scripts/render_start.sh
```

If the Render service **Root Directory** is set to `backend`, use
`bash scripts/render_start.sh` instead.

With no arguments the script applies migrations and then starts the documented
production server — `gunicorn app:app` bound to Render's `$PORT`. If the service
needs a specific gunicorn invocation (extra `--workers`, `--timeout`, etc.),
pass it as arguments and it is run verbatim after migrations succeed:

```bash
bash backend/scripts/render_start.sh gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
```

This repository has no `Procfile` or `render.yaml`, so the exact gunicorn flags
currently configured in the Render dashboard are not tracked in version control.
The `gunicorn app:app` default matches the command documented in these notes;
confirm it against the service's current Start Command, or pass the exact
command as arguments as shown above. The script only runs when it is set as the
start command, so local development and tests are unaffected.

### Render production configuration checklist

For the hosted backend on Render, the service environment must include:

| Variable | Required production expectation |
| --- | --- |
| `APP_ENV` | `production` |
| `SECRET_KEY` | Strong, unique, non-default secret |
| `DATABASE_URL` | Hosted PostgreSQL connection string |
| `ADMIN_API_TOKEN` | Non-empty token for protected operational endpoints |

After any Render environment change, redeploy or restart the backend and verify:

```text
GET https://baseballos-api.onrender.com/api/health
status: ok
environment: production
debug: false
```

If deployed health reports `environment: development` or `debug: true`, the
deployment must not be treated as production-safe rollout evidence.

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
durable metadata to the `sync_runs` table, while keeping the legacy status file
as a fallback. The dashboard trust strip should show separate sync and data
coverage fields:

```text
Data Status: Healthy
Synced: <last successful sync date>
Data Through: <latest baseball data date>
Refresh Coverage: <pitchers refreshed>
```

If game logs exist but durable sync metadata is unavailable, the dashboard
should show that limitation explicitly instead of presenting the database as
empty:

```text
Data Status: Limited
Sync metadata: Unavailable
Data Through: <latest baseball data date>
```

If the latest run fails, the dashboard should preserve the data-through date and
show the failed sync state separately.

The protected endpoint stays protected throughout — the scheduler authenticates
with `X-Admin-Token`; there is no anonymous sync and no public sync button.
