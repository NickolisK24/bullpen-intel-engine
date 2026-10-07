"""Read-only truth certification of one trusted Dashboard publication.

Operator command, run by the manual publication truth certification workflow:

    python scripts/certify_publication_truth.py --snapshot-id 4496 \
        --output-dir ../artifacts/publication-truth-certification

It is read-only three ways: every PostgreSQL connection starts with
default_transaction_read_only=on (applied when the command runs, never at
import), the transaction is set READ ONLY, and a bounded write probe must be
REFUSED before any certification read. Nothing is ever written; the session is
rolled back at the end.

Exit codes: 0 the certification completed (a FAIL verdict is a result, not an
error), 2 the invocation was refused before any evidence was read, 3 read-only
operation could not be proven and nothing was certified, 1 the certification
itself failed.
"""

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

READ_ONLY_PGOPTION = '-c default_transaction_read_only=on'

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_READ_ONLY_UNPROVEN = 3

SCHEMA_VERSION = '2'
DOCUMENT_KIND = 'publication_truth_certification'
REFUSAL_BASENAME = 'certification-refused'

REASON_READ_ONLY_UNPROVEN = 'read_only_unproven'
REASON_SNAPSHOT_NOT_FOUND = 'snapshot_not_found'
REASON_NOT_TRUSTED_PUBLICATION = 'snapshot_not_trusted_publication'

NON_AUTHORIZATION_STATEMENT = (
    'This certification is read-only. It does not authorize publishing or '
    'promoting a snapshot, resolving sync failures, recalculating fatigue, '
    'repairing roster or schedule authority, changing methodology or '
    'thresholds, or any production mutation. A FAIL verdict is evidence for '
    'review, not an instruction.'
)


def _configure_read_only_process():
    """Set the operator environment for this process only, never at import."""
    os.environ['AUTO_SYNC'] = 'false'
    options = os.environ.get('PGOPTIONS', '')
    if READ_ONLY_PGOPTION not in options:
        os.environ['PGOPTIONS'] = f'{options} {READ_ONLY_PGOPTION}'.strip()


def _positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('must be a positive integer') from exc
    if number <= 0 or str(number) != str(value).strip():
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--snapshot-id', type=_positive_int, required=True,
                        help='The stored Dashboard snapshot to certify.')
    parser.add_argument('--output-dir',
                        help='Write the JSON evidence and a Markdown summary here.')
    parser.add_argument('--allow-non-postgres', action='store_true',
                        help='Skip the read-only proof (local SQLite only).')
    return parser.parse_args(argv)


def output_basename(snapshot_id):
    return f'certification-{snapshot_id}'


def _run_identity():
    return {
        'commit_sha': os.environ.get('GITHUB_SHA'),
        'workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
    }


def _write(target, basename, document, markdown):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / f'{basename}.json'
    json_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    (target / f'{basename}.md').write_text(markdown, encoding='utf-8')
    return json_path


