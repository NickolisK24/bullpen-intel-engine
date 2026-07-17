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


# ── ADMIN_API_TOKEN production-bootstrap fix (July 17, 2026 incident) ─────────

def _intraday_run_step(doc):
    steps = doc['jobs']['intraday-audit']['steps']
    return next(s for s in steps if s.get('name', '').startswith('Run intraday reconciliation audit'))


def test_intraday_job_supplies_admin_api_token():
    # Regression for the 2026-07-17 incident: production create_app() requires
    # ADMIN_API_TOKEN, which the intraday job previously omitted, crashing the
    # command during app import before the audit could start.
    run_step = _intraday_run_step(_yaml_doc())
    assert run_step['env']['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'
    # APP_ENV stays production; the audit remains read-only.
    assert run_step['env']['APP_ENV'] == 'production'
    assert run_step['env']['AUTO_SYNC'] == 'false'


def test_intraday_preflight_requires_three_secrets():
    run = _intraday_run_step(_yaml_doc())['run']
    # The shell preflight now guards all three required production secrets.
    assert 'DATABASE_URL' in run
    assert 'SECRET_KEY' in run
    assert 'ADMIN_API_TOKEN' in run
    assert '-z "${ADMIN_API_TOKEN:-}"' in run


def test_intraday_preflight_error_names_admin_secret():
    run = _intraday_run_step(_yaml_doc())['run']
    assert 'Missing DATABASE_URL, SECRET_KEY, or BASEBALLOS_ADMIN_API_TOKEN repository secret.' in run


def test_intraday_validates_artifact_before_upload():
    steps = _yaml_doc()['jobs']['intraday-audit']['steps']
    names = [s.get('name', '') for s in steps]
    validate_idx = next(i for i, n in enumerate(names) if n == 'Validate intraday audit artifact contract')
    upload_idx = next(i for i, s in enumerate(steps) if str(s.get('uses', '')).startswith('actions/upload-artifact'))
    assert validate_idx < upload_idx  # validation happens before upload
    assert 'always()' in steps[validate_idx]['if']
    assert 'validate_intraday_artifact.py' in steps[validate_idx]['run']


def test_intraday_exit_code_step_considers_artifact_validity():
    steps = _yaml_doc()['jobs']['intraday-audit']['steps']
    preserve = next(s for s in steps if s.get('name') == 'Preserve intraday audit exit code')
    # The preserved exit code accounts for artifact validity: a genuine failed
    # audit keeps exit 1 (never green), and a missing/invalid artifact becomes a
    # failure even if the command somehow exited 0.
    assert 'intraday-audit-artifact-valid' in preserve['run']
    assert 'artifact-contract failure' in preserve['run']
    assert 'exit "$code"' in preserve['run']


def test_daily_postgame_backfill_behavior_unchanged():
    doc = _yaml_doc()
    public = doc['jobs']['public-sync']['steps']
    blob = '\n'.join(str(s.get('run', '')) for s in public)
    # The daily/postgame/backfill lanes are untouched by this fix.
    assert 'run_daily_sync.py' in blob
    assert 'run_postgame_refresh.py' in blob
    assert "inputs.mode == 'backfill'" in _text()
    # Those production jobs already supplied ADMIN_API_TOKEN and still do.
    daily = next(s for s in public if s.get('name') == 'Run direct daily sync')
    assert daily['env']['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'


def test_intraday_admin_token_line_present_text():
    # Plain-text guard (no PyYAML needed) that the mapping exists in the file.
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in _text()
    assert 'validate_intraday_artifact.py' in _text()
