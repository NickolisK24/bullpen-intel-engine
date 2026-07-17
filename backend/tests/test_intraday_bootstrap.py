"""Regression tests for the intraday audit production-bootstrap failure contract.

July 17, 2026 incident: the first manual production run of the Phase 1 intraday
reconciliation audit crashed while importing backend/app.py — production
create_app() raised because ADMIN_API_TOKEN was not supplied under
APP_ENV=production — before the audit could acquire the lock, read any source,
or write its JSON artifact.

These tests prove the CLI now always emits a valid, versioned failed artifact on
a bootstrap failure (without leaking secrets, touching sources, acquiring the
lock, or writing), and that the standalone artifact validator accepts every
recognized report and rejects malformed output.
"""

import json
import sys
import types

import pytest

from services import intraday_reconcile
from services import sync_metadata


# ── artifact contract ────────────────────────────────────────────────────────

def test_bootstrap_failure_artifact_contract():
    art = intraday_reconcile.build_bootstrap_failure_artifact(
        source='github_actions',
        started_at_iso='2026-07-17T03:00:00Z',
        completed_at_iso='2026-07-17T03:00:01Z',
        exception_class='RuntimeError',
    )
    assert art['capability'] == 'intraday_reconciliation_audit_v1'
    assert art['version'] == intraday_reconcile.VERSION
    assert art['mode'] == 'intraday'
    assert art['check_only'] is True
    assert art['status'] == 'failed'
    assert art['reason_code'] == 'application_bootstrap_failed'
    assert art['product_date'] is None
    assert art['changed'] is False
    assert art['changed_lanes'] == []
    assert art['affected_team_ids'] == []
    assert art['affected_pitcher_ids'] == []
    assert art['affected_pitcher_mlb_ids'] == []
    # Every lane is explicitly not-checked — never falsely successful.
    for lane in intraday_reconcile.ALL_LANES:
        assert art['lanes'][lane]['verification_status'] == intraday_reconcile.LANE_NOT_CHECKED
    # would_refresh empty; API calls zero (source never began).
    assert art['would_refresh'] == intraday_reconcile._empty_would_refresh()
    assert art['source_api'] == {'api_calls': 0, 'retries': 0, 'by_endpoint': {}}
    # Safety proves no canonical writes / snapshot / fatigue / stories / Tonight.
    safety = art['safety']
    for key in ('writes_performed', 'canonical_writes', 'snapshot_published', 'snapshot_built',
                'fatigue_recalculated', 'stories_generated', 'public_cache_warmed', 'tonight_warmed'):
        assert safety[key] is False
    assert art['limitations'] and 'application_bootstrap_failed' in art['limitations'][0]


def test_bootstrap_artifact_contains_no_secret_values():
    # Even if the underlying exception message carried a secret / connection
    # string, the artifact must record only the exception class — never the
    # message, a traceback, or any credential.
    art = intraday_reconcile.build_bootstrap_failure_artifact(
        source='github_actions',
        started_at_iso='2026-07-17T03:00:00Z',
        exception_class='RuntimeError',
    )
    blob = json.dumps(art)
    for secret_ish in ('ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL', 'postgres://',
                       'postgresql://', 'password', 'Traceback'):
        assert secret_ish not in blob, secret_ish


def test_bootstrap_failure_artifact_passes_validator():
    from scripts.validate_intraday_artifact import validate_artifact
    art = intraday_reconcile.build_bootstrap_failure_artifact(
        source='x', started_at_iso='2026-07-17T03:00:00Z', exception_class='RuntimeError',
    )
    ok, reason = validate_artifact(json.dumps(art))
    assert ok, reason


# ── CLI bootstrap-failure behavior ───────────────────────────────────────────

def _install_raising_app(monkeypatch, message):
    """Make `from app import app` raise, simulating a production create_app()
    failure (e.g. missing ADMIN_API_TOKEN) during app import."""
    class _RaisingAppModule(types.ModuleType):
        def __getattr__(self, name):
            if name == 'app':
                raise RuntimeError(message)
            raise AttributeError(name)

    monkeypatch.setitem(sys.modules, 'app', _RaisingAppModule('app'))


ADMIN_TOKEN_ERROR = (
    'ADMIN_API_TOKEN must be set when APP_ENV=production so that operational '
    'write endpoints are not exposed to anonymous callers.'
)


