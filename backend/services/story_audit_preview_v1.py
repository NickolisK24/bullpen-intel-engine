"""Story Intelligence audit preview V1.

Internal QA helper for inspecting deterministic Story Intelligence output
across teams. This module reads the Story Intelligence Service V1 contract and
adds audit flags only; it does not alter context layers, story selection,
writer output, scoring, public routes, or UI behavior.
"""

from __future__ import annotations

from copy import deepcopy
import re

from models.pitcher import Pitcher
from services.story_intelligence_service_v1 import (
    build_story_intelligence_service_v1,
)
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from utils.db import db


CAPABILITY = 'story_intelligence_audit_preview_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

STATE_STORY = 'story'
STATE_NEUTRAL = 'neutral'

SECTION_MAP = {
    'headline': 'headline',
    'observation': 'observation_paragraph',
    'baseline': 'baseline_paragraph',
    'cause': 'cause_paragraph',
    'constraint': 'constraint_paragraph',
}

INTERNAL_TERMS = (
    *ROBOTIC_TERMS,
    'construction frame',
    'construction_frame',
    'selected_observation',
    'writer output',
    'writer_output',
    'trust_metadata',
    'external_generation_used',
    'story_observation_engine',
    'story_construction_engine',
    'story_writer',
)

AWKWARD_EMPTY_VALUES = {
    'n/a',
    'na',
    'none',
    'null',
    'not available',
    'unavailable',
}

AWKWARD_PHRASE_PATTERNS = (
    ('sox_possessive', re.compile(r"\b(?:red|white)\s+sox's\b", re.IGNORECASE)),
)

LIMITATIONS = [
    'Internal QA preview only.',
    'Uses Story Intelligence Service V1 output.',
    'Does not change story selection logic.',
    'Does not change context-layer calculations.',
    'Does not change scoring, fatigue, availability, or trust calculations.',
    'Does not create public rankings, predictions, routes, or UI.',
]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _clean_text(value):
    return ' '.join(str(value or '').strip().split())


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _text_has_any(text, terms):
    lower = _clean_text(text).lower()
    return any(term in lower for term in terms)


def _default_team_ids(limit=None):
    query = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .order_by(Pitcher.team_id)
    )
    if limit is not None:
        query = query.limit(limit)
    return [row[0] for row in query.all() if row[0] is not None]


def _limited(values, limit=None):
    rows = list(_list(values))
    if limit is None:
        return rows
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return rows
    if limit < 1:
        return []
    return rows[:limit]


def _sections(service_payload):
    written = _dict(_dict(service_payload).get('written_story'))
    return {
        public_key: _clean_text(written.get(writer_key)) or None
        for public_key, writer_key in SECTION_MAP.items()
    }


def _visible_text(sections):
    return ' '.join(value for value in _dict(sections).values() if value)


def _missing_required_sections(sections, *, story_available):
    if not story_available:
        return []
    return [
        key
        for key, value in _dict(sections).items()
        if not _clean_text(value)
    ]


def _awkward_empty_sections(service_payload, sections, *, story_available):
    if not story_available:
        return []
    written = _dict(_dict(service_payload).get('written_story'))
    awkward = []
    for public_key, writer_key in SECTION_MAP.items():
        raw_value = written.get(writer_key)
        cleaned = _clean_text(raw_value)
        if isinstance(raw_value, str) and not cleaned:
            awkward.append(public_key)
            continue
        if cleaned.lower() in AWKWARD_EMPTY_VALUES:
            awkward.append(public_key)
    return awkward


def _awkward_phrasing(text):
    cleaned = _clean_text(text)
    return [
        code
        for code, pattern in AWKWARD_PHRASE_PATTERNS
        if pattern.search(cleaned)
    ]


