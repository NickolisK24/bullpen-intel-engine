"""Deterministic Editorial Review (V2) tests.

Covers editorial pass cases, a warning case per check, guardrail preservation
(the engine's existing term lists are reused), false-positive protection on clean
stories, and compatibility with both blueprint and pre-blueprint (4-beat) stories.
Report-only: review never suppresses, never mutates, and is internal.
"""

import copy

from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_voice_library_v1 import BANNED_PUBLIC_LANGUAGE
from services.editorial_review_v1 import (
    CHECK_NA,
    CHECK_PASS,
    CHECK_WARN,
    PREDICTION_PHRASES,
    STATUS_NEUTRAL,
    STATUS_PASS,
    STATUS_WARN,
    review_canonical_feed,
    review_story,
)


def _blueprint_story(**overrides):
    story = {
        'story_id': '118:2026-06-25',
        'story_available': True,
        'story_type': 'coverage_pressure',
        'team_name': 'Kansas City Royals',
        'team_abbreviation': 'KC',
        'headline': 'The bullpen is carrying more of the game',
        'blueprint': [
            {'key': 'what_everyone_saw', 'label': 'What everyone saw',
             'text': 'On the surface, the pitching line says the bullpen did its job.'},
            {'key': 'what_baseballos_noticed', 'label': 'What BaseballOS noticed',
             'text': 'The bullpen has been entering before the sixth far more than usual.'},
            {'key': 'evidence', 'label': 'Evidence',
             'text': 'The starters are not covering as many innings as the recent baseline.\n\n'
                     'More of the middle innings keep landing on the relief group.'},
            {'key': 'why_it_matters', 'label': 'Why it matters',
             'text': 'Bullpen workload is borrowed, not free; the bill arrives in the games that follow.'},
            {'key': 'why_it_matters_tomorrow', 'label': 'Why it matters tomorrow',
             'text': 'If the short starts continue, the bullpen has fewer ways to spread the middle innings.'},
        ],
    }
    story.update(overrides)
    return story


def _v2_story(**overrides):
    # A pre-blueprint (4-beat) story, as the current feed produces.
    story = {
        'story_id': '147:2026-06-25',
        'story_available': True,
        'story_type': 'trust_lane',
        'headline': 'A full bullpen, a narrow group of trusted late arms',
        'beats': [
            {'key': 'observation', 'label': 'What changed', 'text': 'The late innings still come down to a small group.'},
            {'key': 'baseline', 'label': 'Comparison point', 'text': 'That group is smaller than the roster suggests.'},
            {'key': 'cause', 'label': 'Why it happened', 'text': 'Only a few arms have earned late-game trust.'},
            {'key': 'constraint', 'label': 'What it creates', 'text': 'In a tight game, the dependable late innings still run through that group.'},
        ],
    }
    story.update(overrides)
    return story


def _set_section(story, key, text):
    story = copy.deepcopy(story)
    for section in story['blueprint']:
        if section['key'] == key:
            section['text'] = text
    return story


def _check(report, key):
    return next(c['status'] for c in report['checks'] if c['key'] == key)


def _check_keys(report):
    return {c['key'] for c in report['checks']}


# ── Pass cases ────────────────────────────────────────────────────────────────

def test_clean_blueprint_story_passes_all_checks():
    report = review_story(_blueprint_story())
    assert report['status'] == STATUS_PASS
    assert report['warnings'] == []
    assert all(c['status'] == CHECK_PASS for c in report['checks'])
    # All eleven editorial checks are present.
    assert _check_keys(report) == {
        'one_primary_idea', 'structure_complete', 'evidence_present',
        'educational_principle', 'reader_takeaway_present', 'avoids_prediction',
        'avoids_unsupported_certainty', 'avoids_recap_wording', 'avoids_blame_language',
        'avoids_dramatic_journalism', 'avoids_internal_terminology',
    }


def test_clean_pre_blueprint_story_passes_without_false_warnings():
    # A current 4-beat story has no blueprint or lesson section; those structural
    # checks are not-applicable, and nothing false-warns.
    report = review_story(_v2_story())
    assert report['status'] == STATUS_PASS
    assert report['warnings'] == []
    assert _check(report, 'structure_complete') == CHECK_NA
    assert _check(report, 'educational_principle') == CHECK_NA
    assert _check(report, 'evidence_present') == CHECK_PASS
    assert _check(report, 'reader_takeaway_present') == CHECK_PASS


def test_conditional_forward_clause_is_not_a_prediction():
    # "If the short starts continue …" is conditional, not a prediction.
    report = review_story(_blueprint_story())
    assert _check(report, 'avoids_prediction') == CHECK_PASS


# ── Warning case per check ────────────────────────────────────────────────────

def test_prediction_language_warns():
    report = review_story(_set_section(_blueprint_story(), 'why_it_matters',
                                       'The bullpen is projected to lead the league.'))
    assert report['status'] == STATUS_WARN
    assert _check(report, 'avoids_prediction') == CHECK_WARN
    assert any('Prediction language' in w for w in report['warnings'])


