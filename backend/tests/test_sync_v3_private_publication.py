"""Regression checks for the private hosted edition and rollback entry points."""
from contextlib import closing
from datetime import date
import json
import os
from pathlib import Path

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot as Snapshot
from models.sync_run import SyncRun
from sync_v3.generation import freeze_generation
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install, run_fixture
from sync_v3.staging_product_delivery import OWNER, TARGET, restore_predecessor
from sync_v3.staging_publication_target import recheck_edition_transactions
from utils.db import db


@pytest.fixture
def pg():
    path = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not path:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    return path


def test_official_transaction_recheck_creates_one_successor_across_restarts(pg):
    fixture = Path(__file__).parent / 'fixtures/sync_v3/played.json'
    archive = json.loads(fixture.read_text())
    day = date.fromisoformat(archive['baseball_date'])
    body = next(row['body'] for row in archive['responses'] if row['endpoint'] == '/transactions')
    with isolated_cluster(pg) as (admin, connect):
        install(admin)
        with closing(connect()) as worker:
            run_fixture(worker, fixture)
            predecessor = freeze_generation(worker, day)
            first = recheck_edition_transactions(worker, day, predecessor, lambda endpoint, params: body)
            assert first['acquired']
        with closing(connect()) as worker:
            repeated = recheck_edition_transactions(worker, day, predecessor, pytest.fail)
            assert not repeated['acquired'] and repeated['source_id'] == first['source_id']
            assert freeze_generation(worker, day) != predecessor


def test_rollback_restores_predecessor_and_refuses_an_unexpected_run_binding(pg):
    with isolated_cluster(pg) as (admin, _):
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('CREATE ROLE baseballos_sync_v3_staging_user LOGIN')
            cur.execute('CREATE DATABASE baseballos_v3_roster_staging OWNER baseballos_sync_v3_staging_user')
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{OWNER}@localhost/{TARGET}?host={admin.info.host}'
        db.init_app(app)
        with app.app_context():
            SyncRun.__table__.create(db.engine)
            Snapshot.__table__.create(db.engine)
            day = date(2017, 8, 28)
            digest = 'a' * 64
            with db.session.begin():
                old_run, new_run, other_run = [SyncRun(status='success') for _ in range(3)]
                db.session.add_all([old_run, new_run, other_run])
                db.session.flush()
                old = Snapshot(snapshot_type='bullpen_dashboard', sync_run_id=old_run.id, data_through=day,
                               availability_reference_date=day, is_published=False, source='v3_private_publication')
                db.session.add(old)
                db.session.flush()
                state = {'public_state': 'normal'}
                old.payload = dict(
                    v3_source_generation=dict(teams={'108': {'state': state}}, data_through=str(day),
                                              availability_reference=str(day)),
                    trusted_team_boards=dict(frozen_team_state_by_team_id={
                        '108': dict(team_id=108, dashboard_snapshot_id=old.id, value=state)}))
                new = Snapshot(snapshot_type=old.snapshot_type, sync_run_id=new_run.id, source='v3_private_publication',
                               is_published=True, payload=dict(v3_source_generation={'generation': digest},
                                                              v3_predecessor_runs=[old_run.id], v3_predecessor=old.id))
                db.session.add(new)
                db.session.flush()
                old_id, new_id = old.id, new.id
                for row in (old_run, new_run, other_run):
                    row.published_dashboard_snapshot_id = new_id
            with pytest.raises(ValueError, match='authority changed'):
                restore_predecessor(digest, new_id)
            with db.session.begin():
                assert db.session.get(Snapshot, new_id).is_published
                other_run.published_dashboard_snapshot_id = None
            assert restore_predecessor(digest, new_id) == old_id
            assert restore_predecessor(digest, new_id) == old_id
            assert db.session.get(Snapshot, old_id).is_published
            assert not db.session.get(Snapshot, new_id).is_published
            assert old_run.published_dashboard_snapshot_id == old_id
            assert new_run.published_dashboard_snapshot_id is None


