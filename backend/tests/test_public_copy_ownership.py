"""Public copy is authored at its semantic owner, not repaired in the browser.

Three public sentences used to reach the reader only because a frontend regex
rewrote them on the way to the screen:

- the bullpen landscape note said "Sorted deterministically by ...";
- the Today watch note said "Bullpen cushion is constrained";
- the availability usage-check framing said "Avoid" and "Backtest".

The browser swapped each for a reader form, which made the presentation layer a
second author of a BaseballOS public claim, and on the usage-check card it meant
the blocked-framing guard scanned text the browser had already repaired.

Those rewrites are gone. These tests pin the wording at the owner instead, so a
regression fails here -- next to the code that authors it -- rather than
silently shipping engine vocabulary to a reader.

Nothing here changes a threshold, a state, a count, or which read is chosen.
"""

import re

from services.availability_backtest import _framing
from services.game_context import _landscape_notes
from services.public_bullpen_copy import find_banned_public_prose
from services.tonight_candidate_selection import _optionality_evidence


# Engine vocabulary that must not appear in these authored public sentences.
# ``public_bullpen_copy`` owns the full ban list; this is the subset the three
# retired frontend rewriters were compensating for.
RETIRED_REWRITE_TERMS = (
    'deterministic',
    'deterministically',
    'endpoint',
    'endpoints',
    'snapshot',
    'backend',
    'constrained',
    'restricted',
    'Monitor',
    'Avoid',
    'backtest',
)


def _offending_terms(text):
    return [
        term for term in RETIRED_REWRITE_TERMS
        if re.search(rf'\b{re.escape(term)}\b', text, re.IGNORECASE)
    ]


# ── landscape notes (services/game_context.py) ──────────────────────────────

def test_landscape_notes_carry_no_engine_vocabulary():
    for note in _landscape_notes({'data_state': 'current'}):
        assert _offending_terms(note) == [], note


def test_landscape_notes_state_the_grouping_in_reader_language():
    notes = _landscape_notes({'data_state': 'current'})
    assert 'Groups reflect the current bullpen counts for each team.' in notes


def test_landscape_notes_stay_clean_in_every_data_state():
    for state in ('current', 'historical', 'stale', 'unavailable', None):
        for note in _landscape_notes({'data_state': state}):
            assert _offending_terms(note) == [], (state, note)


# ── Today watch note (services/tonight_candidate_selection.py) ──────────────

def test_optionality_evidence_uses_reader_vocabulary():
    for band in ('thin', 'narrow', 'wide', None):
        sentence = _optionality_evidence(band)
        assert _offending_terms(sentence) == [], (band, sentence)


def test_the_widest_optionality_band_reads_as_stretched():
    # Previously 'Bullpen cushion is constrained', repaired to 'stretched' in
    # the browser. The reader-visible sentence is unchanged; its author moved.
    assert _optionality_evidence('other') == 'Bullpen cushion is stretched'


# ── usage-check framing (services/availability_backtest.py) ─────────────────

def test_backtest_framing_carries_no_engine_vocabulary():
    for field, text in _framing().items():
        assert _offending_terms(text) == [], (field, text)


def test_backtest_framing_uses_the_public_availability_label():
    framing = _framing()
    assert 'Unavailable' in framing['claim']
    assert 'Avoid' not in framing['claim']
    assert 'Avoid' not in framing['caveat']


def test_backtest_framing_title_is_reader_facing():
    assert 'Backtest' not in _framing()['title']
    assert 'Usage Check' in _framing()['title']


# ── the shared guard agrees ─────────────────────────────────────────────────

def test_authored_public_sentences_pass_the_shared_prose_guard():
    """The platform's own banned-prose scan accepts all three, unaided.

    This is the property that lets the browser stop rewriting: the copy is
    already clean when it is published, so nothing downstream has to repair it.
    """
    candidates = list(_landscape_notes({'data_state': 'current'}))
    candidates.append(_optionality_evidence('other'))
    candidates.extend(_framing().values())
    for text in candidates:
        assert find_banned_public_prose('authored', text) is None, text
