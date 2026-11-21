"""Append accepted facts and their exact source lineage in the candidate database."""

from datetime import date

from psycopg2.extras import Json

from services.game_finality import classify_game_finality
from services.game_appearance_extraction import extract_game_appearances
from services.mlb_club_directory import MLB_TEAM_IDS
from services.sync import _extract_pitching_lines_from_boxscore, _pitcher_order_by_side
from sync_v3.discovery import calendar_requests
from sync_v3.pitching_credit import uncredited_pitching_line
from utils.innings import parse_mlb_innings_to_outs


# Official Stats API /api/v1/gameTypes and the MLB All-Star team directory.
MLB_GAME_TYPES = frozenset({'S', 'R', 'F', 'D', 'L', 'W', 'C', 'P', 'A', 'I', 'E'})
ALL_STAR_TEAMS = frozenset({159, 160})


class Refused(ValueError):
    pass


def accept(cur, domain, identity, facts, source_id, observed_at, *, context_id=None):
    """Serialize a single subject, including its first version and unchanged receipts."""
    identity = str(identity)
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))', (domain, identity))
    cur.execute("""SELECT r.id,r.revision,r.facts,c.observed_at FROM candidate.confirmations c
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   WHERE c.domain=%s AND c.identity=%s
                   ORDER BY c.observed_at DESC,c.source_id DESC LIMIT 1""", (domain, identity))
    current = cur.fetchone()
    if current:
        if observed_at < current[3]:
            # An out-of-order copy of the sole, identical daily listing is still
            # the actual finality evidence its subsequently fetched boxscore saw.
            # Never bridge a changed listing or mutate a canonical revision here.
            if domain != 'schedule' or current[1] != 1 or current[2] != facts:
                return None
        if observed_at == current[3] and current[2] != facts:
            raise Refused('Contradictory evidence at the same source instant')
    if current and current[2] == facts:
        version = current[0]
    else:
        cur.execute("""INSERT INTO candidate.revisions(domain,identity,revision,predecessor,source_id,
                       observed_at,facts,context_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (domain, identity, current[1]+1 if current else 1, current[0] if current else None,
                     source_id, observed_at, Json(facts), context_id))
        version = cur.fetchone()[0]
    cur.execute("""INSERT INTO candidate.confirmations(domain,identity,source_id,revision_id,observed_at,context_id)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (domain, identity, source_id, version, observed_at, context_id))
    return version


def game_identity(game):
    sides = [game.get('teams', {}).get(side, {}).get('team', {}).get('id') for side in ('home','away')]
    kind = game.get('gameType')
    if not isinstance(kind, str) or kind not in MLB_GAME_TYPES:
        raise Refused('Unrecognized official game type')
    if any(type(team) is not int for team in sides) or sides[0] == sides[1]:
        raise Refused('Missing or contradictory official game sides')
    is_all_star_matchup = kind == 'A' and set(sides) == ALL_STAR_TEAMS
    if not is_all_star_matchup and any(team not in MLB_TEAM_IDS for team in sides):
        raise Refused('Missing or contradictory official game sides')
    if type(game.get('gamePk')) is not int or game['gamePk'] <= 0:
        raise Refused('Missing official game identity')
    try:
        date.fromisoformat(game.get('officialDate', ''))
    except (ValueError, TypeError) as exc:
        raise Refused('Missing official baseball date') from exc
    return {'gamePk': game['gamePk'], 'officialDate': game['officialDate'],
            'gameType': game['gameType'], 'teams': {side: {'team': {'id': team}} for side, team
                in zip(('home','away'),sides)}, 'status': game['status'],
            'gameNumber': game.get('gameNumber'), 'doubleHeader': game.get('doubleHeader'),
            'gameDate': game.get('gameDate'), 'resumeDate': game.get('resumeDate'),
            'resumeGameDate': game.get('resumeGameDate'), 'resumedFrom': game.get('resumedFrom'),
            'resumedFromDate': game.get('resumedFromDate'),
            'scores': {side: game['teams'][side].get('score') for side in ('home', 'away')}}


