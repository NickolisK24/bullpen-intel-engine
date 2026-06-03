from datetime import datetime, timezone


def utc_now_naive():
    """Return a naive UTC datetime for existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