def test_cli_bootstrap_failure_july_17_2026_incident(monkeypatch, tmp_path, capsys):
    # Tripwires: on a bootstrap failure the audit, the advisory lock, and any
    # source acquisition must never run.
    def _tripwire(name):
        def _raise(*_a, **_k):
            raise AssertionError(f'{name} must not be called on bootstrap failure')
        return _raise

    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', _tripwire('run_intraday_audit'))
    monkeypatch.setattr(sync_metadata, 'acquire_public_sync_read_lock',
                        _tripwire('acquire_public_sync_read_lock'))
    _install_raising_app(monkeypatch, ADMIN_TOKEN_ERROR)

    import scripts.run_intraday_reconcile as cli
    out_path = tmp_path / 'intraday-reconciliation-audit.json'
    rc = cli.main(['--source', 'github_actions', '--json', '--output', str(out_path)])
    captured = capsys.readouterr()

    # Exit code 1, one valid JSON object on stdout, same JSON in --output.
    assert rc == 1
    parsed = json.loads(captured.out)
    assert captured.out.strip().count('\n') == 0
    assert json.loads(out_path.read_text()) == parsed

    assert parsed['status'] == 'failed'
    assert parsed['reason_code'] == 'application_bootstrap_failed'
    assert parsed['capability'] == 'intraday_reconciliation_audit_v1'
    assert parsed['mode'] == 'intraday'
    assert parsed['check_only'] is True
    assert parsed['product_date'] is None
    assert parsed['changed'] is False
    assert parsed['changed_lanes'] == []

    # Diagnostic + traceback go to stderr...
    assert 'RuntimeError' in captured.err
    # ...but the secret-bearing message never reaches stdout or the artifact.
    assert 'ADMIN_API_TOKEN' not in captured.out
    assert 'ADMIN_API_TOKEN' not in out_path.read_text()


def test_cli_bootstrap_failure_makes_no_source_or_lock_or_write_calls(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit',
                        lambda *_a, **_k: called.append('audit'))
    monkeypatch.setattr(sync_metadata, 'acquire_public_sync_read_lock',
                        lambda *_a, **_k: called.append('lock'))
    _install_raising_app(monkeypatch, ADMIN_TOKEN_ERROR)

    import scripts.run_intraday_reconcile as cli
    rc = cli.main(['--source', 'github_actions', '--json'])
    capsys.readouterr()
    assert rc == 1
    # Neither the audit (which does the source reads + writes) nor the lock was
    # ever reached — the app never initialized.
    assert called == []


def test_cli_bootstrap_failure_without_json_flag_still_exits_1(monkeypatch, capsys):
    _install_raising_app(monkeypatch, ADMIN_TOKEN_ERROR)
    import scripts.run_intraday_reconcile as cli
    rc = cli.main(['--source', 'github_actions'])
    out = capsys.readouterr().out
    assert rc == 1
    assert out == ''  # no --json -> nothing on stdout


# ── standalone artifact validator (workflow artifact-contract check) ─────────

def _report(status='success', **overrides):
    payload = {
        'capability': intraday_reconcile.CAPABILITY,
        'mode': 'intraday',
        'check_only': True,
        'status': status,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_validator_accepts_all_recognized_statuses():
    from scripts.validate_intraday_artifact import validate_artifact
    for status in ('success', 'partial', 'failed', 'skipped'):
        ok, reason = validate_artifact(_report(status))
        assert ok, (status, reason)


@pytest.mark.parametrize('text,expected_reason', [
    ('', 'empty_artifact'),
    ('   ', 'empty_artifact'),
    ('{not valid json', 'not_json'),
    ('[1, 2, 3]', 'not_object'),
])
def test_validator_rejects_malformed(text, expected_reason):
    from scripts.validate_intraday_artifact import validate_artifact
    ok, reason = validate_artifact(text)
    assert ok is False
    assert reason == expected_reason


def test_validator_rejects_wrong_contract_fields():
    from scripts.validate_intraday_artifact import validate_artifact
    assert validate_artifact(json.dumps({
        'capability': 'something_else', 'mode': 'intraday', 'check_only': True, 'status': 'success',
    })) == (False, 'wrong_capability')
    assert validate_artifact(json.dumps({
        'capability': intraday_reconcile.CAPABILITY, 'mode': 'daily', 'check_only': True, 'status': 'success',
    })) == (False, 'wrong_mode')
    assert validate_artifact(json.dumps({
        'capability': intraday_reconcile.CAPABILITY, 'mode': 'intraday', 'check_only': False, 'status': 'success',
    })) == (False, 'not_check_only')
    assert validate_artifact(json.dumps({
        'capability': intraday_reconcile.CAPABILITY, 'mode': 'intraday', 'check_only': True, 'status': 'bogus',
    })) == (False, 'unrecognized_status')


def test_validator_rejects_missing_file(tmp_path):
    from scripts.validate_intraday_artifact import validate_artifact_file
    ok, reason = validate_artifact_file(tmp_path / 'does-not-exist.json')
    assert ok is False
    assert reason == 'missing_artifact'


def test_validator_cli_exit_codes(tmp_path, capsys):
    import scripts.validate_intraday_artifact as v
    good = tmp_path / 'good.json'
    good.write_text(_report('failed'))
    assert v.main([str(good)]) == 0
    bad = tmp_path / 'bad.json'
    bad.write_text('{broken')
    assert v.main([str(bad)]) == 3
    assert v.main([str(tmp_path / 'missing.json')]) == 3
    capsys.readouterr()
