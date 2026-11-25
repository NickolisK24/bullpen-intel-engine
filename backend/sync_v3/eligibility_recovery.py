"""Recover missing historical pitching evidence through the private acquisition queue."""

from datetime import date, datetime, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

from services.availability import ACTIVE_WINDOW_DAYS
from services.game_finality import classify_status
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import canonical, evidence, queue
from sync_v3.dependencies import capture_reads
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.group_performance import active_group_performance
from sync_v3.readiness import availability_day_population, represented_readiness
from sync_v3.workload import _game_workload


def _missing_workload(cur, through, report, reads, missing):
    reference = date.fromisoformat(report['reference_date'])
    schedule, _ = calendar_requests(reference)
    if (schedule.endpoint, tuple(sorted(schedule.params().items()))) in reads.requests:
        missing(reference, schedule.endpoint, schedule.params())

    if not report.get('gap_date') or report['reason'] not in ('missing_complete_schedule', 'missing_compatible_final'):
        return
    day = date.fromisoformat(report['gap_date'])
    if not 0 <= (through - day).days < ACTIVE_WINDOW_DAYS:
        return
    _missing_day_finals(cur, day, missing)


def _missing_day_finals(cur, day, missing, *, team=None):
    schedule, _ = calendar_requests(day)
    if missing(day, schedule.endpoint, schedule.params()):
        return
    receipt = evidence.latest_qualified_source(cur, schedule.endpoint, schedule.params())
    if receipt is None:
        return
    for listing in evidence.replay(cur, receipt).body['dates']:
        for game in listing['games']:
            if game['gameType'] != 'R':
                continue
            if team is not None and team not in (game['teams']['home']['team']['id'], game['teams']['away']['team']['id']):
                continue
            if _game_workload(cur, game, day, receipt)[1] == 'missing_compatible_final':
                missing(day, f"/game/{game['gamePk']}/boxscore", {})


def _performance_gaps(cur, team, through, report, missing):
    if report['reason']:
        return report['reason']
    days = report.get('dates') or {}
    if not days:
        return 'no_supported_relief_outings'
    unresolved = None
    for represented, row in sorted(days.items()):
        if row.get('source_conflicts'):
            # The metric qualifier handles the disputed fields. Other outing
            # dates can still supply evidence for independent season metrics.
            unresolved = 'official_performance_source_conflict'
            continue
        reason = row['reason']
        if reason:
            unresolved = unresolved or reason
            day = date.fromisoformat(represented)
            if (day.year == through.year and day <= through and row['outings']
                    and reason in ('missing_complete_schedule', 'missing_compatible_final')):
                _missing_day_finals(cur, day, missing, team=team)
    return unresolved


def _needed(cur, team, through, include_workload, performance=False, board_rest=False):
    if performance:
        report = active_group_performance(cur, team, through)
    else:
        with capture_reads(cur) as reads:
            report = represented_readiness(cur, team, through)
    competition = report.get('competition') or {}
    if (competition.get('team_id') == team and competition.get('status') == 'season_complete' and report['reason']
            and report['reason'] == competition.get('basis') and report.get('team_state') is None):
        return report['reason'], [], True
    if board_rest and not report['reason']:
        staff, arrival = availability_day_population(cur, report, through)
        if staff is None:
            return 'missing_qualified_board_roster', [], False
        if arrival is not None:
            report = arrival
    gaps = dict(report.get('eligibility_gaps', {}))
    for player, profile in report.get('profiles', {}).items():
        if profile.get('reason') == 'uncredited_game_requires_official_final':
            gaps[player] = dict(reason=profile['reason'], evidence=profile.get('game_evidence'))
    requests = set()

    def missing(day, endpoint, params):
        status = evidence.latest_source_status(cur, endpoint, params)
        if status is None or status[1] == 'failed':
            requests.add((day, endpoint, tuple(sorted(params.items()))))
            return True
        return False

    if board_rest:
        for player, profile in report.get('profiles', {}).items():
            if profile['reason'] == 'missing_game_log_or_dated_totals':
                for request in pitcher_requests(through, [int(player)]):
                    missing(through, request.endpoint, request.params())

    if not performance and include_workload and report['reason']:
        _missing_workload(cur, through, report, reads, missing)

    for player, gap in gaps.items():
        fields = gap.get('evidence') or {}
        if gap['reason'] == 'missing_eligibility_stats':
            year, stage = fields['year'], fields['round']
            end = through if year == through.year else date(year, 12, 31)
            if end <= through:
                rounds = () if stage == 'R' else (stage,)
                for request in pitcher_requests(end, [int(player)], postseason_rounds=rounds, round_totals=True):
                    params = request.params()
                    if params['gameType'] == stage:
                        missing(end, request.endpoint, params)
            continue
        if gap['reason'] not in ('eligibility_game_not_confirmed', 'uncredited_game_requires_official_final'):
            continue
        if 'game_date' not in fields:
            continue
        day = date.fromisoformat(fields['game_date'])
        if day > through:
            continue
        request, _ = calendar_requests(day)
        if missing(day, request.endpoint, request.params()):
            continue
        receipt = evidence.latest_qualified_source(cur, request.endpoint, request.params())
        if receipt is None:
            continue
        games = [game for listing in evidence.replay(cur, receipt).body['dates'] for game in listing['games']
                 if game['gamePk'] == fields['game_pk']]
        if len(games) != 1:
            continue
        game, = games
        if (game['officialDate'] == str(day) and game['gameType'] == fields.get('game_type')
                and classify_status(game['status']).final_status
                and fields['team_id'] in (game['teams']['away']['team']['id'], game['teams']['home']['team']['id'])):
            missing(day, f"/game/{game['gamePk']}/boxscore", {})
    reason = _performance_gaps(cur, team, through, report, missing) if performance else report['reason']
    return reason, sorted(requests), False


