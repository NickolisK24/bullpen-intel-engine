"""Candidate Board and History changes from an immutable pair of represented reads."""

from datetime import timedelta

from psycopg2.extras import Json

from services.pitcher_public_labels import READ_PUBLIC_LABELS
from sync_v3.history import METHODOLOGY as WORKLOAD_METHOD
from sync_v3.intelligence_history import DOMAINS


def _pair(cur, domain, identity, through, revisions):
    """Read exact consecutive dates. Pass the two revision numbers to reproduce an earlier view."""
    days = [through - timedelta(days=1), through]
    if revisions is not None and (len(revisions) != 2 or any(type(r) is not int or r < 1 for r in revisions)):
        raise ValueError('Expected two positive snapshot revisions')
    subject, methodology = ('team', WORKLOAD_METHOD) if domain == 'team_workload' else DOMAINS[domain][:2]
    earlier, later = revisions or (None, None)
    cur.execute("""SELECT DISTINCT ON (represented) represented,revision,semantic_digest,input_digest,facts
                   FROM candidate.workload_history WHERE subject=%s AND mlb_id=%s AND methodology=%s
                   AND ((represented=%s AND (%s IS NULL OR revision=%s))
                     OR (represented=%s AND (%s IS NULL OR revision=%s)))
                   ORDER BY represented, revision DESC""",
                (subject, identity, methodology, days[0], earlier, earlier, days[1], later, later))
    rows = cur.fetchall()
    lineage = [dict(represented=day.isoformat(), revision=revision, facts_digest=semantic, input_digest=inputs)
               for day, revision, semantic, inputs, _ in rows]
    events = []
    result = dict(through=through.isoformat(), methodology=methodology, mode='retrospective_candidate',
                  current_serving_eligible=False, lineage=lineage, events=events, status='missing_snapshot')
    result[subject] = identity
    return result, rows


def readiness_changes(cur, team, through, *, revisions=None):
    result, rows = _pair(cur, 'readiness', team, through, revisions)
    methodology, events = result['methodology'], result['events']
    if len(rows) != 2:
        return result
    for day, _, _, _, facts in rows:
        if (facts['team'] != team or facts['membership_date'] != day.isoformat()
                or facts['reference_date'] != (day + timedelta(days=1)).isoformat()
                or facts['comparison']['team_states_compared'] != 1 or not facts['team_state']):
            result['status'] = 'incomparable_readiness'
            return result

    def add(kind, before, after, player=None):
        if before != after:
            events.append(dict(event_id=f'{methodology}/{team}/{through}/{kind}/{player or team}',
                               kind=kind, player=player, previous=before, current=after))

    before, after = [row[-1] for row in rows]
    add('team_state_changed', before['team_state']['public_code'], after['team_state']['public_code'])
    reads = []
    for facts in (before, after):
        side = {}
        for player, arm in facts['arms'].items():
            key = arm['read']['arm_read']['key'] if arm['read'] else None
            side[int(player)] = key if key in READ_PUBLIC_LABELS and key != 'limited_read' else None
        reads.append(side)
    old, new = reads
    for player in sorted(old.keys() & new.keys()):
        if old[player] and new[player]:
            add('arm_read_changed', old[player], new[player], player)
    if not old or not new or None in old.values() or None in new.values():
        result['status'] = 'partial_arm_coverage'
    else:
        add('clean_option_count_changed', sum(key == 'clean_option' for key in old.values()),
            sum(key == 'clean_option' for key in new.values()))
        result['status'] = 'complete'
    return result


def roster_changes(cur, team, through, *, revisions=None):
    """Compare the two dated club lists retained by these exact depth revisions."""
    result, rows = _pair(cur, 'depth', team, through, revisions)
    if len(rows) != 2:
        return result
    sides = []
    for day, revision, _, _, facts in rows:
        active = facts['views']['active']
        hydrated = facts.get('active_profiles') or {}
        if (facts['represented'] != day.isoformat() or facts['team'] != team
                or active['reason'] or active['pitchers'] is None
                or hydrated.get('reason') == 'mlb_active_rosters_disagree'):
            result['status'] = 'incomparable_active_roster'
            return result
        cur.execute("""SELECT r.facts->'members' FROM candidate.workload_history h
                       JOIN candidate.workload_history_sources hs ON hs.snapshot=h.id
                       JOIN candidate.fetches f ON f.id=hs.source_id
                       JOIN candidate.confirmations c ON c.source_id=f.id
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE (h.subject,h.mlb_id,h.represented,h.methodology,h.revision)=('team',%s,%s,%s,%s)
                         AND f.endpoint=%s AND f.parameters=%s AND c.domain='roster' AND c.identity=%s""",
                    (team, day, result['methodology'], revision, f'/teams/{team}/roster',
                     Json({'date': day.isoformat(), 'rosterType': 'active'}), f'{team}/active/{day}'))
        matches = cur.fetchall()
        if len(matches) != 1 or not matches[0][0]:
            result['status'] = 'missing_complete_club_list'
            return result
        members = {row['id']: row for row in matches[0][0]}
        pitchers = {int(player) for player in active['pitchers']}
        if not pitchers.issubset(members):
            result['status'] = 'incomparable_active_roster'
            return result
        sides.append((members, pitchers))
    for idx, kind in enumerate(('active_roster_removed', 'active_roster_added')):
        members, pitchers = sides[idx]
        others, _ = sides[1 - idx]
        for player in sorted(pitchers - others.keys()):
            result['events'].append(dict(
                event_id=f"{result['methodology']}/{team}/{through}/{kind}/{player}",
                kind=kind, player=player, pitcher_name=members[player]['name'],
                previous=idx == 0, current=idx == 1))
    result['status'] = 'complete'
    return result


