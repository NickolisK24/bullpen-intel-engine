"""Tests for the Intelligence Surface snapshot layer (performance).

The snapshot layer caches the GET /api/bullpen/intelligence/today response per
slate and serves it back quickly, falling back to live generation when no
snapshot exists. These cover: a present snapshot is served verbatim, the served
shape matches the live contract, a missing snapshot falls back and is then
stored, explicit reference_date still works, the empty state round-trips, and the
future-date default cap still holds through the cache. Everything is DB-backed
and read-only against COIN gates — no story data is invented.
"""

from datetime import date

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.intelligence_surface_service as surface_service
from services import intelligence_surface_snapshot as snap
from services.intelligence_surface_snapshot import (
    SNAPSHOT_VERSION,
    read_snapshot,
    serve_today_lead_story,
    write_snapshot,
)
from utils.db import db
from models.completed_game_context import CompletedGameContext
from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
import models.prospect  # noqa: F401  (full model registry for create_all)
from api.bullpen import bullpen_bp

_FIXED_TODAY = date(2026, 6, 26)
_REF = date(2026, 6, 25)
_FUTURE = date(2026, 7, 23)

_CONTRACT_KEYS = {
    'status', 'reference_date', 'lead_story',
    'candidates_considered', 'publishable_candidates', 'errors', 'empty_reason',
}


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    monkeypatch.setattr(surface_service, 'product_current_date', lambda: _FIXED_TODAY)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    flask_app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def client(app):
    return app.test_client()


def _seed_lost_game_shape(team_id, game_pk, game_date=_REF, **over):
    base = dict(
        starter_name='Sample Starter', starter_ip=6.0, starter_exit_inning=6,
        bullpen_entry_inning=7, bullpen_entry_score_for=6, bullpen_entry_score_against=2,
        lead_when_bullpen_entered=4, largest_lead=4, largest_deficit=3,
        late_runs_allowed=7, runs_allowed_innings_7_to_9=7,
        lead_protected=False, lead_lost=True, turning_inning=8,
        game_shape_created='normal_start',
    )
    base.update(over)
    row = CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=game_date,
        bullpen_story_tag='lost_game_shape', confidence='HIGH', **base)
    db.session.add(row)
    db.session.commit()
    return row


def _seed_low_confidence(team_id, game_pk, game_date=_REF):
    # Boxscore-only -> LOW -> insufficient_context -> not publishable.
    row = CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=game_date,
        bullpen_story_tag='insufficient_context', confidence='LOW')
    db.session.add(row)
    db.session.commit()
    return row


def _store_marker_snapshot(reference_date, team_id):
    """A hand-written 'ok' snapshot whose lead team has no context row, so it can
    only be returned from the cache (a live build would find nothing)."""
    response = {
        'status': 'ok',
        'reference_date': reference_date.isoformat(),
        'lead_story': {'team_id': team_id, 'game_pk': 1, 'package': {}, 'drafts': {},
                       'selection': {'rank': 1}},
        'candidates_considered': 1,
        'publishable_candidates': 1,
        'errors': 0,
        'empty_reason': None,
    }
    write_snapshot(response, source='test_marker')
    return response


# ── 1. Snapshot is returned when present ──────────────────────────────────────

def test_present_snapshot_is_served_verbatim(app):
    with app.app_context():
        marker = _store_marker_snapshot(_REF, team_id=555)  # no context for 555
        result = serve_today_lead_story(reference_date=_REF)
    assert result == marker
    assert result['lead_story']['team_id'] == 555   # could only come from the cache


def test_endpoint_serves_present_snapshot(client):
    with client.application.app_context():
        _store_marker_snapshot(_REF, team_id=555)
    body = client.get('/api/bullpen/intelligence/today?reference_date=2026-06-25').get_json()
    assert body['lead_story']['team_id'] == 555


# ── 2. Served shape is identical to the live contract ─────────────────────────

