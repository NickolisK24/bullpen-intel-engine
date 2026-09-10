"""Experiment helpers for Availability Engine Unavailable threshold review.

This module compares current thresholds against candidate Unavailable-only
changes. It does not mutate production thresholds or API behavior.
"""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import json

from services.availability import (
    ACTIVE_WINDOW_DAYS,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    THRESHOLDS,
    AvailabilityThresholds,
    classify_availability,
)
from services.availability_explanations import CATEGORY_ORDER, categorize_reason
from services.availability_snapshot import (
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    evaluation_date_for_mode,
    latest_game_date_for,
    logs_for_availability_window,
)
from services.availability_threshold_audit import (
    STATUS_ORDER,
    normalize_record,
    ordered_counts,
    summarize_records,
)


UNAVAILABLE_RULES = [
    {
        'key': 'pitches_yesterday',
        'rule': 'Pitches yesterday',
        'condition': 'pitches_yesterday >= 50',
    },
    {
        'key': 'pitches_last_3_days',
        'rule': 'Three-day pitch volume',
        'condition': 'pitches_last_3_days >= 90',
    },
    {
        'key': 'appearances_and_5_day_pitches',
        'rule': 'Five-day appearance/workload combination',
        'condition': 'appearances_last_5_days >= 4 and pitches_last_5_days >= 75',
    },
    {
        'key': 'fatigue_and_yesterday',
        'rule': 'Critical fatigue plus heavy yesterday workload',
        'condition': 'fatigue_score >= 85.0 and pitches_yesterday >= 35',
    },
]

PRE_ADOPTION_UNAVAILABLE_PITCHES_LAST_3_DAYS = 80


@dataclass(frozen=True)
class UnavailableCandidate:
    key: str
    label: str
    changed_rule: str
    thresholds: AvailabilityThresholds
    focus_input: str | None = None
    focus_threshold: float | None = None
    require_multiple_severe_signals: bool = False


def _with_threshold(**overrides):
    return replace(THRESHOLDS, **overrides)


def pre_adoption_candidate_c_baseline():
    return UnavailableCandidate(
        key='pre_adoption_baseline',
        label='Pre-adoption baseline',
        changed_rule='Historical production threshold before Candidate C adoption',
        thresholds=_with_threshold(
            unavailable_pitches_last_3_days=PRE_ADOPTION_UNAVAILABLE_PITCHES_LAST_3_DAYS,
        ),
        focus_input='pitches_last_3_days',
        focus_threshold=PRE_ADOPTION_UNAVAILABLE_PITCHES_LAST_3_DAYS,
    )


def unavailable_candidates():
    return [
        UnavailableCandidate(
            key='raise_fatigue_90',
            label='Candidate A: raise Unavailable fatigue threshold',
            changed_rule='unavailable_fatigue_score: 85.0 -> 90.0',
            thresholds=_with_threshold(unavailable_fatigue_score=90.0),
            focus_input='fatigue_score',
            focus_threshold=90.0,
        ),
        UnavailableCandidate(
            key='raise_yesterday_55',
            label='Candidate B: raise Unavailable yesterday pitch threshold',
            changed_rule='unavailable_pitches_yesterday: 50 -> 55',
            thresholds=_with_threshold(unavailable_pitches_yesterday=55),
            focus_input='pitches_yesterday',
            focus_threshold=55,
        ),
        UnavailableCandidate(
            key='raise_three_day_90',
            label='Candidate C: adopted Unavailable three-day pitch threshold',
            changed_rule='adopted production baseline: unavailable_pitches_last_3_days = 90',
            thresholds=_with_threshold(unavailable_pitches_last_3_days=90),
            focus_input='pitches_last_3_days',
            focus_threshold=90,
        ),
        UnavailableCandidate(
            key='raise_five_day_combo_85',
            label='Candidate D: raise Unavailable five-day combo pitch threshold',
            changed_rule='unavailable_multi_day_pitch_threshold: 75 -> 85 when appearances_last_5_days >= 4',
            thresholds=_with_threshold(unavailable_multi_day_pitch_threshold=85),
            focus_input='pitches_last_5_days',
            focus_threshold=85,
        ),
        UnavailableCandidate(
            key='require_two_severe_signals',
            label='Candidate E: require two severe signals for Unavailable',
            changed_rule='Require at least two current Unavailable rule signals before preserving Unavailable',
            thresholds=THRESHOLDS,
            require_multiple_severe_signals=True,
        ),
    ]


