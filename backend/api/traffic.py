"""Anonymous-safe ingestion for canonical public page-view measurement."""

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from models.traffic_page_view import TrafficPageView
from models.traffic_share_action import TrafficShareAction
from services.traffic_measurement import record_page_view
from services.traffic_measurement import parse_internal_emails
from services.traffic_share_actions import record_share_action
from services.traffic_reporting import build_traffic_summary
from utils.auth_tokens import normalize_email
from utils.db import db
from utils.identity import resolve_current_user


traffic_bp = Blueprint('traffic', __name__)


@traffic_bp.route('/internal/summary', methods=['GET'])
def internal_summary():
    user = resolve_current_user()
    if user is None:
        return jsonify({'error': 'authentication_required'}), 401

    allowed_emails = parse_internal_emails(
        current_app.config.get('TRAFFIC_INTERNAL_EMAILS', ''),
    )
    if normalize_email(getattr(user, 'email', None)) not in allowed_emails:
        return jsonify({'error': 'traffic_reporting_forbidden'}), 403

    range_key = request.args.get('range', '7d')
    try:
        return jsonify(build_traffic_summary(range_key))
    except ValueError:
        return jsonify({
            'error': 'invalid_range',
            'allowed_ranges': ['7d', '30d', '90d', 'all'],
        }), 400


@traffic_bp.route('/page-view', methods=['POST'])
def page_view():
    payload = None
    try:
        payload = request.get_json(silent=True)
        outcome = record_page_view(
            payload,
            user_agent=request.headers.get('User-Agent', ''),
            current_user=resolve_current_user(),
            internal_emails=current_app.config.get('TRAFFIC_INTERNAL_EMAILS', ''),
        )
        if outcome != 'rejected':
            db.session.commit()
    except IntegrityError:
        db.session.rollback()
        view_id = payload.get('view_id') if isinstance(payload, dict) else None
        try:
            if view_id and TrafficPageView.query.filter_by(view_id=view_id).first() is None:
                current_app.logger.exception('Traffic page-view persistence failed.')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Traffic page-view persistence failed.')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Traffic page-view persistence failed.')
    return '', 202


@traffic_bp.route('/share-action', methods=['POST'])
def share_action():
    payload = None
    try:
        payload = request.get_json(silent=True)
        outcome = record_share_action(
            payload,
            user_agent=request.headers.get('User-Agent', ''),
            current_user=resolve_current_user(),
            internal_emails=current_app.config.get('TRAFFIC_INTERNAL_EMAILS', ''),
        )
        if outcome != 'rejected':
            db.session.commit()
    except IntegrityError:
        db.session.rollback()
        event_id = payload.get('event_id') if isinstance(payload, dict) else None
        try:
            if event_id and TrafficShareAction.query.filter_by(event_id=event_id).first() is None:
                current_app.logger.exception('Traffic share-action persistence failed.')
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Traffic share-action persistence failed.')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Traffic share-action persistence failed.')
    return '', 202
