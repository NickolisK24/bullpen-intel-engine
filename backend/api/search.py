from flask import Blueprint, jsonify, request

from api.query_params import parse_positive_int_param, query_param_error_response
from services.discovery_search import (
    DEFAULT_GROUP_LIMIT,
    MAX_GROUP_LIMIT,
    search_discovery,
)


search_bp = Blueprint('search', __name__)


@search_bp.route('', methods=['GET'])
def search_entities():
    limit, error = parse_positive_int_param(
        request.args,
        'limit',
        default=DEFAULT_GROUP_LIMIT,
        maximum=MAX_GROUP_LIMIT,
        clamp_max=True,
    )
    if error:
        return query_param_error_response(error)
    return jsonify(search_discovery(request.args.get('q', ''), limit=limit))
