"""The one forbidden-content contract for shadow activation artifacts.

Two scans exist for a reason: one before a raw runner summary is staged for
cross-job transport, and one before the final activation evidence is uploaded.
They were written as two shell greps with two copies of the same pattern list,
which is a list that can drift silently — the second copy learns about a new
secret shape only if someone remembers it exists.

There is one list now, and one scanner, and both scans call it.

Contract:

* it never prints matched content — only a filename and a category name, so a
  leaked secret is not re-leaked by the tool that caught it;
* it reports the category rather than the offending line, because the category
  is what an operator needs and the line is what must not travel;
* it fails closed: an unreadable file is unsafe, not skipped.

Standard library only. No Flask, no models, no database, no secrets, no
network. It is invoked from a workflow step, so it must start instantly and
must not depend on application configuration.

    python scripts/scan_forbidden_artifact_content.py FILE [FILE ...]
    python scripts/scan_forbidden_artifact_content.py --directory DIR [--quarantine]

Exit codes: ``0`` every scanned file is safe, ``1`` at least one file is
unsafe, ``2`` the scan itself could not run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


EXIT_SAFE = 0
EXIT_UNSAFE = 1
EXIT_SCAN_FAILED = 2


# Category name -> pattern. Named because a report has to say what kind of
# thing was found without quoting the thing itself.
FORBIDDEN_PATTERNS: dict[str, str] = {
    'postgres_connection_url': r'postgresql://|postgres://',
    'inline_password': r'password=',
    'authorization_header': r'Authorization:',
    'admin_token_header': r'X-Admin-Token',
    'admin_token_variable': r'ADMIN_API_TOKEN',
    'secret_key_variable': r'SECRET_KEY',
    'database_url_variable': r'DATABASE_URL',
    'baseballos_admin_token': r'BASEBALLOS_ADMIN_API_TOKEN',
    'inline_token': r'token=',
    'inline_api_key': r'api_key=|api-key=',
    'inline_secret': r'secret=',
    'python_traceback': r'Traceback \(most recent call last\)',
    'runner_filesystem_path': r'/home/runner/work',
}

# Extensions the activation flow actually produces. Anything else in a scanned
# directory is not evidence and is not transported.
SCANNED_SUFFIXES = ('.json', '.md')

_COMPILED = {
    category: re.compile(pattern)
    for category, pattern in FORBIDDEN_PATTERNS.items()
}


def categories_in(text: str) -> list[str]:
    """Forbidden categories present in ``text``, sorted and deduplicated.

    Returns category names only. The matched substring is deliberately not
    returned, so no caller can accidentally log it.
    """
    return sorted(
        category for category, pattern in _COMPILED.items()
        if pattern.search(text or '')
    )


def scan_file(path) -> list[str]:
    """Categories found in one file. An unreadable file is unsafe."""
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ['unreadable_file']
    return categories_in(text)


def scan_paths(paths, *, quarantine=False) -> dict:
    """Scan an explicit set of files.

    With ``quarantine``, an unsafe file is deleted so it cannot be uploaded by
    a later step. Deletion failure keeps the result unsafe rather than
    downgrading it — a file that could not be removed is still on the runner.
    """
    result = {'scanned': [], 'unsafe': {}, 'quarantined': [], 'safe': True}
    for path in paths:
        path = Path(path)
        result['scanned'].append(path.name)
        categories = scan_file(path)
        if not categories:
            continue
        result['safe'] = False
        result['unsafe'][path.name] = categories
        if quarantine:
            try:
                path.unlink()
                result['quarantined'].append(path.name)
            except OSError:
                pass
    result['scanned'].sort()
    return result


def scan_directory(directory, *, quarantine=False) -> dict:
    """Scan every artifact-shaped file in a directory, non-recursively."""
    directory = Path(directory)
    if not directory.is_dir():
        return {'scanned': [], 'unsafe': {}, 'quarantined': [], 'safe': True,
                'directory_missing': True}
    paths = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix in SCANNED_SUFFIXES
    )
    return scan_paths(paths, quarantine=quarantine)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Scan activation artifacts for forbidden content. Reports a '
            'filename and a category; never the matched content.'
        )
    )
    parser.add_argument('files', nargs='*', help='Explicit files to scan.')
    parser.add_argument(
        '--directory',
        help='Scan every .json and .md file in this directory instead.',
    )
    parser.add_argument(
        '--quarantine', action='store_true',
        help='Delete unsafe files so a later step cannot upload them.',
    )
    parser.add_argument(
        '--label', default='Artifact',
        help='Annotation title used in workflow error output.',
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if bool(args.directory) == bool(args.files):
        print('::error::Provide either files or --directory, not both.')
        return EXIT_SCAN_FAILED

    if args.directory:
        result = scan_directory(args.directory, quarantine=args.quarantine)
    else:
        result = scan_paths(args.files, quarantine=args.quarantine)

    for filename, categories in sorted(result['unsafe'].items()):
        action = (
            'It was quarantined and NOT uploaded.'
            if filename in result['quarantined']
            else 'It must NOT be uploaded.'
        )
        print(
            f'::error title={args.label}::{filename} matched forbidden content '
            f'({", ".join(categories)}). {action}'
        )

    if result['safe']:
        print(f'{len(result["scanned"])} file(s) passed the forbidden-content scan.')
        return EXIT_SAFE
    return EXIT_UNSAFE


if __name__ == '__main__':
    raise SystemExit(main())
