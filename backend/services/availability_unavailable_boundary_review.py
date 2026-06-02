"""Boundary review helpers for Candidate C Unavailable threshold analysis.

This module is evidence-only. It compares baseline thresholds with the
experiment candidate that raises the three-day Unavailable pitch threshold from
80 to 90 and formats human-reviewable transition data.
"""

from collections import Counter
from datetime import date, datetime, timezone
import json

from services.availability import (
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
)
from services.availability_threshold_audit import normalize_record, ordered_counts
from services.availability_unavailable_experiment import (
    classify_rows_for_candidate,
    pre_adoption_candidate_c_baseline,
    unavailable_candidates,
    unavailable_severe_signals,
)


BOUNDARY_TARGET_VALUES = [80, 81, 89, 90, 91]
REVIEW_SUPPORTS = 'Supports further review'
REVIEW_NEUTRAL = 'Neutral'
REVIEW_AGAINST = 'Evidence against change'


def baseline_candidate():
    return pre_adoption_candidate_c_baseline()


def candidate_c():
    return next(candidate for candidate in unavailable_candidates() if candidate.key == 'raise_three_day_90')


def _record_map(records):
    return {
        record['pitcher_id']: normalize_record(record)
        for record in records
    }


def _transition_key(original_status, candidate_status):
    return f'{original_status} -> {candidate_status}'


def case_from_records(baseline_record, candidate_record):
    inputs = baseline_record['inputs']
    baseline_thresholds = baseline_candidate().thresholds
    return {
        'pitcher_id': baseline_record['pitcher_id'],
        'pitcher_name': baseline_record['pitcher_name'],
        'team': baseline_record['team'],
        'original_status': baseline_record['availability_status'],
        'candidate_status': candidate_record['availability_status'],
        'fatigue_score': inputs.get('fatigue_score'),
        'pitches_yesterday': inputs.get('pitches_yesterday'),
        'pitches_last_3_days': inputs.get('pitches_last_3_days'),
        'pitches_last_5_days': inputs.get('pitches_last_5_days'),
        'appearances_last_3_days': inputs.get('appearances_last_3_days'),
        'appearances_last_5_days': inputs.get('appearances_last_5_days'),
        'days_rest': inputs.get('days_rest'),
        'baseline_severe_signals': unavailable_severe_signals(inputs, baseline_thresholds),
        'candidate_severe_signals': unavailable_severe_signals(inputs, candidate_c().thresholds),
        'reasons': baseline_record['reasons'],
    }


def moved_boundary_cases(baseline_records, candidate_records):
    baseline = _record_map(baseline_records)
    candidate = _record_map(candidate_records)
    cases = []
    for pitcher_id, baseline_record in baseline.items():
        candidate_record = candidate.get(pitcher_id)
        if candidate_record is None:
            continue
        if (
            baseline_record['availability_status'] == STATUS_UNAVAILABLE
            and candidate_record['availability_status'] != STATUS_UNAVAILABLE
        ):
            cases.append(case_from_records(baseline_record, candidate_record))

    cases.sort(key=lambda item: (
        item['pitches_last_3_days'] if item['pitches_last_3_days'] is not None else 999,
        item['pitcher_name'],
    ))
    return cases


def transition_counts(baseline_records, candidate_records):
    baseline = _record_map(baseline_records)
    candidate = _record_map(candidate_records)
    counter = Counter()
    for pitcher_id, baseline_record in baseline.items():
        candidate_record = candidate.get(pitcher_id)
        if candidate_record is None:
            continue
        counter[_transition_key(
            baseline_record['availability_status'],
            candidate_record['availability_status'],
        )] += 1
    return ordered_counts(counter, [])


