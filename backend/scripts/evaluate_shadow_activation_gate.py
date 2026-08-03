"""The final activation-health verdict, as one auditable decision.

This gate used to live at the end of the publication-critical job, where a
shadow-only failure turned a successful publication red and skipped every
downstream job that depended on the public data. The verdict is unchanged; only
its blast radius is. It now decides the outcome of the observer job alone.

Ten conditions must all hold for PASS. They are evaluated here, in Python,
rather than as a chain of shell tests, for one reason: the failure matrix has
to be provable. A gate whose behaviour is asserted only by reading the workflow
file is a gate nobody has actually run.

The vocabulary is deliberately three-valued and never four:

* ``PASS``     — every condition held;
* ``FAILED``   — the validator ran and reported a real activation failure;
* ``UNPROVEN`` — the evidence was missing, unsafe, or unreadable.

UNPROVEN is not a skip, not a warning, and never a pass. Absent evidence is the
state most likely to be mistaken for success, so it is named and it fails.

Standard library only. No Flask, no models, no database, no secrets, no
network.

Exit codes: ``0`` PASS, ``1`` FAILED or UNPROVEN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.prepare_shadow_handoff import (  # noqa: E402
    CYCLE_KINDS, METADATA_FILENAME, SCHEMA_VERSION, STATUS_READY,
)


RESULT_PASS = 'PASS'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

EXIT_PASS = 0
EXIT_NOT_PASS = 1

# Why the gate did not pass. Each names one of the ten conditions.
REASON_HANDOFF_DOWNLOAD_FAILED = 'handoff_download_failed'
REASON_METADATA_MISSING = 'handoff_metadata_missing'
REASON_METADATA_INVALID = 'handoff_metadata_invalid'
REASON_HANDOFF_NOT_READY = 'handoff_status_not_ready'
REASON_PREUPLOAD_SCAN_UNSAFE = 'preupload_scan_unsafe'
REASON_SUMMARY_MISSING = 'cycle_summary_missing'
REASON_CYCLE_KIND_INVALID = 'cycle_kind_invalid'
REASON_RUNNER_EXIT_INVALID = 'runner_exit_code_invalid'
REASON_VALIDATOR_FAILED = 'validator_reported_failure'
REASON_VALIDATOR_UNPROVEN = 'validator_could_not_run'
REASON_FINAL_SCAN_UNSAFE = 'final_artifact_scan_unsafe'
REASON_FINAL_UPLOAD_FAILED = 'final_artifact_upload_failed'


def _as_bool(value, *, default=False):
    """Strict truthiness for workflow-supplied strings.

    Anything unrecognized is False. A gate that reads an unexpected value as
    'probably fine' is the failure mode this whole package exists to remove.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {'true', '1', 'yes', 'success'}


def _load_metadata(handoff_dir):
    path = Path(handoff_dir) / METADATA_FILENAME
    if not path.is_file():
        return None, REASON_METADATA_MISSING
    try:
        metadata = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, REASON_METADATA_INVALID
    if not isinstance(metadata, dict):
        return None, REASON_METADATA_INVALID
    if str(metadata.get('schema_version') or '') != SCHEMA_VERSION:
        return None, REASON_METADATA_INVALID
    return metadata, None


