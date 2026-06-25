"""Digest deliverability webhook tests (Phase D2A-7).

The provider (Resend) deliverability webhook maps email.delivered / bounced /
complained to canonical digest_delivered / digest_bounced / digest_complaint
events. It is signature-gated, digest-scoped (correlated to a recent sent
delivery), resolves the user by email without storing the email, and never
changes digest behavior or existing metrics.
"""

import json
from datetime import datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive
from utils.webhook_signing import expected_signature
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.digest_metrics import STATUS_SENT, DigestDelivery
from models.product_event import ProductEvent
from services.product_events import (
    DIGEST_BOUNCED,
    DIGEST_COMPLAINT,
    DIGEST_DELIVERED,
    SOURCE_EMAIL_PROVIDER,
)


SECRET = 'whsec_dGVzdC1zZWNyZXQ='  # base64('test-secret')
SVIX_ID = 'msg_1'
SVIX_TS = '1700000000'
WEBHOOK_PATH = '/api/digest/email-events'


@pytest.fixture
def app():
    from api.digest import digest_bp

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2a7-secret'
    app.config['EMAIL_WEBHOOK_SECRET'] = SECRET
    app.config['FRONTEND_BASE_URL'] = 'http://localhost:5173'
    db.init_app(app)
    app.register_blueprint(digest_bp, url_prefix='/api/digest')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def client(app):
    return app.test_client()


def _seed_recipient(email='fan@example.com', team_id=118, sent=True):
    user = User(email=email, email_verified_at=datetime(2026, 1, 1))
    db.session.add(user)
    db.session.commit()
    if sent:
        db.session.add(DigestDelivery(
            user_id=user.id, team_id=team_id, status=STATUS_SENT, sent_at=utc_now_naive(),
        ))
        db.session.commit()
    return user


def _signed(raw, secret=SECRET):
    sig = expected_signature(secret, SVIX_ID, SVIX_TS, raw)
    return {'svix-id': SVIX_ID, 'svix-timestamp': SVIX_TS, 'svix-signature': f'v1,{sig}'}


def _post(client, body, *, headers='sign'):
    raw = json.dumps(body)
    if headers == 'sign':
        headers = _signed(raw)
    return client.post(WEBHOOK_PATH, data=raw, content_type='application/json', headers=headers)


def _events(name=None):
    query = ProductEvent.query
    if name is not None:
        query = query.filter_by(event_name=name)
    return query.order_by(ProductEvent.id).all()


def _delivered_body(email='fan@example.com', message_id='re_abc'):
    return {'type': 'email.delivered', 'data': {'to': [email], 'email_id': message_id}}


# ── Signature gate ────────────────────────────────────────────────────────────

def test_invalid_signature_is_rejected(app, client):
    with app.app_context():
        _seed_recipient()
    bad = {'svix-id': SVIX_ID, 'svix-timestamp': SVIX_TS, 'svix-signature': 'v1,deadbeef'}
    resp = _post(client, _delivered_body(), headers=bad)
    assert resp.status_code == 400
    with app.app_context():
        assert _events() == []


def test_missing_signature_is_rejected_when_secret_configured(app, client):
    with app.app_context():
        _seed_recipient()
    resp = _post(client, _delivered_body(), headers={})
    assert resp.status_code == 400


# ── Event mapping + correlation ───────────────────────────────────────────────

def test_delivered_is_recorded_and_correlated(app, client):
    with app.app_context():
        user = _seed_recipient(team_id=118)
        uid = user.id
    resp = _post(client, _delivered_body(message_id='re_xyz'))
    assert resp.status_code == 200
    with app.app_context():
        events = _events(DIGEST_DELIVERED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id == uid and ev.team_id == 118 and ev.delivery_id is not None
        assert ev.source == SOURCE_EMAIL_PROVIDER
        assert ev.payload == {'provider_message_id': 're_xyz'}
        # The recipient email is resolved to a user id but never stored.
        assert 'fan@example.com' not in json.dumps(ev.to_dict())


def test_bounced_records_bounce_type(app, client):
    with app.app_context():
        _seed_recipient()
    body = {'type': 'email.bounced',
            'data': {'to': 'fan@example.com', 'email_id': 're_b', 'bounce': {'type': 'hard'}}}
    assert _post(client, body).status_code == 200
    with app.app_context():
        ev = _events(DIGEST_BOUNCED)[0]
        assert ev.payload['bounce_type'] == 'hard'
        assert ev.payload['provider_message_id'] == 're_b'


def test_complaint_is_recorded(app, client):
    with app.app_context():
        _seed_recipient()
    body = {'type': 'email.complained', 'data': {'to': 'fan@example.com', 'email_id': 're_c'}}
    assert _post(client, body).status_code == 200
    with app.app_context():
        assert len(_events(DIGEST_COMPLAINT)) == 1


def test_unknown_event_type_is_ignored(app, client):
    with app.app_context():
        _seed_recipient()
    resp = _post(client, {'type': 'email.opened', 'data': {'to': 'fan@example.com'}})
    assert resp.status_code == 200 and resp.get_json().get('ignored')
    with app.app_context():
        assert _events() == []


def test_uncorrelated_recipient_is_ignored(app, client):
    # No user / no recent sent digest -> not a digest fact, recorded as ignored.
    resp = _post(client, _delivered_body(email='stranger@example.com'))
    assert resp.status_code == 200 and resp.get_json().get('ignored') == 'no_digest_correlation'
    with app.app_context():
        assert _events() == []


def test_known_user_without_recent_send_is_ignored(app, client):
    with app.app_context():
        _seed_recipient(email='noemail@example.com', sent=False)  # user, but no sent digest
    resp = _post(client, _delivered_body(email='noemail@example.com'))
    assert resp.status_code == 200 and resp.get_json().get('ignored') == 'no_digest_correlation'
    with app.app_context():
        assert _events() == []


# ── Dev-permissive when no secret is configured ───────────────────────────────

def test_dev_permits_unsigned_when_secret_unset(app, client):
    app.config['EMAIL_WEBHOOK_SECRET'] = None
    with app.app_context():
        _seed_recipient()
    resp = _post(client, _delivered_body(), headers={})  # no signature headers
    assert resp.status_code == 200
    with app.app_context():
        assert len(_events(DIGEST_DELIVERED)) == 1
