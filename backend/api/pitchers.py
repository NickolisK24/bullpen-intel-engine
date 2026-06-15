from flask import Blueprint, jsonify, request

from api.query_params import parse_positive_int_param, query_param_error_response
from services import sync_metadata
from services.availability_reference_date import (
    product_availability_reference_date_from_sync_status,
    product_current_date,
)
from services.pitcher_search import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    search_pitchers_by_name,
)


pitchers_bp = Blueprint('pitchers', __name__)


@pitchers_bp.route('/search', methods=['GET'])
def search_pitchers():
    limit, error = parse_positive_int_param(
        request.args,
        'limit',
        default=DEFAULT_SEARCH_LIMIT,
        maximum=MAX_SEARCH_LIMIT,
        clamp_max=True,
    )
    if error:
        return query_param_error_response(error)
    sync_status = _sync_status_payload()
    payload = search_pitchers_by_name(
        request.args.get('q', ''),
        limit=limit,
        reference_date=_availability_reference_date(sync_status),
    )
    return jsonify(payload)


def _sync_status_payload():
    try:
        return sync_metadata.build_sync_status_payload()
    except Exception:
        return {
            'status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'availability_reference_date': None,
            'freshness': {
                'availability_reference_date': None,
            },
            'data': {},
        }


def _availability_reference_date(sync_status):
    return (
        product_availability_reference_date_from_sync_status(sync_status)
        or product_current_date()
    )
