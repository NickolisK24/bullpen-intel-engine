"""Evidence for editorial review from a selected historical candidate."""
from services.mlb_club_directory import MLB_CLUBS
from services.rotation_context import build_rotation_context
from services.story_observation_engine import build_team_story_observation_payload
from sync_v3.intelligence_history import DOMAINS
from sync_v3.product_reads import _read_transaction, _selected, read_team_events


def read_story_observations(connection, team, *, revision=None):
    clubs = {club.team_id: club for club in MLB_CLUBS}
    if type(team) is not int or team not in clubs:
        raise ValueError('Expected an MLB club identity')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def read(cur):
        selected = _selected(cur, revision)
        result = dict(scope='isolated_historical_rotation', generation=None, current_serving_eligible=False,
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
        cur.execute("""SELECT DISTINCT r.id,c.identity,r.facts FROM candidate.workload_history_sources s
                       JOIN candidate.confirmations c ON c.source_id=s.source_id AND c.domain='final'
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE s.snapshot=%s AND c.identity=ANY(%s) ORDER BY c.identity,r.id""",
                    (snapshot, [str(pk) for pk in expected]))
        games, logs = set(), []
        for _, identity, lines in cur:
            pk = int(identity)
            if pk in games:
                return dict(result, qualification='conflicting_pinned_game_versions')
            games.add(pk)
            club_lines = [line for line in lines if line['team_id'] == team]
            if not club_lines or any(line['game_date'] != expected[pk] for line in club_lines):
                return dict(result, qualification='unverified_club_game')
            logs.extend(dict(line, mlb_game_pk=pk, game_type='R', innings_pitched_outs=line['outs_recorded'])
                        for line in club_lines)
        if games != expected.keys():
            return dict(result, qualification='missing_pinned_final')
        club = clubs[team]
        context = build_rotation_context(logs, reference_date=through)
        payload = build_team_story_observation_payload(dict(
            team_id=team, team_name=club.team_name, team_abbreviation=club.abbreviation,
            reference_date=reference, data_through_date=through.isoformat(), rotation_context=context))
        return dict(result, qualification='rotation_compared', source_games=sorted(games), observations=payload)
    return _read_transaction(connection, read)


def read_event_evidence(connection, team, event_id, *, revision):
    """Reproduce an editorial/share input; draft and publication identities belong to separate authorities."""
    if type(revision) is not int or revision < 1 or not isinstance(event_id, str) or not event_id:
        raise ValueError('An exact selector revision and event identity are required')
    history = read_team_events(connection, team, revision=revision)
    event = next((item for item in history['events'] if item['event']['event_id'] == event_id), None)
    return dict(scope='historical_editorial_evidence', generation=history['generation'], selection_revision=revision,
                event_id=event_id, evidence=event, status='represented' if event else 'missing_event',
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
                       SELECT f.outcome,r.reason,count(*),min(f.received_at),max(f.received_at)
                       FROM receipts s JOIN candidate.fetches f ON f.id=s.source_id
                       LEFT JOIN candidate.refusals r ON r.source_id=f.id
                       GROUP BY f.outcome,r.reason ORDER BY f.outcome,r.reason""", (digest, digest))
        sources = [dict(outcome=outcome, refusal_reason=reason, receipts=n,
                        earliest_acquisition=first.isoformat(), latest_acquisition=last.isoformat())
                   for outcome, reason, n, first, last in cur]
        return dict(status='verified_historical_inventory', generation=digest, selection_revision=sequence,
                    represented=through.isoformat(), availability_reference=reference, methods=methods, sources=sources,
                    comparison=review['core_candidate_review'], changes=review['historical_changes'],
                    current_serving_eligible=False, trusted_snapshot_id=None)
    return _read_transaction(connection, read)
