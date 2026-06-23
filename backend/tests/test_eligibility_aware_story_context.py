"""Tests for eligibility-aware story context (Phase C3E).

Swing/Bulk participation can qualify a bullpen story ("part of that coverage is
swing/bulk") as appended prose on the forward-constraint beat. It must appear
only when relevant, never change payload shape, and never leak eligibility_type
or any raw eligibility state to the public feed.
"""

import json

from services.bullpen_eligibility_vocabulary import (
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_STARTER_PROTECTED,
    ELIGIBILITY_SWING_BULK_RELIEF,
)
from services.story_eligibility_context import (
    attach_swing_bulk_story_context,
    swing_bulk_clause_for,
    team_swing_bulk_context,
)
from services.story_feed import canonical_story_from_service_payload
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)

RELEVANT_TYPES = (
    TYPE_ROTATION_PRESSURE,
    TYPE_DEPTH_PRESSURE,
    TYPE_TRUST_LANE_PRESSURE,
    TYPE_BRIDGE_INSTABILITY,
    TYPE_OPTIONALITY_STRENGTH,
)

_PRESENT = {'present': True, 'swing_bulk_count': 2, 'eligible_count': 7}
_ABSENT = {'present': False, 'swing_bulk_count': 0, 'eligible_count': 6}


def _payload(observation_type=TYPE_ROTATION_PRESSURE, story_type='coverage_pressure',
             constraint='The bullpen is thin behind the top arms.'):
    return {
        'team_id': 113,
        'team_name': 'Reds',
        'team_abbreviation': 'CIN',
        'as_of_date': '2026-06-20',
        'story_available': True,
        'story_type': story_type,
        'story_type_label': 'Coverage',
        'selected_observation': {'type': observation_type},
        'construction_frame': {'observation_type': observation_type},
        'written_story': {
            'headline': 'The bullpen is carrying more of the game',
            'observation_paragraph': 'The relief group is absorbing more innings than usual.',
            'baseline_paragraph': 'That is heavier than the recent baseline.',
            'cause_paragraph': 'Recent starts have been short.',
            'constraint_paragraph': constraint,
        },
        'freshness': {},
        'trust_metadata': {},
        'limitations': [],
    }


# ── Signal ───────────────────────────────────────────────────────────────────

def test_team_swing_bulk_context_counts_present_arms():
    records = [
        {'eligibility': {'eligible': True, 'eligibility_type': ELIGIBILITY_NORMAL_RELIEF}},
        {'eligibility': {'eligible': True, 'eligibility_type': ELIGIBILITY_SWING_BULK_RELIEF}},
        {'eligibility': {'eligible': False, 'eligibility_type': ELIGIBILITY_STARTER_PROTECTED}},
    ]
    signal = team_swing_bulk_context(records)
    assert signal['present'] is True
    assert signal['swing_bulk_count'] == 1
    assert signal['eligible_count'] == 2


def test_team_swing_bulk_context_absent_without_swing_bulk():
    records = [{'eligibility': {'eligible': True, 'eligibility_type': ELIGIBILITY_NORMAL_RELIEF}}]
    assert team_swing_bulk_context(records)['present'] is False
    assert team_swing_bulk_context([])['present'] is False


# ── Appearance ───────────────────────────────────────────────────────────────

def test_context_appears_for_relevant_family_when_swing_bulk_present():
    out = attach_swing_bulk_story_context(_payload(), _PRESENT)
    constraint = out['written_story']['constraint_paragraph']
    assert constraint.startswith('The bullpen is thin behind the top arms.')
    assert 'swing and bulk options' in constraint


def test_clause_renders_for_every_relevant_family():
    for observation_type in RELEVANT_TYPES:
        clause = swing_bulk_clause_for(_payload(observation_type=observation_type))
        assert clause and ('swing' in clause.lower())


# ── Suppression ──────────────────────────────────────────────────────────────

def test_context_suppressed_when_signal_absent():
    payload = _payload()
    original = payload['written_story']['constraint_paragraph']
    out = attach_swing_bulk_story_context(payload, _ABSENT)
    assert out['written_story']['constraint_paragraph'] == original


def test_context_suppressed_for_irrelevant_family():
    payload = _payload(observation_type=TYPE_STABLE_CORE, story_type='route_change')
    original = payload['written_story']['constraint_paragraph']
    out = attach_swing_bulk_story_context(payload, _PRESENT)
    assert out['written_story']['constraint_paragraph'] == original


def test_context_suppressed_when_no_constraint_beat():
    payload = _payload(constraint='')
    out = attach_swing_bulk_story_context(payload, _PRESENT)
    assert out['written_story']['constraint_paragraph'] == ''


def test_context_suppressed_when_story_unavailable():
    payload = _payload()
    payload['story_available'] = False
    original = payload['written_story']['constraint_paragraph']
    out = attach_swing_bulk_story_context(payload, _PRESENT)
    assert out['written_story']['constraint_paragraph'] == original


# ── Governance ───────────────────────────────────────────────────────────────

def test_eligibility_context_lines_pass_public_governance():
    from services.story_voice_library_v1 import (
        ELIGIBILITY_CONTEXT_LINES,
        contains_banned_public_language,
        contains_denied_public_phrase,
    )
    from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS

    for forms in ELIGIBILITY_CONTEXT_LINES.values():
        for line in forms:
            assert not contains_banned_public_language(line)
            assert not contains_denied_public_phrase(line)
            low = line.lower()
            assert not any(term in low for term in BANNED_TERMS)
            assert not any(term in low for term in ROBOTIC_TERMS)


# ── Public feed: no leakage, no shape change ─────────────────────────────────

def test_context_reaches_narrative_without_leaking_eligibility():
    payload = attach_swing_bulk_story_context(_payload(), _PRESENT)
    item = canonical_story_from_service_payload(payload, date='2026-06-20')
    blob = json.dumps(item).lower()
    assert 'swing and bulk options' in item['narrative'].lower()
    assert 'eligibility_type' not in blob
    assert 'swing_bulk_relief' not in blob
    assert 'normal_relief' not in blob


def test_feed_item_shape_unchanged_by_context():
    base = canonical_story_from_service_payload(_payload(), date='2026-06-20')
    enriched = canonical_story_from_service_payload(
        attach_swing_bulk_story_context(_payload(), _PRESENT), date='2026-06-20',
    )
    assert set(base.keys()) == set(enriched.keys())
    assert [beat['key'] for beat in base['beats']] == [beat['key'] for beat in enriched['beats']]
