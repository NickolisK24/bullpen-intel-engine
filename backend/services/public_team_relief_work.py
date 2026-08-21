from datetime import date, timedelta

from sqlalchemy import asc, desc, or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import board_freshness
from services import game_shape
from services import pitcher_season_ledger_coverage
from services import starter_assignment_context
from utils.games_started import RELIEF, START, games_started_state


CAPABILITY = 'public_team_relief_work'
RECENT_GAME_DATES_MAX = 5
LOOKBACK_DAYS = 30
WINDOW_DAYS = (7, 14)
WORKLOAD_WINDOWS_METHOD_VERSION = 'public_team_relief_work_windows_v1'
WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION = (
    'public_team_relief_work_windows_public_v1'
)
WORKLOAD_WINDOWS_CARRIER_CONTRACT = 'team_board_workload_windows_carrier_v1'
WORKLOAD_WINDOWS_POPULATION_BASIS = 'official_appearance_team_relief_appearances'
WORKLOAD_WINDOWS_POPULATION_AUTHORITY = 'game_log.appearance_team_id_resolved'
WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY = (
    'historical_appearance_team_not_current_roster'
)
WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY = 'calendar_day_inclusive_through_date_v1'

DEPLOYMENT_PROFILE_WINDOW_DAYS = 14
DEPLOYMENT_PROFILE_METHOD_VERSION = 'public_team_deployment_profile_v1'
DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION = 'public_team_deployment_profile_public_v1'
DEPLOYMENT_PROFILE_CARRIER_CONTRACT = 'team_board_deployment_profile_carrier_v1'
DEPLOYMENT_PROFILE_POPULATION_BASIS = WORKLOAD_WINDOWS_POPULATION_BASIS
DEPLOYMENT_PROFILE_POPULATION_AUTHORITY = WORKLOAD_WINDOWS_POPULATION_AUTHORITY
DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY = WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY
DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY = WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
DEPLOYMENT_PROFILE_MULTI_INNING_MIN_OUTS = 4
DEPLOYMENT_PROFILE_COMPLETE = 'complete'
DEPLOYMENT_PROFILE_WITHHELD = 'withheld'
DEPLOYMENT_PROFILE_DATA_THROUGH_MISSING = 'data_through_missing'

WORKLOAD_WINDOWS_COMPLETE = 'complete'
WORKLOAD_WINDOWS_WITHHELD = 'withheld'
WORKLOAD_WINDOWS_DATA_THROUGH_MISSING = 'data_through_missing'

# Every appearance on this board is owned by the team the pitcher REPRESENTED in
# that game (GameLog.appearance_team_id, Foundation 1), never by the pitcher's
# mutable current Pitcher.team_id. The current team is used only for the
# out-of-band diagnostic disclosure below and for the team's display name.
APPEARANCE_TEAM_RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED

# A game-level narrative is a starter-dependent public claim, so it additionally
# requires official final-game authority for this team side. Missing or
# non-final schedule authority suppresses the narrative; the appearance rows
# beneath it still render.
STARTER_AUTHORITY_OFFICIAL = 'official_completed_game_starter'

# Game-level context qualifier. Both bounds reuse the canonical game-shape
# constants: a credited start of two innings or fewer (6 outs) followed by
# five-plus relief innings (15 outs) qualifies as extended bullpen coverage.
EXTENDED_BULLPEN_COVERAGE_LABEL = 'Extended bullpen coverage'
EXTENDED_COVERAGE_STARTER_MAX_OUTS = game_shape.OPENER_MAX_OUTS
EXTENDED_COVERAGE_RELIEF_MIN_OUTS = game_shape.NORMAL_START_MIN_OUTS

# Shapes with exactly one credited starter and fully classified pitching
# lines. Any other shape (including unknown and no-credited-starter games)
# omits the game context block entirely.
CONTEXT_ELIGIBLE_GAME_SHAPES = (
    game_shape.SHAPE_NORMAL_START,
    game_shape.SHAPE_SHORT_START,
    game_shape.SHAPE_OPENER_BULK_GAME,
)

