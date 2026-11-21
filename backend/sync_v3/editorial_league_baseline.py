"""League concentration comparison from the rotation snapshots of one frozen edition."""
from datetime import timedelta

from services.bullpen_concentration_context import (
    BULLPEN_CONCENTRATION_WINDOW_DAYS, build_league_bullpen_concentration_baseline,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.intelligence_history import DOMAINS


def league_concentration(cur, generation, through):
    method = DOMAINS['rotation'][1]
    days = [(through - timedelta(days=n)).isoformat() for n in range(BULLPEN_CONCENTRATION_WINDOW_DAYS)]
    cur.execute("""SELECT h.id,h.mlb_id,h.facts->'dates',h.semantic_digest,h.input_digest
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.methodology=%s AND h.subject='team' AND h.represented=%s
                   ORDER BY h.mlb_id""", (generation, method, through))
    clubs = cur.fetchall()
    citation = dict(methodology=method, start=days[-1], through=days[0],
                    clubs={team: dict(facts_digest=semantic, input_digest=inputs)
                           for _, team, _, semantic, inputs in clubs})
    if [row[1] for row in clubs] != sorted(MLB_TEAM_IDS):
        return None, 'incomplete_league_clubs', citation

    pairs = []
    expected = {}
    for snapshot, team, dates, _, _ in clubs:
        for day in days:
            if day not in dates or dates[day]['reason']:
                return None, 'incomplete_league_calendar', citation
            for game in dates[day]['games']:
                pk = game['game_pk']
                sides = expected.setdefault(pk, {})
                if team in sides:
                    return None, 'conflicting_league_game', citation
                sides[team] = day
                pairs.append((snapshot, str(pk)))

    if any(len(sides) != 2 or len(set(sides.values())) != 1 for sides in expected.values()):
        return None, 'conflicting_league_game', citation
    cur.execute("""WITH required AS (
                       SELECT * FROM unnest(%s::bigint[],%s::text[]) AS p(snapshot,game)
                   ), pinned AS (
                       SELECT p.game,p.snapshot,c.revision_id
                       FROM required p JOIN candidate.workload_history_sources hs ON hs.snapshot=p.snapshot
                       JOIN candidate.confirmations c ON c.source_id=hs.source_id AND c.domain='final' AND c.identity=p.game
                   ), games AS (
                       SELECT game,min(revision_id) AS revision FROM pinned GROUP BY game
                       HAVING count(DISTINCT snapshot)=2 AND count(DISTINCT revision_id)=1
                   )
                   SELECT g.game,r.facts FROM games g JOIN candidate.revisions r ON r.id=g.revision
                   ORDER BY g.game""", ([snapshot for snapshot, _ in pairs], [pk for _, pk in pairs]))
    finals = cur.fetchall()
    if len(finals) != len(expected):
        return None, 'missing_or_conflicting_league_final', citation
    logs = []
    for identity, lines in finals:
        pk = int(identity)
        sides = expected[pk]
        if {line['team_id'] for line in lines} != sides.keys():
            return None, 'conflicting_league_game', citation
        for line in lines:
            if line['game_pk'] != pk or line['game_date'] != sides[line['team_id']]:
                return None, 'conflicting_league_game', citation
            pitches = line['pitches_thrown']
            if line['games_started'] == 0 and (type(pitches) is not int or pitches < 0):
                return None, 'incomplete_league_pitch_counts', citation
            logs.append(dict(line, player_id=line['pitcher_mlb_id'], mlb_game_pk=pk,
                             innings_pitched_outs=line['outs_recorded'], game_type='R'))
    baseline = build_league_bullpen_concentration_baseline(logs, reference_date=through)
    if not baseline['league_team_count_10d']:
        return None, 'no_qualifying_league_workload', citation
    return baseline, 'complete_league_calendar', citation
