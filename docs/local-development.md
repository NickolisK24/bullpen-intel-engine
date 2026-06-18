# Local Development Guide

This guide is the safe, reusable local setup for visually reviewing BaseballOS
team stories and the narrative renderer. It is intentionally local-only: do not
use production Supabase, do not paste a Supabase `DATABASE_URL`, and do not run
migrations, seed, sync, reset, or destructive commands against a remote
database.

## What This Repo Provides

- Backend: Flask app in `backend/app.py`.
- Frontend: Vite app in `frontend/`.
- Database: PostgreSQL expected for app runtime.
- Migrations: existing Flask-Migrate/Alembic migrations in
  `backend/migrations/`.
- Backend env template: `backend/.env.example`.
- Local-only backend env template: `backend/.env.local.example`.
- Seed command: `python seed.py` from `backend/`.
- Recent sync command: `python scripts\run_daily_sync.py --days-back 14 --source local_story_review`
  from `backend/`.
- Frontend dev server: `npm run dev` from `frontend/`.
- No repository `docker-compose.yml` or `docker-compose.yaml` exists today.

The broad setup guide is `docs/current/SETUP.md`. This file narrows that setup
to permanent local story review.

## Safety Rules

Use a local, disposable development database only. The recommended permanent
local database is:

```text
database: baseballos_local
role:     baseballos_local
host:     localhost
port:     5432
```

Recommended connection string format:

```powershell
postgresql://baseballos_local:YOUR_LOCAL_PASSWORD@localhost:5432/baseballos_local
```

Do not use:

```text
supabase.co
pooler.supabase.com
render.com
amazonaws.com
db.example.com
```

The backend has safety guards:

- `backend/config.py` refuses to start in non-production environments unless
  `DATABASE_URL` is local. Local hosts are `localhost`, `127.0.0.1`, `::1`, and
  `host.docker.internal`; SQLite is accepted by the guard, but the app runtime
  is documented for PostgreSQL.
- `APP_ENV=production` is the only mode that accepts a remote database URL, and
  production mode also requires a non-default `SECRET_KEY` and
  `ADMIN_API_TOKEN`.
- Backend test helpers in `backend/tests/db_config.py` refuse schema create/drop
  operations unless the target is disposable, such as in-memory SQLite, temp
  SQLite, or a local Postgres database with `test` in the database name.

For local story review, prefer loading `backend/.env.local` explicitly in the
terminal instead of relying on any ignored `backend/.env` that may exist on your
machine. The local template sets `PYTHON_DOTENV_DISABLED=1` and
`FLASK_SKIP_DOTENV=1` for that reason.

## One-Time Setup

### 1. Verify PostgreSQL Is Installed And Running

```powershell
Get-Command psql
Get-Service | Where-Object { $_.Name -match 'postgres|pgsql' -or $_.DisplayName -match 'PostgreSQL|postgres' }
pg_isready -h localhost -p 5432
```

If PostgreSQL is not installed, install PostgreSQL for Windows and include the
command line tools. On this machine the installed service is PostgreSQL 18, so
the service command is:

```powershell
Start-Service postgresql-x64-18
```

If `psql` is not on `PATH`, add the PostgreSQL `bin` folder for your installed
version, for example:

```powershell
$env:Path = "C:\Program Files\PostgreSQL\18\bin;$env:Path"
```

### 2. Create The Permanent Local Role And Database

Open a local Postgres admin shell. This requires the local `postgres` password
chosen when PostgreSQL was installed:

```powershell
psql -h localhost -p 5432 -U postgres -d postgres
```

Inside `psql`, run:

```sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'baseballos_local') THEN
    CREATE ROLE baseballos_local LOGIN PASSWORD 'REPLACE_WITH_A_LOCAL_PASSWORD';
  END IF;
END
$$;

SELECT 'CREATE DATABASE baseballos_local OWNER baseballos_local'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'baseballos_local'
)\gexec

\q
```

Keep the password local. Do not commit it.

### 3. Create A Local Backend Env File

From the repo root:

```powershell
Copy-Item backend\.env.local.example backend\.env.local
notepad backend\.env.local
```

Edit only the local password placeholder:

