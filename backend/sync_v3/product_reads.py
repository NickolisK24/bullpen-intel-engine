"""Read the isolated historical League listing at one committed selector revision."""

from services.bullpen_board import build_rest_status
from services.league_team_state_listing import build_league_team_state_row
from services.mlb_club_directory import MLB_CLUBS
from services.team_state_public_vocabulary import (
    INTERNAL_TO_PUBLIC_STATE, PUBLIC_STATE_LABELS, TEAM_STATE_READINESS_UNAVAILABLE,
    public_team_state, team_state_unavailable,
)
from sync_v3.appearance_reads import appearance_ledger
from sync_v3.generation import _inspect
from sync_v3.history import _transaction
from sync_v3.intelligence_history import DOMAINS
from sync_v3.team_history_reads import read_calendar_context


def _read_transaction(connection, reader, *args):
    def read(cur):
        cur.execute('SET TRANSACTION READ ONLY')
        return reader(cur, *args)
    return _transaction(connection, read)


def read_league(connection, *, revision=None):
    """Pin either the current research selection or an explicit, immutable selector revision."""
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')
    return _read_transaction(connection, _league, revision, None)


def preview_league(connection, digest):
    """Inspect club evidence from an explicitly identified, independently verified candidate."""
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError('Expected a candidate digest')
    return _read_transaction(connection, _league, None, digest)


def _selected(cur, revision):
    cur.execute("""SELECT s.revision,s.generation,g.represented,g.manifest->>'availability_reference'
                   FROM candidate.core_selections s LEFT JOIN candidate.generations g ON g.digest=s.generation
                   WHERE (%s IS NULL OR s.revision=%s) ORDER BY s.revision DESC LIMIT 1""", (revision, revision))
    return cur.fetchone()


def _movement(change, current, snapshot):
    if change.get('status') not in ('complete', 'partial_arm_coverage'):
        return None
    before, after = change['lineage']
    if after['facts_digest'] != snapshot:
        raise ValueError('League movement disagrees with the selected readiness revision')
    events = [event for event in change['events'] if event['kind'] == 'team_state_changed']
    if events:
        event, = events
        if event['current'] != current:
            raise ValueError('League movement disagrees with the represented state')
        previous = event['previous']
    else:
        previous = current
    return dict(previous_label=PUBLIC_STATE_LABELS[previous], since=before['represented'],
                event_id=events[0]['event_id'] if events else None)


def _orientation(facts, change, digest):
    cards = []
    for arm in facts['arms'].values():
        availability = (arm['read'] or {}).get('availability') or {}
        inputs = availability.get('inputs') or {}
        cards.append(dict(data_state=availability.get('data_state'), workload_facts=dict(
            days_since_last_appearance=inputs.get('days_rest'), back_to_back=inputs.get('back_to_back'))))
    rest = build_rest_status(cards)
    counts = None
    if rest['available']:
        counts = {key: rest[key] for key in ('rested_arm_count', 'worked_yesterday_count', 'back_to_back_count')}
    return dict(rest=counts, rest_reference_date=facts['reference_date'],
                movement=_movement(change, facts['team_state']['public_code'], digest))


def _league(cur, revision, preview):
    result = dict(scope='isolated_historical_core', current_serving_eligible=False, selection_revision=None,
                  generation=None, data_through=None, availability_reference=None, teams=[], citations={})
    blocked = {}
    if preview is None:
        selected = _selected(cur, revision)
        if not selected or selected[1] is None:
            status = 'unknown_revision' if revision is not None and not selected else 'no_selected_generation'
            return dict(result, status=status, selection_revision=selected[0] if selected else None)
        sequence, generation, through, reference = selected
    else:
        report = _inspect(cur, preview, compare_latest=False)
        result['core_candidate_review'] = report['core_candidate_review']
        coverage = report['coverage']
        if coverage['stale_inputs'] or coverage['stale_comparisons']:
            blocked = {club.team_id: 'superseded_evidence' for club in MLB_CLUBS}
        else:
            blocked.update(coverage['withheld'])
            for team in coverage['compared']:
                reason = report['roster_comparison']['clubs'][team]
                if reason != 'matched':
                    blocked[team] = reason
        cur.execute("SELECT represented,manifest->>'availability_reference' FROM candidate.generations WHERE digest=%s",
                    (preview,))
        through, reference = cur.fetchone()
        sequence, generation = None, preview
    readiness = DOMAINS['readiness'][1]
    changes = 'candidate_readiness_changes_v1'
    cur.execute("""SELECT h.mlb_id,h.methodology,h.facts,h.semantic_digest,h.input_digest,h.revision
                   FROM candidate.generation_inputs i JOIN candidate.workload_history h ON h.id=i.snapshot
                   WHERE i.generation=%s AND h.subject='team' AND h.methodology=ANY(%s)""",
                (generation, [readiness, changes]))
    rows = {}
    for team, method, facts, semantic, inputs, version in cur:
        rows[team, method] = facts, dict(revision=version, facts_digest=semantic, input_digest=inputs)
    status_for = {code: internal for internal, code in INTERNAL_TO_PUBLIC_STATE.items()}
    for club in sorted(MLB_CLUBS, key=lambda c: (c.team_name.casefold(), c.team_id)):
        facts, source = rows.get((club.team_id, readiness), ({}, None))
        change, change_source = rows.get((club.team_id, changes), ({}, None))
        if club.team_id in blocked:
            block = team_state_unavailable(TEAM_STATE_READINESS_UNAVAILABLE, data_through=through.isoformat(),
                                           reason_code=blocked[club.team_id])
        else:
            if facts.get('membership_date') != through.isoformat() or facts.get('reference_date') != reference:
                raise ValueError('League dates disagree with the selected generation')
            state = facts['team_state']
            block = public_team_state(dict(season_context=facts['competition'],
                                           freshness=dict(data_through=through.isoformat()),
                                           status_code=status_for[state['public_code']] if state else None))
        identity = dict(team_id=club.team_id, team_abbreviation=club.abbreviation, team_name=club.team_name)
        row = build_league_team_state_row(identity, block)
        row['orientation'] = _orientation(facts, change, source['facts_digest']) if block['available'] else None
        result['teams'].append(row)
        result['citations'][club.team_id] = dict(readiness=source, changes=change_source)
    return dict(result, status='candidate_preview' if preview else 'represented', selection_revision=sequence, generation=generation,
                data_through=through.isoformat(), availability_reference=reference)


