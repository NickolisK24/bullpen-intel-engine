"""Publish a reviewed generation only inside the private product rehearsal database."""
from contextlib import closing, contextmanager, nullcontext
from datetime import date
import json
import os
import sys
from time import CLOCK_MONOTONIC, clock_gettime, perf_counter

from sqlalchemy import URL, text

from sync_v3 import runtime_binding
from sync_v3.render_staging import HOST, OWNER, connect
from sync_v3.staging_publication_target import TARGET


def open_generation_source(password, user):
    from sync_v3.current_worker import verify_target
    from sync_v3.staging_publisher import PUBLISHER, verify_source

    if user not in ('sync_v3_worker', PUBLISHER):
        raise ValueError('Unexpected private generation source reader')
    source = connect(user, password)
    try:
        (verify_target if user == 'sync_v3_worker' else verify_source)(source)
    except Exception:
        source.close()
        raise
    return source


class ReviewedGenerationAdvanced(ValueError):
    """The primary worker must refresh this generation before it can be published."""


def current_edition_inputs(cur, through, availability, *, offseason):
    """Bind the actual product day to qualified schedules, transactions and dated club rosters."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3 import evidence
    from sync_v3.competition_calendar import calendar_games, competition_status
    from sync_v3.discovery import calendar_requests, competition_calendar_request, roster_requests
    from sync_v3.rosters import transactions_confirmed
    from sync_v3.generation import _slate, generation_date_decision

    from sync_v3.render_staging import primary_product_day
    day = primary_product_day()
    competition = competition_status(cur, day)
    if len(competition['clubs']) != 30 or competition['missing_decisions']:
        raise ValueError('Incomplete official competition evidence')
    season = competition_calendar_request(day.year)
    if offseason:
        if any(club['status'] != 'season_complete' for club in competition['clubs'].values()):
            raise ValueError('The offseason generation conflicts with official competition status')
        games = calendar_games(season.params(), evidence.replay(cur, competition['calendar_source']).body)
        latest = max(d for d, row, _ in games.values() if d <= day and row['status_state'] == 'final')
        if latest != through or generation_date_decision(cur, through, day)['status'] != 'aligned':
            raise ValueError('Offseason candidate differs from the last official final or calendar coverage')
    else:
        from sync_v3.primary_date import edition_scope
        scope = edition_scope(cur, day, after_finals=(through == day))
        if scope['offseason'] or scope['through'] != through or scope['availability'] != availability:
            raise ValueError('Competitive edition differs from the current supported workload and availability')
    slate, _ = _slate(cur, day)
    if slate['reason'] or slate['games'] is None or (offseason and slate['games']):
        raise ValueError('Incomplete or conflicting current product slate')
    requests = [season, *calendar_requests(day), *roster_requests(day, MLB_TEAM_IDS)]
    ids = []
    for request in requests:
        oid = evidence.latest_qualified_source(cur, request.endpoint, request.params())
        if oid is None:
            raise ValueError(f'Missing qualified current receipt for {request.endpoint}')
        ids.append(oid)
        if request.endpoint == '/transactions':
            observation = evidence.replay(cur, oid)
            if not transactions_confirmed(cur, oid, observation):
                raise ValueError('Current transactions lack canonical confirmation')
    from sync_v3.depth import _view
    staff = {}
    for team in sorted(MLB_TEAM_IDS):
        active = _view(cur, team, team, 'active', dict(date=availability, rosterType='active'), membership=True)
        if active['reason'] or active['pitchers'] is None:
            raise ValueError(f'Unqualified availability-date pitcher directory for {team}')
        ids.append(active['source'])
        staff[str(team)] = sorted(active['pitchers'])
    return dict(product_day=day.isoformat(), current_source_ids=sorted(set(ids)), active_pitcher_mlb_ids=staff), slate['games']


def reviewed_board_populations(cur, password, user, digest, binding):
    """Read independent, completed team reviews and reject any superseded source input."""
    from sync_v3.staging_publisher import PUBLISHER
    from sync_v3.staging_reader import _connect

    if user != PUBLISHER:
        raise ValueError('The private current edition requires its restricted publisher')
    teams = binding['active_pitcher_mlb_ids']
    names = [f'sync_v3_board_review_{team}' for team in teams]
    with closing(_connect(user, password)) as target, target, target.cursor() as target_cur:
        target_cur.execute('SET TRANSACTION READ ONLY')
        target_cur.execute(f"""SELECT DISTINCT ON (job_name) id, publication_outcome FROM public.sync_runs
            WHERE job_name=ANY(%s) AND source='{runtime_binding.RUN_SOURCE}' AND status='success'
            AND stage='reviewed' AND publication_outcome->>'generation'=%s ORDER BY job_name,id DESC""", (names, digest))
        reviews = target_cur.fetchall()
        target_cur.execute(f"""SELECT id, publication_outcome, started_at FROM public.sync_runs
            WHERE job_name='sync_v3_canonical_cycle' AND source='{runtime_binding.RUN_SOURCE}' AND status='success'
              AND stage='canonical_ready' ORDER BY id DESC LIMIT 1""")
        projection = target_cur.fetchone()
        if not projection or (projection[1]['generation'], projection[1]['day']) != (digest, binding['product_day']):
            raise ValueError('Current publication requires its dated canonical checkpoint')
    populations, receipts, review_ids = {}, set(), {}
    for run, review in reviews:
        team = str(review['team'])
        if team not in teams or team in populations or not set(review['expected']).issubset(teams[team]):
            raise ValueError('Independent Board membership review has inconsistent club identities')
        populations[team] = review['expected']
        review_ids[team] = run
        receipts.update(review['sources'])
    if populations.keys() != teams.keys():
        raise ValueError(f'Current Board workload and population reviews still required for {sorted(teams.keys()-populations.keys())}')
    from sync_v3.staging_board_history import inputs_still_current
    receipts.update(projection[1]['sources'])
    if not inputs_still_current(cur, receipts):
        raise ReviewedGenerationAdvanced('Reviewed Board workload evidence has advanced since reconciliation')
    binding.update(reviewed_board_mlb_ids=populations, board_review_runs=review_ids,
                   canonical_checkpoint=projection[0], canonical_started_at=projection[2].isoformat()+'+00:00')
    binding['current_source_ids'] = sorted(set(binding['current_source_ids']) | receipts)


def product_clock(binding):
    from sync_v3.staging_publication_target import ARCHIVE_TARGET
    if runtime_binding.PRODUCTION or 'product_day' in binding and TARGET != ARCHIVE_TARGET:
        return nullcontext()
    from freezegun import freeze_time
    return freeze_time(f"{binding.get('product_day', binding['availability_reference'])} 12:00:00", real_asyncio=True)


def source_receipt(worker_password, digest, user='sync_v3_worker'):
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.product_reads import _league

    with closing(open_generation_source(worker_password, user)) as source:
        with source, source.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            league = _league(cur, None, digest, compare_latest=True)
            review = league['selection_review']
            offseason = review['status'] == 'season_complete_withholding'
            if review['latest_inventory_digest'] != digest:
                raise ReviewedGenerationAdvanced('A newer inventory supersedes the reviewed generation')
            if review['status'] not in ('core_comparison_complete', 'season_complete_withholding'):
                raise ValueError(f'Generation review withheld: {review["status"]} {review["reason_codes"]}')
            if (league['generation'] != digest or league['status'] != 'candidate_preview'
                    or not league['data_through'] or league['selection_revision'] is not None):
                raise ValueError('Unexpected private generation scope')
            cur.execute("""SELECT manifest->'next_slate'->'games',manifest->'transaction_source',manifest->'clubs'
                           FROM candidate.generations WHERE digest=%s""", (digest,))
            official_slate, transactions, clubs = cur.fetchone()
            completed = {club['team'] for club in clubs if club['readiness'] == 'season_complete'}
            extra = {}
            if offseason or os.environ.get('STAGING_CYCLE_STARTED_AT'):
                if offseason and official_slate != []:
                    raise ValueError('Offseason candidate lacks a qualified empty availability-date slate')
                extra, official_slate = current_edition_inputs(cur, date.fromisoformat(league['data_through']),
                                                            league['availability_reference'], offseason=offseason)
                reviewed_board_populations(cur, worker_password, user, digest, extra)
                if not offseason:
                    from sync_v3.intelligence_history import DOMAINS
                    from sync_v3.product_reads import tonight_rotation
                    cur.execute("""SELECT h.mlb_id,h.facts#>'{windows,7,pressure}' FROM candidate.generation_inputs i
                                JOIN candidate.workload_history h ON h.id=i.snapshot
                                WHERE i.generation=%s AND h.subject='team' AND h.methodology=%s""",
                                (digest, DOMAINS['rotation'][1]))
                    rotations = {str(team): tonight_rotation(pressure) for team, pressure in cur}
                    if set(rotations) != {str(team) for team in MLB_TEAM_IDS}:
                        raise ValueError('Competitive rotation coverage lacks a club')
                    extra['reviewed_tonight_rotation'] = rotations
            if not offseason:
                from sync_v3.generation import generation_date_decision
                represented = date.fromisoformat(league['data_through'])
                reference = date.fromisoformat(league['availability_reference'])
                dates = generation_date_decision(cur, represented, reference)
                if dates['status'] != 'aligned' or dates['availability_reference'] != reference.isoformat():
                    raise ValueError('Competitive candidate lacks its independently supported product date')
            if not offseason and (not transactions or transactions['outcome'] != 'received' or transactions['reason']
                    or not transactions.get('revisions_digest')):
                raise ValueError('Archived product edition lacks a qualified transaction receipt')
            teams = {}
            for row in league['teams']:
                team = row['team_id']
                citation = league['citations'][team]['readiness']
                state = row['team_state']
                qualified = (state['available'] is False and state['outcome'] == 'season_complete'
                             and state['public_state'] is None) if team in completed else state['available'] is True
                if team in teams or not citation or not qualified or state['data_through'] != league['data_through']:
                    raise ValueError(f'Unqualified or duplicate Team State for {team}')
                teams[team] = dict(state=state, readiness=citation)
            if teams.keys() != set(MLB_TEAM_IDS):
                raise ValueError('Private generation lacks the complete League')
            cur.execute("""WITH sources AS (
                SELECT source AS id FROM candidate.generation_sources WHERE generation=%s UNION
                SELECT s.source_id FROM candidate.generation_inputs i
                JOIN candidate.workload_history_sources s ON s.snapshot=i.snapshot WHERE i.generation=%s
                UNION SELECT unnest(%s::bigint[]))
                SELECT count(*), min(f.received_at), max(f.received_at) FROM sources JOIN candidate.fetches f USING(id)""",
                        (digest, digest, extra.get('current_source_ids', [])))
            count, first, last = cur.fetchone()
            if not count or not first or not last:
                raise ValueError('Missing retained generation provenance')
    return dict(contract='private_source_generation_v1', generation=digest, data_through=league['data_through'], **extra,
                availability_reference=league['availability_reference'], teams={str(k):v for k,v in teams.items()},
                official_slate=official_slate, source_count=count, first_source_at=first.isoformat(), last_source_at=last.isoformat())


def observe_product_relations(access):
    """Collect relation names and operations in the private product database without recording values."""
    import re
    from sqlalchemy import event
    from utils.db import db

    catalog = set(db.session.execute(text(
        "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p','v','m')"
    )).scalars())
    pattern = re.compile(r'\b(from|join|insert\s+into|update|delete\s+from)\s+(?:"?public"?\.)?"?([a-z0-9_]+)', re.I)
    def record_relations(conn, cursor, statement, parameters, context, executemany):
        for operation, table in pattern.findall(statement.lower()):
            if table in catalog:
                action = 'read' if operation in ('from', 'join') else operation.split()[0]
                access.setdefault(action, set()).add(table)
    event.listen(db.engine, 'before_cursor_execute', record_relations)
    db.session.remove()


def private_app(password, *, user=OWNER, read_only=False):
    from config import TestingConfig, config

    from sync_v3.staging_reader import READER
    from sync_v3.staging_publisher import PUBLISHER
    from sync_v3.staging_projector import PROJECTOR
    if user not in (OWNER, READER, PUBLISHER, PROJECTOR):
        raise ValueError('Unexpected private product database login')
    if os.environ.get('AUTO_SYNC', '').lower() != 'false' or 'app' in sys.modules:
        raise ValueError('Private product rehearsal requires a fresh process with the scheduler disabled')

    class PrivateProduct(TestingConfig):
        TESTING = not runtime_binding.PRODUCTION
        TRUSTED_PUBLIC_SERVING_ENABLED = True

        @staticmethod
        def init_app(app):
            if runtime_binding.PRODUCTION:
                app.config['SQLALCHEMY_DATABASE_URI'] = runtime_binding.production_url(user, password, read_only=read_only)
                return
            options = {'sslmode':'require', 'connect_timeout':'10'}
            if read_only:
                options['options'] = '-c default_transaction_read_only=on'
            app.config['SQLALCHEMY_DATABASE_URI'] = URL.create(
                'postgresql+psycopg2', username=user, password=password, host=HOST, port=5432,
                database=TARGET, query=options)

    config['private_product_staging'] = PrivateProduct
    os.environ['APP_ENV'] = 'private_product_staging'
    from app import app
    app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
    if not app.extensions.get('baseballos_trusted_public_serving_installed'):
        raise ValueError('Trusted public routes were not installed')
    return app


def report_state_differences(snapshot, binding, worker_password, user='sync_v3_worker'):
    from services.team_state_vnext_production_proof import load_durable_proof
    from sync_v3.intelligence_history import DOMAINS

    frozen = snapshot.payload['trusted_team_boards']['frozen_team_state_by_team_id']
    mismatches = [team for team, member in binding['teams'].items() if frozen[team]['value'] != member['state']]
    print(json.dumps(dict(private_state_mismatches=mismatches)), flush=True)
    inputs = load_durable_proof(snapshot.id).proof['snapshot_team_state_generation_inputs']
    with closing(open_generation_source(worker_password, user)) as source:
        with source, source.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            for team in mismatches:
                cur.execute("""SELECT h.facts FROM candidate.generation_inputs i
                    JOIN candidate.workload_history h ON h.id=i.snapshot
                    WHERE i.generation=%s AND h.mlb_id=%s AND h.methodology=%s""",
                            (binding['generation'], int(team), DOMAINS['readiness'][1]))
                facts, = cur.fetchone()
                observed = inputs[team]['arm_reads'].get('records', [])
                candidate = {k: (v.get('read') or {}).get('availability', {}).get('availability_status')
                             for k,v in facts['arms'].items()}
                product = {arm['mlb_id']: arm['public_read']['key'] for arm in observed}
                print(json.dumps(dict(private_team_difference=dict(
                    team=team, candidate_state=binding['teams'][team]['state']['public_state'],
                    product_state=frozen[team]['value']['public_state'],
                    candidate_arms=candidate, product_arms=product, rule=facts.get('rule')))), flush=True)


def verify_board_rosters(snapshot, binding):
    if 'product_day' not in binding:
        return
    from models.pitcher import Pitcher
    from utils.db import db

    clubs = snapshot.payload['trusted_team_boards']['by_team_id']
    expected = binding['active_pitcher_mlb_ids']
    if clubs.keys() != expected.keys():
        raise ValueError('Private Board club inventory differs from the dated official roster')
    ids = {pitcher for club in clubs.values() for pitcher in club['default_pitcher_ids']}
    directory = dict(db.session.query(Pitcher.id, Pitcher.mlb_id).filter(Pitcher.id.in_(ids)).all())
    for team, club in clubs.items():
        observed = {directory.get(pid) for pid in club['default_pitcher_ids']}
        unsupported = observed - set(expected[team])
        if unsupported:
            raise ValueError(f'Private Board for {team} includes arms outside the official active roster: {unsupported}')
        if observed != set(binding['reviewed_board_mlb_ids'][team]) or len(observed) != len(club['default_pitcher_ids']):
            raise ValueError(f'Private Board population for {team} differs from the qualified official workload')


def legacy_predecessor_receipt(snapshot, day):
    """Pin immutable product data and its committed proof before a first-writer transition."""
    from hashlib import sha256
    from models.tonight_publication import TonightPublication
    from services.team_state_vnext_production_proof import observe_committed_publication_proof
    from services.tonight_read_model import CONTRACT, content_sha256

    if snapshot.source == runtime_binding.SNAPSHOT_SOURCE or 'v3_source_generation' in (snapshot.payload or {}):
        raise ValueError('The requested predecessor is already a v3 edition')
    observed = observe_committed_publication_proof(snapshot)
    if observed['status'] != 'proof_valid':
        raise ValueError('Legacy predecessor lacks its committed Team State proof')
    tonight = TonightPublication.query.filter_by(dashboard_snapshot_id=snapshot.id, sync_run_id=snapshot.sync_run_id,
                                                reference_date=day, contract=CONTRACT).one()
    if tonight.content_sha256 != content_sha256(tonight.payload):
        raise ValueError('Legacy Tonight predecessor hash differs')
    return dict(snapshot=snapshot.id, sync=snapshot.sync_run_id, product_day=str(day), source=snapshot.source,
                data_through=str(snapshot.data_through), availability=str(snapshot.availability_reference_date),
                payload_sha256=sha256(json.dumps(snapshot.payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                tonight_sha256=tonight.content_sha256, team_state_proof=observed['receipt_digest'])


def rehearse_legacy_edition(password, digest, day):
    """Use the ordinary publisher on the rolled-back private competitive timeline."""
    from datetime import datetime, timezone
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from scripts.verify_public_sync_edition import verify
    from services import dashboard_snapshot, sync_metadata
    from services.tonight_read_model import generate_tonight_v1_for_snapshot
    from sync_v3.staging_publication_target import ARCHIVE_TARGET
    from sync_v3.staging_publisher import PUBLISHER
    from utils.db import db

    if TARGET != ARCHIVE_TARGET:
        raise ValueError('Legacy handoff rehearsal requires the isolated archive timeline')
    app = private_app(password, user=PUBLISHER)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context(), product_clock(dict(availability_reference=str(day))):
        with db.session.begin():
            if tuple(db.session.execute(text('SELECT current_database(),current_user')).one()) != (ARCHIVE_TARGET, PUBLISHER):
                raise ValueError('Unexpected private legacy publisher target')
            db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
            latest = DashboardSnapshot.query.filter_by(snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                      is_published=True).one_or_none()
            if latest is None:
                previous = DashboardSnapshot.query.filter_by(snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                              source=runtime_binding.SNAPSHOT_SOURCE).order_by(DashboardSnapshot.id.desc()).first()
                if (not previous or previous.payload['v3_source_generation']['generation'] != digest
                        or db.session.get(SyncRun, previous.sync_run_id).stage != 'private_rolled_back'):
                    raise ValueError('The competitive predecessor has not completed its verified rollback')
                run = SyncRun(job_name=sync_metadata.JOB_DAILY_SYNC, source='legacy_handoff_rehearsal', status='success',
                              stage='acquired', started_at=now, completed_at=now, latest_workload_date=previous.data_through)
                db.session.add(run)
                db.session.flush()
                latest = dashboard_snapshot.build_bullpen_dashboard_snapshot(
                    sync_run_id=run.id, source='daily_sync', publish=False, commit=False, raise_errors=True)
                dashboard_snapshot.publish_dashboard_snapshot(latest, commit=False)
                if not latest.is_published:
                    raise ValueError('Legacy product rehearsal did not publish')
                generate_tonight_v1_for_snapshot(latest, reference_date=day, commit=False)
            elif db.session.get(SyncRun, latest.sync_run_id).source != 'legacy_handoff_rehearsal':
                raise ValueError('The archive has another active publisher')
            ident = latest.id
        latest = db.session.get(DashboardSnapshot, ident)
        dashboard_snapshot.run_post_commit_snapshot_publication(latest)
        pin = legacy_predecessor_receipt(latest, day)
        with http_session(app) as (client, base):
            served = verify(client, base, latest.id, latest.sync_run_id)
        return dict(database=TARGET, database_edition=pin, public_edition_sha256=served['public_edition_sha256'])


def require_legacy_predecessor(snapshot, pin):
    import re

    if not isinstance(pin, dict) or not snapshot or pin.get('database') != TARGET:
        raise ValueError('First handoff requires the pinned predecessor database and edition')
    actual = legacy_predecessor_receipt(snapshot, date.fromisoformat(pin['database_edition']['product_day']))
    if actual != pin['database_edition'] or not re.fullmatch('[0-9a-f]{64}', pin.get('public_edition_sha256') or ''):
        raise ValueError('Legacy predecessor differs from the first-handoff receipt')


def publish(binding, worker_password, *, user=OWNER, source_user='sync_v3_worker'):
    from datetime import datetime, timezone
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from scripts.rehearse_selected_publication import verify_frozen_states
    from scripts.verify_selected_delivery import verify_tonight_edition
    from services import dashboard_snapshot, sync_metadata
    from services.tonight_read_model import generate_tonight_v1_for_snapshot
    from services.team_state_vnext_production_proof import TeamStatePublicationIneligible, observe_committed_publication_proof
    from utils.db import db

    with db.session.begin():
        if tuple(db.session.execute(text('SELECT current_database(),current_user')).one()) != (TARGET, user):
            raise ValueError('Unexpected private publisher target')
        db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        prior = DashboardSnapshot.query.filter_by(snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                  is_published=True).one_or_none()
        if runtime_binding.PRODUCTION:
            supplied_root = os.environ.get('STAGING_LEGACY_PREDECESSOR')
            if not supplied_root or not prior:
                raise ValueError('Production requires the selected handoff predecessor')
            if prior.source == runtime_binding.SNAPSHOT_SOURCE and prior.payload.get('v3_handoff_root') != json.loads(supplied_root):
                raise ValueError('Production replay belongs to another handoff')
        if prior and (prior.payload.get('v3_source_generation') or {}).get('generation') == binding['generation']:
            if prior.payload['v3_source_generation'] == binding:
                verify_frozen_states(prior, binding)
                verify_board_rosters(prior, binding)
                return prior.id, False
            if 'product_day' not in binding:
                raise ValueError('Generation replay has a different source receipt')
        legacy_pin = None
        supplied = os.environ.get('STAGING_LEGACY_PREDECESSOR')
        if prior and prior.source != runtime_binding.SNAPSHOT_SOURCE:
            legacy_pin = json.loads(supplied) if supplied else None
            require_legacy_predecessor(prior, legacy_pin)
            if (binding['data_through'] < legacy_pin['database_edition']['data_through']
                    or binding['availability_reference'] < legacy_pin['database_edition']['availability']):
                raise ValueError('First handoff would regress the current product dates')
        elif supplied and runtime_binding.PRODUCTION and prior:
            if (prior.payload or {}).get('v3_handoff_root') != json.loads(supplied):
                raise ValueError('Production predecessor belongs to another handoff')
        elif supplied or runtime_binding.PRODUCTION:
            raise ValueError('The pinned legacy predecessor is no longer selected')
        # The binding retains provider acquisition times. Operational status orders real
        # writer executions by completion, including when an older archived source is replayed.
        clock = text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")
        invoked = os.environ.get('STAGING_CYCLE_STARTED_AT')
        now = db.session.execute(clock).scalar_one()
        started = datetime.fromisoformat(invoked).astimezone(timezone.utc).replace(tzinfo=None) if invoked else now
        run = SyncRun(job_name=sync_metadata.JOB_DAILY_SYNC, source=runtime_binding.RUN_SOURCE, status='success', stage='acquired',
                      started_at=started, completed_at=now,
                      latest_workload_date=date.fromisoformat(binding['data_through']), records_processed=binding['source_count'])
        db.session.add(run)
        db.session.flush()
        snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id, source=runtime_binding.SNAPSHOT_SOURCE, publish=False, commit=False, raise_errors=True)
        verify_board_rosters(snapshot, binding)
        prior_runs = [] if not prior else [r.id for r in SyncRun.query.filter_by(
            published_dashboard_snapshot_id=prior.id).order_by(SyncRun.id)]
        snapshot.payload = dict(snapshot.payload, v3_source_generation=binding, v3_predecessor=prior.id if prior else None,
                                v3_predecessor_runs=prior_runs)
        if runtime_binding.PRODUCTION:
            snapshot.payload = dict(snapshot.payload, v3_handoff_root=json.loads(supplied))
        if legacy_pin is not None:
            snapshot.payload = dict(snapshot.payload, v3_legacy_predecessor=legacy_pin)
        try:
            dashboard_snapshot.publish_dashboard_snapshot(snapshot, commit=False)
        except TeamStatePublicationIneligible as exc:
            evidence = exc.publication_evidence
            print(json.dumps(dict(private_proof_withheld=dict(
                workload=evidence['candidate_data_through'], dates=evidence['reference_dates'],
                clubs=evidence['affected_team_ids'], first_club=evidence['teams'][0]))), flush=True)
            raise
        if not snapshot.is_published:
            raise ValueError(f'Private trusted publication withheld: {snapshot.error_message}')
        try:
            verify_frozen_states(snapshot, binding)
        except ValueError:
            report_state_differences(snapshot, binding, worker_password, source_user)
            raise
        if observe_committed_publication_proof(snapshot)['status'] != 'proof_valid':
            raise ValueError('Incomplete private Team State proof')
        day = binding.get('product_day', binding['availability_reference'])
        edition, _ = generate_tonight_v1_for_snapshot(snapshot, reference_date=date.fromisoformat(day), commit=False)
        verify_tonight_edition(edition.payload, (snapshot.id, run.id), binding, day)
        verify_slate(edition.payload['games'], binding)
        run.completed_at = db.session.execute(clock).scalar_one()
        return snapshot.id, True


def exercise(password, worker_password, digest, *, inventory=False, user=OWNER, source_user='sync_v3_worker'):
    import re
    from datetime import datetime, timezone
    from models.dashboard_snapshot import DashboardSnapshot
    from services import dashboard_snapshot
    from utils.db import db

    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('An explicit immutable generation is required')
    started = perf_counter()
    binding = source_receipt(worker_password, digest, source_user)
    verified_source_seconds = perf_counter()-started
    app = private_app(password, user=user)
    access = {}
    if inventory:
        with app.app_context():
            observe_product_relations(access)
    with app.app_context(), product_clock(binding):
        # clock_gettime measures real time during the archived product clock.
        before_pointer = clock_gettime(CLOCK_MONOTONIC)
        snapshot_id, promoted = publish(binding, worker_password, user=user, source_user=source_user)
        after_pointer = clock_gettime(CLOCK_MONOTONIC)
        try:
            snapshot = db.session.get(DashboardSnapshot, snapshot_id)
            run_id = snapshot.sync_run_id
            dashboard_snapshot.run_post_commit_snapshot_publication(snapshot)
            db.session.remove()
            before_http = clock_gettime(CLOCK_MONOTONIC)
            counts = verify_http(app, binding, snapshot_id, run_id)
            after_http = clock_gettime(CLOCK_MONOTONIC)
        except Exception:
            db.session.rollback()
            if promoted:
                restore_predecessor(digest, snapshot_id, user=user)
            raise
    with app.app_context():
        target_bytes = db.session.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    verified_at = datetime.now(timezone.utc)
    latest = datetime.fromisoformat(binding['last_source_at'])
    return dict(generation=digest, snapshot=snapshot_id, sync_run=run_id, promoted=promoted,
                access={k:sorted(v) for k,v in access.items()} if inventory else None,
                target_database_bytes=target_bytes, modeled_product_date=binding.get('product_day', binding['availability_reference']), verified_at=verified_at.isoformat(), last_source_at=latest.isoformat(),
                latest_retained_source_to_private_delivery_seconds=(verified_at-latest).total_seconds(),
                canonical_start_to_delivery_seconds=(verified_at-datetime.fromisoformat(binding['canonical_started_at'])).total_seconds()
                if 'canonical_started_at' in binding else None,
                verified_source_seconds=verified_source_seconds, publication_seconds=after_pointer-before_pointer,
                postcommit_seconds=before_http-after_pointer, http_verification_seconds=after_http-before_http,
                seconds=perf_counter()-started, **counts)


def verify_http(app, binding, snapshot_id, run_id):
    from scripts.verify_selected_delivery import verify_tonight_edition

    from models.share_artifact import ShareArtifact
    from utils.db import db

    day = binding.get('product_day', binding['availability_reference'])
    rows = ShareArtifact.query.filter_by(artifact_type='team_state', source_snapshot_id=snapshot_id,
                                         lifecycle_state='published').all()
    shares = {row.team_id: row.public_id for row in rows}
    eligible = {team for team, member in binding['teams'].items() if member['state']['available']}
    if len(rows) != len(eligible) or set(map(str, shares)) != eligible or len(set(shares.values())) != len(eligible):
        raise ValueError('Incomplete private Team State share inventory')
    db.session.remove()
    paths = [f'/api/share-artifacts/{identifier}' for identifier in shares.values()]
    league, tonight, sync_status, *responses = http_delivery(app, ['/api/bullpen/sync/status', *paths])
    if (league.status_code, tonight.status_code) != (200, 200):
        raise ValueError(f'Private product status codes: League {league.status_code}, Tonight {tonight.status_code}')
    sync_status.raise_for_status()
    metadata = sync_status.json()
    latest = metadata.get('last_successful_sync_run') or {}
    # Sync status reports the canonical game log maximum. Pointer rollback preserves newer logs.
    canonical_date = db.session.execute(text('SELECT max(game_date) FROM game_logs')).scalar_one()
    if (metadata.get('metadata_source') != 'sync_runs' or str(canonical_date) != metadata['data']['latest_workload_date']
            or (latest.get('stage') != 'private_rolled_back' and str(canonical_date) != binding['data_through'])
            or not latest.get('id') or latest.get('source') != runtime_binding.RUN_SOURCE):
        raise ValueError('Private sync status lacks the archived acquisition identity or workload date')
    if latest['id'] != run_id and latest.get('stage') != 'private_rolled_back':
        raise ValueError('Private sync status cites a different active edition')
    data = league.json()
    authority = data['publication_authority']
    served = {str(row['team_id']):row['team_state'] for row in data['teams']}
    if ((authority['snapshot_id'], authority['sync_run_id']) != (snapshot_id, run_id)
            or len(data['teams']) != 30 or served != {k:v['state'] for k,v in binding['teams'].items()}):
        raise ValueError('Private League response differs from the immutable input generation')
    payload = tonight.json()
    verify_tonight_edition(payload, (snapshot_id, run_id), binding, day)
    verify_slate(payload['games'], binding)
    for (team, identifier), response in zip(shares.items(), responses):
        response.raise_for_status()
        view = response.json()['artifact']
        source = view['authority']
        if (view['lifecycle_state'] != 'published' or view['team']['team_id'] != team
                or view['public_id'] != identifier or view['product_date'] != binding['data_through']
                or (source['source_snapshot_id'], source['source_sync_run_id']) != (snapshot_id, run_id)
                or any(view['team_state'][key] != served[str(team)][key] for key in ('public_state', 'public_label'))):
            raise ValueError(f'Private share for club {team} differs from the published edition')
    return dict(league_clubs=len(served), tonight_games=len(payload['games']), share_artifacts=len(responses))


def verify_slate(cards, binding):
    expected = {game['game_pk']: (game['away'], game['home']) for game in binding['official_slate']}
    actual = {card['game_pk']: (card['away']['team_id'], card['home']['team_id']) for card in cards}
    if actual != expected or len(cards) != len(expected):
        raise ValueError('Private Tonight game identities differ from the retained official schedule')
    for card in cards:
        for side in ('home', 'away'):
            team = card[side]
            state = binding['teams'][str(team['team_id'])]['state']
            if 'reviewed_tonight_rotation' in binding:
                rotation = binding['reviewed_tonight_rotation'][str(team['team_id'])]
                keys = ('short_start_count', 'bullpen_innings', 'games_analyzed')
                observed = team.get('rotation')
                if ((rotation is None) != (observed is None)
                        or rotation and any(rotation[key] != observed.get(key) for key in keys)):
                    raise ValueError(f"Tonight rotation for {team['team_id']} differs from qualified final lines: "
                                     f"{rotation} / {observed}")
            if any(team['team_state'][key] != state[key] for key in ('public_state', 'public_label')):
                raise ValueError('Private Tonight club differs from the frozen Team State')


def http_delivery(app, extra_paths=()):
    return http_paths(app, ['/api/bullpen/team-states', '/api/bullpen/intelligence/tonight?contract=tonight_v1',
                            *extra_paths])


@contextmanager
def http_session(app):
    from threading import Thread
    from requests import Session
    from werkzeug.serving import make_server

    with make_server('127.0.0.1', 0, app) as server, Session() as client:
        client.trust_env = False
        base = f'http://127.0.0.1:{server.server_port}'
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield client, base
        finally:
            server.shutdown()
            thread.join()


def http_paths(app, paths):
    with http_session(app) as (client, base):
        return tuple(client.get(base + path, timeout=45, allow_redirects=False) for path in paths)


def restore_predecessor(digest, snapshot_id, *, user=OWNER, in_transaction=False):
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from scripts.rehearse_selected_publication import verify_frozen_states
    from utils.db import db

    with nullcontext() if in_transaction else db.session.begin():
        if tuple(db.session.execute(text('SELECT current_database(),current_user')).one()) != (TARGET, user):
            raise ValueError('Unexpected private rollback target')
        db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        current = db.session.get(DashboardSnapshot, snapshot_id)
        if (not current or current.source != runtime_binding.SNAPSHOT_SOURCE
                or current.payload['v3_source_generation']['generation'] != digest):
            raise ValueError('Private rollback receipt differs')
        prev_id = current.payload['v3_predecessor']
        selected = DashboardSnapshot.query.filter_by(snapshot_type=current.snapshot_type, is_published=True).one_or_none()
        run = db.session.get(SyncRun, current.sync_run_id)
        prior = db.session.get(DashboardSnapshot, prev_id) if prev_id else None
        legacy = current.payload.get('v3_legacy_predecessor')
        if legacy:
            require_legacy_predecessor(prior, legacy)
        elif prior:
            verify_frozen_states(prior, prior.payload['v3_source_generation'])
        if (selected.id if selected else None) == prev_id and run.stage == 'private_rolled_back':
            return prev_id
        if selected is None or selected.id != snapshot_id:
            raise ValueError('Private publication advanced since the rollback request')
        previous_runs = set(current.payload['v3_predecessor_runs'])
        linked = SyncRun.query.filter_by(published_dashboard_snapshot_id=snapshot_id).all()
        if {row.id for row in linked} != previous_runs | {run.id}:
            raise ValueError('Private sync-run publication authority changed')
        current.is_published = False
        db.session.flush()
        if prior:
            prior.is_published = True
        for row in linked:
            row.published_dashboard_snapshot_id = prev_id if row.id in previous_runs else None
        run.stage = 'private_rolled_back'
        run.publication_outcome = dict(generation=digest, restored_snapshot=prev_id,
                                       rolled_back_at=db.session.execute(text('SELECT clock_timestamp()')).scalar_one().isoformat())
        db.session.flush()
        return prev_id


def restore_handoff_root(snapshot_id, digest, pin, user):
    """Restore the first legacy selector and all intervening links in one transaction."""
    from models.dashboard_snapshot import DashboardSnapshot
    from utils.db import db

    with db.session.begin():
        db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        tip = db.session.get(DashboardSnapshot, snapshot_id)
        if (not tip or tip.payload.get('v3_handoff_root') != pin or
                tip.payload['v3_source_generation']['generation'] != digest):
            raise ValueError('Rollback tip differs from the approved handoff')
        selected = DashboardSnapshot.query.filter_by(snapshot_type=tip.snapshot_type, is_published=True).one()
        root_id = pin['database_edition']['snapshot']
        if selected.id == root_id:
            require_legacy_predecessor(selected, pin)
            return root_id
        if selected.id != tip.id:
            raise ValueError('Production selector advanced before rollback')
        visited = set()
        while tip.id != root_id:
            if tip.id in visited or tip.payload.get('v3_handoff_root') != pin:
                raise ValueError('Broken production publication predecessor chain')
            visited.add(tip.id)
            previous = restore_predecessor(tip.payload['v3_source_generation']['generation'], tip.id,
                                           user=user, in_transaction=True)
            if previous is None:
                raise ValueError('Production predecessor disappeared before the pinned edition')
            tip = db.session.get(DashboardSnapshot, previous)
        require_legacy_predecessor(tip, pin)
        return tip.id


def exercise_rollback(password, digest, snapshot_id, *, user=OWNER):
    from models.dashboard_snapshot import DashboardSnapshot
    from utils.db import db

    app = private_app(password, user=user)
    with app.app_context():
        pin = json.loads(os.environ['STAGING_LEGACY_PREDECESSOR']) if runtime_binding.PRODUCTION else None
        predecessor = (restore_handoff_root(snapshot_id, digest, pin, user) if pin else
                       restore_predecessor(digest, snapshot_id, user=user))
        if predecessor:
            previous = db.session.get(DashboardSnapshot, predecessor)
            legacy = pin or db.session.get(DashboardSnapshot, snapshot_id).payload.get('v3_legacy_predecessor')
            if legacy:
                from scripts.verify_public_sync_edition import verify
                day = legacy['database_edition']['product_day']
                with (nullcontext() if pin else product_clock(dict(availability_reference=day))), http_session(app) as (client, base):
                    counts = verify(client, base, predecessor, previous.sync_run_id)
                if counts['public_edition_sha256'] != legacy['public_edition_sha256']:
                    raise ValueError('Restored public edition differs from the archived legacy receipt')
            else:
                binding = previous.payload['v3_source_generation']
                with product_clock(binding):
                    counts = verify_http(app, binding, predecessor, previous.sync_run_id)
        else:
            league, tonight = http_delivery(app)
            if (league.status_code, tonight.status_code) != (200, 200):
                raise ValueError('Empty private selector did not return the expected product responses')
            listing, slate = league.json(), tonight.json()
            authority = listing.get('publication_authority') or {}
            if (listing.get('status') != 'snapshot_unavailable' or listing.get('withheld_team_count') != 30
                    or authority.get('snapshot_id') is not None or slate.get('games')
                    or ((slate.get('edition') or {}).get('publication') or {}).get('dashboard_snapshot_id') is not None):
                raise ValueError('The private API served a generation after rollback to an empty selector')
            counts = dict(withheld_clubs=30, tonight_games=0)
        return dict(rolled_back_snapshot=snapshot_id, restored_snapshot=predecessor, **counts)

def verify_product_surfaces(password, digest, *, user=OWNER, inventory=False):
    """Read the normal product endpoints against one published staging edition."""
    from urllib.parse import urlencode
    from models.dashboard_snapshot import DashboardSnapshot
    from models.pitcher import Pitcher
    from services.dashboard_snapshot import SNAPSHOT_TYPE_BULLPEN_DASHBOARD
    from utils.db import db

    app = private_app(password, user=user, read_only=inventory or user != OWNER)
    with app.app_context():
        access = {}
        if inventory:
            observe_product_relations(access)
        snapshot = DashboardSnapshot.query.filter_by(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                     is_published=True).one()
        binding = snapshot.payload['v3_source_generation']
        if snapshot.source != runtime_binding.SNAPSHOT_SOURCE or binding['generation'] != digest:
            raise ValueError('Unexpected private product selector')
        ident = snapshot.id, snapshot.sync_run_id
        through, day = binding['data_through'], binding['availability_reference']
        # Boston's archived Board, role sample and departure-independent club identity have retained evidence.
        team, abbr = 111, 'BOS'
        current = 'product_day' in binding
        game = next((row for row in binding['official_slate'] if team in (row['home'], row['away'])), None)
        paths = {
            'league': '/api/bullpen/league', 'stories': '/api/bullpen/stories', 'trust': '/api/bullpen/trust',
            'board': f'/api/bullpen/teams/{team}/board-v2/core', 'changes': f'/api/bullpen/teams/{team}/changes',
            'history': f'/api/bullpen/teams/{abbr}/history?season={through[:4]}',
            'search': '/api/search?q=Boston'}
        if game:
            paths['matchup'] = f"/api/bullpen/matchups/{game['game_pk']}"
        elif not current:
            raise ValueError('The archived edition lacks the expected Boston game')
        db.session.remove()
        with product_clock(binding):
            if inventory or user != OWNER:
                verify_http(app, binding, ident[0], ident[1])
            data = {}
            for key, response in zip(paths, http_paths(app, paths.values())):
                response.raise_for_status()
                data[key] = response.json()
            for key in ('league', 'stories', 'trust'):
                authority = data[key]['publication_authority']
                if (authority['snapshot_id'], authority['sync_run_id']) != ident or authority['data_through'] != through:
                    raise ValueError(f'Private {key} cites a different edition')
            core = data['board']
            identity = core['publication_identity']
            if ((identity['snapshot_id'], identity['sync_run_id']) != ident or identity['team_id'] != team
                    or identity['represented_date'] != through or identity['availability_reference_date'] != day
                    or core['team_state']['public_state'] != binding['teams'][str(team)]['state']['public_state']):
                raise ValueError('Private Team Board disagrees with the published edition')
            if current:
                if (core['team_state'] != binding['teams'][str(team)]['state']
                        or data['changes']['team']['team_id'] != team or data['history']['team']['team_id'] != team):
                    raise ValueError('Current offseason Board, History or Changes differ from the frozen club')
                details, = http_paths(app, [
                    f'/api/bullpen/teams/{team}/board-v2/details?' + urlencode({k:v for k,v in identity.items() if v is not None})])
                details.raise_for_status()
                if details.json()['publication_identity'] != identity:
                    raise ValueError('Current deferred Board cites a different publication')
                found = [r['id'] for group in data['search']['groups'] if group['entity_type'] == 'team' for r in group['results']]
                if team not in found:
                    raise ValueError('Current search lacks the canonical Boston team')
                boards = {str(team): core}
                other_teams = sorted(binding['reviewed_board_mlb_ids'].keys() - boards.keys())
                responses = http_paths(app, [f'/api/bullpen/teams/{club}/board-v2/core' for club in other_teams])
                for club, response in zip(other_teams, responses):
                    response.raise_for_status()
                    boards[club] = response.json()
                listed = {club:[a['pitcher_id'] for a in board['active_bullpen']['arms']] for club,board in boards.items()}
                pitchers = {pid for staff in listed.values() for pid in staff}
                directory = dict(db.session.query(Pitcher.id, Pitcher.mlb_id).filter(Pitcher.id.in_(pitchers)).all())
                for club, board in boards.items():
                    publication = board['publication_identity']
                    staff = [directory[pid] for pid in listed[club]]
                    if ((publication['snapshot_id'], publication['sync_run_id']) != ident
                            or publication['team_id'] != int(club) or publication['availability_reference_date'] != day
                            or sorted(staff) != binding['reviewed_board_mlb_ids'][club]):
                        raise ValueError(f'HTTP Board differs from the dated official review for {club}')
                checked = list(paths) + ['board_details', 'league_boards']
                if listed[str(team)]:
                    pid = listed[str(team)][0]
                    response, = http_paths(app, [f'/api/bullpen/fatigue/{pid}'])
                    response.raise_for_status()
                    if response.json()['pitcher']['mlb_id'] != directory[pid]:
                        raise ValueError('Current Pitcher Detail differs from the Board identity')
                    checked.append('pitcher')
                return dict(generation=digest, snapshot=ident[0], sync_run=ident[1], checked=checked,
                            product_day=binding['product_day'], team=team, verified_boards=len(boards),
                            board_mlb_ids=binding['reviewed_board_mlb_ids'][str(team)])
            arm = core['active_bullpen']['arms'][0]['pitcher_id']
            player = db.session.get(Pitcher, arm)
            if not player or player.team_id != team:
                raise ValueError('Private Team Board arm has no canonical club identity')
            mlb = player.mlb_id
            db.session.remove()
            details, pitcher = http_paths(app, [
                f'/api/bullpen/teams/{team}/board-v2/details?' + urlencode({k:v for k,v in identity.items() if v is not None}),
                f'/api/bullpen/fatigue/{arm}'])
            details.raise_for_status()
            pitcher.raise_for_status()
            if details.json()['publication_identity'] != identity or pitcher.json()['pitcher']['mlb_id'] != mlb:
                raise ValueError('Deferred Board or Pitcher Detail identity disagrees')
            matchup = data['matchup']['game']
            if (matchup['game_pk'], matchup['home']['team_id'], matchup['away']['team_id']) != (
                    game['game_pk'], game['home'], game['away']):
                raise ValueError('Matchup identity differs from the retained MLB slate')
            if data['changes']['team']['team_id'] != team:
                raise ValueError('Change feed cites a different club')
            history = data['history']
            row, = [row for row in history['rows'] if row['represented_date'] == through]
            from models.share_artifact import ShareArtifact
            expected_share = ShareArtifact.query.filter_by(
                team_id=team, source_snapshot_id=ident[0], source_sync_run_id=ident[1],
                artifact_type='team_state', lifecycle_state='published').one()
            if (history['team']['team_id'] != team or row['artifact']['public_id'] != expected_share.public_id
                    or row['team_state']['public_code'] != core['team_state']['public_state']):
                raise ValueError('Team History lacks the archived publication evidence')
            found = [r['id'] for group in data['search']['groups'] if group['entity_type'] == 'team' for r in group['results']]
            if team not in found or data['search']['represented_date'] != day:
                raise ValueError('Discovery Search lacks the represented Boston identity')
        return dict(generation=digest, snapshot=ident[0], sync_run=ident[1], checked=list(paths)+['board_details','pitcher'],
                    team=team, pitcher_public_id=arm, pitcher_mlb_id=mlb, game_pk=game['game_pk'],
                    history_artifact=row['artifact']['public_id'], change_state=data['changes']['state'],
                    read_relations=sorted(access.get('read', ())) if inventory else None)
