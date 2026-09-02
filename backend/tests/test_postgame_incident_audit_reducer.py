"""Result reducer and repository-state regression.

Requirements 99-106 (reducer) and 118-126 (regression).

The reducer's job is to be unfoolable in one specific way: a classification may
only become the answer when something positively proved it. FAILED is reserved
for a violation of the audit's OWN safety contract — a platform defect the
audit discovers is a successful audit, not a failed workflow.
"""

import hashlib
import re
from pathlib import Path

import pytest
import yaml

from services import game_driven_ingestion as lane
from services import postgame_publication_incident_audit as audit
from tests.test_phase0e_exit_docs import EXPECTED_ALEMBIC_HEAD


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_WORKFLOW = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
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


# These four assert "this package touched nothing it should not". They used to
# ask `git diff origin/main`, which passes on a full clone and returns exit 128
# in CI, where actions/checkout fetches only the PR ref and no origin/main
# exists. A regression test that depends on the checkout's git topology is
# testing the checkout, so the property is now asserted from content directly:
# the reviewed bytes are pinned, which needs no remote, no network, and no
# refs. If any of these files is edited, the digest moves and the test fails —
# which is exactly the guarantee the git version was reaching for.

REVIEWED_DIGESTS = {
    '.github/workflows/manual-noop-qualification-candidate-audit.yml':
        '328e05848091e392522ac5e1d214051084447504c6d2b236fed2de59a33b193f',
    'backend/services/noop_qualification_candidate_audit.py':
        'ffb0021ab3a6112118812ac51020370a8094dc3b8e7c41b6ee5d905984437d82',
    'backend/scripts/run_noop_qualification_candidate_audit.py':
        '3fec12b45c9b94c6655fde09b5fe786463bb9f75c8737fa3e490f7d671071561',
    '.github/workflows/manual-game-driven-noop-qualification.yml':
        '04edaebeb4dc9aef56ebe802947fb6bf4050a8e8fa6e445fcbbcbf54d3ac09b6',
    'backend/services/noop_write_qualification.py':
        'f65351f31b0a9c3c501bb307cf9efd7d13d573178cd9a95ab321fab62d71b5c6',
    'backend/scripts/run_game_driven_noop_qualification.py':
        'edaf91639e166897f89bc01fd6e557553e3869b2085eca7660ee4846597b0453',
}

CANDIDATE_AUDIT_FILES = (
    '.github/workflows/manual-noop-qualification-candidate-audit.yml',
    'backend/services/noop_qualification_candidate_audit.py',
    'backend/scripts/run_noop_qualification_candidate_audit.py',
)
QUALIFICATION_FILES = (
    '.github/workflows/manual-game-driven-noop-qualification.yml',
    'backend/services/noop_write_qualification.py',
    'backend/scripts/run_game_driven_noop_qualification.py',
)


def _digest(relative):
    path = REPO_ROOT / relative
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('relative', CANDIDATE_AUDIT_FILES)
def test_124_the_existing_no_op_candidate_audit_is_unchanged(relative):
    assert _digest(relative) == REVIEWED_DIGESTS[relative], relative


@pytest.mark.parametrize('relative', QUALIFICATION_FILES)
def test_125_the_existing_no_op_qualification_is_unchanged(relative):
    assert _digest(relative) == REVIEWED_DIGESTS[relative], relative


def test_126_this_package_changes_only_the_approved_canonical_module():
    """Exactly two authorities were modified by named governed packages.

    The completeness service gained a read-only membership helper so the audit
    could classify the canonical unresolved set instead of inventing a second
    definition. D-054 later extracted the existing Dashboard snapshot selectors
    and added guarded read entry points. Later governed work made durable Team
    State proof a prerequisite for advancing a trusted/current publication.
    Every other authority stays byte-identical to the incident tree, and both
    exceptions must match their recorded digest — an unrecorded edit to any
    canonical module still fails here."""
    for relative, expected in audit.INCIDENT_CANONICAL_MODULE_DIGESTS.items():
        current = _digest(f'backend/{relative}')
        approved = audit.PACKAGE_MODIFIED_MODULES.get(relative)
        if approved is None:
            assert current == expected, relative
        else:
            assert current == approved['digest_after'], relative

    assert set(audit.PACKAGE_MODIFIED_MODULES) == {
        'services/dashboard_snapshot.py',
        'services/game_ingestion_completeness.py',
    }
    dashboard = audit.PACKAGE_MODIFIED_MODULES['services/dashboard_snapshot.py']
    assert dashboard['digest_after'] == (
        '2092187900026f51a796f0b5a603c42a9bac6be33bd58efd10273b45e6f062e6'
    )
    assert dashboard['behaviour_changed'] is True
    assert 'D-054' in dashboard['change']
    assert 'D-056' in dashboard['change']
    assert 'Production Accuracy Proof' in dashboard['change']
    assert 'F-019' in dashboard['change']


def test_126d_the_modified_module_is_reported_as_changed_by_this_package():
    """Question 3 must not mistake this package's own edit for production
    drift that could explain the incident."""
    observed = {
        relative: _digest(f'backend/{relative}')
        for relative in audit.INCIDENT_CANONICAL_MODULE_DIGESTS
    }
    drift = audit.canonical_module_drift(observed)
    assert drift['changed_by_this_package'] == [
        'services/dashboard_snapshot.py',
        'services/game_ingestion_completeness.py'
    ]
    assert drift['changed_upstream_since_incident'] == []
    assert drift['any_upstream_change_since_incident'] is False
    assert drift['modules']['services/dashboard_snapshot.py'][
        'behaviour_changed'
    ] is True


def test_126b_no_migration_was_added():
    """A migration would move the Alembic head. Asserting the head directly
    needs no remote, and it is the property that actually matters."""
    revisions, downs = set(), set()
    for path in (REPO_ROOT / 'backend/migrations/versions').glob('*.py'):
        source = path.read_text(encoding='utf-8', errors='replace')
        found = re.search(r"^revision = ['\"]([^'\"]+)", source, re.M)
        down = re.search(r"^down_revision = ['\"]([^'\"]+)", source, re.M)
        if found:
            revisions.add(found.group(1))
        if down:
            downs.add(down.group(1))
    heads = revisions - downs
    assert heads == {EXPECTED_ALEMBIC_HEAD}, heads

    # And nothing in this package reaches for a schema change.
    for relative in (
        'backend/services/postgame_publication_incident_audit.py',
        'backend/scripts/run_postgame_publication_incident_audit.py',
    ):
        source = (REPO_ROOT / relative).read_text(encoding='utf-8')
        for marker in ('op.create_table', 'op.add_column', 'op.alter_column',
                       'CREATE TABLE', 'ALTER TABLE'):
            assert marker not in source, f'{marker} in {relative}'


def test_126c_the_incident_audit_never_joins_the_scheduled_set():
    scheduled = []
    for path in (REPO_ROOT / '.github/workflows').glob('*.yml'):
        document = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        if 'schedule' in (document.get(ON) or {}):
            scheduled.append(path.name)
    assert 'manual-postgame-publication-incident-audit.yml' not in scheduled
