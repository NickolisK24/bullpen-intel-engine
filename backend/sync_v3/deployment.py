"""Describe official relief deployment in one date-bound candidate game."""

from collections import Counter, defaultdict
from datetime import timedelta
from types import SimpleNamespace

from services.play_by_play_foundation import _normalize_events
from services import role_movement
from services.game_finality import classify_status
from services.mlb_club_directory import MLB_TEAM_IDS
from services.sync import _extract_leverage_index
from services.team_board_public_deployment_context import _recorded_li, entry_from_ordered_events, movement_window_evidence
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.workload import _game_workload


def qualified_entries(game, day, lines, plays):
    """Require complete ordered plays, matching game sides, batter counts and final score."""
    if not isinstance(plays, list) or not plays:
        return None, 'missing_complete_plays'
    for index, play in enumerate(plays):
        about = play.get('about') if isinstance(play, dict) else None
        if (not isinstance(about, dict) or about.get('isComplete') is not True
                or type(about.get('atBatIndex')) is not int or about['atBatIndex'] != index):
            return None, 'incomplete_play_sequence'
        matchup = play.get('matchup')
        if (not isinstance(play.get('result'), dict) or not isinstance(matchup, dict)
                or not all(isinstance(matchup.get(key), dict) for key in ('pitcher', 'batter'))):
            return None, 'missing_play_participants_or_result'
        pitch_seen = False
        actions = play.get('playEvents', [])
        if not isinstance(actions, list):
            return None, 'invalid_play_events'
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get('details', {}), dict):
                return None, 'invalid_play_events'
            details = action.get('details', {})
            if pitch_seen and details.get('eventType') in ('pitching_substitution', 'pitching_change'):
                return None, 'pitching_change_during_plate_appearance'
            pitch_seen = pitch_seen or action.get('isPitch') is True or details.get('isScoringPlay') is True
    normalized = _normalize_events(plays, game_pk=game['gamePk'], game_date=day, game_type=game['gameType'],
                                   home_team_id=game['teams']['home']['team']['id'],
                                   away_team_id=game['teams']['away']['team']['id'],
                                   sync_run_id=None, local_pitcher_ids={})
    if normalized['status'] != 'ok':
        return None, normalized['reason']
    events = [SimpleNamespace(**event) for event in normalized['events']]
    previous_half, previous_home, previous_away = 0, 0, 0
    for index, event in enumerate(events):
        half = 2 * (event.inning - 1) + int(event.fielding_team_id == event.away_team_id)
        home, away = event.home_score_at_event, event.away_score_at_event
        if ((index == 0 and half != 0) or half not in (previous_half, previous_half + 1)
                or home < previous_home or away < previous_away
                or (home != previous_home and event.fielding_team_id == event.home_team_id)
                or (away != previous_away and event.fielding_team_id == event.away_team_id)):
            return None, 'inconsistent_play_order_or_score'
        previous_half, previous_home, previous_away = half, home, away
    counts = Counter((event.fielding_team_id, event.pitcher_mlb_id) for event in events)
    expected = {(row['team_id'], row['pitcher_mlb_id']): row['batters_faced'] for row in lines}
    if set(counts) != set(expected) or any(counts[key] != value for key, value in expected.items()):
        return None, 'play_batter_counts_differ_from_official_lines'
    final_scores = tuple(game['teams'][s].get('score') for s in ('home', 'away'))
    if (events[-1].home_score_at_event, events[-1].away_score_at_event) != final_scores:
        return None, 'final_score_mismatch'
    return {(club, pitcher): entry_from_ordered_events(pitcher, club, events)
            for club, pitcher in expected}, None


def game_deployment(cur, game_pk, day):
    result = {'game_pk': game_pk, 'baseball_date': day.isoformat(), 'sources': {},
              'relief_appearances': None, 'reason': None}
    sources = result['sources']
    schedule = calendar_requests(day)[0]
    sources['schedule'] = latest_qualified_source(cur, schedule.endpoint, schedule.params())
    if sources['schedule'] is None:
        result['reason'] = 'missing_complete_schedule'
        return result
    slate = replay(cur, sources['schedule']).body
    game = next((g for entry in slate['dates'] for g in entry['games'] if g['gamePk'] == game_pk), None)
    if game is None or game['gameType'] not in role_movement.GAME_TYPES:
        result['reason'] = 'missing_competitive_game'
        return result
    return _from_schedule(cur, game, day, sources['schedule'])


