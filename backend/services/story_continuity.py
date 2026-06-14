from datetime import date, datetime


CAPABILITY = 'homepage_story_continuity_v1'
LOOKBACK_DAYS = 7
FLAGSHIP_STORY_FIELDS = (
    'flagship_story',
    'homepage_flagship_story',
    'hero_story',
    'lead_story',
)
TEAM_THEMES = {'pressure', 'workload', 'recovery'}


STORY_STATUS = {
    'new': ('New Story', 'First appearance in the morning briefing.'),
    'ongoing': ('Ongoing Story', 'Observed for {days} consecutive briefing days.'),
    'returning': ('Returning Story', 'Previously observed earlier in the lookback window.'),
}


def _as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ''


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


def _payload_flagship_story(payload):
    if not isinstance(payload, dict):
        return None
    for key in FLAGSHIP_STORY_FIELDS:
        story = payload.get(key)
        if isinstance(story, dict):
            return story
    return None


def _nested_team(entry):
    team = entry.get('team') if isinstance(entry, dict) else None
    return team if isinstance(team, dict) else {}


def _team_label(entry):
    team = _nested_team(entry)
    team_identifier = (
        entry.get('team_id')
        or entry.get('teamId')
        or team.get('team_id')
        or team.get('teamId')
    )
    return (
        entry.get('team_name')
        or entry.get('teamName')
        or team.get('team_name')
        or team.get('teamName')
        or entry.get('team_abbreviation')
        or entry.get('teamAbbreviation')
        or entry.get('abbr')
        or team.get('team_abbreviation')
        or team.get('teamAbbreviation')
        or team.get('abbr')
        or (f"Team {team_identifier}" if team_identifier is not None else None)
    )


def _team_key(entry):
    team = _nested_team(entry)
    team_id = (
        entry.get('team_id')
        or entry.get('teamId')
        or team.get('team_id')
        or team.get('teamId')
    )
    if team_id is not None:
        return str(team_id)
    abbr = (
        entry.get('team_abbreviation')
        or entry.get('teamAbbreviation')
        or entry.get('abbr')
        or team.get('team_abbreviation')
        or team.get('teamAbbreviation')
        or team.get('abbr')
    )
    if abbr:
        return str(abbr).lower()
    team_name = _team_label(entry)
    return str(team_name).lower() if team_name else None


def _team_id(entry):
    team = _nested_team(entry)
    return (
        entry.get('team_id')
        or entry.get('teamId')
        or team.get('team_id')
        or team.get('teamId')
    )


def _team_abbreviation(entry):
    team = _nested_team(entry)
    return (
        entry.get('team_abbreviation')
        or entry.get('teamAbbreviation')
        or entry.get('abbr')
        or team.get('team_abbreviation')
        or team.get('teamAbbreviation')
        or team.get('abbr')
    )


def _signature(team_key, theme):
    if team_key:
        return f'team:{team_key}|theme:{theme}'
    return f'league|theme:{theme}'


def _story_candidate(entry, story_kind, theme):
    team_key = _team_key(entry)
    return {
        'signature': _signature(team_key, theme),
        'team_id': _team_id(entry) if team_key else None,
        'team_name': _team_label(entry) if team_key else None,
        'team_abbreviation': _team_abbreviation(entry) if team_key else None,
        'story_kind': story_kind,
        'theme': theme,
    }


def _theme_from_story(story):
    theme = _clean_text(story.get('theme')).lower()
    if theme:
        return theme

    kind = _clean_text(
        story.get('story_kind')
        or story.get('storyKind')
        or story.get('category')
        or story.get('family')
        or story.get('kicker')
    ).lower()
    if kind == 'team_pressure' or 'pressure' in kind or 'stress' in kind:
        return 'pressure'
    if kind == 'team_workload_continuity' or 'workload' in kind or 'watch' in kind:
        return 'workload'
    if kind == 'team_recovery' or 'recovery' in kind or 'rest' in kind:
        return 'recovery'
    if kind == 'league_check_in' or 'quiet' in kind:
        return 'quiet'
    return kind or None


