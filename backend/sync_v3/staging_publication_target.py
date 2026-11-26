"""Install the product schema in a private logical database on the approved staging instance."""
import json
import os
import resource
from contextlib import closing, nullcontext
from datetime import date
from zoneinfo import ZoneInfo
from pathlib import Path
from time import monotonic

from flask import Flask
from flask_migrate import Migrate
from sqlalchemy import URL, text

from scripts.database_migrations import upgrade_private_staging
from services.migration_authority import require_owner
from utils.db import db

CURRENT_TARGET = 'baseballos_v3_roster_staging'
ARCHIVE_TARGET = 'baseballos_v3_competitive_rehearsal'
TARGET = ARCHIVE_TARGET if os.environ.get('STAGING_PRODUCT_TIMELINE') == 'competitive_archive' else CURRENT_TARGET


def install_target(password, worker_password):
    from sync_v3.render_staging import DATABASE, HOST, OWNER, connect

    from psycopg2 import sql
    require_owner()
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
                cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(TARGET)))
            elif existing != (OWNER,):
                raise ValueError('Unexpected staging publication database owner')
            cur.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(TARGET)))
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
        with app.app_context():
            with db.engine.begin() as conn:
                identity = conn.execute(text('SELECT current_database(),current_user')).one()
                if tuple(identity) != (TARGET, OWNER):
                    raise ValueError('Unexpected publication migration target')
                conn.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
            expected = upgrade_private_staging()
            if TARGET == ARCHIVE_TARGET:
                from sqlalchemy.dialects.postgresql import insert
                from models.pitcher import Pitcher
                # Transfer only the immutable lookup keys and names. Dated roster, game and
                # intelligence facts must enter this timeline through the regular writers.
                import psycopg2
                with closing(psycopg2.connect(host=HOST, dbname=CURRENT_TARGET, user=OWNER, password=password,
                                              sslmode='require', connect_timeout=10)) as original:
                    with original, original.cursor() as cur:
                        cur.execute('SET TRANSACTION READ ONLY')
                        cur.execute('SELECT id,mlb_id,full_name FROM public.pitchers ORDER BY id')
                        directory = cur.fetchall()
                if not directory:
                    raise ValueError('Missing established private identity directory')
                with db.engine.begin() as conn:
                    table = Pitcher.__table__
                    stmt = insert(table).on_conflict_do_nothing(index_elements=['id'])
                    conn.execute(stmt, [dict(id=k, mlb_id=mlb, full_name=name, active=False)
                                        for k, mlb, name in directory])
                    known = dict(conn.execute(text('SELECT id,mlb_id FROM pitchers')).all())
                    if any(known.get(k) != mlb for k, mlb, _ in directory):
                        raise ValueError('Competitive timeline canonical identities conflict')
                    conn.execute(text("SELECT setval(pg_get_serial_sequence('public.pitchers','id'), "
                                      "greatest((SELECT max(id) FROM pitchers),(SELECT last_value FROM pitchers_id_seq)))"))
                return dict(database=TARGET, identities=len(directory), migration=expected)
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

def project_final_appearances(finals, day, *, include_context=True, in_transaction=False):
    """Apply the governed appearance plan to the staged product and compare every credited row."""
    from collections import Counter
    from services.sync import process_completed_game_for_postgame_refresh, POSTGAME_MARKER_STATUS_FULLY_PROCESSED

    started = monotonic()
    created = inserted = confirmed = contexts = 0
    with (nullcontext() if in_transaction else db.session.begin()):
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected final rehearsal target')
        db.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.session.execute(text('LOCK TABLE pitchers,game_logs,postgame_processed_games IN SHARE ROW EXCLUSIVE MODE'))
        for game, box, facts, extra in finals:
            dates = {f['pitcher_mlb_id']: date.fromisoformat(f['workload_date']) for f in facts if 'workload_date' in f}
            def process(plan_only):
                return process_completed_game_for_postgame_refresh(
                    game, schedule_date=day, boxscore=box, force=True, plan_only=plan_only,
                    require_official_pitching_credit=True, appearance_dates=dates or None)
            planned = process(True)
            summary = planned['reconciliation_summary']
            if planned['incomplete_reason'] or summary['rows_blocked'] or summary['rows_planned'] != len(facts):
                raise ValueError(f"Official game {game['gamePk']} on {day}: {planned['incomplete_reason']}, "
                                 f"{summary['rows_blocked']} blocked, {summary['rows_planned']} planned, "
                                 f"{len(facts)} official appearances, "
                                 f"{planned['pitcher_resolution_failures']} unresolved identities")
            if summary['rows_unchanged'] != len(facts):
                corrections = [dict(fields=row['semantic_changed_fields'], digest=row['mutation_digest'])
                               for row in planned['reconciliation_plan'] if row.get('semantic_changed_fields')]
                if corrections:
                    print(json.dumps(dict(private_final_correction=dict(game_pk=game['gamePk'], day=str(day),
                                                                      corrections=corrections))), flush=True)
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
            expected = Counter((f['pitcher_mlb_id'],f['team_id'],f['outs_recorded'],int(f['is_starter']),dates.get(f['pitcher_mlb_id'], day))
                               for f in facts)
            if Counter(tuple(row) for row in rows) != expected:
                raise ValueError('Staged pitching lines differ from confirmed acquisition')
            if include_context:
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


