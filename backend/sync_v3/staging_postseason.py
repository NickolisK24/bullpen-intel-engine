"""Retain the 18 dated schedules and 35 official decisions from shadow artifact 14993332403."""
import gzip
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic

from psycopg2.extras import Json

from sync_v3.evidence import encode_json


def retain(worker):
    start = monotonic()
    inserted = 0
    checked = 0
    directory = Path(__file__).parent / 'fixtures' / 'nov23-decisions'
    # Use the original full fixture's capture ID and each response's source timestamp.
    with worker, worker.cursor() as cur:
        for filename in sorted(directory.glob('*.json.gz')):
            fixture = json.loads(gzip.decompress(filename.read_bytes()))
            for row in fixture['responses']:
                body = encode_json(row['body'])
                digest = sha256(body).hexdigest()
                key = (fixture['capture'], row['endpoint'], Json(row['params']))
                received = datetime.fromisoformat(row['retrieved_at'])
                cur.execute('INSERT INTO candidate.payloads VALUES (%s,%s) ON CONFLICT DO NOTHING',
                            (digest, body))
                cur.execute('INSERT INTO candidate.captured_requests VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (*key, received, digest))
                inserted += cur.rowcount
                cur.execute("""SELECT r.received_at,r.sha256,encode(pg_catalog.sha256(p.encoded_json),'hex')
                               FROM candidate.captured_requests r JOIN candidate.payloads p USING (sha256)
                               WHERE r.capture=%s AND r.endpoint=%s AND r.parameters=%s""", key)
                if cur.fetchone() != (received, digest, digest):
                    raise ValueError('Archived response disagrees with persistent staging')
                checked += 1
        if checked != 53:
            raise ValueError('Incomplete November postseason archive')
    return dict(verified=checked, inserted=inserted, elapsed_seconds=monotonic()-start)


def reconcile_current_decisions(connection, fetch, *, limit=96):
    """Admit retained decisions and qualify missing public schedule evidence in the private candidate database."""
    from datetime import date, timezone
    from collections import Counter
    from zoneinfo import ZoneInfo

    from sync_v3 import canonical, evidence, queue
    from sync_v3.competition_calendar import calendar_games, competition_status, matches_calendar_game
    from sync_v3.discovery import calendar_requests, competition_calendar_request
    from sync_v3.generation import generation_date_decision
    from sync_v3.sources import RetainedResponse

    day = datetime.now(ZoneInfo('America/New_York')).date()
    clock = lambda: datetime.now(timezone.utc)
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        league = competition_status(cur, day)
        source = evidence.replay(cur, league['calendar_source'])
        games = calendar_games(competition_calendar_request(day.year).params(), source.body)
        through = max(d for d, row, _ in games.values() if d <= day and row['status_state'] == 'final')
        decision = generation_date_decision(cur, through, day)
        scopes = []
        for pk in league['missing_decisions']:
            played, row, game = games[pk]
            if played > day or row['status_state'] != 'final':
                continue
            request = calendar_requests(played)[0]
            schedule_id = evidence.latest_qualified_source(cur, request.endpoint, request.params())
            if schedule_id is None:
                scopes.append((played, request.endpoint, request.params()))
                continue
            schedule = evidence.replay(cur, schedule_id)
            daily = [g for slate in schedule.body['dates'] for g in slate['games'] if g['gamePk'] == pk]
            if len(daily) != 1 or not matches_calendar_game(daily[0], game):
                raise ValueError(f'Official season and daily schedules disagree for {pk}')
            scopes.append((played, f'/game/{pk}/boxscore', {}))
        for value, reason in decision['gaps'].items():
            if reason != 'missing_complete_schedule':
                continue
            missing_day = date.fromisoformat(value)
            req = calendar_requests(missing_day)[0]
            scopes.append((missing_day, req.endpoint, req.params()))
    seen = set()
    outcomes = Counter()
    for played, endpoint, params in scopes:
        payload = dict(endpoint=endpoint, params=params, current_edition_recovery=True)
        key = sha256(encode_json(['current_edition_recovery', str(played), payload])).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        with connection, connection.cursor() as cur:
            now = clock()
            job = queue.enqueue(cur, key, payload, now, budget='historical', product_date=played)
            claim = queue.claim(cur, now, budget='historical', product_date=played, only_job_id=job)
            if not claim:
                continue
            cur.execute("""SELECT c.received_at,c.sha256,p.encoded_json FROM candidate.captured_requests c
                           JOIN candidate.payloads p USING(sha256) WHERE c.endpoint=%s AND c.parameters=%s
                           ORDER BY c.received_at DESC,c.capture LIMIT 1""", (endpoint, Json(params)))
            row = cur.fetchone()
        if row:
            observed, digest, encoded = row
            if sha256(bytes(encoded)).hexdigest() != digest:
                raise ValueError('Stored recovery source digest differs')
            def transport(_endpoint, params):
                return RetainedResponse(json.loads(bytes(encoded)), observed)
            kind = 'retained'
        else:
            transport, kind = fetch, 'live'
        _, result = evidence.execute(connection, claim, transport, clock,
                                     on_received=lambda cur, oid, obs: canonical.observe(cur, oid, obs, played))
        if result != 'received':
            raise ValueError(f'Private current-edition recovery withheld {endpoint} on {played}: {result}')
        outcomes[kind] += 1
        if sum(outcomes.values()) >= limit:
            break
    return dict(day=str(day), through=str(through), prior_missing_decisions=len(league['missing_decisions']),
                prior_date_gaps=len(decision['gaps']), received=dict(outcomes))


def qualify_offseason_edition(connection, day):
    """Freeze the real dated club facts only when official evidence establishes the offseason."""
    from collections import Counter
    from sync_v3 import evidence
    from sync_v3.competition_calendar import calendar_games, competition_status
    from sync_v3.discovery import competition_calendar_request
    from sync_v3.generation import freeze_generation, generation_date_decision
    from sync_v3.intelligence_history import record_intelligence
    from sync_v3.product_reads import _league

    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        competition = competition_status(cur, day)
        clubs = competition['clubs']
        if competition['missing_decisions'] or Counter(c['status'] for c in clubs.values()) != {'season_complete': 30}:
            raise ValueError('The private current edition lacks complete offseason competition evidence')
        receipt = evidence.replay(cur, competition['calendar_source'])
        games = calendar_games(competition_calendar_request(day.year).params(), receipt.body)
        through = max(d for d,row,_ in games.values() if d <= day and row['status_state'] == 'final')
        dates = generation_date_decision(cur, through, day)
        if dates['status'] != 'aligned':
            raise ValueError('The retained current schedule does not support the workload and availability dates')
    for team in sorted(clubs):
        record_intelligence(connection, 'readiness', team, through)
    digest = freeze_generation(connection, through, as_of=day)
    with connection, connection.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        league = _league(cur, None, digest, compare_latest=True)
        review = league['selection_review']
        if review['status'] != 'season_complete_withholding' or review['latest_inventory_digest'] != digest:
            raise ValueError(f'Offseason generation withheld for unresolved evidence: {review}')
        states = {}
        for club in league['teams']:
            state = club['team_state']
            if state.get('available') is not False or state.get('outcome') != 'season_complete':
                raise ValueError('A current active Team State lacks offseason authority')
            states[str(club['team_id'])] = sha256(encode_json(state)).hexdigest()
        if set(states) != {str(team) for team in clubs}:
            raise ValueError('Current private League roster differs from the official club inventory')
    return dict(day=str(day), through=str(through), availability=dates['availability_reference'],
                generation=digest, decision=review['status'], club_state_digests=states)
