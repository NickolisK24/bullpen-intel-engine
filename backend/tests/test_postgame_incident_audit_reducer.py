"""Result reducer and repository-state regression.

Requirements 99-106 (reducer) and 118-126 (regression).

The reducer's job is to be unfoolable in one specific way: a classification may
only become the answer when something positively proved it. FAILED is reserved
for a violation of the audit's OWN safety contract — a platform defect the
audit discovers is a successful audit, not a failed workflow.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

from services import game_driven_ingestion as lane
from services import postgame_publication_incident_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_WORKFLOW = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
CANDIDATE_AUDIT_WORKFLOW = (
    REPO_ROOT
    / '.github/workflows/manual-noop-qualification-candidate-audit.yml'
)
QUALIFICATION_WORKFLOW = (
    REPO_ROOT / '.github/workflows/manual-game-driven-noop-qualification.yml'
)
ON = True


def _proof(**overrides):
    proof = {
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }
    proof.update(overrides)
    return proof


def _ingestion(**overrides):
    ingestion = {
        'missing_required': [], 'unreadable_required': [],
        'digest_mismatches': [], 'all_required_present': True,
        'incident_validation': {'any_mismatch': False},
    }
    ingestion.update(overrides)
    return ingestion


def _decide(**overrides):
    kwargs = {
        'questions': [
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        'findings': [],
        'read_only_proof': _proof(),
        'artifact_ingestion': _ingestion(),
        'budget_state': audit.SourceCallBudget().state(),
    }
    kwargs.update(overrides)
    return audit.decide(**kwargs)


def _finding(classification, **overrides):
    finding = {
        'classification': classification,
        'proven': True,
        'confidence': audit.CONFIDENCE_HIGH,
        'supporting_evidence': ['positive evidence'],
        'counter_evidence': [],
        'evidence_sources': [audit.SOURCE_CURRENT_DB],
        'current_condition_persists': True,
        'genuine_source_gap': False,
    }
    finding.update(overrides)
    return finding


# ── 99-106 Result reducer ───────────────────────────────────────────────────

def test_099_a_proven_root_cause_is_complete_root_cause_identified():
    decision = _decide(findings=[
        _finding(audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT),
    ])
    assert decision['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED
    assert decision['exit_code'] == 0
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT
    )


def test_099b_two_proven_defects_become_multiple_contributing_defects():
    decision = _decide(findings=[
        _finding(audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT),
        _finding(audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT),
    ])
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_MULTIPLE_CONTRIBUTING_DEFECTS
    )
    assert set(decision['contributing_classifications']) == {
        audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT,
        audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT,
    }
    assert decision['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED


def test_100_a_genuine_source_gap_is_no_platform_defect_proven():
    decision = _decide(findings=[
        _finding(
            audit.CLASSIFICATION_EXACT_GAME_INGESTION_GAP,
            proven=False, genuine_source_gap=True,
        ),
    ])
    assert decision['result'] == audit.RESULT_NO_PLATFORM_DEFECT_PROVEN
    assert decision['exit_code'] == 0
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN
    )


def test_101_absent_condition_and_thin_evidence_is_not_reproducible():
    decision = _decide(findings=[
        _finding(
            audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT,
            proven=False, current_condition_persists=False,
        ),
    ])
    assert decision['result'] == audit.RESULT_INCIDENT_NOT_REPRODUCIBLE
    assert decision['exit_code'] == 0
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_INCIDENT_CONDITION_NO_LONGER_REPRODUCIBLE
    )


def test_102_a_read_only_violation_is_failed():
    decision = _decide(read_only_proof=_proof(fingerprints_match=False))
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1


def test_102b_a_discovered_platform_defect_is_not_a_workflow_failure():
    """The distinction the whole contract turns on."""
    decision = _decide(findings=[
        _finding(audit.CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT),
    ])
    assert decision['result'] != audit.RESULT_FAILED
    assert decision['exit_code'] == 0


def test_103_missing_required_evidence_is_unproven():
    decision = _decide(artifact_ingestion=_ingestion(
        missing_required=[audit.ARTIFACT_SHADOW], all_required_present=False,
    ))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2


def test_104_failed_outranks_unproven():
    decision = _decide(
        read_only_proof=_proof(fingerprints_match=False),
        artifact_ingestion=_ingestion(
            missing_required=[audit.ARTIFACT_SHADOW],
            all_required_present=False,
        ),
        questions=[],
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['failed_reasons']
    assert decision['unproven_reasons']


def test_105_classification_requires_positive_evidence():
    """A finding marked proven but carrying no supporting evidence must not
    become the answer — that is exactly 'concluded from an absence'."""
    decision = _decide(findings=[
        _finding(
            audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT,
            supporting_evidence=[],
        ),
    ])
    assert decision['primary_classification'] != (
        audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT
    )
    assert decision['result'] == audit.RESULT_INCIDENT_NOT_REPRODUCIBLE


def test_105b_an_unproven_finding_never_becomes_the_answer():
    decision = _decide(findings=[
        _finding(
            audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT, proven=False,
        ),
    ])
    assert decision['primary_classification'] != (
        audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT
    )


def test_105c_every_finding_carries_supporting_and_counter_evidence():
    decision = _decide(findings=[
        _finding(
            audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT,
            counter_evidence=['rows agree'],
        ),
    ])
    view = decision['findings'][0]
    assert view['supporting_evidence'] == ['positive evidence']
    assert view['counter_evidence'] == ['rows agree']
    assert view['confidence'] in audit.CONFIDENCE_LEVELS


def test_106_the_recommended_next_package_never_authorizes_execution():
    for classification in audit.PRIMARY_CLASSIFICATIONS:
        assert audit.NEXT_PACKAGE_FOR_CLASSIFICATION[classification] in (
            audit.NEXT_PACKAGE_CATEGORIES
        )
    decision = _decide(findings=[
        _finding(audit.CLASSIFICATION_SNAPSHOT_STATE_TRANSITION_DEFECT),
    ])
    assert decision['recommended_next_package'] == (
        audit.NEXT_SNAPSHOT_TRANSITION_FIX
    )
    assert decision['recommendation_informational_only'] is True
    assert 'does not authorize' in decision['recommendation_note']
    assert 'authorize' in audit.NON_AUTHORIZATION_STATEMENT


def test_106b_exactly_nine_next_package_categories_exist():
    assert len(audit.NEXT_PACKAGE_CATEGORIES) == 9
    assert len(set(audit.NEXT_PACKAGE_CATEGORIES)) == 9


# ── 118-126 Repository-state regression ─────────────────────────────────────

@pytest.fixture(scope='module')
def sync_workflow():
    return yaml.safe_load(SYNC_WORKFLOW.read_text(encoding='utf-8'))


def _mode_values(workflow):
    modes = []
    for job in workflow['jobs'].values():
        for step in job.get('steps') or ():
            env = step.get('env') or {}
            if 'GAME_DRIVEN_INGESTION_MODE' in env:
                modes.append((
                    step.get('name'), env['GAME_DRIVEN_INGESTION_MODE'],
                ))
    return modes


def test_118_the_daily_game_driven_lane_remains_shadow(sync_workflow):
    modes = _mode_values(sync_workflow)
    daily = [
        value for name, value in modes if 'daily' in (name or '').lower()
    ]
    assert daily and set(daily) == {'shadow'}


def test_119_the_postgame_game_driven_lane_remains_shadow(sync_workflow):
    modes = _mode_values(sync_workflow)
    postgame = [
        value for name, value in modes if 'postgame' in (name or '').lower()
    ]
    assert postgame and set(postgame) == {'shadow'}


def test_120_backfill_remains_off(sync_workflow):
    modes = _mode_values(sync_workflow)
    backfill = [
        value for name, value in modes if 'backfill' in (name or '').lower()
    ]
    assert backfill and set(backfill) == {'off'}
    assert set(value for _, value in modes) <= {'shadow', 'off'}


def test_121_automated_writes_remain_prohibited(sync_workflow):
    for _, value in _mode_values(sync_workflow):
        assert not lane.writes_enabled(value)


def test_122_authoritative_mode_remains_prohibited(sync_workflow):
    for _, value in _mode_values(sync_workflow):
        assert value != lane.MODE_AUTHORITATIVE
        assert not lane.publication_authoritative(value)


def test_123_publication_authority_remains_false(sync_workflow):
    for _, value in _mode_values(sync_workflow):
        assert lane.publication_authoritative(value) is False


def test_124_the_existing_no_op_candidate_audit_is_unchanged():
    diff = subprocess.run(
        ['git', 'diff', 'origin/main', '--',
         str(CANDIDATE_AUDIT_WORKFLOW.relative_to(REPO_ROOT)),
         'backend/services/noop_qualification_candidate_audit.py',
         'backend/scripts/run_noop_qualification_candidate_audit.py'],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert diff.returncode == 0
    assert diff.stdout.strip() == '', diff.stdout[:400]


def test_125_the_existing_no_op_qualification_is_unchanged():
    diff = subprocess.run(
        ['git', 'diff', 'origin/main', '--',
         str(QUALIFICATION_WORKFLOW.relative_to(REPO_ROOT)),
         'backend/services/noop_write_qualification.py',
         'backend/scripts/run_game_driven_noop_qualification.py'],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert diff.returncode == 0
    assert diff.stdout.strip() == '', diff.stdout[:400]


def test_126_this_package_changes_no_canonical_module():
    """The suite-wide guarantee this package can actually assert: it adds
    files and touches no canonical authority. Every module the audit reads
    through must be byte-identical to the reviewed base."""
    diff = subprocess.run(
        ['git', 'diff', '--name-only', 'origin/main', '--', 'backend/services',
         'backend/models', 'backend/routes'],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert diff.returncode == 0
    changed = [line for line in diff.stdout.splitlines() if line.strip()]
    assert changed == [
        'backend/services/postgame_publication_incident_audit.py'
    ], changed


def test_126b_no_migration_was_added():
    diff = subprocess.run(
        ['git', 'diff', '--name-only', 'origin/main', '--',
         'backend/migrations'],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert diff.returncode == 0
    assert diff.stdout.strip() == ''


def test_126c_the_incident_audit_never_joins_the_scheduled_set():
    scheduled = []
    for path in (REPO_ROOT / '.github/workflows').glob('*.yml'):
        document = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        if 'schedule' in (document.get(ON) or {}):
            scheduled.append(path.name)
    assert 'manual-postgame-publication-incident-audit.yml' not in scheduled
