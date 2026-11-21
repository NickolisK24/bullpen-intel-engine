"""Cross-check the active bullpen membership actually pinned by a candidate generation."""

from collections import defaultdict

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.intelligence_history import DOMAINS


def _club_membership(team, day, reads, receipts):
    domains = ('readiness', 'depth', 'group_performance')
    if any(name not in reads for name in domains):
        return 'missing_population_snapshot'
    readiness, depth, group = (reads[name] for name in domains)
    if (any(read['team'] != team for read in (readiness, depth, group))
            or (readiness['membership_date'], depth['represented'], group['through']) != (day, day, day)):
        return 'misaligned_population_snapshot'
    if readiness['team_state'] is None:
        return readiness['reason'] or 'missing_team_state'
    roster_receipts = [receipts.get(name, set()) for name in domains]
    if len(roster_receipts[0]) != 1 or any(r != roster_receipts[0] for r in roster_receipts[1:]):
        return 'dated_roster_receipts_differ_or_missing'
    active = depth['views']['active']
    if (active['pitchers'] is None or active['reason']
            or (depth.get('active_profiles') or {}).get('reason') == 'mlb_active_rosters_disagree'):
        return 'unverified_dated_active_population'
    if group['reason']:
        return group['reason']
    cohort = [int(m['player']) for m in group['members']]
    if (not cohort or len(set(cohort)) != len(cohort) or set(cohort) != set(map(int, readiness['arms']))
            or not set(cohort).issubset(map(int, active['pitchers']))):
        return 'active_bullpen_identity_conflict'
    return 'matched'


def compare_membership(cur, generation, day):
    names = {DOMAINS[domain][1]: domain for domain in ('depth', 'group_performance', 'readiness')}
    cur.execute("""SELECT h.mlb_id,h.methodology,h.facts FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.subject='team' AND h.methodology=ANY(%s)""",
                (generation, list(names)))
    reads = defaultdict(dict)
    for team, method, facts in cur:
        reads[team][names[method]] = facts
    cur.execute("""SELECT h.mlb_id,h.methodology,f.id FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   JOIN candidate.workload_history_sources s ON s.snapshot=h.id
                   JOIN candidate.fetches f ON f.id=s.source_id
                   JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='roster'
                   WHERE g.generation=%s AND h.subject='team' AND h.methodology=ANY(%s)
                   AND f.endpoint='/teams/' || h.mlb_id::text || '/roster'
                   AND f.parameters=jsonb_build_object('date',%s::text,'rosterType','active')""",
                (generation, list(names), day))
    receipts = defaultdict(lambda: defaultdict(set))
    for team, method, source in cur:
        receipts[team][names[method]].add(source)
    club_status, memberships = {}, defaultdict(list)
    for team in sorted(MLB_TEAM_IDS):
        club_status[team] = _club_membership(team, day, reads[team], receipts[team])
        view = reads[team].get('depth', {}).get('views', {}).get('active', {})
        if view.get('pitchers') and not view['reason']:
            for player in view['pitchers']:
                memberships[int(player)].append(team)
    shared = {player: clubs for player, clubs in memberships.items() if len(clubs) > 1}
    for clubs in shared.values():
        for team in clubs:
            club_status[team] = 'multiple_dated_club_memberships'
    return dict(clubs=club_status, multiple_clubs=shared)


def _official_relief(game, facts, body):
    from utils.innings import parse_mlb_innings_to_outs

    if facts['game_pk'] != game['game_pk'] or body.get('gamePk', game['game_pk']) != game['game_pk']:
        return 'conflicting_game_identity'
    expected = {}
    for side in ('home', 'away'):
        staff = body['teams'][side]
        team = staff['team']['id']
        if team != game[side]:
            return 'conflicting_game_sides'
        for player in staff['pitchers']:
            line = staff['players'][f'ID{player}']['stats']['pitching']
            if line.get('gamesStarted') == 0:
                innings = line.get('inningsPitched')
                if innings is None or not str(innings).strip():
                    return 'missing_official_outs'
                outs = parse_mlb_innings_to_outs(innings)
                count = line.get('gamesPitched')
                activity = (outs, line.get('battersFaced'), line.get('numberOfPitches'))
                if count != 1 and (count is not None or not any(type(n) is int and n > 0 for n in activity)):
                    return 'unverified_relief_appearance'
                key = (team, player)
                if key in expected:
                    return 'duplicate_official_pitcher'
                expected[key] = outs
            elif line.get('gamesStarted') != 1:
                return 'unverified_starter_identity'
    actual = {(arm['mlb_team_id'], arm['mlb_player_id']): arm['outs'] for arm in facts['relief_appearances']}
    if len(actual) != len(facts['relief_appearances']) or actual != expected:
        return 'official_relief_lines_disagree'
    return 'matched'


