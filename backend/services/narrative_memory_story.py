"""
Story-safe continuity adapter for Narrative Memory V1 evidence.

This module does not persist stories or infer story threads. It translates
stored-workload continuity contracts into conservative output that story
surfaces may attach when the evidence is strong enough.
"""

from services.narrative_memory import (
    STATE_ACCELERATING,
    STATE_CONCENTRATED,
    STATE_DECREASING,
    STATE_IDLE,
    STATE_WORKLOAD_EASING,
    build_team_bullpen_recovery_continuity,
    build_team_workload_concentration_continuity,
)


TYPE_WORKLOAD_CONCENTRATION = 'workload_concentration'
TYPE_WORKLOAD_EASING = 'workload_easing'
TYPE_PITCHER_USAGE_TREND = 'pitcher_usage_trend'

MIN_STORY_CONCENTRATION_APPEARANCES = 6
MIN_STORY_OBSERVED_GAMES = 4
MIN_STORY_EASING_SIGNALS = 2

FORBIDDEN_NOTE_PHRASES = (
    'narrative memory',
    'algorithm',
    'model',
    'fatigue score',
    'confidence score',
    'injur',
    'health',
    'manager trust',
    'closer',
    'same story',
    'same-story',
    'developing for',
)


def _pct_label(value):
    return f'{round(float(value or 0) * 100)}%'


def _appearance_word(count):
    return 'appearance' if count == 1 else 'appearances'


def _safe_note(note):
    if not note:
        return None
    text = str(note).strip()
    if not text:
        return None
    lower = text.lower()
    if any(phrase in lower for phrase in FORBIDDEN_NOTE_PHRASES):
        return None
    return text


def _contract_output(team_id, continuity_type, note, contract):
    note = _safe_note(note)
    if not note:
        return None
    return {
        'team_id': team_id,
        'continuity_note': note,
        'continuity': {
            'type': continuity_type,
            'window_days': contract.get('window_days'),
            'window_start': contract.get('window_start'),
            'window_end': contract.get('window_end'),
            'data_through_date': contract.get('data_through_date'),
            'evidence': contract.get('evidence') or {},
            'limitations': list(contract.get('limitations') or []),
        },
    }


def _pitcher_label(row):
    return row.get('pitcher_name') or f"Pitcher {row.get('pitcher_id')}"


def story_safe_workload_concentration(team_id, contract):
    evidence = contract.get('evidence') or {}
    total = int(evidence.get('bullpen_appearances') or 0)
    observed_games = int(evidence.get('observed_bullpen_games') or 0)
    if contract.get('state') != STATE_CONCENTRATED:
        return None
    if total < MIN_STORY_CONCENTRATION_APPEARANCES:
        return None
    if observed_games < MIN_STORY_OBSERVED_GAMES:
        return None

    top_two = evidence.get('top_two_pitchers') or []
    top_two_share = float(evidence.get('top_two_appearance_share') or 0)
    core_share = float(evidence.get('core_arm_appearance_share') or 0)
    top_two_appearances = sum(int(row.get('appearances') or 0) for row in top_two)

    if len(top_two) >= 2 and top_two_share >= 0.6:
        first, second = _pitcher_label(top_two[0]), _pitcher_label(top_two[1])
        note = (
            f'{first} and {second} handled {top_two_appearances} of {total} '
            f'bullpen {_appearance_word(total)} over the last {contract["window_days"]} days.'
        )
    elif core_share >= 0.6:
        note = (
            f'The same core relievers have carried {_pct_label(core_share)} '
            f'of the bullpen work over the last {contract["window_days"]} days.'
        )
    else:
        return None

    return _contract_output(team_id, TYPE_WORKLOAD_CONCENTRATION, note, contract)


def story_safe_workload_easing(team_id, contract):
    evidence = contract.get('evidence') or {}
    prior = evidence.get('prior_segment') or {}
    recent = evidence.get('recent_segment') or {}
    signal_count = int(evidence.get('workload_easing_signal_count') or 0)

    if contract.get('state') != STATE_WORKLOAD_EASING:
        return None
    if signal_count < MIN_STORY_EASING_SIGNALS:
        return None
    if int(prior.get('appearances') or 0) <= 0 or int(recent.get('appearances') or 0) <= 0:
        return None

    prior_rested = int(prior.get('rested_options') or 0)
    recent_rested = int(recent.get('rested_options') or 0)
    prior_appearances = int(prior.get('appearances') or 0)
    recent_appearances = int(recent.get('appearances') or 0)
    if recent_rested > prior_rested and recent_appearances < prior_appearances:
        note = (
            f'Bullpen flexibility has improved over the last {contract["window_days"]} days: '
            f'rested options rose from {prior_rested} to {recent_rested}, while recent '
            f'appearances dropped from {prior_appearances} to {recent_appearances}.'
        )
    elif recent_appearances < prior_appearances:
        note = (
            f'The workload has eased over the last {contract["window_days"]} days, with '
            f'recent appearances dropping from {prior_appearances} to {recent_appearances}.'
        )
    elif recent_rested > prior_rested:
        note = (
            f'The bullpen has more usable arms than earlier in the window, with rested '
            f'options rising from {prior_rested} to {recent_rested}.'
        )
    else:
        return None

    return _contract_output(team_id, TYPE_WORKLOAD_EASING, note, contract)


def story_safe_pitcher_usage_trend(team_id, contract):
    evidence = contract.get('evidence') or {}
    state = contract.get('state')
    frequency = evidence.get('appearance_frequency') or []
    first = frequency[0] if frequency else {}
    observed_games = int(first.get('observed_games') or 0)
    appearances = int(first.get('appearances') or 0)
    pitcher_name = evidence.get('pitcher_name') or 'This reliever'

    if state == STATE_IDLE and evidence.get('days_since_last_appearance') is not None:
        days = int(evidence.get('days_since_last_appearance'))
        note = f'{pitcher_name} has no stored bullpen appearance in the last {days} days.'
    elif state == STATE_ACCELERATING and observed_games >= 4 and appearances >= 3:
        note = f'{pitcher_name} has appeared in {appearances} of the last {observed_games} observed bullpen games.'
    elif state == STATE_DECREASING and observed_games >= 4:
        note = (
            f'{pitcher_name} has been used less often lately, with '
            f'{appearances} appearances in the last {observed_games} observed bullpen games.'
        )
    else:
        return None

    return _contract_output(team_id, TYPE_PITCHER_USAGE_TREND, note, contract)


def build_team_story_continuity(team_id):
    by_type = {}

    concentration = story_safe_workload_concentration(
        team_id,
        build_team_workload_concentration_continuity(team_id, window_days=10),
    )
    if concentration:
        by_type[TYPE_WORKLOAD_CONCENTRATION] = concentration

    easing = story_safe_workload_easing(
        team_id,
        build_team_bullpen_recovery_continuity(team_id, window_days=14),
    )
    if easing:
        by_type[TYPE_WORKLOAD_EASING] = easing

    if not by_type:
        return None

    primary = (
        by_type.get(TYPE_WORKLOAD_CONCENTRATION)
        or by_type.get(TYPE_WORKLOAD_EASING)
    )
    return {
        **primary,
        'by_type': by_type,
    }


def build_dashboard_story_continuity(team_ids):
    teams = {}
    limitations = []
    seen = set()
    for team_id in team_ids or []:
        if team_id is None or team_id in seen:
            continue
        seen.add(team_id)
        result = build_team_story_continuity(team_id)
        if result:
            teams[str(team_id)] = result

    return {
        'capability': 'bullpen_continuity_v1',
        'teams': teams,
        'limitations': limitations,
    }
