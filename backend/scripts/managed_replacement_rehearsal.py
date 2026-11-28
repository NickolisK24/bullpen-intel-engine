"""Private logical-copy and product rehearsal. This command cannot issue cutover evidence."""

from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import subprocess
import sys
import tempfile
import time

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import URL, make_url

from scripts.check_live_replacement import check
from scripts.verify_replacement_copy import SCHEMAS
from sync_v3 import runtime_binding as binding
from sync_v3.handoff_admin import API, prepare

SOURCE_USER = 'baseballos_v3_export'
SOURCE_HOST = 'aws-1-us-east-2.pooler.supabase.com'


def endpoint(secret, project, role, ca):
    url = make_url(secret)
    if (url.drivername != 'postgresql' or url.database != 'postgres' or url.query
            or url.port != 5432 or url.username != f'{role}.{project}' or not url.password
            or not re.fullmatch(r'aws-\d+-us-east-2\.pooler\.supabase\.com', url.host or '')
            or (role == SOURCE_USER and url.host != SOURCE_HOST)):
        raise ValueError('Invalid rehearsal session-pooler binding')
    return dict(host=url.host, port=5432, dbname='postgres', user=url.username,
                password=url.password, sslmode='verify-full', sslrootcert=str(ca), connect_timeout=10)


def cluster(connection, role):
    with connection, connection.cursor() as cur:
        cur.execute('SELECT current_database(), session_user, current_user, system_identifier::text '
                    'FROM pg_catalog.pg_control_system()')
        database, session_user, current_user, system_id = cur.fetchone()
        if (database, session_user, current_user) != ('postgres', role, role):
            raise ValueError('Unexpected database identity')
        return system_id


def client_env(params):
    return dict(PATH=os.environ['PATH'], LC_ALL='C',
                **{'PG' + key.upper().replace('DBNAME', 'DATABASE'): str(value)
                   for key, value in params.items()})


def copy(source, target, dest, directory, report):
    archive = directory / 'product.dump'
    with closing(psycopg2.connect(**source)) as exporter:
        exporter.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with exporter.cursor() as cur:
            cur.execute('SELECT pg_export_snapshot()')
            snapshot = cur.fetchone()[0]
        report('dump')
        schemas = [arg for schema in SCHEMAS for arg in ('--schema', schema)]
        subprocess.run(['pg_dump', '-Fc', '--no-password', '--lock-wait-timeout=30s',
                        '--snapshot', snapshot, *schemas, '-f', archive], env=client_env(source), check=True)
        report('restore', archive_bytes=archive.stat().st_size)
        listing = subprocess.check_output(['pg_restore', '--list', archive], text=True)
        toc = directory / 'restore.list'
        toc.write_text(''.join(line for line in listing.splitlines(True)
                               if not re.match(r'^\d+; \d+ \d+ SCHEMA - public ', line)))
        subprocess.run(['pg_restore', '--use-list', toc, '--no-password', '--no-owner', '--role=postgres',
                        '--single-transaction', '--exit-on-error', '-d', 'postgres', archive],
                       env=client_env(target), check=True)
        report('compare')
        with closing(psycopg2.connect(**source)) as reader:
            sequences = check(reader, dest, snapshot, archive)
    report('copy_verified', sequences=sequences)
    archive.unlink()


def role_url(target, role):
    password = secrets.token_urlsafe(32)
    tenant = target['user'].partition('.')[2]
    username = f'{role}.{tenant}' if tenant else role
    query = {key: str(target[key]) for key in ('sslmode', 'sslrootcert') if key in target}
    host = target['host']
    if host.startswith('/'):
        query['host'] = host
        host = 'localhost'
    return URL.create('postgresql', username=username, password=password, host=host,
                      port=target['port'], database='postgres', query=query)


def product(dest, target, revision, report):
    from sync_v3.handoff_admin import fence_service_role

    api_url = role_url(target, API)
    publisher_url = role_url(target, binding.PUBLISHER)
    with dest, dest.cursor() as cur:
        prepare(cur, revision)
        cur.execute('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM baseballos_legacy_sync')
        cur.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM baseballos_legacy_sync')
        fence_service_role(cur)
        for role, url in ((API, api_url), (binding.PUBLISHER, publisher_url)):
            cur.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD %s').format(sql.Identifier(role)), (url.password,))

    try:
        replay_publication(api_url, publisher_url, revision, report)
    finally:
        with dest, dest.cursor() as cur:
            for role in (API, binding.PUBLISHER):
                cur.execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(role)))
                cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename=%s '
                            "AND backend_type='client backend'", (role,))


