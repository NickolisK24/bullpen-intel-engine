"""Narrative renderer for normalized team story facts."""

from __future__ import annotations

import re
from typing import Any


CAPABILITY = 'team_story_narrative_renderer_v1'
VERSION = '2026-06-18'

FORBIDDEN_PUBLIC_LABELS = (
    'Signal',
    'Evidence',
    'Context',
    'Mechanism',
    'Implication',
    'Observation',
    'Why It Matters',
    "What I'm Watching",
    'What BaseballOS Is Watching',
)

INTERNAL_TAXONOMY_TERMS = (
    'stress_transfer',
    'pressure_distribution',
    'sustainability_question',
    'hidden_capacity_loss',
    'fatigue_load',
    'trust_lane_absence',
    'trust_lane_shallow',
    'workload_high',
    'workload_light',
    'availability_thin',
    'availability_deep',
    'deep_intact',
    'concentration_shape',
    'participation_narrow',
    'participation_broad',
    'era_elite',
    'era_ordinary',
    'trust_lane_depth',
    'HIGH or CRITICAL',
    'fatigue score',
    'confidence score',
)


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _sentence(value: Any) -> str | None:
    text = _public_language(value)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _public_language(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ''

    replacements = (
        ('HIGH or CRITICAL fatigue', 'a heavier workload flag'),
        ('HIGH or CRITICAL', 'heavier'),
        ('Trust Arms', 'trusted late-inning arms'),
        ('Trust Arm', 'trusted late-inning arm'),
        ('Clean Options', 'usable arms'),
        ('Clean Option', 'usable arm'),
        ('Available', 'available'),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)

    text = re.sub(r',?\s*\d+(?:st|nd|rd|th)\s+among current pens', '', text)
    text = text.replace('among current pens', 'among current bullpens')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _first_present(*values: Any) -> str | None:
    for value in values:
        sentence = _sentence(value)
        if sentence:
            return sentence
    return None


def _unique_sentences(values: list[Any], limit: int | None = None) -> list[str]:
    seen = set()
    sentences = []
    for value in values:
        sentence = _sentence(value)
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(sentence)
        if limit is not None and len(sentences) >= limit:
            break
    return sentences


def _paragraph(values: list[Any], limit: int | None = None) -> str | None:
    sentences = _unique_sentences(values, limit=limit)
    if not sentences:
        return None
    return ' '.join(sentences)


def _supporting_values(facts: dict[str, Any]) -> list[Any]:
    environment = facts.get('environment_context')
    if environment:
        return [environment, facts.get('workload_pattern')]
    return [
        facts.get('pressure_source'),
        facts.get('capacity_context'),
        facts.get('rotation_context'),
        facts.get('stability_context'),
        facts.get('workload_pattern'),
    ]


def render_story_narrative(facts: dict[str, Any]) -> str:
    """Render a natural two-to-three paragraph baseball story."""

    opening = _paragraph([
        facts.get('primary_observation'),
        facts.get('supporting_context'),
    ], limit=2)
    supporting = _paragraph(_supporting_values(facts), limit=2)
    closing = _paragraph([
        facts.get('watch_question'),
        facts.get('disclosure'),
    ], limit=2)

    paragraphs = [item for item in (opening, supporting, closing) if item]
    if not paragraphs:
        return ''
    return '\n\n'.join(paragraphs)


def narrative_contains_forbidden_language(narrative: str) -> bool:
    text = narrative or ''
    lower = text.lower()
    labels = {label.lower() for label in FORBIDDEN_PUBLIC_LABELS}
    terms = {term.lower() for term in INTERNAL_TAXONOMY_TERMS}
    return any(label in text for label in FORBIDDEN_PUBLIC_LABELS) or any(term in lower for term in labels | terms)


__all__ = [
    'CAPABILITY',
    'VERSION',
    'FORBIDDEN_PUBLIC_LABELS',
    'INTERNAL_TAXONOMY_TERMS',
    'narrative_contains_forbidden_language',
    'render_story_narrative',
]
