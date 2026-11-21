"""Append-only capture and replay; request attempts stay distinct from content identity."""

from datetime import datetime, timezone
from hashlib import sha256
import json

from psycopg2.extras import Json

from sync_v3.discovery import Request
from sync_v3.queue import settle
from services.mlb_api import MlbApiError
from sync_v3.sources import inspect_response, transport_endpoint


def digest(body):
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode()
    return sha256(encoded).hexdigest()


def execute(connection, claimed, fetch, clock=lambda: datetime.now(timezone.utc)):
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
    if outcome == 'received':
        try:
            inspect_response(request, body, received_at)
        except (ValueError, KeyError, TypeError, AttributeError, MlbApiError) as exc:
            outcome, reason = 'invalid', type(exc).__name__
    fingerprint = digest(body) if outcome != 'failed' else None
    with connection, connection.cursor() as cur:
        if fingerprint:
            cur.execute("""INSERT INTO candidate.payloads VALUES (%s,%s)
                           ON CONFLICT (sha256) DO NOTHING""", (fingerprint, Json(body)))
        cur.execute("""INSERT INTO candidate.fetches(token,endpoint,parameters,received_at,
                       sha256,outcome,reason) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (token, request.endpoint, Json(request.params()), received_at,
                     fingerprint, outcome, reason))
        observation_id = cur.fetchone()[0]
        settle(cur, job_id, token, clock(), error=outcome != 'received')
    return observation_id, outcome


def replay(cur, observation_id):
    cur.execute("""SELECT f.endpoint,f.parameters,f.received_at,p.body,p.sha256 FROM
                   candidate.fetches f JOIN candidate.payloads p USING (sha256)
                   WHERE f.id=%s AND f.outcome='received'""", (observation_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('Replay requires a received observation')
    endpoint, params, acquired, body, stored_digest = row
    if digest(body) != stored_digest:
        raise ValueError('Payload digest mismatch')
    return inspect_response(Request(endpoint, tuple(sorted(params.items())), 0), body, acquired)
