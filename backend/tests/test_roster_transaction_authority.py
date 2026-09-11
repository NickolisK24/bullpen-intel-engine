from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.roster_membership import (
    PlayerTransactionVersion,
    RosterMembershipInterval,
    RosterMembershipMutation,
)
from models.roster_status_snapshot import RosterStatusSnapshot
from models.source_observation import SourceFetchAttempt, SourceObservation
from models.sync_job import SyncJob
from services.mlb_api import MLBApiClient, MlbCollectionResult
from services.roster_transaction_authority import (
    MembershipType,
    current_memberships,
    enqueue_roster_reconciliation,
    enqueue_transaction_reconciliation,
    membership_on_date,
    observe_team_roster,
    reconcile_team_roster,
    run_next_roster_transaction_job,
    supersede_membership_interval,
)
from services.transaction_ingestion import (
    CATEGORY_DFA,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_OPTION,
    CATEGORY_RECALL,
    CATEGORY_RELEASE,
    CATEGORY_TRADE,
    normalize_transaction_category,
    sync_transactions,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SLATE = date(2026, 9, 7)
NOW = datetime(2026, 9, 7, 14, 0, 0)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _entry(mlb_id, name=None, abbreviation='P', position_type='Pitcher'):
    return {
        'person': {'id': mlb_id, 'fullName': name or f'Pitcher {mlb_id}'},
        'position': {
            'abbreviation': abbreviation,
            'code': '1',
            'name': 'Pitcher',
            'type': position_type,
        },
    }


class RosterClient:
    def __init__(self, views=None, completeness=None, exc=None):
        self.views = views or {}
        self.completeness = completeness or {}
        self.exc = exc
        self.calls = []

    def get_team_roster_with_completeness(
        self, team_id, roster_type='active', date=None, **_kwargs,
    ):
        self.calls.append((team_id, roster_type, date))
        if self.exc:
            raise self.exc
        rows = list(self.views.get(roster_type, ()))
        status = self.completeness.get(roster_type, 'complete')
        return MlbCollectionResult(
            records=rows,
            completeness=status,
            proof={'fixture': True, 'record_count': len(rows)},
        )


def test_complete_rosters_open_distinct_memberships_and_provenance(app):
    client = RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]})
    with app.app_context():
        summary = reconcile_team_roster(110, SLATE, client=client, timestamp=NOW)
        intervals = RosterMembershipInterval.query.order_by(
            RosterMembershipInterval.membership_type
        ).all()
        snapshot = RosterStatusSnapshot.query.one()
        pitcher = Pitcher.query.one()

        assert summary['authoritative'] is True
        assert summary['mutation_count'] == 2
        assert [row.membership_type for row in intervals] == [
            'active_roster', 'forty_man_roster',
        ]
        assert all(row.effective_end_date is None for row in intervals)
        assert all(row.opened_by_observation_id for row in intervals)
        assert snapshot.active_roster_observation_id
        assert snapshot.forty_man_roster_observation_id
        assert pitcher.team_id == 110
        assert pitcher.active is True
        assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1


def test_unchanged_roster_creates_no_interval_or_downstream_duplicate(app):
    client = RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]})
    with app.app_context():
        first = reconcile_team_roster(110, SLATE, client=client, timestamp=NOW)
        second = reconcile_team_roster(110, SLATE, client=client, timestamp=NOW)
        assert first['mutation_count'] == 2
        assert second['source_changes'] == 0
        assert second['mutation_count'] == 0
        assert RosterMembershipInterval.query.count() == 2
        assert SourceObservation.query.count() == 2
        assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1


