"""Assemble an immutable inventory of one represented candidate generation."""

from hashlib import sha256
import json

from psycopg2.extras import Json

from services.availability_reference_date import trusted_slate_reference_dates
from services.mlb_club_directory import MLB_TEAM_IDS
from services.game_finality import classify_status
from services.role_movement import GAME_TYPES
from services.pitcher_public_labels import build_public_arm_read
from services.team_state_public_vocabulary import PUBLIC_STATE_LABELS
from services.team_state_vnext_production_proof import _reference_date_alignment
from sync_v3.change_history import COMPARISONS
from sync_v3.cohort import compare_games, compare_membership, verify_change_lineage
from sync_v3.comparison import compare_readiness
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import encode_json, latest_source_status, replay
from sync_v3.schedule_context import missing_listings
from sync_v3.history import METHODOLOGY, _transaction, encoded_evidence_digest, encoded_request
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
    result['games'] = _competitive_games(games)
    result['reason'] = None
    return result, {source}


def _transaction_receipt(params, acquired, outcome, digest, payload, reason):
    if digest is not None and (payload is None or sha256(payload).hexdigest() != digest):
        raise ValueError('Transaction payload digest mismatch')
    count = None
    if outcome == 'received' and reason is None:
        if payload is None:
            raise ValueError('Transaction receipt lacks its payload')
        count = len(json.loads(bytes(payload))['transactions'])
    return dict(parameters=params, recorded_at=acquired.isoformat(),
                acquired_at=acquired.isoformat() if digest else None, outcome=outcome,
                digest=digest, reason=reason, reported_records=count)


def _confirmed_transactions(cur, source):
    cur.execute("""SELECT c.identity,r.revision,r.facts FROM candidate.confirmations c
                   JOIN candidate.revisions r ON r.id=c.revision_id AND r.domain=c.domain AND r.identity=c.identity
                   WHERE c.source_id=%s AND c.domain='transaction' ORDER BY c.identity""", (source,))
    return cur.fetchall()


def _bind_transaction_revisions(cur, source, receipt):
    if receipt['reported_records'] is not None:
        rows = _confirmed_transactions(cur, source)
        receipt.update(confirmed_transactions=len(rows), revisions_digest=sha256(encode_json(rows)).hexdigest())


def _competitive_games(games):
    result = []
    for game in sorted(games, key=lambda item: item['gamePk']):
        if game['gameType'] in GAME_TYPES:
            status = classify_status(game['status'])
            result.append(dict(game_pk=game['gamePk'], game_type=game['gameType'],
                               home=game['teams']['home']['team']['id'], away=game['teams']['away']['team']['id'],
                               status=status.state, final=status.final_status))
    return result


def freeze_generation(connection, through):
    return _transaction(connection, _freeze, through)


CLUB_INPUTS = {DOMAINS[d][1]: d for d in ('depth', 'readiness', 'rotation')}


def _inventory(through, reference, team_inputs, slate):
    club_methods = {method for subject, method, _ in DOMAINS.values() if subject == 'team'} | {METHODOLOGY}
    club_methods.update(f'candidate_{domain}_changes_v1' for domain in COMPARISONS if domain != 'pitcher_rest')
    pitcher_methods = {METHODOLOGY, DOMAINS['pitcher_rest'][1], DOMAINS['pitcher_profile'][1],
                      'candidate_pitcher_rest_changes_v1'}
    game_method = DOMAINS['game_deployment'][1]
    expected, clubs = set(), []
    for team in sorted(MLB_TEAM_IDS):
        expected.update(('team', team, method) for method in club_methods)
        inputs = team_inputs.get(team, {})
        depth, rotation = inputs.get('depth'), inputs.get('rotation')
        pitchers, games = None, None
        if depth:
            view = depth['views']['active']
            hydrated = depth.get('active_profiles') or {}
            if view['pitchers'] and not view['reason'] and hydrated.get('reason') != 'mlb_active_rosters_disagree':
                pitchers = sorted(map(int, view['pitchers']))
                expected.update(('pitcher', player, method) for player in pitchers for method in pitcher_methods)
        if rotation:
            club_day = rotation['dates'][through.isoformat()]
            if not club_day['reason']:
                games = sorted(game['game_pk'] for game in club_day['games'])
                expected.update(('game', game, game_method) for game in games)
        clubs.append(dict(team=team, pitchers=pitchers, regular_season_finals=games,
                          readiness=_readiness_status(team, through, reference, inputs.get('readiness'))))
    for game in slate['games'] or ():
        if game['final']:
            expected.add(('game', game['game_pk'], game_method))
    return expected, clubs


