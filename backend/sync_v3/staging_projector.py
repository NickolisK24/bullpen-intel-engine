"""Restricted canonical writer for the private product's offseason Board recovery."""
from contextlib import closing

from sync_v3.staging_publication_target import TARGET
from sync_v3.staging_publisher import check_scope, install_target
from sync_v3.staging_reader import _connect

PROJECTOR = 'baseballos_v3_staging_projector'
READ = {'pitchers', 'game_logs', 'postgame_processed_games', 'fatigue_scores', 'scheduled_games', 'sync_runs', 'sync_failures'}
INSERT = {'pitchers', 'game_logs', 'postgame_processed_games', 'fatigue_scores', 'sync_runs'}
UPDATE = {'pitchers', 'game_logs', 'postgame_processed_games'}
CHECKPOINT = """WITH CHECK (source='sync_v3_staging' AND status='success'
    AND published_dashboard_snapshot_id IS NULL AND
    ((stage='reviewed' AND job_name ~ '^sync_v3_board_review_[0-9]+$')
      OR (stage='checkpoint' AND job_name ~ '^sync_v3_board_progress_[0-9]+$')))"""


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


def recover_boards(password, source_password, digest):
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
            result = recover_next(source, client, digest)
    return dict(result, product_writer=PROJECTOR)