def test_private_product_reader_can_read_rls_rows_and_detect_grant_drift(pg, monkeypatch):
    import psycopg2
    from sync_v3 import staging_reader

    with isolated_cluster(pg) as (admin, _):
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('CREATE ROLE baseballos_sync_v3_staging_user LOGIN CREATEROLE')
            cur.execute('CREATE DATABASE baseballos_v3_roster_staging OWNER baseballos_sync_v3_staging_user')
            cur.execute('REVOKE ALL ON DATABASE baseballos_v3_roster_staging FROM PUBLIC')

        def connect(user, password):
            return psycopg2.connect(host=admin.info.host, dbname=TARGET, user=user, password=password)

        monkeypatch.setattr(staging_reader, '_connect', connect)
        with closing(connect(OWNER, '')) as owner, owner, owner.cursor() as cur:
            cur.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            cur.execute('CREATE TABLE dashboard_snapshots(id int)')
            cur.execute('INSERT INTO dashboard_snapshots VALUES (5)')
            cur.execute('ALTER TABLE dashboard_snapshots ENABLE ROW LEVEL SECURITY')
            cur.execute('CREATE TABLE users(id int)')
        tables = {'dashboard_snapshots'}
        staging_reader.install('', 'private-test-reader', tables)
        staging_reader.install('', 'private-test-reader', tables)
        with closing(connect(staging_reader.READER, 'private-test-reader')) as reader:
            with reader, reader.cursor() as cur:
                cur.execute('SELECT id FROM dashboard_snapshots')
                assert cur.fetchall() == [(5,)]
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), reader, reader.cursor() as cur:
                cur.execute('SELECT id FROM users')
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), reader, reader.cursor() as cur:
                cur.execute('SET TRANSACTION READ WRITE')
                cur.execute('UPDATE dashboard_snapshots SET id=6')
            with closing(connect(OWNER, '')) as owner, owner, owner.cursor() as cur:
                cur.execute('GRANT UPDATE ON dashboard_snapshots TO baseballos_v3_staging_product_reader')
            with pytest.raises(ValueError, match='grants differ'):
                staging_reader.verify(reader, tables)


def test_private_publisher_cannot_modify_source_or_product_facts(pg, monkeypatch):
    import psycopg2
    from psycopg2 import sql
    from sync_v3 import staging_publisher as publisher
    from sync_v3.replay import schema_digest, schema_scripts

    with isolated_cluster(pg) as (admin, _):
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('CREATE ROLE baseballos_sync_v3_staging_user LOGIN CREATEROLE')
            for database in (TARGET, publisher.DATABASE):
                cur.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(database), sql.Identifier(OWNER)))
                cur.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(database)))

        def connect(database, user, password):
            return psycopg2.connect(host=admin.info.host, dbname=database, user=user, password=password)

        monkeypatch.setattr(publisher, '_connect', lambda u, p: connect(TARGET, u, p))
        monkeypatch.setattr(publisher, 'connect', lambda u, p: connect(publisher.DATABASE, u, p))
        with closing(connect(TARGET, OWNER, '')) as target, target, target.cursor() as cur:
            for name in publisher.READ:
                relation = sql.Identifier(name)
                cur.execute(sql.SQL('CREATE TABLE {} (id serial PRIMARY KEY)').format(relation))
                cur.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(relation))
        with closing(connect(publisher.DATABASE, OWNER, '')) as source, source, source.cursor() as cur:
            cur.execute('CREATE SCHEMA candidate')
            cur.execute('CREATE TABLE candidate.schema_installation (singleton boolean, digest text)')
            cur.execute('INSERT INTO candidate.schema_installation VALUES(true,%s)', (schema_digest(schema_scripts()),))
        publisher.install('', 'test-private-publisher')
        with closing(connect(TARGET, publisher.PUBLISHER, 'test-private-publisher')) as target:
            with target, target.cursor() as cur:
                cur.execute('INSERT INTO dashboard_snapshots DEFAULT VALUES RETURNING id')
                assert cur.fetchone() == (1,)
                cur.execute('UPDATE dashboard_snapshots SET id=2 WHERE id=1')
                assert cur.rowcount == 1
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), target, target.cursor() as cur:
                cur.execute('INSERT INTO game_logs DEFAULT VALUES')
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), target, target.cursor() as cur:
                cur.execute('DELETE FROM dashboard_snapshots')
        with closing(connect(publisher.DATABASE, publisher.PUBLISHER, 'test-private-publisher')) as source:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege), source, source.cursor() as cur:
                cur.execute('UPDATE candidate.schema_installation SET digest=NULL')


