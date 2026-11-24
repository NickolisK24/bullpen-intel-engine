"""One bounded candidate acquisition cycle. The caller supplies its transport."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256

from psycopg2.extras import Json

from services.game_ingestion_planner import DEFAULT_CORRECTION_HORIZON_DAYS
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import canonical, evidence, queue, rosters, savant
from sync_v3.discovery import (active_pitcher_ids, active_profile_request, affiliate_directory_request, calendar_requests, competition_calendar_request, depth_directory, depth_roster_requests,
                               game_requests, pitcher_requests, roster_requests)


def _continuation(request, policy):
    # Only parents carry optional child-discovery instructions across a restart.
    if request.endpoint == '/transactions':
        return {k: v for k, v in policy.items() if k != 'statcast'}
    if request.endpoint == '/schedule' and 'startDate' in request.params():
        return {'statcast': True} if policy.get('statcast') else {}
    if request.params().get('rosterType') == 'active' and 'hydrate' not in request.params():
        for team in policy.get('profile_teams', ()):
            if request.endpoint == f'/teams/{team}/roster':
                return dict(profile_teams=[team], rounds=policy['rounds'], round_totals=policy['round_totals'])
    return {}


def enqueue_requests(cur, requests, now, *, budget, day, cause=None, capture=None, policy=None):
    for request in requests:
        payload = {'endpoint': request.endpoint, 'params': request.params()}
        if policy is not None:
            payload['continuation'] = _continuation(request, policy)
        if capture is not None:
            payload['capture'] = capture
        if capture is None and cause is not None:
            # A queued fetch will observe the change. In-flight or completed
            # requests may have reached the provider before the new signal.
            cur.execute('''SELECT 1 FROM candidate.jobs WHERE budget=%s AND state='pending'
                           AND md5(payload::text)=md5(%s::jsonb::text) AND payload=%s
                           AND available_at<=%s LIMIT 1''', (budget, Json(payload), Json(payload), now))
            if cur.fetchone():
                continue
        # Same request in the same policy slot deduplicates across restart.
        slot = int(now.timestamp()) // request.poll_seconds
        key = [budget, str(day), payload] if capture else [budget, str(day), slot, request.poll_seconds, payload, cause]
        identity = sha256(evidence.encode_json(key)).hexdigest()
        queue.enqueue(cur, identity, payload, now, budget=budget, product_date=day)


def plan_children(cur, observation_id, acquisition, budget, now, day, *, capture=None, statcast=False, policy=None):
    if acquisition.request.endpoint == savant.URL:
        return
    if acquisition.request.endpoint == '/schedule' and 'season' in acquisition.request.params():
        # A retrospective season listing cannot revise the one-day final/schedule authority.
        return
    canonical.observe(cur, observation_id, acquisition, day)
    affected = rosters.observe(cur, observation_id, acquisition, replay_batch=capture is not None)
    if affected:
        day = date.fromisoformat(acquisition.request.params()['endDate'])
        enqueue_requests(cur, roster_requests(day, affected), now,
                         budget=budget, day=day, cause=observation_id, capture=capture, policy=policy)
    if acquisition.request.endpoint == '/teams/affiliates':
        directory = depth_directory(acquisition.request, acquisition.body)
        enqueue_requests(cur, depth_roster_requests(day, directory), now, budget=budget, day=day, capture=capture, policy=policy)
    if acquisition.request.endpoint == '/schedule':
        represented = acquisition.request.params()['startDate']
        requests = game_requests(date.fromisoformat(represented), acquisition.body,
                                 now=acquisition.retrieved_at, reconciled=() if capture else canonical.recently_reconciled(
                                     cur, observation_id, acquisition.retrieved_at))
        if statcast:
            requests = (*requests, *savant.after_final(date.fromisoformat(represented), requests))
        enqueue_requests(cur, requests, now, budget=budget, day=date.fromisoformat(represented), capture=capture, policy=policy)


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


def enqueue_prior_schedule(cur, previous, now, *, overnight):
    """Revisit a retained current-worker slate for overnight finality or an overdue final audit."""
    schedule, _ = calendar_requests(previous)
    cur.execute("""SELECT f.id,j.payload->'continuation' FROM candidate.fetches f
                   JOIN candidate.attempts a ON a.token=f.token
                   JOIN candidate.jobs j ON j.id=a.job_id
                   WHERE f.endpoint='/schedule' AND f.parameters=%s AND f.outcome='received'
                     AND NOT EXISTS (SELECT 1 FROM candidate.refusals r WHERE r.source_id=f.id)
                     AND j.budget='current' AND j.product_date=%s AND j.payload ? 'continuation'
                   ORDER BY f.received_at DESC,f.id DESC LIMIT 1""", (Json(schedule.params()), previous))
    row = cur.fetchone()
    if row is None:
        return
    observation = evidence.replay(cur, row[0])
    requests = game_requests(previous, observation.body, now=now,
                             reconciled=canonical.recently_reconciled(cur, row[0], now))
    polls = [request.poll_seconds for request in requests
             if request.endpoint.endswith('/boxscore') or (overnight and request.endpoint.endswith('/feed/live'))]
    if polls:
        enqueue_requests(cur, (replace(schedule, poll_seconds=min(polls)),), now,
                         budget='current', day=previous, policy=row[1])


def run_cycle(connection, day, fetch, *, teams=MLB_TEAM_IDS, pitchers=(), depth_teams=(), competition=False, postseason_rounds=(), round_totals=False, active_roster_profiles=False, statcast=False, budget='current', max_jobs=32,
              clock=lambda: datetime.now(timezone.utc), capture=None):
    if capture is not None and budget != 'historical':
        raise ValueError('A captured batch requires the historical budget')
    if type(max_jobs) is not int or not 1 <= max_jobs <= 256:
        raise ValueError('Cycle limit must be between one and 256 jobs')
    with connection, connection.cursor() as cur:
        now = clock()
        schedule, transactions = calendar_requests(day)
        if budget == 'current':
            schedule = schedule_request(cur, day, now, schedule)
            for age in range(1, DEFAULT_CORRECTION_HORIZON_DAYS + 1):
                enqueue_prior_schedule(cur, day - timedelta(days=age), now, overnight=age == 1)
        depth_teams = sorted(set(depth_teams))
        profile_teams = set(teams).union(depth_teams)
        postseason_rounds = tuple(postseason_rounds)
        requests = (schedule, transactions, *roster_requests(day, profile_teams), *pitcher_requests(day, pitchers, postseason_rounds=postseason_rounds, round_totals=round_totals))
        if active_roster_profiles:
            requests += tuple(active_profile_request(day, team) for team in sorted(profile_teams))
        if competition:
            requests += (competition_calendar_request(day.year),)
        requests += tuple(affiliate_directory_request(day, club) for club in depth_teams)
        requested_policy = dict(statcast=statcast)
        if active_roster_profiles:
            requested_policy.update(profile_teams=sorted(profile_teams), rounds=sorted(set(postseason_rounds)),
                                    round_totals=round_totals)
        enqueue_requests(cur, requests, now, budget=budget, day=day, capture=capture,
                         policy=requested_policy if budget == 'current' else None)

    def derive(cur, receipt, acquisition):
        now = clock()
        plan_children(cur, receipt, acquisition, budget, now, origin, capture=capture,
                      statcast=options.get('statcast', False), policy=options if budget == 'current' else None)
        if options.get('profile_teams') and capture is None and acquisition.request.endpoint.endswith('/roster'):
            players = active_pitcher_ids(origin, options['profile_teams'], acquisition.request, acquisition.body)
            requests = pitcher_requests(origin, players, postseason_rounds=options['rounds'], round_totals=options['round_totals'])
            enqueue_requests(cur, requests, now, budget=budget, day=origin, policy=options)

    receipts = []
    for claim_index in range(max_jobs):
        with connection, connection.cursor() as cur:
            origin = day
            instant = clock()
            # Alternate with normal queue order so roster and transaction work keeps progressing.
            prefer_games = budget == 'current' and claim_index % 2 == 1
            claimed = queue.claim(cur, instant, budget=budget, product_date=day, capture=capture,
                                  prefer_game_updates=prefer_games)
            if not claimed and budget == 'current':
                claimed = queue.claim(cur, instant, budget=budget, before_product_date=day)
                if claimed:
                    cur.execute('SELECT product_date FROM candidate.jobs WHERE id=%s', (claimed[0],))
                    origin, = cur.fetchone()
        if not claimed:
            break
        # Older untagged jobs retain the explicitly supplied same-date policy.
        options = claimed[2].get('continuation', requested_policy)
        receipts.append(evidence.execute(connection, claimed, fetch, clock, on_received=derive))
    return receipts
