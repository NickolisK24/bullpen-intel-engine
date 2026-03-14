# 🛠️ BaseballOS — Setup Guide

Follow this exactly and you'll have the full app running locally.

---

## Prerequisites

Make sure you have these installed:

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| PostgreSQL | 14+ | `psql --version` |
| pip | latest | `pip --version` |
| npm | 9+ | `npm --version` |

---

## Step 1 — Clone & Set Up the Database

```bash
# Create your postgres database
psql -U postgres
CREATE DATABASE baseballos;
\q
```

---

## Step 2 — Backend Setup

```bash
cd baseballos/backend

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Open .env and set your DATABASE_URL:
# DATABASE_URL=postgresql://postgres:yourpassword@localhost/baseballos

# Run database migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Seed initial data (pulls from MLB Stats API)
python seed.py

# Start the backend server
flask run
# Backend runs at http://localhost:5000
```

---

## Step 3 — Frontend Setup

```bash
# In a NEW terminal tab
cd baseballos/frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
# Frontend runs at http://localhost:5173
```

---

## Step 4 — Open the App

Navigate to **http://localhost:5173** in your browser.

You should see the BaseballOS dashboard load with live data from the MLB Stats API.

---

## Environment Variables (.env)

```env
# backend/.env
DATABASE_URL=postgresql://postgres:yourpassword@localhost/baseballos
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
MLB_API_BASE=https://statsapi.mlb.com/api/v1
```

---

## Troubleshooting

**"CORS error" in browser console**
→ Make sure Flask is running on port 5000 and the frontend proxy is set in `vite.config.js`

**"relation does not exist" from Flask**
→ Run `flask db upgrade` again — migrations may not have applied

**No data showing in dashboard**
→ Run `python seed.py` to pull initial data from MLB API

**Port already in use**
→ `flask run --port 5001` or kill the process using the port

---

## Deployment (Future)

When you're ready to deploy:
- **Backend:** Render.com (free tier, Flask-ready)
- **Frontend:** Vercel (free tier, instant React deploys)
- **Database:** Supabase or Railway (free PostgreSQL)

All three services have free tiers that work perfectly for a portfolio project.