MONTH_NAMES = (
    None,
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
)


class TeamNotFoundError(LookupError):
    pass


def build_public_team_relief_work_payload(team_id):
    team_pitcher = (
        Pitcher.query
        .filter(Pitcher.team_id == team_id)
        .order_by(asc(Pitcher.id))
        .first()
    )
    if team_pitcher is None:
        raise TeamNotFoundError(team_id)

    freshness = board_freshness.board_freshness_block()
    anchor = _parse_data_through(freshness.get('data_through'))
    payload = {
        'capability': CAPABILITY,
        'team': _team_payload(team_pitcher, team_id),
        'data_through': anchor.isoformat() if anchor else None,
        'freshness': freshness,
        'scope_sentence': _scope_sentence(team_pitcher),
        'relief_by_date': [],
    }

    if anchor is None:
        return payload

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    carrier = _workload_windows_from_rows(rows, anchor)
    deployment = _deployment_profile_from_rows(rows, anchor)
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if _start_relief_state(log) == RELIEF
    ]
    all_rows_by_date = {}
    for log, pitcher in rows:
        all_rows_by_date.setdefault(log.game_date, []).append((log, pitcher))

    payload['relief_by_date'] = _relief_by_date(relief_rows, all_rows_by_date, team_id)
    if not relief_rows:
        payload['absence_sentence'] = (
            f'No relief appearances in the {LOOKBACK_DAYS} days through '
            f'{_month_day(anchor)}.'
        )
    unattributed = _unattributed_appearance_count(team_id, start_date, anchor)
    if unattributed:
        payload['unattributed_appearance_count'] = unattributed
        payload['unattributed_sentence'] = (
            f'Official team attribution is unavailable for {unattributed} '
            f'{_appearance_word(unattributed)} by pitchers on this roster in the '
            f'{LOOKBACK_DAYS} days through {_month_day(anchor)}; those '
            f'{_appearance_word(unattributed)} are not counted here.'
        )
    payload['windows'] = carrier['windows']
    payload['deployment_profile'] = deployment
    return payload


def author_workload_windows(team_id, *, data_through):
    """Author the exact governed 7/14-day public windows for one publication.

    The caller supplies the immutable publication's represented date. This is
    the same canonical calculation used by the public relief-work payload; it
    neither consults the current roster for membership nor reconstructs an old
    publication. A missing represented date freezes an explicit unavailable
    carrier rather than manufacturing zeroes.
    """
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'contract': WORKLOAD_WINDOWS_CARRIER_CONTRACT,
            'status': WORKLOAD_WINDOWS_WITHHELD,
            'reason_code': WORKLOAD_WINDOWS_DATA_THROUGH_MISSING,
            'data_through': None,
            'windows': {},
        }

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    return _workload_windows_from_rows(rows, anchor)


def author_public_team_relief_authority(team_id, *, data_through):
    """Author workload windows and deployment from one bounded row query."""
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'workload_windows': author_workload_windows(
                team_id, data_through=None
            ),
            'deployment_profile': author_deployment_profile(
                team_id, data_through=None
            ),
        }
    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    return {
        'workload_windows': _workload_windows_from_rows(rows, anchor),
        'deployment_profile': _deployment_profile_from_rows(rows, anchor),
    }


def author_deployment_profile(team_id, *, data_through):
    """Author the exact public deployment profile for one publication.

    This is one bounded team/window query, never one query per pitcher.  It
    reuses the same official team-at-appearance relief rows as Recent Relief
    Work and does not infer bullpen job titles or managerial intent.
    """
    anchor = _parse_data_through(data_through)
    if anchor is None:
        return {
            'contract': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
            'status': DEPLOYMENT_PROFILE_WITHHELD,
            'reason_code': DEPLOYMENT_PROFILE_DATA_THROUGH_MISSING,
            'data_through': None,
            'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
            'profiles': [],
            'summary': None,
            'limitations': [],
        }

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    rows = _appearance_rows(team_id, start_date, anchor)
    return _deployment_profile_from_rows(rows, anchor)


