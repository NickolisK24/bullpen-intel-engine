"""Install the product schema in a private logical database on the approved staging instance."""
import json
import os
import resource
from contextlib import closing
from zoneinfo import ZoneInfo
from pathlib import Path
from time import monotonic

from alembic.script import ScriptDirectory
from flask import Flask
from flask_migrate import Migrate, upgrade
from sqlalchemy import URL, text

from services.migration_authority import read_current_heads, verify_heads
from utils.db import db

TARGET = 'baseballos_v3_roster_staging'


def install_target(password, worker_password):
    from sync_v3.render_staging import DATABASE, HOST, OWNER, connect

    start = monotonic()
    # CREATE DATABASE runs outside a transaction. Serialize creation and verification.
    with closing(connect(OWNER, password)) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute('SELECT current_database(),current_user')
            if cur.fetchone() != (DATABASE, OWNER):
                raise ValueError('Unexpected staging installer')
            cur.execute('SELECT pg_advisory_lock(hashtext(%s))', (TARGET,))
            cur.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s', (TARGET,))
            existing = cur.fetchone()
            if existing is None:
                cur.execute('CREATE DATABASE baseballos_v3_roster_staging TEMPLATE template0')
            elif existing != (OWNER,):
                raise ValueError('Unexpected staging publication database owner')
            cur.execute('REVOKE ALL ON DATABASE baseballos_v3_roster_staging FROM PUBLIC')
            cur.execute("SELECT has_database_privilege('sync_v3_worker',%s,'CONNECT')", (TARGET,))
            if cur.fetchone() != (False,):
                raise ValueError('Acquisition worker can connect to publication staging')

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = URL.create(
            'postgresql+psycopg2', username=OWNER, password=password, host=HOST,
            port=5432, database=TARGET, query={'sslmode': 'require', 'connect_timeout': '10'})
        db.init_app(app)
        migrations = str(Path(__file__).resolve().parents[1] / 'migrations')
        Migrate(app, db, directory=migrations)
        expected = ScriptDirectory(migrations).get_current_head()
        with app.app_context():
            with db.engine.begin() as conn:
                identity = conn.execute(text('SELECT current_database(),current_user')).one()
                if tuple(identity) != (TARGET, OWNER):
                    raise ValueError('Unexpected publication migration target')
                conn.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
            os.environ['DATABASE_MIGRATION_MODE'] = 'owner'
            if read_current_heads(db.engine) != (expected,):
                upgrade(directory=migrations, revision=expected)
            verify_heads(read_current_heads(db.engine), expected)
            schedule = project_played_schedule(worker_password)
            workload_window = project_workload_window(worker_password)
            roster_report = project_roster_views(worker_password)
            generation = fatigue = None
            if workload_window['reason'] is None:
                fatigue = project_archived_fatigue()
                if monotonic()-start < 135:
                    generation = advance_private_generation(worker_password)
            with db.engine.connect() as conn:
                sizes = conn.execute(text("""SELECT pg_database_size(current_database()),
                    (SELECT count(*) FROM public.dashboard_snapshots),
                    (SELECT count(*) FROM public.pitchers)""")).one()
            db.engine.dispose()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return dict(peak_rss_kib=usage.ru_maxrss, process_cpu_seconds=usage.ru_utime+usage.ru_stime,
                database=TARGET, migration=expected, database_bytes=sizes[0],
                snapshots=sizes[1], pitchers=sizes[2], schedule=schedule, rosters=roster_report, workload_window=workload_window, generation=generation, archived_fatigue=fatigue, elapsed_seconds=monotonic()-start)


