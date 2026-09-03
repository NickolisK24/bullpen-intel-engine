"""F-004 purpose-built public delivery from one trusted publication."""

from copy import deepcopy
from datetime import date, datetime
import json
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

import api.bullpen as bullpen_api
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import dashboard_snapshot
from services.mlb_club_directory import MLB_CLUBS
from services.public_surface_projections import (
    HOME_PAYLOAD_KEYS,
    build_home_projection,
    build_league_projection,
    build_stories_projection,
    build_trust_projection,
)
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_CONTRACT
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


DATA_THROUGH = date(2026, 9, 1)
REFERENCE_DATE = date(2026, 9, 2)


def _snapshot():
    payload = {
        'freshness': {
            'data_through': DATA_THROUGH.isoformat(),
            'availability_reference_date': REFERENCE_DATE.isoformat(),
            'freshness_state': 'current',
            'is_current': True,
        },
        'landscape': {'stored': 'validated by injected landscape builder'},
        'what_changed_since_yesterday': {
            'state': 'changes_detected',
            'comparison': {'current_data_through': DATA_THROUGH.isoformat()},
            'items': [{'team_id': 108, 'headline': 'Published movement.'}],
        },
        'stories': {
            'items': [{
                'story_id': 'story-1',
                'team_id': 108,
                'headline': 'Governed published story.',
                'claim_evidence': {'status': 'supported'},
            }],
            'league_context': {'headline': 'Published league context.'},
        },
        'today_flagship': {'story_id': 'story-1', 'team_id': 108},
        'roles': {'counts': {'setup': 12, 'middle': 40}},
        'injury_il_context': {
            'league': {'injured_list_count': 8, 'inactive_count': 3},
        },
        'roster_readiness': {'claims_available': True},
        # The dominant compatibility carrier must never enter a projection.
        'trusted_team_boards': {'large': ['unused'] * 100},
        'performance': {'large': ['unused'] * 100},
    }
    return SimpleNamespace(
        id=1878,
        sync_run_id=2870,
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
        is_published=True,
        published_at=datetime(2026, 9, 2, 10, 8, 45),
        payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        data_through=DATA_THROUGH,
        availability_reference_date=REFERENCE_DATE,
        snapshot_generated_at=datetime(2026, 9, 2, 10, 8, 44),
        payload=payload,
    )


def _listing(snapshot):
    labels = ('Fresh', 'Stretched', 'Vulnerable')
    teams = []
    for index, club in enumerate(MLB_CLUBS):
        label = labels[index % len(labels)]
        teams.append({
            'team_id': club.team_id,
            'team_abbreviation': club.abbreviation,
            'team_name': club.team_name,
            'team_state': {
                'contract': PUBLIC_TEAM_STATE_CONTRACT,
                'available': True,
                'public_state': label.lower(),
                'public_label': label,
                'data_through': DATA_THROUGH.isoformat(),
            },
        })
    return {
        'capability': 'league_team_state_listing_v1',
        'status': 'ok',
        'expected_team_count': 30,
        'team_count': 30,
        'represented_team_count': 30,
        'teams': teams,
        'freshness': deepcopy(snapshot.payload['freshness']),
        'publication_authority': {'snapshot_id': snapshot.id},
    }


def _landscape(snapshot, **kwargs):
    if 'team_state_listing_builder' in kwargs:
        listing = kwargs['team_state_listing_builder']()
        assert listing['publication_authority']['snapshot_id'] == snapshot.id
    return {
        'capability': 'tonights_bullpen_landscape',
        'status': 'ok',
        'teams_evaluated': 30,
        'constrained_bullpens': [{'team_id': 108, 'team_state': {'public_label': 'Vulnerable'}}],
        'available_bullpens': [{'team_id': 109, 'team_state': {'public_label': 'Fresh'}}],
        'monitoring_concentration': [{'team_id': 110, 'team_state': {'public_label': 'Stretched'}}],
        'storylines': [{'headline': 'Published Landscape storyline.'}],
        'freshness': deepcopy(snapshot.payload['freshness']),
        'publication_authority': {'snapshot_id': snapshot.id},
        'snapshot': {'snapshot_id': snapshot.id},
    }


@pytest.fixture(autouse=True)
def _trusted_snapshot(monkeypatch):
    monkeypatch.setattr(
        dashboard_snapshot,
        'snapshot_unavailable_reason',
        lambda snapshot, **_kwargs: (
            None if snapshot is not None else 'dashboard_snapshot_missing'
        ),
    )


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_api.bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _freshness(*, snapshot):
    return deepcopy(snapshot.payload['freshness'])


