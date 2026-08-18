"""Validate a Team State vNext production-proof artifact against its contract.

The proof workflow runs this in a dedicated observer job AFTER the artifact has been
uploaded, so a missing / empty / malformed / self-contradictory file is reported as
an artifact-contract failure distinct from an honest FAIL verdict, and so a crash
here can never destroy the evidence it was judging. It reads no database, needs no
Flask app context, and makes no network call.

The contract identities come from the service that emits them, so this validator
cannot drift from what the proof actually contains.

Exit codes: ``0`` the proof is valid and its verdict is not FAIL; ``1`` the proof is
valid and reports FAIL; ``3`` the artifact itself is invalid; ``2`` usage error.
"""

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.team_state_vnext_production_proof import (  # noqa: E402
    CAPABILITY,
    CONTRACT,
    INVARIANTS,
    RESULT_FAIL,
    RESULT_INCONCLUSIVE,
    RESULT_PASS,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_PASS_WITH_INCONCLUSIVE,
)


EXIT_OK = 0
EXIT_PROOF_FAILED = 1
EXIT_USAGE = 2
EXIT_INVALID_ARTIFACT = 3

RECOGNIZED_VERDICTS = (VERDICT_PASS, VERDICT_PASS_WITH_INCONCLUSIVE, VERDICT_FAIL)
RECOGNIZED_RESULTS = (RESULT_PASS, RESULT_FAIL, RESULT_INCONCLUSIVE)


def validate_proof(payload):
    """Validate a parsed proof. Returns ``(ok, reason_code)``.

    ``ok`` False with a reason code means the ARTIFACT is invalid — a different and
    louder condition than a valid proof reporting FAIL, which is a real finding about
    production rather than a broken evidence file.
    """
    if not isinstance(payload, dict):
        return False, 'not_object'
    if payload.get('capability') != CAPABILITY:
        return False, 'wrong_capability'
    if payload.get('contract') != CONTRACT:
        return False, 'wrong_contract'
    if payload.get('reconstructed') is not False:
        return False, 'not_a_direct_observation'
    if payload.get('overall_verdict') not in RECOGNIZED_VERDICTS:
        return False, 'unrecognized_verdict'

    invariants = payload.get('invariants')
    if not isinstance(invariants, dict):
        return False, 'invariants_missing'
    for name in INVARIANTS:
        block = invariants.get(name)
        # A missing or unrecognized invariant is an invalid artifact, never a pass.
        if not isinstance(block, dict) or block.get('result') not in RECOGNIZED_RESULTS:
            return False, f'invariant_missing_or_unrecognized:{name}'

    # Every declared assertion must actually have been evaluated.
    if payload.get('assertions_expected') != len(INVARIANTS):
        return False, 'assertions_expected_mismatch'
    if payload.get('assertions_evaluated') != payload.get('assertions_expected'):
        return False, 'assertions_not_fully_evaluated'

    failed = [name for name in INVARIANTS if invariants[name]['result'] == RESULT_FAIL]
    inconclusive = [
        name for name in INVARIANTS if invariants[name]['result'] == RESULT_INCONCLUSIVE
    ]
    verdict = payload['overall_verdict']
    # The verdict may not be kinder than the invariants it summarizes.
    if failed and verdict != VERDICT_FAIL:
        return False, 'verdict_softer_than_invariants'
    if inconclusive and verdict == VERDICT_PASS:
        return False, 'verdict_ignores_inconclusive'
    if sorted(payload.get('failed_assertions') or []) != sorted(failed):
        return False, 'failed_assertions_inconsistent'

    publication = payload.get('publication')
    if not isinstance(publication, dict):
        return False, 'publication_identity_missing'
    for key in ('dashboard_snapshot_id', 'sync_run_id', 'data_through'):
        if publication.get(key) in (None, ''):
            return False, f'publication_identity_incomplete:{key}'

    teams = payload.get('teams')
    if not isinstance(teams, list) or not teams:
        return False, 'teams_missing'
    team_ids = [team.get('team_id') for team in teams if isinstance(team, dict)]
    if len(team_ids) != len(teams):
        return False, 'team_entry_malformed'
    if len(set(team_ids)) != len(team_ids):
        return False, 'duplicate_team_entry'

    # A reconstructed-later snapshot cannot honestly satisfy this: every team must
    # carry the same publication identity the artifact header claims.
    for team in teams:
        if team.get('source_snapshot_id') != publication.get('dashboard_snapshot_id'):
            return False, 'team_publication_identity_mismatch'

    return True, 'ok'


def validate_proof_file(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError:
        return None, False, 'unreadable_artifact'
    if not text.strip():
        return None, False, 'empty_artifact'
    try:
        payload = json.loads(text)
    except ValueError:
        return None, False, 'not_json'
    ok, reason = validate_proof(payload)
    return payload, ok, reason


def _report(payload):
    lines = [
        f"verdict            : {payload.get('overall_verdict')}",
        f"snapshot           : {(payload.get('publication') or {}).get('dashboard_snapshot_id')}",
        f"sync run           : {(payload.get('publication') or {}).get('sync_run_id')}",
        f"data through       : {(payload.get('publication') or {}).get('data_through')}",
        f"teams captured     : {len(payload.get('teams') or [])}",
    ]
    distribution = payload.get('distribution') or {}
    lines.append(
        'distribution       : '
        f"{distribution.get('fresh')} Fresh / {distribution.get('stretched')} Stretched / "
        f"{distribution.get('vulnerable')} Vulnerable"
    )
    if distribution.get('distribution_degenerate'):
        lines.append('DEGENERATE         : no team published Fresh — review required')
    for name in INVARIANTS:
        block = (payload.get('invariants') or {}).get(name) or {}
        lines.append(f"  {name:<32} {block.get('result')}  {block.get('detail')}")
    return '\n'.join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print('usage: validate_team_state_vnext_proof.py PROOF_JSON', file=sys.stderr)
        return EXIT_USAGE

    payload, ok, reason = validate_proof_file(argv[0])
    if not ok:
        print(f'Team State vNext proof artifact is invalid (reason={reason}).', file=sys.stderr)
        return EXIT_INVALID_ARTIFACT

    print(_report(payload))
    if payload['overall_verdict'] == VERDICT_FAIL:
        print(
            'Team State vNext production proof FAILED: '
            f"{', '.join(payload.get('failed_assertions') or [])}.",
            file=sys.stderr,
        )
        return EXIT_PROOF_FAILED
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
