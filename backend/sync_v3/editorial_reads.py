"""Evidence for editorial review from a selected historical candidate."""
from datetime import date, timedelta
from hashlib import sha256
import json

from services.mlb_club_directory import MLB_CLUBS
from services.bullpen_optionality_context import build_bullpen_optionality_context, last_workload_label_for_date
from services import bullpen_concentration_context as concentration
from services import rotation_context as rotation_layer
from services import role_stability_context as stability
from sync_v3.appearance_reads import appearance_ledger
from sync_v3.evidence import replay
from services.story_observation_engine import build_team_story_observation_payload
from sync_v3.intelligence_history import DOMAINS
from sync_v3.product_reads import _public_arms, _read_transaction, _selected, read_team_events


def _optionality(cur, digest, team, reference):
    cur.execute("""SELECT h.facts FROM candidate.generation_inputs g JOIN candidate.workload_history h
                   ON h.id=g.snapshot WHERE g.generation=%s AND h.subject='team' AND h.mlb_id=%s
                   AND h.methodology=%s""", (digest, team, DOMAINS['readiness'][1]))
    facts, = cur.fetchone()
    if facts['reason'] or facts['reference_date'] != reference or not facts['arms']:
        return None
    identities, _ = _public_arms(cur, digest)
    records, latest = [], {}
    for key, arm in facts['arms'].items():
        player = int(key)
        identity = identities.get(player)
        if not identity or identity['team_id'] != team or arm['reason'] or not arm['read']:
            return None
        read = arm['read']
        records.append(dict(player_id=player, name=identity['name'], availability=read['availability']))
        latest[player] = date.fromisoformat(read['last_workload'])
    ref = date.fromisoformat(reference)
    layer = build_bullpen_optionality_context(records, reference_date=ref)
    for option in layer['clean_workload_options']:
        option['last_workload'] = last_workload_label_for_date(latest[option['player_id']], ref)
    return layer


def _stability(cur, digest, team, through):
    ledger = appearance_ledger(cur, digest, 'team', team, through)
    start = (through - timedelta(days=2 * concentration.BULLPEN_CONCENTRATION_WINDOW_DAYS - 1)).isoformat()
    citation = dict(ledger['citation'], start=start, through=through.isoformat())
    if any(day >= start for day in ledger['gaps']):
        return None, 'incomplete_comparison_calendar', citation
    lines = [line for line in ledger['appearances'] if line['game_date'] >= start]
    if any(len(line['boxscore_digests']) != 1 or line['pitches_thrown'] is None for line in lines):
        return None, 'incomplete_workload_or_ambiguous_boxscore', citation
    digests = sorted({line['boxscore_digests'][0] for line in lines})
    cur.execute('SELECT sha256,encoded_json FROM candidate.payloads WHERE sha256=ANY(%s)', (digests,))
    players_by_digest = {}
    for digest_value, encoded in cur:
        if sha256(encoded).hexdigest() != digest_value:
            raise ValueError('Role stability boxscore digest mismatch')
        body = json.loads(bytes(encoded))
        side, = (side for side in body['teams'].values() if side['team']['id'] == team)
        players_by_digest[digest_value] = side['players']
    logs = []
    for line in lines:
        players = players_by_digest[line['boxscore_digests'][0]]
        mlb = line['mlb_id']
        person = players.get(f'ID{mlb}', {}).get('person') or {}
        if person.get('id') != mlb or not person.get('fullName'):
            return None, 'missing_official_reliever_identity', citation
        logs.append(dict(line, games_started=0, game_type='R', player_id=mlb, pitcher_name=person['fullName']))
    layer = stability.build_role_stability_context(logs, reference_date=through)
    if not layer['context_available']:
        return None, 'insufficient_comparable_workload', citation
    return layer, 'complete_comparison_windows', citation