def test_removal_closes_then_readdition_opens_a_new_stint(app):
    with app.app_context():
        reconcile_team_roster(
            110, date(2026, 9, 5),
            client=RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]}),
        )
        reconcile_team_roster(
            110, date(2026, 9, 6),
            client=RosterClient({'active': [], '40Man': [_entry(700001)]}),
        )
        pitcher = Pitcher.query.one()
        active = RosterMembershipInterval.query.filter_by(
            membership_type='active_roster'
        ).one()
        snapshot = RosterStatusSnapshot.query.filter_by(
            pitcher_id=pitcher.id, snapshot_date=date(2026, 9, 6)
        ).one()
        assert active.effective_end_date == date(2026, 9, 6)
        assert snapshot.active_roster is False
        assert snapshot.forty_man_roster is True
        assert membership_on_date(
            pitcher.id, date(2026, 9, 6), MembershipType.ACTIVE_ROSTER,
        ) == []

        reconcile_team_roster(
            110, SLATE,
            client=RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]}),
        )
        stints = RosterMembershipInterval.query.filter_by(
            membership_type='active_roster'
        ).order_by(RosterMembershipInterval.effective_start_date).all()
        assert len(stints) == 2
        assert stints[0].effective_end_date == date(2026, 9, 6)
        assert stints[1].effective_start_date == SLATE
        assert current_memberships(110) == [stints[1]]
        assert len(membership_on_date(pitcher.id, SLATE, 'active_roster')) == 1


def test_complete_team_move_closes_old_and_opens_new_without_overlap(app):
    with app.app_context():
        first = RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]})
        reconcile_team_roster(110, date(2026, 9, 6), client=first)
        second = RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]})
        reconcile_team_roster(111, SLATE, client=second)
        assert len(current_memberships(110)) == 1
        reconcile_team_roster(110, SLATE, client=RosterClient())
        for membership_type in ('active_roster', 'forty_man_roster'):
            rows = RosterMembershipInterval.query.filter_by(
                membership_type=membership_type
            ).order_by(RosterMembershipInterval.team_id).all()
            assert len(rows) == 2
            assert rows[0].effective_end_date == SLATE
            assert rows[1].effective_end_date is None
        assert Pitcher.query.one().team_id == 111
        assert {row.scope_key for row in SyncJob.query.filter_by(
            job_name='process_canonical_impact'
        ).all()} == {'110', '111'}


def test_interval_correction_supersedes_without_erasing_cited_history(app):
    with app.app_context():
        reconcile_team_roster(
            110, SLATE,
            client=RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]}),
        )
        prior = RosterMembershipInterval.query.filter_by(
            membership_type='active_roster'
        ).one()
        observation_id = prior.opened_by_observation_id
        corrected, mutation = supersede_membership_interval(
            prior.id,
            source_observation_id=observation_id,
            correction_reason='official boundary correction',
            effective_start_date=date(2026, 9, 6),
        )
        assert prior.is_current_version is False
        assert corrected.supersedes_interval_id == prior.id
        assert corrected.effective_start_date == date(2026, 9, 6)
        assert mutation.mutation_type == 'membership_corrected'
        assert RosterMembershipInterval.query.count() == 3


@pytest.mark.parametrize('completeness', ['partial', 'unknown'])
def test_incomplete_roster_never_closes_membership_or_clears_current_team(app, completeness):
    with app.app_context():
        reconcile_team_roster(
            110, SLATE,
            client=RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]}),
        )
        summary = reconcile_team_roster(
            110, SLATE,
            client=RosterClient(
                {'active': [], '40Man': []},
                completeness={'active': completeness, '40Man': 'complete'},
            ),
        )
        assert summary['authoritative'] is False
        assert summary['mutation_count'] == 0
        assert RosterMembershipInterval.query.filter_by(
            effective_end_date=None
        ).count() == 2
        assert Pitcher.query.one().team_id == 110


def test_roster_fetch_failure_records_attempt_and_preserves_known_good(app):
    with app.app_context():
        reconcile_team_roster(
            110, SLATE,
            client=RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]}),
        )
        with pytest.raises(RuntimeError, match='source down'):
            reconcile_team_roster(
                110, SLATE, client=RosterClient(exc=RuntimeError('source down')),
            )
        db.session.rollback()
        assert RosterMembershipInterval.query.filter_by(
            effective_end_date=None
        ).count() == 2
        assert SourceFetchAttempt.query.filter_by(status='failed').count() == 1


def test_non_pitcher_roster_entries_do_not_become_bullpen_members(app):
    client = RosterClient({
        'active': [_entry(800001, abbreviation='C', position_type='Catcher')],
        '40Man': [_entry(800001, abbreviation='C', position_type='Catcher')],
    })
    with app.app_context():
        summary = reconcile_team_roster(110, SLATE, client=client)
        assert summary['authoritative'] is True
        assert summary['mutation_count'] == 0
        assert Pitcher.query.count() == 0


