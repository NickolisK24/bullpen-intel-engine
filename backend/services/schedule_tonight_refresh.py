"""Atomic orchestration for schedule authority and the Tonight public cache."""

from __future__ import annotations

from datetime import date, datetime

from services import schedule_authority
from services.tonight_intelligence_snapshot import generate_tonight_snapshot_for_date


def refresh_schedule_and_tonight(
    reference_date: date | None = None,
    *,
    source: str = 'morning_slate_schedule',
) -> dict:
    """Refresh schedule authority, then rebuild Tonight for the same product day.

    A schedule refresh is not successful for public-serving purposes until the
    Tonight cache has been regenerated from the newly committed schedule rows.
    Partial schedule ingestion fails closed and does not publish a new Tonight
    snapshot.
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
        source=f'{source}:schedule_coherence',
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
