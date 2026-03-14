# ⚾ BaseballOS

> Your personal baseball analytics command center. Built to break in.

BaseballOS is a full-stack analytics platform designed to demonstrate real baseball development thinking — pitching fatigue modeling, prospect pipeline tracking, and a portfolio layer that lets the work speak for itself.

**Stack:** React + TailwindCSS · Flask + Python · PostgreSQL · MLB Stats API

---

## 📁 Project Structure

```
baseballos/
├── backend/                  # Flask API server
│   ├── app.py                # App entry point
│   ├── config.py             # Environment config
│   ├── requirements.txt      # Python dependencies
│   ├── api/                  # Route blueprints
│   │   ├── bullpen.py        # Bullpen/fatigue endpoints
│   │   ├── prospects.py      # Prospect tracking endpoints
│   │   └── portfolio.py      # Portfolio data endpoints
│   ├── models/               # SQLAlchemy models
│   │   ├── pitcher.py
│   │   ├── game_log.py
│   │   ├── prospect.py
│   │   └── fatigue_score.py
│   ├── services/             # Business logic
│   │   ├── mlb_api.py        # MLB Stats API client
│   │   ├── fatigue.py        # Fatigue scoring engine
│   │   └── prospects.py      # Prospect analytics
│   └── utils/
│       └── db.py             # DB helpers
├── frontend/                 # React app
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       ├── components/
│       │   ├── dashboard/    # Main hub
│       │   ├── bullpen/      # Bullpen module
│       │   ├── prospects/    # Prospect module
│       │   └── portfolio/    # Portfolio module
│       ├── hooks/            # Custom React hooks
│       └── utils/            # API calls, formatters
└── docs/
    └── SETUP.md              # Detailed setup guide
```

---

## 🚀 Quick Start

See `docs/SETUP.md` for the complete step-by-step setup guide.

**Short version:**
```bash
# Backend
cd backend && pip install -r requirements.txt
flask db init && flask db migrate && flask db upgrade
flask run

# Frontend (new terminal)
cd frontend && npm install
npm run dev
```

App runs at `http://localhost:5173`

---

## 🧠 Modules

### 1. Bullpen & Fatigue Tracker
- Pull live/recent MLB pitcher game logs via MLB Stats API
- Score fatigue using rest days, pitch counts, leverage index, appearances in rolling window
- Visual fatigue heat map per team
- Sortable pitcher table with risk indicators

### 2. Prospect Pipeline
- Track minor league prospects by org, level, and stat trends
- Compare development trajectories across similar archetypes
- ETA projection modeling
- Age-adjusted performance curves

### 3. Portfolio Layer
- Methodology docs embedded into the app
- Data source transparency
- Design decision writeups
- Contact/about section — this IS your resume

---

## 📡 Data Sources

- **MLB Stats API** — `https://statsapi.mlb.com/api/v1/` (free, no auth required)
- **PostgreSQL** — local dev database, easy to migrate to hosted (Render, Railway, Supabase)

---

*Built by Nikko. Army vet. Future baseball dev. This is the work.*
