"""Assemble an immutable inventory of one represented candidate generation."""

from hashlib import sha256

from psycopg2.extras import Json

from services.availability_reference_date import trusted_slate_reference_dates
from services.mlb_club_directory import MLB_TEAM_IDS
from services.game_finality import classify_status
from services.role_movement import GAME_TYPES
from services.pitcher_public_labels import build_public_arm_read
from services.team_state_public_vocabulary import PUBLIC_STATE_LABELS
from services.team_state_vnext_production_proof import _reference_date_alignment
from sync_v3.change_history import COMPARISONS
from sync_v3.comparison import compare_readiness
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import encode_json, latest_source_status, replay
from sync_v3.schedule_context import missing_listings
from sync_v3.history import METHODOLOGY, _transaction
from sync_v3.intelligence_history import DOMAINS


def _readiness_status(team, day, reference, facts):
    if facts is None:
        return 'missing_readiness'
    alignment = _reference_date_alignment(facts['membership_date'], facts['reference_date'],
                                          data_through=day, expected_availability=reference)
    competition = facts['competition']
    if (facts['team'] != team or competition['team_id'] != team or not alignment['aligned']
            or competition['reference_date'] != reference.isoformat()):
        return 'misaligned_readiness'
    if facts['mode'] != 'retrospective_candidate' or facts['current_serving_eligible'] is not False:
        return 'invalid_candidate_authority'
    if compare_readiness(facts) != facts['comparison']:
        return 'decision_comparison_conflict'
    if facts['team_state'] is None:
        if competition['status'] == 'season_complete' and facts['reason'] == competition['basis']:
            return 'season_complete'
        return facts['reason'] or 'missing_team_state'
    state = facts['team_state']
    if PUBLIC_STATE_LABELS.get(state['public_code']) != state['public_label']:
        return 'public_vocabulary_conflict'
    for arm in facts['arms'].values():
        read = arm['read']
        if read and read['arm_read'] != build_public_arm_read(read['availability']):
            return 'arm_label_conflict'
    if competition['status'] != 'active' or facts['reason']:
        return 'unsupported_team_state'
    return 'compared'


def _slate(cur, day):
    params = calendar_requests(day)[0].params()
    receipt = latest_source_status(cur, '/schedule', params)
    result = dict(represented=day.isoformat(), games=None, reason='missing_complete_schedule')
    if not receipt:
        return result, set()
    source, outcome, reason = receipt
    if outcome != 'received' or reason:
        result['reason'] = reason or outcome
        return result, {source}
    games = [g for entry in replay(cur, source).body['dates'] for g in entry['games']]
    missing = missing_listings(cur, params, {g['gamePk'] for g in games}, game_types=GAME_TYPES)
    if missing:
        result['reason'] = 'previous_listing_requires_absence_proof'
        return result, {source}.union(*missing.values())
    result['games'] = []
    for game in sorted(games, key=lambda item: item['gamePk']):
        if game['gameType'] in GAME_TYPES:
            status = classify_status(game['status'])
            result['games'].append(dict(game_pk=game['gamePk'], game_type=game['gameType'],
                                        home=game['teams']['home']['team']['id'], away=game['teams']['away']['team']['id'],
                                        status=status.state, final=status.final_status))
    result['reason'] = None
    return result, {source}


def freeze_generation(connection, through):
    return _transaction(connection, _freeze, through)


