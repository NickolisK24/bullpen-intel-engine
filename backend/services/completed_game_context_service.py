"""Completed Game Context extraction (COIN Phase 2 foundation).

Derives structured, per-team context from a completed MLB game and *only* the
derived fields — never raw play-by-play. The service is pure and deterministic:
it takes a normalized game payload (assembled elsewhere from boxscore /
linescore / play-by-play) and returns one context dict per team. It makes no
network calls and writes nothing on its own; ``upsert_completed_game_context``
is the optional persistence helper for Phase 3 sync wiring.

Core principle: never invent. If only boxscore data is present the service does
not pretend to know running score or game shape — it returns LOW confidence with
the running-score fields left null. Confidence rises only as far as the supplied
data actually supports:

* LOW    — boxscore only (no running score). Tag is ``insufficient_context``.
* MEDIUM — linescore present (per-inning runs + final). Final score, late runs,
           largest lead, and game shape are derivable; bullpen-handoff score is
           not, so lead-protected/lost stay null.
* HIGH   — play-by-play present (running score per play). Full derivation,
           including the score the bullpen inherited and the turning inning.

Normalized payload contract (all keys optional unless noted):

    {
        'game_pk': int,                 # required
        'game_date': 'YYYY-MM-DD' | date,
        'game_type': str,
        'home': {'team_id': int, 'team_name': str, 'pitchers': [line, ...]},
        'away': {'team_id': int, 'team_name': str, 'pitchers': [line, ...]},
        'linescore': {
            'innings': [{'num': 1, 'home': 0, 'away': 1}, ...],
            'home_runs': int,           # optional totals; summed from innings otherwise
            'away_runs': int,
        },
        'plays': [
            {'inning': 1, 'half': 'top'|'bottom',
             'away_score': int, 'home_score': int, 'pitcher_id': int},
            ...                          # cumulative score AFTER each play, in order
        ],
    }

A pitching ``line`` mirrors a game log row:

    {'player_id': int, 'name': str, 'games_started': 0|1,
     'innings_pitched_outs': int, 'pitches_thrown': int}
"""

from __future__ import annotations

from typing import Any

from services.game_shape import (
    SHAPE_NORMAL_START,
    SHAPE_OPENER_BULK_GAME,
    SHAPE_SHORT_START,
    SHAPE_UNKNOWN,
    classify_game_shape,
)
from utils.games_started import START, games_started_state
from utils.innings import outs_to_decimal_innings
from utils.time import utc_now_naive


# ── Confidence ────────────────────────────────────────────────────────────────
CONFIDENCE_HIGH = 'HIGH'
CONFIDENCE_MEDIUM = 'MEDIUM'
CONFIDENCE_LOW = 'LOW'

# ── Bullpen story tags (plain strings, not a DB enum) ─────────────────────────
TAG_PROTECTED_GAME_SHAPE = 'protected_game_shape'
TAG_LOST_GAME_SHAPE = 'lost_game_shape'
TAG_BULLPEN_KEPT_TEAM_ALIVE = 'bullpen_kept_team_alive'
TAG_BULLPEN_OVEREXPOSED = 'bullpen_overexposed'
TAG_LATE_PRESSURE_ACCUMULATED = 'late_pressure_accumulated'
TAG_STARTER_COVERED_BULLPEN = 'starter_covered_bullpen'
TAG_INSUFFICIENT_CONTEXT = 'insufficient_context'

BULLPEN_STORY_TAGS = frozenset({
    TAG_PROTECTED_GAME_SHAPE,
    TAG_LOST_GAME_SHAPE,
    TAG_BULLPEN_KEPT_TEAM_ALIVE,
    TAG_BULLPEN_OVEREXPOSED,
    TAG_LATE_PRESSURE_ACCUMULATED,
    TAG_STARTER_COVERED_BULLPEN,
    TAG_INSUFFICIENT_CONTEXT,
})

# Shapes that read as a team "creating the game shape it wanted" — a built
# starting structure that the bullpen is then asked to protect.
CREATED_SHAPE_VALUES = frozenset({SHAPE_NORMAL_START, SHAPE_OPENER_BULK_GAME})

