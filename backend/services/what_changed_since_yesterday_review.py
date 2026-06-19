"""Internal review for What Changed Since Yesterday V1.

This module builds deterministic all-team evidence for current-vs-prior
bullpen intelligence review. It is internal only: no public UI contract,
recommendations, predictions, rankings, or tactical guidance.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from services.bullpen_identity import IDENTITY_LABELS
from services.what_changed_since_yesterday_copy import (
    COPY_FLAG_REPEATED_HEADLINE,
    COPY_FLAG_REPEATED_SUMMARY,
    build_what_changed_public_copy,
)
from services.what_changed_since_yesterday import (
    CHANGE_IDENTITY,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
    MEANINGFUL_CAPACITY_DELTA,
    MEANINGFUL_TRUST_DELTA,
    STATE_NO_MEANINGFUL_CHANGES,
    STATUS_AVAILABLE,
    build_what_changed_since_yesterday_payload,
)


CAPABILITY = 'what_changed_since_yesterday_review_v1'
VERSION = '2026-06-19.v1'
DEFAULT_EXPECTED_TEAM_COUNT = 30

TOO_MANY_CHANGES_THRESHOLD = 4
LOW_CONFIDENCE_VALUES = {'none', 'unknown', 'low'}

RECOMMENDATION_PATTERNS = (
    'recommend',
    'recommendation',
    'should use',
    'should pitch',
    'must use',
    'manager should',
)
PREDICTION_PATTERNS = (
    'predict',
    'prediction',
    'projected',
    'expected to',
    'likely to',
)
RANKING_PATTERNS = (
    'ranking',
    'ranked',
    'best reliever',
    'best bullpen',
    'worst bullpen',
    'top-ranked',
)
RAW_SCORE_PATTERNS = (
    'raw_score',
    'raw score',
    'score:',
    'score =',
)


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _int(value: Any, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _iso_datetime(value: datetime | None = None) -> str:
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _freshness(payload: dict[str, Any] | None) -> dict[str, Any]:
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    return freshness if isinstance(freshness, dict) else {}


def _payload_date(payload: dict[str, Any] | None) -> str | None:
    freshness = _freshness(payload)
    return (
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
        or freshness.get('availability_reference_date')
        or freshness.get('reference_date')
    )


def payload_snapshot_metadata(
    payload: dict[str, Any] | None,
    *,
    source: str,
    snapshot_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build compact current/prior source metadata for the review artifact."""

    snapshot_metadata = snapshot_metadata or {}
    freshness = _freshness(payload)
    return {
        'source': snapshot_metadata.get('source') or source,
        'snapshot_id': snapshot_metadata.get('snapshot_id'),
        'data_through': snapshot_metadata.get('data_through') or _payload_date(payload),
        'availability_reference_date': (
            snapshot_metadata.get('availability_reference_date')
            or freshness.get('availability_reference_date')
        ),
        'snapshot_generated_at': snapshot_metadata.get('snapshot_generated_at'),
    }


def _snapshot_metadata(snapshot: Any | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        'source': getattr(snapshot, 'source', None) or 'published_dashboard_snapshot',
        'snapshot_id': getattr(snapshot, 'id', None),
        'data_through': _iso_date(getattr(snapshot, 'data_through', None)),
        'availability_reference_date': _iso_date(
            getattr(snapshot, 'availability_reference_date', None)
        ),
        'snapshot_generated_at': (
            snapshot.snapshot_generated_at.isoformat()
            if getattr(snapshot, 'snapshot_generated_at', None)
            else None
        ),
    }


def snapshot_record_metadata(snapshot: Any | None) -> dict[str, Any] | None:
    """Expose snapshot metadata conversion for internal exporter scripts."""

    return _snapshot_metadata(snapshot)


def _team_sort_key(item: dict[str, Any]):
    return (
        str(item.get('team_abbreviation') or '').lower(),
        str(item.get('team_name') or '').lower(),
        _int(item.get('team_id')),
    )


