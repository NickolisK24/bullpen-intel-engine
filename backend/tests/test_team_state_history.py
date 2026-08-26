"""HIST-01 retained Team State timeline contract."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event, update

from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.share_artifact import ShareArtifact
from services import team_state_history as history_module
from services.share_artifacts import (
    build_share_artifact_draft,
    publish_share_artifact,
    supersede_share_artifact,
    withdraw_share_artifact,
)
from services.team_state_history import build_team_state_history
from services.transaction_rehab_assignment import AUTHORITY as REHAB_AUTHORITY
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


def _comparison_result(*, previous_code='stretched', previous_label='Stretched',
                       current_code='fresh', current_label='Fresh'):
    return {
        'domains': {'team_state': {
            'status': 'comparable',
            'previous': {
                'public_state': previous_code,
                'public_label': previous_label,
            },
            'current': {
                'public_state': current_code,
                'public_label': current_label,
            },
        }},
    }


def _transaction_window(start, end, *, status='success', attempted_at=None):
    attempted_at = attempted_at or datetime.combine(end, datetime.min.time())
    row = PlayerTransactionSyncWindow(
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=start,
        source_query_end_date=end,
        attempted_at=attempted_at,
        successful_at=attempted_at if status != 'failed' else None,
        status=status,
        records_fetched=1,
        records_stored=1,
        records_created=1,
        records_corrected=0,
        records_unchanged=0,
        unknown_type_count=0,
        alignment_unknown_count=0,
        alignment_misaligned_count=0,
        alignment_no_snapshot_count=0,
        records_failed=1 if status == 'partial' else 0,
        created_at=attempted_at,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _transaction(
    *,
    transaction_id,
    transaction_date,
    category='recall',
    from_team_id=None,
    to_team_id=TEAM_ID,
    pitcher=None,
    eligible=True,
    transaction_type_code=None,
    participant_role='pitcher',
    transaction_subtype=None,
    transaction_materiality='unresolved',
    subtype_status='unresolved',
    subtype_authority='unresolved',
    subtype_reason_code='legacy_unclassified',
    subtype_evidence=None,
):
    pitcher = pitcher or Pitcher.query.filter_by(mlb_id=910001).one()
    row = PlayerTransaction(
        transaction_key=f'statsapi:{transaction_id}',
        transaction_id=str(transaction_id),
        pitcher_id=pitcher.id if pitcher else None,
        player_mlb_id=pitcher.mlb_id if pitcher else 999999,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=transaction_date,
        transaction_type_code=transaction_type_code or category.upper(),
        normalized_category=category,
        is_il_placement=category == 'il_placement',
        is_il_activation=category == 'il_activation',
        roster_snapshot_alignment='aligned' if eligible else 'unknown',
        explanatory_linkage_eligible=eligible,
        participant_role=participant_role,
        participant_role_authority='canonical_pitcher_identity_v1',
        transaction_subtype=transaction_subtype,
        transaction_materiality=transaction_materiality,
        subtype_status=subtype_status,
        subtype_authority=subtype_authority,
        subtype_reason_code=subtype_reason_code,
        subtype_evidence=subtype_evidence,
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=transaction_date,
        source_query_end_date=transaction_date,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _certified_rehab_fields(pitcher, event_date):
    destination_team_id = 555
    return {
        'category': 'unknown',
        'transaction_type_code': 'ASG',
        'eligible': False,
        'from_team_id': TEAM_ID,
        'to_team_id': destination_team_id,
        'participant_role': 'pitcher',
        'transaction_subtype': 'rehab_assignment',
        'transaction_materiality': 'non_material',
        'subtype_status': 'certified',
        'subtype_authority': REHAB_AUTHORITY,
        'subtype_reason_code': 'certified_rehab_assignment',
        'subtype_evidence': {
            'authority': REHAB_AUTHORITY,
            'transaction_type_code': 'ASG',
            'pitcher_id': pitcher.id,
            'player_mlb_id': pitcher.mlb_id,
            'participant_role': 'pitcher',
            'from_team_id': TEAM_ID,
            'to_team_id': destination_team_id,
            'destination_team_id': destination_team_id,
            'destination_sport_id': 11,
            'destination_parent_org_id': TEAM_ID,
            'metadata_season': event_date.year,
            'roster_snapshot_id': 42,
            'roster_snapshot_date': event_date.isoformat(),
            'roster_team_id': TEAM_ID,
            'roster_status': 'IL_15',
            'active_roster': False,
        },
    }


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
    assert payload['rows'][0]['event_overlay'] == {
        'status': 'withheld', 'outcome': 'unavailable', 'reason_code': 'coverage_gap',
    }
    assert payload['rows'][0]['events'] == []
    assert payload['rows'][1]['event_overlay'] == {
        'status': 'withheld', 'outcome': 'unavailable',
        'reason_code': 'prior_publication_missing',
    }
    assert payload['rows'][1]['events'] == []


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
    assert row['events'] == []


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
    monkeypatch.setattr(
        history_module, 'compare_snapshots',
        lambda previous, current: _comparison_result(),
    )

    payload = build_team_state_history('TST', season=2026)

    comparison = payload['rows'][0]['comparison']
    assert comparison['status'] == 'comparable'
    assert comparison['transition'] == {
        'from_code': 'stretched', 'from_state': 'Stretched',
        'to_code': 'fresh', 'to_state': 'Fresh', 'changed': True,
    }
    assert payload['rows'][0]['event_overlay'] == {
        'status': 'available', 'outcome': 'changed', 'reason_code': None,
    }
    assert payload['rows'][0]['events'] == [{
        'event_type': 'team_state_change',
        'event_id': f'team_state_change:{TEAM_ID}:{older.public_id}:{newer.public_id}',
        'event_date': '2026-07-24',
        'from_date': '2026-07-23',
        'to_date': '2026-07-24',
        'label': 'Team State changed',
        'from_state': {'code': 'stretched', 'label': 'Stretched'},
        'to_state': {'code': 'fresh', 'label': 'Fresh'},
        'citations': {
            'previous': {
                'public_id': older.public_id,
                'citation_url': f'/share/{older.public_id}',
            },
            'current': {
                'public_id': newer.public_id,
                'citation_url': f'/share/{newer.public_id}',
            },
        },
    }]
    # Event identity is derived only from the canonical pair.
    repeated = build_team_state_history('TST', season=2026)
    assert repeated['rows'][0]['events'][0]['event_id'] == payload['rows'][0]['events'][0]['event_id']


def test_comparable_unchanged_pair_is_available_without_an_event(app, monkeypatch):
    older = _publish(date(2026, 7, 23), label='Stretched', snapshot_id=5001)
    newer = _publish(date(2026, 7, 24), label='Stretched', snapshot_id=5002)
    _sidecar(older)
    _sidecar(newer)
    monkeypatch.setattr(
        history_module, 'compare_snapshots',
        lambda previous, current: _comparison_result(
            current_code='stretched', current_label='Stretched',
        ),
    )

    payload = build_team_state_history('TST', season=2026)
    row = payload['rows'][0]

    assert row['comparison']['transition']['changed'] is False
    assert row['event_overlay'] == {
        'status': 'available', 'outcome': 'unchanged', 'reason_code': None,
    }
    assert row['events'] == []


def test_comparison_state_mismatch_with_frozen_artifact_withholds_event(app, monkeypatch):
    older = _publish(date(2026, 7, 23), label='Stretched', snapshot_id=5001)
    newer = _publish(date(2026, 7, 24), label='Fresh', code='fresh', snapshot_id=5002)
    _sidecar(older)
    _sidecar(newer)
    monkeypatch.setattr(
        history_module, 'compare_snapshots',
        lambda previous, current: _comparison_result(
            current_code='vulnerable', current_label='Vulnerable',
        ),
    )

    row = build_team_state_history('TST', season=2026)['rows'][0]

    assert row['event_overlay'] == {
        'status': 'withheld', 'outcome': 'unavailable',
        'reason_code': 'comparison_authority_missing',
    }
    assert row['events'] == []


def test_version_boundary_does_not_author_transition_without_sidecars(app):
    _publish(date(2026, 7, 23), render_version='team-state-1.0.0', snapshot_id=5001)
    _publish(date(2026, 7, 24), render_version='team-state-1.2.0', snapshot_id=5002)

    payload = build_team_state_history('TST', season=2026)

    comparison = payload['rows'][0]['comparison']
    assert comparison['status'] == 'comparison_unavailable'
    assert comparison['boundary'] is True
    assert comparison['transition'] is None
    assert payload['rows'][0]['event_overlay'] == {
        'status': 'withheld', 'outcome': 'unavailable',
        'reason_code': 'comparison_authority_missing',
    }
    assert payload['rows'][0]['events'] == []


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
    assert response.get_json()['contract'] == 'team_state_history_v3'
    assert client.get('/api/bullpen/teams/TST/history?season=nope').status_code == 400
    assert client.get('/api/bullpen/teams/NOPE/history?season=2026').status_code == 404


def test_history_query_count_is_bounded_for_full_retained_window(app):
    for day in range(1, 31):
        _publish(date(2026, 7, day), snapshot_id=6000 + day)
        _transaction(
            transaction_id=f'query-{day:02d}',
            transaction_date=date(2026, 7, day),
            from_team_id=555,
            to_team_id=TEAM_ID,
        )
    for index in range(10):
        _transaction(
            transaction_id=f'same-day-{index:02d}',
            transaction_date=date(2026, 7, 30),
            from_team_id=TEAM_ID,
            to_team_id=555,
        )
    _transaction_window(date(2026, 7, 1), date(2026, 7, 30))

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
    assert sum(len(row['transactions']) for row in payload['rows']) == 40
    assert len(selects) <= 12
    assert all('board-v2' not in statement.lower() for statement in selects)
    assert sum('player_transactions' in statement.lower() for statement in selects) == 1


def test_corrected_canonical_pair_owns_event_and_superseded_source_is_excluded(app, monkeypatch):
    prior = _publish(date(2026, 7, 23), label='Stretched', snapshot_id=5001)
    original = _publish(date(2026, 7, 24), label='Fresh', code='fresh', snapshot_id=5002)
    replacement = _publish(
        date(2026, 7, 24), label='Vulnerable', code='vulnerable', snapshot_id=5003,
    )
    supersede_share_artifact(original, replacement)
    _sidecar(prior)
    _sidecar(original)
    _sidecar(replacement)
    db.session.expire_all()
    monkeypatch.setattr(
        history_module, 'compare_snapshots',
        lambda previous, current: _comparison_result(
            current_code='vulnerable', current_label='Vulnerable',
        ),
    )

    payload = build_team_state_history('TST', season=2026)
    row = payload['rows'][0]
    event_row = row['events'][0]

    assert row['artifact']['public_id'] == replacement.public_id
    assert row['artifact']['corrected_publication'] is True
    assert event_row['citations']['current']['public_id'] == replacement.public_id
    assert original.public_id not in event_row['event_id']
    assert event_row['to_state'] == {'code': 'vulnerable', 'label': 'Vulnerable'}


def test_withdrawn_or_integrity_invalid_date_cannot_support_an_event(app):
    prior = _publish(date(2026, 7, 23), snapshot_id=5001)
    withdrawn = _publish(date(2026, 7, 24), snapshot_id=5002)
    withdraw_share_artifact(withdrawn, reason='source correction')
    broken = _publish(date(2026, 7, 25), snapshot_id=5003)
    db.session.execute(
        update(ShareArtifact)
        .where(ShareArtifact.id == broken.id)
        .values(integrity_hash='0' * 64)
    )
    db.session.commit()

    payload = build_team_state_history('TST', season=2026)

    assert [row['artifact']['public_id'] for row in payload['rows']] == [prior.public_id]
    assert payload['rows'][0]['events'] == []
    assert payload['coverage']['missing_dates'] == ['2026-07-24', '2026-07-25']


def test_v3_preserves_hist_01_and_hist_02_fields_additively(app):
    artifact = _publish(date(2026, 7, 23))

    payload = build_team_state_history('TST', season=2026)
    row = payload['rows'][0]

    assert payload['contract'] == 'team_state_history_v3'
    assert {
        'represented_date', 'team_state', 'headline', 'explanation', 'limitations',
        'artifact', 'comparison',
    }.issubset(row)
    assert row['artifact']['public_id'] == artifact.public_id
    assert row['event_overlay']['status'] == 'withheld'
    assert row['events'] == []
    assert row['transaction_overlay']['status'] == 'unavailable'
    assert row['transactions'] == []


def test_v3_projects_only_qualified_transactions_with_exact_team_attribution(app):
    artifacts = [
        _publish(date(2026, 7, day), snapshot_id=7000 + day)
        for day in (23, 24, 25)
    ]
    _transaction_window(date(2026, 7, 23), date(2026, 7, 25))
    _transaction_window(
        date(2026, 7, 24), date(2026, 7, 25),
        attempted_at=datetime(2026, 7, 25, 12, 0, 0),
    )
    pitcher = Pitcher(
        mlb_id=910002,
        full_name='History Arm',
        team_id=999,
        team_name='Current Other Club',
        team_abbreviation='OTH',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    incoming = _transaction(
        transaction_id='b', transaction_date=date(2026, 7, 24),
        category='recall', from_team_id=555, to_team_id=TEAM_ID,
        pitcher=pitcher,
    )
    outgoing = _transaction(
        transaction_id='a', transaction_date=date(2026, 7, 24),
        category='option', from_team_id=TEAM_ID, to_team_id=555,
        pitcher=pitcher,
    )
    _transaction(
        transaction_id='unknown', transaction_date=date(2026, 7, 24),
        category='unknown', from_team_id=TEAM_ID, to_team_id=555,
        pitcher=pitcher,
    )
    _transaction(
        transaction_id='ineligible', transaction_date=date(2026, 7, 24),
        category='recall', from_team_id=555, to_team_id=TEAM_ID,
        pitcher=pitcher, eligible=False,
    )
    unresolved = _transaction(
        transaction_id='unresolved', transaction_date=date(2026, 7, 24),
        category='recall', from_team_id=555, to_team_id=TEAM_ID,
        pitcher=pitcher,
    )
    unresolved.pitcher_id = None
    _transaction(
        transaction_id='rehab', transaction_date=date(2026, 7, 24),
        pitcher=pitcher, **_certified_rehab_fields(pitcher, date(2026, 7, 24)),
    )
    db.session.commit()
    artifact_hashes = {artifact.id: artifact.integrity_hash for artifact in artifacts}

    payload = build_team_state_history('TST', season=2026)
    rows = {row['represented_date']: row for row in payload['rows']}
    events = rows['2026-07-24']['transactions']

    assert [event['event_id'] for event in events] == [
        outgoing.transaction_key, incoming.transaction_key,
    ]
    assert events[0]['team_relationship'] == {
        'relationship': 'outgoing', 'from_team_id': TEAM_ID, 'to_team_id': 555,
    }
    assert events[1]['team_relationship'] == {
        'relationship': 'incoming', 'from_team_id': 555, 'to_team_id': TEAM_ID,
    }
    assert events[0]['label'] == 'Optioned'
    assert events[1]['description'] == 'History Arm was recalled.'
    assert all(event['event_date'] == '2026-07-24' for event in events)
    assert rows['2026-07-25']['transaction_overlay'] == {
        'status': 'available', 'reason_code': None,
    }
    assert rows['2026-07-25']['transactions'] == []
    assert payload['transaction_coverage']['retained_date_status_counts'] == {
        'available': 3, 'partial': 0, 'unavailable': 0,
    }
    assert payload['transaction_coverage']['is_partial'] is True
    db.session.expire_all()
    assert {
        artifact.id: db.session.get(ShareArtifact, artifact.id).integrity_hash
        for artifact in artifacts
    } == artifact_hashes


def test_transaction_coverage_distinguishes_partial_and_unavailable_dates(app):
    for day in (23, 24, 25):
        _publish(date(2026, 7, day), snapshot_id=7100 + day)
    _transaction_window(
        date(2026, 7, 23), date(2026, 7, 24), status='partial',
    )
    event_row = _transaction(
        transaction_id='partial', transaction_date=date(2026, 7, 24),
        from_team_id=555, to_team_id=TEAM_ID,
    )

    payload = build_team_state_history('TST', season=2026)
    rows = {row['represented_date']: row for row in payload['rows']}

    assert rows['2026-07-24']['transaction_overlay'] == {
        'status': 'partial', 'reason_code': 'transaction_source_partial',
    }
    assert [event['event_id'] for event in rows['2026-07-24']['transactions']] == [
        event_row.transaction_key,
    ]
    assert rows['2026-07-25']['transaction_overlay'] == {
        'status': 'unavailable', 'reason_code': 'transaction_source_unavailable',
    }
    assert rows['2026-07-25']['transactions'] == []
    assert payload['transaction_coverage']['start'] == '2026-07-23'
    assert payload['transaction_coverage']['end'] == '2026-07-24'
    assert payload['transaction_coverage']['retained_date_status_counts'] == {
        'available': 0, 'partial': 2, 'unavailable': 1,
    }


def test_transaction_events_never_create_or_use_nearest_state_dates(app):
    _publish(date(2026, 7, 23), snapshot_id=7201)
    _publish(date(2026, 7, 25), snapshot_id=7202)
    _transaction_window(date(2026, 7, 22), date(2026, 7, 25))
    _transaction(
        transaction_id='gap-date', transaction_date=date(2026, 7, 24),
        from_team_id=555, to_team_id=TEAM_ID,
    )
    _transaction(
        transaction_id='outside-range', transaction_date=date(2026, 7, 22),
        from_team_id=555, to_team_id=TEAM_ID,
    )

    payload = build_team_state_history('TST', season=2026)

    assert [row['represented_date'] for row in payload['rows']] == [
        '2026-07-25', '2026-07-23',
    ]
    assert all(row['transactions'] == [] for row in payload['rows'])
    assert payload['coverage']['missing_dates'] == ['2026-07-24']


def test_transaction_correction_updates_only_the_current_history_projection(app):
    _publish(date(2026, 7, 23), snapshot_id=7301)
    _publish(date(2026, 7, 24), snapshot_id=7302)
    _transaction_window(date(2026, 7, 23), date(2026, 7, 24))
    transaction = _transaction(
        transaction_id='corrected', transaction_date=date(2026, 7, 24),
        category='recall', from_team_id=555, to_team_id=TEAM_ID,
    )
    db.session.commit()

    original = build_team_state_history('TST', season=2026)
    assert original['rows'][0]['transactions'][0]['label'] == 'Recalled'

    transaction.normalized_category = 'option'
    transaction.transaction_type_code = 'OPTION'
    transaction.from_team_id = TEAM_ID
    transaction.to_team_id = 555
    transaction.correction_count = 1
    db.session.commit()

    corrected = build_team_state_history('TST', season=2026)
    event_row = corrected['rows'][0]['transactions'][0]
    assert event_row['event_id'] == 'statsapi:corrected'
    assert event_row['label'] == 'Optioned'
    assert event_row['team_relationship']['relationship'] == 'outgoing'

    transaction.transaction_date = date(2026, 7, 23)
    transaction.correction_count = 2
    db.session.commit()

    moved = build_team_state_history('TST', season=2026)
    assert moved['rows'][0]['represented_date'] == '2026-07-24'
    assert moved['rows'][0]['transactions'] == []
    assert moved['rows'][1]['represented_date'] == '2026-07-23'
    assert moved['rows'][1]['transactions'][0]['event_id'] == 'statsapi:corrected'


def test_transaction_projection_failure_is_local_to_supporting_context(app, monkeypatch):
    older = _publish(date(2026, 7, 23), label='Stretched', snapshot_id=7401)
    newer = _publish(date(2026, 7, 24), label='Fresh', code='fresh', snapshot_id=7402)
    _sidecar(older)
    _sidecar(newer)
    monkeypatch.setattr(
        history_module, 'compare_snapshots',
        lambda previous, current: _comparison_result(),
    )
    monkeypatch.setattr(
        history_module, '_transaction_windows',
        lambda season, session: (_ for _ in ()).throw(RuntimeError('transactions unavailable')),
    )

    payload = build_team_state_history('TST', season=2026)

    assert payload['status'] == 'available'
    assert payload['rows'][0]['events'][0]['event_type'] == 'team_state_change'
    assert payload['rows'][0]['transaction_overlay']['status'] == 'unavailable'
    assert payload['rows'][0]['transactions'] == []
    assert payload['transaction_coverage']['status'] == 'unavailable'