```text
DATABASE_URL=postgresql://baseballos_local:YOUR_LOCAL_PASSWORD@localhost:5432/baseballos_local
```

`backend/.env.local` is ignored by git. It is meant to persist on this machine
across sessions without committing secrets.

### 4. Create The Backend Virtualenv

```powershell
cd D:\Programming\baseballos\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5. Load The Local Env In The Backend Terminal

Run this from `D:\Programming\baseballos\backend` before migrations, seed, sync,
or backend startup:

```powershell
Get-Content .env.local | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#')) {
    $name, $value = $line -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
  }
}
```

Confirm the target is local before any command that touches the database:

```powershell
python -c "from urllib.parse import urlparse; import os; u=urlparse(os.environ['DATABASE_URL']); assert u.hostname in ('localhost','127.0.0.1','::1','host.docker.internal'), u.hostname; print(f'DATABASE_URL local host: {u.hostname}; database: {u.path.lstrip(\"/\")}')"
```

It must print `localhost` and `baseballos_local`. Stop if it contains Supabase
or any hosted database domain.

### 6. Apply Migrations

```powershell
flask db upgrade
```

Do not run `flask db init`. The migrations folder already exists. Do not run
`flask db migrate` for local startup; that command is for generating new schema
changes after model edits.

### 7. Seed Local Data

```powershell
python seed.py
```

`seed.py` calls the MLB Stats API and can take a few minutes. It creates the
initial pitcher, game log, fatigue, roster, and sample prospect data needed for
the app to show meaningful bullpen surfaces.

### 8. Refresh Recent Local Data

After seeding, run a recent local sync to refresh current workload and publish a
local dashboard snapshot:

```powershell
python scripts\run_daily_sync.py --days-back 14 --source local_story_review
```

This also calls the MLB Stats API. It writes only to the local database named in
`DATABASE_URL`.

### 9. Verify Backend DB Connectivity

```powershell
python -c "from sqlalchemy import text; from app import app; from utils.db import db; ctx=app.app_context(); ctx.push(); print(db.session.execute(text('select current_database()')).scalar()); ctx.pop()"
```

Expected output:

```text
baseballos_local
```

## Daily Startup

### Backend Terminal

```powershell
cd D:\Programming\baseballos\backend
.\venv\Scripts\Activate.ps1
Get-Content .env.local | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#')) {
    $name, $value = $line -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
  }
}
python -c "from urllib.parse import urlparse; import os; u=urlparse(os.environ['DATABASE_URL']); assert u.hostname in ('localhost','127.0.0.1','::1','host.docker.internal'), u.hostname; print(f'DATABASE_URL local host: {u.hostname}; database: {u.path.lstrip(\"/\")}')"
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

### Frontend Terminal

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

Raw API check:

```text
http://127.0.0.1:5000/api/bullpen/dashboard
```

In that JSON, confirm:

- `four_beat_stories.items` exists and has at least one item.
- Each visible story item has a `narrative` string.
- Old contract fields such as `body` and `beats` may still exist for backward
  compatibility, but the public story card should render `narrative`.

## Clean Local Reset And Reseed

This is destructive, but only for the local `baseballos_local` database. Do not
run this against any remote host.

Stop the backend first, then open a local Postgres admin shell:

```powershell
psql -h localhost -p 5432 -U postgres -d postgres
```

Inside `psql`:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'baseballos_local';

DROP DATABASE IF EXISTS baseballos_local;
CREATE DATABASE baseballos_local OWNER baseballos_local;
\q
```

Then run the normal local setup commands again from `backend/` with
`.env.local` loaded:

```powershell
flask db upgrade
python seed.py
python scripts\run_daily_sync.py --days-back 14 --source local_story_review
```

## Validation Commands

These commands are non-destructive and safe because they use disposable test
database configuration:

```powershell
cd D:\Programming\baseballos
$env:APP_ENV = 'test'
$env:TEST_DATABASE_URL = 'sqlite:///:memory:'
python -m pytest backend/tests/test_config_database.py backend/tests/test_test_database_safety.py
```

For docs-only changes, the targeted backend safety tests are usually enough.
Run the full frontend tests or build when frontend code changes or when you need
extra confidence before visual review.
