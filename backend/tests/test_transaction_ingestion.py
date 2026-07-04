from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import source_readiness
import services.sync as sync_service
from services.mlb_api import MLBApiClient
from services.transaction_ingestion import (
    ALIGNMENT_ALIGNED,
    ALIGNMENT_MISALIGNED,
    ALIGNMENT_NO_SNAPSHOT,
    ALIGNMENT_NOT_APPLICABLE,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_OPTION,
    CATEGORY_RECALL,
    CATEGORY_UNKNOWN,
    TRANSACTION_FETCH_ENTITY_TYPE,
    TRANSACTION_IDENTITY_ENTITY_TYPE,
    sync_transactions,
)
from utils.db import db


class FakeTransactionClient:
    def __init__(self, transactions=None, exc=None):
        self.transactions = transactions if transactions is not None else []
        self.exc = exc
        self.calls = []

    def get_transactions(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return list(self.transactions)


@pytest.fixture
def app():
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


def _run(started_at=datetime(2026, 7, 4, 12, 0, 0)):
    run = SyncRun(
        job_name='daily_sync',
        status='success',
        source='test',
        started_at=started_at,
        completed_at=started_at,
    )
    db.session.add(run)
    db.session.commit()
    return run


def _pitcher(
    *,
    mlb_id=700001,
    name='Transaction Arm',
    team_id=113,
    roster_status='ACTIVE',
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=True,
        roster_status=roster_status,
        roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _snapshot(pitcher, *, snapshot_date=date(2026, 7, 4), team_id=None):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id or pitcher.team_id,
        snapshot_date=snapshot_date,
        roster_status='ACTIVE',
        active_roster=True,
        forty_man_roster=True,
        position_code='P',
        source='mlb_stats_api:roster_sync:active',
        first_seen_at=datetime(2026, 7, 4, 12, 0, 0),
        created_at=datetime(2026, 7, 4, 12, 0, 0),
        updated_at=datetime(2026, 7, 4, 12, 0, 0),
    )
    db.session.add(row)
    db.session.commit()
    return row


def _tx(**overrides):
    data = {
        'transaction_id': 'tx-1',
        'transaction_date': '2026-07-04',
        'effective_date': None,
        'resolution_date': None,
        'player_mlb_id': 700001,
        'from_team_id': None,
        'to_team_id': 113,
        'transaction_type_code': 'RECALL',
        'transaction_type_description': 'Free text is diagnostic only',
        'source_endpoint': '/transactions',
        'source_query_start_date': '2026-06-27',
        'source_query_end_date': '2026-07-04',
    }
    data.update(overrides)
    return data


def test_statsapi_transaction_client_extracts_structured_fields_only(monkeypatch):
    client = MLBApiClient()

    def fake_get(endpoint, params=None):
        assert endpoint == '/transactions'
        return {
            'transactions': [{
                'id': 123,
                'date': '2026-07-04',
                'effectiveDate': '2026-07-04',
                'person': {'id': 700001, 'fullName': 'Structured Arm'},
                'fromTeam': {'id': 112},
                'toTeam': {'id': 113},
                'type': {
                    'code': 'D15',
                    'description': 'Placed on injured list with detail',
                },
                'ilListType': '15-day',
                'retroactiveDate': '2026-07-01',
                'injuryDescription': 'Must not be exposed by client shape',
            }],
        }

    monkeypatch.setattr(client, '_get', fake_get)

    rows = client.get_transactions('2026-06-27', '2026-07-04')

    assert rows == [{
        'transaction_id': 123,
        'transaction_date': '2026-07-04',
        'effective_date': '2026-07-04',
        'resolution_date': None,
        'player_mlb_id': 700001,
        'player_full_name': 'Structured Arm',
        'from_team_id': 112,
        'to_team_id': 113,
        'transaction_type_code': 'D15',
        'transaction_type_description': 'Placed on injured list with detail',
        'roster_status': None,
        'il_list_type': '15-day',
        'retroactive_date': '2026-07-01',
        'source_endpoint': '/transactions',
        'source_query_start_date': '2026-06-27',
        'source_query_end_date': '2026-07-04',
    }]
    assert 'injuryDescription' not in rows[0]
    assert 'raw' not in rows[0]


def test_typed_transaction_response_stores_fact_without_raw_or_free_text(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)
        run = _run()

        result = sync_transactions(
            client=FakeTransactionClient([
                _tx(raw_response={'not': 'stored'}, injuryDescription='not stored'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
            sync_run_id=run.id,
        )
        row = PlayerTransaction.query.one()

    assert result['records_stored'] == 1
    assert row.normalized_category == CATEGORY_RECALL
    assert row.roster_snapshot_alignment == ALIGNMENT_ALIGNED
    assert row.explanatory_linkage_eligible is True
    assert not hasattr(row, 'raw_response')
    assert not hasattr(row, 'raw_response_json')
    assert not hasattr(row, 'transaction_type_description')
    assert not hasattr(row, 'injury_description')
    assert not hasattr(row, 'health_status')


def test_il_placement_and_activation_store_typed_facts_only(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)

        sync_transactions(
            client=FakeTransactionClient([
                _tx(
                    transaction_id='tx-il-place',
                    transaction_type_code='D15',
                    il_list_type='15-day',
                    retroactive_date='2026-07-01',
                ),
                _tx(
                    transaction_id='tx-il-activate',
                    transaction_type_code='IL_ACTIVATION',
                    il_list_type='15-day',
                    retroactive_date=None,
                ),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        rows = {
            row.transaction_id: row
            for row in PlayerTransaction.query.order_by(PlayerTransaction.id).all()
        }

    assert rows['tx-il-place'].normalized_category == CATEGORY_IL_PLACEMENT
    assert rows['tx-il-place'].is_il_placement is True
    assert rows['tx-il-place'].is_il_activation is False
    assert rows['tx-il-place'].il_list_type == '15_day'
    assert rows['tx-il-place'].retroactive_date == date(2026, 7, 1)
    assert rows['tx-il-activate'].normalized_category == CATEGORY_IL_ACTIVATION
    assert rows['tx-il-activate'].is_il_activation is True
    assert rows['tx-il-activate'].is_il_placement is False


def test_unknown_type_maps_to_unknown_and_is_excluded_from_linkage(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)

        sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-unknown', transaction_type_code='NEW_CODE'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        row = PlayerTransaction.query.one()
        readiness = source_readiness.source_readiness_payload(
            reference_date=date(2026, 7, 4),
        )['families']['player_transactions']

    assert row.normalized_category == CATEGORY_UNKNOWN
    assert row.roster_snapshot_alignment == ALIGNMENT_NOT_APPLICABLE
    assert row.explanatory_linkage_eligible is False
    assert readiness['status'] == source_readiness.DEGRADED
    assert 'unknown_transaction_types_present' in readiness['reason_codes']


def test_repeated_sync_is_idempotent_and_corrections_track_provenance(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)

        first = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-corrected', transaction_type_code='RECALL'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        second = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-corrected', transaction_type_code='RECALL'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 13, 0, 0),
        )
        third = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-corrected', transaction_type_code='OPTION'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 14, 0, 0),
        )
        row = PlayerTransaction.query.one()
        row_count = PlayerTransaction.query.count()

    assert first['records_created'] == 1
    assert second['records_unchanged'] == 1
    assert third['records_corrected'] == 1
    assert row_count == 1
    assert row.normalized_category == CATEGORY_OPTION
    assert row.correction_count == 1
    assert row.last_corrected_at == datetime(2026, 7, 4, 14, 0, 0)
    assert row.correction_source == 'mlb_stats_api:transactions'


def test_roster_alignment_and_precedence_fail_closed(app):
    with app.app_context():
        aligned_pitcher = _pitcher(mlb_id=700001, team_id=113)
        mismatched_pitcher = _pitcher(mlb_id=700002, team_id=113, name='Mismatch Arm')
        no_snapshot_pitcher = _pitcher(mlb_id=700003, team_id=113, name='No Snapshot Arm')
        _snapshot(aligned_pitcher, team_id=113)
        _snapshot(mismatched_pitcher, team_id=113)

        sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-aligned', player_mlb_id=700001, to_team_id=113),
                _tx(transaction_id='tx-misaligned', player_mlb_id=700002, to_team_id=135),
                _tx(transaction_id='tx-no-snapshot', player_mlb_id=700003, to_team_id=113),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        rows = {row.transaction_id: row for row in PlayerTransaction.query.all()}
        refreshed = db.session.get(Pitcher, mismatched_pitcher.id)

    assert rows['tx-aligned'].roster_snapshot_alignment == ALIGNMENT_ALIGNED
    assert rows['tx-misaligned'].roster_snapshot_alignment == ALIGNMENT_MISALIGNED
    assert rows['tx-misaligned'].explanatory_linkage_eligible is False
    assert rows['tx-no-snapshot'].roster_snapshot_alignment == ALIGNMENT_NO_SNAPSHOT
    assert refreshed.roster_status == 'ACTIVE'
    assert refreshed.roster_status_source == 'mlb_stats_api:roster_sync:active'


def test_fetch_failure_deadletters_and_degrades_transaction_readiness(app):
    with app.app_context():
        result = sync_transactions(
            client=FakeTransactionClient(exc=RuntimeError('transactions unavailable')),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        failure = SyncFailure.query.filter_by(
            entity_type=TRANSACTION_FETCH_ENTITY_TYPE,
            resolved=False,
        ).one()
        window = PlayerTransactionSyncWindow.query.one()
        readiness = source_readiness.source_readiness_payload(
            reference_date=date(2026, 7, 4),
        )['families']['player_transactions']

    assert result['records_failed'] == 1
    assert failure.payload['reason'] == 'fetch_failed'
    assert window.status == 'failed'
    assert readiness['status'] == source_readiness.UNAVAILABLE
    assert 'transaction_fetch_failed' in readiness['reason_codes']


def test_shape_surprise_deadletters_and_degrades_readiness(app):
    with app.app_context():
        result = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-missing-identity', player_mlb_id=None),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        failure = SyncFailure.query.filter_by(
            entity_type=TRANSACTION_IDENTITY_ENTITY_TYPE,
            resolved=False,
        ).one()
        readiness = source_readiness.source_readiness_payload(
            reference_date=date(2026, 7, 4),
        )['families']['player_transactions']
        row_count = PlayerTransaction.query.count()

    assert result['records_failed'] == 1
    assert failure.payload['reason'] == 'missing_player_identity'
    assert row_count == 0
    assert readiness['status'] == source_readiness.DEGRADED
    assert 'dead_letters_unresolved' in readiness['reason_codes']


def test_daily_sync_transaction_stage_is_bounded_and_non_authoritative(app, monkeypatch):
    captured = {}
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 7, 4, 12, 0, 0)
            return value.replace(tzinfo=tz) if tz else value

    monkeypatch.setattr(sync_service, 'datetime', FixedDatetime)
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {},
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'by_status': {},
    })

    def fake_transactions(**kwargs):
        captured.update(kwargs)
        return {
            'records_fetched': 1,
            'records_stored': 0,
            'unknown_type_count': 0,
            'records_failed': 1,
            'errors': 1,
            'error_details': [{'reason': 'shape_surprise'}],
        }

    monkeypatch.setattr(sync_service, 'sync_transactions', fake_transactions)
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 1,
        'pitchers_touched': 1,
        'errors': 0,
        'records_failed': 0,
        'logs_corrected': 0,
        'correction_attempts_failed': 0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 0)
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=1)),
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: {'status': 'skipped', 'computed_at': None},
    )

    status = sync_service.run_daily_sync(app, days_back=7)

    assert status['status'] == 'partial'
    assert status['records_failed'] == 1
    assert captured['end_date'] == date(2026, 7, 4)