def read_team_events(connection, team, *, revision=None):
    """The shared dated event slice for candidate Team Board and History reads."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    if type(team) is not int or team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB team identity')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')
    return _read_transaction(connection, _events, team, revision)


def _events(cur, team, revision):
    return _event_slice(cur, team, revision, _selected(cur, revision))


def preview_team_events(connection, team, digest):
    from services.mlb_club_directory import MLB_TEAM_IDS
    if type(team) is not int or team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB team identity')

    def preview(cur):
        report = _inspect(cur, digest, compare_latest=False)
        coverage = report['coverage']
        if coverage['stale_inputs'] or coverage['stale_comparisons'] or coverage['missing_snapshot_count']:
            return dict(status='incomplete_generation', generation=digest, events=[], current_serving_eligible=False)
        cur.execute('SELECT represented FROM candidate.generations WHERE digest=%s', (digest,))
        day, = cur.fetchone()
        result = _event_slice(cur, team, None, (None, digest, day, None))
        return dict(result, status='candidate_preview', core_candidate_review=report['core_candidate_review'])
    return _read_transaction(connection, preview)


def _event_slice(cur, team, revision, selection):
    from sync_v3.change_history import COMPARISONS
    result = dict(team=team, scope='isolated_historical_core', current_serving_eligible=False,
                  selection_revision=selection[0] if selection else None, generation=None,
                  represented=None, events=[], comparisons=[])
    if not selection or selection[1] is None:
        status = 'unknown_revision' if revision is not None and not selection else 'no_selected_generation'
        return dict(result, status=status)
    _, generation, through, _ = selection
    result.update(represented=through.isoformat(), generation=generation)
    # A pitcher change belongs on this club's feed only when the bullpen population
    # is known on both days and the player belonged to this club's group on both.
    cur.execute("""SELECT p.facts->'arms',p.facts->'team_state'
                   FROM candidate.generation_inputs g JOIN candidate.workload_history e ON e.id=g.snapshot
                   JOIN candidate.change_inputs i ON i.change_snapshot=e.id
                   JOIN candidate.workload_history p ON p.id=i.input_snapshot
                   WHERE g.generation=%s AND e.subject='team' AND e.mlb_id=%s
                   AND e.methodology='candidate_readiness_changes_v1' ORDER BY p.represented""", (generation, team))
    populations = [set(map(int, arms)) if state else None for arms, state in cur]
    comparable = len(populations) == 2 and all(arms is not None for arms in populations)
    arms = sorted(populations[0] & populations[1]) if comparable else []
    team_methods = [f'candidate_{domain}_changes_v1' for domain in COMPARISONS if domain != 'pitcher_rest']
    cur.execute("""SELECT h.subject,h.mlb_id,h.methodology,h.revision,h.semantic_digest,h.input_digest,h.facts
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND ((h.subject='team' AND h.mlb_id=%s AND h.methodology=ANY(%s))
                   OR (h.subject='pitcher' AND h.mlb_id=ANY(%s) AND h.methodology='candidate_pitcher_rest_changes_v1'))
                   ORDER BY h.subject,h.mlb_id,h.methodology""", (generation, team, team_methods, arms))
    for subject, entity, method, version, semantic, inputs, facts in cur:
        citation = dict(subject=subject, mlb_id=entity, methodology=method, revision=version,
                        facts_digest=semantic, input_digest=inputs, lineage=facts['lineage'])
        result['comparisons'].append(dict(status=facts['status'], citation=citation))
        for event in facts['events']:
            result['events'].append(dict(event=event, team=team, represented=through.isoformat(), citation=citation))
    result['pitcher_pattern_population_status'] = 'comparable' if comparable else 'missing_comparable_bullpen'
    return dict(result, status='represented')


def _schedule_rows(cur, generation, reference):
    """Resolve the exact, previously verified calendar receipt for the edition."""
    from psycopg2.extras import Json
    from models.slate_game import SlateGame
    from services.schedule_authority import slate_fields_from_game
    from sync_v3.discovery import calendar_requests
    from sync_v3.evidence import replay

    request = calendar_requests(reference)[0]
    cur.execute("""SELECT f.id,g.manifest->'next_slate' FROM candidate.generations g
                   JOIN candidate.generation_sources gs ON gs.generation=g.digest
                   JOIN candidate.fetches f ON f.id=gs.source
                   WHERE g.digest=%s AND f.endpoint=%s AND f.parameters=%s AND f.outcome='received'""",
                (generation, request.endpoint, Json(request.params())))
    matches = cur.fetchall()
    if len(matches) != 1 or matches[0][1]['reason']:
        raise ValueError('Edition lacks a complete pinned schedule')
    source, slate = matches[0]
    receipt = replay(cur, source)
    represented = {g['game_pk']: g for g in slate['games']}
    rows = []
    for entry in receipt.body['dates']:
        for game in entry['games']:
            if game['gamePk'] not in represented:
                continue
            fields = slate_fields_from_game(game, synced_at=receipt.retrieved_at)
            if not fields or fields['game_date_et'] != reference:
                raise ValueError('Unsupported first pitch or product date')
            rows.append(SlateGame(**fields))
    if {row.game_pk for row in rows} != represented.keys():
        raise ValueError('Frozen slate disagrees with represented games')
    return rows


def _public_arms(cur, digest):
    """Resolve only represented bullpen members using the club receipt pinned by readiness."""
    cur.execute("SELECT manifest->>'public_identity_export' FROM candidate.generations WHERE digest=%s", (digest,))
    export, = cur.fetchone()
    cur.execute("""SELECT h.mlb_id,h.facts->'arms',r.facts->'members' FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   LEFT JOIN LATERAL (SELECT rev.facts FROM candidate.workload_history_sources hs
                     JOIN candidate.fetches f ON f.id=hs.source_id
                     JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='roster'
                     JOIN candidate.revisions rev ON rev.id=c.revision_id
                     WHERE hs.snapshot=h.id AND f.endpoint='/teams/' || h.mlb_id::text || '/roster'
                     AND f.parameters=jsonb_build_object('date',h.represented::text,'rosterType','active')
                     AND c.identity=h.mlb_id::text || '/active/' || h.represented::text) r ON true
                   WHERE g.generation=%s AND h.methodology=%s""", (digest, DOMAINS['readiness'][1]))
    players = {}
    for team, arms, roster in cur:
        entries = {member['id']: member for member in roster or ()}
        for key in arms:
            mlb = int(key)
            name = entries.get(mlb, {}).get('name')
            if mlb in players or not isinstance(name, str) or not name.strip():
                return {}, 'official_pitcher_identity_unresolved'
            position = {'1': 'P', 'Y': 'TWP'}.get(entries[mlb].get('position'))
            players[mlb] = dict(mlb_id=mlb, team_id=team, name=name, position=position, public_id=None)
    if export is None:
        return players, 'public_id_mapping_unavailable'
    cur.execute('SELECT mlb_id,pitcher_id FROM candidate.public_pitcher_ids WHERE export=%s AND mlb_id=ANY(%s)',
                (export, sorted(players)))
    mapping = dict(cur)
    for mlb, public_id in mapping.items():
        players[mlb]['public_id'] = public_id
    return players, 'mapped' if players.keys() == mapping.keys() else 'public_id_mapping_incomplete'


def _pitcher_directory(cur, digest):
    """Add named departures from this edition without inferring a receiving club or current role."""
    players, status = _public_arms(cur, digest)
    if status == 'official_pitcher_identity_unresolved':
        return players, status
    cur.execute("""SELECT h.mlb_id,h.represented,h.semantic_digest,h.input_digest,h.revision,h.facts->'lineage',e.event,p.pitcher_id
                   FROM candidate.generations edition JOIN candidate.generation_inputs g ON g.generation=edition.digest
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   CROSS JOIN LATERAL jsonb_array_elements(h.facts->'events') e(event)
                   LEFT JOIN candidate.public_pitcher_ids p ON p.export=edition.manifest->>'public_identity_export'
                     AND p.mlb_id=(e.event->>'player')::integer
                   WHERE edition.digest=%s AND h.subject='team' AND h.methodology='candidate_depth_changes_v1'
                     AND h.facts->>'status'='complete' AND e.event->>'kind'='active_roster_removed'
                   ORDER BY h.mlb_id,e.event->>'event_id'""", (digest,))
    unresolved = set()
    for club, represented, facts, inputs, revision, lineage, event, public_id in cur:
        mlb = event['player']
        name = event['pitcher_name']
        if mlb in unresolved:
            continue
        departure = dict(team=club, represented=represented.isoformat(), event=event,
                         citation=dict(subject='team', mlb_id=club, methodology='candidate_depth_changes_v1',
                                       revision=revision, facts_digest=facts, input_digest=inputs, lineage=lineage))
        if mlb in players:
            player = players[mlb]
            if player['team_id'] == club or 'historical_departure' in player or player['public_id'] != public_id:
                unresolved.add(mlb)
                del players[mlb]
                continue
            player['historical_departure'] = departure
            continue
        if not isinstance(name, str) or not name.strip():
            unresolved.add(mlb)
            continue
        players[mlb] = dict(mlb_id=mlb, public_id=public_id, name=name, position=None, team_id=None,
                            historical_departure=departure)
        if public_id is None and status == 'mapped':
            status = 'public_id_mapping_incomplete'
    return players, 'historical_departure_identity_unresolved' if unresolved else status


def read_search(connection, query, *, revision=None, limit=5):
    from datetime import date
    from services.discovery_search import SearchOwners, matchup_results_from_rows, search_discovery
    from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN

    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def search(cur):
        selected = _selected(cur, revision)
        if not selected or not selected[1]:
            return dict(status='no_selected_generation', generation=None, selection_revision=revision,
                        current_serving_eligible=False, search=None)
        sequence, digest, _, reference = selected
        directory = {c.team_id: dict(team_id=c.team_id, team_abbreviation=c.abbreviation, team_name=c.team_name)
                     for c in MLB_CLUBS}
        players, mapping_status = _pitcher_directory(cur, digest)
        def pitchers(text, count, day):
            from services.pitcher_search import _match_rank, _normalize_search_text
            if mapping_status not in ('mapped', 'public_id_mapping_incomplete'):
                raise ValueError(mapping_status)
            ranked = []
            normalized = _normalize_search_text(text)
            for player in players.values():
                name = player['name']
                rank = _match_rank(name, normalized)
                if rank is None:
                    continue
                team = directory.get(player['team_id']) or {}
                pid = player['public_id']
                if pid is None:
                    raise ValueError(mapping_status)
                item = dict(entity_type='pitcher', id=pid, primary_label=name, secondary_label=team.get('team_name'),
                            metadata=dict(player_id=pid, player_name=name, position=player['position'], roster_status=STATUS_ACTIVE if team else STATUS_UNKNOWN,
                                          team_id=player['team_id'], team_name=team.get('team_name')))
                ranked.append((rank, _normalize_search_text(name), pid, item))
            return [row[-1] for row in sorted(ranked)[:count]]
        def matchups(text, clubs, day, count):
            return matchup_results_from_rows(text, clubs, day, count, _schedule_rows(cur, digest, day))
        owners = SearchOwners(teams=lambda: directory, pitchers=pitchers, matchups=matchups)
        payload = search_discovery(query, limit=limit, reference_date=date.fromisoformat(reference), owners=owners)
        return dict(status='represented', generation=digest, selection_revision=sequence, current_serving_eligible=False,
                    pitcher_identity_status=mapping_status, pitcher_scope='represented_bullpens_and_dated_departures', search=payload)
    return _read_transaction(connection, search)


def _season_comparison(facts):
    """Repeat only the qualified, represented active bullpen's official season facts."""
    from services import performance_metrics as rules
    from services.public_team_performance import WINDOW_POLICY, frozen_comparison_metrics

    window = (facts.get('windows') or {}).get('season')
    if facts.get('reason') or not window or not window['appearances']:
        return None, ()
    metrics = window['metrics']
    rows = []
    capabilities = {}
    for key, definition in [('active_bullpen_era', rules.CURRENT_ACTIVE_PEN_ERA),
                            ('active_bullpen_whip', rules.CURRENT_ACTIVE_PEN_WHIP)]:
        metric = metrics[definition.metric_id]
        qualified = metric['reason'] is None and metric['covered'] == window['appearances']
        rows.append(dict(key=key, metric_id=definition.metric_id, method_version=definition.version,
                         value=metric['value'], qualification=dict(status='qualified' if qualified else 'unavailable'),
                         evidence_state=dict(status='complete' if qualified else 'unavailable')))
    for key in ('home_runs_allowed', 'inherited_runner_context', 'k_bb_percent'):
        metric = metrics[key]
        if metric['reason'] is None and metric['value'] is not None and metric['covered'] == window['appearances']:
            capabilities[key] = dict(status='qualified', value=metric['value'])
    values, versions = frozen_comparison_metrics(dict(metrics=rows, capabilities=capabilities))
    if not values:
        return None, ()
    values['sample'] = dict(active_pitchers=len(facts['members']), relief_appearances=window['appearances'],
                            start=window['start'], through=facts['through'])
    stamp = (DOMAINS['group_performance'][1], WINDOW_POLICY, window['start'], facts['through'], *versions)
    return values, stamp


