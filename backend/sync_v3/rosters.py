"""Club/date-specific membership and transactions retain different authority."""

from datetime import date

from psycopg2.extras import Json

from services.mlb_api import mlb_client
from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_evidence import roster_entry_player_id
from sync_v3.dependencies import consult
from sync_v3.evidence import latest_source_status
from sync_v3.canonical import Refused, accept, trade_leg_identity
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


def observe(cur, source_id, capture, *, replay_batch=False):
    req = capture.request
    if req.endpoint.endswith('/roster') and 'hydrate' not in req.params():
        facts = roster_facts(capture)
        if facts:
            identity = f"{facts['team']}/{facts['type']}/{facts['represented']}"
            accept(cur, 'roster', identity, facts, source_id, capture.retrieved_at)
    if req.endpoint != '/transactions':
        return set()
    grouped = {}
    for item in capture.body['transactions']:
        if not isinstance(item, dict):
            raise Refused('Malformed official transaction')
        record = mlb_client._transaction_record(item, source_endpoint=req.endpoint, params=req.params())
        for key in ('source_endpoint','source_query_start_date','source_query_end_date'):
            record.pop(key, None)
        if not record['transaction_id']:
            raise Refused('Official transaction identity is required')
        grouped.setdefault(str(record['transaction_id']), []).append((record, item))

    teams = set()
    for identity, records in grouped.items():
        facts = _transaction_facts(records)
        revision = accept(cur, 'transaction', identity, facts, source_id, capture.retrieved_at)
        if not replay_batch:
            if not revision:
                continue
            cur.execute('SELECT source_id FROM candidate.revisions WHERE id=%s', (revision,))
            if cur.fetchone()[0] != source_id:
                continue
        # A trade signals a dated roster check. Its legs do not establish membership.
        for record, _ in records:
            teams.update(t for t in (record['from_team_id'], record['to_team_id']) if t in MLB_TEAM_IDS)
    return teams


def _number_change_player(records):
    # A club summary corroborates the named row. It cannot establish a transfer.
    if len(records) != 2 or any(record['transaction_type_code'] != 'NUM' or raw.get('typeDesc') != 'Number Change'
                                for record, raw in records):
        return None
    named = [record for record, _ in records if record['player_mlb_id'] is not None]
    if len(named) != 1:
        return None
    player, = named
    summary = next(record for record, _ in records if record['player_mlb_id'] is None)
    team = player['to_team_id']
    description = records[0][1].get('description')
    if (type(player['player_mlb_id']) is int and player['player_mlb_id'] > 0
            and isinstance(description, str) and description.strip()
            and team in MLB_TEAM_IDS and player['from_team_id'] in (None, team)
            and summary['from_team_id'] == summary['to_team_id'] == team
            and player['transaction_date'] and player['effective_date']
            and all(summary[key] == player[key] for key in ('transaction_date', 'effective_date'))
            and all(value is None or value == player[key] for key, value in summary.items()
                    if key != 'from_team_id')):
        return player
    return None


def _assignment_player(records):
    # The league and destination responses can repeat a club notice alongside
    # the player-specific record. Keep the notice's resolution date on its source.
    named = [(record, raw) for record, raw in records if record['player_mlb_id'] is not None]
    notices = [raw for record, raw in records if record['player_mlb_id'] is None]
    if len(named) != 1 or not notices or any(raw != notices[0] for raw in notices):
        return None
    player, raw = named[0]
    clubs = (player['from_team_id'], player['to_team_id'])
    if (any(type(club) is not int or club <= 0 or club in MLB_TEAM_IDS for club in clubs)
            or clubs[0] == clubs[1] or type(player['player_mlb_id']) is not int or player['player_mlb_id'] <= 0):
        return None
    shared = ('id', 'typeCode', 'typeDesc', 'date', 'effectiveDate', 'toTeam', 'description')
    if (raw.get('typeCode') != 'ASG' or raw.get('typeDesc') != 'Assigned'
            or not isinstance(raw.get('description'), str) or not raw['description'].strip()
            or not all(raw.get(key) for key in shared)):
        return None
    notice = notices[0]
    if (set(notice) == {*shared, 'resolutionDate'} and all(notice[key] == raw[key] for key in shared)
            and notice['resolutionDate'] == raw['effectiveDate']
            and player['resolution_date'] in (None, notice['resolutionDate'])):
        return player
    return None


