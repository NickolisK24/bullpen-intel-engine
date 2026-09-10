"""
Aggregation helpers for auditing Availability Engine threshold behavior.

This module does not classify pitchers. It summarizes already-classified
availability records so scripts and tests can inspect current V1 behavior
without duplicating or changing threshold logic.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
    THRESHOLDS,
)


STATUS_ORDER = [
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
]

CONFIDENCE_ORDER = ['high', 'medium', 'low']
DATA_STATE_ORDER = ['fresh', 'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown']

NUMERIC_INPUTS = [
    'fatigue_score',
    'pitches_yesterday',
    'pitches_last_3_days',
    'pitches_last_5_days',
]

APPEARANCE_INPUTS = [
    'appearances_last_3_days',
    'appearances_last_5_days',
]

BOUNDARIES = [
    ('fatigue_score', 'Monitor fatigue', THRESHOLDS.monitor_fatigue_score),
    ('fatigue_score', 'Limited fatigue', THRESHOLDS.limited_fatigue_score),
    ('fatigue_score', 'Avoid fatigue', THRESHOLDS.avoid_fatigue_score),
    ('fatigue_score', 'Unavailable fatigue', THRESHOLDS.unavailable_fatigue_score),
    ('pitches_yesterday', 'Monitor yesterday pitches', THRESHOLDS.monitor_pitches_yesterday),
    ('pitches_yesterday', 'Limited yesterday pitches', THRESHOLDS.limited_pitches_yesterday),
    ('pitches_yesterday', 'Avoid yesterday pitches', THRESHOLDS.avoid_pitches_yesterday),
    ('pitches_yesterday', 'Unavailable yesterday pitches', THRESHOLDS.unavailable_pitches_yesterday),
    ('pitches_last_3_days', 'Monitor 3-day pitches', THRESHOLDS.monitor_pitches_last_3_days),
    ('pitches_last_3_days', 'Limited 3-day pitches', THRESHOLDS.limited_pitches_last_3_days),
    ('pitches_last_3_days', 'Avoid 3-day pitches', THRESHOLDS.avoid_pitches_last_3_days),
    ('pitches_last_3_days', 'Unavailable 3-day pitches', THRESHOLDS.unavailable_pitches_last_3_days),
    ('pitches_last_5_days', 'Limited 5-day pitches', THRESHOLDS.limited_pitches_last_5_days),
    ('pitches_last_5_days', 'Avoid 5-day pitches', THRESHOLDS.avoid_pitches_last_5_days),
    ('appearances_last_3_days', 'Limited 3-day appearances', THRESHOLDS.limited_appearances_last_3_days),
    ('appearances_last_3_days', 'Avoid 3-day appearances', THRESHOLDS.avoid_appearances_last_3_days),
    ('appearances_last_5_days', 'Monitor 5-day appearances', THRESHOLDS.monitor_appearances_last_5_days),
    ('appearances_last_5_days', 'Limited 5-day appearances', THRESHOLDS.limited_appearances_last_5_days),
    ('appearances_last_5_days', 'Avoid 5-day appearances', THRESHOLDS.avoid_appearances_last_5_days),
]


def normalize_record(record):
    availability = record.get('availability', {})
    inputs = availability.get('inputs') or record.get('inputs') or {}
    return {
        'pitcher_id': record.get('pitcher_id'),
        'pitcher_name': record.get('pitcher_name') or 'Unknown pitcher',
        'team': record.get('team'),
        'availability_status': availability.get('availability_status') or record.get('availability_status'),
        'confidence': availability.get('confidence') or record.get('confidence') or 'unknown',
        'data_state': availability.get('data_state') or record.get('data_state') or 'unknown',
        'reasons': list(availability.get('reasons') or record.get('reasons') or []),
        'limitations': list(availability.get('limitations') or record.get('limitations') or []),
        'inputs': inputs,
    }


def ordered_counts(counter, order=None):
    result = {}
    order = order or []
    for key in order:
        if counter.get(key, 0):
            result[key] = counter[key]
    for key in sorted(counter.keys(), key=lambda item: str(item)):
        if key not in result:
            result[key] = counter[key]
    return result


def median(values):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def summarize_numeric(values):
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return {'count': 0, 'min': None, 'median': None, 'max': None}
    return {
        'count': len(cleaned),
        'min': min(cleaned),
        'median': median(cleaned),
        'max': max(cleaned),
    }


def reason_frequencies(records):
    counter = Counter()
    for record in records:
        counter.update(record['reasons'])
    return counter


def status_by_data_state(records):
    table = defaultdict(Counter)
    for record in records:
        table[record['data_state']][record['availability_status']] += 1
    state_totals = Counter({key: sum(value.values()) for key, value in table.items()})
    return {
        state: ordered_counts(table[state], STATUS_ORDER)
        for state in ordered_counts(state_totals, DATA_STATE_ORDER)
    }


def select_near_threshold_examples(records, limit=12):
    records = [normalize_record(record) for record in records]
    candidates = []
    for record in records:
        inputs = record['inputs']
        for input_name, boundary_name, threshold in BOUNDARIES:
            value = inputs.get(input_name)
            if value is None:
                continue
            distance = abs(float(value) - float(threshold))
            candidates.append({
                'pitcher_id': record['pitcher_id'],
                'pitcher_name': record['pitcher_name'],
                'team': record['team'],
                'availability_status': record['availability_status'],
                'confidence': record['confidence'],
                'data_state': record['data_state'],
                'input': input_name,
                'boundary': boundary_name,
                'value': value,
                'threshold': threshold,
                'distance': round(distance, 2),
                'reasons': record['reasons'],
            })

    candidates.sort(key=lambda item: (item['distance'], item['pitcher_name'], item['boundary']))
    return candidates[:limit]


def summarize_records(records, near_threshold_limit=12, top_reason_limit=15):
    normalized = [normalize_record(record) for record in records]
    status_counts = Counter(record['availability_status'] for record in normalized)
    confidence_counts = Counter(record['confidence'] for record in normalized)
    data_state_counts = Counter(record['data_state'] for record in normalized)
    reason_counts = reason_frequencies(normalized)

    numeric_summary = {
        key: summarize_numeric([record['inputs'].get(key) for record in normalized])
        for key in NUMERIC_INPUTS
    }

    appearance_distribution = {
        key: ordered_counts(Counter(record['inputs'].get(key) for record in normalized), [])
        for key in APPEARANCE_INPUTS
    }

    return {
        'total_pitchers': len(normalized),
        'status_distribution': ordered_counts(status_counts, STATUS_ORDER),
        'confidence_distribution': ordered_counts(confidence_counts, CONFIDENCE_ORDER),
        'data_state_distribution': ordered_counts(data_state_counts, DATA_STATE_ORDER),
        'status_by_data_state': status_by_data_state(normalized),
        'top_reason_frequencies': reason_counts.most_common(top_reason_limit),
        'workload_input_summary': numeric_summary,
        'appearance_distributions': appearance_distribution,
        'data_quality_counts': {
            'stale': data_state_counts.get('stale', 0),
            'missing': data_state_counts.get('missing', 0),
            'incomplete': data_state_counts.get('incomplete', 0),
        },
        'near_threshold_examples': select_near_threshold_examples(normalized, limit=near_threshold_limit),
    }


def _format_value(value):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.1f}'.rstrip('0').rstrip('.')
    return str(value)


def _markdown_counts(title, counts):
    lines = [f'### {title}', '', '| Value | Count |', '|---|---:|']
    if not counts:
        lines.append('| none | 0 |')
    else:
        for key, count in counts.items():
            lines.append(f'| {key} | {count} |')
    lines.append('')
    return lines


def _markdown_numeric(summary):
    lines = ['### Workload Input Summary', '', '| Input | Count | Min | Median | Max |', '|---|---:|---:|---:|---:|']
    for key, values in summary.items():
        lines.append(
            f"| {key} | {values['count']} | {_format_value(values['min'])} | "
            f"{_format_value(values['median'])} | {_format_value(values['max'])} |"
        )
    lines.append('')
    return lines


def _markdown_appearance(summary):
    lines = ['### Appearance Distributions', '']
    for key, counts in summary.items():
        lines.extend([f'#### {key}', '', '| Appearances | Count |', '|---:|---:|'])
        for appearances, count in counts.items():
            lines.append(f'| {_format_value(appearances)} | {count} |')
        lines.append('')
    return lines


def _markdown_reason_frequencies(reason_counts):
    lines = ['### Top Reason Frequencies', '', '| Reason | Count |', '|---|---:|']
    if not reason_counts:
        lines.append('| none | 0 |')
    else:
        for reason, count in reason_counts:
            lines.append(f'| {reason} | {count} |')
    lines.append('')
    return lines


def _markdown_status_by_state(table):
    lines = ['### Status By Data State', '', '| Data state | Status | Count |', '|---|---|---:|']
    if not table:
        lines.append('| none | none | 0 |')
    else:
        for state, statuses in table.items():
            for status, count in statuses.items():
                lines.append(f'| {state} | {status} | {count} |')
    lines.append('')
    return lines


def _markdown_near_threshold(examples):
    lines = [
        '### Near-Threshold Examples',
        '',
        '| Pitcher | Team | Status | Data state | Boundary | Value | Threshold | Distance | Reasons |',
        '|---|---|---|---|---|---:|---:|---:|---|',
    ]
    if not examples:
        lines.append('| none |  |  |  |  |  |  |  |  |')
    else:
        for item in examples:
            reasons = '; '.join(item['reasons']) if item['reasons'] else 'none'
            lines.append(
                f"| {item['pitcher_name']} | {item.get('team') or ''} | {item['availability_status']} | "
                f"{item['data_state']} | {item['boundary']} | {_format_value(item['value'])} | "
                f"{_format_value(item['threshold'])} | {_format_value(item['distance'])} | {reasons} |"
            )
    lines.append('')
    return lines


def render_markdown_report(current_summary, snapshot_summary=None, generated_at=None, reference_date=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    lines = [
        '# Availability Threshold Audit',
        '',
        f'Generated at: {generated_at.isoformat()}',
        f'Current reference date: {reference_date or "today"}',
        '',
        'This report audits current Availability Engine output using the existing classifier.',
        'It is evidence for later threshold review only; it does not change thresholds.',
        '',
        'Trust note: current classifications keep fresh, stale, missing, and incomplete data separate.',
        'Stale or missing Monitor counts should not be read as workload-driven Monitor counts.',
        'Latest-workload snapshot output anchors each pitcher to their latest game date to inspect',
        'historical workload windows; it is not current bullpen availability.',
        '',
    ]

    for title, summary in [
        ('Current Availability Output', current_summary),
        ('Latest-Workload Snapshot Output', snapshot_summary),
    ]:
        if summary is None:
            continue
        lines.extend([
            f'## {title}',
            '',
            f"Total pitchers evaluated: {summary['total_pitchers']}",
            '',
        ])
        lines.extend(_markdown_counts('Status Distribution', summary['status_distribution']))
        lines.extend(_markdown_counts('Confidence Distribution', summary['confidence_distribution']))
        lines.extend(_markdown_counts('Data State Distribution', summary['data_state_distribution']))
        lines.extend(_markdown_status_by_state(summary['status_by_data_state']))
        lines.extend(_markdown_reason_frequencies(summary['top_reason_frequencies']))
        lines.extend(_markdown_numeric(summary['workload_input_summary']))
        lines.extend(_markdown_appearance(summary['appearance_distributions']))
        lines.extend(_markdown_counts('Stale/Incomplete/Missing Counts', summary['data_quality_counts']))
        lines.extend(_markdown_near_threshold(summary['near_threshold_examples']))

    return '\n'.join(lines).rstrip() + '\n'


def render_json_report(current_summary, snapshot_summary=None, generated_at=None, reference_date=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    payload = {
        'generated_at': generated_at.isoformat(),
        'reference_date': str(reference_date or 'today'),
        'trust_note': 'Stale or missing Monitor counts are separated from workload-driven Monitor counts.',
        'current': current_summary,
        'latest_workload_snapshot': snapshot_summary,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
