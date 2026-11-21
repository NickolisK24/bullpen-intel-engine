"""Create an isolated socket-only PostgreSQL cluster and run the v3 rehearsal."""

import argparse
from contextlib import closing, contextmanager
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
                    cur.execute('CREATE ROLE sync_v3_reviewer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
                    cur.execute('CREATE DATABASE sync_v3_rehearsal')
                    for dbname in ('postgres', 'template1', DATABASE):
                        cur.execute(f'REVOKE ALL ON DATABASE {dbname} FROM PUBLIC')
                    cur.execute('GRANT CONNECT ON DATABASE sync_v3_rehearsal TO sync_v3_worker,sync_v3_reviewer')
            finally:
                admin.close()
            owner = connect(DATABASE, 'rehearsal_owner')
            try:
                with owner, owner.cursor() as cur:
                    cur.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
                    cur.execute('CREATE SCHEMA candidate')
                    cur.execute('GRANT USAGE ON SCHEMA candidate TO sync_v3_worker,sync_v3_reviewer')
                def runtime(*, reviewer=False):
                    return connect(DATABASE, 'sync_v3_reviewer' if reviewer else RUNTIME)
                yield owner, runtime
            finally:
                owner.close()
        finally:
            subprocess.run([pg_ctl, '-D', str(data), '-m', 'fast', '-w', 'stop'],
                           check=True, env=env, stdout=subprocess.DEVNULL)


def run(bindir=None, fixture=None, pitcher=None, through=None, team=None, league=False, game=None,
        deployment_team=None, performance_team=None, schedule_team=None, competition=False, readiness_team=None, snapshot=False, snapshot_domain=None, since=None, generation=False, generation_batch=0, build_generation=False, exercise_selection=False, identity_fixture=None, identity_proof=None):
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
            withheld = []
            if fixture:
                from sync_v3.replay import ReplayWithheld, install, run_fixture
                import json
                reference = json.loads(Path(identity_fixture).read_text()) if identity_fixture else None
                if identity_proof:
                    from sync_v3.public_identities import from_observed_publication
                    reference = from_observed_publication(*identity_proof)
                install(owner, identity_export=reference)
                count = 0
                for filename in fixture:
                    try:
                        count += run_fixture(worker, filename)
                    except ReplayWithheld as exc:
                        withheld.append(f'{filename}: {exc}')
                from sync_v3.comparison import compare_finals
                with worker, worker.cursor() as cur:
                    games, appearances = compare_finals(cur)
                    cur.execute('SELECT count(*) FROM candidate.captured_requests')
                    preserved, = cur.fetchone()
                print(f'{preserved} parsed HTTP observations preserved across distinct offline captures')
                print(f'{count} observations in fully accepted days; {games} finals and {appearances} pitching lines compared')
            if snapshot or snapshot_domain:
                import json
                from sync_v3.history import record_workload
                from sync_v3.readiness_history import record_readiness
                if snapshot_domain:
                    from sync_v3.intelligence_history import DOMAINS, record_intelligence
                    subject = snapshot_domain
                    mlb_id = {'team': team, 'pitcher': pitcher, 'game': game}[DOMAINS[subject][0]]
                    builder, scope = record_intelligence, (subject, mlb_id)
                elif readiness_team is not None:
                    subject, mlb_id = 'readiness', readiness_team
                    builder, scope = record_readiness, (mlb_id,)
                else:
                    subject, mlb_id = ('team', team) if team is not None else ('pitcher', pitcher)
                    builder, scope = record_workload, (subject, mlb_id)
                from datetime import timedelta
                first = since or through
                for offset in range((through-first).days+1):
                    day = first + timedelta(days=offset)
                    result = builder(worker, *scope, day)
                    if builder(worker, *scope, day) != result:
                        raise RuntimeError('Repeated historical snapshot diverged')
                    with worker, worker.cursor() as cur:
                        cur.execute('SELECT input_digest FROM candidate.workload_history WHERE id=%s', (result[0],))
                        input_digest, = cur.fetchone()
                    from sync_v3.change_history import COMPARISONS, record_changes
                    if subject in COMPARISONS:
                        event_set = record_changes(worker, subject, mlb_id, day)
                        with worker, worker.cursor() as cur:
                            cur.execute('SELECT facts FROM candidate.workload_history WHERE id=%s', (event_set[0],))
                            print(json.dumps(cur.fetchone()[0]))
                    print(json.dumps(dict(subject=subject, mlb_id=mlb_id, through=day.isoformat(),
                                          snapshot_id=result[0], revision=result[1], semantic_digest=result[2],
                                          input_digest=input_digest)))
            elif readiness_team is not None:
                import json
                from sync_v3.comparison import compare_readiness
                from sync_v3.readiness import represented_readiness
                with worker, worker.cursor() as cur:
                    report = represented_readiness(cur, readiness_team, through)
                    report['comparison'] = compare_readiness(report)
                    print(json.dumps(report, sort_keys=True))
            elif competition:
                import json
                from sync_v3.competition_calendar import competition_status
                with worker, worker.cursor() as cur:
                    print(json.dumps(competition_status(cur, through), sort_keys=True))
            elif schedule_team is not None:
                import json
                from sync_v3.schedule_context import club_schedule_context
                with worker, worker.cursor() as cur:
                    print(json.dumps(club_schedule_context(cur, schedule_team, through), sort_keys=True))
            elif performance_team is not None:
                import json
                from sync_v3.group_performance import active_group_performance
                with worker, worker.cursor() as cur:
                    print(json.dumps(active_group_performance(cur, performance_team, through), sort_keys=True))
            elif deployment_team is not None:
                import json
                from sync_v3.deployment import club_role_movement
                with worker, worker.cursor() as cur:
                    print(json.dumps(club_role_movement(cur, deployment_team, through), sort_keys=True))
            elif game is not None:
                import json
                from sync_v3.deployment import game_deployment
                with worker, worker.cursor() as cur:
                    print(json.dumps(game_deployment(cur, game, through, include_pitch_samples=True), sort_keys=True))
            elif league:
                import json
                from sync_v3.comparison import compare_team_workload
                from sync_v3.workload import load_club_calendars, team_workload
                with worker, worker.cursor() as cur:
                    clubs = {}
                    for team_id, calendar in load_club_calendars(cur, through).items():
                        report = team_workload(cur, calendar, team_id, through)
                        clubs[team_id] = {
                            'boxscore_windows_compared': compare_team_workload(cur, calendar, report),
                            'coverage_gaps': {day.isoformat(): reason for day, (_, reason)
                                              in calendar.items() if reason},
                        }
                    print(json.dumps({'through': through.isoformat(), 'clubs': clubs}, sort_keys=True))
            elif pitcher is not None or team is not None:
                import json
                from sync_v3.workload import (
                    load_calendar, outing_pitch_comparison, rest_from_calendar, team_workload, windows_from_calendar,
                )
                with worker, worker.cursor() as cur:
                    calendar = load_calendar(cur, through, team=team)
                    from sync_v3.rosters import dated_pitcher_sources
                    from sync_v3.season_deployment import pitcher_season_deployment
                    identity = dated_pitcher_sources(cur, pitcher, through) if pitcher is not None else []
                    result = team_workload(cur, calendar, team, through) if team is not None else {
                        'windows': windows_from_calendar(calendar, pitcher, through, identity_sources=identity),
                        'rest': rest_from_calendar(calendar, pitcher, through, identity_sources=identity),
                        'pitch_comparison': outing_pitch_comparison(calendar, pitcher, through),
                        'season_deployment': pitcher_season_deployment(cur, pitcher, through),
                    }
                    if pitcher is not None:
                        from sync_v3.deployment import pitcher_measurement_history
                        result.update(pitcher_measurement_history(cur, pitcher, through, result['season_deployment']))
                    if team is not None:
                        from sync_v3.comparison import compare_team_workload
                        from sync_v3.rotation import club_rotation
                        from sync_v3.depth import club_depth
                        result['depth'] = club_depth(cur, team, through)
                        result['rotation'] = club_rotation(calendar, team, through)
                        result['boxscore_windows_compared'] = compare_team_workload(cur, calendar, result)
                    print(json.dumps(result, sort_keys=True))
            if generation or generation_batch or build_generation:
                import json
                from sync_v3.generation import build_batch, freeze_generation, verify_generation
                if generation_batch or build_generation:
                    seen = set()
                    while True:
                        batch = build_batch(worker, through, generation_batch or 75)
                        print(json.dumps(batch), flush=True)
                        digest = batch['after']
                        if not build_generation or not batch['processed']:
                            break
                        if digest in seen or digest == batch['before']:
                            raise RuntimeError('Candidate generation cannot resolve its outstanding inputs')
                        seen.add(digest)
                else:
                    digest = freeze_generation(worker, through)
                print(json.dumps(verify_generation(worker, digest, compare_latest=True)))
                with worker, worker.cursor() as cur:
                    cur.execute('SELECT manifest FROM candidate.generations WHERE digest=%s', (digest,))
                    print(json.dumps(dict(generation=digest, manifest=cur.fetchone()[0])))
                if identity_proof:
                    from sync_v3.product_reads import compare_archived_league, preview_league
                    print(json.dumps(compare_archived_league(preview_league(worker, digest), reference)))
                if exercise_selection:
                    from sync_v3.selection import select_generation, SelectionWithheld
                    with closing(connect(reviewer=True)) as reviewer:
                        try:
                            revision = select_generation(reviewer, digest, expected_revision=0)
                        except SelectionWithheld as exc:
                            with reviewer, reviewer.cursor() as cur:
                                cur.execute('SELECT count(*) FROM candidate.core_selections')
                                if cur.fetchone() != (0,):
                                    raise RuntimeError('A withheld selection changed the rehearsal ledger')
                            print(json.dumps(dict(isolated_selection=exc.review, ledger_entries=0)))
                        else:
                            if select_generation(reviewer, digest, expected_revision=0) != revision:
                                raise RuntimeError('Retry changed the committed selection')
                            from sync_v3.product_reads import read_league, read_game_cards
                            listing = read_league(worker, revision=revision)
                            if listing['generation'] != digest or len(listing['teams']) != 30:
                                raise RuntimeError('League listing disagrees with the selection')
                            print(json.dumps(dict(historical_league=listing)))
                            slate = read_game_cards(worker, revision=revision)
                            if slate['generation'] != digest:
                                raise RuntimeError('Game cards disagree with the selected generation')
                            print(json.dumps(dict(historical_slate=slate)))
                            restored = select_generation(reviewer, None, expected_revision=revision, rollback=True)
                            print(json.dumps(dict(isolated_selection=digest, revision=revision,
                                                  restored_revision=restored, restored_generation=None)))
            print(f'PostgreSQL {worker.server_version}: isolated cluster, worker permissions verified', flush=True)
            if withheld:
                raise ReplayWithheld('\n'.join(withheld))
        finally:
            worker.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin')
    parser.add_argument('--fixture', action='append', help='Path to an offline day (repeat to replay history)')
    from datetime import date
    subject = parser.add_mutually_exclusive_group()
    subject.add_argument('--readiness-team', type=int, help='Inspect represented regular-season Team State and arm reads')
    subject.add_argument('--competition', action='store_true', help='Classify all clubs on the retrospective reference date')
    subject.add_argument('--schedule-team', type=int, help='Inspect the retrospective club calendar around a date')
    subject.add_argument('--performance-team', type=int, help='Inspect retrospective active bullpen performance')
    subject.add_argument('--deployment-team', type=int, help='Compare two weeks of observed club deployment')
    subject.add_argument('--game', type=int, help='Inspect relief deployment for one official gamePk')
    subject.add_argument('--league', action='store_true', help='Verify club workload windows against official boxes for all 30 teams')
    subject.add_argument('--team', type=int, help='Inspect official relief workload for an MLB club ID')
    subject.add_argument('--pitcher', type=int, help='Inspect historical relief workload for an MLB ID')
    from sync_v3.intelligence_history import DOMAINS
    parser.add_argument('--snapshot-domain', choices=sorted(DOMAINS), help='Freeze an intelligence domain for its MLB subject')
    parser.add_argument('--snapshot', action='store_true', help='Freeze and repeat the represented team or pitcher workload')
    parser.add_argument('--generation', action='store_true', help='Inventory the frozen candidate scopes after the rehearsal')
    parser.add_argument('--build-generation', action='store_true',
                        help='Rehearse outstanding generation scopes in bounded batches until the inventory settles')
    identities = parser.add_mutually_exclusive_group()
    identities.add_argument('--identity-proof', nargs=2, metavar=('ZIP','SHA256'),
                            help='Use identities observed in a verified archived BaseballOS publication')
    identities.add_argument('--identity-fixture', help='Optional sanitized local export of BaseballOS pitcher identity columns')
    parser.add_argument('--exercise-selection', action='store_true',
                        help='Exercise the isolated core selector and restore its initial state')
    parser.add_argument('--generation-batch', type=int, choices=range(1, 101), metavar='N',
                        help='Build up to N outstanding candidate scopes before freezing a generation')
    parser.add_argument('--since', type=date.fromisoformat, help='First represented snapshot date, inclusive')
    parser.add_argument('--through', type=date.fromisoformat)
    args = parser.parse_args()
    has_subject = args.build_generation or args.league or args.competition or any(value is not None for value in (
        args.pitcher, args.team, args.game, args.deployment_team, args.performance_team, args.schedule_team, args.readiness_team,
    ))
    if (args.identity_fixture or args.identity_proof) and not args.fixture:
        parser.error('An identity reference requires an offline source fixture')
    if args.exercise_selection and not args.build_generation:
        parser.error('--exercise-selection requires --build-generation')
    if args.since and (not (args.snapshot or args.snapshot_domain) or not args.through or args.since > args.through):
        parser.error('--since requires snapshot mode and a through date on or after the first date')
    if args.snapshot_domain and getattr(args, DOMAINS[args.snapshot_domain][0]) is None:
        parser.error(f'--snapshot-domain {args.snapshot_domain} requires --{DOMAINS[args.snapshot_domain][0]}')
    if args.snapshot and not args.snapshot_domain and args.team is None and args.pitcher is None and args.readiness_team is None:
        parser.error('--snapshot requires --team, --pitcher or --readiness-team')
    if (args.generation or args.generation_batch) and not (args.snapshot or args.snapshot_domain or args.build_generation):
        parser.error('Generation inventory requires a snapshot calculation or --build-generation')
    if has_subject != bool(args.through) or (has_subject and not args.fixture):
        parser.error('Supply a subject with --through and at least one --fixture')
    run(args.pg_bin, args.fixture, args.pitcher, args.through, args.team, args.league, args.game,
        args.deployment_team, args.performance_team, args.schedule_team, args.competition, args.readiness_team, args.snapshot, args.snapshot_domain, args.since, args.generation, args.generation_batch, args.build_generation, args.exercise_selection, args.identity_fixture, args.identity_proof)