def boundary_sensitivity(baseline_records, candidate_records, lower=80, upper=91):
    baseline = _record_map(baseline_records)
    candidate = _record_map(candidate_records)
    rows = []
    for value in range(lower, upper + 1):
        total = 0
        baseline_unavailable = 0
        candidate_avoid = 0
        candidate_unavailable = 0
        moved = 0
        example_names = []

        for pitcher_id, baseline_record in baseline.items():
            inputs = baseline_record['inputs']
            if inputs.get('pitches_last_3_days') != value:
                continue
            candidate_record = candidate.get(pitcher_id)
            if candidate_record is None:
                continue
            total += 1
            if baseline_record['availability_status'] == STATUS_UNAVAILABLE:
                baseline_unavailable += 1
            if candidate_record['availability_status'] == STATUS_AVOID:
                candidate_avoid += 1
            if candidate_record['availability_status'] == STATUS_UNAVAILABLE:
                candidate_unavailable += 1
            if (
                baseline_record['availability_status'] == STATUS_UNAVAILABLE
                and candidate_record['availability_status'] == STATUS_AVOID
            ):
                moved += 1
                if len(example_names) < 3:
                    example_names.append(baseline_record['pitcher_name'])

        rows.append({
            'pitches_last_3_days': value,
            'total': total,
            'baseline_unavailable': baseline_unavailable,
            'candidate_avoid': candidate_avoid,
            'candidate_unavailable': candidate_unavailable,
            'moved_unavailable_to_avoid': moved,
            'examples': example_names,
        })
    return rows


def closest_boundary_examples(baseline_records, candidate_records, target_values=None, per_value=3):
    target_values = target_values or BOUNDARY_TARGET_VALUES
    baseline = _record_map(baseline_records)
    candidate = _record_map(candidate_records)
    rows = []

    for value in target_values:
        matches = []
        for pitcher_id, baseline_record in baseline.items():
            inputs = baseline_record['inputs']
            if inputs.get('pitches_last_3_days') != value:
                continue
            candidate_record = candidate.get(pitcher_id)
            if candidate_record is None:
                continue
            matches.append(case_from_records(baseline_record, candidate_record))
        matches.sort(key=lambda item: (item['candidate_status'], item['pitcher_name']))
        rows.append({
            'target_value': value,
            'examples': matches[:per_value],
        })
    return rows


def distribution_analysis(cases):
    count_by_three_day = ordered_counts(Counter(
        item['pitches_last_3_days'] for item in cases
    ), [])
    baseline_signal_counts = Counter()
    candidate_signal_counts = Counter()
    fatigue_85_plus = 0
    yesterday_pitchers = 0
    four_in_five = 0
    for item in cases:
        baseline_signal_counts[len(item['baseline_severe_signals'])] += 1
        candidate_signal_counts[len(item['candidate_severe_signals'])] += 1
        if item['fatigue_score'] is not None and item['fatigue_score'] >= 85:
            fatigue_85_plus += 1
        if (item['pitches_yesterday'] or 0) > 0:
            yesterday_pitchers += 1
        if (item['appearances_last_5_days'] or 0) >= 4:
            four_in_five += 1

    values = [item['pitches_last_3_days'] for item in cases if item['pitches_last_3_days'] is not None]
    return {
        'pitches_last_3_days_min': min(values) if values else None,
        'pitches_last_3_days_max': max(values) if values else None,
        'count_by_three_day_pitches': count_by_three_day,
        'baseline_severe_signal_count_distribution': ordered_counts(baseline_signal_counts, []),
        'candidate_severe_signal_count_distribution': ordered_counts(candidate_signal_counts, []),
        'fatigue_85_plus': fatigue_85_plus,
        'pitched_yesterday': yesterday_pitchers,
        'four_appearances_in_5_days': four_in_five,
    }


def review_category(analysis, total_moved):
    if total_moved == 0:
        return REVIEW_NEUTRAL
    min_three_day = analysis['pitches_last_3_days_min']
    max_three_day = analysis['pitches_last_3_days_max']
    if min_three_day is None or max_three_day is None:
        return REVIEW_AGAINST
    if (
        min_three_day >= 80
        and max_three_day <= 89
        and analysis['candidate_severe_signal_count_distribution'] == {0: total_moved}
    ):
        return REVIEW_SUPPORTS
    return REVIEW_AGAINST


