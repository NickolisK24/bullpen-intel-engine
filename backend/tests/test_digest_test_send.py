"""One-user digest test-send readiness tests (D2-DIGEST-SMOKE).

Covers the smallest safe controlled-test mechanism: the additive ``force``
override on deliver_team_digest and the admin-gated single-user
/api/system/digest-test-send endpoint. The endpoint must never be able to
broadcast, must dry-run by default, must not depend on DIGEST_SEND_ENABLED, must
respect opt-in/unsubscribe unless force is given, and must always enforce the
verified-email gate and composer suppression.
"""

from datetime import datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import email_delivery
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.digest_metrics import DigestDelivery

from services.digest_delivery import (
    SENT, SKIPPED, SUPPRESSED, SKIP_NOT_OPTED_IN, SKIP_UNVERIFIED_EMAIL,
    deliver_team_digest,
)
from services.digest_composer import CAPABILITY, SUPPRESS_NO_TEAM, SUPPRESS_NO_MEANINGFUL_CHANGE


def _send_payload(team_id=118):
    return {
        'capability': CAPABILITY, 'send': True, 'reason': None, 'team_id': team_id,
        'team_name': 'Kansas City Royals',
        'subject': 'Kansas City Royals bullpen: what changed',
        'sections': {
            'what_changed': {'summary': 'Bullpen is tightening.',
                             'changes': [{'name': 'First Arm', 'change': 'moved to unavailable'}],
                             'change_count': 1},
            'bullpen_picture': {'headline': 'The bullpen is being pulled earlier'},
            'team_story': {'available': True, 'story_type': 'coverage_pressure',
                           'headline': 'Pulled earlier', 'beat': 'Starters average 4.1 innings.'},
            'deep_link': {'url': 'https://baseballos.app/?team=118&source=digest',
                          'label': "See Kansas City Royals's bullpen"},
            'trust': {'data_through': '2026-06-20', 'is_current': True,
                      'confidence': 'high', 'data_state': 'fresh'},
        },
        'limitations': [],
    }


class _StubUser:
    def __init__(self, *, id=1, email='fan@example.com', verified=True, prefs=None):
        self.id = id
        self.email = email
        self.email_verified_at = datetime(2026, 1, 1) if verified else None
        self.notification_prefs = prefs


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_delivery.reset_outbox()
    yield
    email_delivery.reset_outbox()


@pytest.fixture
def ctx_app():
    app = Flask(__name__)
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'smoke-secret'
    app.config['FRONTEND_BASE_URL'] = 'https://baseballos.app'
    app.config['PUBLIC_API_BASE_URL'] = 'https://api.baseballos.app'
    return app


@pytest.fixture
def full_app():
    from api.system import system_bp
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'smoke-full-secret'
    app.config['FRONTEND_BASE_URL'] = 'https://baseballos.app'
    app.config['PUBLIC_API_BASE_URL'] = 'https://api.baseballos.app'
    db.init_app(app)
    app.register_blueprint(system_bp, url_prefix='/api/system')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def client(full_app):
    return full_app.test_client()


def _add_user(*, email='fan@example.com', verified=True, enabled=False, cadence='daily'):
    user = User(
        email=email,
        email_verified_at=datetime(2026, 1, 1) if verified else None,
        notification_prefs={'digest_enabled': enabled, 'digest_cadence': cadence},
    )
    db.session.add(user)
    db.session.commit()
    return user


# ── force override (unit) ─────────────────────────────────────────────────────

def test_force_bypasses_opt_in_gate_for_a_chosen_user(ctx_app):
    sent = []

    def fake_sender(to, subject, *, text=None, html=None, **extra):
        sent.append(to)
        return {'ok': True, 'provider': 'outbox', 'to': to}

    user = _StubUser(verified=True, prefs=None)  # NOT opted in
    with ctx_app.app_context():
        # Without force: respected -> skipped.
        skipped = deliver_team_digest(
            user, digest_builder=lambda u, **k: _send_payload(), sender=fake_sender)
        assert skipped['status'] == SKIPPED and skipped['reason'] == SKIP_NOT_OPTED_IN
        assert sent == []
        # With force: the chosen user is delivered.
        forced = deliver_team_digest(
            user, force=True, digest_builder=lambda u, **k: _send_payload(), sender=fake_sender)
        assert forced['status'] == SENT and forced['delivered'] is True
        assert sent == ['fan@example.com']


def test_force_still_requires_verified_email(ctx_app):
    user = _StubUser(verified=False, prefs=None)
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, force=True,
            digest_builder=lambda *a, **k: pytest.fail('must not compose for unverified'),
            sender=lambda *a, **k: pytest.fail('must not send to unverified'))
    assert result['status'] == SKIPPED and result['reason'] == SKIP_UNVERIFIED_EMAIL


