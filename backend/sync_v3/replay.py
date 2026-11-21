"""Replay a bounded acquisition cycle using local, explicitly scoped source fixtures."""

from datetime import date, datetime
import json
from pathlib import Path

from sync_v3 import canonical, evidence, queue
from sync_v3.cycle import run_cycle
from sync_v3.sources import RetainedResponse


def install(owner):
    with owner, owner.cursor() as cur:
        for module in (queue, evidence, canonical):
            cur.execute(Path(module.__file__).with_suffix('.sql').read_text())


def run_fixture(connection, filename):
    fixture = json.loads(Path(filename).read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at'])
    if at.utcoffset() is None:
        raise ValueError('Fixture clock requires timezone')
    responses = {}
    for item in fixture['responses']:
        key = (item['endpoint'], tuple(sorted(item['params'].items())))
        if key in responses:
            raise ValueError('Duplicate response at fixture instant')
        responses[key] = RetainedResponse(item['body'], datetime.fromisoformat(item.get('retrieved_at', fixture['observed_at'])))

    def lookup(endpoint, params):
        return responses[(endpoint, tuple(sorted(params.items())))]

    results = run_cycle(connection, day, lookup, teams=fixture['team_ids'], clock=lambda: at,
                        max_jobs=256, budget='historical')
    with connection, connection.cursor() as cur:
        for oid, status in results:
            if status != 'received':
                raise ValueError(f'Unqualified fixture observation {oid}: {status}')
            evidence.replay(cur, oid)
        cur.execute("SELECT state,count(*) FROM candidate.jobs GROUP BY state")
        if cur.fetchall() != [('done', len(results))]:
            raise ValueError('Replay left unfinished obligations')
    return len(results)