def build_review(baseline_records, candidate_records, reference_date=None):
    cases = moved_boundary_cases(baseline_records, candidate_records)
    baseline_unavailable = sum(
        1
        for record in _record_map(baseline_records).values()
        if record['availability_status'] == STATUS_UNAVAILABLE
    )
    total_moved = len(cases)
    analysis = distribution_analysis(cases)
    percent_affected = (total_moved / baseline_unavailable * 100) if baseline_unavailable else 0

    return {
        'reference_date': reference_date or date.today(),
        'candidate': candidate_c(),
        'total_moved': total_moved,
        'baseline_unavailable': baseline_unavailable,
        'percent_unavailable_affected': round(percent_affected, 1),
        'transition_counts': transition_counts(baseline_records, candidate_records),
        'distribution_analysis': analysis,
        'boundary_sensitivity': boundary_sensitivity(baseline_records, candidate_records),
        'closest_boundary_examples': closest_boundary_examples(baseline_records, candidate_records),
        'cases': cases,
        'recommendation_category': review_category(analysis, total_moved),
    }


def build_review_from_rows(rows, reference_date=None):
    reference_date = reference_date or date.today()
    baseline_records = classify_rows_for_candidate(
        rows,
        baseline_candidate(),
        reference_date=reference_date,
    )
    candidate_records = classify_rows_for_candidate(
        rows,
        candidate_c(),
        reference_date=reference_date,
    )
    return build_review(baseline_records, candidate_records, reference_date=reference_date)


def _format_value(value):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.1f}'.rstrip('0').rstrip('.')
    return str(value)


def _join(values):
    return '; '.join(str(item) for item in values) if values else 'none'


def _markdown_counts(title, counts, first_column='Value'):
    lines = [f'### {title}', '', f'| {first_column} | Count |', '|---|---:|']
    if not counts:
        lines.append('| none | 0 |')
    else:
        for key, count in counts.items():
            lines.append(f'| {_format_value(key)} | {count} |')
    lines.append('')
    return lines


