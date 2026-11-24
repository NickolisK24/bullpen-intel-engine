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


def schema_scripts():
    return [(module.__name__, Path(module.__file__).with_suffix('.sql').read_bytes())
            for module in (queue, evidence, canonical, history, public_identities, selection)]


def schema_digest(scripts):
    return sha256(evidence.encode_json([(name, sha256(sql).hexdigest()) for name, sql in scripts])).hexdigest()


def install(owner, *, identity_export=None, earlier_identity_exports=()):
    with owner, owner.cursor() as cur:
        scripts = schema_scripts()
        for _, sql in scripts:
            cur.execute(sql.decode('utf-8'))
        cur.execute('INSERT INTO candidate.schema_installation(singleton,digest) VALUES (true,%s)',
                    (schema_digest(scripts),))
        if identity_export is not None:
            public_identities.load_reference(cur, identity_export)
        for earlier in earlier_identity_exports:
            if (not isinstance(identity_export, public_identities.ObservedIdentityExport)
                    or not isinstance(earlier, public_identities.ObservedIdentityExport)
                    or datetime.fromisoformat(earlier.observed_at) >= datetime.fromisoformat(identity_export.observed_at)):
                raise ValueError('Supplemental identities require an earlier observed publication')
            public_identities.load_reference(cur, earlier)


