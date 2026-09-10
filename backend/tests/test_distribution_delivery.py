import json
from datetime import date, datetime
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from app import create_app
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from scripts import resolve_distribution_publication
from scripts.export_team_story_pages import _snapshot_generated_at
from services import distribution_delivery, sync_due
from services.distribution_delivery import (
    DistributionDeliveryRequest,
    request_distribution_delivery,
)
from services.sync_execution_context import SOURCE_EXTERNAL_SCHEDULE
from tests.db_config import create_test_schema, drop_test_schema
from utils.db import db


@pytest.fixture
def scheduling_app(tmp_path, monkeypatch):
    database_url = f'sqlite:///{(tmp_path / "distribution-scheduling.db").as_posix()}'
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('TEST_DATABASE_URL', database_url)
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('AUTO_SYNC', 'false')
    app = create_app('test')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _delivery():
    return DistributionDeliveryRequest(
        snapshot_id=1754,
        sync_run_id=2303,
        data_through='2026-09-01',
        publication_source='external_schedule',
        publication_type='postgame',
    )


def test_dispatch_carries_exact_publication_without_exposing_token():
    captured = {}

    class Response:
        status = 204

    def opener(request, timeout):
        captured['request'] = request
        captured['timeout'] = timeout
        return Response()

    result = request_distribution_delivery(
        _delivery(),
        environ={distribution_delivery.TOKEN_ENV: 'secret-token'},
        opener=opener,
    )

    payload = json.loads(captured['request'].data)
    assert result['status'] == 'requested'
    assert payload == {
        'ref': 'main',
        'inputs': {
            'mode': 'distribution',
            'snapshot_id': '1754',
            'sync_run_id': '2303',
            'data_through': '2026-09-01',
            'publication_source': 'external_schedule',
            'publication_type': 'postgame',
        },
    }
    assert captured['request'].full_url.endswith(
        '/actions/workflows/baseballos-generated-distribution.yml/dispatches'
    )
    assert 'secret-token' not in json.dumps(result)


def test_missing_token_is_explicit_non_secret_failure():
    result = request_distribution_delivery(_delivery(), environ={})
    assert result == {
        'status': 'failed_to_request',
        'reason': 'dispatch_token_missing',
        'snapshot_id': 1754,
    }


def test_github_failure_is_sanitized():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 403, 'denied', {}, None)

    result = request_distribution_delivery(
        _delivery(),
        environ={distribution_delivery.TOKEN_ENV: 'secret-token'},
        opener=opener,
    )
    assert result['status'] == 'failed_to_request'
    assert result['reason'] == 'github_http_403'
    assert 'denied' not in json.dumps(result)


def test_render_publication_advance_requests_delivery(
    scheduling_app, monkeypatch,
):
    before = SimpleNamespace(id=1753)
    after = SimpleNamespace(
        id=1754,
        sync_run_id=2303,
        data_through=date(2026, 9, 1),
    )
    snapshots = iter((before, after))
    monkeypatch.setattr(sync_due, '_current_published_snapshot', lambda: next(snapshots))
    monkeypatch.setattr(
        sync_due,
        '_run_postgame',
        lambda *args, **kwargs: (
            {'status': 'success', 'sync_run_id': 2303},
            {'verified': True},
            True,
        ),
    )
    captured = {}

    def request(delivery):
        captured['delivery'] = delivery
        return {'status': 'requested', 'snapshot_id': delivery.snapshot_id}

    monkeypatch.setattr(sync_due, 'request_distribution_delivery', request)
    context = sync_due.SyncExecutionContext(
        mode='postgame',
        source=SOURCE_EXTERNAL_SCHEDULE,
        scheduled_for=sync_due.datetime(2026, 9, 1, 2, 5, tzinfo=sync_due.timezone.utc),
    )

    result = sync_due.run_due_sync(scheduling_app, context)

    assert result['status'] == 'executed'
    assert result['distribution_delivery']['status'] == 'requested'
    assert captured['delivery'] == DistributionDeliveryRequest(
        snapshot_id=1754,
        sync_run_id=2303,
        data_through='2026-09-01',
        publication_source='external_schedule',
        publication_type='postgame',
    )


