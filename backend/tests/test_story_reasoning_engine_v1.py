"""Story Reasoning Engine V1 (V2) tests.

Covers the deterministic editorial-intent contract that sits between Story
Construction and the Story Writer: the five answered questions, reproducibility,
beat resolution, evidence selection from the construction frame, graceful
degradation, guardrail cleanliness of the new copy, writer integration
(backward-compatible + byte-stable prose), and — critically — that the intent is
internal only and never reaches the canonical story or public payload.
"""

import copy

import pytest

from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_four_beat_interpreter_v1 import (
    PUBLIC_BANNED_TERMS,
    PUBLIC_BEATS,
    public_beat_for_observation,
)
from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES,
    PURPOSE_LESSON,
    PURPOSE_SURFACE,
    approved_sentence_forms,
)
from services.story_writer_v1 import (
    BANNED_TERMS,
    ROBOTIC_TERMS,
    SECTION_KEYS,
    write_story_frame,
)
from services.editorial_review_v1 import (
    BLAME_PHRASES,
    CERTAINTY_PHRASES,
    DRAMA_PHRASES,
    INTERNAL_PHRASES,
    MULTI_IDEA_PHRASES,
    PREDICTION_PHRASES,
    RECAP_PHRASES,
    STATUS_PASS,
    review_story,
)
from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import canonical_story_from_service_payload
from services.story_reasoning_engine_v1 import (
    CAPABILITY,
    EDITORIAL_QUESTIONS,
    EVIDENCE_SECTIONS,
    FIELD_MISCONCEPTION,
    FIELD_READER_SHIFT,
    FIELD_STRUCTURAL_TRUTH,
    FIELD_SUPPORTING_EVIDENCE,
    FIELD_TRANSFERABLE_PRINCIPLE,
    MAX_SUPPORTING_EVIDENCE,
    TRUTH_BY_BEAT,
    VERSION,
    WATCH_BY_BEAT,
    build_editorial_intent,
    reasoning_engine_report,
    select_supporting_evidence,
)

from tests.test_story_writer_v1 import frame_for, team_context


ANSWER_FIELDS = (
    FIELD_MISCONCEPTION,
    FIELD_STRUCTURAL_TRUTH,
    FIELD_SUPPORTING_EVIDENCE,
    FIELD_TRANSFERABLE_PRINCIPLE,
    FIELD_READER_SHIFT,
)

# Every internal observation type that maps to a public beat, with a context that
# reliably produces that frame.
SUPPORTED_CASES = {
    TYPE_ROTATION_PRESSURE: dict(
        rotation={'rotation_avg_ip_7d': 4.6, 'rotation_avg_ip_14d': 5.6,
                  'rotation_ip_trend': -1.0, 'early_bullpen_entry_rate': 55.0,
                  'bullpen_coverage_ip_7d': 4.4},
    ),
    TYPE_CONCENTRATION_PRESSURE: dict(
        concentration={'concentration_band': 'narrow', 'top_three_workload_share_10d': 74.0},
    ),
    TYPE_OPTIONALITY_STRENGTH: dict(
        optionality={'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
                     'available_arms_count': 7},
    ),
}

ALL_GUARDRAIL_LISTS = (
    BANNED_TERMS, ROBOTIC_TERMS, PUBLIC_BANNED_TERMS, BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES, PREDICTION_PHRASES, CERTAINTY_PHRASES, RECAP_PHRASES,
    BLAME_PHRASES, DRAMA_PHRASES, MULTI_IDEA_PHRASES, INTERNAL_PHRASES,
)


def _frame(observation_type):
    kwargs = SUPPORTED_CASES.get(observation_type, {})
    return frame_for(team_context(**kwargs), observation_type)


def _bridge_frame():
    # A synthetic bridge frame (the default fixture does not generate one). The
    # engine resolves the public beat from the observation type and reads facts
    # from ``story_frame``, so a minimal frame exercises the bridge path.
    return {
        'team_id': 200,
        'team_name': 'Bridge Club',
        'team_abbreviation': 'BC',
        'observation_type': TYPE_BRIDGE_INSTABILITY,
        'severity': 'medium',
        'construction_confidence': 'medium',
        'story_frame': {
            'cause_facts': {'rotation_avg_ip_7d': 4.8},
            'baseline_facts': {'baseline_read': {'available': True}},
            'interpretation_facts': {'optionality_band': 'thin'},
            'observation_facts': {'type': TYPE_BRIDGE_INSTABILITY, 'bridge_gap_innings': 2.0},
            'constraint_facts': {},
        },
    }


