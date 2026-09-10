"""Gate `npm audit --omit=dev` output against the reviewed accepted-risk contract.

The point of this script is narrow: a NEW production dependency advisory must
turn CI red, and the only advisories allowed past are the exact ones a human
reviewed, time-boxed, and wrote down.

It is deliberately strict in both directions. An advisory nobody has reviewed
fails. So does an acceptance that has expired, that names the wrong package, that
is duplicated, that is missing a field, whose decision record has vanished, or
that no longer corresponds to anything npm reports. That last one matters: a
solved advisory must have its exception DELETED, because an exception left lying
around would silently suppress the same advisory if it ever came back.

Only production findings are evaluated. Dev/build advisories are surfaced
elsewhere as information and must never appear in the accepted-risk file.

npm audit JSON shape (auditReportVersion 2, npm 10)
--------------------------------------------------
    {
      "auditReportVersion": 2,
      "vulnerabilities": {
        "<row package>": {
          "name": ..., "severity": ..., "isDirect": ..., "range": ...,
          "via": [
            {"source": 1124268, "name": "react-router", "title": ...,
             "url": "https://github.com/advisories/GHSA-wrjc-x8rr-h8h6", ...},
            "react-router"          <- a plain string means "vulnerable *through*
                                       this package", not a separate advisory
          ],
          ...
        }
      },
      "metadata": {"vulnerabilities": {"total": N, ...}}
    }

So an advisory is a dict entry in `via`; its identifier is the last path segment
of `url`, and the package it is *about* is `via["name"]` — which is not always
the row key. String entries in `via` are dependency propagation and carry no
advisory of their own.

Usage
-----
    python scripts/verify_dependency_audit.py \
        --audit npm-audit-prod.json \
        --accepted ../.github/dependency-audit-accepted.json \
        --repo-root ..

    --today YYYY-MM-DD  override the reference date (tests only; CI uses UTC now)

Exit codes
----------
    0  every reported advisory is covered by a valid acceptance (or none reported)
    1  the gate refuses: unknown, expired, stale, mismatched or malformed acceptance
    2  the inputs could not be read or parsed at all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

PRODUCTION_SECTION = 'frontend'

REQUIRED_FIELDS = (
    'advisory_id',
    'package',
    'expires_on',
    'tracking_issue',
    'decision_record',
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_INPUT_ERROR = 2


class InputError(Exception):
    """The audit report or the accepted-risk file could not be read or parsed."""


def _load_json(path, label):
    if not os.path.isfile(path):
        raise InputError(f'{label} not found: {path}')
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except json.JSONDecodeError as error:
        raise InputError(f'{label} is not valid JSON ({path}): {error}') from error
    except OSError as error:
        raise InputError(f'{label} could not be read ({path}): {error}') from error


def advisory_id_from_url(url):
    """The GHSA id is the last path segment of the advisory URL."""
    return (url or '').rstrip('/').rsplit('/', 1)[-1].strip()


def extract_reported_advisories(report):
    """Return {advisory_id: {'package': str, 'severity': str, 'rows': sorted list}}.

    Raises InputError when the payload is not a recognisable npm audit report, so
    a truncated or error-shaped file can never be mistaken for a clean audit.
    """
    if not isinstance(report, dict):
        raise InputError('audit report is not a JSON object')
    if 'vulnerabilities' not in report:
        raise InputError(
            "audit report has no 'vulnerabilities' key; refusing to treat an "
            'unrecognised payload as a clean audit'
        )
    vulnerabilities = report['vulnerabilities']
    if not isinstance(vulnerabilities, dict):
        raise InputError("audit report 'vulnerabilities' is not an object")

    advisories = {}
    for row_name, row in vulnerabilities.items():
        if not isinstance(row, dict):
            raise InputError(f'audit entry for {row_name!r} is not an object')
        for via in row.get('via', []):
            if not isinstance(via, dict):
                # A plain string is dependency propagation, not an advisory.
                continue
            advisory_id = advisory_id_from_url(via.get('url'))
            if not advisory_id:
                raise InputError(
                    f'advisory under {row_name!r} has no resolvable url/id'
                )
            entry = advisories.setdefault(
                advisory_id,
                {
                    'package': via.get('name') or row_name,
                    'severity': via.get('severity') or row.get('severity'),
                    'rows': set(),
                },
            )
            entry['rows'].add(row_name)
    for entry in advisories.values():
        entry['rows'] = sorted(entry['rows'])
    return advisories


def load_accepted(payload, path):
    """Validate the accepted-risk payload and return its production entries."""
    if not isinstance(payload, dict):
        raise InputError(f'accepted-risk file is not a JSON object: {path}')
    entries = payload.get(PRODUCTION_SECTION, [])
    if not isinstance(entries, list):
        raise InputError(
            f"accepted-risk '{PRODUCTION_SECTION}' section is not a list: {path}"
        )
    for entry in entries:
        if not isinstance(entry, dict):
            raise InputError(f'accepted-risk entry is not an object: {entry!r}')
    return entries


def _parse_expiry(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def evaluate(reported, accepted_entries, today, repo_root):
    """Return (violations, accepted_ids). Empty violations means the gate passes."""
    violations = []
    seen_ids = set()
    valid_acceptances = {}

    for entry in accepted_entries:
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            violations.append(
                'accepted-risk entry {!r} is missing required field(s): {}'.format(
                    entry.get('advisory_id') or entry, ', '.join(missing)
                )
            )
            continue

        advisory_id = entry['advisory_id']

        # Rule G — one advisory, one entry.
        if advisory_id in seen_ids:
            violations.append(
                f'{advisory_id}: listed more than once in the accepted-risk file'
            )
            continue
        seen_ids.add(advisory_id)

        # Rule E — the expiry must be a real date.
        expires_on = _parse_expiry(entry['expires_on'])
        if expires_on is None:
            violations.append(
                f'{advisory_id}: expires_on {entry["expires_on"]!r} is not a '
                'YYYY-MM-DD date'
            )
            continue

        # Rule F — the human decision record must exist.
        record = entry['decision_record']
        if not os.path.isfile(os.path.join(repo_root, record)):
            violations.append(
                f'{advisory_id}: decision record not found in the repository: {record}'
            )
            continue

        # Rule C — an acceptance is invalid from 00:00 UTC on expires_on.
        if today >= expires_on:
            violations.append(
                f'{advisory_id}: acceptance expired on {expires_on.isoformat()} '
                f'(today is {today.isoformat()}). Re-review it, or remove the '
                f'advisory by upgrading. See issue #{entry["tracking_issue"]}.'
            )
            continue

        # Rule D — an acceptance for an advisory nobody reports is stale.
        if advisory_id not in reported:
            violations.append(
                f'{advisory_id}: accepted but no longer reported by npm audit. '
                'Delete the stale entry so it cannot silently suppress this '
                'advisory if it returns.'
            )
            continue

        # Rule B — an advisory id must not suppress an unrelated package.
        reported_package = reported[advisory_id]['package']
        if reported_package != entry['package']:
            violations.append(
                f'{advisory_id}: accepted for package {entry["package"]!r} but '
                f'npm reports it against {reported_package!r}'
            )
            continue

        valid_acceptances[advisory_id] = entry

    # Rule A — anything reported and not validly accepted fails.
    for advisory_id in sorted(reported):
        if advisory_id not in valid_acceptances:
            if advisory_id in seen_ids:
                # Already reported above with a specific reason.
                continue
            info = reported[advisory_id]
            violations.append(
                f'{advisory_id}: NEW production advisory against '
                f'{info["package"]!r} (severity {info["severity"]}) with no '
                'reviewed acceptance. Remediate it, or add a reviewed, '
                'time-boxed entry to .github/dependency-audit-accepted.json.'
            )

    return violations, valid_acceptances


def render_report(reported, accepted_entries, valid_acceptances, violations, today):
    lines = []
    lines.append('Frontend production audit (npm audit --omit=dev)')
    lines.append(f'  reference date        : {today.isoformat()} (UTC)')
    lines.append(f'  reported advisories   : {len(reported)}')
    lines.append(f'  accepted entries      : {len(accepted_entries)}')
    lines.append(f'  valid acceptances     : {len(valid_acceptances)}')
    lines.append(f'  violations            : {len(violations)}')
    lines.append('')

    if reported:
        lines.append('  Reported:')
        for advisory_id in sorted(reported):
            info = reported[advisory_id]
            state = 'accepted' if advisory_id in valid_acceptances else 'NOT ACCEPTED'
            expiry = ''
            if advisory_id in valid_acceptances:
                expiry = f', expires {valid_acceptances[advisory_id]["expires_on"]}'
            lines.append(
                f'    - {advisory_id}  {info["package"]}  '
                f'({info["severity"]}) [{state}{expiry}]'
            )
        lines.append('')

    if violations:
        lines.append('  REFUSED:')
        for violation in violations:
            lines.append(f'    - {violation}')
        lines.append('')
        lines.append('  Result: FAIL')
    elif reported:
        lines.append(
            f'  Result: PASS WITH {len(valid_acceptances)} REVIEWED EXCEPTION(S)'
        )
        lines.append(
            '  Note: this is not a clean audit. Every advisory above is a known, '
            'time-boxed, reviewed exception.'
        )
    else:
        lines.append('  Result: PASS (no production advisories reported)')

    return '\n'.join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            'Verify npm production audit output against the reviewed '
            'accepted-risk contract.'
        )
    )
    parser.add_argument(
        '--audit',
        required=True,
        help='path to `npm audit --omit=dev --json` output',
    )
    parser.add_argument(
        '--accepted',
        required=True,
        help='path to the accepted-risk JSON contract',
    )
    parser.add_argument(
        '--repo-root',
        default='.',
        help='repository root, used to resolve decision_record paths',
    )
    parser.add_argument(
        '--today',
        default=None,
        help=(
            'reference date as YYYY-MM-DD. Defaults to the current UTC date; '
            'set explicitly by tests so expiry behaviour is deterministic.'
        ),
    )
    return parser


def resolve_today(value):
    if value is None:
        return datetime.now(timezone.utc).date()
    parsed = _parse_expiry(value)
    if parsed is None:
        raise InputError(f'--today {value!r} is not a YYYY-MM-DD date')
    return parsed


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        today = resolve_today(args.today)
        report = _load_json(args.audit, 'audit report')
        accepted_payload = _load_json(args.accepted, 'accepted-risk file')
        reported = extract_reported_advisories(report)
        accepted_entries = load_accepted(accepted_payload, args.accepted)
    except InputError as error:
        print(f'dependency-audit gate: INPUT ERROR: {error}', file=sys.stderr)
        return EXIT_INPUT_ERROR

    violations, valid_acceptances = evaluate(
        reported, accepted_entries, today, args.repo_root
    )
    print(
        render_report(
            reported, accepted_entries, valid_acceptances, violations, today
        )
    )
    return EXIT_REFUSED if violations else EXIT_OK


if __name__ == '__main__':  # pragma: no cover - exercised through tests
    sys.exit(main())