def game_changes(cur, team, through, *, revisions=None):
    """Read final-game appearances and qualified short starts on the represented day."""
    result, rows = _pair(cur, 'rotation', team, through, revisions)
    if len(rows) != 2:
        return result
    before, after = [row[-1] for row in rows]
    current = after['dates'][through.isoformat()]
    if current['reason']:
        result['status'] = current['reason']
        return result
    known_games = {game['game_pk'] for daily in before['dates'].values() for game in daily['games']}
    result['status'] = 'complete'
    for game in current['games']:
        pk = game['game_pk']
        if pk in known_games:
            result['status'] = 'game_already_represented'
            continue
        events = [('relief_appearance', player, {}) for player in game['relief_pitchers']]
        shape = game['rotation']
        if game['shape_reason'] or not shape:
            result['status'] = 'partial_rotation_evidence'
        elif shape.get('short_start') is True:
            events.append(('new_short_start', game['credited_starter'], {
                'starter_outs': shape['starter_outs'], 'bullpen_outs': shape['bullpen_outs_required']}))
        for kind, player, facts in events:
            result['events'].append(dict(event_id=f"{result['methodology']}/{team}/{through}/{kind}/{pk}/{player}",
                                         kind=kind, game=pk, player=player, facts=facts))
    return result


def pattern_changes(cur, player, through, *, revisions=None):
    """Compare qualified pitcher facts across consecutive represented baseball dates."""
    from services.team_board_what_changed import PATTERNS

    result, rows = _pair(cur, 'pitcher_rest', player, through, revisions)
    if len(rows) != 2:
        return result
    sides = []
    for day, _, _, _, snapshot in rows:
        rest = snapshot['rest']
        if (rest['mlb_player_id'] != player or rest['through'] != day.isoformat()
                or rest['reference'] != (day + timedelta(days=1)).isoformat() or not rest['facts']):
            result['status'] = 'incomparable_pitcher_rest'
            return result
        sides.append(rest['facts'])
    result['status'] = 'complete'
    for pattern, _ in PATTERNS:
        a, b = (facts[pattern] for facts in sides)
        if any(fact['status'] != 'complete' or type(fact['value']) is not bool for fact in (a, b)):
            result['status'] = 'partial_rest_coverage'
        elif a['value'] != b['value']:
            kind = f"{pattern}_{'started' if b['value'] else 'ended'}"
            result['events'].append(dict(event_id=f"{result['methodology']}/{player}/{through}/{kind}",
                                         kind=kind, player=player, previous=a['value'], current=b['value']))
    return result


def deployment_changes(cur, team, through, *, revisions=None):
    """Use the existing Board comparator for qualified changes in observed deployment."""
    from services.role_movement import CONTRACT
    from services.team_board_what_changed import _movement_read

    result, rows = _pair(cur, 'roles', team, through, revisions)
    if len(rows) != 2:
        return result
    sides = []
    for day, _, _, _, facts in rows:
        if (not facts['complete_game_coverage'] or facts['contract'] != CONTRACT
                or facts['mlb_team_id'] != team or facts['through'] != day.isoformat()):
            result['status'] = 'incomparable_deployment'
            return result
        sides.append({p['mlb_player_id']: _movement_read(dict(p, recent_window=p['recent'], prior_window=p['prior']), day)
                      for p in facts['profiles']})
    before, after = sides
    result['status'] = 'complete' if before and before.keys() == after.keys() else 'partial_deployment_coverage'
    for player in sorted(before.keys() & after.keys()):
        a, b = before[player], after[player]
        if (not a or not b or a['season_phase'] != b['season_phase']
                or [s['status'] for s in a['signals']] != [s['status'] for s in b['signals']]):
            result['status'] = 'partial_deployment_coverage'
        elif a['movement'] != b['movement']:
            kind = 'observed_deployment_changed'
            result['events'].append(dict(event_id=f"{result['methodology']}/{team}/{through}/{kind}/{player}",
                                         kind=kind, player=player, previous=a['movement'], current=b['movement']))
    return result