def evaluate(
    *, handoff_dir, handoff_download_ok, validator_exit_code,
    final_scan_safe, final_upload_ok,
):
    """Decide the activation verdict. Pure: reads state, returns a decision."""
    def verdict(result, reason):
        return {'result': result, 'reason': reason}

    # 1. The handoff artifact reached this job at all.
    if not handoff_download_ok:
        return verdict(RESULT_UNPROVEN, REASON_HANDOFF_DOWNLOAD_FAILED)

    # 2-3. Metadata exists, parses, and matches the schema this gate knows.
    metadata, reason = _load_metadata(handoff_dir)
    if reason is not None:
        return verdict(RESULT_UNPROVEN, reason)

    # 4. The producing side reported a usable handoff.
    if metadata.get('handoff_status') != STATUS_READY:
        return verdict(RESULT_UNPROVEN, REASON_HANDOFF_NOT_READY)

    # 5. The pre-upload scan passed, so nothing unsafe was transported.
    if not _as_bool(metadata.get('preupload_scan_safe')):
        return verdict(RESULT_UNPROVEN, REASON_PREUPLOAD_SCAN_UNSAFE)

    # 6. The expected summary is named and actually present.
    expected = metadata.get('expected_summary_filename')
    if not metadata.get('summary_present') or not expected:
        return verdict(RESULT_UNPROVEN, REASON_SUMMARY_MISSING)
    if not (Path(handoff_dir) / str(expected)).is_file():
        return verdict(RESULT_UNPROVEN, REASON_SUMMARY_MISSING)

    # 7. The cycle is one this contract governs.
    if metadata.get('cycle_kind') not in CYCLE_KINDS:
        return verdict(RESULT_UNPROVEN, REASON_CYCLE_KIND_INVALID)

    # 8. The runner's exit code survived transport as a real integer.
    if not isinstance(metadata.get('runner_exit_code'), int) or isinstance(
        metadata.get('runner_exit_code'), bool
    ):
        return verdict(RESULT_UNPROVEN, REASON_RUNNER_EXIT_INVALID)

    # 9. The validator's own verdict.
    try:
        validator_code = int(str(validator_exit_code).strip())
    except (TypeError, ValueError):
        return verdict(RESULT_UNPROVEN, REASON_VALIDATOR_UNPROVEN)
    if validator_code == 1:
        return verdict(RESULT_FAILED, REASON_VALIDATOR_FAILED)
    if validator_code != 0:
        return verdict(RESULT_UNPROVEN, REASON_VALIDATOR_UNPROVEN)

    # 10. The evidence for this verdict was itself safe and preserved.
    if not _as_bool(final_scan_safe):
        return verdict(RESULT_UNPROVEN, REASON_FINAL_SCAN_UNSAFE)
    if not _as_bool(final_upload_ok):
        return verdict(RESULT_UNPROVEN, REASON_FINAL_UPLOAD_FAILED)

    return verdict(RESULT_PASS, None)


UNCHANGED_AUTHORITY_NOTICE = (
    'Automated write mode remains prohibited. Authoritative mode remains '
    'prohibited. Current publication authority remains unchanged. Review the '
    'retained activation evidence before promotion or rollback.'
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Evaluate the final game-driven shadow activation health gate. '
            'Reads retained evidence only; writes no baseball data.'
        )
    )
    parser.add_argument('--handoff-dir', required=True)
    parser.add_argument('--handoff-download-outcome', default='')
    parser.add_argument('--validator-exit-code', default='')
    parser.add_argument('--final-scan-safe', default='')
    parser.add_argument('--final-upload-outcome', default='')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    decision = evaluate(
        handoff_dir=args.handoff_dir,
        handoff_download_ok=_as_bool(args.handoff_download_outcome),
        validator_exit_code=args.validator_exit_code,
        final_scan_safe=_as_bool(args.final_scan_safe),
        final_upload_ok=_as_bool(args.final_upload_outcome),
    )
    result = decision['result']

    if result == RESULT_PASS:
        print('Game-driven shadow activation health: PASS.')
        return EXIT_PASS

    label = 'FAILED' if result == RESULT_FAILED else 'UNPROVEN'
    print(
        f'::error title=Game-Driven Shadow::Activation health is {label} '
        f'(reason={decision["reason"]}). Treat this as a failure, not a pass. '
        f'{UNCHANGED_AUTHORITY_NOTICE}'
    )
    print(
        'This job reports observer health only. It does not change the '
        'publication-critical result of this run.'
    )
    return EXIT_NOT_PASS


if __name__ == '__main__':
    raise SystemExit(main())