def _assemble(cur, through):
    membership, reference = trusted_slate_reference_dates(through)
    if membership != through or reference is None:
        raise ValueError('A represented baseball date is required')
    cur.execute("""SELECT DISTINCT ON (subject,mlb_id,methodology) subject,mlb_id,methodology,id,revision,
                   semantic_digest,input_digest,CASE WHEN methodology=ANY(%s) THEN facts END
                   FROM candidate.workload_history WHERE represented=%s
                   ORDER BY subject,mlb_id,methodology,revision DESC""",
                (list(CLUB_INPUTS), through))
    snapshots = {}
    for subject, entity, method, sid, revision, semantic, inputs, facts in cur:
        snapshots[subject, entity, method] = (sid, revision, semantic, inputs, facts)
    slate, seen = _slate(cur, through)
    next_slate, upcoming = _slate(cur, reference)
    team_inputs = {}
    for (subject, entity, method), snapshot in snapshots.items():
        if subject == 'team' and method in CLUB_INPUTS:
            team_inputs.setdefault(entity, {})[CLUB_INPUTS[method]] = snapshot[-1]
    expected, clubs = _inventory(through, reference, team_inputs, slate)
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
    cur.execute("SELECT digest, payload ? 'publication_reference' FROM candidate.public_identity_export ORDER BY observed_at DESC LIMIT 1")
    identity_export = cur.fetchone()
    if identity_export:
        manifest['public_identity_export'] = identity_export[0]
        if identity_export[1]:
            cur.execute("""SELECT digest FROM candidate.public_identity_export
                           WHERE payload ? 'publication_reference' AND digest<>%s ORDER BY digest""", (identity_export[0],))
            earlier = [row[0] for row in cur]
            if earlier:
                manifest['earlier_public_identity_exports'] = earlier
    transaction_request = calendar_requests(through)[1]
    receipt = latest_source_status(cur, transaction_request.endpoint, transaction_request.params())
    sources = schedule_sources
    if receipt:
        source, outcome, reason = receipt
        cur.execute("""SELECT f.parameters,f.received_at,f.sha256,p.encoded_json FROM candidate.fetches f
                       LEFT JOIN candidate.payloads p USING (sha256) WHERE f.id=%s""", (source,))
        params, acquired, fingerprint, payload = cur.fetchone()
        manifest['transaction_source'] = _transaction_receipt(params, acquired, outcome, fingerprint, payload, reason)
        _bind_transaction_revisions(cur, source, manifest['transaction_source'])
        sources = [*schedule_sources, source]
    return manifest, parents, sources


def _freeze(cur, through):
    manifest, parents, sources = _assemble(cur, through)
    digest = sha256(encode_json(manifest)).hexdigest()
    cur.execute("""INSERT INTO candidate.generations (digest,represented,manifest) VALUES (%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING digest""", (digest, through, Json(manifest)))
    if not cur.fetchone():
        return digest
    cur.executemany("""INSERT INTO candidate.generation_inputs VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    [(digest, parent) for parent in parents])
    cur.executemany('INSERT INTO candidate.generation_sources VALUES (%s,%s) ON CONFLICT DO NOTHING',
                    [(digest, source) for source in sources])
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
                   UNION
                   SELECT h.subject,h.mlb_id,h.methodology FROM candidate.workload_history h
                   WHERE h.id=ANY(%s) AND h.methodology=%s AND NOT EXISTS (
                       SELECT 1 FROM candidate.history_requests r WHERE r.snapshot=h.id)
                   ORDER BY 1,2,3""", (parents, parents, parents, METHODOLOGY))
    stale_inputs = cur.fetchall()
    return stale_comparisons, stale_inputs


