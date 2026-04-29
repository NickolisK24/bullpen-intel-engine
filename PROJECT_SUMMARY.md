# BaseballOS — Project State Summary

## 1. Project Overview

BaseballOS is a full-stack baseball analytics platform built around three modules: a Bullpen / Fatigue Tracker that pulls live and historical pitcher game logs from the public MLB Stats API and runs them through a weighted 0–100 fatigue scoring engine, a Prospect Pipeline that catalogs minor-league prospects with 20–80 scouting grades and development levels, and a Portfolio layer that documents methodology, projects, and contact information. The app is positioned as a personal analytics command center / portfolio piece intended to demonstrate baseball-development thinking — pitching workload modeling, pipeline tracking, and end-to-end product execution — to a hiring audience inside MLB front offices.

## 2. Tech Stack

**Backend (Python)**
- Flask 3.0.0
- Flask-SQLAlchemy 3.1.1
- Flask-Migrate 4.0.5 (Alembic 1.13.0)
- Flask-CORS 4.0.0
- SQLAlchemy 2.0.23
- psycopg2-binary 2.9.9 (PostgreSQL driver)
- python-dotenv 1.0.0
- requests 2.31.0
- APScheduler 3.10.4 (daily background sync)
- gunicorn 21.2.0 (production WSGI)
- Python 3.10+ required (uses `from datetime ... | None` PEP 604 syntax and `zoneinfo`)

**Frontend (Node / React)**
- React 18.2.0
- React-DOM 18.2.0
- React Router DOM 6.22.0
- Recharts 2.12.0 (radar + line charts)
- clsx 2.1.0
- Vite 5.1.0
- @vitejs/plugin-react 4.2.1
- TailwindCSS 3.4.1
- PostCSS 8.4.35 + autoprefixer 10.4.17

**Datastore**
- PostgreSQL 14+ (configured via `DATABASE_URL`; default `postgresql://postgres:password@localhost/baseballos`)

**Data sources**
- MLB Stats API — `https://statsapi.mlb.com/api/v1` (free, no auth)

**Tooling / fonts**
- Google Fonts (Bebas Neue, DM Sans, JetBrains Mono) loaded via `index.html`

## 3. File Structure

```
bullpen-intel-engine/                          (project root; README references "baseballos/")
├── README.md                                  Top-level pitch + quick start.
├── .gitignore                                 Ignores __pycache__, .env, *.db, venv/, .vscode/, backend/logs/.
├── docs/
│   └── SETUP.md                               Step-by-step Windows/Mac/Linux setup guide.
├── backend/
│   ├── app.py                                 Flask app factory; registers blueprints, CORS, Migrate, and the AUTO_SYNC-gated APScheduler daily job.
│   ├── config.py                              Loads .env and exposes Development / Production config classes.
│   ├── requirements.txt                       Python dependency manifest.
│   ├── seed.py                                One-shot seeder: pulls 30-team rosters + 2024–2025 game logs, scores fatigue, inserts curated sample prospects.
│   ├── recalculate_fatigue.py                 CLI script that re-scores every active pitcher using their last-game date as the reference point and prints a risk distribution.
│   ├── api/
│   │   ├── bullpen.py                         Blueprint: fatigue scores, pitcher logs, teams, sync, MLB passthroughs.
│   │   ├── prospects.py                       Blueprint: prospect listing, by-team, pipeline, compare, overview stats.
│   │   └── portfolio.py                       Blueprint: returns a single hand-authored portfolio JSON payload.
│   ├── models/
│   │   ├── pitcher.py                         Pitcher table + to_dict.
│   │   ├── game_log.py                        GameLog table (pitching line per appearance) with composite indexes.
│   │   ├── prospect.py                        Prospect table (identity + 20-80 grades + season stats).
│   │   └── fatigue_score.py                   FatigueScore table (component + composite scores + supporting metrics).
│   ├── services/
│   │   ├── mlb_api.py                         MLBApiClient singleton — wraps statsapi.mlb.com endpoints (teams, rosters, game logs, schedule, boxscore, prospects).
│   │   ├── fatigue.py                         Pure scoring engine: 5 component sub-scores → weighted composite → risk tier.
│   │   └── sync.py                            Shared sync + recalculate functions used by both POST /api/bullpen/sync and the daily APScheduler job; writes/reads logs/sync_status.json.
│   ├── utils/
│   │   └── db.py                              SQLAlchemy() singleton.
│   └── migrations/                            Flask-Migrate / Alembic project.
│       ├── alembic.ini                        Alembic configuration.
│       ├── env.py                             Standard Flask-Migrate env.py.
│       ├── README                             Single-line migrations README.
│       ├── script.py.mako                     Alembic revision template.
│       └── versions/
│           ├── 3b06397ddc6b_create_all_tables.py     Initial migration (pitchers / prospects / fatigue_scores / game_logs).
│           └── 018704c8d5fe_add_indexes_and_game_type.py  Adds game_type column + ix_fatigue_pitcher_calc, ix_game_log_pitcher_date, ix_game_log_game_pk, ix_game_log_game_type indexes.
└── frontend/
    ├── index.html                             Vite HTML shell; preconnects Google Fonts and mounts #root.
    ├── vite.config.js                         Vite + react plugin; dev server on :5173 with /api → http://127.0.0.1:5000 proxy.
    ├── tailwind.config.js                     Custom palette (field/dugout/chalk/dirt/amber/pine/etc.), font families, animations, grid-lines + stadium-glow backgrounds.
    ├── postcss.config.js                      Tailwind + autoprefixer plugins.
    ├── package.json                           Scripts (dev / build / preview), dependencies.
    ├── package-lock.json                      Lockfile.
    └── src/
        ├── main.jsx                           React DOM root + StrictMode.
        ├── App.jsx                            BrowserRouter + Sidebar layout; routes /, /bullpen, /prospects, /portfolio.
        ├── index.css                          Tailwind layers + CSS variables (palette) + .card/.data-table/.badge-*/.nav-item utilities + bg-noise utility.
        ├── components/
        │   ├── Sidebar.jsx                    Sticky left rail with NavLinks (Dashboard / Bullpen / Pipeline / Portfolio).
        │   ├── UI/
        │   │   ├── index.js                   Barrel exports for shared UI primitives.
        │   │   ├── LoadingPane.jsx            Animated baseball-diamond loading skeleton.
        │   │   ├── ErrorState.jsx             Red-tinted error card with optional Try Again button.
        │   │   ├── SectionHeader.jsx          Page-level title + subtitle + optional action slot.
        │   │   ├── Divider.jsx                Horizontal rule with optional centered label and solid/dashed variant.
        │   │   ├── EmptyState.jsx             Empty-list placeholder (icon + title + subtitle).
        │   │   ├── FatigueBar.jsx             Horizontal fatigue bar; color comes from utils/formatters.fatigueBarColor.
        │   │   ├── GradeBox.jsx               20-80 scouting grade tile.
        │   │   ├── RiskBadge.jsx              Risk pill ("●●●○ HIGH" style) using badge-low/moderate/high/critical classes.
        │   │   ├── Spinner.jsx                Amber-on-dirt CSS spinner (sm/md/lg).
        │   │   └── StatCard.jsx               Animated dashboard stat card; supports `accent` variant + delay.
        │   ├── dashboard/
        │   │   ├── Dashboard.jsx              Hero, overview stats, risk distribution bar, "Most Fatigued" + "Pipeline Snapshot" cards, quick links.
        │   │   ├── SeasonBanner.jsx           Pill showing "Live" or "End-of-Season Snapshot" for a given season.
        │   │   └── SyncStatus.jsx             Reads /api/bullpen/sync/status; renders Last-synced pill with stale (>36h) and error states.
        │   ├── bullpen/
        │   │   ├── Bullpen.jsx                Page: view-mode toggle (Pitchers/Team Rankings), team pills, risk filter tabs, sortable scores table, side detail.
        │   │   ├── PitcherDetail.jsx          Detail panel: score+risk, quick stats, weighted breakdown bars, radar chart, fatigue trend line, recent appearances table with spring-training detection.
        │   │   └── TeamComparison.jsx         Fans out 30 GETs to /teams/{id}/bullpen, computes per-team avg + counts, sortable rankings table.
        │   ├── prospects/
        │   │   ├── Prospects.jsx              Page: pipeline/list view toggle, level selector tiles, ProspectMiniCard grid, side ProspectCard.
        │   │   └── ProspectCard.jsx           Detail panel for a selected prospect: level/ETA, scouting grades, current-season stats, scout notes.
        │   └── portfolio/
        │       └── Portfolio.jsx              Renders /api/portfolio response: hero, stack, projects, fatigue methodology, risk tiers, contact links.
        ├── hooks/
        │   └── useFetch.js                    Tiny fetch hook returning { data, loading, error, refetch } with a deps array.
        └── utils/
            ├── api.js                         Thin fetch wrapper around `/api`; one helper per backend route.
            └── formatters.js                  Number/date formatters + risk/grade/level color maps.

# Files referenced in the request but NOT present on disk
- backend/services/prospects.py     (referenced in README; not implemented)
- backend/logs/sync_status.json     (gitignored; created at runtime by the daily sync job)
```

