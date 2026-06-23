"""Digest scheduling, preferences, unsubscribe & delivery tests (Phase D2D).

Covers the wiring that makes BaseballOS able to send a "what changed for your
team" digest: small opt-in preferences (off by default), signed one-click
unsubscribe, the compose -> email-seam delivery path with all gates (opt-in,
cadence, verified email, primary team, suppression), the daily job/scheduler
hook, and admin observability. No real provider is exercised — dev/test always
captures to the in-memory outbox.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import email_delivery
from utils import auth_email  # noqa: F401  (ensures the shared outbox is wired)
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)

import services.digest_delivery as dd
from services.digest_delivery import (
    DIGEST_JOB_ID,
    ERROR,
    SENT,
    SKIP_NOT_OPTED_IN,
    SKIP_UNVERIFIED_EMAIL,
    SKIPPED,
    SUPPRESSED,
    deliver_team_digest,
    register_digest_job,
    render_digest_email,
    run_digest_job,
)
from services import notification_prefs as nprefs
from services.notification_prefs import (
    apply_digest_prefs,
    default_prefs,
    digest_opted_in,
    disable_digest,
    get_digest_prefs,
)
from services.digest_composer import (
    CAPABILITY,
    SUPPRESS_NO_MEANINGFUL_CHANGE,
    SUPPRESS_NO_TEAM,
)
from utils.auth_tokens import (
    build_unsubscribe_url,
    generate_bearer_token,
    generate_unsubscribe_token,
    verify_bearer_token,
    verify_unsubscribe_token,
)


# ── Helpers / fixtures ────────────────────────────────────────────────────────

class _StubUser:
    """Minimal user stand-in for pure delivery/preference tests (no DB)."""
    def __init__(self, *, id=1, email='fan@example.com', verified=True, prefs=None):
        self.id = id
        self.email = email
        self.email_verified_at = datetime(2026, 1, 1) if verified else None
        self.notification_prefs = prefs


def _send_payload(team_id=118):
    """A compose_digest-style send=True payload (what the composer returns)."""
    return {
        'capability': CAPABILITY,
        'send': True,
        'reason': None,
        'team_id': team_id,
        'team_name': 'Kansas City Royals',
        'subject': 'Kansas City Royals bullpen: what changed',
        'sections': {
            'what_changed': {
                'summary': 'Bullpen is tightening.',
                'changes': [{'name': 'First Arm', 'change': 'moved to unavailable'}],
                'change_count': 1,
            },
            'bullpen_picture': {'headline': 'The bullpen is being pulled in earlier than usual'},
            'team_story': {
                'available': True, 'story_type': 'coverage_pressure',
                'headline': 'Pulled earlier', 'beat': 'Starters are averaging 4.1 innings.',
            },
            'deep_link': {
                'url': 'https://app.example.com/?team=118&source=digest',
                'label': "See Kansas City Royals's bullpen",
            },
            'trust': {'data_through': '2026-06-20', 'is_current': True,
                      'confidence': 'high', 'data_state': 'fresh'},
        },
        'limitations': [],
    }


@pytest.fixture(autouse=True)
def _clean_outbox():
    email_delivery.reset_outbox()
    yield
    email_delivery.reset_outbox()


@pytest.fixture
def ctx_app():
    """Minimal app providing config/context for token + send-path unit tests."""
    app = Flask(__name__)
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2d-secret'
    app.config['FRONTEND_BASE_URL'] = 'https://app.example.com'
    app.config['PUBLIC_API_BASE_URL'] = 'https://api.example.com'
    return app


@pytest.fixture
def full_app():
    """Full app with DB + digest/auth/system blueprints for integration tests."""
    from api.auth import auth_bp
    from api.digest import digest_bp
    from api.system import system_bp

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2d-full-secret'
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
def client(full_app):
    return full_app.test_client()


def _bearer(client, email='user@example.com'):
    from urllib.parse import parse_qs, urlparse
    client.post('/api/auth/request-link', json={'email': email})
    link = email_delivery.outbox[-1]['link']
    token = parse_qs(urlparse(link).query)['token'][0]
    return client.post('/api/auth/verify', json={'token': token}).get_json()['token']


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


# ── Preferences (defaults are opted out) ──────────────────────────────────────

def test_preference_defaults_are_opted_out():
    assert default_prefs() == {'digest_enabled': False, 'digest_cadence': 'daily'}
    user = _StubUser(prefs=None)
    assert get_digest_prefs(user)['digest_enabled'] is False
    assert digest_opted_in(user) is False


def test_apply_and_disable_prefs():
    user = _StubUser(prefs=None)
    apply_digest_prefs(user, enabled=True, cadence='weekly')
    assert user.notification_prefs == {'digest_enabled': True, 'digest_cadence': 'weekly'}
    assert digest_opted_in(user) is True
    disable_digest(user)
    assert user.notification_prefs['digest_enabled'] is False
    assert user.notification_prefs['digest_cadence'] == 'off'
    assert digest_opted_in(user) is False


def test_weekly_cadence_only_due_on_configured_weekday():
    monday = date(2026, 6, 22)   # weekday() == 0
    tuesday = date(2026, 6, 23)
    assert nprefs.cadence_due('weekly', monday) is True
    assert nprefs.cadence_due('weekly', tuesday) is False
    assert nprefs.cadence_due('daily', tuesday) is True
    assert nprefs.cadence_due('off', monday) is False


# ── Unsubscribe tokens (signed, user-scoped, purpose-isolated) ────────────────

def test_unsubscribe_token_roundtrip_and_purpose_scoped(ctx_app):
    user = _StubUser(id=42, email='fan@example.com')
    with ctx_app.app_context():
        token = generate_unsubscribe_token(user)
        assert verify_unsubscribe_token(token) == {'uid': 42, 'email': 'fan@example.com'}
        # A bearer token must not verify as an unsubscribe token, and vice versa.
        bearer = generate_bearer_token(user)
        assert verify_unsubscribe_token(bearer) is None
        assert verify_bearer_token(token) is None
        assert verify_unsubscribe_token('not-a-token') is None


def test_build_unsubscribe_url_uses_public_api_base(ctx_app):
    with ctx_app.app_context():
        assert build_unsubscribe_url('TOK') == 'https://api.example.com/api/digest/unsubscribe?token=TOK'


# ── Delivery gates (no send without opt-in / verified email) ──────────────────

def test_opt_in_required_skips_before_composing():
    user = _StubUser(prefs=None)  # default: disabled
    result = deliver_team_digest(
        user,
        digest_builder=lambda *a, **k: pytest.fail('must not compose without opt-in'),
        sender=lambda *a, **k: pytest.fail('must not send without opt-in'),
    )
    assert result['status'] == SKIPPED and result['reason'] == SKIP_NOT_OPTED_IN


def test_unverified_email_skipped():
    user = _StubUser(verified=False, prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    result = deliver_team_digest(
        user,
        digest_builder=lambda *a, **k: pytest.fail('must not compose for unverified user'),
        sender=lambda *a, **k: pytest.fail('must not send to unverified user'),
    )
    assert result['status'] == SKIPPED and result['reason'] == SKIP_UNVERIFIED_EMAIL


def test_digest_send_path_sends_when_composer_sends(ctx_app):
    sent = []

    def fake_sender(to, subject, *, text=None, html=None, **extra):
        sent.append({'to': to, 'subject': subject, 'text': text, 'html': html, 'extra': extra})
        return {'ok': True, 'provider': 'outbox', 'to': to}

    user = _StubUser(prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, digest_builder=lambda u, **k: _send_payload(118), sender=fake_sender,
        )
    assert result['status'] == SENT and result['delivered'] is True
    assert result['team_id'] == 118
    assert len(sent) == 1
    assert sent[0]['to'] == 'fan@example.com'
    assert sent[0]['extra'].get('kind') == 'team_digest'
    assert 'unsubscribe' in sent[0]['text'].lower()


def test_suppressed_digest_is_not_sent(ctx_app):
    sent = []

    def suppressed_builder(u, **k):
        return {'send': False, 'reason': SUPPRESS_NO_MEANINGFUL_CHANGE, 'team_id': 118}

    user = _StubUser(prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, digest_builder=suppressed_builder, sender=lambda *a, **k: sent.append(1),
        )
    assert result['status'] == SUPPRESSED and result['reason'] == SUPPRESS_NO_MEANINGFUL_CHANGE
    assert sent == []


def test_user_without_primary_team_is_not_sent(ctx_app):
    sent = []

    def no_team_builder(u, **k):
        return {'send': False, 'reason': SUPPRESS_NO_TEAM, 'team_id': None}

    user = _StubUser(prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, digest_builder=no_team_builder, sender=lambda *a, **k: sent.append(1),
        )
    assert result['status'] == SUPPRESSED and result['reason'] == SUPPRESS_NO_TEAM
    assert sent == []


def test_dry_run_does_not_send(ctx_app):
    sent = []
    user = _StubUser(prefs={'digest_enabled': True, 'digest_cadence': 'daily'})
    with ctx_app.app_context():
        result = deliver_team_digest(
            user, dry_run=True,
            digest_builder=lambda u, **k: _send_payload(118),
            sender=lambda *a, **k: sent.append(1),
        )
    assert result['status'] == SENT and result['delivered'] is False and result['dry_run'] is True
    assert sent == []


# ── Email rendering ───────────────────────────────────────────────────────────

def test_render_includes_summary_cta_and_unsubscribe():
    subject, text, html = render_digest_email(
        _send_payload(118), unsubscribe_url='https://api.example.com/api/digest/unsubscribe?token=T',
    )
    assert subject == 'Kansas City Royals bullpen: what changed'
    assert 'Bullpen is tightening.' in text
    assert 'First Arm' in text
    assert 'https://app.example.com/?team=118&source=digest' in text
    assert 'https://api.example.com/api/digest/unsubscribe?token=T' in text
    assert 'Unsubscribe' in html


# ── Daily job (one pass; no duplicate sends; tally) ───────────────────────────

def test_run_digest_job_dedups_and_tallies(ctx_app):
    calls = []

    def fake_deliver(user, *, reference_date=None, dry_run=False):
        calls.append(user.id)
        if user.id == 1:
            return {'status': SENT}
        if user.id == 2:
            return {'status': SUPPRESSED, 'reason': 'no_meaningful_change'}
        return {'status': SKIPPED, 'reason': 'not_opted_in'}

    u1, u2, u3 = _StubUser(id=1), _StubUser(id=2), _StubUser(id=3)
    roster = [u1, u2, u3, u1]  # u1 duplicated -> processed once (no duplicate sends)
    summary = run_digest_job(ctx_app, users=roster, deliver=fake_deliver)

    assert calls == [1, 2, 3]
    assert summary['considered'] == 3
    assert summary['sent'] == 1
    assert summary['suppressed'] == 1 and summary['suppressed_by_reason'] == {'no_meaningful_change': 1}
    assert summary['skipped'] == 1 and summary['skipped_by_reason'] == {'not_opted_in': 1}


def test_run_digest_job_sends_to_outbox_for_eligible_user(full_app):
    with full_app.app_context():
        db.session.add(User(
            email='go@example.com', email_verified_at=datetime(2026, 1, 1),
            notification_prefs={'digest_enabled': True, 'digest_cadence': 'daily'},
        ))
        db.session.commit()

    def deliver(user, *, reference_date=None, dry_run=False):
        # Real email seam (-> outbox in test); inject the composer so the test
        # does not depend on seeded intelligence.
        return deliver_team_digest(
            user, reference_date=reference_date, dry_run=dry_run,
            digest_builder=lambda u, **k: _send_payload(118),
        )

    summary = run_digest_job(full_app, deliver=deliver)
    assert summary['considered'] == 1 and summary['sent'] == 1
    assert len(email_delivery.outbox) == 1
    rec = email_delivery.outbox[-1]
    assert rec['to'] == 'go@example.com'
    assert rec['subject'].endswith('what changed')
    assert rec.get('kind') == 'team_digest'
    assert '/api/digest/unsubscribe?token=' in rec['text']


def test_run_digest_job_real_path_suppresses_user_without_team(full_app):
    # Opted in + verified, but follows no team -> the composer suppresses and
    # nothing is sent (real deliver + real composition engine).
    with full_app.app_context():
        db.session.add(User(
            email='noteam@example.com', email_verified_at=datetime(2026, 1, 1),
            notification_prefs={'digest_enabled': True, 'digest_cadence': 'daily'},
        ))
        db.session.commit()

    summary = run_digest_job(full_app)
    assert summary['sent'] == 0
    assert summary['suppressed_by_reason'].get(SUPPRESS_NO_TEAM, 0) >= 1
    assert email_delivery.outbox == []


# ── Scheduler hook ────────────────────────────────────────────────────────────

def test_register_digest_job_wires_run_digest_job(monkeypatch):
    captured = {}

    class FakeScheduler:
        def add_job(self, func, **kwargs):
            captured['func'] = func
            captured['kwargs'] = kwargs
            return 'job-handle'

    invoked = []
    monkeypatch.setattr(dd, 'run_digest_job', lambda app, **k: invoked.append(app))

    job = register_digest_job(FakeScheduler(), 'THE_APP', trigger=object())
    assert job == 'job-handle'
    assert captured['kwargs']['id'] == DIGEST_JOB_ID
    assert captured['kwargs']['replace_existing'] is True
    # Simulate the scheduler firing the registered job.
    captured['func']()
    assert invoked == ['THE_APP']


# ── Provider independence ─────────────────────────────────────────────────────

def test_no_provider_coupling_in_delivery():
    src = open(dd.__file__).read()
    assert 'send_email' in src  # uses the seam (allowed)
    for term in ('resend', 'smtp', 'api.resend.com', 'EMAIL_API_KEY', 'requests'):
        assert term not in src, term


# ── Preference + unsubscribe API surfaces ─────────────────────────────────────

def test_preferences_opt_in_via_api(client):
    token = _bearer(client, 'prefs@example.com')

    r = client.get('/api/digest/preferences', headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()['notification_prefs']['digest_enabled'] is False  # default off

    r = client.put('/api/digest/preferences', headers=_auth(token),
                    json={'digest_enabled': True, 'digest_cadence': 'weekly'})
    assert r.status_code == 200
    assert r.get_json()['notification_prefs'] == {'digest_enabled': True, 'digest_cadence': 'weekly'}

    r = client.get('/api/digest/preferences', headers=_auth(token))
    assert r.get_json()['notification_prefs']['digest_enabled'] is True


def test_preferences_reject_invalid_cadence(client):
    token = _bearer(client, 'prefs2@example.com')
    r = client.put('/api/digest/preferences', headers=_auth(token), json={'digest_cadence': 'hourly'})
    assert r.status_code == 400


def test_preferences_require_authentication(client):
    assert client.get('/api/digest/preferences').status_code == 401
    assert client.put('/api/digest/preferences', json={'digest_enabled': True}).status_code == 401


def test_unsubscribe_disables_digest(full_app, client):
    with full_app.app_context():
        user = User(
            email='bye@example.com', email_verified_at=datetime(2026, 1, 1),
            notification_prefs={'digest_enabled': True, 'digest_cadence': 'daily'},
        )
        db.session.add(user)
        db.session.commit()
        token = generate_unsubscribe_token(user)
        uid = user.id

    resp = client.get(f'/api/digest/unsubscribe?token={token}')
    assert resp.status_code == 200
    assert b'unsubscribed' in resp.data.lower()

    with full_app.app_context():
        refreshed = db.session.get(User, uid)
        assert get_digest_prefs(refreshed)['digest_enabled'] is False


def test_unsubscribe_with_bad_token_is_noop(client):
    resp = client.get('/api/digest/unsubscribe?token=garbage')
    assert resp.status_code == 200
    assert b'invalid' in resp.data.lower()


def test_unsubscribe_json_format(full_app, client):
    with full_app.app_context():
        user = User(
            email='json@example.com', email_verified_at=datetime(2026, 1, 1),
            notification_prefs={'digest_enabled': True, 'digest_cadence': 'daily'},
        )
        db.session.add(user)
        db.session.commit()
        token = generate_unsubscribe_token(user)

    resp = client.get(f'/api/digest/unsubscribe?token={token}&format=json')
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True, 'digest_enabled': False}


# ── Admin observability ───────────────────────────────────────────────────────

def test_admin_digest_status_is_dry_run(full_app, client):
    with full_app.app_context():
        db.session.add(User(
            email='status@example.com', email_verified_at=datetime(2026, 1, 1),
            notification_prefs={'digest_enabled': True, 'digest_cadence': 'daily'},
        ))
        db.session.commit()

    resp = client.get('/api/system/digest-status')  # admin token unset in test -> allowed
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['dry_run'] is True
    assert body['considered'] >= 1
    assert email_delivery.outbox == []  # a dry-run never sends
