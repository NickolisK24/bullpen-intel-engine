"""Calculate relief workload only inside an explicitly covered baseball-date window."""

from datetime import timedelta

from psycopg2.extras import Json

from services.game_finality import classify_status
from services.public_team_relief_work import (
    RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
    RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
)
from services.workload_appearance import is_workload_appearance_log
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import replay


WINDOWS = (3, 5, 7, 14, 30)


def regular_day(cur, day):
    """Return complete league relief inputs, or the first missing authority."""
    cur.execute("""SELECT f.id,f.outcome,b.source_id FROM candidate.fetches f
                   LEFT JOIN candidate.refusals b ON b.source_id=f.id
                   WHERE f.endpoint='/schedule' AND f.parameters=%s
                   ORDER BY f.received_at DESC,f.id DESC LIMIT 1""",
                (Json(calendar_requests(day)[0].params()),))
    row = cur.fetchone()
    if row is None or row[1] != 'received' or row[2] is not None:
        return None, 'missing_complete_schedule'
    result = replay(cur, row[0])
    lines, sources = [], [row[0]]
    for entry in result.body['dates']:
        for game in entry['games']:
            if game['gameType'] != 'R':
                continue
            status = classify_status(game['status'])
            if status.state in ('postponed','cancelled'):
                continue
            if not status.final_status or game['officialDate'] != day.isoformat():
                return None, 'regular_game_unresolved'
            pk = game['gamePk']
            cur.execute("""SELECT r.facts,f.id,c.context_id,f.outcome,old.revision_id,s.revision_id
                           FROM candidate.fetches f
                           LEFT JOIN candidate.confirmations c ON c.source_id=f.id
                               AND c.domain='final' AND c.identity=%s
                           LEFT JOIN candidate.revisions r ON r.id=c.revision_id
                           LEFT JOIN candidate.confirmations old ON old.source_id=c.context_id
                               AND old.domain='schedule' AND old.identity=c.identity
                           LEFT JOIN candidate.confirmations s ON s.source_id=%s AND
                               s.domain='schedule' AND s.identity=c.identity
                           WHERE f.endpoint=%s ORDER BY f.received_at DESC,f.id DESC LIMIT 1""",
                        (str(pk),row[0],f'/game/{pk}/boxscore'))
            final = cur.fetchone()
            if not final or final[0] is None or final[3] != 'received' or final[4] != final[5]:
                return None, 'missing_compatible_final'
            sources.extend((final[1], final[2]))
            lines.extend(line for line in final[0] if line['is_reliever'] and
                         is_workload_appearance_log(dict(line,innings_pitched_outs=line['outs_recorded'])))
    return {'lines':lines,'sources':sorted(set(sources))}, None


def load_calendar(cur, through):
    return {through-timedelta(days=i):regular_day(cur, through-timedelta(days=i))
            for i in range(max(WINDOWS))}


def pitcher_windows(cur, player, through):
    return windows_from_calendar(load_calendar(cur, through), player, through)


def windows_from_calendar(slices, player, through):
    """All arms can reuse the same qualified calendar without another database read."""
    days = [through-timedelta(days=i) for i in range(max(WINDOWS))]
    selected_by_day = {
        day:[line for line in observed['lines'] if line['pitcher_mlb_id'] == player]
        for day,(observed,_) in slices.items() if observed
    }
    known_player = any(selected_by_day.values())
    result = {}
    for size in WINDOWS:
        span = days[:size]
        gaps = {day.isoformat():slices[day][1] for day in span if slices[day][1]}
        selected = [line for day in span for line in selected_by_day.get(day, ())]
        facts = None
        if not gaps and known_player:
            facts = {'appearances':len(selected),
                     'multi_inning':sum(row['outs_recorded']>=RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS
                                        for row in selected)}
            for field in ('pitches_thrown','batters_faced','outs_recorded'):
                values = [row[field] for row in selected]
                facts[field] = None if None in values else sum(values)
            facts['high_pitch_outings'] = None if facts['pitches_thrown'] is None else sum(
                row['pitches_thrown'] >= RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES for row in selected)
        result[size] = {'player_observed':known_player,'first':span[-1].isoformat(),
                        'through':through.isoformat(),'gaps':gaps,
                        'sources':sorted({s for day in span if not slices[day][1]
                                         for s in slices[day][0]['sources']}), 'facts':facts}
    return result