## 4. Backend — Complete API Reference

All routes are mounted under `/api`. Health is unprefixed; the three blueprints register at `/api/bullpen`, `/api/prospects`, `/api/portfolio`.

### Health
| Method | Route | Purpose | Returns |
| --- | --- | --- | --- |
| GET | `/api/health` | Liveness check. | `{ status: 'ok', message: 'BaseballOS API is live' }` |

### Bullpen blueprint (`backend/api/bullpen.py`)

**GET `/api/bullpen/fatigue`** — Latest fatigue score per pitcher, joined with pitcher info.
- Query params: `team_id` (int), `risk_level` (`LOW|MODERATE|HIGH|CRITICAL`), `limit` (int, default 50).
- Implementation uses a `MAX(calculated_at)` subquery so each pitcher contributes one row.
- Returns: array of `{ ...FatigueScore.to_dict(), pitcher: Pitcher.to_dict() }` ordered by `raw_score DESC`.

**GET `/api/bullpen/fatigue/<pitcher_id>`** — Detailed fatigue profile for one pitcher.
- Returns `{ pitcher, current_fatigue, recent_logs (last 14 days), fatigue_trend (last 30 days) }`.
- Issue: `recent_logs` and `fatigue_trend` use `date.today()` as the anchor, which is empty against historical 2024–2025 seed data and won't match the `last-game-date` reference used by the score itself.

**POST `/api/bullpen/fatigue/recalculate`** — Recalculates fatigue for every active pitcher using each pitcher's last game date as the reference.
- Returns `{ recalculated: int, results: [{ pitcher, score, risk }, ...] }`.
- Note: this is an unauthenticated mutating endpoint that O(N) writes a row per pitcher.

**POST `/api/bullpen/sync`** — Pulls recent game logs from MLB API and recalculates fatigue.
- Optional JSON body `{ "days_back": 7 }` (default 7).
- Delegates to `services.sync.sync_recent_logs` then `recalculate_all_fatigue(use_last_game_date=False)` (i.e. live-mode scoring against today).
- Returns `{ status, new_logs_added, fatigue_recalculated, errors, synced_at, days_back }`.

**GET `/api/bullpen/sync/status`** — Reads the last status file written by the daily APScheduler job.
- Returns `{ last_sync, status, pitchers_updated, new_logs_added, errors, message, finished_at }` or a `'never'` sentinel if `logs/sync_status.json` does not exist.

**GET `/api/bullpen/pitchers`** — All active pitchers (optionally filtered by `team_id`), ordered by team then name.

**GET `/api/bullpen/pitchers/<pitcher_id>/logs`** — Game logs for a pitcher in the last `days` (default 30).
- Issue: filters by `date.today() - days`, which returns empty for the 2024–2025 seed window in 2026.

**GET `/api/bullpen/teams`** — All distinct teams in the DB with `pitcher_count`.

**GET `/api/bullpen/teams/<team_id>/bullpen`** — Full bullpen for one team via a single LEFT JOIN to the latest fatigue score per pitcher. Returns `[{ pitcher, fatigue }]`.