def _markdown_case_table(title, cases):
    lines = [
        f'### {title}',
        '',
        '| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    if not cases:
        lines.append('| none |  |  |  |  |  |  |  |  |  |  |  |')
    else:
        for item in cases:
            lines.append(
                f"| {item['pitcher_name']} | {item.get('team') or ''} | "
                f"{item['original_status']} | {item['candidate_status']} | "
                f"{_format_value(item['fatigue_score'])} | "
                f"{_format_value(item['pitches_yesterday'])} | "
                f"{_format_value(item['pitches_last_3_days'])} | "
                f"{_format_value(item['pitches_last_5_days'])} | "
                f"{_format_value(item['appearances_last_3_days'])} | "
                f"{_format_value(item['appearances_last_5_days'])} | "
                f"{_format_value(item['days_rest'])} | {_join(item['reasons'])} |"
            )
    lines.append('')
    return lines


def _markdown_sensitivity_table(rows):
    lines = [
        '### Threshold Sensitivity By 3-Day Pitch Count',
        '',
        '| 3-day pitches | Total | Baseline Unavailable | Candidate Avoid | Candidate Unavailable | Moved Unavailable -> Avoid | Example moved pitchers |',
        '|---:|---:|---:|---:|---:|---:|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['pitches_last_3_days']} | {row['total']} | "
            f"{row['baseline_unavailable']} | {row['candidate_avoid']} | "
            f"{row['candidate_unavailable']} | {row['moved_unavailable_to_avoid']} | "
            f"{_join(row['examples'])} |"
        )
    lines.append('')
    return lines


def _markdown_closest_examples(groups):
    lines = ['### Closest Boundary Examples', '']
    for group in groups:
        lines.extend(_markdown_case_table(
            f"{group['target_value']} pitches in 3 days",
            group['examples'],
        ))
    return lines


def render_markdown_report(review, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    analysis = review['distribution_analysis']
    lines = [
        '# Availability Unavailable Boundary Review',
        '',
        f'Generated at: {generated_at.isoformat()}',
        f"Reference date: {review['reference_date']}",
        '',
        'This report reviews pitchers moved by Candidate C from the unavailable-threshold experiment.',
        'Candidate C raises the Unavailable three-day pitch threshold from 80 to 90.',
        'This report does not change thresholds, classifier logic, API behavior, dashboard behavior, or frontend behavior.',
        '',
        '## Summary',
        '',
        f"Total moved pitchers: {review['total_moved']}",
        f"Baseline Unavailable bucket: {review['baseline_unavailable']}",
        f"Percentage of Unavailable bucket affected: {review['percent_unavailable_affected']}%",
        f"Recommendation category: {review['recommendation_category']}",
        '',
    ]
    lines.extend(_markdown_counts('Status Transitions', review['transition_counts'], first_column='Transition'))
    lines.extend([
        '## Why Did These Pitchers Move?',
        '',
        f"All moved pitchers had {analysis['pitches_last_3_days_min']} to "
        f"{analysis['pitches_last_3_days_max']} pitches in 3 days.",
        'They crossed the baseline Unavailable 3-day pitch threshold of 80 but did not',
        'cross Candidate C threshold of 90. No moved pitcher retained another Candidate C',
        'Unavailable severe signal.',
        '',
        f"Moved pitchers with fatigue score >= 85: {analysis['fatigue_85_plus']}",
        f"Moved pitchers who pitched yesterday: {analysis['pitched_yesterday']}",
        f"Moved pitchers with 4+ appearances in 5 days: {analysis['four_appearances_in_5_days']}",
        '',
    ])
    lines.extend(_markdown_counts(
        'Moved Cases By 3-Day Pitch Count',
        analysis['count_by_three_day_pitches'],
        first_column='3-day pitches',
    ))
    lines.extend(_markdown_counts(
        'Baseline Severe Signal Count Distribution',
        analysis['baseline_severe_signal_count_distribution'],
        first_column='Signal count',
    ))
    lines.extend(_markdown_counts(
        'Candidate Severe Signal Count Distribution',
        analysis['candidate_severe_signal_count_distribution'],
        first_column='Signal count',
    ))
    lines.extend(['## Closest Boundary Examples', ''])
    lines.extend(_markdown_sensitivity_table(review['boundary_sensitivity']))
    lines.extend(_markdown_closest_examples(review['closest_boundary_examples']))
    lines.extend(['## Detailed Boundary Cases', ''])
    lines.extend(_markdown_case_table('All Moved Pitchers', review['cases']))
    lines.extend([
        '## Review Guidance',
        '',
        '- Supports further review means the transition set is coherent enough to justify human review.',
        '- Neutral means the evidence is inconclusive.',
        '- Evidence against change means the boundary review found a trust or workload-severity concern.',
        '',
        'This report is descriptive. It does not recommend threshold adoption.',
        '',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def render_json_report(review, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    payload = {
        'generated_at': generated_at.isoformat(),
        'reference_date': str(review['reference_date']),
        'candidate': {
            'key': review['candidate'].key,
            'changed_rule': review['candidate'].changed_rule,
        },
        'total_moved': review['total_moved'],
        'baseline_unavailable': review['baseline_unavailable'],
        'percent_unavailable_affected': review['percent_unavailable_affected'],
        'transition_counts': review['transition_counts'],
        'distribution_analysis': review['distribution_analysis'],
        'boundary_sensitivity': review['boundary_sensitivity'],
        'closest_boundary_examples': review['closest_boundary_examples'],
        'cases': review['cases'],
        'recommendation_category': review['recommendation_category'],
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
