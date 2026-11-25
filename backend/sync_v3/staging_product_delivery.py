"""Publish a reviewed generation only inside the private product rehearsal database."""
from contextlib import closing
from datetime import date
import json
import os
import sys
from time import CLOCK_MONOTONIC, clock_gettime, perf_counter

from sqlalchemy import URL, text

from sync_v3.render_staging import HOST, OWNER, PLAYED_DAY, connect
from sync_v3.staging_publication_target import TARGET


def source_receipt(worker_password, digest):
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.current_worker import verify_target
    from sync_v3.product_reads import _league

    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            league = _league(cur, None, digest, compare_latest=True)
            review = league['selection_review']
            if review['status'] != 'core_comparison_complete' or review['latest_inventory_digest'] != digest:
                raise ValueError(f'Generation review withheld: {review["status"]} {review["reason_codes"]}')
            if (league['generation'] != digest or league['status'] != 'candidate_preview'
                    or league['data_through'] != str(PLAYED_DAY) or league['selection_revision'] is not None):
                raise ValueError('Unexpected private generation scope')
            cur.execute("""SELECT manifest->'next_slate'->'games',manifest->'transaction_source'
                           FROM candidate.generations WHERE digest=%s""", (digest,))
            official_slate, transactions = cur.fetchone()
            if (not transactions or transactions['outcome'] != 'received' or transactions['reason']
                    or not transactions.get('revisions_digest')):
                raise ValueError('Archived product edition lacks a qualified transaction receipt')
            teams = {}
            for row in league['teams']:
                team = row['team_id']
                citation = league['citations'][team]['readiness']
                state = row['team_state']
                if team in teams or not citation or not state['available'] or state['data_through'] != str(PLAYED_DAY):
                    raise ValueError(f'Unqualified or duplicate Team State for {team}')
                teams[team] = dict(state=state, readiness=citation)
            if teams.keys() != set(MLB_TEAM_IDS):
                raise ValueError('Private generation lacks the complete League')
            cur.execute("""WITH sources AS (
                SELECT source AS id FROM candidate.generation_sources WHERE generation=%s UNION
                SELECT s.source_id FROM candidate.generation_inputs i
                JOIN candidate.workload_history_sources s ON s.snapshot=i.snapshot WHERE i.generation=%s)
                SELECT count(*), min(f.received_at), max(f.received_at) FROM sources JOIN candidate.fetches f USING(id)""",
                        (digest, digest))
            count, first, last = cur.fetchone()
            if not count or not first or not last:
                raise ValueError('Missing retained generation provenance')
    return dict(contract='private_source_generation_v1', generation=digest, data_through=str(PLAYED_DAY),
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

    if os.environ.get('AUTO_SYNC', '').lower() != 'false' or 'app' in sys.modules:
        raise ValueError('Private product rehearsal requires a fresh process with the scheduler disabled')

    class PrivateProduct(TestingConfig):
        TRUSTED_PUBLIC_SERVING_ENABLED = True

        @staticmethod
        def init_app(app):
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


def report_state_differences(snapshot, binding, worker_password):
    from services.team_state_vnext_production_proof import load_durable_proof
    from sync_v3.intelligence_history import DOMAINS
    from sync_v3.current_worker import verify_target

    frozen = snapshot.payload['trusted_team_boards']['frozen_team_state_by_team_id']
    mismatches = [team for team, member in binding['teams'].items() if frozen[team]['value'] != member['state']]
    print(json.dumps(dict(private_state_mismatches=mismatches)), flush=True)
    inputs = load_durable_proof(snapshot.id).proof['snapshot_team_state_generation_inputs']
    with closing(connect('sync_v3_worker', worker_password)) as source:
        verify_target(source)
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


def publish(binding, worker_password):
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
        if tuple(db.session.execute(text('SELECT current_database(),current_user')).one()) != (TARGET, OWNER):
            raise ValueError('Unexpected private publisher target')
        db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        prior = DashboardSnapshot.query.filter_by(snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                  is_published=True).one_or_none()
        if prior and (prior.payload.get('v3_source_generation') or {}).get('generation') == binding['generation']:
            if prior.payload['v3_source_generation'] != binding:
                raise ValueError('Generation replay has a different source receipt')
            verify_frozen_states(prior, binding)
            return prior.id, False
        if prior and prior.source != 'v3_private_publication':
            raise ValueError('Private predecessor belongs to another publisher')
        def utc(value):
            return datetime.fromisoformat(value).astimezone(timezone.utc).replace(tzinfo=None)
        run = SyncRun(job_name=sync_metadata.JOB_DAILY_SYNC, source='sync_v3_staging', status='success', stage='acquired',
                      started_at=utc(binding['first_source_at']), completed_at=utc(binding['last_source_at']),
                      latest_workload_date=date.fromisoformat(binding['data_through']), records_processed=binding['source_count'])
        db.session.add(run)
        db.session.flush()
        snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id, source='v3_private_publication', publish=False, commit=False, raise_errors=True)
        prior_runs = [] if not prior else [r.id for r in SyncRun.query.filter_by(
            published_dashboard_snapshot_id=prior.id).order_by(SyncRun.id)]
        snapshot.payload = dict(snapshot.payload, v3_source_generation=binding, v3_predecessor=prior.id if prior else None,
                                v3_predecessor_runs=prior_runs)
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
            report_state_differences(snapshot, binding, worker_password)
            raise
        if observe_committed_publication_proof(snapshot)['status'] != 'proof_valid':
            raise ValueError('Incomplete private Team State proof')
        edition, _ = generate_tonight_v1_for_snapshot(snapshot, commit=False)
        verify_tonight_edition(edition.payload, (snapshot.id, run.id), binding, binding['availability_reference'])
        verify_slate(edition.payload['games'], binding)
        return snapshot.id, True


