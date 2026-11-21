"""Official transaction chronology for a represented historical club."""

from hashlib import sha256
from types import SimpleNamespace

from services.mlb_club_directory import MLB_TEAM_IDS
from services.public_recent_transactions import project_qualified_public_transaction
from services.transaction_ingestion import _values_from_transaction
from services.transaction_participant_qualification import ROLE_NON_PITCHER, classify_position
from sync_v3.evidence import encode_json


def _qualified_event(facts, revision, member, through, source):
    if not member or not member.get('public_id') or member.get('position') not in ('P', 'TWP'):
        return None
    roster = member['roster_observation']
    if (roster['represented'] != through.isoformat() or member['mlb_id'] != facts['player_mlb_id']
            or roster['team_id'] not in MLB_TEAM_IDS or roster['membership'] not in ('active', '40Man')
            or (roster['membership'] == 'active' and roster['team_id'] != member['team_id'])
            or facts.get('transaction_date') != through.isoformat()):
        return None
    position = classify_position(code=facts.get('participant_position_code'),
                                 abbreviation=facts.get('participant_position_abbreviation'),
                                 position_type=facts.get('participant_position_type'))
    if position == ROLE_NON_PITCHER:
        return None
    pitcher = SimpleNamespace(id=member['public_id'], mlb_id=member['mlb_id'], full_name=member['name'])
    snapshot = SimpleNamespace(team_id=roster['team_id'], snapshot_date=through,
                               active_roster=True if roster['membership'] == 'active' else None)
    values, error = _values_from_transaction(
        facts, start_date=through, end_date=through, timestamp=source['acquired_at'], sync_run_id=None,
        pitchers_by_mlb_id={pitcher.mlb_id: pitcher}, roster_snapshots_by_pair={(pitcher.id, through): snapshot})
    if error:
        return None
    event = project_qualified_public_transaction(SimpleNamespace(**values), pitcher)
    if event:
        effective = values['effective_date']
        event.update(effective_date=effective.isoformat() if effective else None,
                     roster_digest=roster['roster_digest'], transaction_revision=revision,
                     transaction_facts_digest=sha256(encode_json(facts)).hexdigest())
    return event


def team_transactions(cur, generation, team, through):
    from sync_v3.generation import _confirmed_transactions
    from sync_v3.product_reads import _roster_identities

    cur.execute("""SELECT g.manifest->'transaction_source',f.id FROM candidate.generations g
                   LEFT JOIN LATERAL (SELECT f.id FROM candidate.generation_sources s
                     JOIN candidate.fetches f ON f.id=s.source AND f.endpoint='/transactions'
                     WHERE s.generation=g.digest) f ON true WHERE g.digest=%s""", (generation,))
    source, source_id = cur.fetchone()
    result = dict(team=team, represented=through.isoformat(), source=source, events=[], withheld=None,
                  coverage='retained_league_response')
    if not source or not source_id or source.get('reported_records') is None:
        return dict(result, status='unavailable')
    transactions = _confirmed_transactions(cur, source_id)
    if (source['parameters'] != dict(sportId=1, startDate=through.isoformat(), endDate=through.isoformat())
            or len(transactions) != source.get('confirmed_transactions')
            or len(transactions) != source['reported_records']
            or sha256(encode_json(transactions)).hexdigest() != source.get('revisions_digest')):
        return dict(result, status='unavailable')
    affected = [(revision, facts) for _, revision, facts in transactions
                if team in (facts.get('from_team_id'), facts.get('to_team_id'))]
    members = {}
    if affected:
        players = sorted({facts['player_mlb_id'] for _, facts in affected if type(facts['player_mlb_id']) is int})
        members, disputed = _roster_identities(cur, generation, 'active', set(), player_ids=players)
        reserves, forty_conflicts = _roster_identities(cur, generation, '40Man', disputed, player_ids=players)
        for mlb, reserve in reserves.items():
            existing = members.get(mlb)
            if existing is None:
                members[mlb] = reserve
            elif existing['team_id'] != reserve['roster_observation']['team_id']:
                forty_conflicts.add(mlb)
        for mlb in forty_conflicts:
            members.pop(mlb, None)
    withheld = 0
    for revision, facts in affected:
        event = _qualified_event(facts, revision, members.get(facts['player_mlb_id']), through, source)
        if event:
            result['events'].append(event)
        else:
            withheld += 1
    return dict(result, status='partial' if withheld else 'available', withheld=withheld)