def _deployment_profile_from_rows(rows, anchor):
    start = anchor - timedelta(days=DEPLOYMENT_PROFILE_WINDOW_DAYS - 1)
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.game_date >= start and _start_relief_state(log) == RELIEF
    ]
    by_pitcher = {}
    for log, pitcher in relief_rows:
        entry = by_pitcher.setdefault(pitcher.id, {
            'pitcher_id': pitcher.id,
            'pitcher_mlb_id': pitcher.mlb_id,
            'pitcher_name': pitcher.full_name,
            'appearances_analyzed': 0,
            'saves': 0,
            'holds': 0,
            'games_finished': 0,
            'appearances_with_games_finished': 0,
            'multi_inning_appearances': 0,
            'appearances_with_outs': 0,
            'most_recent_multi_inning_date': None,
            'limitations': [],
        })
        entry['appearances_analyzed'] += 1
        entry['saves'] += int(bool(log.save))
        entry['holds'] += int(bool(log.hold))
        if log.games_finished is not None:
            entry['appearances_with_games_finished'] += 1
            entry['games_finished'] += int(log.games_finished == 1)
        outs = _known_outs(log)
        if outs is not None:
            entry['appearances_with_outs'] += 1
            if outs >= DEPLOYMENT_PROFILE_MULTI_INNING_MIN_OUTS:
                entry['multi_inning_appearances'] += 1
                represented = log.game_date.isoformat()
                if (
                    entry['most_recent_multi_inning_date'] is None
                    or represented > entry['most_recent_multi_inning_date']
                ):
                    entry['most_recent_multi_inning_date'] = represented

    profiles = []
    for profile in by_pitcher.values():
        limitations = []
        if profile['appearances_with_outs'] < profile['appearances_analyzed']:
            limitations.append(
                'Multi-inning counts include only appearances with recorded outs.'
            )
        if (
            profile['appearances_with_games_finished']
            < profile['appearances_analyzed']
        ):
            limitations.append(
                'Games-finished counts include only appearances with recorded finish authority.'
            )
        profile['limitations'] = limitations
        name = profile.get('pitcher_name') or 'This pitcher'
        profile['summary'] = (
            f'{name} recorded {profile["saves"]} {_plural(profile["saves"], "save")}, '
            f'{profile["holds"]} {_plural(profile["holds"], "hold")}, and worked '
            f'multiple innings in {profile["multi_inning_appearances"]} of '
            f'{profile["appearances_with_outs"]} relief '
            f'{_plural(profile["appearances_with_outs"], "appearance")} with recorded outs '
            f'during the {DEPLOYMENT_PROFILE_WINDOW_DAYS}-day window.'
        )
        profiles.append(profile)

    profiles.sort(key=lambda item: (
        -item['appearances_analyzed'],
        str(item.get('pitcher_name') or '').lower(),
        item['pitcher_id'],
    ))
    save_hold_pitchers = sum(
        1 for item in profiles if item['saves'] or item['holds']
    )
    multi_inning_pitchers = sum(
        1 for item in profiles if item['multi_inning_appearances']
    )
    summary = (
        f'Over the {DEPLOYMENT_PROFILE_WINDOW_DAYS} days through {_month_day(anchor)}, '
        f'{save_hold_pitchers} {_plural(save_hold_pitchers, "pitcher")} recorded a save or hold and '
        f'{multi_inning_pitchers} {_plural(multi_inning_pitchers, "pitcher")} worked multiple innings.'
    )
    return {
        'contract': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
        'status': DEPLOYMENT_PROFILE_COMPLETE,
        'reason_code': None,
        'data_through': anchor.isoformat(),
        'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
        'population_basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
        'profiles': profiles,
        'team_summary': {
            'represented_arm_count': len(profiles),
            'pitchers_with_save_or_hold': save_hold_pitchers,
            'pitchers_with_multi_inning_appearance': multi_inning_pitchers,
        },
        'summary': summary,
        'limitations': sorted({
            limitation
            for profile in profiles
            for limitation in profile.get('limitations') or []
        }),
    }