# ── The five answered questions ───────────────────────────────────────────────

def test_intent_answers_all_five_editorial_questions():
    intent = build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE,
        frame=_frame(TYPE_CONCENTRATION_PRESSURE),
        selected_observation={'severity': 'high'},
    )
    assert intent['capability'] == CAPABILITY
    assert intent['version'] == VERSION
    assert intent['story_type'] in PUBLIC_BEATS
    assert intent['observation_type'] == TYPE_CONCENTRATION_PRESSURE
    # Each editorial question is answered.
    assert isinstance(intent[FIELD_MISCONCEPTION], str) and intent[FIELD_MISCONCEPTION]
    assert isinstance(intent[FIELD_STRUCTURAL_TRUTH], str) and intent[FIELD_STRUCTURAL_TRUTH]
    assert isinstance(intent[FIELD_TRANSFERABLE_PRINCIPLE], str) and intent[FIELD_TRANSFERABLE_PRINCIPLE]
    assert isinstance(intent[FIELD_READER_SHIFT], str) and intent[FIELD_READER_SHIFT]
    assert intent[FIELD_SUPPORTING_EVIDENCE]
    assert intent['limitations'] == []
    # The exported question set matches the answered fields.
    assert set(EDITORIAL_QUESTIONS) == set(ANSWER_FIELDS)


@pytest.mark.parametrize('observation_type', list(SUPPORTED_CASES))
def test_supported_observation_types_produce_complete_intent(observation_type):
    intent = build_editorial_intent(
        observation_type=observation_type,
        frame=_frame(observation_type),
        selected_observation={'severity': 'high'},
    )
    assert intent['story_type'] == public_beat_for_observation(
        observation_type, frame=_frame(observation_type)
    )
    for field in ANSWER_FIELDS:
        assert intent[field] not in (None, '', [])


# ── Determinism / reproducibility ─────────────────────────────────────────────

def test_intent_is_deterministic_for_same_frame():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    first = build_editorial_intent(observation_type=TYPE_CONCENTRATION_PRESSURE, frame=frame)
    second = build_editorial_intent(observation_type=TYPE_CONCENTRATION_PRESSURE, frame=frame)
    assert first == second


def test_intent_is_reproducible_across_rebuilt_frames():
    a = build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE, frame=_frame(TYPE_CONCENTRATION_PRESSURE),
    )
    b = build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE, frame=_frame(TYPE_CONCENTRATION_PRESSURE),
    )
    assert a == b


# ── Beat resolution ───────────────────────────────────────────────────────────

def test_resolves_beat_from_explicit_story_type():
    # An already-resolved public beat is honored without an observation type.
    intent = build_editorial_intent(story_type='trust_lane', frame={})
    assert intent['story_type'] == 'trust_lane'
    assert intent[FIELD_STRUCTURAL_TRUTH] == TRUTH_BY_BEAT['trust_lane']
    assert intent[FIELD_READER_SHIFT] == WATCH_BY_BEAT['trust_lane']


def test_resolves_beat_from_observation_type_matches_public_layer():
    for observation_type in SUPPORTED_CASES:
        frame = _frame(observation_type)
        assert build_editorial_intent(observation_type=observation_type, frame=frame)['story_type'] \
            == public_beat_for_observation(observation_type, frame=frame)


def test_unsupported_type_degrades_gracefully():
    intent = build_editorial_intent(observation_type='not_a_real_type', frame={})
    assert intent['story_type'] is None
    assert intent['limitations'] == ['unsupported_story_type']
    for field in ANSWER_FIELDS:
        assert intent[field] in (None, [])
    # Capability/version are still present (well-formed object, not an error).
    assert intent['capability'] == CAPABILITY


def test_no_arguments_degrades_gracefully():
    intent = build_editorial_intent()
    assert intent['story_type'] is None
    assert intent['limitations'] == ['unsupported_story_type']


