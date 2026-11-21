"""Dated game and rest evidence retained by a historical selection."""
from datetime import timedelta

from psycopg2.extras import Json

from sync_v3.discovery import calendar_requests
from sync_v3.evidence import replay
from sync_v3.intelligence_history import DOMAINS


def calendar_events(day, rotation, schedule):
    """Report a rest day once final games on both sides support the empty calendar."""
    dates = rotation['dates']
    key = day.isoformat()
    today = dates[key]
    if today['reason']:
        return [], today['reason']

    week = [dates[(day - timedelta(days=offset)).isoformat()] for offset in range(7)]
    finals = [game for daily in week for game in daily['games']]
    verified = [game for game in finals if not game['shape_reason'] and game['relief_outs'] is not None]
    gaps = any(daily['reason'] for daily in week)
    burden = dict(final_games=None if gaps else len(finals), verified_games=len(verified),
                  bullpen_outs=sum(game['relief_outs'] for game in verified)
                  if not gaps and len(verified) == len(finals) else None)
    events = []
    for game in today['games']:
        shape = game.get('rotation') or {}
        workload = None
        if not game['shape_reason'] and 'short_start' in shape:
            workload = dict(starter_outs=shape['starter_outs'], bullpen_outs=shape['bullpen_outs_required'],
                            short_start=shape['short_start'])
        events.append(dict(date=key, kind='game', game_pks=[game['game_pk']], workload=workload,
                           week=burden, extra_innings=None))

    prior, rest = [(day - timedelta(days=offset)).isoformat() for offset in (2, 1)]
    if any(d in schedule['gaps'] or d not in schedule['dates'] for d in (prior, rest, key)):
        return events, 'adjacent_calendar_unverified'
    if schedule['dates'][rest]['games'] or dates[rest]['reason'] or dates[rest]['games']:
        return events, None
    adjacent_games = []
    for d in (prior, key):
        pks = {g['game_pk'] for g in dates[d]['games']}
        listed = schedule['dates'][d]['games']
        if (dates[d]['reason'] or not pks or {g['game_pk'] for g in listed} != pks
                or any(g['status'] != 'final' or g['official_date'] != d for g in listed)):
            return events, 'adjacent_finals_unverified'
        adjacent_games.extend(sorted(pks))
    events.append(dict(date=rest, kind='off_day', game_pks=sorted(adjacent_games)))
    return events, None


def confirmed_extra_innings(schedule, lines, day):
    regulation = schedule.get('scheduledInnings')
    if (type(regulation) is not int or regulation < 1 or schedule.get('officialDate') != day.isoformat()
            or schedule.get('gameType') != 'R' or any(schedule.get(k) for k in
                ('resumeDate', 'resumeGameDate', 'resumedFrom', 'resumedFromDate'))):
        return None
    totals = {}
    for line in lines:
        if type(line['outs_recorded']) is not int or line['outs_recorded'] < 0:
            return None
        club = line['team_id']
        totals[club] = totals.get(club, 0) + line['outs_recorded']
    if set(totals) != {side['team']['id'] for side in schedule['teams'].values()} or len(totals) != 2:
        return None
    fewest, most = sorted(totals.values())
    # Before either club records an out in the next inning, both have completed the prior inning.
    completed_before_last_out = (most - 1) // 3 if most else 0
    if fewest < 3 * completed_before_last_out:
        return None
    beyond_regulation = most > 3 * regulation
    inning = (schedule.get('linescore') or {}).get('currentInning')
    if type(inning) is int and inning > 0:
        if fewest < 3 * (inning - 1) or most > 3 * inning:
            return None
        return inning > regulation
    return True if beyond_regulation else None


def read_calendar_context(cur, generation, team, day):
    cur.execute("""SELECT h.methodology,h.facts,h.semantic_digest,h.input_digest,h.id
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.mlb_id=%s AND h.subject='team' AND h.represented=%s
                     AND h.methodology=ANY(%s)""",
                (generation, team, day, [DOMAINS[k][1] for k in ('rotation', 'schedule')]))
    sources = {method: (facts, dict(facts_digest=facts_digest, input_digest=input_digest), snapshot)
               for method, facts, facts_digest, input_digest, snapshot in cur}
    rotation = sources[DOMAINS['rotation'][1]]
    schedule = sources[DOMAINS['schedule'][1]]
    events, reason = calendar_events(day, rotation[0], schedule[0])
    games = {e['game_pks'][0]: e for e in events if e['kind'] == 'game'}
    if games:
        cur.execute("""SELECT DISTINCT c.identity,r.id,r.facts,c.context_id
                       FROM candidate.workload_history_sources hs
                       JOIN candidate.confirmations c ON c.source_id=hs.source_id AND c.domain='final'
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE hs.snapshot=%s AND c.identity=ANY(%s)""", (rotation[2], [str(pk) for pk in games]))
        finals = cur.fetchall()
        request = calendar_requests(day)[0]
        cur.execute("""SELECT f.id FROM candidate.workload_history_sources hs
                       JOIN candidate.fetches f ON f.id=hs.source_id
                       WHERE hs.snapshot=%s AND f.endpoint=%s AND f.parameters=%s""",
                    (rotation[2], request.endpoint, Json(request.params())))
        dated_sources = {source for source, in cur}
        slates = {}
        for source in dated_sources | {row[3] for row in finals}:
            slate = replay(cur, source)
            slates[source] = {g['gamePk']: g for d in slate.body['dates'] if d['date'] == day.isoformat()
                              for g in d['games']}
        results = {}
        for identity, version, lines, context_id in finals:
            pk = int(identity)
            for source in dated_sources | {context_id}:
                game = slates[source].get(pk, {})
                value = confirmed_extra_innings(game, lines, day)
                results.setdefault(pk, set()).add((version, value))
        for pk, proofs in results.items():
            if len(proofs) == 1 and dated_sources:
                games[pk]['extra_innings'] = next(iter(proofs))[1]
    return dict(through=day.isoformat(), events=events, calendar_limitation=reason,
                citations={method: source[1] for method, source in sources.items()})