def _build_change_set(cur, domain, subject, entity, through):
    from datetime import timedelta
    from sync_v3.change_history import _freeze_changes, refresh_existing_changes
    from sync_v3.history import _append as append_workload
    from sync_v3.intelligence_history import _append as append_intelligence

    method = METHODOLOGY if domain == 'team' else DOMAINS[domain][1]
    days = (through - timedelta(days=1), through)
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', (subject, entity))
    cur.execute("""SELECT DISTINCT ON (represented) represented,id FROM candidate.workload_history
                   WHERE subject=%s AND mlb_id=%s AND methodology=%s AND represented BETWEEN %s AND %s
                   ORDER BY represented,revision DESC""", (subject, entity, method, *days))
    latest = dict(cur.fetchall())
    updated = []
    for day in days:
        previous = latest.get(day)
        if previous is not None:
            _, stale = _superseded(cur, [previous])
            if not stale:
                continue
        row = (append_workload(cur, subject, entity, day) if domain == 'team'
               else append_intelligence(cur, domain, entity, day))
        updated.append(row[0])
    if updated:
        refresh_existing_changes(cur, updated)
    return _freeze_changes(cur, domain, entity, through)


def build_batch(connection, through, limit):
    """Materialize a bounded batch of missing or superseded candidate calculations."""
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
            _transaction(connection, _build_change_set, changes_for[method], subject, entity, through)
        else:
            build(subject, entity, method, through)
    return dict(before=initial, after=freeze_generation(connection, through), processed=selected)


def review_coverage(manifest):
    """Explain the scope of a verified research generation before any public contract review."""
    clubs = manifest['clubs']
    if sorted(club['team'] for club in clubs) != sorted(MLB_TEAM_IDS):
        raise ValueError('Readiness accounting requires 30 distinct MLB clubs')
    compared, season_complete, withheld = [], [], {}
    for club in clubs:
        if club['readiness'] == 'compared':
            compared.append(club['team'])
        elif club['readiness'] == 'season_complete':
            season_complete.append(club['team'])
        else:
            withheld[club['team']] = club['readiness']
    if withheld:
        status = 'incomplete_readiness'
    elif not compared:
        status = 'all_clubs_season_complete'
    else:
        status = 'represented_readiness_accounted'
    return dict(readiness_status=status, compared=sorted(compared), season_complete=sorted(season_complete),
                withheld=withheld, missing_active_populations=[c['team'] for c in clubs if c['pitchers'] is None],
                missing_snapshot_count=len(manifest['missing']), stale_inputs=manifest['stale_inputs'],
                stale_comparisons=manifest['stale_comparisons'],
                slate_reason=manifest['slate']['reason'], next_slate_reason=manifest['next_slate']['reason'],
                current_serving_eligible=False)


def verify_generation(connection, digest, *, compare_latest=False):
    """Independently recount the pinned inventory, including its immutable facts and calendars."""
    return _transaction(connection, _verify, digest, compare_latest)


def _verify(cur, digest, compare_latest):
    cur.execute('SET TRANSACTION READ ONLY')
    return _inspect(cur, digest, compare_latest)


def _pinned_members(cur, stream):
    """Read facts and their evidence in bounded batches from the same transaction."""
    while rows := stream.fetchmany(8):
        snapshots = [row[0] for row in rows]
        receipts = {sid: [] for sid in snapshots}
        requests = {sid: [] for sid in snapshots}
        cur.execute("""SELECT grouped.snapshots,f.endpoint,f.parameters,f.sha256,f.outcome,coalesce(r.reason,f.reason)
                       FROM (SELECT source_id,array_agg(snapshot) AS snapshots FROM candidate.workload_history_sources
                             WHERE snapshot=ANY(%s) GROUP BY source_id) grouped
                       JOIN candidate.fetches f ON f.id=grouped.source_id
                       LEFT JOIN candidate.refusals r ON r.source_id=f.id""", (snapshots,))
        for linked, *receipt in cur:
            encoded = encode_json(receipt)
            for sid in linked:
                receipts[sid].append(encoded)
        cur.execute("""SELECT array_agg(snapshot),endpoint,parameters FROM candidate.history_requests
                       WHERE snapshot=ANY(%s) GROUP BY endpoint,parameters""", (snapshots,))
        for linked, endpoint, params in cur:
            scope = (endpoint, tuple(sorted(params.items())))
            descriptor = (scope, encoded_request(endpoint, params))
            for sid in linked:
                requests[sid].append(descriptor)
        for row in rows:
            yield row, encoded_evidence_digest(receipts[row[0]], requests[row[0]])