def project_played_schedule(worker_password):
    """Use the verified August acquisition as input to the fenced product writer."""
    from sync_v3.render_staging import PLAYED_DAY, connect
    from sync_v3.discovery import calendar_requests
    from sync_v3.evidence import latest_qualified_source, replay
    from scripts.rehearse_selected_schedule import reconcile_schedule

    with closing(connect('sync_v3_worker', worker_password)) as source, source, source.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        freshness = acquisition_freshness(cur)
        request = calendar_requests(PLAYED_DAY)[0]
        receipt = latest_qualified_source(cur, request.endpoint, request.params())
        if receipt is None:
            raise ValueError('Private played-day acquisition lacks a qualified schedule')
        observation = replay(cur, receipt)
        cur.execute('SELECT sha256 FROM candidate.fetches WHERE id=%s', (receipt,))
        digest, = cur.fetchone()
        identities, finals = stage_identity_inputs(cur, observation, receipt, PLAYED_DAY)

    # The installer owns DDL. The canonical writer runs with table-scoped privileges.
    with db.engine.begin() as conn:
        found = conn.execute(text("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles "
                                  "WHERE rolname='sync_v3_staging_schedule'")).first()
        if found is None:
            conn.execute(text('CREATE ROLE sync_v3_staging_schedule NOLOGIN NOINHERIT'))
        elif tuple(found) != (False, False, False, False):
            raise ValueError('Unexpected staging schedule role attributes')
        conn.execute(text('GRANT sync_v3_staging_schedule TO baseballos_sync_v3_staging_user'))
        conn.execute(text('GRANT USAGE ON SCHEMA public TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT SELECT,INSERT,UPDATE ON scheduled_games,slate_games TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT SELECT ON compatibility_write_events TO sync_v3_staging_schedule'))
        conn.execute(text('GRANT USAGE ON SEQUENCE scheduled_games_id_seq TO sync_v3_staging_schedule'))
        for table in ('scheduled_games', 'slate_games', 'compatibility_write_events'):
            operations = ('SELECT',) if table == 'compatibility_write_events' else ('SELECT', 'INSERT', 'UPDATE')
            for operation in operations:
                name = f'v3_staging_schedule_{operation.lower()}'
                present = conn.execute(text('SELECT 1 FROM pg_policies WHERE schemaname=:schema '
                                            'AND tablename=:table AND policyname=:name'),
                                       dict(schema='public', table=table, name=name)).first()
                if present is None:
                    clauses = {'SELECT': 'USING (true)', 'INSERT': 'WITH CHECK (true)',
                               'UPDATE': 'USING (true) WITH CHECK (true)'}
                    conn.execute(text(f'CREATE POLICY {name} ON public.{table} FOR {operation} '
                                      f'TO sync_v3_staging_schedule {clauses[operation]}'))

    for verify_only in (False, True):
        with db.session.begin():
            db.session.execute(text('SET LOCAL ROLE sync_v3_staging_schedule'))
            reconcile_schedule(PLAYED_DAY, observation, private_staging=True, verify_only=verify_only)
    bound = bind_known_pitchers(identities)
    appearances = project_final_appearances(finals, PLAYED_DAY)
    return dict(appearances=appearances, bound_pitcher_identities=bound, day=str(PLAYED_DAY), receipt=receipt, sha256=digest, received_at=observation.retrieved_at.isoformat(),
                games=sum(len(d['games']) for d in observation.body['dates']), repeated=True,
                current_acquisition=freshness)