def _aligned_performance(away, home):
    from services.current_bullpen_comparison import _aligned_domain, _withheld_domain
    a, stamp_a = away
    b, stamp_b = home
    if not a or not b or not ((a.keys() & b.keys()) - {'sample'}):
        return _withheld_domain('performance')
    return _aligned_domain('performance', a, b, stamp_a=stamp_a, stamp_b=stamp_b, partial=a.keys() != b.keys())


def _league_changes(teams, citations, rotation_changes, generation, represented):
    """Project qualified changes from the same dated revisions used by Board and History."""
    from services import tonight_read_model as tonight
    changes = []
    for row in teams:
        movement = (row['orientation'] or {}).get('movement')
        current = row['team_state']['public_label']
        if not movement or not current or movement['previous_label'] == current:
            continue
        previous = movement['previous_label']
        team = row['team_id']
        receipt = citations[team]['changes']['facts_digest']
        changes.append(dict(change_id=movement['event_id'], team_id=team, team_abbreviation=row['team_abbreviation'],
                            change_class='team_state_changed', occurred_on=represented, evidence_state='complete',
                            headline=f"{row['team_abbreviation']} moved from {previous} to {current}.", detail=None,
                            source_ref=f'{generation}/{receipt}', game_pks=[], state_change={'from':previous, 'to':current}))
    from services.rotation_support_pressure import _baseball_innings
    abbreviations = {row['team_id']: row['team_abbreviation'] for row in teams}
    for team, comparison, receipt in rotation_changes:
        if comparison['status'] != 'complete':
            continue
        for event in comparison['events']:
            if event['kind'] != 'new_short_start':
                continue
            abbreviation = abbreviations[team]
            facts = event['facts']
            starter = _baseball_innings(facts['starter_outs'])
            bullpen = _baseball_innings(facts['bullpen_outs'])
            changes.append(dict(change_id=event['event_id'], team_id=team, team_abbreviation=abbreviation,
                                change_class=event['kind'], occurred_on=represented, evidence_state='complete',
                                headline=f'{abbreviation} recorded a {starter}-inning start.',
                                detail=f'The bullpen recorded {bullpen} innings.',
                                source_ref=f'{generation}/{receipt}', game_pks=[event['game']], state_change=None))
    result = []
    per_team = {}
    for change in sorted(changes, key=tonight._league_change_order):
        team = change['team_id']
        if per_team.get(team, 0) < tonight.LEAGUE_CHANGES_PER_TEAM:
            result.append(change)
            per_team[team] = per_team.get(team, 0) + 1
    return result[:tonight.LEAGUE_CHANGES_TOTAL]


