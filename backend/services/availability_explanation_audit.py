"""Audit helpers for Availability Engine explanation quality.

This module summarizes already-classified availability records. It never
reclassifies pitchers and never changes thresholds.
"""

from collections import Counter
from datetime import datetime, timezone
import json

from services.availability_explanations import (
    CATEGORY_ORDER,
    categorize_limitation,
    categorize_reason,
    reason_catalog,
)
from services.availability_threshold_audit import normalize_record, ordered_counts


def _category_rank(category):
    if category in CATEGORY_ORDER:
        return CATEGORY_ORDER.index(category)
    return len(CATEGORY_ORDER)


def _frequency_rows(counter, categorizer):
    rows = [
        {
            'category': categorizer(text),
            'text': text,
            'count': count,
        }
        for text, count in counter.items()
    ]
    rows.sort(key=lambda row: (_category_rank(row['category']), -row['count'], row['text']))
    return rows


def _category_distribution(rows):
    counts = Counter()
    for row in rows:
        counts[row['category']] += row['count']
    return ordered_counts(counts, CATEGORY_ORDER)


def audit_explanations(records):
    normalized = [normalize_record(record) for record in records]
    reason_counts = Counter()
    limitation_counts = Counter()

    for record in normalized:
        reason_counts.update(record['reasons'])
        limitation_counts.update(record['limitations'])

    reason_rows = _frequency_rows(reason_counts, categorize_reason)
    limitation_rows = _frequency_rows(limitation_counts, categorize_limitation)

    return {
        'total_pitchers': len(normalized),
        'total_reasons': sum(reason_counts.values()),
        'unique_reasons': len(reason_counts),
        'total_limitations': sum(limitation_counts.values()),
        'unique_limitations': len(limitation_counts),
        'reason_category_distribution': _category_distribution(reason_rows),
        'limitation_category_distribution': _category_distribution(limitation_rows),
        'reason_frequencies': reason_rows,
        'limitation_frequencies': limitation_rows,
        'reason_catalog': reason_catalog(),
    }


def _markdown_counts(title, counts):
    lines = [f'### {title}', '', '| Category | Count |', '|---|---:|']
    if not counts:
        lines.append('| none | 0 |')
    else:
        for category, count in counts.items():
            lines.append(f'| {category} | {count} |')
    lines.append('')
    return lines


def _markdown_frequency_table(title, rows):
    lines = [f'### {title}', '', '| Category | Text | Count |', '|---|---|---:|']
    if not rows:
        lines.append('| none | none | 0 |')
    else:
        for row in rows:
            lines.append(f"| {row['category']} | {row['text']} | {row['count']} |")
    lines.append('')
    return lines


def _markdown_catalog(rows):
    lines = [
        '### Possible Reason Catalog',
        '',
        '| Category | Rule | Template | Example |',
        '|---|---|---|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['category']} | {row['rule']} | {row['template']} | {row['example']} |"
        )
    lines.append('')
    return lines


def render_markdown_report(current_audit, snapshot_audit=None, generated_at=None, reference_date=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    lines = [
        '# Availability Explanation Quality Audit',
        '',
        f'Generated at: {generated_at.isoformat()}',
        f'Current reference date: {reference_date or "today"}',
        '',
        'This report audits Availability Engine explanation text using existing classified records.',
        'It is evidence for wording consistency and review only; it does not change thresholds,',
        'status outcomes, fatigue scoring, or API response structure.',
        '',
        'Trust note: reasons describe deterministic workload or data-state facts. Limitations',
        'describe context BaseballOS does not know, such as injuries or team-reported availability.',
        '',
    ]

    for title, audit in [
        ('Current Availability Explanations', current_audit),
        ('Latest-Workload Snapshot Explanations', snapshot_audit),
    ]:
        if audit is None:
            continue
        lines.extend([
            f'## {title}',
            '',
            f"Total pitchers evaluated: {audit['total_pitchers']}",
            f"Total reasons observed: {audit['total_reasons']}",
            f"Unique reasons observed: {audit['unique_reasons']}",
            f"Total limitations observed: {audit['total_limitations']}",
            f"Unique limitations observed: {audit['unique_limitations']}",
            '',
        ])
        lines.extend(_markdown_counts('Reason Category Distribution', audit['reason_category_distribution']))
        lines.extend(_markdown_frequency_table('Observed Reason Frequencies', audit['reason_frequencies']))
        lines.extend(_markdown_counts('Limitation Category Distribution', audit['limitation_category_distribution']))
        lines.extend(_markdown_frequency_table('Observed Limitation Frequencies', audit['limitation_frequencies']))
        lines.extend(_markdown_catalog(audit['reason_catalog']))

    return '\n'.join(lines).rstrip() + '\n'


def render_json_report(current_audit, snapshot_audit=None, generated_at=None, reference_date=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    payload = {
        'generated_at': generated_at.isoformat(),
        'reference_date': str(reference_date or 'today'),
        'trust_note': 'Reasons are workload or data-state facts; limitations are missing context.',
        'current': current_audit,
        'latest_workload_snapshot': snapshot_audit,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
