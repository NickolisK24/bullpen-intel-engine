"""Append-only capture and replay; request attempts stay distinct from content identity."""

from datetime import datetime, timezone
from hashlib import sha256
import json

from psycopg2.extras import Json

from sync_v3.dependencies import consult
from sync_v3.discovery import Request
from sync_v3.queue import settle
from services.mlb_api import MlbApiError
from sync_v3.sources import inspect_response, transport_endpoint, RetainedResponse


def encode_json(body):
    return json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode()


def execute(connection, claimed, fetch, clock=lambda: datetime.now(timezone.utc), *, on_received=None):
    job_id, token, payload = claimed
    request = Request(payload['endpoint'], tuple(sorted(payload['params'].items())), 0)
    endpoint = transport_endpoint(request)
    try:
        body = fetch(endpoint, params=request.params())
    except Exception as exc:
        outcome, reason, body = 'failed', type(exc).__name__, None
    else:
        outcome, reason = 'received', None
    received_at = clock()
    if isinstance(body, RetainedResponse):
        received_at, body = body.retrieved_at, body.body
    if outcome == 'received':
        try:
            acquisition = inspect_response(request, body, received_at)
        except (ValueError, KeyError, TypeError, AttributeError, MlbApiError) as exc:
            outcome, reason = 'invalid', type(exc).__name__
    encoded = encode_json(body) if outcome != 'failed' else None
    fingerprint = sha256(encoded).hexdigest() if encoded is not None else None
    with connection, connection.cursor() as cur:
        if fingerprint:
            cur.execute("""INSERT INTO candidate.payloads VALUES (%s,%s)
                           ON CONFLICT (sha256) DO NOTHING""", (fingerprint, encoded))
        cur.execute("""INSERT INTO candidate.fetches(token,endpoint,parameters,received_at,
                       sha256,outcome,reason) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (token, request.endpoint, Json(request.params()), received_at,
                     fingerprint, outcome, reason))
        observation_id = cur.fetchone()[0]
        if outcome == 'received' and on_received:
            cur.execute('SAVEPOINT derive_from_observation')
            try:
                on_received(cur, observation_id, acquisition)
            except ValueError as exc:
                cur.execute('ROLLBACK TO SAVEPOINT derive_from_observation')
                cur.execute('INSERT INTO candidate.refusals VALUES (%s,%s)', (observation_id, str(exc)))
                outcome = 'refused'
            cur.execute('RELEASE SAVEPOINT derive_from_observation')
        settle(cur, job_id, token, clock(), error=outcome != 'received')
    return observation_id, outcome


def replay(cur, observation_id):
    cur.execute("""SELECT f.endpoint,f.parameters,f.received_at,p.encoded_json,p.sha256 FROM
                   candidate.fetches f JOIN candidate.payloads p USING (sha256)
                   WHERE f.id=%s AND f.outcome='received'""", (observation_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('Replay requires a received observation')
    endpoint, params, acquired, encoded, stored_digest = row
    consult(cur, endpoint, params, observation_id)
    if sha256(encoded).hexdigest() != stored_digest:
        raise ValueError('Payload digest mismatch')
    return inspect_response(Request(endpoint, tuple(sorted(params.items())), 0), json.loads(bytes(encoded)), acquired)


def latest_source_status(cur, endpoint, params):
    cur.execute("""SELECT f.id, f.outcome, coalesce(r.reason, f.reason) FROM candidate.fetches f
                   LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE f.endpoint=%s AND f.parameters=%s ORDER BY f.received_at DESC,f.id DESC LIMIT 1""",
                (endpoint, Json(params)))
    row = cur.fetchone()
    consult(cur, endpoint, params, row[0] if row else None)
    return row


def latest_qualified_source(cur, endpoint, params):
    row = latest_source_status(cur, endpoint, params)
    return row[0] if row and row[1] == 'received' and row[2] is None else None
