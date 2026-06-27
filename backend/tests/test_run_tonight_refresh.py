"""Tests for scripts/run_tonight_refresh.py (production schedule + Tonight warm).

The script refreshes a rolling MLB schedule window and warms the Tonight snapshot
for the product current date. These exercise the injectable orchestration core
(run_refresh) with stubs — no real app/database — covering: schedule ingestion is
called for the right window, the Tonight snapshot is warmed, empty cards are a
valid (non-failure) state, a true ingestion exception propagates (nonzero exit),
and a warm failure is reported safely without crashing the refresh.
"""

from contextlib import contextmanager
from datetime import date

import pytest

import scripts.run_tonight_refresh as rtr


class _FakeApp:
    @contextmanager
    def app_context(self):
        yield


def _today_fn(d=date(2026, 6, 27)):
    return lambda: d


def _ok_ingest(calls):
    def ingest(start, end, *, source):
        calls.append((start, end, source))
        return {'games_seen': 30, 'rows_created': 60, 'errors': 0}
    return ingest


# ── Window + resolution helpers ───────────────────────────────────────────────

def test_window_is_ten_days_each_side():
    start, end = rtr._window(date(2026, 6, 27))
    assert start == '2026-06-17'
    assert end == '2026-07-07'


def test_resolve_today_prefers_explicit_then_product_date():
    assert rtr._resolve_today('2026-07-01', date(2026, 6, 27)) == date(2026, 7, 1)
    assert rtr._resolve_today(None, date(2026, 6, 27)) == date(2026, 6, 27)


def test_arg_parser_accepts_expected_flags():
    args = rtr._parse_args(['--reference-date', '2026-06-27', '--source', 'manual'])
    assert args.reference_date == '2026-06-27'
    assert args.source == 'manual'


# ── Orchestration: ingest + warm ──────────────────────────────────────────────

def test_run_refresh_ingests_window_and_warms_tonight():
    ingest_calls = []
    warm_calls = []

    def warm(today, source):
        warm_calls.append((today, source))
        return {'status': 'ok', 'card_count': 3, 'empty_reason': None}

    out = rtr.run_refresh(
        _FakeApp(), source='github_actions', reference_date=None,
        ingest_fn=_ok_ingest(ingest_calls), today_fn=_today_fn(), warm_fn=warm)

    assert ingest_calls == [('2026-06-17', '2026-07-07', 'github_actions')]
    assert warm_calls == [(date(2026, 6, 27), 'github_actions')]
    assert out['status'] == 'ok'
    assert out['reference_date'] == '2026-06-27'
    assert out['schedule_window'] == {'start_date': '2026-06-17', 'end_date': '2026-07-07'}
    assert out['tonight_snapshot'] == {'status': 'ok', 'card_count': 3, 'empty_reason': None}


def test_empty_tonight_cards_are_not_a_failure():
    out = rtr.run_refresh(
        _FakeApp(), source='manual', reference_date=None,
        ingest_fn=_ok_ingest([]), today_fn=_today_fn(),
        warm_fn=lambda today, source: {
            'status': 'empty', 'card_count': 0, 'empty_reason': 'no_teams_playing_today'})
    assert out['status'] == 'ok'   # the refresh succeeded
    assert out['tonight_snapshot']['status'] == 'empty'
    assert out['tonight_snapshot']['empty_reason'] == 'no_teams_playing_today'


def test_partial_when_schedule_ingestion_reports_row_errors():
    def ingest(start, end, *, source):
        return {'games_seen': 30, 'rows_created': 58, 'errors': 1}
    out = rtr.run_refresh(
        _FakeApp(), source='manual', reference_date=None,
        ingest_fn=ingest, today_fn=_today_fn(),
        warm_fn=lambda today, source: {'status': 'ok', 'card_count': 2})
    assert out['status'] == 'partial'


# ── Failure handling ──────────────────────────────────────────────────────────

def test_schedule_ingestion_exception_propagates():
    # A true ingestion failure must surface (the caller exits nonzero).
    def boom(start, end, *, source):
        raise RuntimeError('MLB schedule fetch failed')
    with pytest.raises(RuntimeError):
        rtr.run_refresh(_FakeApp(), source='manual', reference_date=None,
                        ingest_fn=boom, today_fn=_today_fn(),
                        warm_fn=lambda today, source: {'status': 'ok'})


def test_tonight_warm_failure_is_reported_safely():
    def warm_boom(today, source):
        raise RuntimeError('snapshot build exploded')
    out = rtr.run_refresh(
        _FakeApp(), source='manual', reference_date=None,
        ingest_fn=_ok_ingest([]), today_fn=_today_fn(), warm_fn=warm_boom)
    # The refresh still succeeds (schedule rows were committed); warm is flagged.
    assert out['status'] == 'ok'
    assert out['tonight_snapshot']['status'] == 'failed'
    assert 'snapshot build exploded' in out['tonight_snapshot']['error']


def test_explicit_reference_date_is_honored():
    ingest_calls = []
    out = rtr.run_refresh(
        _FakeApp(), source='manual', reference_date='2026-07-01',
        ingest_fn=_ok_ingest(ingest_calls), today_fn=_today_fn(),
        warm_fn=lambda today, source: {'status': 'ok', 'card_count': 1})
    assert out['reference_date'] == '2026-07-01'
    assert ingest_calls == [('2026-06-21', '2026-07-11', 'manual')]
