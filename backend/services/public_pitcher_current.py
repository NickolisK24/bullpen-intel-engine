"""Canonical public pitcher-current read model.

The builder is shared by the legacy request path and SP-10 candidate artifact
generation.  It reads the governed workload, availability, roster, role, and
deployment authorities once and returns a JSON-safe value that SP-10 can freeze.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.availability_reference_date import parse_reference_date, product_current_date
from services.bullpen_board import last_workload_appearance_from_logs
from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.pitcher_role_authority import author_role_read_labels, role_logs_by_pitcher
from services.public_fatigue_view import public_availability, public_workload_facts
from services.public_recent_work import build_public_recent_work_payload
from services.public_team_relief_work import (
    DEPLOYMENT_PROFILE_METHOD_VERSION,
    DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
    DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
    DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
    author_deployment_profile,
)
from services.roster_status import apply_roster_status_to_availability, classify_roster_status
from services.roster_status_audit import with_recent_inactive_roster_audit
from utils.db import db


CONTRACT_VERSION = 'pitcher-current-publication-v1'
DEPLOYMENT_CONTRACT = 'pitcher_observed_deployment_context_v1'


def _reference_date(freshness):
    return (
        parse_reference_date((freshness or {}).get('availability_reference_date'))
        or product_current_date()
    )


def _workload_signal(pitcher_id, score, reference_date):
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).filter(
        GameLog.pitcher_id == pitcher_id,
    ).scalar()
    logs = GameLog.query.filter(
        GameLog.pitcher_id == pitcher_id,
        GameLog.game_date >= reference_date - timedelta(days=4),
        GameLog.game_date <= reference_date,
    ).order_by(desc(GameLog.game_date)).all()
    return classify_availability(
        score=score,
        game_logs=logs,
        reference_date=reference_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )


def _deployment_context(pitcher, freshness):
    data_through = (freshness or {}).get('data_through')
    if pitcher.team_id is None:
        return {
            'contract': DEPLOYMENT_CONTRACT,
            'status': 'withheld',
            'reason_code': 'represented_team_unavailable',
            'data_through': data_through,
            'window_days': None,
            'source_contract': None,
            'method_version': DEPLOYMENT_PROFILE_METHOD_VERSION,
            'public_contract_version': DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
            'reference_date_policy': DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
            'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
            'profile': None,
            'limitations': [],
        }
    deployment = author_deployment_profile(pitcher.team_id, data_through=data_through)
    profile = next(
        (row for row in deployment.get('profiles') or () if row.get('pitcher_id') == pitcher.id),
        None,
    )
    return {
        'contract': DEPLOYMENT_CONTRACT,
        'status': deployment.get('status'),
        'reason_code': deployment.get('reason_code'),
        'data_through': deployment.get('data_through'),
        'window_days': deployment.get('window_days'),
        'source_contract': deployment.get('contract'),
        'method_version': DEPLOYMENT_PROFILE_METHOD_VERSION,
        'public_contract_version': DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
        'reference_date_policy': DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
        'population_basis': deployment.get('population_basis'),
        'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
        'profile': profile,
        'limitations': (
            list(profile.get('limitations') or ())
            if profile is not None else list(deployment.get('limitations') or ())
        ),
    }


def _unavailable_deployment(freshness):
    return {
        'contract': DEPLOYMENT_CONTRACT,
        'status': 'unavailable',
        'reason_code': 'deployment_context_unavailable',
        'data_through': (freshness or {}).get('data_through'),
        'window_days': None,
        'source_contract': None,
        'method_version': DEPLOYMENT_PROFILE_METHOD_VERSION,
        'public_contract_version': DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
        'reference_date_policy': DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
        'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
        'profile': None,
        'limitations': [],
    }


def build_public_pitcher_current_payload(
    pitcher_id, *, freshness, score_cutoff=None,
):
    """Build the exact public pitcher-detail payload for immutable capture."""
    pitcher = db.session.get(Pitcher, int(pitcher_id))
    if pitcher is None:
        raise LookupError(f'pitcher_not_found:{pitcher_id}')

    latest_query = FatigueScore.query.filter_by(pitcher_id=pitcher.id)
    if score_cutoff is not None:
        latest_query = latest_query.filter(FatigueScore.calculated_at <= score_cutoff)
    latest = latest_query.order_by(desc(FatigueScore.calculated_at)).first()
    reference_date = _reference_date(freshness)
    last_game_date = db.session.query(db.func.max(GameLog.game_date)).filter(
        GameLog.pitcher_id == pitcher.id,
    ).scalar()
    anchor = last_game_date or reference_date
    logs = GameLog.query.filter(
        GameLog.pitcher_id == pitcher.id,
        GameLog.game_date >= anchor - timedelta(days=14),
    ).order_by(desc(GameLog.game_date)).all()
    history_query = FatigueScore.query.filter(
        FatigueScore.pitcher_id == pitcher.id,
        FatigueScore.calculated_at >= anchor - timedelta(days=30),
    ).order_by(FatigueScore.calculated_at)
    if score_cutoff is not None:
        history_query = history_query.filter(FatigueScore.calculated_at <= score_cutoff)

    signal = _workload_signal(pitcher.id, latest, reference_date)
    roster_status = with_recent_inactive_roster_audit(
        classify_roster_status(pitcher), logs, reference_date,
    )
    availability = apply_roster_status_to_availability(signal, roster_status)
    contexts = eligible_bullpen_pitcher_contexts(
        [pitcher], include_stale=True, include_inactive_context=True,
        include_unknown_roster=True, reference_date=reference_date,
    )
    eligibility = contexts[0].get('eligibility') if contexts else None
    role_logs = role_logs_by_pitcher([pitcher.id], reference_date=reference_date)
    role, labels, role_read = author_role_read_labels({
        'pitcher': pitcher,
        'availability': availability,
        'eligibility': eligibility,
        'roster_status': roster_status,
    }, role_logs, reference_date)

    recent_status = {'status': 'available'}
    try:
        recent_work = build_public_recent_work_payload(
            pitcher.id, pitcher=pitcher, freshness=freshness,
        )
    except Exception:
        recent_work = None
        recent_status = {'status': 'unavailable'}
    try:
        deployment = _deployment_context(pitcher, freshness)
    except Exception:
        deployment = _unavailable_deployment(freshness)

    last_appearance = last_workload_appearance_from_logs(logs)
    return {
        'contract_version': CONTRACT_VERSION,
        'pitcher': pitcher.to_dict(),
        'current_fatigue': public_workload_facts(latest),
        'availability': public_availability(availability),
        'workload_signal': public_availability(signal),
        'roster_status': roster_status,
        'freshness': dict(freshness or {}),
        'last_appearance': last_appearance,
        'last_workload_appearance': last_appearance,
        'role': role,
        'pitcher_labels': labels,
        'public_role_read': role_read,
        'recent_work': recent_work,
        'recent_work_status': recent_status,
        'deployment_context': deployment,
        'recent_logs': [row.to_dict() for row in logs],
        'fatigue_trend': [public_workload_facts(row) for row in history_query.all()],
    }


__all__ = ['CONTRACT_VERSION', 'build_public_pitcher_current_payload']
