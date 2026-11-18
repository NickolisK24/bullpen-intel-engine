"""Rate-limited, disk-cached MLB Stats API client (read-only, research use).

Every response is stored gzip-compressed under ``CACHE_DIR/<kind>/<key>.json.gz``
and served from disk forever after. A cache hit never touches the network, so a
rerun of the backtest makes zero requests once the cache is warm.
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from pathlib import Path

import requests

from . import config


class _RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            if now < self.next_at:
                time.sleep(self.next_at - now)
                now = time.monotonic()
            self.next_at = now + self.interval


_limiter = _RateLimiter(config.MAX_REQUESTS_PER_SECOND)
_session_local = threading.local()
stats = {'network': 0, 'cache': 0}


def _session():
    sess = getattr(_session_local, 'session', None)
    if sess is None:
        sess = requests.Session()
        sess.headers['User-Agent'] = config.USER_AGENT
        _session_local.session = sess
    return sess


def cache_path(kind: str, key: str) -> Path:
    return config.CACHE_DIR / kind / f'{key}.json.gz'


def read_cached(kind: str, key: str):
    path = cache_path(kind, key)
    if not path.exists():
        return None
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return json.load(fh)


def get_json(kind: str, key: str, path: str, params: dict | None = None, offline: bool = False):
    cached = read_cached(kind, key)
    if cached is not None:
        stats['cache'] += 1
        return cached
    if offline:
        raise FileNotFoundError(f'not cached and offline: {kind}/{key}')
    url = f'{config.API_BASE}{path}'
    last_error = None
    for attempt in range(5):
        _limiter.wait()
        try:
            resp = _session().get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                out = cache_path(kind, key)
                out.parent.mkdir(parents=True, exist_ok=True)
                tmp = out.with_suffix('.tmp')
                with gzip.open(tmp, 'wt', encoding='utf-8') as fh:
                    json.dump(data, fh)
                tmp.replace(out)
                stats['network'] += 1
                return data
            if resp.status_code in (404,):
                raise requests.HTTPError(f'{resp.status_code} for {url}')
            last_error = f'HTTP {resp.status_code}'
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = repr(exc)
        time.sleep(2 ** attempt)
    raise RuntimeError(f'failed after retries: {url} ({last_error})')


# ── Endpoints ────────────────────────────────────────────────────────────────

def schedule(season: int, offline: bool = False):
    """Full regular-season schedule with linescores and venues."""
    return get_json(
        'schedule', str(season), '/schedule',
        params={
            'sportId': 1,
            'season': season,
            'gameType': 'R',
            'hydrate': 'linescore,venue',
        },
        offline=offline,
    )


def boxscore(game_pk: int, offline: bool = False):
    return get_json('boxscore', str(game_pk), f'/game/{game_pk}/boxscore', offline=offline)


def active_roster(team_id: int, day, offline: bool = False):
    iso = day.isoformat()
    return get_json(
        'roster', f'{team_id}_{iso}', f'/teams/{team_id}/roster',
        params={'rosterType': 'active', 'date': iso},
        offline=offline,
    )
