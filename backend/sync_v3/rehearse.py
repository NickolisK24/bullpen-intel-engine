"""Create an isolated socket-only PostgreSQL cluster and run the v3 rehearsal."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import psycopg2


RUNTIME = 'sync_v3_worker'
DATABASE = 'sync_v3_rehearsal'
SCHEMA = 'candidate'


def _binary(name, bindir):
    executable = str(Path(bindir) / name) if bindir else shutil.which(name)
    if not executable or not os.access(executable, os.X_OK):
        raise RuntimeError(f'{name} is required; use --pg-bin for a local PostgreSQL installation')
    return executable


@contextmanager
def isolated_cluster(bindir=None):
    initdb = _binary('initdb', bindir)
    pg_ctl = _binary('pg_ctl', bindir)
    # No ambient application or libpq configuration is inherited by the server.
    env = {key: os.environ[key] for key in ('PATH', 'LD_LIBRARY_PATH', 'LANG') if key in os.environ}
    with tempfile.TemporaryDirectory(prefix='bos-v3-', dir='/tmp') as tmp:
        data = Path(tmp) / 'data'
        subprocess.run([initdb, '-D', str(data), '-U', 'rehearsal_owner', '-A', 'trust',
                        '--no-locale', '--encoding=UTF8'], env=env, check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([pg_ctl, '-D', str(data), '-l', str(Path(tmp) / 'server.log'),
                        '-o', f"-k {tmp} -c listen_addresses='' -c unix_socket_permissions=0700",
                        '-w', 'start'], env=env, check=True, stdout=subprocess.DEVNULL)
        try:
            # Expand only this absolute, newly created UNIX socket directory.
            # Explicit host, port, database and role keep connections on this cluster.
            def connect(dbname, user):
                return psycopg2.connect(host=tmp, port=5432, dbname=dbname, user=user,
                                        options='-c search_path=pg_catalog', connect_timeout=5)

            admin = connect('postgres', 'rehearsal_owner')
            try:
                admin.autocommit = True
                with admin.cursor() as cur:
                    cur.execute('SHOW listen_addresses')
                    assert cur.fetchone() == ('',)
                    cur.execute('CREATE ROLE sync_v3_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
                    cur.execute('CREATE DATABASE sync_v3_rehearsal')
                    for dbname in ('postgres', 'template1', DATABASE):
                        cur.execute(f'REVOKE ALL ON DATABASE {dbname} FROM PUBLIC')
                    cur.execute('GRANT CONNECT ON DATABASE sync_v3_rehearsal TO sync_v3_worker')
            finally:
                admin.close()
            owner = connect(DATABASE, 'rehearsal_owner')
            try:
                with owner, owner.cursor() as cur:
                    cur.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
                    cur.execute('CREATE SCHEMA candidate')
                    cur.execute('GRANT USAGE ON SCHEMA candidate TO sync_v3_worker')
                yield owner, lambda: connect(DATABASE, RUNTIME)
            finally:
                owner.close()
        finally:
            subprocess.run([pg_ctl, '-D', str(data), '-m', 'fast', '-w', 'stop'],
                           check=True, env=env, stdout=subprocess.DEVNULL)


def run(bindir=None, fixture=None, pitcher=None, through=None):
    with isolated_cluster(bindir) as (owner, connect):
        with owner, owner.cursor() as cur:
            cur.execute('CREATE TABLE public.legacy_pointer (generation integer PRIMARY KEY)')
            cur.execute('INSERT INTO public.legacy_pointer VALUES (1)')
        worker = connect()
        try:
            with worker, worker.cursor() as cur:
                cur.execute("""SELECT current_database(), current_user, inet_server_addr(),
                               has_database_privilege('postgres','CONNECT'),
                               has_schema_privilege('public','CREATE'),
                               has_schema_privilege('candidate','CREATE')""")
                identity = cur.fetchone()
                if identity != (DATABASE, RUNTIME, None, False, False, False):
                    raise RuntimeError(f'Unexpected rehearsal isolation properties: {identity!r}')
            try:
                with worker, worker.cursor() as cur:
                    cur.execute('UPDATE public.legacy_pointer SET generation=2')
            except psycopg2.errors.InsufficientPrivilege:
                pass
            else:
                raise RuntimeError('Worker could modify the legacy selector')
            with owner, owner.cursor() as cur:
                cur.execute('SELECT generation FROM public.legacy_pointer')
                if cur.fetchall() != [(1,)]:
                    raise RuntimeError('Legacy selector changed')
            if fixture:
                from sync_v3.replay import install, run_fixture
                install(owner)
                count = 0
                for filename in fixture:
                    count += run_fixture(worker, filename)
                from sync_v3.comparison import compare_finals
                with worker, worker.cursor() as cur:
                    games, appearances = compare_finals(cur)
                print(f'{count} observations replayed; {games} finals and {appearances} pitching lines compared')
            if pitcher is not None:
                import json
                from sync_v3.workload import pitcher_windows
                with worker, worker.cursor() as cur:
                    print(json.dumps(pitcher_windows(cur, pitcher, through), sort_keys=True))
            print(f'PostgreSQL {worker.server_version}: isolated cluster, worker permissions verified')
        finally:
            worker.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin')
    parser.add_argument('--fixture', action='append', help='Path to an offline day (repeat to replay history)')
    from datetime import date
    parser.add_argument('--pitcher', type=int, help='Inspect historical relief workload for an MLB ID')
    parser.add_argument('--through', type=date.fromisoformat)
    args = parser.parse_args()
    if (args.pitcher is None) != (args.through is None) or (args.pitcher is not None and not args.fixture):
        parser.error('Supply --pitcher and --through together with at least one --fixture')
    run(args.pg_bin, args.fixture, args.pitcher, args.through)
