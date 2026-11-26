"""Exercise the application/fact-writer boundary on disposable PostgreSQL."""
from contextlib import closing
import os
from uuid import uuid4

import psycopg2
import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from api.audience import audience_bp
from api.auth import auth_bp
from api.me import me_bp
from api.traffic import traffic_bp
from models.pitcher import Pitcher
from models.user import User, UserFollowedTeam
from models.traffic_page_view import TrafficPageView
from models.traffic_share_action import TrafficShareAction
from models.traffic_internal_visitor import TrafficInternalVisitor
from utils.auth_tokens import generate_magic_link_token
from models.audience_subscriber import AudienceSubscriber
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from scripts.inspect_sync_writer_binding import inspect
from sync_v3.rehearse import isolated_cluster
from utils.db import db


def exercise_account_and_traffic(app, client):
    email = 'fence@example.invalid'
    assert client.post('/api/auth/request-link', json={'email': email}).status_code == 200
    with app.app_context():
        token = generate_magic_link_token(email)
    verified = client.post('/api/auth/verify', json={'token': token})
    assert verified.status_code == 200
    headers = {'Authorization': 'Bearer ' + verified.json['token']}
    for team in (111, 121):
        assert client.post('/api/me/teams', json={'team_id': team}, headers=headers).status_code == 200
    assert client.put('/api/me/primary-team', json={'team_id': 121}, headers=headers).status_code == 200
    assert client.delete('/api/me/teams/111', headers=headers).status_code == 200
    visit = dict(visitor_id=str(uuid4()), session_id=str(uuid4()), site_host='baseballos.app')
    page = dict(visit, view_id=str(uuid4()), route='/dashboard', surface='dashboard')
    share = dict(visit, event_id=str(uuid4()), surface='bullpen_board', card_type='team', action='copy_link',
                 team_ref='BOS', evidence_target='team_read', data_through='2026-07-15')
    assert client.post('/api/traffic/page-view', json=page, headers=headers).status_code == 202
    assert client.post('/api/traffic/share-action', json=share, headers=headers).status_code == 202
    # Telemetry routes also return 202 for a rejected or failed write.
    with app.app_context():
        assert User.query.filter_by(email=email).one().email_verified_at
        assert UserFollowedTeam.query.one().team_id == 121 and UserFollowedTeam.query.one().is_primary
        assert TrafficPageView.query.filter_by(view_id=page['view_id']).count() == 1
        assert TrafficShareAction.query.filter_by(event_id=share['event_id']).count() == 1


def test_signup_and_publication_have_independent_write_authority(monkeypatch):
    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Requires disposable PostgreSQL')
    monkeypatch.setattr('services.audience_signup.send_welcome_if_available', lambda subscriber: False)
    monkeypatch.setattr('api.auth.send_magic_link', lambda *args, **kwargs: None)
    with isolated_cluster(bindir) as (owner, _):
        def url(role):
            return URL.create('postgresql+psycopg2', username=role, database=owner.info.dbname,
                              query={'host': owner.info.host})

        engine = create_engine(url(owner.info.user))
        with engine.begin() as conn:
            writes = {
                AudienceSubscriber: 'INSERT, UPDATE', User: 'INSERT, UPDATE', UserFollowedTeam: 'INSERT, UPDATE, DELETE',
                TrafficPageView: 'INSERT', TrafficShareAction: 'INSERT', TrafficInternalVisitor: 'INSERT',
            }
            for table in (SyncRun, DashboardSnapshot, Pitcher, *writes):
                table.__table__.create(conn)
            conn.execute(Pitcher.__table__.insert(), [dict(mlb_id=t, full_name="Fixture", team_id=t, active=True)
                                                     for t in (111, 121)])
            conn.exec_driver_sql('CREATE ROLE fixture_web LOGIN')
            conn.exec_driver_sql('GRANT CONNECT ON DATABASE sync_v3_rehearsal TO fixture_web')
            conn.exec_driver_sql('GRANT USAGE ON SCHEMA public TO fixture_web')
            conn.exec_driver_sql('GRANT SELECT ON public.dashboard_snapshots, public.pitchers TO fixture_web')
            for model, actions in writes.items():
                name = model.__tablename__
                conn.exec_driver_sql(f'GRANT SELECT, {actions} ON public.{name} TO fixture_web')
                conn.exec_driver_sql(f'GRANT USAGE ON SEQUENCE public.{name}_id_seq TO fixture_web')
                conn.exec_driver_sql(f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY')
                conn.exec_driver_sql(f'CREATE POLICY app_dml ON public.{name} TO fixture_web '
                                     'USING (true) WITH CHECK (true)')
        engine.dispose()

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = url('fixture_web')
        app.config['SECRET_KEY'] = str(uuid4())
        db.init_app(app)
        app.register_blueprint(audience_bp, url_prefix='/api/audience')
        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(me_bp, url_prefix='/api/me')
        app.register_blueprint(traffic_bp, url_prefix='/api/traffic')
        client = app.test_client()
        exercise_account_and_traffic(app, client)
        response = client.post('/api/audience/signup', json={'email': 'fence@example.invalid'})
        assert response.status_code == 200 and response.json['success']
        with app.app_context():
            assert AudienceSubscriber.query.filter_by(email_normalized='fence@example.invalid').count() == 1
        dsn = url('fixture_web').render_as_string(hide_password=False).replace('postgresql+psycopg2:', 'postgresql:')
        receipt = inspect(dsn)
        assert receipt['session_user'] == receipt['effective_role'] == 'fixture_web'
        assert set(receipt['catalog_write_paths']) == {f'public.{model.__tablename__}' for model in writes}
        with closing(psycopg2.connect(dsn)) as web, web.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute('UPDATE public.dashboard_snapshots SET is_published=false WHERE false')
        with owner, owner.cursor() as cur:
            cur.execute('GRANT UPDATE(is_published) ON public.dashboard_snapshots TO fixture_web')
        assert inspect(dsn)['catalog_write_paths']['public.dashboard_snapshots'] == ['update']
