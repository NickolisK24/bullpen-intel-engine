# BaseballOS

BaseballOS is a public MLB bullpen intelligence platform that explains which
bullpens are fresh, stretched, or vulnerable — and why.

It reads public MLB workload, availability, and late-game context, then presents
a daily descriptive view of bullpen state with visible freshness, data dates,
and confidence context.
BaseballOS is trust-first by design: it explains what it sees, shows how current
the data is, and states what it cannot know.

BaseballOS is an independent project and is not affiliated with or endorsed by
Major League Baseball or its clubs.

## Project Overview

Bullpen context is hard to see in one place. A box score can tell you who
pitched and for how long, but it does not clearly show how recent workload,
rest, availability, and late-inning flexibility fit together heading into
tonight.

BaseballOS pulls that context into one readable product surface. It focuses on:

- Public MLB bullpen intelligence.
- Workload, availability, and late-game context.
- Fresh, stretched, and vulnerable bullpen reads.
- Data dates and confidence context.
- Freshness and data transparency.
- Descriptive language instead of predictions or advice.

## What BaseballOS Does

- Tracks recent bullpen usage and rest across MLB teams.
- Shows which relievers are available, on watch, limited, or unavailable based
  on public workload and roster context.
- Summarizes league-wide bullpen state through daily reads such as Most
  Available, On Watch, and Most Stretched.
- Explains team bullpen boards with availability groups, workload context,
  roster context, and freshness indicators.
- Surfaces daily bullpen storylines without ranking pitchers or forecasting
  outcomes.
- Documents how reads are built through Methodology and Data & Trust pages.

## What BaseballOS Does Not Do

BaseballOS is descriptive by design. It does not:

- Give picks or tell anyone who to use.
- Predict game outcomes, saves, injuries, or manager decisions.
- Provide betting advice or odds analysis.
- Make private injury claims. The absence of a public flag is not a health
  claim.
- Claim certainty about manager intent, bullpen phones, or final game-day
  choices.
- Present private calculations as product certainty.

## Current Product Surfaces

| Surface | Route | Purpose |
| --- | --- | --- |
| Today | `/` | Daily front door: tonight's bullpen watch, a quick league teaser that hands off to the Dashboard, and learning links. |
| Dashboard | `/dashboard` | The full league bullpen board: the landscape lanes, one league state read, and roster availability context. |
| Bullpen | `/bullpen` | Team bullpen board, two-team comparison, and the all-pitchers reference table for team-specific reads. |
| Stories | `/stories` | Browseable bullpen intelligence feed for the day's storylines and league context. |
| Methodology | `/methodology` | Explanation of how BaseballOS builds its public bullpen reads. |
| Data & Trust | `/trust` | Freshness, data coverage, provenance, and trust limitations. |
| About | `/about` | Product-first explanation of why BaseballOS exists. |
| How to Read | `/how-to-read` | One-line definitions for recurring BaseballOS terms. |

## Core Terminology

### Arm Availability

- **Available**: rested enough to pitch today.
- **On Watch**: usable, but recent work is worth watching.
- **Limited**: available only in a reduced role after recent work.
- **Unavailable**: not available today because of rest or roster status.

### Bullpen Reads

- **Bullpen Pressure**: how much workload strain the bullpen is carrying today.
- **Recovery Window**: how much clean rest the bullpen has available.
- **Workload Concentration**: whether recent work is spread around or clustered
  on a few arms.
- **Clean Options**: how many arms enter today without major recent workload
  restriction.
- **Coverage Safety**: whether the bullpen can cover the late innings if the
  game runs long.
- **Trusted Arms**: the rested, unrestricted arms a manager can lean on late.

The canonical public dictionary lives in
`frontend/src/utils/bullpenConcepts.js`, and the canonical public boundary
language (descriptive-not-predictive, no betting advice, manager decisions
unknown) lives in `frontend/src/utils/publicBoundaries.js`. About, How to
Read, and Methodology render from those modules rather than keeping their own
copies.

### Team State

- **Fresh**: the bullpen comes in mostly rested, with room to maneuver late.
- **Stretched**: the bullpen is thin on rested arms after recent work.
- **Vulnerable**: little late-inning margin remains if the game runs long.

## Data Freshness And Trust Posture

BaseballOS is built to be checkable. Product surfaces separate the baseball
date represented in the read from the time BaseballOS last wrote new data.

Key trust rules:

