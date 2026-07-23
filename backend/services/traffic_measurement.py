"""Privacy-bounded first-party measurement for canonical public page views."""

from __future__ import annotations

import ipaddress
import re
import uuid

from models.traffic_internal_visitor import TrafficInternalVisitor
from models.traffic_page_view import TrafficPageView
from utils.auth_tokens import normalize_email
from utils.db import db


CANONICAL_SITE_HOST = 'baseballos.app'
SCHEMA_VERSION = 2
INTERNAL_REGISTRATION_SOURCE = 'authenticated_email_allowlist'

PUBLIC_ROUTE_SURFACES = {
    '/': 'today',
    '/dashboard': 'dashboard',
    '/stories': 'stories',
    '/about': 'about',
    '/how-to-read': 'how_to_read',
    '/methodology': 'methodology',
    '/trust': 'data_trust',
    '/signin': 'sign_in',
    '/auth/verify': 'auth_verify',
}
BULLPEN_SURFACES = {
    'board': 'bullpen_board',
    'compare': 'compare_bullpens',
    'pitchers': 'all_pitchers',
}
SURFACE_ALLOWLIST = frozenset((*PUBLIC_ROUTE_SURFACES.values(), *BULLPEN_SURFACES.values()))

PAYLOAD_KEYS = frozenset({
    'view_id',
    'visitor_id',
    'session_id',
    'route',
    'surface',
    'view_mode',
    'team_ref',
    'team_a_ref',
    'team_b_ref',
    'pitcher_id',
    'entry_source',
    'evidence_target',
    'referrer_domain',
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_content',
    'site_host',
})

ENTRY_SOURCE_ALLOWLIST = frozenset({
    'today', 'dashboard', 'landscape', 'stories', 'comparison',
    'all_pitchers', 'pitcher_search', 'share', 'share_link', 'share_card',
    'since_yesterday',
})
EVIDENCE_TARGET_ALLOWLIST = frozenset({
    'team_read', 'team_relief_work', 'pitcher_lanes', 'pitcher_detail',
    'comparison_read', 'comparison_evidence',
})
BOARD_EVIDENCE_TARGETS = frozenset({
    'team_read', 'team_relief_work', 'pitcher_lanes', 'pitcher_detail',
})
COMPARE_EVIDENCE_TARGETS = frozenset({'comparison_read', 'comparison_evidence'})

_UTM_LIMITS = {
    'utm_source': 64,
    'utm_medium': 64,
    'utm_campaign': 128,
    'utm_content': 128,
}
_BOT_PATTERN = re.compile(
    r'bot|crawler|spider|slurp|bingpreview|facebookexternalhit|'
    r'linkedinbot|twitterbot|discordbot|whatsapp|headlesschrome|lighthouse',
    re.IGNORECASE,
)
_HOST_PATTERN = re.compile(
    r'^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*'
    r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$',
)
_TEAM_ABBREVIATION_PATTERN = re.compile(r'^[A-Z]{2,4}$')
_UTM_UNSAFE_PATTERN = re.compile(r'[^a-z0-9._~-]+')
_SENSITIVE_UTM_PATTERNS = (
    re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+', re.IGNORECASE),
    re.compile(r'[\r\n]'),
    re.compile(
        r'(?<![a-z0-9])(?:bearer|basic|authorization|token|secret|password|passwd|'
        r'api[\s_.-]*key|access[\s_.-]*token|refresh[\s_.-]*token|'
        r'id[\s_.-]*token|client[\s_.-]*secret)(?![a-z0-9])',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.'
        r'[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])',
    ),
    re.compile(r'(?<![a-z0-9])(?:sk|rk|pk)[-_][a-z0-9_-]{12,}(?![a-z0-9])', re.IGNORECASE),
    re.compile(r'(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----', re.IGNORECASE),
)


def parse_internal_emails(value):
    """Return the normalized configured email allowlist without persisting it."""
    emails = set()
    for raw in str(value or '').split(','):
        normalized = normalize_email(raw)
        if normalized:
            emails.add(normalized)
    return frozenset(emails)


