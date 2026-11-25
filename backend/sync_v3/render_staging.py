"""Install or exercise the isolated Ohio staging database through Render's private network."""
import argparse
from contextlib import closing
from datetime import date, datetime
import json
import os
from time import monotonic
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extensions import encrypt_password, parse_dsn

from sync_v3.current_worker import acquisition_failed, day_states, process, verify_target
from sync_v3.replay import install

HOST = 'dpg-dc2t51mc6qcc738080hg-a'
DATABASE = 'baseballos_sync_v3_staging'
OWNER = 'baseballos_sync_v3_staging_user'
BATCH_LIMIT = 256
PLAYED_DAY = date(2017, 8, 28)


def connect(user, password):
    return psycopg2.connect(host=HOST, port=5432, dbname=DATABASE, user=user, password=password,
                            connect_timeout=10, options='-c search_path=pg_catalog',
                            application_name='baseballos_v3_staging', sslmode='require')


def bootstrap(password):
    task = os.environ.get('STAGING_INSTALLER_TASK', 'bootstrap')
    if task in ('build-generation', 'recover-readiness'):
        import resource
        from sync_v3.staging_publication_target import advance_private_generation
        if task == 'build-generation':
            result = advance_private_generation(password, budget_seconds=185)
        else:
            from sync_v3.staging_publication_target import recover_private_readiness
            result = recover_private_readiness(password, budget_seconds=185)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        print(json.dumps(dict(generation=result, peak_rss_kib=usage.ru_maxrss,
                              process_cpu_seconds=usage.ru_utime+usage.ru_stime)), flush=True)
        return
    if task == 'recheck-edition-transactions':
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_publication_target import recheck_edition_transactions
        client = MLBApiClient()
        with closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = recheck_edition_transactions(source, PLAYED_DAY, os.environ['STAGING_PRODUCT_GENERATION'], client._get)
        print(json.dumps(dict(private_transaction_recheck=result)), flush=True)
        return
    if task not in ('bootstrap', 'publish-generation', 'rollback-generation'):
        raise ValueError('Unsupported private installer operation')
    binding = parse_dsn(os.environ['STAGING_OWNER_DSN'])
    if (binding.get('host'), binding.get('dbname'), binding.get('user')) != (HOST, DATABASE, OWNER):
        raise ValueError('Render owner binding differs from the approved staging instance')
    if task in ('publish-generation', 'rollback-generation'):
        from sync_v3.staging_product_delivery import exercise, exercise_rollback
        import resource
        started = monotonic()
        digest = os.environ['STAGING_PRODUCT_GENERATION']
        if task == 'publish-generation':
            report = exercise(binding['password'], password, digest)
        else:
            report = exercise_rollback(binding['password'], digest, int(os.environ['STAGING_ROLLBACK_SNAPSHOT']))
        usage = resource.getrusage(resource.RUSAGE_SELF)
        print(json.dumps(dict(private_product=report, elapsed_seconds=monotonic()-started,
                              peak_rss_kib=usage.ru_maxrss, process_cpu_seconds=usage.ru_utime+usage.ru_stime)), flush=True)
        return
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
    from sync_v3.staging_publication_target import install_target
    print(json.dumps(dict(publication_target=install_target(binding["password"], password))), flush=True)


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
        # Verify the original witness and the most recent acquisition batch in the private database.
        # A restarted worker can detect damaged bytes even when the receipt still has its original digest.
        cur.execute("""WITH recent AS (
                           SELECT id,sha256 FROM candidate.fetches ORDER BY id DESC LIMIT %s
                       ), sample AS (
                           SELECT id,sha256 FROM recent WHERE sha256 IS NOT NULL
                           UNION SELECT id,sha256 FROM candidate.fetches WHERE id=%s
                       )
                       SELECT count(*),count(*) FILTER (
                           WHERE p.sha256 IS NULL OR encode(pg_catalog.sha256(p.encoded_json),'hex')<>s.sha256
                       ) FROM sample s LEFT JOIN candidate.payloads p USING (sha256)""",
                    (BATCH_LIMIT, first[0] if first else None))
        verified, mismatches = cur.fetchone()
        if mismatches:
            raise ValueError('Staging acquisition payload digest mismatch')
        cur.execute('SELECT pg_database_size(current_database())')
        database_bytes, = cur.fetchone()
        return dict(first=first, receipts=count, verified_payload_receipts=verified, database_bytes=database_bytes)


