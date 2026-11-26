"""Hold read-only owner sessions across an operator-managed pool drain. Never log connection strings."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from contextlib import ExitStack, closing
import os
import re

import psycopg2
from sqlalchemy.engine import make_url

from sync_v3.runtime_binding import PROJECT


def endpoint(name, *, dedicated=False):
    url = make_url(os.environ[name])
    host = url.host or ''
    direct = host == f'db.{PROJECT}.supabase.co'
    regional = re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host)
    allowed_ports = (6543,) if dedicated else (5432,) if name.endswith('DIRECT') else (
        (5432,) if name.endswith('SESSION') else (6543,))
    if (url.get_backend_name() != 'postgresql' or url.database != 'postgres' or not url.password
            or url.port not in allowed_ports or bool(direct) != (name.endswith('DIRECT') or dedicated)
            or not (direct or regional) or url.username != ('postgres' if direct else f'postgres.{PROJECT}')):
        raise ValueError(f'Unexpected endpoint for {name}')
    params = url.translate_connect_args(username='user')
    params.update(sslmode='verify-full', connect_timeout=10, application_name='baseballos_pool_drain_check')
    if os.environ.get('SYNC_V3_SSL_ROOT_CERT'):
        params['sslrootcert'] = os.environ['SYNC_V3_SSL_ROOT_CERT']
    return params


def probe(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT current_database(),session_user,current_user')
        if cur.fetchone() != ('postgres','postgres','postgres'):
            raise ValueError('Unexpected canary identity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}', args.revision) or args.output.exists():
        raise ValueError('Expected a tested revision and a new receipt file')
    scopes = ['DIRECT','SESSION','TRANSACTION']
    if os.environ.get('SYNC_V3_DEDICATED_POOL') == 'enabled':
        scopes.append('DEDICATED')
    elif os.environ.get('SYNC_V3_DEDICATED_POOL') != 'disabled':
        raise ValueError('Specify whether a dedicated pool is enabled')
    with ExitStack() as stack:
        held = {}
        for scope in scopes:
            params = endpoint('OLD_OWNER_'+scope,dedicated=scope=='DEDICATED')
            conn = stack.enter_context(closing(psycopg2.connect(**params)))
            conn.autocommit = True
            probe(conn)
            held[scope] = (conn,params)
        print('Old authenticated clients held on '+', '.join(scopes), flush=True)
        if input('After approved rotation and provider drain, type DRAINED: ') != 'DRAINED':
            raise ValueError('Pool drain cancelled')
        for scope,(conn,old) in held.items():
            # Supply new URLs via private files outside the repository. They may be populated
            # after the password changes without restarting these held client connections.
            os.environ['NEW_OWNER_'+scope] = Path(os.environ['NEW_OWNER_'+scope+'_FILE']).read_text().strip()
            new = endpoint('NEW_OWNER_'+scope,dedicated=scope=='DEDICATED')
            if (new['host'],new['port']) != (old['host'],old['port']) or new['password']==old['password']:
                raise ValueError('Fresh control must use the same endpoint and a replacement password')
            with closing(psycopg2.connect(**new)) as control:
                probe(control)
            try:
                probe(conn)
            except (psycopg2.OperationalError,psycopg2.InterfaceError):
                pass
            else:
                raise ValueError(f'An old authenticated {scope} client still works')
            try:
                unexpected = psycopg2.connect(**old)
            except psycopg2.OperationalError as exc:
                if exc.pgcode != '28P01' and not re.search(r'password authentication failed|invalid password|authentication failed',str(exc),re.I):
                    raise ValueError(f'{scope} did not return a credential rejection') from None
            else:
                unexpected.close()
                raise ValueError(f'{scope} still accepts the old password')
            print(scope+' passed',flush=True)
        operation = input('Provider drain operation or support ticket reference: ').strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', operation):
            raise ValueError('Provider operation reference required')
        with args.output.open('x') as output:
            json.dump(dict(project=PROJECT, revision=args.revision, endpoints=scopes, provider_operation=operation,
                           verified_at=datetime.now(timezone.utc).isoformat()), output)



if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        # Driver and URL parsing errors can contain connection information.
        raise SystemExit('Drain check failed ('+type(exc).__name__+'). No drain receipt issued.') from None
