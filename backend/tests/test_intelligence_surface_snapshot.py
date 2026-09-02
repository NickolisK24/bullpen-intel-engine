"""Tests for the Intelligence Surface snapshot layer (performance).

The snapshot layer caches the GET /api/bullpen/intelligence/today response per
slate and serves it back quickly, falling back to live generation when no
snapshot exists. These cover: a present snapshot is served verbatim, the served
shape matches the live contract, a missing snapshot falls back and is then
stored, explicit reference_date still works, the empty state round-trips, and the
future-date default cap still holds through the cache. Everything is DB-backed
and read-only against COIN gates — no story data is invented.
"""

import logging
from datetime import date

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.intelligence_surface_service as surface_service
from services import bullpen_context as bullpen_context_service
from services import intelligence_surface_snapshot as snap
from services.intelligence_surface_snapshot import (
    EMPTY_LEAD_STORY_UNAVAILABLE,
    SNAPSHOT_VERSION,
    generate_snapshot_for_date,
    read_snapshot,
    serve_today_lead_story,
    write_snapshot,
)
from utils.db import db
from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
from models.pitcher import Pitcher
from models.play_by_play_foundation import (
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
)
import models.prospect  # noqa: F401  (full model registry for create_all)
from api.bullpen import bullpen_bp

_FIXED_TODAY = date(2026, 6, 26)
_REF = date(2026, 6, 25)
_FUTURE = date(2026, 7, 23)

_CONTRACT_KEYS = {
    'status', 'reference_date', 'lead_story',
    'candidates_considered', 'publishable_candidates', 'errors', 'empty_reason',
}
_PUBLIC_CONTRACT_KEYS = _CONTRACT_KEYS | {'freshness'}


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
        home_away='home',
        bullpen_entry_inning=7, bullpen_entry_score_for=6, bullpen_entry_score_against=2,
        lead_when_bullpen_entered=4, largest_lead=4, largest_deficit=3,
        final_score_for=6, final_score_against=9,
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
    pitcher = _seed_relief_appearance(row, runs_allowed=row.late_runs_allowed or 1)
    _seed_lost_lead_pbp(row, pitcher)
    return row


def _seed_relief_appearance(context, *, runs_allowed, index=0):
    pitcher = Pitcher(
        mlb_id=context.team_id * 1_000_000 + context.game_pk + index,
        full_name=f'Claim Reliever {context.team_id}-{index + 1}',
        team_id=context.team_id,
        team_abbreviation='TST',
    )
    db.session.add(pitcher)
    db.session.flush()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=context.game_pk,
        game_date=context.game_date,
        game_type='R',
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=15,
        runs_allowed=runs_allowed,
        appearance_team_id=context.team_id,
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_source='test_official_game_side',
    ))
    db.session.commit()
    return pitcher


def _seed_lost_lead_pbp(context, pitcher):
    opponent_id = context.team_id + 1
    endpoint = f'/api/v1.1/game/{context.game_pk}/feed/live'
    db.session.add(PlayByPlayProcessedGame(
        mlb_game_pk=context.game_pk,
        game_date=context.game_date,
        game_type='R',
        home_team_id=context.team_id,
        away_team_id=opponent_id,
        final_state='Final',
        processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
        attempt_count=1,
        events_seen=2,
        events_stored=2,
        pitcher_events_seen=1,
        unresolved_pitcher_count=0,
        reconciliation_mismatch_count=0,
        event_fingerprint=f'pbp-{context.game_pk}',
        source='test_final_play_by_play',
        source_endpoint=endpoint,
    ))
    common = {
        'mlb_game_pk': context.game_pk,
        'game_date': context.game_date,
        'game_type': 'R',
        'home_team_id': context.team_id,
        'away_team_id': opponent_id,
        'outs_at_event': 1,
        'batter_mlb_id': 800001,
        'is_pitching_change': False,
        'is_mound_visit': False,
        'source': 'test_final_play_by_play',
        'source_endpoint': endpoint,
    }
    db.session.add(GamePlayByPlayEvent(
        **common,
        event_index=0,
        source_play_id=f'play-{context.game_pk}-0',
        at_bat_index=0,
        event_type='scoring_play',
        event_type_code='home_run',
        inning=6,
        half_inning='bottom',
        is_top_inning=False,
        home_score_at_event=context.bullpen_entry_score_for,
        away_score_at_event=context.bullpen_entry_score_against,
        batting_team_id=context.team_id,
        fielding_team_id=opponent_id,
        is_scoring_play=True,
    ))
    db.session.add(GamePlayByPlayEvent(
        **common,
        event_index=1,
        source_play_id=f'play-{context.game_pk}-1',
        at_bat_index=1,
        event_type='scoring_play',
        event_type_code='double',
        inning=context.turning_inning,
        half_inning='top',
        is_top_inning=True,
        home_score_at_event=context.final_score_for,
        away_score_at_event=context.final_score_against,
        pitcher_mlb_id=pitcher.mlb_id,
        pitcher_id=pitcher.id,
        batting_team_id=opponent_id,
        fielding_team_id=context.team_id,
        is_scoring_play=True,
    ))
    db.session.commit()