def unavailable_severe_signals(inputs, thresholds=THRESHOLDS):
    signals = []
    fatigue = inputs.get('fatigue_score')
    pitches_yesterday = inputs.get('pitches_yesterday') or 0
    pitches_3 = inputs.get('pitches_last_3_days') or 0
    pitches_5 = inputs.get('pitches_last_5_days') or 0
    apps_5 = inputs.get('appearances_last_5_days') or 0

    if pitches_yesterday >= thresholds.unavailable_pitches_yesterday:
        signals.append(f'{pitches_yesterday} pitches yesterday')
    if pitches_3 >= thresholds.unavailable_pitches_last_3_days:
        signals.append(f'{pitches_3} pitches in 3 days')
    if apps_5 >= 4 and pitches_5 >= thresholds.unavailable_multi_day_pitch_threshold:
        signals.append(f'{apps_5} appearances and {pitches_5} pitches in 5 days')
    if (
        fatigue is not None
        and fatigue >= thresholds.unavailable_fatigue_score
        and pitches_yesterday >= thresholds.avoid_pitches_yesterday
    ):
        signals.append(f'fatigue score {fatigue} with {pitches_yesterday} pitches yesterday')

    return signals


def _disable_unavailable_thresholds(thresholds):
    unreachable = 10**9
    return replace(
        thresholds,
        unavailable_fatigue_score=float(unreachable),
        unavailable_pitches_yesterday=unreachable,
        unavailable_pitches_last_3_days=unreachable,
        unavailable_multi_day_pitch_threshold=unreachable,
    )


def classify_for_candidate(
    score,
    game_logs,
    reference_date,
    latest_game_date,
    candidate,
    active_window_days=ACTIVE_WINDOW_DAYS,
):
    if not candidate.require_multiple_severe_signals:
        return classify_availability(
            score=score,
            game_logs=game_logs,
            reference_date=reference_date,
            latest_game_date=latest_game_date,
            active_window_days=active_window_days,
            thresholds=candidate.thresholds,
        )

    baseline = classify_availability(
        score=score,
        game_logs=game_logs,
        reference_date=reference_date,
        latest_game_date=latest_game_date,
        active_window_days=active_window_days,
        thresholds=candidate.thresholds,
    )
    if baseline['data_state'] != 'fresh' or baseline['availability_status'] != STATUS_UNAVAILABLE:
        return baseline

    signals = unavailable_severe_signals(baseline['inputs'], candidate.thresholds)
    if len(signals) >= 2:
        return baseline

    return classify_availability(
        score=score,
        game_logs=game_logs,
        reference_date=reference_date,
        latest_game_date=latest_game_date,
        active_window_days=active_window_days,
        thresholds=_disable_unavailable_thresholds(candidate.thresholds),
    )


def classify_rows_for_candidate(rows, candidate, reference_date=None, mode=LATEST_WORKLOAD_SNAPSHOT_MODE):
    current_reference_date = reference_date or date.today()
    records = []
    for score, pitcher in rows:
        latest_game_date = latest_game_date_for(pitcher.id)
        evaluation_date = evaluation_date_for_mode(
            mode,
            latest_game_date=latest_game_date,
            current_reference_date=current_reference_date,
        )
        logs = logs_for_availability_window(pitcher.id, evaluation_date)
        availability = classify_for_candidate(
            score=score,
            game_logs=logs,
            reference_date=evaluation_date,
            latest_game_date=latest_game_date,
            candidate=candidate,
        )
        records.append({
            'pitcher_id': pitcher.id,
            'pitcher_name': pitcher.full_name,
            'team': pitcher.team_abbreviation,
            'score': score,
            'pitcher': pitcher,
            'availability': availability,
            'mode': mode,
            'evaluation_date': evaluation_date,
            'latest_game_date': latest_game_date,
            'candidate': candidate.key,
        })
    return records


def reason_category_counts(records):
    counter = Counter()
    for record in [normalize_record(item) for item in records]:
        for reason in record['reasons']:
            counter[categorize_reason(reason)] += 1
    return ordered_counts(counter, CATEGORY_ORDER)


def _status_delta(candidate_counts, baseline_counts):
    return {
        status: candidate_counts.get(status, 0) - baseline_counts.get(status, 0)
        for status in STATUS_ORDER
    }


def _transition_key(baseline_status, candidate_status):
    return f'{baseline_status} -> {candidate_status}'


