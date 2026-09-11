"""Explicit schema startup verification and operator-controlled promotion."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from alembic.script import ScriptDirectory
from sqlalchemy.exc import SQLAlchemyError

from services.migration_authority import (
    MigrationAuthorityError, read_current_heads, require_owner, require_verify_only,
    startup_action, verify_heads,
)


BACKEND = Path(__file__).resolve().parents[1]


def target_head():
    heads = ScriptDirectory(str(BACKEND / 'migrations')).get_heads()
    if len(heads) != 1:
        raise MigrationAuthorityError(f'expected_single_repository_head_got_{heads!r}')
    return heads[0]


def current_heads():
    # This import registers the application; it does not serve web traffic.
    # Do not start schedulers as a side effect of schema administration.
    os.environ['AUTO_SYNC'] = 'false'
    from app import app
    from utils.db import db
    with app.app_context():
        return read_current_heads(db.engine)


def upgrade(target):
    require_owner()
    print('[migration_authority] Executing flask db upgrade', flush=True)
    subprocess.run(
        [sys.executable, '-m', 'flask', '--app', 'app', 'db', 'upgrade', target],
        cwd=BACKEND, check=True, env={**os.environ, 'AUTO_SYNC': 'false'},
    )


def promote(*, source_branch, expected_commit, expected_head):
    require_owner()
    if os.environ.get('SKIP_STARTUP_MIGRATIONS') == 'true':
        raise MigrationAuthorityError('promotion_refuses_emergency_skip')
    if source_branch != 'main' or not re.fullmatch(r'[0-9a-f]{40}', expected_commit):
        raise MigrationAuthorityError('promotion_requires_main_and_exact_commit')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=BACKEND, text=True).strip()
    if git('rev-parse', 'HEAD') != expected_commit or git('rev-parse', 'origin/main') != expected_commit:
        raise MigrationAuthorityError('promotion_source_commit_mismatch')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise MigrationAuthorityError('promotion_requires_clean_tracked_checkout')
    target = target_head()
    if target != expected_head:
        raise MigrationAuthorityError('promotion_target_head_mismatch')
    print(f'[migration_authority] mode=owner source_branch={source_branch} '
          f'source_commit={expected_commit}', flush=True)
    print(f'[migration_authority] current_heads={current_heads()!r} target_head={target}', flush=True)
    upgrade(target)
    verify_heads(current_heads(), target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('startup')
    sub.add_parser('verify')
    promotion = sub.add_parser('promote')
    promotion.add_argument('--source-branch', required=True)
    promotion.add_argument('--expected-commit', required=True)
    promotion.add_argument('--target-head', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'promote':
            promote(source_branch=args.source_branch, expected_commit=args.expected_commit,
                    expected_head=args.target_head)
        elif args.command == 'verify':
            require_verify_only()
            print('[migration_authority] mode=verify_only; schema mutation prohibited', flush=True)
            verify_heads(current_heads(), target_head())
        else:
            action = startup_action()
            if action != 'skip':
                target = target_head()
                if action == 'upgrade':
                    print(f'[migration_authority] current_heads={current_heads()!r} '
                          f'target_head={target}', flush=True)
                    print('[render_start] Applying database migrations: flask db upgrade', flush=True)
                    upgrade(target)
                    print('[render_start] Database migrations applied successfully.', flush=True)
                verify_heads(current_heads(), target)
        return 0
    except (MigrationAuthorityError, subprocess.CalledProcessError) as exc:
        print(f'[migration_authority] REFUSED: {exc}', file=sys.stderr, flush=True)
        return 1
    except SQLAlchemyError as exc:
        # Connection exceptions can contain connection details. Log the failure
        # class, never a URL or credential-bearing exception representation.
        print(f'[migration_authority] REFUSED: database_head_read_failed:{type(exc).__name__}',
              file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