def read_game_cards(connection, *, revision=None, game_pk=None):
    """Serve the same historical game card to the isolated slate and game detail."""
    from datetime import date
    from services import tonight_read_model as tonight
    from services.current_bullpen_comparison import _aligned_domain, named_role_rest
    from services.rotation_support_pressure import _baseball_innings, _split_limitation_reasons
    from sync_v3.history import METHODOLOGY

    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')
    if game_pk is not None and (type(game_pk) is not int or game_pk < 1):
        raise ValueError('Expected an official MLB game identity')

    def cards(cur):
        league = _league(cur, revision, None)
        generation = league['generation']
        result = {key: league[key] for key in ('scope', 'current_serving_eligible', 'selection_revision',
                                               'generation', 'data_through', 'availability_reference', 'status')}
        result.update(games=[], quiet_day=None)
        if generation is None:
            return result
        try:
            slate = _schedule_rows(cur, generation, date.fromisoformat(league['availability_reference']))
        except ValueError as exc:
            return dict(result, status='schedule_unavailable', reason=str(exc))
        ids = {club.team_id for club in MLB_CLUBS}
        games = [row for row in slate if not tonight.is_cancelled_slate_row(row)
                 and row.home_team_id in ids and row.away_team_id in ids]
        cur.execute("""SELECT h.mlb_id,h.facts,h.semantic_digest FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s
                       AND h.methodology='candidate_rotation_changes_v1' AND h.subject='team'
                       AND h.represented=%s ORDER BY h.mlb_id""", (generation, league['data_through']))
        changes = _league_changes(league['teams'], league['citations'], cur.fetchall(), generation, league['data_through'])
        result.update(quiet_day=not games, league_changes=changes, change_scope='comparable_team_state_and_short_starts',
                      featured_game_pks=[], lead=None, limitations=['additional_league_change_classes_unverified'])
        if game_pk is not None and all(row.game_pk != game_pk for row in games):
            return dict(result, status='game_outside_represented_slate')
        if not games:
            return dict(result, summary=tonight._summary([], {}, changes))
        clubs = {team for row in games for team in (row.home_team_id, row.away_team_id)}
        reads, rotation = DOMAINS['readiness'][1], DOMAINS['rotation'][1]
        cur.execute("""SELECT h.mlb_id,h.methodology,h.facts FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s AND h.subject='team'
                       AND h.mlb_id=ANY(%s) AND h.methodology=ANY(%s)""",
                    (generation, sorted(clubs), [METHODOLOGY, reads, rotation, DOMAINS['group_performance'][1]]))
        facts = {(team, method): body for team, method, body in cur}
        arms = {int(player) for team in clubs for player in facts[team, reads]['arms']}
        cur.execute("""SELECT h.mlb_id,h.facts->'rest'->'facts' FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s AND h.subject='pitcher'
                       AND h.mlb_id=ANY(%s) AND h.methodology=%s""", (generation, sorted(arms), DOMAINS['pitcher_rest'][1]))
        usage = {player: values or {} for player, values in cur}
        from services.pitcher_public_labels import build_pitcher_labels
        identities, identity_status = _public_arms(cur, generation)
        cur.execute("""SELECT h.mlb_id,h.facts#>'{deployment,facts,observed_role,role}'
                       FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                       WHERE g.generation=%s AND h.subject='pitcher' AND h.mlb_id=ANY(%s) AND h.methodology=%s""",
                    (generation, sorted(arms), DOMAINS['pitcher_profile'][1]))
        roles = dict(cur)
        from services.public_team_relief_work import DEPLOYMENT_PROFILE_WINDOW_DAYS
        from datetime import timedelta
        end = date.fromisoformat(league['data_through'])
        start = end - timedelta(days=DEPLOYMENT_PROFILE_WINDOW_DAYS - 1)
        cur.execute("""SELECT DISTINCT h.mlb_id,c.identity,r.id,r.facts
                       FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                       JOIN candidate.workload_history_sources hs ON hs.snapshot=h.id
                       JOIN candidate.confirmations c ON c.source_id=hs.source_id AND c.domain='final'
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE g.generation=%s AND h.methodology=%s AND h.mlb_id=ANY(%s)""",
                    (generation, rotation, sorted(clubs)))
        save_games = {}
        versions, ambiguous = set(), set()
        represented_games = {
            (club, game['game_pk']): day for club in clubs
            for day, daily in facts[club, rotation]['dates'].items() if not daily['reason']
            for game in daily['games']
        }
        for club, pk, _, lines in cur:
            represented = represented_games.get((club, int(pk)))
            if represented is None:
                continue
            if (club, pk) in versions:
                ambiguous.add(club)
            versions.add((club, pk))
            for line in lines:
                if (line['team_id'] == club and line['game_date'] == represented
                        and start.isoformat() <= represented <= end.isoformat()
                        and line['games_started'] == 0 and line['save'] == 1):
                    save_games.setdefault((club, line['pitcher_mlb_id']), set()).add(pk)
        sides, role_rests = {}, {}
        for row in league['teams']:
            team = row['team_id']
            if team not in clubs:
                continue
            ids = [int(player) for player in facts[team, reads]['arms']]
            state = row['team_state']
            orientation = row['orientation'] or {}
            counts = orientation.get('rest')
            rest = dict(counts, available=True, active_arm_count=len(ids)) if counts else None
            pressure = facts[team, rotation]['windows']['7']['pressure']
            if pressure and pressure.get('games_analyzed'):
                limitations = _split_limitation_reasons(
                    pressure['excluded_game_reasons'], games_in_window=pressure['games_in_window'],
                    games_analyzed=pressure['games_analyzed'], source_window_partial=bool(pressure['games_excluded']))
                pressure = dict(pressure, status='partial' if limitations else 'complete',
                                bullpen_innings=_baseball_innings(pressure['bullpen_outs_required']))
            key_arms, public_usage, active, named = [], {}, [], []
            # A key-arm ranking needs a complete identity map for this club.
            club_mapped = all(identities.get(mlb, {}).get('public_id') is not None for mlb in ids)
            for mlb in (ids if club_mapped else []):
                player = identities[mlb]
                read = facts[team, reads]['arms'][str(mlb)]['read'] or {}
                availability = read.get('availability') or {}
                inputs = availability.get('inputs') or {}
                role = build_pitcher_labels(availability, roles.get(mlb))['role']
                pid = player['public_id']
                active.append(dict(pitcher_id=pid, roster_state='active',
                                   days_since_last_appearance=usage.get(mlb, {}).get('days_since_last_appearance')))
                saves = len(save_games[team, mlb]) if team not in ambiguous and (team, mlb) in save_games else None
                named.append(dict(pitcher_id=pid, pitcher_name=player['name'], public_role_read=role,
                                  observed_profile=dict(saves=saves)))
                key_arms.append(dict(pitcher_id=player['public_id'], name=player['name'], public_role_read=role,
                                     workload=dict(days_since_last_appearance=inputs.get('days_rest'),
                                                   back_to_back=inputs.get('back_to_back'))))
                public_usage[player['public_id']] = usage.get(mlb)
            role_rests[team] = named_role_rest(active, named)
            overview = facts[team, METHODOLOGY]['windows']['workload']
            sides[team] = dict(team_id=team, abbreviation=row['team_abbreviation'], name=row['team_name'],
                               available=state['available'], reason_code=state['reason_code'],
                               team_state={k: state[k] for k in ('public_state','public_label','available','reason_code')},
                               rest=tonight._rest(rest), workload_7d=tonight._workload_7d(overview),
                               multi_day_usage=dict(three_in_four_count=tonight._three_in_four_count(
                                   [dict(pitcher_id=pid) for pid in ids], usage) if ids else None),
                               rotation=tonight._rotation(pressure), key_arms=tonight._key_arms(key_arms, public_usage), change_refs=[])
        result['games'] = sorted((tonight._game_card(row, sides[row.away_team_id], sides[row.home_team_id])
                                  for row in games), key=tonight._game_order)
        performances = {team: _season_comparison(facts[team, DOMAINS['group_performance'][1]]) for team in clubs}
        for card in result['games']:
            stamp = (generation, league['data_through'], league['availability_reference'], DOMAINS['pitcher_profile'][1],
                     DOMAINS['pitcher_rest'][1])
            card['role_rest'] = _aligned_domain('role_rest', role_rests[card['away']['team_id']],
                                                role_rests[card['home']['team_id']], stamp_a=stamp, stamp_b=stamp)
            card['performance'] = _aligned_performance(performances[card['away']['team_id']],
                                                       performances[card['home']['team_id']])
        tonight.attach_change_refs(sides.values(), changes)
        result['featured_game_pks'] = tonight.apply_featured_games(result['games'], changes)
        result['lead'] = tonight.select_lead(result['games'], changes)
        result['summary'] = tonight._summary(result['games'], sides, changes)
        if game_pk is not None:
            result['games'] = [game for game in result['games'] if game['game_pk'] == game_pk]
        if identity_status != 'mapped':
            result['limitations'].append(identity_status)
        return result
    return _read_transaction(connection, cards)


