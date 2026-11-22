"""Historical Team State and constituent arm reads for a represented club."""

from datetime import date
from hashlib import sha256

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS

from sync_v3.competition_calendar import competition_status
from sync_v3.dependencies import capture_reads
from sync_v3.evidence import encode_json
from sync_v3.history import _store, _transaction
from sync_v3.intelligence_history import record_intelligence, rebuild_intelligence, readiness_history_facts
from sync_v3.readiness import _club_readiness
from sync_v3.rosters import dated_pitcher_sources
from sync_v3.schedule_context import retrospective_availability_date
from sync_v3.workload import load_calendar, rest_from_calendar


AVAILABILITY_HISTORY = 'candidate_dated_availability_v1'
AVAILABILITY_EDITION = 'candidate_availability_edition_v1'


class UnknownAvailabilityEdition(LookupError):
    pass


def record_readiness(connection, team, through):
    return record_intelligence(connection, 'readiness', team, through)


def rebuild_readiness(connection, receipt):
    return rebuild_intelligence(connection, receipt, domains=('readiness',))


def record_availability_snapshots(connection, through, as_of, *, team=None, pitcher=None):
    """Freeze one product-date sample atomically, keeping its workload date explicit."""
    if (as_of < through or (team is not None and team not in MLB_TEAM_IDS)
            or (pitcher is not None and (team is not None or type(pitcher) is not int or pitcher < 1))):
        raise ValueError('Expected a valid product day and at most one MLB subject')
    return _transaction(connection, _record_availability, through, as_of, team, pitcher)


def _record_availability(cur, through, as_of, team, pitcher):
    subject = 'team' if pitcher is None else 'pitcher'
    with capture_reads(cur) as common:
        evidence = retrospective_availability_date(cur, through, as_of)
        if not evidence['availability_reference']:
            return dict(status='withheld', date_evidence=evidence, snapshots=[])
        reference = date.fromisoformat(evidence['availability_reference'])
        if pitcher is None:
            competition = competition_status(cur, reference)
    # Database-local receipt IDs live in the sealed provenance links. Keep
    # the dated schedule observations identifiable in the exported decision.
    decision = {key: value for key, value in evidence.items() if key not in ('dates', 'season_calendar_sources')}
    decision['dates'] = {day: dict(acquired_at=row['acquired_at'], listed_games=row['listed_games'])
                         for day, row in evidence['dates'].items()}
    if pitcher is not None:
        entities = [pitcher]
    elif team is not None:
        entities = [team]
    else:
        entities = sorted(MLB_TEAM_IDS)
    regular_calendar = None
    snapshots = []
    club_reviews = {}
    seen_players = set()
    for entity in entities:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', (subject, entity))
        facts = dict(date_evidence=decision, current_serving_eligible=False)
        with capture_reads(cur) as reads:
            if pitcher is None:
                club = _club_readiness(cur, entity, through, reference, competition, evidence)
                facts['readiness'] = readiness_history_facts(club)
                if seen_players.intersection(club['arms']):
                    raise ValueError('A pitcher appears on two clubs in the availability edition')
                seen_players.update(club['arms'])
                club_reviews[entity] = dict(status='calculated' if club['team_state'] else 'withheld',
                                           reason=club['reason'], readiness=club, comparison=facts['readiness']['comparison'])
                rest_by_player = {}
                if club.get('workload_scope') == 'competitive_postseason_window':
                    rest_by_player = {player: week['rest'] for player, week in club.get('competitive_pitcher_weeks', {}).items()}
                elif club['arms']:
                    if regular_calendar is None:
                        with capture_reads(cur) as calendar_reads:
                            regular_calendar = load_calendar(cur, through)
                    reads.receipts.update(calendar_reads.receipts)
                    reads.requests.update(calendar_reads.requests)
                    for player in club['arms']:
                        rest = rest_from_calendar(regular_calendar, player, through,
                                                  identity_sources=[club['roster_source']], date_evidence=evidence)
                        reads.receipts.update(rest['identity_sources'] + rest['sources'])
                        rest_by_player[player] = {k: v for k, v in rest.items() if k not in ('identity_sources', 'sources')}
                if set(map(int, rest_by_player)) != set(map(int, club['arms'])):
                    raise ValueError('Missing rest readings for the dated club population')
                facts['pitcher_rest'] = rest_by_player
            else:
                calendar = load_calendar(cur, through)
                identity = dated_pitcher_sources(cur, entity, through)
                rest = rest_from_calendar(calendar, entity, through, identity_sources=identity, date_evidence=evidence)
                reads.receipts.update(rest['identity_sources'] + rest['sources'])
                facts['rest'] = {key: val for key, val in rest.items() if key not in ('identity_sources', 'sources')}
                facts['workload_scope'] = 'regular_season'
        sid, revision, digest = _store(cur, subject, entity, reference, AVAILABILITY_HISTORY, facts,
                                       sorted(common.receipts | reads.receipts), common.requests | reads.requests)
        snapshots.append(dict(subject=subject, mlb_id=entity, snapshot_id=sid, revision=revision, semantic_digest=digest))
    result = dict(status='frozen', date_evidence=evidence, snapshots=snapshots)
    if team is None and pitcher is None:
        ids = [snapshot['snapshot_id'] for snapshot in snapshots]
        cur.execute("""SELECT mlb_id,revision,semantic_digest,input_digest FROM candidate.workload_history
                       WHERE id=ANY(%s) ORDER BY mlb_id""", (ids,))
        manifest = dict(contract=AVAILABILITY_EDITION, represented=str(through), as_of=str(as_of),
                        availability_reference=str(reference), current_serving_eligible=False, members=cur.fetchall())
        digest = sha256(encode_json(manifest)).hexdigest()
        cur.execute("""INSERT INTO candidate.generations (digest,represented,manifest) VALUES (%s,%s,%s)
                       ON CONFLICT DO NOTHING RETURNING digest""", (digest, through, Json(manifest)))
        if cur.fetchone():
            cur.executemany('INSERT INTO candidate.generation_inputs VALUES (%s,%s)', [(digest, sid) for sid in ids])
        result['generation'] = digest
        result['review'] = dict(scope='historical_availability_facts', date_evidence=evidence, team=None,
                                pitcher=None, current_serving_eligible=False, clubs=club_reviews)
    return result