def _seed_low_confidence(team_id, game_pk, game_date=_REF):
    # Boxscore-only -> LOW -> insufficient_context -> not publishable.
    row = CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=game_date,
        bullpen_story_tag='insufficient_context', confidence='LOW')
    db.session.add(row)
    db.session.commit()
    return row


def _seed_burke_tied_handoff(game_date=_REF):
    row = CompletedGameContext(
        team_id=145,
        game_pk=824822,
        game_date=game_date,
        bullpen_story_tag='bullpen_kept_team_alive',
        confidence='HIGH',
        starter_name='Sean Burke',
        starter_ip=16 / 3,
        starter_pitch_count=89,
        starter_exit_inning=6,
        starter_exit_score_for=2,
        starter_exit_score_against=2,
        bullpen_entry_inning=6,
        bullpen_entry_score_for=2,
        bullpen_entry_score_against=2,
        lead_when_bullpen_entered=None,
        deficit_when_bullpen_entered=None,
        largest_lead=6,
        largest_deficit=1,
        late_runs_allowed=0,
        runs_allowed_innings_7_to_9=0,
        lead_protected=None,
        lead_lost=None,
        comeback_completed=True,
        turning_inning=3,
        game_shape_created='normal_start',
    )
    db.session.add(row)
    db.session.commit()
    # Six evenly-used relievers keep the unrelated concentration snapshot from
    # adding a negative consequence to this positive-story regression fixture.
    for index in range(6):
        _seed_relief_appearance(row, runs_allowed=0, index=index)
    return row


def _team_context_with_optionality(team_id, optionality_band):
    return {
        'team_id': team_id,
        'reference_date': _REF.isoformat(),
        'data_through_date': _REF.isoformat(),
        'bullpen_optionality_context': {
            'context_available': True,
            'optionality_band': optionality_band,
            'available_arms_count': 6,
            'clean_workload_options': [],
            'secondary_options': [],
        },
        'bullpen_concentration_context': {
            'context_available': True,
            'concentration_band': 'normal',
        },
        'rotation_context': {},
        'role_stability_context': {},
        'injury_context': {},
    }


def _stale_burke_response(reference_date):
    return {
        'status': 'ok',
        'reference_date': reference_date.isoformat(),
        'lead_story': {
            'team_id': 145,
            'game_pk': 824822,
            'package': {},
            'drafts': {
                'team_story': {
                    'writer': 'team_story',
                    'headline': 'Bullpen kept it alive',
                    'body': (
                        "After their most recent game, Sean Burke's 5.3 innings "
                        'left a one-run deficit to erase, but the bullpen kept '
                        'it from growing. The offense finished the rally.'
                    ),
                    'evidence': ['Starter: Sean Burke, 5.3 IP, 89 pitches'],
                    'rendered_text': (
                        "Bullpen kept it alive\n\nAfter their most recent game, "
                        "Sean Burke's 5.3 innings left a one-run deficit to "
                        'erase, but the bullpen kept it from growing.\n\n'
                        'Evidence:\n- Starter: Sean Burke, 5.3 IP, 89 pitches'
                    ),
                },
            },
            'selection': {'rank': 1},
        },
        'candidates_considered': 1,
        'publishable_candidates': 1,
        'errors': 0,
        'empty_reason': None,
    }


