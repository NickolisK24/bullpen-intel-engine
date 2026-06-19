"""Public payload for What Changed Since Yesterday V1."""

from __future__ import annotations

from typing import Any

from services.what_changed_since_yesterday import (
    STATUS_AVAILABLE,
    build_what_changed_since_yesterday_payload,
)
from services.what_changed_since_yesterday_copy import (
    COPY_FLAG_REPEATED_HEADLINE,
    COPY_FLAG_REPEATED_SUMMARY,
    build_what_changed_public_copy,
)


CAPABILITY = 'what_changed_since_yesterday_public_v1'
DEFAULT_PUBLIC_ITEM_LIMIT = 6


def _public_top_change(changes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for change in changes:
        copy = build_what_changed_public_copy(
            {},
            top_change=change,
            changes=changes,
        )
        if copy.get('public_copy_generated') and not copy.get('copy_review_flags'):
            return change
    return None


def _team_key(team_change: dict[str, Any]) -> str:
    return str(
        team_change.get('team_abbreviation')
        or team_change.get('team_id')
        or team_change.get('team_name')
        or 'team'
    )


def _public_item(team_change: dict[str, Any]) -> dict[str, Any] | None:
    if team_change.get('status') != STATUS_AVAILABLE:
        return None
    changes = list(team_change.get('changes') or [])
    top_change = _public_top_change(changes)
    if not top_change:
        return None

    copy = build_what_changed_public_copy(
        team_change,
        top_change=top_change,
        changes=changes,
    )
    if not copy.get('public_copy_generated') or copy.get('copy_review_flags'):
        return None

    return {
        'key': f'{_team_key(team_change)}-what-changed',
        'team_id': team_change.get('team_id'),
        'team_name': team_change.get('team_name'),
        'team_abbreviation': team_change.get('team_abbreviation'),
        'public_headline': copy.get('public_headline'),
        'public_summary': copy.get('public_summary'),
        'public_context': copy.get('public_context'),
        '_copy_review_flags': list(copy.get('copy_review_flags') or []),
    }


def _repeated_values(items: list[dict[str, Any]], field: str) -> set[str]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(field)
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return {
        value
        for value, count in counts.items()
        if count > 1
    }


def _without_private_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith('_')
    }


def build_what_changed_public_payload(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
    *,
    limit: int = DEFAULT_PUBLIC_ITEM_LIMIT,
) -> dict[str, Any]:
    """Build a frontend-safe What Changed Since Yesterday V1 payload."""

    changes = build_what_changed_since_yesterday_payload(
        current_payload,
        prior_payload,
    )
    candidate_items = []
    for team_change in changes.get('teams') or []:
        item = _public_item(team_change)
        if item is None:
            continue
        candidate_items.append(item)

    repeated_headlines = _repeated_values(candidate_items, 'public_headline')
    repeated_summaries = _repeated_values(candidate_items, 'public_summary')
    items = []
    for item in candidate_items:
        flags = list(item.get('_copy_review_flags') or [])
        if item.get('public_headline') in repeated_headlines:
            flags.append(COPY_FLAG_REPEATED_HEADLINE)
        if item.get('public_summary') in repeated_summaries:
            flags.append(COPY_FLAG_REPEATED_SUMMARY)
        if flags:
            continue
        items.append(_without_private_fields(item))
        if len(items) >= limit:
            break

    return {
        'capability': CAPABILITY,
        'source': 'backend',
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'ordering_basis': 'team_abbreviation_then_team_name',
        'item_limit': limit,
        'comparison': {
            'current_data_through': changes.get('reference_date'),
            'previous_data_through': changes.get('prior_date'),
            'comparison_available': changes.get('status') == STATUS_AVAILABLE,
        },
        'items': items,
        'item_count': len(items),
        'limitations': list(changes.get('limitations') or []),
    }


__all__ = [
    'CAPABILITY',
    'DEFAULT_PUBLIC_ITEM_LIMIT',
    'build_what_changed_public_payload',
]