def replay_publication(api_url, publisher_url, revision, report):
    from flask import Flask
    from models.dashboard_snapshot import DashboardSnapshot
    from models.tonight_publication import TonightPublication
    from scripts.verify_public_sync_edition import verify
    from services import public_serving_authority
    from services.tonight_read_model import CONTRACT
    from sync_v3 import staging_product_delivery as delivery
    from utils.db import db

    os.environ.update(APP_ENV='production', AUTO_SYNC='false', DATABASE_MIGRATION_MODE='verify_only',
                      SECRET_KEY=secrets.token_urlsafe(32), ADMIN_API_TOKEN=secrets.token_urlsafe(32),
                      DATABASE_URL=api_url.render_as_string(hide_password=False))
    from app import app as api
    publisher = Flask('rehearsal_publisher')
    publisher.config.update(SQLALCHEMY_DATABASE_URI=publisher_url, TRUSTED_PUBLIC_SERVING_ENABLED=True,
                            TEAM_STATE_PUBLICATION_PROOF_REQUIRED=True)
    db.init_app(publisher)
    public_serving_authority.install_public_serving_authority(publisher)
    with delivery.http_session(api) as (client, base), publisher.app_context():
        with db.session.begin():
            root = DashboardSnapshot.query.filter_by(snapshot_type='bullpen_dashboard', is_published=True).one()
            root_id, root_sync = root.id, root.sync_run_id
            served = verify(client, base, root_id, root_sync)
            day = date.fromisoformat(served['product_day'])
            receipt = delivery.legacy_predecessor_receipt(root, day)
            if served['tonight_sha256'] != receipt['tonight_sha256']:
                raise ValueError('Restored public Tonight receipt differs')
            pin = dict(database='postgres', database_edition=receipt, public_edition_sha256=served['public_edition_sha256'])
            tonight = TonightPublication.query.filter_by(dashboard_snapshot_id=root_id, sync_run_id=root_sync,
                                                         reference_date=day, contract=CONTRACT).one()
            frozen = root.payload['trusted_team_boards']['frozen_team_state_by_team_id']
            edition = dict(data_through=str(root.data_through), availability_reference=str(root.availability_reference_date),
                           teams={team: dict(state=row['value']) for team, row in frozen.items()}, source_count=len(frozen),
                           official_slate=[dict(game_pk=g['game_pk'], home=g['home']['team_id'], away=g['away']['team_id'])
                                           for g in tonight.payload['games']])
        os.environ['STAGING_LEGACY_PREDECESSOR'] = json.dumps(pin)
        # Exercise PR 1014's copied-edition replay, on the verified private destination only.
        for ordinal in (1, 2):
            report('publication', edition=ordinal)
            digest = hashlib.sha256(f'rehearsal:{revision}:{receipt["payload_sha256"]}:{ordinal}'.encode()).hexdigest()
            edition = dict(edition, generation=digest)
            tip, promoted = delivery.publish(edition, None, user=binding.PUBLISHER)
            if not promoted:
                raise ValueError('Expected a new rehearsal publication')
            with db.session.begin():
                tip_sync = db.session.get(DashboardSnapshot, tip).sync_run_id
            result = verify(client, base, tip, tip_sync, binding=edition)
            report('api_verified', edition=ordinal, clubs=result['clubs'])
        report('rollback')
        restored = delivery.restore_handoff_root(tip, digest, pin, binding.PUBLISHER)
        if restored != root_id or verify(client, base, root_id, root_sync)['public_edition_sha256'] != pin['public_edition_sha256']:
            raise ValueError('Rollback fingerprint differs')
    report('rollback_verified')


def rehearse(source, target, expected_source, expected_target, directory, revision, report):
    if not binding.PRODUCTION or expected_source == expected_target:
        raise ValueError('Independent product-profile destination required')
    with closing(psycopg2.connect(**source)) as reader:
        if cluster(reader, SOURCE_USER) != expected_source:
            raise ValueError('Source cluster pin mismatch')
    with closing(psycopg2.connect(**target)) as dest:
        if cluster(dest, 'postgres') != expected_target:
            raise ValueError('Cluster pin mismatch')
        with dest, dest.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext('baseballos.managed_rehearsal'))")
            if not cur.fetchone()[0]:
                raise ValueError('Another rehearsal is active')
            cur.execute("SELECT EXISTS (SELECT FROM pg_class WHERE relnamespace='public'::regnamespace "
                        "AND relkind IN ('r','p','v','m','S','f')), EXISTS (SELECT FROM pg_namespace WHERE nspname=ANY(%s))",
                        (SCHEMAS[1:] + ['candidate','sync_v3_control'],))
            if any(cur.fetchone()):
                raise ValueError('Expected an empty destination')
        copy(source, target, dest, directory, report)
        dest.set_session(readonly=False)
        product(dest, target, revision, report)


def main(report):
    os.umask(0o077)
    start = datetime.fromisoformat(os.environ['REHEARSAL_STARTED_AT'])
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    if not 0 <= elapsed < 7 * 3600 - 1:
        raise ValueError('Outside the approved work window')
    def stop(signum, frame):
        raise TimeoutError('Rehearsal stopped')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGALRM, stop)
    signal.alarm(int(7 * 3600 - elapsed))
    ref = os.environ['REHEARSAL_PROJECT_REF']
    if ref == binding.ORIGINAL_PROJECT or not re.fullmatch('[a-z0-9]{20}', ref):
        raise ValueError('Expected an independently reviewed destination reference')
    with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as tmp:
        directory = Path(tmp)
        ca = directory / 'root.crt'
        ca.write_bytes(Path(__file__).with_name('supabase-production-roots.pem').read_bytes())
        source = endpoint(os.environ.pop('EXPORT_URL'), binding.ORIGINAL_PROJECT, SOURCE_USER, ca)
        target = endpoint(os.environ.pop('DESTINATION_URL'), ref, 'postgres', ca)
        report('identity_checks', free_bytes=shutil.disk_usage(directory).free)
        rehearse(source, target, binding.ORIGINAL_CLUSTER, os.environ['REHEARSAL_CLUSTER_ID'],
                 directory, os.environ['REHEARSAL_REVISION'], report)


if __name__ == '__main__':
    # Application, SQL, tool and HTTP error messages can contain restored data.
    # Only fixed stage names, counts, timing and exception classes go to CI.
    evidence = os.fdopen(os.dup(1), 'w', buffering=1)
    started = time.monotonic()

    def report(stage, **metrics):
        print(json.dumps(dict(stage=stage, seconds=round(time.monotonic()-started), **metrics)), file=evidence)

    with open(os.devnull, 'w') as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
        try:
            main(report)
        except Exception as exc:
            report('failed', error=type(exc).__name__, sqlstate=getattr(exc, 'pgcode', None))
            sys.exit(1)