def _plural(count, singular):
    return singular if count == 1 else f'{singular}s'


def _workload_windows_from_rows(rows, anchor):
    return {
        'contract': WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': WORKLOAD_WINDOWS_COMPLETE,
        'reason_code': None,
        'data_through': anchor.isoformat(),
        'windows': {
            f'window_{window_days}': _window(rows, anchor, window_days)
            for window_days in WINDOW_DAYS
        },
    }


def _appearance_rows(team_id, start_date, anchor):
    # Scoped by official game-side ownership, not by who is on the roster today.
    # This both keeps another club's game out of this board and keeps this
    # club's own game complete when a pitcher has since left the organization.
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .add_entity(Pitcher)
        .filter(
            GameLog.appearance_team_status == APPEARANCE_TEAM_RESOLVED,
            GameLog.appearance_team_id == team_id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
        )
        .order_by(desc(GameLog.game_date), asc(Pitcher.full_name), asc(GameLog.id))
        .all()
    )


def _start_relief_state(log):
    """Official per-game start signal, never a season pattern or row order."""
    try:
        return games_started_state(getattr(log, 'games_started', None))
    except Exception:
        # A malformed flag never counts as a start or a relief outing.
        return 'unknown'


def _parse_data_through(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _team_payload(pitcher, team_id):
    return {
        'team_id': team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
    }


def _scope_sentence(pitcher):
    club = pitcher.team_abbreviation or pitcher.team_name or ''
    return f'Covers appearances made for {club} per official MLB game records.'


def _unattributed_appearance_count(team_id, start_date, anchor):
    """Out-of-band diagnostic only: never an attribution source.

    Counts in-window appearances by pitchers currently on this roster whose
    official game side is unresolved, so the board can disclose what it left
    out instead of silently under-reporting.
    """
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(
            Pitcher.team_id == team_id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
            or_(
                GameLog.appearance_team_status.is_(None),
                GameLog.appearance_team_status != APPEARANCE_TEAM_RESOLVED,
            ),
        )
        .count()
    )


def _relief_by_date(relief_rows, all_rows_by_date, team_id):
    by_date = {}
    for log, pitcher in relief_rows:
        by_date.setdefault(log.game_date, []).append((log, pitcher))

    groups = []
    for game_date in sorted(by_date, reverse=True)[:RECENT_GAME_DATES_MAX]:
        entries = sorted(
            by_date[game_date],
            key=lambda item: (item[1].full_name or '', item[0].id or 0),
        )
        group = _date_group(game_date, entries)
        if not _group_totals_reconcile(group):
            groups.append(_unavailable_group(game_date))
            continue
        games = [
            block
            for block in _game_context_blocks(
                all_rows_by_date.get(game_date) or [], team_id
            )
            if _block_reconciles_with_appearances(block, group)
        ]
        if games:
            group['games'] = games
        groups.append(group)
    return groups


def _game_context_blocks(date_entries, team_id):
    by_game = {}
    for log, pitcher in date_entries:
        if log.mlb_game_pk is None:
            continue
        by_game.setdefault(log.mlb_game_pk, []).append((log, pitcher))

    final_game_numbers = _final_game_numbers(team_id, by_game.keys())
    blocks = []
    for game_pk in sorted(by_game):
        if game_pk not in final_game_numbers:
            # No official final-game authority for this team side: a
            # starter-dependent narrative cannot be published.
            continue
        block = _game_context_block(game_pk, by_game[game_pk])
        if block is not None:
            block['game_number'] = final_game_numbers[game_pk]
            blocks.append(block)
    blocks.sort(key=_game_sort_key)
    return blocks


