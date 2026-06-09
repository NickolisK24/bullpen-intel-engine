from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRODUCT_TIMEZONE = 'America/New_York'


def parse_reference_date(value):
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def product_current_date(now=None, timezone_name=PRODUCT_TIMEZONE):
    """
    Calendar date used for staleness checks.

    This is intentionally product-timezone based, not host-local, so local
    development and deployed workers do not diverge around UTC midnight.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    try:
        product_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        product_timezone = timezone.utc
    return current.astimezone(product_timezone).date()


def product_availability_reference_date(latest_workload_date=None, latest_game_date=None):
    """
    Date used for current availability calculations.

    Availability reads are anchored to stored baseball workload coverage. A
    data set through June 7 describes the next availability read on June 8.
    """
    coverage_date = (
        parse_reference_date(latest_workload_date)
        or parse_reference_date(latest_game_date)
    )
    if coverage_date is None:
        return None
    return coverage_date + timedelta(days=1)


def product_availability_reference_date_from_metadata(metadata):
    metadata = metadata or {}
    return product_availability_reference_date(
        latest_workload_date=metadata.get('latest_workload_date'),
        latest_game_date=metadata.get('latest_game_date'),
    )


def product_availability_reference_date_from_sync_status(sync_status):
    sync_status = sync_status or {}
    if not sync_status.get('last_successful_sync'):
        return None
    freshness = sync_status.get('freshness') or {}
    existing = parse_reference_date(freshness.get('availability_reference_date'))
    if existing is not None:
        return existing
    existing = parse_reference_date(sync_status.get('availability_reference_date'))
    if existing is not None:
        return existing
    data = sync_status.get('data') or {}
    return product_availability_reference_date_from_metadata(data)
