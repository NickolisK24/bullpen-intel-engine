"""Editorial voice tests for What Changed public copy."""

import re

from services.editorial_voice_contract_v1 import contains_editorial_banned_language
from services.what_changed_since_yesterday import CHANGE_RESTED_OPTIONS
from services.what_changed_since_yesterday_copy import (
    COPY_FLAG_TOO_MECHANICAL,
    COPY_STATUS_GENERATED,
    COPY_STATUS_SKIPPED_NO_MEANINGFUL_CHANGE,
    build_what_changed_public_copy,
)


def _change(direction, previous, current):
    return {
        'change_type': CHANGE_RESTED_OPTIONS,
        'change_direction': direction,
        'supporting_facts': [
            {
                'fact_key': 'rested_options',
                'previous_value': previous,
                'current_value': current,
            },
        ],
    }


def _team():
    return {
        'team_name': 'Alpha Club',
        'team_abbreviation': 'AAA',
    }


def _copy(change):
    return build_what_changed_public_copy(_team(), top_change=change, changes=[change])


def _public_text(copy):
    return ' '.join(
        str(copy.get(key) or '')
        for key in ('public_headline', 'public_summary', 'public_context')
    )


def test_improved_movement_renders_as_baseball_consequence():
    copy = _copy(_change('increased', 2, 5))
    text = _public_text(copy).lower()

    assert copy['public_copy_status'] == COPY_STATUS_GENERATED
    assert copy['copy_review_flags'] == []
    assert 'breathing room' in text or 'rested arms' in text
    assert 'clean ways' not in text
    assert 'usable group' not in text
    assert 'moved from' not in text
    assert 'from 2 to 5' not in text


def test_worsening_movement_renders_as_baseball_consequence():
    copy = _copy(_change('decreased', 5, 2))
    text = _public_text(copy).lower()

    assert copy['copy_review_flags'] == []
    assert 'late-inning cushion' in text or 'middle innings' in text
    assert 'clean ways' not in text
    assert 'usable group' not in text
    assert 'moved from' not in text
    assert 'from 5 to 2' not in text


def test_no_meaningful_change_stays_neutral_and_unrendered():
    copy = build_what_changed_public_copy(_team(), top_change=None, changes=[])

    assert copy['public_copy_generated'] is False
    assert copy['public_copy_status'] == COPY_STATUS_SKIPPED_NO_MEANINGFUL_CHANGE
    assert copy['public_headline'] is None
    assert copy['public_summary'] is None
    assert copy['public_context'] is None


def test_zero_count_prose_protection():
    copy = _copy(_change('increased', 0, 3))
    text = _public_text(copy).lower()

    assert copy['copy_review_flags'] == []
    assert not re.search(r'(?<![\w-])0(?![\w-])', text)
    assert '0 trusted' not in text
    assert 'from 0 to' not in text
    assert 'moved from' not in text


def test_banned_phrase_scanner_is_applied_to_fallback_copy():
    change = {
        'change_type': 'unknown_public_test_change',
        'change_direction': 'changed',
        'change_summary': 'The practical path moved from 0 to 1.',
        'supporting_facts': [],
    }
    copy = build_what_changed_public_copy(_team(), top_change=change, changes=[change])
    text = _public_text(copy)

    assert not contains_editorial_banned_language(text)
    assert 'practical path' not in text.lower()
    assert COPY_FLAG_TOO_MECHANICAL not in copy['copy_review_flags']