def test_unsupported_certainty_warns():
    report = review_story(_set_section(_blueprint_story(), 'why_it_matters',
                                       'This guaranteed the bullpen would hold.'))
    assert _check(report, 'avoids_unsupported_certainty') == CHECK_WARN
    assert any('Unsupported certainty' in w for w in report['warnings'])


def test_recap_wording_warns():
    report = review_story(_set_section(_blueprint_story(), 'what_everyone_saw',
                                       'Fans saw a walk-off home run to end it.'))
    assert _check(report, 'avoids_recap_wording') == CHECK_WARN
    assert any('Recap-heavy wording' in w for w in report['warnings'])


def test_blame_language_warns():
    report = review_story(_set_section(_blueprint_story(), 'what_baseballos_noticed',
                                       'The bullpen collapsed and gave it away.'))
    assert _check(report, 'avoids_blame_language') == CHECK_WARN
    assert any('Blame language' in w for w in report['warnings'])


def test_dramatic_journalism_warns():
    report = review_story(_set_section(_blueprint_story(), 'what_everyone_saw',
                                       'It was a stunning, dramatic finish.'))
    assert _check(report, 'avoids_dramatic_journalism') == CHECK_WARN
    assert any('Dramatic journalism' in w for w in report['warnings'])


def test_internal_terminology_warns():
    report = review_story(_set_section(_blueprint_story(), 'evidence',
                                       'The construction frame shows the pressure.'))
    assert _check(report, 'avoids_internal_terminology') == CHECK_WARN
    assert any('Internal terminology' in w for w in report['warnings'])


def test_lesson_repeating_evidence_warns():
    story = _blueprint_story()
    evidence_text = next(s['text'] for s in story['blueprint'] if s['key'] == 'evidence')
    report = review_story(_set_section(story, 'why_it_matters', evidence_text))
    assert _check(report, 'educational_principle') == CHECK_WARN
    assert any('Lesson repeats evidence' in w for w in report['warnings'])


def test_lesson_too_specific_warns():
    report = review_story(_set_section(_blueprint_story(), 'why_it_matters',
                                       'The Kansas City Royals bullpen is deep right now.'))
    assert _check(report, 'educational_principle') == CHECK_WARN
    assert any('transferable principle' in w for w in report['warnings'])


def test_multiple_competing_ideas_warns():
    report = review_story(_set_section(_blueprint_story(), 'what_baseballos_noticed',
                                       'The bullpen enters early. On the other hand, the rotation is fine.'))
    assert _check(report, 'one_primary_idea') == CHECK_WARN
    assert any('Multiple competing ideas' in w for w in report['warnings'])


def test_missing_blueprint_section_warns():
    story = _blueprint_story()
    story['blueprint'] = [s for s in story['blueprint'] if s['key'] != 'why_it_matters_tomorrow']
    report = review_story(story)
    assert _check(report, 'structure_complete') == CHECK_WARN
    assert any('Missing blueprint section' in w for w in report['warnings'])


def test_missing_evidence_warns():
    story = _v2_story()
    story['beats'] = [b for b in story['beats'] if b['key'] not in ('baseline', 'cause')]
    report = review_story(story)
    assert _check(report, 'evidence_present') == CHECK_WARN
    assert any('No evidence section' in w for w in report['warnings'])


def test_missing_reader_takeaway_warns():
    story = _v2_story()
    story['beats'] = [b for b in story['beats'] if b['key'] != 'constraint']
    report = review_story(story)
    assert _check(report, 'reader_takeaway_present') == CHECK_WARN
    assert any('No reader-facing takeaway' in w for w in report['warnings'])


# ── Guardrail preservation ────────────────────────────────────────────────────

def test_existing_engine_guardrails_are_reused():
    # The editorial prediction list extends, not replaces, the engine's lists.
    for term in PUBLIC_BANNED_TERMS:
        assert term.lower() in PREDICTION_PHRASES
    for term in BANNED_PUBLIC_LANGUAGE:
        assert term.lower() in PREDICTION_PHRASES


# ── Report-only behavior + aggregation ────────────────────────────────────────

def test_suppressed_story_is_neutral_and_unchecked():
    report = review_story({'story_id': 'x', 'story_available': False})
    assert report['status'] == STATUS_NEUTRAL
    assert report['checks'] == [] and report['warnings'] == []


def test_review_never_mutates_the_story():
    story = _blueprint_story()
    snapshot = copy.deepcopy(story)
    review_story(story)
    assert story == snapshot


def test_review_canonical_feed_aggregates_and_skips_suppressed():
    feed = {
        'items': [
            _blueprint_story(story_id='1:d'),                       # pass
            _set_section(_blueprint_story(story_id='2:d'), 'what_everyone_saw',
                         'It was a stunning collapse.'),            # warn (drama + blame)
            {'story_id': '3:d', 'story_available': False},          # skipped
        ],
    }
    result = review_canonical_feed(feed)
    assert result['reviewed'] == 2
    assert result['pass_count'] == 1
    assert result['warn_count'] == 1
    assert 'editorial review:' in result['summary']
