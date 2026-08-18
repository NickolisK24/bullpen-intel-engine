from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRODUCT_TIMEZONE = 'America/New_York'
PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION = (
    'Product timezone could not be loaded; product day was resolved in UTC.'
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductDay:
    """Resolved product-timezone calendar authority for pipeline date decisions."""

    calendar_date: date
    local_datetime: datetime
    timezone_name: str
    limitations: tuple[str, ...] = ()


def parse_reference_date(value):
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def resolve_product_day(now=None, timezone_name=PRODUCT_TIMEZONE) -> ProductDay:
    """
    Resolve the BaseballOS product day from a UTC instant.

    This is intentionally product-timezone based, not host-local, so local
    development and deployed workers do not diverge around UTC midnight. If
    the configured product timezone cannot be loaded, UTC is used explicitly
    and the returned ``limitations`` tuple records that degraded authority.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    limitations = ()
    try:
        product_timezone = ZoneInfo(timezone_name)
        resolved_timezone_name = timezone_name
    except ZoneInfoNotFoundError:
        product_timezone = timezone.utc
        resolved_timezone_name = 'UTC'
        limitations = (PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION,)
        logger.warning(
            '%s configured_timezone=%s',
            PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION,
            timezone_name,
        )
    local_datetime = current.astimezone(product_timezone)
    return ProductDay(
        calendar_date=local_datetime.date(),
        local_datetime=local_datetime,
        timezone_name=resolved_timezone_name,
        limitations=limitations,
    )


def product_current_date(now=None, timezone_name=PRODUCT_TIMEZONE):
    """
    Calendar date used for staleness checks.

    This delegates to the shared product-day resolver so read and write paths
    agree on the same timezone authority.
    """
    return resolve_product_day(now=now, timezone_name=timezone_name).calendar_date


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


def trusted_slate_reference_dates(data_through):
    """Split one trusted source's slate into its two governed reference dates.

    A trusted publication carries a single ``data_through`` (the slate its
    evidence covers), but two different questions are asked of it and they have
    different correct answers:

    * ``membership_reference_date`` — the slate itself. The roster authority only
      resolves for the date its roster snapshot covers, so active-bullpen
      membership must be asked on the slate day. Asking on the day after strands
      the read as authority-missing, which is what refused every team once a
      slate went final.
    * ``availability_reference_date`` — the slate plus one day, from
      :func:`product_availability_reference_date`. Availability describes the
      bullpen a reader is about to watch, not the one that just finished
      working: "a data set through June 7 describes the next availability read
      on June 8."

    Collapsing the two into one value classifies arms a day early, which keeps a
    second day of used arms out of the clean bucket and disagrees with every
    live read of the same bullpen. Returns ``(None, None)`` when ``data_through``
    is not a usable date, so callers fail closed to their prior behavior.
    """
    slate = parse_reference_date(data_through)
    if not isinstance(slate, date):
        return None, None
    return slate, product_availability_reference_date(latest_game_date=slate)
