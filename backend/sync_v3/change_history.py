"""Candidate Board and History changes from an immutable pair of represented reads."""

from datetime import timedelta

from psycopg2.extras import Json

from services.pitcher_public_labels import READ_PUBLIC_LABELS
from sync_v3.intelligence_history import DOMAINS


def _pair(cur, domain, team, through, revisions):
    """Read exact consecutive dates. Pass the two revision numbers to reproduce an earlier view."""
    days = [through - timedelta(days=1), through]
    if revisions is not None and (len(revisions) != 2 or any(type(r) is not int or r < 1 for r in revisions)):
        raise ValueError('Expected two positive snapshot revisions')
    methodology = DOMAINS[domain][1]
    earlier, later = revisions or (None, None)
    cur.execute("""SELECT DISTINCT ON (represented) represented,revision,semantic_digest,input_digest,facts
                   FROM candidate.workload_history WHERE subject='team' AND mlb_id=%s AND methodology=%s
                   AND ((represented=%s AND (%s IS NULL OR revision=%s))
                     OR (represented=%s AND (%s IS NULL OR revision=%s)))
                   ORDER BY represented, revision DESC""",
                (team, methodology, days[0], earlier, earlier, days[1], later, later))
    rows = cur.fetchall()
    lineage = [dict(represented=day.isoformat(), revision=revision, facts_digest=semantic, input_digest=inputs)
               for day, revision, semantic, inputs, _ in rows]
    events = []
    result = dict(team=team, through=through.isoformat(), methodology=methodology, mode='retrospective_candidate',
                  current_serving_eligible=False, lineage=lineage, events=events, status='missing_snapshot')
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
