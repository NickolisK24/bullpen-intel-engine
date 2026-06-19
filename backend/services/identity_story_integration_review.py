"""Internal review for Identity-Aware Story Integration V1.

This module summarizes current backend story output for review. It is internal
evidence only: no public UI contract, recommendations, predictions, rankings,
or tactical guidance.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.bullpen_identity import (
    IDENTITY_LABELS,
    STRUCTURAL_SCOPE_CAVEAT,
    TACTICAL_BOUNDARY_CAVEAT,
)
from services.team_story_narrative import select_story_archetype


CAPABILITY = 'identity_story_integration_review_v1'
VERSION = '2026-06-19.v1'
DEFAULT_EXPECTED_TEAM_COUNT = 30

STORY_TOO_LONG_PARAGRAPH_MAX = 3
STORY_TOO_LONG_SENTENCE_MAX = 7
REPEATED_IDENTITY_SENTENCE_THRESHOLD = 3
TOO_MANY_NON_BOUNDARY_CAVEATS_MAX = 2
IDENTITY_CONFIDENCE_ALLOWED = {'medium', 'high'}

GOVERNANCE_LANGUAGE_PATTERNS = (
    'recommend',
    'recommendation',
    'prediction',
    'predict ',
    'betting',
    'wager',
    'ranking',
    'ranked',
    'manager should',
    'should use',
    'should pitch',
)


def _get(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _int(value: Any, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _iso(value: datetime | None = None) -> str:
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def _team_sort_key(item: dict[str, Any]):
    return (
        str(item.get('team_name') or item.get('team_abbreviation') or '').lower(),
        _int(item.get('team_id')),
    )


def _capacity_items(dashboard_payload: dict[str, Any]) -> list[dict[str, Any]]:
    capacity = dashboard_payload.get('capacity_intelligence') or {}
    items = list(capacity.get('teams') or [])
    if items:
        return items
    return list((capacity.get('by_team_id') or {}).values())


def _story_items(dashboard_payload: dict[str, Any]) -> list[dict[str, Any]]:
    stories = dashboard_payload.get('four_beat_stories') or {}
    return list(stories.get('items') or [])


def _story_by_team_id(dashboard_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(story.get('team_id')): story
        for story in _story_items(dashboard_payload)
        if story.get('team_id') is not None
    }


def _identity_for_team(capacity_item: dict[str, Any], story: dict[str, Any] | None) -> dict[str, Any]:
    identity = capacity_item.get('bullpen_identity')
    if isinstance(identity, dict) and identity:
        return identity
    identity = _get(story, 'computed', 'bullpen_identity', default={})
    return identity if isinstance(identity, dict) else {}


def _identity_integration(story: dict[str, Any] | None) -> dict[str, Any]:
    integration = _get(story, 'computed', 'story_identity_integration', default={})
    if isinstance(integration, dict) and integration:
        return integration
    integration = _get(story, 'story_facts', 'story_identity_integration', default={})
    return integration if isinstance(integration, dict) else {}


def _story_text(story: dict[str, Any] | None) -> str:
    if not isinstance(story, dict):
        return ''
    return str(story.get('narrative') or story.get('body') or '').strip()


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r'\n\s*\n', text or '') if part.strip()]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.findall(r'[^.!?]+[.!?]', text or '') if part.strip()]


def _non_boundary_caveats(identity: dict[str, Any]) -> list[str]:
    return [
        str(caveat)
        for caveat in identity.get('caveats') or []
        if caveat not in {STRUCTURAL_SCOPE_CAVEAT, TACTICAL_BOUNDARY_CAVEAT}
    ]


def _raw_identity_label_leaked(text: str) -> bool:
    lower = (text or '').lower()
    blocked = {label.lower() for label in IDENTITY_LABELS.values()}
    blocked.update(IDENTITY_LABELS)
    return any(item and item in lower for item in blocked)


def _governance_language_detected(text: str) -> bool:
    lower = (text or '').lower()
    return any(pattern in lower for pattern in GOVERNANCE_LANGUAGE_PATTERNS)


def _identity_sentence_bolted_on(text: str, identity_sentence: str | None) -> bool:
    if not identity_sentence:
        return False
    normalized = identity_sentence.strip()
    if not normalized:
        return False
    return any(paragraph.strip() == normalized for paragraph in _paragraphs(text))


def _story_archetype(story: dict[str, Any] | None) -> str | None:
    facts = (story or {}).get('story_facts') or {}
    if not isinstance(facts, dict) or not facts:
        return None
    return select_story_archetype(facts)


def _team_item(capacity_item: dict[str, Any], story: dict[str, Any] | None) -> dict[str, Any]:
    identity = _identity_for_team(capacity_item, story)
    integration = _identity_integration(story)
    text = _story_text(story)
    paragraphs = _paragraphs(text)
    sentences = _sentences(text)
    identity_sentence = integration.get('text')
    identity_applied = bool(integration.get('applied'))

    return {
        'team_id': capacity_item.get('team_id'),
        'team_name': capacity_item.get('team_name'),
        'team_abbreviation': capacity_item.get('team_abbreviation'),
        'story_present': bool(story),
        'selected_story_key': (story or {}).get('rule_key'),
        'selected_story_label': (story or {}).get('rule_label'),
        'selected_story_archetype': _story_archetype(story),
        'story_text': text,
        'paragraph_count': len(paragraphs),
        'sentence_count': len(sentences),
        'identity_text_applied': identity_applied,
        'identity_confidence': identity.get('confidence'),
        'identity_key': identity.get('identity_key'),
        'identity_label': identity.get('identity_label'),
        'identity_sentence': identity_sentence,
        'identity_integration_reason': integration.get('reason'),
        'caveats': identity.get('caveats') or [],
        'review_flags': _team_review_flags(
            text=text,
            story=story,
            identity=identity,
            identity_applied=identity_applied,
            identity_sentence=identity_sentence,
            paragraph_count=len(paragraphs),
            sentence_count=len(sentences),
        ),
    }


def _team_review_flags(
    *,
    text: str,
    story: dict[str, Any] | None,
    identity: dict[str, Any],
    identity_applied: bool,
    identity_sentence: str | None,
    paragraph_count: int,
    sentence_count: int,
) -> list[str]:
    flags = []
    confidence = _norm(identity.get('confidence'))

    if not story:
        flags.append('no_selected_story')
    if (
        paragraph_count > STORY_TOO_LONG_PARAGRAPH_MAX
        or sentence_count > STORY_TOO_LONG_SENTENCE_MAX
    ):
        flags.append('story_too_long')
    if identity_applied and identity_sentence and identity_sentence not in text:
        flags.append('identity_sentence_missing_from_story')
    if _identity_sentence_bolted_on(text, identity_sentence):
        flags.append('identity_sentence_feels_bolted_on')
    if _raw_identity_label_leaked(text):
        flags.append('raw_identity_label_leaked')
    if _governance_language_detected(text):
        flags.append('governance_language_detected')
    if len(_non_boundary_caveats(identity)) > TOO_MANY_NON_BOUNDARY_CAVEATS_MAX:
        flags.append('too_many_caveats')
    if identity_applied and confidence not in IDENTITY_CONFIDENCE_ALLOWED:
        flags.append('low_confidence_identity_text_applied')

    return flags


def _apply_repeated_sentence_flags(teams: list[dict[str, Any]], sentence_counts: Counter) -> None:
    for team in teams:
        sentence = team.get('identity_sentence')
        if (
            team.get('identity_text_applied')
            and sentence
            and sentence_counts[sentence] > REPEATED_IDENTITY_SENTENCE_THRESHOLD
        ):
            team['review_flags'].append('identity_sentence_repeated_too_often')


def _review_summary(teams: list[dict[str, Any]]) -> dict[str, Any]:
    applied = [team for team in teams if team.get('identity_text_applied')]
    skipped = [team for team in teams if not team.get('identity_text_applied')]
    sentence_counts = Counter(
        team.get('identity_sentence')
        for team in applied
        if team.get('identity_sentence')
    )
    flags = Counter(
        flag
        for team in teams
        for flag in team.get('review_flags') or []
    )
    by_key = Counter(team.get('identity_key') or 'unknown' for team in applied)
    by_label = Counter(team.get('identity_label') or 'Unknown / Insufficient Context' for team in applied)

    return {
        'identity_text_applied_count': len(applied),
        'identity_text_skipped_count': len(skipped),
        'applied_count_by_identity_key': {
            key: by_key[key]
            for key in sorted(by_key)
        },
        'applied_count_by_identity_label': {
            label: by_label[label]
            for label in sorted(by_label)
        },
        'repeated_identity_sentence_threshold': REPEATED_IDENTITY_SENTENCE_THRESHOLD,
        'identity_sentence_counts': {
            sentence: sentence_counts[sentence]
            for sentence in sorted(sentence_counts)
        },
        'review_flag_counts': {
            flag: flags[flag]
            for flag in sorted(flags)
        },
        'teams_for_human_review': [
            {
                'team_id': team.get('team_id'),
                'team_name': team.get('team_name'),
                'team_abbreviation': team.get('team_abbreviation'),
                'selected_story_key': team.get('selected_story_key'),
                'identity_label': team.get('identity_label'),
                'review_flags': team.get('review_flags') or [],
            }
            for team in teams
            if team.get('review_flags')
        ],
    }


def build_identity_story_integration_review(
    dashboard_payload: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    expected_team_count: int = DEFAULT_EXPECTED_TEAM_COUNT,
    payload_source: str = 'live_dashboard_build',
) -> dict[str, Any]:
    """Build a deterministic all-team story integration review artifact."""

    stories_by_team = _story_by_team_id(dashboard_payload or {})
    teams = sorted(
        (
            _team_item(item, stories_by_team.get(str(item.get('team_id'))))
            for item in _capacity_items(dashboard_payload or {})
        ),
        key=_team_sort_key,
    )
    sentence_counts = Counter(
        team.get('identity_sentence')
        for team in teams
        if team.get('identity_text_applied') and team.get('identity_sentence')
    )
    _apply_repeated_sentence_flags(teams, sentence_counts)
    summary = _review_summary(teams)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_at': _iso(generated_at),
        'source': 'backend',
        'payload_source': payload_source,
        'expected_team_count': expected_team_count,
        'team_count': len(teams),
        'story_count': sum(1 for team in teams if team.get('story_present')),
        'complete_team_count': len(teams) == expected_team_count,
        'ordering_basis': 'team_name_then_team_id',
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'review_thresholds': {
            'story_too_long_paragraph_max': STORY_TOO_LONG_PARAGRAPH_MAX,
            'story_too_long_sentence_max': STORY_TOO_LONG_SENTENCE_MAX,
            'repeated_identity_sentence_threshold': REPEATED_IDENTITY_SENTENCE_THRESHOLD,
            'too_many_non_boundary_caveats_max': TOO_MANY_NON_BOUNDARY_CAVEATS_MAX,
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


__all__ = [
    'CAPABILITY',
    'DEFAULT_EXPECTED_TEAM_COUNT',
    'VERSION',
    'build_identity_story_integration_review',
    'write_json_report',
]
