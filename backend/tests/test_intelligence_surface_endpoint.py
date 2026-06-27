"""Route tests for GET /api/bullpen/intelligence/today (Intelligence Surface).

Exercises the real database enumeration path: completed-game-context rows for a
date become candidates, the publishable COIN stories are ranked, and the single
lead story is returned. Also covers the honest empty state, the reference_date
parameter, a bad-parameter rejection, the default-date future cap, and that the
legacy team story endpoint is left untouched.
"""

from datetime import date

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.intelligence_surface_service as surface
import services.sync as sync_service
from utils.db import db
from models.completed_game_context import CompletedGameContext
import models.prospect  # noqa: F401  (ensure model registry is fully loaded)
from api.bullpen import bullpen_bp

# Pin "today" so the default-date cap is deterministic regardless of wall clock.
_FIXED_TODAY = date(2026, 6, 26)
_REF = date(2026, 6, 25)        # a valid, non-future slate (<= _FIXED_TODAY)
_FUTURE = date(2026, 7, 23)     # a stray future-dated artifact (> _FIXED_TODAY)


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    monkeypatch.setattr(surface, 'product_current_date', lambda: _FIXED_TODAY)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_context(team_id, game_pk, *, tag, confidence, game_date=_REF, **over):
    row = CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=game_date,
        bullpen_story_tag=tag, confidence=confidence,
    )
    for key, value in over.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.commit()
    return row


def _seed_lost_game_shape(team_id, game_pk, **over):
    base = dict(
        starter_name='Sample Starter', starter_ip=6.0, starter_exit_inning=6,
        bullpen_entry_inning=7, bullpen_entry_score_for=6, bullpen_entry_score_against=2,
        lead_when_bullpen_entered=4, largest_lead=4, largest_deficit=3,
        late_runs_allowed=7, runs_allowed_innings_7_to_9=7,
        lead_protected=False, lead_lost=True, turning_inning=8,
        game_shape_created='normal_start',
    )
    base.update(over)
    return _seed_context(team_id, game_pk, tag='lost_game_shape',
                         confidence='HIGH', **base)


def _seed_overexposed(team_id, game_pk, **over):
    base = dict(
        starter_name='Short Starter', starter_ip=3.0, bullpen_entry_inning=4,
        largest_lead=0, largest_deficit=2, late_runs_allowed=1,
        runs_allowed_innings_7_to_9=1, game_shape_created='short_start',
    )
    base.update(over)
    return _seed_context(team_id, game_pk, tag='bullpen_overexposed',
                         confidence='MEDIUM', **base)


# ── Empty state ───────────────────────────────────────────────────────────────

def test_empty_system_returns_honest_empty_state(client):
    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert body['status'] == 'empty'
    assert body['lead_story'] is None
    assert body['empty_reason'] == 'no_completed_game_contexts'
    assert body['candidates_considered'] == 0
    assert body['publishable_candidates'] == 0


# ── Lead selection over real rows ─────────────────────────────────────────────

def test_returns_critical_lead_over_medium(client):
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000)   # CRITICAL
        _seed_overexposed(147, 147000)        # MEDIUM

    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert body['status'] == 'ok'
    lead = body['lead_story']
    assert lead['team_id'] == 137
    assert lead['selection']['story_priority'] == 'CRITICAL'
    assert lead['selection']['primary_story'] == 'lost_game_shape'
    assert lead['package']['primary_story'] == 'lost_game_shape'
    assert 'team_story' in lead['drafts']
    assert lead['drafts']['team_story']['headline']
    assert body['candidates_considered'] == 2
    assert body['publishable_candidates'] == 2


def test_reference_date_scopes_candidates(client):
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=date(2026, 6, 24))
        _seed_overexposed(147, 147000, game_date=_REF)

    # Asking for the 24th sees only the Giants row.
    body = client.get('/api/bullpen/intelligence/today?reference_date=2026-06-24').get_json()
    assert body['reference_date'] == '2026-06-24'
    assert body['lead_story']['team_id'] == 137
    assert body['candidates_considered'] == 1


def test_rejects_malformed_reference_date(client):
    resp = client.get('/api/bullpen/intelligence/today?reference_date=not-a-date')
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == 'reference_date'


# ── Default date ignores future-dated artifacts ───────────────────────────────

def test_default_ignores_future_dated_context(client):
    # A future CRITICAL story must not be chosen as the default slate, even
    # though it would outrank the past story on priority.
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=_FUTURE)   # future CRITICAL
        _seed_overexposed(147, 147000, game_date=date(2026, 6, 24))  # past MEDIUM

    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert body['status'] == 'ok'
    assert body['reference_date'] == '2026-06-24'   # the latest non-future date
    assert body['lead_story']['team_id'] == 147
    assert body['candidates_considered'] == 1       # the future row is not a candidate


def test_default_selects_latest_non_future_date(client):
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=date(2026, 6, 20))
        _seed_overexposed(147, 147000, game_date=date(2026, 6, 24))   # latest non-future
        _seed_lost_game_shape(141, 141000, game_date=_FUTURE)          # ignored

    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert body['reference_date'] == '2026-06-24'
    assert body['lead_story']['team_id'] == 147
    assert body['candidates_considered'] == 1


def test_only_future_context_yields_empty_default(client):
    # If the only context is in the future, the default finds no candidates and
    # returns the honest empty state rather than locking onto the future date.
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=_FUTURE)

    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert body['status'] == 'empty'
    assert body['empty_reason'] == 'no_completed_game_contexts'
    assert body['candidates_considered'] == 0


def test_explicit_future_reference_date_is_still_honored(client):
    # An operator can still evaluate a future date when they ask for it directly.
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=_FUTURE)

    body = client.get('/api/bullpen/intelligence/today?reference_date=2026-07-23').get_json()
    assert body['status'] == 'ok'
    assert body['reference_date'] == '2026-07-23'
    assert body['lead_story']['team_id'] == 137
    assert body['lead_story']['selection']['story_priority'] == 'CRITICAL'


# ── Legacy story endpoint is unchanged ────────────────────────────────────────

def test_legacy_team_story_endpoint_still_responds(client):
    # The new endpoint must not disturb the existing per-team story contract.
    body = client.get('/api/bullpen/teams/137/story').get_json()
    assert body['contract'] == 'story_intelligence_api_v1'
    assert body['team_id'] == 137


# ── No mutation: selection is read-only ───────────────────────────────────────

def test_endpoint_does_not_mutate_rows(client):
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000)
        before = CompletedGameContext.query.count()

    client.get('/api/bullpen/intelligence/today')

    with client.application.app_context():
        after = CompletedGameContext.query.count()
        row = CompletedGameContext.query.filter_by(team_id=137).first()
    assert after == before == 1
    assert row.bullpen_story_tag == 'lost_game_shape'
