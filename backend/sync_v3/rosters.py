"""Club/date-specific membership and transactions retain different authority."""

from datetime import date

from services.mlb_api import mlb_client
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_evidence import roster_entry_player_id
from sync_v3.canonical import Refused, accept


def roster_facts(capture):
    params = capture.request.params()
    team = int(capture.request.endpoint.split('/')[2])
    if team not in MLB_TEAM_IDS:
        raise Refused('Affiliate evidence has no MLB membership authority')
    kind = params['rosterType']
    if kind not in ('active', '40Man'):
        return None
    represented = date.fromisoformat(params['date']).isoformat()
    members = {}
    for entry in capture.body['roster']:
        if not isinstance(entry, dict) or not isinstance(entry.get('person'), dict):
            raise Refused('Roster participant is missing an official identity')
        person = roster_entry_player_id(entry)
        if not person or person <= 0 or person in members:
            raise Refused('Missing or duplicate roster participant')
        members[person] = {'id': person, 'name': entry['person'].get('fullName'),
                           'position': (entry.get('position') or {}).get('code'),
                           'status': (entry.get('status') or {}).get('code')}
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


def membership_on(cur, team, kind, represented, player):
    identity = f'{team}/{kind}/{represented.isoformat()}'
    cur.execute("""SELECT facts FROM candidate.revisions WHERE domain='roster' AND identity=%s
                   ORDER BY revision DESC LIMIT 1""", (identity,))
    row = cur.fetchone()
    return any(member['id'] == player for member in row[0]['members']) if row else None
