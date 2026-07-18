from pathlib import Path
import re
import subprocess

import pytest

from services.evidence_classification import validate_evidence_classifications


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ALEMBIC_HEAD = 'e6b4c2a8d1f3'
EXPECTED_CHANGED_PATHS = {
    'backend/tests/test_phase0e_exit_docs.py',
    'docs/phase0e/README.md',
    'docs/phase0e/legal_review_paper.md',
    'docs/phase0e/phase0e_exit_report.md',
    'docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md',
}
PHASE0E_EXIT_DOCUMENT_PATHS = EXPECTED_CHANGED_PATHS - {
    'backend/tests/test_phase0e_exit_docs.py',
}
PHASE0E_EXIT_BRANCH_TRIGGER_PATHS = PHASE0E_EXIT_DOCUMENT_PATHS - {
    'docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md',
}


def test_phase0e_legal_paper_covers_required_exit_sections():
    text = _read('docs/phase0e/legal_review_paper.md')
    required_headings = (
        'Executive Summary',
        'Current Classification Inventory',
        'Public Candidate Review',
        'Source Review',
        'Public Claim Standards',
        'Editorial Standards',
        'Risk Review',
        'Decision Matrix',
        'Founder Decision Checklist',
        'Phase 0E Exit Summary',
        'Remaining Work',
    )
    for heading in required_headings:
        assert f'## {heading}' in text

    required_fragments = (
        'No public evidence surfacing occurs in Phase 0E.',
        'The Phase 0B legal/source review gate remains CLOSED.',
        'This paper does not recommend publication.',
        'No option is selected or endorsed by this paper.',
        'Public evidence surfacing is NOT part of Phase 0E.',
        'PC: 44',
        'EL: 9',
        'IO: 4',
        'PI: 8',
        'Total: 65',
        '0E-01',
        '0E-02',
        '0E-03',
        '0E-04',
        '0E-05',
        '0E-06',
    )
    for fragment in required_fragments:
        assert fragment in text


def test_phase0e_exit_report_and_index_reference_final_package():
    exit_report = _read('docs/phase0e/phase0e_exit_report.md')
    readme = _read('docs/phase0e/README.md')
    roadmap = _read('docs/roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md')

    for fragment in (
        'a9d4e7c2f6b1',
        'e4b7c9d2a6f0',
        'pitcher_roster_membership_context',
        'reliever_daily_read',
        'team_daily_read',
        'DEFER-WITH-STRUCTURE',
        'REJECT-AND-CLOSE',
        'public evidence surfacing remains blocked',
    ):
        assert fragment in exit_report

    assert 'docs/phase0e/legal_review_paper.md' in readme
    assert 'docs/phase0e/phase0e_exit_report.md' in readme
    assert '0E-06' in roadmap
    assert 'legal review paper and exit report' in roadmap


def test_phase0e_exit_classification_and_alembic_head_remain_fixed():
    classification = validate_evidence_classifications()
    assert classification['rule_count'] == 65
    assert classification['classified_count'] == 65
    assert classification['tallies']['PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'] == 44
    assert classification['tallies']['ELIGIBLE_PUBLIC_CANDIDATE_LATER'] == 9
    assert classification['tallies']['INTERNAL_ONLY_FOR_NOW'] == 4
    assert classification['tallies']['PERMANENTLY_INTERNAL'] == 8

    assert _alembic_heads() == {EXPECTED_ALEMBIC_HEAD}


def test_phase0e_exit_branch_keeps_public_runtime_isolated():
    changed = _changed_paths_against_main()
    if not changed.intersection(PHASE0E_EXIT_BRANCH_TRIGGER_PATHS):
        pytest.skip('Phase 0E exit document branch diff not present.')
    unexpected = sorted(path for path in changed if path not in EXPECTED_CHANGED_PATHS)
    assert unexpected == []

    forbidden_prefixes = (
        'backend/api/',
        'backend/migrations/',
        'backend/models/composed_read.py',
        'backend/models/legacy_read_audit.py',
        'backend/scripts/build_composed_reads.py',
        'backend/scripts/render_read_review_packet.py',
        'backend/scripts/run_reconciliation_audit.py',
        'backend/services/composed_read',
        'backend/services/dashboard_snapshot.py',
        'backend/services/evidence_classification.py',
        'backend/services/evidence_rules.py',
        'backend/services/legacy_read_reconciliation.py',
        'backend/services/reliever_daily_read.py',
        'backend/services/sync.py',
        'backend/services/team_daily_read.py',
        'backend/services/tonight_intelligence_snapshot.py',
        'backend/services/what_changed_since_yesterday',
        'frontend/',
    )
    assert not [
        path for path in changed
        if any(path.startswith(prefix) for prefix in forbidden_prefixes)
    ]


def _read(relative_path):
    return (REPO_ROOT / relative_path).read_text(encoding='utf-8')


def _alembic_heads():
    revisions = {}
    for path in (REPO_ROOT / 'backend/migrations/versions').glob('*.py'):
        text = path.read_text(encoding='utf-8')
        revision = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down_revision = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if revision:
            revisions[revision.group(1)] = (
                down_revision.group(1).strip() if down_revision else None
            )
    referenced = {value for value in revisions.values() if value and value != 'None'}
    return set(revisions) - referenced


def _changed_paths_against_main():
    outputs = []
    commands = (
        ('git', 'diff', '--name-only', 'origin/main...HEAD'),
        ('git', 'diff', '--name-only', 'origin/main'),
        ('git', 'diff', '--cached', '--name-only', 'origin/main'),
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            continue
        outputs.extend(result.stdout.splitlines())
    return {
        path.strip().replace('\\', '/')
        for path in outputs
        if path.strip()
    }
