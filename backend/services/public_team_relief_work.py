from datetime import date, timedelta

from sqlalchemy import asc, desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import board_freshness
from services import game_shape


CAPABILITY = 'public_team_relief_work'
RECENT_GAME_DATES_MAX = 5
LOOKBACK_DAYS = 30
WINDOW_DAYS = (7, 14)

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
    rows = (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .add_entity(Pitcher)
        .filter(
            Pitcher.team_id == team_id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
        )
        .order_by(desc(GameLog.game_date), asc(Pitcher.full_name), asc(GameLog.id))
        .all()
    )
    relief_rows = [
        (log, pitcher)
        for log, pitcher in rows
        if log.games_started == 0
    ]
    all_rows_by_date = {}
    for log, pitcher in rows:
        all_rows_by_date.setdefault(log.game_date, []).append((log, pitcher))

    payload['relief_by_date'] = _relief_by_date(relief_rows, all_rows_by_date)
    if not relief_rows:
        payload['absence_sentence'] = (
            f'No relief appearances in the {LOOKBACK_DAYS} days through '
            f'{_month_day(anchor)}.'
        )
    payload['windows'] = {
        f'window_{window_days}': _window(rows, anchor, window_days)
        for window_days in WINDOW_DAYS
    }
    return payload


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
    return f'Covers pitchers currently on the {club} roster per MLB roster data.'


def _relief_by_date(relief_rows, all_rows_by_date):
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
        games = _game_context_blocks(all_rows_by_date.get(game_date) or [])
        if games:
            group['games'] = games
        groups.append(group)
    return groups


def _game_context_blocks(date_entries):
    by_game = {}
    for log, pitcher in date_entries:
        if log.mlb_game_pk is None:
            continue
        by_game.setdefault(log.mlb_game_pk, []).append((log, pitcher))

    blocks = []
    for game_pk in sorted(by_game):
        block = _game_context_block(game_pk, by_game[game_pk])
        if block is not None:
            blocks.append(block)
    return blocks


def _game_context_block(game_pk, entries):
    shape_payload = game_shape.classify_game_shape(
        [log for log, _pitcher in entries]
    )
    if shape_payload['shape'] not in CONTEXT_ELIGIBLE_GAME_SHAPES:
        return None

    starters = [
        (log, pitcher) for log, pitcher in entries if log.games_started == 1
    ]
    relief = [
        (log, pitcher) for log, pitcher in entries if log.games_started == 0
    ]
    if len(starters) != 1 or not relief:
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

    sentences = [
        _starter_context_sentence(starter_pitcher, starter_outs, starter_pitches),
        _relief_context_sentence(relief_count, relief_outs, relief_pitches),
    ]
    if label is not None:
        sentences.append(
            _total_context_sentence(total_pitchers, total_outs, total_pitches)
        )

    return {
        'mlb_game_pk': game_pk,
        'opponent': starter_log.opponent,
        'opponent_abbreviation': starter_log.opponent_abbreviation,
        'game_shape': shape_payload['shape'],
        'context_label': label,
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
        },
        'total': {
            'pitcher_count': total_pitchers,
            'outs': total_outs,
            'innings': _ip_text(total_outs),
            'pitches': total_pitches,
        },
        'context_sentences': sentences,
    }


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


def _relief_context_sentence(relief_count, outs, pitches):
    sentence = (
        f'{_reliever_count_text(relief_count)} covered the remaining '
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
    sentence = (
        f'{_month_day(game_date)} \u2014 {_relief_count_text(relief_count)}, '
        f'{_ip_text(outs_total)} IP'
    )
    if pitches_total is not None:
        sentence = f'{sentence}, {_pitch_count_text(pitches_total)}'
    return {
        'game_date': game_date.isoformat(),
        'relief_appearances': relief_count,
        'outs_total': outs_total,
        'pitches_total': pitches_total,
        'appearances_with_pitches': len(known_pitches),
        'sentence': f'{sentence}.',
        'appearances': [
            _appearance_line(log, pitcher)
            for log, pitcher in entries
        ],
    }


def _appearance_line(log, pitcher):
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'pitcher_full_name': pitcher.full_name,
        'roster_status_sentence': _roster_status_sentence(pitcher),
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
        if log.games_started == 0
    ]
    relief_count = len(relief_rows)
    pitcher_count = len({pitcher.id for log, pitcher in relief_rows})
    unknown_count = sum(
        1 for log, pitcher in window_rows if log.games_started is None
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


def _appearance_word(count):
    return 'appearance' if count == 1 else 'appearances'


def _pitcher_count_text(count):
    return f'{count} {"pitcher" if count == 1 else "pitchers"}'


def _pitch_count_text(count):
    pitch_word = 'pitch' if count == 1 else 'pitches'
    return f'{count} {pitch_word}'
