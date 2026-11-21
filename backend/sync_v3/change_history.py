"""Candidate Board and History changes from an immutable pair of represented reads."""

from datetime import timedelta

from services.pitcher_public_labels import READ_PUBLIC_LABELS
from sync_v3.intelligence_history import DOMAINS


def readiness_changes(cur, team, through, *, revisions=None):
    """Read exact consecutive dates. Pass the two revision numbers to reproduce an earlier view."""
    days = [through - timedelta(days=1), through]
    if revisions is not None and (len(revisions) != 2 or any(type(r) is not int or r < 1 for r in revisions)):
        raise ValueError('Expected two positive snapshot revisions')
    methodology = DOMAINS['readiness'][1]
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
