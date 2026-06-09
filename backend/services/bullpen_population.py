from datetime import timedelta

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from services.bullpen_eligibility import evaluate_bullpen_eligibility
from services.pitcher_role import ROLE_WINDOW_DAYS
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
    classify_role,
    role_authority_enabled,
)
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

    ref = reference_date or product_current_date()
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


def _eligibility_for(pitcher, logs, roster_status, reference_date, use_role_authority):
    """
    Decide bullpen eligibility for one pitcher.

    Role Authority (default) derives Starter/Reliever/Ambiguous/Unknown from the
    authoritative gamesStarted signal. The legacy innings heuristic remains
    selectable for rollback and for the read-only diagnostic comparison.
    """
    if use_role_authority:
        return classify_role(pitcher, logs, reference_date=reference_date)
    return evaluate_bullpen_eligibility(
        pitcher,
        logs,
        reference_date=reference_date,
        respect_local_active=not roster_status.get('is_authoritative'),
    )


def eligible_bullpen_pitcher_contexts(
    pitchers,
    include_stale=False,
    include_inactive_context=False,
    reference_date=None,
    logs_by_pitcher=None,
    use_role_authority=None,
):
    """
    Return the default-board eligible bullpen population for a pitcher set.

    This is the single shared definition consumed by the Bullpen Board, Bullpen
    Stress (via team context), What Changed, and Follow My Team: roster status
    must permit the default board, and role authority (or the legacy heuristic)
    must include the pitcher. Defining it once here is the anti-drift layer — no
    surface re-decides role.

    Role mapping (Role Authority V1):
      - Starter   → excluded from the bullpen population.
      - Reliever  → included.
      - Ambiguous → included with a visible caveat (they relieve).
      - Unknown   → withheld by default; surfaced only in expanded
                    (include_inactive_context) mode, never silently a reliever.
    """
    pitcher_list = list(pitchers or [])
    ref = reference_date or product_current_date()
    if use_role_authority is None:
        use_role_authority = role_authority_enabled()
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
        eligibility = _eligibility_for(
            pitcher, logs, roster_status, ref, use_role_authority,
        )
        if not eligibility.get('eligible'):
            # Unknown roles are surfaced only in expanded mode for awareness;
            # Starters are always excluded.
            unknown_in_expanded = (
                use_role_authority
                and include_inactive_context
                and eligibility.get('role') == ROLE_UNKNOWN
            )
            if not unknown_in_expanded:
                continue

        contexts.append({
            'pitcher': pitcher,
            'logs': logs,
            'eligibility': eligibility,
            'roster_status': roster_status,
        })

    return contexts, roster_status_summary(roster_statuses, contexts)


def population_diagnostic(
    pitchers,
    include_stale=False,
    reference_date=None,
    logs_by_pitcher=None,
):
    """
    Read-only comparison of the legacy innings population vs. the Role Authority
    population for the same pitcher set. Changes nothing; used by the diagnostic
    rollout to audit additions/removals before role authority drives a surface.
    """
    pitcher_list = list(pitchers or [])
    ref = reference_date or product_current_date()
    if logs_by_pitcher is None:
        logs_by_pitcher = usage_logs_by_pitcher(
            [pitcher.id for pitcher in pitcher_list],
            include_stale=include_stale,
            reference_date=ref,
        )

    legacy_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitcher_list, include_stale=include_stale, reference_date=ref,
        logs_by_pitcher=logs_by_pitcher, use_role_authority=False,
    )
    role_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitcher_list, include_stale=include_stale, reference_date=ref,
        logs_by_pitcher=logs_by_pitcher, use_role_authority=True,
    )
    legacy_ids = {ctx['pitcher'].id for ctx in legacy_contexts}
    role_ids = {ctx['pitcher'].id for ctx in role_contexts}

    name_of = {p.id: getattr(p, 'full_name', None) for p in pitcher_list}

    # Classify every roster-permitted pitcher so Starters/Unknowns are reported.
    role_distribution = {ROLE_STARTER: 0, ROLE_RELIEVER: 0, ROLE_AMBIGUOUS: 0, ROLE_UNKNOWN: 0}
    confidence_distribution = {'high': 0, 'medium': 0, 'low': 0, 'none': 0}
    records = []
    for pitcher in pitcher_list:
        roster_status = classify_roster_status(pitcher)
        if not allows_default_board(roster_status) and not (
            include_stale and allows_inactive_context(roster_status)
        ):
            continue
        role = classify_role(pitcher, logs_by_pitcher.get(pitcher.id, []), reference_date=ref)
        role_name = role.get('role')
        if role_name in role_distribution:
            role_distribution[role_name] += 1
        conf = role.get('confidence', 'none')
        if conf in confidence_distribution:
            confidence_distribution[conf] += 1
        records.append({
            'pitcher_id': pitcher.id,
            'name': name_of.get(pitcher.id),
            'role': role_name,
            'confidence': conf,
            'reason': role.get('reason'),
            'in_legacy_population': pitcher.id in legacy_ids,
            'in_role_population': pitcher.id in role_ids,
        })

    def _named(ids):
        return [{'pitcher_id': pid, 'name': name_of.get(pid)} for pid in sorted(ids)]

    return {
        'use_role_authority_default': role_authority_enabled(),
        'totals': {
            'legacy_population': len(legacy_ids),
            'role_population': len(role_ids),
        },
        'additions': _named(role_ids - legacy_ids),   # newly included (e.g. long relievers)
        'removals': _named(legacy_ids - role_ids),     # newly excluded (e.g. starters)
        'role_distribution': role_distribution,
        'confidence_distribution': confidence_distribution,
        'records': records,
    }


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