def exercise(password, worker_password, digest, *, inventory=False):
    import re
    from datetime import datetime, timezone
    from freezegun import freeze_time
    from models.dashboard_snapshot import DashboardSnapshot
    from services import dashboard_snapshot
    from utils.db import db

    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('An explicit immutable generation is required')
    started = perf_counter()
    binding = source_receipt(worker_password, digest)
    verified_source_seconds = perf_counter()-started
    app = private_app(password)
    day = binding['availability_reference']
    access = {}
    if inventory:
        with app.app_context():
            observe_product_relations(access)
    with app.app_context(), freeze_time(f'{day} 12:00:00', real_asyncio=True):
        # clock_gettime measures real time during the archived product clock.
        before_pointer = clock_gettime(CLOCK_MONOTONIC)
        snapshot_id, promoted = publish(binding, worker_password)
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
                restore_predecessor(digest, snapshot_id)
            raise
    with app.app_context():
        target_bytes = db.session.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
    verified_at = datetime.now(timezone.utc)
    latest = datetime.fromisoformat(binding['last_source_at'])
    return dict(generation=digest, snapshot=snapshot_id, sync_run=run_id, promoted=promoted,
                access={k:sorted(v) for k,v in access.items()} if inventory else None,
                target_database_bytes=target_bytes, modeled_product_date=day, verified_at=verified_at.isoformat(), last_source_at=latest.isoformat(),
                latest_retained_source_to_private_delivery_seconds=(verified_at-latest).total_seconds(),
                verified_source_seconds=verified_source_seconds, publication_seconds=after_pointer-before_pointer,
                postcommit_seconds=before_http-after_pointer, http_verification_seconds=after_http-before_http,
                seconds=perf_counter()-started, **counts)


def verify_http(app, binding, snapshot_id, run_id):
    from scripts.verify_selected_delivery import verify_tonight_edition

    from models.share_artifact import ShareArtifact
    from utils.db import db

    day = binding['availability_reference']
    rows = ShareArtifact.query.filter_by(artifact_type='team_state', source_snapshot_id=snapshot_id,
                                         lifecycle_state='published').all()
    shares = {row.team_id: row.public_id for row in rows}
    if len(rows) != 30 or set(map(str, shares)) != binding['teams'].keys() or len(set(shares.values())) != 30:
        raise ValueError('Incomplete private Team State share inventory')
    db.session.remove()
    paths = [f'/api/share-artifacts/{identifier}' for identifier in shares.values()]
    league, tonight, sync_status, *responses = http_delivery(app, ['/api/bullpen/sync/status', *paths])
    if (league.status_code, tonight.status_code) != (200, 200):
        raise ValueError(f'Private product status codes: League {league.status_code}, Tonight {tonight.status_code}')
    sync_status.raise_for_status()
    metadata = sync_status.json()
    latest = metadata.get('last_successful_sync_run') or {}
    if (metadata.get('metadata_source') != 'sync_runs' or metadata['data']['latest_workload_date'] != binding['data_through']
            or not latest.get('id') or latest.get('source') != 'sync_v3_staging'):
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
            if any(team['team_state'][key] != state[key] for key in ('public_state', 'public_label')):
                raise ValueError('Private Tonight club differs from the frozen Team State')