def _game_sort_key(entry):
    """Deterministic official ordering: MLB game number, then game_pk.

    A game whose number is unknown sorts after numbered games rather than
    borrowing a position it cannot prove.
    """
    number = entry.get('game_number')
    return (0, number, entry['mlb_game_pk']) if isinstance(number, int) else (
        1, 0, entry['mlb_game_pk']
    )


def _final_game_numbers(team_id, game_pks):
    """Official final-game authority and MLB game number for this team side.

    Returns ``{game_pk: game_number_or_None}`` for the games this team side
    officially completed. ``game_number`` is MLB's own ``gameNumber`` carried by
    the schedule ledger, so a doubleheader's first and second game are told
    apart by official authority rather than by list order.
    """
    wanted = sorted({pk for pk in game_pks if pk is not None})
    if not wanted:
        return {}
    rows = (
        ScheduledGame.query
        .filter(
            ScheduledGame.team_id == team_id,
            ScheduledGame.game_pk.in_(wanted),
        )
        .all()
    )
    return {
        row.game_pk: row.game_number
        for row in rows
        if row.status_state == ScheduledGame.STATE_FINAL
    }


def _game_context_block(game_pk, entries):
    shape_payload = game_shape.classify_game_shape(
        [log for log, _pitcher in entries]
    )
    if shape_payload['shape'] not in CONTEXT_ELIGIBLE_GAME_SHAPES:
        return None

    starters = [
        (log, pitcher)
        for log, pitcher in entries
        if _start_relief_state(log) == START
    ]
    relief = [
        (log, pitcher)
        for log, pitcher in entries
        if _start_relief_state(log) == RELIEF
    ]
    if len(starters) != 1 or not relief:
        return None
    if len(starters) + len(relief) != len(entries):
        # An unclassified line means the official starter set is not provably
        # complete for this team side.
        return None

    starter_log, starter_pitcher = starters[0]
    starter_outs = _known_outs(starter_log)
    relief_outs_each = [_known_outs(log) for log, _pitcher in relief]
    if starter_outs is None or any(outs is None for outs in relief_outs_each):
        return None

    relief_outs = sum(relief_outs_each)
    total_outs = starter_outs + relief_outs
    relief_count = len(relief)
    total_pitchers = 1 + relief_count

    starter_pitches = starter_log.pitches_thrown
    relief_known_pitches = [
        log.pitches_thrown
        for log, _pitcher in relief
        if log.pitches_thrown is not None
    ]
    relief_pitches = (
        sum(relief_known_pitches)
        if len(relief_known_pitches) == relief_count
        else None
    )
    total_pitches = (
        starter_pitches + relief_pitches
        if starter_pitches is not None and relief_pitches is not None
        else None
    )

    label = None
    if (
        starter_outs <= EXTENDED_COVERAGE_STARTER_MAX_OUTS
        and relief_outs >= EXTENDED_COVERAGE_RELIEF_MIN_OUTS
    ):
        label = EXTENDED_BULLPEN_COVERAGE_LABEL

    assignment = None
    if label is not None:
        history_coverage = (
            pitcher_season_ledger_coverage.history_coverage_for_game_log(
                starter_log,
                starter_pitcher,
            )
        )
        assignment = starter_assignment_context.build_starter_assignment_context(
            starter_log,
            starter_pitcher,
            history_coverage=history_coverage,
        )

    if assignment is not None:
        # The assignment lead already names the starter and carries the
        # combined-workload meaning, so the follow-up uses a pronoun and
        # the total-workload prose is left to the total block below.
        sentences = [
            assignment['sentence'],
            _starter_followup_sentence(starter_outs, starter_pitches),
            _relief_context_sentence(relief_count, relief_outs, relief_pitches),
        ]
    else:
        sentences = [
            _starter_context_sentence(starter_pitcher, starter_outs, starter_pitches),
            _relief_context_sentence(relief_count, relief_outs, relief_pitches),
        ]
        if label is not None:
            sentences.append(
                _total_context_sentence(total_pitchers, total_outs, total_pitches)
            )

    block = {
        'mlb_game_pk': game_pk,
        'appearance_team_id': starter_log.appearance_team_id,
        'opponent': starter_log.opponent,
        'opponent_abbreviation': starter_log.opponent_abbreviation,
        'game_shape': shape_payload['shape'],
        'context_label': label,
        'starter_authority': STARTER_AUTHORITY_OFFICIAL,
        'reconciled': True,
        'starter': {
            'pitcher_id': starter_pitcher.id,
            'pitcher_mlb_id': starter_pitcher.mlb_id,
            'pitcher_full_name': starter_pitcher.full_name,
            'outs': starter_outs,
            'innings': _ip_text(starter_outs),
            'pitches': starter_pitches,
        },
        'relief': {
            'pitcher_count': relief_count,
            'outs': relief_outs,
            'innings': _ip_text(relief_outs),
            'pitches': relief_pitches,
            'pitcher_ids': sorted(pitcher.id for _log, pitcher in relief),
        },
        'total': {
            'pitcher_count': total_pitchers,
            'outs': total_outs,
            'innings': _ip_text(total_outs),
            'pitches': total_pitches,
        },
        'context_sentences': sentences,
    }
    if assignment is not None:
        block['starter_assignment'] = assignment
    return block


