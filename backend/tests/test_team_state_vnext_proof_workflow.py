"""Workflow contract for the Team State vNext production proof.

The proof is observational. It must produce evidence on every daily publication,
preserve that evidence when an assertion fails, and never be able to suppress the
publication or the static delivery that follows it. These assertions read the
workflow definition, so a future edit that quietly makes the proof
publication-critical fails here instead of in production.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip('yaml')


WORKFLOW_PATH = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'baseballos-sync.yml'
PROOF_JOB = 'team-state-vnext-proof'
PROOF_DIR = 'artifacts/team-state-vnext-proof'
PROOF_PATH = f'{PROOF_DIR}/team-state-vnext-production-proof.json'


@pytest.fixture(scope='module')
def workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))


def _steps(workflow, job):
    return workflow['jobs'][job].get('steps') or []


def _step(workflow, job, needle):
    for step in _steps(workflow, job):
        if needle in str(step.get('name', '')):
            return step
    raise AssertionError(f'no step matching {needle!r} in job {job}')


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def test_the_observer_exports_the_durable_proof_for_the_actual_publication(workflow):
    step = _step(workflow, 'public-sync', 'Export durable Team State production proof')
    assert 'export_team_state_publication_proof.py' in step['run']
    assert '--current' in step['run']
    assert PROOF_PATH in step['run']
    assert step['continue-on-error'] is True


def test_no_other_job_or_step_enables_proof_capture(workflow):
    for job_name, job in workflow['jobs'].items():
        assert 'TEAM_STATE_VNEXT_PROOF_PATH' not in (job.get('env') or {}), job_name
        for step in job.get('steps') or []:
            if step.get('name') == 'Run direct daily sync':
                continue
            assert 'TEAM_STATE_VNEXT_PROOF_PATH' not in (step.get('env') or {}), step.get('name')


def test_missing_upload_is_an_error_and_no_publication_is_distinguished(workflow):
    upload = _step(workflow, 'public-sync', 'Upload Team State vNext production proof')
    assert upload['with']['if-no-files-found'] == 'error'
    validate = _step(workflow, PROOF_JOB, 'Validate the Team State vNext production proof')
    assert 'publication_observed' in validate['run']
    assert 'verdict=not_applicable' in validate['run']


def test_the_proof_is_not_written_into_the_shadow_handoff_source_directory(workflow):
    """prepare_shadow_handoff sweeps its source directory wholesale."""
    handoff = _step(workflow, 'public-sync', 'Prepare game-driven shadow handoff')
    shadow_dir = handoff['env']['ACTIVATION_DIR']
    assert not PROOF_DIR.startswith(shadow_dir.rstrip('/') + '/')
    assert PROOF_DIR != shadow_dir


def test_the_proof_is_uploaded_even_when_the_run_fails(workflow):
    upload = _step(workflow, 'public-sync', 'Upload Team State vNext production proof')
    assert 'always()' in upload['if']
    assert upload['with']['path'] == PROOF_DIR
    assert upload['with']['retention-days'] == 30


def test_the_proof_is_scanned_for_forbidden_content_before_upload(workflow):
    steps = [str(step.get('name', '')) for step in _steps(workflow, 'public-sync')]
    scan = next(i for i, name in enumerate(steps) if 'Scan Team State vNext proof' in name)
    upload = next(i for i, name in enumerate(steps) if 'Upload Team State vNext' in name)
    assert scan < upload
    scan_step = _steps(workflow, 'public-sync')[scan]
    assert 'scan_forbidden_artifact_content.py' in scan_step['run']
    assert '--quarantine' in scan_step['run']


def test_proof_emission_cannot_fail_the_publication_job(workflow):
    for name in ('Scan Team State vNext proof', 'Upload Team State vNext production proof'):
        assert _step(workflow, 'public-sync', name)['continue-on-error'] is True


# ---------------------------------------------------------------------------
# Validation, in its own job
# ---------------------------------------------------------------------------


def test_the_validator_runs_in_a_dedicated_observer_job(workflow):
    job = workflow['jobs'][PROOF_JOB]
    assert job['needs'] == 'public-sync'
    assert 'always()' in job['if']
    validate = _step(workflow, PROOF_JOB, 'Validate the Team State vNext production proof')
    assert 'validate_team_state_vnext_proof.py' in validate['run']


def test_the_observer_job_holds_no_production_credential(workflow):
    rendered = yaml.safe_dump(workflow['jobs'][PROOF_JOB])
    for secret in ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN', 'BASEBALLOS_SYNC_URL'):
        assert secret not in rendered


def test_a_missing_proof_artifact_is_reported_rather_than_passing_quietly(workflow):
    validate = _step(workflow, PROOF_JOB, 'Validate the Team State vNext production proof')
    assert '::error::' in validate['run']
    assert 'exit 3' in validate['run']


def test_the_observer_does_not_gate_the_static_or_enrichment_delivery(workflow):
    """The exact regression this job shape exists to prevent."""
    for downstream in ('internal-enrichment', 'static-team-story-preview'):
        job = workflow['jobs'][downstream]
        needs = job['needs']
        needs = [needs] if isinstance(needs, str) else list(needs)
        assert PROOF_JOB not in needs
        assert 'public-sync' in needs
        assert PROOF_JOB not in str(job.get('if', ''))


def test_the_observer_does_not_gate_the_shadow_health_job(workflow):
    needs = workflow['jobs']['shadow-activation-health']['needs']
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert PROOF_JOB not in needs
