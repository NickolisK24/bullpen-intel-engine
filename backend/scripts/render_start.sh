#!/usr/bin/env bash
#
# Render production startup: apply database migrations, then start the server.
#
# Why this exists
# ---------------
# The deployed backend can reference schema (columns / tables) introduced by
# Alembic migrations that have not yet been applied to the hosted database.
# When that happens, every request that touches the new schema fails with a
# Postgres UndefinedColumn / UndefinedTable error (HTTP 500). Running
# `flask db upgrade` *before* the web server accepts traffic closes that gap.
#
# Fail-closed contract
# --------------------
#   * `set -euo pipefail` + no error suppression means a failed migration exits
#     this script non-zero and the server is NEVER started.
#   * The migration error from Flask-Migrate / Alembic is written to stderr,
#     which Render captures in the service logs, so the failure is visible.
#   * Migration errors are never swallowed, ignored, or downgraded.
#
# Local development is unaffected: nothing runs this script unless it is set as
# the explicit start command. See docs/current/SETUP.md -> "Deployment notes".
#
# Usage (set as the Render service "Start Command")
# -------------------------------------------------
#   If the Render service Root Directory is the repository root:
#       bash backend/scripts/render_start.sh
#   If the Render service Root Directory is already `backend`:
#       bash scripts/render_start.sh
#
# With no arguments the script launches the documented production server
# (`gunicorn app:app`) bound to Render's $PORT. To run an exact / custom server
# invocation instead, pass it as arguments and it is exec'd verbatim after
# migrations succeed, e.g.:
#       bash backend/scripts/render_start.sh gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
#
set -euo pipefail

# Resolve the backend/ directory (the parent of this script's scripts/ dir) and
# run from there so FLASK_APP=app.py, the migrations/ directory, and the
# `app:app` import target all resolve regardless of the caller's working
# directory or the Render Root Directory setting.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

# Flask CLI entry point. Honour an externally provided FLASK_APP, otherwise fall
# back to the repository's documented value so `flask db upgrade` can locate the
# application factory.
export FLASK_APP="${FLASK_APP:-app.py}"

echo "[render_start] Applying database migrations: flask db upgrade"
flask db upgrade
echo "[render_start] Database migrations applied successfully."

# Start the production server only after migrations succeed. An explicit server
# command passed as arguments is exec'd verbatim; otherwise fall back to the
# documented gunicorn invocation bound to Render's $PORT (default 10000). exec
# replaces this shell so the server process receives signals directly.
if [ "$#" -gt 0 ]; then
  echo "[render_start] Starting server: $*"
  exec "$@"
else
  PORT="${PORT:-10000}"
  # Conservative production tuning. A single default worker with the default
  # 30s timeout means one slow/blocked request (e.g. a stalled DB socket) can
  # SIGKILL the only worker and briefly take the whole service down. Two workers
  # give headroom; --timeout 60 leaves room above the DB statement timeout (15s)
  # so a fast-failing query returns an honest error instead of a worker kill;
  # --graceful-timeout 30 bounds shutdown. Worker count is intentionally small
  # to stay within Render instance memory; override by passing an explicit
  # gunicorn invocation as arguments, or tune via env without a code change.
  GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
  GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-60}"
  GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-30}"
  echo "[render_start] Starting server: gunicorn app:app --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS} --timeout ${GUNICORN_TIMEOUT} --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT}"
  exec gunicorn app:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}"
fi
