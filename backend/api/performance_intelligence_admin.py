"""Internal admin read for governed performance intelligence (M-001).

Internal only, read-only, one team and one represented baseball date at a time.
Reuses the existing ``require_admin_token`` authorization rather than building a
parallel administration system. It performs no write, no backfill, and no
generation.

This introduces no public route and no public payload. M-001 is internally
reviewable; it is not published. Every response repeats the three publication
gates as blocked and separates *metric readiness* — whether enough proved
evidence exists for the founder to look at a value — from *publication*, which
requires a governed gate that is explicitly open. Neither this route nor a
satisfied minimum sample opens one.

Errors fail closed with sanitized codes; no raw internal exception is exposed.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request

from utils.auth import require_admin_token


performance_intelligence_admin_bp = Blueprint('performance_intelligence_admin', __name__)

REVIEW_CONTEXT = 'internal_review_only'
REVIEW_NOTICE = (
    'Internal review only. This value is not published on any public surface, '
    'and every public publication gate remains blocked.'
)


def _parse_team_id(raw):
    try:
        team_id = int(raw)
    except (TypeError, ValueError):
        return None
    return team_id if team_id > 0 else None


def _parse_required_date(raw):
    if raw in (None, ''):
        return None, False
    try:
        return date.fromisoformat(str(raw)), True
    except (TypeError, ValueError):
        return None, False


def _parse_season(raw, represented_date):
    if raw in (None, ''):
        return represented_date.year, True
    try:
        season = int(raw)
    except (TypeError, ValueError):
        return None, False
    return (season, True) if 1876 <= season <= 2100 else (None, False)


@performance_intelligence_admin_bp.route('/active-bullpen-era', methods=['GET'])
@require_admin_token
def get_active_bullpen_era():
    """One team, one represented baseball date, complete structured read."""
    team_id = _parse_team_id(request.args.get('team_id'))
    if team_id is None:
        return jsonify({'error': 'invalid_team_id'}), 400

    represented_date, ok = _parse_required_date(request.args.get('represented_date'))
    if not ok:
        return jsonify({'error': 'invalid_represented_date'}), 400

    season, ok = _parse_season(request.args.get('season'), represented_date)
    if not ok:
        return jsonify({'error': 'invalid_season'}), 400

    # Imported lazily so app import never pulls the performance graph at load
    # time, matching the existing internal-admin pattern.
    from services import performance_metrics
    from services import performance_intelligence

    try:
        read = performance_intelligence.build_metric_read(
            performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA,
            team_id,
            season=season,
            reference_date=represented_date,
            through_date=represented_date,
        )
    except Exception:
        # Defense in depth: the service already fails closed, but never leak a
        # raw internal exception to the caller.
        return jsonify({'error': 'internal_error', 'context': REVIEW_CONTEXT}), 503

    return jsonify({
        'context': REVIEW_CONTEXT,
        'notice': REVIEW_NOTICE,
        'public': False,
        'read': read,
    }), 200