def test_current_board_requires_exact_workload_cohort_and_dated_membership():
    from types import SimpleNamespace
    from models.pitcher import Pitcher
    from sync_v3.staging_product_delivery import verify_board_rosters

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    db.init_app(app)
    with app.app_context():
        Pitcher.__table__.create(db.engine)
        db.session.add_all([Pitcher(id=7, mlb_id=547973, full_name='Aroldis Chapman'),
                            Pitcher(id=8, mlb_id=523260, full_name='Joe Kelly')])
        db.session.flush()
        club = dict(default_pitcher_ids=[7])
        snapshot = SimpleNamespace(payload=dict(trusted_team_boards=dict(by_team_id={'111': club})))
        binding = dict(product_day='2026-11-25', active_pitcher_mlb_ids={'111': [547973]},
                       reviewed_board_mlb_ids={'111': [547973]})
        verify_board_rosters(snapshot, binding)
        club['default_pitcher_ids'] = [7, 8]
        with pytest.raises(ValueError, match='outside the official active roster'):
            verify_board_rosters(snapshot, binding)
        for ids in ([], [7, 7]):
            club['default_pitcher_ids'] = ids
            with pytest.raises(ValueError, match='differs from the qualified official workload'):
                verify_board_rosters(snapshot, binding)


def test_projector_can_record_club_reviews_but_cannot_select_a_publication(pg, monkeypatch):
    import psycopg2
    from psycopg2 import sql
    from sync_v3 import staging_projector as projector, staging_publisher as publisher

    with isolated_cluster(pg) as (admin, _):
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('CREATE ROLE baseballos_sync_v3_staging_user LOGIN CREATEROLE')
            cur.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(TARGET), sql.Identifier(OWNER)))
            cur.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(TARGET)))

        def connect(user, password):
            return psycopg2.connect(host=admin.info.host, dbname=TARGET, user=user, password=password)

        monkeypatch.setattr(projector, '_connect', connect)
        monkeypatch.setattr(publisher, '_connect', connect)
        with closing(connect(OWNER, '')) as owner, owner, owner.cursor() as cur:
            for table in projector.READ | {'dashboard_snapshots'}:
                name = sql.Identifier(table)
                primary_key = sql.SQL('game_pk integer') if table == 'slate_games' else sql.SQL('id serial')
                cur.execute(sql.SQL('CREATE TABLE {} ({} PRIMARY KEY, source text, job_name text, '
                                    'status text, stage text, published_dashboard_snapshot_id integer)')
                            .format(name, primary_key))
                cur.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(name))
        projector.install('', 'local-test-password')
        with closing(connect(projector.PROJECTOR, 'local-test-password')) as runtime:
            with runtime, runtime.cursor() as cur:
                cur.execute("INSERT INTO sync_runs(source,job_name,status,stage) "
                            "VALUES ('sync_v3_staging','sync_v3_board_review_111','success','reviewed')")
                cur.execute("INSERT INTO sync_runs(source,job_name,status,stage) "
                            "VALUES ('sync_v3_staging','sync_v3_roster_reconciliation','success','verified_roster_observations')")
            for statement in ("SELECT setval('pitchers_id_seq', 300)",
                              "INSERT INTO sync_runs(source,job_name,status,stage) "
                              "VALUES ('sync_v3_staging','daily_sync','success','reviewed')",
                              "UPDATE sync_runs SET published_dashboard_snapshot_id=1",
                              "INSERT INTO dashboard_snapshots DEFAULT VALUES"):
                with pytest.raises(psycopg2.errors.InsufficientPrivilege), runtime, runtime.cursor() as cur:
                    cur.execute(statement)


def test_projector_process_receives_only_its_two_required_logins(monkeypatch):
    from sync_v3.render_staging import runtime_environment
    for key in ('STAGING_PROJECTOR_PASSWORD', 'STAGING_PRODUCT_PUBLISHER_PASSWORD', 'STAGING_OWNER_DSN',
                'STAGING_WORKER_PASSWORD', 'DATABASE_URL'):
        monkeypatch.setenv(key, 'test')
    env = runtime_environment('STAGING_WORKER_PASSWORD', 'STAGING_PROJECTOR_PASSWORD')
    assert set(env) & {'STAGING_OWNER_DSN','DATABASE_URL','STAGING_PRODUCT_PUBLISHER_PASSWORD'} == set()
    assert env['AUTO_SYNC'] == 'false' and env['STAGING_PROJECTOR_PASSWORD'] == env['STAGING_WORKER_PASSWORD'] == 'test'
