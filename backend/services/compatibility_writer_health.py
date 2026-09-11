"""Read-only ownership invariants, separate from expected write suppressions."""

from datetime import timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased

from models.compatibility_write_event import CompatibilityWriteEvent
from models.final_game_reconciliation import FinalGameVersion, FinalPitchingAppearanceVersion
from models.game_log import GameLog
from models.live_game_delta import ProvisionalPitchingAppearanceState
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.roster_membership import PlayerTransactionVersion
from models.roster_membership import RosterMembershipInterval
from models.sync_job import SyncJob, SyncJobAttempt
from utils.db import db
from utils.time import utc_now_naive


def compatibility_writer_health(*, now=None):
    now = now or utc_now_naive()
    membership = aliased(RosterMembershipInterval)
    governed = and_(
        membership.pitcher_id == Pitcher.id, membership.is_current_version.is_(True),
        membership.is_void.is_(False), membership.effective_end_date.is_(None),
        membership.membership_type.in_(('active_roster', 'forty_man_roster')),
    )
    has_membership = db.session.query(membership.id).filter(governed).exists()
    team_matches = db.session.query(membership.id).filter(
        governed, membership.team_id == Pitcher.team_id,
    ).exists()
    mismatched_pitchers = db.session.query(Pitcher.id, Pitcher.team_id).filter(
        has_membership, ~team_matches,
    ).order_by(Pitcher.id).all()
    current_live = db.session.query(ProvisionalPitchingAppearanceState.id).join(
        FinalGameVersion, and_(
            FinalGameVersion.game_pk == ProvisionalPitchingAppearanceState.game_pk,
            FinalGameVersion.is_current.is_(True),
        ),
    ).filter(ProvisionalPitchingAppearanceState.is_current.is_(True)).count()
    appearance = FinalPitchingAppearanceVersion
    mismatched_final = db.session.query(appearance.game_pk, appearance.pitcher_id).outerjoin(
        GameLog, and_(GameLog.mlb_game_pk == appearance.game_pk, GameLog.pitcher_id == appearance.pitcher_id),
    ).filter(appearance.is_current.is_(True), or_(
        GameLog.id.is_(None),
        GameLog.pitches_thrown.is_distinct_from(appearance.pitches_thrown),
        GameLog.innings_pitched_outs.is_distinct_from(appearance.outs_recorded),
        GameLog.batters_faced.is_distinct_from(appearance.batters_faced),
        GameLog.appearance_team_id.is_distinct_from(appearance.team_id_at_appearance),
    )).all()
    extra_final = db.session.query(GameLog.mlb_game_pk, GameLog.pitcher_id).join(
        FinalGameVersion, and_(FinalGameVersion.game_pk == GameLog.mlb_game_pk,
                              FinalGameVersion.is_current.is_(True)),
    ).filter(~db.session.query(appearance.id).filter(
        appearance.game_pk == GameLog.mlb_game_pk,
        appearance.pitcher_id == GameLog.pitcher_id,
        appearance.is_current.is_(True),
    ).exists()).all()
    conflicting_clubs = db.session.query(membership.pitcher_id, membership.membership_type).filter(
        membership.is_current_version.is_(True), membership.is_void.is_(False),
        membership.effective_end_date.is_(None),
        membership.membership_type.in_(('active_roster', 'forty_man_roster')),
    ).group_by(membership.pitcher_id, membership.membership_type).having(
        func.count(func.distinct(membership.team_id)) > 1,
    ).all()
    recent = dict(db.session.query(CompatibilityWriteEvent.outcome, func.count()).filter(
        CompatibilityWriteEvent.created_at >= now - timedelta(hours=24),
    ).group_by(CompatibilityWriteEvent.outcome).all())
    from services.transaction_ingestion import (
        _TRANSACTION_VERSION_FACT_FIELDS, _transaction_fact_fingerprint,
    )
    transaction_conflicts = []
    # One joined scan compares the current projection with its immutable owner
    # version. A nonduplicate row can still contain an incorrect correction.
    for transaction, version in db.session.query(PlayerTransaction, PlayerTransactionVersion).outerjoin(
        PlayerTransactionVersion, and_(
            PlayerTransactionVersion.player_transaction_id == PlayerTransaction.id,
            PlayerTransactionVersion.version_number == PlayerTransaction.current_version_number,
        ),
    ).filter(PlayerTransaction.current_version_number > 0).yield_per(250):
        fingerprint = _transaction_fact_fingerprint({
            field: getattr(transaction, field) for field in _TRANSACTION_VERSION_FACT_FIELDS
        })
        if version is None or fingerprint != version.fact_fingerprint:
            transaction_conflicts.append(transaction.id)
    contention = db.session.query(SyncJobAttempt.sync_job_id, func.count()).join(
        SyncJob, SyncJob.id == SyncJobAttempt.sync_job_id,
    ).filter(
        SyncJobAttempt.claimed_at >= now - timedelta(hours=1),
        SyncJobAttempt.error_message.contains('semantic fence busy'),
        SyncJob.status.in_(('pending', 'running', 'retry_wait', 'dead')),
    ).group_by(SyncJobAttempt.sync_job_id).all()
    return {
        'governed_projection_conflicts': len(mismatched_pitchers),
        'governed_projection_conflict_details': [
            {'pitcher_id': pitcher_id, 'team_id': team_id} for pitcher_id, team_id in mismatched_pitchers
        ],
        'current_provisional_for_final': current_live,
        'final_projection_conflicts': len(mismatched_final),
        'extra_final_contributions': len(extra_final),
        'conflicting_mlb_memberships': len(conflicting_clubs),
        'transaction_projection_conflicts': len(transaction_conflicts),
        'transaction_projection_conflict_ids': transaction_conflicts,
        'final_projection_conflict_details': [
            {'game_pk': game_pk, 'pitcher_id': pitcher_id} for game_pk, pitcher_id in mismatched_final
        ],
        'recent_write_outcomes': recent,
        'recent_suppressions': {outcome: count for outcome, count in recent.items() if outcome != 'applied'},
        'lock_contention_attempts': sum(count for _, count in contention),
        'repeated_lock_contention_jobs': sum(count >= 3 for _, count in contention),
        'unresolved_ownership_conflicts': (
            len(mismatched_pitchers) + current_live + len(mismatched_final)
            + len(extra_final) + len(conflicting_clubs) + len(transaction_conflicts)
        ),
    }
