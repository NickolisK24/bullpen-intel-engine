"""Aggregate classified workload records for availability and inventory summaries."""

from collections import Counter

from services.availability import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.availability_explanations import STALE_WORKLOAD_LIMITATION
from services.availability_snapshot import CURRENT_AVAILABILITY_MODE


SCORED_PITCHER_INVENTORY_MODE = 'scored_pitcher_inventory'


STATUS_ORDER = [
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
]

CONFIDENCE_ORDER = [
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
]

DATA_STATE_ORDER = [
    'fresh',
    'stale',
    'missing',
    'incomplete',
]

def _ordered_count(counter, order):
    counts = {key: int(counter.get(key, 0)) for key in order}
    for key in sorted(counter):
        if key not in counts:
            counts[key] = int(counter[key])
    return counts


def _availability_from_record(record):
    if not record:
        return {}
    return record.get('availability') or {}


def _summary_notes(total_pitchers, data_state_counts, is_current_availability=True):
    if total_pitchers == 0:
        if is_current_availability:
            return ['No availability classifications are available yet.']
        return ['No scored pitcher inventory records are available yet.']

    stale = data_state_counts.get('stale', 0)
    missing = data_state_counts.get('missing', 0)
    incomplete = data_state_counts.get('incomplete', 0)
    limited = stale + missing + incomplete
    notes = []

    if limited > total_pitchers / 2:
        if is_current_availability:
            notes.append('Recent usage information is missing for most pitchers, so most availability reads are less certain.')
        else:
            notes.append('Recent usage information is missing for most scored pitchers, so inventory workload reads are less certain.')
    elif limited > 0:
        if is_current_availability:
            notes.append('Recent usage information is incomplete for some pitchers, so some availability reads are less certain.')
        else:
            notes.append('Recent usage information is incomplete for some scored pitchers, so inventory workload reads are less certain.')
    else:
        if is_current_availability:
            notes.append('Availability classifications are based on current workload data.')
        else:
            notes.append('Scored pitcher inventory is based on current workload data.')

    if stale:
        if is_current_availability:
            notes.append(STALE_WORKLOAD_LIMITATION)
        else:
            notes.append('Stale workload data is retained here as inventory context, not bullpen availability.')
    if missing:
        if is_current_availability:
            notes.append('Missing workload history makes availability reads less certain.')
        else:
            notes.append('Missing workload history makes inventory reads less certain.')
    if incomplete:
        if is_current_availability:
            notes.append('Incomplete workload inputs make availability reads less certain.')
        else:
            notes.append('Incomplete workload inputs make inventory reads less certain.')

    return notes


def summarize_availability_records(records, mode=CURRENT_AVAILABILITY_MODE, is_current_availability=True):
    """Build an ordered status/confidence/data-state summary from classified records."""
    records = list(records or [])
    status_counts = Counter()
    confidence_counts = Counter()
    data_state_counts = Counter()

    for record in records:
        availability = _availability_from_record(record)
        status_counts[availability.get('availability_status') or 'Unknown'] += 1
        confidence_counts[availability.get('confidence') or 'unknown'] += 1
        data_state_counts[availability.get('data_state') or 'unknown'] += 1

    total_pitchers = len(records)

    return {
        'mode': mode,
        'is_current_availability': bool(is_current_availability),
        'total_pitchers': total_pitchers,
        'statuses': _ordered_count(status_counts, STATUS_ORDER),
        'confidence': _ordered_count(confidence_counts, CONFIDENCE_ORDER),
        'data_state': _ordered_count(data_state_counts, DATA_STATE_ORDER),
        'notes': _summary_notes(
            total_pitchers,
            data_state_counts,
            is_current_availability=is_current_availability,
        ),
    }


def summarize_scored_pitcher_inventory(records):
    return summarize_availability_records(
        records,
        mode=SCORED_PITCHER_INVENTORY_MODE,
        is_current_availability=False,
    )