def http_delivery(app, extra_paths=()):
    return http_paths(app, ['/api/bullpen/team-states', '/api/bullpen/intelligence/tonight?contract=tonight_v1',
                            *extra_paths])


def http_paths(app, paths):
    from threading import Thread
    from requests import Session
    from werkzeug.serving import make_server

    with make_server('127.0.0.1', 0, app) as server, Session() as client:
        client.trust_env = False
        base = f'http://127.0.0.1:{server.server_port}'
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            return tuple(client.get(base + path, timeout=45, allow_redirects=False) for path in paths)
        finally:
            server.shutdown()
            thread.join()


def restore_predecessor(digest, snapshot_id):
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from scripts.rehearse_selected_publication import verify_frozen_states
    from utils.db import db

    with db.session.begin():
        if tuple(db.session.execute(text('SELECT current_database(),current_user')).one()) != (TARGET, OWNER):
            raise ValueError('Unexpected private rollback target')
        db.session.execute(text('LOCK TABLE dashboard_snapshots, sync_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        current = db.session.get(DashboardSnapshot, snapshot_id)
        if (not current or current.source != 'v3_private_publication'
                or current.payload['v3_source_generation']['generation'] != digest):
            raise ValueError('Private rollback receipt differs')
        prev_id = current.payload['v3_predecessor']
        selected = DashboardSnapshot.query.filter_by(snapshot_type=current.snapshot_type, is_published=True).one_or_none()
        run = db.session.get(SyncRun, current.sync_run_id)
        if (selected.id if selected else None) == prev_id and run.stage == 'private_rolled_back':
            return prev_id
        if selected is None or selected.id != snapshot_id:
            raise ValueError('Private publication advanced since the rollback request')
        prior = db.session.get(DashboardSnapshot, prev_id) if prev_id else None
        if prior:
            verify_frozen_states(prior, prior.payload['v3_source_generation'])
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


def exercise_rollback(password, digest, snapshot_id):
    from freezegun import freeze_time
    from models.dashboard_snapshot import DashboardSnapshot
    from utils.db import db

    app = private_app(password)
    with app.app_context():
        predecessor = restore_predecessor(digest, snapshot_id)
        if predecessor:
            previous = db.session.get(DashboardSnapshot, predecessor)
            binding = previous.payload['v3_source_generation']
            with freeze_time(f"{binding['availability_reference']} 12:00:00", real_asyncio=True):
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
    from freezegun import freeze_time
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
        if snapshot.source != 'v3_private_publication' or binding['generation'] != digest:
            raise ValueError('Unexpected private product selector')
        ident = snapshot.id, snapshot.sync_run_id
        through, day = binding['data_through'], binding['availability_reference']
        # Boston's archived Board, role sample and departure-independent club identity have retained evidence.
        team, abbr = 111, 'BOS'
        game = next(row for row in binding['official_slate'] if team in (row['home'], row['away']))
        paths = {
            'league': '/api/bullpen/league', 'stories': '/api/bullpen/stories', 'trust': '/api/bullpen/trust',
            'board': f'/api/bullpen/teams/{team}/board-v2/core', 'changes': f'/api/bullpen/teams/{team}/changes',
            'history': f'/api/bullpen/teams/{abbr}/history?season={through[:4]}',
            'search': '/api/search?q=Boston', 'matchup': f"/api/bullpen/matchups/{game['game_pk']}"}
        db.session.remove()
        with freeze_time(f'{day} 12:00:00', real_asyncio=True):
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
