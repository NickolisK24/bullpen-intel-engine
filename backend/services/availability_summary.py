"""Aggregate current Availability Engine output for dashboard trust summaries."""

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


def _summary_notes(total_pitchers, data_state_counts):
    if total_pitchers == 0:
        return ['No availability classifications are available yet.']

    stale = data_state_counts.get('stale', 0)
    missing = data_state_counts.get('missing', 0)
    incomplete = data_state_counts.get('incomplete', 0)
    limited = stale + missing + incomplete
    notes = []

    if limited > total_pitchers / 2:
        notes.append('Most pitchers are classified from stale or missing workload data.')
    elif limited > 0:
        notes.append('Some availability classifications are limited by stale or incomplete workload data.')
    else:
        notes.append('Availability classifications are based on fresh workload data.')

    if stale:
        notes.append(STALE_WORKLOAD_LIMITATION)
    if missing:
        notes.append('Missing workload history reduces availability confidence.')
    if incomplete:
        notes.append('Incomplete workload inputs reduce availability confidence.')

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
        'notes': _summary_notes(total_pitchers, data_state_counts),
    }
