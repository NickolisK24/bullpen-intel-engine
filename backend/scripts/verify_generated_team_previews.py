#!/usr/bin/env python3
"""Delivery verification for the generated routed-team preview pages (CI-003 / #598).

WHAT THIS IS NOT
----------------
This script does not decide baseball meaning. It never maps a Team State, never
judges state eligibility, never selects a snapshot, never establishes
data-through authority, and never writes a word of public copy. Every one of
those remains owned by ``backend/scripts/export_team_story_pages.py`` and
``backend/services/team_story_previews.py``. Re-implementing any of it here
would create a second publication authority, which is precisely what #598 is
meant to avoid.

WHAT THIS IS
------------
A fail-closed DELIVERY gate. The exporter already declares, in its structured
result, exactly what it believes it published: how many teams, which files,
which fallback, which trusted snapshot, which teams were withheld. This script
proves the filesystem agrees with that declaration before the tree is allowed to
become a commit on ``main``.

The invariants are plumbing invariants, and each one names a way generated
publication can silently go wrong:

  1. the exporter declared success at all;
  2. its own counts agree with each other (teams == previews == files written);
  3. every declared file exists, is a regular file, and is not empty;
  4. the invalid-team fallback exists and is still the invalid-team page;
  5. the directory holds exactly the declared set — nothing silently missing,
     nothing stale left behind from an earlier run;
  6. every page carries a representation receipt;
  7. every page making a dated claim carries the full receipt set;
  8. every snapshot receipt on disk names the ONE trusted publication the
     exporter says this run published from — two clocks in one run is the
     failure #594 exists to prevent, and this proves it did not happen;
  9. the withheld set on disk is exactly the withheld set the exporter declared.

Reading receipts back out of the emitted HTML is deliberate: the point is to
verify the ARTIFACT, not to re-ask the generator what it intended. The values
used for commit provenance are taken from the structured result, never scraped.

The script is read-only with respect to generated output. It writes only the
digest and summary files it is explicitly asked to write.

Exit codes
----------
  0  delivery proven
  1  delivery invariant violated  (fail closed — do not publish)
  2  the verification itself could not run (missing/malformed inputs)
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path


EXIT_OK = 0
EXIT_DELIVERY_VIOLATION = 1
EXIT_CANNOT_VERIFY = 2

REPRESENTATION_DATED_READ = 'dated_team_read'
REPRESENTATION_WITHHELD = 'withheld'
REPRESENTATION_INVALID_TEAM = 'invalid_team'

# Receipts every dated claim must carry. A dated page missing any of these is a
# page that states a baseball date without saying where the date came from.
DATED_RECEIPT_KEYS = (
    'generated-at',
    'data-through',
    'snapshot-id',
    'authority-contract',
)

_META_PATTERN = re.compile(
    r'<meta\s+name="baseballos:(?P<key>[a-z-]+)"\s+content="(?P<value>[^"]*)"\s*/>'
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Verify that the generated routed-team preview files on disk match '
            'the exporter\'s declared result. Delivery integrity only.'
        )
    )
    parser.add_argument(
        '--export-result',
        required=True,
        help='Path to the JSON result printed by export_team_story_pages.py.',
    )
    parser.add_argument(
        '--output-root',
        required=True,
        help='Frontend public root the exporter wrote into (contains team/).',
    )
    parser.add_argument(
        '--digest-out',
        help=(
            'Write a deterministic sha256 digest of every generated file here. '
            'Re-running with the same flag after the frontend gate and '
            'comparing the two digests is what proves the validated bytes are '
            'the bytes that get staged.'
        ),
    )
    parser.add_argument(
        '--summary-out',
        help='Write a non-secret JSON verification summary here.',
    )
    return parser.parse_args(argv)


def _read_authority_meta(text):
    """Return the ``baseballos:*`` receipts declared by one generated page."""
    return {
        match.group('key'): html.unescape(match.group('value'))
        for match in _META_PATTERN.finditer(text)
    }


def _load_export_result(path):
    raw = Path(path).read_text(encoding='utf-8')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('export result is not a JSON object')
    return result


def _relative(path, repo_root):
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return candidate.as_posix()


def verify(export_result, output_root, repo_root):
    """Return ``(violations, facts)`` for one generated publication."""
    violations = []
    facts = {}

    status = export_result.get('status')
    facts['export_status'] = status
    if status != 'ok':
        violations.append(
            f'exporter did not declare success (status={status!r}); '
            'nothing may be published from this run'
        )
        # Everything below reads the exporter's declaration. Without a
        # successful one there is nothing coherent left to check.
        return violations, facts

    output = export_result.get('output')
    if not isinstance(output, dict):
        violations.append('export result carries no output object')
        return violations, facts

    teams = export_result.get('teams')
    previews = export_result.get('previews')
    count = output.get('count')
    facts['teams'] = teams
    facts['previews'] = previews
    facts['generated_file_count'] = count

    # The exporter owns HOW MANY teams there should be. This only proves its own
    # three counts agree, so a partial write cannot pass as a complete one.
    if not isinstance(count, int) or count < 1:
        violations.append(f'output.count is not a positive integer (got {count!r})')
    if teams != previews or previews != count:
        violations.append(
            f'exporter counts disagree: teams={teams!r} previews={previews!r} '
            f'output.count={count!r}'
        )

    snapshot_id = export_result.get('publication_snapshot_id')
    data_through = export_result.get('publication_data_through')
    facts['snapshot_id'] = snapshot_id
    facts['data_through'] = data_through
    facts['generated_at'] = export_result.get('generated_at')
    if snapshot_id in (None, ''):
        violations.append('export result names no trusted publication snapshot id')
    if data_through in (None, ''):
        violations.append('export result names no publication data-through date')

    declared_files = output.get('files')
    fallback = output.get('fallback')
    if not isinstance(declared_files, list) or not declared_files:
        violations.append('output.files is missing or empty')
        declared_files = []
    if not fallback:
        violations.append('output.fallback is missing')

    team_root = Path(output_root) / 'team'
    facts['team_page_root'] = _relative(team_root, repo_root)
    if not team_root.is_dir():
        violations.append(f'generated team page root does not exist: {team_root}')
        return violations, facts

    declared = [Path(entry) for entry in declared_files]
    if fallback:
        declared.append(Path(fallback))

    # (3)(4) every declared file is really there, and really has content.
    for path in declared:
        if not path.is_file():
            violations.append(f'declared generated file is missing: {path}')
        elif path.stat().st_size == 0:
            violations.append(f'declared generated file is empty: {path}')

    # (5) nothing silently missing, nothing stale. A directory left behind by an
    # earlier run would keep serving an old claim at a live public route.
    on_disk = {p.resolve() for p in team_root.glob('*/index.html')}
    fallback_path = (team_root / 'index.html').resolve()
    if fallback_path.exists():
        on_disk.add(fallback_path)
    expected = {p.resolve() for p in declared if p.exists()}
    for stale in sorted(on_disk - expected):
        violations.append(
            f'unexpected generated file present on disk: {_relative(stale, repo_root)}'
        )

    # (6)(7)(8)(9) receipts.
    observed_snapshot_ids = set()
    withheld_on_disk = []
    dated_pages = 0
    for path in declared:
        if not path.is_file():
            continue
        meta = _read_authority_meta(path.read_text(encoding='utf-8'))
        relative = _relative(path, repo_root)
        representation = meta.get('representation')

        if not representation:
            violations.append(f'{relative}: no baseballos:representation receipt')
            continue

        if path.resolve() == fallback_path:
            if representation != REPRESENTATION_INVALID_TEAM:
                violations.append(
                    f'{relative}: invalid-team fallback declares '
                    f'representation={representation!r}'
                )
            continue

        if representation == REPRESENTATION_WITHHELD:
            withheld_on_disk.append(path.parent.name)
        elif representation == REPRESENTATION_DATED_READ:
            dated_pages += 1
            for key in DATED_RECEIPT_KEYS:
                if not meta.get(key):
                    violations.append(
                        f'{relative}: dated claim is missing the '
                        f'baseballos:{key} receipt'
                    )
        else:
            violations.append(
                f'{relative}: unrecognised representation {representation!r}'
            )

        if meta.get('snapshot-id'):
            observed_snapshot_ids.add(meta['snapshot-id'])

    facts['dated_pages'] = dated_pages
    facts['withheld_pages'] = sorted(withheld_on_disk)
    facts['observed_snapshot_ids'] = sorted(observed_snapshot_ids)

    # ONE trusted publication per run. Two snapshot ids across one generated set
    # means two baseball clocks were combined, which is the exact conflation the
    # generator's own contract forbids.
    if len(observed_snapshot_ids) > 1:
        violations.append(
            'generated pages cite more than one publication snapshot: '
            f'{sorted(observed_snapshot_ids)}'
        )
    if snapshot_id not in (None, '') and observed_snapshot_ids:
        expected_snapshot = {str(snapshot_id)}
        if observed_snapshot_ids != expected_snapshot:
            violations.append(
                f'generated pages cite snapshot(s) {sorted(observed_snapshot_ids)} '
                f'but the exporter published from snapshot {snapshot_id!r}'
            )

    declared_withheld = export_result.get('withheld_teams')
    if isinstance(declared_withheld, list):
        if sorted(declared_withheld) != sorted(withheld_on_disk):
            violations.append(
                f'withheld set on disk {sorted(withheld_on_disk)} does not match '
                f'the exporter declaration {sorted(declared_withheld)}'
            )

    return violations, facts


def build_digest(export_result, output_root, repo_root):
    """Deterministic sha256 digest of the generated files, sorted by path.

    Recomputing this after the frontend gate and diffing it against the digest
    taken before the gate is what makes "the validated tree is the committed
    tree" a proof rather than an assertion.
    """
    output = export_result.get('output') or {}
    paths = [Path(entry) for entry in (output.get('files') or [])]
    fallback = output.get('fallback')
    if fallback:
        paths.append(Path(fallback))

    entries = []
    for path in sorted(paths, key=lambda item: _relative(item, repo_root)):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({'path': _relative(path, repo_root), 'sha256': digest})
    return entries


def main(argv=None):
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]

    try:
        export_result = _load_export_result(args.export_result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            '::error title=Generated Preview Delivery::Could not read the '
            f'exporter result ({exc}). Delivery is UNPROVEN.'
        )
        return EXIT_CANNOT_VERIFY

    violations, facts = verify(export_result, args.output_root, repo_root)
    digest = build_digest(export_result, args.output_root, repo_root)

    if args.digest_out:
        digest_path = Path(args.digest_out)
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(
            json.dumps(digest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
        )

    summary = {
        'result': 'pass' if not violations else 'fail',
        'violations': violations,
        'digest_file_count': len(digest),
        **facts,
    }
    if args.summary_out:
        summary_path = Path(args.summary_out)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8'
        )

    if violations:
        for violation in violations:
            print(f'::error title=Generated Preview Delivery::{violation}')
        print(
            '::error title=Generated Preview Delivery::Delivery verification '
            'FAILED. Nothing is committed or published; the previously published '
            'pages remain in place and continue to state their own baseball date.'
        )
        return EXIT_DELIVERY_VIOLATION

    print(
        'Generated preview delivery verified: '
        f"{facts.get('generated_file_count')} team page(s) "
        f"({facts.get('dated_pages')} dated, "
        f"{len(facts.get('withheld_pages') or [])} withheld) "
        f"from snapshot {facts.get('snapshot_id')}, "
        f"data through {facts.get('data_through')}."
    )
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
