"""Retrospective MLB game facts alongside (independent of) published Team States."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame as Schedule
from models.team_game_pitching_split import TeamGamePitchingSplit as Split
from services.game_shape import OPENER_MAX_OUTS, BULK_FOLLOWER_MIN_OUTS
from services.rotation_support_pressure import SHORT_START_OUTS, MIN_COMPLETE_TEAM_GAME_OUTS
from services.team_game_pitching_splits import SOURCE


def retained_club_history(team_id, start, through, session):
    games = session.query(Schedule, Split).outerjoin(Split, and_(
        Split.team_id == Schedule.team_id, Split.mlb_game_pk == Schedule.game_pk,
        Split.game_date == Schedule.game_date, Split.game_type == Schedule.game_type,
        Split.source == SOURCE,
    )).filter(Schedule.team_id == team_id, Schedule.game_date.between(start, through)).order_by(
        Schedule.game_date, Schedule.game_pk,
    ).all()
    scheduled_dates = {game.game_date for game, _ in games}
    before, after = defaultdict(list), defaultdict(list)
    disputed_days = set()
    final_games = defaultdict(list)
    relief_outs = {}
    events = []
    for game, split in games:
        if game.status_state != Schedule.STATE_FINAL or game.game_type != 'R':
            continue
        final_games[game.game_date].append(game.game_pk)
        if not split or split.suspended_resumed_linkage_status != Split.LINKAGE_NONE:
            continue
        day = game.game_date
        if split.calendar_context_status == Split.STATUS_COMPLETE:
            if split.off_day_before is False:
                disputed_days.add(day - timedelta(days=1))
            if split.off_day_after is False:
                disputed_days.add(day + timedelta(days=1))
            if split.off_day_before:
                before[day - timedelta(days=1)].append(game.game_pk)
            if split.off_day_after:
                after[day + timedelta(days=1)].append(game.game_pk)
        starter, pen = split.starter_outs_recorded, split.bullpen_outs_recorded
        workload = None
        if (split.split_completeness_status == Split.STATUS_COMPLETE
                and split.starter_identity_status == Split.STARTER_KNOWN
                and starter is not None and pen is not None and min(starter, pen) >= 0
                and starter + pen == split.total_team_outs and starter + pen >= MIN_COMPLETE_TEAM_GAME_OUTS):
            # A short credited outing can be an opener. Only label unambiguous starts.
            short = starter < SHORT_START_OUTS and not (starter <= OPENER_MAX_OUTS and pen >= BULK_FOLLOWER_MIN_OUTS)
            relief_outs[game.game_pk] = pen
            workload = {'starter_outs': starter, 'bullpen_outs': pen, 'short_start': short}
        extra = split.extra_inning_indicator is True
        if workload or extra:
            events.append({'date': day.isoformat(), 'kind': 'game', 'game_pks': [game.game_pk],
                           'extra_innings': extra, 'workload': workload})
    # End-of-day totals include both games of a doubleheader. Withhold the total
    # if a retained final in the window has no usable split.
    for event in events:
        day = date.fromisoformat(event['date'])
        window = [pk for offset in range(7) for pk in final_games.get(day - timedelta(days=offset), ())]
        known = [relief_outs[pk] for pk in window if pk in relief_outs]
        event['week'] = {'final_games': len(window), 'verified_games': len(known),
                         'bullpen_outs': sum(known) if len(known) == len(window) else None}
    # Require agreement from both adjacent final dates; a hole in our schedule alone is insufficient.
    for day in (before.keys() & after.keys()) - scheduled_dates - disputed_days:
        events.append({'date': day.isoformat(), 'kind': 'off_day', 'game_pks': sorted(after[day] + before[day])})

    pitchers = session.query(Pitcher.id, Pitcher.full_name).join(GameLog).filter(
        GameLog.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED,
        GameLog.appearance_team_id == team_id, GameLog.game_date.between(start, through),
        GameLog.game_type == 'R', or_(GameLog.games_started == 0, GameLog.games_started.is_(None)),
    ).distinct().order_by(Pitcher.full_name, Pitcher.id)
    return {'events': sorted(events, key=lambda event: (event['date'], event['game_pks'])),
            'pitchers': [{'id': row.id, 'name': row.full_name} for row in pitchers]}
