"""Choose the workload and availability dates from retained MLB schedules."""
from datetime import timedelta

from sync_v3 import evidence
from sync_v3.competition_calendar import calendar_games, competition_status
from sync_v3.discovery import competition_calendar_request
from sync_v3.generation import _slate, generation_date_decision


def workload_cutoff(games, day, *, after_finals):
    """An unfinished slate cannot advance the published workload date."""
    eligible = {played for played, row, _ in games.values()
                if played < day and row['status_state'] == 'final'}
    today = [row['status_state'] for played, row, _ in games.values() if played == day]
    if after_finals and 'final' in today and all(s in ('final', 'postponed', 'cancelled') for s in today):
        eligible.add(day)
    if not eligible:
        raise ValueError('No confirmed competitive workload date for the requested edition')
    return max(eligible)


def edition_scope(cur, day, *, after_finals=False):
    competition = competition_status(cur, day)
    if not competition['calendar_source'] or len(competition['clubs']) != 30:
        raise ValueError('Incomplete league competition inventory')
    request = competition_calendar_request(day.year)
    season = calendar_games(request.params(), evidence.replay(cur, competition['calendar_source']).body)
    through = workload_cutoff(season, day, after_finals=after_finals)
    slate, _ = _slate(cur, through)
    if slate['reason'] or not slate['games'] or not any(g['final'] for g in slate['games']):
        raise ValueError('Daily schedule does not confirm the workload cutoff')
    if any(not game['final'] and game['status'] not in ('postponed', 'cancelled') for game in slate['games']):
        raise ValueError('Workload slate still contains an unsettled game')
    daily_finals = {game['game_pk'] for game in slate['games'] if game['final']}
    calendar_finals = {pk for pk, (played, row, _) in season.items()
                       if played == through and row['status_state'] == 'final'}
    if daily_finals != calendar_finals:
        raise ValueError('Daily and season calendars disagree on completed games at the cutoff')
    as_of = day + timedelta(days=1) if day == through else day
    dates = generation_date_decision(cur, through, as_of)
    if dates['status'] != 'aligned':
        raise ValueError(f"Workload and availability dates are unresolved: {dates['reason']}")
    offseason = all(club['status'] == 'season_complete' for club in competition['clubs'].values())
    return dict(day=day, as_of=as_of, through=through, availability=dates['availability_reference'],
                offseason=offseason, decisions_missing=competition['missing_decisions'])


def prepare(source, worker_password, day, *, after_finals=False, budget_seconds=100):
    from contextlib import closing
    from services.mlb_api import MLBApiClient
    from sync_v3.discovery import calendar_requests
    from sync_v3.staging_postseason import qualify_offseason_edition
    from sync_v3.staging_publication_target import acquire_window_source, advance_private_generation

    season = competition_calendar_request(day.year)
    client = MLBApiClient()
    with closing(client.session):
        calendar = acquire_window_source(source, client, day, season.endpoint, season.params())
        with source, source.cursor() as cur:
            games = calendar_games(season.params(), evidence.replay(cur, calendar).body)
        cutoff = workload_cutoff(games, day, after_finals=after_finals)
        for played in {cutoff, day}:
            request = calendar_requests(played)[0]
            acquire_window_source(source, client, played, request.endpoint, request.params())

    with source, source.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        scope = edition_scope(cur, day, after_finals=after_finals)
    if scope['offseason']:
        result = qualify_offseason_edition(source, day)
        digest, decision = result['generation'], result['decision']
    else:
        result = advance_private_generation(worker_password, workload_day=scope['through'],
                                            as_of=scope['as_of'], budget_seconds=budget_seconds)
        digest = result.get('digest')
        review = result.get('review')
        decision = review.get('status') if isinstance(review, dict) else review or 'withheld'
    return dict(day=str(day), through=str(scope['through']), availability=scope['availability'],
                mode='offseason' if scope['offseason'] else 'competitive', generation=digest,
                decision=decision, ready=bool(digest) and decision in ('season_complete_withholding', 'core_comparison_complete'),
                source_review=result)
