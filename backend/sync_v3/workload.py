"""Calculate relief workload only inside an explicitly covered baseball-date window."""

from datetime import date, timedelta
from types import SimpleNamespace

from services.game_finality import classify_status
from services.mlb_club_directory import MLB_TEAM_IDS
from services.game_shape import (
    BULLPEN_WORKLOAD_ROTATION_START, BULLPEN_WORKLOAD_UNKNOWN, bullpen_workload_appearance_class,
)
from services.public_team_relief_work import (
    RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
    RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
    _recent_usage_rest_pitcher,
    _team_workload_overview,
)
from services.workload_appearance import is_workload_appearance_log
from sync_v3.discovery import calendar_requests
from sync_v3.dependencies import consult
from sync_v3.evidence import latest_source_status, replay
from sync_v3.rosters import dated_pitcher_sources, roster_on
from sync_v3.schedule_context import missing_listings


WINDOWS = (3, 5, 7, 14, 30)


def workload_lines(final_lines):
    """Resolve official starters against the other lines on their own side."""
    sides = {}
    for facts in final_lines:
        line = dict(facts, innings_pitched_outs=facts['outs_recorded'])
        sides.setdefault(line['team_id'], []).append(line)
    for team in sides.values():
        for line in team:
            classification = bullpen_workload_appearance_class(line, team)
            if classification != BULLPEN_WORKLOAD_ROTATION_START and is_workload_appearance_log(line):
                yield dict(line, workload_class=classification)


def _game_workload(cur, game, day, schedule_source):
    status = classify_status(game['status'])
    if status.state in ('postponed', 'cancelled'):
        return None, None
    # MLB can list the same final on its original date and its resumption date.
    # Its one boxscore combines both sessions. A UTC timestamp alone cannot
    # establish the baseball date of an individual appearance.
    for timestamp, baseball_date in (('resumeDate', 'resumeGameDate'), ('resumedFrom', 'resumedFromDate')):
        represented = game.get(baseball_date)
        if (game.get(timestamp) or represented) and represented != day.isoformat():
            return None, 'resumed_game_workload_dates_unresolved'
    if not status.final_status or game['officialDate'] != day.isoformat():
        return None, 'regular_game_unresolved'
    pk = game['gamePk']
    cur.execute("""SELECT r.facts,f.id,c.context_id,f.outcome,old.revision_id,s.revision_id
                   FROM candidate.fetches f
                   LEFT JOIN candidate.confirmations c ON c.source_id=f.id
                       AND c.domain='final' AND c.identity=%s
                   LEFT JOIN candidate.revisions r ON r.id=c.revision_id
                   LEFT JOIN candidate.confirmations old ON old.source_id=c.context_id
                       AND old.domain='schedule' AND old.identity IN (c.identity,%s)
                   LEFT JOIN candidate.confirmations s ON s.source_id=%s AND
                       s.domain='schedule' AND s.identity IN (c.identity,%s)
                   WHERE f.endpoint=%s ORDER BY f.received_at DESC,f.id DESC LIMIT 1""",
                (str(pk), f'{pk}/{day}', schedule_source, f'{pk}/{day}', f'/game/{pk}/boxscore'))
    final = cur.fetchone()
    consult(cur, f'/game/{pk}/boxscore', {}, final[1] if final else None, final[2] if final else None)
    if not final or final[0] is None or final[3] != 'received' or final[4] is None or final[4] != final[5]:
        return None, 'missing_compatible_final'
    return (final[0], (final[1], final[2])), None


def _day_by_scope(cur, day, scopes):
    """Load a final once and apply its coverage to each affected scope."""
    row = latest_source_status(cur, '/schedule', calendar_requests(day)[0].params())
    if row is None or row[1] != 'received' or row[2] is not None:
        return {scope: (None, 'missing_complete_schedule') for scope in scopes}
    schedule = replay(cur, row[0])
    results = {scope: ({'lines': [], 'official_lines': [], 'series': {}, 'sources': {row[0]}}, None)
               for scope in scopes}
    present = {g['gamePk'] for entry in schedule.body['dates'] for g in entry['games']}
    missing = missing_listings(cur, schedule.request.params(), present, game_types={'R'})
    for scope in scopes:
        if scope in missing or (scope is None and missing):
            results[scope] = None, 'previous_listing_requires_absence_proof'
    for entry in schedule.body['dates']:
        for game in entry['games']:
            if game['gameType'] != 'R':
                continue
            sides = {game['teams'][side]['team']['id'] for side in ('home', 'away')}
            affected = [scope for scope in scopes if (scope is None or scope in sides)
                        and results[scope][1] is None]
            if not affected:
                continue
            final, reason = _game_workload(cur, game, day, row[0])
            if reason:
                for scope in affected:
                    results[scope] = None, reason
            elif final:
                official, sources = final
                workload = list(workload_lines(official))
                for scope in affected:
                    observed = results[scope][0]
                    observed['lines'].extend(workload)
                    observed['official_lines'].extend(official)
                    observed['sources'].update(sources)
                    observed['series'][game['gamePk']] = {
                        'number': game.get('seriesGameNumber'), 'length': game.get('gamesInSeries'),
                        'game_number': game.get('gameNumber'), 'home': game['teams']['home']['team']['id'],
                        'away': game['teams']['away']['team']['id'],
                    }
    for observed, _ in results.values():
        if observed is not None:
            observed['sources'] = sorted(observed['sources'])
    return results


