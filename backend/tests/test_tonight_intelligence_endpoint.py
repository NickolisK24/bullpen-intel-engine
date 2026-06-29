"""Route tests for GET /api/bullpen/intelligence/tonight.

Exercises the HTTP layer over the real schedule path (seeded scheduled_games)
with a stubbed bullpen-context builder so the cards are deterministic without
roster data. Also confirms default/explicit reference dates, the 400 on a bad
date, empty states, public-card hygiene, and that /intelligence/today is
untouched.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
import services.tonight_intelligence_service as tonight_svc
import services.tonight_intelligence_snapshot as tonight_snap
import services.tonight_candidate_selection as tcs
from utils.db import db
from models.scheduled_game import ScheduledGame
import models.pitcher  # noqa: F401
import models.game_log  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import models.completed_game_context  # noqa: F401  (today endpoint table)
import models.intelligence_surface_snapshot  # noqa: F401  (today endpoint cache)
from api.bullpen import bullpen_bp

_FIXED_TODAY = date(2026, 6, 26)


def _pen(*, clean=1, band='thin', paths=2, conc='normal', share=40.0, name='Detroit Tigers'):
    return {
        'context_available': True, 'clean_options_count': clean,
        'optionality_band': band, 'practical_close_game_paths_count': paths,
        'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 1,
        'restricted_arms_count': 3, 'concentration_band': conc,
        'top_three_workload_share_10d': share, 'team_name': name,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    # Pin "today" so the default-date path is deterministic. The cache layer
    # resolves the date now, so pin it there (and on the builder for safety).
    monkeypatch.setattr(tonight_snap, 'product_current_date', lambda: _FIXED_TODAY)
    monkeypatch.setattr(tonight_svc, 'product_current_date', lambda: _FIXED_TODAY)
    # Stub the bullpen context so cards do not depend on roster seeding.
    monkeypatch.setattr(
        tcs, '_default_bullpen_context_builder',
        lambda team_id, reference_date: _pen(name=f'Team {team_id}'))
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


def _seed_playing_stretch(team_id=116, *, game_date=_FIXED_TODAY):
    # Two recent finals, then a multi-game stretch with no near off day.
    db.session.add(ScheduledGame(team_id=team_id, game_pk=team_id * 10 + 1,
                                 game_date=date(2026, 6, 24), status_state='final',
                                 opponent_team_id=142))
    db.session.add(ScheduledGame(team_id=team_id, game_pk=team_id * 10 + 2,
                                 game_date=date(2026, 6, 25), status_state='final',
                                 opponent_team_id=142))
    for i, d in enumerate(('2026-06-26', '2026-06-27', '2026-06-28', '2026-06-29')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=team_id * 10 + 3 + i, game_date=date.fromisoformat(d),
            game_datetime=datetime(2026, 6, 26, 23, 10) if d == '2026-06-26' else None,
            status_state='scheduled', opponent_team_id=142, home_away='home'))
    db.session.commit()


# ── 1 & 2. ok with cards, defaulting to product_current_date ──────────────────

def test_ok_with_cards_default_date(client):
    with client.application.app_context():
        _seed_playing_stretch(116)
    body = client.get('/api/bullpen/intelligence/tonight').get_json()
    assert body['status'] == 'ok'
    assert body['reference_date'] == '2026-06-26'
    assert body['card_count'] == len(body['cards']) >= 1
    assert body['cards'][0]['team_id'] == 116
    assert body['cards'][0]['signal_family'] == 'schedule_pressure'


# ── 3. Explicit reference date honored ────────────────────────────────────────

def test_explicit_reference_date(client):
    with client.application.app_context():
        _seed_playing_stretch(116)
    body = client.get('/api/bullpen/intelligence/tonight?reference_date=2026-06-26').get_json()
    assert body['reference_date'] == '2026-06-26'
    assert body['status'] == 'ok'


# ── 4. Invalid reference date -> 400 ──────────────────────────────────────────

def test_invalid_reference_date_returns_400(client):
    resp = client.get('/api/bullpen/intelligence/tonight?reference_date=not-a-date')
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == 'reference_date'


# ── 5 & 6. Empty states ───────────────────────────────────────────────────────

def test_empty_when_no_schedule_rows(client):
    body = client.get('/api/bullpen/intelligence/tonight').get_json()
    assert body['status'] == 'empty'
    assert body['empty_reason'] == 'no_schedule_context'
    assert body['cards'] == [] and body['card_count'] == 0


def test_empty_when_no_team_playing_today(client):
    with client.application.app_context():
        # A game yesterday and tomorrow, nothing on 2026-06-26.
        db.session.add(ScheduledGame(team_id=116, game_pk=991, game_date=date(2026, 6, 25),
                                     status_state='final', opponent_team_id=142))
        db.session.add(ScheduledGame(team_id=116, game_pk=992, game_date=date(2026, 6, 28),
                                     status_state='scheduled', opponent_team_id=142))
        db.session.commit()
    body = client.get('/api/bullpen/intelligence/tonight').get_json()
    assert body['status'] == 'empty'
    assert body['empty_reason'] == 'no_teams_playing_today'


# ── 7 & 8. Public card hygiene ────────────────────────────────────────────────

def test_public_cards_omit_strength_and_include_public_fields(client):
    with client.application.app_context():
        _seed_playing_stretch(116)
    card = client.get('/api/bullpen/intelligence/tonight').get_json()['cards'][0]
    assert 'strength' not in card
    for key in ('team_id', 'team_name', 'headline', 'summary', 'signal_type',
                'signal_family', 'pregame_story', 'evidence', 'schedule_context',
                'bullpen_context', 'limitations'):
        assert key in card
    assert card['pregame_story']['label'] == "Tonight's Bullpen Watch"
    assert card['pregame_story']['watching'].startswith('BaseballOS is watching')


# ── Public-copy polish: served cards are team-neutral in prose ────────────────

def test_served_cards_do_not_put_team_name_in_prose(client, monkeypatch):
    # A plural team name must not become the grammatical subject of the copy.
    monkeypatch.setattr(
        tcs, '_default_bullpen_context_builder',
        lambda team_id, reference_date: _pen(name='Chicago Cubs', clean=1, band='thin'))
    with client.application.app_context():
        _seed_playing_stretch(116)
    cards = client.get('/api/bullpen/intelligence/tonight').get_json()['cards']
    assert cards
    for card in cards:
        assert card['team_name'] == 'Chicago Cubs'        # name on the card
        assert 'Chicago Cubs' not in card['headline']      # never in the prose
        assert 'Chicago Cubs' not in card['summary']


# ── 10. No ranking / recommendation language ──────────────────────────────────

def test_endpoint_response_has_no_forbidden_language(client):
    with client.application.app_context():
        _seed_playing_stretch(116)
        _seed_playing_stretch(118)
    body = client.get('/api/bullpen/intelligence/tonight').get_json()
    blob = str(body).lower()
    for term in ('will win', 'will lose', 'guaranteed', 'probability', 'odds',
                 'recommend', 'ranked', 'ranking', 'predict', 'projection',
                 'best option', 'pick', 'edge', 'fatigue score',
                 'confidence score', 'will happen', 'expected to happen',
                 'healthy', 'injury-free'):
        assert term not in blob, term


# ── 15. Deterministic ─────────────────────────────────────────────────────────

def test_deterministic_response(client):
    with client.application.app_context():
        _seed_playing_stretch(116)
    first = client.get('/api/bullpen/intelligence/tonight').get_json()
    second = client.get('/api/bullpen/intelligence/tonight').get_json()
    assert first == second


# ── 12. /intelligence/today behavior unchanged ────────────────────────────────

def test_today_endpoint_still_returns_its_own_contract(client):
    # With no completed-game contexts, today returns its honest empty envelope —
    # a different shape than tonight (lead_story vs cards), proving separation.
    body = client.get('/api/bullpen/intelligence/today').get_json()
    assert 'lead_story' in body
    assert 'cards' not in body
    assert body['status'] == 'empty'
    assert body['empty_reason'] == 'no_completed_game_contexts'


# ── Fail-closed: a snapshot read connection failure ───────────────────────────

def test_read_failure_returns_honest_503_without_leaking_db_error(client, monkeypatch):
    """A SnapshotReadUnavailable from the cache read surfaces as the existing
    honest 503 envelope — no rebuild, no raw DB error in the public JSON."""
    import api.bullpen as bullpen_api
    from services.snapshot_read_guard import SnapshotReadUnavailable

    def _raise(*a, **k):
        raise SnapshotReadUnavailable('tonight', _FIXED_TODAY, 'tonight_v1')

    monkeypatch.setattr(bullpen_api, 'serve_tonight_cached', _raise)

    resp = client.get('/api/bullpen/intelligence/tonight')
    assert resp.status_code == 503
    body = resp.get_json()
    assert set(body) >= {'status', 'reference_date', 'cards', 'card_count',
                         'empty_reason', 'limitations'}
    assert body['status'] == 'error'
    assert body['cards'] == []
    assert body['card_count'] == 0

    raw = resp.get_data(as_text=True)
    for leak in ('SSL SYSCALL', 'OperationalError', 'SnapshotReadUnavailable', 'Traceback'):
        assert leak not in raw