def test_complete_empty_roster_is_empty_valid_authority(app):
    with app.app_context():
        observed = observe_team_roster(
            110, SLATE, 'active', client=RosterClient({'active': []}), commit=True,
        )
        assert observed.completeness == 'complete'
        assert observed.result.outcome == 'empty_valid'
        assert observed.result.observation.record_count == 0


def test_job_enqueue_dedupes_and_worker_links_run_and_observations(app):
    client = RosterClient({'active': [_entry(700001)], '40Man': [_entry(700001)]})
    with app.app_context():
        first = enqueue_roster_reconciliation(110, SLATE)
        second = enqueue_roster_reconciliation(110, SLATE)
        assert first.id == second.id
        completed = run_next_roster_transaction_job('sp05-test', client=client, timestamp=NOW)
        assert completed.status == 'succeeded'
        assert completed.sync_run_id is not None
        assert SourceObservation.query.filter_by(sync_job_id=completed.id).count() == 2


def test_transaction_endpoint_completeness_limit_contract():
    client = MLBApiClient()
    calls = []
    client._get = lambda endpoint, params=None: (
        calls.append((endpoint, params))
        or {'transactions': []}
    )
    result = client.get_transactions_with_completeness(
        '2026-09-01', '2026-09-07', limit=1000,
    )
    assert result.completeness == 'complete'
    assert result.records == []
    assert calls[0][1]['limit'] == 1000
    assert result.proof['pagination'] == 'no_offset_cursor_page_or_total_contract'

    client._get = lambda _endpoint, params=None: {
        'transactions': [{'id': value} for value in range(params['limit'])]
    }
    limited = client.get_transactions_with_completeness(
        '2026-01-01', '2026-09-07', limit=2,
    )
    assert limited.completeness == 'partial'
    assert limited.proof['limit_reached'] is True


class CompleteTransactionClient:
    def __init__(self, rows, completeness='complete', exc=None):
        self.rows = rows
        self.completeness = completeness
        self.exc = exc

    def get_transactions_with_completeness(self, **_kwargs):
        if self.exc:
            raise self.exc
        return MlbCollectionResult(
            records=list(self.rows),
            completeness=self.completeness,
            proof={'fixture': True, 'limit_reached': self.completeness == 'partial'},
        )

    def get_people_info(self, _ids):
        return {}

    def get_team_metadata(self, _season):
        return {}

    def get_team_roster(self, *_args, **_kwargs):
        return []


def _transaction(description='Recalled', to_team_id=110):
    return {
        'transaction_id': 'official-1',
        'transaction_date': SLATE.isoformat(),
        'player_mlb_id': 700001,
        'player_full_name': 'Transaction Pitcher',
        'transaction_type_code': 'RC',
        'transaction_type_description': description,
        'from_team_id': 555,
        'to_team_id': to_team_id,
        'source_endpoint': '/transactions',
    }


def test_transaction_versions_preserve_correction_and_description(app):
    with app.app_context():
        db.session.add(Pitcher(
            mlb_id=700001, full_name='Transaction Pitcher', team_id=110, active=True,
        ))
        db.session.commit()
        first = sync_transactions(
            start_date=SLATE, end_date=SLATE,
            client=CompleteTransactionClient([_transaction()]),
            timestamp=NOW,
        )
        corrected = sync_transactions(
            start_date=SLATE, end_date=SLATE,
            client=CompleteTransactionClient([_transaction('Recalled - corrected', 111)]),
            timestamp=datetime(2026, 9, 7, 15, 0, 0),
        )
        row = PlayerTransaction.query.one()
        versions = PlayerTransactionVersion.query.order_by(
            PlayerTransactionVersion.version_number
        ).all()
        assert first['records_created'] == 1
        assert corrected['records_corrected'] == 1
        assert row.transaction_type_description == 'Recalled - corrected'
        assert row.current_version_number == 2
        assert [item.version_number for item in versions] == [1, 2]
        assert versions[1].predecessor_version_id == versions[0].id
        assert versions[0].fact_json['to_team_id'] == 110
        assert versions[1].fact_json['to_team_id'] == 111
        assert corrected['affected_team_ids'] == [111, 555]


