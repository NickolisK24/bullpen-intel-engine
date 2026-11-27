"""Transaction-bound production provisioning and handoff operations; no implicit deployment."""

import argparse
import json
import os
from contextlib import closing
from pathlib import Path
import re

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json

from sync_v3 import runtime_binding as b
from sync_v3.production import LOCK
from sync_v3.replay import schema_scripts, schema_digest

API = 'baseballos_product_api'
LEGACY = 'baseballos_legacy_sync'
EXCLUDED = (
    'users',
    'user_followed_teams',
    'audience_subscribers',
    'editorial_post_history',
    'traffic_internal_visitors',
    'traffic_page_views',
    'traffic_share_actions',
    'prospects',
)
PREVIEW = Path(__file__).resolve().parents[2] / 'docs/sync-v3/preview-service-role-fence.sql'


def governed_relations(cur):
    from scripts.database_migrations import target_head

    cur.execute('SELECT version_num FROM public.alembic_version')
    if cur.fetchall() != [(target_head(),)]:
        raise ValueError('Unexpected product migration head')
    cur.execute(
        "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')"
    )
    actual = {name for name, in cur.fetchall()}
    governed_names = set(re.findall(r"\('([a-z_]+)'\)", PREVIEW.read_text().split('), targets AS')[0]))
    if actual != governed_names | set(EXCLUDED):
        raise ValueError('Product relation inventory differs from the reviewed handoff')
    return governed_names


def prepare(cur, revision):
    from sync_v3 import staging_projector as projector, staging_publisher as publisher

    if not re.fullmatch('[0-9a-f]{40}', revision or ''):
        raise ValueError('Exact tested revision required')
    governed_relations(cur)
    for role in (b.WORKER, b.PROJECTOR, b.PUBLISHER, API, LEGACY, 'sync_v3_reviewer'):
        cur.execute(
            sql.SQL(
                'CREATE ROLE {} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS'
            ).format(sql.Identifier(role))
        )
    cur.execute('CREATE SCHEMA candidate')
    cur.execute('CREATE SCHEMA sync_v3_control')
    cur.execute(
        'REVOKE ALL ON SCHEMA candidate, sync_v3_control FROM PUBLIC, anon, authenticated, service_role'
    )
    cur.execute('GRANT USAGE ON SCHEMA candidate TO sync_v3_worker,sync_v3_reviewer,baseballos_v3_publisher')
    scripts = schema_scripts()
    for _, script in scripts:
        cur.execute(script.decode())
    cur.execute('INSERT INTO candidate.schema_installation VALUES (true,%s)', (schema_digest(scripts),))
    # Supabase object default grants are separate from schema USAGE. Clear any inherited defaults on these new objects.
    for kind in ('TABLES', 'SEQUENCES', 'FUNCTIONS'):
        cur.execute(
            f'REVOKE ALL ON ALL {kind} IN SCHEMA candidate FROM PUBLIC, anon, authenticated, service_role'
        )
    cur.execute('GRANT SELECT ON ALL TABLES IN SCHEMA candidate TO baseballos_v3_publisher')
    cur.execute(
        """CREATE TABLE sync_v3_control.authority (
        singleton boolean PRIMARY KEY CHECK (singleton), mode text NOT NULL CHECK(mode IN ('legacy','v3','rollback')),
        revision text, predecessor jsonb, drain_receipt jsonb, changed_at timestamptz NOT NULL DEFAULT clock_timestamp())"""
    )
    cur.execute(
        "INSERT INTO sync_v3_control.authority(singleton,mode,revision) VALUES(true,'legacy',%s)", (revision,)
    )
    cur.execute('REVOKE ALL ON sync_v3_control.authority FROM PUBLIC, anon, authenticated, service_role')
    cur.execute(
        'GRANT USAGE ON SCHEMA sync_v3_control TO sync_v3_worker,baseballos_v3_projector,baseballos_v3_publisher'
    )
    cur.execute(
        'GRANT SELECT ON sync_v3_control.authority TO sync_v3_worker,baseballos_v3_projector,baseballos_v3_publisher'
    )
    cur.execute(
        'GRANT CONNECT ON DATABASE postgres TO sync_v3_worker,baseballos_v3_projector,baseballos_v3_publisher,baseballos_product_api'
    )
    publisher.grant_scope(
        cur,
        b.PROJECTOR,
        projector.READ,
        projector.INSERT,
        projector.UPDATE,
        'private_projector',
        insert_checks={'sync_runs': projector.CHECKPOINT},
        update_checks={'evidence_objects': projector.INVALIDATION_POLICY},
        update_columns={'evidence_objects': projector.INVALIDATION_FIELDS},
    )
    publisher.grant_scope(cur, b.PUBLISHER, publisher.READ, publisher.INSERT, publisher.UPDATE, 'v3_publisher')
    # Flask serves public, account-scoped and admin reads. This login is private to the trusted API server.
    cur.execute(
        """SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')
                   ORDER BY 1"""
    )
    reads = {name for name, in cur.fetchall()}
    writes = set(EXCLUDED) - {'prospects'}
    publisher.grant_scope(
        cur, API, reads, writes, {'users', 'audience_subscribers', 'user_followed_teams'}, 'product_api'
    )
    cur.execute('GRANT DELETE ON public.user_followed_teams TO baseballos_product_api')
    cur.execute(
        'CREATE POLICY product_api_delete ON public.user_followed_teams FOR DELETE TO baseballos_product_api USING (true)'
    )

    grant_legacy(cur, reads)