def _validation_flags(service_payload, sections, *, story_available):
    text = _visible_text(sections)
    writer_validation = _dict(_dict(service_payload).get('writer_output')).get('validation')
    writer_validation = _dict(writer_validation)
    missing = _missing_required_sections(sections, story_available=story_available)
    awkward = _awkward_empty_sections(
        service_payload,
        sections,
        story_available=story_available,
    )
    awkward_phrasing = _awkward_phrasing(text) if story_available else []
    has_banned = bool(writer_validation.get('contains_banned_language')) or _text_has_any(
        text,
        BANNED_TERMS,
    )
    has_internal = bool(writer_validation.get('contains_robotic_language')) or _text_has_any(
        text,
        INTERNAL_TERMS,
    )
    return {
        'has_internal_terms': has_internal,
        'has_banned_language': has_banned,
        'missing_required_sections': missing,
        'awkward_empty_sections': awkward,
        'awkward_phrasing': awkward_phrasing,
        'needs_review': bool(
            has_internal or has_banned or missing or awkward or awkward_phrasing
        ),
    }


def _preview_team(service_payload):
    payload = _dict(service_payload)
    story_available = bool(payload.get('story_available'))
    sections = _sections(payload) if story_available else {
        key: None for key in SECTION_MAP
    }
    selected = _dict(payload.get('selected_observation'))
    flags = _validation_flags(payload, sections, story_available=story_available)
    return {
        'team_id': payload.get('team_id'),
        'team_name': payload.get('team_name'),
        'team_abbreviation': payload.get('team_abbreviation'),
        'state': STATE_STORY if story_available else STATE_NEUTRAL,
        'service_state': payload.get('state'),
        'story_available': story_available,
        'story_type': selected.get('type') if story_available else None,
        'headline': sections.get('headline'),
        'sections': sections,
        'freshness': deepcopy(_dict(payload.get('freshness'))),
        'trust_metadata': deepcopy(_dict(payload.get('trust_metadata'))),
        'neutral_reason': payload.get('neutral_reason') if not story_available else None,
        'validation_flags': flags,
        'limitations': list(_list(payload.get('limitations'))),
    }


def _state_counts(teams):
    return {
        STATE_STORY: sum(1 for team in teams if team.get('state') == STATE_STORY),
        STATE_NEUTRAL: sum(1 for team in teams if team.get('state') == STATE_NEUTRAL),
        'needs_review': sum(
            1
            for team in teams
            if _dict(team.get('validation_flags')).get('needs_review')
        ),
    }


def _story_type_counts(teams):
    counts = {}
    for team in teams:
        story_type = team.get('story_type')
        if not story_type:
            continue
        counts[story_type] = counts.get(story_type, 0) + 1
    return counts


def build_story_audit_preview(*, team_ids=None, team_contexts=None, as_of_date=None, limit=None):
    """
    Build an internal Story Intelligence QA preview.

    If team_contexts are supplied, they are passed through the service directly.
    If team_ids are supplied, those ids are evaluated in deterministic team-id
    order. If neither is supplied, all known DB team ids are evaluated, with an
    optional limit for lightweight review runs.
    """
    if team_contexts is not None:
        selected_contexts = _limited(team_contexts, limit=limit)
        service_payload = build_story_intelligence_service_v1(
            team_contexts=selected_contexts,
            as_of_date=as_of_date,
        )
    else:
        selected_ids = _limited(
            team_ids if team_ids is not None else _default_team_ids(limit=limit),
            limit=limit if team_ids is not None else None,
        )
        service_payload = build_story_intelligence_service_v1(
            team_ids=selected_ids,
            as_of_date=as_of_date,
        )

    teams = [
        _preview_team(team)
        for team in _list(_dict(service_payload).get('teams'))
    ]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'as_of_date': _iso(as_of_date) or _dict(service_payload).get('as_of_date'),
        'team_count': len(teams),
        'state_counts': _state_counts(teams),
        'story_type_counts': _story_type_counts(teams),
        'teams': teams,
        'limitations': [*LIMITATIONS, *_list(_dict(service_payload).get('limitations'))],
    }


__all__ = [
    'CAPABILITY',
    'INTERNAL_TERMS',
    'SECTION_MAP',
    'STATE_NEUTRAL',
    'STATE_STORY',
    'VERSION',
    'build_story_audit_preview',
]