def _known_outs(log):
    outs = log.innings_pitched_outs
    if outs is None:
        return None
    try:
        parsed = int(outs)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _starter_context_sentence(pitcher, outs, pitches):
    sentence = (
        f'{pitcher.full_name} started and recorded {_out_count_text(outs)} '
        f'({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _starter_followup_sentence(outs, pitches):
    sentence = f'He recorded {_out_count_text(outs)} ({_ip_text(outs)} IP)'
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _relief_context_sentence(relief_count, outs, pitches):
    sentence = (
        f'{_sentence_start_reliever_count_text(relief_count)} covered the remaining '
        f'{_out_count_text(outs)} ({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} on {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _total_context_sentence(pitcher_count, outs, pitches):
    sentence = (
        f'{_pitcher_count_text(pitcher_count)} combined for '
        f'{_out_count_text(outs)} ({_ip_text(outs)} IP)'
    )
    if pitches is not None:
        sentence = f'{sentence} and {_pitch_count_text(pitches)}'
    return f'{sentence}.'


def _out_count_text(count):
    return f'{count} {"out" if count == 1 else "outs"}'


def _reliever_count_text(count):
    return f'{count} {"reliever" if count == 1 else "relievers"}'


def _sentence_start_reliever_count_text(count):
    words = {
        1: 'One',
        2: 'Two',
        3: 'Three',
        4: 'Four',
        5: 'Five',
        6: 'Six',
        7: 'Seven',
        8: 'Eight',
        9: 'Nine',
    }
    label = words.get(count, str(count))
    return f'{label} {"reliever" if count == 1 else "relievers"}'


def _date_group(game_date, entries):
    relief_count = len(entries)
    outs_total = sum((log.innings_pitched_outs or 0) for log, pitcher in entries)
    known_pitches = [
        log.pitches_thrown
        for log, pitcher in entries
        if log.pitches_thrown is not None
    ]
    pitches_total = (
        sum(known_pitches)
        if len(known_pitches) == relief_count
        else None
    )
    game_pks = sorted({
        log.mlb_game_pk for log, pitcher in entries if log.mlb_game_pk is not None
    })
    sentence = (
        f'{_month_day(game_date)} \u2014 {_relief_count_text(relief_count)}'
    )
    if len(game_pks) > 1:
        # A date total that spans more than one game says so, so no game-level
        # narrative beneath it can be mistaken for covering these totals.
        sentence = f'{sentence} across {_game_count_text(len(game_pks))}'
    sentence = f'{sentence}, {_ip_text(outs_total)} IP'
    if pitches_total is not None:
        sentence = f'{sentence}, {_pitch_count_text(pitches_total)}'
    return {
        'game_date': game_date.isoformat(),
        'relief_appearances': relief_count,
        'outs_total': outs_total,
        'pitches_total': pitches_total,
        'appearances_with_pitches': len(known_pitches),
        'game_pks': game_pks,
        'game_count': len(game_pks),
        'sentence': f'{sentence}.',
        'appearances': [
            _appearance_line(log, pitcher)
            for log, pitcher in entries
        ],
    }


def _group_totals_reconcile(group):
    """Every published summary number must equal the rows shown beneath it."""
    appearances = group.get('appearances') or []
    if group.get('relief_appearances') != len(appearances):
        return False
    outs = [row.get('innings_pitched_outs') for row in appearances]
    if any(value is None for value in outs):
        return False
    if group.get('outs_total') != sum(outs):
        return False
    known_pitches = [
        row.get('pitches_thrown')
        for row in appearances
        if row.get('pitches_thrown') is not None
    ]
    if group.get('appearances_with_pitches') != len(known_pitches):
        return False
    expected_pitches = (
        sum(known_pitches) if len(known_pitches) == len(appearances) else None
    )
    return group.get('pitches_total') == expected_pitches


def _block_reconciles_with_appearances(block, group):
    """A game narrative may only describe rows visible beneath it.

    Its relief pitcher set must equal that game's shown appearance rows, and
    its relief totals must equal those same rows.
    """
    game_pk = block.get('mlb_game_pk')
    if game_pk is None or game_pk not in (group.get('game_pks') or []):
        return False

    shown = [
        row for row in (group.get('appearances') or [])
        if row.get('mlb_game_pk') == game_pk
    ]
    claimed_ids = list((block.get('relief') or {}).get('pitcher_ids') or [])
    if sorted(row.get('pitcher_id') for row in shown) != sorted(claimed_ids):
        return False
    if (block.get('relief') or {}).get('pitcher_count') != len(shown):
        return False
    if block.get('starter', {}).get('pitcher_id') in claimed_ids:
        return False

    outs = [row.get('innings_pitched_outs') for row in shown]
    if any(value is None for value in outs):
        return False
    if (block.get('relief') or {}).get('outs') != sum(outs):
        return False
    known_pitches = [
        row.get('pitches_thrown')
        for row in shown
        if row.get('pitches_thrown') is not None
    ]
    expected_pitches = (
        sum(known_pitches) if len(known_pitches) == len(shown) else None
    )
    return (block.get('relief') or {}).get('pitches') == expected_pitches


def _unavailable_group(game_date):
    """Honest unavailable state \u2014 never a partial or substituted baseball claim."""
    return {
        'game_date': game_date.isoformat(),
        'unavailable': True,
        'sentence': (
            f'{_month_day(game_date)} \u2014 relief work is unavailable because '
            f'the summary and the appearance records do not reconcile.'
        ),
        'appearances': [],
    }


def _appearance_line(log, pitcher):
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'pitcher_full_name': pitcher.full_name,
        'roster_status_sentence': _roster_status_sentence(pitcher),
        'mlb_game_pk': log.mlb_game_pk,
        'appearance_team_id': log.appearance_team_id,
        'game_date': log.game_date.isoformat(),
        'opponent': log.opponent,
        'opponent_abbreviation': log.opponent_abbreviation,
        'innings_pitched': log.innings_pitched,
        'innings_pitched_outs': log.innings_pitched_outs,
        'pitches_thrown': log.pitches_thrown,
        'strikeouts': log.strikeouts or 0,
        'walks': log.walks or 0,
        'hits_allowed': log.hits_allowed or 0,
        'runs_allowed': log.runs_allowed or 0,
        'save': bool(log.save),
        'hold': bool(log.hold),
        'blown_save': bool(log.blown_save),
        'win': bool(log.win),
        'loss': bool(log.loss),
        'save_situation': bool(log.save_situation),
        'sentence': _appearance_sentence(log, pitcher),
    }


def _roster_status_sentence(pitcher):
    status = pitcher.roster_status
    if pitcher.active:
        return 'On the active roster per MLB roster data.'
    if status:
        return f'Roster status: {status} per MLB roster data.'
    return 'Roster status unavailable.'


def _appearance_sentence(log, pitcher):
    parts = [
        f'{pitcher.full_name} \u2014 {_ip_text(log.innings_pitched_outs)} IP',
    ]
    if log.pitches_thrown is not None:
        parts.append(f'{_pitch_count_text(log.pitches_thrown)}')
    parts.extend([
        f'{log.strikeouts or 0} K',
        f'{log.walks or 0} BB',
    ])
    hits = log.hits_allowed or 0
    runs = log.runs_allowed or 0
    if hits or runs:
        parts.extend([
            f'{hits} H',
            f'{runs} R',
        ])
    return f'{", ".join(parts)}.'


def _window(rows, anchor, window_days):
    start_date = anchor - timedelta(days=window_days - 1)
    window_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.game_date >= start_date
    ]
    relief_rows = [
        (log, pitcher)
        for log, pitcher in window_rows
        if _start_relief_state(log) == RELIEF
    ]
    relief_count = len(relief_rows)
    pitcher_count = len({pitcher.id for log, pitcher in relief_rows})
    unknown_count = sum(
        1 for log, pitcher in window_rows
        if _start_relief_state(log) not in (START, RELIEF)
    )
    known_pitches = [
        log.pitches_thrown
        for log, pitcher in relief_rows
        if log.pitches_thrown is not None
    ]
    payload = {
        'through': anchor.isoformat(),
        'relief_appearances': relief_count,
        'pitchers_in_relief': pitcher_count,
        'pitches_total': _window_pitches_total(relief_count, known_pitches),
        'appearances_with_pitches': len(known_pitches),
        'start_relief_unknown': unknown_count,
        'sentence': (
            f'{_relief_count_text(relief_count)} in the {window_days} days '
            f'through {_month_day(anchor)}.'
        ),
        'pitchers_sentence': (
            f'{_pitcher_count_text(pitcher_count)} appeared in relief in the '
            f'{window_days} days through {_month_day(anchor)}.'
        ),
        'pitches_sentence': _pitches_sentence(relief_count, known_pitches),
    }
    if unknown_count:
        total = relief_count + unknown_count
        payload['start_relief_unknown_sentence'] = (
            f'Start/relief status unavailable for {unknown_count} of {total} '
            f'{_appearance_word(total)} in the {window_days} days through '
            f'{_month_day(anchor)}; relief totals cover the other {relief_count}.'
        )
    return payload


