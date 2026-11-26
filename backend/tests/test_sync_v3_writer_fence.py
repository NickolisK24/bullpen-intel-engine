"""Exercise the application/fact-writer boundary on disposable PostgreSQL."""
from contextlib import closing
import os

import psycopg2
import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from api.audience import audience_bp
from models.audience_subscriber import AudienceSubscriber
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from scripts.inspect_sync_writer_binding import inspect
from sync_v3.rehearse import isolated_cluster
from utils.db import db


def test_signup_and_publication_have_independent_write_authority(monkeypatch):
    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Requires disposable PostgreSQL')
    monkeypatch.setattr('services.audience_signup.send_welcome_if_available', lambda subscriber: False)
    with isolated_cluster(bindir) as (owner, _):
        def url(role):
            return URL.create('postgresql+psycopg2', username=role, database=owner.info.dbname,
                              query={'host': owner.info.host})

        engine = create_engine(url(owner.info.user))
        with engine.begin() as conn:
            for table in (SyncRun, DashboardSnapshot, AudienceSubscriber):
                table.__table__.create(conn)
            conn.exec_driver_sql('CREATE ROLE fixture_web LOGIN')
            conn.exec_driver_sql('GRANT CONNECT ON DATABASE sync_v3_rehearsal TO fixture_web')
            conn.exec_driver_sql('GRANT USAGE ON SCHEMA public TO fixture_web')
            conn.exec_driver_sql('GRANT SELECT ON public.dashboard_snapshots TO fixture_web')
            conn.exec_driver_sql('GRANT SELECT, INSERT, UPDATE ON public.audience_subscribers TO fixture_web')
            conn.exec_driver_sql('GRANT USAGE ON SEQUENCE public.audience_subscribers_id_seq TO fixture_web')
            conn.exec_driver_sql('ALTER TABLE public.audience_subscribers ENABLE ROW LEVEL SECURITY')
            conn.exec_driver_sql('CREATE POLICY app_signup ON public.audience_subscribers TO fixture_web '
                                 'USING (true) WITH CHECK (true)')
        engine.dispose()

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = url('fixture_web')
        db.init_app(app)
        app.register_blueprint(audience_bp, url_prefix='/api/audience')
        response = app.test_client().post('/api/audience/signup', json={'email': 'fence@example.invalid'})
        assert response.status_code == 200 and response.json['success']
        with app.app_context():
            assert AudienceSubscriber.query.filter_by(email_normalized='fence@example.invalid').count() == 1
        dsn = url('fixture_web').render_as_string(hide_password=False).replace('postgresql+psycopg2:', 'postgresql:')
        receipt = inspect(dsn)
        assert receipt['session_user'] == receipt['effective_role'] == 'fixture_web'
        assert set(receipt['catalog_write_paths']) == {'public.audience_subscribers'}
        with closing(psycopg2.connect(dsn)) as web, web.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute('UPDATE public.dashboard_snapshots SET is_published=false WHERE false')
        with owner, owner.cursor() as cur:
            cur.execute('GRANT UPDATE(is_published) ON public.dashboard_snapshots TO fixture_web')
        assert inspect(dsn)['catalog_write_paths']['public.dashboard_snapshots'] == ['update']
