"""Recover the pitching history used by a dated private offseason Board."""
from datetime import date, datetime, time, timedelta
from time import monotonic

from sqlalchemy import text

from sync_v3 import evidence
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.membership_usage import _eligibility_sample
from sync_v3.season_deployment import BaselineWithheld
from sync_v3.staging_publication_target import TARGET, acquire_window_source, project_final_appearances
from utils.db import db


def _acquire_gap(source, client, team, player, through, availability, exc):
    reason, fields = str(exc), exc.game_evidence or {}
    if reason == 'missing_eligibility_stats':
        end = through if fields['year'] == through.year else date(fields['year'], 12, 31)
        stage = fields['round']
        requests = pitcher_requests(end, [player], postseason_rounds=() if stage == 'R' else (stage,), round_totals=True)
        for request in requests:
            if request.params()['gameType'] == stage:
                acquire_window_source(source, client, end, request.endpoint, request.params())
        return
    if reason == 'missing_mlb_debut_evidence':
        acquire_window_source(source, client, availability, f'/teams/{team}/roster',
                              dict(date=str(availability), rosterType='active', hydrate='person'))
        return
    if reason in ('eligibility_game_not_confirmed', 'uncredited_game_requires_official_final'):
        played, pk = date.fromisoformat(fields['game_date']), fields['game_pk']
        request = calendar_requests(played)[0]
        acquire_window_source(source, client, played, request.endpoint, request.params())
        acquire_window_source(source, client, played, f'/game/{pk}/boxscore', {})
        return
    raise exc


def _project_sample(source, player, sample, final_cache, projected, through, availability):
    from models.fatigue_score import FatigueScore
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from services.fatigue import calculate_fatigue

    if not sample:
        return 0
    latest = sample[0]['day']
    score_day = availability if (availability-latest).days <= 14 else latest+timedelta(days=1)
    start = score_day - timedelta(days=14)
    if len(sample) == 10 and sample[-1]['day'] >= start:
        raise ValueError(f'Official last-ten sample needs the full score window for {player}')
    for row in sample:
        played, pk = row['day'], row['pk']
        facts, (schedule_id, box_id, _) = final_cache[played, pk, row['game_type']]
        if (pk, box_id) in projected:
            continue
        with source, source.cursor() as cur:
            listing = evidence.replay(cur, schedule_id).body
            game, = [g for day in listing['dates'] for g in day['games'] if g['gamePk'] == pk]
            box = evidence.replay(cur, box_id).body
        project_final_appearances([(game, box, facts, {})], played, include_context=False)
        projected.add((pk, box_id))
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private Board recovery target')
        pitcher = Pitcher.query.filter_by(mlb_id=player).one()
        games = {r['pk'] for r in sample if r['day'] >= start}
        logs = (GameLog.query.filter(GameLog.pitcher_id==pitcher.id, GameLog.game_date.between(start,score_day),
                                     GameLog.game_date<=through).order_by(GameLog.game_date.desc(), GameLog.id).all())
        if {log.mlb_game_pk for log in logs} != games or any(log.pitches_thrown is None for log in logs):
            raise ValueError(f'Private score window differs from official pitching evidence for {player}')
        stamp = datetime.combine(score_day, time(12))
        score = calculate_fatigue(pitcher, logs, reference_date=score_day)
        score.calculated_at = stamp
        previous = FatigueScore.query.filter_by(pitcher_id=pitcher.id, calculated_at=stamp).one_or_none()
        fields = [col.name for col in FatigueScore.__table__.columns if col.name not in ('id','calculated_at')]
        if previous is None:
            db.session.add(score)
        elif any(getattr(previous, k) != getattr(score, k) for k in fields):
            raise ValueError(f'Existing dated fatigue differs from complete pitching inputs for {player}')
    return len(sample)


def _no_current_pitching_evidence(source, team, player, through, availability, rounds):
    """Allow a withheld role when all current-year logs and matching totals contain no appearances."""
    from sync_v3.season_deployment import qualified_game_rows

    with source, source.cursor() as cur:
        req = dict(date=str(availability), rosterType='active', hydrate='person')
        roster = evidence.latest_qualified_source(cur, f'/teams/{team}/roster', req)
        if not roster:
            return False
        people = [entry['person'] for entry in evidence.replay(cur, roster).body['roster']
                  if entry['person']['id'] == player]
        if len(people) != 1 or people[0].get('mlbDebutDate'):
            return False
        bodies = {}
        for request in pitcher_requests(through, [player], postseason_rounds=rounds, round_totals=True):
            params = request.params()
            receipt = evidence.latest_qualified_source(cur, request.endpoint, params)
            if receipt is None:
                return False
            bodies[params['gameType'], params['stats']] = evidence.replay(cur, receipt).body
        for stage in ('R', *sorted(rounds)):
            groups, _ = qualified_game_rows(player, through, bodies[stage, 'gameLog'], bodies[stage, 'byDateRange'],
                                            cur=cur, game_type=stage, allow_empty=True)
            if any(groups.values()):
                return False
    return True


def recover(source, client, team, after, digest, *, seconds=185):
    from services.club_competition_status import POSTSEASON_GAME_TYPES
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.depth import _view

    started = monotonic()
    if team not in MLB_TEAM_IDS:
        raise ValueError('An MLB club is required')
    with source, source.cursor() as cur:
        cur.execute("SELECT represented,manifest->>'availability_reference' FROM candidate.generations WHERE digest=%s", (digest,))
        through, ref = cur.fetchone()
        availability = date.fromisoformat(ref)
        view = _view(cur, team, team, 'active', dict(date=ref, rosterType='active'), membership=True)
        if view['reason']:
            raise ValueError(f"Unqualified availability roster: {view['reason']}")
        listed = view['pitchers']
    remaining = sorted(player for player in listed if player > after)
    verified = []
    projected = set()
    for player in remaining:
        seen = set()
        while monotonic()-started < seconds:
            try:
                with source, source.cursor() as cur:
                    cache = {}
                    sample, _, _ = _eligibility_sample(cur, team, player, through, listed, POSTSEASON_GAME_TYPES,
                                                       cache, roster_day=availability)
                count = _project_sample(source, player, sample, cache, projected, through, availability)
                verified.append(dict(mlb=player, games=count))
                after = player
                break
            except BaselineWithheld as exc:
                key = (str(exc), str(exc.game_evidence))
                if key in seen and str(exc) == 'missing_mlb_debut_evidence' and _no_current_pitching_evidence(
                        source, team, player, through, availability, POSTSEASON_GAME_TYPES):
                    verified.append(dict(mlb=player, games=0, role='withheld_no_supported_mlb_appearances'))
                    after = player
                    break
                if key in seen:
                    raise ValueError(f'Persistent eligibility gap for MLB {player}: {key}') from exc
                seen.add(key)
                _acquire_gap(source, client, team, player, through, availability, exc)
        if monotonic()-started >= seconds:
            break
    complete = not any(p > after for p in listed)
    board = None
    if complete:
        from services.availability_population import current_availability_records
        from services.availability_snapshot import latest_fatigue_rows
        with db.session.begin():
            rows = [(score, pitcher) for score, pitcher in latest_fatigue_rows(team_id=team) if pitcher.active]
            board = sorted(record['pitcher'].mlb_id for record in current_availability_records(rows, reference_date=availability))
            if not set(board).issubset(listed):
                raise ValueError(f'Current Board still claims unsupported official club membership for {team}')
    return dict(team=team, through=str(through), availability=ref, roster=len(listed), after_mlb=after,
                complete=complete, verified=verified, board_mlb_ids=board, seconds=monotonic()-started)
