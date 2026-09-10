"""Validate an intraday reconciliation audit JSON artifact against its output
contract, independently of the audit itself.

The intraday GitHub Actions job runs this BEFORE uploading the artifact so a
missing / empty / malformed / wrong-shape file is reported as an
**artifact-contract failure** — distinct from a normal partial/failed audit,
which always produces a valid, recognized JSON report. This never inspects
baseball data and needs no Flask app context or database.

Exit codes: 0 = valid artifact; 3 = invalid (missing/empty/malformed/wrong
capability/mode/check_only/status); 2 = usage error.
"""

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The service owns the contract identity; import it so the validator can never
# drift from what the audit actually emits. This import needs no app context.
from services.intraday_reconcile import (  # noqa: E402
    CAPABILITY,
    MODE,
    RECOGNIZED_STATUSES,
)


def validate_artifact(text):
    """Validate raw artifact text. Returns ``(ok: bool, reason_code: str)``.

    Accepts a valid success / skipped / partial / failed report; rejects
    empty, malformed, non-object, or wrong-capability/mode/check_only/status
    payloads.
    """
    if text is None or str(text).strip() == '':
        return False, 'empty_artifact'
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return False, 'not_json'
    if not isinstance(payload, dict):
        return False, 'not_object'
    if payload.get('capability') != CAPABILITY:
        return False, 'wrong_capability'
    if payload.get('mode') != MODE:
        return False, 'wrong_mode'
    if payload.get('check_only') is not True:
        return False, 'not_check_only'
    if payload.get('status') not in RECOGNIZED_STATUSES:
        return False, 'unrecognized_status'
    return True, 'ok'


def validate_artifact_file(path):
    """Validate an artifact file by path. Returns ``(ok, reason_code)``.

    A missing file is ``missing_artifact``; an empty file is ``empty_artifact``.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return False, 'missing_artifact'
    try:
        text = file_path.read_text(encoding='utf-8')
    except OSError:
        return False, 'unreadable_artifact'
    return validate_artifact(text)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print('usage: validate_intraday_artifact.py <artifact.json>', file=sys.stderr)
        return 2
    ok, reason = validate_artifact_file(argv[0])
    if ok:
        print(f'Intraday audit artifact is valid ({argv[0]}).', file=sys.stderr)
        return 0
    print(
        f'Intraday audit artifact FAILED the output-contract check '
        f'({argv[0]}): {reason}.',
        file=sys.stderr,
    )
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
