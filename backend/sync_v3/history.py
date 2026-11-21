"""Append immutable candidate workload snapshots for a represented baseball date."""

from datetime import date
from hashlib import sha256

from psycopg2.extras import Json

from sync_v3.comparison import compare_team_workload
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import encode_json, latest_source_status, replay
from sync_v3.rosters import dated_pitcher_sources
from sync_v3.workload import WINDOWS, load_calendar, team_workload, windows_from_calendar


METHODOLOGY = 'candidate_regular_workload_v1'


def _sample(cur, subject, mlb_id, through):
    if subject == 'team':
        calendar = load_calendar(cur, through, team=mlb_id)
        report = team_workload(cur, calendar, mlb_id, through)
        lineage = set(report['workload_sources'])
        if report['roster_source'] is not None:
            lineage.add(report['roster_source'])
        facts = {'workload': report['facts'], 'compared_windows': compare_team_workload(cur, calendar, report)}
    elif subject == 'pitcher':
        calendar = load_calendar(cur, through)
        identity = dated_pitcher_sources(cur, mlb_id, through)
        windows = windows_from_calendar(calendar, mlb_id, through, identity_sources=identity)
        lineage = set(identity)
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
            for slate in replay(cur, receipt[0]).body['dates']:
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
    cur.execute('''SELECT f.endpoint,f.parameters,f.sha256,f.outcome,coalesce(r.reason,f.reason)
                   FROM candidate.fetches f LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE f.id=ANY(%s)''', (sources,))
    # Observation IDs depend on load order. Stable request scopes and content digests do not.
    inputs = sorted({encode_json(row) for row in cur})
    input_hash = sha256(b'\n'.join(inputs)).hexdigest()
    content_hash = sha256(encode_json([subject, mlb_id, through.isoformat(), METHODOLOGY, facts])).hexdigest()
    scope = (subject, mlb_id, through, METHODOLOGY)
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