def _insert_snapshot_row(reference_date, *, version, response):
    row = IntelligenceSurfaceSnapshot(
        reference_date=reference_date,
        snapshot_version=version,
        status=response.get('status'),
        response_json=response,
        lead_story_team_id=145,
        lead_story_game_pk=824822,
        candidates_considered=response.get('candidates_considered') or 0,
        publishable_candidates=response.get('publishable_candidates') or 0,
        empty_reason=response.get('empty_reason'),
        errors=response.get('errors') or 0,
        source='stale_test_fixture',
    )
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
    return read_snapshot(reference_date)


def _lead_blob(response):
    lead = (response or {}).get('lead_story') or {}
    drafts = lead.get('drafts') or {}
    return ' '.join(
        ' '.join(str(draft.get(key) or '') for key in ('headline', 'body', 'rendered_text'))
        for draft in drafts.values()
        if isinstance(draft, dict)
    )


def test_snapshot_fingerprint_covers_today_gate_and_live_evidence_sources():
    covered = set(snap._FINGERPRINTED_SOURCE_FILES)
    assert {
        'services/daily_edition_publication_gate.py',
        'services/intelligence_surface_service.py',
        'services/today_relief_appearance_evidence.py',
    } <= covered


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
    assert set(served) == _PUBLIC_CONTRACT_KEYS
    assert set(again) == _PUBLIC_CONTRACT_KEYS
    # Cache round-trips the exact bytes the builder produced.
    assert again == served
    # Same contract shape as a live build (deep values differ only by the
    # per-build generated_at timestamp inside the package, not by structure).
    assert set(served['lead_story']) == set(live['lead_story'])
    assert set(served['lead_story']['drafts']) == set(live['lead_story']['drafts'])
    assert served['lead_story']['selection'] == live['lead_story']['selection']
    assert served['freshness']['slate_coverage']['complete_enough_to_publish'] is False


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
        assert row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION
        assert row.response_json['_snapshot_metadata']['story_writer_fingerprint']
        assert '_snapshot_metadata' not in stored


def test_claim_evidence_gap_is_not_cached_and_recovers_after_receipt_arrives(app):
    with app.app_context():
        context = _seed_lost_game_shape(137, 137000)
        pitcher = Pitcher.query.filter_by(full_name='Claim Reliever 137-1').one()
        GameLog.query.delete(synchronize_session=False)
        db.session.commit()

        withheld = serve_today_lead_story(reference_date=_REF)
        assert withheld['status'] == 'empty'
        assert withheld['empty_reason'] == 'lead_story_withheld_claim_evidence'
        assert IntelligenceSurfaceSnapshot.query.count() == 0

        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=context.game_pk,
            game_date=context.game_date,
            game_type='R',
            games_started=0,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=15,
            runs_allowed=context.late_runs_allowed,
            appearance_team_id=context.team_id,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
            appearance_team_source='test_official_game_side',
        ))
        db.session.commit()

        recovered = serve_today_lead_story(reference_date=_REF)

    assert recovered['status'] == 'ok'
    assert recovered['lead_story']['team_id'] == 137


