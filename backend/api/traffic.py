"""Anonymous-safe ingestion for canonical public page-view measurement."""

from flask import Blueprint, current_app, request
from sqlalchemy.exc import IntegrityError

from models.traffic_page_view import TrafficPageView
from services.traffic_measurement import record_page_view
from utils.db import db
from utils.identity import resolve_current_user


traffic_bp = Blueprint('traffic', __name__)


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
