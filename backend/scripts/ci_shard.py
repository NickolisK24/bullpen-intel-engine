#!/usr/bin/env python3
"""Deterministic backend CI shard ownership.

The backend confidence gate is one suite. CI runs it as four concurrent jobs,
each against its own PostgreSQL database, because concurrent processes that share
one database collide on ``db.create_all()`` / ``db.drop_all()`` DDL, on unique
constraints, and on the database-global advisory locks the sync services take.
Isolation is what makes the split safe; this script is what makes it complete.

Ownership lives in a checked-in manifest, ``backend/tests/ci_shard_manifest.json``,
so a CI run never invents an assignment. Every collected backend test file appears
in exactly one shard, and ``verify`` proves that against live pytest collection —
at file level and at pytest node-ID level — before anything is trusted.

A new test file is deliberately a verification failure until it is assigned and
the manifest is reviewed. Silently absorbing an unreviewed file is the one
outcome this script exists to prevent.

Usage
-----
    python scripts/ci_shard.py files --shard 1
    python scripts/ci_shard.py verify
    python scripts/ci_shard.py summary
    python scripts/ci_shard.py generate --timings <path> [--output <path>]

Run from the ``backend/`` directory. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
TESTS_DIR = os.path.join(BACKEND_ROOT, 'tests')
MANIFEST_PATH = os.path.join(TESTS_DIR, 'ci_shard_manifest.json')

SUPPORTED_SCHEMA_VERSIONS = (1,)
REQUIRED_SHARD_COUNT = 4
TEST_PATH_PREFIX = 'tests/'

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


class ManifestError(Exception):
    """Raised when the checked-in manifest is missing, malformed, or unsafe."""


# ── Manifest loading and validation ───────────────────────────────────────────
def _relative_test_path_problem(path):
    """Return a human-readable problem with ``path``, or None when it is safe.

    The manifest is an input to a shell command line in CI, so a path that
    escapes ``backend/tests`` or that names something other than a backend test
    module is refused before it is ever printed.
    """
    if not isinstance(path, str) or not path:
        return 'path must be a non-empty string'
    if path != path.strip():
        return 'path has leading or trailing whitespace'
    if '\\' in path:
        return 'path must use forward slashes'
    if os.path.isabs(path):
        return 'path must be relative to the backend/ directory'
    if not path.startswith(TEST_PATH_PREFIX):
        return f'path must start with {TEST_PATH_PREFIX!r}'
    if any(segment in ('.', '..', '') for segment in path.split('/')):
        return 'path must not contain empty or relative segments'

    basename = path.rsplit('/', 1)[-1]
    if not (basename.startswith('test_') and basename.endswith('.py')):
        return 'path must name a backend test_*.py module'

    resolved = os.path.realpath(os.path.join(BACKEND_ROOT, path))
    tests_root = os.path.realpath(TESTS_DIR)
    if not resolved.startswith(tests_root + os.sep):
        return 'path escapes backend/tests'
    if not os.path.isfile(resolved):
        return 'path does not exist on disk'
    return None


def load_manifest(manifest_path=MANIFEST_PATH):
    """Read and fully validate the manifest. Raises ManifestError on any problem."""
    if not os.path.isfile(manifest_path):
        raise ManifestError(f'manifest not found: {manifest_path}')

    try:
        with open(manifest_path, encoding='utf-8') as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ManifestError(f'manifest is not readable JSON: {exc}') from exc

    if not isinstance(manifest, dict):
        raise ManifestError('manifest must be a JSON object')

    schema_version = manifest.get('schema_version')
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f'unsupported schema_version {schema_version!r}; '
            f'supported: {list(SUPPORTED_SCHEMA_VERSIONS)}'
        )

    shard_count = manifest.get('shard_count')
    if shard_count != REQUIRED_SHARD_COUNT:
        raise ManifestError(
            f'shard_count must be exactly {REQUIRED_SHARD_COUNT}, got {shard_count!r}'
        )

    shards = manifest.get('shards')
    if not isinstance(shards, dict):
        raise ManifestError('manifest.shards must be a JSON object')

    expected_keys = {str(index) for index in range(1, REQUIRED_SHARD_COUNT + 1)}
    if set(shards) != expected_keys:
        raise ManifestError(
            f'manifest.shards keys must be exactly {sorted(expected_keys)}, '
            f'got {sorted(shards)}'
        )

    seen = {}
    for shard_id in sorted(expected_keys, key=int):
        shard = shards[shard_id]
        if not isinstance(shard, dict):
            raise ManifestError(f'shard {shard_id} must be a JSON object')
        entries = shard.get('files')
        if not isinstance(entries, list):
            raise ManifestError(f'shard {shard_id} must carry a "files" list')
        if not entries:
            raise ManifestError(f'shard {shard_id} is empty')
        for entry in entries:
            if not isinstance(entry, dict) or 'path' not in entry:
                raise ManifestError(
                    f'shard {shard_id} has an entry without a "path" key'
                )
            path = entry['path']
            problem = _relative_test_path_problem(path)
            if problem is not None:
                raise ManifestError(f'shard {shard_id} path {path!r}: {problem}')
            if path in seen:
                raise ManifestError(
                    f'path {path!r} is assigned to shard {seen[path]} '
                    f'and shard {shard_id}'
                )
            seen[path] = shard_id

    return manifest


def shard_files(manifest, shard_id):
    """Return the ordered file list owned by ``shard_id`` (an int 1..4)."""
    return [entry['path'] for entry in manifest['shards'][str(shard_id)]['files']]


def manifest_paths(manifest):
    """Return every assigned path across all shards, in shard order."""
    paths = []
    for shard_id in range(1, REQUIRED_SHARD_COUNT + 1):
        paths.extend(shard_files(manifest, shard_id))
    return paths


def _entry_seconds(entry):
    value = entry.get('measured_seconds')
    return float(value) if isinstance(value, (int, float)) else 0.0


def shard_measured_seconds(manifest, shard_id):
    entries = manifest['shards'][str(shard_id)]['files']
    return sum(_entry_seconds(entry) for entry in entries)


# ── Live pytest collection ────────────────────────────────────────────────────
def collection_environment():
    """Environment for a collection subprocess: disposable, and never PostgreSQL.

    Importing the test modules imports ``app``, which builds the Flask app at
    import time and refuses to start without a local ``DATABASE_URL``. Collection
    therefore needs a database *URL*, but never a database *server*: SQLAlchemy
    opens nothing during import, and pytest collects skip-marked tests as nodes
    regardless of the target.

    Pinning an in-memory SQLite target here — rather than inheriting whatever the
    shell happens to export — is what makes the accounting answer identical on a
    laptop and in a CI job that has no PostgreSQL service.
    """
    env = dict(os.environ)
    env['APP_ENV'] = 'test'
    env['AUTO_SYNC'] = 'false'
    env['DATABASE_URL'] = 'sqlite:///:memory:'
    env['TEST_DATABASE_URL'] = 'sqlite:///:memory:'
    return env


def collect_node_ids(targets=None):
    """Return the sorted pytest node IDs collected for ``targets``.

    ``targets`` defaults to the whole ``tests`` directory. Collection runs in a
    subprocess from ``backend/`` so it sees exactly the tree CI sees.
    """
    argv = [
        sys.executable, '-m', 'pytest',
        *(targets if targets is not None else ['tests']),
        '--collect-only', '-q',
        '-p', 'no:cacheprovider',
    ]
    result = subprocess.run(
        argv,
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env=collection_environment(),
    )
    if result.returncode != 0:
        raise ManifestError(
            'pytest collection failed (exit {code}):\n{err}\n{out}'.format(
                code=result.returncode,
                err=result.stderr.strip()[-4000:],
                out=result.stdout.strip()[-4000:],
            )
        )

    node_ids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith(TEST_PATH_PREFIX) and '::' in line:
            node_ids.append(line)
    if not node_ids:
        raise ManifestError('pytest collection produced no node IDs')
    return sorted(node_ids)


def node_file(node_id):
    return node_id.split('::', 1)[0]


def files_from_node_ids(node_ids):
    return {node_file(node_id) for node_id in node_ids}


def counts_by_file(node_ids):
    counts = {}
    for node_id in node_ids:
        counts[node_file(node_id)] = counts.get(node_file(node_id), 0) + 1
    return counts


# ── verify ────────────────────────────────────────────────────────────────────
def command_verify(_args):
    """Prove the manifest partitions live collection exactly once. Fail closed."""
    problems = []

    try:
        manifest = load_manifest()
    except ManifestError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        print('backend CI shard verification: FAIL')
        return EXIT_FAIL

    assigned = manifest_paths(manifest)
    assigned_set = set(assigned)

    try:
        full_node_ids = collect_node_ids()
    except ManifestError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        print('backend CI shard verification: FAIL')
        return EXIT_FAIL

    collected_files = files_from_node_ids(full_node_ids)
    per_file_counts = counts_by_file(full_node_ids)

    missing = sorted(collected_files - assigned_set)
    extra = sorted(assigned_set - collected_files)
    duplicated = sorted({path for path in assigned if assigned.count(path) > 1})

    if missing:
        problems.append(
            f'{len(missing)} collected test file(s) are not assigned to any shard'
        )
    if extra:
        problems.append(
            f'{len(extra)} manifest file(s) are no longer collected by pytest'
        )
    if duplicated:
        problems.append(f'{len(duplicated)} file(s) assigned to more than one shard')

    # Node-ID accounting. File-level exactness is necessary but not sufficient:
    # this proves the four shard command lines really do collect every test
    # exactly once, which is the property the split has to preserve.
    shard_node_ids = {}
    per_shard_error = None
    for shard_id in range(1, REQUIRED_SHARD_COUNT + 1):
        try:
            shard_node_ids[shard_id] = set(collect_node_ids(shard_files(manifest, shard_id)))
        except ManifestError as exc:
            per_shard_error = f'shard {shard_id} collection failed: {exc}'
            problems.append(per_shard_error)
            break

    union = set()
    overlaps = []
    if per_shard_error is None:
        shard_ids = sorted(shard_node_ids)
        for index, left in enumerate(shard_ids):
            for right in shard_ids[index + 1:]:
                shared = shard_node_ids[left] & shard_node_ids[right]
                if shared:
                    overlaps.append((left, right, sorted(shared)))
            union |= shard_node_ids[left]

        missing_nodes = sorted(set(full_node_ids) - union)
        extra_nodes = sorted(union - set(full_node_ids))
        if missing_nodes:
            problems.append(f'{len(missing_nodes)} node ID(s) collected by no shard')
        if extra_nodes:
            problems.append(f'{len(extra_nodes)} node ID(s) collected by a shard but not by the full suite')
        if overlaps:
            problems.append(f'{len(overlaps)} shard pair(s) collect overlapping node IDs')
    else:
        missing_nodes = []
        extra_nodes = []

    print('backend CI shard verification')
    print(f'  manifest              : {os.path.relpath(MANIFEST_PATH, BACKEND_ROOT)}')
    print(f'  baseline commit       : {manifest.get("baseline_commit", "unknown")}')
    print(f'  assignment strategy   : {manifest.get("assignment_strategy", "unknown")}')
    print(f'  collected test files  : {len(collected_files)}')
    print(f'  manifest test files   : {len(assigned_set)}')
    print(f'  collected node IDs    : {len(full_node_ids)}')
    if per_shard_error is None:
        print(f'  shard node ID union   : {len(union)}')
    print('')
    print('  shard  files  tests  measured_seconds')
    for shard_id in range(1, REQUIRED_SHARD_COUNT + 1):
        files = shard_files(manifest, shard_id)
        tests = sum(per_file_counts.get(path, 0) for path in files)
        print('  {shard:>5}  {files:>5}  {tests:>5}  {seconds:>16.1f}'.format(
            shard=shard_id,
            files=len(files),
            tests=tests,
            seconds=shard_measured_seconds(manifest, shard_id),
        ))
    print('')
    print(f'  missing files         : {len(missing)}')
    for path in missing[:20]:
        print(f'      + {path}')
    if len(missing) > 20:
        print(f'      … and {len(missing) - 20} more')
    print(f'  extra files           : {len(extra)}')
    for path in extra[:20]:
        print(f'      - {path}')
    if len(extra) > 20:
        print(f'      … and {len(extra) - 20} more')
    print(f'  duplicated files      : {len(duplicated)}')
    for path in duplicated[:20]:
        print(f'      ! {path}')
    print(f'  missing node IDs      : {len(missing_nodes)}')
    for node_id in missing_nodes[:10]:
        print(f'      + {node_id}')
    print(f'  duplicated node IDs   : {sum(len(shared) for _, _, shared in overlaps)}')
    for left, right, shared in overlaps[:5]:
        print(f'      ! shards {left} and {right} share {len(shared)} node ID(s)')
    print('')

    if problems:
        for problem in problems:
            print(f'  problem: {problem}')
        print('')
        print('A new or renamed backend test file fails verification on purpose.')
        print('Regenerate the manifest deliberately:')
        print('  python scripts/ci_shard.py generate --timings <timings.json>')
        print('backend CI shard verification: FAIL')
        return EXIT_FAIL

    print('backend CI shard verification: PASS')
    return EXIT_OK


# ── files ─────────────────────────────────────────────────────────────────────
def command_files(args):
    """Print the file list for one shard, one path per line, nothing else."""
    try:
        shard_id = int(args.shard)
    except (TypeError, ValueError):
        print(f'error: --shard must be an integer, got {args.shard!r}', file=sys.stderr)
        return EXIT_USAGE
    if not 1 <= shard_id <= REQUIRED_SHARD_COUNT:
        print(
            f'error: --shard must be between 1 and {REQUIRED_SHARD_COUNT}, got {shard_id}',
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        manifest = load_manifest()
    except ManifestError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return EXIT_FAIL

    files = shard_files(manifest, shard_id)
    if not files:
        print(f'error: shard {shard_id} owns no files', file=sys.stderr)
        return EXIT_FAIL

    for path in files:
        print(path)
    return EXIT_OK


# ── summary ───────────────────────────────────────────────────────────────────
def command_summary(args):
    """Print a readable view of the manifest, optionally with live test counts."""
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return EXIT_FAIL

    per_file_counts = {}
    if args.collect:
        try:
            per_file_counts = counts_by_file(collect_node_ids())
        except ManifestError as exc:
            print(f'error: {exc}', file=sys.stderr)
            return EXIT_FAIL

    print('backend CI shard manifest')
    print(f'  schema version      : {manifest["schema_version"]}')
    print(f'  shard count         : {manifest["shard_count"]}')
    print(f'  baseline commit     : {manifest.get("baseline_commit", "unknown")}')
    print(f'  baseline date       : {manifest.get("baseline_date", "unknown")}')
    print(f'  generated for       : {manifest.get("generated_for", "unknown")}')
    print(f'  assignment strategy : {manifest.get("assignment_strategy", "unknown")}')
    print(f'  total files         : {len(manifest_paths(manifest))}')
    print('')
    header = '  shard  files  measured_seconds'
    if args.collect:
        header += '  tests'
    print(header)
    for shard_id in range(1, REQUIRED_SHARD_COUNT + 1):
        files = shard_files(manifest, shard_id)
        row = '  {shard:>5}  {files:>5}  {seconds:>16.1f}'.format(
            shard=shard_id,
            files=len(files),
            seconds=shard_measured_seconds(manifest, shard_id),
        )
        if args.collect:
            row += '  {tests:>5}'.format(
                tests=sum(per_file_counts.get(path, 0) for path in files)
            )
        print(row)
    print('')
    print('Measured seconds are balancing inputs only. They never decide which')
    print('tests run; the file lists do, and verify proves those lists are exact.')
    return EXIT_OK


# ── generate ──────────────────────────────────────────────────────────────────
def command_generate(args):
    """Rebuild a candidate manifest with greedy longest-processing-time.

    Never invoked by CI. Rebalancing is a reviewed change: run this locally,
    read the diff, run ``verify``, then commit.
    """
    try:
        with open(args.timings, encoding='utf-8') as handle:
            timings = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f'error: timings file is not readable JSON: {exc}', file=sys.stderr)
        return EXIT_USAGE
    if not isinstance(timings, dict):
        print('error: timings file must be a JSON object of path -> seconds', file=sys.stderr)
        return EXIT_USAGE

    try:
        node_ids = collect_node_ids()
    except ManifestError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return EXIT_FAIL
    collected_files = sorted(files_from_node_ids(node_ids))

    unknown = [path for path in collected_files if path not in timings]
    if unknown:
        print(
            f'note: {len(unknown)} collected file(s) have no measured timing and '
            'will be balanced as 0.0s:',
            file=sys.stderr,
        )
        for path in unknown[:20]:
            print(f'  {path}', file=sys.stderr)

    # Greedy longest-processing-time: longest first, each file to the shard with
    # the smallest running total. Ties break on relative path so the manifest is
    # byte-reproducible from the same timings.
    ordered = sorted(
        collected_files,
        key=lambda path: (-float(timings.get(path, 0.0)), path),
    )
    shards = {index: [] for index in range(1, REQUIRED_SHARD_COUNT + 1)}
    totals = {index: 0.0 for index in range(1, REQUIRED_SHARD_COUNT + 1)}
    for path in ordered:
        target = min(sorted(totals), key=lambda index: (totals[index], index))
        shards[target].append(path)
        totals[target] += float(timings.get(path, 0.0))

    manifest = {
        'schema_version': 1,
        'shard_count': REQUIRED_SHARD_COUNT,
        'baseline_commit': args.baseline_commit,
        'baseline_date': args.baseline_date or date.today().isoformat(),
        'generated_for': args.generated_for,
        'assignment_strategy': (
            'greedy longest-processing-time using measured per-file runtime, '
            'ties broken by relative path'
        ),
        'timing_note': (
            'measured_seconds values are balancing inputs only. They are not '
            'test-selection authority: the per-shard file lists decide what runs, '
            'and "python scripts/ci_shard.py verify" proves those lists cover live '
            'pytest collection exactly once.'
        ),
        'shards': {
            str(index): {
                'measured_seconds': round(totals[index], 3),
                'files': [
                    {
                        'path': path,
                        'measured_seconds': round(float(timings[path]), 3)
                        if path in timings else None,
                    }
                    for path in sorted(shards[index])
                ],
            }
            for index in range(1, REQUIRED_SHARD_COUNT + 1)
        },
    }

    output = args.output or MANIFEST_PATH
    with open(output, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=False)
        handle.write('\n')

    print(f'wrote {output}', file=sys.stderr)
    for index in range(1, REQUIRED_SHARD_COUNT + 1):
        print(
            f'  shard {index}: {len(shards[index]):>3} files, '
            f'{totals[index]:.1f}s measured',
            file=sys.stderr,
        )
    print('Review the diff, then run: python scripts/ci_shard.py verify', file=sys.stderr)
    return EXIT_OK


# ── entry point ───────────────────────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog='ci_shard.py',
        description='Deterministic backend CI shard ownership.',
    )
    subparsers = parser.add_subparsers(dest='command')

    files_parser = subparsers.add_parser(
        'files', help='print the test files owned by one shard, one per line')
    files_parser.add_argument('--shard', required=True,
                              help=f'shard number, 1..{REQUIRED_SHARD_COUNT}')
    files_parser.set_defaults(handler=command_files)

    verify_parser = subparsers.add_parser(
        'verify', help='prove the manifest partitions live pytest collection exactly once')
    verify_parser.set_defaults(handler=command_verify)

    summary_parser = subparsers.add_parser(
        'summary', help='print a human-readable view of the manifest')
    summary_parser.add_argument(
        '--collect', action='store_true',
        help='also run pytest collection to report per-shard test counts')
    summary_parser.set_defaults(handler=command_summary)

    generate_parser = subparsers.add_parser(
        'generate', help='rebuild a candidate manifest locally (never used by CI)')
    generate_parser.add_argument(
        '--timings', required=True,
        help='JSON object mapping "tests/test_x.py" to measured seconds')
    generate_parser.add_argument(
        '--output', default=None,
        help='where to write the manifest (default: the checked-in manifest)')
    generate_parser.add_argument(
        '--baseline-commit', dest='baseline_commit', default='unknown',
        help='commit the timings were measured on')
    generate_parser.add_argument(
        '--baseline-date', dest='baseline_date', default=None,
        help='date the timings were measured (default: today)')
    generate_parser.add_argument(
        '--generated-for', dest='generated_for',
        default='CI Runtime and Confidence Pass Stage 1',
        help='short provenance note stored in the manifest')
    generate_parser.set_defaults(handler=command_generate)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, 'handler', None):
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    return args.handler(args)


if __name__ == '__main__':
    sys.exit(main())
