# BaseballOS

BaseballOS is a public MLB **bullpen intelligence** platform.

It answers a narrow question well:

> **What is happening inside every MLB bullpen right now, and why?**

BaseballOS turns public workload, roster, schedule, and appearance data into
evidence-backed bullpen context. The product describes the observable present;
it does not predict outcomes, infer private health, guess manager intent, or
turn bullpen state into betting or fantasy advice.

**Trust is the foundation. Intelligence is the product. Understanding is the outcome.**

BaseballOS is an independent project and is not affiliated with or endorsed by
Major League Baseball or its clubs.

## Why BaseballOS Exists

Bullpen information is fragmented. A box score can tell you who pitched, a
roster page can tell you who is active, and a schedule can tell you when the
next game starts. None of those sources alone explains what the current bullpen
picture means.

BaseballOS assembles those facts into a checkable read:

```text
authoritative source
-> canonical baseball record
-> deterministic derivation
-> evidence
-> public read
-> trusted publication
-> permanent memory
```

A useful BaseballOS read should leave a reader thinking:

> “I did not know that — and I can see why it is true.”

## Public Product Contract

### Team State

The public Team State vocabulary is exactly:

- **Fresh** — comparatively stronger rested coverage and operating room.
- **Stretched** — recent workload or coverage has narrowed the bullpen's clean options.
- **Vulnerable** — the current operating picture is materially constrained with limited margin if more work is required.

There is no fourth Team State. Unsupported or data-limited reads fail closed
instead of receiving a softer label.

### Arm reads

The current public arm-read vocabulary is:

- **Clean Option**
- **Watch Arm**
- **Limited Rest**
- **Unavailable**
- **Limited Read**

Internal availability states remain implementation detail. Public labels are
backend-owned and descriptive; they are not instructions to a manager or a
fantasy player.

### Public roles

Role and current workload are separate concepts. Public role labels are:

- **Trusted Arm**
- **Setup Arm**
- **Coverage Arm**
- **Middle Relief Arm**
- **Limited Read**

A Trusted Arm can have Limited Rest. A Coverage Arm can be a Clean Option.
BaseballOS does not collapse role and current workload into one score.

## What BaseballOS Does

- Tracks recent reliever appearances, pitches, outs, rest, and multi-day usage.
- Separates current active-bullpen membership from historical appearance ownership.
- Resolves completed-game starter/reliever identity from official game evidence.
- Builds current team and arm reads from governed, reproducible inputs.
- Shows the evidence and represented baseball date behind public claims.
- Fails closed when source authority, freshness, coverage, or evidence is insufficient.
- Preserves trusted historical publications as immutable Share Artifacts.
- Provides league, team, arm, comparison, narrative, methodology, and trust surfaces.

## What BaseballOS Does Not Do

BaseballOS does not:

- predict game outcomes, saves, blown saves, injuries, or future reliever usage;
- provide betting picks, odds analysis, fantasy advice, or matchup “edges”;
- claim private medical knowledge;
- claim to know manager or pitching-coach intent;
- convert missing information into zero or a plausible fallback;
- lead public surfaces with unexplained composite scores, rankings, or leaderboards.

Silence, limited scope, or a withheld read are valid product states.

## Product Surfaces

| Surface | Route | Primary question |
| --- | --- | --- |
| Today | `/` | What is the bullpen story today, and what deserves attention tonight? |
| Dashboard | `/dashboard` | Across MLB, which bullpens are Fresh, Stretched, or Vulnerable, and where should I look closer? |
| Team Board | `/bullpen` team view | What is this bullpen's current observable state, which arms are carrying it, and why? |
| Compare | `/bullpen` comparison view | How do these two bullpen pictures differ right now? |
| Reliever Finder | `/bullpen` pitcher finder | How do I find a reliever and inspect his current BaseballOS record? |
| Pitcher Detail | current detail route/drawer | What has this reliever recently carried, what is his public read, and what supports it? |
| Stories | `/stories` | Beyond today's lead, which supported bullpen storylines are worth inspecting? |
| Methodology | `/methodology` | How does BaseballOS compute and govern what it shows? |
| Data & Trust | `/trust` | Is the current data complete and current enough for the claim I am reading? |
| Share Artifact | `/share/{public_id}` | What exactly did BaseballOS publish at that time, and what evidence supported it? |

