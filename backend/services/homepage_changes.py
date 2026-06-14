from datetime import date, datetime


CAPABILITY = 'homepage_bullpen_changes_v1'

LANDSCAPE_LISTS = (
    'constrained_bullpens',
    'monitoring_concentration',
    'available_bullpens',
)

COUNT_FIELDS = (
    ('restricted', 'Relievers needing rest'),
    ('monitor', 'Watch-list arms'),
    ('available', 'Rested options'),
)


def _parse_date(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _date_value(payload):
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    return _parse_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
    )


def _team_name(entry):
    return entry.get('team_name') or entry.get('team_abbreviation') or f"Team {entry.get('team_id')}"


def _entry_counts(entry):
    return {
        'available': int(entry.get('available') or 0),
        'monitor': int(entry.get('monitor') or 0),
        'restricted': int(entry.get('restricted') or 0),
        'total': int(entry.get('total_relievers') or 0),
    }


def _landscape_team_entries(payload):
    landscape = payload.get('landscape') if isinstance(payload, dict) else {}
    landscape = landscape if isinstance(landscape, dict) else {}
    teams = {}
    order = 0

    for list_name in LANDSCAPE_LISTS:
        entries = landscape.get(list_name) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            team_id = entry.get('team_id')
            if team_id is None or team_id in teams:
                continue
            teams[team_id] = {
                'team_id': team_id,
                'team_name': _team_name(entry),
                'team_abbreviation': entry.get('team_abbreviation'),
                'counts': _entry_counts(entry),
                'order': order,
            }
            order += 1

    return teams


def _team_support(payload, team_id):
    story_context = payload.get('story_context') if isinstance(payload, dict) else {}
    story_teams = story_context.get('teams') if isinstance(story_context, dict) else {}
    team_context = (
        story_teams.get(str(team_id))
        or story_teams.get(team_id)
        if isinstance(story_teams, dict)
        else None
    )
    by_type = team_context.get('by_type') if isinstance(team_context, dict) else {}
    if isinstance(by_type, dict):
        for key in ('usage_demand', 'rotation_length'):
            note = (by_type.get(key) or {}).get('context_note')
            if isinstance(note, str) and note.strip():
                return note.strip()

    continuity = payload.get('continuity') if isinstance(payload, dict) else {}
    continuity_teams = continuity.get('teams') if isinstance(continuity, dict) else {}
    team_continuity = (
        continuity_teams.get(str(team_id))
        or continuity_teams.get(team_id)
        if isinstance(continuity_teams, dict)
        else None
    )
    by_type = team_continuity.get('by_type') if isinstance(team_continuity, dict) else {}
    if isinstance(by_type, dict):
        for key in ('workload_concentration', 'workload_easing'):
            note = (by_type.get(key) or {}).get('continuity_note')
            if isinstance(note, str) and note.strip():
                return note.strip()

    return None


def _field_change_sentence(label, previous, current):
    direction = 'increased' if current > previous else 'decreased'
    return f'{label} {direction} from {previous} to {current}.'


def _fallback_why(field, previous, current):
    increased = current > previous
    if field == 'restricted':
        return (
            'More relievers now need rest after recent work than in the prior window.'
            if increased
            else 'Fewer relievers now need rest after recent work than in the prior window.'
        )
    if field == 'monitor':
        return (
            'More relievers now sit in the watch-list workload band than in the prior window.'
            if increased
            else 'Fewer relievers now sit in the watch-list workload band than in the prior window.'
        )
    if field == 'available':
        return (
            'The current board shows more rested options than the prior window.'
            if increased
            else 'The current board shows fewer rested options than the prior window.'
        )
    return 'The current bullpen picture moved from the prior window.'


def _primary_team_change(current, previous, support_note):
    candidates = []
    for order, (field, label) in enumerate(COUNT_FIELDS):
        current_value = current['counts'].get(field, 0)
        previous_value = previous['counts'].get(field, 0)
        if current_value == previous_value:
            continue
        candidates.append({
            'field': field,
            'field_label': label,
            'previous_value': previous_value,
            'current_value': current_value,
            'magnitude': abs(current_value - previous_value),
            'field_order': order,
        })

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item['magnitude'], item['field_order']))
    change = candidates[0]
    why = support_note or _fallback_why(
        change['field'],
        change['previous_value'],
        change['current_value'],
    )

    return {
        'key': f"{current['team_id']}-{change['field']}",
        'team_id': current['team_id'],
        'team_name': current['team_name'],
        'team_abbreviation': current.get('team_abbreviation'),
        'change': _field_change_sentence(
            change['field_label'],
            change['previous_value'],
            change['current_value'],
        ),
        'why_changed': why,
        'category': change['field'],
        'previous_value': change['previous_value'],
        'current_value': change['current_value'],
        '_magnitude': change['magnitude'],
        '_field_order': change['field_order'],
        '_team_order': current['order'],
    }


def _public_item(item):
    return {
        key: value for key, value in item.items()
        if not key.startswith('_')
    }


def build_homepage_changes_payload(current_payload, previous_payload, limit=3):
    current_date = _date_value(current_payload)
    previous_date = _date_value(previous_payload)
    if current_date is None or previous_date is None or previous_date >= current_date:
        return {
            'capability': CAPABILITY,
            'ranking_applied': False,
            'selection_made': False,
            'comparison': {
                'current_data_through': current_date.isoformat() if current_date else None,
                'previous_data_through': previous_date.isoformat() if previous_date else None,
            },
            'items': [],
            'limitations': ['A prior comparison window is not available.'],
        }

    current_teams = _landscape_team_entries(current_payload)
    previous_teams = _landscape_team_entries(previous_payload)
    items = []

    for team_id, current in current_teams.items():
        previous = previous_teams.get(team_id)
        if previous is None:
            continue
        item = _primary_team_change(
            current,
            previous,
            _team_support(current_payload, team_id),
        )
        if item is not None:
            items.append(item)

    items.sort(key=lambda item: (-item['_magnitude'], item['_field_order'], item['_team_order']))
    visible = [_public_item(item) for item in items[:limit]]

    return {
        'capability': CAPABILITY,
        'ranking_applied': False,
        'selection_made': False,
        'comparison': {
            'current_data_through': current_date.isoformat(),
            'previous_data_through': previous_date.isoformat(),
        },
        'items': visible,
        'limitations': [],
    }
