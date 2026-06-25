"""Canonical product event foundation tests (Phase D2A-1).

Verifies that the existing digest lifecycle is now canonicalized into the single
append-only ``product_events`` log — generated / suppressed / sent / opened /
clicked / returned / unsubscribed / reenabled — WITHOUT changing any existing
production behavior. Events are immutable facts (append-only), current state stays
derived, and a telemetry failure can never break a production write.
"""

import ast
import glob
import os
from datetime import datetime, timedelta

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import email_delivery
from utils.auth_tokens import generate_tracking_token, generate_unsubscribe_token
from utils.time import utc_now_naive

from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.digest_metrics import DigestDelivery, DigestRun, STATUS_SENT
from models.product_event import ProductEvent

import services.product_events as pe
from services.product_events import (
    DIGEST_CLICKED,
    DIGEST_GENERATED,
    DIGEST_OPENED,
    DIGEST_REENABLED,
    DIGEST_RETURNED,
    DIGEST_SENT,
    DIGEST_SUPPRESSED,
    DIGEST_UNSUBSCRIBED,
    RETURN_VIA_CLICK,
    RETURN_VIA_SIGN_IN,
    SOURCE_CLICK_REDIRECT,
    SOURCE_ONE_CLICK,
    SOURCE_SETTINGS,
    SOURCE_SIGN_IN,
    SOURCE_TRACKING_PIXEL,
    record_digest_optin_change,
)
from services.digest_metrics import (
    DbDigestRecorder,
    attribute_return,
    record_click,
    record_delivery,
    record_open,
)
from services.digest_delivery import deliver_team_digest, run_digest_job


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _sent_payload(team_id=118):
    return {
        'send': True, 'reason': None, 'team_id': team_id, 'subject': 'what changed',
        'sections': {
            'deep_link': {'url': f'https://app.example.com/?team={team_id}&source=digest',
                          'label': 'See your team'},
            'trust': {'data_through': '2026-06-20'},
        },
    }


def _suppressed_payload(team_id=118, reason='no_meaningful_change'):
    return {'send': False, 'reason': reason, 'team_id': team_id}


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_delivery.reset_outbox()
    yield
    email_delivery.reset_outbox()


@pytest.fixture
def app():
    from api.auth import auth_bp
    from api.digest import digest_bp

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2a1-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'https://app.example.com'
    app.config['PUBLIC_API_BASE_URL'] = 'https://api.example.com'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
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


def _add_user(*, email='fan@example.com', verified=True, enabled=True, cadence='daily'):
    user = User(
        email=email,
        email_verified_at=datetime(2026, 1, 1) if verified else None,
        notification_prefs={'digest_enabled': enabled, 'digest_cadence': cadence},
    )
    db.session.add(user)
    db.session.commit()
    return user


def _add_sent_delivery(*, user_id=None, team_id=118, sent_at=None):
    delivery = record_delivery(user_id=user_id, team_id=team_id, status=STATUS_SENT,
                               sent_at=sent_at or utc_now_naive())
    db.session.commit()
    return delivery


def _events(name=None):
    query = ProductEvent.query
    if name is not None:
        query = query.filter_by(event_name=name)
    return query.order_by(ProductEvent.id).all()


# ── Open / click / return tracking → canonical events ─────────────────────────

def test_open_records_canonical_opened_event(app):
    with app.app_context():
        delivery = _add_sent_delivery(user_id=None, team_id=118)
        assert record_open(generate_tracking_token(delivery.id)) is True
        events = _events(DIGEST_OPENED)
        assert len(events) == 1
        ev = events[0]
        assert ev.delivery_id == delivery.id
        assert ev.team_id == 118
        assert ev.source == SOURCE_TRACKING_PIXEL
        # Existing behavior preserved: the derived counters still move.
        refreshed = db.session.get(DigestDelivery, delivery.id)
        assert refreshed.opened_at is not None and refreshed.open_count == 1


