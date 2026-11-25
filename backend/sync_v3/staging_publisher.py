"""Provision the private publisher from the observed publication and rollback access."""
from contextlib import closing

from psycopg2 import sql
from psycopg2.extensions import encrypt_password

from sync_v3.render_staging import DATABASE, OWNER, connect
from sync_v3.replay import schema_digest, schema_scripts
from sync_v3.staging_reader import _connect
from sync_v3.staging_publication_target import TARGET

PUBLISHER = 'baseballos_v3_staging_publisher'
READ = set('dashboard_snapshots fatigue_scores game_logs pitchers play_by_play_processed_games '
           'player_transaction_sync_windows postgame_processed_games roster_status_snapshots scheduled_games '
           'share_artifact_assets share_artifact_evidence share_artifact_generation_audits share_artifact_relations '
           'share_artifacts slate_games sync_failures sync_runs team_game_pitching_splits '
           'team_state_publication_proofs tonight_publications'.split())
INSERT = set('dashboard_snapshots share_artifact_evidence share_artifact_generation_audits share_artifacts '
             'sync_runs team_state_publication_proofs tonight_publications'.split())
UPDATE = {'dashboard_snapshots', 'share_artifacts', 'sync_runs'}


def check_scope(cur, database, *, installer=False):
    cur.execute('SELECT current_database(), session_user, current_user')
    expected = OWNER if installer else PUBLISHER
    if cur.fetchone() != (database, expected, expected):
        raise ValueError('Unexpected private publication database or effective login')
    cur.execute("""SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
                   OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid)
                   OR has_database_privilege(r.oid,current_database(),'CREATE')
                   OR (current_database()=%s AND has_database_privilege(r.oid,current_database(),'TEMP'))
                   OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname !~ '^pg_' AND
                              has_schema_privilege(r.oid,n.oid,'CREATE'))
                   OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                              WHERE p.prosecdef AND n.nspname !~ '^pg_' AND n.nspname != 'information_schema'
                              AND has_schema_privilege(r.oid,n.oid,'USAGE') AND has_function_privilege(r.oid,p.oid,'EXECUTE'))
                   FROM pg_roles r WHERE rolname=%s""", (TARGET, PUBLISHER))
    if cur.fetchone() != (False,):
        raise ValueError('Private publisher has unreviewed administration or routine access')
    cur.execute("""SELECT n.nspname,c.relname,
                   has_table_privilege(%s,c.oid,'SELECT'),has_any_column_privilege(%s,c.oid,'SELECT'),
                   has_any_column_privilege(%s,c.oid,'INSERT'),has_any_column_privilege(%s,c.oid,'UPDATE'),
                   has_table_privilege(%s,c.oid,'DELETE,TRUNCATE,REFERENCES,TRIGGER') OR
                   has_any_column_privilege(%s,c.oid,'REFERENCES')
                   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_'
                   AND n.nspname != 'information_schema' AND c.relkind IN ('r','p','v','f','m')""", (PUBLISHER,)*6)
    for schema, table, read, columns, insert, update, other in cur.fetchall():
        target = database == TARGET and schema == 'public'
        can_read = (database == DATABASE and schema == 'candidate') or (target and table in READ)
        if (read, columns, insert, update, other) != (can_read, can_read, target and table in INSERT,
                                                      target and table in UPDATE, False):
            raise ValueError(f'Unexpected publisher access to {schema}.{table}')


def verify_source(connection):
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        check_scope(cur, DATABASE)
        cur.execute('SELECT digest FROM candidate.schema_installation WHERE singleton')
        if cur.fetchall() != [(schema_digest(schema_scripts()),)]:
            raise ValueError('Unexpected private candidate schema revision')


def install(owner_password, password):
    role = sql.Identifier(PUBLISHER)
    with closing(_connect(OWNER, owner_password)) as owner, owner, owner.cursor() as cur:
        cur.execute('SELECT current_database(), current_user')
        if cur.fetchone() != (TARGET, OWNER):
            raise ValueError('Unexpected private target installer')
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('private_product_publisher'))")
        cur.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (PUBLISHER,))
        if not cur.fetchone():
            verifier = encrypt_password(password, PUBLISHER, owner, 'scram-sha-256')
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT PASSWORD %s').format(role), (verifier,))
        cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(TARGET), role))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        for tables, action, predicate in ((READ,'SELECT','USING (true)'), (INSERT,'INSERT','WITH CHECK (true)'),
                                         (UPDATE,'UPDATE','USING (true) WITH CHECK (true)')):
            for table in sorted(tables):
                relation = sql.Identifier('public', table)
                cur.execute(sql.SQL('GRANT {} ON {} TO {}').format(sql.SQL(action), relation, role))
                policy = 'private_publisher_' + action.lower()
                cur.execute(sql.SQL('DROP POLICY IF EXISTS {} ON {}').format(sql.Identifier(policy), relation))
                cur.execute(sql.SQL('CREATE POLICY {} ON {} FOR {} TO {} {}')
                            .format(sql.Identifier(policy), relation, sql.SQL(action), role, sql.SQL(predicate)))
                if action == 'INSERT':
                    cur.execute("""SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                   WHERE c.oid=pg_get_serial_sequence(%s,'id')::regclass""", ('public.'+table,))
                    sequence = cur.fetchone()
                    if sequence:
                        cur.execute(sql.SQL('GRANT USAGE ON SEQUENCE {} TO {}').format(sql.Identifier(*sequence), role))
        check_scope(cur, TARGET, installer=True)
    with closing(connect(OWNER, owner_password)) as owner, owner, owner.cursor() as cur:
        cur.execute('SELECT current_database(), current_user')
        if cur.fetchone() != (DATABASE, OWNER):
            raise ValueError('Unexpected private candidate installer')
        cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(DATABASE), role))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA candidate TO {}').format(role))
        cur.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA candidate TO {}').format(role))
        check_scope(cur, DATABASE, installer=True)
    with closing(connect(PUBLISHER, password)) as source:
        verify_source(source)
    with closing(_connect(PUBLISHER, password)) as target, target, target.cursor() as cur:
        check_scope(cur, TARGET)
