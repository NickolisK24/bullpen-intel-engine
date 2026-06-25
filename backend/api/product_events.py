"""Product behavior ingestion API (Phase D2A-2, extended D2A-3).

A single, owned, anonymous-safe seam for recording first-party product behavior
into the canonical Product Event log:

  • POST /api/product/today-loaded    (D2A-2) — a Today-view arrival.
  • POST /api/product/story-viewed     (D2A-3) — a story was presented to the user.
  • POST /api/product/story-interacted (D2A-7) — a story was explicitly interacted with.
  • POST /api/product/story-event      (V3-1)  — an owned story observation under an
                                        allowlisted event_name (V3-1: story_impression;
                                        V3-2: + story_team_board_opened).

Future product-behavior facts can be added here without new infrastructure.

This is OWNED telemetry (no third-party analytics). It records measurement only —
it never reads or changes product state, and it is deliberately minimal: the
smallest useful payload, no browser-analytics payloads (no mouse / scroll /
cursor / heatmaps, and no stored viewport geometry — viewport visibility is only
ever a client-side trigger, e.g. story_impression), and no PII.
"""

from flask import Blueprint, jsonify, request

from services.product_events import (
    normalize_anon_id,
    normalize_arrival_source,
    normalize_short_text,
    normalize_story_event_name,
    normalize_story_interaction,
    normalize_story_surface,
    record_story_event,
    record_story_interacted,
    record_story_viewed,
    record_today_loaded,
)
from utils.db import db
from utils.identity import resolve_current_user


product_bp = Blueprint('product', __name__)


def _coerce_team_id(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@product_bp.route('/today-loaded', methods=['POST'])
def today_loaded():
    """Record a Today-view arrival. Anonymous-safe; always returns 200.

    Associates the signed-in user when a valid bearer token is present; otherwise
    records an anonymous arrival (optionally carrying a client-supplied,
    pseudonymous anon_id that lets a later sign-in bridge the two). Recording is
    best-effort — a telemetry failure never surfaces as an error to the client.
    """
    data = request.get_json(silent=True) or {}
    user = resolve_current_user()  # None when anonymous; never raises
    record_today_loaded(
        user_id=getattr(user, 'id', None),
        anon_id=normalize_anon_id(data.get('anon_id')),
        team_id=_coerce_team_id(data.get('team_id')),
        source=normalize_arrival_source(data.get('source')),
    )
    db.session.commit()
    return jsonify({'ok': True}), 200


@product_bp.route('/story-viewed', methods=['POST'])
def story_viewed():
    """Record that a story was presented to the user. Anonymous-safe; always 200.

    A pure observation — it records WHICH story (story_id + the existing canonical
    story_type), for WHICH team, on WHICH surface, and to WHOM. It infers nothing
    about engagement, understanding, or completion. Associates the signed-in user
    when present; otherwise an anonymous (optionally anon_id-tagged) view.
    Best-effort — a telemetry failure never surfaces as an error to the client.
    """
    data = request.get_json(silent=True) or {}
    user = resolve_current_user()  # None when anonymous; never raises
    record_story_viewed(
        user_id=getattr(user, 'id', None),
        anon_id=normalize_anon_id(data.get('anon_id')),
        team_id=_coerce_team_id(data.get('team_id')),
        story_id=normalize_short_text(data.get('story_id')),
        story_type=normalize_short_text(data.get('story_type')),
        surface=normalize_story_surface(data.get('surface')),
    )
    db.session.commit()
    return jsonify({'ok': True}), 200


@product_bp.route('/story-interacted', methods=['POST'])
def story_interacted():
    """Record an explicit interaction with a rendered story. Anonymous-safe; 200.

    A pure observation of an existing UI action (selecting / opening / expanding a
    story). It records WHICH story, surface, interaction kind, and WHOM — and
    infers nothing about engagement, interest, completion, or understanding.
    Best-effort — a telemetry failure never surfaces as an error to the client.
    """
    data = request.get_json(silent=True) or {}
    user = resolve_current_user()  # None when anonymous; never raises
    record_story_interacted(
        user_id=getattr(user, 'id', None),
        anon_id=normalize_anon_id(data.get('anon_id')),
        team_id=_coerce_team_id(data.get('team_id')),
        story_id=normalize_short_text(data.get('story_id')),
        story_type=normalize_short_text(data.get('story_type')),
        surface=normalize_story_surface(data.get('surface')),
        interaction_type=normalize_story_interaction(data.get('interaction_type')),
    )
    db.session.commit()
    return jsonify({'ok': True}), 200


@product_bp.route('/story-event', methods=['POST'])
def story_event():
    """Record an owned story observation under an allowlisted event_name. Always 200.

    The single generic seam for V3 story observations. The client supplies an
    ``event_name`` (V3-1: ``story_impression``; V3-2: ``story_team_board_opened``)
    plus the canonical story descriptors. An unrecognized or missing event_name
    records nothing — the call is best-effort and fault-isolated, still returns
    200, and never fabricates an event. Associates the signed-in user when present;
    otherwise an anonymous (optionally anon_id-tagged) observation.
    ``story_impression`` means the card appeared on screen; ``story_team_board_opened``
    means the reader followed the story's primary CTA into the Team Board.
    """
    data = request.get_json(silent=True) or {}
    event_name = normalize_story_event_name(data.get('event_name'))
    if event_name is not None:
        user = resolve_current_user()  # None when anonymous; never raises
        record_story_event(
            event_name,
            user_id=getattr(user, 'id', None),
            anon_id=normalize_anon_id(data.get('anon_id')),
            team_id=_coerce_team_id(data.get('team_id')),
            story_id=normalize_short_text(data.get('story_id')),
            story_type=normalize_short_text(data.get('story_type')),
            surface=normalize_story_surface(data.get('surface')),
        )
        db.session.commit()
    return jsonify({'ok': True}), 200
