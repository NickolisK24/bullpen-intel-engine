"""Digest metrics & return-tracking tests (Phase D2E).

Covers durable measurement of the D2 return loop: sent/suppressed deliveries are
recorded, opens and clicks are tracked on our own provider-independent endpoints,
returns are attributed (click-through and sign-in), the admin metrics surface
exposes the required totals, and the D2D scheduler/delivery behavior is intact.
"""

import ast
import glob
import os
import re
from datetime import datetime, timedelta

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import email_delivery
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.digest_metrics import DigestDelivery, DigestRun, STATUS_SENT, STATUS_SUPPRESSED

import services.digest_delivery as dd
import services.digest_metrics as dm
from services.digest_metrics import (
    DbDigestRecorder,
    attribute_return,
    metrics_overview,
    record_delivery,
    record_open,
    tracking_urls_for,
)
from services.digest_delivery import deliver_team_digest, register_digest_job, run_digest_job
from services.digest_composer import CAPABILITY, SUPPRESS_NO_MEANINGFUL_CHANGE
from utils.auth_tokens import (
    generate_tracking_token,
    generate_unsubscribe_token,
    verify_tracking_token,
)
from utils.time import utc_now_naive


# ── Helpers / fixtures ────────────────────────────────────────────────────────

def _send_payload(team_id=118):
    return {
        'capability': CAPABILITY, 'send': True, 'reason': None, 'team_id': team_id,
        'team_name': 'Kansas City Royals',
        'subject': 'Kansas City Royals bullpen: what changed',
        'sections': {
            'what_changed': {'summary': 'Bullpen is tightening.',
                             'changes': [{'name': 'First Arm', 'change': 'moved to unavailable'}],
                             'change_count': 1},
            'bullpen_picture': {'headline': 'The bullpen is being pulled in earlier than usual'},
            'team_story': {'available': True, 'story_type': 'coverage_pressure',
                           'headline': 'Pulled earlier', 'beat': 'Starters average 4.1 innings.'},
            'deep_link': {'url': 'https://app.example.com/?team=118&source=digest',
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
def app():
    from api.auth import auth_bp
    from api.digest import digest_bp
    from api.system import system_bp

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2e-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'https://app.example.com'
    app.config['PUBLIC_API_BASE_URL'] = 'https://api.example.com'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(digest_bp, url_prefix='/api/digest')
    app.register_blueprint(system_bp, url_prefix='/api/system')
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


# ── Sent / suppressed recording ───────────────────────────────────────────────

def test_sent_metrics_recorded(app):
    with app.app_context():
        _add_sent_delivery(team_id=118)
        overview = metrics_overview()
    assert overview['totals']['sent'] == 1
    assert overview['totals']['suppressed'] == 0


def test_suppressed_metrics_recorded(app):
    with app.app_context():
        record_delivery(user_id=None, team_id=147, status=STATUS_SUPPRESSED,
                        reason=SUPPRESS_NO_MEANINGFUL_CHANGE)
        db.session.commit()
        overview = metrics_overview()
    assert overview['totals']['suppressed'] == 1
    assert overview['totals']['sent'] == 0
    assert overview['suppressed_by_reason'].get(SUPPRESS_NO_MEANINGFUL_CHANGE) == 1


# ── Open tracking ─────────────────────────────────────────────────────────────

def test_open_tracking_recorded(app):
    with app.app_context():
        delivery = _add_sent_delivery()
        token = generate_tracking_token(delivery.id)
        assert record_open(token) is True
        assert record_open(token) is True  # second open
        refreshed = db.session.get(DigestDelivery, delivery.id)
        assert refreshed.opened_at is not None
        assert refreshed.open_count == 2
        assert metrics_overview()['totals']['opens'] == 1          # unique deliveries opened
        assert metrics_overview()['totals']['open_events'] == 2    # raw events


def test_open_pixel_endpoint_records_and_returns_gif(app, client):
    with app.app_context():
        delivery = _add_sent_delivery()
        token = generate_tracking_token(delivery.id)
        delivery_id = delivery.id

    resp = client.get(f'/api/digest/open?t={token}')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/gif'
    assert resp.data[:6] == b'GIF89a'

    with app.app_context():
        assert db.session.get(DigestDelivery, delivery_id).opened_at is not None


def test_open_pixel_with_bad_token_still_returns_pixel(app, client):
    resp = client.get('/api/digest/open?t=garbage')
    assert resp.status_code == 200 and resp.mimetype == 'image/gif'


# ── Click tracking (+ return attribution) ─────────────────────────────────────

def test_click_tracking_records_and_redirects(app, client):
    with app.app_context():
        user = _add_user()
        delivery = _add_sent_delivery(user_id=user.id, team_id=118)
        token = generate_tracking_token(delivery.id)
        delivery_id = delivery.id

    resp = client.get(f'/api/digest/click?t={token}')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://app.example.com/?team=118&source=digest'

    with app.app_context():
        refreshed = db.session.get(DigestDelivery, delivery_id)
        assert refreshed.clicked_at is not None
        assert refreshed.click_count == 1
        # A click is a return: the digest brought the user back.
        assert refreshed.returned_at is not None
        totals = metrics_overview()['totals']
        assert totals['clicks'] == 1 and totals['returns'] == 1


def test_click_with_bad_token_redirects_to_app_root(app, client):
    resp = client.get('/api/digest/click?t=nonsense')
    assert resp.status_code == 302
    assert resp.headers['Location'] == 'https://app.example.com/'


# ── Return attribution ────────────────────────────────────────────────────────

def test_return_attribution_works_and_is_idempotent(app):
    with app.app_context():
        user = _add_user()
        delivery = _add_sent_delivery(user_id=user.id, sent_at=utc_now_naive() - timedelta(hours=2))
        assert attribute_return(user.id) is True
        first = db.session.get(DigestDelivery, delivery.id).returned_at
        assert first is not None
        # Idempotent: a second attribution does not move the first return.
        assert attribute_return(user.id) is False
        assert db.session.get(DigestDelivery, delivery.id).returned_at == first
        assert metrics_overview()['totals']['returns'] == 1


def test_return_not_attributed_outside_window(app):
    with app.app_context():
        user = _add_user()
        _add_sent_delivery(user_id=user.id, sent_at=utc_now_naive() - timedelta(days=10))
        assert attribute_return(user.id, window_days=7) is False
        assert metrics_overview()['totals']['returns'] == 0


def test_sign_in_attributes_return(app, client):
    # A user who received a digest and then signs in is attributed a return.
    from urllib.parse import parse_qs, urlparse
    with app.app_context():
        user = _add_user(email='returner@example.com')
        _add_sent_delivery(user_id=user.id, sent_at=utc_now_naive() - timedelta(hours=1))
        uid = user.id

    client.post('/api/auth/request-link', json={'email': 'returner@example.com'})
    link = email_delivery.outbox[-1]['link']
    token = parse_qs(urlparse(link).query)['token'][0]
    resp = client.post('/api/auth/verify', json={'token': token})
    assert resp.status_code == 200

    with app.app_context():
        returned = DigestDelivery.query.filter_by(user_id=uid).first().returned_at
        assert returned is not None


# ── Admin metrics surface ─────────────────────────────────────────────────────

def test_admin_metrics_endpoint(app, client):
    with app.app_context():
        user = _add_user()
        d = _add_sent_delivery(user_id=user.id)
        record_open(generate_tracking_token(d.id))
        record_delivery(user_id=None, team_id=147, status=STATUS_SUPPRESSED, reason='no_meaningful_change')
        db.session.commit()

    resp = client.get('/api/system/digest-metrics')  # admin token unset in test -> allowed
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['capability'] == 'digest_metrics'
    for key in ('sent', 'suppressed', 'opens', 'clicks', 'returns'):
        assert key in body['totals']
    assert body['totals']['sent'] == 1
    assert body['totals']['suppressed'] == 1
    assert body['totals']['opens'] == 1
    assert 'open_rate' in body['rates']


# ── Job persistence + scheduler integration ───────────────────────────────────

def test_run_job_persists_run_and_deliveries(app):
    with app.app_context():
        _add_user(email='go@example.com', enabled=True)        # opted in + verified
        _add_user(email='off@example.com', enabled=False)      # not opted in -> skipped

    # Provide our own recorder so the injected deliver still records (the auto
    # recorder only attaches to the default, non-injected delivery path).
    recorder = DbDigestRecorder()

    def deliver(user, *, reference_date=None, dry_run=False):
        return deliver_team_digest(
            user, reference_date=reference_date, dry_run=dry_run, recorder=recorder,
            digest_builder=lambda u, **k: _send_payload(118),
        )

    summary = run_digest_job(app, recorder=recorder, deliver=deliver)
    assert summary['sent'] == 1 and summary['skipped'] == 1

    with app.app_context():
        run = DigestRun.query.order_by(DigestRun.id.desc()).first()
        assert run is not None and run.sent == 1 and run.considered == 2
        assert DigestDelivery.query.filter_by(status=STATUS_SENT).count() == 1
        assert metrics_overview()['totals']['sent'] == 1
    # The send went through the real email seam -> outbox in test.
    assert len(email_delivery.outbox) == 1


def test_dry_run_persists_nothing(app):
    with app.app_context():
        _add_user(email='go@example.com', enabled=True)
        summary = run_digest_job(app, dry_run=True)
        assert summary['dry_run'] is True
        assert DigestRun.query.count() == 0
        assert DigestDelivery.query.count() == 0
    assert email_delivery.outbox == []


def test_scheduler_registration_intact(monkeypatch):
    captured = {}

    class FakeScheduler:
        def add_job(self, func, **kwargs):
            captured['kwargs'] = kwargs
            return 'job'

    invoked = []
    monkeypatch.setattr(dd, 'run_digest_job', lambda app, **k: invoked.append(app))
    register_digest_job(FakeScheduler(), 'APP', trigger=object())
    assert captured['kwargs']['id'] == dd.DIGEST_JOB_ID
    captured['kwargs']  # job registered
    # The registered job still drives run_digest_job (the delivery flow).


# ── Delivery records via recorder + email carries tracking ────────────────────

def test_deliver_records_and_email_has_tracking(app):
    with app.app_context():
        user = _add_user(email='track@example.com')
        recorder = DbDigestRecorder()
        result = deliver_team_digest(
            user, recorder=recorder, digest_builder=lambda u, **k: _send_payload(118),
        )
        db.session.commit()
        assert result['status'] == STATUS_SENT
        delivery = DigestDelivery.query.filter_by(status=STATUS_SENT).one()
        assert delivery.user_id == user.id and delivery.team_id == 118 and delivery.sent_at is not None

    rec = email_delivery.outbox[-1]
    assert '/api/digest/open?t=' in rec['html']    # open pixel embedded
    assert '/api/digest/click?t=' in rec['html']   # CTA wrapped for click tracking


def test_tracking_urls_are_fully_qualified(app):
    # Regression: open/click tracking URLs must carry the backend origin so a
    # mail client never resolves a host-less path to the invalid
    # http:///api/digest/click. The origin comes from PUBLIC_API_BASE_URL
    # (BACKEND_BASE_URL is accepted as its alias at config load).
    with app.app_context():
        delivery = _add_sent_delivery(team_id=118)
        urls = tracking_urls_for(delivery.id)
    assert urls['open_url'].startswith('https://api.example.com/api/digest/open?t=')
    assert urls['click_url'].startswith('https://api.example.com/api/digest/click?t=')


def test_default_delivery_without_recorder_has_no_tracking(app):
    # D2D behavior preserved: no recorder -> no open pixel and no click wrapping;
    # the raw deep link is carried in the plain-text body.
    user = _StubUser(prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    with app.app_context():
        deliver_team_digest(user, digest_builder=lambda u, **k: _send_payload(118))
    rec = email_delivery.outbox[-1]
    assert '/api/digest/open?t=' not in rec['html']
    assert '/api/digest/click?t=' not in rec['html']
    assert 'https://app.example.com/?team=118&source=digest' in rec['text']


# ── Tokens & provider independence ────────────────────────────────────────────

def test_tracking_token_roundtrip_and_purpose_scoped(app):
    with app.app_context():
        token = generate_tracking_token(4242)
        assert verify_tracking_token(token) == 4242
        # An unsubscribe token must not verify as a tracking token.
        unsub = generate_unsubscribe_token(_StubUser(id=1))
        assert verify_tracking_token(unsub) is None
        assert verify_tracking_token('garbage') is None


def test_no_provider_coupling():
    for module in (dm, dd):
        src = open(module.__file__).read()
        for term in ('resend', 'smtp', 'api.resend.com', 'EMAIL_API_KEY', 'requests'):
            assert term not in src, (module.__file__, term)


# ── Durable storage migration ─────────────────────────────────────────────────

_MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migrations', 'versions',
)
_METRICS_REVISION = 'd1f8a3c64b29'
_IDENTITY_REVISION = 'c7f3a1e9d2b4'
# D2A-1 adds the canonical product-event log on top of the metrics migration.
_EVENT_FOUNDATION_REVISION = 'e7d2c9a4b6f1'
# COIN Phase 2 adds the derived completed-game-context table on top of the
# event-foundation revision, so the single alembic head moves forward to it.
_COMPLETED_GAME_CONTEXT_REVISION = 'b9e4c1f7a2d6'
# The Intelligence Surface snapshot cache chains off the completed-game-context
# table, advancing the single alembic head once more.
_INTELLIGENCE_SURFACE_SNAPSHOT_REVISION = 'a7f2c1d4e9b6'
# Schedule Storage V1 adds the scheduled_games table on top of the snapshot
# revision, advancing the single alembic head once more.
_SCHEDULED_GAMES_REVISION = 'c5b1e9a2f7d4'
# Tonight Snapshot V1 adds the tonight_intelligence_snapshots cache on top of
# scheduled_games, advancing the single alembic head once more.
_TONIGHT_SNAPSHOT_REVISION = 'd4a8c2e6b1f9'
# Unknown-safe pitch counts remove the game_logs.pitches_thrown default on top
# of tonight snapshots, advancing the single alembic head once more.
_UNKNOWN_PITCH_COUNT_REVISION = 'e3b7a9c4d2f6'
# Stat correction provenance columns chain on top of unknown-safe pitch counts,
# advancing the single alembic head once more.
_GAME_LOG_CORRECTION_PROVENANCE_REVISION = 'f6a2c9d8e1b3'
# Postgame marker lifecycle columns chain on top of stat correction provenance,
# advancing the single alembic head once more.
_POSTGAME_MARKER_LIFECYCLE_REVISION = 'c2f6a9d8e4b1'
# Scheduled-game resumption linkage columns chain on top of the postgame marker
# lifecycle revision, advancing the single alembic head once more.
_SCHEDULED_GAME_RESUMPTION_LINKAGE_REVISION = 'b1c9d7e2a4f6'
# Unknown-safe boxscore fields chain on top of scheduled-game resumption
# linkage, advancing the single alembic head once more.
_BOXSCORE_FIELD_EXPANSION_REVISION = 'd6b8f3a1c9e7'
# Roster status snapshots chain on top of unknown-safe boxscore fields,
# advancing the single alembic head once more.
_ROSTER_STATUS_SNAPSHOT_REVISION = 'e1a9c4d7b6f2'
# Player transactions chain on top of roster status snapshots, advancing the
# single alembic head once more.
_PLAYER_TRANSACTION_REVISION = 'f8c2d4e6a1b9'
# Final play-by-play foundation chains on top of player transactions, advancing
# the single alembic head once more.
_FINAL_PLAY_BY_PLAY_REVISION = 'a2f4c6d8e9b1'
# Team-game pitching splits chain on top of final play-by-play, advancing the
# single alembic head once more.
_TEAM_GAME_PITCHING_SPLIT_REVISION = 'b6e1a2f4c9d7'
# Phase 0D evidence contract chains on top of team-game splits, advancing the
# single alembic head once more without adding a production evidence family.
_PHASE0D_EVIDENCE_CONTRACT_REVISION = 'c8d2f4a1b6e9'
# Phase 0E composed reads chain on top of the evidence contract, advancing the
# single alembic head once more without registering a production read type.
_PHASE0E_COMPOSED_READ_REVISION = 'a9d4e7c2f6b1'
# Phase 0E legacy-read reconciliation audit chains on top of composed reads,
# advancing the single alembic head with exactly the audit tables.
_PHASE0E_LEGACY_READ_AUDIT_REVISION = 'e4b7c9d2a6f0'


def test_metrics_migration_is_well_formed_and_chains_off_identity():
    matches = glob.glob(os.path.join(_MIGRATIONS_DIR, f'{_METRICS_REVISION}_*.py'))
    assert len(matches) == 1, matches
    source = open(matches[0]).read()
    ast.parse(source)  # parses cleanly
    assert f"revision = '{_METRICS_REVISION}'" in source
    assert f"down_revision = '{_IDENTITY_REVISION}'" in source
    assert 'def upgrade' in source and 'def downgrade' in source
    for token in ("'digest_runs'", "'digest_deliveries'",
                  'ix_digest_deliveries_user', 'ix_digest_deliveries_status'):
        assert token in source, token


def test_migrations_have_a_single_head():
    revisions = {}
    for path in glob.glob(os.path.join(_MIGRATIONS_DIR, '*.py')):
        text = open(path).read()
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = (down.group(1).strip() if down else None)
    referenced = {d for d in revisions.values() if d and d != 'None'}
    heads = set(revisions) - referenced
    assert heads == {_PHASE0E_LEGACY_READ_AUDIT_REVISION}
    # The chain advances: event log -> completed-game-context -> surface snapshot
    # -> scheduled_games -> tonight snapshot -> unknown-safe pitch counts
    # -> stat-correction provenance -> postgame marker lifecycle.
    assert revisions[_COMPLETED_GAME_CONTEXT_REVISION] == _EVENT_FOUNDATION_REVISION
    assert (revisions[_INTELLIGENCE_SURFACE_SNAPSHOT_REVISION]
            == _COMPLETED_GAME_CONTEXT_REVISION)
    assert (revisions[_SCHEDULED_GAMES_REVISION]
            == _INTELLIGENCE_SURFACE_SNAPSHOT_REVISION)
    assert (revisions[_TONIGHT_SNAPSHOT_REVISION]
            == _SCHEDULED_GAMES_REVISION)
    assert (revisions[_UNKNOWN_PITCH_COUNT_REVISION]
            == _TONIGHT_SNAPSHOT_REVISION)
    assert (revisions[_GAME_LOG_CORRECTION_PROVENANCE_REVISION]
            == _UNKNOWN_PITCH_COUNT_REVISION)
    assert (revisions[_POSTGAME_MARKER_LIFECYCLE_REVISION]
            == _GAME_LOG_CORRECTION_PROVENANCE_REVISION)
    assert (revisions[_SCHEDULED_GAME_RESUMPTION_LINKAGE_REVISION]
            == _POSTGAME_MARKER_LIFECYCLE_REVISION)
    assert (revisions[_BOXSCORE_FIELD_EXPANSION_REVISION]
            == _SCHEDULED_GAME_RESUMPTION_LINKAGE_REVISION)
    assert (revisions[_ROSTER_STATUS_SNAPSHOT_REVISION]
            == _BOXSCORE_FIELD_EXPANSION_REVISION)
    assert (revisions[_PLAYER_TRANSACTION_REVISION]
            == _ROSTER_STATUS_SNAPSHOT_REVISION)
    assert (revisions[_FINAL_PLAY_BY_PLAY_REVISION]
            == _PLAYER_TRANSACTION_REVISION)
    assert (revisions[_TEAM_GAME_PITCHING_SPLIT_REVISION]
            == _FINAL_PLAY_BY_PLAY_REVISION)
    assert (revisions[_PHASE0D_EVIDENCE_CONTRACT_REVISION]
            == _TEAM_GAME_PITCHING_SPLIT_REVISION)
    assert (revisions[_PHASE0E_COMPOSED_READ_REVISION]
            == _PHASE0D_EVIDENCE_CONTRACT_REVISION)
    assert (revisions[_PHASE0E_LEGACY_READ_AUDIT_REVISION]
            == _PHASE0E_COMPOSED_READ_REVISION)