def _blocks(cur, generation, subject, entity, methods):
    cur.execute("""SELECT h.methodology,h.revision,h.semantic_digest,h.input_digest,h.facts
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.subject=%s AND h.mlb_id=%s AND h.methodology=ANY(%s)""",
                (generation, subject, entity, list(methods)))
    return {methods[method]: dict(value=facts, citation=dict(methodology=method, revision=revision,
                                 facts_digest=semantic, input_digest=inputs)) for method, revision, semantic, inputs, facts in cur}


def _pitch_hand(depth, player):
    """Report the official person attribute at acquisition when the dated MLB rosters agree."""
    facts = depth['value']
    active = facts['views']['active']
    hydrated = facts.get('active_profiles') or {}
    result = dict(value=None, basis=facts['profile_hand_basis'], observed_at=None, citation=depth['citation'])
    if active.get('reason') or hydrated.get('reason') or not hydrated.get('retrieved_at'):
        return dict(result, reason=hydrated.get('reason') or active.get('reason') or 'missing_hydrated_profile')
    member = (active.get('pitchers') or {}).get(str(player))
    profile = (hydrated.get('pitchers') or {}).get(str(player))
    if member is None or profile is None:
        return dict(result, reason='missing_dated_pitcher_profile')
    hand = profile.get('profile_pitch_hand')
    if hand not in ('R', 'L', 'S') or member.get('profile_pitch_hand') not in (None, hand):
        return dict(result, reason='missing_or_conflicting_official_pitch_hand')
    return dict(result, value=hand, observed_at=hydrated['retrieved_at'], reason=None)


