"""Starter-assignment sentence for one completed team-game.

Derives at most one fact-backed lead sentence explaining why the credited
starter's assignment was uncommon — for example a first start in several
weeks behind a run of relief outings. Every claim is bounded to stored
game-log rows from the same regular season; anything those rows cannot
prove is omitted. Career-level and club-level claims are out of scope:
stored history begins with the seeded seasons and game logs carry no team
attribution, so neither claim is provable here.
"""

from datetime import date

from sqlalchemy import desc

from models.game_log import GameLog
from utils.games_started import RELIEF, START, games_started_state


# Thresholds are deliberately conservative so ordinary assignments stay
# silent: a prior-start gap of fourteen-plus days, a relief run of
# three-plus outings behind it, and five-plus relief outings before a
# first start of the season.
MIN_DAYS_SINCE_PREVIOUS_START = 14
MIN_CONSECUTIVE_RELIEF_APPEARANCES = 3
FIRST_SEASON_START_MIN_RELIEF_APPEARANCES = 5

NARRATIVE_FIRST_START_IN_DAYS = 'first_start_in_days_after_relief_run'
NARRATIVE_FIRST_SEASON_START = 'first_start_of_season_after_relief'

REGULAR_SEASON_GAME_TYPE = 'R'


def build_starter_assignment_context(starter_log, pitcher):
    """Fetch same-season history for the credited starter and derive."""
    target_date = getattr(starter_log, 'game_date', None)
    target_game_pk = getattr(starter_log, 'mlb_game_pk', None)
    pitcher_id = getattr(starter_log, 'pitcher_id', None)
    if target_date is None or target_game_pk is None or pitcher_id is None:
        return None
    if _game_type(starter_log) != REGULAR_SEASON_GAME_TYPE:
        return None

    season_opening = date(target_date.year, 1, 1)
    history_rows = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_type == REGULAR_SEASON_GAME_TYPE,
            GameLog.game_date >= season_opening,
            GameLog.game_date <= target_date,
        )
        .order_by(desc(GameLog.game_date), desc(GameLog.mlb_game_pk))
        .all()
    )
    return derive_starter_assignment_context(starter_log, pitcher, history_rows)


def derive_starter_assignment_context(starter_log, pitcher, history_rows):
    """Pure derivation over already-fetched same-season rows.

    Fails closed to ``None`` whenever the rows cannot prove a claim: a
    missing date or game id anywhere in the history, an unknown
    start/relief flag inside the sequence, or numbers below the
    conservative thresholds above.
    """
    target_date = getattr(starter_log, 'game_date', None)
    target_game_pk = getattr(starter_log, 'mlb_game_pk', None)
    if target_date is None or target_game_pk is None:
        return None
    if _game_type(starter_log) != REGULAR_SEASON_GAME_TYPE:
        return None
    name = getattr(pitcher, 'full_name', None)
    if not name:
        return None

    prior = []
    seen_game_pks = set()
    for row in history_rows or []:
        row_date = getattr(row, 'game_date', None)
        row_game_pk = getattr(row, 'mlb_game_pk', None)
        if row_date is None or row_game_pk is None:
            return None
        if row_game_pk in seen_game_pks or row_game_pk == target_game_pk:
            continue
        seen_game_pks.add(row_game_pk)
        if row_date > target_date:
            continue
        if row_date == target_date and row_game_pk > target_game_pk:
            continue
        prior.append((row_date, row_game_pk, row))
    prior.sort(key=lambda item: (item[0], item[1]), reverse=True)

    consecutive_relief = 0
    previous_start_date = None
    for row_date, _row_game_pk, row in prior:
        state = _start_relief_state(row)
        if state == START:
            previous_start_date = row_date
            break
        if state == RELIEF:
            consecutive_relief += 1
            continue
        return None

    if previous_start_date is not None:
        days_since_previous_start = (target_date - previous_start_date).days
        if days_since_previous_start < MIN_DAYS_SINCE_PREVIOUS_START:
            return None
        if consecutive_relief < MIN_CONSECUTIVE_RELIEF_APPEARANCES:
            return None
        return {
            'narrative_type': NARRATIVE_FIRST_START_IN_DAYS,
            'sentence': (
                f'{name} made his first start in {days_since_previous_start} '
                f'days after {consecutive_relief} consecutive '
                f'{_relief_appearance_word(consecutive_relief)}.'
            ),
            'previous_start_date': previous_start_date.isoformat(),
            'days_since_previous_start': days_since_previous_start,
            'consecutive_relief_appearances': consecutive_relief,
        }

    if consecutive_relief < FIRST_SEASON_START_MIN_RELIEF_APPEARANCES:
        return None
    return {
        'narrative_type': NARRATIVE_FIRST_SEASON_START,
        'sentence': (
            f'{name} made his first start of the season after '
            f'{consecutive_relief} {_relief_appearance_word(consecutive_relief)}.'
        ),
        'previous_start_date': None,
        'days_since_previous_start': None,
        'consecutive_relief_appearances': consecutive_relief,
    }


def _game_type(log):
    return getattr(log, 'game_type', None) or REGULAR_SEASON_GAME_TYPE


def _start_relief_state(log):
    try:
        return games_started_state(getattr(log, 'games_started', None))
    except Exception:
        # A malformed flag never counts as a start or a relief outing.
        return 'unknown'


def _relief_appearance_word(count):
    return 'relief appearance' if count == 1 else 'relief appearances'