**GET `/api/bullpen/stats/overview`** — Dashboard counts: `total_pitchers`, `total_game_logs`, `risk_breakdown`, `avg_fatigue_score`, `scored_pitchers`.
- Issue: `avg_fatigue_score` is computed over all rows in `fatigue_scores`, not just the latest score per pitcher — this skews the displayed average.

**GET `/api/bullpen/mlb/teams`** — Live passthrough to `MLBApiClient.get_all_teams()`.

**GET `/api/bullpen/mlb/pitcher/<player_id>/logs`** — Live passthrough to `get_pitcher_game_logs(player_id, season=?)` (season query param optional).

### Prospects blueprint (`backend/api/prospects.py`)

**GET `/api/prospects/`** — Filterable prospect list.
- Params: `team_id` (int), `level` (uppercased before matching), `position` (uppercased), `min_grade` (int), `limit` (int, default 100).
- Sorted by `overall_grade DESC NULLS LAST, full_name ASC`.

**GET `/api/prospects/<prospect_id>`** — Single prospect detail.

**GET `/api/prospects/by-team`** — Returns `[{ team_name, team_abbreviation, prospects: [...] }]`, prospects sorted by overall grade.

**GET `/api/prospects/pipeline`** — Returns `{ levels: ['ROK','A','A+','AA','AAA','MLB'], pipeline: { LEVEL: [...] }, total }`.

**GET `/api/prospects/compare?id1=&id2=`** — Side-by-side pair (400 if either id missing).

**GET `/api/prospects/stats/overview`** — `{ total, by_level, top_10 }` — top-10 sorted by overall grade.

### Portfolio blueprint (`backend/api/portfolio.py`)

**GET `/api/portfolio/`** — Returns a hardcoded JSON object with name, title, background bullets, mission goal, stack list, projects, methodology (fatigue engine components + risk tiers), and contact handles. No DB access.

## 5. Data Models

All four models are SQLAlchemy classes registered through `utils.db.db = SQLAlchemy()`. Migrations live in `backend/migrations/versions/`.

### `pitchers` (`backend/models/pitcher.py`)
| Column | Type | Notes |
| --- | --- | --- |
| id | Integer | Primary key. |
| mlb_id | Integer | Unique, NOT NULL — MLB Stats API person id. |
| full_name | String(100) | NOT NULL. |
| team_id | Integer | NOT NULL — MLB team id. |
| team_name | String(100) | |
| team_abbreviation | String(10) | |
| position | String(10) | Defaults to `'P'`. |
| throws | String(1) | `'R'` or `'L'`. |
| age | Integer | |
| jersey_number | String(5) | |
| active | Boolean | Defaults `True`; queries always filter on this. |
| created_at | DateTime | Defaults `datetime.utcnow`. |
| updated_at | DateTime | `onupdate=datetime.utcnow`. |

Relationships: `game_logs` and `fatigue_scores` (one-to-many, cascade delete-orphan).

### `game_logs` (`backend/models/game_log.py`)
| Column | Type | Notes |
| --- | --- | --- |
| id | Integer | Primary key. |
| pitcher_id | Integer FK→pitchers.id | NOT NULL. |
| mlb_game_pk | Integer | NOT NULL — MLB game primary key. |
| game_date | Date | NOT NULL. |
| opponent | String(50) | |
| opponent_abbreviation | String(10) | |
| game_type | String(2) | `'R'` regular, `'S'` spring, `'P'` playoffs (default `'R'`). |
| innings_pitched | Float | Default 0.0. |
| pitches_thrown | Integer | Default 0. |
| strikes | Integer | Default 0. |
| hits_allowed | Integer | Default 0. |
| runs_allowed | Integer | Default 0. |
| earned_runs | Integer | Default 0. |
| walks | Integer | Default 0. |
| strikeouts | Integer | Default 0. |
| home_runs_allowed | Integer | Default 0. |
| leverage_index | Float | Nullable — never populated by current sync code. |
| inherited_runners | Integer | Default 0. |
| inherited_runners_scored | Integer | Default 0. |
| save_situation, hold, blown_save, win, loss, save | Boolean | Default False. |
| created_at | DateTime | Defaults `datetime.utcnow`. |

Indexes: `ix_game_log_pitcher_date (pitcher_id, game_date)`, `ix_game_log_game_pk (mlb_game_pk)`, `ix_game_log_game_type (game_type)`.

### `prospects` (`backend/models/prospect.py`)
| Column | Type | Notes |
| --- | --- | --- |
| id | Integer | Primary key. |
| mlb_id | Integer | Unique (nullable). |
| full_name | String(100) | NOT NULL. |
| team_id | Integer | |
| team_name | String(100) | |
| team_abbreviation | String(10) | |
| position | String(10) | |
| bats | String(1) | |
| throws | String(1) | |
| age | Integer | |
| birth_date | Date | |
| nationality | String(50) | |
| current_level | String(10) | `ROK / A / A+ / AA / AAA / MLB`. |
| eta_year | Integer | Projected MLB ETA. |
| hit_grade, power_grade, speed_grade, field_grade, arm_grade, overall_grade | Integer | 20–80 scouting scale. |
| games_played, at_bats | Integer | Default 0. |
| batting_average, on_base_pct, slugging_pct, ops | Float | |
| home_runs, rbi, stolen_bases | Integer | Default 0. |
| strikeout_rate, walk_rate | Float | |
| era, whip, innings_pitched, k_per_9, bb_per_9, fip | Float | Pitching-prospect stats. |
| notes | Text | |
| active | Boolean | Default True. |
| created_at, updated_at | DateTime | utcnow / onupdate. |

`to_dict()` nests `grades` and `stats` sub-objects for the frontend.