def project_roster_views(worker_password, *, edition_dates=None, initialized=False):
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
    roster_sources = set()
    current_club_inputs = {}
    client = MLBApiClient()
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        dates = edition_dates or (PLAYED_DAY, PLAYED_DAY + timedelta(days=1))
        for day in dict.fromkeys(dates):
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
                    roster_sources.add(oid)
                    kind = params['rosterType']
                    bodies[kind] = obs.body
                    stamps[kind] = obs.retrieved_at
                from sync_v3.depth import _view, board_rest_pitchers
                with source, source.cursor() as cur:
                    if edition_dates:
                        # The offseason directory includes official two-way players. Pregame rest has
                        # a separate eligibility contract and is withheld for season-complete clubs.
                        view = _view(cur, team, team, 'active', dict(date=str(day), rosterType='active'), membership=True)
                        if view['reason']:
                            raise ValueError(f"Unresolved official roster for {team} on {day}: {view['reason']}")
                        members = view['pitchers']
                    else:
                        members = board_rest_pitchers(cur, team, day)
                if members is None:
                    raise ValueError(f'Unqualified dated staff for {team} on {day}')
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
                    if edition_dates and day == dates[-1]:
                        current_club_inputs[team] = (index, links)
                    for player, record in index.items():
                        if record['roster_types'] & {'active', '40Man'}:
                            candidates.setdefault(player, []).append(dict(team_id=team, evidence=record,
                                                                         observation_links=links, snapshot_date=day))
                    if existing and not edition_dates and team == 108 and day > PLAYED_DAY:
                        matched_departure_evidence(team, 502032, day, bodies, existing)
                clubs += 1
            dated[day] = candidates
            result[str(day)] = dict(clubs=clubs, views=clubs*4, newly_acquired=acquired)
    result['source_receipts'] = sorted(roster_sources)
    result['roster_identities'] = bind_active_staff(staff, initialized=initialized)
    for day, candidates in dated.items():
        result[str(day)]['membership'] = project_credited_membership(
            day, candidates, apply_position=day == dates[-1], club_inputs=current_club_inputs if day == dates[-1] else {})
    return result


