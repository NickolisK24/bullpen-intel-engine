"""Process a bounded batch of current MLB work in a provisioned private v3 database."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import date
import json
from pathlib import Path

import psycopg2

from services.mlb_api import MLBApiClient
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import savant
from sync_v3.cycle import run_cycle
from sync_v3.replay import schema_digest, schema_scripts


def verify_target(connection):
    """Read-only admission before any job is enqueued or any source is contacted."""
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT current_database(),
                       current_user = 'sync_v3_worker' AND session_user = current_user
                       AND has_table_privilege('candidate.jobs','INSERT')
                       AND NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
                           OR has_database_privilege(current_database(),'CREATE')
                           OR has_schema_privilege('candidate','CREATE') OR has_schema_privilege('public','CREATE')
                           OR has_table_privilege('candidate.core_selections','INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
                           OR has_any_column_privilege('candidate.core_selections','INSERT,UPDATE')
                           OR has_function_privilege('candidate.record_core_selection(bigint,text,text)','EXECUTE')
                           OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                      WHERE n.nspname='public' AND c.relname IN ('dashboard_snapshots','sync_runs'))
                           OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                           OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                      WHERE n.nspname <> 'candidate' AND n.nspname <> 'information_schema'
                                        AND n.nspname !~ '^pg_' AND c.relkind IN ('r','p','v','f')
                                        AND (has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
                                             OR has_any_column_privilege(c.oid,'INSERT,UPDATE'))))
                       FROM pg_roles r WHERE rolname=current_user""")
        name, admitted = cur.fetchone()
        if name not in ('sync_v3_shadow', 'sync_v3_rehearsal', 'baseballos_sync_v3_staging') or not admitted:
            raise ValueError('Expected the isolated candidate database and its restricted acquisition worker')
        cur.execute("SELECT digest,has_table_privilege('candidate.schema_installation','INSERT,UPDATE,DELETE,TRUNCATE'),"
                    "has_any_column_privilege('candidate.schema_installation','INSERT,UPDATE') "
                    "FROM candidate.schema_installation WHERE singleton")
        if cur.fetchall() != [(schema_digest(schema_scripts()), False, False)]:
            raise ValueError('The candidate schema installation differs from the worker revision')
        return name


def day_states(cur, day, budget):
    cur.execute("""SELECT state,count(*) FROM candidate.jobs WHERE budget=%s AND product_date=%s
                   AND (budget='current' OR (payload->>'capture' IS NULL AND NOT (payload ? 'eligibility_recovery'))) GROUP BY state""", (budget, day))
    return dict(cur.fetchall())


def process(connection, day, *, max_jobs, profiles=False, depth_teams=(), postseason_rounds=(), round_totals=False,
            budget='current'):
    if budget not in ('current', 'historical'):
        raise ValueError('Unknown acquisition budget')
    if postseason_rounds and not profiles:
        raise ValueError("Postseason pitcher acquisition requires active profiles")
    if round_totals and not postseason_rounds:
        raise ValueError("Round totals require at least one postseason round")
    name = verify_target(connection)
    client = MLBApiClient()
    with closing(client.session):
        def fetch(endpoint, params):
            if endpoint == savant.URL:
                return savant.fetch(params)
            return client._get(endpoint, params=params)

        receipts = run_cycle(connection, day, fetch, max_jobs=max_jobs, competition=True,
                             statcast=True, active_roster_profiles=profiles, depth_teams=depth_teams,
                             postseason_rounds=postseason_rounds, round_totals=round_totals, budget=budget)
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        states = day_states(cur, day, budget)
        prior = None
        if budget == 'current':
            cur.execute("""SELECT id,product_date FROM candidate.jobs
                           WHERE budget='current' AND state='dead' AND product_date < %s
                             AND payload ? 'continuation' AND payload->>'capture' IS NULL
                           ORDER BY product_date,id LIMIT 1""", (day,))
            prior = cur.fetchone()
    prior_dead_job = dict(id=prior[0], product_date=prior[1].isoformat()) if prior else None
    return dict(database=name, baseball_date=day.isoformat(), receipts=dict(Counter(s for _, s in receipts)),
                jobs_for_date=states, prior_dead_job=prior_dead_job, publication_attempted=False)


