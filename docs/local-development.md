# Local Development Guide

This guide is the safe local setup for visually reviewing BaseballOS team
stories and the narrative renderer. It is intentionally local-only: do not use
production Supabase, do not paste a Supabase `DATABASE_URL`, and do not run
migrations, seed, sync, or destructive commands against a remote database.

## What This Repo Provides

- Backend: Flask app in `backend/app.py`.
- Frontend: Vite app in `frontend/`.
- Database: PostgreSQL expected for app runtime.
- Migrations: existing Flask-Migrate/Alembic migrations in
  `backend/migrations/`.
- Seed command: `python seed.py` from `backend/`.
- Recent sync command: `python scripts\run_daily_sync.py --days-back 14 --source local_story_review`
  from `backend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- No repository `docker-compose.yml` or `docker-compose.yaml` exists today.

The broad setup guide is `docs/current/SETUP.md`. This file narrows that setup
to safe local narrative review.

## Safety Rules

Use a local, disposable database only. The safest local database URL is a
PostgreSQL database on `localhost` or `127.0.0.1`, for example:

```powershell
postgresql://postgres:password@localhost:5432/baseballos_story_review
```

Do not use:

```powershell
supabase.co
pooler.supabase.com
render.com
amazonaws.com
db.example.com
```

The backend has safety guards:

- `backend/config.py` refuses to start in non-production environments unless
  `DATABASE_URL` is local. Local hosts are `localhost`, `127.0.0.1`, `::1`, and
  `host.docker.internal`; SQLite is accepted by the guard but the app runtime
  is documented for PostgreSQL.
- `APP_ENV=production` is the only mode that accepts a remote database URL, and
  production mode also requires a non-default `SECRET_KEY` and
  `ADMIN_API_TOKEN`.
- Backend test helpers in `backend/tests/db_config.py` refuse schema create/drop
  operations unless the target is disposable, such as in-memory SQLite, temp
  SQLite, or a local Postgres database with `test` in the database name.

For local story review, set `PYTHON_DOTENV_DISABLED=1` and
`FLASK_SKIP_DOTENV=1` before backend commands. That keeps any ignored
`backend/.env` on your machine from silently changing the database or
environment.

## Terminal 1: Local Database

Start PostgreSQL locally. If PostgreSQL is already running as a Windows service,
this may not need a terminal.

Create a disposable review database:

```powershell
psql -U postgres -h localhost -p 5432
```

Then inside `psql`:

```sql
CREATE DATABASE baseballos_story_review;
\q
```

Use your local username, password, host, and port in `DATABASE_URL`. The
database name can be different, but it should be clearly local and disposable.

## Terminal 2: Backend Setup

Run backend commands from `backend/`:

```powershell
cd D:\Programming\baseballos\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Set explicit local environment variables in the same terminal:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:FLASK_SKIP_DOTENV = '1'
$env:APP_ENV = 'development'
$env:FLASK_APP = 'app.py'
$env:DATABASE_URL = 'postgresql://postgres:password@localhost:5432/baseballos_story_review'
$env:SECRET_KEY = 'local-story-review'
$env:AUTO_SYNC = 'false'
$env:FOUR_BEAT_STORIES_ENABLED = 'true'
```

Leave `ADMIN_API_TOKEN` unset for local development unless you specifically want
to test token-protected operator calls. With `APP_ENV=development` and no admin
token, protected write endpoints are allowed locally with a warning.

Confirm the URL is local before any migration, seed, or sync command:

```powershell
$env:DATABASE_URL
```

It must show `localhost`, `127.0.0.1`, `::1`, or `host.docker.internal`. Stop if
it contains Supabase or any hosted database domain.

Apply existing migrations:

```powershell
flask db upgrade
```

Do not run `flask db init`. The migrations folder already exists. Do not run
`flask db migrate` for local startup; that command is for generating new schema
changes after model edits.

Populate a new local database:

```powershell
python seed.py
```

`seed.py` calls the MLB Stats API and can take a few minutes. It creates the
initial pitcher, game log, fatigue, roster, and sample prospect data needed for
the app to show meaningful bullpen surfaces.

After seeding, run a recent local sync to refresh current workload and publish a
local dashboard snapshot:

```powershell
python scripts\run_daily_sync.py --days-back 14 --source local_story_review
```

This also calls the MLB Stats API. It writes only to the local database named in
`DATABASE_URL`. If the network is unavailable, the app can still start, but the
story feed may be empty or stale until seed/sync data exists.

Start the backend:

```powershell
flask run --host 127.0.0.1 --port 5000
```

Backend URL:

```text
http://127.0.0.1:5000
```

Useful checks:

```text
http://127.0.0.1:5000/api/health
http://127.0.0.1:5000/api/bullpen/dashboard
```

For local development, `/api/bullpen/dashboard` serves a published local
snapshot if one exists. If no valid snapshot exists, non-production mode allows
a live fallback assembled from the local database.

## Terminal 3: Frontend Setup

Run frontend commands from `frontend/`:

```powershell
cd D:\Programming\baseballos\frontend
npm install
npm run dev
```

Do not set `VITE_API_BASE_URL` for local review. The Vite dev server proxies
`/api` to `http://127.0.0.1:5000` through `frontend/vite.config.js`.

Frontend URL:

```text
http://localhost:5173
```

Open:

```text
http://localhost:5173/stories
http://localhost:5173/
http://localhost:5173/bullpen
```

## Visual Narrative Renderer Check

Use `/stories` as the primary visual review surface. It reads
`/api/bullpen/dashboard`, normalizes `four_beat_stories.items`, and renders
`story.narrative` before falling back to older story body fields.

Verify:

- Story cards show a title plus natural paragraph text.
- Paragraphs read like a baseball analyst explaining a bullpen situation.
- Cards do not expose public section labels such as `Signal`, `Evidence`,
  `Context`, `Mechanism`, `Implication`, `Observation`, `Why It Matters`, or
  `What I'm Watching`.
- Trust or disclosure notes appear only when the backend already provides them.
- Team story links open the bullpen board, for example
  `/bullpen?view=board&team=TOR&source=four-beat-stories`.

The raw API check is:

```text
http://127.0.0.1:5000/api/bullpen/dashboard
```

In that JSON, confirm:

- `four_beat_stories.items` exists and has at least one item.
- Each visible story item has a `narrative` string.
- Old contract fields such as `body` and `beats` may still exist for backward
  compatibility, but the public story card should render `narrative`.

## Validation Commands

These commands are non-destructive and safe because they use disposable test
database configuration:

```powershell
cd D:\Programming\baseballos
$env:APP_ENV = 'test'
$env:TEST_DATABASE_URL = 'sqlite:///:memory:'
python -m pytest backend/tests/test_config_database.py backend/tests/test_test_database_safety.py
```

Frontend script inventory:

```powershell
cd D:\Programming\baseballos\frontend
npm test
npm run build
```

For a docs-only change, the targeted backend safety tests are usually enough.
Run the full frontend tests or build when frontend code changes or when you need
extra confidence before visual review.
