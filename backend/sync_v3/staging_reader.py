"""Provision and verify the API login on the isolated Render product database."""
from contextlib import closing

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import encrypt_password

from sync_v3.render_staging import HOST, OWNER
from sync_v3.staging_publication_target import TARGET


READER = 'baseballos_v3_staging_product_reader'
# Relations read by the normal private HTTP routes in hosted run 1795634882.
PRODUCT_RELATIONS = frozenset({
    'dashboard_snapshots', 'fatigue_scores', 'game_ingestion_work_items', 'game_logs',
    'game_pitch_events', 'pitchers', 'play_by_play_processed_games', 'player_transaction_sync_windows',
    'player_transactions', 'postgame_processed_games', 'scheduled_games', 'share_artifact_assets',
    'share_artifact_evidence', 'share_artifact_relations', 'share_artifacts', 'slate_games',
    'sync_runs', 'team_game_pitching_splits', 'tonight_publications',
})


def _connect(user, password):
    from sync_v3 import runtime_binding
    if runtime_binding.PRODUCTION:
        return runtime_binding.connect_runtime(user, password)
    return psycopg2.connect(host=HOST, port=5432, dbname=TARGET, user=user, password=password,
                            connect_timeout=10, sslmode='require', application_name='baseballos_staging_reader_admission')


def install(owner_password, reader_password, tables):
    if not tables:
        raise ValueError('A reviewed product relation inventory is required')
    with closing(_connect(OWNER, owner_password)) as owner, owner, owner.cursor() as cur:
        cur.execute('SELECT current_database(), current_user')
        if cur.fetchone() != (TARGET, OWNER):
            raise ValueError('Unexpected private product installer identity')
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('private_product_reader'))")
        cur.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (READER,))
        if not cur.fetchone():
            verifier = encrypt_password(reader_password, READER, owner, 'scram-sha-256')
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT PASSWORD %s').format(sql.Identifier(READER)), (verifier,))
        cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(TARGET), sql.Identifier(READER)))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(READER)))
        cur.execute("""SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace
                       AND relkind IN ('r','p','v','m') AND relname=ANY(%s)""", (sorted(tables),))
        relations = dict(cur.fetchall())
        if relations.keys() != set(tables):
            raise ValueError('Private product schema differs from reviewed relation inventory')
        for name, has_rls in relations.items():
            relation = sql.Identifier('public', name)
            cur.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(relation, sql.Identifier(READER)))
            if has_rls:
                cur.execute("""SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename=%s
                               AND policyname='private_product_read'""", (name,))
                if not cur.fetchone():
                    cur.execute(sql.SQL('CREATE POLICY private_product_read ON {} FOR SELECT TO {} USING (true)')
                                .format(relation, sql.Identifier(READER)))
        cur.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET default_transaction_read_only=on')
                    .format(sql.Identifier(READER), sql.Identifier(TARGET)))
        _verify_grants(cur, tables)
    with closing(_connect(READER, reader_password)) as reader:
        verify(reader, tables)


def _verify_grants(cur, tables):
    cur.execute("""SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
                   OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                   OR has_database_privilege(r.oid,current_database(),'CREATE,TEMP')
                   OR has_schema_privilege(r.oid,'public','CREATE') FROM pg_roles r WHERE rolname=%s""", (READER,))
    if cur.fetchone() != (False,):
        raise ValueError('The private API login has administrative or writable schema privileges')
    cur.execute("""SELECT relname,has_table_privilege(%s,oid,'SELECT'),has_any_column_privilege(%s,oid,'SELECT'),
                   has_table_privilege(%s,oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
                   OR has_any_column_privilege(%s,oid,'INSERT,UPDATE,REFERENCES')
                   FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p','v','m')""",
                (READER, READER, READER, READER))
    rows = cur.fetchall()
    allowed = set(tables)
    if ({name for name, read, _, _ in rows if read} != allowed
            or any(write or columns != read for _, read, columns, write in rows)):
        raise ValueError('The API grants differ from the reviewed read-only product scope')
    cur.execute("""SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                   WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND p.prosecdef
                   AND has_schema_privilege(%s,n.oid,'USAGE') AND has_function_privilege(%s,p.oid,'EXECUTE'))""",
                (READER, READER))
    if cur.fetchone()[0]:
        raise ValueError('Unexpected security-definer routine accessible to the private API login')


def verify(connection, tables):
    with connection, connection.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, current_setting('transaction_read_only')")
        if cur.fetchone() != (TARGET, READER, 'on'):
            raise ValueError('Unexpected private API identity or transaction mode')
        _verify_grants(cur, tables)


def serve_edition(password, digest):
    from sync_v3.staging_product_delivery import verify_product_surfaces

    with closing(_connect(READER, password)) as reader:
        verify(reader, PRODUCT_RELATIONS)
    result = verify_product_surfaces(password, digest, user=READER)
    return dict(result, database_role=READER, readable_tables=len(PRODUCT_RELATIONS), writable_tables=0)
