"""Team previews select the evidence that explains the state (H-7).

The board publishes its governed reasons in a fixed order whose first entry is
always the available-count sentence. The preview used to take that first entry,
which produced the audit's observation:

    NYY  Stretched   3 available
    COL  Vulnerable  3 available
    DET  Vulnerable  3 available

An identical available count cannot explain why three clubs sit in different
Team States, so that sentence is weak evidence -- and it is also the one that
carries provenance ("from the latest completed workload data") inside a
baseball claim, which belongs in the dated line instead.

The preview now SELECTS among the reasons the board already authored, most
state-discriminating first. Nothing is composed, no count is recomputed, no new
metric was added, and selection stays deterministic: ties resolve to the
board's own published order.
"""

from services.team_story_previews import _baseball_point


PROVENANCE = 'from the latest completed workload data'


def _board(available=3, monitor=0, unavailable=0, state='Stretched', reasons=None):
    """A board payload shaped exactly like the one bullpen_board publishes."""
    if reasons is None:
        reasons = [
            f'{available} relievers are available {PROVENANCE}.',
            'No relievers are marked Unavailable.'
            if unavailable == 0
            else f'{unavailable} relievers are Unavailable.',
        ]
        if monitor:
            reasons.append(f'{monitor} relievers are in the On Watch group.')
        reasons.append('Availability classifications are workload-based only.')
    return {'context': {'health': {'state': state, 'label': f'{state} label', 'reasons': reasons}}}


# ── the audit's scenario ────────────────────────────────────────────────────

def test_clubs_in_different_states_do_not_share_one_evidence_sentence():
    clubs = (
        ('NYY', 'Stretched', 3, 2, 1),
        ('COL', 'Vulnerable', 3, 4, 3),
        ('DET', 'Vulnerable', 3, 1, 0),
        ('LAD', 'Fresh', 3, 0, 0),
    )
    points = [
        _baseball_point(_board(available=a, monitor=m, unavailable=u, state=s))
        for _, s, a, m, u in clubs
    ]
    assert len(set(points)) == len(points), points


def test_the_generic_available_count_is_not_the_preferred_evidence():
    point = _baseball_point(_board(available=3, monitor=2, unavailable=1))
    assert point == '1 relievers are Unavailable.'


def test_no_preview_sentence_embeds_provenance_when_evidence_exists():
    for monitor, unavailable in ((0, 0), (2, 0), (0, 3), (2, 3)):
        point = _baseball_point(_board(monitor=monitor, unavailable=unavailable))
        assert PROVENANCE not in point, (monitor, unavailable, point)


# ── ranking ─────────────────────────────────────────────────────────────────

def test_a_stated_constraint_outranks_an_on_watch_count():
    assert _baseball_point(_board(monitor=4, unavailable=2)) == '2 relievers are Unavailable.'


def test_on_watch_outranks_the_zero_constraint_line():
    assert _baseball_point(_board(monitor=2, unavailable=0)) == (
        '2 relievers are in the On Watch group.'
    )


def test_a_clean_bullpen_still_gets_its_meaningful_zero():
    """Zero is the evidence when nothing is constrained, so it is stated."""
    assert _baseball_point(_board(monitor=0, unavailable=0)) == (
        'No relievers are marked Unavailable.'
    )


def test_the_methodology_disclosure_never_becomes_the_baseball_point():
    board = _board(reasons=['Availability classifications are workload-based only.'])
    assert _baseball_point(board) == 'Stretched label'


def test_the_available_count_is_still_used_when_it_is_all_there_is():
    board = _board(reasons=[f'5 relievers are available {PROVENANCE}.'])
    assert _baseball_point(board) == f'5 relievers are available {PROVENANCE}.'


# ── fallbacks preserved ─────────────────────────────────────────────────────

def test_falls_back_to_the_governed_health_label():
    assert _baseball_point(_board(reasons=[])) == 'Stretched label'


def test_returns_none_when_the_board_carries_nothing():
    assert _baseball_point({}) is None
    assert _baseball_point(None) is None


# ── determinism ─────────────────────────────────────────────────────────────

def test_selection_is_byte_identical_across_repeats():
    board = _board(available=3, monitor=2, unavailable=1)
    runs = [_baseball_point(board) for _ in range(5)]
    assert len(set(runs)) == 1, runs


def test_equal_rank_reasons_resolve_to_the_boards_published_order():
    board = _board(reasons=[
        '2 relievers are Unavailable.',
        '4 relievers are Unavailable.',
    ])
    assert _baseball_point(board) == '2 relievers are Unavailable.'
