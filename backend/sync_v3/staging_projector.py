"""Restricted canonical writer for the private product's offseason Board recovery."""
from contextlib import closing
import json

from sync_v3.staging_publication_target import TARGET
from sync_v3.staging_publisher import check_scope, install_target
from sync_v3.staging_reader import _connect

PROJECTOR = 'baseballos_v3_staging_projector'
# Final-game and roster trigger guards consult the two version tables inside PostgreSQL.
READ = {'slate_games', 'compatibility_write_events', 'final_game_versions', 'roster_membership_intervals', 'pitchers', 'game_logs', 'postgame_processed_games', 'fatigue_scores', 'scheduled_games', 'sync_runs', 'sync_failures'}
INSERT = {'scheduled_games', 'slate_games', 'pitchers', 'game_logs', 'postgame_processed_games', 'fatigue_scores', 'sync_runs'}
UPDATE = {'scheduled_games', 'slate_games', 'pitchers', 'game_logs', 'postgame_processed_games'}
ROSTER_EVIDENCE = {'source_subjects', 'source_observations', 'source_payload_artifacts', 'source_fetch_attempts'}
READ |= ROSTER_EVIDENCE | {'roster_status_snapshots', 'completed_game_contexts'}
INSERT |= ROSTER_EVIDENCE | {'roster_status_snapshots', 'completed_game_contexts'}
UPDATE.add('roster_status_snapshots')
CHECKPOINT = """WITH CHECK (source='sync_v3_staging' AND status='success'
    AND published_dashboard_snapshot_id IS NULL AND
    ((stage='reviewed' AND job_name ~ '^sync_v3_board_review_[0-9]+$')
      OR (stage='checkpoint' AND job_name ~ '^sync_v3_board_progress_[0-9]+$')
      OR (stage='verified_roster_observations' AND job_name='sync_v3_roster_reconciliation')
      OR (stage='canonical_ready' AND job_name='sync_v3_canonical_cycle')))"""


def verify(cur):
    check_scope(cur, TARGET, login=PROJECTOR, reads=READ, inserts=INSERT, updates=UPDATE)
    cur.execute("""SELECT relrowsecurity FROM pg_class WHERE oid='public.sync_runs'::regclass""")
    if cur.fetchone() != (True,):
        raise ValueError('Private projectors require row-level protection on sync runs')
    cur.execute("""SELECT polname FROM pg_policy WHERE polrelid='public.sync_runs'::regclass
        AND polpermissive AND polcmd IN ('*','a') AND
        (0=ANY(polroles) OR (SELECT oid FROM pg_roles WHERE rolname=current_user)=ANY(polroles))""")
    if cur.fetchall() != [('private_projector_insert',)]:
        raise ValueError('Unexpected insert policy on private Board review records')


def install(owner_password, password):
    install_target(owner_password, password, PROJECTOR, READ, INSERT, UPDATE, 'private_projector',
                   insert_checks={'sync_runs': CHECKPOINT})
    with closing(_connect(PROJECTOR, password)) as target, target, target.cursor() as cur:
        verify(cur)


def current_checkpoint(source, digest, day):
    from models.sync_run import SyncRun
    from sync_v3.staging_board_history import inputs_still_current
    from utils.db import db

    with db.session.begin():
        row = SyncRun.query.filter_by(job_name='sync_v3_canonical_cycle', stage='canonical_ready',
                                      source='sync_v3_staging', status='success').order_by(SyncRun.id.desc()).first()
        if not row:
            return None
        proof = row.publication_outcome
        if proof['generation'] != digest or proof['day'] != str(day):
            return None
        review = row.id
    with source, source.cursor() as cur:
        return review if inputs_still_current(cur, proof['sources']) else None


def record_checkpoint(digest, day, through, sources, started):
    from sqlalchemy import text
    from models.sync_run import SyncRun
    from utils.db import db

    with db.session.begin():
        now = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        record = SyncRun(job_name='sync_v3_canonical_cycle', stage='canonical_ready', source='sync_v3_staging',
                         status='success', latest_workload_date=through, records_processed=len(sources),
                         started_at=started, completed_at=now,
                         publication_outcome=dict(generation=digest, day=str(day), sources=sorted(sources)))
        db.session.add(record)
        db.session.flush()
        return record.id


def recover_boards(password, source_password, digest, *, competition_day=None, competitive=False):
    from services.mlb_api import MLBApiClient
    from sync_v3.current_worker import verify_target
    from sync_v3.render_staging import connect
    from sync_v3.staging_board_history import recover_next
    from sync_v3.staging_product_delivery import private_app

    with closing(_connect(PROJECTOR, password)) as target, target, target.cursor() as cur:
        verify(cur)
    client = MLBApiClient()
    with private_app(password, user=PROJECTOR).app_context(), closing(client.session):
        with closing(connect('sync_v3_worker', source_password)) as source:
            verify_target(source)
            checkpoint = current_checkpoint(source, digest, competition_day) if competition_day else None
            if competition_day and not checkpoint:
                from datetime import datetime, timezone
                started = datetime.now(timezone.utc).replace(tzinfo=None)
                from sync_v3.staging_postseason import project_offseason_competition
                from utils.db import db
                from datetime import date
                from sync_v3.staging_publication_target import project_roster_views, project_archived_fatigue, project_workload_window
                with source, source.cursor() as cur:
                    cur.execute("SELECT represented, manifest->>'availability_reference' FROM candidate.generations "
                                "WHERE digest=%s", (digest,))
                    through, availability = cur.fetchone()
                if competitive:
                    window = project_workload_window(source_password, workload_day=through, scoped=True)
                    if window['reason']:
                        if window['missing_games'] and window['recovered']:
                            return dict(phase='canonical_pending', generation=digest, workload=window)
                        raise ValueError(f"Competitive workload coverage is incomplete: {window['reason']}")
                    sources = set(window['receipts'].values())
                else:
                    competition = project_offseason_competition(source, client, competition_day, scoped=True)
                    sources = set(competition.pop('source_receipts'))
                    print(json.dumps(dict(private_scoped_competition=competition)), flush=True)
                db.session.remove()
                dates = through, date.fromisoformat(availability)
                roster = project_roster_views(source_password, edition_dates=dates, initialized=True)
                roster['assignments'] = project_archived_fatigue(edition_dates=dates)
                sources.update(roster.pop('source_receipts'))
                print(json.dumps(dict(private_scoped_roster=roster)), flush=True)
                checkpoint = record_checkpoint(digest, competition_day, through, sources, started)
                return dict(phase='canonical_ready', checkpoint=checkpoint, product_writer=PROJECTOR,
                            source_count=len(sources), generation=digest)
            result = recover_next(source, client, digest)
    return dict(result, canonical_checkpoint=checkpoint, product_writer=PROJECTOR)


