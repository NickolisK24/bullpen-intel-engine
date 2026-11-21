"""One bounded candidate acquisition cycle. The caller supplies its transport."""

from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import canonical, evidence, queue, rosters
from sync_v3.discovery import calendar_requests, game_requests, roster_requests


def enqueue_requests(cur, requests, now, *, budget, day, cause=None):
    for request in requests:
        payload = {'endpoint': request.endpoint, 'params': request.params()}
        if cause is not None:
            # A queued fetch will observe the change. In-flight or completed
            # requests may have reached the provider before the new signal.
            cur.execute('''SELECT 1 FROM candidate.jobs WHERE budget=%s AND state='pending'
                           AND md5(payload::text)=md5(%s::jsonb::text) AND payload=%s
                           AND available_at<=%s LIMIT 1''', (budget, Json(payload), Json(payload), now))
            if cur.fetchone():
                continue
        # Same request in the same policy slot deduplicates across restart.
        slot = int(now.timestamp()) // request.poll_seconds
        identity = sha256(evidence.encode_json([budget, str(day), slot, request.poll_seconds, payload, cause])).hexdigest()
        queue.enqueue(cur, identity, payload, now, budget=budget, product_date=day)


def plan_children(cur, observation_id, acquisition, budget, now):
    canonical.observe(cur, observation_id, acquisition)
    affected = rosters.observe(cur, observation_id, acquisition)
    if affected:
        day = date.fromisoformat(acquisition.request.params()['endDate'])
        enqueue_requests(cur, roster_requests(day, affected), now,
                         budget=budget, day=day, cause=observation_id)
    if acquisition.request.endpoint == '/schedule':
        represented = acquisition.request.params()['startDate']
        requests = game_requests(date.fromisoformat(represented), acquisition.body,
                                 now=acquisition.retrieved_at, reconciled=canonical.recently_reconciled(
                                     cur, observation_id, acquisition.retrieved_at))
        enqueue_requests(cur, requests, now, budget=budget, day=date.fromisoformat(represented))


def schedule_request(cur, day, now, schedule):
    cur.execute("""SELECT id,outcome FROM candidate.fetches WHERE endpoint='/schedule'
                   AND parameters=%s ORDER BY received_at DESC,id DESC LIMIT 1""", (Json(schedule.params()),))
    row = cur.fetchone()
    if not row:
        return schedule
    if row[1] != 'received':
        return replace(schedule, poll_seconds=900)
    retained = evidence.replay(cur, row[0])
    requests = game_requests(day, retained.body, now=now,
                             reconciled=canonical.recently_reconciled(cur, row[0], now))
    return replace(schedule, poll_seconds=min((r.poll_seconds for r in requests),
                                             default=schedule.poll_seconds))


def run_cycle(connection, day, fetch, *, teams=MLB_TEAM_IDS, budget='current', max_jobs=32,
              clock=lambda: datetime.now(timezone.utc)):
    if type(max_jobs) is not int or not 1 <= max_jobs <= 256:
        raise ValueError('Cycle limit must be between one and 256 jobs')
    with connection, connection.cursor() as cur:
        now = clock()
        schedule, transactions = calendar_requests(day)
        if budget == 'current':
            schedule = schedule_request(cur, day, now, schedule)
        enqueue_requests(cur, (schedule, transactions, *roster_requests(day, teams)), now, budget=budget, day=day)

    receipts = []
    for _ in range(max_jobs):
        with connection, connection.cursor() as cur:
            claimed = queue.claim(cur, clock(), budget=budget, product_date=day)
        if not claimed:
            break
        receipts.append(evidence.execute(connection, claimed, fetch, clock, on_received=lambda c, oid, acquired:
                                         plan_children(c, oid, acquired, budget, clock())))
    return receipts
