"""Historical Pitcher charts from the pitcher profile and club role snapshot in one generation."""

from datetime import date, timedelta

from services import role_movement
from services.sync import _extract_leverage_index
from services.team_board_public_deployment_context import WINDOW_DAYS, _recorded_li, deployment_context_fields
from services.team_board_what_changed import _movement_read
from sync_v3.deployment import qualified_entries
from sync_v3.evidence import replay
from sync_v3.intelligence_history import DOMAINS


def _entry_and_leverage(cur, snapshot, outing, player):
    """Use only final and play receipts consulted when the pitcher's profile was frozen."""
    if outing['reason']:
        return None, None, None
    pk = outing['game_pk']
    team = player['team_id']
    day = date.fromisoformat(outing['date'])
    cur.execute("""SELECT f.id, r.facts, c.context_id FROM candidate.workload_history_sources hs
                   JOIN candidate.fetches f ON f.id=hs.source_id
                   JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='final' AND c.identity=%s
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   JOIN candidate.confirmations sc ON sc.source_id=c.context_id AND sc.domain='schedule' AND sc.identity=%s
                   WHERE hs.snapshot=%s AND f.endpoint=%s""",
                (str(pk), f'{pk}/{day}', snapshot, f'/game/{pk}/boxscore'))
    rows = cur.fetchall()
    if len(rows) != 1:
        return None, None, None
    source, lines, schedule_source = rows[0]
    cur.execute("""SELECT f.id FROM candidate.workload_history_sources hs JOIN candidate.fetches f ON f.id=hs.source_id
                   WHERE hs.snapshot=%s AND f.endpoint='/schedule' AND f.parameters->>'startDate'=%s
                     AND f.parameters->>'endDate'=%s""", (snapshot, str(day), str(day)))
    if cur.fetchall() != [(schedule_source,)]:
        return None, None, None
    schedule = replay(cur, schedule_source)
    games = [g for slate in schedule.body['dates'] for g in slate['games'] if g['gamePk'] == pk]
    if len(games) != 1:
        return None, None, None
    game = games[0]
    arm = [line for line in lines if line['pitcher_mlb_id'] == player['mlb_id']]
    if (game['gameType'] != 'R' or game['officialDate'] != outing['date'] or len(arm) != 1
            or arm[0]['team_id'] != team or arm[0]['games_started'] != 0):
        return None, None, None
    box = replay(cur, source)
    stats = box.body['teams'][arm[0]['side']]['players'][f"ID{player['mlb_id']}"]['stats']['pitching']
    leverage = _recorded_li(_extract_leverage_index(stats))
    cur.execute("""SELECT f.id FROM candidate.workload_history_sources hs JOIN candidate.fetches f ON f.id=hs.source_id
                   LEFT JOIN candidate.refusals r ON r.source_id=f.id
                   WHERE hs.snapshot=%s AND f.endpoint=%s AND f.outcome='received' AND r.source_id IS NULL
                     AND f.received_at >= %s""", (snapshot, f'/game/{pk}/playByPlay', box.retrieved_at))
    plays = cur.fetchall()
    if len(plays) != 1:
        return None, None, leverage
    entries, _ = qualified_entries(game, day, lines, replay(cur, plays[0][0]).body['allPlays'])
    inning, margin = (entries or {}).get((team, player['mlb_id']), (None, None))
    return inning, margin, leverage


def historical_pitcher_deployment(cur, digest, player, through):
    pitcher_method = DOMAINS['pitcher_profile'][1]
    role_method = DOMAINS['roles'][1]
    cur.execute("""SELECT h.methodology,h.id,CASE WHEN h.subject='team' THEN h.facts - 'games_by_date'
                     ELSE jsonb_build_object('through',h.facts->'pitch_history'->'through',
                            'player',h.facts->'pitch_history'->'mlb_player_id',
                            'reason',h.facts->'performance'->'reason','games',h.facts->'performance'->'games')
                     END FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.represented=%s AND
                    ((h.subject='pitcher' AND h.mlb_id=%s AND h.methodology=%s) OR
                     (h.subject='team' AND h.mlb_id=%s AND h.methodology=%s))""",
                (digest, through, player['mlb_id'], pitcher_method, player['team_id'], role_method))
    snapshots = {method: (sid, facts) for method, sid, facts in cur}
    context = movement = None
    if pitcher_method in snapshots:
        snapshot, facts = snapshots[pitcher_method]
        if facts['through'] == through.isoformat() and facts['player'] == player['mlb_id'] and facts['reason'] is None:
            start = (through - timedelta(days=WINDOW_DAYS - 1)).isoformat()
            outings = [row for row in facts['games'] if row['team_id'] == player['team_id']
                       and start <= row['date'] <= through.isoformat()]
            values = [_entry_and_leverage(cur, snapshot, row, player) for row in outings]
            innings = [inning for inning, _, _ in values if inning is not None]
            margins = [margin for _, margin, _ in values if margin is not None]
            leverage = [li for _, _, li in values if li is not None]
            context = deployment_context_fields(player['public_id'], len(outings), innings, margins, leverage)
    if role_method in snapshots:
        _, roles = snapshots[role_method]
        if (roles['mlb_team_id'] == player['team_id'] and roles['through'] == through.isoformat()
                and roles['contract'] == role_movement.CONTRACT and roles['complete_game_coverage']):
            profiles = [p for p in roles['profiles'] if p['mlb_player_id'] == player['mlb_id']]
            if len(profiles) == 1:
                p = profiles[0]
                windows = dict(recent_window=p['recent'], prior_window=p['prior'])
                verified = _movement_read(dict(p, **windows), through)
                if verified:
                    movement = dict(verified, **windows, pitcher_id=player['public_id'])
    if context is None and movement is None:
        return None
    return dict(through=through.isoformat(), window_days=WINDOW_DAYS, context=context, movement=movement,
                generation=digest, current_serving_eligible=False)