def test_repeat_opens_append_immutable_facts(app):
    # Every open is its own immutable fact; the count stays a derived projection.
    with app.app_context():
        delivery = _add_sent_delivery()
        token = generate_tracking_token(delivery.id)
        record_open(token)
        record_open(token)
        assert len(_events(DIGEST_OPENED)) == 2
        assert db.session.get(DigestDelivery, delivery.id).open_count == 2


def test_click_records_clicked_and_returned_events(app):
    with app.app_context():
        user = _add_user()
        delivery = _add_sent_delivery(user_id=user.id, team_id=118)
        record_click(generate_tracking_token(delivery.id))

        clicked = _events(DIGEST_CLICKED)
        assert len(clicked) == 1 and clicked[0].source == SOURCE_CLICK_REDIRECT
        returned = _events(DIGEST_RETURNED)
        assert len(returned) == 1
        assert returned[0].source == SOURCE_CLICK_REDIRECT
        assert returned[0].payload['attribution_source'] == RETURN_VIA_CLICK
        assert returned[0].delivery_id == delivery.id


def test_second_click_does_not_duplicate_return_event(app):
    # A click is always a fact; a return is only the FIRST return after a digest.
    with app.app_context():
        user = _add_user()
        delivery = _add_sent_delivery(user_id=user.id)
        token = generate_tracking_token(delivery.id)
        record_click(token)
        record_click(token)
        assert len(_events(DIGEST_CLICKED)) == 2
        assert len(_events(DIGEST_RETURNED)) == 1


def test_sign_in_attribution_records_return_event(app):
    with app.app_context():
        user = _add_user(email='returner@example.com')
        _add_sent_delivery(user_id=user.id, sent_at=utc_now_naive() - timedelta(hours=1))
        assert attribute_return(user.id) is True

        returned = _events(DIGEST_RETURNED)
        assert len(returned) == 1
        assert returned[0].source == SOURCE_SIGN_IN
        assert returned[0].payload['attribution_source'] == RETURN_VIA_SIGN_IN
        # Idempotent: a second attribution adds no new fact.
        assert attribute_return(user.id) is False
        assert len(_events(DIGEST_RETURNED)) == 1


# ── Digest job → generated + sent / suppressed events ─────────────────────────

def _run_with(app, payload):
    recorder = DbDigestRecorder()

    def deliver(user, *, reference_date=None, dry_run=False):
        return deliver_team_digest(
            user, reference_date=reference_date, dry_run=dry_run, recorder=recorder,
            digest_builder=lambda u, **k: payload,
        )

    return run_digest_job(app, recorder=recorder, deliver=deliver)


def test_run_job_records_generated_and_sent(app):
    with app.app_context():
        _add_user(email='go@example.com', enabled=True)
    _run_with(app, _sent_payload(118))

    with app.app_context():
        run = DigestRun.query.order_by(DigestRun.id.desc()).first()
        generated = _events(DIGEST_GENERATED)
        sent = _events(DIGEST_SENT)
        assert len(generated) == 1 and len(sent) == 1
        assert generated[0].payload['has_meaningful_change'] is True
        assert generated[0].run_id == run.id
        # The sent event is linked to its delivery row.
        delivery = DigestDelivery.query.filter_by(status=STATUS_SENT).one()
        assert sent[0].delivery_id == delivery.id and sent[0].run_id == run.id
        assert _events(DIGEST_SUPPRESSED) == []


def test_run_job_records_generated_and_suppressed(app):
    with app.app_context():
        _add_user(email='sup@example.com', enabled=True)
    _run_with(app, _suppressed_payload(118, 'no_meaningful_change'))

    with app.app_context():
        generated = _events(DIGEST_GENERATED)
        suppressed = _events(DIGEST_SUPPRESSED)
        assert len(generated) == 1 and len(suppressed) == 1
        assert generated[0].payload['has_meaningful_change'] is False
        assert suppressed[0].payload['reason'] == 'no_meaningful_change'
        assert _events(DIGEST_SENT) == []