def _window_pitches_total(relief_count, known_pitches):
    if relief_count == 0:
        return 0
    if len(known_pitches) == relief_count:
        return sum(known_pitches)
    return None


def _pitches_sentence(relief_count, known_pitches):
    known_count = len(known_pitches)
    pitches_total = sum(known_pitches)
    if known_count == relief_count:
        return (
            f'{_pitch_count_text(pitches_total)} across those '
            f'{_relief_count_text(relief_count)}.'
        )
    missing_count = relief_count - known_count
    return (
        f'Pitch count unavailable for {missing_count} of {relief_count} '
        f'{_relief_appearance_word(relief_count)}; '
        f'{_pitch_count_text(pitches_total)} across the other {known_count}.'
    )


def _month_day(value):
    return f'{MONTH_NAMES[value.month]} {value.day}'


def _ip_text(innings_pitched_outs):
    outs = innings_pitched_outs or 0
    return f'{outs // 3}.{outs % 3}'


def _relief_count_text(count):
    return f'{count} {_relief_appearance_word(count)}'


def _relief_appearance_word(count):
    return 'relief appearance' if count == 1 else 'relief appearances'


def _game_count_text(count):
    return f'{count} {"game" if count == 1 else "games"}'


def _appearance_word(count):
    return 'appearance' if count == 1 else 'appearances'


def _pitcher_count_text(count):
    return f'{count} {"pitcher" if count == 1 else "pitchers"}'


def _pitch_count_text(count):
    pitch_word = 'pitch' if count == 1 else 'pitches'
    return f'{count} {pitch_word}'