## Trust Model

BaseballOS treats trust as infrastructure rather than a disclaimer.

Core rules:

- **One authority per fact.** Downstream services consume canonical facts instead of inventing local interpretations.
- **Publication is separate from calculation.** A calculated state is not public until its trust gates pass.
- **Freshness is visible.** The baseball date represented is distinct from technical sync time.
- **Unknowns stay unknown.** Missing evidence narrows or suppresses the dependent claim.
- **Historical and live state stay separate.** Published historical meaning is never silently recalculated from current data.
- **Corrections preserve history.** Published artifacts are superseded or withdrawn rather than edited in place.
- **Failure reduces scope.** Independent valid evidence can remain available when another domain fails.

The appearance ledger is publication-critical. If BaseballOS cannot prove that
required completed-game pitching evidence is complete, a new league snapshot is
withheld and the previous trusted snapshot continues to serve with its original
data-through date.

## Current Architecture

| Layer | Technology / responsibility |
| --- | --- |
| Frontend | React, Vite, TailwindCSS — public product surfaces and browser-safe internal views |
| Backend | Python, Flask — APIs, intelligence services, publication, auth boundaries, operational services |
| Persistence | PostgreSQL, SQLAlchemy, Alembic — canonical records, snapshots, artifacts, audits, users |
| Source acquisition | Public MLB Stats API data |
| Scheduled orchestration | GitHub Actions |
| Hosted frontend | Vercel |
| Hosted backend | Render |

The production path currently preserves a deliberate authority boundary:

- the legacy daily/postgame writer remains authoritative for baseball-data mutation;
- game-driven daily and postgame lanes operate in **shadow**;
- backfill is off unless explicitly dispatched for governed historical replay;
- automated game-driven write mode and publication-authority transfer are not approved.

Exact workflow schedules, budgets, and runtime values live in
`.github/workflows/baseballos-sync.yml` and current runbooks rather than this
README.

## Documentation

Start here:

- [Documentation hub](docs/README.md)
- [Canonical document library](docs/canonical/README.md)
- [Repository documentation map](docs/REPOSITORY_DOCUMENTATION_MAP.md)
- [Current roadmap & decision ledger](docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md)
- [Sync pipeline runbook](docs/current/SYNC_PIPELINE.md)
- [Setup guide](docs/current/SETUP.md)
- [Changelog](docs/current/CHANGELOG.md)

The six canonical documents are the durable authority layer. Audits, phase
records, incident reports, implementation plans, and archived material are
evidence — not competing product authorities.

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+
- PostgreSQL 14+
- Git

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt   # runtime deps + pytest; production uses requirements.txt
cp .env.example .env
# Set a local DATABASE_URL and FLASK_APP=app.py
flask db upgrade
python seed.py                    # optional; makes live MLB source calls
flask run
```

Do **not** run `flask db init`; the repository already owns Alembic migration
history.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Production build:

```bash
npm run build
npm run preview
```

The exact environment-variable contract lives in `backend/.env.example` and
`frontend/.env.example`. Production must never deliver an admin token to the
browser.

## Validation

Backend tests:

```bash
python -m pytest backend/tests
```

Frontend tests and production build:

```bash
cd frontend
npm test
npm run build
```

CI uses PostgreSQL-backed backend confidence shards and lockfile-faithful
frontend installation. A green test suite does not replace production smoke,
scheduled-run evidence, or live-source verification when those are part of an
acceptance contract.

## Current Direction

The canonical Roadmap is the only execution authority. The active work remains
trust and production closeout before broader product expansion.

The high-level sequence is:

1. finish the current production reliability / authority evidence;
2. close remaining public credibility contradictions;
3. make trusted intelligence portable through canonical share assets and crawler-visible metadata;
4. resume visible evidence depth such as Active Bullpen ERA and named-arm context;
5. build the stronger daily habit and consequence layer;
6. use the offseason for deeper pitch, leverage, dependency, depth, timeline, and archive work.

For exact current issue order, production evidence, and decisions, use the
[Product Roadmap & Decision Ledger](docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md).
