"""Tonight v1: a game-oriented projection of one trusted Team Board publication.

Tonight is not a second bullpen engine. Every bullpen fact on a game card is
read from the frozen ``trusted_team_boards`` package of ONE trusted Dashboard
snapshot, through the same validators the Team Board serving path uses:

    Team State      team_board_snapshot_team_state.receipt_value
    rest            rest_status carrier            (_frozen_rest_status_for_view)
    workload_7d     workload overview window_7     (_frozen_workload_overview_for_view)
    3-in-4 count    recent_usage_rest arm facts    (_frozen_recent_usage_rest_for_view)
    key arms        Active Bullpen arms + public_role_read (team_board_v2._active_arms)
    rotation        frozen rotation impact         (_frozen_rotation_impact_for_view)

Schedule identity comes from ``slate_games`` for ``game_date_et`` equal to the
publication's availability reference date, which is the date of the games
that publication describes before first pitch.

The builder reads no FatigueScore, GameLog, live roster or legacy
``bullpen_context``. Each game's ``context`` sentence (TN-04) is authored from
the two frozen TeamSides only, by ``build_matchup_context``. ``league_changes``
(TN-05) aggregates each team's frozen Team Board What Changed events from the
same snapshot, by ``build_league_changes``; it never detects a change itself.
Featured games (TN-06) are selected from those frozen facts by fixed rule
priority, by ``select_featured_games``. The lead is present and empty.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import re
import json
import logging
from typing import Any, Mapping

from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import bullpen_board
from services import public_serving_authority as psa
from services import team_board_v2
from services.editorial_voice_contract_v1 import find_editorial_violations
from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from services.team_board_snapshot_team_state import receipt_value
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

CONTRACT = 'tonight_v1'

STATE_SCHEDULED = 'scheduled'
STATE_LIVE = 'live'
STATE_FINAL = 'final'
STATE_POSTPONED = 'postponed'
STATE_SUSPENDED = 'suspended'
STATE_UNCERTAIN = 'uncertain'
GAME_STATES = (
    STATE_SCHEDULED, STATE_LIVE, STATE_FINAL,
    STATE_POSTPONED, STATE_SUSPENDED, STATE_UNCERTAIN,
)
TEAM_STATE_BUCKETS = ('fresh', 'stretched', 'vulnerable', 'withheld')

KEY_ARM_ROLE_ORDER = ('trust_arm', 'bridge_arm')
KEY_ARM_LIMIT = 3
PATTERN_BACK_TO_BACK = 'B2B'
PATTERN_THREE_IN_FOUR = '3-in-4'

EVIDENCE_WITHHELD = 'withheld'
FACT_COMPLETE = 'complete'
WORKLOAD_STATUS_ORDER = ('unavailable', 'unknown', 'partial', FACT_COMPLETE)

REASON_TEAM_PACKAGE_UNAVAILABLE = 'team_board_package_unavailable'
REASON_TEAM_STATE_RECEIPT_UNAVAILABLE = 'team_state_receipt_unavailable'
REASON_REST_UNAVAILABLE = 'rest_status_unavailable'
REASON_WORKLOAD_UNAVAILABLE = 'workload_overview_unavailable'
REASON_USAGE_INCOMPLETE = 'recent_usage_incomplete'
REASON_TIME_UNCONFIRMED = 'first_pitch_time_unconfirmed'
REASON_NONCANONICAL_GAME = 'noncanonical_team_game_excluded'
REASON_TEAM_BOARD_PACKAGE_MISSING = 'trusted_team_board_package_missing'

# TN-04 matchup context. One primary reason per game, chosen by fixed priority.
CONTEXT_TEAM_STATE_VULNERABLE = 'team_state_vulnerable'
CONTEXT_BACK_TO_BACK = 'back_to_back_pressure'
CONTEXT_THREE_IN_FOUR = 'three_in_four_pressure'
CONTEXT_SHORT_START = 'short_start_transfer'
CONTEXT_TEAM_STATE_CONTRAST = 'team_state_contrast'
CONTEXT_RESTED_ARMS = 'rested_arm_snapshot'
CONTEXT_PRIORITY = (
    CONTEXT_TEAM_STATE_VULNERABLE,
    CONTEXT_BACK_TO_BACK,
    CONTEXT_THREE_IN_FOUR,
    CONTEXT_SHORT_START,
    CONTEXT_TEAM_STATE_CONTRAST,
    CONTEXT_RESTED_ARMS,
)
# Serving presentation markers: the sentence is pregame context once a game is
# underway, and is hidden once the game is over or off.
CONTEXT_PREGAME = 'pregame_context'
CONTEXT_PREGAME_HIDDEN = 'pregame_context_hidden'
_CONTEXT_MARKERS = (CONTEXT_PREGAME, CONTEXT_PREGAME_HIDDEN)

EVIDENCE_COMPLETE = FACT_COMPLETE
EVIDENCE_PARTIAL = 'partial'
EVIDENCE_UNAVAILABLE = 'unavailable'
BACK_TO_BACK_CONTEXT_MIN = 2
CONTEXT_SENTENCE_MAX_CHARS = 160
# Descriptive copy only: no prediction, ranking, betting or condition words.
CONTEXT_BANNED_TERMS = (
    'advantage', 'edge', 'favored', 'favorite', 'better spot', 'worse spot',
    'should win', 'likely to win', 'likely', 'will', 'should', 'trouble',
    'danger', 'exploit', 'target', 'fade', 'bet', 'betting', 'fantasy', 'pick',
    'prediction', 'gassed', 'tired', 'exhausted',
)

# TN-05 league What Changed. Canonical TB-09 event types, in product priority.
# ``four_in_six_started`` and any other type are not Tonight change classes.
LEAGUE_CHANGE_PRIORITY = (
    'team_state_changed',
    'active_bullpen_joined',
    'active_bullpen_left',
    'verified_transaction',
    'back_to_back_started',
    'three_in_four_started',
    'high_pitch_outing_started',
    'new_short_start',
)
# Joined and left share one class rank: membership.
_LEAGUE_CHANGE_RANK = {
    'team_state_changed': 1,
    'active_bullpen_joined': 2,
    'active_bullpen_left': 2,
    'verified_transaction': 3,
    'back_to_back_started': 4,
    'three_in_four_started': 5,
    'high_pitch_outing_started': 6,
    'new_short_start': 7,
}
LEAGUE_CHANGES_PER_TEAM = 2
LEAGUE_CHANGES_TOTAL = 12
LEAGUE_CHANGE_ID_VERSION = 'tonight_league_change_v1'
LEAGUE_CHANGE_BANNED_TERMS = (
    'advantage', 'edge', 'favorite', 'favored', 'likely', 'will', 'should win',
    'target', 'fade', 'bet', 'betting', 'fantasy', 'pick', 'prediction',
    'gassed', 'exhausted', 'hurt', 'injured',
)
# A verified transaction may state an injured-list move factually.
_TRANSACTION_ALLOWED_TERMS = frozenset({'injured', 'hurt'})
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# TN-06 featured games: fixed rule priority over frozen facts. Not a score.
FEATURED_VULNERABLE_TEAM = 'vulnerable_team'
FEATURED_TEAM_STATE_CHANGE = 'team_state_change'
FEATURED_MULTIPLE_BACK_TO_BACK = 'multiple_back_to_back_arms'
FEATURED_THREE_IN_FOUR = 'three_in_four_pressure'
FEATURED_SHORT_START = 'short_start_transfer'
FEATURED_MEMBERSHIP_CHANGE = 'bullpen_membership_change'
FEATURED_RULE_PRIORITY = (
    FEATURED_VULNERABLE_TEAM,
    FEATURED_TEAM_STATE_CHANGE,
    FEATURED_MULTIPLE_BACK_TO_BACK,
    FEATURED_THREE_IN_FOUR,
    FEATURED_SHORT_START,
    FEATURED_MEMBERSHIP_CHANGE,
)
FEATURED_MAX = 4
# Selection is frozen at publication; only a game not yet underway is eligible.
FEATURED_ELIGIBLE_STATES = frozenset({'scheduled', 'uncertain'})

_CLUBS_BY_ID = {club.team_id: club for club in MLB_CLUBS}
_CANONICAL_TEAM_IDS = frozenset(MLB_TEAM_IDS)


class TonightPublicationConflict(RuntimeError):
    """The same publication identity was rebuilt with different content."""


# ── Pure builder ─────────────────────────────────────────────────────────────

def build_tonight_v1(snapshot, slate_games, *, generated_at):
    """Project one trusted snapshot plus its slate into the tonight_v1 payload.

    ``slate_games`` must already be the slate for this publication's baseball
    date. Performs no database reads: every input is the snapshot object and
    the slate rows passed in.
    """
    package = _team_board_package(snapshot)
    baseball_date = _iso(getattr(snapshot, 'availability_reference_date', None))
    limitations = []
    if package is None:
        limitations.append(REASON_TEAM_BOARD_PACKAGE_MISSING)

    sides = {}
    games = []
    excluded = 0
    for row in slate_games or ():
        away_id = _int(getattr(row, 'away_team_id', None))
        home_id = _int(getattr(row, 'home_team_id', None))
        if away_id not in _CANONICAL_TEAM_IDS or home_id not in _CANONICAL_TEAM_IDS:
            excluded += 1
            continue
        for team_id in (away_id, home_id):
            if team_id not in sides:
                sides[team_id] = _team_side(snapshot, package, team_id)
        games.append(_game_card(row, sides[away_id], sides[home_id]))
    if excluded:
        limitations.append(REASON_NONCANONICAL_GAME)
    for side in sides.values():
        if side['available'] is not True:
            limitations.append(side['reason_code'])

    games.sort(key=_game_order)
    league_changes = build_league_changes(_frozen_what_changed_by_team(snapshot, package))
    attach_change_refs(sides.values(), league_changes)
    featured_game_pks = apply_featured_games(games, league_changes)
    return {
        'contract': CONTRACT,
        'edition': {
            'baseball_date': baseball_date,
            'data_through': _iso(getattr(snapshot, 'data_through', None)),
            'availability_reference_date': baseball_date,
            'generated_at': _iso(generated_at),
            'publication': {
                'dashboard_snapshot_id': getattr(snapshot, 'id', None),
                'sync_run_id': getattr(snapshot, 'sync_run_id', None),
                'team_board_package_contract': (
                    package.get('contract') if isinstance(package, Mapping) else None
                ),
            },
            'schedule_as_of': _schedule_as_of(slate_games),
        },
        'summary': _summary(games, sides, league_changes),
        # Authored by later packages; present and empty so the contract is stable.
        'lead': None,
        'featured_game_pks': featured_game_pks,
        'games': games,
        'league_changes': league_changes,
        # Temporary contract: a day with no games. Semantic quiet-day rules
        # arrive with lead, featured, and change selection.
        'quiet_day': len(games) == 0,
        'limitations': _dedupe(limitations),
    }


def _team_board_package(snapshot):
    payload = getattr(snapshot, 'payload', None)
    package = payload.get(psa.TEAM_BOARD_PACKAGE_KEY) if isinstance(payload, Mapping) else None
    if (
        not isinstance(package, Mapping)
        or package.get('contract') != psa.TEAM_BOARD_PACKAGE_CONTRACT
        or not isinstance(package.get('by_team_id'), Mapping)
    ):
        return None
    return package


def _team_side(snapshot, package, team_id):
    club = _CLUBS_BY_ID[team_id]
    team_package = (
        package['by_team_id'].get(str(team_id)) if package is not None else None
    )
    if not isinstance(team_package, Mapping):
        return _unavailable_side(club, REASON_TEAM_PACKAGE_UNAVAILABLE)

    identity = team_package.get('team') if isinstance(team_package.get('team'), Mapping) else {}
    arms = _active_arms(team_package)
    usage = psa._frozen_recent_usage_rest_for_view(snapshot, team_package)
    usage_by_pitcher = _usage_by_pitcher(usage)
    rest = _rest(psa._frozen_rest_status_for_view(snapshot, team_package))
    workload = _workload_7d(psa._frozen_workload_overview_for_view(snapshot, team_package))
    return {
        'team_id': team_id,
        'abbreviation': identity.get('team_abbreviation') or club.abbreviation,
        'name': identity.get('team_name') or club.team_name,
        'available': True,
        'reason_code': None,
        'team_state': _team_state(snapshot, team_id),
        'rest': rest,
        'multi_day_usage': {
            'three_in_four_count': _three_in_four_count(arms, usage_by_pitcher),
        },
        'workload_7d': workload,
        'key_arms': _key_arms(arms, usage_by_pitcher),
        'rotation': _rotation(
            psa._frozen_rotation_impact_for_view(snapshot, team_package, team_id)
        ),
        'change_refs': [],
    }


def _unavailable_side(club, reason_code):
    return {
        'team_id': club.team_id,
        'abbreviation': club.abbreviation,
        'name': club.team_name,
        'available': False,
        'reason_code': reason_code,
        'team_state': _withheld_team_state(reason_code),
        'rest': _rest(None),
        'multi_day_usage': {'three_in_four_count': None},
        'workload_7d': _workload_7d(None),
        'key_arms': [],
        'rotation': None,
        'change_refs': [],
    }


def _team_state(snapshot, team_id):
    present, value = receipt_value(snapshot, team_id)
    if not present or not isinstance(value, Mapping):
        return _withheld_team_state(REASON_TEAM_STATE_RECEIPT_UNAVAILABLE)
    available = value.get('available') is True
    return {
        'public_state': value.get('public_state') if available else None,
        'public_label': value.get('public_label') if available else None,
        'available': available,
        'reason_code': value.get('reason_code'),
    }


def _withheld_team_state(reason_code):
    return {
        'public_state': None,
        'public_label': None,
        'available': False,
        'reason_code': reason_code,
    }


def _rest(carrier):
    if isinstance(carrier, Mapping) and carrier.get('available') is True:
        return {
            'active_arm_count': carrier.get('active_arm_count'),
            'rested_arm_count': carrier.get('rested_arm_count'),
            'worked_yesterday_count': carrier.get('worked_yesterday_count'),
            'back_to_back_count': carrier.get('back_to_back_count'),
            'available': True,
            'reason_code': None,
        }
    reason = carrier.get('reason_code') if isinstance(carrier, Mapping) else None
    return {
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'available': False,
        'reason_code': reason or REASON_REST_UNAVAILABLE,
    }


def _workload_7d(overview):
    window = None
    if isinstance(overview, Mapping):
        windows = overview.get('windows')
        window = windows.get('window_7') if isinstance(windows, Mapping) else None
    if not isinstance(window, Mapping):
        return {
            'appearances': None,
            'pitches': None,
            'outs': None,
            'status': 'unavailable',
            'reason_codes': [REASON_WORKLOAD_UNAVAILABLE],
        }
    facts = {name: window.get(name) for name in ('appearances', 'pitches', 'outs')}
    statuses = [
        fact.get('status') if isinstance(fact, Mapping) else 'unavailable'
        for fact in facts.values()
    ]
    status = next(
        (value for value in WORKLOAD_STATUS_ORDER if value in statuses),
        'unavailable',
    )
    reasons = []
    for fact in facts.values():
        if isinstance(fact, Mapping):
            reasons.extend(fact.get('reason_codes') or [])
    return {
        **{
            name: (
                fact.get('value')
                if isinstance(fact, Mapping) and fact.get('status') == FACT_COMPLETE
                else None
            )
            for name, fact in facts.items()
        },
        'status': status,
        'reason_codes': _dedupe(reasons),
    }


def _active_arms(team_package):
    """The exact Active Bullpen arm set the Team Board serves for this package."""
    records = psa._records_for_view(team_package, False)
    groups = bullpen_board.group_cards(bullpen_board._board_cards(records))
    return team_board_v2._active_arms({'groups': groups})


def _usage_by_pitcher(usage):
    if not isinstance(usage, Mapping):
        return None
    return {
        item.get('pitcher_id'): item
        for item in usage.get('active_pitchers') or ()
        if isinstance(item, Mapping) and type(item.get('pitcher_id')) is int
    }


def _three_in_four_fact(usage_by_pitcher, pitcher_id):
    if usage_by_pitcher is None:
        return None
    item = usage_by_pitcher.get(pitcher_id)
    fact = item.get('three_in_four') if isinstance(item, Mapping) else None
    if not isinstance(fact, Mapping) or fact.get('status') != FACT_COMPLETE:
        return None
    return fact.get('value') is True


def _three_in_four_count(arms, usage_by_pitcher):
    """Count Active Bullpen arms whose frozen 3-in-4 fact is complete and true.

    Any arm without a complete fact makes the count unknowable, so the count is
    withheld rather than presented as a partial total.
    """
    if usage_by_pitcher is None:
        return None
    total = 0
    for arm in arms:
        value = _three_in_four_fact(usage_by_pitcher, arm.get('pitcher_id'))
        if value is None:
            return None
        total += int(value)
    return total


def _key_arms(arms, usage_by_pitcher):
    """At most three governed trust/bridge arms, in fixed role then name order."""
    eligible = []
    for arm in arms:
        role = arm.get('public_role_read') if isinstance(arm.get('public_role_read'), Mapping) else {}
        key = role.get('key')
        if key not in KEY_ARM_ROLE_ORDER:
            continue
        eligible.append((KEY_ARM_ROLE_ORDER.index(key), str(arm.get('name') or '').casefold(),
                         arm.get('pitcher_id') or 0, arm, role))
    eligible.sort(key=lambda item: item[:3])
    selected = []
    for _order, _name, _pid, arm, role in eligible[:KEY_ARM_LIMIT]:
        workload = arm.get('workload') if isinstance(arm.get('workload'), Mapping) else {}
        if workload.get('back_to_back') is True:
            pattern = PATTERN_BACK_TO_BACK
        elif _three_in_four_fact(usage_by_pitcher, arm.get('pitcher_id')) is True:
            pattern = PATTERN_THREE_IN_FOUR
        else:
            pattern = None
        selected.append({
            'pitcher_id': arm.get('pitcher_id'),
            'name': arm.get('name'),
            'role_key': role.get('key'),
            'role_label': role.get('label'),
            'days_since_last_appearance': workload.get('days_since_last_appearance'),
            'pattern': pattern,
        })
    return selected


def _rotation(carrier):
    """Only meaningful short-start context: at least one short start."""
    if not isinstance(carrier, Mapping) or carrier.get('status') not in ('complete', 'partial'):
        return None
    short_starts = carrier.get('short_start_count')
    if type(short_starts) is not int or short_starts < 1:
        return None
    return {
        'short_start_count': short_starts,
        'bullpen_innings': carrier.get('bullpen_innings'),
        'games_analyzed': carrier.get('games_analyzed'),
        'status': carrier.get('status'),
    }


def game_state(row):
    """The one mapping from slate_games normalization to Tonight game states."""
    normalized = getattr(row, 'normalized_state', None)
    detailed = str(getattr(row, 'status_detailed', None) or '').lower()
    if normalized == SlateGame.STATE_UPCOMING:
        return STATE_SCHEDULED
    if normalized == SlateGame.STATE_LIVE:
        return STATE_LIVE
    if normalized == SlateGame.STATE_COMPLETED:
        return STATE_FINAL
    if normalized == SlateGame.STATE_CANCELLED:
        return STATE_POSTPONED if 'postpon' in detailed else STATE_UNCERTAIN
    if normalized == SlateGame.STATE_UNCERTAIN and 'suspend' in detailed:
        return STATE_SUSPENDED
    return STATE_UNCERTAIN


def _game_card(row, away, home):
    game_pk = _int(getattr(row, 'game_pk', None))
    first_pitch = getattr(row, 'game_time_utc', None)
    state = game_state(row)
    context = build_matchup_context(away, home)
    if first_pitch is None:
        context['reason_codes'].append(REASON_TIME_UNCONFIRMED)
    return {
        'game_pk': game_pk,
        'game_number': _int(getattr(row, 'game_number', None)),
        'first_pitch_utc': _utc_iso(first_pitch),
        'state': state,
        'state_as_of': _utc_iso(getattr(row, 'last_synced', None)),
        'away': away,
        'home': home,
        'context': present_matchup_context(context, state),
        'featured': False,
        'featured_reason_codes': [],
        'links': {
            'away_team_board': _team_board_link(away),
            'home_team_board': _team_board_link(home),
            'matchup': f'/matchup/{game_pk}' if game_pk is not None else None,
        },
    }


# ── Matchup context (TN-04) ──────────────────────────────────────────────────

def build_matchup_context(away, home):
    """One descriptive, deterministic sentence from two frozen TeamSides.

    Pure: no database access and no baseball derivation. The first condition in
    ``CONTEXT_PRIORITY`` that the frozen facts support is rendered from a fixed
    template; nothing is concatenated. A fact whose TeamSide marks it
    unavailable (or ``None``) is never used and never read as zero. Sides are
    always named away first, then home.

    ``evidence_state``:
      complete     a sentence, every fact it and the higher-priority checks read
                   was available;
      partial      a sentence, but it uses a partial rotation fact, or an input
                   of the selected or a higher-priority check was withheld on a
                   side (the sentence is true but may not be the top condition);
      withheld     no sentence: some usable fact exists, but the facts a
                   sentence needs were withheld;
      unavailable  no sentence and no usable fact on either side.
    """
    sides = (away, home)
    checks = (
        (CONTEXT_TEAM_STATE_VULNERABLE, _team_state_fact, _vulnerable_sentence),
        (CONTEXT_BACK_TO_BACK, _back_to_back_fact, _back_to_back_sentence),
        (CONTEXT_THREE_IN_FOUR, _three_in_four_fact_for_side, _three_in_four_sentence),
        (CONTEXT_SHORT_START, _short_start_fact, _short_start_sentence),
        (CONTEXT_TEAM_STATE_CONTRAST, _team_state_fact, _contrast_sentence),
        (CONTEXT_RESTED_ARMS, _rested_fact, _rested_sentence),
    )
    withheld = False
    for reason, fact, render in checks:
        facts = [fact(side) for side in sides]
        if reason != CONTEXT_SHORT_START and any(value is None for value in facts):
            withheld = True
        rendered = render(sides, facts)
        if rendered is None:
            continue
        sentence, partial = rendered
        return {
            'sentence': sentence,
            'reason_codes': [reason],
            'evidence_state': (
                EVIDENCE_PARTIAL if partial or withheld else EVIDENCE_COMPLETE
            ),
        }
    usable = any(
        fact(side) is not None
        for side in sides
        for fact in (_team_state_fact, _back_to_back_fact,
                     _three_in_four_fact_for_side, _short_start_fact, _rested_fact)
    )
    return {
        'sentence': None,
        'reason_codes': [],
        'evidence_state': EVIDENCE_WITHHELD if usable else EVIDENCE_UNAVAILABLE,
    }


def present_matchup_context(context, state):
    """The context as shown for one game state; never mutates ``context``.

    scheduled / uncertain: unchanged. live: the sentence stays, marked
    ``pregame_context``. final / postponed / suspended: the sentence is hidden
    and marked ``pregame_context_hidden``. A hidden sentence stays hidden. Any
    earlier marker is replaced, so presenting a stored context for a new state
    is idempotent. ``evidence_state`` never changes.
    """
    context = context if isinstance(context, Mapping) else {}
    original_codes = list(context.get('reason_codes') or ())
    reason_codes = [code for code in original_codes if code not in _CONTEXT_MARKERS]
    sentence = context.get('sentence')
    if sentence is None:
        # Already hidden (or never authored): stays exactly as it was stored.
        if CONTEXT_PREGAME_HIDDEN in original_codes:
            reason_codes.append(CONTEXT_PREGAME_HIDDEN)
    elif state == STATE_LIVE:
        reason_codes.append(CONTEXT_PREGAME)
    elif state in (STATE_FINAL, STATE_POSTPONED, STATE_SUSPENDED):
        sentence = None
        reason_codes.append(CONTEXT_PREGAME_HIDDEN)
    return {
        'sentence': sentence,
        'reason_codes': reason_codes,
        'evidence_state': context.get('evidence_state'),
    }


def _name(side):
    return side.get('abbreviation') or side.get('name')


def _plural(count, noun):
    return noun if count == 1 else f'{noun}s'


def _team_state_fact(side):
    team_state = side.get('team_state') if side.get('available') else None
    if not isinstance(team_state, Mapping) or team_state.get('available') is not True:
        return None
    if team_state.get('public_state') not in ('fresh', 'stretched', 'vulnerable'):
        return None
    if not team_state.get('public_label'):
        return None
    return (team_state['public_state'], team_state['public_label'])


def _rest_count(side, field):
    rest = side.get('rest') if side.get('available') else None
    if not isinstance(rest, Mapping) or rest.get('available') is not True:
        return None
    value = rest.get(field)
    return value if type(value) is int and value >= 0 else None


def _back_to_back_fact(side):
    return _rest_count(side, 'back_to_back_count')


def _rested_fact(side):
    return _rest_count(side, 'rested_arm_count')


def _three_in_four_fact_for_side(side):
    usage = side.get('multi_day_usage') if side.get('available') else None
    value = usage.get('three_in_four_count') if isinstance(usage, Mapping) else None
    return value if type(value) is int and value >= 0 else None


def _short_start_fact(side):
    rotation = side.get('rotation') if side.get('available') else None
    if not isinstance(rotation, Mapping) or rotation.get('status') not in ('complete', 'partial'):
        return None
    count = rotation.get('short_start_count')
    if type(count) is not int or count < 1:
        return None
    return (count, rotation['status'] == 'partial')


def _vulnerable_sentence(sides, facts):
    flagged = [i for i, fact in enumerate(facts) if fact is not None and fact[0] == 'vulnerable']
    if len(flagged) == 2:
        return (
            f'{_name(sides[0])} and {_name(sides[1])} both enter tonight with '
            f'{facts[0][1]} bullpen states.'
        ), False
    if len(flagged) == 1:
        team, other = flagged[0], 1 - flagged[0]
        sentence = (
            f'{_name(sides[team])} enters tonight with a {facts[team][1]} bullpen state'
        )
        if facts[other] is not None:
            sentence += f', while {_name(sides[other])} is {facts[other][1]}'
        return sentence + '.', False
    return None


def _back_to_back_sentence(sides, facts):
    flagged = [
        i for i, count in enumerate(facts)
        if count is not None and count >= BACK_TO_BACK_CONTEXT_MIN
    ]
    if not flagged:
        return None
    first = flagged[0]
    sentence = (
        f'{_name(sides[first])} has {facts[first]} bullpen arms coming off '
        'back-to-back usage'
    )
    if len(flagged) == 2:
        sentence += f'; {_name(sides[1])} has {facts[1]}'
    return sentence + '.', False


def _three_in_four_sentence(sides, facts):
    flagged = [i for i, count in enumerate(facts) if count is not None and count >= 1]
    if not flagged:
        return None
    first = flagged[0]
    sentence = (
        f'{_name(sides[first])} has {facts[first]} '
        f'{_plural(facts[first], "reliever")} carrying a 3-in-4 workload pattern'
    )
    if len(flagged) == 2:
        sentence += f'; {_name(sides[1])} has {facts[1]}'
    return sentence + '.', False


def _short_start_sentence(sides, facts):
    flagged = [i for i, fact in enumerate(facts) if fact is not None]
    if not flagged:
        return None
    first = flagged[0]
    count = facts[first][0]
    sentence = (
        f"{_name(sides[first])}'s bullpen has absorbed {count} short "
        f"{_plural(count, 'start')} in the recent rotation window"
    )
    if len(flagged) == 2:
        sentence += f"; {_name(sides[1])}'s has absorbed {facts[1][0]}"
    return sentence + '.', any(facts[i][1] for i in flagged)


def _contrast_sentence(sides, facts):
    if facts[0] is None or facts[1] is None or facts[0][0] == facts[1][0]:
        return None
    return (
        f'{_name(sides[0])} is {facts[0][1]} entering tonight; '
        f'{_name(sides[1])} is {facts[1][1]}.'
    ), False


def _rested_sentence(sides, facts):
    if facts[0] is None or facts[1] is None:
        return None
    return (
        f'{_name(sides[0])} has {facts[0]} rested bullpen '
        f'{_plural(facts[0], "arm")}; {_name(sides[1])} has {facts[1]}.'
    ), False


# ── League What Changed (TN-05) ──────────────────────────────────────────────

def _frozen_what_changed_by_team(snapshot, package):
    """Every canonical team's validated TB-09 carrier from this exact snapshot.

    Uses the Team Board serving validator, so a carrier that does not match this
    publication, or holds any malformed event, contributes nothing. Reads only
    the already-loaded package; no query, no predecessor lookup.
    """
    if package is None:
        return {}
    carriers = {}
    for key, team_package in sorted(package['by_team_id'].items()):
        try:
            team_id = int(key)
        except (TypeError, ValueError):
            continue
        if team_id not in _CANONICAL_TEAM_IDS or not isinstance(team_package, Mapping):
            continue
        carrier = psa._frozen_what_changed_for_view(snapshot, team_package, team_id)
        if carrier is None:
            continue
        identity = team_package.get('team') if isinstance(team_package.get('team'), Mapping) else {}
        carriers[team_id] = {
            'abbreviation': identity.get('team_abbreviation') or _CLUBS_BY_ID[team_id].abbreviation,
            'carrier': carrier,
        }
    return carriers


def build_league_changes(carriers_by_team_id, *, max_per_team=LEAGUE_CHANGES_PER_TEAM,
                         max_total=LEAGUE_CHANGES_TOTAL):
    """Aggregate frozen TB-09 events into the bounded league list. Pure.

    ``carriers_by_team_id`` maps a canonical team id to ``{'abbreviation',
    'carrier'}`` where ``carrier`` is that team's validated frozen What Changed.
    This only filters, normalizes, dedupes, orders and caps: every item is one
    frozen event, and nothing is compared or inferred here.
    """
    per_team = []
    for team_id in sorted(carriers_by_team_id):
        entry = carriers_by_team_id[team_id]
        items = _team_league_changes(team_id, entry.get('abbreviation'), entry.get('carrier'))
        items.sort(key=_league_change_order)
        per_team.extend(items[:max_per_team])
    per_team.sort(key=_league_change_order)
    return per_team[:max_total]


def attach_change_refs(sides, league_changes):
    """Point each TeamSide at its own retained league changes, in list order."""
    by_team = {}
    for item in league_changes:
        by_team.setdefault(item['team_id'], []).append(item['change_id'])
    for side in sides:
        side['change_refs'] = list(by_team.get(side.get('team_id'), ()))


def _team_league_changes(team_id, abbreviation, carrier):
    if (
        team_id not in _CANONICAL_TEAM_IDS
        or not isinstance(carrier, Mapping)
        or carrier.get('state') != 'changes'
        or carrier.get('team_id') != team_id
    ):
        return []
    abbreviation = abbreviation or _CLUBS_BY_ID[team_id].abbreviation
    items = []
    seen_ids = set()
    linked_transactions = set()
    events = [event for event in carrier.get('events') or () if isinstance(event, Mapping)]
    for event in events:
        verified = _mapping_or_empty(_mapping_or_empty(event.get('facts')).get('verified_transaction'))
        if event.get('event_type') in ('active_bullpen_joined', 'active_bullpen_left') and verified.get('transaction_id'):
            linked_transactions.add(verified['transaction_id'])
    for event in events:
        item = _league_change(team_id, abbreviation, carrier, event)
        if item is None:
            continue
        transaction_id = _transaction_id(event)
        # One verified move already carried by its membership change is the same event.
        if event.get('event_type') == 'verified_transaction' and transaction_id in linked_transactions:
            continue
        if item['change_id'] in seen_ids:
            continue
        seen_ids.add(item['change_id'])
        items.append(item)
    return items


def _league_change(team_id, abbreviation, carrier, event):
    event_type = event.get('event_type')
    summary = event.get('summary')
    if (
        event_type not in _LEAGUE_CHANGE_RANK
        or event.get('team_id') != team_id
        or event.get('evidence_status') != 'complete'
        or not isinstance(summary, str) or not summary.strip()
    ):
        return None
    if event_type == 'team_state_changed':
        previous, current = event.get('previous_value'), event.get('current_value')
        if not (isinstance(previous, str) and previous and isinstance(current, str) and current):
            return None
        headline, detail = f'{abbreviation} moved from {previous} to {current}.', None
    else:
        headline, detail = _split_summary(summary)
    occurred_on = _iso_date_or_none(event.get('event_date'))
    transaction_id = _transaction_id(event)
    receipt = (
        f"{carrier.get('contract')}:{carrier.get('current_snapshot_id')}:"
        f"{carrier.get('previous_snapshot_id')}:{team_id}"
    )
    identity = [
        LEAGUE_CHANGE_ID_VERSION, receipt, event_type,
        event.get('subject_id'), event.get('event_date'),
        event.get('previous_value'), event.get('current_value'), transaction_id,
    ]
    change_id = hashlib.sha256(
        json.dumps(identity, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()[:24]
    item = {
        'change_id': change_id,
        'team_id': team_id,
        'team_abbreviation': abbreviation,
        'change_class': event_type,
        'headline': headline,
        'detail': detail,
        'occurred_on': occurred_on,
        'evidence_state': event.get('evidence_status'),
        'source_ref': receipt + (f'#transaction:{transaction_id}' if transaction_id else ''),
        'game_pks': _game_pks(event.get('facts')),
    }
    allowed = _TRANSACTION_ALLOWED_TERMS if transaction_id else frozenset()
    terms = tuple(term for term in LEAGUE_CHANGE_BANNED_TERMS if term not in allowed)
    if any(find_editorial_violations(text, terms=terms) for text in (headline, detail) if text):
        return None
    return item


def _split_summary(summary):
    """Frozen TB-09 copy: the first sentence is the headline; a second is detail."""
    text = ' '.join(summary.split())
    head, sep, rest = text.partition('. ')
    if not sep:
        return text, None
    return head + '.', rest or None


def _transaction_id(event):
    facts = _mapping_or_empty(event.get('facts'))
    if event.get('event_type') == 'verified_transaction':
        value = facts.get('transaction_id')
    else:
        value = _mapping_or_empty(facts.get('verified_transaction')).get('transaction_id')
    return value if isinstance(value, (str, int)) and value != '' else None


def _game_pks(facts):
    facts = _mapping_or_empty(facts)
    values = []
    if type(facts.get('mlb_game_pk')) is int:
        values.append(facts['mlb_game_pk'])
    values.extend(value for value in facts.get('game_pks') or () if type(value) is int)
    return sorted(set(values))


def _league_change_order(item):
    occurred = item['occurred_on']
    return (
        _LEAGUE_CHANGE_RANK[item['change_class']],
        # Most recent first; undated after dated within a class.
        occurred is None,
        -date.fromisoformat(occurred).toordinal() if occurred else 0,
        item['team_abbreviation'],
        item['change_id'],
    )


def _iso_date_or_none(value):
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _mapping_or_empty(value):
    return value if isinstance(value, Mapping) else {}


# ── Featured games (TN-06) ───────────────────────────────────────────────────

def featured_reasons_for_game(game, league_changes_by_id):
    """Every featured rule one frozen game card satisfies, in rule priority. Pure.

    Reads only the card's two TeamSides and the retained TN-05 changes their
    ``change_refs`` point to. A withheld or unknown fact never qualifies, and a
    ref that does not resolve to a retained change is ignored. The TN-04
    context is not consulted.
    """
    if not isinstance(game, Mapping) or game.get('state') not in FEATURED_ELIGIBLE_STATES:
        return []
    sides = [game.get(key) for key in ('away', 'home')]
    sides = [side for side in sides if isinstance(side, Mapping)]
    change_classes = {
        league_changes_by_id[ref]['change_class']
        for side in sides for ref in side.get('change_refs') or ()
        if ref in league_changes_by_id
        and league_changes_by_id[ref].get('team_id') == side.get('team_id')
    }
    checks = {
        FEATURED_VULNERABLE_TEAM: any(
            (_team_state_fact(side) or (None,))[0] == 'vulnerable' for side in sides
        ),
        FEATURED_TEAM_STATE_CHANGE: 'team_state_changed' in change_classes,
        FEATURED_MULTIPLE_BACK_TO_BACK: any(
            (_back_to_back_fact(side) or 0) >= BACK_TO_BACK_CONTEXT_MIN for side in sides
        ),
        FEATURED_THREE_IN_FOUR: any(
            (_three_in_four_fact_for_side(side) or 0) >= 1 for side in sides
        ),
        FEATURED_SHORT_START: any(_short_start_fact(side) is not None for side in sides),
        FEATURED_MEMBERSHIP_CHANGE: bool(
            change_classes & {'active_bullpen_joined', 'active_bullpen_left'}
        ),
    }
    return [rule for rule in FEATURED_RULE_PRIORITY if checks[rule]]


def select_featured_games(games, league_changes, *, max_featured=FEATURED_MAX):
    """``[(game_pk, reasons)]`` for at most ``max_featured`` games. Pure.

    Order: the highest-priority rule a game satisfies, then first pitch
    (unknown last), then game_number, then game_pk. No weights or scores.
    """
    by_id = {
        item['change_id']: item for item in league_changes or ()
        if isinstance(item, Mapping) and item.get('change_id')
    }
    candidates = []
    for game in games or ():
        reasons = featured_reasons_for_game(game, by_id)
        if not reasons or type(game.get('game_pk')) is not int:
            continue
        first_pitch = game.get('first_pitch_utc')
        candidates.append((
            FEATURED_RULE_PRIORITY.index(reasons[0]),
            first_pitch is None,
            first_pitch or '',
            game.get('game_number') if type(game.get('game_number')) is int else 0,
            game['game_pk'],
            reasons,
        ))
    candidates.sort(key=lambda item: item[:5])
    return [(item[4], item[5]) for item in candidates[:max_featured]]


def apply_featured_games(games, league_changes, *, max_featured=FEATURED_MAX):
    """Mark the selected cards and return ``featured_game_pks`` in selection order."""
    selected = select_featured_games(games, league_changes, max_featured=max_featured)
    reasons_by_pk = dict(selected)
    for game in games:
        reasons = reasons_by_pk.get(game.get('game_pk'))
        game['featured'] = reasons is not None
        game['featured_reason_codes'] = list(reasons or ())
    return [game_pk for game_pk, _reasons in selected]


def _team_board_link(side):
    abbreviation = side.get('abbreviation')
    return f'/bullpen?view=board&team={abbreviation}' if abbreviation else None


def _game_order(game):
    first_pitch = game['first_pitch_utc']
    return (
        first_pitch is None,
        first_pitch or '',
        game['game_number'] if game['game_number'] is not None else 0,
        game['game_pk'] or 0,
    )


def _summary(games, sides, league_changes=()):
    by_state = {state: 0 for state in GAME_STATES}
    for game in games:
        by_state[game['state']] += 1
    team_states = {bucket: 0 for bucket in TEAM_STATE_BUCKETS}
    back_to_back_clubs = 0
    for side in sides.values():
        state = side['team_state']['public_state'] if side['team_state']['available'] else None
        team_states[state if state in team_states else 'withheld'] += 1
        count = side['rest']['back_to_back_count']
        if side['rest']['available'] and type(count) is int and count > 0:
            back_to_back_clubs += 1
    return {
        'game_count': len(games),
        'games_by_state': by_state,
        'team_state_counts': team_states,
        'clubs_with_back_to_back_arms': back_to_back_clubs,
        'change_count': len(league_changes),
    }


def _schedule_as_of(slate_games):
    stamps = [
        getattr(row, 'last_synced', None) for row in slate_games or ()
        if getattr(row, 'last_synced', None) is not None
    ]
    return _utc_iso(max(stamps)) if stamps else None


# ── Storage ──────────────────────────────────────────────────────────────────

def load_slate_games(baseball_date):
    """The Tonight slate: every slate_games row whose ET game date matches."""
    if baseball_date is None:
        return []
    return (
        SlateGame.query
        .filter(SlateGame.game_date_et == baseball_date)
        .order_by(SlateGame.game_pk)
        .all()
    )


def content_sha256(payload):
    """Hash the payload without its generation timestamp."""
    body = json.loads(json.dumps(payload, sort_keys=True, default=str))
    edition = body.get('edition')
    if isinstance(edition, dict):
        edition.pop('generated_at', None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def generate_tonight_v1_for_snapshot(snapshot, *, generated_at=None):
    """Build and store the tonight_v1 row for one trusted snapshot.

    Returns ``(row, outcome)`` where outcome is ``'created'`` or ``'reused'``.
    A rebuild of the same publication identity with identical content reuses
    the stored row; different content raises ``TonightPublicationConflict``
    and leaves the stored row untouched.
    """
    baseball_date = getattr(snapshot, 'availability_reference_date', None)
    if getattr(snapshot, 'id', None) is None or baseball_date is None:
        raise ValueError('tonight_v1_requires_identified_snapshot')
    if getattr(snapshot, 'data_through', None) is None:
        raise ValueError('tonight_v1_requires_data_through')
    generated_at = generated_at or utc_now_naive()
    payload = build_tonight_v1(
        snapshot, load_slate_games(baseball_date), generated_at=generated_at,
    )
    digest = content_sha256(payload)
    existing = TonightPublication.query.filter_by(
        reference_date=baseball_date,
        dashboard_snapshot_id=snapshot.id,
        contract=CONTRACT,
    ).one_or_none()
    if existing is not None:
        if existing.content_sha256 == digest:
            return existing, 'reused'
        raise TonightPublicationConflict(
            f'tonight_v1 for snapshot {snapshot.id} on {baseball_date} already '
            'exists with different content'
        )
    row = TonightPublication(
        contract=CONTRACT,
        reference_date=baseball_date,
        dashboard_snapshot_id=snapshot.id,
        sync_run_id=getattr(snapshot, 'sync_run_id', None),
        data_through=snapshot.data_through,
        availability_reference_date=baseball_date,
        payload=payload,
        content_sha256=digest,
        generated_at=generated_at,
    )
    db.session.add(row)
    db.session.commit()
    return row, 'created'


def read_tonight_v1(reference_date, dashboard_snapshot_id):
    """The stored tonight_v1 row for one exact publication identity, if any."""
    return TonightPublication.query.filter_by(
        reference_date=reference_date,
        dashboard_snapshot_id=dashboard_snapshot_id,
        contract=CONTRACT,
    ).one_or_none()


def generate_tonight_v1_after_publication(snapshot):
    """Post-publication step: never raises, never touches the publication.

    Returns a small result dict. A failure is logged and reported; the trusted
    Dashboard publication and any earlier tonight_v1 rows are unaffected.
    """
    snapshot_id = getattr(snapshot, 'id', None)
    if _team_board_package(snapshot) is None:
        logger.info(
            'tonight_v1 projection skipped snapshot_id=%s reason=%s',
            snapshot_id, REASON_TEAM_BOARD_PACKAGE_MISSING,
        )
        return {'status': 'skipped', 'reason': REASON_TEAM_BOARD_PACKAGE_MISSING}
    try:
        row, outcome = generate_tonight_v1_for_snapshot(snapshot)
    except Exception as exc:  # noqa: BLE001 - reported, never re-raised
        db.session.rollback()
        logger.exception(
            'tonight_v1 projection failed non-fatally snapshot_id=%s', snapshot_id,
        )
        return {'status': 'failed', 'error': type(exc).__name__}
    logger.info(
        'tonight_v1 projection %s snapshot_id=%s tonight_publication_id=%s game_count=%s',
        outcome, snapshot_id, row.id, (row.payload.get('summary') or {}).get('game_count'),
    )
    return {'status': outcome, 'tonight_publication_id': row.id}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _int(value):
    return value if type(value) is int else None


def _iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _utc_iso(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat() + 'Z'
    return value


def _dedupe(values):
    return list(dict.fromkeys(value for value in values if value))


__all__ = [
    'CONTRACT',
    'GAME_STATES',
    'TonightPublicationConflict',
    'CONTEXT_BANNED_TERMS',
    'CONTEXT_PRIORITY',
    'CONTEXT_SENTENCE_MAX_CHARS',
    'FEATURED_MAX',
    'FEATURED_RULE_PRIORITY',
    'LEAGUE_CHANGE_BANNED_TERMS',
    'LEAGUE_CHANGE_PRIORITY',
    'attach_change_refs',
    'build_league_changes',
    'apply_featured_games',
    'build_matchup_context',
    'featured_reasons_for_game',
    'build_tonight_v1',
    'content_sha256',
    'game_state',
    'generate_tonight_v1_after_publication',
    'generate_tonight_v1_for_snapshot',
    'load_slate_games',
    'present_matchup_context',
    'select_featured_games',
    'read_tonight_v1',
]