def grant_legacy(cur, reads):
    from sync_v3 import staging_publisher as publisher

    # Existing legacy commands share this bounded fallback login. Alembic uses a separate administrator.
    governed = reads - set(EXCLUDED) - {'alembic_version'}
    publisher.grant_scope(cur, LEGACY, reads, governed, governed, 'legacy_sync')
    for table in sorted(governed):
        ident = sql.Identifier('public', table)
        cur.execute(sql.SQL('GRANT DELETE ON {} TO baseballos_legacy_sync').format(ident))
        cur.execute(sql.SQL('DROP POLICY IF EXISTS legacy_sync_delete ON {}').format(ident))
        cur.execute(
            sql.SQL(
                'CREATE POLICY legacy_sync_delete ON {} FOR DELETE TO baseballos_legacy_sync USING (true)'
            ).format(ident)
        )
    cur.execute('GRANT CONNECT ON DATABASE postgres TO baseballos_legacy_sync')


def prohibit_sessions(cur, roles):
    cur.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s) AND rolcanlogin', (roles,))
    if cur.fetchall():
        raise ValueError('Commit NOLOGIN for the outgoing runtime before draining')
    cur.execute(
        "SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s) AND backend_type='client backend'", (roles,)
    )
    if cur.fetchall():
        raise ValueError('Outgoing runtime still has connected sessions')
    cur.execute('SELECT 1 FROM pg_prepared_xacts WHERE owner=ANY(%s)', (roles,))
    if cur.fetchone():
        raise ValueError('An outgoing writer has a prepared transaction')


# Reviewed provider definitions touch Vault or Storage only. Changes require a fresh review.
PROVIDER_DEFINERS = {
    (
        'storage.reconcile_lifecycle_state(text,boolean)',
        'supabase_storage_admin',
        '2b5169238709dcbfa8c1ddc8f0421b6420f14c4f4516fefc5d32d138eb336e10',
    ),
    (
        'vault.create_secret(text,text,text,uuid)',
        'supabase_admin',
        'cd921f1ec31bb6cfd83dde4b41ad2fbe4e5fa331858743de0cea635926c8c1d0',
    ),
    (
        'vault.update_secret(uuid,text,text,text,uuid)',
        'supabase_admin',
        '9ab4c94a4ed480064303a497a6132ba2318cdc5899477a8354916da0481754c5',
    ),
}