def _freeze(cur, through):
    membership, reference = trusted_slate_reference_dates(through)
    if membership != through or reference is None:
        raise ValueError('A represented baseball date is required')
    club_methods = {method for subject, method, _ in DOMAINS.values() if subject == 'team'} | {METHODOLOGY}
    club_methods.update(f'candidate_{domain}_changes_v1' for domain in COMPARISONS if domain != 'pitcher_rest')
    pitcher_methods = {METHODOLOGY, DOMAINS['pitcher_rest'][1], DOMAINS['pitcher_profile'][1],
                      'candidate_pitcher_rest_changes_v1'}
    game_method = DOMAINS['game_deployment'][1]
    cur.execute("""SELECT DISTINCT ON (subject,mlb_id,methodology) subject,mlb_id,methodology,id,revision,
                   semantic_digest,input_digest,CASE WHEN methodology=ANY(%s) THEN facts END
                   FROM candidate.workload_history WHERE represented=%s
                   ORDER BY subject,mlb_id,methodology,revision DESC""",
                ([DOMAINS[d][1] for d in ('depth', 'readiness', 'rotation')], through))
    snapshots = {}
    for subject, entity, method, sid, revision, semantic, inputs, facts in cur:
        snapshots[subject, entity, method] = (sid, revision, semantic, inputs, facts)
    expected, clubs = set(), []
    for team in sorted(MLB_TEAM_IDS):
        expected.update(('team', team, method) for method in club_methods)
        def team_facts(domain):
            row = snapshots.get(('team', team, DOMAINS[domain][1]))
            return row[-1] if row else None
        depth, rotation = team_facts('depth'), team_facts('rotation')
        pitchers, games = None, None
        if depth:
            view = depth['views']['active']
            hydrated = depth.get('active_profiles') or {}
            if view['pitchers'] and not view['reason'] and hydrated.get('reason') != 'mlb_active_rosters_disagree':
                pitchers = sorted(map(int, view['pitchers']))
                expected.update(('pitcher', player, method) for player in pitchers for method in pitcher_methods)
        if rotation:
            slate = rotation['dates'][through.isoformat()]
            if not slate['reason']:
                games = sorted(game['game_pk'] for game in slate['games'])
                expected.update(('game', game, game_method) for game in games)
        clubs.append(dict(team=team, pitchers=pitchers, regular_season_finals=games,
                          readiness=_readiness_status(team, through, reference, team_facts('readiness'))))
    slate, seen = _slate(cur, through)
    next_slate, upcoming = _slate(cur, reference)
    for game in slate['games'] or ():
        if game['final']:
            expected.add(('game', game['game_pk'], game_method))
    schedule_sources = sorted(seen | upcoming)
    cur.execute('''SELECT parameters,received_at,sha256,outcome FROM candidate.fetches WHERE id=ANY(%s)
                   ORDER BY parameters,received_at,sha256,outcome''', (schedule_sources,))
    calendars = [dict(parameters=params, received_at=at.isoformat(), digest=digest, outcome=outcome)
                 for params, at, digest, outcome in cur]
    members, missing, parents = [], [], []
    for scope in sorted(expected):
        snapshot = snapshots.get(scope)
        if snapshot is None:
            missing.append(scope)
        else:
            sid, revision, semantic, inputs, _ = snapshot
            parents.append(sid)
            members.append(dict(subject=scope[0], mlb_id=scope[1], method=scope[2], revision=revision,
                                semantic_digest=semantic, input_digest=inputs))
    stale_comparisons, stale_inputs = _superseded(cur, parents)
    manifest = dict(slate=slate, next_slate=next_slate, calendar_sources=calendars,
                    stale_inputs=stale_inputs, stale_comparisons=stale_comparisons, contract='candidate_generation_inventory_v1', represented=through.isoformat(),
                    availability_reference=reference.isoformat(), clubs=clubs, members=members, missing=missing,
                    current_serving_eligible=False)
    digest = sha256(encode_json(manifest)).hexdigest()
    cur.execute("""INSERT INTO candidate.generations (digest,represented,manifest) VALUES (%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING digest""", (digest, through, Json(manifest)))
    if not cur.fetchone():
        return digest
    cur.executemany("""INSERT INTO candidate.generation_inputs VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    [(digest, parent) for parent in parents])
    cur.executemany('INSERT INTO candidate.generation_sources VALUES (%s,%s) ON CONFLICT DO NOTHING',
                    [(digest, source) for source in schedule_sources])
    return digest



def _superseded(cur, parents):
    cur.execute("""SELECT DISTINCT events.subject,events.mlb_id,events.methodology
                   FROM candidate.change_inputs c JOIN candidate.workload_history events ON events.id=c.change_snapshot
                   JOIN candidate.workload_history p ON p.id=c.input_snapshot
                   WHERE events.id=ANY(%s) AND EXISTS (
                       SELECT 1 FROM candidate.workload_history later WHERE
                       (later.subject,later.mlb_id,later.represented,later.methodology)=
                       (p.subject,p.mlb_id,p.represented,p.methodology) AND later.revision>p.revision)
                   ORDER BY 1,2,3""", (parents,))
    stale_comparisons = cur.fetchall()
    # A new receipt may be present before its dependent calculation is rebuilt.
    # A source scope first acquired after a missing-input snapshot counts as stale too.
    cur.execute("""WITH scopes AS (
                     SELECT snapshot,endpoint,parameters FROM candidate.history_requests WHERE snapshot=ANY(%s)
                     UNION
                     SELECT hs.snapshot,f.endpoint,f.parameters FROM candidate.workload_history_sources hs
                     JOIN candidate.fetches f ON f.id=hs.source_id WHERE hs.snapshot=ANY(%s)
                   ), latest AS (
                     SELECT k.endpoint,k.parameters,f.id FROM (SELECT DISTINCT endpoint,parameters FROM scopes) k
                     JOIN LATERAL (SELECT id FROM candidate.fetches f WHERE f.endpoint=k.endpoint
                                   AND f.parameters=k.parameters ORDER BY received_at DESC,id DESC LIMIT 1) f ON true
                   )
                   SELECT DISTINCT h.subject,h.mlb_id,h.methodology FROM scopes s
                   JOIN latest l USING(endpoint,parameters)
                   JOIN candidate.workload_history h ON h.id=s.snapshot
                   WHERE NOT EXISTS (SELECT 1 FROM candidate.workload_history_sources hs
                                     WHERE hs.snapshot=h.id AND hs.source_id=l.id)
                   ORDER BY 1,2,3""", (parents, parents))
    stale_inputs = cur.fetchall()
    return stale_comparisons, stale_inputs


def build_batch(connection, through, limit):
    """Materialize a bounded batch of missing or superseded candidate calculations."""
    from datetime import timedelta
    from sync_v3.change_history import record_changes
    from sync_v3.history import record_workload
    from sync_v3.intelligence_history import record_intelligence

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('A rehearsal batch requires a limit between 1 and 100 scopes')
    initial = freeze_generation(connection, through)
    with connection, connection.cursor() as cur:
        cur.execute('SELECT manifest FROM candidate.generations WHERE digest=%s', (initial,))
        manifest = cur.fetchone()[0]
    outstanding = {tuple(scope) for key in ('missing', 'stale_inputs', 'stale_comparisons')
                   for scope in manifest[key]}
    domain_for = {method: domain for domain, (_, method, _) in DOMAINS.items()}
    changes_for = {f'candidate_{domain}_changes_v1': domain for domain in COMPARISONS}
    discovery_methods = [DOMAINS[d][1] for d in ('readiness', 'depth', 'rotation')]

    def priority(scope):
        method = scope[2]
        if method in discovery_methods:
            return (0, discovery_methods.index(method), scope)
        return (2 if method in changes_for else 1, 0, scope)

    def build(subject, entity, method, day):
        if method == METHODOLOGY:
            record_workload(connection, subject, entity, day)
        else:
            record_intelligence(connection, domain_for[method], entity, day)

    selected = sorted(outstanding, key=priority)[:limit]
    for subject, entity, method in selected:
        if method in changes_for:
            domain = changes_for[method]
            source_method = METHODOLOGY if domain == 'team' else DOMAINS[domain][1]
            for day in (through - timedelta(days=1), through):
                build(subject, entity, source_method, day)
            record_changes(connection, domain, entity, through)
        else:
            build(subject, entity, method, through)
    return dict(before=initial, after=freeze_generation(connection, through), processed=selected)


def verify_generation(connection, digest):
    """Independently recount the pinned inventory, including its immutable facts and calendars."""
    return _transaction(connection, _verify, digest)


def _verify(cur, digest):
    cur.execute('SELECT represented,manifest FROM candidate.generations WHERE digest=%s', (digest,))
    stored = cur.fetchone()
    if not stored:
        raise ValueError('Unknown candidate generation')
    through, manifest = stored
    if (sha256(encode_json(manifest)).hexdigest() != digest or manifest['represented'] != through.isoformat()
            or manifest['current_serving_eligible'] is not False
            or sorted(c['team'] for c in manifest['clubs']) != sorted(MLB_TEAM_IDS)):
        raise ValueError('Invalid candidate generation identity or club inventory')
    members = {(m['subject'], m['mlb_id'], m['method']): m for m in manifest['members']}
    if len(members) != len(manifest['members']) or members.keys() & {tuple(s) for s in manifest['missing']}:
        raise ValueError('Inconsistent candidate scope inventory')
    # Pitch profiles and game facts can be large. Keep memory bounded during full verification.
    with cur.connection.cursor(name='verify_candidate_members') as stream:
        stream.itersize = 8
        stream.execute("""SELECT h.subject,h.mlb_id,h.represented,h.methodology,h.revision,h.semantic_digest,h.input_digest,h.facts
                       FROM candidate.generation_inputs p JOIN candidate.workload_history h ON h.id=p.snapshot
                       WHERE p.generation=%s""", (digest,))
        for subject, entity, day, method, revision, semantic, inputs, facts in stream:
            actual = sha256(encode_json([subject, entity, day.isoformat(), method, facts])).hexdigest()
            member = members.pop((subject, entity, method), None)
            if (not member or day != through or member['revision'] != revision or member['input_digest'] != inputs
                    or semantic != actual or member['semantic_digest'] != actual):
                raise ValueError('Pinned candidate snapshot disagrees with the manifest')
    if members:
        raise ValueError('Missing pinned candidate snapshots')
    cur.execute("""SELECT f.parameters,f.received_at,f.outcome,f.sha256,p.encoded_json
                   FROM candidate.generation_sources s JOIN candidate.fetches f ON f.id=s.source
                   LEFT JOIN candidate.payloads p ON p.sha256=f.sha256 WHERE s.generation=%s
                   ORDER BY f.parameters,f.received_at,f.sha256,f.outcome""", (digest,))
    calendars = []
    for params, at, outcome, expected, payload in cur:
        if expected is not None and (payload is None or sha256(payload).hexdigest() != expected):
            raise ValueError('Calendar payload digest mismatch')
        calendars.append(dict(parameters=params, received_at=at.isoformat(), digest=expected, outcome=outcome))
    if calendars != manifest['calendar_sources']:
        raise ValueError('Pinned calendars disagree with the manifest')
    return dict(digest=digest, clubs=len(manifest['clubs']), snapshots=len(manifest['members']),
                missing_scopes=len(manifest['missing']), calendar_receipts=len(calendars), current_serving_eligible=False)
