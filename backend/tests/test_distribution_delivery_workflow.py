from pathlib import Path

import yaml


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / '.github/workflows/baseballos-generated-distribution.yml'
)


def _workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))


def _job():
    return _workflow()['jobs']['deliver-generated-content']


def _commands(job=None):
    job = job or _job()
    return '\n'.join(
        line
        for step in (job.get('steps') or [])
        for line in (step.get('run') or '').splitlines()
        if not line.lstrip().startswith('#')
    )


def test_distribution_retry_isolated_from_sync_and_requires_snapshot():
    workflow = _workflow()
    dispatch = workflow[True]['workflow_dispatch']['inputs']
    assert dispatch['mode']['options'] == ['distribution']
    assert 'snapshot_id' in dispatch
    commands = _commands()
    assert 'An explicit snapshot_id is required.' in commands
    assert 'run_due_sync.py' not in commands
    assert 'run_daily_sync.py' not in commands
    assert 'run_postgame_refresh.py' not in commands


def test_delivery_freezes_then_rechecks_exact_publication_before_staging():
    commands = _commands()
    assert commands.count('resolve_distribution_publication.py') == 2
    first_resolve = commands.index('resolve_distribution_publication.py')
    team_export = commands.index('export_team_story_pages.py')
    share_export = commands.index('export_share_artifact_pages.py')
    second_resolve = commands.rindex('resolve_distribution_publication.py')
    stage = commands.index('git add -- frontend/public/team frontend/public/share')
    assert first_resolve < team_export < second_resolve < stage
    assert first_resolve < share_export < second_resolve
    assert commands.count('--snapshot-id "$SNAPSHOT_ID"') == 3


def test_generated_content_guard_and_fast_forward_push_remain_narrow():
    commands = _commands()
    assert 'git add -- frontend/public/team frontend/public/share' in commands
    assert "grep -Ev '^frontend/public/(team|share)/'" in commands
    assert 'git add .' not in commands
    assert 'git add -A' not in commands
    assert 'git push origin HEAD:refs/heads/main' in commands
    assert '--force' not in commands


def test_delivery_job_is_serial_and_checks_out_current_main():
    workflow = _workflow()
    assert workflow['concurrency'] == {
        'group': 'baseballos-sync',
        'cancel-in-progress': False,
    }
    checkout = _job()['steps'][0]
    assert checkout['uses'] == 'actions/checkout@v4'
    assert checkout['with']['ref'] == 'main'


def test_failure_gates_precede_commit_and_noop_avoids_empty_commit():
    commands = _commands()
    for gate in (
        'export_team_story_pages.py',
        'export_share_artifact_pages.py',
        'verify_generated_team_previews.py',
        'verify_generated_share_previews.py',
        'npm test',
        'npm run build',
        'git write-tree',
    ):
        assert commands.index(gate) < commands.index('git commit')
    assert 'git diff --cached --quiet' in commands
    assert 'publish=false' in commands
