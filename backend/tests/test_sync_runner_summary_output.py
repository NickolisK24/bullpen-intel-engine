"""``--output`` on the daily and postgame runners.

Durable activation evidence must come from the runner itself, not from parsing
a log stream that interleaves stdout with logging. These tests own that
contract: the same object, written atomically, with the existing stdout and
exit semantics untouched.
"""

import json
import os
from pathlib import Path

import pytest

from utils.summary_output import (
    SummaryOutputError, serialize_summary, write_summary,
)


SUMMARY = {
    'status': 'success',
    'sync': {'status': 'success', 'game_driven_ingestion': {'mode': 'shadow'}},
    'publication_proof': {'verified': True},
    'zeta': 1,
    'alpha': 2,
}


# ── The writer itself ───────────────────────────────────────────────────────


def test_it_writes_valid_json(tmp_path):
    destination = tmp_path / 'summary.json'
    write_summary(SUMMARY, destination)
    assert json.loads(destination.read_text(encoding='utf-8')) == SUMMARY


def test_the_file_content_equals_the_stdout_rendering(tmp_path):
    destination = tmp_path / 'summary.json'
    write_summary(SUMMARY, destination)
    assert destination.read_text(encoding='utf-8') == serialize_summary(SUMMARY)


def test_keys_are_sorted_and_deterministic(tmp_path):
    first = tmp_path / 'a.json'
    second = tmp_path / 'b.json'
    write_summary(SUMMARY, first)
    write_summary(dict(reversed(list(SUMMARY.items()))), second)
    assert first.read_text() == second.read_text()
    body = first.read_text()
    assert body.index('"alpha"') < body.index('"zeta"')


def test_the_parent_directory_is_created(tmp_path):
    destination = tmp_path / 'nested' / 'deeper' / 'summary.json'
    write_summary(SUMMARY, destination)
    assert destination.exists()


def test_no_temporary_sibling_survives_a_successful_write(tmp_path):
    destination = tmp_path / 'summary.json'
    write_summary(SUMMARY, destination)
    assert [path.name for path in tmp_path.iterdir()] == ['summary.json']


def test_no_temporary_sibling_survives_a_failed_write(tmp_path, monkeypatch):
    destination = tmp_path / 'summary.json'

    def explode(*args, **kwargs):
        raise OSError('replace refused')

    monkeypatch.setattr(os, 'replace', explode)
    with pytest.raises(SummaryOutputError):
        write_summary(SUMMARY, destination)
    assert list(tmp_path.iterdir()) == []


def test_a_reader_never_sees_a_partial_file(tmp_path, monkeypatch):
    """The replace is the only moment the destination changes."""
    destination = tmp_path / 'summary.json'
    destination.write_text('{"previous": true}', encoding='utf-8')
    observed = {}

    real_replace = os.replace

    def watched(src, dst):
        observed['before_replace'] = Path(dst).read_text(encoding='utf-8')
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', watched)
    write_summary(SUMMARY, destination)
    assert observed['before_replace'] == '{"previous": true}'
    assert json.loads(destination.read_text()) == SUMMARY


def test_an_unusable_destination_directory_raises_a_safe_reason(tmp_path):
    """A parent that is a regular file cannot become a directory.

    Chosen over a chmod-based test deliberately: CI and this container both run
    as root, and root ignores permission bits, so a chmod test would pass
    without exercising anything.
    """
    blocker = tmp_path / 'not-a-directory'
    blocker.write_text('regular file', encoding='utf-8')
    with pytest.raises(SummaryOutputError) as excinfo:
        write_summary(SUMMARY, blocker / 'summary.json')
    assert excinfo.value.reason == 'summary_output_directory_unavailable'


def test_the_error_carries_no_path_or_raw_message(tmp_path, monkeypatch):
    destination = tmp_path / 'secret-place' / 'summary.json'

    def explode(*args, **kwargs):
        raise OSError(f'permission denied: {destination}')

    monkeypatch.setattr(os, 'replace', explode)
    with pytest.raises(SummaryOutputError) as excinfo:
        write_summary(SUMMARY, destination)
    rendered = f'{excinfo.value.reason} {excinfo.value}'
    assert str(tmp_path) not in rendered
    assert 'permission denied' not in rendered


def test_a_missing_path_is_refused():
    with pytest.raises(SummaryOutputError):
        write_summary(SUMMARY, '')


def test_non_serializable_values_fall_back_to_a_safe_string(tmp_path):
    from datetime import date

    destination = tmp_path / 'summary.json'
    write_summary({'when': date(2026, 8, 1)}, destination)
    assert json.loads(destination.read_text()) == {'when': '2026-08-01'}


# ── Runner CLI compatibility ────────────────────────────────────────────────


def _daily_args(argv):
    from scripts import run_daily_sync

    return run_daily_sync._parse_args(argv)


def _postgame_args(argv):
    from scripts import run_postgame_refresh

    return run_postgame_refresh._parse_args(argv)


def test_the_daily_runner_still_accepts_its_production_invocation():
    args = _daily_args([
        '--days-back', '7', '--source', 'github_actions', '--public-only',
    ])
    assert args.days_back == 7
    assert args.public_only is True
    assert args.output is None


