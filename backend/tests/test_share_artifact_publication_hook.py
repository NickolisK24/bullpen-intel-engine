"""Tests for the post-publication Team State generation hook (Share Cards
SC-03B-02).

Proves generation is wired into the trusted-snapshot publication lifecycle:
a committed successful publication automatically attempts league-wide batch
generation with the authoritative snapshot context, exactly once, after the
publication has committed — and that a downstream generation failure never rolls
back or unpublishes the snapshot. No scheduler, renderer, frontend, or public
endpoint is involved.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
from services import dashboard_snapshot as ds
from services import share_artifact_batch_generation as batch_module
from services import share_artifact_publication_hook as hook_module
from services.dashboard_snapshot import (
    DASHBOARD_PAYLOAD_VERSION,
    SNAPSHOT_STATUS_READY,
    SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
    publish_dashboard_snapshot,
)
from services.share_artifact_batch_generation import BatchSourceAuthorityError
from services.share_artifact_publication_hook import (
    POST_PUBLICATION_ACTOR,
    run_post_publication_generation,
)
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
# Reuse the SC-03B-01 batch test scaffolding (plain helpers, not fixtures).
from tests.test_share_artifact_batch_generation import (
    PRODUCT_DATE,
    SNAPSHOT_ID,
    TEAM_IDS,
    _install_snapshot,
    _real_generator,
    _seed_teams,
)
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


def _fake_published_snapshot(*, snapshot_id=SNAPSHOT_ID, data_through=PRODUCT_DATE,
                             is_published=True, status=SNAPSHOT_STATUS_READY):
    class _Snap:
        pass
    snap = _Snap()
    snap.id = snapshot_id
    snap.data_through = data_through
    snap.is_published = is_published
    snap.status = status
    return snap


def _make_publishable_snapshot(monkeypatch, *, data_through=PRODUCT_DATE):
    """Build a real DashboardSnapshot that will reach the publish success path.

    Bypasses the slate-coverage and appearance-ledger withhold gates (exercised
    elsewhere) so this suite can focus on the publication->generation wiring.
    """
    monkeypatch.setattr(ds, '_payload_slate_coverage_unavailable_reason', lambda payload: None)
    monkeypatch.setattr(ds.appearance_ledger, 'appearance_ledger_publish_block',
                        lambda *a, **k: (None, None))
    run = SyncRun(job_name='sc03b02_publication_test')
    db.session.add(run)
    db.session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status='pending',
        is_published=False,
        payload={'ok': True},
        payload_version=DASHBOARD_PAYLOAD_VERSION,
        data_through=data_through,
        snapshot_generated_at=datetime(2026, 7, 20, 12, 0, 0),
        source='sc03b02_test',
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


# ---------------------------------------------------------------------------
# Direct hook: authoritative context, exactly once, guards, isolation
# ---------------------------------------------------------------------------


# 2 / 3 / 5 — authoritative snapshot id + product date propagated, exactly once.
def test_hook_propagates_authoritative_context_exactly_once(app, monkeypatch):
    calls = []

    def _spy(*, source_snapshot_id, product_date, actor, generator=None, **kwargs):
        calls.append((source_snapshot_id, product_date, actor))

        class _R:  # minimal stand-in for BatchGenerationResult logging fields
            attempted_count = generated_count = reused_count = 0
            refused_count = failed_count = missing_count = 0
        return _R()

    monkeypatch.setattr(batch_module, 'generate_team_state_artifacts_batch', _spy)
    snap = _fake_published_snapshot()
    run_post_publication_generation(snap)
    assert calls == [(SNAPSHOT_ID, PRODUCT_DATE, POST_PUBLICATION_ACTOR)]


# Only a published snapshot authorizes generation.
def test_hook_does_not_fire_for_unpublished_snapshot(app, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_module, 'generate_team_state_artifacts_batch',
                        lambda **k: calls.append(k))
    assert run_post_publication_generation(_fake_published_snapshot(is_published=False)) is None
    assert run_post_publication_generation(None) is None
    assert calls == []


# A published snapshot with no product date fails closed (never guesses).
def test_hook_skips_when_no_product_date(app, monkeypatch):
    calls = []
    monkeypatch.setattr(batch_module, 'generate_team_state_artifacts_batch',
                        lambda **k: calls.append(k))
    assert run_post_publication_generation(_fake_published_snapshot(data_through=None)) is None
    assert calls == []


# 8 — an unexpected batch exception is isolated (hook never raises).
def test_hook_isolates_unexpected_batch_exception(app, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError('batch exploded')

    monkeypatch.setattr(batch_module, 'generate_team_state_artifacts_batch', _boom)
    assert run_post_publication_generation(_fake_published_snapshot()) is None


# A governed batch source-authority refusal is a non-fatal None.
def test_hook_isolates_source_authority_refusal(app, monkeypatch):
    def _refuse(**kwargs):
        raise BatchSourceAuthorityError('snapshot_stale')

    monkeypatch.setattr(batch_module, 'generate_team_state_artifacts_batch', _refuse)
    assert run_post_publication_generation(_fake_published_snapshot()) is None


# 1 / 6 — the hook drives the real batch and reruns reuse (idempotent).
def test_hook_generates_then_reuses_through_real_batch(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)  # canonical published snapshot matches id/date/trusted
    snap = _fake_published_snapshot()
    first = run_post_publication_generation(snap, generator=_real_generator())
    assert first is not None
    assert first.source_snapshot_id == SNAPSHOT_ID
    assert first.product_date == PRODUCT_DATE
    assert first.generated_count == len(TEAM_IDS)
    assert first.missing_count == 0
    second = run_post_publication_generation(snap, generator=_real_generator())
    assert second.generated_count == 0
    assert second.reused_count == len(TEAM_IDS)
    assert ShareArtifact.query.filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    ).count() == len(TEAM_IDS)


# ---------------------------------------------------------------------------
# Integration through publish_dashboard_snapshot
# ---------------------------------------------------------------------------


# 1 / 4 / 5 / 9 — a committed publication triggers generation once, after commit,
# with the snapshot already canonical.
def test_publish_triggers_generation_once_after_commit(app, monkeypatch):
    observed = []

    def _spy(snapshot, **kwargs):
        # At hook time the snapshot must already be the committed canonical one.
        persisted = db.session.get(DashboardSnapshot, snapshot.id)
        observed.append({
            'is_published': snapshot.is_published,
            'status': snapshot.status,
            'persisted_published': bool(persisted and persisted.is_published),
        })
        return None

    monkeypatch.setattr(hook_module, 'run_post_publication_generation', _spy)
    snapshot = _make_publishable_snapshot(monkeypatch)
    result = publish_dashboard_snapshot(snapshot, commit=True)

    assert result.is_published is True and result.status == SNAPSHOT_STATUS_READY
    assert len(observed) == 1  # exactly once
    assert observed[0]['is_published'] is True
    assert observed[0]['status'] == SNAPSHOT_STATUS_READY
    assert observed[0]['persisted_published'] is True  # publication committed first
    # Snapshot remains canonical/published.
    assert db.session.get(DashboardSnapshot, snapshot.id).is_published is True


# 7 — a generation failure never rolls back / unpublishes the snapshot.
def test_generation_failure_does_not_unpublish(app, monkeypatch):
    def _boom(snapshot, **kwargs):
        raise RuntimeError('hook exploded')

    monkeypatch.setattr(hook_module, 'run_post_publication_generation', _boom)
    snapshot = _make_publishable_snapshot(monkeypatch)
    result = publish_dashboard_snapshot(snapshot, commit=True)  # must not raise
    assert result.is_published is True
    assert db.session.get(DashboardSnapshot, snapshot.id).is_published is True


# The hook is gated: with the flag absent (bare-Flask apps), publication does not
# generate — this is why existing publication tests are unaffected.
def test_generation_gated_off_when_flag_absent(app, monkeypatch):
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = False
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    snapshot = _make_publishable_snapshot(monkeypatch)
    publish_dashboard_snapshot(snapshot, commit=True)
    assert calls == []


# A withheld publication (not published) never triggers generation.
def test_withheld_publication_does_not_generate(app, monkeypatch):
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    # Force the slate-coverage withhold gate.
    monkeypatch.setattr(ds, '_payload_slate_coverage_unavailable_reason',
                        lambda payload: 'slate_coverage_incomplete')
    run = SyncRun(job_name='sc03b02_withheld')
    db.session.add(run)
    db.session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD, sync_run_id=run.id,
        status='pending', is_published=False, payload={'ok': True},
        payload_version=DASHBOARD_PAYLOAD_VERSION, data_through=PRODUCT_DATE,
        snapshot_generated_at=datetime(2026, 7, 20, 12, 0, 0), source='sc03b02_test',
    )
    db.session.add(snapshot)
    db.session.flush()
    result = publish_dashboard_snapshot(snapshot, commit=True)
    assert result.is_published is False
    assert calls == []


# A non-committed publish (commit=False) does not fire generation.
def test_uncommitted_publish_does_not_generate(app, monkeypatch):
    calls = []
    monkeypatch.setattr(hook_module, 'run_post_publication_generation',
                        lambda snapshot, **k: calls.append(snapshot))
    snapshot = _make_publishable_snapshot(monkeypatch)
    publish_dashboard_snapshot(snapshot, commit=False)
    assert calls == []


# 10 / 11 / 12 — no browser/frontend, renderer, or public-endpoint dependency.
def test_hook_has_no_web_renderer_or_frontend_dependency():
    from pathlib import Path
    hook_src = Path(hook_module.__file__).read_text(encoding='utf-8')
    for forbidden in ('request', 'jsonify', 'render', 'Blueprint', 'evidenceCard', 'frontend'):
        assert forbidden not in hook_src, f'hook must not reference {forbidden}'
    # The batch operation is never exposed on a public route (only the internal
    # admin surface added in SC-03B-01).
    from app import create_app
    real_app = create_app('test')
    gen_routes = [str(r) for r in real_app.url_map.iter_rules()
                  if 'batch' in str(r) or 'team-state/generate' in str(r)]
    assert all(r.startswith('/api/internal/share-artifacts/') for r in gen_routes)
