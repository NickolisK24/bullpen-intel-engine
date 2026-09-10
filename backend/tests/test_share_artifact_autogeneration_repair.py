"""Regression tests for the SC-03B-04 autogeneration publication-path repair.

Root cause: the canonical production publication path
(``sync.complete_sync_run_with_snapshot`` -> ``build_bullpen_dashboard_snapshot(
publish=True, commit=False)`` -> external ``db.session.commit()``) publishes with
``commit=False`` and commits the transaction itself. The SC-03B-02 hook fired only
when ``publish_dashboard_snapshot`` was called with ``commit=True``, so in
production the post-publication Team State generation hook was never invoked —
zero audit attempts, zero artifacts, 30 missing.

The repair extracts one canonical post-commit completion function
(``dashboard_snapshot.run_post_commit_snapshot_publication``) and calls it from
every legitimate committed-publication path: ``publish_dashboard_snapshot`` when it
owns the commit, and ``complete_sync_run_with_snapshot`` after its own commit.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask

from services import dashboard_snapshot as ds
from services import share_artifact_publication_hook as hook_module
from services import sync as sync_service
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _published_snapshot(snapshot_id=205, data_through=date(2026, 7, 23)):
    return SimpleNamespace(
        id=snapshot_id, is_published=True, status=ds.SNAPSHOT_STATUS_READY,
        data_through=data_through,
    )


# -- 3 / 14: the canonical daily-sync publication path reaches the hook ----------


def test_sync_completion_triggers_generation_after_commit(app, monkeypatch):
    """Reproduces the production symptom: complete_sync_run_with_snapshot commits a
    trusted snapshot but (pre-repair) never invokes generation. After the repair it
    calls the canonical post-commit completion exactly once, with the committed
    snapshot's authoritative context."""
    calls = []
    monkeypatch.setattr(
        hook_module, 'run_post_publication_generation',
        lambda snapshot, **k: calls.append(snapshot),
    )
    fake_run = SimpleNamespace(id=42, stage=None, published_dashboard_snapshot_id=None)
    fake_snapshot = _published_snapshot()
    monkeypatch.setattr(sync_service.sync_metadata, 'finish_sync_run', lambda *a, **k: fake_run)
    monkeypatch.setattr(ds, 'build_bullpen_dashboard_snapshot', lambda **k: fake_snapshot)

    run, snapshot = sync_service.complete_sync_run_with_snapshot(999, final_status='success')

    assert snapshot is fake_snapshot
    assert run.stage == sync_service.sync_metadata.STAGE_PUBLISHED
    assert calls == [fake_snapshot]  # fires exactly once, after commit


# -- post-commit completion function guards --------------------------------------


def test_post_commit_completion_fires_for_committed_published_snapshot(app, monkeypatch):
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    snap = _published_snapshot()
    ds.run_post_commit_snapshot_publication(snap)
    assert calls == [snap]


def test_post_commit_completion_is_a_noop_for_withheld_or_pending(app, monkeypatch):
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    ds.run_post_commit_snapshot_publication(SimpleNamespace(id=1, is_published=False, status='ready'))
    ds.run_post_commit_snapshot_publication(SimpleNamespace(id=2, is_published=True, status='pending'))
    ds.run_post_commit_snapshot_publication(None)
    assert calls == []


def test_post_commit_completion_gated_off_when_flag_absent(app, monkeypatch):
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = False
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    ds.run_post_commit_snapshot_publication(_published_snapshot())
    assert calls == []


def test_post_commit_completion_never_raises(app, monkeypatch):
    def _boom(snapshot, **k):
        raise RuntimeError('generation exploded')

    monkeypatch.setattr(hook_module, 'run_post_publication_generation', _boom)
    # Must not raise — a downstream failure never disturbs the committed publication.
    ds.run_post_commit_snapshot_publication(_published_snapshot())


# -- publish_dashboard_snapshot(commit=True) still fires exactly once -------------


def test_publish_dashboard_snapshot_commit_true_still_fires_once(app, monkeypatch):
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun

    monkeypatch.setattr(ds, '_payload_slate_coverage_unavailable_reason', lambda payload: None)
    monkeypatch.setattr(ds.appearance_ledger, 'appearance_ledger_publish_block',
                        lambda *a, **k: (None, None))
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot.id))

    run = SyncRun(job_name='sc03b04_commit_true')
    db.session.add(run)
    db.session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type=ds.SNAPSHOT_TYPE_BULLPEN_DASHBOARD, sync_run_id=run.id,
        status='pending', is_published=False, payload={'ok': True},
        payload_version=ds.DASHBOARD_PAYLOAD_VERSION, data_through=date(2026, 7, 23),
    )
    db.session.add(snapshot)
    db.session.flush()

    ds.publish_dashboard_snapshot(snapshot, commit=True)
    assert snapshot.is_published is True
    assert calls == [snapshot.id]  # exactly once


# -- config authority: one env var decides the flag, fail-safe on the unknown ----
#
# The production symptom was NOT config (both the web process and the daily-sync
# script share the single module-level ``app = create_app()`` in app.py, so they
# resolve one identical flag). These lock that authority down: ``create_app`` is the
# sole place ``SHARE_ARTIFACT_AUTOGENERATION`` becomes
# ``SHARE_ARTIFACT_AUTOGENERATION_ENABLED``; default is enabled; only an explicit
# affirmative enables it; anything unrecognized fails safe to disabled.


@pytest.mark.parametrize(
    'env_value, expected',
    [
        (None, True),      # absent -> enabled by default (an operational off-switch)
        ('true', True),
        ('True', True),
        ('TRUE', True),
        ('1', True),
        ('yes', True),
        ('false', False),
        ('0', False),
        ('no', False),
        ('', False),       # empty -> disabled
        ('maybe', False),  # unrecognized -> fail-safe disabled
        ('enabled', False),
        ('2', False),
    ],
)
def test_create_app_resolves_autogeneration_flag(monkeypatch, env_value, expected):
    from app import create_app

    if env_value is None:
        monkeypatch.delenv('SHARE_ARTIFACT_AUTOGENERATION', raising=False)
    else:
        monkeypatch.setenv('SHARE_ARTIFACT_AUTOGENERATION', env_value)

    real_app = create_app('test')
    assert real_app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] is expected


def test_daily_sync_and_web_resolve_the_same_config_authority():
    """Web and daily-sync are one config authority: both import the single
    module-level ``app = create_app()``. There is no second, sync-only config path
    that could resolve the flag differently."""
    from pathlib import Path

    sync_src = Path('scripts/run_daily_sync.py').read_text(encoding='utf-8')
    assert 'from app import app' in sync_src
    # The sync script never re-derives the flag itself.
    assert 'SHARE_ARTIFACT_AUTOGENERATION' not in sync_src

    app_src = Path('app.py').read_text(encoding='utf-8')
    # create_app is the sole site that maps the env var to the config flag.
    assert app_src.count("os.environ.get('SHARE_ARTIFACT_AUTOGENERATION'") == 1
    assert 'app = create_app()' in app_src


def test_operator_overview_reports_the_same_config_state(app):
    """The operator surface reads the identical config the hook gates on — a single
    source of truth, so what the operator sees is what generation actually does."""
    from services import share_artifact_operations as ops

    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    assert ops.autogeneration_enabled() is True
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = False
    assert ops.autogeneration_enabled() is False