def test_force_does_not_bypass_suppression(ctx_app):
    sent = []
    user = _StubUser(verified=True, prefs=None)
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, force=True,
            digest_builder=lambda u, **k: {'send': False, 'reason': SUPPRESS_NO_MEANINGFUL_CHANGE,
                                           'team_id': 118},
            sender=lambda *a, **k: sent.append(1))
    assert result['status'] == SUPPRESSED and result['reason'] == SUPPRESS_NO_MEANINGFUL_CHANGE
    assert sent == []


# ── /api/system/digest-test-send endpoint ────────────────────────────────────

def test_endpoint_requires_explicit_email_cannot_broadcast(client):
    # No email -> 400 (it can never mean "send to everyone").
    assert client.post('/api/system/digest-test-send', json={}).status_code == 400
    assert client.post('/api/system/digest-test-send', json={'email': '   '}).status_code == 400


def test_endpoint_unknown_email_is_404_and_redacted(client):
    resp = client.post('/api/system/digest-test-send', json={'email': 'nobody@example.com'})
    assert resp.status_code == 404
    body = resp.get_json()
    assert body['error'] == 'user_not_found'
    assert body['target'] == 'n***@example.com'  # redacted, never the raw address


def test_endpoint_dry_run_persists_nothing_and_sends_nothing(full_app, client):
    with full_app.app_context():
        _add_user(email='dryrun@example.com', verified=True, enabled=True)  # opted in, no team
    resp = client.post('/api/system/digest-test-send', json={'email': 'dryrun@example.com'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['mode'] == 'dry_run'
    assert body['requires_digest_send_enabled'] is False
    assert body['digest_send_enabled'] is False
    assert body['target'] == 'd***@example.com'  # no raw email leaked
    # Opted in + verified but no primary team -> composer suppresses.
    assert body['result']['status'] == SUPPRESSED
    assert body['result']['reason'] == SUPPRESS_NO_TEAM
    with full_app.app_context():
        assert DigestDelivery.query.count() == 0  # dry-run persists nothing
    assert email_delivery.outbox == []


def test_endpoint_respects_opt_in_without_force(full_app, client):
    with full_app.app_context():
        _add_user(email='optout@example.com', verified=True, enabled=False)  # NOT opted in
    resp = client.post('/api/system/digest-test-send', json={'email': 'optout@example.com'})
    body = resp.get_json()
    assert body['result']['status'] == SKIPPED
    assert body['result']['reason'] == SKIP_NOT_OPTED_IN


def test_endpoint_force_bypasses_opt_in_but_suppression_still_applies(full_app, client):
    with full_app.app_context():
        _add_user(email='forced@example.com', verified=True, enabled=False)  # not opted in, no team
    resp = client.post('/api/system/digest-test-send',
                       json={'email': 'forced@example.com', 'force': True})
    body = resp.get_json()
    # force reached compose (not skipped for opt-in), but no team -> still suppressed.
    assert body['force'] is True
    assert body['result']['status'] == SUPPRESSED
    assert body['result']['reason'] == SUPPRESS_NO_TEAM
    assert email_delivery.outbox == []


def test_endpoint_send_mode_commits_a_delivery_record(full_app, client):
    # send=true + force on a no-team user: composer suppresses (no email), but the
    # send path records the (suppressed) delivery, proving send-mode persists.
    with full_app.app_context():
        _add_user(email='record@example.com', verified=True, enabled=False)
    resp = client.post('/api/system/digest-test-send',
                       json={'email': 'record@example.com', 'send': True, 'force': True})
    body = resp.get_json()
    assert body['mode'] == 'send'
    assert body['result']['status'] == SUPPRESSED  # no team -> suppressed, nothing emailed
    assert email_delivery.outbox == []
    with full_app.app_context():
        rows = DigestDelivery.query.all()
        assert len(rows) == 1 and rows[0].status == SUPPRESSED and rows[0].reason == SUPPRESS_NO_TEAM


def test_endpoint_report_exposes_link_config(full_app, client):
    with full_app.app_context():
        _add_user(email='links@example.com', verified=True, enabled=True)
    body = client.post('/api/system/digest-test-send', json={'email': 'links@example.com'}).get_json()
    assert body['links']['frontend_base_url'] == 'https://baseballos.app'
    assert body['links']['public_api_base_url'] == 'https://api.baseballos.app'
    assert body['links']['public_api_base_url_set'] is True
