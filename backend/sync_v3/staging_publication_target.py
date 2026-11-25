"""Install the product schema in a private logical database on the approved staging instance."""
import os
from contextlib import closing
from zoneinfo import ZoneInfo
from pathlib import Path
from time import monotonic

from alembic.script import ScriptDirectory
from flask import Flask
from flask_migrate import Migrate, upgrade
from sqlalchemy import URL, text

from services.migration_authority import read_current_heads, verify_heads
from utils.db import db

TARGET = 'baseballos_v3_publication_staging'


def install_target(password, worker_password):
    from sync_v3.render_staging import DATABASE, HOST, OWNER, connect

    start = monotonic()
    # CREATE DATABASE runs outside a transaction. Serialize creation and verification.
    with closing(connect(OWNER, password)) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('SELECT current_database(),current_user')
            if cur.fetchone() != (DATABASE, OWNER):
                raise ValueError('Unexpected staging installer')
            cur.execute('SELECT pg_advisory_lock(hashtext(%s))', (TARGET,))
            cur.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s', (TARGET,))
            existing = cur.fetchone()
            if existing is None:
                cur.execute('CREATE DATABASE baseballos_v3_publication_staging TEMPLATE template0')
            elif existing != (OWNER,):
                raise ValueError('Unexpected staging publication database owner')
            cur.execute('REVOKE ALL ON DATABASE baseballos_v3_publication_staging FROM PUBLIC')
            cur.execute("SELECT has_database_privilege('sync_v3_worker',%s,'CONNECT')", (TARGET,))
            if cur.fetchone() != (False,):
                raise ValueError('Acquisition worker can connect to publication staging')

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = URL.create(
            'postgresql+psycopg2', username=OWNER, password=password, host=HOST,
            port=5432, database=TARGET, query={'sslmode': 'require', 'connect_timeout': '10'})
        db.init_app(app)
        migrations = str(Path(__file__).resolve().parents[1] / 'migrations')
        Migrate(app, db, directory=migrations)
        expected = ScriptDirectory(migrations).get_current_head()
        with app.app_context():
            with db.engine.begin() as conn:
                identity = conn.execute(text('SELECT current_database(),current_user')).one()
                if tuple(identity) != (TARGET, OWNER):
                    raise ValueError('Unexpected publication migration target')
                conn.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
            os.environ['DATABASE_MIGRATION_MODE'] = 'owner'
            if read_current_heads(db.engine) != (expected,):
                upgrade(directory=migrations, revision=expected)
            verify_heads(read_current_heads(db.engine), expected)
            with db.engine.connect() as conn:
                sizes = conn.execute(text("""SELECT pg_database_size(current_database()),
                    (SELECT count(*) FROM public.dashboard_snapshots),
                    (SELECT count(*) FROM public.pitchers)""")).one()
            schedule = project_played_schedule(worker_password)
            db.engine.dispose()
    return dict(database=TARGET, migration=expected, database_bytes=sizes[0],
                snapshots=sizes[1], pitchers=sizes[2], schedule=schedule, elapsed_seconds=monotonic()-start)


