"""Install or exercise the isolated Ohio staging database through Render's private network."""
import argparse
from contextlib import closing
from datetime import date, datetime, timezone
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


def runtime_environment(*required):
    keep = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'VIRTUAL_ENV', *required)
    return {**{key: os.environ[key] for key in keep if key in os.environ}, 'AUTO_SYNC': 'false'}


def bootstrap(password):
    started_at = None
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
    if task == 'prepare-dated-primary':
        from sync_v3.primary_date import prepare
        today = datetime.now(ZoneInfo('America/New_York')).date()
        requested = os.environ.get('STAGING_PRIMARY_BASEBALL_DATE')
        day = date.fromisoformat(requested) if requested else today
        if day > today:
            raise ValueError('A primary edition cannot use a future source calendar')
        with closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = prepare(source, password, day, after_finals=os.environ.get('STAGING_PRIMARY_PHASE')=='postgame')
        print(json.dumps(dict(private_primary_date=result)), flush=True)
        return
    if task == 'run-current-offseason':
        import resource
        started_at = datetime.now(timezone.utc)
        from sync_v3.staging_publication_target import acquisition_freshness
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_postseason import qualify_offseason_edition, reconcile_current_decisions
        day = datetime.now(ZoneInfo('America/New_York')).date()
        client = MLBApiClient()
        with closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            report = process(source, day, max_jobs=BATCH_LIMIT, profiles=True)
            if acquisition_failed(report):
                raise ValueError('The current scheduled source cycle has unsettled acquisition failures')
            recovery = reconcile_current_decisions(source, client._get)
            qualified = qualify_offseason_edition(source, day)
            with source, source.cursor() as cur:
                freshness = acquisition_freshness(cur)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        print(json.dumps(dict(current_cycle=dict(day=str(day), receipts=report['receipts'], recovery=recovery,
                                                generation=qualified['generation'], acquisition_freshness=freshness,
                                                seconds=(datetime.now(timezone.utc)-started_at).total_seconds(),
                                                process_cpu_seconds=usage.ru_utime+usage.ru_stime,
                                                peak_rss_kib=usage.ru_maxrss))), flush=True)
        os.environ['STAGING_PRODUCT_GENERATION'] = qualified['generation']
        import subprocess
        import sys
        # Wait for the independent, resumable Board writer before giving the publisher control.
        projector_env = runtime_environment('STAGING_PROJECTOR_PASSWORD', 'STAGING_WORKER_PASSWORD',
                                            'STAGING_PRODUCT_GENERATION', 'STAGING_ROSTER_PUBLIC_IDENTITIES')
        projection = subprocess.run([sys.executable, '-m', 'sync_v3.render_staging', 'project-before-publish'],
                                    env=projector_env, check=False)
        if projection.returncode == 75:
            print(json.dumps(dict(current_cycle_pending=dict(day=str(day), generation=qualified['generation']))), flush=True)
            return
        projection.check_returncode()
        task = 'publish-with-scoped-login'
    operations = {
        'verify-reader-edition': ('read', ('STAGING_PRODUCT_READER_PASSWORD',)),
        'publish-with-scoped-login': ('publish', ('STAGING_PRODUCT_PUBLISHER_PASSWORD',)),
        'rollback-with-scoped-login': ('rollback', ('STAGING_PRODUCT_PUBLISHER_PASSWORD',)),
        'recover-board-with-scoped-login': ('project', ('STAGING_PROJECTOR_PASSWORD', 'STAGING_WORKER_PASSWORD')),
    }
    if task in operations:
        import sys
        operation, secrets = operations[task]
        env = runtime_environment(*secrets, 'STAGING_PRODUCT_GENERATION', 'STAGING_ROLLBACK_SNAPSHOT')
        if task == 'publish-with-scoped-login' and started_at is not None:
            env['STAGING_CYCLE_STARTED_AT'] = started_at.isoformat()
        os.execve(sys.executable, [sys.executable, '-m', 'sync_v3.render_staging', operation], env)
    if task == 'qualify-offseason-edition':
        from sync_v3.staging_postseason import qualify_offseason_edition
        with closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = qualify_offseason_edition(source, datetime.now(ZoneInfo('America/New_York')).date())
        print(json.dumps(dict(private_offseason_edition=result)), flush=True)
        return
    if task == 'recover-current-edition':
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_postseason import reconcile_current_decisions
        client = MLBApiClient()
        with closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = reconcile_current_decisions(source, client._get)
        print(json.dumps(dict(private_current_recovery=result)), flush=True)
        return
    if task == 'inspect-current-edition':
        from collections import Counter
        from sync_v3.competition_calendar import calendar_games, competition_status
        from sync_v3.discovery import competition_calendar_request
        from sync_v3.evidence import replay
        from sync_v3.generation import generation_date_decision
        from sync_v3.staging_publication_target import acquisition_freshness
        with closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            with source, source.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                freshness = acquisition_freshness(cur)
                day = date.fromisoformat(freshness['day'])
                competition = competition_status(cur, day)
                latest_final = None
                if competition['calendar_source']:
                    request = competition_calendar_request(day.year)
                    games = calendar_games(request.params(), replay(cur, competition['calendar_source']).body)
                    latest_final = max((played for played, row, _ in games.values()
                                        if played <= day and row['status_state'] == 'final'), default=None)
                decision = generation_date_decision(cur, latest_final, day) if latest_final else None
                report = dict(freshness=freshness, last_listed_final=str(latest_final) if latest_final else None,
                              represented_date_decision=decision, confirmed_decisions=len(competition['decision_sources']),
                              missing_decisions=competition['missing_decisions'],
                              club_status=dict(Counter(club['status'] for club in competition['clubs'].values())))
        print(json.dumps(dict(private_current_edition=report), default=str), flush=True)
        return
    if task == 'recheck-edition-transactions':
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_publication_target import recheck_edition_transactions
        from sync_v3.generation import freeze_generation
        from datetime import timedelta
        client = MLBApiClient()
        with closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = recheck_edition_transactions(source, PLAYED_DAY, os.environ['STAGING_PRODUCT_GENERATION'], client._get)
            result['next_generation'] = freeze_generation(source, PLAYED_DAY, as_of=PLAYED_DAY + timedelta(days=1))
            if result['next_generation'] == result['predecessor_generation']:
                raise ValueError('A new retained transaction receipt did not advance the generation')
        print(json.dumps(dict(private_transaction_recheck=result)), flush=True)
        return
    if task not in ('bootstrap', 'publish-generation', 'rollback-generation', 'project-eligibility', 'project-roster-provenance', 'verify-product-surfaces', 'inspect-product-reads', 'install-product-reader', 'inspect-publication-access', 'install-product-publisher', 'install-product-projector', 'project-offseason-competition', 'project-offseason-rosters', 'recover-offseason-board-history', 'recover-next-offseason-board'):
        raise ValueError('Unsupported private installer operation')
    binding = parse_dsn(os.environ['STAGING_OWNER_DSN'])
    if (binding.get('host'), binding.get('dbname'), binding.get('user')) != (HOST, DATABASE, OWNER):
        raise ValueError('Render owner binding differs from the approved staging instance')
    if task in ('recover-offseason-board-history', 'recover-next-offseason-board'):
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_board_history import recover, recover_next
        from sync_v3.staging_product_delivery import observe_product_relations, private_app
        client = MLBApiClient()
        with private_app(binding['password']).app_context(), closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            product_access = {}
            observe_product_relations(product_access)
            digest = os.environ['STAGING_PRODUCT_GENERATION']
            if task == 'recover-next-offseason-board':
                result = recover_next(source, client, digest)
            else:
                result = recover(source, client, int(os.environ['STAGING_BOARD_CLUB']),
                                 int(os.environ.get('STAGING_BOARD_AFTER', '0')), digest)
            result['product_access'] = {op: sorted(tables) for op, tables in product_access.items()}
        print(json.dumps(dict(private_board_history=result)), flush=True)
        return
    if task == 'project-offseason-rosters':
        from sync_v3.staging_product_delivery import private_app
        from sync_v3.staging_postseason import qualify_offseason_edition
        from sync_v3.staging_publication_target import project_archived_fatigue, project_roster_views
        with closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            receipt = qualify_offseason_edition(source, datetime.now(ZoneInfo('America/New_York')).date())
        dates = tuple(date.fromisoformat(receipt[field]) for field in ('through', 'availability'))
        with private_app(binding['password']).app_context():
            result = project_roster_views(password, edition_dates=dates)
            result['assignments'] = project_archived_fatigue(edition_dates=dates)
        print(json.dumps(dict(private_offseason_rosters=result)), flush=True)
        return
    if task == 'project-offseason-competition':
        from services.mlb_api import MLBApiClient
        from sync_v3.staging_product_delivery import private_app
        from sync_v3.staging_postseason import project_offseason_competition
        app = private_app(binding['password'])
        client = MLBApiClient()
        with app.app_context(), closing(client.session), closing(connect('sync_v3_worker', password)) as source:
            verify_target(source)
            result = project_offseason_competition(source, client, datetime.now(ZoneInfo('America/New_York')).date())
        print(json.dumps(dict(private_offseason_projection=result)), flush=True)
        return
    if task == 'install-product-projector':
        from services.migration_authority import require_owner
        from sync_v3.staging_projector import PROJECTOR, install
        require_owner()
        install(binding['password'], os.environ['STAGING_PROJECTOR_PASSWORD'])
        print(json.dumps(dict(private_projector_install=dict(role=PROJECTOR))), flush=True)
        return
    if task == 'install-product-publisher':
        from services.migration_authority import require_owner
        from sync_v3.staging_publisher import PUBLISHER, install
        require_owner()
        install(binding['password'], os.environ['STAGING_PRODUCT_PUBLISHER_PASSWORD'])
        print(json.dumps(dict(private_publisher_install=dict(role=PUBLISHER))), flush=True)
        return
    if task == 'install-product-reader':
        from services.migration_authority import require_owner
        from sync_v3.staging_reader import PRODUCT_RELATIONS, READER, install as install_reader
        require_owner()
        install_reader(binding['password'], os.environ['STAGING_PRODUCT_READER_PASSWORD'], PRODUCT_RELATIONS)
        print(json.dumps(dict(private_reader_install=dict(role=READER, readable_tables=len(PRODUCT_RELATIONS),
                                                         writable_tables=0))), flush=True)
        return
    if task in ('verify-product-surfaces', 'inspect-product-reads'):
        from sync_v3.staging_product_delivery import verify_product_surfaces
        result = verify_product_surfaces(binding['password'], os.environ['STAGING_PRODUCT_GENERATION'],
                                         inventory=task == 'inspect-product-reads')
        print(json.dumps(dict(private_surfaces=result)), flush=True)
        return
    if task == 'project-roster-provenance':
        from sync_v3.staging_product_delivery import private_app
        from sync_v3.staging_publication_target import project_archived_fatigue, project_prior_fatigue, project_roster_views
        from services.public_roster_readiness import build_public_roster_readiness
        app = private_app(binding['password'])
        with app.app_context():
            result = project_roster_views(password)
            result['fatigue'] = project_archived_fatigue()
            result['prior_scores'] = project_prior_fatigue(password, os.environ['STAGING_PRODUCT_GENERATION'])
            readiness = build_public_roster_readiness(reference_date=PLAYED_DAY, scope='league')
            result['readiness'] = {key: readiness[key] for key in ('claims_available', 'reason_codes', 'coverage')}
            if not readiness['claims_available']:
                raise ValueError(f"Private roster authority withheld: {readiness['reason_codes']}")
        print(json.dumps(dict(private_roster=result)), flush=True)
        return
    if task == 'project-eligibility':
        from sync_v3.staging_product_delivery import private_app
        from sync_v3.staging_publication_target import project_eligibility_history
        app = private_app(binding['password'])
        with app.app_context():
            result = project_eligibility_history(password, budget_seconds=180)
        print(json.dumps(dict(private_eligibility=result)), flush=True)
        return
    if task in ('publish-generation', 'rollback-generation', 'inspect-publication-access'):
        from sync_v3.staging_product_delivery import exercise, exercise_rollback
        import resource
        started = monotonic()
        digest = os.environ['STAGING_PRODUCT_GENERATION']
        if task != 'rollback-generation':
            report = exercise(binding['password'], password, digest, inventory=task == 'inspect-publication-access')
        else:
            report = exercise_rollback(binding['password'], digest, int(os.environ['STAGING_ROLLBACK_SNAPSHOT']))
        usage = resource.getrusage(resource.RUSAGE_SELF)
        print(json.dumps(dict(private_product=report, elapsed_seconds=monotonic()-started,
                              peak_rss_kib=usage.ru_maxrss, process_cpu_seconds=usage.ru_utime+usage.ru_stime)), flush=True)
        return
    from services.migration_authority import require_owner
    require_owner()
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
    parser.add_argument('operation', choices=('bootstrap', 'acquire', 'read', 'publish', 'rollback', 'project', 'project-before-publish'))
    args = parser.parse_args()
    try:
        if args.operation in ('publish', 'rollback'):
            from sync_v3.staging_publisher import PUBLISHER, check_scope, _connect, TARGET
            from sync_v3.staging_product_delivery import exercise, exercise_rollback
            password = os.environ['STAGING_PRODUCT_PUBLISHER_PASSWORD']
            digest = os.environ['STAGING_PRODUCT_GENERATION']
            with closing(_connect(PUBLISHER, password)) as target, target, target.cursor() as cur:
                check_scope(cur, TARGET)
            if args.operation == 'publish':
                result = exercise(password, password, digest, user=PUBLISHER, source_user=PUBLISHER)
            else:
                result = exercise_rollback(password, digest, int(os.environ['STAGING_ROLLBACK_SNAPSHOT']), user=PUBLISHER)
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            result.update(peak_rss_kib=usage.ru_maxrss, process_cpu_seconds=usage.ru_utime+usage.ru_stime)
            if args.operation == 'publish' and 'STAGING_CYCLE_STARTED_AT' in os.environ:
                started_at = datetime.fromisoformat(os.environ['STAGING_CYCLE_STARTED_AT'])
                result['cycle_started_at'] = started_at.isoformat()
                result['invocation_through_http_seconds'] = (datetime.now(timezone.utc)-started_at).total_seconds()
            print(json.dumps(dict(private_scoped_publication=dict(result, role=PUBLISHER))), flush=True)
        elif args.operation in ('project', 'project-before-publish'):
            from sync_v3.staging_projector import recover_boards
            result = recover_boards(os.environ['STAGING_PROJECTOR_PASSWORD'], os.environ['STAGING_WORKER_PASSWORD'],
                                    os.environ['STAGING_PRODUCT_GENERATION'],
                                    competition_day=datetime.now(ZoneInfo('America/New_York')).date()
                                    if args.operation == 'project-before-publish' else None)
            print(json.dumps(dict(private_board_history=result)), flush=True)
            if args.operation == 'project-before-publish' and (
                    result.get('phase') == 'canonical_ready' or result['completed_clubs'] < result['total']
                    or result['batches']):
                parser.exit(75)
        elif args.operation == 'read':
            from sync_v3.staging_reader import serve_edition
            result = serve_edition(os.environ['STAGING_PRODUCT_READER_PASSWORD'], os.environ['STAGING_PRODUCT_GENERATION'])
            print(json.dumps(dict(private_reader_edition=result)), flush=True)
        else:
            (bootstrap if args.operation == 'bootstrap' else acquire)(os.environ['STAGING_WORKER_PASSWORD'])
    except psycopg2.Error as exc:
        parser.exit(1, f'Staging database operation failed ({exc.pgcode or type(exc).__name__}).\n')
