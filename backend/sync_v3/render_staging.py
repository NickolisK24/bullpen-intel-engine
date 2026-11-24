"""Install or exercise the isolated Ohio staging database through Render's private network."""
import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extensions import encrypt_password, parse_dsn

from sync_v3.current_worker import process, verify_target
from sync_v3.replay import install

HOST = 'dpg-dc2t51mc6qcc738080hg-a'
DATABASE = 'baseballos_sync_v3_staging'
OWNER = 'baseballos_sync_v3_staging_user'


def connect(user, password):
    return psycopg2.connect(host=HOST, port=5432, dbname=DATABASE, user=user, password=password,
                            connect_timeout=10, options='-c search_path=pg_catalog',
                            application_name='baseballos_v3_staging', sslmode='require')


def bootstrap(password):
    binding = parse_dsn(os.environ['STAGING_OWNER_DSN'])
    if (binding.get('host'), binding.get('dbname'), binding.get('user')) != (HOST, DATABASE, OWNER):
        raise ValueError('Render owner binding differs from the approved staging instance')
    with closing(connect(OWNER, binding['password'])) as owner:
        with owner.cursor() as cur:
            cur.execute("""SELECT current_database(),current_user,current_setting('server_version_num')::int/10000,
                                  to_regnamespace('candidate') IS NULL""")
            database, role, major, fresh = cur.fetchone()
            if (database, role, major) != (DATABASE, OWNER, 17):
                raise ValueError('Unexpected staging owner or database')
            if fresh:
                cur.execute('CREATE ROLE sync_v3_reviewer NOLOGIN NOINHERIT')
                cur.execute('CREATE ROLE sync_v3_worker LOGIN NOINHERIT PASSWORD %s',
                            (encrypt_password(password, 'sync_v3_worker', owner, 'scram-sha-256'),))
                cur.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
                cur.execute('CREATE SCHEMA candidate')
                cur.execute('GRANT USAGE ON SCHEMA candidate TO sync_v3_worker,sync_v3_reviewer')
        if fresh:
            install(owner)
    with closing(connect('sync_v3_worker', password)) as worker:
        verify_target(worker)
    print(json.dumps(dict(database=DATABASE, installed=fresh, worker_admitted=True)))


def witness(worker):
    with worker, worker.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT id,sha256 FROM candidate.fetches WHERE outcome='received' ORDER BY id LIMIT 1""")
        first = cur.fetchone()
        cur.execute('SELECT count(*) FROM candidate.fetches')
        count, = cur.fetchone()
        cur.execute('SELECT count(*) FROM candidate.core_selections')
        if cur.fetchone() != (0,):
            raise ValueError('Staging acquisition requires an empty selector')
        return dict(first=first, receipts=count)


def acquire(password):
    with closing(connect('sync_v3_worker', password)) as worker:
        verify_target(worker)
        before = witness(worker)
        day = datetime.now(ZoneInfo('America/New_York')).date()
        report = process(worker, day, max_jobs=128 if before['first'] else 1)
        after = witness(worker)
        if before['first'] and before['first'] != after['first']:
            raise ValueError('Prior acquisition receipt changed')
        print(json.dumps(dict(before=before, after=after, report=report)), flush=True)
        if set(report['receipts']) - {'received'} or report['jobs_for_date'].get('dead'):
            raise ValueError('Incomplete staging acquisition')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('bootstrap', 'acquire'))
    args = parser.parse_args()
    try:
        (bootstrap if args.operation == 'bootstrap' else acquire)(os.environ['STAGING_WORKER_PASSWORD'])
    except psycopg2.Error as exc:
        parser.exit(1, f'Staging database operation failed ({exc.pgcode or type(exc).__name__}).\n')
