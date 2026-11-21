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
    issues = [oid for oid, status in results if status != 'received']
    with connection, connection.cursor() as cur:
        for oid, status in results:
            if status == 'received':
                evidence.replay(cur, oid)
    work = read_replay_work(connection, day, capture, _issue_receipts=issues)
    states = work['job_states']
    if issues or set(states) != {'done'}:
        from sync_v3.comparison import compare_finals
        with connection, connection.cursor() as cur:
            games, lines = compare_finals(cur)
        raise ReplayWithheld(f'Replay withheld for {day} capture {capture}: {len(results)} new observations; '
                             f'{games} accepted finals and {lines} verified lines across this database; '
                             f'job states={states}; unresolved jobs with last recorded receipt (first 32)='
                             f'{json.dumps(work["jobs"], sort_keys=True)}')
    return len(results)


def read_replay_work(connection, day, capture, *, after_job_id=0, _issue_receipts=()):
    """Inspect durable historical work for one capture in a consistent read-only transaction."""
    if type(day) is not date or not isinstance(capture, str) or len(capture) != 64 or any(
            char not in '0123456789abcdef' for char in capture):
        raise ValueError('Expected an exact baseball date and SHA-256 capture identity')

    if type(after_job_id) is not int or not 0 <= after_job_id < 2**63:
        raise ValueError('Expected a nonnegative job ID')

    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT state,count(*) FROM candidate.jobs WHERE budget='historical'
                       AND product_date=%s AND payload->>'capture'=%s GROUP BY state""", (day, capture))
        states = dict(cur.fetchall())
        result = dict(baseball_date=day.isoformat(), capture=capture, job_states=states, jobs=[], next_after_job_id=None)
        if not states or (set(states) == {'done'} and not _issue_receipts):
            return result
        cur.execute("""WITH unresolved AS (
                           SELECT id,state,payload,attempts,max_attempts,available_at,lease_until,prerequisite
                           FROM candidate.jobs
                           WHERE budget='historical' AND product_date=%s AND payload->>'capture'=%s AND id>%s
                             AND (state<>'done' OR id IN (
                                 SELECT a.job_id FROM candidate.fetches f JOIN candidate.attempts a USING(token)
                                 WHERE f.id=ANY(%s::bigint[])
                             ))
                           ORDER BY id LIMIT 33
                       )
                       SELECT DISTINCT ON (j.id) j.id AS job_id,j.state,j.attempts,j.max_attempts,
                              CASE WHEN j.state='pending' THEN to_jsonb(j.available_at) END AS available_at,
                              to_jsonb(j.lease_until) AS lease_until,j.prerequisite,p.state AS prerequisite_state,
                              j.payload->>'endpoint' AS endpoint,j.payload->'params' AS parameters,
                              f.id AS receipt_id,
                              CASE WHEN r.source_id IS NOT NULL THEN 'refused' ELSE f.outcome END AS outcome,
                              coalesce(r.reason,f.reason) AS reason,f.sha256
                       FROM unresolved j LEFT JOIN candidate.jobs p ON p.id=j.prerequisite
                       LEFT JOIN candidate.attempts a ON a.job_id=j.id
                       LEFT JOIN candidate.fetches f ON f.token=a.token
                       LEFT JOIN candidate.refusals r ON r.source_id=f.id
                       ORDER BY j.id,f.id DESC NULLS LAST""", (day, capture, after_job_id, list(_issue_receipts)))
        fields = [field.name for field in cur.description]
        jobs = [dict(zip(fields, row)) for row in cur]
        result['jobs'] = jobs[:32]
        if len(jobs) > 32:
            result['next_after_job_id'] = jobs[31]['job_id']
        return result

    return history._transaction(connection, read)