def test_the_postgame_runner_still_accepts_its_production_invocation():
    args = _postgame_args(['--source', 'github_actions', '--public-only'])
    assert args.public_only is True
    assert args.output is None


def test_the_postgame_runner_still_accepts_the_backfill_invocation():
    args = _postgame_args([
        '--date', '2026-06-20', '--source', 'github_actions_backfill',
        '--public-only',
    ])
    assert args.schedule_date == '2026-06-20'
    assert args.output is None


def test_the_daily_runner_accepts_output():
    args = _daily_args(['--output', 'artifacts/x/daily-sync-summary.json'])
    assert args.output == 'artifacts/x/daily-sync-summary.json'


def test_the_postgame_runner_accepts_output():
    args = _postgame_args(['--output', 'artifacts/x/postgame-sync-summary.json'])
    assert args.output == 'artifacts/x/postgame-sync-summary.json'


def test_the_postgame_runner_still_enforces_retry_failed_requires_date():
    with pytest.raises(SystemExit):
        _postgame_args(['--retry-failed'])


def test_the_postgame_runner_still_enforces_game_pk_requires_retry_failed():
    with pytest.raises(SystemExit):
        _postgame_args(['--game-pk', '1'])


# ── Runner behaviour around the output ──────────────────────────────────────


class _FakeApp:
    """Stands in for the Flask app the runner imports at call time."""

    def app_context(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_daily_collaborators(monkeypatch, *, status, verified):
    """Patch the real modules the runner reaches, not sys.modules entries.

    Replacing ``sys.modules['services.sync']`` only works when that module has
    not been imported yet; once any earlier test imports it, ``from services
    import sync`` resolves the package attribute and the replacement is
    silently bypassed. Patching the attribute on the real module is correct in
    both orders.
    """
    import sys
    import types

    app_module = types.ModuleType('app')
    app_module.app = _FakeApp()
    monkeypatch.setitem(sys.modules, 'app', app_module)

    monkeypatch.setattr(
        'services.sync.run_daily_sync', lambda app, **kwargs: dict(status),
    )
    monkeypatch.setattr(
        'services.sync_publication_proof.build_candidate_publication_proof',
        lambda *args, **kwargs: {'verified': verified},
    )


def _run_daily(monkeypatch, capsys, *, status, verified, argv):
    from scripts import run_daily_sync

    _install_daily_collaborators(monkeypatch, status=status, verified=verified)
    exit_code = run_daily_sync.main(argv)
    printed = capsys.readouterr().out.strip().splitlines()
    return exit_code, printed


def test_the_daily_runner_writes_the_printed_object(monkeypatch, capsys, tmp_path):
    destination = tmp_path / 'daily-sync-summary.json'
    exit_code, printed = _run_daily(
        monkeypatch, capsys,
        status={'status': 'success', 'publication_critical': {'complete': True}},
        verified=True,
        argv=['--output', str(destination)],
    )
    assert exit_code == 0
    written = json.loads(destination.read_text(encoding='utf-8'))
    assert written == json.loads(printed[-1])


def test_the_daily_runner_preserves_stdout_without_output(monkeypatch, capsys):
    exit_code, printed = _run_daily(
        monkeypatch, capsys,
        status={'status': 'success', 'publication_critical': {'complete': True}},
        verified=True,
        argv=[],
    )
    assert exit_code == 0
    assert json.loads(printed[-1])['status'] == 'success'


def test_the_daily_runner_keeps_its_failure_exit_code(monkeypatch, capsys, tmp_path):
    destination = tmp_path / 'daily-sync-summary.json'
    exit_code, _ = _run_daily(
        monkeypatch, capsys,
        status={'status': 'failed'},
        verified=False,
        argv=['--output', str(destination)],
    )
    assert exit_code == 1
    # The evidence is still written for a failed cycle — that is exactly when
    # it is needed most.
    assert destination.exists()


def test_the_daily_runner_fails_when_the_output_cannot_be_written(
    monkeypatch, capsys, tmp_path,
):
    def explode(*args, **kwargs):
        raise SummaryOutputError('summary_output_write_failed')

    monkeypatch.setattr('utils.summary_output.write_summary', explode)
    exit_code, _ = _run_daily(
        monkeypatch, capsys,
        status={'status': 'success', 'publication_critical': {'complete': True}},
        verified=True,
        argv=['--output', str(tmp_path / 'daily-sync-summary.json')],
    )
    assert exit_code == 1


def test_the_written_summary_carries_no_credentials(monkeypatch, capsys, tmp_path):
    destination = tmp_path / 'daily-sync-summary.json'
    _run_daily(
        monkeypatch, capsys,
        status={
            'status': 'success',
            'publication_critical': {'complete': True},
            'game_driven_ingestion': {'mode': 'shadow', 'error_class': 'ValueError'},
        },
        verified=True,
        argv=['--output', str(destination)],
    )
    body = destination.read_text(encoding='utf-8')
    for forbidden in (
        'postgresql://', 'postgres://', 'password=', 'Authorization:',
        'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL', 'token=',
        'api_key=', 'secret=', 'Traceback',
    ):
        assert forbidden not in body