# ── Surface read + lesson reuse the approved voice library ─────────────────────

def test_misconception_and_principle_come_from_voice_library():
    for observation_type in SUPPORTED_CASES:
        frame = _frame(observation_type)
        intent = build_editorial_intent(observation_type=observation_type, frame=frame)
        beat = intent['story_type']
        assert intent[FIELD_MISCONCEPTION] in approved_sentence_forms(beat, PURPOSE_SURFACE)
        assert intent[FIELD_TRANSFERABLE_PRINCIPLE] in approved_sentence_forms(beat, PURPOSE_LESSON)


# ── Structural truth + reader shift copy banks ────────────────────────────────

def test_new_copy_banks_cover_every_public_beat():
    assert set(TRUTH_BY_BEAT) == set(PUBLIC_BEATS)
    assert set(WATCH_BY_BEAT) == set(PUBLIC_BEATS)


def test_structural_truth_and_reader_shift_drawn_from_banks():
    intent = build_editorial_intent(observation_type=TYPE_OPTIONALITY_STRENGTH,
                                    frame=_frame(TYPE_OPTIONALITY_STRENGTH))
    beat = intent['story_type']
    assert intent[FIELD_STRUCTURAL_TRUTH] == TRUTH_BY_BEAT[beat]
    assert intent[FIELD_READER_SHIFT] == WATCH_BY_BEAT[beat]


def test_bridge_path_resolves_and_completes():
    intent = build_editorial_intent(frame=_bridge_frame())
    assert intent['story_type'] == 'bridge'
    assert intent[FIELD_STRUCTURAL_TRUTH] == TRUTH_BY_BEAT['bridge']
    assert intent[FIELD_READER_SHIFT] == WATCH_BY_BEAT['bridge']
    assert intent['confidence'] == 'medium'
    assert intent['severity'] == 'medium'
    assert intent[FIELD_SUPPORTING_EVIDENCE]


# ── Supporting evidence selection ─────────────────────────────────────────────

def test_supporting_evidence_is_structured_and_diverse():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    evidence = build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE, frame=frame,
    )[FIELD_SUPPORTING_EVIDENCE]
    assert 0 < len(evidence) <= MAX_SUPPORTING_EVIDENCE
    keys = [row['key'] for row in evidence]
    assert len(keys) == len(set(keys))  # distinct metrics
    for row in evidence:
        assert set(row) == {'section', 'key', 'value'}
        assert row['section'] in EVIDENCE_SECTIONS
        assert row['key'] not in ('type', 'team_name')  # structural labels excluded
        assert row['value'] not in (None, '', [], {})
    # Spans more than one editorial angle.
    assert len({row['section'] for row in evidence}) >= 2


def test_supporting_evidence_empty_for_factless_frame():
    intent = build_editorial_intent(observation_type=TYPE_CONCENTRATION_PRESSURE,
                                    frame={'observation_type': TYPE_CONCENTRATION_PRESSURE})
    assert intent[FIELD_SUPPORTING_EVIDENCE] == []
    assert 'no_structured_evidence' in intent['limitations']


def test_select_supporting_evidence_accepts_bare_sections_dict():
    sections = {'cause_facts': {'rotation_ip_trend': -0.9}, 'observation_facts': {'type': 'x'}}
    evidence = select_supporting_evidence(sections)
    assert evidence == [{'section': 'cause_facts', 'key': 'rotation_ip_trend', 'value': -0.9}]


# ── Guardrail cleanliness of the new copy ─────────────────────────────────────

def test_new_copy_clears_every_guardrail_vocabulary():
    for bank in (TRUTH_BY_BEAT, WATCH_BY_BEAT):
        for text in bank.values():
            lowered = text.lower()
            for terms in ALL_GUARDRAIL_LISTS:
                for term in terms:
                    term = (term or '').lower()
                    assert not (term and term in lowered), f'{term!r} found in {text!r}'