### `fatigue_scores` (`backend/models/fatigue_score.py`)
| Column | Type | Notes |
| --- | --- | --- |
| id | Integer | Primary key. |
| pitcher_id | Integer FK→pitchers.id | NOT NULL. |
| calculated_at | DateTime | Defaults `datetime.utcnow`. |
| raw_score | Float | NOT NULL — composite 0–100. |
| pitch_count_score, rest_days_score, appearances_score, leverage_score, innings_score | Float | Component sub-scores 0–100. |
| days_since_last_appearance | Integer | |
| appearances_last_7, appearances_last_14 | Integer | Default 0. |
| pitches_last_7_days | Integer | Default 0. |
| innings_last_7_days | Float | Default 0.0. |
| avg_leverage_last_7 | Float | Defaults to 1.0 in calculator if no logs have leverage. |
| risk_level | String(10) | `LOW / MODERATE / HIGH / CRITICAL`. |

Index: `ix_fatigue_pitcher_calc (pitcher_id, calculated_at)` for fast latest-score lookups.

## 6. Fatigue Engine

Defined in `backend/services/fatigue.py`. Pure function — takes a `Pitcher`, an ordered list of recent `GameLog`s, and an optional `reference_date`, and returns an unsaved `FatigueScore`.

### Window selection
- `ref = reference_date or date.today()`.
- `seven_days_ago = ref - 7 days`; `fourteen_days_ago = ref - 14 days`.
- `logs_7` and `logs_14` are computed by filtering `game_logs` whose `game_date` falls in `[fourteen_days_ago, ref]` and `[seven_days_ago, ref]`.
- `last_log = game_logs[0]` (caller is expected to pass logs ordered most-recent first).
- `days_since_last = (ref - last_log.game_date).days`, or `None` if no logs.

### Aggregates fed into the components
- `pitches_last_7 = sum(pitches_thrown)` over `logs_7`.
- `innings_last_7 = sum(innings_pitched)` over `logs_7`.
- `appearances_7 = len(logs_7)`, `appearances_14 = len(logs_14)`.
- `avg_leverage = mean(leverage_index for logs_7 with non-null LI)`; if none → `1.0`.

### Component weights (`WEIGHTS`)
| Component | Weight |
| --- | --- |
| pitch_count | 0.30 |
| rest_days   | 0.25 |
| appearances | 0.20 |
| leverage    | 0.15 |
| innings     | 0.10 |

### Scoring curves

**`score_pitch_count(pitches_last_7)` — `PITCH_THRESHOLDS = {max_fresh: 0, moderate: 50, high: 90, critical: 120}`**
- `<= 0` → 0.
- `>= 120` → 100.
- `90 ≤ p < 120` → linearly interpolated 50 → 100.
- `50 ≤ p < 90` → linearly interpolated 0 → 50.
- `0 < p < 50` → `(p / 50) * 25` (so a 49-pitch outing maps to ~24).

**`score_rest_days(days_since_last)` — discrete table**
- `None` or `>= 5` → 0.
- 4 → 10, 3 → 30, 2 → 55, 1 → 80, 0 → 100.

**`score_appearances(apps_7, apps_14)` — `APPEARANCE_THRESHOLDS = {max_fresh: 0, moderate: 2, high: 4, critical: 5}`**
- Inputs are blended: `weighted = apps_7 * 0.7 + apps_14 * 0.15`.
- `weighted <= 0` → 0; `>= 5` → 100.
- `4 ≤ weighted < 5` → 60 → 100 (linear).
- `2 ≤ weighted < 4` → 0 → 60 (linear).
- `< 2` → `weighted * 15`.

**`score_leverage(avg_leverage)` — discrete buckets**
- `None` → 20 (neutral default).
- `>= 2.5` → 100. `>= 2.0` → 80. `>= 1.5` → 60. `>= 1.0` → 40. else → 15.

**`score_innings(innings_last_7)` — three-band linear**
- `<= 0` → 0. `>= 6.0` → 100.
- `4.0 ≤ ip < 6.0` → 50 → 100 (linear).
- `0 < ip < 4.0` → `(ip / 4.0) * 50`.

### Composite + risk tiers

```
raw = pc*0.30 + rest*0.25 + apps*0.20 + lev*0.15 + inn*0.10
raw = clamp(raw, 0, 100)
```

Risk tiers via `RISK_LEVELS = [(25, 'LOW'), (50, 'MODERATE'), (81, 'HIGH'), (101, 'CRITICAL')]`:
- `score < 25`  → LOW
- `25 ≤ score < 50` → MODERATE
- `50 ≤ score < 81` → HIGH
- `>= 81`       → CRITICAL

Note the `Portfolio.fatigue_engine.risk_tiers` JSON labels these as `0–25 / 26–50 / 51–75 / 76–100`, which is inconsistent with the implementation (51–80 HIGH, 81+ CRITICAL).

### `reference_date` behavior
- Live mode (sync, manual recalculate via `recalculate_all_fatigue(use_last_game_date=False)`): `ref = today`. Pitchers with no recent games naturally get a `LOW`/0 score.
- Historical mode (seed.py, recalculate_fatigue.py, POST `/api/bullpen/fatigue/recalculate`, daily APScheduler): `ref = pitcher.last_game_date`. This is what makes 2024–2025 data produce meaningful end-of-season scores instead of months-of-rest-induced zeroes. The 14-day pre-window is taken relative to that reference.

`recalculate_all_fatigue(pitchers_with_logs)` in `fatigue.py` is a separate batch helper (only takes a list of `(pitcher, logs)` tuples) and is not currently used; the live recalculation path lives in `services.sync.recalculate_all_fatigue`.

## 7. Services

### `services/mlb_api.py`
Singleton `mlb_client = MLBApiClient()` wrapping `https://statsapi.mlb.com/api/v1`. Uses a `requests.Session` with a `BaseballOS/1.0` User-Agent and a 10s timeout. All errors are caught in `_get` and surfaced as `None` (with a `print` to stdout — not a logger). Methods:
- `get_all_teams(sport_id=1)` → list of MLB teams.
- `get_team_roster(team_id, roster_type='pitchers')` — `roster_type` can be `'allRoster'`, `'pitchers'`, `'active'`, or `'40Man'`. (The seeder calls it with `'40Man'`.)
- `get_pitcher_game_logs(player_id, season=None)` → list of game-log split objects.
- `get_player_info(player_id)` → first person object.
- `get_pitching_stats(player_id, season, stat_type)` — aggregate season/career/lastXGames/yearByYear.
- `get_schedule`, `get_recent_schedule(days_back=14)`, `get_game_boxscore(game_pk)`, `get_game_pitching_lines(game_pk)` — schedule + boxscore helpers; the boxscore parser extracts pitcher lines from both home and away sides.
- `get_minor_league_teams()` (sportIds 11,12,13,14,16) and `get_prospect_stats(player_id, season)` — minor-league helpers, currently unused by the rest of the codebase.
- `search_player(name)` — multi-sport name search.

