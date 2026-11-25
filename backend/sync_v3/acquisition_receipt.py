"""Attest the settled current-worker queue for an isolated played-day handoff."""
from datetime import timezone
from hashlib import sha256

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import evidence, savant
from sync_v3.depth import _pitchers
from sync_v3.discovery import (active_profile_request, calendar_requests,
                               competition_calendar_request, game_requests, pitcher_requests, roster_requests)


def played_day_acquisition(cur, day):
    # The caller holds a consistent view of the queue and the reviewed generation.
    cur.execute("""SELECT 1 FROM candidate.jobs WHERE budget='current' AND product_date<%s
                   AND state<>'done' AND payload->>'capture' IS NULL LIMIT 1""", (day,))
    if cur.fetchone():
        raise ValueError('Earlier current acquisition has outstanding work')
    cur.execute("""WITH attempts AS (
                       SELECT a.*, min(a.claimed_at) OVER job AS first_claim,
                              count(*) OVER job AS total, count(a.finished_at) OVER job AS finished
                       FROM candidate.attempts a JOIN candidate.jobs j ON j.id=a.job_id
                       WHERE j.product_date=%s AND j.budget='current'
                       WINDOW job AS (PARTITION BY a.job_id)
                   )
                   SELECT j.id,j.identity,j.state,j.payload,a.first_claim,a.finished_at,
                          a.total,a.total=j.attempts AND a.total=a.finished,
                          f.id,f.endpoint,f.parameters,f.received_at,f.sha256,
                          f.outcome='received' AND r.source_id IS NULL
                            AND encode(pg_catalog.sha256(p.encoded_json),'hex')=f.sha256
                   FROM candidate.jobs j
                   LEFT JOIN attempts a ON a.job_id=j.id AND a.outcome='done'
                   LEFT JOIN candidate.fetches f ON f.token=a.token
                   LEFT JOIN candidate.payloads p ON p.sha256=f.sha256
                   LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE j.product_date=%s AND j.budget='current' ORDER BY j.id""", (day, day))
    sources, jobs = {}, set()
    digest = sha256()
    start = finish = None
    attempts = 0
    for row in cur:
        (job, identity, state, payload, claimed, settled, total, closed,
         source, endpoint, params, received, fingerprint, valid) = row
        if (state != 'done' or not closed or not valid or job in jobs or 'capture' in payload or 'continuation' not in payload
                or (endpoint, params) != (payload.get('endpoint'), payload.get('params'))
                or settled is None or settled < claimed):
            raise ValueError('Current acquisition lacks a unique qualified completion for each job')
        claimed = claimed.astimezone(timezone.utc)
        settled = settled.astimezone(timezone.utc)
        jobs.add(job)
        attempts += total
        key = (endpoint, tuple(sorted(params.items())))
        if key not in sources or (received, source) > sources[key][:2]:
            sources[key] = received, source, fingerprint, payload['continuation']
        digest.update(evidence.encode_json(
            [job, identity, source, fingerprint, total, claimed.isoformat(), settled.isoformat()]
        ))
        start = min(start, claimed) if start else claimed
        finish = max(finish, settled) if finish else settled

    schedule, transactions = calendar_requests(day)
    required = [schedule, transactions, competition_calendar_request(day.year), *roster_requests(day, MLB_TEAM_IDS)]
    required.extend(active_profile_request(day, team) for team in sorted(MLB_TEAM_IDS))

    def source_for(request):
        match = sources.get((request.endpoint, request.parameters))
        if match is None:
            raise ValueError(f'Missing settled acquisition for {request.endpoint} on {day}')
        _, source, fingerprint, options = match
        latest = evidence.latest_qualified_source(cur, request.endpoint, request.params())
        if latest != source:
            cur.execute('SELECT sha256 FROM candidate.fetches WHERE id=%s', (latest,))
            if cur.fetchone() != (fingerprint,):
                raise ValueError(f'Current acquisition differs from qualified evidence for {request.endpoint}')
        return source, options

    for request in required:
        source, options = source_for(request)
        if request == schedule:
            observed = evidence.replay(cur, source)
            games = game_requests(day, observed.body, now=observed.retrieved_at)
            if not any(child.endpoint.endswith('/boxscore') for child in games) or any(
                    child.endpoint.endswith('/feed/live') for child in games):
                raise ValueError('Played-day acquisition requires a settled slate with an official final')
            for child in (*games, *savant.after_final(day, games)):
                source_for(child)
        if request.params().get('rosterType') == 'active' and 'hydrate' not in request.params():
            team = int(request.endpoint.split('/')[2])
            players, reason = _pitchers(evidence.replay(cur, source).body, team, team, 'active')
            if reason or options.get('profile_teams') != [team]:
                raise ValueError(f'Current acquisition lacks dated pitcher discovery for {team}')
            for child in pitcher_requests(day, players, postseason_rounds=options['rounds'],
                                          round_totals=options['round_totals']):
                source_for(child)
    return dict(contract='v3_current_acquisition_day_v1', represented=day.isoformat(), jobs=len(jobs), attempts=attempts,
                digest=digest.hexdigest(), started_at=start.isoformat(), completed_at=finish.isoformat())