def _story_kind_from_story(story, theme):
    return _clean_text(
        story.get('story_kind')
        or story.get('storyKind')
        or story.get('category')
        or story.get('family')
        or (
            {
                'pressure': 'team_pressure',
                'workload': 'team_workload_continuity',
                'recovery': 'team_recovery',
                'quiet': 'league_check_in',
            }.get(theme)
        )
    )


def _candidate_from_flagship_story(story):
    if not isinstance(story, dict):
        return None
    theme = _theme_from_story(story)
    if not theme:
        return None
    if theme in TEAM_THEMES and not _team_key(story):
        return None
    return _story_candidate(story, _story_kind_from_story(story, theme), theme)


def _workload_points(entry, story_kind):
    monitor = _as_number(entry.get('monitor'))
    total = _as_number(entry.get('total_relievers') or entry.get('total'))
    points = 0
    if total > 0:
        share = monitor / total
        if share >= 0.5:
            points = max(points, 24)
        elif share >= 0.35:
            points = max(points, 20)
        elif share >= 0.25:
            points = max(points, 14)
        elif monitor > 0:
            points = max(points, 8)
    if monitor >= 4:
        points = max(points, 22)
    elif monitor >= 3:
        points = max(points, 18)
    if 'workload' in story_kind or 'watch' in story_kind:
        points = max(points, 10)
    return points


def _stress_points(entry, story_kind):
    restricted = _as_number(entry.get('restricted'))
    total = _as_number(entry.get('total_relievers') or entry.get('total'))
    points = 0
    if total > 0:
        share = restricted / total
        if share >= 0.45:
            points = max(points, 28)
        elif share >= 0.35:
            points = max(points, 24)
        elif share >= 0.25:
            points = max(points, 18)
        elif restricted > 0:
            points = max(points, 9)
    if restricted >= 4:
        points = max(points, 26)
    elif restricted >= 3:
        points = max(points, 23)
    if 'pressure' in story_kind or 'stress' in story_kind:
        points = max(points, 12)
    return points


def _team_impact_points(entry):
    total = _as_number(entry.get('total_relievers') or entry.get('total'))
    restricted = _as_number(entry.get('restricted'))
    monitor = _as_number(entry.get('monitor'))
    available = _as_number(entry.get('available'))
    if total >= 7:
        points = 12
    elif total >= 5:
        points = 9
    elif total > 0:
        points = 6
    else:
        points = 0
    if restricted >= 3 or monitor >= 4 or available >= 6:
        points += 3
    return points


def _continuity_points(story_kind):
    if 'continuity' in story_kind:
        return 12
    if 'pressure' in story_kind:
        return 8
    return 0


def _recency_points(payload):
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    games = (payload.get('landscape') or {}).get('games') if isinstance(payload, dict) else {}
    games = games if isinstance(games, dict) else {}
    if (
        freshness.get('status') == 'current'
        or freshness.get('is_current') is True
        or freshness.get('sync_status') == 'success'
    ):
        return 14
    if freshness.get('data_through') or games.get('as_of_date') or games.get('data_state') == 'historical':
        return 11
    return 4


def _fallback_candidate_priority(entry, story_kind, payload):
    total = _as_number(entry.get('total_relievers') or entry.get('total'))
    evidence_points = 15 if total > 0 else 0
    fan_relevance_points = 5 if _team_key(entry) else 3
    return (
        _workload_points(entry, story_kind)
        + _stress_points(entry, story_kind)
        + _recency_points(payload)
        + _team_impact_points(entry)
        + _continuity_points(story_kind)
        + evidence_points
        + fan_relevance_points
    )


