"""H-7 corpus guard — evidence discrimination across a realistic league.

The existing unit test (``test_preview_evidence_selection.py``) proves the
SELECTOR ranks correctly. It could not prove the thing H-7 was actually about,
because it hands every club a hand-written reason list containing a distinct
On Watch count. Production boards did not look like that: the On Watch sentence
was authored only when the board entered the monitoring/elevated branch, so a
calm board offered exactly two candidates — the generic available-count
sentence and, when nothing was restricted, the fixed
``No relievers are marked Unavailable.`` The selector correctly demoted the
generic one and shipped the constant.

The measured result on the real published corpus (snapshot 411, 30 pages):
7 unique evidence sentences, largest duplicate cluster 14 pages, and seven
Vulnerable clubs whose only published evidence was the zero-constraint
sentence — copy that reads as the opposite of the state it accompanied.

So this file authors its reasons with the REAL ``_health_reasons`` and selects
with the REAL ``_baseball_point``. A fixture that writes its own reason strings
cannot regress-test evidence authorship, which is where the defect lived.

Bounds here are semantic, not a snapshot of one day's league. Nothing asserts a
particular uniqueness count, because diversity is an output of the season, not
a contract — the contract is that a club with a material governed concern never
publishes the zero-constraint sentence as its whole explanation.
"""

from collections import Counter

from services.bullpen_board import (
    HEALTH_ELEVATED,
    HEALTH_MANAGEABLE,
    HEALTH_MONITORING,
    _health_reasons,
)
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.team_story_previews import _baseball_point


ZERO_CONSTRAINT = 'No relievers are marked Unavailable.'


def _counts(available=0, monitor=0, limited=0, avoid=0, unavailable=0):
    return {
        STATUS_AVAILABLE: available,
        STATUS_MONITOR: monitor,
        STATUS_LIMITED: limited,
        STATUS_AVOID: avoid,
        STATUS_UNAVAILABLE: unavailable,
    }


def _board(*, health_state, counts, team_state):
    """A board payload shaped as bullpen_board publishes it.

    ``health_state`` is the board's own health tier; ``team_state`` is the
    published Team State, which comes from the trusted readiness authority and
    is carried here only so a test can group evidence by it. Evidence never
    determines it.
    """
    total = sum(counts.values())
    reasons = _health_reasons(health_state, counts, total)
    return {
        'team_state': team_state,
        'context': {'health': {'state': health_state, 'label': f'{health_state} label', 'reasons': reasons}},
    }


# A league shaped like the real one: mostly calm boards with some arms on watch,
# a few with genuine restrictions, and the meaningful-zero case. Held as raw
# counts so a test can ask what the board KNOWS, independently of what it wrote.
_LEAGUE_SHAPE = (
    (_counts(available=5, monitor=1), 'Stretched'),
    (_counts(available=4, monitor=2), 'Vulnerable'),
    (_counts(available=4, monitor=3), 'Vulnerable'),
    (_counts(available=3, monitor=4), 'Stretched'),
    (_counts(available=3, monitor=5), 'Vulnerable'),
    (_counts(available=4, monitor=2, unavailable=1), 'Stretched'),
    (_counts(available=2, monitor=3, unavailable=2), 'Vulnerable'),
    (_counts(available=2, monitor=1, avoid=1, unavailable=2), 'Vulnerable'),
    (_counts(available=8), 'Fresh'),
)


def _health_state_for(counts):
    """The board tier these counts would land in, for fixture purposes only."""
    restricted = counts[STATUS_AVOID] + counts[STATUS_UNAVAILABLE]
    if restricted >= 2:
        return HEALTH_ELEVATED
    if restricted >= 1:
        return HEALTH_MONITORING
    return HEALTH_MANAGEABLE


def _league():
    return [
        # Calm boards, nothing restricted, differing On Watch pressure. These are
        # the clubs that all shipped the identical constant before.
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=5, monitor=1), team_state='Stretched'),
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=4, monitor=2), team_state='Vulnerable'),
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=4, monitor=3), team_state='Vulnerable'),
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=3, monitor=4), team_state='Stretched'),
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=3, monitor=5), team_state='Vulnerable'),
        # Genuine restrictions.
        _board(health_state=HEALTH_MONITORING, counts=_counts(available=4, monitor=2, unavailable=1), team_state='Stretched'),
        _board(health_state=HEALTH_ELEVATED, counts=_counts(available=2, monitor=3, unavailable=2), team_state='Vulnerable'),
        _board(health_state=HEALTH_ELEVATED, counts=_counts(available=2, monitor=1, avoid=1, unavailable=2), team_state='Vulnerable'),
        # Meaningful zero: nothing restricted AND nothing on watch. The
        # zero-constraint sentence is the honest whole answer here.
        _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=8), team_state='Fresh'),
    ]


def _points(league):
    return [(board['team_state'], _baseball_point(board)) for board in league]


# ── the defect class ────────────────────────────────────────────────────────

