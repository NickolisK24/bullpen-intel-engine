"""Static contract for the Team State history export workflow.

The exporter reaches production data, so the workflow that runs it must stay
manual and read-only. These assertions are deliberately blunt: they read the
workflow file as text and refuse anything that could turn a calibration read
into a production write or an automatic run.
"""

from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / '.github' / 'workflows' / 'team-state-history-export.yml'
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text()


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def executable_text(workflow_text):
    """Workflow text with comments stripped, so prose never satisfies a scan."""
    lines = []
    for line in workflow_text.splitlines():
        stripped = line.split('#', 1)[0] if line.lstrip().startswith('#') else line
        lines.append(stripped)
    return '\n'.join(lines)


def test_workflow_exists():
    assert WORKFLOW_PATH.exists()


def test_workflow_is_manual_dispatch_only(workflow):
    # PyYAML resolves the bare key ``on`` to True; accept either spelling.
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}, (
        'the export workflow must be manually dispatched only'
    )


def test_workflow_has_no_schedule_or_automatic_trigger(workflow_text):
    for forbidden in ('schedule:', 'cron:', 'repository_dispatch:', 'workflow_run:', 'push:'):
        assert forbidden not in workflow_text, f'export workflow must not declare {forbidden}'


def test_workflow_requests_read_only_permissions(workflow):
    assert workflow.get('permissions') == {'contents': 'read'}


def test_workflow_takes_explicit_range_inputs(workflow):
    triggers = workflow.get('on', workflow.get(True))
    inputs = triggers['workflow_dispatch']['inputs']
    assert {'snapshot_id_from', 'snapshot_id_to', 'date_from', 'date_to'} <= set(inputs)


def test_workflow_fails_loudly_without_a_range(workflow_text):
    assert 'A bounded range is required' in workflow_text
    assert 'exit 1' in workflow_text


def test_workflow_runs_no_mutation_sync_or_publication_command(executable_text):
    for forbidden in (
        'run_intraday_repair', 'build_dashboard_snapshot', 'publish_',
        'flask db upgrade', 'alembic', 'sync.py', '--mode', 'git push',
        'backfill', 'recalculate',
    ):
        assert forbidden not in executable_text, (
            f'export workflow must not invoke {forbidden}'
        )


def test_workflow_runs_only_the_exporter(workflow_text):
    assert 'python -m scripts.export_team_state_history' in workflow_text


def test_workflow_uploads_the_artifact_and_errors_when_absent(workflow_text):
    assert 'actions/upload-artifact' in workflow_text
    assert 'if-no-files-found: error' in workflow_text


def test_workflow_does_not_request_admin_or_write_secrets(workflow_text):
    assert 'ADMIN_API_TOKEN' not in workflow_text
    assert 'BASEBALLOS_SYNC_URL' not in workflow_text