### `services/fatigue.py`
See section 6. Exposes `score_pitch_count`, `score_rest_days`, `score_appearances`, `score_leverage`, `score_innings`, `get_risk_level(score)`, `calculate_fatigue(pitcher, logs, reference_date=None)`, and the (unused) `recalculate_all_fatigue(pitchers_with_logs)`.

### `services/sync.py`
Shared sync logic used by both the manual POST endpoint and the APScheduler daily job. Pure DB + MLB API — no Flask request objects, so callers must hold an app context.
- `STATUS_FILE = backend/logs/sync_status.json`.
- `_season_for(ref)` — returns the calendar year (treats Feb–Nov MLB season as a single calendar year).
- `sync_recent_logs(days_back=7, reference_date=None)` — for every active pitcher pulls `get_pitcher_game_logs(pitcher.mlb_id, season=ref.year)`, filters to dates `>= ref - days_back`, deduplicates on `(pitcher_id, mlb_game_pk)`, and inserts a `GameLog` (now correctly captures `game_type` from `game.gameType`). Commits at the end. Returns `{ new_logs_added, pitchers_touched, errors, days_back, season, cutoff }`.
- `recalculate_all_fatigue(use_last_game_date=True)` — for every active pitcher, picks `reference_date = latest_log.game_date` if `use_last_game_date` else `today`, pulls a 14-day window, calls `calculate_fatigue`, persists the score. Returns count.
- `run_daily_sync(app, days_back=7)` — top-level entry called by APScheduler at 06:00 ET. Ensures `logs/`, attaches a `FileHandler` to `baseballos.daily_sync`, runs sync + recalc inside `app.app_context()`, writes `sync_status.json` (`{ last_sync, status, pitchers_updated, new_logs_added, errors, message, finished_at }`), handles "no_games" offseason path, and detaches the file handler at the end. Wrapped in try/except so a failure produces `status='error'` instead of crashing the scheduler.
- `read_status()` — returns the parsed status file or a `'never'` sentinel.

### `services/prospects.py`
**Not present on disk.** README references it but the file does not exist. All prospect logic currently lives in `api/prospects.py` and the seed script.

## 8. Frontend — Component Map

### `App.jsx`
Wraps the app in `BrowserRouter`, renders the persistent `Sidebar`, and routes `/` → `Dashboard`, `/bullpen` → `Bullpen`, `/prospects` → `Prospects`, `/portfolio` → `Portfolio`.

### `Sidebar.jsx`
Sticky 224px (`w-56`) left rail. Hardcoded NAV array of `{ to, icon, label }` mapped to `NavLink`s with an `active` class. Footer shows "Nikko · Army Vet · Developer · Building to break in.".

### Dashboard

**`dashboard/Dashboard.jsx`**
- Calls: `GET /api/bullpen/stats/overview`, `GET /api/bullpen/fatigue?limit=8&risk_level=`, `GET /api/prospects/stats/overview`.
- Renders: hero (BASEBALLOS title, `SeasonBanner` hardcoded to `season='2024'` + `isLive=false`, `SyncStatus` pill), 4 `StatCard`s (Active Pitchers / Game Logs / Avg Fatigue / Critical-High split), risk-distribution stacked bar, "Most Fatigued" preview table (links to `/bullpen`), "Pipeline Snapshot" with level tiles and a top-5 list (links to `/prospects`), three quick-link cards.
- Issue: the overview's `avg_fatigue_score` is computed across all rows of `fatigue_scores` (see backend section 4), so this number drifts upward each time recalc is run.

**`dashboard/SeasonBanner.jsx`**
- Pure presentational pill: pulsing green dot + "Live — {season} Season" if `isLive`, otherwise static amber dot + "{season} End-of-Season Snapshot".
- Props: `season` (default `'2024'`), `isLive` (default `false`).

**`dashboard/SyncStatus.jsx`**
- Calls: `getSyncStatus()` → `GET /api/bullpen/sync/status`.
- Loading / error / never-synced sentinels render dimmed pills. Computes `ageHours = (now - last_sync) / 3.6e6`; flags `> 36h` as "stale" (amber) and `status === 'error'` as red. Optional `pitchers_updated` count appended.

### Bullpen

**`bullpen/Bullpen.jsx`**
- Calls: `getTeams()`, plus either `getTeamBullpen(team_id)` (when a team is selected; rows mapped to `{ ...fatigue, pitcher }` and filtered for non-null `raw_score`) or `getFatigueScores({ limit: 200 })`. Recalculate button hits `recalculateFatigue()` (POST).
- Local UI state: `viewMode` (`pitchers | teams`), `selectedTeam`, `riskFilter` (`ALL/CRITICAL/HIGH/MODERATE/LOW`), `selectedPitcher`, `recalcing`, `sortBy` (`score | name | rest | pitches`).
- Renders the top toolbar (view-mode toggle + Recalculate), dispatches to `<TeamComparison />` or the inner `<PitcherView />` (team pills, risk filter tabs with counts, sortable scores table; clicking a row toggles the `<PitcherDetail />` side panel).

**`bullpen/PitcherDetail.jsx`**
- Calls: `getPitcherFatigue(pitcherId)` → `GET /api/bullpen/fatigue/<pitcher_id>`.
- Props: `pitcherId`, `onClose`.
- Renders header (team / name / position / throws / age / jersey), big composite score + `RiskBadge`, `FatigueBar`, 6-tile quick stats grid, weighted component breakdown bars, Recharts radar of the 5 components, Recharts line chart of `fatigue_trend` (with `CRITICAL` ReferenceLine at y=81), and a recent-appearances table that detects spring-training games (`game_type === 'S'` or opponent === `'SIM'`/`'Simulated'`) and tags high-leverage outings (LI > 1.5).
- Issue: trend chart and recent-logs come from server-side queries that anchor on `date.today()`, so they are typically empty against historical seed data.