def test_no_publication_advance_skips_delivery(scheduling_app, monkeypatch):
    current = SimpleNamespace(id=1753, sync_run_id=2302, data_through=date(2026, 8, 31))
    monkeypatch.setattr(sync_due, '_current_published_snapshot', lambda: current)
    monkeypatch.setattr(
        sync_due,
        '_run_postgame',
        lambda *args, **kwargs: (
            {'status': 'success', 'sync_run_id': 2303},
            {'verified': True},
            True,
        ),
    )
    monkeypatch.setattr(
        sync_due,
        'request_distribution_delivery',
        lambda delivery: (_ for _ in ()).throw(AssertionError('must not dispatch')),
    )
    context = sync_due.SyncExecutionContext(
        mode='postgame',
        source=SOURCE_EXTERNAL_SCHEDULE,
        scheduled_for=sync_due.datetime(2026, 9, 1, 2, 5, tzinfo=sync_due.timezone.utc),
    )

    result = sync_due.run_due_sync(scheduling_app, context)

    assert result['status'] == 'executed'
    assert result['distribution_delivery'] == {
        'status': 'skipped',
        'reason': 'publication_not_advanced',
        'snapshot_id': 1753,
    }


def test_distribution_request_failure_does_not_invalidate_publication(
    scheduling_app, monkeypatch,
):
    before = SimpleNamespace(id=1753)
    after = SimpleNamespace(
        id=1754,
        sync_run_id=2303,
        data_through=date(2026, 9, 1),
    )
    snapshots = iter((before, after))
    monkeypatch.setattr(sync_due, '_current_published_snapshot', lambda: next(snapshots))
    monkeypatch.setattr(
        sync_due,
        '_run_postgame',
        lambda *args, **kwargs: (
            {'status': 'success', 'sync_run_id': 2303},
            {'verified': True},
            True,
        ),
    )
    monkeypatch.setattr(
        sync_due,
        'request_distribution_delivery',
        lambda delivery: {
            'status': 'failed_to_request',
            'reason': 'github_unreachable',
            'snapshot_id': delivery.snapshot_id,
        },
    )
    context = sync_due.SyncExecutionContext(
        mode='postgame',
        source=SOURCE_EXTERNAL_SCHEDULE,
        scheduled_for=sync_due.datetime(2026, 9, 1, 2, 5, tzinfo=sync_due.timezone.utc),
    )

    result = sync_due.run_due_sync(scheduling_app, context)

    assert result['status'] == 'executed'
    assert result['distribution_delivery']['status'] == 'failed_to_request'


def test_publication_resolver_pins_current_identity_and_refuses_stale(
    scheduling_app, monkeypatch,
):
    with scheduling_app.app_context():
        prior_run = SyncRun(
            job_name='postgame_refresh',
            source='external_schedule',
            status='success',
            stage='published',
        )
        db.session.add(prior_run)
        db.session.flush()
        prior = DashboardSnapshot(
            snapshot_type='bullpen_dashboard',
            sync_run_id=prior_run.id,
            status='ready',
            is_published=False,
            data_through=date(2026, 8, 31),
            payload={},
            source='postgame_refresh',
        )
        db.session.add(prior)
        run = SyncRun(
            job_name='postgame_refresh',
            source='external_schedule',
            status='success',
            stage='published',
        )
        db.session.add(run)
        db.session.flush()
        snapshot = DashboardSnapshot(
            snapshot_type='bullpen_dashboard',
            sync_run_id=run.id,
            status='ready',
            is_published=True,
            data_through=date(2026, 9, 1),
            payload={},
            source='postgame_refresh',
        )
        db.session.add(snapshot)
        db.session.flush()
        run.published_dashboard_snapshot_id = snapshot.id
        snapshot.published_at = datetime(2026, 9, 1, 2, 7)
        db.session.commit()
        monkeypatch.setattr(
            resolve_distribution_publication.dashboard_snapshot_service,
            'get_latest_valid_dashboard_snapshot',
            lambda: snapshot,
        )

        resolved = resolve_distribution_publication.resolve_publication(
            snapshot_id=snapshot.id,
            sync_run_id=run.id,
            data_through='2026-09-01',
            publication_source='external_schedule',
            publication_type='postgame',
        )
        assert resolved['publication_snapshot_id'] == snapshot.id
        assert resolved['sync_run_id'] == run.id
        assert resolved['current'] is True

        with pytest.raises(ValueError, match='requested_snapshot_not_current'):
            resolve_distribution_publication.resolve_publication(
                snapshot_id=prior.id,
            )


def test_team_export_retry_uses_stable_snapshot_timestamp():
    snapshot = SimpleNamespace(
        snapshot_generated_at=sync_due.datetime(2026, 9, 1, 2, 6),
    )
    assert _snapshot_generated_at(snapshot) == '2026-09-01T02:06:00+00:00'
    assert _snapshot_generated_at(snapshot) == _snapshot_generated_at(snapshot)
