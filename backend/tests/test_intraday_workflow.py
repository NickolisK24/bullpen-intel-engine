"""Static assertions on the intraday audit GitHub Actions job.

Proves the manual intraday job is correctly gated, names/uploads the right
artifact, preserves the command exit code, adds no cron, and never runs any
mutating sync step. Plain-text checks always run; deeper structural checks use
PyYAML when it is available (skipped otherwise, so CI without PyYAML still runs
the text assertions).
"""

from pathlib import Path

import pytest


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'baseballos-sync.yml'
)
MUTATING_STEP_MARKERS = (
    'run_daily_sync.py',
    'run_postgame_refresh.py',
    'run_tonight_refresh.py',
    'appearance_ledger_audit.py',
    'dashboard',
    'run_internal_enrichment.py',
    'export_team_story_pages.py',
)


def _text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def _yaml_doc():
    yaml = pytest.importorskip('yaml')
    return yaml.safe_load(_text())


# ── plain-text assertions (no PyYAML required) ───────────────────────────────

def test_workflow_file_exists():
    assert WORKFLOW_PATH.is_file()


def test_intraday_mode_is_a_dispatch_choice():
    assert '- intraday' in _text()


def test_artifact_filename_and_upload_name():
    text = _text()
    assert 'intraday-reconciliation-audit.json' in text
    assert 'name: intraday-reconciliation-audit-${{ github.run_id }}' in text
    assert 'actions/upload-artifact@v4' in text


def test_command_prints_json_and_writes_output():
    text = _text()
    assert 'run_intraday_reconcile.py' in text
    assert '--json' in text
    assert '--output intraday-reconciliation-audit.json' in text


def test_public_sync_job_excludes_intraday():
    # The publish lane must not run for an intraday dispatch.
    assert "!(github.event_name == 'workflow_dispatch' && inputs.mode == 'intraday')" in _text()


def test_exactly_two_cron_schedules_and_none_for_intraday():
    text = _text()
    # No cron was added for intraday; the only crons remain daily + postgame.
    assert text.count('- cron:') == 2
    assert "'0 10 * * *'" in text   # daily
    assert "'0 2,4,6 * * *'" in text  # postgame


# ── structural assertions (PyYAML) ───────────────────────────────────────────

def test_intraday_job_is_gated_to_mode():
    doc = _yaml_doc()
    job = doc['jobs']['intraday-audit']
    cond = job['if']
    # Only a manual dispatch with mode==intraday can start it — a schedule event
    # can never fall through into this job.
    assert "github.event_name == 'workflow_dispatch'" in cond
    assert "inputs.mode == 'intraday'" in cond


def test_no_intraday_cron_added():
    doc = _yaml_doc()
    on = doc.get(True, doc.get('on'))
    crons = [s['cron'] for s in on['schedule']]
    assert crons == ['0 10 * * *', '0 2,4,6 * * *']


def test_upload_runs_even_on_failure_and_exit_code_preserved():
    doc = _yaml_doc()
    steps = doc['jobs']['intraday-audit']['steps']
    upload = next(s for s in steps if str(s.get('uses', '')).startswith('actions/upload-artifact'))
    assert 'always()' in upload['if']
    # A dedicated final step re-applies the command's original exit code after
    # the artifact upload.
    preserve = next(s for s in steps if s.get('name') == 'Preserve intraday audit exit code')
    assert 'always()' in preserve['if']
    assert 'exit "$code"' in preserve['run']


def test_intraday_job_runs_no_mutating_step():
    doc = _yaml_doc()
    steps = doc['jobs']['intraday-audit']['steps']
    blob = '\n'.join(str(s.get('run', '')) for s in steps)
    for marker in MUTATING_STEP_MARKERS:
        assert marker not in blob, f'intraday audit job must not run {marker}'
