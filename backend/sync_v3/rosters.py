"""Club/date-specific membership and transactions retain different authority."""

from datetime import date

from psycopg2.extras import Json

from services.mlb_api import mlb_client
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_evidence import roster_entry_player_id
from sync_v3.canonical import Refused, accept
from sync_v3.roster_scope import classify_roster_team


def roster_facts(capture):
    params = capture.request.params()
    team = int(capture.request.endpoint.split('/')[2])
    if team not in MLB_TEAM_IDS:
        raise Refused('Affiliate evidence has no MLB membership authority')
    kind = params['rosterType']
    if kind not in ('active', '40Man'):
        return None
    represented = date.fromisoformat(params['date']).isoformat()
    records = capture.body['roster']
    authority = classify_roster_team(team, records=records)
    if not authority['mlb_membership_authority']:
        raise Refused('Historical SP-05 roster authority scope conflict')
    grouped = {}
    for entry in records:
        if not isinstance(entry, dict) or not isinstance(entry.get('person'), dict):
            raise Refused('Roster participant is missing an official identity')
        person = roster_entry_player_id(entry)
        if not person or person <= 0:
            raise Refused('Missing roster participant')
        grouped.setdefault(person, []).append(entry)
    members = {}
    for person, entries in grouped.items():
        names = {e['person'].get('fullName') for e in entries}
        positions = {(e.get('position') or {}).get('code') for e in entries}
        statuses = {(e.get('status') or {}).get('code') for e in entries}
        # A dated list establishes inclusion. Distinct status codes on rows for
        # the same person cannot establish one status; preserve the alternatives.
        members[person] = {'id':person, 'name':names.pop() if len(names)==1 else None,
                           'position':positions.pop() if len(positions)==1 else None,
                           'status':next(iter(statuses)) if len(statuses)==1 else None,
                           'source_statuses':sorted(code for code in statuses if code)}
    return {'team': team, 'type': kind, 'represented': represented,
            'members': [members[person] for person in sorted(members)]}


def observe(cur, source_id, capture):
    req = capture.request
    if req.endpoint.endswith('/roster'):
        facts = roster_facts(capture)
        if facts:
            identity = f"{facts['team']}/{facts['type']}/{facts['represented']}"
            accept(cur, 'roster', identity, facts, source_id, capture.retrieved_at)
    if req.endpoint != '/transactions':
        return set()
    teams = set()
    for item in capture.body['transactions']:
        if not isinstance(item, dict):
            raise Refused('Malformed official transaction')
        record = mlb_client._transaction_record(item, source_endpoint=req.endpoint, params=req.params())
        for key in ('source_endpoint','source_query_start_date','source_query_end_date'):
            record.pop(key, None)
        if not record['transaction_id']:
            raise Refused('Official transaction identity is required')
        revision = accept(cur, 'transaction', record['transaction_id'], record, source_id, capture.retrieved_at)
        if revision:
            cur.execute('SELECT source_id FROM candidate.revisions WHERE id=%s', (revision,))
            if cur.fetchone()[0] == source_id:
                teams.update(t for t in (record['from_team_id'], record['to_team_id']) if t in MLB_TEAM_IDS)
    return teams


def roster_on(cur, team, kind, represented):
    """Return the accepted dated roster and its source, or withhold the population."""
    cur.execute("""SELECT f.id,f.outcome,r.source_id FROM candidate.fetches f
                   LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE f.endpoint=%s AND f.parameters=%s
                   ORDER BY f.received_at DESC,f.id DESC LIMIT 1""",
                (f'/teams/{team}/roster', Json({'date':represented.isoformat(), 'rosterType':kind})))
    latest = cur.fetchone()
    if not latest or latest[1] != 'received' or latest[2] is not None:
        return None
    cur.execute("""SELECT r.facts FROM candidate.confirmations c JOIN candidate.revisions r
                   ON r.id=c.revision_id WHERE c.domain='roster' AND c.source_id=%s""", (latest[0],))
    row = cur.fetchone()
    return (row[0], latest[0]) if row else None


def membership_on(cur, team, kind, represented, player):
    roster = roster_on(cur, team, kind, represented)
    if roster is None:
        return None
    return any(member['id'] == player for member in roster[0]['members'])
