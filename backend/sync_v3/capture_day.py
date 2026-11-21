"""Download one retrospective MLB day to an offline fixture. No database connection."""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile

from services.mlb_api import MLBApiClient
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.discovery import calendar_requests, game_requests, roster_requests
from sync_v3.sources import inspect_response, transport_endpoint


def capture(day, path, teams=MLB_TEAM_IDS):
    if path.exists():
        raise FileExistsError(path)
    client = MLBApiClient()
    requests = list(calendar_requests(day)) + list(roster_requests(day, teams))
    seen = set()
    # Stream individual provider responses; don't accumulate season-sized payloads.
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            out.write('{"responses":[')
            for request in requests:
                if request in seen:
                    continue
                body = client._get(transport_endpoint(request), params=request.params())
                at = datetime.now(timezone.utc)
                inspect_response(request, body, at)
                if request.endpoint == '/schedule':
                    requests.extend(game_requests(day, body, now=at))
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
                    'team_ids':list(teams),'provider':'MLB Stats API','kind':'retrospective'}
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
    args = parser.parse_args()
    print(f'{capture(args.day, args.output, args.team or MLB_TEAM_IDS)} official responses captured')
