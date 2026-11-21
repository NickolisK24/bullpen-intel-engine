"""One bounded candidate acquisition cycle. The caller supplies its transport."""

from datetime import date, datetime, timezone
from hashlib import sha256

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import canonical, evidence, queue
from sync_v3.discovery import calendar_requests, game_requests, roster_requests


def enqueue_requests(cur, requests, now, *, budget):
    for request in requests:
        payload = {'endpoint': request.endpoint, 'params': request.params()}
        # Same request in the same policy slot deduplicates across restart.
        slot = int(now.timestamp()) // request.poll_seconds
        identity = sha256(evidence.encode_json([budget, slot, request.poll_seconds, payload])).hexdigest()
        queue.enqueue(cur, identity, payload, now, budget=budget)


def run_cycle(connection, day, fetch, *, teams=MLB_TEAM_IDS, budget='current', max_jobs=32,
              clock=lambda: datetime.now(timezone.utc)):
    if type(max_jobs) is not int or not 1 <= max_jobs <= 256:
        raise ValueError('Cycle limit must be between one and 256 jobs')
    with connection, connection.cursor() as cur:
        now = clock()
        enqueue_requests(cur, (*calendar_requests(day), *roster_requests(day, teams)), now, budget=budget)

    receipts = []
    for _ in range(max_jobs):
        with connection, connection.cursor() as cur:
            claimed = queue.claim(cur, clock(), budget=budget)
        if not claimed:
            break
        def plan_children(cur, observation_id, acquisition):
            canonical.observe(cur, observation_id, acquisition)
            if acquisition.request.endpoint == '/schedule':
                represented = acquisition.request.params()['startDate']
                requests = game_requests(date.fromisoformat(represented), acquisition.body,
                                         now=acquisition.retrieved_at, reconciled=canonical.recently_reconciled(
                                             cur, observation_id, acquisition.retrieved_at))
                enqueue_requests(cur, requests, acquisition.retrieved_at, budget=budget)
        receipts.append(evidence.execute(connection, claimed, fetch, clock, on_received=plan_children))
    return receipts