def regular_day(cur, day, *, team=None):
    """Require the complete official slate and each relevant regular-season final."""
    return _day_by_scope(cur, day, (team,))[team]


def _load_calendars(cur, through, scopes):
    calendars = {scope: {} for scope in scopes}
    for offset in range(max(WINDOWS)):
        day = through - timedelta(days=offset)
        for scope, result in _day_by_scope(cur, day, scopes).items():
            calendars[scope][day] = result
    return calendars


def load_calendar(cur, through, *, team=None):
    return _load_calendars(cur, through, (team,))[team]


def load_club_calendars(cur, through):
    return _load_calendars(cur, through, sorted(MLB_TEAM_IDS))


def pitcher_windows(cur, player, through):
    return windows_from_calendar(load_calendar(cur, through), player, through,
                                 identity_sources=dated_pitcher_sources(cur, player, through))


def windows_from_calendar(slices, player, through, *, identity_sources=()):
    """All arms can reuse the same qualified calendar without another database read."""
    days = [through-timedelta(days=i) for i in range(max(WINDOWS))]
    selected_by_day = {
        day:[line for line in observed['lines'] if line['pitcher_mlb_id'] == player]
        for day,(observed,_) in slices.items() if observed
    }
    known_player = bool(identity_sources) or any(selected_by_day.values())
    result = {}
    for size in WINDOWS:
        span = days[:size]
        gaps = {day.isoformat():slices[day][1] for day in span if slices[day][1]}
        for day in span:
            if any(line['workload_class'] == BULLPEN_WORKLOAD_UNKNOWN for line in selected_by_day.get(day, ())):
                gaps[day.isoformat()] = 'workload_class_unknown'
        selected = [line for day in span for line in selected_by_day.get(day, ())]
        facts = None
        if not gaps and known_player:
            facts = {'appearances':len(selected),
                     'multi_inning':sum(row['outs_recorded']>=RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS
                                        for row in selected)}
            for field in ('pitches_thrown','batters_faced','outs_recorded'):
                values = [row[field] for row in selected]
                facts[field] = None if None in values else sum(values)
            facts['high_pitch_outings'] = None if facts['pitches_thrown'] is None else sum(
                row['pitches_thrown'] >= RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES for row in selected)
        result[size] = {'player_observed':known_player,'first':span[-1].isoformat(),
                        'through':through.isoformat(),'gaps':gaps, 'identity_sources': list(identity_sources),
                        'sources':sorted({s for day in span if not slices[day][1]
                                         for s in slices[day][0]['sources']}), 'facts':facts}
    return result


def rest_from_calendar(slices, player, through, *, identity_sources=()):
    """The Team Board's governed facts entering the next baseball date."""
    coverage, rows, classes, sources = {}, [], {}, set()
    for day, (observed, reason) in slices.items():
        complete = observed is not None
        coverage[day.isoformat()] = {
            'complete_enough_to_publish': complete,
            'reason_codes': [reason] if reason else [],
        }
        if complete:
            sources.update(observed['sources'])
            for line in observed['lines']:
                if line['pitcher_mlb_id'] == player:
                    row = SimpleNamespace(pitcher_id=player, mlb_game_pk=line['game_pk'],
                                          game_date=date.fromisoformat(line['game_date']),
                                          innings_pitched_outs=line['outs_recorded'],
                                          pitches_thrown=line['pitches_thrown'])
                    rows.append(row)
                    classes[(player, row.mlb_game_pk)] = line['workload_class']
    reference = through + timedelta(days=1)
    result = {'mlb_player_id': player, 'through': through.isoformat(),
              'reference': reference.isoformat(), 'sources': sorted(sources),
              'identity_sources': list(identity_sources), 'facts': None}
    if not rows and not identity_sources:
        return result

    # The Board helper's normal input is a seven-day ledger. Check a longer
    # absence against every intervening day before using an older outing.
    recent = [row for row in rows if row.game_date > through - timedelta(days=7)]
    carrier = _recent_usage_rest_pitcher(
        pitcher_id=player, pitcher_name=None, rows=recent, anchor=through,
        reference=reference, coverage=coverage, source_days_since=None,
        roster_state=None, classes=classes,
    )
    facts = {name: carrier[name] for name in (
        'days_since_last_appearance', 'pitched_yesterday', 'back_to_back', 'three_straight',
        'three_in_four', 'four_in_six', 'recent_multi_inning', 'high_pitch_outing',
        'last_bullpen_appearance',
    )}
    if rows and not recent:
        last = max(row.game_date for row in rows)
        span = [last + timedelta(days=i) for i in range((through-last).days+1)]
        if (all(coverage.get(d.isoformat(), {}).get('complete_enough_to_publish') for d in span)
                and all(classes[(player, row.mlb_game_pk)] != BULLPEN_WORKLOAD_UNKNOWN
                        for row in rows if row.game_date == last)):
            facts['days_since_last_appearance'] = {
                'value': (reference-last).days, 'status': 'complete', 'reason_codes': [],
                'last_appearance_date': last.isoformat(),
            }
    # The last appearance cannot be settled across a more recent unclassified outing.
    ambiguous = [row.game_date for row in rows if classes[(player, row.mlb_game_pk)] == BULLPEN_WORKLOAD_UNKNOWN]
    proven = [row.game_date for row in rows if classes[(player, row.mlb_game_pk)] != BULLPEN_WORKLOAD_UNKNOWN]
    if ambiguous and (not proven or max(ambiguous) > max(proven)):
        facts['days_since_last_appearance'] = {
            'value': None, 'status': 'unknown', 'reason_codes': ['workload_class_unknown'],
        }
    result['facts'] = facts
    return result


