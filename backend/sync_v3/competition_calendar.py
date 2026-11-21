"""Season calendar evidence for the existing club competition classifier."""

from datetime import date

from services.club_competition_status import (
    COMPETITIVE_GAME_TYPES, POSTSEASON_GAME_TYPES, SERIES_LENGTHS, historical_single_game_wild_card,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from services.schedule_ingestion import _parse_game
from sync_v3.discovery import competition_calendar_request


def calendar_games(params, body):
    year = params['season']
    if type(year) is not int or params != competition_calendar_request(year).params():
        raise ValueError('Unexpected competition calendar scope')
    if not isinstance(body.get('dates'), list) or type(body.get('totalGames')) is not int:
        raise ValueError('Incomplete competition calendar')
    games = {}
    seen_days = set()
    total = 0
    clubs = set()
    series_lengths = {}
    world_series_teams = set()
    single_game_clubs = {}
    for entry in sorted(body['dates'], key=lambda entry: entry['date']):
        day = date.fromisoformat(entry['date'])
        slate = entry['games']
        if (day.year != year or day in seen_days or not isinstance(slate, list)
                or type(entry.get('totalGames')) is not int or len(slate) != entry['totalGames']):
            raise ValueError('Inconsistent competition calendar date or count')
        seen_days.add(day)
        daily = set()
        for game in slate:
            row = _parse_game(game)
            if row is None or not isinstance(game.get('status'), dict) or not game['status'].get('detailedState'):
                raise ValueError('Missing official game status')
            pk, kind = row['game_pk'], row['game_type']
            home, away = row['home_team_id'], row['away_team_id']
            historical_wild_card = historical_single_game_wild_card(year, kind)
            if historical_wild_card:
                if type(game.get('gamesInSeries')) is not int or game['gamesInSeries'] != 1:
                    raise ValueError('Conflicting historical Wild Card format')
                for club in (home, away):
                    if single_game_clubs.setdefault(club, pk) != pk:
                        raise ValueError('Conflicting historical Wild Card games')
                if len(single_game_clubs) > 4:
                    raise ValueError('Conflicting historical Wild Card participants')
            if (type(game.get('gamePk')) is not int or pk <= 0 or pk in daily or kind not in COMPETITIVE_GAME_TYPES
                    or home not in MLB_TEAM_IDS or away not in MLB_TEAM_IDS or home == away
                    or str(game.get('season')) != str(year) or row['game_date'].year != year
                    or (kind in POSTSEASON_GAME_TYPES and not historical_wild_card and row['games_in_series'] not in SERIES_LENGTHS)):
                raise ValueError('Invalid competitive game identity or series')
            if kind in POSTSEASON_GAME_TYPES:
                series = kind, tuple(sorted((home, away)))
                if series_lengths.setdefault(series, row['games_in_series']) != row['games_in_series']:
                    raise ValueError('Conflicting playoff format')
                if kind == 'W':
                    world_series_teams.update((home, away))
                    if len(world_series_teams) > 2:
                        raise ValueError('Conflicting World Series participants')
            clubs.update((home, away))
            daily.add(pk)
            total += 1
            prior = games.get(pk)
            if prior and any(prior[1][k] != row[k] for k in ('home_team_id', 'away_team_id', 'game_type')):
                raise ValueError('Conflicting competitive game identity')
            if prior and (prior[1]['status_state'] == 'final' and row['status_state'] != 'final'
                          or kind in POSTSEASON_GAME_TYPES and prior[1]['games_in_series'] != row['games_in_series']):
                raise ValueError('Conflicting repeat game status or playoff format')
            # Retrospective makeup and resumed listings repeat the same gamePk.
            # Keep the final completion date from the later listed session.
            games[pk] = day, row, game
    if total != body['totalGames'] or clubs != set(MLB_TEAM_IDS):
        raise ValueError('Incomplete league season coverage')
    return games


def _daily_games(cur, day, schedules):
    from sync_v3.discovery import calendar_requests
    from sync_v3.evidence import latest_qualified_source, replay

    if day not in schedules:
        request = calendar_requests(day)[0]
        source = latest_qualified_source(cur, request.endpoint, request.params())
        schedules[day] = source, {
            game['gamePk']: game for slate in replay(cur, source).body['dates'] for game in slate['games']
        } if source else {}
    return schedules[day]


def _decision(cur, day, listing, schedules):
    """Require the same final in the season calendar, daily schedule and confirmed box."""
    from sync_v3.workload import _game_workload

    source, games = _daily_games(cur, day, schedules)
    daily = games.get(listing['gamePk'])
    if not daily:
        return None
    for key in ('gameType', 'officialDate', 'gamesInSeries'):
        if daily.get(key) != listing.get(key):
            return None
    for side in ('away', 'home'):
        a, b = daily['teams'][side], listing['teams'][side]
        if (a['team']['id'], a.get('score'), a.get('isWinner')) != (
                b['team']['id'], b.get('score'), b.get('isWinner')):
            return None
    final, _ = _game_workload(cur, daily, day, source)
    if not final:
        return None
    lines, receipts = final
    winners = [line['team_id'] for line in lines if line.get('win') is True]
    sides = list(daily['teams'][side] for side in ('away', 'home'))
    if any(type(side.get('score')) is not int for side in sides) or sides[0]['score'] == sides[1]['score']:
        return None
    winner, loser = sorted(sides, key=lambda side: side['score'], reverse=True)
    if winners != [winner['team']['id']] or winner.get('isWinner') is not True or loser.get('isWinner') is not False:
        return None
    return winners[0], sorted({source, *receipts})


def competition_status(cur, reference):
    """Retrospective club eligibility from retained evidence; no publication decision."""
    from services.club_competition_status import (
        BASIS_NOT_IN_POSTSEASON, ClubCompetitionStatus,
        STATUS_ACTIVE, STATUS_UNDETERMINED, classify_club_competition_status,
    )
    from sync_v3.evidence import latest_qualified_source, replay

    request = competition_calendar_request(reference.year)
    source = latest_qualified_source(cur, request.endpoint, request.params())
    games = calendar_games(request.params(), replay(cur, source).body) if source else {}
    rows, decisions, missing, receipts, schedules = [], {}, {}, {}, {}
    future_postseason = set()
    slate_source = None
    for pk, (day, row, game) in games.items():
        home, away = row['home_team_id'], row['away_team_id']
        if row['game_type'] in POSTSEASON_GAME_TYPES:
            # A retrospectively known playoff pairing cannot prove a club was active
            # before that game. It can veto a false negative from schedule absence.
            if day >= reference:
                future_postseason.update((home, away))
                if day > reference:
                    continue
                source_id, slate = _daily_games(cur, day, schedules)
                listed = _parse_game(slate.get(pk))
                keys = ('home_team_id', 'away_team_id', 'game_type', 'games_in_series', 'status_state')
                if not listed or any(listed[k] != row[k] for k in keys):
                    continue
                slate_source = source_id
            elif row['status_state'] == 'final':
                decision = _decision(cur, day, game, schedules)
                if decision:
                    decisions[pk], receipts[pk] = decision
                else:
                    missing[pk] = (home, away, row['game_type'])
        for team, opponent in ((home, away), (away, home)):
            rows.append(dict(row, game_date=day, team_id=team, opponent_team_id=opponent))
    historical_wild_cards = frozenset(pk for pk, (_, row, _) in games.items()
                                      if row['game_type'] == 'F' and row['games_in_series'] == 1)
    clubs = {}
    for team in sorted(MLB_TEAM_IDS):
        status = classify_club_competition_status(team, reference, schedule_rows=rows, winner_by_game=decisions,
                                                  historical_wild_cards=historical_wild_cards)
        if status.basis == BASIS_NOT_IN_POSTSEASON and team in future_postseason:
            status = ClubCompetitionStatus(team, STATUS_UNDETERMINED, 'postseason_participation_unresolved', reference)
        if status.status == STATUS_ACTIVE and any(
                kind == 'W' or team in (home, away) for home, away, kind in missing.values()):
            status = ClubCompetitionStatus(team, STATUS_UNDETERMINED, 'missing_official_decision', reference)
        clubs[team] = status.to_dict()
    return {'reference_date': reference.isoformat(), 'retrospective': True, 'calendar_source': source,
            'postseason_started': any(day <= reference and row['game_type'] in POSTSEASON_GAME_TYPES
                                      for day, row, _ in games.values()),
            'reference_slate_source': slate_source, 'decision_sources': receipts, 'missing_decisions': sorted(missing), 'clubs': clubs}