def test_intent_text_fields_clear_guardrails_end_to_end():
    for observation_type in SUPPORTED_CASES:
        intent = build_editorial_intent(observation_type=observation_type,
                                        frame=_frame(observation_type))
        text = ' '.join(
            intent[field] for field in
            (FIELD_MISCONCEPTION, FIELD_STRUCTURAL_TRUTH, FIELD_TRANSFERABLE_PRINCIPLE, FIELD_READER_SHIFT)
            if intent[field]
        ).lower()
        for terms in ALL_GUARDRAIL_LISTS:
            for term in terms:
                term = (term or '').lower()
                assert not (term and term in text), f'{term!r} found in intent text'


# ── Metadata capture + input immutability ─────────────────────────────────────

def test_captures_severity_and_confidence():
    frame = _frame(TYPE_ROTATION_PRESSURE)  # fixture sets construction_confidence
    intent = build_editorial_intent(
        observation_type=TYPE_ROTATION_PRESSURE, frame=frame,
        selected_observation={'severity': 'high'},
    )
    assert intent['severity'] == 'high'
    assert intent['confidence'] == frame.get('construction_confidence')


def test_does_not_mutate_inputs():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    observation = {'severity': 'high', 'type': TYPE_CONCENTRATION_PRESSURE}
    frame_snapshot = copy.deepcopy(frame)
    observation_snapshot = copy.deepcopy(observation)
    build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE, frame=frame, selected_observation=observation,
    )
    assert frame == frame_snapshot
    assert observation == observation_snapshot


# ── Writer integration: additive + byte-stable prose ──────────────────────────

def test_writer_attaches_editorial_intent_without_changing_prose():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    output = write_story_frame(frame)
    assert output['editorial_intent']['capability'] == CAPABILITY
    # Backward-compatible: written sections + validation unchanged.
    assert tuple(output['written_observation'].keys()) == SECTION_KEYS
    assert output['validation']['passed'] is True


def test_writer_uses_supplied_intent():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    supplied = build_editorial_intent(
        observation_type=TYPE_CONCENTRATION_PRESSURE, frame=frame,
        selected_observation={'severity': 'high'},
    )
    output = write_story_frame(frame, editorial_intent=supplied)
    assert output['editorial_intent'] == supplied
    assert output['editorial_intent']['severity'] == 'high'


def test_writer_remains_deterministic_with_intent():
    frame = _frame(TYPE_CONCENTRATION_PRESSURE)
    assert write_story_frame(frame) == write_story_frame(frame)


# ── Service path: intent present internally, aligned, never exposed ────────────

def _available_payload():
    ctx = team_context(concentration={'concentration_band': 'narrow', 'top_three_workload_share_10d': 74.0})
    payload = build_team_story(118, as_of_date='2026-06-20', team_context=ctx)
    assert payload['story_available'] is True
    return payload


def test_service_payload_carries_intent_internally_and_aligned():
    payload = _available_payload()
    intent = payload['writer_output']['editorial_intent']
    assert intent['capability'] == CAPABILITY
    # The internal intent's beat matches the resolved public story type.
    assert intent['story_type'] == payload['story_type']


def test_intent_is_not_exposed_in_canonical_story():
    payload = _available_payload()
    intent = payload['writer_output']['editorial_intent']
    canonical = canonical_story_from_service_payload(payload, date='2026-06-20')
    assert 'editorial_intent' in payload['writer_output']      # internal: present
    assert 'editorial_intent' not in canonical                 # public: absent
    blob = repr(canonical)
    assert intent[FIELD_STRUCTURAL_TRUTH] not in blob
    assert intent[FIELD_READER_SHIFT] not in blob


def test_canonical_story_still_passes_editorial_review():
    payload = _available_payload()
    canonical = canonical_story_from_service_payload(payload, date='2026-06-20')
    report = review_story(canonical)
    assert report['status'] == STATUS_PASS
    assert report['warnings'] == []


# ── Report ────────────────────────────────────────────────────────────────────

def test_reasoning_engine_report():
    report = reasoning_engine_report()
    assert report['capability'] == CAPABILITY
    assert report['deterministic'] is True
    assert report['beats_covered'] == sorted(PUBLIC_BEATS)
    assert report['max_supporting_evidence'] == MAX_SUPPORTING_EVIDENCE
    assert list(report['evidence_sections']) == list(EVIDENCE_SECTIONS)