def _text_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for child in value.values():
            values.extend(_text_values(child))
        return values
    if isinstance(value, list):
        values = []
        for child in value:
            values.extend(_text_values(child))
        return values
    if isinstance(value, str):
        return [value]
    return []


def _contains_any(texts: list[str], patterns: tuple[str, ...]) -> bool:
    combined = '\n'.join(texts).lower()
    return any(pattern in combined for pattern in patterns)


def _identity_label_leaked(texts: list[str]) -> bool:
    combined = '\n'.join(texts).lower()
    labels = {str(label).lower() for label in IDENTITY_LABELS.values()}
    labels.update(str(key).lower() for key in IDENTITY_LABELS)
    return any(label and label in combined for label in labels)


def _supporting_facts(change: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(change, dict):
        return []
    facts = change.get('supporting_facts')
    return list(facts) if isinstance(facts, list) else []


def _change_delta(change: dict[str, Any]) -> int | None:
    facts = _supporting_facts(change)
    if not facts:
        return None
    previous = facts[0].get('previous_value')
    current = facts[0].get('current_value')
    if not isinstance(previous, int) or not isinstance(current, int):
        return None
    return abs(current - previous)


def _is_tiny_count_change(change: dict[str, Any] | None) -> bool:
    if not isinstance(change, dict):
        return False
    delta = _change_delta(change)
    if delta is None:
        return False
    change_type = change.get('change_type')
    if (
        change_type in {CHANGE_RESTED_OPTIONS, CHANGE_USABLE_DEPTH}
        and delta < MEANINGFUL_CAPACITY_DELTA
    ):
        return True
    return change_type == CHANGE_TRUST_STRUCTURE and delta < MEANINGFUL_TRUST_DELTA


def _select_top_change(changes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for change in changes:
        if not _is_tiny_count_change(change):
            return change
    return changes[0] if changes else None


def _safe_review_summary(team_change: dict[str, Any], top_change: dict[str, Any] | None) -> str:
    if not top_change:
        if team_change.get('status') != STATUS_AVAILABLE:
            return 'Comparison is unavailable because prior context is missing.'
        return 'No meaningful bullpen change was detected from the available prior snapshot.'
    if top_change.get('change_type') == CHANGE_IDENTITY:
        return 'Bullpen identity changed between snapshots.'
    return str(top_change.get('change_summary') or '').strip()


def _team_review_flags(
    team_change: dict[str, Any],
    *,
    top_change: dict[str, Any] | None,
    review_summary: str,
) -> list[str]:
    flags = []
    changes = list(team_change.get('changes') or [])
    comparison_possible = team_change.get('status') == STATUS_AVAILABLE
    confidence = _norm((top_change or {}).get('confidence'))

    if not comparison_possible:
        flags.append('no_prior_snapshot')
    elif not changes:
        flags.append('no_meaningful_change')
    if len(changes) > TOO_MANY_CHANGES_THRESHOLD:
        flags.append('too_many_changes')
    if top_change and confidence in LOW_CONFIDENCE_VALUES:
        flags.append('low_confidence_top_change')
    if _is_tiny_count_change(top_change):
        flags.append('tiny_change_promoted')

    structural_count = sum(
        1
        for change in changes
        if change.get('significance') == 'structural'
    )
    if (
        len(changes) >= 3
        and structural_count == 0
    ) or any(_norm(change.get('confidence')) in LOW_CONFIDENCE_VALUES for change in changes):
        flags.append('possible_noise')

    change_texts = _text_values(changes)
    review_texts = [review_summary]
    all_texts = change_texts + review_texts
    if _contains_any(all_texts, RAW_SCORE_PATTERNS):
        flags.append('raw_score_leak')
    if _contains_any(all_texts, RECOMMENDATION_PATTERNS):
        flags.append('recommendation_language')
    if _contains_any(all_texts, PREDICTION_PATTERNS):
        flags.append('prediction_language')
    if _contains_any(all_texts, RANKING_PATTERNS):
        flags.append('ranking_language')
    if _identity_label_leaked(review_texts):
        flags.append('identity_label_public_leak')

    return flags


def _team_review_item(
    team_change: dict[str, Any],
    *,
    current_snapshot: dict[str, Any],
    prior_snapshot: dict[str, Any],
) -> dict[str, Any]:
    changes = list(team_change.get('changes') or [])
    top_change = _select_top_change(changes)
    review_summary = _safe_review_summary(team_change, top_change)
    comparison_possible = team_change.get('status') == STATUS_AVAILABLE
    public_copy = build_what_changed_public_copy(
        team_change,
        top_change=top_change,
        changes=changes,
    )

    return {
        'team_id': team_change.get('team_id'),
        'team_abbreviation': team_change.get('team_abbreviation'),
        'team_name': team_change.get('team_name'),
        'current_snapshot': current_snapshot,
        'prior_snapshot': prior_snapshot,
        'comparison_possible': comparison_possible,
        'selected_top_change': top_change,
        'top_change_selection_basis': (
            'first_non_tiny_meaningful_change_in_engine_order_not_ranked'
            if top_change
            else None
        ),
        'all_meaningful_changes': changes,
        'unchanged_or_insufficient_context_state': {
            'status': team_change.get('status'),
            'state': team_change.get('state'),
            'limitations': list(team_change.get('limitations') or []),
        },
        'confidence': (top_change or {}).get('confidence') or (
            'medium' if comparison_possible else 'none'
        ),
        'review_summary': review_summary,
        'supporting_facts': _supporting_facts(top_change),
        'review_flags': _team_review_flags(
            team_change,
            top_change=top_change,
            review_summary=review_summary,
        ),
        **public_copy,
    }


def _repeated_public_copy_counts(teams: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(
        team.get(field)
        for team in teams
        if team.get('public_copy_generated') and team.get(field)
    )
    return {
        text: count
        for text, count in sorted(counts.items())
        if count > 1
    }


def _apply_repeated_public_copy_flags(teams: list[dict[str, Any]]) -> None:
    repeated_headlines = _repeated_public_copy_counts(teams, 'public_headline')
    repeated_summaries = _repeated_public_copy_counts(teams, 'public_summary')
    for team in teams:
        if not team.get('public_copy_generated'):
            continue
        flags = team.setdefault('copy_review_flags', [])
        if (
            team.get('public_headline') in repeated_headlines
            and COPY_FLAG_REPEATED_HEADLINE not in flags
        ):
            flags.append(COPY_FLAG_REPEATED_HEADLINE)
        if (
            team.get('public_summary') in repeated_summaries
            and COPY_FLAG_REPEATED_SUMMARY not in flags
        ):
            flags.append(COPY_FLAG_REPEATED_SUMMARY)


def _distribution_summary(teams: list[dict[str, Any]]) -> dict[str, Any]:
    change_types = Counter()
    change_directions = Counter()
    flags = Counter()
    copy_flags = Counter()

    for team in teams:
        for change in team.get('all_meaningful_changes') or []:
            change_types[change.get('change_type') or 'unknown'] += 1
            change_directions[change.get('change_direction') or 'unknown'] += 1
        for flag in team.get('review_flags') or []:
            flags[flag] += 1
        for flag in team.get('copy_review_flags') or []:
            copy_flags[flag] += 1

    teams_with_comparison = [
        team for team in teams if team.get('comparison_possible')
    ]
    teams_with_changes = [
        team for team in teams if team.get('all_meaningful_changes')
    ]
    teams_with_copy = [
        team for team in teams if team.get('public_copy_generated')
    ]

    return {
        'teams_reviewed': len(teams),
        'teams_with_comparison_available': len(teams_with_comparison),
        'teams_without_prior_snapshot': sum(
            1
            for team in teams
            if 'no_prior_snapshot' in team.get('review_flags', [])
        ),
        'teams_with_meaningful_changes': len(teams_with_changes),
        'teams_with_no_meaningful_changes': sum(
            1
            for team in teams
            if team.get('comparison_possible')
            and team.get('unchanged_or_insufficient_context_state', {}).get('state')
            == STATE_NO_MEANINGFUL_CHANGES
        ),
        'count_by_change_type': {
            key: change_types[key]
            for key in sorted(change_types)
        },
        'count_by_change_direction': {
            key: change_directions[key]
            for key in sorted(change_directions)
        },
        'review_flag_counts': {
            flag: flags[flag]
            for flag in sorted(flags)
        },
        'public_copy_generated_count': len(teams_with_copy),
        'no_public_copy_count': len(teams) - len(teams_with_copy),
        'repeated_headline_counts': _repeated_public_copy_counts(
            teams,
            'public_headline',
        ),
        'repeated_summary_counts': _repeated_public_copy_counts(
            teams,
            'public_summary',
        ),
        'copy_review_flag_counts': {
            flag: copy_flags[flag]
            for flag in sorted(copy_flags)
        },
    }


def build_what_changed_since_yesterday_review(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
    *,
    generated_at: datetime | None = None,
    expected_team_count: int = DEFAULT_EXPECTED_TEAM_COUNT,
    current_snapshot_metadata: dict[str, Any] | None = None,
    prior_snapshot_metadata: dict[str, Any] | None = None,
    current_payload_source: str = 'live_dashboard_build',
    prior_payload_source: str = 'ready_dashboard_snapshot_before_current_data_through',
) -> dict[str, Any]:
    """Build a deterministic all-team What Changed V1 review artifact."""

    change_payload = build_what_changed_since_yesterday_payload(
        current_payload,
        prior_payload,
    )
    current_snapshot = payload_snapshot_metadata(
        current_payload,
        source=current_payload_source,
        snapshot_metadata=current_snapshot_metadata,
    )
    prior_snapshot = payload_snapshot_metadata(
        prior_payload,
        source=(
            prior_payload_source
            if prior_payload is not None
            else 'missing_prior_dashboard_snapshot'
        ),
        snapshot_metadata=prior_snapshot_metadata,
    )
    teams = sorted(
        (
            _team_review_item(
                team,
                current_snapshot=current_snapshot,
                prior_snapshot=prior_snapshot,
            )
            for team in change_payload.get('teams') or []
        ),
        key=_team_sort_key,
    )
    _apply_repeated_public_copy_flags(teams)
    summary = _distribution_summary(teams)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_at': _iso_datetime(generated_at),
        'source': 'backend',
        'current_payload_source': current_payload_source,
        'prior_payload_source': prior_snapshot.get('source'),
        'prior_snapshot_source_used': prior_snapshot.get('source'),
        'expected_team_count': expected_team_count,
        'team_count': len(teams),
        'complete_team_count': len(teams) == expected_team_count,
        'ordering_basis': 'team_abbreviation_then_team_name',
        'top_change_selection_basis': (
            'first_non_tiny_meaningful_change_in_engine_order_not_ranked'
        ),
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'comparison': {
            'current_snapshot': current_snapshot,
            'prior_snapshot': prior_snapshot,
            'current_data_through': current_snapshot.get('data_through'),
            'prior_data_through': prior_snapshot.get('data_through'),
            'comparison_available': summary['teams_with_comparison_available'] > 0,
        },
        'change_payload_state': {
            'status': change_payload.get('status'),
            'state': change_payload.get('state'),
            'limitations': list(change_payload.get('limitations') or []),
        },
        'distribution_summary': summary,
        'teams': teams,
    }


def write_json_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return path


def current_data_through_date(payload: dict[str, Any] | None) -> date | None:
    """Return the current payload's comparable data-through date."""

    return _parse_date(_payload_date(payload))


__all__ = [
    'CAPABILITY',
    'DEFAULT_EXPECTED_TEAM_COUNT',
    'VERSION',
    'build_what_changed_since_yesterday_review',
    'current_data_through_date',
    'payload_snapshot_metadata',
    'snapshot_record_metadata',
    'write_json_report',
]
