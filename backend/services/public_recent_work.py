from datetime import date, timedelta

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import board_freshness


RECENT_LINES_MAX = 8
LOOKBACK_DAYS = 30
WINDOW_DAYS = (7, 14)
CAPABILITY = 'public_recent_work'

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


class PitcherNotFoundError(LookupError):
    pass


def build_public_recent_work_payload(pitcher_id):
    pitcher = Pitcher.query.filter(Pitcher.id == pitcher_id).one_or_none()
    if pitcher is None:
        raise PitcherNotFoundError(pitcher_id)

    freshness = board_freshness.board_freshness_block()
    anchor = _parse_data_through(freshness.get('data_through'))
    payload = {
        'capability': CAPABILITY,
        'pitcher': _pitcher_payload(pitcher),
        'data_through': anchor.isoformat() if anchor else None,
        'freshness': freshness,
        'roster_status': _roster_status_payload(pitcher),
        'last_appearance': None,
        'recent_appearances': [],
    }

    if anchor is None:
        return payload

    start_date = anchor - timedelta(days=LOOKBACK_DAYS - 1)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher.id,
            GameLog.game_date >= start_date,
            GameLog.game_date <= anchor,
        )
        .order_by(desc(GameLog.game_date), desc(GameLog.id))
        .all()
    )

    payload['recent_appearances'] = [
        _appearance_line(log)
        for log in logs[:RECENT_LINES_MAX]
    ]
    if logs:
        payload['last_appearance'] = _last_appearance_payload(logs[0], anchor)
    else:
        payload['absence_sentence'] = (
            f'No appearances in the {LOOKBACK_DAYS} days through {_month_day(anchor)}.'
        )

    payload['workload'] = {
        f'window_{window_days}': _workload_window(logs, anchor, window_days)
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


def _pitcher_payload(pitcher):
    return {
        'id': pitcher.id,
        'mlb_id': pitcher.mlb_id,
        'full_name': pitcher.full_name,
        'team_id': pitcher.team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
    }


def _roster_status_payload(pitcher):
    status = pitcher.roster_status
    if pitcher.active:
        sentence = 'On the active roster per MLB roster data.'
    elif status:
        sentence = f'Roster status: {status} per MLB roster data.'
    else:
        sentence = 'Roster status unavailable.'
    return {
        'status': status,
        'source': pitcher.roster_status_source,
        'sentence': sentence,
    }


def _appearance_line(log):
    return {
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
    }


def _last_appearance_payload(log, anchor):
    payload = _appearance_line(log)
    payload.update({
        'sentence': _last_appearance_sentence(log),
        'timing_sentence': _timing_sentence(log.game_date, anchor),
        'fact_sentences': _fact_sentences(log),
    })
    return payload


def _last_appearance_sentence(log):
    opponent = log.opponent_abbreviation or log.opponent or ''
    parts = [
        f'Last appearance: {_month_day(log.game_date)} vs {opponent} \u2014 '
        f'{_ip_text(log.innings_pitched_outs)} IP'
    ]
    if log.pitches_thrown is not None:
        parts.append(f'{log.pitches_thrown} pitches')
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


def _timing_sentence(game_date, anchor):
    days_before = (anchor - game_date).days
    anchor_text = _month_day(anchor)
    if days_before == 0:
        return f'That appearance came on {anchor_text}.'
    day_word = 'day' if days_before == 1 else 'days'
    return f'That appearance came {days_before} {day_word} before {anchor_text}.'


def _fact_sentences(log):
    game_date = _month_day(log.game_date)
    facts = []
    if log.save:
        facts.append(f'Recorded a save ({game_date}).')
    if log.hold:
        facts.append(f'Recorded a hold ({game_date}).')
    if log.blown_save:
        facts.append(f'Charged with a blown save ({game_date}).')
    if log.win:
        facts.append(f'Credited with the win ({game_date}).')
    if log.loss:
        facts.append(f'Charged with the loss ({game_date}).')
    return facts


def _workload_window(logs, anchor, window_days):
    start_date = anchor - timedelta(days=window_days - 1)
    window_logs = [log for log in logs if log.game_date >= start_date]
    appearances = len(window_logs)
    appearances_text = _appearance_count_text(appearances)
    payload = {
        'through': anchor.isoformat(),
        'appearances': appearances,
        'pitches_total': 0 if appearances == 0 else None,
        'appearances_with_pitches': sum(
            1 for log in window_logs if log.pitches_thrown is not None
        ),
        'sentence': (
            f'{appearances_text} in the {window_days} days through {_month_day(anchor)}.'
        ),
    }
    if appearances == 0:
        return payload

    known_pitches = [
        log.pitches_thrown
        for log in window_logs
        if log.pitches_thrown is not None
    ]
    known_count = len(known_pitches)
    pitches_total = sum(known_pitches)
    if known_count == appearances:
        payload['pitches_total'] = pitches_total
        payload['pitches_sentence'] = (
            f'{_pitch_count_text(pitches_total)} across those '
            f'{_appearance_count_text(appearances)}.'
        )
    else:
        missing_count = appearances - known_count
        payload['pitches_sentence'] = (
            f'Pitch count unavailable for {missing_count} of {appearances} '
            f'{_appearance_word(appearances)}; {_pitch_count_text(pitches_total)} '
            f'across the other {known_count}.'
        )
    return payload


def _month_day(value):
    return f'{MONTH_NAMES[value.month]} {value.day}'


def _ip_text(innings_pitched_outs):
    outs = innings_pitched_outs or 0
    return f'{outs // 3}.{outs % 3}'


def _appearance_count_text(count):
    return f'{count} {_appearance_word(count)}'


def _appearance_word(count):
    return 'appearance' if count == 1 else 'appearances'


def _pitch_count_text(count):
    pitch_word = 'pitch' if count == 1 else 'pitches'
    return f'{count} {pitch_word}'
