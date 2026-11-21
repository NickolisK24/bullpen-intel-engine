"""Replay a bounded acquisition cycle using local, explicitly scoped source fixtures."""

from datetime import date, datetime
import json
from pathlib import Path

from sync_v3 import canonical, evidence, history, queue
from sync_v3.cycle import run_cycle
from sync_v3.sources import RetainedResponse


class ReplayWithheld(ValueError):
    """All receipts persisted, but some candidate work remains unqualified."""


def install(owner):
    with owner, owner.cursor() as cur:
        for module in (queue, evidence, canonical, history):
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

    results = run_cycle(connection, day, lookup, teams=fixture['team_ids'], pitchers=fixture.get('pitcher_ids', ()), clock=lambda: at,
                        depth_teams=fixture.get('depth_teams', ()), competition=fixture.get('competition', False), max_jobs=256, budget='historical')
    errors = []
    with connection, connection.cursor() as cur:
        for oid, status in results:
            if status != 'received':
                cur.execute('''SELECT f.endpoint,f.parameters,coalesce(r.reason,f.reason),f.sha256
                               FROM candidate.fetches f LEFT JOIN candidate.refusals r ON r.source_id=f.id
                               WHERE f.id=%s''', (oid,))
                errors.append((status, *cur.fetchone()))
                continue
            evidence.replay(cur, oid)
        cur.execute("SELECT state,count(*) FROM candidate.jobs WHERE product_date=%s GROUP BY state", (day,))
        states = dict(cur.fetchall())
        if errors or set(states) != {'done'}:
            from sync_v3.comparison import compare_finals
            games, lines = compare_finals(cur)
            raise ReplayWithheld(f'Replay withheld: {len(results)} observations; {games} accepted finals, '
                             f'{lines} verified lines; job states={states}; unresolved={errors}')
    return len(results)
