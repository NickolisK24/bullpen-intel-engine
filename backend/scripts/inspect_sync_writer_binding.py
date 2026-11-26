"""Read masked deployment binding identities and catalog privileges without loading the application."""
import argparse
from contextlib import closing
import json
import os

import psycopg2


def inspect(url):
    # Render and GitHub use the SQLAlchemy spelling as well as native libpq URLs.
    if url.startswith('postgresql+psycopg2://'):
        url = url.replace('postgresql+psycopg2://', 'postgresql://', 1)
    with closing(psycopg2.connect(url, connect_timeout=10)) as conn:
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with conn, conn.cursor() as cur:
            cur.execute("SELECT session_user, current_user, current_database(), "
                        "current_setting('transaction_read_only'), rolsuper, rolbypassrls, rolcreaterole "
                        "FROM pg_roles WHERE rolname = current_user")
            session, effective, database, mode, superuser, bypass, create_roles = cur.fetchone()
            if mode != 'on':
                raise RuntimeError('Read-only binding required')
            cur.execute("""SELECT n.nspname, c.relname, pg_has_role(current_user,c.relowner,'USAGE'),
                                  has_any_column_privilege(c.oid,'INSERT'), has_any_column_privilege(c.oid,'UPDATE'),
                                  has_table_privilege(c.oid,'DELETE'), has_table_privilege(c.oid,'TRUNCATE')
                           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname IN ('public','candidate') AND c.relkind IN ('r','p','v','f')
                             AND has_schema_privilege(n.oid,'USAGE') ORDER BY 1,2""")
            grants = {}
            for schema, name, *flags in cur.fetchall():
                capabilities = [action for action, allowed in zip(
                    ('owner_authority','insert','update','delete','truncate'), flags) if allowed]
                if capabilities:
                    grants[f'{schema}.{name}'] = capabilities
            cur.execute("""SELECT n.nspname, p.proname, p.oid::regprocedure::text FROM pg_proc p
                           JOIN pg_namespace n ON n.oid=p.pronamespace
                           WHERE n.nspname IN ('public','candidate') AND p.prosecdef
                             AND has_schema_privilege(n.oid,'USAGE') AND has_function_privilege(p.oid,'EXECUTE')
                           ORDER BY 1,2,3""")
            routines = [signature for _, _, signature in cur.fetchall()]
            cur.execute("""SELECT rolname FROM pg_roles WHERE rolname != session_user
                           AND pg_has_role(session_user,oid,'MEMBER') ORDER BY rolname""")
            memberships = [r[0] for r in cur.fetchall()]
    return dict(session_user=session, effective_role=effective, database=database, superuser=superuser,
                bypass_rls=bypass, can_create_roles=create_roles, member_roles=memberships,
                catalog_write_paths=grants, executable_security_definers=routines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binding', choices=('DATABASE_URL','DATABASE_MIGRATION_URL'))
    args = parser.parse_args()
    url = os.environ.get(args.binding)
    if not url:
        parser.exit(2, f'{args.binding} is absent in this execution context\n')
    try:
        result = inspect(url)
    except (psycopg2.Error, ValueError, RuntimeError):
        # Driver and parser exceptions can include connection parameters.
        parser.exit(1, f'{args.binding} inspection failed; check the binding inside its deployment\n')
    print(json.dumps(dict(binding=args.binding, **result), sort_keys=True))


if __name__ == '__main__':
    main()
