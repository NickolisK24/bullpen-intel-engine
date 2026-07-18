"""Authenticated private slate briefing and posting receipt routes."""

from flask import Blueprint, g, jsonify, request

from api.private_posts import user_can_access_private_posting_board
from services.slate_briefing import (
    PostingValidationError,
    build_slate_briefing,
    mark_candidate_posted,
    recent_posting_history,
)
from utils.identity import require_authenticated_user


slate_briefing_bp = Blueprint('slate_briefing', __name__)


def _allowed():
    return user_can_access_private_posting_board(g.current_user)


@slate_briefing_bp.route('/slate-briefing', methods=['GET'])
@require_authenticated_user
def get_slate_briefing():
    if not _allowed():
        return jsonify({'error': 'posting_board_forbidden'}), 403
    try:
        return jsonify(build_slate_briefing(request.args.get('date', 'today')))
    except PostingValidationError as exc:
        return jsonify({'error': exc.code}), exc.status


@slate_briefing_bp.route('/slate-briefing/mark-posted', methods=['POST'])
@require_authenticated_user
def post_slate_briefing_receipt():
    if not _allowed():
        return jsonify({'error': 'posting_board_forbidden'}), 403
    try:
        receipt = mark_candidate_posted(request.get_json(silent=True) or {})
        return jsonify({'posting_record': receipt.to_dict()}), 201
    except PostingValidationError as exc:
        return jsonify({'error': exc.code}), exc.status


@slate_briefing_bp.route('/slate-briefing/history', methods=['GET'])
@require_authenticated_user
def get_slate_briefing_history():
    if not _allowed():
        return jsonify({'error': 'posting_board_forbidden'}), 403
    try:
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return jsonify({'error': 'invalid_limit'}), 400
    return jsonify({'posting_records': recent_posting_history(limit)})