def read_team_board(connection, team, *, revision=None):
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.history import METHODOLOGY
    if type(team) is not int or team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB team identity')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def board(cur):
        listing = _league(cur, revision, None)
        result = {key: listing[key] for key in ('scope','generation','selection_revision','current_serving_eligible',
                                                'data_through','availability_reference','status')}
        if not result['generation']:
            return result
        generation = result['generation']
        row, = (item for item in listing['teams'] if item['team_id'] == team)
        methods = {method: domain for domain, (subject, method, _) in DOMAINS.items() if subject == 'team'}
        methods[METHODOLOGY] = 'workload'
        blocks = _blocks(cur, generation, 'team', team, methods)
        players, status = _public_arms(cur, generation)
        arms = []
        for key, arm in sorted(blocks['readiness']['value']['arms'].items(), key=lambda item: int(item[0])):
            mlb = int(key)
            identity = players.get(mlb, {})
            arms.append(dict(mlb_id=mlb, public_pitcher_id=identity.get('public_id'),
                             name=identity.get('name'), pitch_hand=_pitch_hand(blocks['depth'], mlb),
                             read=arm['read'], reason=arm['reason']))
        from datetime import date
        result['recent_relief'] = appearance_ledger(cur, generation, 'team', team, date.fromisoformat(listing['data_through']))
        return dict(result, team=row, active_bullpen=arms, pitcher_identity_status=status, sections=blocks,
                    what_changed=_events(cur, team, listing['selection_revision']))
    return _read_transaction(connection, board)


