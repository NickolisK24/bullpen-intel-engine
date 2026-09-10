from datetime import datetime, timezone


def utc_now_naive():
    """Return a naive UTC datetime for existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_iso(value):
    """Serialize a value as an unambiguous, timezone-explicit ISO string.

    Our DateTime columns store naive UTC, which serializes without a timezone
    marker (e.g. "2026-06-23T11:07:33") and is then mis-parsed by browsers as
    local time. This treats a naive datetime as UTC and emits an explicit-UTC
    ISO string ending in "Z" so callers render the correct local/ET time.

    A ``date`` (no time component) is returned as a plain date ISO string
    (timezone has no meaning for a calendar date), and ``None`` stays ``None``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    return value.isoformat()