def reconcile_final(cur, pk, body, source_id, observed_at, day):
    # Makeup listings share one game identity across different calendar dates.
    # Only the requesting date's slate observed by boxscore acquisition can
    # establish its finality. A later removal/refusal cannot fall back to an old row.
    cur.execute("""WITH slate AS (
                       SELECT id,outcome FROM candidate.fetches WHERE endpoint='/schedule' AND parameters=%s
                       AND received_at<=%s ORDER BY received_at DESC,id DESC LIMIT 1
                   ) SELECT r.facts,c.source_id FROM slate s JOIN candidate.confirmations c ON c.source_id=s.id
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   WHERE s.outcome='received' AND c.domain='schedule' AND c.identity IN (%s,%s)""",
                (Json(calendar_requests(day)[0].params()), observed_at, f'{pk}/{day}', str(pk)))
    row = cur.fetchone()
    if not row or not classify_game_finality(row[0], boxscore=body).is_final_and_usable:
        raise Refused('Official final schedule and usable boxscore required')
    game, schedule_source = row
    if body.get('gamePk', pk) != pk:
        raise Refused('Boxscore game identity conflict')
    order = _pitcher_order_by_side(body)
    for side in ('home','away'):
        if body['teams'][side]['team']['id'] != game['teams'][side]['team']['id']:
            raise Refused('Boxscore side differs from official schedule')
    pitching_lines = _extract_pitching_lines_from_boxscore(body)
    for line in pitching_lines:
        innings = line['stats'].get('inningsPitched')
        if innings is None or not str(innings).strip():
            raise Refused('Official innings pitched missing for pitcher')
    appearances = extract_game_appearances(game=game, pitching_lines=pitching_lines,
                                          pitcher_order=order, game_date=game['officialDate'])
    for side in ('home','away'):
        lines = [a for a in appearances if a['side'] == side]
        if {a['pitcher_mlb_id'] for a in lines} != set(order[side]) or sum(a['is_starter'] for a in lines) != 1:
            raise Refused('Incomplete or contradictory pitching lineup')
        total = body['teams'][side].get('teamStats', {}).get('pitching', {}).get('inningsPitched')
        if total is None or not str(total).strip():
            raise Refused('Official innings pitched missing for team')
        if parse_mlb_innings_to_outs(total) != sum(a['outs_recorded'] for a in lines):
            raise Refused('Official team pitching outs do not reconcile')
    uncredited = {int(line['person_id'] or line['player_id']) for line in pitching_lines
                  if uncredited_pitching_line(line['stats'])}
    appearances = [line for line in appearances if line['pitcher_mlb_id'] not in uncredited]
    version = accept(cur, 'final', pk, appearances, source_id, observed_at, context_id=schedule_source)
    if version is None:
        return None
    cur.execute('''SELECT r.source_id,p.facts FROM candidate.revisions r
                   LEFT JOIN candidate.revisions p ON p.id=r.predecessor WHERE r.id=%s''', (version,))
    originating_source, prior = cur.fetchone()
    if originating_source != source_id:
        return version
    impacts = final_impacts(prior or (), appearances)
    cur.executemany('''INSERT INTO candidate.impacts VALUES (%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING''', [(version,*scope) for scope in sorted(impacts)])
    return version


def final_impacts(prior, appearances):
    # A reliever's corrected line can change the credited starter's opener classification.
    from sync_v3.workload import workload_lines

    before = {line['pitcher_mlb_id']:line for line in prior or ()}
    after = {line['pitcher_mlb_id']:line for line in appearances}
    impacts = set()
    before_class, after_class = [
        {line['pitcher_mlb_id']: line['workload_class'] for line in workload_lines(lines)}
        for lines in (prior, appearances)
    ]
    for player in before.keys() | after.keys():
        if before.get(player) == after.get(player) and before_class.get(player) == after_class.get(player):
            continue
        for line in (before.get(player), after.get(player)):
            if line:
                impacts.add(('pitcher',player,line['game_date']))
                if line['team_id'] in MLB_TEAM_IDS:
                    impacts.add(('team',line['team_id'],line['game_date']))
    return impacts


def observe(cur, source_id, capture, day):
    req, body, at = capture.request, capture.body, capture.retrieved_at
    if req.endpoint == '/schedule':
        for entry in body['dates']:
            for item in entry['games']:
                facts = game_identity(item)
                accept(cur, 'schedule', f"{facts['gamePk']}/{entry['date']}", facts, source_id, at)
    elif req.endpoint.endswith('/boxscore'):
        reconcile_final(cur, int(req.endpoint.split('/')[2]), body, source_id, at, day)


def recently_reconciled(cur, schedule_source, observed_at):
    """Audit a final again after a day or after a material schedule revision."""
    cur.execute("""SELECT DISTINCT split_part(s.identity,'/',1) FROM candidate.confirmations s
                   JOIN LATERAL (SELECT context_id,observed_at FROM candidate.confirmations f
                       WHERE f.domain='final' AND f.identity=split_part(s.identity,'/',1)
                       ORDER BY f.observed_at DESC,f.source_id DESC LIMIT 1) f ON TRUE
                   JOIN candidate.confirmations old ON old.source_id=f.context_id
                       AND old.domain='schedule' AND old.identity=s.identity
                   WHERE s.domain='schedule' AND s.source_id=%s AND s.revision_id=old.revision_id
                       AND f.observed_at > %s::timestamptz - interval '1 day'""",
                (schedule_source, observed_at))
    return {int(row[0]) for row in cur}