def read_pitcher(connection, public_id, *, revision=None):
    """Read a public Pitcher.id under the same identity map and generation used by Search."""
    from sync_v3.history import METHODOLOGY
    if type(public_id) is not int or public_id < 1:
        raise ValueError('Expected a BaseballOS public pitcher identity')
    if revision is not None and (type(revision) is not int or revision < 1):
        raise ValueError('Historical selector revision must be a positive integer')

    def pitcher(cur):
        selected = _selected(cur, revision)
        result = dict(scope='isolated_historical_core', current_serving_eligible=False, public_pitcher_id=public_id,
                      selection_revision=selected[0] if selected else None, generation=None)
        if not selected or not selected[1]:
            return dict(result,status='no_selected_generation')
        sequence, digest, through, reference = selected
        result.update(generation=digest, data_through=through.isoformat(), availability_reference=reference)
        players, status = _pitcher_directory(cur, digest)
        player = next((p for p in players.values() if p['public_id'] == public_id), None)
        if player is None:
            return dict(result, status='outside_represented_bullpens' if status == 'mapped' else status)
        if player['team_id'] is None:
            return dict(result, status='historical_roster_departure', identity=player, sections={})
        methods = {method: domain for domain, (subject, method, _) in DOMAINS.items() if subject == 'pitcher'}
        methods[METHODOLOGY] = 'workload'
        blocks = _blocks(cur, digest, 'pitcher', player['mlb_id'], methods)
        depth = _blocks(cur, digest, 'team', player['team_id'], {DOMAINS['depth'][1]:'depth'})['depth']
        result['pitch_hand'] = _pitch_hand(depth, player['mlb_id'])
        changes = _events(cur, player['team_id'], sequence)
        events = [row for row in changes['events'] if row['event'].get('player') == player['mlb_id']]
        if player.get('historical_departure'):
            events.append(player['historical_departure'])
        return dict(result, status='represented', identity=player, sections=blocks, represented_events=events,
                    recent_work=appearance_ledger(cur, digest, 'pitcher', player['mlb_id'], through))
    return _read_transaction(connection, pitcher)