def test_a_club_with_on_watch_arms_never_publishes_only_the_zero_constraint():
    """The H-7 defect, stated as an invariant.

    Scoped to clubs that HAVE a material governed concern. The zero-constraint
    sentence stays perfectly valid evidence for a club that genuinely has
    nothing restricted and nothing on watch — this bans it as the whole
    explanation when the board knows something more material.
    """
    for counts, team_state in _LEAGUE_SHAPE:
        # The concern is read from the COUNTS, not from the authored reasons.
        # Deriving it from the text would make this test self-fulfilling: before
        # the fix a calm board authored no On Watch sentence, so a text-based
        # check would have found no concern and passed while the defect stood.
        has_material_concern = (
            counts[STATUS_MONITOR] > 0
            or counts[STATUS_AVOID] > 0
            or counts[STATUS_UNAVAILABLE] > 0
        )
        if not has_material_concern:
            continue
        board = _board(
            health_state=_health_state_for(counts),
            counts=counts,
            team_state=team_state,
        )
        assert _baseball_point(board) != ZERO_CONSTRAINT, (counts, team_state)


def test_vulnerable_clubs_do_not_explain_themselves_with_a_zero_constraint():
    """The worst-reading instance the audit found, pinned directly."""
    for team_state, point in _points(_league()):
        if team_state != 'Vulnerable':
            continue
        assert point != ZERO_CONSTRAINT, (
            'a Vulnerable club published the zero-constraint sentence as its '
            'entire baseball point'
        )


def test_calm_boards_still_author_an_on_watch_count():
    """The authorship fix itself: no longer gated on the monitoring branch."""
    board = _board(
        health_state=HEALTH_MANAGEABLE,
        counts=_counts(available=4, monitor=3),
        team_state='Stretched',
    )
    reasons = board['context']['health']['reasons']

    assert any('On Watch' in reason for reason in reasons)
    assert _baseball_point(board) == 'Three relievers are in the On Watch group.'


def test_a_true_zero_board_still_uses_the_zero_constraint_sentence():
    """Not a global ban: with no concern to state, the constant is the truth."""
    board = _board(
        health_state=HEALTH_MANAGEABLE,
        counts=_counts(available=8),
        team_state='Fresh',
    )

    assert _baseball_point(board) == ZERO_CONSTRAINT


# ── diversity, measured semantically ────────────────────────────────────────

def test_clubs_with_different_evidence_profiles_get_different_sentences():
    """Two genuinely different profiles must be capable of differing."""
    lighter = _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=4, monitor=2), team_state='Stretched')
    heavier = _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=3, monitor=5), team_state='Stretched')

    assert _baseball_point(lighter) != _baseball_point(heavier)


def test_no_single_sentence_dominates_the_league():
    """A soft diversity bound over a fixture built for this contract.

    Deliberately generous: the guard that matters is the semantic one above.
    This exists so a future change that collapses the corpus again fails
    somewhere, even if it keeps every individual invariant technically true.
    """
    points = [point for _state, point in _points(_league())]
    largest = Counter(points).most_common(1)[0][1]

    assert largest / len(points) < 0.4, Counter(points)


def test_identical_evidence_across_states_is_not_a_defect_by_itself():
    """Two clubs with the SAME governed facts should say the same thing.

    Determinism requires it. The audit's finding was never 'duplicates exist';
    it was that duplicates spanned clubs whose evidence genuinely differed.
    """
    a = _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=4, monitor=2), team_state='Stretched')
    b = _board(health_state=HEALTH_MANAGEABLE, counts=_counts(available=4, monitor=2), team_state='Vulnerable')

    assert _baseball_point(a) == _baseball_point(b)


# ── determinism ─────────────────────────────────────────────────────────────

def test_selection_is_byte_identical_across_repeats():
    first = _points(_league())
    second = _points(_league())
    third = _points(_league())

    assert first == second == third


# ── count grammar on the newly-reachable sentence ───────────────────────────

def test_on_watch_count_grammar_covers_zero_one_and_many():
    """The sentence is now authored in cases it never reached before."""
    def point_for(monitor, health_state=HEALTH_MANAGEABLE):
        return _baseball_point(_board(
            health_state=health_state,
            counts=_counts(available=4, monitor=monitor),
            team_state='Stretched',
        ))

    # One: singular noun and verb.
    assert point_for(1) == 'One reliever is in the On Watch group.'
    # Many: plural noun and verb.
    assert point_for(3) == 'Three relievers are in the On Watch group.'

    # Zero on a monitoring board still authors the sentence (unchanged
    # behaviour), and it reads correctly rather than '0 relievers is'.
    zero_reasons = _health_reasons(
        HEALTH_MONITORING, _counts(available=4, monitor=0, unavailable=1), 5
    )
    on_watch = [reason for reason in zero_reasons if 'On Watch' in reason]
    assert on_watch == ['No relievers are in the On Watch group.']

    for broken in ('1 relievers', 'None relievers', '0 relievers is'):
        assert broken not in ' '.join(zero_reasons)
