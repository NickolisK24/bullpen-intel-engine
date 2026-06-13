"""
Story-safe adapter for Bullpen Context Engine V1 evidence.

Context is supporting evidence only. It does not create observations, alter
continuity, rank teams, score stories, or infer causality.
"""

from services.bullpen_context import build_team_bullpen_context


TYPE_ROTATION_LENGTH = 'rotation_length'
TYPE_USAGE_DEMAND = 'usage_demand'

MIN_ROTATION_STARTS_PER_WINDOW = 2
MIN_ROTATION_DELTA_IP = 0.5
MIN_USAGE_TOTAL_APPEARANCES = 4
MIN_USAGE_APPEARANCE_DELTA = 2
MIN_USAGE_PITCH_DELTA = 25

FORBIDDEN_NOTE_PHRASES = (
    'algorithm',
    'model',
    'fatigue score',
    'confidence score',
    'injur',
    'il ',
    'guarantee',
    'lock',
    'prediction',
    'proves',
    'caused',
    'because of',
)


def _value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value):
    return int(_number(value, 0))


def _safe_note(note):
    if not note:
        return None
    text = str(note).strip()
    if not text:
        return None
    lower = f' {text.lower()} '
    if any(phrase in lower for phrase in FORBIDDEN_NOTE_PHRASES):
        return None
    return text


def _possessive(team_name):
    name = str(team_name or '').strip()
    if not name:
        return "This club's"
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def _plural(count, singular, plural=None):
    return singular if count == 1 else (plural or f'{singular}s')


def _context_output(team_id, context_type, note, context, contract):
    note = _safe_note(note)
    if not note:
        return None
    return {
        'team_id': team_id,
        'context_note': note,
        'context': {
            'type': context_type,
            'window_days': context.get('window_days'),
            'data_through_date': contract.get('data_through_date'),
            'evidence': context,
            'limitations': list(contract.get('limitations') or []),
        },
    }


def story_safe_rotation_length(team_id, contract):
    context = contract.get('rotation_context') or {}
    trend = context.get('trend')
    if trend not in ('shorter_outings', 'longer_outings'):
        return None

    last_starts = _count(context.get('starter_starts_last_7'))
    prev_starts = _count(context.get('starter_starts_prev_7'))
    if last_starts < MIN_ROTATION_STARTS_PER_WINDOW or prev_starts < MIN_ROTATION_STARTS_PER_WINDOW:
        return None

    delta = _number(context.get('delta_ip'))
    if abs(delta) < MIN_ROTATION_DELTA_IP:
        return None

    last_avg = _number(context.get('starter_avg_ip_last_7'))
    prev_avg = _number(context.get('starter_avg_ip_prev_7'))
    team_name = _value(contract.get('team'), 'team_name') or _value(contract.get('team'), 'team_abbreviation')
    subject = _possessive(team_name)
    days = _count(context.get('window_days')) or 7

    if trend == 'shorter_outings':
        note = (
            f'{subject} starters have averaged {last_avg:.1f} innings over the last {days} days, '
            f'down from {prev_avg:.1f} the week before, leaving more innings for the bullpen in those games.'
        )
    else:
        note = (
            f'{subject} starters have averaged {last_avg:.1f} innings over the last {days} days, '
            f'up from {prev_avg:.1f} the week before, leaving fewer innings for the bullpen in those games.'
        )

    return _context_output(team_id, TYPE_ROTATION_LENGTH, note, context, contract)


def story_safe_usage_demand(team_id, contract):
    context = contract.get('usage_demand_context') or {}
    trend = context.get('trend')
    if trend not in ('increasing_demand', 'decreasing_demand'):
        return None

    last_appearances = _count(context.get('bullpen_appearances_last_7'))
    prev_appearances = _count(context.get('bullpen_appearances_prev_7'))
    appearance_delta = _count(context.get('appearance_delta'))
    pitch_delta = _count(context.get('pitch_delta'))
    if last_appearances + prev_appearances < MIN_USAGE_TOTAL_APPEARANCES:
        return None
    if abs(appearance_delta) < MIN_USAGE_APPEARANCE_DELTA and abs(pitch_delta) < MIN_USAGE_PITCH_DELTA:
        return None

    last_pitches = _count(context.get('bullpen_pitches_last_7'))
    prev_pitches = _count(context.get('bullpen_pitches_prev_7'))
    days = _count(context.get('window_days')) or 7
    last_appearance_label = _plural(last_appearances, 'appearance')
    prev_appearance_label = _plural(prev_appearances, 'appearance')
    last_pitch_label = _plural(last_pitches, 'pitch', 'pitches')
    prev_pitch_label = _plural(prev_pitches, 'pitch', 'pitches')

    if trend == 'increasing_demand':
        note = (
            f'Recent bullpen work has picked up: {last_appearances} {last_appearance_label} '
            f'and {last_pitches} {last_pitch_label} over the last {days} days, '
            f'up from {prev_appearances} {prev_appearance_label} and {prev_pitches} {prev_pitch_label} '
            'the week before.'
        )
    else:
        note = (
            f'Recent bullpen work has eased: {last_appearances} {last_appearance_label} '
            f'and {last_pitches} {last_pitch_label} over the last {days} days, '
            f'down from {prev_appearances} {prev_appearance_label} and {prev_pitches} {prev_pitch_label} '
            'the week before.'
        )

    return _context_output(team_id, TYPE_USAGE_DEMAND, note, context, contract)


def build_team_story_context(team_id):
    contract = build_team_bullpen_context(team_id)
    by_type = {}

    rotation = story_safe_rotation_length(team_id, contract)
    if rotation:
        by_type[TYPE_ROTATION_LENGTH] = rotation

    usage = story_safe_usage_demand(team_id, contract)
    if usage:
        by_type[TYPE_USAGE_DEMAND] = usage

    if not by_type:
        return None

    primary = by_type.get(TYPE_USAGE_DEMAND) or by_type.get(TYPE_ROTATION_LENGTH)
    return {
        **primary,
        'by_type': by_type,
    }


def build_dashboard_story_context(team_ids):
    teams = {}
    limitations = []
    seen = set()
    for team_id in team_ids or []:
        if team_id is None or team_id in seen:
            continue
        seen.add(team_id)
        result = build_team_story_context(team_id)
        if result:
            teams[str(team_id)] = result

    return {
        'capability': 'bullpen_context_story_v1',
        'teams': teams,
        'limitations': limitations,
    }
