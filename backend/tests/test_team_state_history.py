"""HIST-01 retained Team State timeline contract."""

from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event, update

from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.share_artifact import ShareArtifact
from services import team_state_history as history_module
from services.share_artifacts import (
    build_share_artifact_draft,
    publish_share_artifact,
    supersede_share_artifact,
    withdraw_share_artifact,
)
from services.team_state_history import build_team_state_history
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TEAM_ID = 147


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        db.session.add(Pitcher(
            mlb_id=910001,
            full_name='History Arm',
            team_id=TEAM_ID,
            team_name='Test Club',
            team_abbreviation='TST',
            active=True,
        ))
        db.session.flush()
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def client(app):
    from api.team_history import team_history_bp
    app.register_blueprint(team_history_bp, url_prefix='/api/bullpen')
    return app.test_client()


def _payload(represented_date, label='Stretched', code='stretched'):
    return {
        'payload_version': 'team-state-1.2.0',
        'team': {
            'team_id': TEAM_ID,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'authority': {
            'source_snapshot_id': 5000,
            'source_sync_run_id': None,
            'data_through': represented_date.isoformat(),
            'published_at': f'{represented_date.isoformat()}T12:00:00',
        },
        'team_state': {
            'status_code': 'operationally_constrained',
            'public_state': {'public_code': code, 'public_label': label},
            'summary': f'Frozen {label} explanation.',
            'contract_state': 'available',
            'constraints': [],
        },
        'trust': {
            'confidence': 'high',
            'data_state': 'fresh',
            'freshness_state': 'current',
            'trust_state': 'supported',
        },
        'public_copy': {
            'state': {'public_code': code, 'public_label': label},
            'headline': f'Test Club bullpen — {label}',
            'why': f'Frozen {label} explanation.',
            'freshness_line': f'Data through {represented_date.isoformat()}.',
            'trust_line': 'Published from retained evidence.',
            'description': f'Test Club bullpen was {label}.',
            'limitations': [],
            'evidence': [],
        },
    }


def _publish(represented_date, *, label='Stretched', code='stretched', snapshot_id=5000,
             render_version='team-state-1.2.0'):
    payload = _payload(represented_date, label, code)
    payload['authority']['source_snapshot_id'] = snapshot_id
    artifact = build_share_artifact_draft(
        artifact_type='team_state',
        team_id=TEAM_ID,
        source_snapshot_id=snapshot_id,
        product_date=represented_date,
        payload=payload,
        render_version=render_version,
        source='history_test',
    )
    db.session.commit()
    return publish_share_artifact(artifact)


def _sidecar(artifact):
    row = DashboardSnapshot(
        snapshot_type='team_board_delta',
        status='ready',
        is_published=False,
        published_at=artifact.published_at,
        payload={
            'source': {'artifact_id': artifact.id},
            'team_id': TEAM_ID,
            'represented_date': artifact.product_date.isoformat(),
        },
        payload_version=1,
        data_through=artifact.product_date,
        snapshot_generated_at=artifact.published_at,
        source=f'tb_delta:team:{TEAM_ID}',
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_history_selects_exact_frozen_rows_and_reports_gaps(app):
    older = _publish(date(2026, 7, 23), label='Stretched')
    newer = _publish(date(2026, 7, 25), label='Fresh', code='fresh', snapshot_id=5002)

    payload = build_team_state_history('tst', season=2026)

    assert payload['team'] == {
        'team_id': TEAM_ID,
        'team_name': 'Test Club',
        'team_abbreviation': 'TST',
        'team_board_href': '/bullpen?view=board&team=TST',
    }
    assert payload['coverage'] == {
        'start': '2026-07-23',
        'end': '2026-07-25',
        'covered_date_count': 2,
        'missing_dates': ['2026-07-24'],
        'is_partial': True,
    }
    assert [row['represented_date'] for row in payload['rows']] == ['2026-07-25', '2026-07-23']
    assert payload['rows'][0]['team_state']['public_label'] == 'Fresh'
    assert payload['rows'][1]['explanation'] == 'Frozen Stretched explanation.'
    assert payload['rows'][0]['artifact']['citation_url'] == f'/share/{newer.public_id}'
    assert payload['rows'][1]['artifact']['public_id'] == older.public_id
    assert payload['rows'][0]['comparison']['reason_code'] == 'coverage_gap'
    assert payload['rows'][0]['comparison']['transition'] is None


def test_newest_active_correction_wins_and_lifecycle_rows_are_excluded(app):
    original = _publish(date(2026, 7, 23), snapshot_id=5001)
    replacement = _publish(
        date(2026, 7, 23), label='Fresh', code='fresh', snapshot_id=5002,
    )
    supersede_share_artifact(original, replacement)
    withdrawn = _publish(date(2026, 7, 24), snapshot_id=5003)
    withdraw_share_artifact(withdrawn, reason='source correction')

    payload = build_team_state_history('TST', season=2026)

    assert len(payload['rows']) == 1
    row = payload['rows'][0]
    assert row['artifact']['public_id'] == replacement.public_id
    assert row['artifact']['corrected_publication'] is True
    assert original.public_id != row['artifact']['public_id']
    assert payload['coverage']['end'] == '2026-07-23'


def test_integrity_failure_falls_back_to_older_healthy_same_date(app):
    healthy = _publish(date(2026, 7, 23), snapshot_id=5001)
    broken = _publish(date(2026, 7, 23), label='Fresh', code='fresh', snapshot_id=5002)
    db.session.execute(
        update(ShareArtifact)
        .where(ShareArtifact.id == broken.id)
        .values(integrity_hash='0' * 64)
    )
    db.session.commit()

    payload = build_team_state_history('TST', season=2026)

    assert len(payload['rows']) == 1
    assert payload['rows'][0]['artifact']['public_id'] == healthy.public_id


def test_integrity_failure_without_replacement_becomes_explicit_gap(app):
    broken = _publish(date(2026, 7, 23))
    db.session.execute(
        update(ShareArtifact)
        .where(ShareArtifact.id == broken.id)
        .values(integrity_hash='0' * 64)
    )
    db.session.commit()

    payload = build_team_state_history('TST', season=2026)

    assert payload['status'] == 'quiet'
    assert payload['rows'] == []
    assert payload['coverage']['covered_date_count'] == 0
    assert payload['coverage']['start'] == '2026-07-23'
    assert payload['coverage']['end'] == '2026-07-23'
    assert payload['coverage']['missing_dates'] == ['2026-07-23']


def test_comparable_transition_is_backend_owned(app, monkeypatch):
    older = _publish(date(2026, 7, 23), label='Stretched', snapshot_id=5001)
    newer = _publish(date(2026, 7, 24), label='Fresh', code='fresh', snapshot_id=5002)
    _sidecar(older)
    _sidecar(newer)
    monkeypatch.setattr(history_module, 'compare_snapshots', lambda previous, current: {
        'domains': {'team_state': {
            'status': 'comparable',
            'previous': {'public_state': 'stretched', 'public_label': 'Stretched'},
            'current': {'public_state': 'fresh', 'public_label': 'Fresh'},
        }},
    })

    payload = build_team_state_history('TST', season=2026)

    comparison = payload['rows'][0]['comparison']
    assert comparison['status'] == 'comparable'
    assert comparison['transition'] == {
        'from_state': 'Stretched', 'to_state': 'Fresh', 'changed': True,
    }


def test_version_boundary_does_not_author_transition_without_sidecars(app):
    _publish(date(2026, 7, 23), render_version='team-state-1.0.0', snapshot_id=5001)
    _publish(date(2026, 7, 24), render_version='team-state-1.2.0', snapshot_id=5002)

    payload = build_team_state_history('TST', season=2026)

    comparison = payload['rows'][0]['comparison']
    assert comparison['status'] == 'comparison_unavailable'
    assert comparison['boundary'] is True
    assert comparison['transition'] is None


def test_payload_contract_boundary_does_not_author_transition():
    comparison = history_module._comparison(
        (
            date(2026, 7, 23),
            SimpleNamespace(id=1, render_version='team-state-render-v1'),
            {'payload_version': 'team-state-1.2.0'},
        ),
        (
            date(2026, 7, 24),
            SimpleNamespace(id=2, render_version='team-state-render-v1'),
            {'payload_version': 'team-state-2.0.0'},
        ),
        {},
    )

    assert comparison['status'] == 'comparison_unavailable'
    assert comparison['boundary'] is True
    assert comparison['transition'] is None


def test_history_api_validates_season_and_team(client, app):
    _publish(date(2026, 7, 23))
    response = client.get('/api/bullpen/teams/TST/history?season=2026')
    assert response.status_code == 200
    assert response.get_json()['contract'] == 'team_state_history_v1'
    assert client.get('/api/bullpen/teams/TST/history?season=nope').status_code == 400
    assert client.get('/api/bullpen/teams/NOPE/history?season=2026').status_code == 404


def test_history_query_count_is_bounded_for_full_retained_window(app):
    for day in range(1, 31):
        _publish(date(2026, 7, day), snapshot_id=6000 + day)

    selects = []

    def count_selects(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            selects.append(statement)

    event.listen(db.engine, 'before_cursor_execute', count_selects)
    try:
        payload = build_team_state_history('TST', season=2026)
    finally:
        event.remove(db.engine, 'before_cursor_execute', count_selects)

    assert payload['coverage']['covered_date_count'] == 30
    assert len(selects) <= 10
    assert all('board-v2' not in statement.lower() for statement in selects)
