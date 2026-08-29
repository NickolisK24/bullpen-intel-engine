"""Compact, same-publication read model for manual bullpen comparison.

The carrier projects already-authored Team Board facts from one trusted
Dashboard snapshot.  It performs no ranking, prediction, or baseball
calculation and deliberately does not serialize two full Team Board payloads.
"""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Mapping

from services import public_serving_authority as authority
from services.bullpen_board import (
    REST_STATUS_METHOD_VERSION,
    REST_STATUS_PUBLIC_CONTRACT_VERSION,
    _board_cards,
    _roster_counts_withheld,
    group_cards,
    is_valid_rest_status_carrier,
)
from services.public_team_relief_work import (
    WORKLOAD_WINDOWS_METHOD_VERSION,
    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
)
from services.rotation_support_pressure import (
    PUBLIC_CONTRACT_VERSION as ROTATION_PUBLIC_CONTRACT_VERSION,
    VERSION as ROTATION_METHOD_VERSION,
)
from services.team_board_delta_substrate import (
    try_build_rotation_impact_capture,
    try_build_workload_window_capture,
)


CAPABILITY = 'current_bullpen_comparison_v1'
CONTRACT = 'current_bullpen_comparison_carrier_v1'
STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_WITHHELD = 'withheld'
REASON_TEAM_MISSING = 'published_team_missing'
REASON_NOT_COMPARABLE = 'comparison_authority_mismatch'
REASON_DOMAIN_UNAVAILABLE = 'comparison_domain_unavailable'

logger = logging.getLogger(__name__)

DOMAIN_MESSAGES = {
    'team_state': 'Team State comparison is unavailable for this publication.',
    'rest': 'Rest comparison is unavailable for this publication.',
    'workload': 'Recent workload comparison is unavailable for this publication.',
    'rotation': 'Rotation transfer comparison is unavailable for this publication.',
    'availability': 'Availability comparison is unavailable for this publication.',
}


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _team_destination(team):
    abbreviation = str(_mapping(team).get('team_abbreviation') or '').strip().upper()
    return f'/bullpen?view=board&team={abbreviation}&source=comparison' if abbreviation else None


def _team_identity(team_id, team_package):
    team = deepcopy(dict(_mapping(_mapping(team_package).get('team'))))
    if team.get('team_id') not in (None, team_id):
        return None
    team['team_id'] = team_id
    return {
        **team,
        'team_board_href': _team_destination(team),
    }


def _withheld_domain(domain, reason_code=REASON_DOMAIN_UNAVAILABLE):
    return {
        'status': STATUS_WITHHELD,
        'reason_code': reason_code,
        'message': DOMAIN_MESSAGES[domain],
        'limitations': [],
        'team_a': None,
        'team_b': None,
    }


def _aligned_domain(
    domain, side_a, side_b, *, stamp_a, stamp_b, partial=False, limitations=None
):
    if side_a is None or side_b is None:
        return _withheld_domain(domain)
    if stamp_a != stamp_b or any(value in (None, '') for value in stamp_a):
        return _withheld_domain(domain, REASON_NOT_COMPARABLE)
    return {
        'status': STATUS_PARTIAL if partial else STATUS_AVAILABLE,
        'reason_code': None,
        'message': None,
        'limitations': list(limitations or []),
        'team_a': side_a,
        'team_b': side_b,
    }


def _safe_project(domain, projector, *args, fallback, **kwargs):
    try:
        return projector(*args, **kwargs)
    except Exception:  # noqa: BLE001 - each optional domain fails locally
        logger.warning(
            'Current bullpen comparison withheld domain=%s after projection failure.',
            domain,
            exc_info=True,
        )
        return fallback


def _team_state(snapshot, team_id, overrides=None):
    value = (overrides or {}).get(team_id)
    if value is None:
        value = authority._published_team_state(snapshot, team_id)
    if not isinstance(value, Mapping) or value.get('available') is not True:
        return None, ()
    return deepcopy(dict(value)), (
        value.get('contract'),
        value.get('data_through'),
    )