def read_story_observations(connection, team, *, revision=None):
    clubs = {club.team_id: club for club in MLB_CLUBS}
    if type(team) is not int or team not in clubs:
        raise ValueError('Expected an MLB club identity')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def read(cur):
        selected = _selected(cur, revision)
        result = dict(scope='isolated_historical_game_lines', team=team, generation=None, current_serving_eligible=False,
                      observations=None, qualification='no_selected_generation')
        if not selected or selected[1] is None:
            return result
        sequence, digest, through, reference = selected
        result.update(generation=digest, selection_revision=sequence, represented=through.isoformat())
        cur.execute("""SELECT h.id,h.facts,h.semantic_digest,h.input_digest FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s AND h.subject='team'
                       AND h.mlb_id=%s AND h.methodology=%s""", (digest, team, DOMAINS['rotation'][1]))
        snapshot, rotation, semantic, inputs = cur.fetchone()
        result['citation'] = dict(methodology=DOMAINS['rotation'][1], facts_digest=semantic, input_digest=inputs)
        dates = rotation['dates']
        if len(dates) != 14 or any(day['reason'] for day in dates.values()):
            return dict(result, qualification='incomplete_rotation_calendar')
        expected = {game['game_pk']: day for day, data in dates.items() for game in data['games']}
        cur.execute("""SELECT r.id,c.identity,r.facts,min(c.source_id),array_agg(DISTINCT f.sha256 ORDER BY f.sha256)
                       FROM candidate.workload_history_sources s
                       JOIN candidate.confirmations c ON c.source_id=s.source_id AND c.domain='final'
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       JOIN candidate.fetches f ON f.id=c.source_id
                       WHERE s.snapshot=%s AND c.identity=ANY(%s) GROUP BY r.id,c.identity ORDER BY c.identity,r.id""",
                    (snapshot, [str(pk) for pk in expected]))
        games, logs = set(), []
        names_complete = True
        body_digests = {}
        for _, identity, lines, receipt, digests in cur.fetchall():
            pk = int(identity)
            if pk in games:
                return dict(result, qualification='conflicting_pinned_game_versions')
            games.add(pk)
            club_lines = [line for line in lines if line['team_id'] == team]
            if not club_lines or any(line['game_date'] != expected[pk] for line in club_lines):
                return dict(result, qualification='unverified_club_game')
            body_digests[identity] = digests
            box = replay(cur, receipt).body if len(digests) == 1 else None
            for line in club_lines:
                mlb = line['pitcher_mlb_id']
                side = box['teams'][line['side']] if box else {}
                person = side.get('players', {}).get(f'ID{mlb}', {}).get('person') or {}
                name = person.get('fullName') if person.get('id') == mlb else None
                if not name and line['games_started'] == 0:
                    names_complete = False
                logs.append(dict(line, mlb_game_pk=pk, game_type='R', player_id=mlb, pitcher_name=name,
                                 innings_pitched_outs=line['outs_recorded']))
        if games != expected.keys():
            return dict(result, qualification='missing_pinned_final')
        club = clubs[team]
        layers = {'rotation_context': rotation_layer.build_rotation_context(logs, reference_date=through)}
        coverage = {'rotation_context': 'complete_calendar'}
        if names_complete:
            layers['bullpen_concentration_context'] = concentration.build_bullpen_concentration_context(
                logs, reference_date=through)
            coverage['bullpen_concentration_context'] = 'complete_calendar'
        else:
            coverage['bullpen_concentration_context'] = 'missing_official_reliever_identity'
        role_stability, coverage['role_stability_context'], result['role_stability_citation'] = _stability(
            cur, digest, team, through)
        if role_stability:
            layers['role_stability_context'] = role_stability
        # These legacy builders normally receive currently assigned players. The pinned final
        # proves the club at appearance, including for a player who subsequently transferred.
        legacy_scope = {rotation_layer.CURRENT_ASSIGNMENT_LIMITATION, concentration.CURRENT_ASSIGNMENT_LIMITATION,
                        stability.CURRENT_ASSIGNMENT_LIMITATION}
        for layer in layers.values():
            layer['limitations'] = [text for text in layer.get('limitations', []) if text not in legacy_scope]
            layer['limitations'].append('The official final pitching line establishes the club at appearance.')
        optionality = _optionality(cur, digest, team, reference)
        if optionality:
            layers['bullpen_optionality_context'] = optionality
        coverage['bullpen_optionality_context'] = 'complete_dated_arm_reads' if optionality else 'incomplete_arm_reads'
        payload = build_team_story_observation_payload(dict(
            team_id=team, team_name=club.team_name, team_abbreviation=club.abbreviation,
            reference_date=reference, data_through_date=through.isoformat(), **layers))
        return dict(result, qualification='game_lines_compared', coverage=coverage, source_games=sorted(games),
                    boxscore_digests=body_digests,
                    observations=payload)
    return _read_transaction(connection, read)


def read_event_evidence(connection, team, event_id, *, revision):
    """Reproduce an editorial/share input; draft and publication identities belong to separate authorities."""
    if type(revision) is not int or revision < 1 or not isinstance(event_id, str) or not event_id:
        raise ValueError('An exact selector revision and event identity are required')
    history = read_team_events(connection, team, revision=revision)
    matches = [item for item in history['events'] if item['event']['event_id'] == event_id]
    event = matches[0] if len(matches) == 1 else None
    status = history['status']
    if status == 'represented':
        if len(matches) > 1:
            status = 'ambiguous_event'
        elif event is None:
            status = 'missing_event'
    return dict(scope='historical_editorial_evidence', generation=history['generation'], selection_revision=revision,
                team=team, represented=history['represented'], event_id=event_id, evidence=event, status=status,
                current_serving_eligible=False, trusted_snapshot_id=None)


def read_trust(connection, *, revision=None):
    """Verify the methods and acquisition span supporting one selected historical generation."""
    from sync_v3.generation import _inspect
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def read(cur):
        selected = _selected(cur, revision)
        if not selected or selected[1] is None:
            return dict(status='no_selected_generation', generation=None, current_serving_eligible=False)
        sequence, digest, through, reference = selected
        review = _inspect(cur, digest, compare_latest=False)
        cur.execute("""SELECT h.subject,h.methodology,count(*) FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s
                       GROUP BY h.subject,h.methodology ORDER BY h.subject,h.methodology""", (digest,))
        methods = [dict(subject=kind, methodology=method, scopes=n) for kind, method, n in cur]
        cur.execute("""WITH receipts AS (
                           SELECT hs.source_id FROM candidate.generation_inputs g
                           JOIN candidate.workload_history_sources hs ON hs.snapshot=g.snapshot WHERE g.generation=%s
                           UNION SELECT source FROM candidate.generation_sources WHERE generation=%s)
                       SELECT f.outcome,coalesce(r.reason,f.reason),count(*),min(f.received_at),max(f.received_at)
                       FROM receipts s JOIN candidate.fetches f ON f.id=s.source_id
                       LEFT JOIN candidate.refusals r ON r.source_id=f.id
                       GROUP BY f.outcome,coalesce(r.reason,f.reason) ORDER BY 1,2""", (digest, digest))
        sources = [dict(outcome=outcome, refusal_reason=reason, receipts=n,
                        earliest_acquisition=first.isoformat(), latest_acquisition=last.isoformat())
                   for outcome, reason, n, first, last in cur]
        return dict(status='verified_historical_inventory', generation=digest, selection_revision=sequence,
                    represented=through.isoformat(), availability_reference=reference, methods=methods, sources=sources,
                    comparison=review['core_candidate_review'], changes=review['historical_changes'],
                    current_serving_eligible=False, trusted_snapshot_id=None)
    return _read_transaction(connection, read)
