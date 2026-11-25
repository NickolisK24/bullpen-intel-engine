"""Install the product schema in a private logical database on the approved staging instance."""
import os
from contextlib import closing
from pathlib import Path
from time import monotonic

from alembic.script import ScriptDirectory
from flask import Flask
from flask_migrate import Migrate, upgrade
from sqlalchemy import URL, text

from services.migration_authority import read_current_heads, verify_heads
from utils.db import db

TARGET = 'baseballos_v3_publication_staging'


def install_target(password):
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
            db.engine.dispose()
    return dict(database=TARGET, migration=expected, database_bytes=sizes[0],
                snapshots=sizes[1], pitchers=sizes[2], elapsed_seconds=monotonic()-start)
