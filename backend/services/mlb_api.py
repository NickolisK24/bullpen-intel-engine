import logging
import random
import time

import requests
from flask import current_app, has_app_context

from datetime import datetime, timedelta


logger = logging.getLogger('baseballos.mlb_api')


# ── Defaults (overridable via app config / env — see config.Config) ──────────
# These are the fallbacks used when no Flask app context is active (e.g. a
# script or the import-time singleton before an app exists). When an app
# context is present the same-named app.config values win, so behavior is
# configurable per environment without hardcoding at call sites.
_DEFAULT_BASE_URL = 'https://statsapi.mlb.com/api/v1'
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 1.0
_DEFAULT_BACKOFF_CAP = 30.0
_DEFAULT_BACKOFF_JITTER = True

# HTTP statuses that are worth retrying. 429 (rate limited) and 5xx (server
# errors) are transient; every other 4xx is a client error we must not retry.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class MlbApiMetrics:
    """
    Lightweight accumulator for one sync run's worth of API activity.

    Single-flight by design: the daily sync is serialized (APScheduler single
    job + the GitHub Actions concurrency group), so a per-client counter is
    sufficient and avoids threading machinery. Reset at the start of a run and
    snapshot at the end to populate sync_runs.api_calls_made / retries_used.
    """

    def __init__(self):
        self.api_calls = 0
        self.retries = 0

    def reset(self):
        self.api_calls = 0
        self.retries = 0

    def snapshot(self):
        return {'api_calls': self.api_calls, 'retries': self.retries}


