"""Stage the shadow cycle summary for transport to the observer job.

GitHub Actions jobs do not share a filesystem. The publication-critical job
writes the raw cycle summary; the activation validator now runs in a separate
observer job. Something has to carry the evidence across, and that carrier is
the one place where a raw production artifact could escape the runner.

So the staging rule is deliberate: **nothing is uploaded from the directory the
runner wrote to.** The raw summary is scanned first, copied into an empty
staging directory only if it passes, and only the staging directory is ever
uploaded. Uploading the source directory would mean a bug in the scanner
becomes a leak; uploading a staging directory means a bug in the scanner
becomes an empty handoff, which the observer treats as unproven.

Metadata is always written, including on every failure path. A handoff that
says nothing and a handoff that says "the summary was missing" look identical
to an artifact consumer otherwise, and only one of those is diagnosable.

This runs inside the publication-critical job, so it is transport only: it must
never be able to turn a successful publication red. The caller marks it
non-blocking; this script's job is to make sure that whatever happened is
described accurately.

Standard library only. No Flask, no models, no database, no secrets, no
network.

Exit codes: ``0`` a ready handoff was staged, ``1`` staged but not ready (the
observer will fail), ``2`` the preparation itself could not run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.scan_forbidden_artifact_content import scan_file  # noqa: E402


SCHEMA_VERSION = '1'
METADATA_FILENAME = 'handoff-metadata.json'

CYCLE_DAILY = 'daily'
CYCLE_POSTGAME = 'postgame'
CYCLE_KINDS = (CYCLE_DAILY, CYCLE_POSTGAME)

SUMMARY_FILENAME = {
    CYCLE_DAILY: 'daily-sync-summary.json',
    CYCLE_POSTGAME: 'postgame-sync-summary.json',
}

STATUS_READY = 'ready'
STATUS_SUMMARY_MISSING = 'summary_missing'
STATUS_ARTIFACT_UNSAFE = 'artifact_unsafe'
STATUS_INVALID_METADATA = 'invalid_metadata'
STATUS_PREPARATION_ERROR = 'preparation_error'

HANDOFF_STATUSES = (
    STATUS_READY, STATUS_SUMMARY_MISSING, STATUS_ARTIFACT_UNSAFE,
    STATUS_INVALID_METADATA, STATUS_PREPARATION_ERROR,
)

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_PREPARATION_FAILED = 2


def _normalized_runner_exit_code(raw):
    """A runner exit code the observer can pass to the validator.

    An absent or non-numeric value is not coerced to success. It becomes
    ``None``, which makes the handoff not-ready — the validator's contract
    depends on knowing what the runner actually did.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def build_metadata(
    *, run_id, repository_sha, cycle_kind, runner_exit_code,
    expected_summary_filename, summary_present, preupload_scan_safe,
    handoff_status,
):
    """The safe description of what crossed the job boundary.

    Deliberately narrow: identifiers the workflow already exposes, the cycle,
    the runner's exit code, and three booleans. No environment dump, no
    exception text, no path, no URL, no credential.
    """
    return {
        'schema_version': SCHEMA_VERSION,
        'run_id': str(run_id or ''),
        'repository_sha': str(repository_sha or ''),
        'cycle_kind': cycle_kind,
        'runner_exit_code': runner_exit_code,
        'expected_summary_filename': expected_summary_filename,
        'summary_present': bool(summary_present),
        'preupload_scan_safe': bool(preupload_scan_safe),
        'handoff_status': handoff_status,
    }


def resolve_cycle(source_dir):
    """Which cycle produced evidence, decided by which summary exists.

    Returns ``(cycle_kind, summary_path)`` or ``(None, None)``. Daily is
    checked first because a daily run never also writes a postgame summary;
    finding both would mean the runner directory was reused, and the first
    match keeps the choice deterministic rather than ambiguous.
    """
    source_dir = Path(source_dir)
    for cycle in CYCLE_KINDS:
        candidate = source_dir / SUMMARY_FILENAME[cycle]
        if candidate.is_file():
            return cycle, candidate
    return None, None