**`bullpen/TeamComparison.jsx`**
- Calls: `getTeams()`, then in parallel `getTeamBullpen(team_id)` for every team (Promise.all) — 30 concurrent backend calls per refresh.
- Per team computes `avg_score`, per-tier counts, `avg_tier` via a local `scoreToTier` helper (matches backend thresholds).
- Sortable columns: Team, Avg Fatigue, CRITICAL/HIGH/MODERATE/LOW counts. Inline-styled risk colors so Tailwind purge doesn't drop them. Per-row error message if a team request failed.

### Prospects

**`prospects/Prospects.jsx`**
- Calls: `getProspectPipeline()` and `getProspects({ limit: 200 })`.
- Local state: `selectedLevel`, `selectedProspect`, `viewMode` (`pipeline | list`).
- Renders: 6-level selector grid (with counts), then either a per-level pipeline board (top 8 cards per level) or a flat grid for the active level / list mode. Internal `ProspectMiniCard` component renders compact cards with overall grade + level + position-aware stat chips; clicking opens the side `<ProspectCard />`.

**`prospects/ProspectCard.jsx`**
- Pure presentational; takes `prospect` + `onClose`. Header (team/name/identity), big level tile + ETA pill + overall grade, scouting-grade row (5 grades for hitters, 3 for pitchers), 6 or 8 stat tiles (positional vs pitcher), optional Scout Notes block.

### Portfolio

**`portfolio/Portfolio.jsx`**
- Calls: `getPortfolio()` → `GET /api/portfolio/`.
- Renders hero with name/title/background bullets/mission, stack pills, Project cards with status badges, fatigue methodology table + 4-tile risk-tier grid, and contact buttons (GitHub / LinkedIn / mailto).

## 9. Shared UI Components

Located in `frontend/src/components/UI/`, re-exported via `UI/index.js`.

### `LoadingPane`
- Props: `message?: string`, `label?: string` (legacy alias). Falls back to `'Loading...'`.
- Renders a pulsing baseball-diamond SVG (rotated 45°, with circles for the bases and a smaller mound dot), the message in mono uppercase, and three staggered amber dots underneath.
- Used in: `Dashboard` (overview, top-fatigue, pipeline panes), `Bullpen` (scores table), `PitcherDetail`, `TeamComparison`, `Prospects`, `Portfolio`.

### `ErrorState`
- Props: `message`, `onRetry?` (optional callback). Renders a red-tinted card with an alert icon, `message` body text, and an optional "Try Again" button when `onRetry` is provided.
- Used everywhere `useFetch` is used: `Dashboard`, `Bullpen`, `PitcherDetail`, `TeamComparison`, `Prospects`, `Portfolio`.

### `SectionHeader`
- Props: `title`, `subtitle?`, `action?` (right-aligned ReactNode).
- Renders a bold uppercase Bebas-Neue title, an optional mono subtitle, and an action slot. Bottom border + bottom margin.
- Used by: `Bullpen`, `Prospects`, `Portfolio`.

### `Divider`
- Props: `label?`, `variant?: 'solid' | 'dashed'` (default solid).
- With no `label`, just a horizontal rule. With a `label`, renders the label centered between two lines, in mono uppercase.
- Used by: `Bullpen`, `PitcherDetail` (Score Breakdown / Fatigue Profile / Fatigue Trend / Recent Appearances), `Prospects` (imported), `ProspectCard` (Current Season Stats / Scout Notes), `Portfolio` (Risk Tiers).

### Other shared primitives
- `EmptyState({ icon='⚾', title, subtitle })` — empty list placeholder.
- `Spinner({ size='md' })` — small/medium/large CSS spinner.
- `FatigueBar({ score, showLabel?, height='h-1.5' })` — color from `fatigueBarColor` (≥76 red, ≥51 orange, ≥26 amber, else emerald).
- `RiskBadge({ level })` — `●`/`○` filled-dot count + level label, classed via `badge-low/moderate/high/critical`.
- `StatCard({ label, value, sub?, accent?, delay?, icon? })` — animated dashboard tile.
- `GradeBox({ grade, label })` — 20-80 grade tile, color-coded (≥70 amber, ≥60 emerald, ≥50 chalk, else dim).

## 10. Data State

`backend/logs/sync_status.json` does **not exist** in the working tree (the `logs/` directory is gitignored and is created by `app.py` at runtime; the status file is only written after the daily APScheduler job runs at least once, or after a successful manual sync). So nothing about the most recent live sync can be read from disk in the current state. What can be inferred from code:

- **Pitchers seeded**: `seed.py` walks all 30 MLB team IDs (`108–147, 158`) and inserts every player on the `40Man` roster whose position is `P`, `SP`, `RP`, or `CL`. Exact count is non-deterministic (depends on roster size at seed time) but typically lands in the 400–500 range across MLB.
- **Game logs**: `seed.py` pulls the full season game log for each pitcher for both `2024` and `2025`. With ~400 pitchers and 50–70 appearances each across the two seasons, the table is typically tens of thousands of rows.
- **Seasons covered**: `HISTORICAL_SEASONS = [2024, 2025]`. `services/sync.sync_recent_logs` always uses the calendar year of `reference_date` (so a sync run today on 2026-04-29 would attempt to pull season=2026, regardless of whether MLB has data for it yet).
- **Last sync**: unknown — no `sync_status.json` exists, and the `AUTO_SYNC` env var must be `1/true/yes` for the scheduler to even register. The frontend will render "Never synced" until at least one run completes.
- **Risk distribution**: not derivable from code alone — depends on the seeded roster + the last-game-date scoring window. `seed.py` and `recalculate_fatigue.py` print a `LOW / MODERATE / HIGH / CRITICAL` summary at the end of their runs, but nothing is persisted in this repo to read it back.

## 11. What Is Working

