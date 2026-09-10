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


SCHEMA_VERSION = 2
SURFACE_ALLOWLIST = frozenset({'bullpen_board', 'compare_bullpens', 'stories'})
CARD_TYPE_ALLOWLIST = frozenset({'team', 'comparison', 'link_only'})
ACTION_ALLOWLIST = frozenset({
    'native_card_share', 'native_link_share', 'copy_link', 'download_card',
})
TEAM_EVIDENCE_TARGETS = frozenset({
    'team_read', 'team_relief_work', 'pitcher_lanes', 'pitcher_detail',
})
COMPARISON_EVIDENCE_TARGETS = frozenset({'comparison_read', 'comparison_evidence'})
CARD_VERSION_ALLOWLIST = frozenset({'team_story_v2', 'comparison_story_v2'})
TEAM_STORY_ANGLES = frozenset({
    'availability_constraint', 'repeated_usage', 'availability_watch',
    'workload_concentration', 'recent_work_volume', 'starter_support',
    'availability_depth', 'roster_context',
})
COMPARISON_STORY_ANGLES = frozenset({
    'comparison_availability', 'comparison_on_watch', 'comparison_limited',
    'comparison_unavailable', 'comparison_no_separation',
})
CARD_VERSION_FOR_CARD_TYPE = {'team': 'team_story_v2', 'comparison': 'comparison_story_v2'}
STORY_ANGLES_FOR_CARD_VERSION = {
    'team_story_v2': TEAM_STORY_ANGLES,
    'comparison_story_v2': COMPARISON_STORY_ANGLES,
}
PAYLOAD_KEYS = frozenset({
    'event_id', 'visitor_id', 'session_id', 'surface', 'card_type', 'action',
    'team_ref', 'team_a_ref', 'team_b_ref', 'evidence_target', 'data_through',
    'site_host', 'card_version', 'story_angle',
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

    card_version, story_angle = _normalize_story_context(payload, card_type)
    if card_version is False:
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
        'card_version': card_version,
        'story_angle': story_angle,
        'data_through': data_through,
        'site_host': CANONICAL_SITE_HOST,
        'device_class': classify_device(user_agent),
        'is_bot': is_known_bot(user_agent),
        'schema_version': SCHEMA_VERSION,
    }


def _normalize_story_context(payload, card_type):
    """Validate the bounded (card_version, story_angle) pair.

    Returns ``(card_version, story_angle)`` with both values or both ``None``.
    Returns ``(False, False)`` to signal the whole payload must be rejected.
    """
    supplied_version = payload.get('card_version')
    supplied_angle = payload.get('story_angle')
    has_version = supplied_version not in (None, '')
    has_angle = supplied_angle not in (None, '')

    # The fields are paired: both present or both absent.
    if has_version != has_angle:
        return False, False
    if not has_version:
        return None, None

    # Story metadata never belongs to a link-only action.
    if card_type == 'link_only':
        return False, False

    card_version = _bounded(supplied_version, CARD_VERSION_ALLOWLIST)
    if card_version is None or CARD_VERSION_FOR_CARD_TYPE.get(card_type) != card_version:
        return False, False

    story_angle = _bounded(supplied_angle, STORY_ANGLES_FOR_CARD_VERSION[card_version])
    if story_angle is None:
        return False, False

    return card_version, story_angle


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