def _decision_page(connection, through_revision, limit, project):
    if type(through_revision) is not int or through_revision < 1 or type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError('History requires a positive revision and a limit from 1 to 30')

    def history(cur):
        cur.execute("""SELECT s.revision,s.generation,g.represented,g.manifest->>'availability_reference',
                              s.action,s.predecessor FROM candidate.core_selections s
                       LEFT JOIN candidate.generations g ON g.digest=s.generation
                       WHERE s.revision<=%s ORDER BY s.revision DESC LIMIT %s""", (through_revision, limit+1))
        page = cur.fetchall()
        if not page or page[0][0] != through_revision:
            return dict(status='unknown_revision', rows=[], next_revision=None, current_serving_eligible=False)
        rows = []
        for sequence, digest, day, reference, action, predecessor in page[:limit]:
            row = dict(selection_revision=sequence, predecessor=predecessor, action=action, generation=digest,
                       represented=day.isoformat() if day else None)
            row.update(project(cur, (sequence, digest, day, reference)))
            rows.append(row)
        return dict(status='historical_decisions', rows=rows, next_revision=page[limit][0] if len(page)>limit else None,
                    current_serving_eligible=False)
    return _read_transaction(connection, history)


def read_team_history(connection, team, *, through_revision, limit=14):
    """Page through actual isolated selection and recovery decisions, retaining gaps and supersessions."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    if type(team) is not int or team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB team identity')

    def team_changes(cur, selected):
        changes = _event_slice(cur, team, selected[0], selected)
        row = {key: changes[key] for key in ('events', 'comparisons', 'status')}
        row['calendar_context'] = read_calendar_context(cur, selected[1], team, selected[2]) if selected[1] else None
        return row
    return dict(_decision_page(connection, through_revision, limit, team_changes), team=team)


def read_pitcher_history(connection, public_id, *, through_revision, limit=14):
    """Reproduce the club assignment, published-candidate read and deployment evidence at each decision."""
    if type(public_id) is not int or public_id < 1:
        raise ValueError('Expected a BaseballOS public pitcher identity')

    def arm_history(cur, selected):
        sequence, digest, day, reference = selected
        if digest is None:
            return dict(status='no_selected_generation', events=[])
        players, status = _pitcher_directory(cur, digest)
        player = next((p for p in players.values() if p['public_id'] == public_id), None)
        if player is None:
            return dict(status='outside_represented_bullpens' if status == 'mapped' else status, events=[])
        if player['team_id'] is None:
            return dict(status='historical_roster_departure', identity=player, events=[player['historical_departure']])
        mlb, club = player['mlb_id'], player['team_id']
        readiness_method = DOMAINS['readiness'][1]
        role_method = DOMAINS['pitcher_profile'][1]
        cur.execute("""SELECT h.facts->'arms'->%s,h.semantic_digest,h.input_digest FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot WHERE g.generation=%s
                       AND h.subject='team' AND h.mlb_id=%s AND h.methodology=%s""", (str(mlb), digest, club, readiness_method))
        arm, facts, inputs = cur.fetchone()
        cur.execute("""SELECT h.facts#>'{deployment,facts,observed_role}',h.semantic_digest,h.input_digest
                       FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                       WHERE g.generation=%s AND h.subject='pitcher' AND h.mlb_id=%s AND h.methodology=%s""",
                    (digest, mlb, role_method))
        role, role_facts, role_inputs = cur.fetchone()
        changes = _event_slice(cur, club, sequence, selected)
        events = [row for row in changes['events'] if row['event'].get('player') == mlb]
        if player.get('historical_departure'):
            events.append(player['historical_departure'])
        return dict(status='represented', identity=player, availability_reference=reference, arm=arm, role=role,
                    events=events, citations={
                        readiness_method: dict(facts_digest=facts, input_digest=inputs),
                        role_method: dict(facts_digest=role_facts, input_digest=role_inputs)})
    return dict(_decision_page(connection, through_revision, limit, arm_history), public_pitcher_id=public_id)