def compare_records(baseline_records, candidate_records, candidate):
    baseline = [normalize_record(record) for record in baseline_records]
    proposed = [normalize_record(record) for record in candidate_records]
    baseline_by_id = {record['pitcher_id']: record for record in baseline}
    proposed_by_id = {record['pitcher_id']: record for record in proposed}

    transitions = Counter()
    unavailable_moves = Counter()
    changed_examples = []

    for pitcher_id, baseline_record in baseline_by_id.items():
        candidate_record = proposed_by_id.get(pitcher_id)
        if candidate_record is None:
            continue
        baseline_status = baseline_record['availability_status']
        candidate_status = candidate_record['availability_status']
        transitions[_transition_key(baseline_status, candidate_status)] += 1
        if baseline_status == STATUS_UNAVAILABLE and candidate_status != STATUS_UNAVAILABLE:
            unavailable_moves[candidate_status] += 1
        if baseline_status != candidate_status:
            changed_examples.append(_example_row(baseline_record, candidate_record, candidate))

    baseline_summary = summarize_records(baseline_records, near_threshold_limit=12, top_reason_limit=10)
    candidate_summary = summarize_records(candidate_records, near_threshold_limit=12, top_reason_limit=10)

    return {
        'candidate': candidate,
        'baseline_summary': baseline_summary,
        'candidate_summary': candidate_summary,
        'status_delta': _status_delta(
            candidate_summary['status_distribution'],
            baseline_summary['status_distribution'],
        ),
        'transitions': ordered_counts(transitions, []),
        'unavailable_moves': ordered_counts(unavailable_moves, [
            STATUS_AVOID,
            STATUS_LIMITED,
            STATUS_MONITOR,
        ]),
        'changed_examples': changed_examples[:12],
        'boundary_examples': select_boundary_examples(baseline_records, candidate, limit=8),
        'reason_category_distribution': reason_category_counts(candidate_records),
    }


def _example_row(baseline_record, candidate_record, candidate):
    inputs = baseline_record['inputs']
    return {
        'pitcher_name': baseline_record['pitcher_name'],
        'team': baseline_record['team'],
        'baseline_status': baseline_record['availability_status'],
        'candidate_status': candidate_record['availability_status'],
        'fatigue_score': inputs.get('fatigue_score'),
        'pitches_yesterday': inputs.get('pitches_yesterday'),
        'pitches_last_3_days': inputs.get('pitches_last_3_days'),
        'pitches_last_5_days': inputs.get('pitches_last_5_days'),
        'appearances_last_5_days': inputs.get('appearances_last_5_days'),
        'severe_signals': unavailable_severe_signals(inputs, THRESHOLDS),
        'reasons': baseline_record['reasons'],
    }


def select_boundary_examples(records, candidate, limit=8):
    normalized = [normalize_record(record) for record in records]
    examples = []
    if candidate.require_multiple_severe_signals:
        for record in normalized:
            if record['availability_status'] != STATUS_UNAVAILABLE:
                continue
            signals = unavailable_severe_signals(record['inputs'], candidate.thresholds)
            examples.append({
                'pitcher_name': record['pitcher_name'],
                'team': record['team'],
                'availability_status': record['availability_status'],
                'input_value': len(signals),
                'distance': abs(len(signals) - 2),
                'severe_signals': signals,
                'reasons': record['reasons'],
            })
        examples.sort(key=lambda item: (item['distance'], item['input_value'], item['pitcher_name']))
        return examples[:limit]

    input_name = candidate.focus_input
    threshold = candidate.focus_threshold
    if input_name is None or threshold is None:
        return []

    for record in normalized:
        value = record['inputs'].get(input_name)
        if value is None:
            continue
        examples.append({
            'pitcher_name': record['pitcher_name'],
            'team': record['team'],
            'availability_status': record['availability_status'],
            'input_value': value,
            'distance': abs(float(value) - float(threshold)),
            'severe_signals': unavailable_severe_signals(record['inputs'], candidate.thresholds),
            'reasons': record['reasons'],
        })
    examples.sort(key=lambda item: (item['distance'], item['pitcher_name']))
    return examples[:limit]


