"""Evidence-contract tests for Pregame Story V1 (Tonight's Bullpen Watch).

These guard the contract between the homepage Tonight card and the linked team
bullpen state page. The card is generated from the strict optionality context,
while the team page tags an arm "Clean Option" on AVAILABLE status alone. Without
these guards a card could say "0 clean options" / "almost no clean margin" while
the destination page shows an available, named Clean Option — a trust-breaking
contradiction.

The rules enforced here (see the audit):
  R1 No "0 / no / almost no clean" when the team page exposes any Clean Option.
  R2 No public count drawn from a denominator larger than the active bullpen.
  R3 No public story number that cannot be traced to a visible team-state count.
  R4 Card headline severity must not exceed the team state severity.
  R5 Card and team-state must agree on core counts (the card simply does not
     publish a contradicting arm count).

The Astros-shaped regression (7 relievers, 1 Available Trust Arm/Clean Option,
state Thin) is pinned at the bottom.
"""

import re

from services.tonight_candidate_selection import (
    SIGNAL_NO_CLEAN_MARGIN,
    build_team_tonight_candidate,
    build_tonight_candidates,
)

REF = '2026-06-26'

# Bare arm-count / severity claims that must never reach a public Tonight card.
# Schedule facts ("3 games before the next off day") and workload share
# ("59.2% of recent bullpen workload") are intentionally NOT matched.
_FORBIDDEN_CARD_PATTERNS = (
    r'\bzero\b',
    r'\b(?:almost\s+)?no\s+clean\b',
    r'\bno\s+practical\b',
    r'\bonly\s+one\s+clean\b',
    r'\b\d+\s+clean\b',
    r'\b\d+\s+practical\s+close-game\b',
    r'\b\d+\s+rested(?:-enough)?\b',
    r'\b\d+\s+limited\b',
)

# Headline severity tiers. The team state "Thin" sits at tier 1; a card may not
# exceed the linked team state's tier.
_SEVERITY_TIER = {
    'thin': 1,
    'limited': 1,
    'narrow': 1,
}
_OVERCLAIM_SEVERITY = ('almost no', 'no clean', 'zero')


def _sc(team_id=116, *, playing=True, days_until=3, games_until=3, games_next3=3,
        is_last_before_off=False):
    return {
        'team_id': team_id, 'reference_date': REF, 'context_available': True,
        'is_playing_today': playing, 'opponent_today': 'Minnesota Twins',
        'opponent_team_id_today': 142, 'home_away_today': 'home',
        'game_time_today': '2026-06-26T23:10:00Z', 'doubleheader_today': False,
        'games_today_count': 1 if playing else 0,
        'games_played_last_3_days': 3, 'games_played_last_5_days': 5,
        'games_in_next_3_days': games_next3, 'next_off_day': '2026-06-30',
        'days_until_next_off_day': days_until, 'games_until_next_off_day': games_until,
        'is_first_game_after_off_day': False,
        'is_last_game_before_off_day': is_last_before_off,
        'consecutive_games_played_entering_today': 3,
        'consecutive_games_scheduled_from_today': 4, 'limitations': [],
    }


def _pen(*, clean=0, band='thin', paths=1, available=1, monitor=2, limited=3,
         restricted=4, conc='normal', share=30.0, name='Houston Astros'):
    return {
        'context_available': True, 'clean_options_count': clean,
        'optionality_band': band, 'practical_close_game_paths_count': paths,
        'available_arms_count': available, 'monitor_arms_count': monitor,
        'limited_arms_count': limited, 'restricted_arms_count': restricted,
        'concentration_band': conc, 'top_three_workload_share_10d': share,
        'team_name': name,
    }


def _builder(pen_by_team):
    return lambda team_id, reference_date: pen_by_team.get(team_id)


def _card_text(card):
    # Include the structured pregame_story (key_note, why_it_matters, etc.) so the
    # contract scan covers every public sentence a reader actually sees, not just
    # the headline/summary/evidence — the original "13 limited by recent work" /
    # "0 rested-enough arms" leak lived in the pregame_story key_note.
    story = card.get('pregame_story') or {}
    return ' '.join([
        card['headline'], card['summary'], *card['evidence'],
        *[str(value) for value in story.values()],
    ]).lower()


