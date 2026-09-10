from datetime import date

from services import schedule_tonight_refresh


REF_DATE = date(2026, 7, 23)


def test_successful_schedule_refresh_rebuilds_and_verifies_tonight(monkeypatch):
    calls = []

    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {
            'status': 'ok',
            'start_date': '2026-07-22',
            'end_date': '2026-07-26',
            'summary': {'errors': 0},
        },
    )

    def fake_generate(reference_date, *, source):
        calls.append((reference_date, source))
        return {
            'status': 'ok',
            'reference_date': REF_DATE.isoformat(),
            'card_count': 5,
            'cards': [{}] * 5,
            'snapshot': {'source': source},
        }

    monkeypatch.setattr(
        schedule_tonight_refresh,
        'generate_tonight_snapshot_for_date',
        fake_generate,
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE,
        source='morning_slate_schedule',
    )

    assert result['status'] == 'ok'
    assert result['reference_date'] == REF_DATE.isoformat()
    assert result['tonight_snapshot']['verified'] is True
    assert result['tonight_snapshot']['card_count'] == 5
    assert calls == [
        (REF_DATE, 'morning_slate_schedule:schedule_coherence'),
    ]


def test_empty_tonight_snapshot_is_valid_when_it_matches_refreshed_date(monkeypatch):
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {'status': 'ok', 'summary': {'errors': 0}},
    )
    monkeypatch.setattr(
        schedule_tonight_refresh,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, source: {
            'status': 'empty',
            'reference_date': REF_DATE.isoformat(),
            'card_count': 0,
            'empty_reason': 'no_games',
        },
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(REF_DATE)

    assert result['status'] == 'ok'
    assert result['tonight_snapshot']['verified'] is True
    assert result['tonight_snapshot']['empty_reason'] == 'no_games'


def test_partial_schedule_refresh_does_not_publish_tonight(monkeypatch):
    generated = []
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {
            'status': 'partial',
            'summary': {'errors': 1},
        },
    )
    monkeypatch.setattr(
        schedule_tonight_refresh,
        'generate_tonight_snapshot_for_date',
        lambda *args, **kwargs: generated.append((args, kwargs)),
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(REF_DATE)

    assert result['status'] == 'partial'
    assert result['tonight_snapshot'] == {
        'status': 'skipped',
        'reason': 'schedule_refresh_not_complete',
    }
    assert generated == []


def test_mismatched_tonight_reference_date_fails_closed(monkeypatch):
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {'status': 'ok', 'summary': {'errors': 0}},
    )
    monkeypatch.setattr(
        schedule_tonight_refresh,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, source: {
            'status': 'ok',
            'reference_date': '2026-07-22',
            'card_count': 4,
        },
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(REF_DATE)

    assert result['status'] == 'failed'
    assert result['tonight_snapshot']['verified'] is False
    assert 'did not verify' in result['error']


def test_unexpected_tonight_status_fails_closed(monkeypatch):
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {'status': 'ok', 'summary': {'errors': 0}},
    )
    monkeypatch.setattr(
        schedule_tonight_refresh,
        'generate_tonight_snapshot_for_date',
        lambda reference_date, source: {
            'status': 'failed',
            'reference_date': REF_DATE.isoformat(),
            'card_count': 0,
        },
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(REF_DATE)

    assert result['status'] == 'failed'
    assert result['tonight_snapshot']['verified'] is False