def fence_service_role(cur):
    cur.execute(PREVIEW.read_text())
    changes = cur.fetchall()
    for _, _, _, _, _, statement in changes:
        cur.execute(statement)
    cur.execute(
        """SELECT c.relname FROM pg_class c WHERE c.relnamespace='public'::regnamespace
        AND c.relkind IN ('r','p','v','f') AND NOT(c.relname=ANY(%s))
        AND (has_any_column_privilege('service_role',c.oid,'INSERT,UPDATE,REFERENCES')
        OR has_table_privilege('service_role',c.oid,'DELETE,TRUNCATE,TRIGGER'))""",
        (list(EXCLUDED),),
    )
    if cur.fetchone():
        raise ValueError('Inherited, indirect or unreviewed governed write grants remain')
    cur.execute(
        """SELECT 1 FROM pg_class t JOIN pg_depend d ON d.refobjid=t.oid AND d.refclassid='pg_class'::regclass
        JOIN pg_class s ON s.oid=d.objid AND d.classid='pg_class'::regclass
        WHERE t.relnamespace='public'::regnamespace AND NOT(t.relname=ANY(%s)) AND s.relkind='S'
          AND d.deptype IN ('a','i') AND CASE WHEN s.relkind='S' THEN has_sequence_privilege('service_role',s.oid,'USAGE,UPDATE') ELSE false END""",
        (list(EXCLUDED),),
    )
    if cur.fetchone():
        raise ValueError('Service role retains governed sequence authority')
    cur.execute(
        """SELECT p.oid::regprocedure::text,pg_get_userbyid(p.proowner),
        encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname !~ '^pg_' AND n.nspname != 'information_schema' AND p.prosecdef
        AND has_schema_privilege('service_role',n.oid,'USAGE') AND has_function_privilege('service_role',p.oid,'EXECUTE')"""
    )
    if set(cur.fetchall()) - PROVIDER_DEFINERS:
        raise ValueError('Callable definer requires review before service-role fencing')
    cur.execute(
        """SELECT 1 FROM pg_roles r WHERE r.rolcanlogin AND r.rolname NOT IN ('postgres','supabase_admin')
        AND (pg_has_role(r.oid,'postgres','SET') OR EXISTS (
          SELECT 1 FROM pg_roles a WHERE a.rolname='supabase_admin' AND pg_has_role(r.oid,a.oid,'SET')))"""
    )
    if cur.fetchone():
        raise ValueError('Another login can assume the database owner')
    cur.execute(
        """SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        WHERE NOT t.tgisinternal AND t.tgenabled!='D' AND c.relnamespace='public'::regnamespace
          AND c.relname=ANY(%s)""",
        (list(EXCLUDED),),
    )
    if cur.fetchone():
        raise ValueError('Review new trigger side effects on unrelated writable product tables')
    cur.execute(
        """WITH RECURSIVE governed(oid) AS (
        SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')
          AND NOT(relname=ANY(%s))
        UNION SELECT r.ev_class FROM governed g JOIN pg_depend d ON d.refclassid='pg_class'::regclass
          AND d.refobjid=g.oid AND d.classid='pg_rewrite'::regclass JOIN pg_rewrite r ON r.oid=d.objid)
        SELECT 1 FROM governed g JOIN pg_class c ON c.oid=g.oid WHERE c.relkind='v'
          AND has_schema_privilege('service_role',c.relnamespace,'USAGE')
          AND (has_any_column_privilege('service_role',c.oid,'INSERT,UPDATE')
               OR has_table_privilege('service_role',c.oid,'DELETE'))""",
        (list(EXCLUDED),),
    )
    if cur.fetchone():
        raise ValueError('A writable view still reaches governed product records')
    allowed = ('postgres', 'supabase_admin', 'pg_write_all_data', b.PROJECTOR, b.PUBLISHER)
    cur.execute(
        """SELECT r.rolname,c.relname FROM pg_roles r JOIN pg_class c ON c.relnamespace='public'::regnamespace
        WHERE c.relkind IN ('r','p','v','f') AND NOT(c.relname=ANY(%s)) AND NOT(r.rolname=ANY(%s))
        AND has_schema_privilege(r.oid,c.relnamespace,'USAGE') AND (
        has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE') OR has_table_privilege(r.oid,c.oid,'DELETE,TRUNCATE,TRIGGER'))""",
        (list(EXCLUDED), list(allowed)),
    )
    if cur.fetchone():
        raise ValueError('An additional role can modify a governed product relation')
    cur.execute(
        """SELECT 1 FROM pg_auth_members am JOIN pg_roles r ON r.oid=am.roleid
        JOIN pg_roles m ON m.oid=am.member WHERE r.rolname=ANY(%s) AND m.rolname NOT IN ('postgres','supabase_admin')""",
        ([LEGACY, b.WORKER, b.PROJECTOR, b.PUBLISHER, API, 'sync_v3_reviewer', 'pg_write_all_data'],),
    )
    if cur.fetchone():
        raise ValueError('Unexpected role membership can assume a governed writer')

    return len(changes)