- Backend boots via `flask run`, exposes `/api/health` and registers all three blueprints with CORS open for `localhost:5173/3000`.
- Alembic migrations are present and create all four tables, plus the indexes / `game_type` column from migration `018704c8d5fe`.
- `MLBApiClient` covers every endpoint the seeder + sync need (teams, rosters, person info, game logs).
- `seed.py` end-to-end: roster pull → pitcher upsert → 2024+2025 game-log pull → fatigue scoring → curated 10-prospect insert.
- `recalculate_fatigue.py` CLI script and `POST /api/bullpen/fatigue/recalculate` both score against each pitcher's last game date so historical data produces meaningful scores.
- `services/sync.py` is the single source of truth for live sync + recalc; the manual POST and the `AUTO_SYNC=true` daily APScheduler job both go through it.
- Daily scheduler is wired correctly: only starts when `AUTO_SYNC=true`, only in the Werkzeug child process under debug, runs at 06:00 ET, has a 1h misfire grace, and writes a status file the dashboard pill reads.
- All Bullpen endpoints return clean joined data (notably the team-bullpen LEFT-JOIN avoids N+1).
- Prospects endpoints (list / detail / by-team / pipeline / compare / overview) all read from the seeded `prospects` table.
- `GET /api/portfolio/` returns a fully populated hand-authored payload that the Portfolio page renders.
- Frontend routing, Tailwind palette, custom utilities (`.card`, `.data-table`, `.badge-*`, `.nav-item`, `bg-noise`, `bg-stadium-glow`), and the shared UI primitives all render and animate correctly.
- Dashboard hero, overview stat cards, risk distribution stacked bar, top-fatigue preview, pipeline snapshot, sync-status pill, and quick links all wire to real backend data.
- Bullpen Pitchers view: team filter pills, risk-level tabs with live counts, sortable columns (score/name/rest/pitches), fatigue bar visualization, side detail panel.
- PitcherDetail: weighted breakdown bars, Recharts radar of components, Recharts line chart of trend, recent-appearances table with spring-training badge + high-leverage tag.
- Bullpen Team Rankings: parallel 30-team fan-out, sortable per-tier counts, inline-styled colors that survive Tailwind purge.
- Prospects pipeline view: 6-level selector tiles with counts, per-level board, list mode, side `ProspectCard` detail.
- Portfolio page renders the full methodology section and contact links.

## 12. What Is Stubbed or Incomplete

- **`backend/services/prospects.py`** — referenced in README's project structure, not present on disk. No prospect analytics service layer exists; everything is a direct query from the blueprint.
- **`leverage_index` and `inherited_runners` columns** — present on `game_logs`, never populated. MLB Stats API doesn't return LI in the standard `gameLog` payload, so `score_leverage` always defaults its avg to 1.0 → constant 40 sub-score across the entire dataset. The "Leverage Index" component is effectively a constant in production.
- **`SeasonBanner`** — hardcoded to `season='2024'` and `isLive={false}` in `Dashboard.jsx`. There's no logic that derives the active season from the data.
- **MLB prospect ingestion** — `MLBApiClient.get_minor_league_teams()`, `get_prospect_stats()`, and `search_player()` exist but are never called. Prospects come from a 10-row hand-authored list in `seed.py`; nothing pulls live minor-league data.
- **`PitcherDetail.recent_logs` / `fatigue_trend`** — the endpoint anchors both queries on `date.today()`, so they return empty arrays against the historical 2024–2025 seed data. The radar still renders (uses the latest `current_fatigue`), but the trend line and recent-appearances table will be empty until the sync starts pulling current games.
- **`avg_fatigue_score`** in `/bullpen/stats/overview` averages every row in `fatigue_scores`, including stale recalculations. It is not the average of the latest score per pitcher.
- **`sync_status.json`** — only created after a sync runs. On a fresh checkout the dashboard pill says "Never synced" until either `POST /api/bullpen/sync` succeeds or the scheduler runs once.
- **AUTO_SYNC scheduler** — disabled by default; needs `AUTO_SYNC=true` plus a long-running Flask process to ever fire. There's no notion of season-awareness besides the calendar year.
- **`/api/bullpen/sync` recalculation** — uses `use_last_game_date=False` (today as ref). The daily job uses `use_last_game_date=True`. So the manual button and the scheduled job produce different scores for the same data — the manual one will return zeroes off-season.
- **No tests** — `requirements.txt` does not include pytest; no `tests/` directory exists.
- **No CI / lint / type-checking config** — neither backend nor frontend.
- **No `.env.example`** — `docs/SETUP.md` says `cp .env.example .env`, but the example file isn't checked in.
- **Prospects "compare"** — endpoint exists but no frontend UI exposes it.
- **Health endpoint** — exposed but never called from the frontend.

## 13. Known Bugs and Issues

- **Risk-tier label drift between code and copy.** `services/fatigue.py` defines `HIGH = 51–80`, `CRITICAL = 81+`, but `api/portfolio.py` advertises `HIGH = 51–75`, `CRITICAL = 76–100`. `frontend/src/utils/formatters.js::fatigueBarColor` uses the portfolio thresholds (76 → red, 51 → orange). `Bullpen TeamComparison.scoreToTier` uses the code thresholds (≤80 HIGH). Pick one and unify.
- **`/api/bullpen/stats/overview.avg_fatigue_score` averages all `fatigue_scores` rows.** Each recalculation appends new rows, so the displayed average drifts over time. Fix: compute the average over the same `MAX(calculated_at)`-per-pitcher subquery used elsewhere.
- **`PitcherDetail` historical anchor mismatch.** `GET /api/bullpen/fatigue/<pitcher_id>` filters `recent_logs` and `fatigue_trend` by `date.today() - N days` while the score itself was generated against a 2024/2025 reference date. Anchor those queries on `latest_log.game_date` (or expose a `reference_date` query param).
- **`/api/bullpen/sync` uses live-mode recalc.** During spring training or off-season this overwrites the carefully-built historical scores with all zeros. Should pass `use_last_game_date=True`, or at least branch on whether new logs were pulled.
- **`sync_recent_logs` always queries `season = ref.year`.** In early February or late November this can miss live games whose season differs from the calendar year. Consider using the schedule endpoint to discover active seasons.
- **`MLBApiClient._get` swallows errors with `print()`.** Errors during seeding/sync go to stdout instead of `current_app.logger`; under gunicorn they'll be lost.
- **`POST /api/bullpen/fatigue/recalculate` is unauthenticated.** A public POST that O(N) writes one row per active pitcher; trivially abusable in production.
- **Seed `seed_fatigue_scores` ignores its `reference_date` argument.** The dedicated CLI `recalculate_fatigue.py` does the right thing, but the version inside `seed.py` only passes the logs and not a reference date — so on first run, fatigue is scored against today, not the last game date. The CLI must be re-run after seeding for historical scores. (Compare the two functions.)
- **`Bullpen.PitcherView.handleRecalculate` does no error handling.** Silent failure if the POST 500s.
- **`TeamComparison` fans out 30 parallel requests with no debouncing.** The Refresh button can hammer the backend; should at least disable while loading.
- **`useFetch` deps lint disable.** Hook re-runs whenever `fetchFn` identity changes, which it does every render unless callers wrap in `useCallback`. Most callers pass arrow functions, so each render rebuilds them — `useFetch` only re-runs because `deps` is `[]` by default. Subtle and could bite later.
- **CORS hard-codes `localhost:5173` and `:3000`.** No production origin support.
- **`config.py` ships a real-looking default `DATABASE_URL`** that includes `password` as the password — could mislead a user into committing a working URL.
- **No upper bound on `limit` query params** (`/bullpen/fatigue?limit=`, `/prospects/?limit=`). Trivial DoS vector.
- **Front-end `Portfolio` route is unauthenticated and returns personal contact info** — fine for a portfolio site, just worth flagging.