def acquisition_freshness(cur):
    """Report local acquisition age, qualified core coverage and ready backlog in one read view."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.discovery import calendar_requests, competition_calendar_request, roster_requests
    from sync_v3.evidence import latest_qualified_source

    cur.execute('SELECT transaction_timestamp()')
    at, = cur.fetchone()
    day = at.astimezone(ZoneInfo('America/New_York')).date()
    summary = {}
    groups = dict(calendar=calendar_requests(day)[:1], transactions=calendar_requests(day)[1:],
                  competition=[competition_calendar_request(day.year)], rosters=roster_requests(day, MLB_TEAM_IDS))
    for group, requests in groups.items():
        ages = []
        for request in requests:
            receipt = latest_qualified_source(cur, request.endpoint, request.params())
            if receipt is not None:
                cur.execute('SELECT received_at FROM candidate.fetches WHERE id=%s', (receipt,))
                age = (at - cur.fetchone()[0]).total_seconds()
                ages.append(round(age))
        summary[group] = dict(required=len(requests), qualified=len(ages), oldest_seconds=max(ages, default=None))
    cur.execute("""SELECT count(*), EXTRACT(EPOCH FROM transaction_timestamp()-min(j.available_at))::bigint
                   FROM candidate.jobs j WHERE j.budget='current' AND j.product_date<=%s
                   AND j.state='pending' AND j.available_at<=transaction_timestamp()
                   AND (j.prerequisite IS NULL OR EXISTS
                       (SELECT 1 FROM candidate.jobs p WHERE p.id=j.prerequisite AND p.state='done'))""", (day,))
    ready, waiting = cur.fetchone()
    return dict(measured_at=at.isoformat(), day=str(day), groups=summary, ready_jobs=ready, oldest_ready_seconds=waiting)

def stage_identity_inputs(cur, schedule, schedule_id, day):
    """Resolve approved ID pairs only against confirmed final pitching lines."""
    from services.pitcher_identity_reconciliation import minimal_identity_values
    from sync_v3.evidence import latest_qualified_source, replay

    pairs = json.loads(os.environ['STAGING_BASEBALL_PUBLIC_IDENTITIES'])['pairs']
    if (len(pairs) != 14 or any(len(p) != 2 or any(type(n) != int or n <= 0 for n in p) for p in pairs)
            or any(len({p[i] for p in pairs}) != len(pairs) for i in (0, 1))):
        raise ValueError('Unexpected staging cohort directory')
    directory = {mlb: public for public, mlb in pairs}
    identities = {}
    finals = []
    for entry in schedule.body['dates']:
        for game in entry['games']:
            pk = game['gamePk']
            source = latest_qualified_source(cur, f'/game/{pk}/boxscore', {})
            cur.execute("""SELECT DISTINCT r.facts FROM candidate.confirmations f
                           JOIN candidate.revisions r ON r.id=f.revision_id
                           JOIN candidate.confirmations ctx ON ctx.source_id=f.context_id
                           JOIN candidate.confirmations slate ON slate.revision_id=ctx.revision_id
                           WHERE f.domain='final' AND f.identity=%s AND f.source_id=%s
                           AND ctx.domain='schedule' AND ctx.identity IN (%s,%s)
                           AND slate.domain=ctx.domain AND slate.identity=ctx.identity AND slate.source_id=%s""",
                        (str(pk), source, str(pk), f'{pk}/{day}', schedule_id))
            facts, = cur.fetchone()
            box = replay(cur, source).body
            extra = {}
            for key, endpoint in (('linescore', 'linescore'), ('play_by_play', 'playByPlay')):
                context_source = latest_qualified_source(cur, f'/game/{pk}/{endpoint}', {})
                if context_source is None:
                    raise ValueError('Missing qualified final context input')
                extra[key] = replay(cur, context_source).body
            finals.append((game, box, facts, extra))
            for line in facts:
                mlb = line['pitcher_mlb_id']
                if mlb not in directory:
                    continue
                team = box['teams'][line['side']]
                player = team['players'][f'ID{mlb}']
                if team['team']['id'] != line['team_id'] or player['person']['id'] != mlb:
                    raise ValueError('Final appearance identity mismatch')
                name = player['person']['fullName']
                position = player['position']['abbreviation']
                if not name or not position:
                    raise ValueError('Missing credited player identity')
                values = minimal_identity_values(player_mlb_id=mlb, line_name=name, line_position=position,
                                                 position_override=position not in ('P', 'Pitcher'))
                identities[mlb] = dict(values, id=directory[mlb])
    if identities.keys() != directory.keys():
        raise ValueError('Approved mapping is outside credited final cohort')
    return identities, finals


def bind_known_pitchers(identities):
    """Bootstrap existing public keys once under the private migration owner's transaction."""
    from models.pitcher import Pitcher

    table = Pitcher.__table__
    with db.engine.begin() as conn:
        if conn.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected identity bootstrap target')
        conn.execute(text('LOCK TABLE public.pitchers IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        for mlb, values in identities.items():
            row = conn.execute(table.select().where((table.c.id == values['id']) | (table.c.mlb_id == mlb))).one_or_none()
            if row is None:
                conn.execute(table.insert().values(**values))
            elif (row.id, row.mlb_id) != (values['id'], mlb):
                raise ValueError('Existing staging identity conflicts with approved mapping')
        # Explicit primary keys must not collide with subsequent generated identities.
        conn.execute(text("""SELECT setval(pg_get_serial_sequence('public.pitchers','id'),
                          greatest((SELECT max(id) FROM pitchers),(SELECT last_value FROM pitchers_id_seq),:reserved))"""),
                     dict(reserved=max(pair[0] for pair in json.loads(os.environ['STAGING_ROSTER_PUBLIC_IDENTITIES'])['pairs'])))
    return len(identities)

def project_final_appearances(finals, day):
    """Apply the governed appearance plan to the staged product and compare every credited row."""
    from collections import Counter
    from services.sync import process_completed_game_for_postgame_refresh, POSTGAME_MARKER_STATUS_FULLY_PROCESSED

    started = monotonic()
    created = inserted = confirmed = contexts = 0
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected final rehearsal target')
        db.session.execute(text('LOCK TABLE pitchers,game_logs,postgame_processed_games IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        for game, box, facts, extra in finals:
            def process(plan_only):
                return process_completed_game_for_postgame_refresh(
                    game, schedule_date=day, boxscore=box, force=True, plan_only=plan_only)
            planned = process(True)
            summary = planned['reconciliation_summary']
            if planned['incomplete_reason'] or summary['rows_blocked'] or summary['rows_planned'] != len(facts):
                raise ValueError('Official final has an incomplete governed plan')
            if summary['rows_unchanged'] != len(facts):
                applied = process(False)
                if applied['incomplete_reason'] or applied['processing_status'] != POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
                    raise ValueError('Final reconciliation incomplete')
                created += applied['pitchers_created']
                inserted += applied['logs_added']
                db.session.flush()
            repeated = process(True)
            if repeated['incomplete_reason'] or repeated['reconciliation_summary']['rows_unchanged'] != len(facts):
                raise ValueError('Final reconciliation did not converge')
            rows = db.session.execute(text("""SELECT p.mlb_id,l.appearance_team_id,l.innings_pitched_outs,
                          l.games_started,l.game_date FROM game_logs l JOIN pitchers p ON p.id=l.pitcher_id
                          WHERE l.mlb_game_pk=:pk"""), dict(pk=game['gamePk']))
            expected = Counter((f['pitcher_mlb_id'],f['team_id'],f['outs_recorded'],int(f['is_starter']),day)
                               for f in facts)
            if Counter(tuple(row) for row in rows) != expected:
                raise ValueError('Staged pitching lines differ from confirmed acquisition')
            contexts += project_context(game, box, extra, day)
            confirmed += len(facts)
    return dict(verified=confirmed, team_game_contexts=contexts, inserted=inserted, identities_created=created, seconds=monotonic()-started)

def project_context(game, box, extra, day):
    from models.completed_game_context import CompletedGameContext
    from services.completed_game_context_payload_adapter import build_completed_game_payload
    from services.completed_game_context_service import extract_completed_game_contexts, upsert_completed_game_context

    payload = build_completed_game_payload(game, boxscore=box, game_date=day, **extra)
    contexts = extract_completed_game_contexts(payload)
    expected = {(side['team']['id'], side['score']) for side in game['teams'].values()}
    if len(contexts) != 2 or {(c['team_id'], c['final_score_for']) for c in contexts} != expected:
        raise ValueError('Derived final context differs from official result')
    for context in contexts:
        row = CompletedGameContext.query.filter_by(team_id=context['team_id'], game_pk=game['gamePk']).one_or_none()
        if row is None:
            row = upsert_completed_game_context(context)
            db.session.flush()
            db.session.refresh(row)
        if any(getattr(row, k) != context[k] for k in CompletedGameContext.DERIVED_COLUMNS
               if k in context and k != 'generated_at'):
            raise ValueError('Stored game context differs from retained final evidence')
    return len(contexts)


def project_roster_views(worker_password):
    """Retain the qualified MLB roster observations for workload and availability separately."""
    from datetime import timedelta
    from hashlib import sha256
    from sync_v3 import evidence, queue, rosters
    from sync_v3.render_staging import PLAYED_DAY, connect
    from sync_v3.discovery import roster_requests
    from sync_v3.current_worker import verify_target
    from services.mlb_api import MLBApiClient
    from services.mlb_club_directory import MLB_TEAM_IDS
    from services.roster_evidence import RunRosterEvidence
    from services.primary_roster_inputs import retain_roster_inputs
    from scripts.rehearse_selected_roster import CapturedRoster, matched_departure_evidence
    from models.source_observation import SourceObservation, SourceSubject

    result = {}
    staff = {}
    dated = {}
    client = MLBApiClient()
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        for day in (PLAYED_DAY, PLAYED_DAY + timedelta(days=1)):
            acquired = 0
            clubs = 0
            candidates = {}
            for team in sorted(MLB_TEAM_IDS):
                bodies, stamps = {}, {}
                for req in roster_requests(day, [team]):
                    params = req.params()
                    with source, source.cursor() as cur:
                        oid = evidence.latest_qualified_source(cur, req.endpoint, params)
                        if oid is None:
                            payload = dict(endpoint=req.endpoint, params=params, eligibility_recovery=True)
                            key = sha256(evidence.encode_json(['eligibility_recovery', str(day), payload])).hexdigest()
                            cur.execute('SELECT clock_timestamp()')
                            at, = cur.fetchone()
                            job = queue.enqueue(cur, key, payload, at, budget='historical', product_date=day)
                            claim = queue.claim(cur, at, budget='historical', product_date=day, only_job_id=job)
                    if oid is None:
                        if not claim:
                            raise ValueError('Roster acquisition pending retry or lease')
                        oid, outcome = evidence.execute(source, claim, client._get, on_received=rosters.observe)
                        if outcome != 'received':
                            raise ValueError(f'Historical roster recovery returned {outcome}')
                        acquired += 1
                    with source, source.cursor() as cur:
                        obs = evidence.replay(cur, oid)
                    kind = params['rosterType']
                    bodies[kind] = obs.body
                    stamps[kind] = obs.retrieved_at
                from sync_v3.depth import board_rest_pitchers
                with source, source.cursor() as cur:
                    members = board_rest_pitchers(cur, team, day)
                if members is None:
                    raise ValueError('Unqualified dated staff')
                for entry in bodies['active']['roster']:
                    person = entry['person']
                    if person['id'] in members:
                        staff[person['id']] = person['fullName']
                capture = RunRosterEvidence(CapturedRoster(team, day, bodies), represented_date=day)
                with db.session.begin():
                    existing = {}
                    for kind in bodies:
                        view = capture.roster_view(team, kind)
                        if view.error:
                            raise ValueError('Invalid retained roster view')
                        stamp = stamps[kind].astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
                        capture.fetch_times[team, kind] = (stamp, stamp)
                        row = (SourceObservation.query.join(SourceSubject)
                               .filter(SourceSubject.subject_key == f'primary:{team}:{kind}',
                                       SourceSubject.baseball_date == day, SourceSubject.source_domain == 'roster')
                               .order_by(SourceObservation.version_number.desc()).first())
                        if row:
                            if (not row.is_authoritative or row.completeness != 'complete'
                                    or row.payload_artifact.payload_json['records'] != list(view.entries)
                                    or row.observed_at != stamp):
                                raise ValueError('Target roster differs from retained acquisition')
                            existing[kind] = row
                    if not existing:
                        links = retain_roster_inputs(capture, team, None, [])
                    elif existing.keys() != bodies.keys():
                        raise ValueError('Partial target roster capture')
                    if existing:
                        links = dict(active_roster_observation_id=existing['active'].id,
                                     forty_man_roster_observation_id=existing['40Man'].id)
                    from services.roster_status_sync import build_exact_date_team_roster_status_index
                    index, errors = build_exact_date_team_roster_status_index(team, day, evidence=capture)
                    if errors:
                        raise ValueError('Incomplete official roster evidence')
                    for player, record in index.items():
                        if record['roster_types'] & {'active', '40Man'}:
                            candidates.setdefault(player, []).append(dict(team_id=team, evidence=record,
                                                                         observation_links=links, snapshot_date=day))
                    if existing and team == 108 and day > PLAYED_DAY:
                        matched_departure_evidence(team, 502032, day, bodies, existing)
                clubs += 1
            dated[day] = candidates
            result[str(day)] = dict(clubs=clubs, views=clubs*4, newly_acquired=acquired)
    result['roster_identities'] = bind_active_staff(staff)
    for day, candidates in dated.items():
        result[str(day)]['membership'] = project_credited_membership(day, candidates)
    return result


def project_credited_membership(day, by_player):
    from models.pitcher import Pitcher
    from models.roster_status_snapshot import RosterStatusSnapshot
    from services.primary_roster_inputs import replay_membership
    from services.roster_status_sync import classify_roster_evidence, persist_missing_exact_roster_status_snapshots

    with db.session.begin():
        pitchers = Pitcher.query.order_by(Pitcher.id).all()
        candidates = []
        for pitcher in pitchers:
            matches = by_player.get(pitcher.mlb_id, [])
            if len(matches) > 1:
                raise ValueError('Conflicting dated club memberships')
            if matches:
                candidates.append(dict(matches[0], pitcher=pitcher))
        report = persist_missing_exact_roster_status_snapshots(candidates)
        if report['conflicts'] or report['failure_records']:
            raise ValueError('Dated roster writer refused observations')
        active = 0
        for candidate in candidates:
            row = RosterStatusSnapshot.query.filter_by(pitcher_id=candidate['pitcher'].id, snapshot_date=day).one()
            kinds = candidate['evidence']['roster_types']
            expected = ('active' in kinds, '40Man' in kinds)
            if (row.team_id != candidate['team_id'] or row.mlb_id != candidate['pitcher'].mlb_id
                    or row.roster_status != classify_roster_evidence(candidate['evidence'])['status']
                    or (row.active_roster, row.forty_man_roster) != expected
                    or any(getattr(row, key) != value for key, value in candidate['observation_links'].items())
                    or replay_membership(row) != expected):
                raise ValueError('Dated roster evidence differs from stored membership')
            active += int(expected[0])
        return dict(verified=len(candidates), active=active, outside_active_and_40man=len(pitchers)-len(candidates),
                    created=report['created'])


def bind_active_staff(staff):
    """Reserve approved public keys before allocating any new staging-local pitcher keys."""
    from models.pitcher import Pitcher
    pairs = json.loads(os.environ['STAGING_ROSTER_PUBLIC_IDENTITIES'])['pairs']
    if (len(pairs) != 60 or any(len(p) != 2 or any(type(x) != int or x <= 0 for x in p) for p in pairs)
            or any(len({p[i] for p in pairs}) != 60 for i in (0, 1))):
        raise ValueError('Invalid roster identity cohort')
    public = {mlb: pid for pid, mlb in pairs}
    if not public.keys() <= staff.keys():
        raise ValueError('Approved mapping exceeds qualified roster cohort')
    table = Pitcher.__table__
    with db.engine.begin() as conn:
        if conn.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private target')
        conn.execute(text('LOCK TABLE pitchers IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        existing = dict(conn.execute(text('SELECT mlb_id,id FROM pitchers')).all())
        by_id = {pid: mlb for mlb, pid in existing.items()}
        collisions = sum(existing.get(mlb, pid) != pid or by_id.get(pid, mlb) != mlb
                         for mlb, pid in public.items())
        if collisions:
            raise ValueError(f'{collisions} staging public identity collisions')
        created = 0
        for mapped in (True, False):
            for mlb, name in sorted(staff.items()):
                if mlb in existing or (mlb in public) != mapped:
                    continue
                values = dict(mlb_id=mlb, full_name=name, position='P', active=False)
                if mapped:
                    values['id'] = public[mlb]
                conn.execute(table.insert().values(**values))
                created += 1
            if mapped:
                conn.execute(text("""SELECT setval(pg_get_serial_sequence('public.pitchers','id'),
                                 greatest((SELECT max(id) FROM pitchers),(SELECT last_value FROM pitchers_id_seq)))"""))
        stored = dict(conn.execute(text('SELECT mlb_id,id FROM pitchers')).all())
        if not staff.keys() <= stored.keys() or any(stored[k] != v for k,v in public.items()):
            raise ValueError('Roster identity verification failed')
    return dict(mapped=len(public), created=created, collisions=collisions)


def project_workload_window(worker_password):
    """Establish the expected final-game population before evaluating workload completeness."""
    from datetime import timedelta
    from services.appearance_ledger import appearance_ledger_publish_block, ledger_window_days
    from services.mlb_api import MLBApiClient
    from scripts.rehearse_selected_schedule import reconcile_schedule, retained_makeups
    from sync_v3 import evidence
    from sync_v3.current_worker import verify_target
    from sync_v3.discovery import calendar_requests
    from sync_v3.render_staging import PLAYED_DAY, connect

    client = MLBApiClient()
    receipts = {}
    observations = {}
    # calculate_fatigue counts appearances in the fourteen days before the availability date.
    required_days = max(ledger_window_days(), 14)
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        for offset in range(1-required_days, 2):
            day = PLAYED_DAY + timedelta(days=offset)
            request = calendar_requests(day)[0]
            params = request.params()
            oid = acquire_window_source(source, client, day, request.endpoint, params)
            with source, source.cursor() as cur:
                obs = evidence.replay(cur, oid)
            observations[day] = obs
            receipts[str(day)] = oid
    makeups = retained_makeups(observations)
    for day, obs in observations.items():
        with db.session.begin():
            db.session.execute(text('SET LOCAL ROLE sync_v3_staging_schedule'))
            reconcile_schedule(day, obs, private_staging=True, makeups=makeups)
    with db.session.begin():
        reason, ledger = appearance_ledger_publish_block(end_date=PLAYED_DAY, window_days=required_days)
        if ledger is None:
            raise ValueError('Appearance ledger unavailable for private publication')
    recovered = 0
    if ledger['missing_games']:
        recovered = recover_missing_finals(worker_password, receipts, ledger['missing_games'])
        with db.session.begin():
            reason, ledger = appearance_ledger_publish_block(end_date=PLAYED_DAY, window_days=required_days)
            if ledger is None:
                raise ValueError('Appearance ledger unavailable after recovery')
    return dict(receipts=receipts, reconciled_makeups=sorted(makeups), window_days=ledger['window_days'], recovered=recovered, reason=reason, expected_games=ledger['expected_games'],
                represented_games=ledger['represented_games'], stored_appearances=ledger['stored_appearances'],
                missing_games=len(ledger['missing_games']))


def acquire_window_source(source, client, day, endpoint, params):
    from hashlib import sha256
    from sync_v3 import canonical, evidence, queue
    with source, source.cursor() as cur:
        oid = evidence.latest_qualified_source(cur, endpoint, params)
        if oid is None:
            payload = dict(endpoint=endpoint, params=params, eligibility_recovery=True)
            key = sha256(evidence.encode_json(['eligibility_recovery', str(day), payload])).hexdigest()
            cur.execute('SELECT clock_timestamp()')
            at, = cur.fetchone()
            job = queue.enqueue(cur, key, payload, at, budget='historical', product_date=day)
            claim = queue.claim(cur, at, budget='historical', product_date=day, only_job_id=job)
    if oid is None:
        if not claim:
            raise ValueError(f'Acquisition pending for {day}')
        oid, outcome = evidence.execute(source, claim, client._get,
            on_received=lambda cur, oid, obs: canonical.observe(cur, oid, obs, day))
        if outcome != 'received':
            raise ValueError(f'Source recovery for {day} returned {outcome}')
    return oid


def recover_missing_finals(worker_password, receipts, missing):
    """Commit a verified final at a time. A later execution resumes at the first missing game."""
    from datetime import date
    from services.mlb_api import MLBApiClient
    from sync_v3 import evidence
    from sync_v3.current_worker import verify_target
    from sync_v3.render_staging import connect

    client = MLBApiClient()
    started = monotonic()
    recovered = 0
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        for entry in sorted(missing, key=lambda item: (item['game_date'], item['game_pk'])):
            if monotonic() - started > 120:
                break
            day = date.fromisoformat(entry['game_date'])
            pk = entry['game_pk']
            schedule_id = receipts[str(day)]
            with source, source.cursor() as cur:
                schedule = evidence.replay(cur, schedule_id)
                game, = [g for d in schedule.body['dates'] for g in d['games'] if g['gamePk'] == pk]
            bodies = {}
            for key, path in [('box', 'boxscore'), ('linescore', 'linescore'), ('play_by_play', 'playByPlay')]:
                oid = acquire_window_source(source, client, day, f'/game/{pk}/{path}', {})
                with source, source.cursor() as cur:
                    if key == 'box':
                        cur.execute("""SELECT DISTINCT r.facts FROM candidate.confirmations c
                            JOIN candidate.revisions r ON r.id=c.revision_id
                            WHERE c.domain='final' AND c.identity=%s AND c.context_id=%s AND c.source_id=%s""",
                                    (str(pk), schedule_id, oid))
                        facts, = cur.fetchone()
                    bodies[key] = evidence.replay(cur, oid).body
            project_final_appearances([(game, bodies.pop('box'), facts, bodies)], day)
            recovered += 1
    return recovered


def recheck_edition_transactions(source, through, digest, fetch):
    """Reacquire the published archive day's transactions once, preserving both receipts."""
    from sync_v3 import evidence, queue
    from sync_v3.cycle import plan_children
    from sync_v3.discovery import calendar_requests

    request = calendar_requests(through)[1]
    capture = f'private-edition-recheck/{digest}'
    payload = dict(endpoint=request.endpoint, params=request.params(), capture=capture)
    with source, source.cursor() as cur:
        cur.execute("""SELECT manifest->'transaction_source' FROM candidate.generations
                       WHERE digest=%s AND represented=%s""", (digest, through))
        row = cur.fetchone()
        if not row or not row[0] or not row[0].get('revisions_digest'):
            raise ValueError('The archived edition lacks pinned canonical transactions')
        prior = row[0]
        cur.execute('SELECT clock_timestamp()')
        at, = cur.fetchone()
        job = queue.enqueue(cur, capture, payload, at, budget='historical', product_date=through)
        claim = queue.claim(cur, at, budget='historical', product_date=through, capture=capture, only_job_id=job)
    if claim:
        def reconcile(cur, receipt, observation):
            plan_children(cur, receipt, observation, 'historical', observation.retrieved_at, through)

        _, outcome = evidence.execute(source, claim, fetch, on_received=reconcile)
        if outcome != 'received':
            raise ValueError(f'Private transaction reacquisition returned {outcome}')
    with source, source.cursor() as cur:
        cur.execute("""SELECT f.id,f.sha256 FROM candidate.attempts a JOIN candidate.fetches f USING(token)
                       JOIN candidate.jobs j ON a.job_id=j.id WHERE j.id=%s AND j.state='done'
                       AND f.outcome='received' AND NOT EXISTS (
                           SELECT 1 FROM candidate.refusals r WHERE r.source_id=f.id)""", (job,))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise ValueError('Expected a settled, qualified transaction recheck')
        source_id, fingerprint = rows[0]
        if evidence.latest_qualified_source(cur, request.endpoint, request.params()) != source_id:
            raise ValueError('The reacquisition has been superseded')
        if fingerprint != prior['digest']:
            raise ValueError('MLB revised the archived transactions. Reconcile the retained change before publication.')
    return dict(predecessor_generation=digest, acquired=bool(claim), source_id=source_id, sha256=fingerprint)


def recover_private_readiness(worker_password, *, budget_seconds):
    """Resume only the archived clubs whose latest readiness evidence withheld a state."""
    from services.mlb_api import MLBApiClient
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.current_worker import verify_target
    from sync_v3.eligibility_recovery import recover
    from sync_v3.intelligence_history import DOMAINS, record_intelligence
    from sync_v3.render_staging import PLAYED_DAY, connect

    started = monotonic()
    client = MLBApiClient()
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute("""SELECT DISTINCT ON (mlb_id) mlb_id,facts->>'reason' FROM candidate.workload_history
                           WHERE subject='team' AND methodology=%s AND represented=%s
                           ORDER BY mlb_id,revision DESC""", (DOMAINS['readiness'][1], PLAYED_DAY))
            statuses = dict(cur.fetchall())
        if statuses.keys() != set(MLB_TEAM_IDS):
            raise ValueError('Expected all thirty archived readiness snapshots')
        outstanding = {team for team, reason in statuses.items() if reason}
        blocked = {}
        receipts = 0
        for team in sorted(outstanding):
            while monotonic() - started < budget_seconds:
                report = recover(source, team, PLAYED_DAY, max_jobs=24, include_workload=True,
                                 fetch=lambda endpoint, params: client._get(endpoint, params=params))
                receipts += len(report['receipts'])
                state = report['status']
                if state == 'ready':
                    record_intelligence(source, 'readiness', team, PLAYED_DAY)
                    outstanding.remove(team)
                elif state != 'batch_limit':
                    blocked[team] = report['readiness_reason']
                print(json.dumps(dict(private_readiness=dict(club=team, status=state,
                                 reason=report['readiness_reason'], received=len(report['receipts']),
                                 remaining=len(outstanding)))), flush=True)
                if state != 'batch_limit':
                    break
            if monotonic() - started >= budget_seconds:
                break
        return dict(task='recover-readiness', receipts=receipts, remaining_clubs=sorted(outstanding),
                    withheld=blocked, elapsed_seconds=monotonic()-started)


def advance_private_generation(worker_password, *, budget_seconds=90):
    """Build candidate intelligence from private acquisition. Keep the selection pointer untouched."""
    from datetime import timedelta
    from sync_v3.current_worker import verify_target
    from sync_v3.generation import build_batch, generation_date_decision, verify_generation
    from sync_v3.render_staging import PLAYED_DAY, connect

    as_of = PLAYED_DAY + timedelta(days=1)
    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            decision = generation_date_decision(cur, PLAYED_DAY, as_of)
        if decision['reason']:
            return dict(decision=decision, scopes_built=0)
        started = monotonic()
        count = 0
        while True:
            batch = build_batch(source, PLAYED_DAY, 100, as_of=as_of, deadline=started+budget_seconds)
            digest = batch['after']
            count += len(batch['processed'])
            if not batch['processed']:
                review = verify_generation(source, digest, compare_latest=True)
                return dict(digest=digest, scopes_built=count, elapsed_seconds=monotonic()-started,
                            review=review['selection_review'], clubs=review['clubs'],
                            snapshots=review['snapshots'], missing_scopes=review['missing_scopes'])
            if digest == batch['before']:
                raise ValueError('Private intelligence batch did not advance')
            with source, source.cursor() as cur:
                cur.execute("""SELECT jsonb_array_length(manifest->'missing'),
                                      jsonb_array_length(manifest->'stale_inputs'),
                                      jsonb_array_length(manifest->'stale_comparisons'),
                                      ARRAY(SELECT club->>'readiness' FROM jsonb_array_elements(manifest->'clubs') club)
                               FROM candidate.generations WHERE digest=%s""", (digest,))
                missing, stale, comparisons, club_status = cur.fetchone()
            progress = dict(digest=digest, scopes_built=count, elapsed_seconds=monotonic()-started,
                            missing_scopes=missing, stale_inputs=stale, stale_comparisons=comparisons,
                            review='building', club_readiness={reason: club_status.count(reason) for reason in sorted(set(club_status))})
            print(json.dumps(dict(private_intelligence=progress)), flush=True)
            if monotonic()-started >= budget_seconds:
                return progress


def project_archived_fatigue():
    """Project the archived edition's official roster and calculate its fourteen-day scores."""
    from datetime import datetime, time, timedelta
    from models.fatigue_score import FatigueScore
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.roster_status_snapshot import RosterStatusSnapshot
    from services.fatigue import calculate_fatigue
    from services.mlb_club_directory import MLB_CLUBS
    from services.primary_roster_inputs import replay_membership
    from services.roster_status_sync import _apply_snapshot_to_pitcher_cache, _declare_roster_ownership
    from services.team_assignment_sync import _classification_from_roster_evidence, _apply_assignment
    from sync_v3.render_staging import PLAYED_DAY

    day = PLAYED_DAY + timedelta(days=1)
    # The private archived edition uses the same noon UTC product clock as the disposable rehearsal.
    edition_clock = datetime.combine(day, time(12))
    teams = {club.team_id: dict(name=club.team_name, abbreviation=club.abbreviation) for club in MLB_CLUBS}
    fields = [col.name for col in FatigueScore.__table__.columns if col.name not in ('id', 'calculated_at')]
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected historical product target')
        db.session.execute(text('LOCK TABLE pitchers, roster_status_snapshots, game_logs, fatigue_scores '
                                'IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        rows = (db.session.query(Pitcher, RosterStatusSnapshot)
                .join(RosterStatusSnapshot, RosterStatusSnapshot.pitcher_id == Pitcher.id)
                .filter(RosterStatusSnapshot.snapshot_date == day)
                .order_by(RosterStatusSnapshot.team_id, Pitcher.id).all())
        count = 0
        last_team = None
        for pitcher, snapshot in rows:
            active, forty = replay_membership(snapshot)
            if not (active or forty) or pitcher.mlb_id != snapshot.mlb_id:
                raise ValueError('Historical membership does not support the assignment')
            if snapshot.team_id != last_team:
                _declare_roster_ownership(snapshot.team_id)
                last_team = snapshot.team_id
            evidence = dict(appearances=[dict(team_id=snapshot.team_id, roster_type='active' if active else '40Man')])
            assignment = _classification_from_roster_evidence(evidence, teams)
            _apply_assignment(pitcher, assignment, edition_clock)
            _apply_snapshot_to_pitcher_cache(pitcher, snapshot)
            logs = (GameLog.query.filter(GameLog.pitcher_id == pitcher.id,
                                         GameLog.game_date.between(day-timedelta(days=14), PLAYED_DAY))
                    .order_by(GameLog.game_date.desc(), GameLog.id.desc()).all())
            if not logs:
                continue
            score = calculate_fatigue(pitcher, logs, reference_date=day)
            score.calculated_at = edition_clock
            prior = FatigueScore.query.filter_by(pitcher_id=pitcher.id, calculated_at=edition_clock).one_or_none()
            if prior is None:
                db.session.add(score)
            elif any(getattr(prior, name) != getattr(score, name) for name in fields):
                raise ValueError('Stored archived score differs from current qualified workload')
            count += 1
        db.session.flush()
        db.session.expire_all()
        for pitcher, snapshot in rows:
            if not pitcher.active or pitcher.team_id != snapshot.team_id or pitcher.roster_status != snapshot.roster_status:
                raise ValueError('Dated roster cache differs from qualified official evidence')
        if count != FatigueScore.query.filter_by(calculated_at=edition_clock).count():
            raise ValueError('Historical fatigue population changed')
        return dict(represented_date=str(day), modeled_product_clock=edition_clock.isoformat()+'Z',
                    roster_assignments=len(rows), verified_scores=count)