class MlbApiError(Exception):
    """Raised on a non-transient (non-retryable) MLB API client error (4xx)."""

    def __init__(self, message, status_code=None, endpoint=None):
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class MLBApiClient:
    """
    Client for the MLB Stats API (statsapi.mlb.com).
    Free, no auth required. Documentation: https://statsapi.mlb.com/docs/

    Resilience: every request enforces a per-request timeout and retries
    transient failures (connection errors, timeouts, 429, 5xx) with exponential
    backoff + jitter, honoring Retry-After on 429. Non-transient 4xx responses
    are classified and logged distinctly and never retried. Every attempt is
    logged with endpoint, attempt number, outcome, and latency.
    """

    def __init__(self):
        self.base_url = _DEFAULT_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BaseballOS/1.0 (Portfolio Analytics Tool)'
        })
        self.metrics = MlbApiMetrics()

    # ── Config resolution ────────────────────────────────────────────────────

    def _config(self, key, default):
        """Read a setting from app.config when available, else fall back."""
        if has_app_context():
            return current_app.config.get(key, default)
        return default

    def _request_settings(self):
        return {
            'base_url': self._config('MLB_API_BASE', self.base_url),
            'timeout': self._config('MLB_API_TIMEOUT', _DEFAULT_TIMEOUT),
            'max_retries': self._config('MLB_API_MAX_RETRIES', _DEFAULT_MAX_RETRIES),
            'backoff_base': self._config('MLB_API_BACKOFF_BASE', _DEFAULT_BACKOFF_BASE),
            'backoff_cap': self._config('MLB_API_BACKOFF_CAP', _DEFAULT_BACKOFF_CAP),
            'jitter': self._config('MLB_API_BACKOFF_JITTER', _DEFAULT_BACKOFF_JITTER),
        }

    def _backoff_delay(self, attempt, base, cap, jitter, retry_after=None):
        """
        Exponential backoff with full jitter, capped. A Retry-After hint (429)
        takes precedence but is still bounded by the cap so a hostile header
        cannot make a job hang.
        """
        if retry_after is not None:
            return min(retry_after, cap)
        raw = min(cap, base * (2 ** (attempt - 1)))
        if jitter:
            return random.uniform(0, raw)
        return raw

    @staticmethod
    def _parse_retry_after(response):
        """Parse a Retry-After header (delta-seconds form) into a float."""
        if response is None:
            return None
        value = response.headers.get('Retry-After')
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    def _get(self, endpoint, params=None):
        """
        Make a resilient GET request to the MLB API.

        Returns parsed JSON on success, or None when the endpoint cannot be
        reached after exhausting retries / on a non-transient client error. The
        None contract is preserved for every existing caller — failures degrade
        to empty results rather than raising.
        """
        settings = self._request_settings()
        url = f"{settings['base_url']}{endpoint}"
        max_retries = settings['max_retries']
        last_exc = None

        # attempt is 1-based; total tries = max_retries + 1 (initial + retries).
        for attempt in range(1, max_retries + 2):
            self.metrics.api_calls += 1
            started = time.monotonic()
            try:
                response = self.session.get(
                    url, params=params, timeout=settings['timeout']
                )
                latency_ms = (time.monotonic() - started) * 1000.0
                status = response.status_code

                if status in _RETRYABLE_STATUS:
                    retry_after = (
                        self._parse_retry_after(response) if status == 429 else None
                    )
                    if attempt <= max_retries:
                        delay = self._backoff_delay(
                            attempt,
                            settings['backoff_base'],
                            settings['backoff_cap'],
                            settings['jitter'],
                            retry_after=retry_after,
                        )
                        self.metrics.retries += 1
                        logger.warning(
                            'MLB API retry endpoint=%s attempt=%s/%s status=%s '
                            'outcome=retry latency_ms=%.1f sleep_s=%.2f%s',
                            endpoint, attempt, max_retries + 1, status,
                            latency_ms, delay,
                            ' retry_after=%.2f' % retry_after if retry_after is not None else '',
                        )
                        time.sleep(delay)
                        continue
                    logger.error(
                        'MLB API exhausted endpoint=%s attempt=%s/%s status=%s '
                        'outcome=give_up latency_ms=%.1f',
                        endpoint, attempt, max_retries + 1, status, latency_ms,
                    )
                    return None

                if 400 <= status < 500:
                    # Non-transient client error — classify and log distinctly,
                    # never retry. Degrade to None for callers.
                    logger.error(
                        'MLB API client_error endpoint=%s attempt=%s status=%s '
                        'outcome=non_transient latency_ms=%.1f',
                        endpoint, attempt, status, latency_ms,
                    )
                    return None

                response.raise_for_status()
                logger.info(
                    'MLB API ok endpoint=%s attempt=%s status=%s outcome=success '
                    'latency_ms=%.1f',
                    endpoint, attempt, status, latency_ms,
                )
                return response.json()

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                latency_ms = (time.monotonic() - started) * 1000.0
                last_exc = exc
                if attempt <= max_retries:
                    delay = self._backoff_delay(
                        attempt,
                        settings['backoff_base'],
                        settings['backoff_cap'],
                        settings['jitter'],
                    )
                    self.metrics.retries += 1
                    logger.warning(
                        'MLB API retry endpoint=%s attempt=%s/%s outcome=retry '
                        'error=%s latency_ms=%.1f sleep_s=%.2f',
                        endpoint, attempt, max_retries + 1, type(exc).__name__,
                        latency_ms, delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error(
                    'MLB API exhausted endpoint=%s attempt=%s/%s outcome=give_up '
                    'error=%s latency_ms=%.1f',
                    endpoint, attempt, max_retries + 1, type(exc).__name__, latency_ms,
                )
                return None

            except requests.exceptions.RequestException as exc:
                # Anything else (e.g. malformed URL, too many redirects) is not
                # something a retry will fix.
                latency_ms = (time.monotonic() - started) * 1000.0
                logger.error(
                    'MLB API error endpoint=%s attempt=%s outcome=non_transient '
                    'error=%s latency_ms=%.1f',
                    endpoint, attempt, type(exc).__name__, latency_ms,
                )
                return None

        # Defensive: loop always returns above, but never imply success.
        if last_exc is not None:
            logger.error('MLB API failed endpoint=%s error=%s', endpoint, last_exc)
        return None

    # ─── Teams ───────────────────────────────────────────────

    def get_all_teams(self, sport_id=1):
        """Get all MLB teams. sport_id=1 is MLB."""
        data = self._get('/teams', params={'sportId': sport_id})
        if not data:
            return []
        return data.get('teams', [])

    def get_team_roster(self, team_id, roster_type='pitchers', season=None, date=None, hydrate=None):
        """
        Get team roster.
        roster_type: 'allRoster', 'pitchers', 'active', '40Man', 'fullRoster',
        'nonRosterInvitees'
        """
        params = {'rosterType': roster_type}
        if season:
            params['season'] = season
        if date:
            params['date'] = date
        if hydrate:
            params['hydrate'] = hydrate

        data = self._get(f'/teams/{team_id}/roster', params=params)
        if not data:
            return []
        return data.get('roster', [])

    # ─── Pitchers ────────────────────────────────────────────

    def get_pitcher_game_logs(self, player_id, season=None):
        """Get game-by-game pitching logs for a player."""
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': 'gameLog',
            'group': 'pitching',
            'season': season,
            'sportId': 1
        })
        if not data:
            return []
        stats = data.get('stats', [])
        if stats:
            return stats[0].get('splits', [])
        return []

    def get_player_info(self, player_id):
        """Get detailed player info."""
        data = self._get(f'/people/{player_id}')
        if not data:
            return None
        people = data.get('people', [])
        return people[0] if people else None

    def get_pitching_stats(self, player_id, season=None, stat_type='season'):
        """
        Get aggregate pitching stats.
        stat_type: 'season', 'career', 'lastXGames', 'yearByYear'
        """
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': stat_type,
            'group': 'pitching',
            'season': season
        })
        if not data:
            return None
        stats = data.get('stats', [])
        if stats and stats[0].get('splits'):
            return stats[0]['splits'][0].get('stat', {})
        return None

    # ─── Schedule & Games ────────────────────────────────────

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        """Get game schedule."""
        params = {'sportId': 1, 'hydrate': 'team'}
        if start_date:
            params['startDate'] = start_date
        if end_date:
            params['endDate'] = end_date
        if team_id:
            params['teamId'] = team_id

        data = self._get('/schedule', params=params)
        if not data:
            return []
        dates = data.get('dates', [])
        games = []
        for date in dates:
            games.extend(date.get('games', []))
        return games

    def get_recent_schedule(self, days_back=14):
        """Get games from the last N days."""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        return self.get_schedule(start_date=start_date, end_date=end_date)

    def get_game_boxscore(self, game_pk):
        """Get full boxscore for a specific game."""
        data = self._get(f'/game/{game_pk}/boxscore')
        return data

    def get_game_pitching_lines(self, game_pk):
        """Extract pitcher lines from a game boxscore."""
        boxscore = self.get_game_boxscore(game_pk)
        if not boxscore:
            return []

        pitchers = []
        for side in ['home', 'away']:
            team_data = boxscore.get('teams', {}).get(side, {})
            team_info = team_data.get('team', {})
            pitchers_data = team_data.get('pitchers', [])
            player_data = team_data.get('players', {})

            for pitcher_id in pitchers_data:
                key = f'ID{pitcher_id}'
                player = player_data.get(key, {})
                stats = player.get('stats', {}).get('pitching', {})
                if stats:
                    pitchers.append({
                        'player_id': pitcher_id,
                        'name': player.get('person', {}).get('fullName'),
                        'team': team_info.get('name'),
                        'team_id': team_info.get('id'),
                        'stats': stats,
                        'side': side
                    })
        return pitchers

    # ─── Prospects / Minor Leagues ────────────────────────────

    def get_minor_league_teams(self):
        """Get minor league team list."""
        data = self._get('/teams', params={'sportIds': '11,12,13,14,16'})
        if not data:
            return []
        return data.get('teams', [])

    def get_prospect_stats(self, player_id, season=None):
        """Get stats for a prospect (works across levels)."""
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': 'yearByYear',
            'sportId': 1,
            'season': season
        })
        if not data:
            return []
        stats = data.get('stats', [])
        if stats:
            return stats[0].get('splits', [])
        return []

    def search_player(self, name):
        """Search for a player by name."""
        data = self._get('/people/search', params={
            'names': name,
            'sportIds': '1,11,12,13,14,16'
        })
        if not data:
            return []
        return data.get('people', [])


# Singleton instance
mlb_client = MLBApiClient()
