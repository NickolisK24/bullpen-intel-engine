"""Replay a bounded acquisition cycle using local, explicitly scoped source fixtures."""

from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path

from psycopg2.extras import Json

from sync_v3 import canonical, evidence, history, public_identities, queue, selection
from sync_v3.cycle import run_cycle
from sync_v3.sources import RetainedResponse


class ReplayWithheld(ValueError):
    """All receipts persisted, but some candidate work remains unqualified."""


def install(owner, *, identity_export=None, earlier_identity_exports=()):
    with owner, owner.cursor() as cur:
        for module in (queue, evidence, canonical, history, public_identities, selection):
            cur.execute(Path(module.__file__).with_suffix('.sql').read_text())
        if identity_export is not None:
            public_identities.load_reference(cur, identity_export)
        for earlier in earlier_identity_exports:
            if (not isinstance(identity_export, public_identities.ObservedIdentityExport)
                    or not isinstance(earlier, public_identities.ObservedIdentityExport)
                    or datetime.fromisoformat(earlier.observed_at) >= datetime.fromisoformat(identity_export.observed_at)):
                raise ValueError('Supplemental identities require an earlier observed publication')
            public_identities.load_reference(cur, earlier)


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

    capture = sha256(evidence.encode_json(fixture)).hexdigest()
    # Preserve every supplied HTTP observation, including child roster requests
    # whose transaction parent is refused. The archive grants no canonical authority.
    with connection, connection.cursor() as cur:
        for (endpoint, params), observation in responses.items():
            if observation.retrieved_at.utcoffset() is None:
                raise ValueError('Captured receipt requires a timezone')
            encoded = evidence.encode_json(observation.body)
            digest = sha256(encoded).hexdigest()
            cur.execute('INSERT INTO candidate.payloads VALUES (%s,%s) ON CONFLICT DO NOTHING', (digest, encoded))
            cur.execute('''INSERT INTO candidate.captured_requests VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT DO NOTHING''',
                        (capture, endpoint, Json(dict(params)), observation.retrieved_at, digest))
    results = []
    while True:
        batch = run_cycle(connection, day, lookup, teams=fixture['team_ids'], pitchers=fixture.get('pitcher_ids', ()),
                          clock=lambda: at, depth_teams=fixture.get('depth_teams', ()),
                          competition=fixture.get('competition', False), postseason_rounds=fixture.get('postseason_rounds', ()),
                          round_totals=fixture.get('round_totals', False), active_roster_profiles=fixture.get('active_roster_profiles', False),
                          max_jobs=256, budget='historical', capture=capture)
        results.extend(batch)
        if len(batch) < 256:
            break
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
        cur.execute("SELECT state,count(*) FROM candidate.jobs WHERE product_date=%s AND payload->>'capture'=%s GROUP BY state", (day,capture))
        states = dict(cur.fetchall())
        if errors or set(states) != {'done'}:
            from sync_v3.comparison import compare_finals
            games, lines = compare_finals(cur)
            raise ReplayWithheld(f'Replay withheld: {len(results)} observations; {games} accepted finals, '
                             f'{lines} verified lines; job states={states}; unresolved={errors}')
    return len(results)