## 14. Environment and Run Instructions

Prerequisites: Python 3.10+, Node.js 18+, PostgreSQL 14+, npm 9+, pip.

### One-time setup (Windows PowerShell or cmd)

```bat
:: 1. Create the database
psql -U postgres
CREATE DATABASE baseballos;
\q

:: 2. Backend env + dependencies
cd D:\Programming\baseballos\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

:: 3. Create backend\.env (no .env.example is checked in — write it by hand)
::    DATABASE_URL=postgresql://postgres:YOURPW@localhost/baseballos
::    FLASK_APP=app.py
::    FLASK_ENV=development
::    SECRET_KEY=dev-secret
::    MLB_API_BASE=https://statsapi.mlb.com/api/v1
::    AUTO_SYNC=false      :: set to true only if you want the 06:00 ET daily job

:: 4. Run migrations
flask db upgrade

:: 5. Seed initial data (pulls 30 rosters + 2024+2025 game logs from MLB API — slow)
python seed.py

:: 6. Generate proper end-of-season fatigue scores
python recalculate_fatigue.py
```

### Running the app (two terminals)

Terminal 1 — backend:
```bat
cd D:\Programming\baseballos\backend
venv\Scripts\activate
flask run
:: Backend on http://localhost:5000
```

Terminal 2 — frontend:
```bat
cd D:\Programming\baseballos\frontend
npm install      :: only first time
npm run dev
:: Frontend on http://localhost:5173 (Vite proxies /api to :5000)
```

Open `http://localhost:5173` in a browser.

### Tips
- If port 5000 is taken: `flask run --port 5001` and update `vite.config.js` proxy target.
- To re-seed only fatigue scores: `python recalculate_fatigue.py`.
- To force a live sync: `curl -X POST http://localhost:5000/api/bullpen/sync -H "Content-Type: application/json" -d "{\"days_back\": 7}"`.
- To enable the daily scheduler: set `AUTO_SYNC=true` in `.env` and run `flask run`.

## 15. Next Priorities

1. **Unify risk-tier thresholds** across `services/fatigue.py`, `api/portfolio.py`, `frontend/src/utils/formatters.js::fatigueBarColor`, and `frontend/src/components/bullpen/TeamComparison.jsx::scoreToTier`. Pick one canonical breakdown and have the others read from it (consider exposing tiers via the API rather than hard-coding in the UI).
2. **Fix `avg_fatigue_score`** in `/bullpen/stats/overview` to average only the latest score per pitcher (use the same `MAX(calculated_at)` subquery already in the file).
3. **Fix the historical anchor mismatch in `GET /api/bullpen/fatigue/<id>`** so `recent_logs` and `fatigue_trend` use `latest_log.game_date` (or a `?reference_date=` param). The detail panel currently shows blank charts on seed data.
4. **Switch `POST /api/bullpen/sync`'s recalc to `use_last_game_date=True`** (or branch by whether games were pulled) so the manual button doesn't wipe historical scores during the off-season.
5. **Stop persisting one row per pitcher per recalc** — either upsert the latest score or add a cleanup pass; otherwise `fatigue_scores` grows without bound and skews any unfiltered aggregate.
6. **Drive `SeasonBanner` from data** rather than hardcoded `'2024'/false`. Derive the active season from `MAX(game_logs.game_date).year` or from the latest sync status.
7. **Wire real LI / inherited-runners data** by parsing boxscores (`MLBApiClient.get_game_pitching_lines` already exists) — without this, the leverage component is a constant 40.
8. **Build out `services/prospects.py`** and switch `seed.py` to pull live minor-league prospect data instead of the 10 hand-authored rows. Even an MLB Pipeline scrape job would be more representative than the current sample.
9. **Add a rate-limit / cap on `limit=` query params** and lock down `POST /api/bullpen/fatigue/recalculate` (admin token, IP allow-list, or move it to a CLI-only path).
10. **Add `.env.example`, a `tests/` skeleton with a few high-value pytest cases for the fatigue scoring curves**, and at least one CI workflow that runs `flask db upgrade` against an ephemeral Postgres + the test suite.
11. **Replace `print()` in `MLBApiClient._get` with `current_app.logger`**, and route `seed.py`/`sync.py` warnings into the same logger so production logs are coherent.
12. **Unify the manual recalculate button behavior with the daily job** — surface the result of `services.sync.recalculate_all_fatigue` in the response (current button just refetches the table afterward).
13. **Make the dashboard's Most Fatigued / Pipeline Snapshot panes refresh after a recalc** by lifting the relevant `useFetch` results into a context (or having the Recalculate button broadcast an event).