def test_partial_transaction_collection_never_mutates_canonical_rows(app):
    with app.app_context():
        summary = sync_transactions(
            start_date=SLATE, end_date=SLATE,
            client=CompleteTransactionClient([_transaction()], completeness='partial'),
        )
        assert summary['completeness'] == 'partial'
        assert summary['errors'] == 1
        assert PlayerTransaction.query.count() == 0
        assert SourceObservation.query.one().completeness == 'partial'


@pytest.mark.parametrize(
    ('code', 'expected'),
    [
        ('RC', CATEGORY_RECALL),
        ('OPT', CATEGORY_OPTION),
        ('IL_15', CATEGORY_IL_PLACEMENT),
        ('IL_ACTIVATION', CATEGORY_IL_ACTIVATION),
        ('TRD', CATEGORY_TRADE),
        ('DFA', CATEGORY_DFA),
        ('REL', CATEGORY_RELEASE),
    ],
)
def test_required_transaction_categories_remain_typed(code, expected):
    assert normalize_transaction_category(code) == expected


def test_transaction_job_enqueues_only_two_affected_teams(app):
    with app.app_context():
        db.session.add(Pitcher(
            mlb_id=700001, full_name='Transaction Pitcher', team_id=110, active=True,
        ))
        db.session.commit()
        job = enqueue_transaction_reconciliation(SLATE, SLATE)
        run_next_roster_transaction_job(
            'sp05-transactions',
            client=CompleteTransactionClient([_transaction(to_team_id=111)]),
            timestamp=NOW,
        )
        roster_jobs = SyncJob.query.filter_by(job_name='fetch_roster').all()
        assert job.status == 'succeeded'
        assert {row.scope_key for row in roster_jobs} == {'111'}


def test_transaction_worker_preserves_failure_evidence_and_enters_job_retry(app):
    with app.app_context():
        job = enqueue_transaction_reconciliation(SLATE, SLATE)
        with pytest.raises(RuntimeError, match='Official transaction acquisition failed'):
            run_next_roster_transaction_job(
                'sp05-transactions-failure',
                client=CompleteTransactionClient([], exc=RuntimeError('source down')),
            )
        db.session.expire_all()
        assert db.session.get(SyncJob, job.id).status == 'retry_wait'
        assert SourceFetchAttempt.query.filter_by(status='failed').count() == 1


def test_migration_upgrade_preserves_rows_and_downgrades():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('pitchers', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('sync_jobs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('source_observations', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    transactions = sa.Table(
        'player_transactions', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('transaction_key', sa.String(160), nullable=False),
    )
    snapshots = sa.Table(
        'roster_status_snapshots', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
    )
    metadata.create_all(engine)
    path = (
        Path(__file__).resolve().parents[1] / 'migrations' / 'versions'
        / 'f3c7a1d9e5b2_add_roster_transaction_authority.py'
    )
    spec = importlib.util.spec_from_file_location('sp05_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(transactions.insert().values(id=1, transaction_key='keep-me'))
        connection.execute(snapshots.insert().values(id=1))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert 'roster_membership_intervals' in names
        assert 'player_transaction_versions' in names
        assert connection.execute(sa.text(
            'SELECT transaction_key FROM player_transactions WHERE id = 1'
        )).scalar_one() == 'keep-me'
        migration.downgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert 'roster_membership_intervals' not in names
        assert 'player_transaction_versions' not in names


def test_same_team_concurrent_contract_is_postgresql_enforced(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL-only advisory lock and partial unique index proof')
        indexes = {item['name']: item for item in sa.inspect(db.engine).get_indexes(
            'roster_membership_intervals'
        )}
        assert indexes[
            'uq_roster_membership_intervals_current_open_player_team_type'
        ]['unique'] is True

    barrier = Barrier(2)

    def _reconcile():
        with app.app_context():
            barrier.wait(timeout=10)
            result = reconcile_team_roster(
                110,
                SLATE,
                client=RosterClient({
                    'active': [_entry(700001)],
                    '40Man': [_entry(700001)],
                }),
            )
            db.session.remove()
            return result['mutation_count']

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _value: _reconcile(), range(2)))

    with app.app_context():
        assert sorted(counts) == [0, 2]
        assert RosterMembershipInterval.query.count() == 2
        assert RosterMembershipMutation.query.count() == 2
        assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1