def played_batch(worker, current_day, current_report):
    """Measure one idle historical batch in the dedicated acquisition database."""
    if current_report['receipts'] or set(current_report['jobs_for_date']) != {'done'}:
        return dict(status='current_work_has_priority')
    with worker, worker.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT EXISTS (SELECT 1 FROM candidate.jobs WHERE budget='current' AND product_date<=%s
                       AND state<>'done' AND payload ? 'continuation' AND payload->>'capture' IS NULL)""",
                    (current_day,))
        if cur.fetchone()[0]:
            return dict(status='current_work_has_priority')
        states = day_states(cur, PLAYED_DAY, 'historical')
    if states.get('dead'):
        raise ValueError(f'Historical acquisition has exhausted jobs: {states}')
    result = dict(status='already_complete', jobs=states)
    if set(states) != {'done'}:
        start = monotonic()
        report = process(worker, PLAYED_DAY, max_jobs=BATCH_LIMIT, profiles=True, budget='historical')
        result = dict(status='batch', jobs=report['jobs_for_date'], report=report,
                      seconds=monotonic() - start, after=witness(worker))
    with worker, worker.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT count(DISTINCT (f.endpoint,f.parameters)),
                          count(DISTINCT f.endpoint) FILTER (WHERE f.endpoint LIKE '/people/%%/stats'),
                          count(DISTINCT f.endpoint) FILTER (WHERE f.endpoint LIKE '/teams/%%/roster'),
                          count(DISTINCT f.endpoint) FILTER (WHERE f.endpoint LIKE '/game/%%/boxscore')
                       FROM candidate.jobs j JOIN candidate.attempts a ON a.job_id=j.id
                       JOIN candidate.fetches f ON f.token=a.token WHERE j.budget='historical'
                       AND j.product_date=%s AND j.payload->>'capture' IS NULL
                       AND NOT (j.payload ? 'eligibility_recovery') AND f.outcome='received'
                       AND NOT (f.endpoint LIKE '/people/%%/stats' AND f.parameters->>'stats'='byDateRange'
                           AND f.parameters->>'endDate'<>%s)
                       AND NOT EXISTS (SELECT 1 FROM candidate.refusals r WHERE r.source_id=f.id)""", (PLAYED_DAY, PLAYED_DAY.isoformat()))
        requests, pitchers, clubs, finals = cur.fetchone()
    if set(result['jobs']) == {'done'} and (requests, pitchers, clubs, finals) != (926, 371, 30, 10):
        raise ValueError(f'Historical acquisition differs from August cohort: {requests} requests, '
                         f'{pitchers} pitchers, {clubs} clubs, {finals} boxscores')
    return dict(result, requests=requests, pitcher_profiles=pitchers, roster_clubs=clubs, boxscores=finals)


def acquire(password):
    with closing(connect('sync_v3_worker', password)) as worker:
        verify_target(worker)
        before = witness(worker)
        from sync_v3.staging_postseason import retain
        print(json.dumps(dict(postseason_archive=retain(worker))), flush=True)
        day = datetime.now(ZoneInfo('America/New_York')).date()
        started = monotonic()
        limit = BATCH_LIMIT if before['first'] else 1
        for batch_number in range(1, 6):
            report = process(worker, day, max_jobs=limit, profiles=True)
            after = witness(worker)
            if before['first'] and before['first'] != after['first']:
                raise ValueError('Prior acquisition receipt changed')
            print(json.dumps(dict(before=before, after=after, report=report, batch=batch_number,
                                  seconds=monotonic()-started)), flush=True)
            if acquisition_failed(report):
                raise ValueError('Incomplete staging acquisition')
            if (limit != BATCH_LIMIT or report['receipts'].get('received') != limit
                    or monotonic()-started >= 150):
                break
            before = after
        if os.environ.get('STAGING_PLAYED_SLATE') == PLAYED_DAY.isoformat():
            played = played_batch(worker, day, report)
            print(json.dumps(dict(historical=played)), flush=True)
            if played['status'] == 'batch':
                if acquisition_failed(played['report']) or after['first'] != played['after']['first']:
                    raise ValueError('Incomplete historical acquisition or changed first staging receipt')



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('bootstrap', 'acquire'))
    args = parser.parse_args()
    try:
        (bootstrap if args.operation == 'bootstrap' else acquire)(os.environ['STAGING_WORKER_PASSWORD'])
    except psycopg2.Error as exc:
        parser.exit(1, f'Staging database operation failed ({exc.pgcode or type(exc).__name__}).\n')