def _transaction_facts(records):
    first, _ = records[0]
    if first['transaction_type_code'] == 'ASG' and len(records) > 1:
        player = _assignment_player(records)
        if player is not None:
            return player
    if first['transaction_type_code'] == 'NUM' and len(records) > 1:
        description = records[0][1].get('description')
        if any(raw.get('description') != description for _, raw in records):
            raise Refused('Conflicting official number-change descriptions')
        player = _number_change_player(records)
        if player is not None:
            return player
    records = [(record, raw.get('typeDesc')) for record, raw in records]
    if all(entry == records[0] for entry in records):
        return first
    # MLB assigns one ID to a trade and reports one row per player or consideration.
    # Require distinct legs of one dated trade connecting the participating MLB clubs.
    clubs = {}
    legs = {}
    for record, type_description in records:
        player = record['player_mlb_id']
        origin, destination = record['from_team_id'], record['to_team_id']
        descriptions = [value for value in (record['transaction_type_description'], type_description) if value is not None]
        if (record['transaction_type_code'] != 'TR' or not descriptions or any(value != 'Trade' for value in descriptions)
                or record['transaction_id'] != first['transaction_id']
                or origin not in MLB_TEAM_IDS or destination not in MLB_TEAM_IDS or origin == destination
                or not first['transaction_date']
                or record['transaction_date'] != first['transaction_date']
                or (player is not None and (type(player) is not int or player <= 0))):
            raise Refused('Contradictory evidence at the same source instant')
        # A named player can move only once in this trade. Unnamed considerations
        # can be distinguished only by their direction, never by array position.
        leg = trade_leg_identity(record)
        if leg in legs:
            raise Refused('Contradictory evidence at the same source instant')
        legs[leg] = dict(record, transaction_type_description='Trade')
        clubs.setdefault(origin, set()).add(destination)
        clubs.setdefault(destination, set()).add(origin)
    # Distinct deals sharing an ID cannot be joined without a connecting transfer.
    connected = set()
    pending = [first['from_team_id']]
    while pending:
        club = pending.pop()
        if club not in connected:
            connected.add(club)
            pending.extend(clubs[club] - connected)
    if connected != clubs.keys():
        raise Refused('Disconnected official trade participants')
    if not any(key[0] for key in legs):
        raise Refused('Trade participants unresolved')
    return dict(transaction_id=first['transaction_id'], trade_legs=[legs[key] for key in sorted(legs)])


def roster_on(cur, team, kind, represented):
    """Return the accepted dated roster and its source, or withhold the population."""
    latest = latest_source_status(cur, f'/teams/{team}/roster', {'date': represented.isoformat(), 'rosterType': kind})
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


def dated_pitcher_sources(cur, player, represented):
    """Positive identity proof for an arm with no qualifying relief appearance."""
    endpoints = [f'/teams/{team}/roster' for team in sorted(MLB_TEAM_IDS)]
    params = {'date': represented.isoformat(), 'rosterType': 'active'}
    cur.execute("""SELECT club.endpoint,latest.id,(latest.outcome='received' AND r.facts->'members' @> %s)
                   FROM unnest(%s::text[]) AS club(endpoint)
                   LEFT JOIN LATERAL (
                       SELECT f.id, f.outcome FROM candidate.fetches f
                       WHERE f.endpoint=club.endpoint AND f.parameters=%s
                       ORDER BY f.received_at DESC,f.id DESC LIMIT 1
                   ) latest ON true
                   LEFT JOIN candidate.confirmations c ON c.source_id=latest.id AND c.domain='roster'
                   LEFT JOIN candidate.revisions r ON r.id=c.revision_id
                   ORDER BY latest.id""", (Json([{'id': player, 'position': '1'}]), endpoints, Json(params)))
    sources = []
    for endpoint, source, present in cur:
        consult(cur, endpoint, params, source)
        if present:
            sources.append(source)
    return sources