def burden_changes(cur, team, through, *, revisions=None):
    """Use independently recounted team totals on like-for-like rolling windows."""
    result, rows = _pair(cur, 'team_workload', team, through, revisions)
    if len(rows) != 2:
        return result
    result['status'] = 'complete'
    for days in (7, 14):
        key = f'window_{days}'
        sides = []
        for day, _, _, _, facts in rows:
            report = facts['windows']
            window = report['workload']['windows'][key]
            if (key not in report['compared_windows'] or window['through'] != day.isoformat()
                    or window['start'] != (day - timedelta(days=days - 1)).isoformat()):
                break
            sides.append({metric: window[metric]['value'] for metric in ('appearances', 'outs', 'pitches')
                          if window[metric]['status'] == 'complete' and type(window[metric]['value']) is int})
        if len(sides) != 2:
            result['status'] = 'partial_burden_coverage'
            continue
        before, after = sides
        common = sorted(before.keys() & after.keys())
        if len(common) != 3:
            result['status'] = 'partial_burden_coverage'
        if any(before[k] != after[k] for k in common):
            kind = f'workload_{days}_day_changed'
            result['events'].append(dict(event_id=f"{result['methodology']}/{team}/{through}/{kind}",
                                         kind=kind, previous={k: before[k] for k in common},
                                         current={k: after[k] for k in common}))
    return result


COMPARISONS = {'readiness': readiness_changes, 'depth': roster_changes, 'rotation': game_changes,
               'roles': deployment_changes, 'pitcher_rest': pattern_changes, 'team': burden_changes}


def record_changes(connection, domain, identity, through):
    """Freeze a shared candidate event set with links to its exact immutable inputs."""
    from sync_v3.history import _transaction
    return _transaction(connection, _freeze_changes, domain, identity, through)


def _freeze_changes(cur, domain, identity, through):
    from datetime import date
    from sync_v3.history import _store

    subject = 'pitcher' if domain == 'pitcher_rest' else 'team'
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', (subject, identity))
    report = COMPARISONS[domain](cur, identity, through)
    parents = []
    for source in report['lineage']:
        cur.execute("""SELECT id FROM candidate.workload_history
                       WHERE (subject,mlb_id,represented,methodology,revision)=(%s,%s,%s,%s,%s)""",
                    (subject, identity, date.fromisoformat(source['represented']),
                     report['methodology'], source['revision']))
        parents.append(cur.fetchone()[0])
    cur.execute('SELECT DISTINCT source_id FROM candidate.workload_history_sources WHERE snapshot=ANY(%s)', (parents,))
    receipts = [source for source, in cur]
    cur.execute('SELECT DISTINCT endpoint,parameters FROM candidate.history_requests WHERE snapshot=ANY(%s)', (parents,))
    requests = {(endpoint, tuple(sorted(params.items()))) for endpoint, params in cur}
    snapshot = _store(cur, subject, identity, through, f'candidate_{domain}_changes_v1', report, receipts, requests)
    cur.execute('SELECT creation_xid=pg_current_xact_id() FROM candidate.workload_history WHERE id=%s', (snapshot[0],))
    if not cur.fetchone()[0]:
        return snapshot
    cur.executemany("""INSERT INTO candidate.change_inputs VALUES (%s,%s)
                       ON CONFLICT DO NOTHING""", [(snapshot[0], parent) for parent in parents])
    return snapshot


def refresh_existing_changes(cur, snapshots):
    """An input date can affect existing comparisons ending on that day or the next."""
    cur.execute("""SELECT DISTINCT subject,methodology,mlb_id,represented
                   FROM candidate.workload_history WHERE id=ANY(%s)""", (snapshots,))
    methods = {DOMAINS[d][1]: d for d in COMPARISONS if d in DOMAINS}
    scopes = set()
    for subject, method, identity, day in cur.fetchall():
        domain = 'team' if method == WORKLOAD_METHOD and subject == 'team' else methods.get(method)
        if domain:
            cur.execute("""SELECT DISTINCT represented FROM candidate.workload_history
                           WHERE subject=%s AND methodology=%s AND mlb_id=%s AND represented BETWEEN %s AND %s""",
                        (subject, f'candidate_{domain}_changes_v1', identity, day, day + timedelta(days=1)))
            scopes.update((domain, identity, represented) for represented, in cur)
    for scope in sorted(scopes):
        _freeze_changes(cur, *scope)