def recover(connection, team, through, *, fetch, max_jobs, include_workload=False, performance=False, board_rest=False,
            clock=lambda: datetime.now(timezone.utc)):
    from sync_v3.current_worker import verify_target

    if sum((include_workload, performance, board_rest)) > 1:
        raise ValueError('Select one historical recovery objective')
    name = verify_target(connection)
    today = clock().astimezone(ZoneInfo('America/New_York')).date()
    if team not in MLB_TEAM_IDS or not 1 <= max_jobs <= 256 or through >= today:
        raise ValueError('Historical evidence recovery requires an MLB club, a completed date and a bounded job limit')
    outcomes = []
    waiting = False
    while True:
        with connection, connection.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            reason, requests, season_complete = _needed(cur, team, through, include_workload, performance, board_rest)
        if not reason or not requests or len(outcomes) >= max_jobs:
            break
        count = len(outcomes)
        waiting = False
        for day, endpoint, parameters in requests:
            if len(outcomes) >= max_jobs:
                break
            payload = dict(endpoint=endpoint, params=dict(parameters), eligibility_recovery=True)
            identity = sha256(evidence.encode_json(['eligibility_recovery', str(day), payload])).hexdigest()
            with connection, connection.cursor() as cur:
                at = clock()
                job = queue.enqueue(cur, identity, payload, at, budget='historical', product_date=day)
                claimed = queue.claim(cur, at, budget='historical', product_date=day, only_job_id=job)
                if not claimed:
                    cur.execute('SELECT state FROM candidate.jobs WHERE id=%s', (job,))
                    waiting |= cur.fetchone()[0] in ('pending', 'running')
            if claimed:
                _, outcome = evidence.execute(connection, claimed, fetch, clock,
                                              on_received=lambda c, oid, obs: canonical.observe(c, oid, obs, day))
                outcomes.append(outcome)
        if count == len(outcomes) or any(outcome != 'received' for outcome in outcomes):
            break
    if season_complete:
        status = 'season_complete'
    elif not reason:
        status = 'ready'
        if performance:
            status = 'outing_finals_complete'
        elif board_rest:
            status = 'board_eligibility_complete'
    elif any(outcome != 'received' for outcome in outcomes):
        status = 'acquisition_failed'
    elif requests and len(outcomes) == max_jobs:
        status = 'batch_limit'
    elif requests and waiting:
        status = 'awaiting_retry_or_lease'
    else:
        status = 'withheld'
    report = dict(database=name, club=team, through=str(through), status=status, receipts=outcomes,
                  publication_attempted=False)
    if performance:
        report['performance_reason'] = reason
    elif board_rest:
        report['board_rest_reason'] = reason
    else:
        report['readiness_reason'] = reason
    return report
