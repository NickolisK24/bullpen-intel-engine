"""Backtest configuration. Paths, seasons, and request limits live here only."""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BACKEND_DIR = REPO_ROOT / 'backend'

CACHE_DIR = Path(os.environ.get('BULLPEN_BACKTEST_CACHE', HERE / '.cache'))
OUTPUT_DIR = Path(os.environ.get('BULLPEN_BACKTEST_OUTPUT', HERE / 'output'))

# Seasons whose games are evaluated. HISTORY_SEASONS are fetched only so the
# first weeks of the earliest evaluated season have prior appearance history
# (role authority reads a pitcher's last 10 appearances, regardless of date).
EVAL_SEASONS = (2024, 2025, 2026)
HISTORY_SEASONS = (2023,)

API_BASE = 'https://statsapi.mlb.com/api/v1'
# Internal research only. Every response is cached on disk and never refetched.
# Requests are globally throttled (all worker threads share one limiter).
MAX_REQUESTS_PER_SECOND = float(os.environ.get('BULLPEN_BACKTEST_RPS', '4'))
WORKER_THREADS = 4
USER_AGENT = 'bullpen-backtest-research/1.0'