def test_dry_run_records_no_events(app):
    with app.app_context():
        _add_user(email='go@example.com', enabled=True)
        run_digest_job(app, dry_run=True)
        assert _events() == []
        assert DigestRun.query.count() == 0 and DigestDelivery.query.count() == 0
    assert email_delivery.outbox == []


# ── Opt-in transitions → unsubscribe / reenable events ────────────────────────

def test_one_click_unsubscribe_endpoint_records_event(app, client):
    with app.app_context():
        user = _add_user(email='leaving@example.com', enabled=True, cadence='daily')
        token = generate_unsubscribe_token(user)
        uid = user.id

    resp = client.get(f'/api/digest/unsubscribe?token={token}')
    assert resp.status_code == 200

    with app.app_context():
        events = _events(DIGEST_UNSUBSCRIBED)
        assert len(events) == 1
        assert events[0].user_id == uid and events[0].source == SOURCE_ONE_CLICK


def test_settings_transitions_record_unsub_then_reenable(app):
    with app.app_context():
        user = _add_user(enabled=True, cadence='daily')
        # opted-in -> opted-out
        record_digest_optin_change(
            user, {'digest_enabled': True, 'digest_cadence': 'daily'},
            {'digest_enabled': False, 'digest_cadence': 'off'}, source=SOURCE_SETTINGS,
        )
        # opted-out -> opted-in
        record_digest_optin_change(
            user, {'digest_enabled': False, 'digest_cadence': 'off'},
            {'digest_enabled': True, 'digest_cadence': 'daily'}, source=SOURCE_SETTINGS,
        )
        db.session.commit()
        unsub = _events(DIGEST_UNSUBSCRIBED)
        reenable = _events(DIGEST_REENABLED)
        assert len(unsub) == 1 and unsub[0].source == SOURCE_SETTINGS
        assert len(reenable) == 1 and reenable[0].source == SOURCE_SETTINGS


def test_non_boundary_pref_change_records_nothing(app):
    # daily -> weekly never crosses the opt-in boundary, so there is no fact.
    with app.app_context():
        user = _add_user(enabled=True, cadence='daily')
        record_digest_optin_change(
            user, {'digest_enabled': True, 'digest_cadence': 'daily'},
            {'digest_enabled': True, 'digest_cadence': 'weekly'}, source=SOURCE_SETTINGS,
        )
        db.session.commit()
        assert _events(DIGEST_UNSUBSCRIBED) == [] and _events(DIGEST_REENABLED) == []


# ── Fault isolation: telemetry never breaks a production write ─────────────────

def test_event_failure_does_not_break_existing_behavior(app, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError('event store unavailable')

    with app.app_context():
        delivery = _add_sent_delivery()
        monkeypatch.setattr(pe, 'ProductEvent', _boom)
        # The open still succeeds and the derived state is still written.
        assert record_open(generate_tracking_token(delivery.id)) is True
        refreshed = db.session.get(DigestDelivery, delivery.id)
        assert refreshed.opened_at is not None and refreshed.open_count == 1
        assert _events(DIGEST_OPENED) == []  # no event recorded, but no crash


# ── Migration is well-formed and chains off the metrics head ──────────────────

_MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migrations', 'versions',
)
_EVENT_FOUNDATION_REVISION = 'e7d2c9a4b6f1'
_METRICS_REVISION = 'd1f8a3c64b29'


def test_product_events_migration_is_well_formed_and_chains_off_metrics():
    matches = glob.glob(os.path.join(_MIGRATIONS_DIR, f'{_EVENT_FOUNDATION_REVISION}_*.py'))
    assert len(matches) == 1, matches
    source = open(matches[0]).read()
    ast.parse(source)
    assert f"revision = '{_EVENT_FOUNDATION_REVISION}'" in source
    assert f"down_revision = '{_METRICS_REVISION}'" in source
    assert 'def upgrade' in source and 'def downgrade' in source
    for token in ("'product_events'", 'ix_product_events_name_occurred',
                  'ix_product_events_occurred_at', 'ix_product_events_user'):
        assert token in source, token