def team_workload(cur, calendar, team, through):
    roster = roster_on(cur, team, 'active', through)
    return team_from_calendar(calendar, team, through, roster)


def team_from_calendar(calendar, team, through, roster):
    """Attribute official relief to the game side before joining dated membership."""
    if team not in MLB_TEAM_IDS:
        raise ValueError('Team workload requires an MLB club identity')
    active = {member['id']: member for member in roster[0]['members']} if roster else {}
    rows, coverage, sources = [], {}, set()
    for day, (observed, reason) in calendar.items():
        coverage[day.isoformat()] = {
            'complete_enough_to_publish': observed is not None,
            'reason_codes': [reason] if reason else [],
        }
        if observed is None:
            continue
        sources.update(observed['sources'])
        for line in observed['official_lines']:
            if line['team_id'] != team:
                continue
            player = line['pitcher_mlb_id']
            pitcher = SimpleNamespace(id=player, full_name=active.get(player, {}).get('name'))
            log = SimpleNamespace(game_date=day, games_started=line['games_started'],
                                  batters_faced=line.get('batters_faced'),
                                  pitches_thrown=line['pitches_thrown'],
                                  innings_pitched_outs=line['outs_recorded'])
            rows.append((log, pitcher))
    facts = _team_workload_overview(rows, through, coverage, active.keys(),
                                    window_days=WINDOWS, include_batters_faced=True)
    facts['contract'] = 'candidate_club_relief_workload_v1'
    concentration = facts['concentration_7_day']
    # A dated MLB active roster includes starters and position players. The
    # frozen Board bullpen cohort is a downstream publication dependency.
    for item in concentration['contributors']:
        active_on_date = item.pop('current_active')
        item['on_dated_active_roster'] = active_on_date if roster else None
    for old, new in (
        ('active_current_contribution', 'on_dated_active_roster_contribution'),
        ('off_active_contribution', 'off_dated_active_roster_contribution'),
    ):
        split = concentration.pop(old)
        concentration[new] = split if roster else None
    return {'mlb_team_id': team, 'player_id_namespace': 'mlb',
            'roster_source': roster[1] if roster else None,
            'workload_sources': sorted(sources), 'facts': facts}


def outing_pitch_comparison(calendar, player, through):
    """Compare the latest single outing with previous outings in the same 30 days."""
    first = through - timedelta(days=29)
    result = {'contract': 'candidate_outing_pitch_comparison_v1', 'mlb_player_id': player,
              'start': first.isoformat(), 'through': through.isoformat(), 'facts': None,
              'sources': [], 'reason': None}
    outings = []
    sources = set()
    for offset in range(30):
        day = first + timedelta(days=offset)
        observed, gap = calendar.get(day, (None, 'missing_complete_schedule'))
        if observed is None:
            result['reason'] = gap
            return result
        sources.update(observed['sources'])
        outings.extend((day, line) for line in observed['lines'] if line['pitcher_mlb_id'] == player)
    result['sources'] = sorted(sources)
    if not outings:
        result['reason'] = 'no_observed_workload_appearance'
        return result
    last = outings[-1][0]
    prior = [line for day, line in outings if day < last]
    latest = [line for day, line in outings if day == last]
    if any(line['workload_class'] == BULLPEN_WORKLOAD_UNKNOWN for _, line in outings):
        result['reason'] = 'workload_class_unknown'
    elif len(latest) != 1:
        result['reason'] = 'latest_outing_order_unknown'
    elif not prior:
        result['reason'] = 'no_prior_outings_in_window'
    elif any(line['pitches_thrown'] is None for _, line in outings):
        result['reason'] = 'pitch_count_unknown'
    else:
        pitches = latest[0]['pitches_thrown']
        prior_counts = [line['pitches_thrown'] for line in prior]
        result['facts'] = {
            'last_outing_date': last.isoformat(), 'last_game_pk': latest[0]['game_pk'],
            'last_outing_pitches': pitches, 'prior_outings': len(prior),
            'prior_total_pitches': sum(prior_counts), 'prior_max_pitches': max(prior_counts),
            'difference_from_prior_max': pitches - max(prior_counts),
        }
    return result