def prepare(
    *, source_dir, staging_dir, run_id='', repository_sha='',
    daily_runner_exit=None, postgame_runner_exit=None,
):
    """Scan, stage, and describe. Returns ``(metadata, exit_code)``."""
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)

    cycle, summary_path = resolve_cycle(source_dir)
    if cycle is None:
        metadata = build_metadata(
            run_id=run_id, repository_sha=repository_sha, cycle_kind=None,
            runner_exit_code=None, expected_summary_filename=None,
            summary_present=False, preupload_scan_safe=True,
            handoff_status=STATUS_SUMMARY_MISSING,
        )
        return metadata, EXIT_NOT_READY

    runner_exit_code = _normalized_runner_exit_code(
        daily_runner_exit if cycle == CYCLE_DAILY else postgame_runner_exit
    )
    expected_filename = SUMMARY_FILENAME[cycle]

    # Scanned BEFORE the copy. The staging directory never holds a file that
    # has not passed, so a later upload step cannot transport one.
    categories = scan_file(summary_path)
    if categories:
        metadata = build_metadata(
            run_id=run_id, repository_sha=repository_sha, cycle_kind=cycle,
            runner_exit_code=runner_exit_code,
            expected_summary_filename=expected_filename,
            summary_present=True, preupload_scan_safe=False,
            handoff_status=STATUS_ARTIFACT_UNSAFE,
        )
        return metadata, EXIT_NOT_READY

    try:
        shutil.copy2(summary_path, staging / expected_filename)
    except OSError:
        metadata = build_metadata(
            run_id=run_id, repository_sha=repository_sha, cycle_kind=cycle,
            runner_exit_code=runner_exit_code,
            expected_summary_filename=expected_filename,
            summary_present=True, preupload_scan_safe=True,
            handoff_status=STATUS_PREPARATION_ERROR,
        )
        return metadata, EXIT_PREPARATION_FAILED

    status = (
        STATUS_READY if runner_exit_code is not None
        else STATUS_PREPARATION_ERROR
    )
    metadata = build_metadata(
        run_id=run_id, repository_sha=repository_sha, cycle_kind=cycle,
        runner_exit_code=runner_exit_code,
        expected_summary_filename=expected_filename,
        summary_present=True, preupload_scan_safe=True,
        handoff_status=status,
    )
    return metadata, (EXIT_READY if status == STATUS_READY else EXIT_NOT_READY)


def write_metadata(metadata, staging_dir) -> Path:
    path = Path(staging_dir) / METADATA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )
    return path


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Stage a scanned shadow cycle summary and safe metadata for the '
            'activation observer job. Transport only; writes no baseball data.'
        )
    )
    parser.add_argument('--source-dir', required=True)
    parser.add_argument('--staging-dir', required=True)
    parser.add_argument('--run-id', default='')
    parser.add_argument('--repository-sha', default='')
    parser.add_argument('--daily-runner-exit', default=None)
    parser.add_argument('--postgame-runner-exit', default=None)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        metadata, code = prepare(
            source_dir=args.source_dir,
            staging_dir=args.staging_dir,
            run_id=args.run_id,
            repository_sha=args.repository_sha,
            daily_runner_exit=args.daily_runner_exit,
            postgame_runner_exit=args.postgame_runner_exit,
        )
    except Exception as exc:  # noqa: BLE001 - class only, never the message
        metadata = build_metadata(
            run_id=args.run_id, repository_sha=args.repository_sha,
            cycle_kind=None, runner_exit_code=None,
            expected_summary_filename=None, summary_present=False,
            preupload_scan_safe=False,
            handoff_status=STATUS_PREPARATION_ERROR,
        )
        code = EXIT_PREPARATION_FAILED
        print(
            '::warning title=Shadow Handoff::Handoff preparation failed '
            f'({type(exc).__name__}). Activation evidence will be unproven.'
        )

    try:
        write_metadata(metadata, args.staging_dir)
    except OSError:
        print(
            '::warning title=Shadow Handoff::Handoff metadata could not be '
            'written. Activation evidence will be unproven.'
        )
        return EXIT_PREPARATION_FAILED

    status = metadata['handoff_status']
    if status == STATUS_READY:
        print(
            f'Shadow handoff staged: cycle={metadata["cycle_kind"]} '
            f'runner_exit_code={metadata["runner_exit_code"]}.'
        )
    else:
        print(
            f'::warning title=Shadow Handoff::Handoff status is {status}. '
            'The activation observer will report unproven activation health. '
            'Publication-critical results for this run are unaffected.'
        )
    return code


if __name__ == '__main__':
    raise SystemExit(main())