def _rest(team_package):
    value = _mapping(_mapping(team_package).get('rest_status'))
    stamp = _mapping(_mapping(team_package).get('rest_status_authority'))
    if (
        not is_valid_rest_status_carrier(dict(value))
        or value.get('available') is not True
        or stamp.get('method_version') != REST_STATUS_METHOD_VERSION
        or stamp.get('public_contract_version') != REST_STATUS_PUBLIC_CONTRACT_VERSION
        or stamp.get('team_board_package_contract') != authority.TEAM_BOARD_PACKAGE_CONTRACT
    ):
        return None, ()
    return {
        'rested_options': value.get('rested_arm_count'),
        'worked_yesterday': value.get('worked_yesterday_count'),
        'back_to_back': value.get('back_to_back_count'),
    }, (
        stamp.get('method_version'),
        stamp.get('public_contract_version'),
        stamp.get('availability_reference_date'),
        stamp.get('reference_date_policy'),
        repr(stamp.get('population_basis')),
    )


def _workload(snapshot, team_id):
    capture = try_build_workload_window_capture(snapshot=snapshot, team_id=team_id)
    if not isinstance(capture, Mapping):
        return None, ()
    window = _mapping(_mapping(capture.get('windows')).get('window_7'))
    if (
        capture.get('method_version') != WORKLOAD_WINDOWS_METHOD_VERSION
        or capture.get('public_contract_version') != WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
        or not window
    ):
        return None, ()
    return {
        'window_days': 7,
        'relief_appearances': window.get('relief_appearances'),
        'contributing_relievers': window.get('pitchers_in_relief'),
        'pitches': window.get('pitches_total'),
    }, (
        capture.get('method_version'),
        capture.get('public_contract_version'),
        capture.get('represented_date'),
        capture.get('reference_date_policy'),
        repr(capture.get('population_basis')),
        window.get('through'),
    )


def _rotation(snapshot, team_id):
    capture = try_build_rotation_impact_capture(snapshot=snapshot, team_id=team_id)
    if not isinstance(capture, Mapping):
        return None, (), False
    value = _mapping(capture.get('value'))
    if (
        capture.get('method_version') != ROTATION_METHOD_VERSION
        or capture.get('public_contract_version') != ROTATION_PUBLIC_CONTRACT_VERSION
        or not value
    ):
        return None, (), False
    games_analyzed = value.get('games_analyzed')
    if type(games_analyzed) is not int or games_analyzed <= 0:
        return None, (), False
    short_starts = value.get('short_start_count')
    bullpen_innings = value.get('bullpen_innings_required')
    if type(short_starts) is not int or short_starts < 0:
        short_starts = None
    if (
        isinstance(bullpen_innings, bool)
        or not isinstance(bullpen_innings, (int, float))
        or bullpen_innings < 0
    ):
        bullpen_innings = None
    if short_starts is None and bullpen_innings is None:
        return None, (), False
    limitations = list(value.get('limitations') or [])
    partial = value.get('status') == 'limited_read' or bool(limitations)
    return {
        'window_days': value.get('window_days'),
        'short_starts': short_starts,
        'bullpen_innings': bullpen_innings,
        'limitations': limitations,
    }, (
        capture.get('method_version'),
        capture.get('public_contract_version'),
        capture.get('represented_date'),
        capture.get('reference_date_policy'),
        repr(capture.get('population_basis')),
        value.get('reference_date'),
        value.get('window_days'),
    ), partial


def _availability(team_package, *, package_date, reference_date):
    package = _mapping(team_package)
    if _roster_counts_withheld(package.get('roster_authority')):
        return None, ()
    records = authority._records_for_view(package, False)
    groups = group_cards(_board_cards(records))
    counts = {group.get('status'): group.get('count') for group in groups}
    required = ('Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable')
    if any(type(counts.get(key)) is not int or counts[key] < 0 for key in required):
        return None, ()
    # "Unavailable" is the existing public fold of internal Avoid and strict
    # Unavailable.  It is authored here once; the browser never reconstructs it.
    return {
        'available': counts['Available'],
        'on_watch': counts['Monitor'],
        'limited': counts['Limited'],
        'unavailable': counts['Avoid'] + counts['Unavailable'],
    }, (
        authority.TEAM_BOARD_PACKAGE_CONTRACT,
        package_date,
        reference_date,
    )