def product_schedule_predecessor(cur, day, observation):
    """Resolve the exact retained predecessor from the private target's dated schedule stamp."""
    from datetime import timezone
    from psycopg2.extras import Json
    from sqlalchemy import text
    from sync_v3 import evidence
    from sync_v3.discovery import calendar_requests
    from utils.db import db

    stamps = db.session.execute(text('SELECT DISTINCT last_synced FROM slate_games WHERE game_date_et=:day'),
                                dict(day=day)).scalars().all()
    predecessor = None
    if len(stamps) == 1 and stamps[0] < observation.retrieved_at.astimezone(timezone.utc).replace(tzinfo=None):
        request = calendar_requests(day)[0]
        cur.execute("""SELECT id FROM candidate.fetches f WHERE endpoint=%s AND parameters=%s
            AND received_at=%s AND outcome='received' AND reason IS NULL AND NOT EXISTS
            (SELECT 1 FROM candidate.refusals r WHERE r.source_id=f.id)""",
                    (request.endpoint, Json(request.params()), stamps[0].replace(tzinfo=timezone.utc)))
        ids = [item[0] for item in cur]
        if len(ids) == 1:
            predecessor = evidence.replay(cur, ids[0])
    return predecessor


def project_dated_schedules(password, source_password, digest, *, archive=False):
    """Apply the two generation-bound slates together and preserve the current product on archive replay."""
    from datetime import date
    from sqlalchemy import text
    from scripts.rehearse_selected_schedule import pinned_schedule, reconcile_schedule, retained_makeups
    from sync_v3 import evidence
    from sync_v3.current_worker import verify_target
    from sync_v3.render_staging import connect
    from sync_v3.staging_product_delivery import private_app
    from utils.db import db

    with closing(_connect(PROJECTOR, password)) as target, target, target.cursor() as cur:
        verify(cur)
    with closing(connect('sync_v3_worker', source_password)) as source, private_app(password, user=PROJECTOR).app_context():
        verify_target(source)
        with source, source.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute("SELECT represented,manifest->>'availability_reference' FROM candidate.generations WHERE digest=%s", (digest,))
            through, availability = cur.fetchone()
            dates = (through, date.fromisoformat(availability))
            slates = {day: pinned_schedule(cur, digest, day) for day in dates}
            makeups = retained_makeups({day: observation for day, (_, observation) in slates.items()})
            with db.session.begin() as transaction:
                db.session.execute(text('LOCK TABLE scheduled_games,slate_games IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
                for day, (_, observation) in slates.items():
                    predecessor = product_schedule_predecessor(cur, day, observation)
                    reconcile_schedule(day, observation, private_staging=True, makeups=makeups, predecessor=predecessor)
                    reconcile_schedule(day, observation, private_staging=True, makeups=makeups, verify_only=True)
                from services.game_finality import classify_status
                from services.club_competition_status import COMPETITIVE_GAME_TYPES
                from sync_v3.workload import _game_workload
                from sync_v3.staging_publication_target import project_final_appearances
                receipt, observed = slates[through]
                finals = []
                boxes = []
                for entry in observed.body['dates']:
                    for game in entry['games']:
                        if game['gameType'] not in COMPETITIVE_GAME_TYPES or not classify_status(game['status']).final_status:
                            continue
                        qualified, reason = _game_workload(cur, game, through, receipt['source'], resolve_sessions=True)
                        if not qualified:
                            raise ValueError(f"Unqualified pitching workload for game {game['gamePk']}: {reason}")
                        facts, (box, *_) = qualified
                        finals.append((game, evidence.replay(cur, box).body, facts, {}))
                        boxes.append(box)
                appearances = project_final_appearances(finals, through, include_context=False, in_transaction=True)
                if archive:
                    transaction.rollback()
        window = None
        if archive:
            from sync_v3.staging_publication_target import project_workload_window
            window = project_workload_window(source_password, workload_day=through, scoped=True, verify_only=True)
            if window['reason']:
                raise ValueError(f"Archived pitching window is incomplete: {window['reason']}")
    return dict(generation=digest, workload_window=window, boxes=boxes, verified_appearances=appearances['verified'], source_ids=[receipt['source'] for receipt, _ in slates.values()],
                dates=[str(day) for day in dates], archived_replay=archive)