# ── Deterministic thresholds (outs-based, mirroring game_shape) ───────────────
NORMAL_START_MIN_OUTS = 15   # 5.0 IP — below this the starter went short
DEEP_START_MIN_OUTS = 18     # 6.0 IP — at/above this the starter went deep
HEAVY_BULLPEN_OUTS = 12      # 4.0 IP — bullpen absorbed a heavy load
LIGHT_BULLPEN_OUTS = 9       # 3.0 IP — bullpen exposure stayed limited
LATE_INNING_START = 7        # innings 7+ are "late"
LATE_INNING_END = 9          # 7-9 window; extras counted only in late_runs_allowed
LATE_PRESSURE_MIN_SCORING_INNINGS = 2


def _value(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pitchers(side: Any) -> list:
    return list(_value(side, 'pitchers', []) or [])


def _line_outs(line: Any) -> int | None:
    return _int_or_none(_value(line, 'innings_pitched_outs'))


def _starter_line(pitchers: list):
    """The single credited starter, or None when ambiguous/absent.

    Conservative by design: openers/bulk games with one credited start resolve
    cleanly, but multiple or missing starts yield None so we never guess a
    starter (and never crash on missing starter data).
    """
    starts = [
        p for p in pitchers
        if games_started_state(_value(p, 'games_started')) == START
    ]
    return starts[0] if len(starts) == 1 else None


def _bullpen_outs(pitchers: list, starter_line) -> int:
    starter_id = _value(starter_line, 'player_id') if starter_line else None
    total = 0
    for p in pitchers:
        if starter_line is not None and _value(p, 'player_id') == starter_id:
            continue
        outs = _line_outs(p)
        if outs is not None:
            total += outs
    return total


# ── Linescore helpers ─────────────────────────────────────────────────────────

def _usable_linescore(linescore) -> bool:
    if not isinstance(linescore, dict):
        return False
    innings = linescore.get('innings')
    if isinstance(innings, list) and innings:
        return True
    return linescore.get('home_runs') is not None and linescore.get('away_runs') is not None


def _linescore_totals(linescore, is_home):
    """Return (for_runs, against_runs) from linescore totals or summed innings."""
    home_total = _int_or_none(linescore.get('home_runs'))
    away_total = _int_or_none(linescore.get('away_runs'))
    if home_total is None or away_total is None:
        home_sum = away_sum = 0
        for inning in linescore.get('innings', []) or []:
            home_sum += _int_or_none(_value(inning, 'home')) or 0
            away_sum += _int_or_none(_value(inning, 'away')) or 0
        if home_total is None:
            home_total = home_sum
        if away_total is None:
            away_total = away_sum
    return (home_total, away_total) if is_home else (away_total, home_total)


def _usable_plays(plays) -> bool:
    return isinstance(plays, list) and len(plays) > 0


def _play_perspective(play, is_home):
    """(for_score, against_score) after this play, from the team's perspective."""
    home = _int_or_none(_value(play, 'home_score')) or 0
    away = _int_or_none(_value(play, 'away_score')) or 0
    return (home, away) if is_home else (away, home)


def _team_on_defense(half, is_home) -> bool:
    # Home team pitches the top half; away team pitches the bottom half.
    half = (half or '').lower()
    return (is_home and half == 'top') or (not is_home and half == 'bottom')


def _empty_context(team_id, game_pk, *, game_date=None, opponent_team_id=None,
                   opponent_name=None, home_away=None, starter_line=None,
                   confidence=CONFIDENCE_LOW):
    """A fail-closed context: identity + starter identity only, everything else null."""
    starter_outs = _line_outs(starter_line) if starter_line else None
    return {
        'team_id': team_id,
        'game_pk': game_pk,
        'game_date': game_date,
        'opponent_team_id': opponent_team_id,
        'opponent_name': opponent_name,
        'home_away': home_away,
        'final_score_for': None,
        'final_score_against': None,
        'starter_player_id': _value(starter_line, 'player_id') if starter_line else None,
        'starter_name': _value(starter_line, 'name') if starter_line else None,
        'starter_ip': outs_to_decimal_innings(starter_outs) if starter_outs is not None else None,
        'starter_pitch_count': _int_or_none(_value(starter_line, 'pitches_thrown')) if starter_line else None,
        'starter_exit_inning': None,
        'starter_exit_score_for': None,
        'starter_exit_score_against': None,
        'bullpen_entry_inning': None,
        'bullpen_entry_score_for': None,
        'bullpen_entry_score_against': None,
        'lead_when_bullpen_entered': None,
        'deficit_when_bullpen_entered': None,
        'largest_lead': None,
        'largest_deficit': None,
        'late_runs_allowed': None,
        'runs_allowed_innings_7_to_9': None,
        'lead_protected': None,
        'lead_lost': None,
        'comeback_completed': None,
        'turning_inning': None,
        'game_shape_created': None,
        'game_shape_protected': None,
        'bullpen_story_tag': TAG_INSUFFICIENT_CONTEXT,
        'confidence': confidence,
        'generated_at': utc_now_naive(),
    }


def _derive_from_plays(plays, is_home, starter_id, team_pitcher_ids):
    """Walk ordered cumulative play scores to derive the running-score context."""
    prev_for = prev_against = 0
    largest_lead = 0
    largest_deficit = 0
    late_runs_allowed = 0
    runs_7_9 = 0
    late_scoring_innings = set()
    starter_exit = None       # (inning, for, against) after the starter's last play
    bullpen_entry = None      # (inning, for_before, against_before)
    last_sign = 0
    turning_inning = None
    final_for = final_against = None

    for play in plays:
        inning = _int_or_none(_value(play, 'inning'))
        half = _value(play, 'half')
        pid = _value(play, 'pitcher_id')
        for_s, against_s = _play_perspective(play, is_home)
        final_for, final_against = for_s, against_s

        margin = for_s - against_s
        largest_lead = max(largest_lead, margin)
        largest_deficit = max(largest_deficit, -margin)

        if _team_on_defense(half, is_home) and pid in team_pitcher_ids:
            runs_this = max(0, against_s - prev_against)
            if inning is not None and inning >= LATE_INNING_START:
                late_runs_allowed += runs_this
                if runs_this > 0:
                    late_scoring_innings.add(inning)
                if inning <= LATE_INNING_END:
                    runs_7_9 += runs_this
            if starter_id is not None and pid == starter_id:
                starter_exit = (inning, for_s, against_s)
            elif bullpen_entry is None:
                bullpen_entry = (inning, prev_for, prev_against)

        sign = (margin > 0) - (margin < 0)
        if sign != 0 and last_sign != 0 and sign != last_sign:
            turning_inning = inning
        if sign != 0:
            last_sign = sign

        prev_for, prev_against = for_s, against_s

    return {
        'final_for': final_for,
        'final_against': final_against,
        'largest_lead': largest_lead,
        'largest_deficit': largest_deficit,
        'late_runs_allowed': late_runs_allowed,
        'runs_7_9': runs_7_9,
        'late_scoring_innings': late_scoring_innings,
        'starter_exit': starter_exit,
        'bullpen_entry': bullpen_entry,
        'turning_inning': turning_inning,
    }


def _derive_from_linescore(linescore, is_home):
    """Inning-resolution derivation: final, largest lead, and late runs allowed."""
    final_for, final_against = _linescore_totals(linescore, is_home)

    cum_for = cum_against = 0
    largest_lead = 0
    largest_deficit = 0
    late_runs_allowed = 0
    runs_7_9 = 0
    late_scoring_innings = set()

    for inning in linescore.get('innings', []) or []:
        num = _int_or_none(_value(inning, 'num'))
        home_runs = _int_or_none(_value(inning, 'home')) or 0
        away_runs = _int_or_none(_value(inning, 'away')) or 0
        for_runs = home_runs if is_home else away_runs
        against_runs = away_runs if is_home else home_runs
        cum_for += for_runs
        cum_against += against_runs
        margin = cum_for - cum_against
        largest_lead = max(largest_lead, margin)
        largest_deficit = max(largest_deficit, -margin)
        if num is not None and num >= LATE_INNING_START:
            late_runs_allowed += against_runs
            if against_runs > 0:
                late_scoring_innings.add(num)
            if num <= LATE_INNING_END:
                runs_7_9 += against_runs

    return {
        'final_for': final_for,
        'final_against': final_against,
        'largest_lead': largest_lead,
        'largest_deficit': largest_deficit,
        'late_runs_allowed': late_runs_allowed,
        'runs_7_9': runs_7_9,
        'late_scoring_innings': late_scoring_innings,
    }


def _classify_tag(ctx, *, starter_outs, bullpen_outs, late_scoring_count,
                  entered_not_ahead):
    """Pick one conservative bullpen story tag. Prefer insufficient over misleading."""
    if ctx['confidence'] == CONFIDENCE_LOW:
        return TAG_INSUFFICIENT_CONTEXT

    created_shape = ctx.get('game_shape_created') in CREATED_SHAPE_VALUES

    if ctx.get('lead_lost') and created_shape:
        return TAG_LOST_GAME_SHAPE
    if ctx.get('lead_protected') and created_shape:
        return TAG_PROTECTED_GAME_SHAPE
    if ctx.get('comeback_completed') and entered_not_ahead and ctx.get('late_runs_allowed') is not None \
            and ctx['late_runs_allowed'] <= 1:
        return TAG_BULLPEN_KEPT_TEAM_ALIVE
    if starter_outs is not None and starter_outs < NORMAL_START_MIN_OUTS \
            and bullpen_outs >= HEAVY_BULLPEN_OUTS:
        return TAG_BULLPEN_OVEREXPOSED
    if late_scoring_count >= LATE_PRESSURE_MIN_SCORING_INNINGS:
        return TAG_LATE_PRESSURE_ACCUMULATED
    if starter_outs is not None and starter_outs >= DEEP_START_MIN_OUTS \
            and bullpen_outs <= LIGHT_BULLPEN_OUTS:
        return TAG_STARTER_COVERED_BULLPEN
    return TAG_INSUFFICIENT_CONTEXT


def _derive_team_context(game, side) -> dict | None:
    game_pk = _int_or_none(_value(game, 'game_pk'))
    side_obj = _value(game, side)
    if game_pk is None or not isinstance(side_obj, dict):
        return None
    team_id = _int_or_none(_value(side_obj, 'team_id'))
    if team_id is None:
        return None

    is_home = side == 'home'
    other = 'away' if is_home else 'home'
    other_obj = _value(game, other) or {}
    game_date = _value(game, 'game_date')
    opponent_team_id = _int_or_none(_value(other_obj, 'team_id'))
    opponent_name = _value(other_obj, 'team_name')
    home_away = 'home' if is_home else 'away'

    pitchers = _pitchers(side_obj)
    starter_line = _starter_line(pitchers)
    starter_id = _value(starter_line, 'player_id') if starter_line else None
    starter_outs = _line_outs(starter_line) if starter_line else None
    bullpen_outs = _bullpen_outs(pitchers, starter_line)
    team_pitcher_ids = {
        _value(p, 'player_id') for p in pitchers if _value(p, 'player_id') is not None
    }

    linescore = _value(game, 'linescore')
    plays = _value(game, 'plays')

    # Boxscore-only → fail closed at LOW. Do not invent running score / shape.
    if not _usable_plays(plays) and not _usable_linescore(linescore):
        return _empty_context(
            team_id, game_pk, game_date=game_date,
            opponent_team_id=opponent_team_id, opponent_name=opponent_name,
            home_away=home_away, starter_line=starter_line,
        )

    ctx = _empty_context(
        team_id, game_pk, game_date=game_date,
        opponent_team_id=opponent_team_id, opponent_name=opponent_name,
        home_away=home_away, starter_line=starter_line,
    )

    if _usable_plays(plays):
        ctx['confidence'] = CONFIDENCE_HIGH
        d = _derive_from_plays(plays, is_home, starter_id, team_pitcher_ids)
        if d['starter_exit'] is not None:
            ctx['starter_exit_inning'] = d['starter_exit'][0]
            ctx['starter_exit_score_for'] = d['starter_exit'][1]
            ctx['starter_exit_score_against'] = d['starter_exit'][2]
        if d['bullpen_entry'] is not None:
            entry_inning, entry_for, entry_against = d['bullpen_entry']
            ctx['bullpen_entry_inning'] = entry_inning
            ctx['bullpen_entry_score_for'] = entry_for
            ctx['bullpen_entry_score_against'] = entry_against
            margin = entry_for - entry_against
            ctx['lead_when_bullpen_entered'] = margin if margin > 0 else None
            ctx['deficit_when_bullpen_entered'] = -margin if margin < 0 else None
        ctx['turning_inning'] = d['turning_inning']
    else:
        ctx['confidence'] = CONFIDENCE_MEDIUM
        d = _derive_from_linescore(linescore, is_home)

    ctx['final_score_for'] = d['final_for']
    ctx['final_score_against'] = d['final_against']
    ctx['largest_lead'] = d['largest_lead']
    ctx['largest_deficit'] = d['largest_deficit']
    ctx['late_runs_allowed'] = d['late_runs_allowed']
    ctx['runs_allowed_innings_7_to_9'] = d['runs_7_9']

    # Game shape is only asserted when running-score context exists.
    shape = classify_game_shape(pitchers).get('shape', SHAPE_UNKNOWN)
    ctx['game_shape_created'] = shape if shape != SHAPE_UNKNOWN else None

    final_for = ctx['final_score_for']
    final_against = ctx['final_score_against']
    won = final_for is not None and final_against is not None and final_for > final_against

    # Outcome reads — tri-state, only asserted when the inputs support them.
    entry_margin = None
    if ctx['bullpen_entry_score_for'] is not None:
        entry_margin = ctx['bullpen_entry_score_for'] - ctx['bullpen_entry_score_against']
    if entry_margin is not None and entry_margin > 0 and final_for is not None:
        ctx['lead_protected'] = bool(won)
        ctx['lead_lost'] = bool(not won)

    if final_for is not None and ctx['largest_deficit'] is not None:
        trailed = ctx['largest_deficit'] > 0 or (entry_margin is not None and entry_margin < 0)
        ctx['comeback_completed'] = bool(won and trailed)

    if ctx['game_shape_created'] in CREATED_SHAPE_VALUES:
        if ctx['lead_protected'] is True:
            ctx['game_shape_protected'] = True
        elif ctx['lead_lost'] is True:
            ctx['game_shape_protected'] = False

    entered_not_ahead = entry_margin is not None and entry_margin <= 0
    ctx['bullpen_story_tag'] = _classify_tag(
        ctx,
        starter_outs=starter_outs,
        bullpen_outs=bullpen_outs,
        late_scoring_count=len(d['late_scoring_innings']),
        entered_not_ahead=entered_not_ahead,
    )
    return ctx


def extract_completed_game_contexts(game) -> list[dict]:
    """Derive one context dict per team from a normalized completed-game payload.

    Returns up to two dicts (home, then away). Fails closed: returns ``[]`` when
    the game identity or both team blocks are missing, and returns a LOW-
    confidence ``insufficient_context`` row when only boxscore data is present.
    Never returns or stores raw play-by-play.
    """
    if not isinstance(game, dict):
        return []
    contexts = []
    for side in ('home', 'away'):
        ctx = _derive_team_context(game, side)
        if ctx is not None:
            contexts.append(ctx)
    return contexts


def upsert_completed_game_context(context: dict):
    """Persist one derived context, keyed by (team_id, game_pk).

    Optional helper for Phase 3 sync wiring — pure extraction above never
    touches the database. Stores only derived fields; the caller is responsible
    for the surrounding session/transaction.
    """
    from models.completed_game_context import CompletedGameContext
    from utils.db import db

    team_id = context.get('team_id')
    game_pk = context.get('game_pk')
    if team_id is None or game_pk is None:
        raise ValueError('completed game context requires team_id and game_pk')

    row = (
        CompletedGameContext.query
        .filter_by(team_id=team_id, game_pk=game_pk)
        .one_or_none()
    )
    if row is None:
        row = CompletedGameContext(team_id=team_id, game_pk=game_pk)
        db.session.add(row)

    for column in CompletedGameContext.DERIVED_COLUMNS:
        if column in context:
            setattr(row, column, context[column])
    return row