def compare_games(cur, generation, manifest):
    from sync_v3.evidence import replay

    results, open_games = {}, []
    for game in manifest['slate']['games'] or ():
        if not game['final']:
            if game['status'] not in ('postponed', 'cancelled'):
                open_games.append(game['game_pk'])
            continue
        pk = game['game_pk']
        cur.execute("""SELECT h.id,h.facts FROM candidate.generation_inputs g
                       JOIN candidate.workload_history h ON h.id=g.snapshot
                       WHERE g.generation=%s AND h.subject='game' AND h.mlb_id=%s AND h.methodology=%s""",
                    (generation, pk, DOMAINS['game_deployment'][1]))
        row = cur.fetchone()
        if not row:
            results[pk] = 'missing_game_snapshot'
            continue
        snapshot, facts = row
        if facts['baseball_date'] != manifest['represented'] or facts.get('game_type') != game['game_type']:
            results[pk] = 'misaligned_game_snapshot'
            continue
        if facts['reason'] or facts['relief_appearances'] is None:
            results[pk] = facts['reason'] or 'missing_game_evidence'
            continue
        cur.execute("""SELECT f.id FROM candidate.workload_history_sources s JOIN candidate.fetches f ON f.id=s.source_id
                       JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='final' AND c.identity=%s
                       WHERE s.snapshot=%s AND f.endpoint=%s AND f.outcome='received'""",
                    (str(pk), snapshot, f'/game/{pk}/boxscore'))
        receipts = cur.fetchall()
        results[pk] = (_official_relief(game, facts, replay(cur, receipts[0][0]).body)
                       if len(receipts) == 1 else 'missing_unique_official_final')
    return dict(slate_reason=manifest['slate']['reason'], finals=results, open_games=open_games)


def verify_change_lineage(cur, generation, through):
    from datetime import timedelta
    from sync_v3.change_history import COMPARISONS
    from sync_v3.history import METHODOLOGY

    parents_for = {f'candidate_{domain}_changes_v1': DOMAINS[domain][1] if domain in DOMAINS else METHODOLOGY
                   for domain in COMPARISONS}
    cur.execute("""SELECT e.id,p.subject,p.mlb_id,p.represented,p.methodology,p.revision,p.semantic_digest,p.input_digest
                   FROM candidate.generation_inputs g JOIN candidate.workload_history e ON e.id=g.snapshot
                   JOIN candidate.change_inputs i ON i.change_snapshot=e.id
                   JOIN candidate.workload_history p ON p.id=i.input_snapshot
                   WHERE g.generation=%s ORDER BY p.represented,p.id""", (generation,))
    parents = defaultdict(list)
    for child, subject, entity, day, method, revision, semantic, inputs in cur:
        parents[child].append((subject, entity, method, day, dict(
            represented=day.isoformat(), revision=revision, facts_digest=semantic, input_digest=inputs)))
    cur.execute("""SELECT e.id,e.subject,e.mlb_id,e.methodology,e.facts FROM candidate.generation_inputs g
                   JOIN candidate.workload_history e ON e.id=g.snapshot WHERE g.generation=%s
                   AND e.methodology=ANY(%s)""", (generation, list(parents_for)))
    sets, events, partial = 0, set(), 0
    allowed = {through - timedelta(days=1), through}
    for child, subject, entity, method, report in cur:
        inputs = parents[child]
        dates = [p[3] for p in inputs]
        if (any(p[:3] != (subject, entity, parents_for[method]) for p in inputs)
                or set(dates) - allowed or len(dates) != len(set(dates))
                or report['methodology'] != parents_for[method] or report.get(subject) != entity
                or report['through'] != through.isoformat() or report['lineage'] != [p[4] for p in inputs]
                or (len(inputs) < 2 and (report['events'] or report['status'] != 'missing_snapshot'))):
            raise ValueError('Historical change citations disagree with pinned snapshot parents')
        for event in report['events']:
            key = event['event_id']
            if not key or key in events:
                raise ValueError('Duplicate or missing historical change identity')
            events.add(key)
        sets += 1
        partial += report['status'] != 'complete'
    return dict(sets=sets, events=len(events), partial_or_withheld_sets=partial)
