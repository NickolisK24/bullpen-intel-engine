"""Install the product schema in a private logical database on the approved staging instance."""
import json
import os
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

TARGET = 'baseballos_v3_publication_staging'


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
                cur.execute('CREATE DATABASE baseballos_v3_publication_staging TEMPLATE template0')
            elif existing != (OWNER,):
                raise ValueError('Unexpected staging publication database owner')
            cur.execute('REVOKE ALL ON DATABASE baseballos_v3_publication_staging FROM PUBLIC')
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
            with db.engine.connect() as conn:
                sizes = conn.execute(text("""SELECT pg_database_size(current_database()),
                    (SELECT count(*) FROM public.dashboard_snapshots),
                    (SELECT count(*) FROM public.pitchers)""")).one()
            schedule = project_played_schedule(worker_password)
            roster_report = project_roster_views(worker_password)
            db.engine.dispose()
    return dict(database=TARGET, migration=expected, database_bytes=sizes[0],
                snapshots=sizes[1], pitchers=sizes[2], schedule=schedule, rosters=roster_report, elapsed_seconds=monotonic()-start)


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
                          greatest((SELECT max(id) FROM pitchers),(SELECT last_value FROM pitchers_id_seq)))"""))
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
            result[str(day)] = dict(clubs=clubs, views=clubs*4, newly_acquired=acquired,\n                                    credited_membership=project_credited_membership(day, candidates))
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
