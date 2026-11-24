"""Download one retrospective MLB day to an offline fixture. No database connection."""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile

from requests import RequestException

from services.mlb_api import MLBApiClient
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import savant
from sync_v3.discovery import (active_profile_request, affiliate_directory_request, calendar_requests, competition_calendar_request, depth_directory, depth_roster_requests,
                               game_requests, pitcher_requests, roster_requests)
from sync_v3.sources import inspect_response, transport_endpoint


def capture(day, path, teams=MLB_TEAM_IDS, pitchers=(), depth_teams=(), competition=False, active_profiles=False, postseason_rounds=(), round_totals=False, statcast=False):
    if path.exists():
        raise FileExistsError(path)
    depth_teams = sorted(set(depth_teams))
    teams, pitchers = sorted(set(teams).union(depth_teams)), sorted(set(pitchers))
    client = MLBApiClient()
    requests = list(calendar_requests(day)) + list(roster_requests(day, teams))
    requests.extend(pitcher_requests(day, pitchers, postseason_rounds=postseason_rounds, round_totals=round_totals))
    if active_profiles:
        requests.extend(active_profile_request(day, team) for team in teams)
    requests.extend(affiliate_directory_request(day, club) for club in depth_teams)
    if competition:
        requests.append(competition_calendar_request(day.year))
    discovered_pitchers = set(pitchers)
    seen = set()
    failures = []
    # Stream individual provider responses; don't accumulate season-sized payloads.
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            out.write('{"responses":[')
            for request in requests:
                if request in seen:
                    continue
                endpoint = transport_endpoint(request)
                if endpoint == savant.URL:
                    try:
                        body = savant.fetch(request.params())
                    except (RequestException, ValueError) as exc:
                        failures.append(dict(endpoint=endpoint, params=request.params(), reason=type(exc).__name__,
                                             observed_at=datetime.now(timezone.utc).isoformat()))
                        continue
                else:
                    body = client._get(endpoint, params=request.params())
                at = datetime.now(timezone.utc)
                try:
                    inspect_response(request, body, at)
                except ValueError as exc:
                    if endpoint != savant.URL:
                        raise
                    # Preserve the original response. Offline admission will record its invalid receipt.
                    failures.append(dict(endpoint=endpoint, params=request.params(), reason=type(exc).__name__,
                                         observed_at=at.isoformat()))
                if request.endpoint == '/schedule' and 'startDate' in request.params():
                    games = game_requests(day, body, now=at)
                    requests.extend(games)
                    if statcast:
                        requests.extend(savant.after_final(day, games))
                elif (active_profiles and request.endpoint.endswith('/roster')
                      and request.params().get('rosterType') == 'active' and 'hydrate' not in request.params()):
                    from sync_v3.depth import _pitchers
                    team = int(request.endpoint.split('/')[2])
                    if team in teams:
                        population, reason = _pitchers(body, team, team, 'active')
                        if reason is None:
                            requests.extend(pitcher_requests(day, population.keys()-discovered_pitchers, postseason_rounds=postseason_rounds, round_totals=round_totals))
                            discovered_pitchers.update(population)
                elif request.endpoint == '/teams/affiliates':
                    requests.extend(depth_roster_requests(day, depth_directory(request, body)))
                elif request.endpoint == '/transactions':
                    for item in body['transactions']:
                        tx = client._transaction_record(item, source_endpoint='/transactions',
                                                        params=request.params())
                        touched = set((tx['from_team_id'], tx['to_team_id'])).intersection(MLB_TEAM_IDS)
                        requests.extend(roster_requests(day, touched))
                if seen:
                    out.write(',')
                json.dump({'endpoint':transport_endpoint(request),'params':request.params(),
                           'body':body,'retrieved_at':at.isoformat()}, out, separators=(',',':'))
                seen.add(request)
            out.write('],')
            meta = {'baseball_date':day.isoformat(), 'observed_at':datetime.now(timezone.utc).isoformat(),
                    'team_ids':list(teams), 'pitcher_ids':sorted(discovered_pitchers), 'depth_teams':depth_teams, 'competition':competition, 'provider':'MLB Stats API','kind':'retrospective'}
            if statcast:
                meta['statcast'] = True
                if failures:
                    meta['acquisition_failures'] = failures
                meta['providers'] = ['MLB Stats API']
                if any(request.endpoint == savant.URL for request in seen):
                    meta['providers'].append('Baseball Savant')
            if active_profiles:
                meta['active_roster_profiles'] = True
            if round_totals:
                meta['round_totals'] = True
            if postseason_rounds:
                meta['postseason_rounds'] = sorted(set(postseason_rounds))
            out.write(json.dumps(meta)[1:])
            out.flush()
            # A concurrent capture cannot overwrite an earlier successful observation.
            import os
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
            client.session.close()
    return len(seen)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('day', type=date.fromisoformat)
    parser.add_argument('output', type=Path)
    parser.add_argument('--team', action='append', type=int)
    parser.add_argument('--pitcher', action='append', type=int)
    parser.add_argument('--depth-team', action='append', type=int)
    parser.add_argument('--active-profiles', action='store_true', help='Capture dated and season pitching stats for the requested active MLB lists')
    parser.add_argument('--competition', action='store_true', help='Retain the official competitive season calendar')
    parser.add_argument('--postseason-round', choices=('F', 'D', 'L', 'W'), action='append', default=[],
                        help='Also capture pitching game logs from this playoff round for requested pitcher profiles')
    parser.add_argument('--round-totals', action='store_true', help='Also retain dated official totals for each requested postseason round')
    parser.add_argument('--statcast', action='store_true', help='Retain daily Savant pitch CSV on played Statcast-era dates')
    args = parser.parse_args()
    if args.round_totals and not args.postseason_round:
        parser.error('--round-totals requires a postseason round')
    print(f'{capture(args.day, args.output, args.team or MLB_TEAM_IDS, args.pitcher or (), args.depth_team or (), args.competition, args.active_profiles, args.postseason_round, args.round_totals, statcast=args.statcast)} official responses captured')
