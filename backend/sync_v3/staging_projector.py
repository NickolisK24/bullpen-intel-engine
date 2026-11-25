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
READ |= ROSTER_EVIDENCE | {'roster_status_snapshots'}
INSERT |= ROSTER_EVIDENCE | {'roster_status_snapshots'}
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


def recover_boards(password, source_password, digest, *, competition_day=None):
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
                competition = project_offseason_competition(source, client, competition_day, scoped=True)
                db.session.remove()
                sources = set(competition.pop('source_receipts'))
                print(json.dumps(dict(private_scoped_competition=competition)), flush=True)
                from datetime import date
                from sync_v3.staging_publication_target import project_roster_views, project_archived_fatigue
                with source, source.cursor() as cur:
                    cur.execute("SELECT represented, manifest->>'availability_reference' FROM candidate.generations "
                                "WHERE digest=%s", (digest,))
                    through, availability = cur.fetchone()
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
