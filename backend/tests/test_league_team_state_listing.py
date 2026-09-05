"""D-054 governed 30-club Team State listing contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

import api.bullpen as bullpen_api
from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
import services.league_team_state_listing as listing
import services.board_freshness as board_freshness
import services.published_team_state as projection
import services.public_serving_authority as serving
from services.mlb_club_directory import (
    EXPECTED_CLUB_COUNT,
    MLB_CLUBS,
    MLB_TEAM_IDS,
)
from services.snapshot_read_guard import SnapshotReadUnavailable
from services.team_assignment_sync import MLB_TEAM_IDS as ASSIGNMENT_TEAM_IDS
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


DATA_THROUGH = date(2026, 8, 14)
GENERATED_AT = '2026-08-15T12:00:00+00:00'
REPO_ROOT = Path(__file__).resolve().parents[2]


def _snapshot():
    return SimpleNamespace(
        id=411,
        sync_run_id=721,
        data_through=DATA_THROUGH,
        availability_reference_date=DATA_THROUGH,
        snapshot_generated_at=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
        published_at=datetime(2026, 8, 15, 2, 5, tzinfo=timezone.utc),
        payload={
            'freshness': {
                'data_through': DATA_THROUGH.isoformat(),
                'freshness_state': 'current',
                'is_current': True,
            },
        },
    )


def _artifact(
    team_id,
    status_code='operationally_stable',
    *,
    artifact_id=1,
    published_at=None,
    lifecycle_state='published',
    snapshot_id=411,
    sync_run_id=721,
    data_through=DATA_THROUGH.isoformat(),
):
    return SimpleNamespace(
        id=artifact_id,
        public_id=f'artifact-{team_id}-{artifact_id}',
        team_id=team_id,
        lifecycle_state=lifecycle_state,
        source_snapshot_id=snapshot_id,
        source_sync_run_id=sync_run_id,
        published_at=published_at or datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
        payload={
            'team_state': {
                'contract_state': 'published',
                'status_code': status_code,
            },
            'authority': {'data_through': data_through},
        },
    )


def _build(artifacts=(), *, directory=None, snapshot=None):
    snapshot = snapshot or _snapshot()
    return listing.build_league_team_state_listing(
        generated_at=GENERATED_AT,
        snapshot_resolver=lambda: (snapshot, None),
        artifact_loader=lambda *_args, **_kwargs: list(artifacts),
        directory_loader=lambda: directory or {},
    )


def _row(body, team_id):
    return next(row for row in body['teams'] if row['team_id'] == team_id)


@pytest.fixture(autouse=True)
def _valid_integrity(monkeypatch):
    monkeypatch.setattr(
        projection,
        'verify_share_artifact_integrity',
        lambda _artifact: True,
    )


def test_registry_is_exactly_30_unique_immutable_clubs():
    assert EXPECTED_CLUB_COUNT == len(MLB_CLUBS) == 30
    assert len({club.team_id for club in MLB_CLUBS}) == EXPECTED_CLUB_COUNT
    assert len({club.abbreviation for club in MLB_CLUBS}) == EXPECTED_CLUB_COUNT
    with pytest.raises(FrozenInstanceError):
        MLB_CLUBS[0].team_name = 'Changed'


def test_existing_team_id_constants_derive_from_registry():
    assert MLB_TEAM_IDS == tuple(club.team_id for club in MLB_CLUBS)
    assert ASSIGNMENT_TEAM_IDS is MLB_TEAM_IDS
    seed_source = (REPO_ROOT / 'backend' / 'seed.py').read_text(encoding='utf-8')
    assert 'from services.mlb_club_directory import MLB_TEAM_IDS' in seed_source
    assert 'ALL_TEAM_IDS = list(MLB_TEAM_IDS)' in seed_source


def test_listing_has_exactly_one_neutrally_ordered_row_per_club():
    body = _build()
    assert body['expected_team_count'] == 30
    assert body['team_count'] == len(body['teams']) == 30
    assert len({row['team_id'] for row in body['teams']}) == 30
    assert body['teams'] == sorted(
        body['teams'], key=lambda row: (row['team_name'].casefold(), row['team_id'])
    )


@pytest.mark.parametrize(
    'status_code,label',
    [
        ('operationally_stable', 'Fresh'),
        ('operationally_constrained', 'Stretched'),
        ('operationally_stressed', 'Vulnerable'),
    ],
)
def test_published_artifact_projects_each_governed_team_state(status_code, label):
    team_id = MLB_CLUBS[0].team_id
    state = _row(_build([_artifact(team_id, status_code)]), team_id)['team_state']
    assert state['contract'] == 'team_state_public_v1'
    assert state['available'] is True
    assert state['public_label'] == label
    assert state['data_through'] == DATA_THROUGH.isoformat()


def test_missing_artifact_is_an_explicit_withheld_row():
    state = _row(_build(), MLB_CLUBS[0].team_id)['team_state']
    assert state['available'] is False
    assert state['public_label'] is None
    assert state['reason_code'] == 'published_team_state_artifact_missing'


def test_malformed_frozen_status_fails_closed_through_governed_projection():
    team_id = MLB_CLUBS[0].team_id
    state = _row(_build([_artifact(team_id, 'invented_state')]), team_id)['team_state']
    assert state['available'] is False
    assert state['outcome'] == 'unsupported_internal_state'
    assert state['public_label'] is None


def test_integrity_failure_withholds_only_the_affected_club(monkeypatch):
    bad_id = MLB_CLUBS[0].team_id
    good_id = MLB_CLUBS[1].team_id

    def _verify(artifact):
        if artifact.team_id == bad_id:
            raise ValueError('mismatch')
        return True

    monkeypatch.setattr(projection, 'verify_share_artifact_integrity', _verify)
    body = _build([_artifact(bad_id), _artifact(good_id)])
    assert _row(body, bad_id)['team_state']['reason_code'] == (
        'published_team_state_artifact_integrity_failed'
    )
    assert _row(body, good_id)['team_state']['public_label'] == 'Fresh'


@pytest.mark.parametrize('lifecycle_state', ['withdrawn', 'superseded', 'draft'])
def test_non_published_lifecycle_artifacts_are_ignored(lifecycle_state):
    team_id = MLB_CLUBS[0].team_id
    state = _row(
        _build([_artifact(team_id, lifecycle_state=lifecycle_state)]),
        team_id,
    )['team_state']
    assert state['reason_code'] == 'published_team_state_artifact_missing'


def test_duplicate_published_artifacts_use_published_at_then_id_descending():
    team_id = MLB_CLUBS[0].team_id
    same_time = datetime(2026, 8, 15, 4, tzinfo=timezone.utc)
    artifacts = [
        _artifact(team_id, 'operationally_stable', artifact_id=3,
                  published_at=datetime(2026, 8, 15, 3, tzinfo=timezone.utc)),
        _artifact(team_id, 'operationally_constrained', artifact_id=4,
                  published_at=same_time),
        _artifact(team_id, 'operationally_stressed', artifact_id=5,
                  published_at=same_time),
    ]
    assert _row(_build(artifacts), team_id)['team_state']['public_label'] == 'Vulnerable'


def test_29_represented_plus_one_withheld_preserves_denominator_invariants():
    artifacts = [_artifact(club.team_id) for club in MLB_CLUBS[:-1]]
    body = _build(artifacts)
    assert body['represented_team_count'] == 29
    assert body['withheld_team_count'] == 1
    assert body['represented_team_count'] + body['withheld_team_count'] == 30
    labels = [
        row['team_state']['public_label']
        for row in body['teams']
        if row['team_state']['available']
    ]
    assert sum(labels.count(label) for label in ('Fresh', 'Stretched', 'Vulnerable')) == 29


def test_zero_pitcher_club_and_partial_live_directory_do_not_shrink_membership():
    live = {
        club.team_id: {
            'team_id': club.team_id,
            'team_name': f'Live {club.team_name}',
            'team_abbreviation': club.abbreviation,
        }
        for club in MLB_CLUBS[:11]
    }
    body = _build(directory=live)
    assert len(body['teams']) == 30
    assert _row(body, MLB_CLUBS[10].team_id)['team_name'].startswith('Live ')
    assert _row(body, MLB_CLUBS[11].team_id)['team_name'] == MLB_CLUBS[11].team_name


def test_response_contains_no_raw_availability_or_ranking_vocabulary():
    body = _build([_artifact(MLB_CLUBS[0].team_id)])
    raw = json.dumps(body)
    assert 'Monitor' not in raw
    assert 'Avoid' not in raw
    assert body['ranking_applied'] is False
    assert body['selection_made'] is False
    assert body['prediction_applied'] is False

    forbidden = {'rank', 'score', 'grade', 'priority', 'top', 'bottom'}

    def _keys(value):
        if isinstance(value, dict):
            yield from value.keys()
            for child in value.values():
                yield from _keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from _keys(child)

    assert forbidden.isdisjoint(set(_keys(body)))


@pytest.mark.parametrize(
    'snapshot_id,sync_run_id,data_through',
    [
        (999, 721, DATA_THROUGH.isoformat()),
        (411, 999, DATA_THROUGH.isoformat()),
        (411, 721, '2026-08-13'),
    ],
)
def test_artifact_publication_context_mismatch_withholds_the_club(
    snapshot_id, sync_run_id, data_through,
):
    team_id = MLB_CLUBS[0].team_id
    artifact = _artifact(
        team_id,
        snapshot_id=snapshot_id,
        sync_run_id=sync_run_id,
        data_through=data_through,
    )
    state = _row(_build([artifact]), team_id)['team_state']
    assert state['available'] is False
    assert state['reason_code'] == listing.PUBLICATION_CONTEXT_MISMATCH


def test_represented_rows_and_publication_authority_share_one_snapshot_context():
    artifacts = [_artifact(club.team_id) for club in MLB_CLUBS]
    body = _build(artifacts)
    assert body['represented_team_count'] == 30
    assert {row['team_state']['data_through'] for row in body['teams']} == {
        DATA_THROUGH.isoformat()
    }
    assert body['publication_authority']['snapshot_id'] == 411
    assert body['publication_authority']['sync_run_id'] == 721
    assert body['publication_authority']['data_through'] == DATA_THROUGH.isoformat()
    assert body['publication_authority'] == serving.publication_authority(_snapshot())


def test_snapshot_pinned_freshness_suppresses_runtime_overlay(monkeypatch):
    monkeypatch.setattr(
        board_freshness.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: pytest.fail('explicit snapshot was ignored'),
    )
    monkeypatch.setattr(
        board_freshness.sync_metadata,
        'build_sync_status_payload',
        lambda: pytest.fail('runtime overlay was not suppressed'),
    )

    block = board_freshness.published_snapshot_freshness_block(
        snapshot=_snapshot(),
        include_runtime_overlay=False,
    )
    assert block['data_through'] == DATA_THROUGH.isoformat()
    assert block['freshness_state'] == 'current'


def test_published_freshness_default_callers_keep_snapshot_and_overlay_behavior(
    monkeypatch,
):
    snapshot = _snapshot()
    monkeypatch.setattr(
        board_freshness.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        board_freshness,
        'published_snapshot_overlay',
        lambda selected: {
            'served_consistency_state': 'previous_published_view',
            'current_sync_status': 'running',
        } if selected is snapshot else {},
    )

    block = board_freshness.published_snapshot_freshness_block()
    assert block['served_consistency_state'] == 'previous_published_view'
    assert 'sync_in_progress_serving_previous_published_view' in block['reason_codes']


def test_snapshot_unavailable_returns_30_withheld_rows_and_existing_reason():
    reason = 'dashboard_snapshot_freshness_fail_closed'
    body = listing.build_league_team_state_listing(
        generated_at=GENERATED_AT,
        snapshot_resolver=lambda: (None, reason),
        artifact_loader=lambda *_args, **_kwargs: pytest.fail('artifact query ran'),
        directory_loader=lambda: {},
    )
    assert body['status'] == 'snapshot_unavailable'
    assert body['reason'] == reason
    assert body['publication_authority'] is None
    assert body['freshness']['freshness_state'] == 'metadata_unavailable'
    assert body['freshness']['reason_codes'] == [reason]
    assert body['represented_team_count'] == 0
    assert body['withheld_team_count'] == 30
    assert len(body['teams']) == 30
    assert {row['team_state']['reason_code'] for row in body['teams']} == {reason}


def test_query_budget_is_constant_and_no_mlb_client_is_called(monkeypatch):
    calls = {'snapshot': 0, 'artifacts': 0, 'directory': 0}

    def _snapshot_resolver():
        calls['snapshot'] += 1
        return _snapshot(), None

    artifact_rows = []

    def _artifact_loader(*_args, **_kwargs):
        calls['artifacts'] += 1
        return artifact_rows

    def _directory_loader():
        calls['directory'] += 1
        return {}

    from services.mlb_api import mlb_client

    monkeypatch.setattr(
        mlb_client,
        'get_all_teams',
        lambda: pytest.fail('reader request called MLB'),
    )
    for fixture in (
        [_artifact(MLB_CLUBS[0].team_id)],
        [_artifact(club.team_id) for club in MLB_CLUBS],
    ):
        artifact_rows[:] = fixture
        calls.update(snapshot=0, artifacts=0, directory=0)
        listing.build_league_team_state_listing(
            snapshot_resolver=_snapshot_resolver,
            artifact_loader=_artifact_loader,
            directory_loader=_directory_loader,
        )
        assert calls == {'snapshot': 1, 'artifacts': 1, 'directory': 1}


def _seed_real_listing_population(artifact_count):
    sync_run = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='published',
        source='test',
        started_at=datetime(2026, 8, 15, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
    )
    db.session.add(sync_run)
    db.session.flush()

    snapshot = DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=sync_run.id,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 8, 15, 2, 5, tzinfo=timezone.utc),
        payload={
            'freshness': {
                'data_through': DATA_THROUGH.isoformat(),
                'availability_reference_date': DATA_THROUGH.isoformat(),
                'freshness_state': 'current',
                'is_current': True,
                'slate_coverage': {
                    'slate_date': DATA_THROUGH.isoformat(),
                    'validations_passed': True,
                    'complete_enough_to_publish': True,
                },
            },
        },
        payload_version=1,
        data_through=DATA_THROUGH,
        availability_reference_date=DATA_THROUGH,
        snapshot_generated_at=datetime(2026, 8, 15, 2, tzinfo=timezone.utc),
        source='query_count_test',
    )
    db.session.add(snapshot)
    db.session.flush()

    for index, club in enumerate(MLB_CLUBS):
        db.session.add(Pitcher(
            mlb_id=900000 + index,
            full_name=f'{club.abbreviation} Query Fixture',
            team_id=club.team_id,
            team_name=club.team_name,
            team_abbreviation=club.abbreviation,
            position='P',
            active=True,
        ))

    for index, club in enumerate(MLB_CLUBS[:artifact_count]):
        db.session.add(ShareArtifact(
            public_id=f'query-count-{artifact_count}-{club.team_id}',
            artifact_type=TEAM_STATE_ARTIFACT_TYPE,
            render_version='team-state-1.0.0',
            team_id=club.team_id,
            source_snapshot_id=snapshot.id,
            source_sync_run_id=sync_run.id,
            product_date=DATA_THROUGH,
            lifecycle_state='published',
            payload={
                'team_state': {
                    'contract_state': 'published',
                    'status_code': 'operationally_stable',
                },
                'authority': {'data_through': DATA_THROUGH.isoformat()},
            },
            trust_metadata={},
            equivalence_key=f'query-count-equivalence-{artifact_count}-{index}',
            integrity_hash='query-count-test-integrity',
            source='query_count_test',
            published_at=datetime(2026, 8, 15, 3, index, tzinfo=timezone.utc),
        ))

    db.session.commit()


def _real_listing_query_count(artifact_count):
    _seed_real_listing_population(artifact_count)
    db.session.remove()
    statements = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        body = listing.build_league_team_state_listing(generated_at=GENERATED_AT)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert body['status'] == 'ok'
    assert body['team_count'] == 30
    assert body['represented_team_count'] == artifact_count
    return len(statements)


def test_real_database_query_count_does_not_grow_with_artifact_population():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)

    counts = {}
    for artifact_count in (1, 30):
        with flask_app.app_context():
            create_test_schema(flask_app)
            try:
                counts[artifact_count] = _real_listing_query_count(artifact_count)
            finally:
                db.session.remove()
                drop_test_schema(flask_app)

    assert counts[1] == counts[30]


def test_service_source_has_no_recomputation_or_per_team_reader_path():
    source = Path(listing.__file__).read_text(encoding='utf-8')
    for forbidden in (
        'resolve_team_readiness_payload',
        'assemble_bullpen_readiness',
        'canonical_team_state',
        '_published_team_state(',
        'services.mlb_api',
    ):
        assert forbidden not in source


def test_existing_published_team_state_reader_is_a_thin_projection_consumer(monkeypatch):
    sentinel = {'contract': 'team_state_public_v1', 'available': True}
    artifact = _artifact(108)

    class _Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return artifact

    monkeypatch.setattr(serving.db.session, 'query', lambda *_args: _Query())
    monkeypatch.setattr(
        serving,
        'project_published_team_state_artifact',
        lambda selected, **_kwargs: sentinel if selected is artifact else None,
    )
    assert serving._published_team_state(_snapshot(), 108) is sentinel


def _app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(bullpen_api.bullpen_bp, url_prefix='/api/bullpen')
    return app


def test_route_serves_valid_and_snapshot_unavailable_envelopes(monkeypatch):
    valid = _build([_artifact(MLB_CLUBS[0].team_id)])
    monkeypatch.setattr(bullpen_api, 'build_league_team_state_listing', lambda: valid)
    response = _app().test_client().get('/api/bullpen/team-states')
    assert response.status_code == 200
    assert response.get_json()['capability'] == listing.CAPABILITY
    assert response.get_json()['teams'][0].keys() == {
        'team_id', 'team_abbreviation', 'team_name', 'team_state'
    }

    unavailable = listing.build_snapshot_unavailable_listing(
        'dashboard_snapshot_missing',
        generated_at=GENERATED_AT,
        directory_loader=lambda: {},
    )
    monkeypatch.setattr(
        bullpen_api,
        'build_league_team_state_listing',
        lambda: unavailable,
    )
    response = _app().test_client().get('/api/bullpen/team-states')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'snapshot_unavailable'
    assert len(response.get_json()['teams']) == 30


def test_route_preserves_snapshot_read_failure_as_honest_503(monkeypatch):
    def _raise():
        raise SnapshotReadUnavailable('bullpen_dashboard', 'current_publication', 1)

    monkeypatch.setattr(bullpen_api, 'build_league_team_state_listing', _raise)
    response = _app().test_client().get('/api/bullpen/team-states')
    assert response.status_code == 503
    body = response.get_json()
    assert body['status'] == 'snapshot_unavailable'
    assert body['reason'] == listing.SNAPSHOT_READ_UNAVAILABLE
    assert len(body['teams']) == 30
    raw = response.get_data(as_text=True)
    for leak in ('OperationalError', 'SnapshotReadUnavailable', 'Traceback'):
        assert leak not in raw


def test_d054_remains_in_the_contiguous_ledger_through_d058():
    roadmap = (
        REPO_ROOT / 'docs' / 'canonical' / '05_PRODUCT_ROADMAP_DECISION_LEDGER.md'
    ).read_text(encoding='utf-8')
    assert '| D-054 | Aug 15, 2026 |' in roadmap
    assert 'Decision Ledger through D-058' in roadmap
    assert 'D-054, added by UX-2B' in roadmap
    assert 'represented + withheld = expected = 30' in roadmap
