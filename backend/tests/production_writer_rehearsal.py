"""Exercise the production role grants in a socket-only cluster with the real Alembic schema."""

from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import psycopg2
import pytest
from flask import Flask
from sqlalchemy.engine import URL

from sync_v3 import runtime_binding as binding
from sync_v3.handoff_admin import API, LEGACY, prepare, transition
from sync_v3.rehearse import isolated_cluster
from sync_v3.current_worker import verify_target
from sync_v3.generation import freeze_generation
from sync_v3.replay import run_fixture
from sync_v3.staging_projector import verify as verify_projector
from sync_v3.staging_publisher import check_scope
from sync_v3 import staging_product_delivery as delivery
from utils.db import db

REVISION = 'a' * 40


def exercise(host):
    def connect(role):
        return psycopg2.connect(host=host, port=5432, dbname='postgres', user=role)

    def url(role):
        return URL.create(
            'postgresql',
            username=role,
            host='localhost',
            database='postgres',
            query={'host': host, 'port': '5432'},
        )

    def app_for(role):
        app = Flask(role)
        app.config.update(SQLALCHEMY_DATABASE_URI=url(role), SECRET_KEY='isolated-test')
        db.init_app(app)
        return app

    def statements(role, *commands):
        with closing(connect(role)) as conn, conn, conn.cursor() as cur:
            for command in commands:
                cur.execute(command)

    statements('rehearsal_owner', 'CREATE ROLE fixture_setup LOGIN SUPERUSER')
    statements('fixture_setup', 'ALTER ROLE rehearsal_owner RENAME TO postgres')
    statements(
        'postgres',
        'DROP ROLE fixture_setup',
        'ALTER ROLE sync_v3_worker RENAME TO private_fixture_worker',
        'ALTER ROLE sync_v3_reviewer RENAME TO private_fixture_reviewer',
        'CREATE ROLE anon',
        'CREATE ROLE authenticated',
        'CREATE ROLE service_role BYPASSRLS',
    )
    env = dict(
        os.environ,
        DATABASE_URL=str(url('postgres')),
        TEST_DATABASE_URL=str(url('postgres')),
        APP_ENV='test',
        AUTO_SYNC='false',
        DATABASE_MIGRATION_MODE='owner',
    )
    subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', 'upgrade'], env=env, check=True)
    with closing(connect('postgres')) as admin, admin, admin.cursor() as cur:
        prepare(cur, REVISION)
        cur.execute('GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role')
        cur.execute('GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role')
        cur.execute('ALTER ROLE baseballos_product_api LOGIN')
        cur.execute('ALTER ROLE baseballos_legacy_sync LOGIN')

    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from services import dashboard_snapshot, public_serving_authority
    from services.tonight_read_model import generate_tonight_v1_for_snapshot
    from tests.test_trusted_publication_rehearsal import _seed_teams
    from utils.time import utc_now_naive

    # Install the same trusted publication hooks used by the web application.
    with app_for('postgres').app_context():
        day = public_serving_authority.product_current_date()
        _seed_teams(day)
    legacy_app = app_for(LEGACY)
    legacy_app.config.update(TRUSTED_PUBLIC_SERVING_ENABLED=True, TEAM_STATE_PUBLICATION_PROOF_REQUIRED=True)
    public_serving_authority.install_public_serving_authority(legacy_app)
    with legacy_app.app_context():
        run = SyncRun(
            job_name='daily_sync',
            source='daily_sync',
            status='success',
            stage='acquired',
            started_at=utc_now_naive(),
            completed_at=utc_now_naive(),
            latest_workload_date=day - timedelta(days=1),
        )
        db.session.add(run)
        db.session.flush()
        snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id, source='daily_sync', publish=False, commit=False, raise_errors=True
        )
        dashboard_snapshot.publish_dashboard_snapshot(snapshot, commit=False)
        assert snapshot.is_published
        tonight, _ = generate_tonight_v1_for_snapshot(snapshot, reference_date=day, commit=False)
        db.session.commit()
        receipt = delivery.legacy_predecessor_receipt(snapshot, day)
        pin = dict(database='postgres', database_edition=receipt, public_edition_sha256=None)
        root = snapshot.id
        frozen = snapshot.payload['trusted_team_boards']['frozen_team_state_by_team_id']
        source = dict(
            data_through=str(snapshot.data_through),
            availability_reference=str(snapshot.availability_reference_date),
            teams={team: dict(state=row['value']) for team, row in frozen.items()},
            source_count=len(frozen),
            official_slate=[
                dict(game_pk=g['game_pk'], home=g['home']['team_id'], away=g['away']['team_id'])
                for g in tonight.payload['games']
            ],
        )
        db.session.remove()
        db.engine.dispose()

    os.environ.update(APP_ENV='test', TEST_DATABASE_URL=str(url(API)), DATABASE_URL=str(url(API)))
    from app import app as public_app
    from scripts.verify_public_sync_edition import verify as verify_http

    public_app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    public_serving_authority.install_public_serving_authority(public_app)

    def public_fingerprint():
        with delivery.http_session(public_app) as (client, base):
            return verify_http(client, base, root, receipt['sync'])['public_edition_sha256']

    pin['public_edition_sha256'] = public_fingerprint()

    def handoff(old, new):
        with closing(connect('postgres')) as admin, admin, admin.cursor() as cur:
            transition(
                cur,
                old,
                new,
                REVISION,
                pin,
                drain=dict(
                    project=binding.PROJECT,
                    revision=REVISION,
                    endpoints=['DIRECT', 'SESSION', 'TRANSACTION'],
                    provider_operation='isolated-socket-fixture',
                ),
            )

    with closing(connect(LEGACY)) as held:
        statements('postgres', 'ALTER ROLE baseballos_legacy_sync NOLOGIN')
        with pytest.raises(ValueError, match='connected sessions'):
            handoff('legacy', 'v3')
        with held, held.cursor() as cur:
            cur.execute('SELECT 1')
            assert cur.fetchone() == (1,)
    statements(
        'postgres',
        'CREATE FUNCTION public.unreviewed() RETURNS int LANGUAGE sql SECURITY DEFINER AS $$ SELECT 1 $$',
    )
    with pytest.raises(ValueError, match='Callable definer'):
        handoff('legacy', 'v3')
    statements('postgres', 'DROP FUNCTION public.unreviewed()')
    with closing(connect('postgres')) as old_writer, old_writer.cursor() as cur:
        cur.execute('SET LOCAL ROLE service_role')
        cur.execute('UPDATE public.pitchers SET active=false WHERE false')
        with pytest.raises(psycopg2.errors.LockNotAvailable):
            handoff('legacy', 'v3')
    handoff('legacy', 'v3')
    for role in ('service_role', LEGACY, API, binding.PROJECTOR, binding.WORKER):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            statements(
                'postgres',
                'SET LOCAL ROLE ' + role,
                'UPDATE dashboard_snapshots SET is_published=false WHERE false',
            )

    from sync_v3.staging_publication_target import bind_active_staff

    with app_for(binding.PROJECTOR).app_context():
        staff = {7900000: 'Existing fixture pitcher', 8100123: 'New test identity'}
        assert bind_active_staff(staff, initialized=True) == dict(mapped=1, created=1, collisions=0)
        assert bind_active_staff(staff, initialized=True) == dict(mapped=2, created=0, collisions=0)
    fixture = Path(__file__).parent / 'fixtures/sync_v3/played.json'
    from datetime import date

    played = date.fromisoformat(json.loads(fixture.read_text())['baseball_date'])
    with closing(connect(binding.WORKER)) as worker:
        assert verify_target(worker) == 'postgres'
        run_fixture(worker, fixture)
        generation = freeze_generation(worker, played)
    with closing(connect(binding.WORKER)) as worker:
        assert freeze_generation(worker, played) == generation
    with closing(connect(binding.PROJECTOR)) as conn, conn, conn.cursor() as cur:
        verify_projector(cur)
        cur.execute(
            """INSERT INTO sync_runs(source,status,stage,job_name,started_at,created_at)
                       VALUES('sync_v3','success','canonical_ready','sync_v3_canonical_cycle',now(),now())"""
        )
    with closing(connect(binding.PUBLISHER)) as conn, conn.cursor() as cur:
        check_scope(cur, 'postgres')

    from api.audience import audience_bp
    from api.auth import auth_bp
    from api.me import me_bp
    from api.traffic import traffic_bp
    from tests.test_sync_v3_writer_fence import exercise_account_and_traffic

    web = app_for(API)
    for blueprint, path in (
        (audience_bp, 'audience'),
        (auth_bp, 'auth'),
        (me_bp, 'me'),
        (traffic_bp, 'traffic'),
    ):
        web.register_blueprint(blueprint, url_prefix='/api/' + path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr('api.auth.send_magic_link', lambda *args, **kwargs: None)
        patch.setattr('services.audience_signup.send_welcome_if_available', lambda subscriber: False)
        client = web.test_client()
        exercise_account_and_traffic(web, client)
        assert client.post('/api/audience/signup', json={'email': 'scope@example.invalid'}).json['success']
        from models.audience_subscriber import AudienceSubscriber
        from models.editorial_post_history import EditorialPostHistory

        with web.app_context():
            assert AudienceSubscriber.query.filter_by(email_normalized='scope@example.invalid').one()
            db.session.add(
                EditorialPostHistory(team_id=111, story_shape='isolated_fixture', posted_at=utc_now_naive())
            )
            db.session.commit()
            assert EditorialPostHistory.query.filter_by(story_shape='isolated_fixture').one()

    # Promote two successors in separate commits. Restore through both in a single publisher transaction.
    publisher_app = app_for(binding.PUBLISHER)
    publisher_app.config.update(TRUSTED_PUBLIC_SERVING_ENABLED=True, TEAM_STATE_PUBLICATION_PROOF_REQUIRED=True)
    public_serving_authority.install_public_serving_authority(publisher_app)
    os.environ['STAGING_LEGACY_PREDECESSOR'] = json.dumps(pin)
    with publisher_app.app_context():
        for digest in ('1' * 64, '2' * 64):
            edition = dict(source, generation=digest)
            prior_id, promoted = delivery.publish(edition, None, user=binding.PUBLISHER)
            assert promoted
            assert delivery.publish(edition, None, user=binding.PUBLISHER) == (prior_id, False)
            with db.session.begin():
                sync = db.session.get(DashboardSnapshot, prior_id).sync_run_id
            with delivery.http_session(public_app) as (client, base):
                assert verify_http(client, base, prior_id, sync)['clubs'] == 30
        with pytest.raises(ValueError, match='tip differs'):
            delivery.restore_handoff_root(prior_id, '3' * 64, pin, binding.PUBLISHER)
    statements('postgres', 'ALTER ROLE sync_v3_worker NOLOGIN', 'ALTER ROLE baseballos_v3_projector NOLOGIN')
    handoff('v3', 'rollback')
    with publisher_app.app_context():
        assert delivery.restore_handoff_root(prior_id, digest, pin, binding.PUBLISHER) == root
        assert delivery.restore_handoff_root(prior_id, digest, pin, binding.PUBLISHER) == root
        db.session.remove()
        db.engine.dispose()
    assert public_fingerprint() == pin['public_edition_sha256']
    statements('postgres', 'ALTER ROLE baseballos_v3_publisher NOLOGIN')
    handoff('rollback', 'legacy')
    statements(LEGACY, 'UPDATE dashboard_snapshots SET is_published=true WHERE false')


if __name__ == '__main__':
    with isolated_cluster(os.environ['SYNC_V3_TEST_PG_BIN']) as (owner, _):
        exercise(owner.info.host)