def _refusal(args, *, exit_code, reason_code, message, read_only_proof=None):
    """Report a refusal on stderr and, when asked, as a structured document."""
    print(f'refusing: {message}', file=sys.stderr)
    if args.output_dir:
        document = {
            'document': DOCUMENT_KIND,
            'schema_version': SCHEMA_VERSION,
            'mode': 'refused',
            'exit_code': exit_code,
            'reason_code': reason_code,
            'message': message,
            'inputs': {'snapshot_id': args.snapshot_id},
            'read_only_proof': read_only_proof,
            'run': _run_identity(),
            'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        }
        _write(args.output_dir, REFUSAL_BASENAME, document, '\n'.join([
            '# Publication truth certification: refused',
            '',
            f'- Reason: {reason_code}',
            f'- Exit code: {exit_code}',
            f'- {message}',
            '',
            NON_AUTHORIZATION_STATEMENT,
            '',
        ]))
    return exit_code


def _cell(value):
    return '' if value is None else str(value)


def _board_cell(board):
    if not board:
        return ''
    return f"{board['count']} ({board['monitor_stale']}/{board['monitor_missing']})"


def markdown_summary(document):
    """Render the certification document. It derives nothing new."""
    report = document['certification']
    subject = report['subject']
    proof = document['read_only_proof'] or {}
    lines = [
        '# Publication truth certification',
        '',
        f"- Snapshot: {subject['snapshot_id']} (sync run {subject['sync_run_id']})",
        f"- Data through: {subject['data_through']}",
        f"- Availability reference date: {subject['availability_reference_date']}",
        f"- Membership date: {subject['membership_date']}",
        f"- Write probe refused: {proof.get('read_only_probe_refused')}",
        f"- Team State sidecars bound: {subject['team_state_sidecars_bound']}",
        f"- League verdict: {report['league_verdict']}",
        "- Domains: " + ', '.join(
            f'{name}={verdict}' for name, verdict in sorted(report['domains'].items())),
        f"- Teams: {report['teams_passed']} PASS, {report['teams_conditional']} "
        f"CONDITIONAL, {report['teams_failed']} FAIL",
        '',
        '## Arm attribution and Team State',
        '',
        'Team State population counts (the board column is the Team Board\'s own '
        'On Watch group, the count behind its public On Watch sentence).',
        '',
        '| team | state | active | clean | on watch | workload | stale | missing | '
        'fetch fail | incomplete | limited | avoid+unavail | low conf | reproduced | '
        'hypothetical as clean | hypothetical excluded | board on watch (stale/missing) |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- '
        '| --- | --- | --- | --- |',
    ]
    for team_id, attribution in report['arm_attribution'].items():
        counts = attribution['counts']
        state = report['team_state'][team_id]
        hypothetical = state['hypothetical']
        lines.append(' | '.join([
            f"| {attribution['team']}", _cell(state.get('public_state')),
            _cell(counts['active_bullpen_count']), _cell(counts['clean']),
            _cell(counts['monitor_total']), _cell(counts['monitor_workload']),
            _cell(counts['monitor_stale']), _cell(counts['monitor_missing']),
            _cell(counts['monitor_fetch_failure']), _cell(counts['monitor_incomplete']),
            _cell(counts['limited']), _cell(counts['avoid'] + counts['unavailable']),
            _cell(counts['low_confidence']), _cell(state['reproduction_matches_published']),
            _cell(hypothetical['evidence_quality_monitor_as_clean']),
            _cell(hypothetical['evidence_quality_monitor_excluded']),
            _board_cell(attribution.get('board_on_watch_group')) + ' |',
        ]))
    lines += [
        '',
        'The two hypothetical columns are HYPOTHETICAL / AUDIT ONLY. '
        + report['hypothetical_notice'],
        '',
        '## Roster and workload',
        '',
        '| team | roster | expected | published | missing | extra | duplicate | '
        'wrong team | workload | arms | facts | mismatches |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for team_id, roster in report['roster'].items():
        workload = report['workload'][team_id]
        lines.append(
            f"| {roster['team']} | {roster['verdict']} | {roster['expected_member_count']} | "
            f"{roster['active_bullpen_count']} | {len(roster['missing'])} | "
            f"{len(roster['extra'])} | {len(roster['duplicate'])} | "
            f"{len(roster['wrong_team'])} | {workload['verdict']} | "
            f"{workload['arms_checked']} | {workload['facts_compared']} | "
            f"{len(workload['mismatches'])} |"
        )
    lines += [
        '',
        '## Postseason relief work (last 7 days)',
        '',
        '| team | relief appearances | postseason appearances | postseason pitches | '
        'arms with postseason work |',
        '| --- | --- | --- | --- | --- |',
    ]
    for team_id, postseason in report['postseason_workload'].items():
        window = postseason['windows']['last_7_days']
        if not window['relief_appearances']:
            continue
        lines.append(
            f"| {postseason['team']} | {window['relief_appearances']} | "
            f"{window['postseason_relief_appearances']} | "
            f"{window['postseason_relief_pitches']} | "
            f"{window['arms_with_postseason_relief']} |"
        )
    lines += [
        '',
        f"Findings: {len(report['findings'])}. Not covered: "
        + '; '.join(report['not_covered']) + '.',
        '',
        NON_AUTHORIZATION_STATEMENT,
        '',
    ]
    return '\n'.join(lines)


def _is_trusted_publication(snapshot):
    from services import public_serving_authority as psa
    from services.dashboard_snapshot import SNAPSHOT_TYPE_BULLPEN_DASHBOARD

    payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
    return (
        snapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD
        and isinstance(payload.get(psa.TEAM_BOARD_PACKAGE_KEY), dict)
    )


def build_app():
    from app import create_app
    return create_app()


def main(argv=None):
    args = _parse_args(argv)

    _configure_read_only_process()
    app = build_app()
    from models.dashboard_snapshot import DashboardSnapshot
    from services import publication_truth_certification as certification
    from services.noop_qualification_candidate_audit import (
        ReadOnlyNotEnforced,
        ReadOnlyProbeViolation,
        enforce_read_only,
    )
    from utils.db import db

    with app.app_context():
        try:
            if db.session.get_bind().dialect.name == 'postgresql':
                try:
                    read_only_proof = enforce_read_only(db.session)
                except ReadOnlyProbeViolation as violation:
                    db.session.rollback()
                    return _refusal(
                        args, exit_code=EXIT_READ_ONLY_UNPROVEN,
                        reason_code=REASON_READ_ONLY_UNPROVEN,
                        message='the bounded write probe was ACCEPTED; nothing was certified',
                        read_only_proof=dict(violation.evidence),
                    )
                except ReadOnlyNotEnforced:
                    db.session.rollback()
                    return _refusal(
                        args, exit_code=EXIT_READ_ONLY_UNPROVEN,
                        reason_code=REASON_READ_ONLY_UNPROVEN,
                        message='read-only operation could not be proven',
                    )
            elif args.allow_non_postgres:
                read_only_proof = {
                    'read_only_probe_refused': None, 'protection': 'none_local_only'}
            else:
                return _refusal(
                    args, exit_code=EXIT_READ_ONLY_UNPROVEN,
                    reason_code=REASON_READ_ONLY_UNPROVEN,
                    message='read-only cannot be proven on this database',
                )

            snapshot = db.session.get(DashboardSnapshot, args.snapshot_id)
            if snapshot is None:
                return _refusal(
                    args, exit_code=EXIT_REFUSED, reason_code=REASON_SNAPSHOT_NOT_FOUND,
                    message=f'snapshot {args.snapshot_id} not found',
                    read_only_proof=read_only_proof,
                )
            if not _is_trusted_publication(snapshot):
                return _refusal(
                    args, exit_code=EXIT_REFUSED,
                    reason_code=REASON_NOT_TRUSTED_PUBLICATION,
                    message=(
                        f'snapshot {args.snapshot_id} is not a trusted Dashboard '
                        'publication carrying Team Board packages'
                    ),
                    read_only_proof=read_only_proof,
                )
            report = certification.certify_snapshot(snapshot)
        finally:
            db.session.rollback()

    document = {
        'document': DOCUMENT_KIND,
        'schema_version': SCHEMA_VERSION,
        'mode': 'certified',
        'read_only_proof': read_only_proof,
        'run': _run_identity(),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        'certification': report,
    }
    summary = {
        'snapshot_id': report['subject']['snapshot_id'],
        'league_verdict': report['league_verdict'],
        'domains': report['domains'],
        'teams_passed': report['teams_passed'],
        'teams_conditional': report['teams_conditional'],
        'teams_failed': report['teams_failed'],
    }
    if args.output_dir:
        path = _write(
            args.output_dir, output_basename(args.snapshot_id), document,
            markdown_summary(document),
        )
        print(f'Wrote {path.name}')
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
