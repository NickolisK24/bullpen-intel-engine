"""Tests for to_utc_iso — unambiguous, timezone-explicit timestamp serialization.

Naive UTC datetimes (our DateTime-column convention) must serialize with an
explicit 'Z' so the frontend renders the correct local/ET time instead of
mis-parsing the bare string as browser-local time. Calendar dates stay date-only.
"""

from datetime import date, datetime, timedelta, timezone

from utils.time import to_utc_iso


def test_naive_datetime_is_marked_utc_with_z():
    assert to_utc_iso(datetime(2026, 6, 23, 11, 7, 33)) == '2026-06-23T11:07:33Z'


def test_aware_datetime_is_converted_to_utc_z():
    eastern = timezone(timedelta(hours=-4))
    # 07:07 -04:00 == 11:07 UTC
    assert to_utc_iso(datetime(2026, 6, 23, 7, 7, 33, tzinfo=eastern)) == '2026-06-23T11:07:33Z'


def test_date_stays_date_only():
    assert to_utc_iso(date(2026, 6, 22)) == '2026-06-22'


def test_none_passthrough():
    assert to_utc_iso(None) is None


def test_user_facing_datetime_is_timezone_explicit():
    out = to_utc_iso(datetime(2026, 1, 2, 3, 4, 5))
    assert out.endswith('Z')
    assert '+00:00' not in out
