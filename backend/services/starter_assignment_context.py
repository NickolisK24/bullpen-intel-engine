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
from services import pitcher_season_ledger_coverage
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
COVERAGE_STATE_COMPLETE = 'complete'
COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET = 'pitcher_regular_season_through_target'


def build_starter_assignment_context(starter_log, pitcher, *, history_coverage=None):
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
    return derive_starter_assignment_context(
        starter_log,
        pitcher,
        history_rows,
        history_coverage=history_coverage,
    )


def derive_starter_assignment_context(
    starter_log,
    pitcher,
    history_rows,
    *,
    history_coverage=None,
):
    """Pure derivation over already-fetched same-season rows.

    Fails closed to ``None`` whenever the rows cannot prove a claim: missing
    row identity, an unknown start/relief flag, absent pitcher-season source
    counts, or numbers below the conservative thresholds above.
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

    prepared = _prepare_history(
        starter_log,
        pitcher,
        history_rows,
        target_date,
        target_game_pk,
    )
    if prepared is None:
        return None
    if not _has_verified_history_coverage(history_coverage, prepared):
        return None
    prior = prepared['prior']

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


def _prepare_history(starter_log, pitcher, history_rows, target_date, target_game_pk):
    target_state = _start_relief_state(starter_log)
    if target_state != START:
        return None

    counted = {target_game_pk: starter_log}
    prior = []
    for row in history_rows or []:
        row_date = getattr(row, 'game_date', None)
        row_game_pk = getattr(row, 'mlb_game_pk', None)
        if row_date is None or row_game_pk is None:
            return None
        if row_date > target_date:
            continue
        if row_date == target_date and row_game_pk > target_game_pk:
            continue
        if row_game_pk == target_game_pk:
            continue
        if row_game_pk in counted:
            continue
        counted[row_game_pk] = row
        prior.append((row_date, row_game_pk, row))

    starts = 0
    for row in counted.values():
        state = _start_relief_state(row)
        if state == START:
            starts += 1
            continue
        if state == RELIEF:
            continue
        return None

    prior.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return {
        'prior': prior,
        'pitcher_id': getattr(starter_log, 'pitcher_id', None),
        'pitcher_mlb_id': getattr(pitcher, 'mlb_id', None),
        'season': target_date.year,
        'game_type': _game_type(starter_log),
        'target_game_pk': target_game_pk,
        'covered_through_date': target_date.isoformat(),
        'stored_appearance_count': len(counted),
        'stored_games_started_count': starts,
        'stored_manifest_fingerprint': (
            pitcher_season_ledger_coverage.manifest_fingerprint(
                pitcher_season_ledger_coverage.build_stored_manifest_from_rows(
                    counted.values()
                )['entries']
            )
        ),
    }


def _has_verified_history_coverage(history_coverage, prepared):
    if not isinstance(history_coverage, dict):
        return False
    if history_coverage.get('coverage_state') != COVERAGE_STATE_COMPLETE:
        return False
    if (
        history_coverage.get('coverage_scope')
        != COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET
    ):
        return False
    if history_coverage.get('pitcher_id') != prepared['pitcher_id']:
        return False
    if history_coverage.get('pitcher_mlb_id') != prepared['pitcher_mlb_id']:
        return False
    if history_coverage.get('season') != prepared['season']:
        return False
    if history_coverage.get('game_type') != prepared['game_type']:
        return False
    if history_coverage.get('target_game_pk') != prepared['target_game_pk']:
        return False
    if history_coverage.get('covered_through_date') != prepared['covered_through_date']:
        return False

    stored_appearances = prepared['stored_appearance_count']
    stored_starts = prepared['stored_games_started_count']
    stored_fingerprint = prepared['stored_manifest_fingerprint']
    coverage_stored_appearances = _as_nonnegative_int(
        history_coverage.get('stored_appearance_count')
    )
    coverage_source_appearances = _as_nonnegative_int(
        history_coverage.get('source_appearance_count')
    )
    coverage_stored_starts = _as_nonnegative_int(
        history_coverage.get('stored_games_started_count')
    )
    coverage_source_starts = _as_nonnegative_int(
        history_coverage.get('source_games_started_count')
    )
    return (
        coverage_stored_appearances == stored_appearances
        and coverage_source_appearances == stored_appearances
        and coverage_stored_starts == stored_starts
        and coverage_source_starts == stored_starts
        and history_coverage.get('stored_manifest_fingerprint') == stored_fingerprint
        and history_coverage.get('source_manifest_fingerprint') == stored_fingerprint
    )


def _as_nonnegative_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed
