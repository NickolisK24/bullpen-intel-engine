"""Privacy-bounded ingestion for completed evidence sharing actions."""

from __future__ import annotations

from datetime import date

from models.traffic_share_action import TrafficShareAction
from services.traffic_measurement import (
    CANONICAL_SITE_HOST,
    classify_device,
    is_known_bot,
    normalize_evidence_target,
    normalize_team_ref,
    normalize_uuid,
    parse_internal_emails,
    register_internal_visitor,
)
from utils.db import db


SCHEMA_VERSION = 1
SURFACE_ALLOWLIST = frozenset({'bullpen_board', 'compare_bullpens', 'stories'})
CARD_TYPE_ALLOWLIST = frozenset({'team', 'comparison', 'link_only'})
ACTION_ALLOWLIST = frozenset({
    'native_card_share', 'native_link_share', 'copy_link', 'download_card',
})
TEAM_EVIDENCE_TARGETS = frozenset({
    'team_read', 'team_relief_work', 'pitcher_lanes', 'pitcher_detail',
})
COMPARISON_EVIDENCE_TARGETS = frozenset({'comparison_read', 'comparison_evidence'})
PAYLOAD_KEYS = frozenset({
    'event_id', 'visitor_id', 'session_id', 'surface', 'card_type', 'action',
    'team_ref', 'team_a_ref', 'team_b_ref', 'evidence_target', 'data_through',
    'site_host',
})


def _bounded(value, allowlist):
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in allowlist else None


def normalize_data_through(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def normalize_share_action(payload, *, user_agent=''):
    if not isinstance(payload, dict) or set(payload) - PAYLOAD_KEYS:
        return None

    event_id = normalize_uuid(payload.get('event_id'))
    visitor_id = normalize_uuid(payload.get('visitor_id'))
    session_id = normalize_uuid(payload.get('session_id'))
    surface = _bounded(payload.get('surface'), SURFACE_ALLOWLIST)
    card_type = _bounded(payload.get('card_type'), CARD_TYPE_ALLOWLIST)
    action = _bounded(payload.get('action'), ACTION_ALLOWLIST)
    site_host = str(payload.get('site_host') or '').strip().lower()
    if not all((event_id, visitor_id, session_id, surface, card_type, action)):
        return None
    if site_host != CANONICAL_SITE_HOST:
        return None

    team_ref = normalize_team_ref(payload.get('team_ref'))
    team_a_ref = normalize_team_ref(payload.get('team_a_ref'))
    team_b_ref = normalize_team_ref(payload.get('team_b_ref'))
    for supplied, normalized in (
        (payload.get('team_ref'), team_ref),
        (payload.get('team_a_ref'), team_a_ref),
        (payload.get('team_b_ref'), team_b_ref),
    ):
        if supplied not in (None, '') and normalized is None:
            return None

    supplied_evidence = payload.get('evidence_target')
    evidence_target = normalize_evidence_target(supplied_evidence)
    if supplied_evidence not in (None, '') and evidence_target is None:
        return None
    supplied_date = payload.get('data_through')
    data_through = normalize_data_through(supplied_date)
    if supplied_date not in (None, '') and data_through is None:
        return None

    if card_type == 'team':
        if surface != 'bullpen_board' or not team_ref or team_a_ref or team_b_ref:
            return None
        if evidence_target not in TEAM_EVIDENCE_TARGETS | {None}:
            return None
    elif card_type == 'comparison':
        if surface != 'compare_bullpens' or team_ref or not team_a_ref or not team_b_ref:
            return None
        if team_a_ref == team_b_ref:
            return None
        if evidence_target not in COMPARISON_EVIDENCE_TARGETS | {None}:
            return None
    else:
        if surface != 'stories' or not team_ref or team_a_ref or team_b_ref:
            return None
        if evidence_target not in TEAM_EVIDENCE_TARGETS | {None}:
            return None

    if action in {'native_card_share', 'download_card'} and card_type == 'link_only':
        return None

    return {
        'event_id': event_id,
        'visitor_id': visitor_id,
        'session_id': session_id,
        'surface': surface,
        'card_type': card_type,
        'action': action,
        'team_ref': team_ref,
        'team_a_ref': team_a_ref,
        'team_b_ref': team_b_ref,
        'evidence_target': evidence_target,
        'data_through': data_through,
        'site_host': CANONICAL_SITE_HOST,
        'device_class': classify_device(user_agent),
        'is_bot': is_known_bot(user_agent),
        'schema_version': SCHEMA_VERSION,
    }


def record_share_action(payload, *, user_agent='', current_user=None, internal_emails=''):
    """Validate and stage one completed action; the API owns the commit."""
    normalized = normalize_share_action(payload, user_agent=user_agent)
    if normalized is None:
        return 'rejected'

    register_internal_visitor(
        normalized['visitor_id'],
        current_user,
        parse_internal_emails(internal_emails),
    )
    if TrafficShareAction.query.filter_by(event_id=normalized['event_id']).first() is not None:
        return 'duplicate'
    db.session.add(TrafficShareAction(**normalized))
    return 'inserted'
