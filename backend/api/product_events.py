"""Product behavior ingestion API (Phase D2A-2).

A single, owned, anonymous-safe seam for recording first-party product behavior
into the canonical Product Event log. Today it accepts only the Today-view
arrival (today_loaded); future product-behavior facts can be added here without
new infrastructure.

This is OWNED telemetry (no third-party analytics). It records measurement only —
it never reads or changes product state, and it is deliberately minimal: the
smallest useful payload, no browser analytics (no mouse / scroll / viewport /
heatmaps), and no PII.
"""

from flask import Blueprint, jsonify, request

from services.product_events import (
    normalize_anon_id,
    normalize_arrival_source,
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