def test_home_projection_preserves_visible_fields_and_omits_deep_carriers():
    snapshot = _snapshot()
    result = build_home_projection(
        snapshot,
        landscape_builder=_landscape,
        freshness_builder=_freshness,
    )

    assert result['status'] == 'ok'
    assert result['snapshot']['snapshot_id'] == snapshot.id
    assert result['publication_authority']['snapshot_id'] == snapshot.id
    assert result['freshness'] == snapshot.payload['freshness']
    assert result['what_changed_since_yesterday'] == snapshot.payload['what_changed_since_yesterday']
    assert result['landscape']['snapshot']['snapshot_id'] == snapshot.id
    assert 'trusted_team_boards' not in result
    assert 'performance' not in result


def test_league_projection_is_one_30_team_publication_projection():
    snapshot = _snapshot()
    listing_calls = []

    def listing_builder(**kwargs):
        selected, reason = kwargs['snapshot_resolver']()
        assert selected is snapshot
        assert reason is None
        listing_calls.append(selected.id)
        return _listing(snapshot)

    result = build_league_projection(
        snapshot,
        team_state_listing_builder=listing_builder,
        landscape_builder=_landscape,
        freshness_builder=_freshness,
    )

    rows = result['team_states']['teams']
    assert listing_calls == [snapshot.id]
    assert len(rows) == len({row['team_id'] for row in rows}) == 30
    assert {row['team_state']['public_label'] for row in rows} == {
        'Fresh', 'Stretched', 'Vulnerable',
    }
    assert result['snapshot']['snapshot_id'] == snapshot.id
    assert result['landscape']['snapshot']['snapshot_id'] == snapshot.id
    assert result['roles'] == snapshot.payload['roles']
    assert result['injury_il_context'] == snapshot.payload['injury_il_context']
    assert result['roster_readiness'] == snapshot.payload['roster_readiness']
    assert set(result['landscape']) <= {
        'capability', 'status', 'reason', 'storylines', 'freshness',
        'publication_authority', 'snapshot',
    }


def test_stories_projection_preserves_governed_story_bytes():
    snapshot = _snapshot()
    result = build_stories_projection(snapshot, freshness_builder=_freshness)

    assert result['stories'] == snapshot.payload['stories']
    assert result['today_flagship'] == snapshot.payload['today_flagship']
    assert json.dumps(result['stories'], sort_keys=True) == json.dumps(
        snapshot.payload['stories'], sort_keys=True,
    )
    assert result['snapshot']['snapshot_id'] == snapshot.id


def test_trust_projection_carries_only_publication_currentness():
    snapshot = _snapshot()
    result = build_trust_projection(snapshot, freshness_builder=_freshness)

    assert set(result) == {
        'capability', 'version', 'status', 'ranking_applied',
        'selection_made', 'prediction_applied', 'publication_authority',
        'snapshot', 'freshness',
    }
    assert result['freshness'] == snapshot.payload['freshness']
    assert result['snapshot']['snapshot_id'] == snapshot.id


def test_all_projections_expose_the_same_selected_publication_identity():
    snapshot = _snapshot()
    projections = (
        build_home_projection(
            snapshot,
            landscape_builder=_landscape,
            freshness_builder=_freshness,
        ),
        build_league_projection(
            snapshot,
            team_state_listing_builder=lambda **_kwargs: _listing(snapshot),
            landscape_builder=_landscape,
            freshness_builder=_freshness,
        ),
        build_stories_projection(snapshot, freshness_builder=_freshness),
        build_trust_projection(snapshot, freshness_builder=_freshness),
    )

    identities = [projection['snapshot'] for projection in projections]
    assert all(identity == identities[0] for identity in identities)
    assert all(
        projection['publication_authority']['snapshot_id'] == snapshot.id
        for projection in projections
    )


@pytest.mark.parametrize(
    ('builder', 'dependent_field'),
    [
        (build_home_projection, 'what_changed_since_yesterday'),
        (build_stories_projection, 'stories'),
    ],
)
def test_missing_publication_fails_closed_without_live_substitute(builder, dependent_field):
    result = builder(None, unavailable_reason='trusted_publication_unavailable')

    assert result['status'] == 'snapshot_unavailable'
    assert result['snapshot']['snapshot_id'] is None
    assert result['publication_authority'] is None
    assert result[dependent_field] is None


def test_missing_publication_fails_closed_for_league_and_trust():
    league = build_league_projection(
        None,
        unavailable_reason='trusted_publication_unavailable',
    )
    trust = build_trust_projection(
        None,
        unavailable_reason='trusted_publication_unavailable',
    )

    assert league['status'] == 'snapshot_unavailable'
    assert league['team_states']['status'] == 'snapshot_unavailable'
    assert league['landscape']['status'] == 'snapshot_unavailable'
    assert trust['status'] == 'snapshot_unavailable'
    assert trust['snapshot']['snapshot_id'] is None


