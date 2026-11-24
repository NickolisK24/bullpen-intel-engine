"""Run today's source worker and restore its private checkpoint on a fresh server."""
import argparse
from contextlib import closing
from datetime import date
from hashlib import file_digest, sha256
import json
from pathlib import Path
import subprocess

from psycopg2 import sql
from sync_v3.current_worker import process, verify_target
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install


def inventory(connection):
    """Compare logical rows independently of PostgreSQL's physical placement."""
    totals = {}
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT tablename FROM pg_tables WHERE schemaname='candidate' ORDER BY tablename""")
        tables = [name for name, in cur]
        for name in tables:
            # Hash large payloads directly in PostgreSQL. Only row hashes
            # cross the socket. Preserve multiplicity and ignore physical order.
            row_value = sql.SQL('to_jsonb(t)::text') if name != 'payloads' else sql.SQL(
                "sha256 || ':' || encode(sha256(encoded_json),'hex')")
            cur.execute(sql.SQL("""SELECT encode(sha256(convert_to({},'UTF8')),'hex') AS digest
                                   FROM candidate.{} t ORDER BY digest""").format(row_value, sql.Identifier(name)))
            digest = sha256()
            for row_digest, in cur:
                digest.update(bytes.fromhex(row_digest))
            totals[name] = dict(rows=cur.rowcount, sha256=digest.hexdigest())
        cur.execute("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='candidate' ORDER BY sequencename")
        totals['sequences'] = dict(cur.fetchall())
        cur.execute("SELECT count(*) FROM candidate.payloads WHERE sha256 <> encode(sha256(encoded_json),'hex')")
        if cur.fetchone() != (0,):
            raise ValueError('Stored MLB response differs from its retained digest')
    return totals


def run(day, directory, bindir, client_bin):
    dump = directory / 'current-worker.pgdump'
    report = {}
    with isolated_cluster(bindir) as (owner, connect):
        install(owner)
        with closing(connect()) as worker:
            report['first_batch'] = process(worker, day, max_jobs=1)
        with closing(connect()) as worker:
            report['second_batch'] = process(worker, day, max_jobs=256)
        report['source'] = inventory(owner)
        subprocess.run([client_bin / 'pg_dump', '-h', owner.info.host, '-U', owner.info.user, '-d', owner.info.dbname,
                        '--format=custom', '--schema=candidate', '--no-owner', '--file', dump], check=True)
    with dump.open('rb') as data:
        report['checkpoint_sha256'] = file_digest(data, 'sha256').hexdigest()
    report['checkpoint_bytes'] = dump.stat().st_size
    # Restore only the archive just generated inside this process. Never accept
    # a remote dump or connection string as an input to this verification.
    with isolated_cluster(bindir) as (owner, connect):
        with owner, owner.cursor() as cur:
            # isolated_cluster creates an empty namespace and the two restricted
            # roles. A full restore recreates the namespace, grants and constraints.
            cur.execute('DROP SCHEMA candidate RESTRICT')
        subprocess.run([client_bin / 'pg_restore', '-h', owner.info.host, '-U', owner.info.user, '-d', owner.info.dbname,
                        '--single-transaction', '--exit-on-error', '--no-owner', dump],
                       check=True)
        with closing(connect()) as worker:
            verify_target(worker)
        report['restored'] = inventory(owner)
    (directory / 'current-worker.json').write_text(json.dumps(report, sort_keys=True))
    print(json.dumps(dict(day=str(day), source_jobs=report['source']['jobs']['rows'],
                          checkpoint_bytes=report['checkpoint_bytes'], checkpoint_sha256=report['checkpoint_sha256'],
                          jobs_for_date=report['second_batch']['jobs_for_date'],
                          restored=report['source'] == report['restored'])), flush=True)
    if (report['source'] != report['restored'] or report['source']['core_selections']['rows']
            or set(report['second_batch']['jobs_for_date']) != {'done'}
            or set(report['first_batch']['receipts']) != {'received'}
            or set(report['second_batch']['receipts']) - {'received'}):
        raise ValueError('Incomplete private acquisition or checkpoint recovery')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('day', type=date.fromisoformat)
    parser.add_argument('directory', type=Path)
    parser.add_argument('bindir', type=Path)
    parser.add_argument('--client-bin', type=Path)
    args = parser.parse_args()
    run(args.day, args.directory, args.bindir, args.client_bin or args.bindir)
