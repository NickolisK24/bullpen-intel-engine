"""Freeze and reproduce historical Team State and its constituent arm reads."""

from sync_v3.comparison import compare_readiness
from sync_v3.dependencies import capture_reads
from sync_v3.history import _store, _transaction
from sync_v3.readiness import represented_readiness


METHODOLOGY = 'candidate_regular_readiness_v1'


def _append(cur, team, through):
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', ('team', team))
    with capture_reads(cur) as reads:
        report = represented_readiness(cur, team, through)
        report['comparison'] = compare_readiness(report)
    # Surrogate receipt IDs differ across clusters. They belong to immutable
    # provenance links, outside the portable digest of the baseball facts.
    facts = {key: value for key, value in report.items() if key not in (
        'calendar_source', 'reference_slate_source', 'decision_sources', 'roster_source', 'workload_sources', 'profiles')}
    facts['verified_decisions'] = sorted(report['decision_sources'])
    facts['profile_status'] = {player: profile['reason'] for player, profile in report.get('profiles', {}).items()}
    return _store(cur, 'team', team, through, METHODOLOGY, facts, sorted(reads.receipts), reads.requests)


def record_readiness(connection, team, through):
    return _transaction(connection, _append, team, through)


def _affected(cur, receipt):
    cur.execute('SELECT endpoint,parameters FROM candidate.fetches WHERE id=%s', (receipt,))
    request = cur.fetchone()
    if not request:
        raise ValueError('Unknown receipt')
    from psycopg2.extras import Json
    cur.execute("""SELECT h.mlb_id,h.represented FROM candidate.history_requests d
                   JOIN candidate.workload_history h ON h.id=d.snapshot
                   WHERE d.endpoint=%s AND d.parameters=%s AND h.methodology=%s AND NOT EXISTS (
                       SELECT 1 FROM candidate.workload_history newer WHERE
                       (newer.subject,newer.mlb_id,newer.represented,newer.methodology)=
                       (h.subject,h.mlb_id,h.represented,h.methodology) AND newer.revision>h.revision)
                   ORDER BY h.mlb_id,h.represented""", (request[0], Json(request[1]), METHODOLOGY))
    return [_append(cur, team, through) for team, through in cur.fetchall()]


def rebuild_readiness(connection, receipt):
    """Re-evaluate latest snapshots that consulted this request, including previous misses."""
    return _transaction(connection, _affected, receipt)
