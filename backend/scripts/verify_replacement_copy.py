"""Compare independent product databases using read-only, repeatable-read connections.

Both databases must already be quiescent. Supply verified direct TLS connections via
libpq service files. Output contains only aggregate evidence and cluster identifiers.
"""

import argparse
from contextlib import closing
import hashlib
import json
import re

import psycopg2
from psycopg2 import sql


SCHEMAS = ['public', 'roster_history_repair', 'transaction_history_repair']


def manifest(conn):
    conn.set_session(isolation_level='REPEATABLE READ', readonly=True)
    with conn, conn.cursor() as cur:
        cur.execute("SET LOCAL search_path=pg_catalog")
        for option in ("TIME ZONE 'UTC'", "DateStyle='ISO, YMD'", "IntervalStyle='postgres'",
                       "bytea_output='hex'", "extra_float_digits=3"):
            cur.execute('SET LOCAL ' + option)
        cur.execute("SET LOCAL timezone='UTC'")
        cur.execute("SET LOCAL datestyle='ISO, YMD'")
        cur.execute("SET LOCAL intervalstyle='iso_8601'")
        cur.execute("SET LOCAL extra_float_digits=3")
        cur.execute("SELECT system_identifier::text FROM pg_control_system()")
        cluster = cur.fetchone()[0]
        cur.execute("""SELECT n.nspname,c.relname,c.relkind FROM pg_class c
                     JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p','S','v','m','f')
                     ORDER BY 1,2""", (SCHEMAS,))
        evidence = {}
        for schema, name, kind in cur.fetchall():
            ident = sql.Identifier(schema, name)
            key = f'{schema}.{name}'
            if kind == 'S':
                cur.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(ident))
                evidence[key] = cur.fetchone()
                continue
            if kind != 'r':
                raise ValueError(f'Review additional relation {key} of kind {kind}')
            cur.execute("""SELECT a.attname FROM pg_index i
                        CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(num,ord)
                        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.num
                        WHERE i.indrelid=to_regclass(%s) AND i.indisprimary AND k.ord<=i.indnkeyatts
                        ORDER BY k.ord""", (ident.as_string(conn),))
            order = sql.SQL(',').join(sql.Identifier('r', col) for col, in cur.fetchall())
            if not order.as_string(conn):
                raise ValueError(f'No stable primary key for {key}')
            digest = hashlib.sha256()
            count = 0
            with conn.cursor(name='replacement_copy_rows') as rows:
                rows.execute(sql.SQL("SELECT sha256(convert_to(row_to_json(r)::text,'UTF8')) FROM {} r ORDER BY {}")
                             .format(ident, order))
                for row_digest, in rows:
                    digest.update(row_digest)
                    count += 1
            evidence[key] = (count, digest.hexdigest())
        cur.execute("""SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
                         pg_get_functiondef(p.oid),p.prosecdef
                    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                    WHERE n.nspname=ANY(%s) ORDER BY 1,2,3""", (SCHEMAS,))
        evidence['routines'] = cur.fetchall()
        if 'public.alembic_version' not in evidence or 'public.dashboard_snapshots' not in evidence:
            raise ValueError('Expected the BaseballOS product schema')
    return cluster, evidence


def compare(source, destination):
    original, before = manifest(source)
    replacement, after = manifest(destination)
    if original == replacement:
        raise ValueError('Source and destination must be independently initialized clusters')
    differences = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    if differences:
        raise ValueError('Replacement differs in ' + ', '.join(differences))
    fingerprint = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    return dict(source_cluster=original, target_cluster=replacement, content_sha256=fingerprint)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-service', required=True)
    parser.add_argument('--destination-service', required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}', args.revision):
        parser.error('Supply the exact tested release SHA')
    with closing(psycopg2.connect(service=args.source_service, sslmode='verify-full')) as source:
        with closing(psycopg2.connect(service=args.destination_service, sslmode='verify-full')) as destination:
            print(json.dumps(dict(compare(source, destination), revision=args.revision), sort_keys=True))
