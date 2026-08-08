from scripts.run_daily_sync import (
    PRODUCTION_DAILY_TRIGGER_REFUSAL,
    production_daily_trigger_refusal_reason,
)


def _production_env(**overrides):
    values = {
        'APP_ENV': 'production',
        'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'schedule',
    }
    values.update(overrides)
    return values


def test_scheduled_github_daily_is_authorized():
    assert production_daily_trigger_refusal_reason(_production_env()) is None


def test_workflow_dispatch_daily_is_refused():
    assert production_daily_trigger_refusal_reason(
        _production_env(GITHUB_EVENT_NAME='workflow_dispatch')
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_local_production_daily_is_refused():
    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'production'}
    ) == PRODUCTION_DAILY_TRIGGER_REFUSAL


def test_nonproduction_daily_runner_remains_available():
    assert production_daily_trigger_refusal_reason(
        {'APP_ENV': 'test', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
    ) is None