- Data freshness is visible to users.
- Stale, missing, or delayed data should fail closed instead of implying a
  current live read.
- Sample or non-live states must not look like current MLB-backed data.
- Reads are descriptive and evidence-backed, not predictive.
- Public roster flags are not private medical information.
- BaseballOS cannot know manager intent or final game-day usage decisions.

The production sync path is:

```text
team assignment sync
-> roster status sync
-> game log and workload sync
-> availability calculation
-> trust and freshness reporting
-> dashboard snapshot build
-> static team story preview export
```

## Tech Stack

| Layer | Technology / location |
| --- | --- |
| Frontend | React, Vite, TailwindCSS |
| Backend | Flask, Python |
| Database | PostgreSQL |
| Data source | Public MLB Stats API data |
| Hosted frontend | Vercel static build |
| Hosted backend | Render Flask service |
| Scheduled sync | GitHub Actions calling protected backend endpoints |

Daily sync is driven externally by `.github/workflows/baseballos-sync.yml`.
Health checks do not perform sync. Protected write endpoints require the
configured admin token in production.

## Local Development

Prerequisites:

- Python 3.10+
- Node.js 18+
- npm 9+
- PostgreSQL 14+

Backend:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env so DATABASE_URL points at your local PostgreSQL database.
flask db upgrade
python seed.py
flask run
```

Frontend, in a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend dev server proxies API calls to the backend during local
development. See [docs/current/SETUP.md](docs/current/SETUP.md) for full local
setup, deployment, environment variable, and scheduled sync details.

## Environment Variables

Backend:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Explicit database connection string. Local development must use a local database. |
| `FLASK_APP` | Flask CLI entry point, usually `app.py`. |
| `APP_ENV` | Runtime environment; use `production` for hosted production. |
| `SECRET_KEY` | Flask secret key; must be non-default in production. |
| `MLB_API_BASE` | Optional MLB Stats API base URL override. |
| `AUTO_SYNC` | Enables the local in-process scheduler when set to a true-like value. |
| `ADMIN_API_TOKEN` | Gates protected operational endpoints. |
| `EMAIL_PROVIDER` / `EMAIL_API_KEY` / `EMAIL_FROM` | Optional transactional email config. Missing provider config does not block audience signup persistence; welcome email is skipped safely. |

Frontend:

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Backend origin when hosted separately. |
| `VITE_SENTRY_DSN` | Optional Sentry DSN for production/staging frontend error monitoring. Missing config is a safe no-op. |
| `VITE_APP_ENV` | Optional frontend environment label for error monitoring (`production`, `staging`, `preview`, or local defaults). |
| `VITE_RELEASE_SHA` | Optional release identifier attached to captured frontend errors. |

The frontend has no admin token. Privileged operational endpoints are gated by
the backend `ADMIN_API_TOKEN` and are triggered server-side or with manual
operational commands, never from the browser.

## Tests

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

README-only documentation edits do not require the full frontend or backend
test suite unless implementation files also change. Use `git diff --check` for
whitespace validation.

## Current Roadmap Direction

### V3: Product Credibility Pass

V3 focuses on making BaseballOS clearer, more trustworthy, and easier for a
first-time reader to understand. The pass includes public terminology cleanup,
live-data trust guardrails, Today page hierarchy, footer and onboarding pages,
and clearer product boundaries.

### Future Direction

Future work is expected to build toward:

- Daily bullpen intelligence with clearer pregame context.
- Upcoming games with bullpen context once the slate source is reliable.
- Bullpen usage paths and coverage routes as future product direction, not a
  current feature.
- Continued freshness, provenance, and trust improvements.

## Documentation Entry Points

- [Documentation Index](docs/README.md)
- [Setup Guide](docs/current/SETUP.md)
- [Current Roadmap](docs/current/ROADMAP.md)
- [V4 Foundation Integrity & Bullpen Evidence Roadmap](docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md)
- [Product Vision Specification](docs/product/product-vision-specification.md)
- [Product Credibility Pass Completion Audit](docs/audits/product-credibility-pass-completion.md)
- [Data Freshness Validation Summary](backend/reports/data_freshness_validation_summary.md)

Historical phase records remain under [docs/archive/2026-06/](docs/archive/2026-06/).

## Authorship And Contribution Note

BaseballOS is built and maintained by **Nickolis Kacludis**
([NickolisK24](https://github.com/NickolisK24)).