def test_cached_receipts_invalidate_when_authoritative_name_changes(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        first = serve_today_lead_story(reference_date=_REF)
        first_id = first['lead_story']['publication_identity']['publication_id']
        pitcher = Pitcher.query.filter_by(full_name='Claim Reliever 137-1').one()
        pitcher.full_name = 'Corrected Claim Reliever'
        db.session.commit()

        assert read_snapshot(_REF) is None
        corrected = serve_today_lead_story(reference_date=_REF)

    assert [
        item['name']
        for item in corrected['lead_story']['claim_evidence']['relief_appearances']
    ] == ['Corrected Claim Reliever']
    assert corrected['lead_story']['publication_identity']['publication_id'] != first_id


def test_cached_receipt_digest_treats_unknown_optional_fields_as_omitted(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        log = GameLog.query.filter_by(mlb_game_pk=137000).one()
        log.pitches_thrown = None
        log.runs_allowed = None
        db.session.commit()

        published = serve_today_lead_story(reference_date=_REF)
        evidence = published['lead_story']['claim_evidence']['relief_appearances']
        assert published['status'] == 'ok'
        assert 'pitches_thrown' not in evidence[0]
        assert 'runs_allowed' not in evidence[0]

        cached = read_snapshot(_REF)

    assert cached == published


def test_cached_positive_consequence_is_withheld_after_current_state_turns_negative(
    app,
    monkeypatch,
):
    current = {'optionality_band': 'flexible'}

    def _build_current_context(team_id, reference_date=None, **_kwargs):
        assert str(reference_date) == _REF.isoformat()
        return _team_context_with_optionality(
            team_id,
            current['optionality_band'],
        )

    monkeypatch.setattr(
        bullpen_context_service,
        'build_team_bullpen_context',
        _build_current_context,
    )

    with app.app_context():
        _seed_burke_tied_handoff()
        published = serve_today_lead_story(reference_date=_REF)
        assert published['status'] == 'ok', published
        assert (
            published['lead_story']['selection']['semantic_gate']['consequence_key']
            == 'late_inning_margin'
        )

        current['optionality_band'] = 'thin'
        assert read_snapshot(_REF) is None
        withheld = serve_today_lead_story(reference_date=_REF)

    assert withheld['status'] == 'empty'
    assert withheld['lead_story'] is None
    assert withheld['empty_reason'] == 'lead_story_withheld_claim_evidence'


def test_current_context_error_does_not_replace_recoverable_cached_lead(
    app,
    monkeypatch,
):
    current = {'unavailable': False}

    def _build_current_context(team_id, reference_date=None, **_kwargs):
        if current['unavailable']:
            raise RuntimeError('current bullpen context unavailable')
        return _team_context_with_optionality(team_id, 'flexible')

    monkeypatch.setattr(
        bullpen_context_service,
        'build_team_bullpen_context',
        _build_current_context,
    )

    with app.app_context():
        _seed_burke_tied_handoff()
        published = serve_today_lead_story(reference_date=_REF)
        assert published['status'] == 'ok'
        publication_id = published['lead_story']['publication_identity']['publication_id']

        current['unavailable'] = True
        failed = serve_today_lead_story(reference_date=_REF)
        stored = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()

        current['unavailable'] = False
        recovered = serve_today_lead_story(reference_date=_REF)

    assert failed['status'] == 'empty'
    assert failed['empty_reason'] == 'no_publishable_coin_story'
    assert failed['errors'] == 1
    assert stored.status == 'ok'
    assert (
        stored.response_json['lead_story']['publication_identity']['publication_id']
        == publication_id
    )
    assert recovered['status'] == 'ok'
    assert recovered['lead_story']['publication_identity']['publication_id'] == publication_id


def test_snapshot_miss_uses_bounded_regeneration_and_persists(app, monkeypatch):
    seen = {}
    response = {
        'status': 'ok',
        'reference_date': _REF.isoformat(),
        'lead_story': {
            'team_id': 137,
            'game_pk': 137000,
            'package': {},
            'drafts': {},
            'selection': {'rank': 1},
        },
        'candidates_considered': 2,
        'publishable_candidates': 2,
        'errors': 0,
        'empty_reason': None,
    }

    def _build(**kwargs):
        seen.update(kwargs)
        return response

    monkeypatch.setattr(snap, 'build_today_lead_story', _build)

    with app.app_context():
        result = serve_today_lead_story(reference_date=_REF)
        stored = read_snapshot(_REF)
        row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()

    for key in _CONTRACT_KEYS:
        assert result[key] == response[key]
    assert stored == result
    assert result['freshness']['complete_enough_to_publish'] is False
    assert seen['reference_date'] == _REF
    assert seen['bounded'] is True
    assert row.source == 'on_demand'
    assert row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION


def test_snapshot_regeneration_error_returns_safe_fallback(app, monkeypatch, caplog):
    def _boom(**kwargs):
        raise RuntimeError('writer exploded')

    monkeypatch.setattr(snap, 'build_today_lead_story', _boom)

    with app.app_context(), caplog.at_level(logging.ERROR):
        result = serve_today_lead_story(reference_date=_REF)

    assert {
        key: result[key]
        for key in _CONTRACT_KEYS
    } == {
        'status': 'empty',
        'reference_date': _REF.isoformat(),
        'lead_story': None,
        'candidates_considered': 0,
        'publishable_candidates': 0,
        'errors': 1,
        'empty_reason': EMPTY_LEAD_STORY_UNAVAILABLE,
    }
    assert result['freshness']['complete_enough_to_publish'] is False
    assert read_snapshot(_REF) is None
    assert 'Intelligence surface snapshot regeneration failed' in caplog.text
    assert 'writer exploded' in caplog.text


def test_persist_false_does_not_store(app):
    with app.app_context():
        _seed_lost_game_shape(137, 137000)
        serve_today_lead_story(reference_date=_REF, persist=False)
        assert read_snapshot(_REF) is None


def test_old_writer_version_snapshot_is_not_served_and_is_rebuilt(app):
    with app.app_context():
        _seed_burke_tied_handoff()
        stale = _stale_burke_response(_REF)
        _insert_snapshot_row(
            _REF,
            version='intelligence_surface_v1',
            response=stale,
        )

        result = serve_today_lead_story(reference_date=_REF)

        blob = _lead_blob(result).lower()
        assert result['lead_story']['team_id'] == 145
        assert '5.1 innings' in blob
        assert '5.1 ip' in str(result['lead_story']['drafts']).lower()
        assert 'tied game' in blob
        assert '5.3' not in blob
        assert 'one-run deficit to erase' not in blob

        stale_row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version='intelligence_surface_v1',
        ).one()
        current_row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()
        assert stale_row.response_json == stale
        assert current_row.source == 'on_demand'
        assert current_row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION


def test_june_29_reference_date_regenerates_current_burke_story(app):
    june_29 = date(2026, 6, 29)
    with app.app_context():
        _seed_burke_tied_handoff(game_date=june_29)
        _insert_snapshot_row(
            june_29,
            version='intelligence_surface_v1',
            response=_stale_burke_response(june_29),
        )

        result = serve_today_lead_story(reference_date=june_29)

        blob = _lead_blob(result).lower()
        assert result['reference_date'] == '2026-06-29'
        assert result['lead_story']['team_id'] == 145
        assert '5.1 innings' in blob
        assert 'tied game' in blob
        assert '5.3' not in blob
        assert 'one-run deficit to erase' not in blob
        row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=june_29,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()
        assert row.source == 'on_demand'
        assert row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION


def test_current_version_snapshot_missing_metadata_is_not_served(app):
    with app.app_context():
        _seed_burke_tied_handoff()
        _insert_snapshot_row(
            _REF,
            version=SNAPSHOT_VERSION,
            response=_stale_burke_response(_REF),
        )

        assert read_snapshot(_REF) is None
        result = serve_today_lead_story(reference_date=_REF)

        blob = _lead_blob(result).lower()
        assert '5.1 innings' in blob
        assert 'tied game' in blob
        assert 'one-run deficit to erase' not in blob
        row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()
        assert row.source == 'on_demand'
        assert row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION
        assert '5.3 innings' not in str(row.response_json).lower()


def test_snapshot_refresh_overwrites_stale_completed_game_story(app):
    with app.app_context():
        _seed_burke_tied_handoff()
        _insert_snapshot_row(
            _REF,
            version=SNAPSHOT_VERSION,
            response=_stale_burke_response(_REF),
        )

        result = generate_snapshot_for_date(_REF, source='test_refresh')

        blob = _lead_blob(result).lower()
        assert '5.1 innings' in blob
        assert 'tied game' in blob
        assert '5.3' not in blob
        assert 'one-run deficit to erase' not in blob
        row = IntelligenceSurfaceSnapshot.query.filter_by(
            reference_date=_REF,
            snapshot_version=SNAPSHOT_VERSION,
        ).one()
        assert row.source == 'test_refresh'
        assert row.response_json['_snapshot_metadata']['snapshot_version'] == SNAPSHOT_VERSION
        assert '5.3 innings' not in str(row.response_json).lower()


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
