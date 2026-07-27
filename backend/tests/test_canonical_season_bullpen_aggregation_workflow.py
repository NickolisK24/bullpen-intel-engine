"""Production bootstrap guards for the Foundation 3A audit workflow."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'canonical_season_bullpen_aggregation.yml'


def _workflow_source():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def test_workflow_wires_required_admin_token_secret():
    src = _workflow_source()
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in src


def test_workflow_validates_all_required_production_secrets_before_bootstrap():
    src = _workflow_source()
    assert '[ -z "${DATABASE_URL:-}" ]' in src
    assert '[ -z "${SECRET_KEY:-}" ]' in src
    assert '[ -z "${ADMIN_API_TOKEN:-}" ]' in src
    assert 'Missing required production repository secret.' in src


def test_workflow_never_prints_admin_token_or_secret_reference():
    for line in _workflow_source().splitlines():
        if 'echo ' not in line:
            continue
        assert 'ADMIN_API_TOKEN' not in line
        assert 'BASEBALLOS_ADMIN_API_TOKEN' not in line


def test_workflow_remains_dispatch_only_and_read_only():
    src = _workflow_source()
    assert 'workflow_dispatch:' in src
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                    '\n  workflow_call:', '\n  repository_dispatch:'):
        assert trigger not in src
    assert 'permissions:' in src and 'contents: read' in src
    assert 'run_2026_season_bullpen_aggregation.py' in src
    assert 'expected_fingerprint' not in src
    assert '\n      confirmation:' not in src
