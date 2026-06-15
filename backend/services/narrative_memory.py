"""
Narrative Memory V1 continuity helpers.

This module derives continuity from existing persisted workload history. It
does not persist stories, archive observations, create narrative threads, or
infer roles/health/status beyond what GameLog evidence can prove.
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from utils.games_started import (
    MATERIAL_UNKNOWN_START_LIMITATION,
    UNKNOWN_START_LIMITATION,
    games_started_summary,
    is_relief,
)


DEFAULT_WINDOWS = (7, 10, 14)
RESTED_OPTION_IDLE_DAYS = 2
MIN_CONCENTRATION_APPEARANCES = 5

CAPABILITY_WORKLOAD_CONCENTRATION = 'workload_concentration_continuity'
CAPABILITY_BULLPEN_RECOVERY = 'bullpen_recovery_continuity'
CAPABILITY_PITCHER_USAGE_TREND = 'pitcher_usage_trend_continuity'

STATE_LIMITED = 'limited'
STATE_CONCENTRATED = 'concentrated'
STATE_NOT_CONCENTRATED = 'not_concentrated'
STATE_WORKLOAD_EASING = 'workload_easing'
STATE_NO_CLEAR_WORKLOAD_EASING = 'no_clear_workload_easing'
STATE_ACCELERATING = 'accelerating'
STATE_DECREASING = 'decreasing'
STATE_STABLE = 'stable'
STATE_IDLE = 'idle'

CURRENT_TEAM_ASSIGNMENT_LIMITATION = (
    'Team continuity uses pitchers currently assigned to the team; historical '
    'team membership is not modeled separately.'
)
OBSERVED_GAMES_LIMITATION = (
    'Observed game counts are derived from stored bullpen appearances, not a '
    'separate team-game schedule.'
)
NULL_START_LIMITATION = (
    'Some appearances are missing gamesStarted; unknown rows are excluded from '
    'bullpen-only workload evidence.'
)


def _value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iso(value):
    return value.isoformat() if value else None


def _pct(part, total):
    if not total:
        return 0
    return round(part / total, 2)


def _pct_label(value):
    return f'{round(value * 100)}%'


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for value in group or []:
            if value not in merged:
                merged.append(value)
    return merged


def _valid_window_days(window_days):
    try:
        days = int(window_days)
    except (TypeError, ValueError):
        raise ValueError('window_days must be a positive integer') from None
    if days <= 0:
        raise ValueError('window_days must be a positive integer')
    return days


def _resolve_reference_date(logs, reference_date=None):
    ref = _as_date(reference_date)
    if ref is not None:
        return ref

    dates = [
        _as_date(_value(log, 'game_date'))
        for log in logs or []
        if _value(log, 'game_date') is not None
    ]
    return max(dates) if dates else product_current_date()


def _window_for(reference_date, window_days):
    days = _valid_window_days(window_days)
    end = _as_date(reference_date)
    return end - timedelta(days=days - 1), end


def _is_bullpen_log(log):
    return is_relief(log)


def _filter_logs(logs, start, end, bullpen_only=True):
    filtered = []
    for log in logs or []:
        game_date = _as_date(_value(log, 'game_date'))
        if game_date is None or game_date < start or game_date > end:
            continue
        if bullpen_only and not _is_bullpen_log(log):
            continue
        filtered.append(log)
    return filtered


def _start_signal_fields(logs):
    summary = games_started_summary(logs)
    if summary.material_unknown:
        state = 'material_unknown'
    elif summary.unknown:
        state = 'partial'
    else:
        state = 'complete'
    return {
        'start_classification_state': state,
        'unknown_start_rows': summary.unknown,
        'unknown_start_row_share': round(summary.unknown_share, 2),
    }


def _add_start_signal_limitations(contract, signal):
    if not signal.get('unknown_start_rows'):
        return
    limitations = [NULL_START_LIMITATION]
    if signal.get('start_classification_state') == 'material_unknown':
        limitations.append(MATERIAL_UNKNOWN_START_LIMITATION)
    else:
        limitations.append(UNKNOWN_START_LIMITATION)
    contract['limitations'] = _merge_unique(contract.get('limitations'), limitations)


def _pitcher_id(log):
    return _value(log, 'pitcher_id')


def _pitcher_name_from(value):
    return (
        _value(value, 'full_name')
        or _value(value, 'pitcher_name')
        or _value(value, 'name')
    )


def _pitcher_lookup(pitchers=None, logs=None):
    lookup = {}
    for pitcher in pitchers or []:
        pitcher_id = _value(pitcher, 'id')
        if pitcher_id is not None:
            lookup[pitcher_id] = _pitcher_name_from(pitcher)
    for log in logs or []:
        pitcher_id = _pitcher_id(log)
        if pitcher_id is not None and pitcher_id not in lookup:
            lookup[pitcher_id] = _pitcher_name_from(log)
    return lookup


def _game_key(log):
    game_pk = _value(log, 'mlb_game_pk')
    if game_pk is not None:
        return f'game:{game_pk}'
    game_date = _as_date(_value(log, 'game_date'))
    return f'date:{_iso(game_date)}'


def _game_sort_key(game):
    game_key = game['game_key']
    return (game['game_date'], str(game_key))


def _observed_games(logs):
    games = {}
    for log in logs or []:
        game_date = _as_date(_value(log, 'game_date'))
        if game_date is None:
            continue
        key = _game_key(log)
        games[key] = {
            'game_key': key,
            'game_date': game_date,
            'game_date_iso': _iso(game_date),
        }
    return sorted(games.values(), key=_game_sort_key, reverse=True)


def _pool_ids(pitcher_pool=None, pitchers=None, logs=None):
    ids = set()
    for item in pitcher_pool or []:
        if isinstance(item, int):
            ids.add(item)
        else:
            pitcher_id = _value(item, 'id')
            if pitcher_id is not None:
                ids.add(pitcher_id)
    for pitcher in pitchers or []:
        pitcher_id = _value(pitcher, 'id')
        if pitcher_id is not None:
            ids.add(pitcher_id)
    if not ids:
        for log in logs or []:
            pitcher_id = _pitcher_id(log)
            if pitcher_id is not None:
                ids.add(pitcher_id)
    return ids


def _pitcher_summary(logs, pitchers=None):
    names = _pitcher_lookup(pitchers=pitchers, logs=logs)
    by_pitcher = defaultdict(lambda: {
        'pitcher_id': None,
        'pitcher_name': None,
        'appearances': 0,
        'pitches': 0,
        'appearance_dates': set(),
    })

    for log in logs or []:
        pitcher_id = _pitcher_id(log)
        if pitcher_id is None:
            continue
        bucket = by_pitcher[pitcher_id]
        bucket['pitcher_id'] = pitcher_id
        bucket['pitcher_name'] = names.get(pitcher_id)
        bucket['appearances'] += 1
        bucket['pitches'] += int(_value(log, 'pitches_thrown', 0) or 0)
        game_date = _as_date(_value(log, 'game_date'))
        if game_date is not None:
            bucket['appearance_dates'].add(game_date)

    summaries = []
    for item in by_pitcher.values():
        summaries.append({
            'pitcher_id': item['pitcher_id'],
            'pitcher_name': item['pitcher_name'],
            'appearances': item['appearances'],
            'pitches': item['pitches'],
            'appearance_dates': [_iso(day) for day in sorted(item['appearance_dates'])],
        })

    return sorted(
        summaries,
        key=lambda item: (
            -item['appearances'],
            -item['pitches'],
            item['pitcher_name'] or '',
            item['pitcher_id'] if item['pitcher_id'] is not None else -1,
        ),
    )


def _segment_summary(logs, pitchers=None):
    pitcher_rows = _pitcher_summary(logs, pitchers=pitchers)
    appearances = len(logs)
    pitches = sum(int(_value(log, 'pitches_thrown', 0) or 0) for log in logs or [])
    dates = sorted({
        _as_date(_value(log, 'game_date'))
        for log in logs or []
        if _value(log, 'game_date') is not None
    })
    top = pitcher_rows[0] if pitcher_rows else None
    return {
        'appearances': appearances,
        'pitches': pitches,
        'appearance_dates': [_iso(day) for day in dates],
        'observed_games': len(_observed_games(logs)),
        'pitchers_used': len(pitcher_rows),
        'top_pitcher': top,
        'top_pitcher_appearance_share': _pct(top['appearances'], appearances) if top else 0,
        'pitchers': pitcher_rows,
    }


def _base_contract(capability, reference_date, window_days, logs, limitations=None):
    start, end = _window_for(reference_date, window_days)
    window_logs = _filter_logs(logs, start, end, bullpen_only=False)
    data_through = max(
        (_as_date(_value(log, 'game_date')) for log in window_logs),
        default=None,
    )
    return {
        'capability': capability,
        'window_days': _valid_window_days(window_days),
        'window_start': _iso(start),
        'window_end': _iso(end),
        'data_through_date': _iso(data_through),
        'evidence': {},
        'limitations': list(limitations or []),
    }


def _starter_count(logs):
    return sum(1 for log in logs or [] if _value(log, 'games_started') == 1)


def build_workload_concentration_continuity(
    logs,
    pitchers=None,
    reference_date=None,
    window_days=10,
    limitations=None,
):
    """
    Identify repeated bullpen workload concentration in a fixed date window.

    The evidence is based on relief appearances only. Rows with
    games_started=1 or unknown gamesStarted are excluded from bullpen workload
    evidence.
    """
    all_logs = list(logs or [])
    ref = _resolve_reference_date(all_logs, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    bullpen_logs = _filter_logs(all_logs, start, end)
    contract = _base_contract(
        CAPABILITY_WORKLOAD_CONCENTRATION,
        ref,
        window_days,
        bullpen_logs,
        limitations=limitations,
    )

    signal = _start_signal_fields(_filter_logs(all_logs, start, end, bullpen_only=False))
    _add_start_signal_limitations(contract, signal)

    summary = _segment_summary(bullpen_logs, pitchers=pitchers)
    total = summary['appearances']
    top_pitchers = summary['pitchers']
    top_two = top_pitchers[:2]
    top_two_appearances = sum(row['appearances'] for row in top_two)

    core_threshold = 3 if _valid_window_days(window_days) >= 10 else 2
    core_arms = [
        row for row in top_pitchers
        if row['appearances'] >= core_threshold
    ]
    core_ids = {row['pitcher_id'] for row in core_arms}
    core_appearances = sum(row['appearances'] for row in core_arms)
    observed_dates = {
        _as_date(_value(log, 'game_date'))
        for log in bullpen_logs
        if _value(log, 'game_date') is not None
    }
    core_dates = {
        _as_date(_value(log, 'game_date'))
        for log in bullpen_logs
        if _pitcher_id(log) in core_ids and _value(log, 'game_date') is not None
    }

    top_share = summary['top_pitcher_appearance_share']
    top_two_share = _pct(top_two_appearances, total)
    core_share = _pct(core_appearances, total)
    persistence_share = _pct(len(core_dates), len(observed_dates))

    if signal['start_classification_state'] == 'material_unknown':
        state = STATE_LIMITED
    elif total < MIN_CONCENTRATION_APPEARANCES or not top_pitchers:
        state = STATE_LIMITED
        contract['limitations'] = _merge_unique(
            contract['limitations'],
            ['Fewer than 5 stored bullpen appearances are available in this window.'],
        )
    elif top_two_share >= 0.55 or core_share >= 0.55 or top_share >= 0.4:
        state = STATE_CONCENTRATED
    else:
        state = STATE_NOT_CONCENTRATED

    contract.update({
        'state': state,
        'summary': _workload_concentration_summary(
            state=state,
            total=total,
            top_two=top_two,
            top_two_share=top_two_share,
            core_arms=core_arms,
            persistence_share=persistence_share,
        ),
        'evidence': {
            'bullpen_appearances': total,
            'excluded_starter_appearances': _starter_count(_filter_logs(all_logs, start, end, bullpen_only=False)),
            'unknown_start_rows_excluded': signal['unknown_start_rows'],
            **signal,
            'observed_bullpen_games': summary['observed_games'],
            'observed_usage_dates': [_iso(day) for day in sorted(observed_dates)],
            'pitchers_used': summary['pitchers_used'],
            'top_pitcher': summary['top_pitcher'],
            'top_pitcher_appearance_share': top_share,
            'top_two_pitchers': top_two,
            'top_two_appearance_share': top_two_share,
            'core_arm_threshold': core_threshold,
            'core_arms': core_arms,
            'core_arm_appearances': core_appearances,
            'core_arm_appearance_share': core_share,
            'core_usage_dates': [_iso(day) for day in sorted(core_dates)],
            'core_usage_date_share': persistence_share,
        },
    })
    return contract


def _workload_concentration_summary(state, total, top_two, top_two_share, core_arms, persistence_share):
    if state == STATE_LIMITED:
        return 'Stored workload history is too thin to assess repeated bullpen concentration.'
    if state == STATE_CONCENTRATED and top_two:
        names = [
            row.get('pitcher_name') or f"Pitcher {row.get('pitcher_id')}"
            for row in top_two
        ]
        if len(names) == 1:
            subject = names[0]
        else:
            subject = f'{names[0]} and {names[1]}'
        return (
            f'{subject} handled {sum(row["appearances"] for row in top_two)} '
            f'of {total} stored bullpen appearances in this window '
            f'({_pct_label(top_two_share)}).'
        )
    if core_arms and persistence_share > 0:
        return (
            'A repeated bullpen core appears in '
            f'{_pct_label(persistence_share)} of observed usage dates, but '
            'appearance share is not concentrated enough for a strong read.'
        )
    return 'Stored bullpen appearances are spread across the window.'


def build_bullpen_recovery_continuity(
    logs,
    pitchers=None,
    pitcher_pool=None,
    reference_date=None,
    window_days=14,
    limitations=None,
):
    """
    Compare the earlier and later parts of a workload window for recovery signs.

    Recovery evidence is factual: more pitchers idle for the last two days,
    lower top-arm appearance share, and less recent workload volume. The state
    says workload is easing only when multiple stored-workload signals agree.
    It does not infer health, injury, trust, or availability beyond stored usage.
    """
    all_logs = list(logs or [])
    ref = _resolve_reference_date(all_logs, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    recent_days = max(3, _valid_window_days(window_days) // 2)
    recent_start = end - timedelta(days=recent_days - 1)
    prior_end = recent_start - timedelta(days=1)

    bullpen_logs = _filter_logs(all_logs, start, end)
    contract = _base_contract(
        CAPABILITY_BULLPEN_RECOVERY,
        ref,
        window_days,
        bullpen_logs,
        limitations=limitations,
    )
    signal = _start_signal_fields(_filter_logs(all_logs, start, end, bullpen_only=False))
    _add_start_signal_limitations(contract, signal)

    prior_logs = _filter_logs(bullpen_logs, start, prior_end)
    recent_logs = _filter_logs(bullpen_logs, recent_start, end)
    prior = _segment_summary(prior_logs, pitchers=pitchers)
    recent = _segment_summary(recent_logs, pitchers=pitchers)
    pool_ids = _pool_ids(pitcher_pool=pitcher_pool, pitchers=pitchers, logs=bullpen_logs)
    if not pitcher_pool and not pitchers:
        contract['limitations'] = _merge_unique(
            contract['limitations'],
            ['Rested-option counts use pitchers observed in the window because no bullpen pool was supplied.'],
        )

    prior_rested = _rested_options(bullpen_logs, pool_ids, prior_end)
    recent_rested = _rested_options(bullpen_logs, pool_ids, end)
    rested_delta = recent_rested - prior_rested
    top_share_delta = round(
        recent['top_pitcher_appearance_share'] - prior['top_pitcher_appearance_share'],
        2,
    )
    appearance_delta = recent['appearances'] - prior['appearances']
    pitch_delta = recent['pitches'] - prior['pitches']
    easing_signals = {
        'rested_options_increased': rested_delta > 0,
        'top_pitcher_share_decreased': top_share_delta <= -0.1,
        'appearance_volume_decreased': appearance_delta < 0,
        'pitch_volume_decreased': pitch_delta < 0,
    }
    easing_signal_count = sum(1 for value in easing_signals.values() if value)

    if signal['start_classification_state'] == 'material_unknown':
        state = STATE_LIMITED
        contract['limitations'] = _merge_unique(
            contract['limitations'],
            ['Start/relief coverage is too incomplete for a workload-easing read.'],
        )
    elif prior['appearances'] == 0 or recent['appearances'] == 0:
        state = STATE_LIMITED
        contract['limitations'] = _merge_unique(
            contract['limitations'],
            ['Both the earlier and later segments need stored bullpen appearances for a workload-easing read.'],
        )
    elif easing_signal_count >= 2:
        state = STATE_WORKLOAD_EASING
    else:
        state = STATE_NO_CLEAR_WORKLOAD_EASING

    contract.update({
        'state': state,
        'summary': _bullpen_recovery_summary(
            state,
            prior_rested,
            recent_rested,
            prior['top_pitcher_appearance_share'],
            recent['top_pitcher_appearance_share'],
        ),
        'evidence': {
            'prior_segment': {
                'window_start': _iso(start),
                'window_end': _iso(prior_end),
                **prior,
                'rested_options': prior_rested,
            },
            'recent_segment': {
                'window_start': _iso(recent_start),
                'window_end': _iso(end),
                **recent,
                'rested_options': recent_rested,
            },
            'rested_option_idle_days': RESTED_OPTION_IDLE_DAYS,
            'rested_options_change': rested_delta,
            'top_pitcher_share_change': top_share_delta,
            'appearance_count_change': appearance_delta,
            'pitch_count_change': pitch_delta,
            'workload_easing_signals': easing_signals,
            'workload_easing_signal_count': easing_signal_count,
            'bullpen_pool_size': len(pool_ids),
            'excluded_starter_appearances': _starter_count(_filter_logs(all_logs, start, end, bullpen_only=False)),
            'unknown_start_rows_excluded': signal['unknown_start_rows'],
            **signal,
        },
    })
    return contract


def _rested_options(logs, pool_ids, segment_end):
    if segment_end is None:
        return 0
    idle_start = segment_end - timedelta(days=RESTED_OPTION_IDLE_DAYS - 1)
    recently_used = {
        _pitcher_id(log)
        for log in logs or []
        if _pitcher_id(log) in pool_ids
        and idle_start <= _as_date(_value(log, 'game_date')) <= segment_end
    }
    return len(set(pool_ids) - recently_used)


def _bullpen_recovery_summary(state, prior_rested, recent_rested, prior_share, recent_share):
    if state == STATE_LIMITED:
        return 'Stored workload history is too thin to assess workload easing continuity.'
    if state == STATE_WORKLOAD_EASING:
        return (
            f'Stored workload shows flexibility improving: rested options moved from {prior_rested} to {recent_rested}, '
            f'while top-arm appearance share moved from {_pct_label(prior_share)} '
            f'to {_pct_label(recent_share)}.'
        )
    return (
        'The stored workload window does not show clear workload easing; '
        f'rested options moved from {prior_rested} to {recent_rested}.'
    )


def build_pitcher_usage_trend_continuity(
    pitcher_logs,
    team_logs=None,
    pitcher=None,
    pitcher_id=None,
    pitchers=None,
    reference_date=None,
    window_days=10,
    game_windows=(6, 10),
    limitations=None,
):
    """
    Build pitcher usage continuity from stored appearances.

    Counts such as "4 of the last 6 games" are based on observed team bullpen
    games. No role, health, closer, or manager-trust claim is inferred.
    """
    pitcher_logs = list(pitcher_logs or [])
    team_logs = list(team_logs if team_logs is not None else pitcher_logs)
    all_logs = team_logs + pitcher_logs
    ref = _resolve_reference_date(all_logs, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    pitcher_id = pitcher_id or _value(pitcher, 'id') or (
        _pitcher_id(pitcher_logs[0]) if pitcher_logs else None
    )
    if pitcher_id is None:
        raise ValueError('pitcher_id is required when pitcher_logs do not identify a pitcher')

    names = _pitcher_lookup(pitchers=_merge_unique([pitcher] if pitcher else [], pitchers), logs=pitcher_logs)
    pitcher_name = names.get(pitcher_id) or _pitcher_name_from(pitcher)
    bullpen_team_logs = _filter_logs(team_logs, start, end)
    bullpen_pitcher_logs = [
        log for log in _filter_logs(pitcher_logs, start, end)
        if _pitcher_id(log) == pitcher_id
    ]
    contract = _base_contract(
        CAPABILITY_PITCHER_USAGE_TREND,
        ref,
        window_days,
        bullpen_team_logs + bullpen_pitcher_logs,
        limitations=limitations,
    )
    contract['limitations'] = _merge_unique(contract['limitations'], [OBSERVED_GAMES_LIMITATION])
    signal = _start_signal_fields(_filter_logs(all_logs, start, end, bullpen_only=False))
    _add_start_signal_limitations(contract, signal)

    games = _observed_games(bullpen_team_logs)
    pitcher_game_keys = {_game_key(log) for log in bullpen_pitcher_logs}
    frequency = []
    for game_window in game_windows:
        size = _valid_window_days(game_window)
        selected_games = games[:size]
        appearances = sum(1 for game in selected_games if game['game_key'] in pitcher_game_keys)
        entry = {
            'game_window': size,
            'observed_games': len(selected_games),
            'appearances': appearances,
        }
        if len(selected_games) < size:
            entry['limited'] = True
            contract['limitations'] = _merge_unique(
                contract['limitations'],
                [f'Only {len(selected_games)} observed bullpen games are available for the last-{size} count.'],
            )
        frequency.append(entry)

    recent_days = max(3, _valid_window_days(window_days) // 2)
    recent_start = end - timedelta(days=recent_days - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_count = len(_filter_logs(bullpen_pitcher_logs, start, prior_end))
    recent_count = len(_filter_logs(bullpen_pitcher_logs, recent_start, end))

    all_pitcher_dates = [
        _as_date(_value(log, 'game_date'))
        for log in pitcher_logs
        if _value(log, 'game_date') is not None
        and _as_date(_value(log, 'game_date')) <= end
        and _is_bullpen_log(log)
    ]
    last_appearance = max(all_pitcher_dates, default=None)
    days_since = (end - last_appearance).days if last_appearance else None

    state = _pitcher_usage_state(
        recent_count=recent_count,
        prior_count=prior_count,
        days_since=days_since,
    )
    if signal['start_classification_state'] == 'material_unknown':
        state = STATE_LIMITED
    contract.update({
        'state': state,
        'summary': _pitcher_usage_summary(
            pitcher_name=pitcher_name,
            frequency=frequency,
            days_since=days_since,
            state=state,
        ),
        'evidence': {
            'pitcher_id': pitcher_id,
            'pitcher_name': pitcher_name,
            'appearance_frequency': frequency,
            'window_appearances': len(bullpen_pitcher_logs),
            'excluded_starter_appearances': _starter_count(_filter_logs(pitcher_logs, start, end, bullpen_only=False)),
            'unknown_start_rows_excluded': signal['unknown_start_rows'],
            **signal,
            'prior_segment_appearances': prior_count,
            'recent_segment_appearances': recent_count,
            'appearance_count_change': recent_count - prior_count,
            'last_appearance_date': _iso(last_appearance),
            'days_since_last_appearance': days_since,
            'observed_bullpen_games': len(games),
        },
    })
    return contract


def _pitcher_usage_state(recent_count, prior_count, days_since):
    if days_since is not None and days_since >= 7:
        return STATE_IDLE
    if recent_count > prior_count:
        return STATE_ACCELERATING
    if recent_count < prior_count:
        return STATE_DECREASING
    return STATE_STABLE


def _pitcher_usage_summary(pitcher_name, frequency, days_since, state):
    name = pitcher_name or 'This pitcher'
    first = frequency[0] if frequency else None
    if days_since is not None and days_since >= 7:
        return f'{name} has no stored bullpen appearance in the last 7 days.'
    if first and first['observed_games']:
        return (
            f'{name} appeared in {first["appearances"]} of the last '
            f'{first["observed_games"]} observed bullpen games.'
        )
    if state == STATE_ACCELERATING:
        return f'{name} has more stored bullpen appearances in the recent segment.'
    if state == STATE_DECREASING:
        return f'{name} has fewer stored bullpen appearances in the recent segment.'
    return f'{name} has limited stored bullpen usage in this window.'


def _team_reference_date(team_id, reference_date=None):
    ref = _as_date(reference_date)
    if ref is not None:
        return ref
    latest = (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(Pitcher.team_id == team_id)
        .with_entities(GameLog.game_date)
        .order_by(desc(GameLog.game_date))
        .first()
    )
    return latest[0] if latest else product_current_date()


def _team_pitchers(team_id):
    return (
        Pitcher.query
        .filter(Pitcher.team_id == team_id, Pitcher.active == True)
        .order_by(Pitcher.full_name)
        .all()
    )


def _team_logs(team_id, start, end):
    return (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(
            Pitcher.team_id == team_id,
            GameLog.game_date >= start,
            GameLog.game_date <= end,
        )
        .order_by(GameLog.game_date.desc(), Pitcher.full_name)
        .all()
    )


def _pitcher_logs_through_window(pitcher_id, start, end):
    window_logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= start,
            GameLog.game_date <= end,
        )
        .order_by(GameLog.game_date.desc())
        .all()
    )
    latest_prior = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date < start,
        )
        .order_by(desc(GameLog.game_date))
        .first()
    )
    if latest_prior:
        return window_logs + [latest_prior]
    return window_logs


def build_team_workload_concentration_continuity(team_id, reference_date=None, window_days=10):
    ref = _team_reference_date(team_id, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    pitchers = _team_pitchers(team_id)
    logs = _team_logs(team_id, start, end)
    return build_workload_concentration_continuity(
        logs,
        pitchers=pitchers,
        reference_date=ref,
        window_days=window_days,
        limitations=[CURRENT_TEAM_ASSIGNMENT_LIMITATION],
    )


def build_team_bullpen_recovery_continuity(team_id, reference_date=None, window_days=14):
    ref = _team_reference_date(team_id, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    pitchers = _team_pitchers(team_id)
    logs = _team_logs(team_id, start, end)
    return build_bullpen_recovery_continuity(
        logs,
        pitchers=pitchers,
        pitcher_pool=pitchers,
        reference_date=ref,
        window_days=window_days,
        limitations=[CURRENT_TEAM_ASSIGNMENT_LIMITATION],
    )


def build_team_pitcher_usage_trend_continuity(
    team_id,
    pitcher_id,
    reference_date=None,
    window_days=10,
    game_windows=(6, 10),
):
    ref = _team_reference_date(team_id, reference_date=reference_date)
    start, end = _window_for(ref, window_days)
    pitchers = _team_pitchers(team_id)
    team_logs = _team_logs(team_id, start, end)
    pitcher_logs = _pitcher_logs_through_window(pitcher_id, start, end)
    pitcher = next((item for item in pitchers if item.id == pitcher_id), None)
    return build_pitcher_usage_trend_continuity(
        pitcher_logs,
        team_logs=team_logs,
        pitcher=pitcher,
        pitcher_id=pitcher_id,
        pitchers=pitchers,
        reference_date=ref,
        window_days=window_days,
        game_windows=game_windows,
        limitations=[CURRENT_TEAM_ASSIGNMENT_LIMITATION],
    )