def build_current_bullpen_comparison(
    snapshot, team_a_id, team_b_id, *, team_state_overrides=None,
):
    """Project one compact aligned comparison from one selected snapshot."""
    package = _mapping(_mapping(getattr(snapshot, 'payload', None)).get(
        authority.TEAM_BOARD_PACKAGE_KEY
    ))
    by_team = _mapping(package.get('by_team_id'))
    package_date = package.get('data_through')
    reference_date = package.get('availability_reference_date')
    if (
        package.get('contract') != authority.TEAM_BOARD_PACKAGE_CONTRACT
        or package_date != _iso(getattr(snapshot, 'data_through', None))
    ):
        return None, REASON_DOMAIN_UNAVAILABLE

    package_a = by_team.get(str(team_a_id))
    package_b = by_team.get(str(team_b_id))
    identity_a = _team_identity(team_a_id, package_a)
    identity_b = _team_identity(team_b_id, package_b)
    if identity_a is None or identity_b is None:
        return None, REASON_TEAM_MISSING

    state_a, state_stamp_a = _safe_project(
        'team_state', _team_state, snapshot, team_a_id,
        overrides=team_state_overrides, fallback=(None, ())
    )
    state_b, state_stamp_b = _safe_project(
        'team_state', _team_state, snapshot, team_b_id,
        overrides=team_state_overrides, fallback=(None, ())
    )
    rest_a, rest_stamp_a = _safe_project(
        'rest', _rest, package_a, fallback=(None, ())
    )
    rest_b, rest_stamp_b = _safe_project(
        'rest', _rest, package_b, fallback=(None, ())
    )
    workload_a, workload_stamp_a = _safe_project(
        'workload', _workload, snapshot, team_a_id, fallback=(None, ())
    )
    workload_b, workload_stamp_b = _safe_project(
        'workload', _workload, snapshot, team_b_id, fallback=(None, ())
    )
    rotation_a, rotation_stamp_a, rotation_partial_a = _safe_project(
        'rotation', _rotation, snapshot, team_a_id, fallback=(None, (), False)
    )
    rotation_b, rotation_stamp_b, rotation_partial_b = _safe_project(
        'rotation', _rotation, snapshot, team_b_id, fallback=(None, (), False)
    )
    availability_a, availability_stamp_a = _safe_project(
        'availability', _availability, package_a, fallback=(None, ()),
        package_date=package_date, reference_date=reference_date,
    )
    availability_b, availability_stamp_b = _safe_project(
        'availability', _availability, package_b, fallback=(None, ()),
        package_date=package_date, reference_date=reference_date,
    )

    domains = {
        'team_state': _aligned_domain(
            'team_state', state_a, state_b,
            stamp_a=state_stamp_a, stamp_b=state_stamp_b,
        ),
        'rest': _aligned_domain(
            'rest', rest_a, rest_b,
            stamp_a=rest_stamp_a, stamp_b=rest_stamp_b,
        ),
        'workload': _aligned_domain(
            'workload', workload_a, workload_b,
            stamp_a=workload_stamp_a, stamp_b=workload_stamp_b,
        ),
        'rotation': _aligned_domain(
            'rotation', rotation_a, rotation_b,
            stamp_a=rotation_stamp_a, stamp_b=rotation_stamp_b,
            partial=rotation_partial_a or rotation_partial_b,
            limitations=list(dict.fromkeys(
                list((rotation_a or {}).get('limitations') or [])
                + list((rotation_b or {}).get('limitations') or [])
            )),
        ),
        'availability': _aligned_domain(
            'availability', availability_a, availability_b,
            stamp_a=availability_stamp_a, stamp_b=availability_stamp_b,
        ),
    }
    unavailable = [name for name, domain in domains.items() if domain['status'] == STATUS_WITHHELD]
    partial = [name for name, domain in domains.items() if domain['status'] == STATUS_PARTIAL]
    limitations = [domains[name]['message'] for name in unavailable]
    for name in partial:
        for limitation in domains[name].get('limitations') or []:
            if limitation not in limitations:
                limitations.append(limitation)
    return {
        'capability': CAPABILITY,
        'contract': CONTRACT,
        'status': STATUS_PARTIAL if unavailable or partial else STATUS_AVAILABLE,
        'reason_code': None,
        'represented_date': package_date,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'teams': {'team_a': identity_a, 'team_b': identity_b},
        'domains': domains,
        'limitations': limitations,
    }, None
