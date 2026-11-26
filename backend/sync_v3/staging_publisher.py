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


def check_scope(cur, database, *, installer=False, login=PUBLISHER, reads=READ, inserts=INSERT, updates=UPDATE):
    cur.execute('SELECT current_database(), session_user, current_user')
    expected = OWNER if installer else login
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
                   FROM pg_roles r WHERE rolname=%s""", (TARGET, login))
    if cur.fetchone() != (False,):
        raise ValueError('Private runtime login has unreviewed administration or routine access')
    cur.execute("""SELECT n.nspname,c.relname,
                   has_table_privilege(%s,c.oid,'SELECT'),has_any_column_privilege(%s,c.oid,'SELECT'),
                   has_any_column_privilege(%s,c.oid,'INSERT'),has_any_column_privilege(%s,c.oid,'UPDATE'),
                   has_table_privilege(%s,c.oid,'DELETE,TRUNCATE,REFERENCES,TRIGGER') OR
                   has_any_column_privilege(%s,c.oid,'REFERENCES')
                   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname !~ '^pg_'
                   AND n.nspname != 'information_schema' AND c.relkind IN ('r','p','v','f','m')""", (login,)*6)
    for schema, table, read, columns, insert, update, other in cur.fetchall():
        target = database == TARGET and schema == 'public'
        can_read = (database == DATABASE and schema == 'candidate' and login == PUBLISHER) or (target and table in reads)
        if (read, columns, insert, update, other) != (can_read, can_read, target and table in inserts,
                                                      target and table in updates, False):
            raise ValueError(f'Unexpected {login} access to {schema}.{table}')


def verify_source(connection):
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        check_scope(cur, DATABASE)
        cur.execute('SELECT digest FROM candidate.schema_installation WHERE singleton')
        if cur.fetchall() != [(schema_digest(schema_scripts()),)]:
            raise ValueError('Unexpected private candidate schema revision')


def install_target(owner_password, password, login, reads, inserts, updates, policy_prefix, *, insert_checks=None, update_columns=None, update_checks=None):
    role = sql.Identifier(login)
    with closing(_connect(OWNER, owner_password)) as owner, owner, owner.cursor() as cur:
        cur.execute('SELECT current_database(), current_user')
        if cur.fetchone() != (TARGET, OWNER):
            raise ValueError('Unexpected private target installer')
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (login,))
        cur.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (login,))
        if not cur.fetchone():
            verifier = encrypt_password(password, login, owner, 'scram-sha-256')
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT PASSWORD %s').format(role), (verifier,))
        cur.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(TARGET), role))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        for tables, action, predicate in ((reads,'SELECT','USING (true)'), (inserts,'INSERT','WITH CHECK (true)'),
                                         (updates,'UPDATE','USING (true) WITH CHECK (true)')):
            for table in sorted(tables):
                relation = sql.Identifier('public', table)
                privilege = sql.SQL(action)
                if action == 'UPDATE' and table in (update_columns or {}):
                    cols = sql.SQL(', ').join(map(sql.Identifier, sorted(update_columns[table])))
                    privilege = sql.SQL('UPDATE ({})').format(cols)
                cur.execute(sql.SQL('GRANT {} ON {} TO {}').format(privilege, relation, role))
                policy = policy_prefix + '_' + action.lower()
                conditions = {'INSERT': insert_checks or {}, 'UPDATE': update_checks or {}}
                condition = conditions.get(action, {}).get(table, predicate)
                cur.execute(sql.SQL('DROP POLICY IF EXISTS {} ON {}').format(sql.Identifier(policy), relation))
                cur.execute(sql.SQL('CREATE POLICY {} ON {} FOR {} TO {} {}')
                            .format(sql.Identifier(policy), relation, sql.SQL(action), role, sql.SQL(condition)))
                if action == 'INSERT':
                    cur.execute("""SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                   WHERE c.oid=(SELECT pg_get_serial_sequence(%s,'id')::regclass
                                     FROM pg_attribute WHERE attrelid=%s::regclass AND attname='id' AND NOT attisdropped)""", ('public.'+table, 'public.'+table))
                    sequence = cur.fetchone()
                    if sequence:
                        cur.execute(sql.SQL('GRANT USAGE ON SEQUENCE {} TO {}').format(sql.Identifier(*sequence), role))
        check_scope(cur, TARGET, installer=True, login=login, reads=reads, inserts=inserts, updates=updates)


def install(owner_password, password):
    install_target(owner_password, password, PUBLISHER, READ, INSERT, UPDATE, 'private_publisher')
    role = sql.Identifier(PUBLISHER)
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