def project_played_schedule(worker_password):
    """Use the verified August acquisition as input to the fenced product writer."""
    from sync_v3.render_staging import PLAYED_DAY, connect
    from sync_v3.discovery import calendar_requests
    from sync_v3.evidence import latest_qualified_source, replay
    from scripts.rehearse_selected_schedule import reconcile_schedule

    with closing(connect('sync_v3_worker', worker_password)) as source, source, source.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        freshness = acquisition_freshness(cur)
        request = calendar_requests(PLAYED_DAY)[0]
        receipt = latest_qualified_source(cur, request.endpoint, request.params())
        if receipt is None:
            raise ValueError('Private played-day acquisition lacks a qualified schedule')
        observation = replay(cur, receipt)
        cur.execute('SELECT sha256 FROM candidate.fetches WHERE id=%s', (receipt,))
        digest, = cur.fetchone()

    # The installer owns DDL. The canonical writer runs with table-scoped privileges.
    with db.engine.begin() as conn:
        found = conn.execute(text("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles "
                                  "WHERE rolname='sync_v3_staging_schedule'")).first()
        if found is None:
            conn.execute(text('CREATE ROLE sync_v3_staging_schedule NOLOGIN NOINHERIT'))
        elif tuple(found) != (False, False, False, False):
            raise ValueError('Unexpected staging schedule role attributes')
        conn.execute(text('GRANT sync_v3_staging_schedule TO baseballos_sync_v3_staging_user'))
        conn.execute(text('GRANT USAGE ON SCHEMA public TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT SELECT,INSERT,UPDATE ON scheduled_games,slate_games TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT SELECT ON compatibility_write_events TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT USAGE ON SEQUENCE scheduled_games_id_seq TO sync_v3_staging_schedule'))
        for table in ('scheduled_games', 'slate_games', 'compatibility_write_events'):
            operations = ('SELECT',) if table == 'compatibility_write_events' else ('SELECT', 'INSERT', 'UPDATE')
            for operation in operations:
                name = f'v3_staging_schedule_{operation.lower()}'
                present = conn.execute(text('SELECT 1 FROM pg_policies WHERE schemaname=:schema '
                                            'AND tablename=:table AND policyname=:name'),
                                       dict(schema='public', table=table, name=name)).first()
                if present is None:
                    clauses = {'SELECT': 'USING (true)', 'INSERT': 'WITH CHECK (true)',
                               'UPDATE': 'USING (true) WITH CHECK (true)'}
                    conn.execute(text(f'CREATE POLICY {name} ON public.{table} FOR {operation} '
                                      f'TO sync_v3_staging_schedule {clauses[operation]}'))

    for verify_only in (False, True):
        with db.session.begin():
            db.session.execute(text('SET LOCAL ROLE sync_v3_staging_schedule'))
            reconcile_schedule(PLAYED_DAY, observation, private_staging=True, verify_only=verify_only)
    return dict(day=str(PLAYED_DAY), receipt=receipt, sha256=digest, received_at=observation.retrieved_at.isoformat(),
                games=sum(len(d['games']) for d in observation.body['dates']), repeated=True,
                current_acquisition=freshness)

def acquisition_freshness(cur):
    """Report local acquisition age, qualified core coverage and ready backlog in one read view."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.discovery import calendar_requests, competition_calendar_request, roster_requests
    from sync_v3.evidence import latest_qualified_source

    cur.execute('SELECT transaction_timestamp()')
    at, = cur.fetchone()
    day = at.astimezone(ZoneInfo('America/New_York')).date()
    summary = {}
    groups = dict(calendar=calendar_requests(day)[:1], transactions=calendar_requests(day)[1:],
                  competition=[competition_calendar_request(day.year)], rosters=roster_requests(day, MLB_TEAM_IDS))
    for group, requests in groups.items():
        ages = []
        for request in requests:
            receipt = latest_qualified_source(cur, request.endpoint, request.params())
            if receipt is not None:
                cur.execute('SELECT received_at FROM candidate.fetches WHERE id=%s', (receipt,))
                age = (at - cur.fetchone()[0]).total_seconds()
                ages.append(round(age))
        summary[group] = dict(required=len(requests), qualified=len(ages), oldest_seconds=max(ages, default=None))
    cur.execute("""SELECT count(*), EXTRACT(EPOCH FROM transaction_timestamp()-min(j.available_at))::bigint
                   FROM candidate.jobs j WHERE j.budget='current' AND j.product_date<=%s
                   AND j.state='pending' AND j.available_at<=transaction_timestamp()
                   AND (j.prerequisite IS NULL OR EXISTS
                       (SELECT 1 FROM candidate.jobs p WHERE p.id=j.prerequisite AND p.state='done'))""", (day,))
    ready, waiting = cur.fetchone()
    return dict(measured_at=at.isoformat(), day=str(day), groups=summary, ready_jobs=ready, oldest_ready_seconds=waiting)
