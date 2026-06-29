"""Tests for the Tonight intelligence snapshot layer (performance).

Caches the public Tonight response per slate and serves it back, falling back to
live generation when no snapshot exists. These cover: a present snapshot is
served verbatim, a miss builds + stores, the stored shape matches the live
contract, internal strength is never stored, explicit reference_date works, the
empty state round-trips, and a write failure never breaks serving. DB-backed.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.tonight_intelligence_snapshot as snap
import services.tonight_candidate_selection as tcs
from services.tonight_intelligence_snapshot import (
    TONIGHT_SNAPSHOT_VERSION,
    generate_tonight_snapshot_for_date,
    read_snapshot,
    serve_tonight_cached,
    write_snapshot,
)
from services.tonight_intelligence_service import serve_tonight
from utils.db import db
from models.scheduled_game import ScheduledGame
from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
import models.pitcher  # noqa: F401
import models.game_log  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401

REF = date(2026, 6, 26)

_SERVICE_KEYS = {'status', 'reference_date', 'cards', 'card_count',
                 'empty_reason', 'limitations'}
_CONTRACT_KEYS = _SERVICE_KEYS | {'snapshot'}
_CARD_KEYS = {'team_id', 'team_name', 'headline', 'summary', 'signal_type',
              'signal_family', 'pregame_story', 'evidence', 'schedule_context',
              'bullpen_context', 'limitations'}


def _pen(*, clean=1, band='thin', paths=2, conc='normal', share=40.0, name='Detroit Tigers'):
    return {
        'context_available': True, 'clean_options_count': clean,
        'optionality_band': band, 'practical_close_game_paths_count': paths,
        'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 1,
        'restricted_arms_count': 3, 'concentration_band': conc,
        'top_three_workload_share_10d': share, 'team_name': name,
    }


@pytest.fixture
def app(monkeypatch):
    # Stub the bullpen context so cards don't depend on roster seeding.
    monkeypatch.setattr(
        tcs, '_default_bullpen_context_builder',
        lambda team_id, reference_date: _pen(name=f'Team {team_id}'))
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _seed_playing_stretch(team_id=116):
    db.session.add(ScheduledGame(team_id=team_id, game_pk=team_id * 10 + 1,
                                 game_date=date(2026, 6, 25), status_state='final',
                                 opponent_team_id=142))
    for i, d in enumerate(('2026-06-26', '2026-06-27', '2026-06-28', '2026-06-29')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=team_id * 10 + 2 + i, game_date=date.fromisoformat(d),
            game_datetime=datetime(2026, 6, 26, 23, 10) if d == '2026-06-26' else None,
            status_state='scheduled', opponent_team_id=142, home_away='home'))
    db.session.commit()


# ── Miss -> build + store; hit -> served verbatim ─────────────────────────────

def test_miss_builds_and_stores_then_hit_serves_verbatim(app):
    with app.app_context():
        _seed_playing_stretch(116)
        assert read_snapshot(REF) is None

        first = serve_tonight_cached(REF)
        assert first['status'] == 'ok'
        assert first['card_count'] >= 1
        # Now stored.
        row = TonightIntelligenceSnapshot.query.filter_by(
            reference_date=REF, snapshot_version=TONIGHT_SNAPSHOT_VERSION).one()
        assert row.status == 'ok'
        assert row.card_count == first['card_count']
        assert row.source == 'on_demand'
        stored = read_snapshot(REF)
        assert stored['cards'] == first['cards']
        assert stored['snapshot']['source'] == 'on_demand'
        assert stored['snapshot']['generated_at']
        assert first['snapshot']['served_from'] == 'on_demand'

        # A hand-marked sentinel proves the second call is served from the cache.
        row.response_json = {**first, 'cards': [{**first['cards'][0], 'team_id': 999}]}
        db.session.commit()
        second = serve_tonight_cached(REF)
        assert second['cards'][0]['team_id'] == 999   # could only come from the cache
        assert second['snapshot']['served_from'] == 'snapshot'


def test_snapshot_hit_serves_cached_without_live_build(app, monkeypatch):
    with app.app_context():
        write_snapshot({'status': 'empty', 'reference_date': REF.isoformat(),
                        'cards': [], 'card_count': 0,
                        'empty_reason': 'no_cards_cleared_bar', 'limitations': []},
                       source='pregame_warm')

        def _unexpected(*a, **k):
            raise AssertionError('cache hit must not build live')

        monkeypatch.setattr(snap, '_run_live_build_with_timeout', _unexpected)

        out = serve_tonight_cached(REF)

    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_cards_cleared_bar'
    assert out['snapshot']['served_from'] == 'snapshot'
    assert out['snapshot']['source'] == 'pregame_warm'


# ── Stored shape matches the live contract; no strength stored ────────────────

def test_stored_response_matches_public_contract_without_strength(app):
    with app.app_context():
        _seed_playing_stretch(116)
        served = serve_tonight_cached(REF)
        live = serve_tonight(REF)

    assert set(served) == _CONTRACT_KEYS
    assert set(live) == _SERVICE_KEYS
    for card in served['cards']:
        assert set(card) == _CARD_KEYS
        assert card['pregame_story']['label'] == "Tonight's Bullpen Watch"
        assert 'strength' not in card
    # The stored JSON is exactly what was served, and carries no strength.
    blob = str(read_snapshot(REF))
    assert 'strength' not in blob


# ── Explicit reference_date ───────────────────────────────────────────────────

def test_explicit_reference_date_builds_and_caches(app):
    with app.app_context():
        _seed_playing_stretch(116)
        out = serve_tonight_cached(date(2026, 6, 26))
        assert out['reference_date'] == '2026-06-26'
        assert read_snapshot(date(2026, 6, 26)) is not None
        # A different date with no games (outside the seeded window) caches an
        # empty response.
        empty = serve_tonight_cached(date(2026, 7, 20))
        assert empty['status'] == 'empty'
        stored_empty = read_snapshot(date(2026, 7, 20))
        assert stored_empty['status'] == 'empty'
        assert stored_empty['snapshot']['source'] == 'on_demand'


# ── Empty responses are cached and round-trip ─────────────────────────────────

def test_empty_response_is_cached(app):
    with app.app_context():
        out = serve_tonight_cached(REF)   # no schedule rows at all
        assert out['status'] == 'empty'
        assert out['empty_reason'] == 'no_schedule_context'
        row = TonightIntelligenceSnapshot.query.filter_by(reference_date=REF).one()
        assert row.status == 'empty'
        assert row.card_count == 0
        again = serve_tonight_cached(REF)
        assert again['status'] == out['status']
        assert again['empty_reason'] == out['empty_reason']
        assert again['snapshot']['served_from'] == 'snapshot'


def test_snapshot_miss_live_build_timeout_returns_bounded_empty(app, monkeypatch):
    def _timeout(*a, **k):
        raise snap.TonightLiveBuildTimeout('too slow')

    monkeypatch.setattr(snap, '_run_live_build_with_timeout', _timeout)

    with app.app_context():
        out = serve_tonight_cached(REF, live_build_timeout_seconds=0.01)

    assert out['status'] == 'empty'
    assert out['empty_reason'] == snap.EMPTY_LIVE_BUILD_TIMEOUT
    assert out['cards'] == []
    assert out['card_count'] == 0
    assert out['limitations'] == ['Tonight watch is temporarily unavailable.']
    assert out['snapshot']['served_from'] == 'live_build_timeout'
    with app.app_context():
        assert TonightIntelligenceSnapshot.query.count() == 0


def test_snapshot_miss_live_build_exception_returns_bounded_empty(app, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError('builder exploded')

    monkeypatch.setattr(snap, '_run_live_build_with_timeout', _boom)

    with app.app_context():
        out = serve_tonight_cached(REF)

    assert out['status'] == 'empty'
    assert out['empty_reason'] == snap.EMPTY_SNAPSHOT_BUILD_UNAVAILABLE
    assert out['cards'] == []
    assert out['card_count'] == 0
    assert out['limitations'] == ['Tonight watch is temporarily unavailable.']
    assert out['snapshot']['served_from'] == 'live_build_failed'
    with app.app_context():
        assert TonightIntelligenceSnapshot.query.count() == 0


# ── Write failure does not break serving ──────────────────────────────────────

def test_write_failure_does_not_fail_serving(app, monkeypatch):
    with app.app_context():
        _seed_playing_stretch(116)

        def boom(*a, **k):
            raise RuntimeError('db down')
        monkeypatch.setattr(snap, 'write_snapshot', boom)

        out = serve_tonight_cached(REF)   # must still return a built response
        assert out['status'] == 'ok'
        # Nothing was stored, but the request succeeded.
        assert TonightIntelligenceSnapshot.query.count() == 0


def test_persist_false_does_not_store(app):
    with app.app_context():
        _seed_playing_stretch(116)
        serve_tonight_cached(REF, persist=False)
        assert read_snapshot(REF) is None


# ── Warming helper ────────────────────────────────────────────────────────────

def test_generate_snapshot_for_date_warms_cache(app):
    with app.app_context():
        _seed_playing_stretch(116)
        response = generate_tonight_snapshot_for_date(REF, source='pregame_warm')
        assert response['status'] == 'ok'
        assert response['snapshot']['served_from'] == 'pregame_warm'
        row = TonightIntelligenceSnapshot.query.filter_by(reference_date=REF).one()
        assert row.source == 'pregame_warm'
        assert row.generated_at is not None
        stored = read_snapshot(REF)
        assert stored['cards'] == response['cards']
        assert stored['snapshot']['source'] == 'pregame_warm'


def test_warming_overwrites_stale_no_schedule_context_snapshot(app):
    # Reproduces the production bug: a stale empty snapshot cached before schedule
    # rows existed must be overwritten once the schedule is ingested and warmed.
    with app.app_context():
        write_snapshot({'status': 'empty', 'reference_date': REF.isoformat(),
                        'cards': [], 'card_count': 0,
                        'empty_reason': 'no_schedule_context', 'limitations': []},
                       source='on_demand')
        assert read_snapshot(REF)['empty_reason'] == 'no_schedule_context'

        # Schedule arrives, then warm.
        _seed_playing_stretch(116)
        generate_tonight_snapshot_for_date(REF, source='tonight_refresh')

        refreshed = read_snapshot(REF)
        assert refreshed['status'] == 'ok'
        assert refreshed['empty_reason'] is None
        assert refreshed['card_count'] >= 1
        assert refreshed['snapshot']['source'] == 'tonight_refresh'
        # Still one row for the slate — overwritten in place, not duplicated.
        assert TonightIntelligenceSnapshot.query.filter_by(reference_date=REF).count() == 1


# ── write_snapshot hygiene ────────────────────────────────────────────────────

def test_write_snapshot_skips_when_no_reference_date(app):
    with app.app_context():
        row = write_snapshot({'status': 'empty', 'reference_date': None,
                              'cards': [], 'card_count': 0}, source='test')
        assert row is None
        assert TonightIntelligenceSnapshot.query.count() == 0


# ── Determinism ───────────────────────────────────────────────────────────────

def test_deterministic_served_response(app):
    with app.app_context():
        _seed_playing_stretch(116)
        first = serve_tonight_cached(REF)
    with app.app_context():
        second = serve_tonight_cached(REF)   # from snapshot now
    first_content = {k: v for k, v in first.items() if k != 'snapshot'}
    second_content = {k: v for k, v in second.items() if k != 'snapshot'}
    assert first_content == second_content
    assert first['snapshot']['served_from'] == 'on_demand'
    assert second['snapshot']['served_from'] == 'snapshot'


# ── Fail-closed: a read-level DB connection failure ───────────────────────────

def test_read_failure_propagates_and_skips_synchronous_rebuild(app, monkeypatch):
    """A connection-level read failure (SnapshotReadUnavailable) must propagate
    and must NOT fall through to the expensive synchronous serve_tonight build —
    a dead connection is not a cache miss."""
    from services.snapshot_read_guard import SnapshotReadUnavailable

    def _raise_unavailable(*a, **k):
        raise SnapshotReadUnavailable('tonight', REF, TONIGHT_SNAPSHOT_VERSION)

    built = {'called': False}

    def _track_build(*a, **k):
        built['called'] = True
        return {'status': 'ok', 'reference_date': REF.isoformat(), 'cards': [],
                'card_count': 0, 'empty_reason': None, 'limitations': []}

    monkeypatch.setattr(snap, 'read_snapshot_first', _raise_unavailable)
    monkeypatch.setattr(snap, 'serve_tonight', _track_build)

    with app.app_context():
        with pytest.raises(SnapshotReadUnavailable):
            serve_tonight_cached(REF)

    assert built['called'] is False
