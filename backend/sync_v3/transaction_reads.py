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


def _receipt_rows(cur, generation, through):
    from sync_v3.generation import _confirmed_transactions

    cur.execute("""SELECT g.manifest->'transaction_source',f.id FROM candidate.generations g
                   LEFT JOIN LATERAL (SELECT f.id FROM candidate.generation_sources s
                     JOIN candidate.fetches f ON f.id=s.source AND f.endpoint='/transactions'
                     WHERE s.generation=g.digest) f ON true WHERE g.digest=%s""", (generation,))
    source, source_id = cur.fetchone()
    if not source or not source_id or source.get('reported_records') is None:
        return source, None
    transactions = _confirmed_transactions(cur, source_id)
    if (source['parameters'] != dict(sportId=1, startDate=through.isoformat(), endDate=through.isoformat())
            or len(transactions) != source.get('confirmed_transactions')
            or len(transactions) != source['reported_records']
            or sha256(encode_json(transactions)).hexdigest() != source.get('revisions_digest')):
        return source, None
    return source, transactions


def _transaction_members(cur, generation, affected):
    from sync_v3.product_reads import _roster_identities

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
    return members


def team_transactions(cur, generation, team, through):
    source, transactions = _receipt_rows(cur, generation, through)
    result = dict(team=team, represented=through.isoformat(), source=source, events=[], withheld=None,
                  coverage='retained_league_response')
    if transactions is None:
        return dict(result, status='unavailable')
    affected = [(revision, facts) for _, revision, facts in transactions
                if team in (facts.get('from_team_id'), facts.get('to_team_id'))]
    members = _transaction_members(cur, generation, affected)
    withheld = 0
    for revision, facts in affected:
        event = _qualified_event(facts, revision, members.get(facts['player_mlb_id']), through, source)
        if event:
            result['events'].append(event)
        else:
            withheld += 1
    return dict(result, status='partial' if withheld else 'available', withheld=withheld)


def slate_transaction_changes(cur, generation, through, abbreviations):
    """Compare with the predecessor at first selection, including when this edition is restored."""
    cur.execute("""SELECT g.digest,g.represented FROM (
                       SELECT predecessor FROM candidate.core_selections
                       WHERE generation=%s AND action='select' ORDER BY revision LIMIT 1
                   ) original JOIN candidate.core_selections prior ON prior.revision=original.predecessor
                   JOIN candidate.generations g ON g.digest=prior.generation""", (generation,))
    previous = cur.fetchone()
    if not previous or (through - previous[1]).days not in (0, 1):
        return [], 'comparable_transaction_edition_unavailable'
    return _compare_transactions(cur, generation, through, previous, abbreviations)


def _compare_transactions(cur, generation, through, previous, abbreviations):
    from services.tonight_read_model import _league_change

    _, prior = _receipt_rows(cur, *previous)
    source, current = _receipt_rows(cur, generation, through)
    if prior is None or current is None:
        return [], 'comparable_transaction_receipt_unavailable'
    known = {identity for identity, _, _ in prior}
    candidates = [(revision, facts) for identity, revision, facts in current if identity not in known
                  and facts.get('transaction_date') == through.isoformat()]
    members = _transaction_members(cur, generation, candidates)
    carrier = dict(contract='candidate_official_transaction', current_snapshot_id=generation,
                   previous_snapshot_id=previous[0])
    changes = []
    for revision, facts in candidates:
        event = _qualified_event(facts, revision, members.get(facts['player_mlb_id']), through, source)
        if not event or (facts.get('effective_date') and not event['effective_date']):
            continue
        same_day = event['effective_date'] == event['transaction_date']
        headline, detail = event['description'], None
        if not same_day:
            effective = f"effective {event['effective_date']}" if event['effective_date'] else 'effective date unavailable'
            headline = f"MLB reported a transaction for {event['pitcher']['name']}."
            detail = f"{event['label']} ({effective})."
        for team in {event['from_team_id'], event['to_team_id']}.intersection(abbreviations):
            item = _league_change(team, abbreviations[team], carrier, dict(
                event_type='verified_transaction', team_id=team, evidence_status='complete',
                summary=' '.join(filter(None, (headline, detail))), event_date=event['transaction_date'],
                subject_id=event['pitcher']['pitcher_id'], facts=dict(transaction_id=event['transaction_id'])))
            if item:
                # Initials in a verified pitcher name can also contain a period followed by a space.
                item.update(headline=headline, detail=detail)
                item['source_ref'] = (f"{generation}/{previous[0]}/{source['digest']}/{event['roster_digest']}"
                                      f"#transaction:{event['transaction_id']}")
                changes.append((team, facts['player_mlb_id'] if same_day else None, item))
    return changes, None
