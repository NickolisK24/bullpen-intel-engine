"""Email delivery infrastructure tests (Phase D2B).

Provider is isolated behind the send_email seam: dev/test always capture to the
in-memory outbox (no real send), production routes to the configured provider
(Resend) with safe error handling, and the magic-link flow still works through
the abstraction. No digest, scheduling, or preferences are exercised.
"""

import os

import pytest
from flask import Flask

from utils import auth_email, email_delivery
from utils.email_delivery import (
    PROVIDER_OUTBOX,
    PROVIDER_RESEND,
    email_delivery_health,
    send_email,
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_app(env='test', **cfg):
    app = Flask(__name__)
    app.config['APP_ENV'] = env
    app.config.update(cfg)
    return app


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_delivery.reset_outbox()
    yield
    email_delivery.reset_outbox()


# ── Outbox behavior preserved (dev/test never sends) ──────────────────────────

def test_outbox_capture_in_test_env():
    app = _make_app('test')
    with app.app_context():
        result = send_email('fan@example.com', 'Hello', text='hi', html='<p>hi</p>')
    assert result == {'ok': True, 'provider': PROVIDER_OUTBOX, 'to': 'fan@example.com'}
    rec = email_delivery.outbox[-1]
    assert rec['to'] == 'fan@example.com' and rec['email'] == 'fan@example.com'
    assert rec['subject'] == 'Hello' and rec['text'] == 'hi' and rec['html'] == '<p>hi</p>'


def test_reset_outbox_clears():
    app = _make_app('test')
    with app.app_context():
        send_email('a@b.com', 'S')
    assert email_delivery.outbox
    email_delivery.reset_outbox()
    assert email_delivery.outbox == []


def test_magic_link_still_works_through_abstraction():
    app = _make_app('test')
    with app.app_context():
        result = auth_email.send_magic_link('signin@example.com', 'http://localhost:5173/auth/verify?token=abc')
    assert result['ok'] is True and result['provider'] == PROVIDER_OUTBOX
    rec = auth_email.outbox[-1]
    assert rec['email'] == 'signin@example.com'
    assert rec['link'] == 'http://localhost:5173/auth/verify?token=abc'  # D1C shape preserved
    assert 'Sign in to BaseballOS' in rec['html']


def test_auth_email_outbox_is_the_shared_outbox():
    # The re-exported name must be the same list the delivery layer appends to.
    assert auth_email.outbox is email_delivery.outbox


# ── Provider selection ────────────────────────────────────────────────────────

def test_dev_and_test_always_select_outbox_even_if_provider_set():
    for env in ('development', 'test'):
        app = _make_app(env, EMAIL_PROVIDER='resend', EMAIL_API_KEY='k', EMAIL_FROM='x@y.com')
        with app.app_context():
            assert email_delivery._provider_name() == PROVIDER_OUTBOX


def test_production_selects_configured_provider():
    app = _make_app('production', EMAIL_PROVIDER='resend')
    with app.app_context():
        assert email_delivery._provider_name() == PROVIDER_RESEND
    app2 = _make_app('production', EMAIL_PROVIDER='outbox')
    with app2.app_context():
        assert email_delivery._provider_name() == PROVIDER_OUTBOX  # explicit staging override


# ── Production send path (provider isolated; monkeypatched transport) ─────────

def test_production_send_calls_provider_and_does_not_capture(monkeypatch):
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls['url'] = url
        calls['json'] = json
        calls['headers'] = headers
        calls['timeout'] = timeout
        return _FakeResponse(200)

    import requests
    monkeypatch.setattr(requests, 'post', fake_post)

    app = _make_app('production', EMAIL_PROVIDER='resend',
                    EMAIL_API_KEY='secret-key', EMAIL_FROM='BaseballOS <no-reply@x.com>')
    with app.app_context():
        result = send_email('to@example.com', 'Subj', text='t', html='<p>h</p>')

    assert result == {'ok': True, 'provider': PROVIDER_RESEND, 'to': 'to@example.com'}
    assert calls['url'] == email_delivery.RESEND_ENDPOINT
    assert calls['json'] == {
        'from': 'BaseballOS <no-reply@x.com>', 'to': ['to@example.com'],
        'subject': 'Subj', 'html': '<p>h</p>', 'text': 't',
    }
    assert calls['headers']['Authorization'] == 'Bearer secret-key'
    # Production never holds the message in the in-memory outbox.
    assert email_delivery.outbox == []


def test_production_provider_status_error_is_handled(monkeypatch):
    import requests
    monkeypatch.setattr(requests, 'post', lambda *a, **k: _FakeResponse(500))
    app = _make_app('production', EMAIL_PROVIDER='resend', EMAIL_API_KEY='k', EMAIL_FROM='x@y.com')
    with app.app_context():
        result = send_email('to@example.com', 'S', text='t')
    assert result['ok'] is False and result['error'] == 'status_500'


def test_production_transport_error_is_handled(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError('down')

    monkeypatch.setattr(requests, 'post', boom)
    app = _make_app('production', EMAIL_PROVIDER='resend', EMAIL_API_KEY='k', EMAIL_FROM='x@y.com')
    with app.app_context():
        result = send_email('to@example.com', 'S', text='t')
    assert result['ok'] is False and result['error'] == 'transport_error'


def test_production_unconfigured_provider_fails_soft(monkeypatch):
    # No API key/sender: must not send, not crash, not capture.
    import requests
    monkeypatch.setattr(requests, 'post', lambda *a, **k: pytest.fail('should not send'))
    app = _make_app('production', EMAIL_PROVIDER='resend')
    with app.app_context():
        result = send_email('to@example.com', 'S', text='t')
    assert result['ok'] is False and result['error'] == 'not_configured'
    assert email_delivery.outbox == []


def test_unknown_provider_is_rejected_safely():
    app = _make_app('production', EMAIL_PROVIDER='smoke-signals')
    with app.app_context():
        result = send_email('to@example.com', 'S')
    assert result['ok'] is False and result['error'] == 'unknown_provider'


# ── Health validation ─────────────────────────────────────────────────────────

def test_health_outbox_env_is_ready():
    app = _make_app('test')
    with app.app_context():
        health = email_delivery_health()
    assert health['provider'] == PROVIDER_OUTBOX and health['ready'] is True


def test_health_production_flags_missing_config():
    app = _make_app('production', EMAIL_PROVIDER='resend')
    with app.app_context():
        health = email_delivery_health()
    assert health['ready'] is False
    assert any('EMAIL_API_KEY' in issue for issue in health['issues'])
    assert any('EMAIL_FROM' in issue for issue in health['issues'])


def test_health_production_ready_when_configured():
    app = _make_app('production', EMAIL_PROVIDER='resend', EMAIL_API_KEY='k', EMAIL_FROM='x@y.com')
    with app.app_context():
        health = email_delivery_health()
    assert health['ready'] is True and health['issues'] == []


def test_health_endpoint_returns_payload():
    from api.system import system_bp
    app = _make_app('test')  # admin token unset in non-production -> allowed
    app.register_blueprint(system_bp, url_prefix='/api/system')
    client = app.test_client()
    resp = client.get('/api/system/email-delivery-health')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['provider'] == PROVIDER_OUTBOX and 'ready' in body


# ── Provider isolation (no leakage into auth code) ────────────────────────────

def test_no_provider_leakage_into_auth_code():
    src = open(os.path.join(BACKEND_ROOT, 'api', 'auth.py')).read()
    assert 'from utils.auth_email import' in src
    for term in ('email_delivery', 'resend', 'requests', 'EMAIL_API_KEY', 'api.resend.com'):
        assert term not in src, term


def test_auth_email_does_not_call_a_provider_directly():
    src = open(os.path.join(BACKEND_ROOT, 'utils', 'auth_email.py')).read()
    # The seam composes and delegates to send_email; it never names a provider.
    assert 'send_email' in src
    for term in ('resend', 'requests', 'api.resend.com', 'EMAIL_API_KEY'):
        assert term not in src, term
