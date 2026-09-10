import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from api.audience import audience_bp
from models.audience_subscriber import AudienceSubscriber
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils import email_delivery
from utils.db import db


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_delivery.reset_outbox()
    yield
    email_delivery.reset_outbox()


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    db.init_app(app)
    app.register_blueprint(audience_bp, url_prefix='/api/audience')
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


def test_valid_signup_persists_subscriber_and_welcome(client, app):
    resp = client.post('/api/audience/signup', json={
        'email': '  Fan@Example.COM  ',
        'source': 'homepage_hero',
    })

    assert resp.status_code == 200
    assert resp.get_json() == {
        'success': True,
        'message': 'You are on the list for BaseballOS bullpen notes.',
    }
    with app.app_context():
        subscriber = AudienceSubscriber.query.one()
        assert subscriber.email_normalized == 'fan@example.com'
        assert subscriber.email_original == 'Fan@Example.COM'
        assert subscriber.source == 'homepage_hero'
        assert subscriber.status == 'subscribed'
        assert subscriber.welcome_sent_at is not None
        assert subscriber.last_welcome_error is None
    assert len(email_delivery.outbox) == 1
    assert email_delivery.outbox[-1]['email'] == 'fan@example.com'
    assert email_delivery.outbox[-1]['kind'] == 'audience_welcome'
    assert 'No picks. No betting.' in email_delivery.outbox[-1]['text']


def test_invalid_email_is_rejected_without_persistence_or_email(client, app):
    resp = client.post('/api/audience/signup', json={'email': 'not-an-email'})

    assert resp.status_code == 400
    assert resp.get_json() == {
        'success': False,
        'message': 'Enter a valid email address.',
        'reason': 'invalid_email',
    }
    with app.app_context():
        assert AudienceSubscriber.query.count() == 0
    assert email_delivery.outbox == []


def test_duplicate_email_is_idempotent_and_does_not_resend(client, app):
    first = client.post('/api/audience/signup', json={'email': 'fan@example.com'})
    second = client.post('/api/audience/signup', json={'email': '  FAN@example.com  '})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json() == second.get_json()
    with app.app_context():
        assert AudienceSubscriber.query.filter_by(email_normalized='fan@example.com').count() == 1
    assert len(email_delivery.outbox) == 1


def test_provider_missing_path_succeeds_and_does_not_mark_welcome_sent(client, app):
    app.config['APP_ENV'] = 'production'
    app.config['EMAIL_PROVIDER'] = 'resend'
    app.config['EMAIL_API_KEY'] = None
    app.config['EMAIL_FROM'] = None

    resp = client.post('/api/audience/signup', json={'email': 'missing-provider@example.com'})

    assert resp.status_code == 200
    with app.app_context():
        subscriber = AudienceSubscriber.query.filter_by(
            email_normalized='missing-provider@example.com',
        ).one()
        assert subscriber.welcome_sent_at is None
        assert subscriber.last_welcome_error == 'email_provider_not_configured'
    assert email_delivery.outbox == []


def test_configured_provider_sends_welcome_without_outbox(monkeypatch, client, app):
    calls = {}

    class FakeResponse:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None):
        calls['url'] = url
        calls['json'] = json
        calls['headers'] = headers
        calls['timeout'] = timeout
        return FakeResponse()

    import requests
    monkeypatch.setattr(requests, 'post', fake_post)
    app.config['APP_ENV'] = 'production'
    app.config['EMAIL_PROVIDER'] = 'resend'
    app.config['EMAIL_API_KEY'] = 'secret'
    app.config['EMAIL_FROM'] = 'BaseballOS <notes@example.com>'

    resp = client.post('/api/audience/signup', json={'email': 'configured@example.com'})

    assert resp.status_code == 200
    assert calls['json']['to'] == ['configured@example.com']
    assert calls['json']['subject'] == 'Welcome to BaseballOS bullpen notes'
    assert calls['headers']['Authorization'] == 'Bearer secret'
    with app.app_context():
        subscriber = AudienceSubscriber.query.filter_by(
            email_normalized='configured@example.com',
        ).one()
        assert subscriber.welcome_sent_at is not None
        assert subscriber.last_welcome_error is None
    assert email_delivery.outbox == []


def test_database_uniqueness_is_enforced(app):
    with app.app_context():
        db.session.add(AudienceSubscriber(email_normalized='unique@example.com'))
        db.session.commit()
        db.session.add(AudienceSubscriber(email_normalized='unique@example.com'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