def normalize_uuid(value):
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def normalize_route(value):
    if not isinstance(value, str):
        return None
    route = value.strip()
    if not route or len(route) > 256 or not route.startswith('/'):
        return None
    if '?' in route or '#' in route or '://' in route or '\\' in route:
        return None
    if route != '/':
        route = route.rstrip('/')
    if route == '/bullpen' or route in PUBLIC_ROUTE_SURFACES:
        return route
    return None


def normalize_team_ref(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if text.isdigit():
        number = int(text)
        return str(number) if number > 0 else None
    return text if _TEAM_ABBREVIATION_PATTERN.fullmatch(text) else None


def normalize_pitcher_id(value):
    if value is None or value == '' or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 and str(value).strip() == str(number) else None


def normalize_bounded_value(value, allowlist):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in allowlist else None


def normalize_entry_source(value):
    return normalize_bounded_value(value, ENTRY_SOURCE_ALLOWLIST)


def normalize_evidence_target(value):
    return normalize_bounded_value(value, EVIDENCE_TARGET_ALLOWLIST)


def normalize_utm(value, *, limit):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        return None
    if any(pattern.search(value) for pattern in _SENSITIVE_UTM_PATTERNS):
        return None
    normalized = _UTM_UNSAFE_PATTERN.sub('_', value.strip().lower())
    normalized = re.sub(r'_+', '_', normalized).strip('_.-~')
    return normalized[:limit] or None


def normalize_referrer_domain(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        return None
    hostname = value.strip().lower().rstrip('.')
    if not hostname or any(char in hostname for char in ('/', '\\', '@', ':')):
        return None
    try:
        ipaddress.ip_address(hostname)
        return None
    except ValueError:
        pass
    try:
        hostname = hostname.encode('idna').decode('ascii')
    except UnicodeError:
        return None
    return hostname if _HOST_PATTERN.fullmatch(hostname) else None


def is_known_bot(user_agent):
    return bool(_BOT_PATTERN.search(str(user_agent or '')))


def classify_device(user_agent):
    user_agent = str(user_agent or '').lower()
    if not user_agent:
        return 'unknown'
    if 'ipad' in user_agent or 'tablet' in user_agent or 'kindle' in user_agent:
        return 'tablet'
    if re.search(r'iphone|ipod|android.+mobile|windows phone|mobile', user_agent):
        return 'mobile'
    if re.search(r'windows nt|macintosh|x11|cros|linux', user_agent):
        return 'desktop'
    return 'unknown'


def normalize_page_view(payload, *, user_agent=''):
    if not isinstance(payload, dict) or set(payload) - PAYLOAD_KEYS:
        return None
    string_only_fields = (
        'view_id', 'visitor_id', 'session_id', 'route', 'surface', 'view_mode',
        'entry_source', 'evidence_target',
        'referrer_domain', 'utm_source', 'utm_medium', 'utm_campaign',
        'utm_content', 'site_host',
    )
    if any(
        payload.get(key) is not None and not isinstance(payload.get(key), str)
        for key in string_only_fields
    ):
        return None

    view_id = normalize_uuid(payload.get('view_id'))
    visitor_id = normalize_uuid(payload.get('visitor_id'))
    session_id = normalize_uuid(payload.get('session_id'))
    route = normalize_route(payload.get('route'))
    site_host = str(payload.get('site_host') or '').strip().lower()
    if not all((view_id, visitor_id, session_id, route)):
        return None
    if site_host != CANONICAL_SITE_HOST:
        return None

    supplied_surface = payload.get('surface')
    view_mode = payload.get('view_mode')
    team_ref = payload.get('team_ref')
    team_a_ref = payload.get('team_a_ref')
    team_b_ref = payload.get('team_b_ref')
    pitcher_id = payload.get('pitcher_id')
    entry_source = normalize_entry_source(payload.get('entry_source'))
    evidence_target = normalize_evidence_target(payload.get('evidence_target'))
    if payload.get('evidence_target') not in (None, '') and evidence_target is None:
        return None
    if route == '/bullpen':
        if not isinstance(view_mode, str) or view_mode not in BULLPEN_SURFACES:
            return None
        surface = BULLPEN_SURFACES[view_mode]
        normalized_team = normalize_team_ref(team_ref)
        normalized_team_a = normalize_team_ref(team_a_ref)
        normalized_team_b = normalize_team_ref(team_b_ref)
        normalized_pitcher = normalize_pitcher_id(pitcher_id)
        if view_mode == 'board':
            if any(value not in (None, '') for value in (team_a_ref, team_b_ref)):
                return None
            if team_ref not in (None, '') and normalized_team is None:
                return None
            if pitcher_id not in (None, '') and normalized_pitcher is None:
                return None
            if evidence_target not in BOARD_EVIDENCE_TARGETS | {None}:
                return None
            if evidence_target in {'team_read', 'team_relief_work', 'pitcher_lanes'} and not normalized_team:
                return None
            if evidence_target == 'pitcher_detail' and normalized_pitcher is None:
                return None
            normalized_team_a = None
            normalized_team_b = None
        elif view_mode == 'compare':
            if any(value not in (None, '') for value in (team_ref, pitcher_id)):
                return None
            if team_a_ref not in (None, '') and normalized_team_a is None:
                return None
            if team_b_ref not in (None, '') and normalized_team_b is None:
                return None
            if normalized_team_a and normalized_team_b and normalized_team_a == normalized_team_b:
                normalized_team_a = None
                normalized_team_b = None
            completed_pair = bool(normalized_team_a and normalized_team_b)
            if evidence_target not in COMPARE_EVIDENCE_TARGETS | {None}:
                return None
            if evidence_target and not completed_pair:
                return None
            normalized_team = None
            normalized_pitcher = None
        else:
            if any(value not in (None, '') for value in (team_a_ref, team_b_ref, pitcher_id)):
                return None
            if team_ref not in (None, '') and normalized_team is None:
                return None
            if evidence_target is not None:
                return None
            normalized_team_a = None
            normalized_team_b = None
            normalized_pitcher = None
    else:
        surface = PUBLIC_ROUTE_SURFACES[route]
        if any(value not in (None, '') for value in (
            view_mode, team_ref, team_a_ref, team_b_ref, pitcher_id,
            payload.get('entry_source'), payload.get('evidence_target'),
        )):
            return None
        view_mode = None
        normalized_team = None
        normalized_team_a = None
        normalized_team_b = None
        normalized_pitcher = None
        entry_source = None
        evidence_target = None

    if supplied_surface != surface or supplied_surface not in SURFACE_ALLOWLIST:
        return None

    return {
        'view_id': view_id,
        'visitor_id': visitor_id,
        'session_id': session_id,
        'route': route,
        'surface': surface,
        'view_mode': view_mode,
        'team_ref': normalized_team,
        'team_a_ref': normalized_team_a,
        'team_b_ref': normalized_team_b,
        'pitcher_id': normalized_pitcher,
        'entry_source': entry_source,
        'evidence_target': evidence_target,
        'referrer_domain': normalize_referrer_domain(payload.get('referrer_domain')),
        **{
            key: normalize_utm(payload.get(key), limit=limit)
            for key, limit in _UTM_LIMITS.items()
        },
        'site_host': CANONICAL_SITE_HOST,
        'device_class': classify_device(user_agent),
        'is_bot': is_known_bot(user_agent),
        'schema_version': SCHEMA_VERSION,
    }


def register_internal_visitor(visitor_id, user, configured_emails):
    if user is None or normalize_email(getattr(user, 'email', None)) not in configured_emails:
        return None
    existing = TrafficInternalVisitor.query.filter_by(visitor_id=visitor_id).first()
    if existing is not None:
        return existing
    internal = TrafficInternalVisitor(
        visitor_id=visitor_id,
        registered_by_user_id=getattr(user, 'id', None),
        registration_source=INTERNAL_REGISTRATION_SOURCE,
    )
    db.session.add(internal)
    return internal


def record_page_view(payload, *, user_agent='', current_user=None, internal_emails=''):
    """Validate and stage one idempotent page view; the API owns the commit."""
    normalized = normalize_page_view(payload, user_agent=user_agent)
    if normalized is None:
        return 'rejected'

    configured_emails = parse_internal_emails(internal_emails)
    register_internal_visitor(normalized['visitor_id'], current_user, configured_emails)

    if TrafficPageView.query.filter_by(view_id=normalized['view_id']).first() is not None:
        return 'duplicate'
    db.session.add(TrafficPageView(**normalized))
    return 'inserted'
