from datetime import date, datetime


CAPABILITY = 'homepage_story_continuity_v1'
LOOKBACK_DAYS = 7


STORY_STATUS = {
    'new': ('New Story', 'First appearance in the morning briefing.'),
    'ongoing': ('Ongoing Story', 'Observed for {days} consecutive briefing days.'),
    'returning': ('Returning Story', 'Previously observed earlier in the lookback window.'),
}


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


def _team_label(entry):
    return entry.get('team_name') or entry.get('team_abbreviation') or f"Team {entry.get('team_id')}"


def _team_key(entry):
    team_id = entry.get('team_id')
    if team_id is not None:
        return str(team_id)
    abbr = entry.get('team_abbreviation')
    if abbr:
        return str(abbr).lower()
    return str(_team_label(entry)).lower()


def _signature(team_key, theme):
    if team_key:
        return f'team:{team_key}|theme:{theme}'
    return f'league|theme:{theme}'


def _story_candidate(entry, story_kind, theme):
    return {
        'signature': _signature(_team_key(entry), theme),
        'team_id': entry.get('team_id'),
        'team_name': _team_label(entry),
        'team_abbreviation': entry.get('team_abbreviation'),
        'story_kind': story_kind,
        'theme': theme,
    }


def story_continuity_candidates(payload):
    landscape = payload.get('landscape') if isinstance(payload, dict) else {}
    landscape = landscape if isinstance(landscape, dict) else {}
    candidates = []
    seen = set()

    def add(entry, story_kind, theme):
        if not isinstance(entry, dict):
            return
        candidate = _story_candidate(entry, story_kind, theme)
        if candidate['signature'] in seen:
            return
        seen.add(candidate['signature'])
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
        candidates.append({
            'signature': _signature(None, 'quiet'),
            'team_id': None,
            'team_name': None,
            'team_abbreviation': None,
            'story_kind': 'league_check_in',
            'theme': 'quiet',
        })

    return candidates


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
