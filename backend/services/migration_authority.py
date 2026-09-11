"""Fail-closed schema authority shared by startup, promotion, and shadow work."""

import os


MODE_KEY = 'DATABASE_MIGRATION_MODE'
MODES = ('owner', 'verify_only', 'disabled')


class MigrationAuthorityError(RuntimeError):
    pass


def migration_mode(env=None, *, required=True):
    env = os.environ if env is None else env
    value = env.get(MODE_KEY)
    if value is None and not required:
        return 'disabled'
    if value not in MODES:
        raise MigrationAuthorityError(
            f'{MODE_KEY}_must_be_explicit_owner_verify_only_or_disabled'
        )
    return value


def require_owner(env=None):
    env = os.environ if env is None else env
    if migration_mode(env) != 'owner':
        raise MigrationAuthorityError('schema_mutation_requires_owner')
    # An integration process cannot turn its shadow identity into ownership.
    if env.get('SYNC_PIPELINE_SHADOW_MODE', 'false') != 'false':
        raise MigrationAuthorityError('shadow_process_cannot_own_schema')
    refs = [env[key] for key in ('GITHUB_REF', 'RENDER_GIT_BRANCH') if env.get(key)]
    if env.get('APP_ENV') == 'production':
        if not refs or any(ref not in ('main', 'refs/heads/main') for ref in refs):
            raise MigrationAuthorityError('production_owner_requires_main_provenance')
    return 'owner'


def require_verify_only(env=None):
    if migration_mode(env) != 'verify_only':
        raise MigrationAuthorityError('integration_requires_verify_only')


def read_current_heads(engine):
    """Inspect on a separate connection; never create or update version metadata."""
    from alembic.migration import MigrationContext
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    try:
        with engine.connect() as connection:
            if connection.dialect.name == 'postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                if connection.execute(text('SHOW transaction_read_only')).scalar() != 'on':
                    raise MigrationAuthorityError('schema_inspection_requires_read_only_transaction')
            return tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
    except SQLAlchemyError as exc:
        raise MigrationAuthorityError(f'database_head_read_failed:{type(exc).__name__}') from None


def verify_heads(current, expected):
    heads = tuple(current)
    print(f'[migration_authority] current_heads={heads!r} target_head={expected}', flush=True)
    if heads != (expected,):
        raise MigrationAuthorityError(f'expected_migration_head_{expected}_got_{heads!r}')


def startup_action(env=None):
    env = os.environ if env is None else env
    emergency = env.get('SKIP_STARTUP_MIGRATIONS') == 'true'
    mode = migration_mode(env, required=not emergency)
    print(f'[migration_authority] mode={mode} emergency_skip={str(emergency).lower()}', flush=True)
    if emergency:
        print('[render_start] WARNING: startup database migrations explicitly skipped '
              'via SKIP_STARTUP_MIGRATIONS=true', flush=True)
        return 'skip'
    if mode == 'owner':
        require_owner(env)
        return 'upgrade'
    if mode == 'verify_only':
        return 'verify'
    raise MigrationAuthorityError('startup_requires_owner_or_verify_only_or_emergency_skip')


def guard_alembic(environment_context):
    # Alembic marks its current-revision display as dont_mutate. All other
    # execution contexts require authority, including direct CLI invocations.
    if not environment_context.get_context().opts.get('dont_mutate', False):
        require_owner()
