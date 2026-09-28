"""Atomic orchestration for schedule authority and the Tonight public cache."""

from __future__ import annotations

from datetime import date, datetime

from services import schedule_authority
from services.tonight_intelligence_snapshot import (
    compose_tonight_snapshot_source,
    generate_tonight_snapshot_for_date,
)


# What this lane's Tonight rebuild is FOR, as stored provenance. The value is
# composed through the one governed composer rather than interpolated here, so
# the width contract is checked at the boundary instead of at COMMIT.
TONIGHT_REFRESH_PURPOSE = 'schedule_coherence'


def refresh_schedule(
    reference_date: date | None = None,
    *,
    source: str = 'morning_slate_schedule',
) -> dict:
    """Refresh schedule authority only (TN-11.7).

    Updates ``scheduled_games`` / ``slate_games`` for the rolling window around
    the product day. It builds no legacy tonight_v5 snapshot: the public Tonight
    authority is the immutable tonight_v1 row projected from each trusted
    Dashboard publication, so schedule coherence no longer requires a second,
    mutable Tonight cache. Partial ingestion reports ``partial`` and fails the
    caller closed exactly as before.
    """
    ref = _reference_date(reference_date)
    schedule = schedule_authority.ingest_rolling_window(ref, source=source)
    return {
        'status': schedule.get('status'),
        'reference_date': ref.isoformat(),
        'schedule': schedule,
        'legacy_tonight_v5': 'not_generated',
    }


def refresh_schedule_and_tonight(
    reference_date: date | None = None,
    *,
    source: str = 'morning_slate_schedule',
) -> dict:
    """Legacy compatibility: refresh schedule, then rebuild the tonight_v5 cache.

    Deprecated (TN-11.7). No scheduler, publication or repair path calls this;
    they use :func:`refresh_schedule`. It remains only so an operator can
    explicitly warm the deprecated ``contract=tonight_v5`` compatibility cache.
    Partial schedule ingestion fails closed and does not write a v5 snapshot.
    """
    ref = _reference_date(reference_date)
    schedule = schedule_authority.ingest_rolling_window(ref, source=source)
    result = {
        'status': schedule.get('status'),
        'reference_date': ref.isoformat(),
        'schedule': schedule,
        'tonight_snapshot': {
            'status': 'skipped',
            'reason': 'schedule_refresh_not_complete',
        },
    }
    if schedule.get('status') != 'ok':
        return result

    tonight = generate_tonight_snapshot_for_date(
        ref,
        source=compose_tonight_snapshot_source(source, TONIGHT_REFRESH_PURPOSE),
    )
    snapshot_ref = tonight.get('reference_date')
    snapshot_status = tonight.get('status')
    verified = snapshot_ref == ref.isoformat() and snapshot_status in {'ok', 'empty'}
    result['tonight_snapshot'] = {
        'status': snapshot_status,
        'reference_date': snapshot_ref,
        'card_count': int(tonight.get('card_count') or 0),
        'empty_reason': tonight.get('empty_reason'),
        'snapshot': tonight.get('snapshot'),
        'verified': verified,
    }
    result['status'] = 'ok' if verified else 'failed'
    if not verified:
        result['error'] = 'Tonight snapshot did not verify against the refreshed schedule date.'
    return result


def _reference_date(value) -> date:
    if value is None:
        return datetime.now(schedule_authority.EASTERN).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