def acquisition_failed(report):
    return bool(set(report['receipts']) - {'received'} or report['jobs_for_date'].get('dead')
                or report['prior_dead_job'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Private staging hostname or absolute PostgreSQL socket directory')
    parser.add_argument('--database', choices=('sync_v3_shadow', 'sync_v3_rehearsal', 'baseballos_sync_v3_staging'), default='sync_v3_shadow')
    parser.add_argument('--day', type=date.fromisoformat, required=True)
    parser.add_argument('--max-jobs', type=int, choices=range(1, 257), metavar='1..256', default=32)
    parser.add_argument('--active-profiles', action='store_true')
    parser.add_argument('--depth-team', type=int, choices=MLB_TEAM_IDS, action='append', default=[],
                        help='Also acquire the dated affiliate rosters for this MLB club')
    parser.add_argument('--postseason-round', choices=('F', 'D', 'L', 'W'), action='append', default=[],
                        help='Acquire this round for pitchers discovered through --active-profiles')
    parser.add_argument('--round-totals', action='store_true')
    recovery_modes = parser.add_mutually_exclusive_group()
    recovery_modes.add_argument('--recover-eligibility', type=int, choices=MLB_TEAM_IDS, metavar='MLB_TEAM_ID',
                        help='Recover only missing historical eligibility evidence for this club and date')
    recovery_modes.add_argument('--recover-readiness', type=int, choices=MLB_TEAM_IDS, metavar='MLB_TEAM_ID',
                                help='Also recover the dated schedule and finals required for historical club readiness')
    args = parser.parse_args()
    recovery_team = args.recover_eligibility or args.recover_readiness
    if recovery_team and (args.active_profiles or args.depth_team or args.postseason_round or args.round_totals):
        parser.error('Eligibility recovery derives the source scope from the retained evidence')
    if args.postseason_round and not args.active_profiles:
        parser.error('--postseason-round requires --active-profiles')
    if args.round_totals and not args.postseason_round:
        parser.error('--round-totals requires --postseason-round')
    socket = Path(args.host).is_absolute()
    if not args.host.strip() or ',' in args.host or (args.database == 'sync_v3_rehearsal' and not socket):
        parser.error('Supply a single private host. The rehearsal database requires a local Unix socket.')
    try:
        with closing(psycopg2.connect(host=args.host, dbname=args.database, user='sync_v3_worker',
                                      sslmode='disable' if socket else 'verify-full', connect_timeout=5,
                                      options='-c search_path=pg_catalog',
                                      application_name='baseballos_sync_v3_shadow')) as connection:
            if recovery_team:
                from sync_v3.eligibility_recovery import recover
                client = MLBApiClient()
                with closing(client.session):
                    report = recover(connection, recovery_team, args.day, max_jobs=args.max_jobs,
                                     include_workload=bool(args.recover_readiness),
                                     fetch=lambda endpoint, params: client._get(endpoint, params=params))
                print(json.dumps(report, sort_keys=True))
                return 0 if report['status'] in ('ready', 'season_complete', 'batch_limit', 'awaiting_retry_or_lease') else 1
            report = process(connection, args.day, max_jobs=args.max_jobs, profiles=args.active_profiles,
                             depth_teams=args.depth_team, postseason_rounds=args.postseason_round,
                             round_totals=args.round_totals)
    except psycopg2.Error as exc:
        parser.exit(1, f'Candidate database operation failed ({exc.pgcode or type(exc).__name__}).\n')
    print(json.dumps(report, sort_keys=True))
    if acquisition_failed(report):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