def _from_schedule(cur, game, day, schedule_source):
    game_pk = game['gamePk']
    sources = {'schedule': schedule_source}
    result = {'game_pk': game_pk, 'game_type': game['gameType'], 'baseball_date': day.isoformat(),
              'sources': sources, 'relief_appearances': None, 'reason': None}
    final, reason = _game_workload(cur, game, day, sources['schedule'])
    if final is None:
        result['reason'] = reason or 'game_without_final_work'
        return result
    lines, (sources['boxscore'], sources['final_schedule']) = final
    sources['play_by_play'] = latest_qualified_source(cur, f'/game/{game_pk}/playByPlay', {})
    box = replay(cur, sources['boxscore'])
    entries = None
    reason = 'missing_complete_plays'
    if sources['play_by_play'] is not None:
        receipt = replay(cur, sources['play_by_play'])
        if receipt.retrieved_at < box.retrieved_at:
            reason = 'plays_predate_final_boxscore'
        else:
            entries, reason = qualified_entries(game, day, lines, receipt.body['allPlays'])
    result['entry_reason'] = reason
    result['relief_appearances'] = []
    for row in lines:
        if row['games_started'] == 0:
            key = row['team_id'], row['pitcher_mlb_id']
            inning, margin = entries[key] if entries else (None, None)
            stats = box.body['teams'][row['side']]['players'][f'ID{key[1]}']['stats']['pitching']
            result['relief_appearances'].append({
                'mlb_team_id': key[0], 'mlb_player_id': key[1], 'entry_inning': inning,
                'entry_score_margin': margin,
                'entry_reason': reason or ('single_entry_unresolved' if inning is None else None),
                'leverage_index': _recorded_li(_extract_leverage_index(stats)),
                'save': row['save'], 'hold': row['hold'],
                'games_finished': row['games_finished'], 'outs': row['outs_recorded'],
            })
    return result


def club_role_movement(cur, team, through):
    """Compare two covered weeks of official relief for the game-side club."""
    if team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB club identity')
    recent_start, _, prior_start, prior_end = role_movement.window_bounds(through)
    observations = defaultdict(list)
    sources, gaps = {}, {}
    for offset in range((through - prior_start).days + 1):
        day = prior_start + timedelta(days=offset)
        represented = day.isoformat()
        schedule = calendar_requests(day)[0]
        source = latest_qualified_source(cur, schedule.endpoint, schedule.params())
        if source is None:
            gaps[represented] = ['missing_complete_schedule']
            continue
        sources[represented] = {'schedule': source, 'games': {}}
        for entry in replay(cur, source).body['dates']:
            for game in entry['games']:
                if game['gameType'] not in role_movement.GAME_TYPES:
                    continue
                if all(game['teams'][side]['team']['id'] != team for side in ('home', 'away')):
                    continue
                if classify_status(game['status']).state in ('postponed', 'cancelled'):
                    continue
                result = _from_schedule(cur, game, day, source)
                sources[represented]['games'][game['gamePk']] = {
                    **result['sources'], 'final_reason': result['reason'], 'entry_reason': result.get('entry_reason'),
                }
                if result['reason']:
                    gaps.setdefault(represented, []).append(result['reason'])
                    continue
                for arm in result['relief_appearances']:
                    if arm['mlb_team_id'] == team:
                        observations[arm['mlb_player_id']].append((
                            day, game['gameType'], arm['entry_inning'], arm['leverage_index']))
    profiles = []
    if not gaps:
        for player, rows in sorted(observations.items()):
            recent = movement_window_evidence([row[1:] for row in rows if row[0] >= recent_start],
                                              recent_start, through)
            prior = movement_window_evidence([row[1:] for row in rows if row[0] <= prior_end], prior_start, prior_end)
            profiles.append({'mlb_player_id': player, 'recent': recent, 'prior': prior,
                             **role_movement.classify_observed_role_movement(recent=recent, prior=prior)})
    return {'contract': role_movement.CONTRACT, 'mlb_team_id': team, 'through': through.isoformat(),
            'complete_game_coverage': not gaps, 'gaps': gaps, 'sources': sources, 'profiles': profiles}