def _inspect(cur, digest, compare_latest):
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
    declared = set(members)
    missing = [tuple(s) for s in manifest['missing']]
    team_inputs = {}
    # Pitch profiles and game facts can be large. Keep memory bounded during full verification.
    with cur.connection.cursor(name='verify_candidate_members') as stream:
        stream.execute("""SELECT h.id,h.subject,h.mlb_id,h.represented,h.methodology,h.revision,h.semantic_digest,h.input_digest,h.facts
                       FROM candidate.generation_inputs p JOIN candidate.workload_history h ON h.id=p.snapshot
                       WHERE p.generation=%s""", (digest,))
        for row, evidence in _pinned_members(cur, stream):
            _, subject, entity, day, method, revision, semantic, inputs, facts = row
            if evidence != inputs:
                raise ValueError('Pinned snapshot sources disagree with the frozen input digest')
            actual = sha256(encode_json([subject, entity, day.isoformat(), method, facts])).hexdigest()
            if subject == 'team' and method in CLUB_INPUTS:
                team_inputs.setdefault(entity, {})[CLUB_INPUTS[method]] = facts
            member = members.pop((subject, entity, method), None)
            if (not member or day != through or member['revision'] != revision or member['input_digest'] != inputs
                    or semantic != actual or member['semantic_digest'] != actual):
                raise ValueError(f'Pinned candidate snapshot disagrees with the manifest: '
                                 f'{subject} {entity}, {day}, {method} revision {revision}')
    _, reference = trusted_slate_reference_dates(through)
    expected_scopes, clubs = _inventory(through, reference, team_inputs, manifest['slate'])
    if (clubs != manifest['clubs'] or manifest['availability_reference'] != reference.isoformat()
            or declared.union(missing) != expected_scopes or len(missing) != len(set(missing))):
        raise ValueError('Pinned facts disagree with declared club or scope coverage')
    if members:
        raise ValueError('Missing pinned candidate snapshots')
    cur.execute("""SELECT f.parameters,f.received_at,f.outcome,f.sha256,p.encoded_json,f.endpoint,coalesce(r.reason,f.reason),f.id
                   FROM candidate.generation_sources s JOIN candidate.fetches f ON f.id=s.source
                   LEFT JOIN candidate.payloads p ON p.sha256=f.sha256 LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE s.generation=%s
                   ORDER BY f.parameters,f.received_at,f.sha256,f.outcome,f.id""", (digest,))
    calendars = []
    dates = (through, reference)
    requests = [calendar_requests(day)[0].params() for day in dates]
    by_date = [[], []]
    transaction = None
    transaction_request = calendar_requests(through)[1]
    transaction_source_id = None
    for params, at, outcome, expected, payload, endpoint, reason, source_id in cur:
        if endpoint == transaction_request.endpoint:
            if transaction is not None or params != transaction_request.params():
                raise ValueError('Unexpected pinned transaction scope')
            transaction_source_id = source_id
            transaction = _transaction_receipt(params, at, outcome, expected, payload, reason)
            continue
        if endpoint != '/schedule' or params not in requests:
            raise ValueError('Unexpected source in pinned calendars')
        by_date[requests.index(params)].append((outcome, reason, payload))
        if expected is not None and (payload is None or sha256(payload).hexdigest() != expected):
            raise ValueError('Calendar payload digest mismatch')
        calendars.append(dict(parameters=params, received_at=at.isoformat(), digest=expected, outcome=outcome))
    if transaction is not None:
        _bind_transaction_revisions(cur, transaction_source_id, transaction)
    if transaction != manifest.get('transaction_source'):
        raise ValueError('Pinned transaction receipt disagrees with the manifest')
    if calendars != manifest['calendar_sources']:
        raise ValueError('Pinned calendars disagree with the manifest')
    for index, key in enumerate(('slate', 'next_slate')):
        slate = manifest[key]
        if slate['represented'] != dates[index].isoformat():
            raise ValueError('Misaligned pinned calendar date')
        if slate['reason']:
            if slate['games'] is not None:
                raise ValueError('Withheld calendar declares games')
            continue
        receipts = by_date[index]
        if len(receipts) != 1 or receipts[0][:2] != ('received', None) or receipts[0][2] is None:
            raise ValueError('Calendar lacks a pinned successful receipt')
        games = [g for entry in json.loads(bytes(receipts[0][2]))['dates'] for g in entry['games']]
        if slate['games'] != _competitive_games(games):
            raise ValueError('Declared games disagree with pinned calendar')
    if 'public_identity_export' in manifest:
        from sync_v3.public_identities import verify_reference
        source, latest = verify_reference(cur, manifest['public_identity_export'])
        archives = manifest.get('earlier_public_identity_exports', [])
        if archives != sorted(set(archives)):
            raise ValueError('Invalid supplemental identity archive inventory')
        for earlier in archives:
            archive_source, observed = verify_reference(cur, earlier)
            if archive_source != 'BaseballOS.observed_team_state_publication' or archive_source != source or observed >= latest:
                raise ValueError('Expected a prior observed identity archive')
    coverage = review_coverage(manifest)
    rosters = compare_membership(cur, digest, through.isoformat())
    games = compare_games(cur, digest, manifest)
    report = dict(digest=digest, represented=through.isoformat(), availability_reference=manifest['availability_reference'],
                coverage=coverage, roster_comparison=rosters, game_comparison=games,
                historical_changes=verify_change_lineage(cur, digest, through),
                core_candidate_review=review_core_candidate(coverage, rosters, games),
                clubs=len(manifest['clubs']), snapshots=len(manifest['members']),
                missing_scopes=len(manifest['missing']), calendar_receipts=len(calendars), transaction_source=transaction, current_serving_eligible=False)
    if compare_latest:
        inventory, _, _ = _assemble(cur, through)
        current = sha256(encode_json(inventory)).hexdigest()
        review = report['core_candidate_review']
        if current != digest:
            review = dict(status='withheld', reason_codes=['superseded_generation'])
        report['selection_review'] = dict(**review, latest_inventory_digest=current, represented=through.isoformat(),
                                          scope='isolated_historical_core')
    return report


def review_core_candidate(coverage, rosters, games):
    """Scope the historical readiness and final-game review. Public serving requires separate proof."""
    reasons = []
    if coverage['stale_inputs'] or coverage['stale_comparisons']:
        reasons.append('superseded_evidence')
    active = coverage['compared']
    if coverage['readiness_status'] == 'all_clubs_season_complete' and not reasons:
        return dict(status='season_complete_withholding', reason_codes=[])
    if coverage['withheld']:
        reasons.append('unresolved_club_readiness')
    if coverage['missing_snapshot_count']:
        reasons.append('missing_candidate_scopes')
    if coverage['slate_reason'] or coverage['next_slate_reason']:
        reasons.append('incomplete_represented_schedule')
    if set(active).intersection(coverage['missing_active_populations']):
        reasons.append('missing_dated_population')
    if rosters['multiple_clubs'] or any(rosters['clubs'].get(team) != 'matched' for team in active):
        reasons.append('active_membership_unverified')
    if games['open_games']:
        reasons.append('represented_slate_still_open')
    if any(value != 'matched' for value in games['finals'].values()):
        reasons.append('official_final_unverified')
    return dict(status='withheld' if reasons else 'core_comparison_complete', reason_codes=reasons)