def _assert_card_is_contract_safe(card, team_state):
    """A single card must not contradict the linked team-state payload."""
    text = _card_text(card)

    # R2/R3: no forbidden bare arm-count or absolute-severity claim.
    for pattern in _FORBIDDEN_CARD_PATTERNS:
        assert not re.search(pattern, text), (pattern, card['signal_type'], text)

    # R1: never claim no/zero clean options when the team page exposes one.
    if team_state['clean_option_names']:
        for phrase in _OVERCLAIM_SEVERITY:
            assert phrase not in text, (phrase, card['signal_type'], text)

    # R4: headline severity may not exceed the team state severity.
    headline = card['headline'].lower()
    assert not any(phrase in headline for phrase in _OVERCLAIM_SEVERITY), headline
    team_tier = _SEVERITY_TIER.get(team_state['state'].lower(), 1)
    card_tier = max(
        (tier for word, tier in _SEVERITY_TIER.items() if word in headline),
        default=1,
    )
    assert card_tier <= team_tier, (card_tier, team_tier, headline)


# ── R1 / R4: no-zero-vs-named and severity ceiling ────────────────────────────

def test_no_clean_margin_does_not_overclaim_when_an_arm_is_available():
    # Strict clean count is 0, but one arm is AVAILABLE -> the team page would tag
    # it a Clean Option. The card must stay "thin", not "almost no".
    card = build_team_tonight_candidate(
        116, REF,
        schedule_context=_sc(116, days_until=1, games_until=1),
        bullpen_context=_pen(clean=0, band='thin', paths=1, available=1))
    assert card is not None
    team_state = {'state': 'Thin', 'clean_option_names': ['Nate Pearson'],
                  'available': 1, 'monitor': 2, 'limited': 3, 'avoid': 1,
                  'unavailable': 0, 'reliever_total': 7}
    _assert_card_is_contract_safe(card, team_state)
    assert card['headline'] == 'Thin late-game margin tonight'


# ── R2 / R3: every signal family stays contract-safe ──────────────────────────

def test_all_tonight_signals_are_contract_safe():
    schedule = [
        _sc(116, days_until=6, games_until=6),                       # schedule pressure
        _sc(118, days_until=1, games_until=1),                       # late-game path
        _sc(120, games_next3=3, days_until=4, games_until=4),        # workload pressure
        _sc(122, is_last_before_off=True, days_until=1, games_until=1),  # off-day relief
    ]
    pens = {
        116: _pen(clean=0, band='thin', paths=1, available=1, name='Detroit Tigers'),
        118: _pen(clean=0, band='thin', paths=0, available=1, name='Chicago Cubs'),
        120: _pen(clean=3, band='flexible', paths=4, available=3, conc='narrow',
                  share=58.0, name='Colorado Rockies'),
        122: _pen(clean=2, band='narrow', paths=2, available=2, name='Atlanta Braves'),
    }
    cards = build_tonight_candidates(REF, limit=6, schedule_contexts=schedule,
                                     bullpen_context_builder=_builder(pens))
    assert cards
    team_state = {'state': 'Thin', 'clean_option_names': ['some arm'],
                  'available': 1, 'monitor': 2, 'limited': 3, 'avoid': 1,
                  'unavailable': 0, 'reliever_total': 7}
    for card in cards:
        _assert_card_is_contract_safe(card, team_state)


def test_card_never_publishes_a_wider_pool_limited_count():
    # Even with a large restricted/limited tally in the (active-bullpen) context,
    # the card must not surface a bare "<n> limited" / "<n> rested" claim that a
    # reader cannot trace on the destination page. Guards against the historical
    # "13 limited by recent work" leak.
    card = build_team_tonight_candidate(
        116, REF,
        schedule_context=_sc(116, days_until=1, games_until=1),
        bullpen_context=_pen(clean=0, band='thin', paths=0, available=1,
                             limited=13, restricted=13))
    text = _card_text(card)
    assert not re.search(r'\b\d+\s+limited\b', text), text
    assert not re.search(r'\b13\b', text), text


# ── Astros-shaped regression ──────────────────────────────────────────────────

def test_astros_shaped_case_does_not_contradict_team_page():
    # 7 relievers, 1 Available (Trust Arm/Clean Option), 2 Monitor, 3 Limited,
    # 1 Avoid, 0 Unavailable, state Thin. The strict clean count is 0.
    card = build_team_tonight_candidate(
        117, REF,
        schedule_context=_sc(117, days_until=1, games_until=1),
        bullpen_context=_pen(clean=0, band='thin', paths=1, available=1, monitor=2,
                             limited=3, restricted=4, name='Houston Astros'))
    assert card is not None
    assert card['signal_type'] == SIGNAL_NO_CLEAN_MARGIN
    text = _card_text(card)
    # The exact failures observed in production must not recur.
    assert 'almost no clean margin' not in text
    assert '0 clean' not in text and 'no clean' not in text
    assert '13 limited' not in text
    assert '0 rested' not in text and '0 practical' not in text
    assert card['headline'] == 'Thin late-game margin tonight'
    assert card['team_name'] == 'Houston Astros'
    assert card['team_name'] not in card['headline']    # team name stays off prose
    assert card['team_name'] not in card['summary']