def run_fixture(connection, filename, *, on_receipt_page=None, on_statcast_review=None):
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
        cur.execute("""SELECT endpoint,parameters,received_at,sha256 FROM candidate.captured_requests
                       WHERE capture=%s""", (capture,))
        retained = {(endpoint, tuple(sorted(params.items()))): (at, digest)
                    for endpoint, params, at, digest in cur}
        if retained.keys() - responses.keys():
            raise ValueError('Capture contains a request absent from the supplied fixture')
        for (endpoint, params), observation in responses.items():
            if observation.retrieved_at.utcoffset() is None:
                raise ValueError('Captured receipt requires a timezone')
            encoded = evidence.encode_json(observation.body)
            digest = sha256(encoded).hexdigest()
            previous = retained.get((endpoint, params))
            if previous is not None:
                if previous != (observation.retrieved_at, digest):
                    raise ValueError('Retained request disagrees with the supplied fixture')
                continue
            cur.execute('INSERT INTO candidate.payloads VALUES (%s,%s) ON CONFLICT DO NOTHING', (digest, encoded))
            cur.execute('''INSERT INTO candidate.captured_requests VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT DO NOTHING''',
                        (capture, endpoint, Json(dict(params)), observation.retrieved_at, digest))
            if cur.rowcount == 0:
                cur.execute("""SELECT received_at,sha256 FROM candidate.captured_requests
                               WHERE capture=%s AND endpoint=%s AND parameters=%s""",
                            (capture, endpoint, Json(dict(params))))
                if cur.fetchone() != (observation.retrieved_at, digest):
                    raise ValueError('Concurrent request disagrees with the supplied fixture')
    results = []
    while True:
        batch = run_cycle(connection, day, lookup, teams=fixture['team_ids'], pitchers=fixture.get('pitcher_ids', ()),
                          clock=lambda: at, depth_teams=fixture.get('depth_teams', ()),
                          competition=fixture.get('competition', False), postseason_rounds=fixture.get('postseason_rounds', ()),
                          statcast=fixture.get('statcast', False), round_totals=fixture.get('round_totals', False), active_roster_profiles=fixture.get('active_roster_profiles', False),
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
    if on_receipt_page is not None:
        after = 0
        while after is not None:
            page = read_replay_receipts(connection, day, capture, after_receipt_id=after)
            on_receipt_page(page)
            after = page['next_after_receipt_id']
    states = work['job_states']
    if issues or set(states) != {'done'}:
        from sync_v3.comparison import compare_finals
        with connection, connection.cursor() as cur:
            games, lines = compare_finals(cur)
        raise ReplayWithheld(f'Replay withheld for {day} capture {capture}: {len(results)} new observations; '
                             f'{games} accepted finals and {lines} verified lines across this database; '
                             f'job states={states}; unresolved jobs with last recorded receipt (first 32)='
                             f'{json.dumps(work["jobs"], sort_keys=True)}')
    if fixture.get('statcast') and on_statcast_review is not None:
        from sync_v3.savant import review_capture
        with connection, connection.cursor() as cur:
            review = review_capture(cur, capture)
        if review is not None:
            on_statcast_review(review)
    return len(results)


def read_replay_work(connection, day, capture, *, after_job_id=0, _issue_receipts=()):
    """Inspect durable historical work for one capture in a consistent read-only transaction."""
    _validate_replay_scope(day, capture, after_job_id, 'job')

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


def _validate_replay_scope(day, capture, cursor_id, kind):
    if type(day) is not date or not isinstance(capture, str) or len(capture) != 64 or any(
            char not in '0123456789abcdef' for char in capture):
        raise ValueError('Expected an exact baseball date and SHA-256 capture identity')

    if type(cursor_id) is not int or not 0 <= cursor_id < 2**63:
        raise ValueError(f'Expected a nonnegative {kind} ID')


def read_replay_receipts(connection, day, capture, *, after_receipt_id=0):
    """Trace a page of historical job receipts to their accepted canonical effects."""
    _validate_replay_scope(day, capture, after_receipt_id, 'receipt')

    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT f.id,j.id,f.endpoint,f.parameters,f.received_at,f.sha256,
                              CASE WHEN r.source_id IS NULL THEN f.outcome ELSE 'refused' END,
                              coalesce(r.reason,f.reason)
                       FROM candidate.jobs j JOIN candidate.attempts a ON a.job_id=j.id
                       JOIN candidate.fetches f ON f.token=a.token
                       LEFT JOIN candidate.refusals r ON r.source_id=f.id
                       WHERE j.budget='historical' AND j.product_date=%s AND j.payload->>'capture'=%s
                         AND f.id>%s ORDER BY f.id LIMIT 33""", (day, capture, after_receipt_id))
        page = cur.fetchall()
        receipts = {receipt: dict(receipt_id=receipt, job_id=job, endpoint=endpoint, parameters=params,
                                  observed_at=observed.isoformat(), sha256=digest, outcome=outcome,
                                  reason=reason, canonical_effects={})
                    for receipt, job, endpoint, params, observed, digest, outcome, reason in page[:32]}
        if receipts:
            cur.execute("""SELECT c.source_id,c.domain,
                                  count(*) FILTER (WHERE r.source_id=c.source_id AND r.predecessor IS NULL),
                                  count(*) FILTER (WHERE r.source_id=c.source_id AND r.predecessor IS NOT NULL),
                                  count(*) FILTER (WHERE r.source_id<>c.source_id)
                           FROM candidate.confirmations c JOIN candidate.revisions r ON r.id=c.revision_id
                           WHERE c.source_id=ANY(%s::bigint[]) GROUP BY c.source_id,c.domain
                           ORDER BY c.source_id,c.domain""", (list(receipts),))
            for receipt, domain, created, superseded, confirmed in cur:
                if receipts[receipt]['outcome'] != 'received':
                    raise ValueError('Unaccepted source receipt has canonical effects')
                receipts[receipt]['canonical_effects'][domain] = dict(
                    created=created, superseded=superseded, confirmed=confirmed)
        return dict(baseball_date=day.isoformat(), capture=capture, receipts=list(receipts.values()),
                    next_after_receipt_id=page[31][0] if len(page) > 32 else None)

    return history._transaction(connection, read)


def read_receipt_changes(connection, day, capture, receipt_id, *, after_revision_id=0):
    """Follow a scoped source receipt to canonical identities and predecessor revisions."""
    _validate_replay_scope(day, capture, after_revision_id, 'revision')
    if type(receipt_id) is not int or not 0 < receipt_id < 2**63:
        raise ValueError('Expected a positive receipt ID')

    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT f.sha256, CASE WHEN deny.source_id IS NULL THEN f.outcome ELSE 'refused' END,
                              coalesce(deny.reason,f.reason)
                       FROM candidate.fetches f LEFT JOIN candidate.refusals deny ON deny.source_id=f.id
                       JOIN candidate.attempts a ON a.token=f.token
                       JOIN candidate.jobs j ON j.id=a.job_id
                       WHERE f.id=%s AND j.budget='historical' AND j.product_date=%s
                         AND j.payload->>'capture'=%s""", (receipt_id, day, capture))
        row = cur.fetchone()
        result = dict(baseball_date=day.isoformat(), capture=capture, receipt_id=receipt_id,
                      status='unknown_receipt', changes=[], next_after_revision_id=None)
        if row is None:
            return result
        result.update(status='represented', sha256=row[0], outcome=row[1], reason=row[2])
        cur.execute("""SELECT r.id,c.domain,c.identity,r.revision,r.predecessor,r.source_id,c.context_id,
                              CASE WHEN r.source_id<>c.source_id THEN 'confirmed'
                                   WHEN r.predecessor IS NULL THEN 'created' ELSE 'superseded' END
                       FROM candidate.confirmations c JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE c.source_id=%s AND r.id>%s ORDER BY r.id LIMIT 33""",
                    (receipt_id, after_revision_id))
        changes = cur.fetchall()
        if changes and result['outcome'] != 'received':
            raise ValueError('Unaccepted source receipt has canonical effects')
        result['changes'] = [dict(revision_id=version, domain=domain, identity=identity, revision=revision,
                                  predecessor_id=parent, creating_receipt_id=source,
                                  context_receipt_id=context, effect=effect)
                             for version, domain, identity, revision, parent, source, context, effect in changes[:32]]
        if len(changes) > 32:
            result['next_after_revision_id'] = changes[31][0]
        return result

    return history._transaction(connection, read)
