"""Editorial voice contract infrastructure tests.

These tests cover the shared helpers public surfaces migrate to. Compare
Bullpens moved first; Today's Watch, What Changed, and the homepage-visible
completed-game story writers now share the same public voice contract.
"""

from pathlib import Path

from services.editorial_voice_contract_v1 import (
    BASEBALL_CONSEQUENCE_LINES,
    STATUS_PASS,
    STATUS_WARN,
    build_comparison_explanation,
    build_comparison_sentence,
    contains_editorial_banned_language,
    count_to_baseball_language,
    editorial_conformance_report,
    editorial_voice_contract_report,
    find_editorial_violations,
    is_editorially_conformant,
    raw_count_matches,
    render_baseball_consequence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

UNMIGRATED_PUBLIC_SURFACE_FILES = (
    'backend/services/story_writer_v1.py',
    'backend/services/story_feed.py',
)


def test_count_to_baseball_language_uses_baseball_copy_without_raw_counts():
    expected = {
        0: 'not one trusted arm',
        1: 'the lone trusted arm',
        2: 'both trusted arms',
        3: 'three trusted arms',
        6: 'six trusted arms',
        7: 'a deeper group of trusted arms',
        12: 'a large group of trusted arms',
    }

    for count, phrase in expected.items():
        rendered = count_to_baseball_language(count, 'trusted arm', 'trusted arms')
        assert rendered == phrase
        assert raw_count_matches(rendered) == []


def test_count_to_baseball_language_can_return_determiner_only():
    assert count_to_baseball_language(0, 'arm', include_noun=False) == 'not one'
    assert count_to_baseball_language(1, 'arm', include_noun=False) == 'the lone'
    assert count_to_baseball_language(2, 'arm', include_noun=False) == 'both'


def test_baseball_consequence_translation_is_deterministic_and_governed():
    first = render_baseball_consequence('late_inning_margin', stable_parts=('KC', 'available'))
    second = render_baseball_consequence('late_inning_margin', stable_parts=('KC', 'available'))

    assert first == second
    assert first.rstrip('.') in BASEBALL_CONSEQUENCE_LINES['late_inning_margin']
    assert is_editorially_conformant(first)


def test_comparison_sentence_orders_subject_reason_and_baseball_consequence():
    subject = 'Kansas City has both trusted arms rested'
    reason = 'the bridge has not one arm on the watch list'
    sentence = build_comparison_sentence(
        subject=subject,
        reason=reason,
        consequence_key='late_inning_margin',
        stable_parts=('KC', 'bridge'),
    )

    assert sentence.startswith(f'{subject} because {reason}.')
    assert 'That ' in sentence
    assert raw_count_matches(sentence) == []
    assert is_editorially_conformant(sentence, allow_raw_counts=False)


def test_comparison_explanation_returns_structured_parts_for_future_surfaces():
    explanation = build_comparison_explanation(
        subject='The bullpen has both clean late paths open',
        reason='the late group is rested',
        consequence='That gives the manager more than one route through a tight game',
    )

    assert explanation == {
        'subject': 'The bullpen has both clean late paths open',
        'reason': 'the late group is rested',
        'baseball_consequence': 'That gives the manager more than one route through a tight game.',
        'sentence': (
            'The bullpen has both clean late paths open because the late group is rested. '
            'That gives the manager more than one route through a tight game.'
        ),
    }


def test_editorial_banned_language_helper_catches_singular_plural_loopholes():
    cases = (
        'The practical path is thinner than before.',
        'The practical paths are thinner than before.',
        'The current route retained 0 arm from the baseline.',
        'The current route retained 0 arms from the baseline.',
        'That is a 3-spot change from the prior route.',
        'Those are 3-spot changes from the prior route.',
        'Both bullpens currently show similar availability distributions.',
        'The availability distribution looks similar.',
        'Clean option is limited as the public explanation.',
        'Clean options are limited as the public explanation.',
        'The secondary arms are carrying caution.',
        'Interpretation weighs clean Trust Arms above clean Depth Arms.',
        'Late-inning pressure weighs Trust and Bridge Arm stress above Depth Arm stress.',
        'Two relievers are classified Available.',
        'The bridge has clean arms left.',
        'The bridge has a short list of clean arms left.',
        'The bullpen is in good shape.',
        'The bullpen has fewer clean ways through a close game.',
        'That narrows the usable group before the game gets late.',
        'The club has less usable depth than yesterday.',
        'Only 0 of 0 bullpen arms have clear role labels.',
        'Coverage margin combines active capacity and resource health.',
        'The trust structure has 0 trusted-group arms.',
        'There are 0 available in the top trust bucket.',
        'Trust metadata limits confidence in the explanation.',
        'This readiness state reflects workload evidence.',
        'Coverage evidence is partial for the explained state.',
        'The current availability read is limited.',
        'The current bullpen planning read is limited.',
        'Explanation confidence mirrors the existing value.',
        'Governed availability evidence supports Monitor state.',
    )

    for text in cases:
        assert contains_editorial_banned_language(text), text


def test_editorial_banned_language_helper_catches_raw_arithmetic_patterns():
    violations = find_editorial_violations('Only 2 of 7 bullpen arms have clear labels.')

    assert any(item['category'] == 'raw_count_formula' for item in violations)
    assert any(item['match'] == '2 of 7' for item in violations)


def test_shared_consequence_helpers_retire_model_adjacent_phrases():
    retired = ('clean ways', 'usable group', 'usable depth')

    for key, forms in BASEBALL_CONSEQUENCE_LINES.items():
        for form in forms:
            lower = form.lower()
            for phrase in retired:
                assert phrase not in lower, (key, phrase, form)

    rendered = ' '.join(
        render_baseball_consequence(
            key,
            stable_parts=('phrase-retirement', key, index),
        )
        for key in BASEBALL_CONSEQUENCE_LINES
        for index in range(8)
    ).lower()
    for phrase in retired:
        assert phrase not in rendered


def test_find_editorial_violations_reports_term_match_category_and_order():
    text = 'Context indicates the practical paths retained 0 arms.'
    violations = find_editorial_violations(text)

    assert [item['match'].lower() for item in violations] == [
        'context indicates',
        'practical paths',
        'retained 0 arms',
    ]
    assert all(item['category'] for item in violations)
    assert [item['start'] for item in violations] == sorted(item['start'] for item in violations)


def test_editorial_conformance_report_can_gate_raw_counts_for_prose():
    count_phrase = count_to_baseball_language(2, 'trusted reliever')
    safe = f'The bridge has {count_phrase}, so the late innings have room to breathe.'
    unsafe = 'The bridge has 2 trusted relievers, so the late innings have room to breathe.'

    assert editorial_conformance_report(safe, allow_raw_counts=False)['status'] == STATUS_PASS
    report = editorial_conformance_report(unsafe, allow_raw_counts=False)
    assert report['status'] == STATUS_WARN
    assert report['raw_counts'] == ['2']


def test_contract_report_documents_migrated_surfaces():
    report = editorial_voice_contract_report()

    assert report['plural_aware_matching'] is True
    assert report['count_language']['raw_counts_in_prose'] is False
    assert 'late_inning_margin' in report['consequence_keys']
    assert report['public_surfaces_migrated'] == [
        'compare_bullpens',
        'todays_watch',
        'what_changed',
        'todays_story_completed_game',
    ]


def test_compare_bullpens_is_registered_as_first_migrated_surface():
    text = (REPO_ROOT / 'backend/services/bullpen_comparison.py').read_text(encoding='utf-8')
    assert 'editorial_voice_contract_v1' in text


def test_todays_watch_is_registered_as_migrated_surface():
    text = (REPO_ROOT / 'backend/services/tonight_candidate_selection.py').read_text(encoding='utf-8')
    assert 'editorial_voice_contract_v1' in text


def test_what_changed_is_registered_as_migrated_surface():
    for rel_path in (
        'backend/services/what_changed_since_yesterday_copy.py',
        'backend/services/what_changed_since_yesterday_public.py',
    ):
        text = (REPO_ROOT / rel_path).read_text(encoding='utf-8')
        assert 'editorial_voice_contract_v1' in text


def test_todays_story_completed_game_is_registered_as_migrated_surface():
    text = (REPO_ROOT / 'backend/story_writers/base_story_writer.py').read_text(encoding='utf-8')
    assert 'editorial_voice_contract_v1' in text


def test_helpers_are_not_wired_into_unmigrated_public_surfaces_yet():
    for rel_path in UNMIGRATED_PUBLIC_SURFACE_FILES:
        text = (REPO_ROOT / rel_path).read_text(encoding='utf-8')
        assert 'editorial_voice_contract_v1' not in text, rel_path
