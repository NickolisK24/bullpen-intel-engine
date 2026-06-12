"""
Unit tests for the resilient MLB Stats API client.

These exercise the retry/backoff/classification logic with mocked HTTP
responses — no network. Backoff jitter is disabled and time.sleep is stubbed
so the tests are fast and deterministic and can assert exact delays.
"""

import requests
import pytest
from flask import Flask

from services.mlb_api import MLBApiClient


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(
        MLB_API_BASE='https://example.test/api/v1',
        MLB_API_TIMEOUT=5,
        MLB_API_MAX_RETRIES=3,
        MLB_API_BACKOFF_BASE=1.0,
        MLB_API_BACKOFF_CAP=30.0,
        MLB_API_BACKOFF_JITTER=False,
    )
    return app


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {'ok': True}
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f'{self.status_code}')


@pytest.fixture
def sleeps(monkeypatch):
    """Capture every backoff sleep duration instead of actually sleeping."""
    captured = []
    monkeypatch.setattr('services.mlb_api.time.sleep', lambda s: captured.append(s))
    return captured


def _client_with_responses(monkeypatch, responses):
    """Build a client whose session.get yields the given responses/exceptions."""
    client = MLBApiClient()
    calls = {'n': 0}

    def fake_get(url, params=None, timeout=None):
        idx = calls['n']
        calls['n'] += 1
        item = responses[min(idx, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client.session, 'get', fake_get)
    client._calls = calls
    return client


class TestTransientRetries:
    def test_timeout_is_retried_then_succeeds(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            requests.exceptions.Timeout('slow'),
            requests.exceptions.Timeout('slow'),
            FakeResponse(200, {'value': 1}),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result == {'value': 1}
        assert client._calls['n'] == 3          # 2 failures + 1 success
        assert client.metrics.retries == 2
        assert client.metrics.api_calls == 3

    def test_connection_error_is_retried(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            requests.exceptions.ConnectionError('down'),
            FakeResponse(200, {'value': 2}),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result == {'value': 2}
        assert client.metrics.retries == 1

    def test_5xx_is_retried(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            FakeResponse(503),
            FakeResponse(500),
            FakeResponse(200, {'value': 3}),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result == {'value': 3}
        assert client.metrics.retries == 2

    def test_exhausted_retries_returns_none_without_hanging(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            requests.exceptions.Timeout('slow'),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result is None
        # 1 initial + 3 retries = 4 attempts; then it gives up (never hangs).
        assert client._calls['n'] == 4
        assert client.metrics.retries == 3


class TestNonTransient:
    def test_404_is_not_retried(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [FakeResponse(404)])
        with app.app_context():
            result = client._get('/missing')
        assert result is None
        assert client._calls['n'] == 1          # no retry on a 4xx
        assert client.metrics.retries == 0
        assert sleeps == []

    def test_400_is_not_retried(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [FakeResponse(400)])
        with app.app_context():
            result = client._get('/bad')
        assert result is None
        assert client._calls['n'] == 1


class TestRateLimiting:
    def test_429_is_retried(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            FakeResponse(429),
            FakeResponse(200, {'value': 9}),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result == {'value': 9}
        assert client.metrics.retries == 1

    def test_retry_after_header_is_honored(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            FakeResponse(429, headers={'Retry-After': '7'}),
            FakeResponse(200, {'value': 9}),
        ])
        with app.app_context():
            client._get('/thing')
        # The first (and only) backoff slept the Retry-After value, not the
        # exponential default of 1s.
        assert sleeps == [7.0]

    def test_retry_after_is_capped(self, app, monkeypatch, sleeps):
        client = _client_with_responses(monkeypatch, [
            FakeResponse(429, headers={'Retry-After': '99999'}),
            FakeResponse(200, {'value': 9}),
        ])
        with app.app_context():
            client._get('/thing')
        # A hostile Retry-After cannot make the job hang — bounded by the cap.
        assert sleeps == [30.0]


class TestBackoff:
    def test_exponential_backoff_capped(self, app, monkeypatch, sleeps):
        # base=1, jitter off → delays 1, 2, 4 ... but capped at the configured
        # cap. Lower the cap to prove it bites.
        app.config['MLB_API_BACKOFF_CAP'] = 3.0
        app.config['MLB_API_MAX_RETRIES'] = 4
        client = _client_with_responses(monkeypatch, [
            FakeResponse(500),
            FakeResponse(500),
            FakeResponse(500),
            FakeResponse(500),
            FakeResponse(200, {'value': 1}),
        ])
        with app.app_context():
            result = client._get('/thing')
        assert result == {'value': 1}
        # 1, 2, then capped at 3, 3.
        assert sleeps == [1.0, 2.0, 3.0, 3.0]
