"""Off-provider backup and isolated restore rehearsal (WP-0.2, EOS-009).

Three steps, each safe to run on its own:

``dump``
    ``pg_dump`` of the source database to a local custom-format file, inside a
    read-only, repeatable-read snapshot, plus a manifest of row counts for the
    canonical tables and the Alembic head. Use a READ-ONLY database role for
    the source. Never writes to the source.

``restore``
    ``pg_restore`` of that file into an EMPTY scratch database. Refuses unless
    the target database name contains ``rehearsal``, ``restore`` or
    ``scratch``, the target is not the source, and the target has no tables.
    It never restores over production.

``verify``
    Recount the canonical tables in the restored copy and compare them with
    the dump manifest. Exit 1 on any difference.

Connection strings come only from the environment (``SOURCE_DATABASE_URL``,
``TARGET_DATABASE_URL``) and are never printed; output shows host and
database name only.

    SOURCE_DATABASE_URL=<read-only role> python backend/scripts/database_restore_rehearsal.py \
        dump --output /secure/path/baseballos.dump
    TARGET_DATABASE_URL=<scratch db> python backend/scripts/database_restore_rehearsal.py \
        restore --input /secure/path/baseballos.dump
    TARGET_DATABASE_URL=<scratch db> python backend/scripts/database_restore_rehearsal.py \
        verify --manifest /secure/path/baseballos.dump.manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

# The durable season record (EOS-009). A missing table is reported, not
# skipped, so a dump that silently lost a table fails verification.
CANONICAL_TABLES = (
    'alembic_version',
    'pitchers',
    'game_logs',
    'scheduled_games',
    'player_transactions',
    'roster_status_snapshots',
    'dashboard_snapshots',
    'share_artifacts',
    'team_state_publication_proofs',
    'sync_runs',
)
SCRATCH_NAME_TOKENS = ('rehearsal', 'restore', 'scratch')


class RehearsalRefused(RuntimeError):
    """A safety guard refused the operation."""


def describe(url):
    """Host and database name only; never credentials."""
    parts = urlsplit(url or '')
    return f"{parts.hostname or '?'}:{parts.port or 5432}/{(parts.path or '/').lstrip('/') or '?'}"


def _identity(url):
    parts = urlsplit(url or '')
    return (parts.hostname, parts.port or 5432, (parts.path or '/').lstrip('/'))


def require_safe_target(target_url, source_url=None):
    if not target_url:
        raise RehearsalRefused('TARGET_DATABASE_URL is not set')
    host, port, name = _identity(target_url)
    if not name or not any(token in name.lower() for token in SCRATCH_NAME_TOKENS):
        raise RehearsalRefused(
            f'target database {name!r} is not named as a scratch database '
            f'(must contain one of {SCRATCH_NAME_TOKENS})'
        )
    for guarded in (source_url, os.environ.get('DATABASE_URL')):
        if guarded and _identity(guarded) == (host, port, name):
            raise RehearsalRefused('target database is the source or the configured application database')


def _connect(url):
    import psycopg2  # imported lazily so --help works without the driver

    return psycopg2.connect(url)


def table_counts(url, tables=CANONICAL_TABLES):
    """Row counts per table (``None`` when the table is absent) and the Alembic head."""
    counts = {}
    head = None
    connection = _connect(url)
    try:
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute('SELECT to_regclass(%s)', (f'public.{table}',))
                if cursor.fetchone()[0] is None:
                    counts[table] = None
                    continue
                cursor.execute(f'SELECT count(*) FROM public."{table}"')
                counts[table] = cursor.fetchone()[0]
            if counts.get('alembic_version') is not None:
                cursor.execute('SELECT version_num FROM public.alembic_version ORDER BY 1')
                head = [row[0] for row in cursor.fetchall()]
    finally:
        connection.rollback()
        connection.close()
    return counts, head


def _public_table_count(url):
    connection = _connect(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            return cursor.fetchone()[0]
    finally:
        connection.rollback()
        connection.close()


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command, url):
    # libpq reads the connection string from the argument; it is never
    # echoed. stderr is filtered of the URL before it is shown.
    completed = subprocess.run(command + ['--dbname', url], capture_output=True, text=True)
    if completed.returncode != 0:
        message = (completed.stderr or '').replace(url, describe(url))
        raise RuntimeError(f'{command[0]} failed: {message.strip()[:2000]}')
    return completed


def dump(source_url, output):
    if not source_url:
        raise RehearsalRefused('SOURCE_DATABASE_URL is not set')
    output = Path(output)
    counts, head = table_counts(source_url)
    _run([
        'pg_dump', '--format=custom', '--no-owner', '--no-privileges',
        '--serializable-deferrable', '--file', str(output),
    ], source_url)
    manifest = {
        'contract': 'baseballos_restore_rehearsal_v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source': describe(source_url),
        'dump_file': output.name,
        'dump_sha256': _sha256(output),
        'dump_bytes': output.stat().st_size,
        'alembic_head': head,
        'table_counts': counts,
        'missing_tables': sorted(table for table, count in counts.items() if count is None),
    }
    manifest_path = output.with_name(output.name + '.manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest, manifest_path


def restore(target_url, input_path, *, source_url=None):
    require_safe_target(target_url, source_url)
    if _public_table_count(target_url):
        raise RehearsalRefused('target database is not empty; restore only into a fresh scratch database')
    _run(['pg_restore', '--no-owner', '--no-privileges', '--exit-on-error', str(input_path)], target_url)
    return {'restored_into': describe(target_url), 'input': Path(input_path).name}


def verify(target_url, manifest_path, *, source_url=None):
    require_safe_target(target_url, source_url)
    manifest = json.loads(Path(manifest_path).read_text())
    counts, head = table_counts(target_url, tuple(manifest['table_counts']))
    differences = {
        table: {'dumped': expected, 'restored': counts.get(table)}
        for table, expected in manifest['table_counts'].items()
        if counts.get(table) != expected
    }
    if head != manifest.get('alembic_head'):
        differences['alembic_head'] = {'dumped': manifest.get('alembic_head'), 'restored': head}
    return {
        'verified': not differences and not manifest.get('missing_tables'),
        'target': describe(target_url),
        'table_counts': counts,
        'alembic_head': head,
        'differences': differences,
        'missing_tables': manifest.get('missing_tables') or [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='BaseballOS backup and isolated restore rehearsal.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('dump').add_argument('--output', required=True)
    sub.add_parser('restore').add_argument('--input', required=True)
    sub.add_parser('verify').add_argument('--manifest', required=True)
    args = parser.parse_args(argv)

    source_url = os.environ.get('SOURCE_DATABASE_URL')
    target_url = os.environ.get('TARGET_DATABASE_URL')
    try:
        if args.command == 'dump':
            result, manifest_path = dump(source_url, args.output)
            result = {**result, 'manifest': str(manifest_path)}
        elif args.command == 'restore':
            result = restore(target_url, args.input, source_url=source_url)
        else:
            result = verify(target_url, args.manifest, source_url=source_url)
    except RehearsalRefused as exc:
        print(f'refused: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('verified', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
