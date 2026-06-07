from flask import Blueprint, jsonify, request

from services.pitcher_search import (
    DEFAULT_SEARCH_LIMIT,
    search_pitchers_by_name,
)


pitchers_bp = Blueprint('pitchers', __name__)


@pitchers_bp.route('/search', methods=['GET'])
def search_pitchers():
    payload = search_pitchers_by_name(
        request.args.get('q', ''),
        limit=request.args.get('limit', DEFAULT_SEARCH_LIMIT, type=int),
    )
    return jsonify(payload)
