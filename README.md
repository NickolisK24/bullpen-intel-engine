# ⚾ BaseballOS

> Baseball Analytics Command Center — **flagship module: the Bullpen Intelligence Engine.**

BaseballOS is a full-stack baseball analytics platform. It is built to grow into a
multi-module command center, but it is honest about where it stands today: the
**Bullpen Intelligence Engine** is the mature, real, end-to-end product. Other
modules are clearly marked as prototype or planned so you always know what you're
looking at.

**Stack:** React + TailwindCSS · Flask + Python · PostgreSQL · MLB Stats API

---

## 🎯 What BaseballOS Is Today

The flagship capability is **bullpen fatigue intelligence**: a transparent, end-to-end
system that ingests real MLB game logs, scores relief-pitcher workload, and presents it
through a polished dashboard with a fully documented methodology.

Everything in **Current Capabilities** below is implemented and works against real
MLB Stats API data. Everything under **Planned / Experimental** is labeled as such in
the app itself — no module is presented as more finished than it is.

---

## ✅ Current Capabilities (Implemented)

**Bullpen Intelligence Engine**
- **Fatigue scoring engine** — a 0–100 workload heuristic built from four factors the
  MLB Stats API exposes reliably: pitch-count load (35%), rest days (30%), appearance
  frequency (20%), and innings load (15%). Deterministic and fully documented.
- **MLB Stats API ingestion** — pulls rosters and game-by-game pitching logs; safe to
  re-run (skips duplicates).
- **Pitcher workload analysis** — per-pitcher detail with score breakdown, component
  radar, fatigue trend, and recent appearances.
- **Team bullpen views** — per-team bullpen overview and team-vs-team workload rankings.
- **Sync & freshness tracking** — manual and scheduled sync with a "last synced" status
  the dashboard surfaces honestly (including stale/error states).
- **Historical workload exploration** — scores anchor on each pitcher's most recent game
  so seeded 2024–2025 data produces meaningful end-of-season workload, not offseason zeros.
- **Methodology transparency** — an in-app page documenting exactly how every number is
  computed, including what the model intentionally does *not* use and why.

> The fatigue score is a transparent **workload heuristic** — not an injury or
> performance prediction. See the in-app Methodology page for the full breakdown and
> known limitations.

---

## 🧪 Planned / Experimental Modules

These exist in the app so the roadmap is visible, but they are **not** production-ready
and are labeled accordingly in the UI.

**Prospect Pipeline — early prototype (sample data)**
- A development-pipeline view (levels, scouting-grade scale, ETA, comparisons) wired to a
  working API.
- Currently populated with a **small set of illustrative, hand-entered sample players**,
  not a live minor-league ingestion. Treat it as a UI/roadmap preview, not a data product.

---

## 🗺️ Future Vision

BaseballOS is intended to expand into a broader baseball analytics command center. Likely
directions, only after the bullpen engine is fully polished and deployed:
- Real minor-league prospect ingestion with a defensible grade/ETA source
- Reliever availability projections
- Deeper team-level bullpen-management views
- Live in-season mode

These are direction, not promises — nothing here is implied to exist yet.

---

## 📁 Project Structure

```
baseballos/
├── backend/                    # Flask API server
│   ├── app.py                  # App factory + entry point
│   ├── config.py               # Environment config
│   ├── requirements.txt        # Python dependencies
│   ├── seed.py                 # Seeds pitchers, game logs, fatigue scores (+ sample prospects)
│   ├── recalculate_fatigue.py  # Recompute fatigue from historical reference dates
│   ├── api/                    # Route blueprints
│   │   ├── bullpen.py          # Bullpen / fatigue / sync endpoints (flagship)
│   │   ├── prospects.py        # Prospect endpoints (prototype, sample data)
│   │   └── methodology.py      # Methodology / transparency endpoint
│   ├── models/                 # SQLAlchemy models
│   │   ├── pitcher.py
│   │   ├── game_log.py
│   │   ├── fatigue_score.py
│   │   └── prospect.py
│   ├── services/               # Business logic
│   │   ├── mlb_api.py          # MLB Stats API client
│   │   ├── fatigue.py          # Fatigue scoring engine
│   │   └── sync.py             # Shared sync (manual + scheduled)
│   ├── analysis/               # Out-of-band retrospective analysis
│   ├── migrations/             # Alembic migrations
│   └── utils/db.py
├── frontend/                   # React app
│   └── src/
│       ├── components/
│       │   ├── dashboard/      # Command center hub
│       │   ├── bullpen/        # Bullpen module (flagship)
│       │   ├── prospects/      # Prospect prototype
│       │   ├── methodology/    # Methodology / transparency
│       │   └── UI/             # Shared UI primitives
│       ├── hooks/
│       └── utils/              # API client, formatters, shared fatigue-model definitions
└── docs/
    └── SETUP.md                # Detailed setup guide
```

---

## 🚀 Quick Start

See `docs/SETUP.md` for the complete step-by-step setup guide.

**Short version:**
```bash
# Backend
cd backend && pip install -r requirements.txt
flask db upgrade        # apply existing migrations
python seed.py          # pull data from the MLB Stats API
flask run

# Frontend (new terminal)
cd frontend && npm install
npm run dev
```

App runs at `http://localhost:5173`.

---

## 📡 Data Sources

- **MLB Stats API** — `https://statsapi.mlb.com/api/v1/` (free, no auth required) — rosters,
  game logs, and box scores.
- **PostgreSQL** — local dev database, straightforward to migrate to a hosted provider
  (Render, Railway, Supabase).

---

*Built by Nikko. Army vet. Future baseball dev. This is the work.*
