"""Historical Board workload from the selected club's competitive game calendar."""

from collections import defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from psycopg2.extras import Json

from services.club_competition_status import COMPETITIVE_GAME_TYPES, POSTSEASON_GAME_TYPES
from services.game_finality import classify_status
from services.public_team_relief_work import team_relief_concentration, team_relief_windows
from sync_v3.competition_calendar import calendar_games
from sync_v3.discovery import calendar_requests, competition_calendar_request
from sync_v3.evidence import replay
from sync_v3.history import METHODOLOGY
from sync_v3.intelligence_history import DOMAINS


def _club_game(game, team):
    home, away = (game['teams'][side]['team']['id'] for side in ('home', 'away'))
    if team in (home, away):
        status = classify_status(game['status'])
        return home, away, game['gameType'], game['officialDate'], 'final' if status.final_status else status.state
    return None


def _coverage_reason(day, season_year, season_digest, slate_digests, daily, expected, verified):
    if not season_digest or day.year != season_year:
        return 'missing_competition_calendar'
    if len(slate_digests) != 1 or daily != expected:
        return 'club_calendars_unconfirmed'
    for pk, (_, _, kind, official, state) in daily.items():
        if state in ('postponed', 'cancelled'):
            continue
        if (kind not in COMPETITIVE_GAME_TYPES or state != 'final' or official != day.isoformat()
                or (kind in POSTSEASON_GAME_TYPES and pk not in verified)):
            return 'club_game_unresolved'
    return None


def board_workload_windows(cur, digest, team, through, regular, postseason):
    start = through - timedelta(days=29)
    dates = [start + timedelta(days=offset) for offset in range(30)]
    readiness_method = DOMAINS['readiness'][1]
    calendar = competition_calendar_request(through.year)
    cur.execute("""SELECT DISTINCT f.id,f.sha256,h.facts->'verified_decisions',f.outcome,ref.source_id
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   JOIN candidate.workload_history_sources hs ON hs.snapshot=h.id
                   JOIN candidate.fetches f ON f.id=hs.source_id
                   LEFT JOIN candidate.refusals ref ON ref.source_id=f.id
                   WHERE g.generation=%s AND h.subject='team' AND h.mlb_id=%s AND h.methodology=%s
                     AND f.endpoint='/schedule' AND f.parameters=%s ORDER BY f.id""",
                (digest, team, readiness_method, Json(calendar.params())))
    pins = cur.fetchall()
    season_digest = None
    expected = defaultdict(dict)
    verified = set()
    if pins and all(row[3:] == ('received', None) for row in pins) and len({row[1] for row in pins}) == 1:
        source, season_digest, decisions = pins[0][:3]
        verified = set(decisions or [])
        body = replay(cur, source).body
        calendar_games(calendar.params(), body)
        # Compare daily listings. The season's final-game index collapses a
        # postponement and its later makeup into one entry for the same gamePk.
        for slate in body['dates']:
            day = date.fromisoformat(slate['date'])
            if start <= day <= through:
                for game in slate['games']:
                    identity = _club_game(game, team)
                    if identity:
                        expected[day][game['gamePk']] = identity

    cur.execute("""SELECT f.parameters,f.sha256,r.facts FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   JOIN candidate.workload_history_sources hs ON hs.snapshot=h.id
                   JOIN candidate.fetches f ON f.id=hs.source_id
                   LEFT JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='schedule'
                   LEFT JOIN candidate.revisions r ON r.id=c.revision_id
                   WHERE g.generation=%s AND h.subject='team' AND h.mlb_id=%s AND h.methodology=%s
                     AND f.endpoint='/schedule' AND f.outcome='received'
                     AND f.parameters->>'startDate' BETWEEN %s AND %s""",
                (digest, team, METHODOLOGY, start.isoformat(), through.isoformat()))
    slates, daily = defaultdict(set), defaultdict(dict)
    for params, sha, game in cur:
        day = date.fromisoformat(params['startDate'])
        if params != calendar_requests(day)[0].params():
            continue
        slates[day].add(sha)
        identity = _club_game(game, team) if game else None
        if identity:
            daily[day][game['gamePk']] = identity

    gaps = dict(regular['gaps'])
    gaps.update(postseason['gaps'])
    coverage = {}
    for day in dates:
        key = day.isoformat()
        reason = gaps.get(key) or _coverage_reason(
            day, through.year, season_digest, slates[day], daily[day], expected[day], verified)
        coverage[key] = dict(complete_enough_to_publish=reason is None, reason_codes=[reason] if reason else [])
    logs = []
    outings = []
    for line in regular['appearances'] + postseason['appearances']:
        day = date.fromisoformat(line['game_date'])
        if line['appearance_team_id'] != team or not start <= day <= through:
            raise ValueError('Workload line outside selected team or window')
        game = daily[day].get(line['game_pk'])
        if not game or game[-1] != 'final':
            coverage[line['game_date']] = dict(complete_enough_to_publish=False, reason_codes=['club_calendars_unconfirmed'])
        log = SimpleNamespace(game_date=day, games_started=0, pitches_thrown=line['pitches_thrown'],
                              innings_pitched_outs=line['innings_pitched_outs'])
        logs.append(log)
        if day >= through - timedelta(days=6):
            outings.append((line['game_pk'], line.get('mlb_id')))
    windows = team_relief_windows(logs, through, coverage)
    appearances = windows['window_7']['appearances']
    count = None
    if (appearances['status'] == 'complete' and appearances['value'] == len(outings) == len(set(outings))
            and all(type(player) is int and player > 0 for _, player in outings)):
        count = len({player for _, player in outings})
    return dict(data_through=through.isoformat(), windows=windows, contributing_relievers_7d=count,
                season_calendar_digest=season_digest,
                regular_citation=regular['citation'], postseason_citation=postseason['citation'])


def board_concentration(through, seven, appearances, directory, population):
    """Rank game-side contributors using frozen public pitcher identities and the dated bullpen cohort."""
    rows, active = [], set()
    members = {member['player'] for member in population['members']}
    if seven['pitches']['status'] == 'complete':
        recent = [line for line in appearances if seven['start'] <= line['game_date'] <= seven['through']]
        missing = set()
        for mlb in {line['mlb_id'] for line in recent}:
            player = directory.get(mlb)
            if not player or player['public_id'] is None or not player.get('name'):
                missing.add(mlb)
        if missing:
            withheld = dict(seven, pitches=dict(status='unavailable', value=None,
                                                reason_codes=['contributor_identity_unresolved']))
            return dict(team_relief_concentration([], through, withheld, set()),
                        unresolved_contributor_mlb_ids=sorted(missing))
        for line in recent:
            mlb = line['mlb_id']
            player = directory[mlb]
            if (population['reason'] or population['through'] != through.isoformat()
                    or line['appearance_team_id'] != population['team']
                    or (mlb in members and player['team_id'] != population['team'])):
                withheld = dict(seven, pitches=dict(status='unavailable', value=None,
                                                    reason_codes=['bullpen_membership_unconfirmed']))
                return team_relief_concentration([], through, withheld, set())
            pitcher = SimpleNamespace(id=player['public_id'], full_name=player['name'])
            if mlb in members:
                active.add(pitcher.id)
            log = SimpleNamespace(game_date=date.fromisoformat(line['game_date']), games_started=0,
                                  pitches_thrown=line['pitches_thrown'], innings_pitched_outs=line['innings_pitched_outs'])
            rows.append((log, pitcher))
    return team_relief_concentration(rows, through, seven, active)
