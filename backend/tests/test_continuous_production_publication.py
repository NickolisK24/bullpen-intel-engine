from datetime import date
from types import SimpleNamespace

from services import continuous_production_publication as publication


def test_publication_reuses_complete_dashboard_writer_and_refreshes_tonight(
    monkeypatch,
):
    snapshot = SimpleNamespace(id=52, is_published=True, error_message=None)
    calls = []
    monkeypatch.setattr(publication, 'current_publication_id', lambda: 41)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: calls.append(('dashboard', kwargs)) or snapshot,
    )
    monkeypatch.setattr(
        publication, 'product_current_date', lambda: date(2026, 8, 31),
    )
    monkeypatch.setattr(
        publication,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, **kwargs: calls.append(
            ('tonight', reference_date, kwargs)
        ),
    )

    result = publication.publish_continuous_update(
        {}, source_identity='final-observation', source_order=1,
        sync_run_id=91, expected_current_id=41,
    )

    assert result.committed is True
    assert result.previous_publication_id == 41
    assert result.new_publication_id == 52
    assert calls == [
        ('dashboard', {
            'sync_run_id': 91,
            'source': publication.PUBLICATION_SOURCE,
            'publish': True,
            'commit': True,
            'raise_errors': True,
            'publication_critical_complete': True,
        }),
        ('tonight', date(2026, 8, 31), {
            'source': publication.PUBLICATION_SOURCE,
        }),
    ]


def test_publication_refuses_when_serving_pointer_changed(monkeypatch):
    monkeypatch.setattr(publication, 'current_publication_id', lambda: 42)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError('writer must not run after pointer mismatch')
        ),
    )

    result = publication.publish_continuous_update(
        {}, source_identity='final-observation', source_order=1,
        sync_run_id=91, expected_current_id=41,
    )

    assert result.committed is False
    assert result.reason_code == 'expected_current_mismatch'
    assert result.previous_publication_id == 42


def test_tonight_failure_does_not_roll_back_published_dashboard(monkeypatch):
    snapshot = SimpleNamespace(id=52, is_published=True, error_message=None)
    monkeypatch.setattr(publication, 'current_publication_id', lambda: 41)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: snapshot,
    )
    monkeypatch.setattr(publication, 'product_current_date', lambda: date(2026, 8, 31))
    monkeypatch.setattr(
        publication,
        'generate_tonight_snapshot_for_date',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('warm failed')),
    )

    result = publication.publish_continuous_update(
        {}, source_identity='final-observation', source_order=1,
        sync_run_id=91, expected_current_id=41,
    )

    assert result.committed is True
    assert result.cache_handoff_status == 'retry_required'
    assert result.errors == ('RuntimeError',)


def test_retry_uses_durable_dashboard_receipt_instead_of_republishing(monkeypatch):
    prior = SimpleNamespace(
        id=52,
        is_published=True,
        error_message=None,
        source=publication.PUBLICATION_SOURCE,
        sync_run_id=91,
    )
    builds = []
    refreshes = []
    monkeypatch.setattr(publication, 'current_publication_id', lambda: prior.id)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'get_latest_valid_dashboard_snapshot',
        lambda: prior,
    )
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: builds.append(kwargs) or prior,
    )
    monkeypatch.setattr(
        publication, 'product_current_date', lambda: date(2026, 8, 31),
    )
    monkeypatch.setattr(
        publication,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, **kwargs: refreshes.append((reference_date, kwargs)),
    )

    result = publication.publish_continuous_update(
        {}, source_identity='final-observation', source_order=1,
        sync_run_id=91, expected_current_id=41,
    )

    assert result.status == 'already_committed'
    assert result.reason_code == 'production_snapshot_already_committed'
    assert result.committed is False
    assert result.previous_publication_id == 52
    assert result.new_publication_id == 52
    assert result.cache_handoff_status == 'complete'
    assert builds == []
    assert refreshes == [
        (date(2026, 8, 31), {'source': publication.PUBLICATION_SOURCE}),
    ]


def test_cache_only_retry_requires_existing_durable_receipt(monkeypatch):
    builds = []
    refreshes = []
    monkeypatch.setattr(publication, 'current_publication_id', lambda: 63)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'get_latest_valid_dashboard_snapshot',
        lambda: SimpleNamespace(
            id=63, source='daily_sync', sync_run_id=102,
        ),
    )
    monkeypatch.setattr(
        publication,
        '_published_receipt',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: builds.append(kwargs),
    )
    monkeypatch.setattr(
        publication,
        'generate_tonight_snapshot_for_date',
        lambda *args, **kwargs: refreshes.append((args, kwargs)),
    )

    result = publication.publish_continuous_update(
        {},
        source_identity='final-observation',
        source_order=1,
        sync_run_id=91,
        expected_current_id=52,
        require_published_receipt=True,
    )

    assert result.committed is False
    assert result.reason_code == 'publication_receipt_missing'
    assert result.cache_handoff_status == 'not_attempted'
    assert builds == []
    assert refreshes == []


def test_superseded_dashboard_receipt_prevents_duplicate_republication(monkeypatch):
    historical = SimpleNamespace(
        id=52,
        is_published=False,
        source=publication.PUBLICATION_SOURCE,
        sync_run_id=91,
    )
    current = SimpleNamespace(
        id=63,
        is_published=True,
        source='daily_sync',
        sync_run_id=102,
    )
    builds = []
    refreshes = []
    monkeypatch.setattr(publication, 'current_publication_id', lambda: current.id)
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'get_latest_valid_dashboard_snapshot',
        lambda: current,
    )
    monkeypatch.setattr(
        publication,
        '_published_receipt',
        lambda sync_run_id, **_kwargs: historical if sync_run_id == 91 else None,
    )
    monkeypatch.setattr(
        publication.dashboard_snapshot,
        'build_bullpen_dashboard_snapshot',
        lambda **kwargs: builds.append(kwargs),
    )
    monkeypatch.setattr(
        publication, 'product_current_date', lambda: date(2026, 8, 31),
    )
    monkeypatch.setattr(
        publication,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, **kwargs: refreshes.append((reference_date, kwargs)),
    )

    result = publication.publish_continuous_update(
        {}, source_identity='final-observation', source_order=1,
        sync_run_id=91, expected_current_id=52,
    )

    assert result.reason_code == 'production_snapshot_already_committed'
    assert result.new_publication_id == historical.id
    assert result.cache_handoff_status == 'complete'
    assert builds == []
    assert refreshes == [
        (date(2026, 8, 31), {'source': publication.PUBLICATION_SOURCE}),
    ]
