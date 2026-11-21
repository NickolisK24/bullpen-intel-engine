"""Replay archived pitcher reads over a fully evidenced, exclusively postseason workload window."""

from datetime import date, timedelta

from services.availability import ACTIVE_WINDOW_DAYS
from services.club_competition_status import COMPETITIVE_GAME_TYPES, POSTSEASON_GAME_TYPES
from services.game_finality import classify_status
from sync_v3.competition_calendar import competition_status
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.readiness import _represented_arm
from sync_v3.season_deployment import BaselineWithheld, _count, _counts
from sync_v3.rosters import roster_on
from sync_v3.workload import _game_workload


def _game_scope(game):
    return (game['gameType'], game['officialDate'], classify_status(game['status']).state,
            game['teams']['away']['team']['id'], game['teams']['home']['team']['id'])


def _compare_arm(player, splits, lines, availability, evidence):
    games = set()
    window = []
    stages = {r['game_pk']: r['round'] for r in lines if r['pitcher_mlb_id'] == player}
    try:
        for split in splits:
            day = date.fromisoformat(split['date'])
            if not availability - timedelta(days=ACTIVE_WINDOW_DAYS) <= day < availability:
                continue
            pk = split['game']['gamePk']
            if (type(pk) is not int or pk <= 0 or day.year != availability.year
                    or type(split['team']['id']) is not int or split['team']['id'] < 1):
                raise ValueError('Invalid game log identity')
            if pk in games:
                return dict(evidence, reason='duplicate_game_log_appearance')
            if pk in stages and split['gameType'] != stages[pk]:
                return dict(evidence, reason='round_and_final_disagree')
            games.add(pk)
            window.append(split)
            stats = split['stat']
            _counts(stats)
            _count(stats, 'numberOfPitches')
    except (BaselineWithheld, KeyError, TypeError, ValueError):
        return dict(evidence, reason='invalid_round_game_log')
    arm, reason = _represented_arm(player, window, lines, availability)
    if arm is None:
        return dict(evidence, reason=reason, replay=None)
    return dict(evidence, reason=None, replay=arm['arm_read'], matches=arm['arm_read'] == evidence['archived'],
                games_compared=arm['games_compared'])


def compare_postseason_arms(cur, club, through, reference):
    """Check the published arm cohort independently of eligibility and Team State selection."""
    availability = through + timedelta(days=1)
    result = dict(scope='archived_postseason_arm_reads', team=club, through=str(through),
                  availability_reference=str(availability), archive=reference.provenance,
                  current_serving_eligible=False, arms={}, sources={}, status='withheld')
    if (reference.provenance['data_through'] != str(through) or reference.membership_reference != str(through)
            or reference.availability_reference != str(availability)):
        return dict(result, reason='edition_dates_differ')
    inputs = reference.available_inputs.get(str(club))
    if not inputs:
        return dict(result, reason='archived_arm_inputs_unavailable')
    group = inputs['arm_reads']
    public_ids = [r['pitcher_id'] for r in group['records']]
    if (not public_ids or len(set(public_ids)) != len(public_ids) or sorted(public_ids) != sorted(group['member_pitcher_ids'])
            or group.get('missing_record_pitcher_ids') != []):
        return dict(result, reason='incomplete_archived_arm_inputs')
    season = competition_status(cur, availability)
    if not season['calendar_source'] or season['clubs'][club]['status'] != 'active':
        return dict(result, reason='active_competition_unconfirmed')
    roster = roster_on(cur, club, 'active', through)
    if not roster:
        return dict(result, reason='missing_dated_active_roster')
    members = {m['id'] for m in roster[0]['members'] if m['status'] == 'A' and m['position'] == '1'}
    calendar = replay(cur, season['calendar_source']).body
    expected = {s['date']: {g['gamePk']: _game_scope(g) for g in s['games']} for s in calendar['dates']}
    sources = result['sources']
    sources.update(calendar=season['calendar_source'], roster=roster[1], dates={}, decisions={})
    lines, rounds = [], set()
    for offset in range(ACTIVE_WINDOW_DAYS):
        day = through - timedelta(days=offset)
        request = calendar_requests(day)[0]
        source = latest_qualified_source(cur, request.endpoint, request.params())
        if not source or day.year != through.year:
            return dict(result, reason='missing_dated_schedule', gap_date=str(day))
        daily = {g['gamePk']: g for slate in replay(cur, source).body['dates'] for g in slate['games']
                 if g['gameType'] in COMPETITIVE_GAME_TYPES}
        if {pk: _game_scope(g) for pk, g in daily.items()} != expected.get(str(day), {}):
            return dict(result, reason='competitive_calendars_disagree', gap_date=str(day))
        sources['dates'][str(day)] = source
        for pk, game in daily.items():
            if classify_status(game['status']).state in ('postponed', 'cancelled'):
                continue
            if game['gameType'] not in POSTSEASON_GAME_TYPES or pk not in season['decision_sources']:
                return dict(result, reason='verified_postseason_final_required', game_pk=pk)
            final, gap = _game_workload(cur, game, day, source)
            if gap or final is None:
                return dict(result, reason=gap or 'missing_compatible_final', game_pk=pk)
            lines.extend(dict(line, round=game['gameType']) for line in final[0])
            rounds.add(game['gameType'])
            sources['decisions'][pk] = season['decision_sources'][pk]
    if not rounds:
        return dict(result, reason='no_verified_postseason_games')
    for row in group['records']:
        player = row['mlb_id']
        evidence = dict(archived=row['public_read'], public_id=row['pitcher_id'], game_logs={})
        result['arms'][player] = evidence
        if player not in members:
            evidence['reason'] = 'dated_active_pitcher_unconfirmed'
            continue
        splits = []
        for request in pitcher_requests(through, [player], postseason_rounds=rounds):
            kind = request.params()['gameType']
            if kind not in rounds:
                continue
            source = latest_qualified_source(cur, request.endpoint, request.params())
            if source is None:
                evidence['reason'] = 'missing_round_game_log'
                break
            evidence['game_logs'][kind] = source
            groups = replay(cur, source).body['stats']
            if groups:
                splits.extend(groups[0]['splits'])
        else:
            result['arms'][player] = _compare_arm(player, splits, lines, availability, evidence)
    matches = sum(arm.get('matches') is True for arm in result['arms'].values())
    differences = sum(arm.get('matches') is False for arm in result['arms'].values())
    return dict(result, status='compared_archived_cohort' if matches + differences else 'no_comparable_arm_reads',
                matched=matches, different=differences, withheld=len(public_ids)-matches-differences, rounds=sorted(rounds))
