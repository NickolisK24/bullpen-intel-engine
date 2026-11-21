"""Append immutable candidate workload snapshots for a represented baseball date."""

from datetime import date
from hashlib import sha256
import re

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS

from sync_v3.comparison import compare_team_workload
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import encode_json, latest_source_status, replay
from sync_v3.rosters import dated_pitcher_sources
from sync_v3.schedule_context import missing_listings
from sync_v3.workload import WINDOWS, load_calendar, team_workload, windows_from_calendar


METHODOLOGY = 'candidate_regular_workload_v1'


def _sample(cur, subject, mlb_id, through):
    if subject == 'team':
        calendar = load_calendar(cur, through, team=mlb_id)
        report = team_workload(cur, calendar, mlb_id, through)
        lineage = set(report['workload_sources'])
        roster = latest_source_status(cur, f'/teams/{mlb_id}/roster', {'date': through.isoformat(), 'rosterType': 'active'})
        if roster:
            lineage.add(roster[0])
        facts = {'workload': report['facts'], 'compared_windows': compare_team_workload(cur, calendar, report)}
    elif subject == 'pitcher':
        calendar = load_calendar(cur, through)
        identity = dated_pitcher_sources(cur, mlb_id, through)
        windows = windows_from_calendar(calendar, mlb_id, through, identity_sources=identity)
        lineage = set(identity)
        # Preserve the receipt that removed a previously attested identity, or
        # refused its latest observation, even when another club still confirms it.
        cur.execute("""SELECT DISTINCT (facts->>'team')::integer FROM candidate.revisions
                       WHERE domain='roster' AND identity=ANY(%s) AND facts->'members' @> %s""",
                    ([f'{t}/active/{through}' for t in MLB_TEAM_IDS], Json([{'id': mlb_id, 'position': '1'}])))
        for team, in cur.fetchall():
            roster = latest_source_status(cur, f'/teams/{team}/roster', {'date': through.isoformat(), 'rosterType': 'active'})
            if roster:
                lineage.add(roster[0])
        facts = {}
        for days, window in windows.items():
            lineage.update(window['sources'])
            facts[str(days)] = {k: v for k, v in window.items() if k not in ('sources', 'identity_sources')}
    else:
        raise ValueError('Expected a team or pitcher workload snapshot')
    gaps = {day.isoformat(): reason for day, (_, reason) in calendar.items() if reason}
    for day in gaps:
        request = calendar_requests(date.fromisoformat(day))[0]
        receipt = latest_source_status(cur, request.endpoint, request.params())
        if not receipt:
            continue
        lineage.add(receipt[0])
        if receipt[1] == 'received' and receipt[2] is None:
            slates = replay(cur, receipt[0]).body['dates']
            if gaps[day] == 'previous_listing_requires_absence_proof':
                present = {g['gamePk'] for slate in slates for g in slate['games']}
                for team, receipts in missing_listings(cur, request.params(), present, game_types={'R'}).items():
                    if subject == 'pitcher' or team == mlb_id:
                        lineage.update(receipts)
            for slate in slates:
                for game in slate['games']:
                    teams = {side['team']['id'] for side in game['teams'].values()}
                    if game['gameType'] == 'R' and (subject == 'pitcher' or mlb_id in teams):
                        box = latest_source_status(cur, f"/game/{game['gamePk']}/boxscore", {})
                        if box:
                            lineage.add(box[0])
    return {'windows': facts, 'coverage_gaps': gaps}, sorted(lineage)


def _transaction(connection, operation, *args):
    """Concurrent builders retry serialization conflicts with a fresh view."""
    from psycopg2 import errors, extensions
    if connection.autocommit or connection.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
        raise ValueError('Snapshot requires an idle transactional connection')
    for attempt in range(3):
        try:
            with connection, connection.cursor() as cur:
                cur.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                return operation(cur, *args)
        except (errors.SerializationFailure, errors.UniqueViolation):
            if attempt == 2:
                raise


def record_workload(connection, subject, mlb_id, through):
    return _transaction(connection, _append, subject, mlb_id, through)


def _append(cur, subject, mlb_id, through):
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', (subject, mlb_id))
    facts, sources = _sample(cur, subject, mlb_id, through)
    return _store(cur, subject, mlb_id, through, METHODOLOGY, facts, sources)