def _landscape_fallback_candidates(payload):
    landscape = payload.get('landscape') if isinstance(payload, dict) else {}
    landscape = landscape if isinstance(landscape, dict) else {}
    candidates = []

    def add(entry, story_kind, theme):
        if not isinstance(entry, dict):
            return
        candidate = {
            **_story_candidate(entry, story_kind, theme),
            '_fallback_priority': _fallback_candidate_priority(entry, story_kind, payload),
            '_fallback_index': len(candidates),
        }
        candidates.append(candidate)

    for entry in landscape.get('constrained_bullpens') or []:
        if int(entry.get('restricted') or 0) > 0:
            add(entry, 'team_pressure', 'pressure')
            break

    for entry in landscape.get('monitoring_concentration') or []:
        if int(entry.get('monitor') or 0) > 0:
            add(entry, 'team_workload_continuity', 'workload')
            break

    for entry in landscape.get('available_bullpens') or []:
        if int(entry.get('available') or 0) > 0:
            add(entry, 'team_recovery', 'recovery')
            break

    if not candidates:
        return [{
            'signature': _signature(None, 'quiet'),
            'team_id': None,
            'team_name': None,
            'team_abbreviation': None,
            'story_kind': 'league_check_in',
            'theme': 'quiet',
        }]

    selected = max(
        candidates,
        key=lambda candidate: (
            candidate['_fallback_priority'],
            -candidate['_fallback_index'],
        ),
    )
    return [{
        key: value
        for key, value in selected.items()
        if not key.startswith('_fallback_')
    }]


def story_continuity_candidates(payload):
    flagship_candidate = _candidate_from_flagship_story(_payload_flagship_story(payload))
    if flagship_candidate:
        return [flagship_candidate]
    return _landscape_fallback_candidates(payload)


def _prior_briefing_signatures(prior_payloads):
    days = []
    seen_dates = set()
    for payload in prior_payloads or []:
        data_through = _date_value(payload)
        if data_through is None or data_through in seen_dates:
            continue
        seen_dates.add(data_through)
        days.append({
            'data_through': data_through,
            'signatures': {
                candidate['signature']
                for candidate in story_continuity_candidates(payload)
            },
        })
    return sorted(days, key=lambda item: item['data_through'], reverse=True)


def _status_for_signature(signature, prior_days):
    if not prior_days:
        return None

    if signature in prior_days[0]['signatures']:
        # consecutive_days includes the current briefing day; the loop only
        # adds matching prior briefing days.
        consecutive = 1
        for day in prior_days:
            if signature not in day['signatures']:
                break
            consecutive += 1
        return 'ongoing', consecutive

    if any(signature in day['signatures'] for day in prior_days[1:]):
        return 'returning', None

    return 'new', None


def _status_payload(candidate, status, consecutive_days, lookback_days):
    label, template = STORY_STATUS[status]
    description = template.format(days=consecutive_days) if consecutive_days else template
    return {
        **candidate,
        'status': status,
        'label': label,
        'description': description,
        'consecutive_days': consecutive_days,
        'lookback_days': lookback_days,
    }


def build_story_continuity_payload(
    current_payload,
    prior_payloads=None,
    lookback_days=LOOKBACK_DAYS,
):
    current_date = _date_value(current_payload)
    prior_days = _prior_briefing_signatures(prior_payloads)
    current_candidates = story_continuity_candidates(current_payload)
    items = []

    for candidate in current_candidates:
        status = _status_for_signature(candidate['signature'], prior_days)
        if status is None:
            continue
        status_key, consecutive_days = status
        items.append(_status_payload(
            candidate,
            status_key,
            consecutive_days,
            lookback_days,
        ))

    return {
        'capability': CAPABILITY,
        'ranking_applied': False,
        'selection_made': False,
        'current_data_through': current_date.isoformat() if current_date else None,
        'lookback_days': lookback_days,
        'items': items,
        'limitations': [] if prior_days else ['No prior briefing snapshots are available.'],
    }
