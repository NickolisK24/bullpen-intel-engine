from datetime import date, timedelta

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.bullpen_eligibility import evaluate_bullpen_eligibility
from services.pitcher_role import ROLE_WINDOW_DAYS
from services.roster_status import (
    allows_default_board,
    allows_inactive_context,
    classify_roster_status,
    roster_status_summary,
)


def usage_logs_by_pitcher(pitcher_ids, days=ROLE_WINDOW_DAYS, include_stale=False, reference_date=None):
    """
    Recent usage logs grouped by pitcher_id for bullpen population decisions.

    Default mode matches the Bullpen Board's non-stale behavior. When stale
    context is explicitly requested, the helper keeps enough latest usage
    evidence to classify role and bullpen relevance without presenting it as
    current availability.
    """
    if not pitcher_ids:
        return {}

    ref = reference_date or date.today()
    query = GameLog.query.filter(GameLog.pitcher_id.in_(pitcher_ids))
    if not include_stale:
        query = query.filter(GameLog.game_date >= ref - timedelta(days=days))

    logs = query.order_by(GameLog.pitcher_id, desc(GameLog.game_date)).all()
    grouped = {}
    for log in logs:
        bucket = grouped.setdefault(log.pitcher_id, [])
        if include_stale and len(bucket) >= 10:
            continue
        bucket.append(log)
    return grouped


def eligible_bullpen_pitcher_contexts(
    pitchers,
    include_stale=False,
    include_inactive_context=False,
    reference_date=None,
    logs_by_pitcher=None,
):
    """
    Return the default-board eligible bullpen population for a pitcher set.

    This is the shared definition used by the Bullpen Board and the What
    Changed card: roster status must permit the default board, and usage must
    pass the bullpen eligibility gate. It does not classify availability.
    Roster-inactive context is opt-in so stale workload inclusion cannot leak
    unavailable players into default league-wide counts.
    """
    pitcher_list = list(pitchers or [])
    ref = reference_date or date.today()
    if logs_by_pitcher is None:
        logs_by_pitcher = usage_logs_by_pitcher(
            [pitcher.id for pitcher in pitcher_list],
            include_stale=include_stale,
            reference_date=ref,
        )

    contexts = []
    roster_statuses = []
    for pitcher in pitcher_list:
        roster_status = classify_roster_status(pitcher)
        roster_statuses.append(roster_status)
        if not allows_default_board(roster_status):
            if not (include_inactive_context and allows_inactive_context(roster_status)):
                continue

        logs = logs_by_pitcher.get(pitcher.id, [])
        eligibility = evaluate_bullpen_eligibility(
            pitcher,
            logs,
            reference_date=ref,
            respect_local_active=not roster_status.get('is_authoritative'),
        )
        if not eligibility.get('eligible'):
            continue

        contexts.append({
            'pitcher': pitcher,
            'logs': logs,
            'eligibility': eligibility,
            'roster_status': roster_status,
        })

    return contexts, roster_status_summary(roster_statuses, contexts)


def eligible_bullpen_pitchers(team_id, include_stale=False, reference_date=None):
    pitchers = (
        Pitcher.query
        .filter(Pitcher.team_id == team_id, Pitcher.active == True)
        .order_by(Pitcher.full_name)
        .all()
    )
    contexts, roster_summary = eligible_bullpen_pitcher_contexts(
        pitchers,
        include_stale=include_stale,
        reference_date=reference_date,
    )
    return [context['pitcher'] for context in contexts], roster_summary
