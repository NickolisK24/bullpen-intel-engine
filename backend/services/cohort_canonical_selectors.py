"""Bounded canonical game selectors for a single cohort build.

Compatibility workload and roster projections are deliberately not represented
as canonical versions here. Their content closure remains separate work.
"""

from models.final_game_reconciliation import FinalGameVersion, FinalPitchingAppearanceVersion
from models.live_game_delta import ProvisionalPitchingAppearanceState
from models.pregame_context import GamePregameContextVersion
from models.roster_membership import RosterMembershipInterval
from sqlalchemy import func
from utils.db import db


def require_bounded_canonical_scope(plan):
    games, pitchers, teams = (plan.affected_game_ids_json, plan.affected_pitcher_ids_json,
                             plan.affected_team_ids_json)
    if plan.authority_class in ('final', 'corrected_final') and not games and not pitchers:
        raise ValueError('canonical_final_selector_requires_bounded_scope')
    if plan.authority_class in ('live', 'pregame_authoritative') and not games:
        raise ValueError('canonical_selector_requires_game_scope')
    if (plan.authority_class == 'roster_authoritative' or set(plan.affected_domains_json or ()).intersection(
        ('roster_composition', 'organizational_depth', 'team_state', 'clean_options')
    )) and not teams and not pitchers:
        raise ValueError('canonical_roster_selector_requires_bounded_scope')


def capture_canonical_selectors(plan):
    require_bounded_canonical_scope(plan)
    games = sorted(set(int(value) for value in plan.affected_game_ids_json or ()))
    authority = plan.authority_class
    result = {}
    teams = sorted(set(plan.affected_team_ids_json or ()))
    pitchers = sorted(set(plan.affected_pitcher_ids_json or ()))
    if authority == 'roster_authoritative' or set(plan.affected_domains_json or ()).intersection(
        ('roster_composition', 'organizational_depth', 'team_state', 'clean_options')
    ):
        if not teams and not pitchers:
            raise ValueError('canonical_roster_selector_requires_bounded_scope')
        query = RosterMembershipInterval.query.populate_existing().filter(
            RosterMembershipInterval.is_current_version.is_(True),
            RosterMembershipInterval.is_void.is_(False),
            RosterMembershipInterval.effective_start_date <= plan.baseball_date,
            db.or_(RosterMembershipInterval.effective_end_date.is_(None),
                   RosterMembershipInterval.effective_end_date >= plan.baseball_date),
        )
        query = query.filter(RosterMembershipInterval.team_id.in_(teams)) if teams else query.filter(
            RosterMembershipInterval.pitcher_id.in_(pitchers))
        result['roster_scope'] = {'teams': teams, 'pitchers': [] if teams else pitchers}
        result['roster_versions'] = [{
            'id': row.id, 'team_id': row.team_id, 'pitcher_id': row.pitcher_id,
            'membership_type': row.membership_type,
            'start': row.effective_start_date.isoformat(),
            'end': row.effective_end_date.isoformat() if row.effective_end_date else None,
            'supersedes_interval_id': row.supersedes_interval_id,
            'opened_by_observation_id': row.opened_by_observation_id,
            'closed_by_observation_id': row.closed_by_observation_id,
        } for row in query.order_by(RosterMembershipInterval.id).all()]
    if authority in ('final', 'corrected_final'):
        if not games and not pitchers:
            raise ValueError('canonical_final_selector_requires_bounded_scope')
        query = FinalPitchingAppearanceVersion.query.populate_existing().filter(
            FinalPitchingAppearanceVersion.is_current.is_(True))
        if games:
            query = query.filter(FinalPitchingAppearanceVersion.game_pk.in_(games))
        if pitchers:
            query = query.filter(FinalPitchingAppearanceVersion.pitcher_id.in_(pitchers))
        result['appearance_scope'] = {'games': games, 'pitchers': pitchers}
        result['appearance_versions'] = [{field: getattr(row, field) for field in (
            'id', 'game_pk', 'pitcher_id', 'final_game_version_id', 'version_number',
            'predecessor_version_id', 'fact_fingerprint', 'boxscore_observation_id',
        )} for row in query.order_by(FinalPitchingAppearanceVersion.game_pk,
                                    FinalPitchingAppearanceVersion.pitcher_id).all()]
    if not games:
        if authority == 'live':
            raise ValueError('canonical_live_selector_requires_game_scope')
        return result
    if authority in ('live', 'final', 'corrected_final') or 'game_context' in (
        plan.affected_domains_json or ()
    ):
        rows = FinalGameVersion.query.populate_existing().filter(
            FinalGameVersion.game_pk.in_(games), FinalGameVersion.is_current.is_(True),
        ).order_by(FinalGameVersion.game_pk).all()
        by_game = {row.game_pk: row for row in rows}
        result['final'] = {
            str(game): None if game not in by_game else {
                field: getattr(by_game[game], field)
                for field in ('id', 'version_number', 'predecessor_version_id',
                              'fact_fingerprint', 'core_completeness',
                              'boxscore_observation_id', 'home_team_id', 'away_team_id',
                              'home_score', 'away_score', 'innings_played', 'extra_innings')
            } for game in games
        }
    if authority == 'pregame_authoritative':
        latest = db.session.query(
            GamePregameContextVersion.game_pk.label('game'),
            func.max(GamePregameContextVersion.version_number).label('version'),
        ).filter(
            GamePregameContextVersion.game_pk.in_(games),
        ).group_by(GamePregameContextVersion.game_pk).subquery()
        rows = GamePregameContextVersion.query.populate_existing().join(latest,
            (GamePregameContextVersion.game_pk == latest.c.game)
            & (GamePregameContextVersion.version_number == latest.c.version),
        ).order_by(GamePregameContextVersion.game_pk).all()
        by_game = {row.game_pk: row for row in rows}
        result['pregame'] = {
            str(game): None if game not in by_game else {
                **{field: getattr(by_game[game], field) for field in (
                    'id', 'version_number', 'source_observation_id', 'context_fingerprint',
                    'completeness', 'home_probable_pitcher_id', 'away_probable_pitcher_id',
                )},
                'scheduled_at': (by_game[game].scheduled_at.isoformat()
                                 if by_game[game].scheduled_at else None),
            } for game in games
        }
    if authority == 'live':
        rows = ProvisionalPitchingAppearanceState.query.populate_existing().filter(
            ProvisionalPitchingAppearanceState.game_pk.in_(games),
            ProvisionalPitchingAppearanceState.is_current.is_(True),
        ).order_by(ProvisionalPitchingAppearanceState.game_pk,
                   ProvisionalPitchingAppearanceState.pitcher_id).all()
        result['live'] = {
            str(game): [{field: getattr(row, field) for field in (
                'id', 'game_pk', 'pitcher_id', 'team_id_at_appearance',
                'pitches_thrown', 'outs_recorded', 'batters_faced', 'outing_status',
                'latest_observation_id', 'fact_fingerprint', 'completeness', 'authority_state',
            )} for row in rows if row.game_pk == game] for game in games
        }
    return result


def capture_reference():
    from services.availability_reference_date import resolve_product_day

    day = resolve_product_day()
    return {'product_date': day.calendar_date.isoformat(),
            'timezone': day.timezone_name, 'limitations': list(day.limitations)}
