from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    DENIED_PUBLIC_PHRASES,
    approved_sentence_forms,
    contains_banned_public_language,
    contains_denied_public_phrase,
    render_voice_line,
    voice_library_report,
)


PUBLIC_BEATS = (
    BEAT_ROUTE_CHANGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_SUSTAINABILITY_QUESTION,
)


def test_voice_library_exposes_approved_forms_for_each_public_beat():
    report = voice_library_report()

    assert report['deterministic'] is True
    for beat in PUBLIC_BEATS:
        forms = approved_sentence_forms(beat)
        assert len(forms) >= 10
        assert report['beats'][beat]['opening']['count'] == len(forms)
        assert report['beats'][beat]['opening']['contains_denied_public_phrase'] is False
        assert report['beats'][beat]['opening']['contains_banned_public_language'] is False
        for form in forms:
            assert contains_denied_public_phrase(form) is False
            assert contains_banned_public_language(form) is False


def test_voice_selection_is_deterministic_for_same_stable_identifiers():
    kwargs = {
        'stable_parts': (118, 'KC', 'route_change', 'First Arm and Second Arm'),
        'team': 'Kansas City Royals',
        'possessive': "Kansas City Royals'",
        'names': 'First Arm and Second Arm',
    }

    first = render_voice_line(BEAT_ROUTE_CHANGE, **kwargs)
    second = render_voice_line(BEAT_ROUTE_CHANGE, **kwargs)

    assert first == second


def test_same_beat_can_render_multiple_approved_sentence_forms():
    outputs = {
        render_voice_line(
            BEAT_ROUTE_CHANGE,
            stable_parts=(team_id, 'route_change', 'First Arm and Second Arm'),
            team=f'Team {team_id}',
            possessive=f"Team {team_id}'s",
            names='First Arm and Second Arm',
        )
        for team_id in range(100, 140)
    }

    assert len(outputs) >= 5
    for output in outputs:
        assert contains_denied_public_phrase(output) is False
        assert contains_banned_public_language(output) is False


def test_voice_library_keeps_best_story_curiosity_forms_available():
    route_forms = approved_sentence_forms(BEAT_ROUTE_CHANGE)
    coverage_forms = approved_sentence_forms(BEAT_COVERAGE_PRESSURE)
    sustainability_forms = approved_sentence_forms(BEAT_SUSTAINABILITY_QUESTION)

    assert 'The next close game still points toward {names}' in route_forms
    assert 'The game keeps arriving at the bullpen sooner than the baseline' in coverage_forms
    assert 'The workload continues to land in the same pocket' in sustainability_forms


def test_depth_constraint_voice_forms_can_use_named_pressure_points():
    forms = approved_sentence_forms(BEAT_DEPTH_CONSTRAINT)

    assert any('{names}' in form and 'pressure point' in form for form in forms)
    assert any('{names}' in form and 'late-game map' in form for form in forms)
    assert any('{names}' in form and 'roster count' in form for form in forms)


def test_voice_library_deny_lists_cover_requested_editorial_terms():
    for phrase in (
        'sit at the front of',
        'active route',
        'practical path',
        'route count',
        'named names',
        'usable relievers',
        'still have multiple ways to cover a close game',
        'not boxed into one relief lane',
        'less room behind the trusted late plan',
        'relief read',
    ):
        assert phrase in DENIED_PUBLIC_PHRASES

    for phrase in ('projected', 'odds', 'expected to win'):
        assert phrase in BANNED_PUBLIC_LANGUAGE
