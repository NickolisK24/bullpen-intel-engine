"""Public payload for What Changed Since Yesterday V1."""

from __future__ import annotations

import re
from typing import Any

from services.bullpen_identity import IDENTITY_LABELS
from services.consequence_intelligence import (
    STATUS_AVAILABLE as CONSEQUENCE_STATUS_AVAILABLE,
    build_consequence_intelligence_payload,
)
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

CONSEQUENCE_CONFIDENCE_ALLOWED = {'medium', 'high'}
CONSEQUENCE_SIGNIFICANCE_ALLOWED = {'meaningful', 'structural'}
CONSEQUENCE_CONTEXT_MAX_WORDS = 26

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
    'forecast',
)
RANKING_PATTERNS = (
    'ranking',
    'ranked',
    'best reliever',
    'best bullpen',
    'worst bullpen',
    'top-ranked',
)
BETTING_PATTERNS = (
    'bet',
    'betting',
    'odds',
    'wager',
)
PROBABILITY_PATTERNS = (
    'probability',
    'probable',
    'percent chance',
    'chance to',
    'likelihood',
)
RELIEVER_SELECTION_PATTERNS = (
    'should use',
    'must use',
    'manager should',
    'which reliever',
    'specific reliever',
    'use the closer',
)
RAW_SCORE_PATTERNS = (
    'raw_score',
    'raw score',
    'score:',
    'score =',
)
CONSEQUENCE_FLAG_FIELDS = (
    'review_flags',
    'reviewFlags',
    'governance_flags',
    'governanceFlags',
)


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


def _team_lookup_key(team_change: dict[str, Any] | None) -> str | None:
    if not isinstance(team_change, dict):
        return None
    team_id = team_change.get('team_id') or team_change.get('teamId')
    if team_id is not None:
        return str(team_id)
    abbr = team_change.get('team_abbreviation') or team_change.get('teamAbbreviation')
    return str(abbr).lower() if abbr else None


def _teams_by_key(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    by_team = payload.get('by_team_id')
    if isinstance(by_team, dict):
        return {
            str(key): value
            for key, value in by_team.items()
            if isinstance(value, dict)
        }
    teams = payload.get('teams')
    if isinstance(teams, list):
        return {
            str(_team_lookup_key(team)): team
            for team in teams
            if isinstance(team, dict) and _team_lookup_key(team) is not None
        }
    return {}


def _facts(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    facts = item.get('supporting_facts')
    return [
        fact
        for fact in (facts if isinstance(facts, list) else [])
        if isinstance(fact, dict)
    ]


def _fact_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get('fact_key') == right.get('fact_key')
        and left.get('previous_value') == right.get('previous_value')
        and left.get('current_value') == right.get('current_value')
    )


def _consequence_matches_change(
    consequence: dict[str, Any],
    change: dict[str, Any],
) -> bool:
    consequence_facts = _facts(consequence)
    change_facts = _facts(change)
    if not consequence_facts or not change_facts:
        return False
    return any(
        _fact_matches(consequence_fact, change_fact)
        for consequence_fact in consequence_facts
        for change_fact in change_facts
    )


def _word_count(value: str | None) -> int:
    return len(str(value or '').split())


def _contains_pattern(text: str, pattern: str) -> bool:
    lower = text.lower()
    if pattern.isalpha():
        return re.search(rf'\b{re.escape(pattern)}\b', lower) is not None
    return pattern in lower


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(_contains_pattern(text, pattern) for pattern in patterns)


def _identity_label_leaked(text: str) -> bool:
    lower = text.lower()
    labels = {str(label).lower() for label in IDENTITY_LABELS.values()}
    labels.update(str(key).lower() for key in IDENTITY_LABELS)
    return any(label and label in lower for label in labels)


def _has_review_or_governance_flags(item: dict[str, Any]) -> bool:
    for field in CONSEQUENCE_FLAG_FIELDS:
        flags = item.get(field)
        if isinstance(flags, str) and flags.strip():
            return True
        if isinstance(flags, (list, tuple, set)) and len(flags) > 0:
            return True
    return False


def _safe_consequence_context(
    consequence_team: dict[str, Any] | None,
    top_change: dict[str, Any],
) -> str | None:
    if not isinstance(consequence_team, dict):
        return None
    if consequence_team.get('status') != CONSEQUENCE_STATUS_AVAILABLE:
        return None
    if _has_review_or_governance_flags(consequence_team):
        return None
    consequences = list(consequence_team.get('consequences') or [])
    if not consequences:
        return None

    primary = consequences[0]
    if not isinstance(primary, dict):
        return None
    if _has_review_or_governance_flags(primary):
        return None
    if not _consequence_matches_change(primary, top_change):
        return None
    if str(primary.get('confidence') or '').lower() not in CONSEQUENCE_CONFIDENCE_ALLOWED:
        return None
    if str(primary.get('significance') or '').lower() not in CONSEQUENCE_SIGNIFICANCE_ALLOWED:
        return None

    context = str(primary.get('consequence_context') or '').strip()
    if not context or _word_count(context) > CONSEQUENCE_CONTEXT_MAX_WORDS:
        return None

    if _contains_any(context, RECOMMENDATION_PATTERNS):
        return None
    if _contains_any(context, PREDICTION_PATTERNS):
        return None
    if _contains_any(context, RANKING_PATTERNS):
        return None
    if _contains_any(context, BETTING_PATTERNS):
        return None
    if _contains_any(context, PROBABILITY_PATTERNS):
        return None
    if _contains_any(context, RELIEVER_SELECTION_PATTERNS):
        return None
    if _contains_any(context, RAW_SCORE_PATTERNS):
        return None
    if _identity_label_leaked(context):
        return None

    return context


def _public_item(
    team_change: dict[str, Any],
    *,
    consequence_team: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
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
    consequence_context = _safe_consequence_context(consequence_team, top_change)

    return {
        'key': f'{_team_key(team_change)}-what-changed',
        'team_id': team_change.get('team_id'),
        'team_name': team_change.get('team_name'),
        'team_abbreviation': team_change.get('team_abbreviation'),
        'public_headline': copy.get('public_headline'),
        'public_summary': copy.get('public_summary'),
        'public_context': consequence_context or copy.get('public_context'),
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
    consequence_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a frontend-safe What Changed Since Yesterday V1 payload."""

    changes = build_what_changed_since_yesterday_payload(
        current_payload,
        prior_payload,
    )
    if consequence_payload is None:
        consequence_payload = build_consequence_intelligence_payload(
            current_payload,
            prior_payload,
            what_changed_payload=changes,
        )
    consequence_by_team = _teams_by_key(consequence_payload)
    candidate_items = []
    for team_change in changes.get('teams') or []:
        item = _public_item(
            team_change,
            consequence_team=consequence_by_team.get(str(_team_lookup_key(team_change))),
        )
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