def read_availability_snapshot(connection, snapshot_id):
    """Read the exact sealed revision, including after a correction or a later edition."""
    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute("""SELECT subject,mlb_id,represented,revision,predecessor,semantic_digest,input_digest,facts
                       FROM candidate.workload_history WHERE id=%s AND methodology=%s""",
                    (snapshot_id, AVAILABILITY_HISTORY))
        row = cur.fetchone()
        if not row:
            raise ValueError('Unknown dated availability snapshot')
        subject, mlb_id, reference, revision, previous, semantic, inputs, facts = row
        return dict(subject=subject, mlb_id=mlb_id, availability_reference=str(reference), revision=revision,
                    predecessor=previous, snapshot_id=snapshot_id, semantic_digest=semantic, input_digest=inputs, facts=facts)
    return _transaction(connection, read)


def read_availability_edition(connection, digest):
    """Resolve all club and arm facts from one immutable availability manifest."""
    from sync_v3.generation import _pinned_members

    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute('SELECT represented,manifest FROM candidate.generations WHERE digest=%s', (digest,))
        entry = cur.fetchone()
        if not entry or entry[1].get('contract') != AVAILABILITY_EDITION:
            raise UnknownAvailabilityEdition('Expected a frozen availability edition')
        through, manifest = entry
        if (sha256(encode_json(manifest)).hexdigest() != digest or str(through) != manifest['represented']
                or manifest['current_serving_eligible'] is not False):
            raise ValueError('Invalid availability manifest')
        clubs, members = {}, []
        players = set()
        with cur.connection.cursor(name='frozen_availability') as stream:
            stream.execute("""SELECT h.id,h.subject,h.mlb_id,h.represented,h.methodology,h.revision,
                                     h.semantic_digest,h.input_digest,h.facts
                              FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                              WHERE g.generation=%s ORDER BY h.mlb_id""", (digest,))
            for row, computed_inputs in _pinned_members(cur, stream):
                sid, subject, club, reference, method, revision, semantic, inputs, facts = row
                decision = facts['date_evidence']
                readiness = facts['readiness']
                if (subject != 'team' or method != AVAILABILITY_HISTORY or readiness['team'] != club
                        or facts['current_serving_eligible'] is not False or readiness['current_serving_eligible'] is not False
                        or decision['data_through'] != str(through) or readiness['membership_date'] != str(through)
                        or decision['as_of'] != manifest['as_of'] or str(reference) != manifest['availability_reference']
                        or decision['availability_reference'] != str(reference) or readiness['reference_date'] != str(reference)
                        or inputs != computed_inputs or semantic != sha256(encode_json(
                            [subject, club, str(reference), method, facts])).hexdigest()):
                    raise ValueError('Invalid frozen availability member')
                rest = facts['pitcher_rest']
                if (players.intersection(rest) or set(rest) != set(readiness['arms']) or any(
                        item['reference'] != str(reference) or item['through'] != str(through)
                        or item['mlb_player_id'] != int(player) for player, item in rest.items())):
                    raise ValueError('Pitcher rest disagrees with the dated club population')
                players.update(rest)
                clubs[club] = dict(snapshot_id=sid, revision=revision, readiness=readiness, pitcher_rest=rest)
                members.append([club, revision, semantic, inputs])
        if sorted(clubs) != sorted(MLB_TEAM_IDS) or members != manifest['members'] or len(members) != len(clubs):
            raise ValueError('Incomplete or inconsistent availability edition')
        return dict(generation=digest, data_through=str(through), as_of=manifest['as_of'],
                    availability_reference=manifest['availability_reference'], clubs=clubs, current_serving_eligible=False)
    return _transaction(connection, read)
