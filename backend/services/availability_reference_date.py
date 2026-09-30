from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRODUCT_TIMEZONE = 'America/New_York'
PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION = (
    'Product timezone could not be loaded; product day was resolved in UTC.'
)

# Mirrors ``ScheduledGame.STATE_POSTPONED`` without importing models here.
SCHEDULE_STATE_POSTPONED = 'postponed'
# Rows after the product day that prove the schedule window covered the gap.
SCHEDULE_CONFIRMATION_LOOKAHEAD_DAYS = 3

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


def schedule_aware_availability_reference_date(coverage_date, as_of_date=None, schedule_rows=()):
    """The canonical availability reference date: which baseball day a read describes.

    ``coverage_date`` is the latest date with ingested workload (``data_through``).
    ``as_of_date`` is the explicit product day the read is being produced for.
    ``schedule_rows`` are ScheduledGame-like rows (``game_date``,
    ``status_state``) for dates after ``coverage_date``.

    The day after coverage is always the earliest honest reference. The reference
    moves further forward, one calendar day at a time and never past
    ``as_of_date``, only across dates the schedule authority confirms were
    league-wide no-game dates: no row on that date other than a postponed game,
    and schedule rows exist on some later date (so the ingested window covered
    it). Data through Sep 27 read on Sep 29 after a Sep 28 off-day therefore
    describes Sep 29, and a Sep 27 appearance is two days old, not "yesterday".

    Any other gap date stops the advance: a final game there is data lag (played
    but not ingested), and a scheduled, live, suspended or unknown game is
    unresolved. The read then keeps its own earlier, honestly labelled date
    instead of claiming a recovery day that is not proven. Returns ``None`` when
    there is no coverage date.
    """
    base = product_availability_reference_date(latest_game_date=coverage_date)
    as_of = parse_reference_date(as_of_date)
    if base is None or as_of is None or as_of <= base:
        return base

    live_dates = set()
    latest_row_date = None
    for row in schedule_rows or ():
        day = parse_reference_date(getattr(row, 'game_date', None))
        if day is None:
            continue
        if latest_row_date is None or day > latest_row_date:
            latest_row_date = day
        if getattr(row, 'status_state', None) != SCHEDULE_STATE_POSTPONED:
            live_dates.add(day)

    reference = base
    while reference < as_of:
        gap_day = reference
        if gap_day in live_dates or latest_row_date is None or latest_row_date <= gap_day:
            break
        reference = gap_day + timedelta(days=1)
    return reference


def load_schedule_rows_after(coverage_date, as_of_date):
    """One bounded ``scheduled_games`` read for the gap after ``coverage_date``."""
    from models.scheduled_game import ScheduledGame

    coverage = parse_reference_date(coverage_date)
    as_of = parse_reference_date(as_of_date)
    if coverage is None or as_of is None or as_of <= coverage + timedelta(days=1):
        return []
    horizon = as_of + timedelta(days=SCHEDULE_CONFIRMATION_LOOKAHEAD_DAYS)
    return (
        ScheduledGame.query
        .with_entities(ScheduledGame.game_date, ScheduledGame.status_state)
        .filter(ScheduledGame.game_date > coverage)
        .filter(ScheduledGame.game_date <= horizon)
        .all()
    )


def resolve_availability_reference_date(coverage_date, as_of_date=None, schedule_rows=None):
    """Schedule-aware reference date, loading schedule rows only when a gap exists."""
    if schedule_rows is None:
        schedule_rows = load_schedule_rows_after(coverage_date, as_of_date)
    return schedule_aware_availability_reference_date(
        coverage_date, as_of_date, schedule_rows,
    )


def product_availability_reference_date_from_metadata(metadata):
    """Reference date for durable workload metadata.

    Metadata collected with an explicit as-of date carries its schedule-aware
    ``availability_reference_date`` (see ``sync_metadata``); otherwise this is
    the day after coverage.
    """
    metadata = metadata or {}
    resolved = parse_reference_date(metadata.get('availability_reference_date'))
    if resolved is not None:
        return resolved
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


def trusted_slate_reference_dates(data_through, availability_reference_date=None):
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

    A trusted snapshot's own ``availability_reference_date`` was resolved
    schedule-aware at publication (it may sit past ``slate + 1`` across off-days).
    Pass it so a reread describes the same day the publication does; a value that
    is not after the slate is ignored.
    """
    slate = parse_reference_date(data_through)
    if not isinstance(slate, date):
        return None, None
    published = parse_reference_date(availability_reference_date)
    if isinstance(published, date) and published > slate:
        return slate, published
    return slate, product_availability_reference_date(latest_game_date=slate)