def test_projection_failure_does_not_change_other_projection_semantics():
    snapshot = _snapshot()

    def broken_landscape(_snapshot):
        raise RuntimeError('isolated home projection failure')

    with pytest.raises(RuntimeError):
        build_home_projection(snapshot, landscape_builder=broken_landscape)

    stories = build_stories_projection(snapshot, freshness_builder=_freshness)
    trust = build_trust_projection(snapshot, freshness_builder=_freshness)
    assert stories['stories'] == snapshot.payload['stories']
    assert trust['freshness'] == snapshot.payload['freshness']


def test_projection_source_has_no_semantic_calculators():
    source = (
        __import__('pathlib').Path(__file__).resolve().parents[1]
        / 'services' / 'public_surface_projections.py'
    ).read_text(encoding='utf-8')

    for forbidden in (
        'classify_availability',
        'canonical_team_state(',
        'build_landscape(',
        'current_availability_records',
        'build_canonical_story_feed',
    ):
        assert forbidden not in source


def test_routes_select_one_publication_and_keep_dashboard_compatibility(client, monkeypatch):
    snapshot = _snapshot()
    selections = []

    selected_keys = []

    def select_once(payload_keys):
        selections.append(snapshot.id)
        selected_keys.append(tuple(payload_keys))
        return snapshot, None

    monkeypatch.setattr(bullpen_api, 'select_trusted_publication', select_once)
    monkeypatch.setattr(
        bullpen_api,
        'build_home_projection',
        lambda selected, unavailable_reason=None: {
            'status': 'ok',
            'snapshot': {'snapshot_id': selected.id},
        },
    )

    response = client.get('/api/bullpen/home')
    assert response.status_code == 200
    assert response.get_json()['snapshot']['snapshot_id'] == snapshot.id
    assert selections == [snapshot.id]
    assert selected_keys == [HOME_PAYLOAD_KEYS]
    assert '/api/bullpen/dashboard' in {rule.rule for rule in client.application.url_map.iter_rules()}


def test_publication_projection_exposes_stable_etag_and_honors_revalidation(client, monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(
        bullpen_api,
        'select_trusted_publication',
        lambda _payload_keys: (snapshot, None),
    )
    monkeypatch.setattr(
        bullpen_api,
        'build_home_projection',
        lambda selected, unavailable_reason=None: {
            'capability': 'public_home_projection_v1',
            'version': '1.0.0',
            'status': 'ok',
            'snapshot': {
                'snapshot_id': selected.id,
                'sync_run_id': selected.sync_run_id,
                'represented_date': selected.data_through.isoformat(),
                'payload_version': selected.payload_version,
            },
        },
    )

    first = client.get('/api/bullpen/home')
    validator = first.headers['ETag']
    second = client.get('/api/bullpen/home', headers={'If-None-Match': validator})

    assert first.status_code == 200
    assert first.headers['Cache-Control'] == 'public, max-age=0, must-revalidate'
    assert first.headers['X-BaseballOS-Snapshot-ID'] == str(snapshot.id)
    assert second.status_code == 304
    assert second.data == b''
    assert second.headers['ETag'] == validator


def test_unavailable_projection_is_never_cached_as_current(client, monkeypatch):
    monkeypatch.setattr(
        bullpen_api,
        'select_trusted_publication',
        lambda _payload_keys: (None, 'trusted_publication_unavailable'),
    )

    response = client.get('/api/bullpen/trust')

    assert response.status_code == 200
    assert response.get_json()['status'] == 'snapshot_unavailable'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'ETag' not in response.headers


def test_all_projection_routes_are_registered(client):
    rules = {rule.rule for rule in client.application.url_map.iter_rules()}
    assert {
        '/api/bullpen/home',
        '/api/bullpen/league',
        '/api/bullpen/stories',
        '/api/bullpen/trust',
    } <= rules


def test_projection_snapshot_query_reads_only_requested_json_domains(client):
    source = _snapshot()
    run = SyncRun(job_name='public_surface_projection_test', status='success')
    db.session.add(run)
    db.session.flush()
    record = DashboardSnapshot(
        snapshot_type=source.snapshot_type,
        sync_run_id=run.id,
        status=source.status,
        is_published=source.is_published,
        published_at=source.published_at,
        payload=deepcopy(source.payload),
        payload_version=source.payload_version,
        data_through=source.data_through,
        availability_reference_date=source.availability_reference_date,
        snapshot_generated_at=source.snapshot_generated_at,
        source='test',
    )
    db.session.add(record)
    db.session.commit()
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        selected = dashboard_snapshot.get_latest_valid_dashboard_snapshot_projection(
            ('stories',)
        )
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)

    assert selected.id == record.id
    assert set(selected.payload) == {'freshness', 'stories'}
    assert 'trusted_team_boards' not in selected.payload
    assert len(statements) == 1
    assert 'payload' in statements[0].lower()