def build_experiment(rows, reference_date=None, candidates=None):
    reference_date = reference_date or date.today()
    baseline_candidate = UnavailableCandidate(
        key='baseline',
        label='Baseline',
        changed_rule='Current production thresholds',
        thresholds=THRESHOLDS,
    )
    candidates = list(candidates or unavailable_candidates())
    baseline_records = classify_rows_for_candidate(rows, baseline_candidate, reference_date=reference_date)
    comparisons = []
    for candidate in candidates:
        candidate_records = classify_rows_for_candidate(rows, candidate, reference_date=reference_date)
        comparisons.append(compare_records(baseline_records, candidate_records, candidate))

    return {
        'reference_date': reference_date,
        'baseline_records': baseline_records,
        'baseline_summary': summarize_records(baseline_records, near_threshold_limit=12, top_reason_limit=10),
        'baseline_reason_categories': reason_category_counts(baseline_records),
        'comparisons': comparisons,
        'recommendation': recommend(comparisons),
    }


def recommend(comparisons):
    single_variable_changes = [
        item for item in comparisons
        if not item['candidate'].require_multiple_severe_signals
    ]
    largest_single_variable_move = max(
        (sum(item['unavailable_moves'].values()) for item in single_variable_changes),
        default=0,
    )
    multi_signal = next(
        (item for item in comparisons if item['candidate'].require_multiple_severe_signals),
        None,
    )
    multi_signal_moves = sum(multi_signal['unavailable_moves'].values()) if multi_signal else 0

    rationale = [
        'Current-mode output is stale/missing dominated, so production tuning should not rely on current-mode distribution alone.',
        f'Largest one-variable candidate moved {largest_single_variable_move} pitchers out of Unavailable.',
    ]
    if multi_signal is not None:
        rationale.append(
            f'The multi-signal gate moved {multi_signal_moves} pitchers, but it changes rule semantics rather than one threshold.'
        )
    rationale.append('Review near-boundary pitcher examples before adopting any future production threshold change.')

    return {
        'decision': 'Needs more data',
        'rationale': rationale,
    }


def _format_value(value):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.1f}'.rstrip('0').rstrip('.')
    return str(value)


def _markdown_counts(title, counts, first_column='Value'):
    lines = [f'### {title}', '', f'| {first_column} | Count |', '|---|---:|']
    if not counts:
        lines.append('| none | 0 |')
    else:
        for key, count in counts.items():
            lines.append(f'| {key} | {count} |')
    lines.append('')
    return lines


def _markdown_status_delta(delta):
    lines = ['### Status Delta From Baseline', '', '| Status | Delta |', '|---|---:|']
    for status in STATUS_ORDER:
        value = delta.get(status, 0)
        sign = '+' if value > 0 else ''
        lines.append(f'| {status} | {sign}{value} |')
    lines.append('')
    return lines


def _markdown_rule_table():
    lines = ['## Current Unavailable Rules', '', '| Rule | Condition |', '|---|---|']
    for rule in UNAVAILABLE_RULES:
        lines.append(f"| {rule['rule']} | `{rule['condition']}` |")
    lines.append('')
    return lines


def _markdown_comparison_overview(comparisons):
    lines = [
        '## Candidate Overview',
        '',
        '| Candidate | Changed rule | Unavailable | Delta | Moved from Unavailable |',
        '|---|---|---:|---:|---:|',
    ]
    for comparison in comparisons:
        candidate = comparison['candidate']
        status_counts = comparison['candidate_summary']['status_distribution']
        unavailable = status_counts.get(STATUS_UNAVAILABLE, 0)
        delta = comparison['status_delta'].get(STATUS_UNAVAILABLE, 0)
        moved = sum(comparison['unavailable_moves'].values())
        sign = '+' if delta > 0 else ''
        lines.append(
            f'| {candidate.label} | {candidate.changed_rule} | {unavailable} | {sign}{delta} | {moved} |'
        )
    lines.append('')
    return lines


def _markdown_example_table(title, examples):
    lines = [
        f'### {title}',
        '',
        '| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---|---|',
    ]
    if not examples:
        lines.append('| none |  |  |  |  |  |  |  |  |  |  |')
    else:
        for item in examples:
            signals = '; '.join(item.get('severe_signals') or []) or 'none'
            reasons = '; '.join(item.get('reasons') or []) or 'none'
            lines.append(
                f"| {item['pitcher_name']} | {item.get('team') or ''} | "
                f"{item.get('baseline_status', item.get('availability_status', ''))} | "
                f"{item.get('candidate_status', '')} | "
                f"{_format_value(item.get('fatigue_score'))} | "
                f"{_format_value(item.get('pitches_yesterday'))} | "
                f"{_format_value(item.get('pitches_last_3_days'))} | "
                f"{_format_value(item.get('pitches_last_5_days'))} | "
                f"{_format_value(item.get('appearances_last_5_days'))} | "
                f"{signals} | {reasons} |"
            )
    lines.append('')
    return lines


