"""V2 Story Blueprint (Phase A) tests.

The blueprint reframes the existing four authored beats into the 5-section
teaching shape (what everyone saw / what BaseballOS noticed / evidence / why it
matters / why it matters tomorrow) without inventing facts, breaking the existing
story contract, or leaking banned / internal / prediction language.
"""

from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES,
    LESSON_LINES,
    SURFACE_FRAMING_LINES,
    WATCH_LINES,
)
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_audit_preview_v1 import INTERNAL_TERMS
from services.story_blueprint_v1 import (
    SECTION_EVIDENCE,
    SECTION_NOTICED,
    SECTION_ORDER,
    SECTION_SAW,
    SECTION_TOMORROW,
    SECTION_WHY,
    build_story_blueprint,
)
from services.story_feed import canonical_story_from_service_payload


# All public guardrail term lists the blueprint copy must clear (substring match,
# mirroring how the engine screens prose).
GUARDRAIL_TERMS = tuple(
    term.lower()
    for term in (
        *BANNED_TERMS,
        *ROBOTIC_TERMS,
        *PUBLIC_BANNED_TERMS,
        *BANNED_PUBLIC_LANGUAGE,
        *DENIED_PUBLIC_PHRASES,
        *INTERNAL_TERMS,
    )
)

PUBLIC_BEATS = (
    'route_change', 'coverage_pressure', 'depth_constraint',
    'sustainability_question', 'availability_depth', 'trust_lane', 'bridge',
)


def _beats():
    return [
        {'key': 'observation', 'label': 'What changed', 'text': 'The bullpen entered before the sixth in recent games.'},
        {'key': 'baseline', 'label': 'Comparison point', 'text': 'That is earlier than the team usually needs the bullpen.'},
        {'key': 'cause', 'label': 'Why it happened', 'text': 'The starters are not covering as many innings as before.'},
        {'key': 'constraint', 'label': 'What it creates', 'text': 'In a tight game, more middle innings keep landing on the bullpen.'},
    ]


def _service_payload(story_available=True):
    if not story_available:
        return {'story_available': False, 'neutral_reason': 'no_story_observations',
                'story_type': None, 'limitations': ['no_story_observations']}
    return {
        'story_available': True,
        'story_type': 'coverage_pressure',
        'story_type_label': 'Coverage Pressure',
        'selected_observation': {'type': 'rotation_pressure'},
        'written_story': {
            'headline': 'The bullpen is carrying more of the game',
            'observation_paragraph': _beats()[0]['text'],
            'baseline_paragraph': _beats()[1]['text'],
            'cause_paragraph': _beats()[2]['text'],
            'constraint_paragraph': _beats()[3]['text'],
        },
        'freshness': {'data_through': '2026-06-24'},
        'trust_metadata': {'resolved': True},
        'limitations': [],
        'as_of_date': '2026-06-25',
    }


# ── Unit: blueprint shape, reuse, determinism ─────────────────────────────────

def test_blueprint_has_five_sections_in_canonical_order():
    bp = build_story_blueprint(story_type='coverage_pressure', beats=_beats(), stable_parts=('118:2026-06-25',))
    assert [s['key'] for s in bp] == list(SECTION_ORDER)
    assert [s['label'] for s in bp] == [
        'What everyone saw', 'What BaseballOS noticed', 'Evidence',
        'Why it matters', 'Why it matters tomorrow',
    ]
    assert all(s['text'].strip() for s in bp)


def test_blueprint_reuses_existing_beats_without_new_claims():
    beats = _beats()
    bp = {s['key']: s for s in build_story_blueprint(story_type='coverage_pressure', beats=beats, stable_parts=('x',))}
    # 'noticed' reuses the authored beat prose verbatim.
    assert bp[SECTION_NOTICED]['text'] == beats[0]['text']
    # Evidence reuses the baseline + cause beats.
    assert beats[1]['text'] in bp[SECTION_EVIDENCE]['text']
    assert beats[2]['text'] in bp[SECTION_EVIDENCE]['text']
    # Surface / lesson / tomorrow come from approved voice copy.
    assert bp[SECTION_SAW]['text'] in SURFACE_FRAMING_LINES['coverage_pressure']
    assert bp[SECTION_WHY]['text'] in LESSON_LINES['coverage_pressure']
    assert bp[SECTION_TOMORROW]['text'] in WATCH_LINES['coverage_pressure']


def test_blueprint_is_deterministic():
    a = build_story_blueprint(story_type='trust_lane', beats=_beats(), stable_parts=('147:2026-06-25',))
    b = build_story_blueprint(story_type='trust_lane', beats=_beats(), stable_parts=('147:2026-06-25',))
    assert a == b


def test_blueprint_empty_without_story_type_or_beats():
    assert build_story_blueprint(story_type='', beats=_beats(), stable_parts=('x',)) == []
    assert build_story_blueprint(story_type='coverage_pressure', beats=[], stable_parts=('x',)) == []


def test_blueprint_drops_sections_with_missing_beats():
    # Only observation present -> noticed + surface + lesson + tomorrow survive
    # (tomorrow is now a voice-bank watch cue, independent of the constraint beat);
    # evidence has no baseline/cause beats to draw on, so it is dropped.
    beats = [{'key': 'observation', 'label': 'What changed', 'text': 'Something changed.'}]
    keys = [s['key'] for s in build_story_blueprint(story_type='bridge', beats=beats, stable_parts=('x',))]
    assert SECTION_NOTICED in keys
    assert SECTION_TOMORROW in keys
    assert SECTION_EVIDENCE not in keys


# ── Guardrails: surface + lesson copy carries no banned/internal/prediction terms

def test_blueprint_copy_clears_all_guardrail_term_lists():
    for beat in PUBLIC_BEATS:
        bp = build_story_blueprint(story_type=beat, beats=_beats(), stable_parts=(beat,))
        for section in bp:
            lowered = section['text'].lower()
            hits = [term for term in GUARDRAIL_TERMS if term and term in lowered]
            assert not hits, (beat, section['key'], hits)


def test_every_surface_and_lesson_form_is_clean():
    for beat in PUBLIC_BEATS:
        for form in SURFACE_FRAMING_LINES[beat] + LESSON_LINES[beat]:
            lowered = form.lower()
            hits = [term for term in GUARDRAIL_TERMS if term and term in lowered]
            assert not hits, (beat, form, hits)


# ── Integration: canonical story carries the blueprint, backward-compatible ────

def test_available_canonical_story_carries_blueprint():
    item = canonical_story_from_service_payload(
        _service_payload(True),
        team={'team_id': 118, 'team_name': 'Kansas City Royals', 'team_abbreviation': 'KC'},
        date='2026-06-25',
    )
    assert [s['key'] for s in item['blueprint']] == list(SECTION_ORDER)
    # Existing contract fields are untouched (additive change).
    for key in ('story_id', 'story_type', 'headline', 'narrative', 'beats', 'evidence'):
        assert key in item
    assert item['beats'][0]['text'] == _beats()[0]['text']


def test_suppressed_story_has_empty_blueprint():
    item = canonical_story_from_service_payload(
        _service_payload(False),
        team={'team_id': 147, 'team_name': 'X', 'team_abbreviation': 'X'},
        date='2026-06-25',
    )
    assert item['story_available'] is False
    assert item['blueprint'] == []
