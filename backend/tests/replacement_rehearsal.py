"""Exercise a logical move between private clusters and the existing writer handoff."""
from contextlib import closing
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import psycopg2
from psycopg2 import sql
import pytest

from scripts.verify_replacement_copy import compare
from sync_v3.rehearse import isolated_cluster
from sync_v3 import runtime_binding
from tests.production_writer_rehearsal import REVISION, exercise


def run():
    bindir = os.environ['SYNC_V3_TEST_PG_BIN']
    clients = Path(os.environ.get('SYNC_V3_TEST_PG_CLIENT_BIN', bindir))
    with isolated_cluster(bindir) as (original, _), isolated_cluster(bindir) as (fresh, _):
        target = fresh.info.host

        def connection(host, user='postgres', password=None):
            return psycopg2.connect(host=host, port=5432, dbname='postgres', user=user, password=password)

        with closing(connection(target, 'rehearsal_owner')) as admin, admin, admin.cursor() as cur:
            cur.execute('CREATE ROLE isolated_restore LOGIN SUPERUSER')
        with closing(connection(target, 'isolated_restore')) as admin, admin, admin.cursor() as cur:
            cur.execute('ALTER ROLE rehearsal_owner RENAME TO postgres')
            for role in ('anon', 'authenticated', 'service_role'):
                cur.execute(f'CREATE ROLE {role}')
            cur.execute('ALTER ROLE service_role BYPASSRLS')
            cur.execute('ALTER ROLE sync_v3_worker RENAME TO fixture_worker')
            cur.execute('ALTER ROLE sync_v3_reviewer RENAME TO fixture_reviewer')

        def transfer(source):
            started = time.monotonic()
            password = secrets.token_urlsafe(32)
            with closing(connection(source)) as admin, admin, admin.cursor() as cur:
                cur.execute('ALTER ROLE postgres PASSWORD %s', (password,))
                cur.execute('INSERT INTO users(email,created_at) VALUES (%s,now())', ('migrated@example.invalid',))
            replacement_password = secrets.token_urlsafe(32)
            with closing(connection(target)) as admin, admin, admin.cursor() as cur:
                cur.execute('ALTER ROLE postgres PASSWORD %s', (replacement_password,))
                cur.execute('SHOW hba_file')
                hba = Path(cur.fetchone()[0])
                # Both servers expose only their own private mode-0700 Unix socket.
                with hba.open('r+') as file:
                    previous = file.read()
                    file.seek(0)
                    file.write('local postgres postgres scram-sha-256\n' + previous)
                cur.execute('SELECT pg_reload_conf()')
            with closing(connection(target, password=replacement_password)):
                pass
            with pytest.raises(psycopg2.OperationalError, match='password authentication failed'):
                connection(target, password=password)
            # Use the destination's independent fixture administrator to restore.
            with closing(connection(source)) as held, tempfile.TemporaryDirectory() as temp:
                archive = Path(temp) / 'product.dump'
                env = dict(os.environ, PGDATABASE='postgres', PGPORT='5432')
                with closing(connection(source)) as freeze, freeze, freeze.cursor() as lock:
                    lock.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                    tables = [sql.Identifier('public', name) for name, in lock.fetchall()]
                    lock.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE NOWAIT').format(sql.SQL(',').join(tables)))
                    with closing(connection(source)) as writer, pytest.raises(psycopg2.errors.LockNotAvailable):
                        with writer, writer.cursor() as cur:
                            cur.execute("SET LOCAL lock_timeout='100ms'")
                            cur.execute("UPDATE public.users SET onboarded_at=now()")
                    subprocess.run([clients / 'pg_dump', '-Fc', '-n', 'public', '-n', 'roster_history_repair',
                                    '-n', 'transaction_history_repair','-f', archive],
                                   env=dict(env, PGHOST=source, PGUSER='postgres'), check=True)
                    listing = subprocess.check_output([clients / 'pg_restore', '--list', archive], text=True)
                    toc = Path(temp) / 'restore.list'
                    toc.write_text(''.join(line for line in listing.splitlines(True)
                                           if not re.match(r'^\d+; \d+ \d+ SCHEMA - public ', line)))
                    subprocess.run([clients / 'pg_restore', '--use-list', toc, '--exit-on-error', '--single-transaction',
                                    '--no-owner', '--role=postgres', '-d', 'postgres', archive],
                                   env=dict(env, PGHOST=target, PGUSER='isolated_restore'), check=True)
                    with closing(connection(target, 'isolated_restore')) as dest:
                        receipt = compare(held, dest)
                held.set_session(readonly=False)
                with held, held.cursor() as cur:
                    cur.execute("UPDATE users SET email='source-only@example.invalid' WHERE email='migrated@example.invalid'")
                    assert cur.rowcount == 1
                with closing(connection(target, 'isolated_restore')) as dest, dest, dest.cursor() as cur:
                    cur.execute("SELECT email FROM users")
                    assert cur.fetchall() == [('migrated@example.invalid',)]
                with closing(connection(target, 'isolated_restore')) as dest:
                    with pytest.raises(ValueError, match='public.users'):
                        compare(held, dest)
                print(json.dumps(dict(**receipt, archive_bytes=archive.stat().st_size,
                                      elapsed_seconds=round(time.monotonic()-started, 2))), flush=True)
            # Local fixture now authenticates the test harness through its private socket again.
            hba.write_text(previous)
            with closing(connection(target, 'isolated_restore')) as admin, admin, admin.cursor() as cur:
                cur.execute('SELECT pg_reload_conf()')
            runtime_binding.PROJECT = 'isolated-replacement'
            runtime_binding.ORIGINAL_CLUSTER = receipt['source_cluster']
            runtime_binding.REPLACEMENT_CLUSTER = receipt['target_cluster']
            with closing(connection(target)) as admin, admin, admin.cursor() as cur:
                cur.execute('DROP ROLE isolated_restore')
            return target, dict(receipt, revision=REVISION)

        exercise(original.info.host, transfer)
        with closing(connection(target, 'baseballos_product_api')) as app, app, app.cursor() as cur:
            cur.execute("SELECT count(*) FROM users WHERE email IN ('migrated@example.invalid','fence@example.invalid')")
            assert cur.fetchone() == (2,)
            cur.execute('SELECT count(*) FROM user_followed_teams WHERE is_primary')
            assert cur.fetchone() == (1,)
        print('Replacement publication, API writes, and same-target rollback passed.', flush=True)


if __name__ == '__main__':
    run()
