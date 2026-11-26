"""Pinned production connection and authority boundaries for the existing primary."""
import os
import re

import psycopg2
from sqlalchemy import URL

PRODUCTION = os.environ.get('SYNC_V3_DEPLOYMENT') == 'production'
PROJECT = 'jbhzvzlqrledmlqrlzim'
DATABASE = 'postgres'
WORKER = 'sync_v3_worker'
PROJECTOR = 'baseballos_v3_projector'
PUBLISHER = 'baseballos_v3_publisher'
RUN_SOURCE = 'sync_v3' if PRODUCTION else 'sync_v3_staging'
SNAPSHOT_SOURCE = 'sync_v3_publication' if PRODUCTION else 'v3_private_publication'


def production_url(role, password, *, read_only=False):
    if role not in (WORKER, PROJECTOR, PUBLISHER) or not password:
        raise ValueError('A dedicated production runtime login is required')
    host = os.environ.get('SYNC_V3_SESSION_HOST', f'db.{PROJECT}.supabase.co')
    direct = host == f'db.{PROJECT}.supabase.co'
    if not direct and not re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', host):
        raise ValueError('Expected the project direct endpoint or Supabase session pool')
    options = {'sslmode': 'verify-full', 'connect_timeout': '10', 'application_name': role}
    if os.environ.get('SYNC_V3_SSL_ROOT_CERT'):
        options['sslrootcert'] = os.environ['SYNC_V3_SSL_ROOT_CERT']
    if read_only:
        options['options'] = '-c default_transaction_read_only=on'
    return URL.create('postgresql+psycopg2', username=role if direct else f'{role}.{PROJECT}',
                      password=password, host=host, port=5432, database=DATABASE, query=options)


def connect_runtime(role, password):
    url = production_url(role, password)
    connection = psycopg2.connect(**url.translate_connect_args(username='user'), **url.query)
    try:
        with connection, connection.cursor() as cur:
            cur.execute('SELECT current_database(),session_user,current_user')
            if cur.fetchone() != (DATABASE, role, role):
                raise ValueError('Production connection identity mismatch')
    except BaseException:
        connection.close()
        raise
    return connection