def project_credited_membership(day, by_player, *, apply_position, club_inputs):
    from models.pitcher import Pitcher
    from models.sync_run import SyncRun
    from sync_v3.render_staging import PLAYED_DAY
    from models.roster_status_snapshot import RosterStatusSnapshot
    from services.primary_roster_inputs import replay_membership
    from services.roster_status_sync import (_apply_current_position_to_pitcher_cache, _apply_snapshot_to_pitcher_cache, _declare_roster_ownership,
                                             classify_roster_evidence, persist_missing_exact_roster_status_snapshots)

    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private roster projection target')
        db.session.execute(text('LOCK TABLE roster_status_snapshots IN SHARE ROW EXCLUSIVE MODE'))
        pitchers = Pitcher.query.order_by(Pitcher.id).all()
        candidates = []
        for pitcher in pitchers:
            matches = by_player.get(pitcher.mlb_id, [])
            if len(matches) > 1:
                raise ValueError('Conflicting dated club memberships')
            if matches:
                candidates.append(dict(matches[0], pitcher=pitcher))
            elif pitcher.active and pitcher.team_id in club_inputs:
                index, links = club_inputs[pitcher.team_id]
                candidates.append(dict(team_id=pitcher.team_id, pitcher=pitcher, snapshot_date=day,
                                       evidence=index.get(pitcher.mlb_id), observation_links=links))
        attributed = {pid for pid, in db.session.query(RosterStatusSnapshot.pitcher_id).filter(
            RosterStatusSnapshot.snapshot_date == day, RosterStatusSnapshot.sync_run_id.isnot(None))}
        unbound = {item['pitcher'].id for item in candidates} - attributed
        start = db.session.execute(text("SELECT transaction_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        to_attribute = []
        run = None
        report = persist_missing_exact_roster_status_snapshots(candidates)
        if report['conflicts'] or report['failure_records']:
            raise ValueError('Dated roster writer refused observations')
        active = 0
        owner_team = None
        for candidate in sorted(candidates, key=lambda item: (item['team_id'], item['pitcher'].id)):
            if candidate['team_id'] != owner_team:
                owner_team = candidate['team_id']
                _declare_roster_ownership(owner_team)
            row = RosterStatusSnapshot.query.filter_by(pitcher_id=candidate['pitcher'].id, snapshot_date=day).one()
            evidence = candidate['evidence']
            kinds = (evidence or {}).get('roster_types', ())
            expected = ('active' in kinds, '40Man' in kinds) if evidence is not None else (None, None)
            if (row.team_id != candidate['team_id'] or row.mlb_id != candidate['pitcher'].mlb_id
                    or row.roster_status != classify_roster_evidence(candidate['evidence'])['status']
                    or (row.active_roster, row.forty_man_roster) != expected
                    or any(getattr(row, key) != value for key, value in candidate['observation_links'].items())
                    or replay_membership(row) != expected):
                raise ValueError('Dated roster evidence differs from stored membership')
            if apply_position and evidence:
                _apply_current_position_to_pitcher_cache(candidate['pitcher'], evidence)
            if club_inputs and not any(expected):
                from services.team_assignment_sync import (
                    _apply_assignment, _classification_from_roster_evidence, _source_for, ROSTER_PRECEDENCE,
                    SOURCE_PREFIX, TEAM_ASSIGNMENT_UNKNOWN,
                )
                from services.mlb_club_directory import MLB_CLUBS
                pitcher = candidate['pitcher']
                if pitcher.team_assignment_source in {_source_for(kind) for kind in ROSTER_PRECEDENCE}:
                    # The earlier roster-backed club assignment expired. The four new views can
                    # establish another assignment or leave present affiliation unknown.
                    appearances = [dict(team_id=row.team_id, roster_type=kind) for kind in kinds]
                    team_map = {club.team_id: dict(name=club.team_name, abbreviation=club.abbreviation) for club in MLB_CLUBS}
                    assignment = _classification_from_roster_evidence(dict(appearances=appearances), team_map)
                    _apply_assignment(pitcher, assignment or dict(status=TEAM_ASSIGNMENT_UNKNOWN,
                                      source=f'{SOURCE_PREFIX}:dated_roster_absence'), row.updated_at or row.first_seen_at)
                _apply_snapshot_to_pitcher_cache(pitcher, row)
            if row.sync_run_id is None:
                to_attribute.append(row)
            active += int(bool(expected[0]))
        if {row.pitcher_id for row in to_attribute} != unbound:
            raise ValueError('Dated roster reconciliation scope changed')
        if to_attribute:
            completed = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
            run = SyncRun(job_name='sync_v3_roster_reconciliation', source='sync_v3_staging',
                          latest_workload_date=day, status='success', stage='verified_roster_observations',
                          records_processed=len(unbound), started_at=start, completed_at=completed)
            db.session.add(run)
            db.session.flush()
            for row in sorted(to_attribute, key=lambda snapshot: (snapshot.team_id, snapshot.pitcher_id)):
                if row.team_id != owner_team:
                    owner_team = row.team_id
                    _declare_roster_ownership(owner_team)
                row.sync_run_id = run.id
            db.session.flush()
            credited = {pid for pid, in db.session.query(RosterStatusSnapshot.pitcher_id).filter_by(
                snapshot_date=day, sync_run_id=run.id)}
            if credited != unbound:
                raise ValueError('Stored roster reconciliation provenance differs from the verified membership')
        return dict(verified=len(candidates), active=active, outside_active_and_40man=len(pitchers)-len(candidates),
                    created=report['created'], newly_attributed=len(unbound), reconciliation_run=run.id if run else None)


def bind_active_staff(staff, *, initialized=False):
    """Reserve approved public keys before allocating any new staging-local pitcher keys."""
    from models.pitcher import Pitcher
    pairs = json.loads(os.environ['STAGING_ROSTER_PUBLIC_IDENTITIES'])['pairs']
    if (len(pairs) != 60 or any(len(p) != 2 or any(type(x) != int or x <= 0 for x in p) for p in pairs)
            or any(len({p[i] for p in pairs}) != 60 for i in (0, 1))):
        raise ValueError('Invalid roster identity cohort')
    public = {mlb: pid for pid, mlb in pairs}
    table = Pitcher.__table__
    with db.engine.begin() as conn:
        if conn.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private target')
        conn.execute(text('LOCK TABLE pitchers IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        existing = dict(conn.execute(text('SELECT mlb_id,id FROM pitchers')).all())
        if not public.keys() <= (staff.keys() | existing.keys()):
            raise ValueError('Unreserved public identity lies outside the qualified roster cohort')
        if initialized and not public.keys() <= existing.keys():
            raise ValueError('The current writer requires preinstalled public pitcher identities')
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
            if mapped and not initialized:
                conn.execute(text("""SELECT setval(pg_get_serial_sequence('public.pitchers','id'),
                                 greatest((SELECT max(id) FROM pitchers),(SELECT last_value FROM pitchers_id_seq)))"""))
        stored = dict(conn.execute(text('SELECT mlb_id,id FROM pitchers')).all())
        if not staff.keys() <= stored.keys() or any(stored[k] != v for k,v in public.items()):
            raise ValueError('Roster identity verification failed')
    return dict(mapped=len(public), created=created, collisions=collisions)


def project_workload_window(worker_password, *, workload_day=None, scoped=False, verify_only=False):
    """Establish the expected final-game population before evaluating workload completeness."""
    from datetime import timedelta
    from services.appearance_ledger import appearance_ledger_publish_block, ledger_window_days
    from services.mlb_api import MLBApiClient
    from scripts.rehearse_selected_schedule import reconcile_schedule, retained_makeups
    from sync_v3 import evidence
    from sync_v3.current_worker import verify_target
    from sync_v3.discovery import calendar_requests
    from sync_v3.render_staging import PLAYED_DAY, connect

    workload_day = workload_day or PLAYED_DAY
    client = MLBApiClient()
    receipts = {}
    observations = {}
    # calculate_fatigue counts appearances in the fourteen days before the availability date.
    required_days = max(ledger_window_days(), 14)
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        for offset in range(1-required_days, 2):
            day = workload_day + timedelta(days=offset)
            request = calendar_requests(day)[0]
            params = request.params()
            oid = acquire_window_source(source, client, day, request.endpoint, params)
            with source, source.cursor() as cur:
                obs = evidence.replay(cur, oid)
            observations[day] = obs
            receipts[str(day)] = oid
        makeups = retained_makeups(observations)
        for day, obs in observations.items():
            with db.session.begin(), source, source.cursor() as cur:
                predecessor = None
                if not scoped:
                    db.session.execute(text('SET LOCAL ROLE sync_v3_staging_schedule'))
                elif not verify_only:
                    from sync_v3.staging_projector import product_schedule_predecessor
                    predecessor = product_schedule_predecessor(cur, day, obs)
                reconcile_schedule(day, obs, private_staging=True, makeups=makeups, verify_only=verify_only,
                                   predecessor=predecessor)
    with db.session.begin():
        reason, ledger = appearance_ledger_publish_block(end_date=workload_day, window_days=required_days)
        if ledger is None:
            raise ValueError('Appearance ledger unavailable for private publication')
    recovered = 0
    if ledger['missing_games'] and not verify_only:
        recovered = recover_missing_finals(worker_password, receipts, ledger['missing_games'])
        with db.session.begin():
            reason, ledger = appearance_ledger_publish_block(end_date=workload_day, window_days=required_days)
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
        def reconcile(cur, source_id, observation):
            if endpoint == '/transactions':
                from sync_v3.cycle import plan_children
                plan_children(cur, source_id, observation, 'historical', observation.retrieved_at, day)
            elif endpoint != '/schedule' or 'season' not in params:
                canonical.observe(cur, source_id, observation, day)
        oid, outcome = evidence.execute(source, claim, client._get, on_received=reconcile)
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


def project_eligibility_history(worker_password, *, budget_seconds):
    """Reconcile the actual historical appearances used by the qualified ten-appearance role samples."""
    from datetime import date
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3 import evidence
    from sync_v3.current_worker import verify_target
    from sync_v3.discovery import calendar_requests
    from sync_v3.intelligence_history import DOMAINS
    from sync_v3.render_staging import PLAYED_DAY, connect
    from sync_v3.workload import _game_workload

    started = monotonic()
    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute("""SELECT DISTINCT ON (mlb_id) mlb_id,facts->>'reason',facts->'eligibility_games'
                           FROM candidate.workload_history WHERE subject='team' AND methodology=%s AND represented=%s
                           ORDER BY mlb_id, revision DESC""", (DOMAINS['readiness'][1], PLAYED_DAY))
            samples = {}
            clubs = set()
            for team, reason, staff in cur:
                if reason or staff is None:
                    raise ValueError(f'Club {team} still lacks a qualified eligibility sample')
                clubs.add(team)
                for player, games in staff.items():
                    if int(player) in samples or len(games) != len(set(games)) or len(games) > 10:
                        raise ValueError('Ambiguous official pitcher eligibility sample')
                    samples[int(player)] = set(games)
            if clubs != set(MLB_TEAM_IDS) or not samples:
                raise ValueError('Incomplete private eligibility population')

        with db.session.begin():
            if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
                raise ValueError('Unexpected private eligibility target')
            rows = db.session.execute(text("""SELECT p.mlb_id,l.mlb_game_pk FROM pitchers p JOIN game_logs l
                ON p.id=l.pitcher_id WHERE p.mlb_id=ANY(:players) AND l.game_date<=:day"""),
                dict(players=sorted(samples), day=PLAYED_DAY))
            present = set(rows)
        missing = sorted({pk for player, games in samples.items() for pk in games if (player, pk) not in present})
        reconciled = 0
        print(json.dumps(dict(eligibility_projection_start=dict(pitchers=len(samples), missing_games=len(missing)))),
              flush=True)
        for pk in missing:
            with source, source.cursor() as cur:
                cur.execute("""SELECT f.parameters->>'startDate' FROM candidate.confirmations c
                    JOIN candidate.fetches f ON f.id=c.context_id WHERE c.domain='final' AND c.identity=%s
                    ORDER BY c.observed_at DESC,c.source_id DESC LIMIT 1""", (str(pk),))
                row = cur.fetchone()
                if not row or not row[0]:
                    raise ValueError(f'Missing dated final confirmation for eligibility game {pk}')
                day = date.fromisoformat(row[0])
                schedule = calendar_requests(day)[0]
                receipt = evidence.latest_qualified_source(cur, schedule.endpoint, schedule.params())
                listing = evidence.replay(cur, receipt).body
                game, = [g for entry in listing['dates'] for g in entry['games'] if g['gamePk'] == pk]
                final, reason = _game_workload(cur, game, day, receipt)
                if not final:
                    raise ValueError(f'Eligibility game {pk} withheld: {reason}')
                facts, (box_id, _) = final
                box = evidence.replay(cur, box_id).body
            project_final_appearances([(game, box, facts, {})], day, include_context=False)
            reconciled += 1
            if monotonic()-started >= budget_seconds:
                break

        if reconciled == len(missing):
            with db.session.begin():
                rows = db.session.execute(text("""SELECT mlb_id,mlb_game_pk FROM (
                    SELECT p.mlb_id,l.mlb_game_pk,row_number() OVER (
                        PARTITION BY p.id ORDER BY l.game_date DESC,l.id) AS position
                    FROM pitchers p JOIN game_logs l ON l.pitcher_id=p.id
                    WHERE p.mlb_id=ANY(:players) AND l.game_date<=:day
                ) ranked WHERE position<=10"""), dict(players=sorted(samples), day=PLAYED_DAY))
                actual = {player: set() for player in samples}
                for player, pk in rows:
                    actual[player].add(pk)
                conflicts = sorted(player for player in samples if actual[player] != samples[player])
                if conflicts:
                    raise ValueError(f'Private target eligibility dates disagree for MLB pitchers {conflicts}')
        return dict(qualified_clubs=len(clubs), pitchers=len(samples), represented_appearances=sum(map(len, samples.values())),
                    missing_games_at_start=len(missing), reconciled_games=reconciled, remaining_games=len(missing)-reconciled,
                    elapsed_seconds=monotonic()-started)


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


def recover_private_readiness(worker_password, *, budget_seconds, workload_day=None):
    """Resume the clubs whose dated readiness evidence is still incomplete."""
    from services.mlb_api import MLBApiClient
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.current_worker import verify_target
    from sync_v3.eligibility_recovery import recover
    from sync_v3.intelligence_history import DOMAINS, record_intelligence
    from sync_v3.render_staging import PLAYED_DAY, connect

    workload_day = workload_day or PLAYED_DAY
    started = monotonic()
    client = MLBApiClient()
    with closing(client.session), closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute("""SELECT DISTINCT ON (mlb_id) mlb_id,facts->>'reason',
                           (facts->'competition'->>'status'='season_complete' AND
                            facts->>'reason'=facts->'competition'->>'basis') AS settled FROM candidate.workload_history
                           WHERE subject='team' AND methodology=%s AND represented=%s
                           ORDER BY mlb_id,revision DESC""", (DOMAINS['readiness'][1], workload_day))
            statuses = {team: (reason, settled) for team, reason, settled in cur}
        if statuses.keys() != set(MLB_TEAM_IDS):
            raise ValueError('Expected all thirty dated readiness snapshots')
        outstanding = {team for team, (reason, settled) in statuses.items() if reason and not settled}
        blocked = {}
        receipts = 0
        for team in sorted(outstanding):
            while monotonic() - started < budget_seconds:
                report = recover(source, team, workload_day, max_jobs=24, include_workload=True,
                                 fetch=lambda endpoint, params: client._get(endpoint, params=params))
                receipts += len(report['receipts'])
                state = report['status']
                if state == 'ready':
                    record_intelligence(source, 'readiness', team, workload_day)
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


def advance_private_generation(worker_password, *, budget_seconds=90, workload_day=None, as_of=None, checkpoint=None):
    """Build candidate intelligence from private acquisition. Keep the selection pointer untouched."""
    from datetime import timedelta
    from sync_v3.current_worker import verify_target
    from sync_v3.generation import build_batch, generation_date_decision, verify_generation
    from sync_v3.render_staging import PLAYED_DAY, connect

    workload_day = workload_day or PLAYED_DAY
    as_of = as_of or workload_day + timedelta(days=1)
    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            decision = generation_date_decision(cur, workload_day, as_of)
        if decision['reason']:
            return dict(decision=decision, scopes_built=0)
        started = monotonic()
        count = 0
        digest = checkpoint
        if digest is None:
            with source, source.cursor() as cur:
                cur.execute('''SELECT digest, manifest->'missing'='[]'::jsonb
                                      AND manifest->'stale_inputs'='[]'::jsonb AND manifest->'stale_comparisons'='[]'::jsonb
                               FROM candidate.generations WHERE represented=%s
                               AND manifest->>'contract'='candidate_generation_inventory_v1'
                               ORDER BY creation_xid DESC LIMIT 1''', (workload_day,))
                previous = cur.fetchone()
            digest = previous[0] if previous else None
            if previous and previous[1]:
                # The reviewer recomputes the latest inventory in its read-only transaction.
                review = verify_generation(source, digest, compare_latest=True)
                if review['selection_review']['latest_inventory_digest'] == digest:
                    return dict(digest=digest, scopes_built=0, elapsed_seconds=monotonic()-started,
                                review=review['selection_review'], clubs=review['clubs'],
                                snapshots=review['snapshots'], missing_scopes=review['missing_scopes'])
                digest = None
        while True:
            batch = build_batch(source, workload_day, 100, as_of=as_of, deadline=started+budget_seconds, resume=digest)
            digest = batch['after']
            count += len(batch['processed'])
            if not batch['processed'] and digest == batch['before']:
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
            if not (missing or stale or comparisons) or monotonic()-started >= budget_seconds:
                return progress


def lock_private_fatigue():
    # Coordinate private score writers without granting UPDATE on dated score history.
    db.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('baseballos_v3_private_fatigue'))"))


def project_archived_fatigue(*, edition_dates=None):
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

    through, day = edition_dates or (PLAYED_DAY, PLAYED_DAY + timedelta(days=1))
    # The private archived edition uses the same noon UTC product clock as the disposable rehearsal.
    edition_clock = datetime.combine(day, time(12))
    teams = {club.team_id: dict(name=club.team_name, abbreviation=club.abbreviation) for club in MLB_CLUBS}
    fields = [col.name for col in FatigueScore.__table__.columns if col.name not in ('id', 'calculated_at')]
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected historical product target')
        lock_private_fatigue()
        db.session.execute(text('LOCK TABLE pitchers, roster_status_snapshots, game_logs '
                                'IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        rows = (db.session.query(Pitcher, RosterStatusSnapshot)
                .join(RosterStatusSnapshot, RosterStatusSnapshot.pitcher_id == Pitcher.id)
                .filter(RosterStatusSnapshot.snapshot_date == day,
                        RosterStatusSnapshot.active_roster.is_(True) | RosterStatusSnapshot.forty_man_roster.is_(True))
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
                                         GameLog.game_date.between(day-timedelta(days=14), through))
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


def project_prior_fatigue(worker_password, digest):
    """Restore previous scores for qualified relievers whose last outing predates the edition window."""
    from datetime import datetime, time, timedelta
    from models.fatigue_score import FatigueScore
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from services.fatigue import calculate_fatigue
    from sync_v3.current_worker import verify_target
    from sync_v3.intelligence_history import DOMAINS
    from sync_v3.render_staging import PLAYED_DAY, connect

    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("""SELECT h.mlb_id,h.facts->'arms',h.facts->'eligibility_games'
                           FROM candidate.generation_inputs i JOIN candidate.workload_history h ON h.id=i.snapshot
                           WHERE i.generation=%s AND h.represented=%s AND h.methodology=%s""",
                        (digest, PLAYED_DAY, DOMAINS['readiness'][1]))
            clubs = cur.fetchall()
    from services.mlb_club_directory import MLB_TEAM_IDS
    if {club for club, _, _ in clubs} != set(MLB_TEAM_IDS):
        raise ValueError('Expected all clubs in the pinned readiness inventory')
    restored = []
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private historical workload target')
        db.session.execute(text('LOCK TABLE game_logs IN SHARE MODE'))
        lock_private_fatigue()
        db.session.execute(text('LOCK TABLE fatigue_scores IN SHARE ROW EXCLUSIVE MODE'))
        fields = [col.name for col in FatigueScore.__table__.columns if col.name not in ('id', 'calculated_at')]
        for _, arms, samples in clubs:
            for mlb in arms:
                games = set(samples[mlb])
                if not games:
                    continue
                pitcher = Pitcher.query.filter_by(mlb_id=int(mlb)).one()
                logs = (GameLog.query.filter(GameLog.pitcher_id == pitcher.id, GameLog.mlb_game_pk.in_(games))
                        .order_by(GameLog.game_date.desc(), GameLog.id.desc()).all())
                if len(logs) != len(games) or any(log.game_type != 'R' or log.game_date > PLAYED_DAY for log in logs):
                    raise ValueError(f'Incomplete private pitching sample for {mlb}')
                last = logs[0].game_date
                if (PLAYED_DAY-last).days < 14:
                    continue
                day = last + timedelta(days=1)
                start = day - timedelta(days=14)
                if len(games) == 10 and logs[-1].game_date >= start:
                    raise ValueError(f'Prior score window extends beyond the retained sample for {mlb}')
                window = [log for log in logs if log.game_date >= start]
                if any(log.pitches_thrown is None for log in window):
                    raise ValueError(f'Historical score lacks a pitch count for {mlb}')
                score = calculate_fatigue(pitcher, window, reference_date=day)
                score.calculated_at = datetime.combine(day, time(12))
                prior = FatigueScore.query.filter_by(pitcher_id=pitcher.id, calculated_at=score.calculated_at).one_or_none()
                if prior is None:
                    db.session.add(score)
                elif any(getattr(prior, name) != getattr(score, name) for name in fields):
                    raise ValueError(f'Prior fatigue revision differs for {mlb}')
                restored.append(dict(mlb_id=int(mlb), represented_date=day.isoformat(), created=prior is None,
                                     games=sorted(log.mlb_game_pk for log in window)))
    return restored