def transition(cur, old, new, revision, pin, *, drain=None, replacement=None):
    cur.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))', (LOCK,))
    if not cur.fetchone()[0]:
        raise ValueError('A v3 job still owns the handoff lock')
    if (old, new) not in (('legacy', 'v3'), ('v3', 'rollback'), ('rollback', 'legacy')):
        raise ValueError('Unsupported production transition')
    cur.execute('SELECT mode,revision,predecessor FROM sync_v3_control.authority WHERE singleton FOR UPDATE')
    state = cur.fetchone()
    if not state or state[0] != old or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Control state or revision changed')
    if revision != state[1] or old != 'legacy' and pin != state[2]:
        raise ValueError('Rollback must use the same tested revision and pinned predecessor')
    # A service-role client can already have executed DML before its ACL is revoked.
    # Order every outstanding governed write against the transfer, including prepared transactions.
    relations = [sql.Identifier('public', table) for table in sorted(governed_relations(cur))]
    cur.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE NOWAIT').format(sql.SQL(', ').join(relations)))
    if new in ('legacy', 'v3'):
        cur.execute(
            """SELECT id,sync_run_id FROM public.dashboard_snapshots
            WHERE snapshot_type='bullpen_dashboard' AND is_published FOR UPDATE NOWAIT"""
        )
        if (
            pin.get('database') != b.DATABASE
            or cur.fetchall() != [(pin['database_edition']['snapshot'], pin['database_edition']['sync'])]
            or not re.fullmatch('[0-9a-f]{64}', pin['public_edition_sha256'])
        ):
            raise ValueError('Pinned legacy selector differs')
    if new == 'v3':
        if b.PROJECT != b.ORIGINAL_PROJECT:
            cur.execute('SELECT system_identifier::text FROM pg_control_system()')
            cluster = cur.fetchone()[0]
            if (
                drain is not None
                or cluster == b.ORIGINAL_CLUSTER
                or cluster != b.REPLACEMENT_CLUSTER
                or not isinstance(replacement, dict)
                or replacement.get('source_cluster') != b.ORIGINAL_CLUSTER
                or replacement.get('target_cluster') != cluster
                or replacement.get('revision') != revision
                or not re.fullmatch('[0-9a-f]{64}', replacement.get('content_sha256') or '')
            ):
                raise ValueError('Verified logical copy between the two reviewed clusters required')
            evidence = replacement
        else:
            if (
                replacement is not None
                or not isinstance(drain, dict)
                or drain.get('project') != b.PROJECT
                or drain.get('revision') != revision
                or drain.get('endpoints')
                not in (['DIRECT', 'SESSION', 'TRANSACTION'], ['DIRECT', 'SESSION', 'TRANSACTION', 'DEDICATED'])
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', drain.get('provider_operation') or '')
            ):
                raise ValueError('Require a successful provider pool drain receipt for this project and revision')
            evidence = drain
        cur.execute('UPDATE sync_v3_control.authority SET drain_receipt=%s WHERE singleton', (Json(evidence),))
        if state[2] is not None:
            raise ValueError('A rolled-back handoff requires a newly reviewed runtime provisioning')
        prohibit_sessions(cur, [LEGACY])
        cur.execute('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM baseballos_legacy_sync')
        cur.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM baseballos_legacy_sync')
        fence_service_role(cur)
        for role in (b.WORKER, b.PROJECTOR, b.PUBLISHER):
            cur.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)))
    if new == 'rollback':
        prohibit_sessions(cur, [b.WORKER, b.PROJECTOR])
    if new == 'legacy':
        prohibit_sessions(cur, [b.WORKER, b.PROJECTOR, b.PUBLISHER])
        # Remove effective data grants even if an external pool retains an authenticated frontend.
        for role in (b.WORKER, b.PROJECTOR, b.PUBLISHER):
            for kind in ('TABLES', 'SEQUENCES'):
                cur.execute(
                    sql.SQL('REVOKE ALL ON ALL {} IN SCHEMA public, candidate FROM {}').format(
                        sql.SQL(kind), sql.Identifier(role)
                    )
                )
            cur.execute(sql.SQL('REVOKE USAGE ON SCHEMA candidate FROM {}').format(sql.Identifier(role)))
        cur.execute(
            "SELECT relname FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')"
        )
        grant_legacy(cur, {name for name, in cur.fetchall()})
        cur.execute('ALTER ROLE baseballos_legacy_sync LOGIN')
    cur.execute(
        """UPDATE sync_v3_control.authority SET mode=%s,revision=%s,predecessor=%s,changed_at=clock_timestamp()
                   WHERE singleton""",
        (new, revision, Json(pin)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'activate', 'begin-rollback', 'release-legacy'))
    parser.add_argument('--revision')
    parser.add_argument('--receipt', type=Path)
    receipts = parser.add_mutually_exclusive_group()
    receipts.add_argument('--pool-drain', type=Path)
    receipts.add_argument('--replacement-copy', type=Path)
    args = parser.parse_args()
    if not b.PRODUCTION:
        parser.error('Set SYNC_V3_DEPLOYMENT=production explicitly')
    from sqlalchemy.engine import make_url

    url = make_url(os.environ['DATABASE_MIGRATION_URL'])
    direct = f'db.{b.PROJECT}.supabase.co'
    if (
        url.get_backend_name() != 'postgresql'
        or url.database != b.DATABASE
        or url.port not in (None, 5432)
        or not (
            url.host == direct
            and url.username == 'postgres'
            or re.fullmatch(r'aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com', url.host or '')
            and url.username == f'postgres.{b.PROJECT}'
        )
    ):
        parser.error('Expected a project-pinned, session-mode migration login')
    params = url.translate_connect_args(username='user')
    params.update(sslmode='verify-full', connect_timeout=10, application_name='baseballos_handoff_admin')
    if os.environ.get('SYNC_V3_SSL_ROOT_CERT'):
        params['sslrootcert'] = os.environ['SYNC_V3_SSL_ROOT_CERT']
    with closing(psycopg2.connect(**params)) as conn, conn, conn.cursor() as cur:
        cur.execute('SELECT current_database(),session_user,current_user')
        if cur.fetchone() != (b.DATABASE, 'postgres', 'postgres'):
            raise ValueError('Unexpected migration identity')
        if args.operation == 'prepare':
            prepare(cur, args.revision)
        else:
            if not args.revision or not args.receipt:
                parser.error('A revision and verified public predecessor receipt are required')
            pair = {
                'activate': ('legacy', 'v3'),
                'begin-rollback': ('v3', 'rollback'),
                'release-legacy': ('rollback', 'legacy'),
            }
            transition(
                cur,
                *pair[args.operation],
                args.revision,
                json.loads(args.receipt.read_text())['legacy_predecessor'],
                drain=json.loads(args.pool_drain.read_text()) if args.pool_drain else None,
                replacement=json.loads(args.replacement_copy.read_text()) if args.replacement_copy else None,
            )
    print(json.dumps({'committed': args.operation}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(
            f'Production handoff failed ({type(exc).__name__}); transaction was not confirmed.'
        ) from None