def test_snapshot_response_shape_matches_live_contract(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        live = surface_service.build_today_lead_story(reference_date=_REF)
        served = serve_today_lead_story(reference_date=_REF)   # builds + stores, then returns
        again = serve_today_lead_story(reference_date=_REF)    # now from snapshot
    assert set(live) == _CONTRACT_KEYS
    assert set(served) == _CONTRACT_KEYS
    assert set(again) == _CONTRACT_KEYS
    # Cache round-trips the exact bytes the builder produced.
    assert again == served
    # Same contract shape as a live build (deep values differ only by the
    # per-build generated_at timestamp inside the package, not by structure).
    assert set(served['lead_story']) == set(live['lead_story'])
    assert set(served['lead_story']['drafts']) == set(live['lead_story']['drafts'])
    assert served['lead_story']['selection'] == live['lead_story']['selection']


# ── 3 & 4. Missing snapshot falls back to live generation, then stores it ─────

def test_missing_snapshot_falls_back_then_persists(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        assert read_snapshot(_REF) is None          # nothing cached yet
        result = serve_today_lead_story(reference_date=_REF)
        assert result['status'] == 'ok'
        assert result['lead_story']['team_id'] == 137   # built live
        # The on-demand result is now stored for next time.
        stored = read_snapshot(_REF)
        assert stored == result
        row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF, snapshot_version=SNAPSHOT_VERSION).one()
        assert row.status == 'ok'
        assert row.lead_story_team_id == 137
        assert row.source == 'on_demand'


def test_persist_false_does_not_store(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        serve_today_lead_story(reference_date=_REF, persist=False)
        assert read_snapshot(_REF) is None


# ── 5. Explicit reference_date still works ────────────────────────────────────

def test_explicit_reference_date_builds_and_serves(client):
    with client.application.app_context():
        _seed_lost_game_shape(137, 137000, game_date=date(2026, 6, 24))
    first = client.get('/api/bullpen/intelligence/today?reference_date=2026-06-24').get_json()
    assert first['status'] == 'ok'
    assert first['reference_date'] == '2026-06-24'
    assert first['lead_story']['team_id'] == 137
    # Second call is served from the snapshot stored on the first.
    with client.application.app_context():
        assert read_snapshot(date(2026, 6, 24)) is not None
    second = client.get('/api/bullpen/intelligence/today?reference_date=2026-06-24').get_json()
    assert second == first


# ── 6. Empty state round-trips correctly ──────────────────────────────────────

def test_empty_state_is_served_and_stored(app):
    with app.app_context():
        _seed_low_confidence(147, 147000)   # publishable=0
        result = serve_today_lead_story()
        assert result['status'] == 'empty'
        assert result['empty_reason'] == 'no_publishable_coin_story'
        # Empty-but-dated responses are cached too.
        row = IntelligenceSurfaceSnapshot.query.filter_by(reference_date=_REF).one()
        assert row.status == 'empty'
        again = serve_today_lead_story()
        assert again == result


def test_empty_db_default_returns_empty_and_stores_nothing(app):
    with app.app_context():
        result = serve_today_lead_story()
        assert result['status'] == 'empty'
        assert result['empty_reason'] == 'no_completed_game_contexts'
        # No slate date to key on -> nothing cached.
        assert IntelligenceSurfaceSnapshot.query.count() == 0


# ── 7. Future-date default cap still holds through the cache ──────────────────

def test_default_ignores_future_context_even_with_future_snapshot(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000, game_date=_FUTURE)   # future CRITICAL
        _seed_lost_game_shape(147, 147000, game_date=date(2026, 6, 24))  # past
        # A stray cached snapshot for the future date must not be chosen by default.
        _store_marker_snapshot(_FUTURE, team_id=999)

        result = serve_today_lead_story()   # no reference_date
        assert result['reference_date'] == '2026-06-24'
        assert result['lead_story']['team_id'] == 147
        assert result['lead_story']['team_id'] != 999   # the future snapshot was ignored


def test_explicit_future_reference_date_uses_its_snapshot(app):
    with app.app_context():
        marker = _store_marker_snapshot(_FUTURE, team_id=999)
        result = serve_today_lead_story(reference_date=_FUTURE)
    assert result == marker   # explicit future date is honored and cache-served


# ── Storage helper hygiene ────────────────────────────────────────────────────

def test_write_snapshot_skips_when_no_reference_date(app):
    with app.app_context():
        row = write_snapshot({'status': 'empty', 'reference_date': None,
                              'lead_story': None}, source='test')
        assert row is None
        assert IntelligenceSurfaceSnapshot.query.count() == 0


def test_safe_write_snapshot_never_raises(app, monkeypatch):
    with app.app_context():
        def boom(*a, **k):
            raise RuntimeError('db down')
        monkeypatch.setattr(snap, 'write_snapshot', boom)
        # Should swallow the error and return without raising.
        snap._safe_write_snapshot({'reference_date': _REF.isoformat()}, source='test')


# ── Fail-closed: a read-level DB connection failure ───────────────────────────

def test_read_failure_propagates_and_skips_synchronous_rebuild(app, monkeypatch):
    """A connection-level read failure (SnapshotReadUnavailable) must propagate
    and must NOT fall through to the expensive synchronous build_today_lead_story
    rebuild — a dead connection is not a cache miss."""
    from services.snapshot_read_guard import SnapshotReadUnavailable

    def _raise_unavailable(*a, **k):
        raise SnapshotReadUnavailable('intelligence_surface', _REF, SNAPSHOT_VERSION)

    built = {'called': False}

    def _track_build(*a, **k):
        built['called'] = True
        return {'status': 'ok', 'reference_date': _REF.isoformat(), 'lead_story': None,
                'candidates_considered': 0, 'publishable_candidates': 0,
                'errors': 0, 'empty_reason': None}

    monkeypatch.setattr(snap, 'read_snapshot_first', _raise_unavailable)
    monkeypatch.setattr(snap, 'build_today_lead_story', _track_build)

    with app.app_context():
        with pytest.raises(SnapshotReadUnavailable):
            serve_today_lead_story(reference_date=_REF)

    assert built['called'] is False
