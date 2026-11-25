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


def _window_beyond_last_ten(source, client, player, through, start, latest, sample, cache):
    from services.club_competition_status import POSTSEASON_GAME_TYPES
    from sync_v3.season_deployment import check_pitcher_final, qualified_game_rows
    from sync_v3.workload import _game_workload

    selected = {r['pk']: r for r in sample}
    for year in range(start.year, latest.year + 1):
        end = through if year == through.year else date(year, 12, 31)
        groups = {}
        for request in pitcher_requests(end, [player], postseason_rounds=POSTSEASON_GAME_TYPES, round_totals=True):
            params = request.params()
            oid = acquire_window_source(source, client, end, request.endpoint, params)
            with source, source.cursor() as cur:
                groups[params['gameType'], params['stats']] = evidence.replay(cur, oid).body
        for stage in ('R', *sorted(POSTSEASON_GAME_TYPES)):
            with source, source.cursor() as cur:
                clubs, _ = qualified_game_rows(player, end, groups[stage,'gameLog'], groups[stage,'byDateRange'],
                                               cur=cur, game_type=stage, allow_empty=True)
            for row in (r for club in clubs.values() for r in club if start <= r['day'] <= latest):
                pk, day = row['pk'], row['day']
                if pk in selected:
                    continue
                request = calendar_requests(day)[0]
                schedule = acquire_window_source(source, client, day, request.endpoint, request.params())
                acquire_window_source(source, client, day, f'/game/{pk}/boxscore', {})
                with source, source.cursor() as cur:
                    listing = evidence.replay(cur, schedule).body
                    game, = [g for slate in listing['dates'] for g in slate['games'] if g['gamePk'] == pk]
                    final, reason = _game_workload(cur, game, day, schedule)
                    if not final or game['gameType'] != stage:
                        raise ValueError(f'Incomplete official workload for {player} in {pk}: {reason}')
                    facts, receipts = final
                    check_pitcher_final(player, row, facts, for_membership=True)
                    cache[day,pk,stage] = facts, (schedule,*receipts)
                    selected[pk] = dict(row, game_type=stage)
    return list(selected.values())


def _project_sample(source, client, player, sample, final_cache, projected, through, availability):
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
        sample = _window_beyond_last_ten(source, client, player, through, start, latest, sample, final_cache)
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
    with source, source.cursor() as cur:
        return _no_current_pitching_read(cur, team, player, through, availability, rounds)


def _no_current_pitching_read(cur, team, player, through, availability, rounds):
    from sync_v3.season_deployment import qualified_game_rows

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
                count = _project_sample(source, client, player, sample, cache, projected, through, availability)
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
    review = None
    if complete:
        from services.availability_population import current_availability_records
        from services.availability_snapshot import latest_fatigue_rows
        with db.session.begin():
            rows = [(score, pitcher) for score, pitcher in latest_fatigue_rows(team_id=team) if pitcher.active]
            board = sorted(record['pitcher'].mlb_id for record in current_availability_records(rows, reference_date=availability))
            if not set(board).issubset(listed):
                unexpected = sorted(set(board) - set(listed))
                raise ValueError(f'Current Board still claims unsupported club membership for {team}: {unexpected}')
        review = qualify_club(source, team, through, availability, digest, board)
    return dict(team=team, through=str(through), availability=ref, roster=len(listed), after_mlb=after, review=review,
                complete=complete, verified=verified, board_mlb_ids=board, seconds=monotonic()-started)


def qualify_club(source, team, through, availability, digest, expected_target):
    """Compare the product's default arms with roles from official appearances before recording the review."""
    from types import SimpleNamespace
    from models.sync_run import SyncRun
    from services.bullpen_population import eligible_bullpen_pitcher_contexts
    from services.bullpen_visibility import build_visibility_contract
    from services.club_competition_status import POSTSEASON_GAME_TYPES
    from sync_v3.dependencies import capture_reads
    from sync_v3.depth import _view

    with source, source.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        with capture_reads(cur) as reads:
            view = _view(cur, team, team, 'active', dict(date=str(availability), rosterType='active'), membership=True)
            entries = evidence.replay(cur, view['source']).body['roster']
            people = {e['person']['id']: e for e in entries}
            pitchers, logs, cache = [], {}, {}
            for player in sorted(view['pitchers']):
                try:
                    sample, _, _ = _eligibility_sample(cur, team, player, through, view['pitchers'],
                                                       POSTSEASON_GAME_TYPES, cache, roster_day=availability)
                except BaselineWithheld as exc:
                    if str(exc) != 'missing_mlb_debut_evidence' or not _no_current_pitching_read(
                            cur, team, player, through, availability, POSTSEASON_GAME_TYPES):
                        raise
                    continue
                row = people[player]
                if not sample:
                    continue
                pitchers.append(SimpleNamespace(id=player, mlb_id=player, position=row['position']['abbreviation'],
                                                active=True, full_name=row['person']['fullName'], roster_status='active',
                                                roster_status_source='mlb_stats_api:roster_sync:active'))
                logs[player] = [SimpleNamespace(game_date=r['day'], games_started=r['counts']['gamesStarted'],
                                  innings_pitched_outs=r['counts']['outs'], save=r['counts']['saves'],
                                  hold=r['counts']['holds'], save_situation=r['counts']['saveOpportunities']) for r in sample]
            paths = list(reads.requests)
        sources = sorted({evidence.latest_qualified_source(cur, path, dict(params)) for path, params in paths})
    contexts = eligible_bullpen_pitcher_contexts(pitchers, reference_date=availability, logs_by_pitcher=logs)
    expected = sorted(c['pitcher'].id for c in contexts if build_visibility_contract(
        c['eligibility'], c['roster_status'], c['logs'], availability)['is_visible_by_default'])
    if expected != expected_target:
        raise ValueError(f'Official and projected Board differ for {team}: expected {expected}, observed {expected_target}')
    proof = dict(team=team, through=str(through), availability=str(availability), generation=digest,
                 expected=expected, sources=sources)
    with db.session.begin():
        if db.session.execute(text('SELECT current_database()')).scalar_one() != TARGET:
            raise ValueError('Unexpected private Board qualification target')
        job_name = f'sync_v3_board_review_{team}'
        previous = SyncRun.query.filter_by(job_name=job_name, source='sync_v3_staging').order_by(SyncRun.id.desc()).first()
        if previous and previous.publication_outcome == proof:
            return previous.id
        now = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        review = SyncRun(job_name=job_name, source='sync_v3_staging', status='success', stage='reviewed',
                         started_at=now, completed_at=now, latest_workload_date=through,
                         records_processed=len(expected), publication_outcome=proof)
        db.session.add(review)
        db.session.flush()
        return review.id