def _store(cur, subject, mlb_id, through, methodology, facts, sources, requests=()):
    cur.execute('''SELECT f.endpoint,f.parameters,f.sha256,f.outcome,coalesce(r.reason,f.reason)
                   FROM candidate.fetches f LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE f.id=ANY(%s)''', (sources,))
    # Observation IDs depend on load order. Stable request scopes and content digests do not.
    inputs = sorted({encode_json(row) for row in cur})
    request_descriptors = [encode_json(['request', endpoint, dict(params)]) for endpoint, params in sorted(requests)]
    input_hash = sha256(b'\n'.join(inputs + request_descriptors)).hexdigest()
    content_hash = sha256(encode_json([subject, mlb_id, through.isoformat(), methodology, facts])).hexdigest()
    scope = (subject, mlb_id, through, methodology)
    cur.execute("""SELECT id,revision,semantic_digest,input_digest FROM candidate.workload_history
                   WHERE (subject,mlb_id,represented,methodology)=(%s,%s,%s,%s)
                   ORDER BY revision DESC LIMIT 1""", scope)
    previous = cur.fetchone()
    if previous and previous[2:] == (content_hash, input_hash):
        return previous[0], previous[1], content_hash
    revision = previous[1] + 1 if previous else 1
    cur.execute("""INSERT INTO candidate.workload_history
                   (subject,mlb_id,represented,methodology,revision,predecessor,semantic_digest,input_digest,facts)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (*scope, revision, previous[0] if previous else None, content_hash, input_hash, Json(facts)))
    identifier = cur.fetchone()[0]
    cur.executemany('INSERT INTO candidate.workload_history_sources VALUES (%s,%s)',
                    [(identifier, source) for source in sources])
    cur.executemany('INSERT INTO candidate.history_requests VALUES (%s,%s,%s)',
                    [(identifier, endpoint, Json(dict(params))) for endpoint, params in requests])
    return identifier, revision, content_hash


def affected_workload(cur, final_revision):
    """Find existing snapshots whose rolling window intersects a changed appearance."""
    cur.execute("""WITH changes AS (
                       SELECT entity_type,entity_id,represented FROM candidate.impacts WHERE revision_id=%s
                   ), candidates AS (
                       SELECT DISTINCT ON (h.subject,h.mlb_id,h.represented) h.*
                       FROM candidate.workload_history h
                       WHERE h.methodology=%s AND EXISTS (
                           SELECT 1 FROM changes c
                           WHERE h.represented BETWEEN c.represented AND c.represented + %s
                       ) ORDER BY h.subject,h.mlb_id,h.represented,h.revision DESC
                   )
                   SELECT subject,mlb_id,h.represented FROM candidates h WHERE EXISTS (
                       SELECT 1 FROM changes c WHERE h.represented BETWEEN c.represented AND c.represented + %s
                       AND ((h.subject=c.entity_type AND h.mlb_id=c.entity_id)
                            OR (h.subject='pitcher' AND (h.facts->'coverage_gaps') ? c.represented::text))
                   ) ORDER BY 1,2,3""",
                (final_revision, METHODOLOGY, max(WINDOWS)-1, max(WINDOWS)-1))
    return cur.fetchall()

def _rebuild(cur, revision):
    cur.execute("SELECT domain FROM candidate.revisions WHERE id=%s", (revision,))
    if cur.fetchone() != ('final',):
        raise ValueError('Workload rebuild requires an accepted final revision')
    return [_append(cur, *scope) for scope in affected_workload(cur, revision)]


def rebuild_for_final(connection, revision):
    """Refresh only previously frozen scopes touched by this final, in one transaction."""
    return _transaction(connection, _rebuild, revision)


def _rebuild_receipt(cur, receipt):
    cur.execute('SELECT endpoint,parameters FROM candidate.fetches WHERE id=%s', (receipt,))
    row = cur.fetchone()
    if not row:
        raise ValueError('Unknown receipt')
    endpoint, params = row
    if endpoint == '/schedule' and 'startDate' in params:
        day = date.fromisoformat(params['startDate'])
        if calendar_requests(day)[0].params() != params:
            raise ValueError('Unsupported schedule scope')
        # Even a quiet slate supplies negative evidence. A failed or corrected
        # league response can change coverage for every subject inside this window.
        cur.execute("""SELECT DISTINCT subject,mlb_id,represented FROM candidate.workload_history
                       WHERE methodology=%s AND represented BETWEEN %s AND %s::date + %s
                       ORDER BY 1,2,3""", (METHODOLOGY, day, day, max(WINDOWS)-1))
    elif endpoint.startswith('/teams/') and endpoint.endswith('/roster') and set(params) == {'date','rosterType'}:
        if params['rosterType'] != 'active':
            return []
        day = date.fromisoformat(params['date'])
        team = int(endpoint.split('/')[2])
        # Positive pitcher identity proofs use dated active membership from any
        # club. Include previous memberships when a corrected roster removes one.
        cur.execute("""WITH players AS (
                           SELECT DISTINCT (member->>'id')::integer AS id
                           FROM candidate.revisions r, LATERAL jsonb_array_elements(r.facts->'members') member
                           WHERE r.domain='roster' AND r.identity=%s AND member->>'position'='1'
                       )
                       SELECT DISTINCT subject,mlb_id,represented FROM candidate.workload_history
                       WHERE methodology=%s AND represented=%s AND (
                           (subject='team' AND mlb_id=%s) OR (subject='pitcher' AND mlb_id IN (SELECT id FROM players))
                       ) ORDER BY 1,2,3""", (f'{team}/active/{day}', METHODOLOGY, day, team))
    elif (box := re.fullmatch(r'/game/([1-9][0-9]*)/boxscore', endpoint)) and not params:
        # Even an unusable latest box can withdraw coverage. Use dated schedule
        # evidence for its game and sides since an invalid box has no authority.
        cur.execute("""WITH games AS (
                           SELECT DISTINCT (f.parameters->>'startDate')::date AS day,
                               (r.facts->'teams'->'home'->'team'->>'id')::integer AS home,
                               (r.facts->'teams'->'away'->'team'->>'id')::integer AS away
                           FROM candidate.confirmations c JOIN candidate.fetches f ON f.id=c.source_id
                           JOIN candidate.revisions r ON r.id=c.revision_id
                           WHERE c.domain='schedule' AND c.identity=%s AND r.facts->>'gameType'='R'
                       )
                       SELECT DISTINCT subject,mlb_id,represented FROM candidate.workload_history h
                       JOIN games g ON h.represented BETWEEN g.day AND g.day + %s
                       WHERE h.methodology=%s AND (h.subject='pitcher' OR h.mlb_id IN (g.home,g.away))
                       ORDER BY 1,2,3""", (box[1], max(WINDOWS)-1, METHODOLOGY))
    else:
        raise ValueError('Expected a dated schedule, roster or game boxscore receipt')
    scopes = cur.fetchall()
    return [_append(cur, *scope) for scope in scopes]


def rebuild_for_observation(connection, receipt):
    """Refresh the windows relying on a retained schedule, roster or boxscore observation."""
    return _transaction(connection, _rebuild_receipt, receipt)
