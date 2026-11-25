"""Publish a reviewed generation only inside the private product rehearsal database."""
from contextlib import closing
from datetime import date
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


def private_app(password):
    from config import TestingConfig, config

    if os.environ.get('AUTO_SYNC', '').lower() != 'false' or 'app' in sys.modules:
        raise ValueError('Private product rehearsal requires a fresh process with the scheduler disabled')

    class PrivateProduct(TestingConfig):
        TRUSTED_PUBLIC_SERVING_ENABLED = True

        @staticmethod
        def init_app(app):
            app.config['SQLALCHEMY_DATABASE_URI'] = URL.create(
                'postgresql+psycopg2', username=OWNER, password=password, host=HOST, port=5432,
                database=TARGET, query={'sslmode':'require','connect_timeout':'10'})

    config['private_product_staging'] = PrivateProduct
    os.environ['APP_ENV'] = 'private_product_staging'
    from app import app
    app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
    if not app.extensions.get('baseballos_trusted_public_serving_installed'):
        raise ValueError('Trusted public routes were not installed')
    return app


def publish(binding):
    from datetime import datetime, timezone
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from scripts.rehearse_selected_publication import verify_frozen_states
    from services import dashboard_snapshot
    from services.team_state_vnext_production_proof import observe_committed_publication_proof
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
        run = SyncRun(job_name='sync_v3_private_edition', source='sync_v3_staging', status='success', stage='acquired',
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
        dashboard_snapshot.publish_dashboard_snapshot(snapshot, commit=False)
        if not snapshot.is_published:
            raise ValueError(f'Private trusted publication withheld: {snapshot.error_message}')
        verify_frozen_states(snapshot, binding)
        if observe_committed_publication_proof(snapshot)['status'] != 'proof_valid':
            raise ValueError('Incomplete private Team State proof')
        return snapshot.id, True


def exercise(password, worker_password, digest):
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
    with app.app_context(), freeze_time(f'{day} 12:00:00', real_asyncio=True):
        # clock_gettime measures real time during the archived product clock.
        before_pointer = clock_gettime(CLOCK_MONOTONIC)
        snapshot_id, promoted = publish(binding)
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
    verified_at = datetime.now(timezone.utc)
    latest = datetime.fromisoformat(binding['last_source_at'])
    return dict(generation=digest, snapshot=snapshot_id, sync_run=run_id, promoted=promoted,
                modeled_product_date=day, verified_at=verified_at.isoformat(), last_source_at=latest.isoformat(),
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
    league, tonight, *responses = http_delivery(app, paths)
    if (league.status_code, tonight.status_code) != (200, 200):
        raise ValueError(f'Private product status codes: League {league.status_code}, Tonight {tonight.status_code}')
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
    from threading import Thread
    from requests import Session
    from werkzeug.serving import make_server

    with make_server('127.0.0.1', 0, app) as server, Session() as client:
        client.trust_env = False
        base = f'http://127.0.0.1:{server.server_port}'
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            return tuple(client.get(base + path, timeout=45, allow_redirects=False) for path in (
                '/api/bullpen/team-states', '/api/bullpen/intelligence/tonight?contract=tonight_v1', *extra_paths))
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
