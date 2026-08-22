from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event
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
    CATEGORY_CONTRACT_SELECTION,
    CATEGORY_DFA,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_OPTION,
    CATEGORY_RECALL,
    CATEGORY_UNKNOWN,
    TRANSACTION_FETCH_ENTITY_TYPE,
    TRANSACTION_IDENTITY_ENTITY_TYPE,
    normalize_transaction_category,
    sync_transactions,
)
from services.transaction_rehab_assignment import (
    AUTHORITY as REHAB_AUTHORITY,
    MATERIALITY_NON_MATERIAL,
    STATUS_CERTIFIED,
    SUBTYPE_REHAB_ASSIGNMENT,
    is_certified_non_material_rehab_assignment,
)
from utils.db import db


class FakeTransactionClient:
    def __init__(
        self,
        transactions=None,
        exc=None,
        people=None,
        people_exc=None,
        team_metadata=None,
        team_metadata_exc=None,
    ):
        self.transactions = transactions if transactions is not None else []
        self.exc = exc
        self.people = people or {}
        self.people_exc = people_exc
        self.team_metadata = team_metadata or {}
        self.team_metadata_exc = team_metadata_exc
        self.calls = []
        self.people_calls = []
        self.team_metadata_calls = []

    def get_transactions(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return list(self.transactions)

    def get_people_info(self, player_ids):
        self.people_calls.append(list(player_ids))
        if self.people_exc:
            raise self.people_exc
        return {player_id: self.people[player_id] for player_id in player_ids if player_id in self.people}

    def get_team_metadata(self, season):
        self.team_metadata_calls.append(season)
        if self.team_metadata_exc:
            raise self.team_metadata_exc
        return dict(self.team_metadata)


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


def _snapshot(
    pitcher,
    *,
    snapshot_date=date(2026, 7, 4),
    team_id=None,
    roster_status='ACTIVE',
    active_roster=True,
):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id or pitcher.team_id,
        snapshot_date=snapshot_date,
        roster_status=roster_status,
        active_roster=active_roster,
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


def _team_metadata(*, source_team_id=113, destination_team_id=555, parent_org_id=113):
    return {
        source_team_id: {
            'team_id': source_team_id,
            'sport_id': 1,
            'parent_org_id': None,
            'season': 2026,
        },
        destination_team_id: {
            'team_id': destination_team_id,
            'sport_id': 11,
            'parent_org_id': parent_org_id,
            'season': 2026,
        },
    }


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
        'participant_position_code': None,
        'participant_position_abbreviation': None,
        'participant_position_type': None,
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


def test_statsapi_people_client_batches_position_authority(monkeypatch):
    client = MLBApiClient()
    calls = []

    def fake_get(endpoint, params=None):
        calls.append((endpoint, params))
        return {'people': [
            {'id': 700001, 'primaryPosition': {'code': '1', 'abbreviation': 'P'}},
            {'id': 700002, 'primaryPosition': {'code': '6', 'abbreviation': 'SS'}},
        ]}

    monkeypatch.setattr(client, '_get', fake_get)

    people = client.get_people_info([700002, 700001, 700002])

    assert calls == [('/people', {'personIds': '700001,700002'})]
    assert set(people) == {700001, 700002}


def test_statsapi_team_metadata_is_one_season_scoped_batch(monkeypatch):
    client = MLBApiClient()
    calls = []

    def fake_get(endpoint, params=None):
        calls.append((endpoint, params))
        return {'teams': [
            {'id': 113, 'sport': {'id': 1}, 'parentOrgId': None},
            {'id': 555, 'sport': {'id': 11}, 'parentOrgId': 113},
        ]}

    monkeypatch.setattr(client, '_get', fake_get)

    metadata = client.get_team_metadata(2026)

    assert calls == [('/teams', {'season': 2026, 'hydrate': 'sport'})]
    assert metadata == {
        113: {'team_id': 113, 'sport_id': 1, 'parent_org_id': None, 'season': 2026},
        555: {'team_id': 555, 'sport_id': 11, 'parent_org_id': 113, 'season': 2026},
    }


def test_ingestion_persists_explicit_participant_roles_with_one_batch_lookup(app):
    with app.app_context():
        pitcher = _pitcher(mlb_id=700001)
        _snapshot(pitcher)
        client = FakeTransactionClient(
            [_tx(transaction_id='pitcher'), _tx(
                transaction_id='position-player',
                player_mlb_id=700002,
                player_full_name='Position Player',
            )],
            people={700002: {
                'id': 700002,
                'primaryPosition': {'code': '6', 'abbreviation': 'SS', 'type': 'Infielder'},
            }},
        )

        sync_transactions(
            client=client,
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        rows = {row.transaction_id: row for row in PlayerTransaction.query.all()}

    assert rows['pitcher'].participant_role == 'pitcher'
    assert rows['pitcher'].participant_role_authority == 'canonical_pitcher_identity_v1'
    assert rows['position-player'].participant_role == 'non_pitcher'
    assert rows['position-player'].participant_role_authority == 'mlb_people_primary_position_v1'
    assert rows['position-player'].participant_position_code == '6'
    assert client.people_calls == [[700002]]


def test_source_position_authority_avoids_people_lookup(app):
    with app.app_context():
        client = FakeTransactionClient([_tx(
            player_mlb_id=700003,
            player_full_name='Source Position Player',
            participant_position_code='2',
            participant_position_abbreviation='C',
            participant_position_type='Catcher',
        )])

        sync_transactions(
            client=client,
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        row = PlayerTransaction.query.one()

    assert row.participant_role == 'non_pitcher'
    assert row.participant_role_authority == 'mlb_transaction_primary_position_v1'
    assert client.people_calls == []


def test_missing_and_two_way_position_evidence_fail_closed_or_stay_relevant(app):
    with app.app_context():
        client = FakeTransactionClient(
            [
                _tx(transaction_id='missing', player_mlb_id=700010, player_full_name='Unknown Role'),
                _tx(transaction_id='two-way', player_mlb_id=700011, player_full_name='Two Way'),
            ],
            people={
                700010: {'id': 700010},
                700011: {
                    'id': 700011,
                    'primaryPosition': {'code': 'Y', 'abbreviation': 'TWP', 'type': 'Two-Way Player'},
                },
            },
        )

        sync_transactions(
            client=client,
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        rows = {row.transaction_id: row for row in PlayerTransaction.query.all()}

    assert rows['missing'].participant_role == 'unresolved'
    assert rows['two-way'].participant_role == 'pitcher'
    assert rows['two-way'].pitcher_id is None


def test_people_lookup_failure_stores_unresolved_without_guessing(app):
    with app.app_context():
        client = FakeTransactionClient(
            [_tx(player_mlb_id=700099, player_full_name='Unresolved Participant')],
            people_exc=RuntimeError('people unavailable'),
        )
        result = sync_transactions(
            client=client,
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        row = PlayerTransaction.query.one()

    assert result['records_stored'] == 1
    assert row.participant_role == 'unresolved'
    assert row.participant_role_authority == 'unresolved'


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


@pytest.mark.parametrize(
    ('type_code', 'category'),
    (
        ('CU', CATEGORY_RECALL),
        ('DES', CATEGORY_DFA),
        ('SE', CATEGORY_CONTRACT_SELECTION),
    ),
)
def test_structured_event_codes_map_to_existing_categories(type_code, category):
    assert normalize_transaction_category(type_code) == category


@pytest.mark.parametrize('type_code', ('SC', 'ASG', 'CLW', 'SFA', 'NEW_CODE'))
def test_unapproved_structured_event_codes_remain_unknown(type_code):
    assert normalize_transaction_category(type_code) == CATEGORY_UNKNOWN


def test_natural_resync_corrects_newly_governed_event_authority(app, monkeypatch):
    import services.transaction_ingestion as transaction_ingestion

    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)
        monkeypatch.delitem(transaction_ingestion._CATEGORY_BY_TYPE_CODE, 'CU')
        first = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-natural-correction', transaction_type_code='CU'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        row = PlayerTransaction.query.one()
        assert row.normalized_category == CATEGORY_UNKNOWN
        assert row.explanatory_linkage_eligible is False

        monkeypatch.setitem(
            transaction_ingestion._CATEGORY_BY_TYPE_CODE,
            'CU',
            CATEGORY_RECALL,
        )
        second = sync_transactions(
            client=FakeTransactionClient([
                _tx(transaction_id='tx-natural-correction', transaction_type_code='CU'),
            ]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 13, 0, 0),
        )
        row = PlayerTransaction.query.one()

    assert first['records_created'] == 1
    assert second['records_corrected'] == 1
    assert row.normalized_category == CATEGORY_RECALL
    assert row.roster_snapshot_alignment == ALIGNMENT_ALIGNED
    assert row.explanatory_linkage_eligible is True
    assert row.correction_count == 1


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
                # A person-referencing row (name present) whose id is missing
                # is a malformed player row and must keep failing closed. Rows
                # with no person reference at all are covered separately as
                # non-player classifications.
                _tx(
                    transaction_id='tx-missing-identity',
                    player_mlb_id=None,
                    player_full_name='Identified Person Without Id',
                ),
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
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda **_kwargs: {
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


def _seed_identity_dead_letter(entity_ref, created_at=datetime(2026, 7, 12, 10, 55, 0)):
    failure = SyncFailure(
        job_name='daily_sync',
        entity_type=TRANSACTION_IDENTITY_ENTITY_TYPE,
        entity_ref=str(entity_ref),
        payload={'reason': 'missing_player_identity'},
        error='Transaction row missing player identity',
        created_at=created_at,
        resolved=False,
    )
    db.session.add(failure)
    db.session.commit()
    return failure


def _non_player_trade_component(transaction_id, *, from_team_id, to_team_id):
    """
    Captured source shape of a team-level trade component: the structured
    client mapped no person object and no person name from the raw row.
    """
    return _tx(
        transaction_id=transaction_id,
        player_mlb_id=None,
        player_full_name=None,
        transaction_type_code='TRADE',
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date='2026-07-12',
    )


def _person_row_missing_id(transaction_id='tx-name-only'):
    """A person-referencing row whose id is missing: must stay fail-closed."""
    return _tx(
        transaction_id=transaction_id,
        player_mlb_id=None,
        player_full_name='Unresolvable Person',
        transaction_type_code='RECALL',
    )


def test_non_player_rows_classify_generically_without_identity_failures(app):
    with app.app_context():
        run = _run()
        result = sync_transactions(
            client=FakeTransactionClient([
                _non_player_trade_component('926807', from_team_id=142, to_team_id=133),
                _non_player_trade_component('926870', from_team_id=133, to_team_id=142),
            ]),
            start_date=date(2026, 7, 6),
            end_date=date(2026, 7, 13),
            timestamp=datetime(2026, 7, 13, 10, 55, 0),
            sync_run_id=run.id,
        )
        failure_count = SyncFailure.query.count()
        stored_count = PlayerTransaction.query.count()
        window = (
            PlayerTransactionSyncWindow.query
            .order_by(PlayerTransactionSyncWindow.id.desc())
            .first()
        )

    assert result['non_player_count'] == 2
    assert result['records_failed'] == 0
    assert result['errors'] == 0
    assert failure_count == 0
    # Non-player components never enter player roster calculations.
    assert stored_count == 0
    assert window.status == 'success'


def test_person_row_missing_id_still_fails_closed(app):
    with app.app_context():
        run = _run()
        result = sync_transactions(
            client=FakeTransactionClient([_person_row_missing_id()]),
            start_date=date(2026, 7, 6),
            end_date=date(2026, 7, 13),
            timestamp=datetime(2026, 7, 13, 10, 55, 0),
            sync_run_id=run.id,
        )
        failures = SyncFailure.query.filter_by(
            entity_type=TRANSACTION_IDENTITY_ENTITY_TYPE,
            resolved=False,
        ).all()
        window = (
            PlayerTransactionSyncWindow.query
            .order_by(PlayerTransactionSyncWindow.id.desc())
            .first()
        )

    assert result['records_failed'] == 1
    assert result['non_player_count'] == 0
    assert len(failures) == 1
    assert failures[0].entity_ref == 'tx-name-only'
    assert window.status == 'partial'


def test_repeated_identity_failure_does_not_duplicate_dead_letters(app):
    with app.app_context():
        run = _run()
        for _ in range(2):
            result = sync_transactions(
                client=FakeTransactionClient([_person_row_missing_id()]),
                start_date=date(2026, 7, 6),
                end_date=date(2026, 7, 13),
                timestamp=datetime(2026, 7, 13, 10, 55, 0),
                sync_run_id=run.id,
            )
            # Honesty is preserved on every run even without a duplicate row.
            assert result['records_failed'] == 1
        rows = SyncFailure.query.filter_by(
            entity_type=TRANSACTION_IDENTITY_ENTITY_TYPE,
            entity_ref='tx-name-only',
        ).all()

    assert len(rows) == 1
    assert rows[0].resolved is False


def test_non_player_reprocessing_resolves_prior_dead_letter_idempotently(app):
    with app.app_context():
        run = _run()
        original = _seed_identity_dead_letter('926807')
        original_id = original.id

        for _ in range(2):
            result = sync_transactions(
                client=FakeTransactionClient([
                    _non_player_trade_component('926807', from_team_id=142, to_team_id=133),
                ]),
                start_date=date(2026, 7, 6),
                end_date=date(2026, 7, 13),
                timestamp=datetime(2026, 7, 13, 10, 55, 0),
                sync_run_id=run.id,
            )
            assert result['records_failed'] == 0
            assert result['non_player_count'] == 1

        rows = SyncFailure.query.filter_by(entity_ref='926807').all()

    # The historical dead letter is preserved, resolved exactly once, and no
    # replacement failures were recorded.
    assert len(rows) == 1
    assert rows[0].id == original_id
    assert rows[0].resolved is True
    assert rows[0].resolved_at is not None


def test_successful_storage_resolves_prior_identity_dead_letter(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(pitcher)
        run = _run()
        _seed_identity_dead_letter('tx-1')

        result = sync_transactions(
            client=FakeTransactionClient([_tx()]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
            sync_run_id=run.id,
        )
        row = SyncFailure.query.filter_by(entity_ref='tx-1').one()
        stored = PlayerTransaction.query.count()

    assert result['records_stored'] == 1
    assert stored == 1
    assert row.resolved is True
    assert row.resolved_at is not None


@pytest.mark.parametrize('roster_status', ['IL_15', 'IL_60'])
def test_ingestion_certifies_non_material_rehab_from_exact_typed_authority(
    app,
    roster_status,
):
    with app.app_context():
        pitcher = _pitcher(team_id=999)
        mutable_pitcher_team_id = pitcher.team_id
        snapshot = _snapshot(
            pitcher,
            team_id=113,
            roster_status=roster_status,
            active_roster=False,
        )
        snapshot_id = snapshot.id
        client = FakeTransactionClient(
            [_tx(
                transaction_type_code='ASG',
                from_team_id=113,
                to_team_id=555,
            )],
            team_metadata=_team_metadata(),
        )

        sync_transactions(
            client=client,
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        row = PlayerTransaction.query.one()

    assert client.team_metadata_calls == [2026]
    assert row.normalized_category == CATEGORY_UNKNOWN
    assert row.transaction_subtype == SUBTYPE_REHAB_ASSIGNMENT
    assert row.transaction_materiality == MATERIALITY_NON_MATERIAL
    assert row.subtype_status == STATUS_CERTIFIED
    assert row.subtype_authority == REHAB_AUTHORITY
    assert row.subtype_evidence['roster_snapshot_id'] == snapshot_id
    assert row.subtype_evidence['roster_snapshot_date'] == '2026-07-04'
    assert row.subtype_evidence['roster_team_id'] == 113
    assert row.subtype_evidence['roster_status'] == roster_status
    assert row.subtype_evidence['active_roster'] is False
    assert row.subtype_evidence['destination_parent_org_id'] == 113
    assert is_certified_non_material_rehab_assignment(row) is True
    # Mutable current assignment is intentionally irrelevant.
    assert mutable_pitcher_team_id == 999


def test_rehab_certification_requires_exact_date_not_nearest_snapshot(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(
            pitcher,
            snapshot_date=date(2026, 7, 3),
            team_id=113,
            roster_status='IL_15',
            active_roster=False,
        )
        sync_transactions(
            client=FakeTransactionClient(
                [_tx(
                    transaction_type_code='ASG',
                    from_team_id=113,
                    to_team_id=555,
                )],
                team_metadata=_team_metadata(),
            ),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
        )
        row = PlayerTransaction.query.one()

    assert row.subtype_status == 'unresolved'
    assert row.subtype_reason_code == 'exact_roster_snapshot_missing'
    assert is_certified_non_material_rehab_assignment(row) is False


@pytest.mark.parametrize(
    ('roster_status', 'active_roster', 'reason'),
    [
        ('40_MAN_ONLY', False, 'roster_snapshot_not_pitcher_il'),
        ('ACTIVE', True, 'roster_snapshot_active'),
    ],
)
def test_non_il_or_active_roster_asg_is_not_certified(
    app,
    roster_status,
    active_roster,
    reason,
):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(
            pitcher,
            team_id=113,
            roster_status=roster_status,
            active_roster=active_roster,
        )
        sync_transactions(
            client=FakeTransactionClient(
                [_tx(
                    transaction_type_code='ASG',
                    from_team_id=113,
                    to_team_id=555,
                )],
                team_metadata=_team_metadata(),
            ),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
        )
        row = PlayerTransaction.query.one()

    assert row.subtype_status == 'not_certified'
    assert row.subtype_reason_code == reason
    assert is_certified_non_material_rehab_assignment(row) is False


@pytest.mark.parametrize(
    ('from_team_id', 'to_team_id', 'metadata', 'reason'),
    [
        (113, 555, _team_metadata(parent_org_id=114), 'destination_parent_org_mismatch'),
        (None, 113, _team_metadata(), 'source_team_missing'),
        (113, 114, {
            113: {'team_id': 113, 'sport_id': 1, 'parent_org_id': None, 'season': 2026},
            114: {'team_id': 114, 'sport_id': 1, 'parent_org_id': None, 'season': 2026},
        }, 'destination_team_is_mlb'),
    ],
)
def test_ambiguous_asg_shapes_remain_uncertified(
    app,
    from_team_id,
    to_team_id,
    metadata,
    reason,
):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(
            pitcher,
            team_id=113,
            roster_status='IL_15',
            active_roster=False,
        )
        sync_transactions(
            client=FakeTransactionClient(
                [_tx(
                    transaction_type_code='ASG',
                    from_team_id=from_team_id,
                    to_team_id=to_team_id,
                )],
                team_metadata=metadata,
            ),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
        )
        row = PlayerTransaction.query.one()

    assert row.subtype_reason_code == reason
    assert is_certified_non_material_rehab_assignment(row) is False


def test_rehab_authority_natural_resync_corrects_unresolved_current_window_row(app):
    with app.app_context():
        pitcher = _pitcher()
        _snapshot(
            pitcher,
            team_id=113,
            roster_status='IL_60',
            active_roster=False,
        )
        transaction = _tx(
            transaction_type_code='ASG',
            from_team_id=113,
            to_team_id=555,
        )
        sync_transactions(
            client=FakeTransactionClient([transaction]),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 12, 0, 0),
        )
        first = PlayerTransaction.query.one()
        assert first.subtype_status == 'unresolved'

        result = sync_transactions(
            client=FakeTransactionClient(
                [transaction],
                team_metadata=_team_metadata(),
            ),
            start_date=date(2026, 6, 27),
            end_date=date(2026, 7, 4),
            timestamp=datetime(2026, 7, 4, 13, 0, 0),
        )
        corrected = PlayerTransaction.query.one()

    assert result['records_corrected'] == 1
    assert corrected.correction_count == 1
    assert corrected.subtype_status == STATUS_CERTIFIED
    assert is_certified_non_material_rehab_assignment(corrected) is True


def test_rehab_ingestion_prefetches_exact_roster_rows_once(app):
    with app.app_context():
        first = _pitcher(mlb_id=700001)
        second = _pitcher(mlb_id=700002)
        for pitcher in (first, second):
            _snapshot(
                pitcher,
                team_id=113,
                roster_status='IL_15',
                active_roster=False,
            )
        statements = []

        def record_statement(conn, cursor, statement, parameters, context, executemany):
            if 'roster_status_snapshots' in statement.lower() and statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', record_statement)
        try:
            sync_transactions(
                client=FakeTransactionClient(
                    [
                        _tx(transaction_id='one', player_mlb_id=first.mlb_id,
                            transaction_type_code='ASG', from_team_id=113, to_team_id=555),
                        _tx(transaction_id='two', player_mlb_id=second.mlb_id,
                            transaction_type_code='ASG', from_team_id=113, to_team_id=555),
                    ],
                    team_metadata=_team_metadata(),
                ),
                start_date=date(2026, 6, 27),
                end_date=date(2026, 7, 4),
            )
        finally:
            event.remove(db.engine, 'before_cursor_execute', record_statement)

    assert len(statements) == 1