def _markdown_boundary_table(examples):
    lines = [
        '### Boundary Examples',
        '',
        '| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |',
        '|---|---|---|---:|---:|---|---|',
    ]
    if not examples:
        lines.append('| none |  |  |  |  |  |  |')
    else:
        for item in examples:
            signals = '; '.join(item.get('severe_signals') or []) or 'none'
            reasons = '; '.join(item.get('reasons') or []) or 'none'
            lines.append(
                f"| {item['pitcher_name']} | {item.get('team') or ''} | "
                f"{item['availability_status']} | {_format_value(item.get('input_value'))} | "
                f"{_format_value(item.get('distance'))} | {signals} | {reasons} |"
            )
    lines.append('')
    return lines


def render_markdown_report(experiment, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    recommendation = experiment['recommendation']
    lines = [
        '# Availability Unavailable Threshold Experiment',
        '',
        f'Generated at: {generated_at.isoformat()}',
        f"Reference date: {experiment['reference_date']}",
        '',
        'This experiment compares current Availability Engine thresholds against',
        'Unavailable-only candidate changes. It does not modify production',
        'thresholds, fatigue scoring, API behavior, dashboard behavior, or frontend behavior.',
        '',
    ]
    lines.extend(_markdown_rule_table())
    lines.extend([
        '## Baseline Snapshot Distribution',
        '',
        'Latest-workload snapshot output is validation-only and not current bullpen availability.',
        '',
    ])
    lines.extend(_markdown_counts('Baseline Status Distribution', experiment['baseline_summary']['status_distribution']))
    lines.extend(_markdown_counts('Baseline Confidence Distribution', experiment['baseline_summary']['confidence_distribution']))
    lines.extend(_markdown_counts('Baseline Data State Distribution', experiment['baseline_summary']['data_state_distribution']))
    lines.extend(_markdown_counts('Baseline Reason Categories', experiment['baseline_reason_categories'], first_column='Category'))
    lines.extend(_markdown_comparison_overview(experiment['comparisons']))

    for comparison in experiment['comparisons']:
        candidate = comparison['candidate']
        lines.extend([
            f'## {candidate.label}',
            '',
            f'Changed rule: {candidate.changed_rule}',
            '',
        ])
        lines.extend(_markdown_counts('Candidate Status Distribution', comparison['candidate_summary']['status_distribution']))
        lines.extend(_markdown_status_delta(comparison['status_delta']))
        lines.extend(_markdown_counts('Transitions', comparison['transitions'], first_column='Transition'))
        lines.extend(_markdown_counts('Moved From Unavailable', comparison['unavailable_moves'], first_column='Candidate status'))
        lines.extend(_markdown_counts('Reason Categories', comparison['reason_category_distribution'], first_column='Category'))
        lines.extend(_markdown_example_table('Changed Examples', comparison['changed_examples']))
        lines.extend(_markdown_boundary_table(comparison['boundary_examples']))

    lines.extend([
        '## Recommendation',
        '',
        f"Recommendation: {recommendation['decision']}",
        '',
    ])
    for item in recommendation['rationale']:
        lines.append(f'- {item}')
    lines.extend([
        '',
        'Any candidate threshold still requires human review and approval before',
        'production adoption.',
        '',
    ])
    return '\n'.join(lines).rstrip() + '\n'


def render_json_report(experiment, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    payload = {
        'generated_at': generated_at.isoformat(),
        'reference_date': str(experiment['reference_date']),
        'unavailable_rules': UNAVAILABLE_RULES,
        'baseline_summary': experiment['baseline_summary'],
        'baseline_reason_categories': experiment['baseline_reason_categories'],
        'recommendation': experiment['recommendation'],
        'comparisons': [
            {
                'candidate': {
                    'key': item['candidate'].key,
                    'label': item['candidate'].label,
                    'changed_rule': item['candidate'].changed_rule,
                    'require_multiple_severe_signals': item['candidate'].require_multiple_severe_signals,
                },
                'candidate_summary': item['candidate_summary'],
                'status_delta': item['status_delta'],
                'transitions': item['transitions'],
                'unavailable_moves': item['unavailable_moves'],
                'changed_examples': item['changed_examples'],
                'boundary_examples': item['boundary_examples'],
                'reason_category_distribution': item['reason_category_distribution'],
            }
            for item in experiment['comparisons']
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
