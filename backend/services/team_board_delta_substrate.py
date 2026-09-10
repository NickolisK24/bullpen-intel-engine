"""Prospective, version-aware frozen inputs for future Team Board deltas.

This module does not author change events or reader-facing copy.  It freezes a
small comparison envelope next to each newly published Team State artifact and
later proves whether two such envelopes are semantically compatible. Optional
Arm Read and workload-window domains are copied only from values already frozen
in that publication cycle. Existing dashboard snapshots and Share Artifacts are
never modified or backfilled.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import logging
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping

from models.dashboard_snapshot import DashboardSnapshot
from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
from services.availability_snapshot import CURRENT_AVAILABILITY_MODE
from services.bullpen_board import (
    REST_STATUS_METHOD_VERSION,
    REST_STATUS_PUBLIC_CONTRACT_VERSION,
    is_valid_rest_status_carrier,
)
from services.pitcher_public_labels import (
    ARM_READ_METHOD_VERSION,
    ARM_READ_PUBLIC_CONTRACT_VERSION,
    READ_PUBLIC_LABELS,
    build_public_arm_read,
)
from services.public_team_relief_work import (
    DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
    DEPLOYMENT_PROFILE_COMPLETE,
    DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
    DEPLOYMENT_PROFILE_METHOD_VERSION,
    DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
    DEPLOYMENT_PROFILE_POPULATION_BASIS,
    DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
    DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
    DEPLOYMENT_PROFILE_WINDOW_DAYS,
    WORKLOAD_WINDOWS_CARRIER_CONTRACT,
    WORKLOAD_WINDOWS_COMPLETE,
    WORKLOAD_WINDOWS_METHOD_VERSION,
    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
    WINDOW_DAYS,
)
from services.public_serving_authority import (
    BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
    BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY,
    BULLPEN_MEMBERSHIP_METHOD_VERSION,
    BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY,
    BULLPEN_MEMBERSHIP_POPULATION_BASIS,
    BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION,
    BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY,
    REST_STATUS_MEMBERSHIP_AUTHORITY,
    REST_STATUS_POPULATION_AUTHORITY,
    REST_STATUS_POPULATION_BASIS,
    REST_STATUS_REFERENCE_DATE_POLICY,
    TEAM_BOARD_PACKAGE_CONTRACT,
)
from services.rotation_support_pressure import (
    CAPABILITY as ROTATION_IMPACT_CAPABILITY,
    DELTA_CARRIER_CONTRACT as ROTATION_IMPACT_CARRIER_CONTRACT,
    MEMBERSHIP_AUTHORITY as ROTATION_IMPACT_MEMBERSHIP_AUTHORITY,
    POPULATION_AUTHORITY as ROTATION_IMPACT_POPULATION_AUTHORITY,
    POPULATION_BASIS as ROTATION_IMPACT_POPULATION_BASIS,
    PUBLIC_CONTRACT_VERSION as ROTATION_IMPACT_PUBLIC_CONTRACT_VERSION,
    REFERENCE_DATE_POLICY as ROTATION_IMPACT_REFERENCE_DATE_POLICY,
    VERSION as ROTATION_IMPACT_METHOD_VERSION,
)
from services.roster_authority import VERSION as ROSTER_AUTHORITY_VERSION
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_CONTRACT
from services.team_state_payload import TEAM_STATE_V1_2
from team_operations import TEAM_STATE_METHOD_VERSION
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SNAPSHOT_TYPE = 'team_board_delta'
SNAPSHOT_SOURCE_PREFIX = 'tb_delta:team:'
SNAPSHOT_PAYLOAD_VERSION = 1
ENVELOPE_VERSION = 'team_board_delta_envelope_v1'
CAPABILITY = 'team_board_daily_delta_substrate'

COMPARABLE = 'comparable'
PREVIOUS_MISSING = 'previous_missing'
CURRENT_MISSING = 'current_missing'
METHOD_VERSION_MISSING = 'method_version_missing'
METHOD_VERSION_MISMATCH = 'method_version_mismatch'
POPULATION_BASIS_MISSING = 'population_basis_missing'
POPULATION_BASIS_MISMATCH = 'population_basis_mismatch'
CONTRACT_INCOMPATIBLE = 'contract_incompatible'
FRESHNESS_UNTRUSTED = 'freshness_untrusted'
REPRESENTED_DATE_INVALID = 'represented_date_invalid'
SOURCE_IDENTITY_MISSING = 'source_identity_missing'
TEAM_ID_MISMATCH = 'team_id_mismatch'
PITCHER_IDENTITY_MISMATCH = 'pitcher_identity_mismatch'
VALUE_MISSING = 'value_missing'
DOMAIN_NOT_READY = 'domain_not_ready'
DOMAIN_NOT_INCLUDED = 'domain_not_in_substrate'

READINESS_COMPARABLE_WHEN_STAMPED = 'comparable_when_stamped'
READINESS_NOT_YET_COMPARABLE = 'not_yet_comparable'
READINESS_NOT_PART_OF_SUBSTRATE = 'not_part_of_substrate'

# Domain readiness is explicit and deliberately conservative.  Adding a name
# here never makes it comparable: only a dedicated compatibility rule can do
# that.  Role movement remains withheld by the TB-05 governance boundary.
DOMAIN_READINESS = MappingProxyType({
    'team_state': READINESS_COMPARABLE_WHEN_STAMPED,
    'active_arm_count': READINESS_COMPARABLE_WHEN_STAMPED,
    'arm_read': READINESS_COMPARABLE_WHEN_STAMPED,
    'rest_status': READINESS_COMPARABLE_WHEN_STAMPED,
    'workload_7d': READINESS_COMPARABLE_WHEN_STAMPED,
    'workload_14d': READINESS_COMPARABLE_WHEN_STAMPED,
    'workload_concentration': READINESS_NOT_YET_COMPARABLE,
    'rotation_impact': READINESS_COMPARABLE_WHEN_STAMPED,
    'bullpen_membership': READINESS_COMPARABLE_WHEN_STAMPED,
    'deployment_profile': READINESS_COMPARABLE_WHEN_STAMPED,
    'role_movement': READINESS_NOT_YET_COMPARABLE,
    'roster_transactions': READINESS_NOT_PART_OF_SUBSTRATE,
})

FROZEN_TEAM_BOARD_SOURCE_AUTHORITY = 'trusted_team_board_publication'


def _canonical_rotation_population_basis():
    return {
        'basis': ROTATION_IMPACT_POPULATION_BASIS,
        'population_authority': ROTATION_IMPACT_POPULATION_AUTHORITY,
        'membership_authority': ROTATION_IMPACT_MEMBERSHIP_AUTHORITY,
    }


def _canonical_membership_population_basis():
    return {
        'basis': BULLPEN_MEMBERSHIP_POPULATION_BASIS,
        'population_authority': BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY,
        'membership_authority': BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY,
        'roster_authority_version': ROSTER_AUTHORITY_VERSION,
    }


def _canonical_rest_status_population_basis():
    return {
        'basis': REST_STATUS_POPULATION_BASIS,
        'population_authority': REST_STATUS_POPULATION_AUTHORITY,
        'membership_authority': REST_STATUS_MEMBERSHIP_AUTHORITY,
    }


class DeltaStampError(ValueError):
    """A naturally generated read lacked safe prospective stamp inputs."""


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _mapping(value) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _artifact_public_state(artifact) -> Mapping[str, Any]:
    payload = _mapping(getattr(artifact, 'payload', None))
    team_state = _mapping(payload.get('team_state'))
    if getattr(artifact, 'render_version', None) == TEAM_STATE_V1_2:
        public_state = _mapping(team_state.get('public_state'))
        return {
            'public_state': public_state.get('public_code'),
            'public_label': public_state.get('public_label'),
        }
    return {
        'public_state': team_state.get('public_state'),
        'public_label': team_state.get('public_label'),
    }


def build_arm_read_capture(
    *,
    records,
    team_id,
    membership,
    membership_reference_date,
    availability_reference_date,
) -> dict:
    """Freeze canonical public reads from one already-classified publication read.

    ``records`` must be the exact active-bullpen records already selected for the
    Team State read.  This function projects their public labels; it never loads
    rows, classifies availability, or reconstructs an older date.
    """
    member_ids, authority_complete = membership or ((), False)
    membership_date = _as_date(membership_reference_date)
    availability_date = _as_date(availability_reference_date)
    if not authority_complete:
        raise DeltaStampError('arm_read_population_authority_unproven')
    if membership_date is None or availability_date is None:
        raise DeltaStampError('arm_read_reference_date_missing')

    expected_ids = {int(value) for value in (member_ids or ())}
    frozen = []
    for record in records or ():
        record = _mapping(record)
        pitcher = record.get('pitcher')
        pitcher_id = getattr(pitcher, 'id', None)
        if pitcher_id is None:
            raise DeltaStampError('arm_read_pitcher_identity_missing')
        pitcher_id = int(pitcher_id)
        if pitcher_id not in expected_ids:
            raise DeltaStampError('arm_read_population_identity_mismatch')
        pitcher_team_id = getattr(pitcher, 'team_id', None)
        if pitcher_team_id is not None and int(pitcher_team_id) != int(team_id):
            raise DeltaStampError('arm_read_team_identity_mismatch')

        availability = deepcopy(dict(record.get('availability') or {}))
        # Membership has already been resolved by the canonical Roster
        # Authority. Do not classify the pitcher again here: a selected member
        # is authoritatively active unless the same-cycle record carries a more
        # specific already-governed roster payload.
        roster_status = _mapping(record.get('roster_status')) or {
            'status': 'ACTIVE',
            'is_authoritative': True,
            'is_active_mlb': True,
            'is_inactive_context': False,
            'source': 'canonical_active_bullpen_membership',
        }
        public_read = build_public_arm_read(
            availability=availability,
            roster_status=roster_status,
        )
        if (
            public_read.get('key') not in READ_PUBLIC_LABELS
            or public_read.get('label') in (None, '')
        ):
            raise DeltaStampError('arm_read_public_value_missing')

        frozen.append({
            'pitcher_id': pitcher_id,
            'mlb_id': getattr(pitcher, 'mlb_id', None),
            'pitcher_name': getattr(pitcher, 'full_name', None),
            'team_id': int(team_id),
            'public_read': deepcopy(public_read),
            'evidence_state': {
                'data_state': availability.get('data_state'),
                'confidence': availability.get('confidence'),
            },
            'roster_authority': {
                'version': ROSTER_AUTHORITY_VERSION,
                'status': roster_status.get('status'),
                'is_authoritative': roster_status.get('is_authoritative'),
                'is_active_mlb': roster_status.get('is_active_mlb'),
            },
        })

    frozen.sort(key=lambda item: item['pitcher_id'])
    frozen_ids = [item['pitcher_id'] for item in frozen]
    missing_ids = sorted(expected_ids.difference(frozen_ids))

    return {
        'team_id': int(team_id),
        'membership_reference_date': membership_date.isoformat(),
        'availability_reference_date': availability_date.isoformat(),
        'method_version': ARM_READ_METHOD_VERSION,
        'public_contract_version': ARM_READ_PUBLIC_CONTRACT_VERSION,
        'population_basis': {
            'basis': 'canonical_current_active_bullpen',
            'population_authority': 'resolve_readiness_population',
            'membership_authority': 'resolve_active_bullpen_membership',
            'roster_authority_version': ROSTER_AUTHORITY_VERSION,
            'availability_mode': CURRENT_AVAILABILITY_MODE,
            'reference_date_policy': 'membership_slate_availability_next_day_v1',
        },
        'member_pitcher_ids': sorted(expected_ids),
        'missing_record_pitcher_ids': missing_ids,
        'records': frozen,
    }


def _valid_workload_window(value, *, window_days, represented_date):
    value = _mapping(value)
    if value.get('through') != represented_date:
        return False
    integer_fields = (
        'relief_appearances',
        'pitchers_in_relief',
        'appearances_with_pitches',
        'start_relief_unknown',
    )
    if any(
        type(value.get(field)) is not int or value.get(field) < 0
        for field in integer_fields
    ):
        return False
    pitches_total = value.get('pitches_total')
    if pitches_total is not None and (
        type(pitches_total) is not int or pitches_total < 0
    ):
        return False
    if value.get('appearances_with_pitches') > value.get('relief_appearances'):
        return False
    for field in ('sentence', 'pitchers_sentence', 'pitches_sentence'):
        if not isinstance(value.get(field), str) or not value.get(field):
            return False
    if value.get('start_relief_unknown') and not isinstance(
        value.get('start_relief_unknown_sentence'), str
    ):
        return False
    return window_days in WINDOW_DAYS


def build_workload_window_capture(*, snapshot, team_id) -> dict | None:
    """Copy same-cycle workload windows from one immutable Team Board package.

    Missing carriers identify pre-Gap-32 publications and return ``None`` so
    their existing Team State and Arm Read domains remain independently usable.
    Present-but-invalid authority raises and is withheld by the optional sidecar
    capture path; no workload calculation or historical query occurs here.
    """
    payload = _mapping(getattr(snapshot, 'payload', None))
    package = _mapping(payload.get('trusted_team_boards'))
    by_team_id = _mapping(package.get('by_team_id'))
    team = _mapping(by_team_id.get(str(int(team_id))))
    if not team or 'workload_windows' not in team:
        return None
    team_identity = _mapping(team.get('team'))
    if team_identity.get('team_id') != int(team_id):
        raise DeltaStampError('workload_team_identity_mismatch')

    carrier = _mapping(team.get('workload_windows'))
    authority = _mapping(team.get('workload_windows_authority'))
    represented_date = _iso(getattr(snapshot, 'data_through', None))
    if package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT:
        raise DeltaStampError('workload_package_contract_unproven')
    if carrier.get('contract') != WORKLOAD_WINDOWS_CARRIER_CONTRACT:
        raise DeltaStampError('workload_carrier_contract_invalid')
    if carrier.get('status') != WORKLOAD_WINDOWS_COMPLETE:
        raise DeltaStampError('workload_value_unavailable')
    if carrier.get('data_through') != represented_date:
        raise DeltaStampError('workload_represented_date_mismatch')
    if package.get('data_through') != represented_date:
        raise DeltaStampError('workload_package_date_mismatch')
    if authority.get('method_version') != WORKLOAD_WINDOWS_METHOD_VERSION:
        raise DeltaStampError('workload_method_version_unproven')
    if (
        authority.get('public_contract_version')
        != WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
    ):
        raise DeltaStampError('workload_public_contract_unproven')
    if authority.get('team_board_package_contract') != package.get('contract'):
        raise DeltaStampError('workload_package_contract_unproven')
    if authority.get('data_through') != represented_date:
        raise DeltaStampError('workload_authority_date_mismatch')
    population_basis = authority.get('population_basis')
    if not isinstance(population_basis, Mapping) or any(
        population_basis.get(field) in (None, '')
        for field in ('basis', 'population_authority', 'membership_authority')
    ):
        raise DeltaStampError('workload_population_basis_unproven')
    if authority.get('reference_date_policy') in (None, ''):
        raise DeltaStampError('workload_reference_date_policy_unproven')

    windows = _mapping(carrier.get('windows'))
    frozen = {}
    for window_days in WINDOW_DAYS:
        key = f'window_{window_days}'
        value = windows.get(key)
        if not _valid_workload_window(
            value,
            window_days=window_days,
            represented_date=represented_date,
        ):
            raise DeltaStampError(f'{key}_value_invalid')
        frozen[key] = deepcopy(dict(value))

    return {
        'team_id': int(team_id),
        'represented_date': represented_date,
        'method_version': authority.get('method_version'),
        'public_contract_version': authority.get('public_contract_version'),
        'carrier_contract_version': carrier.get('contract'),
        'contract_version': authority.get('team_board_package_contract'),
        'population_basis': deepcopy(dict(population_basis)),
        'reference_date_policy': authority.get('reference_date_policy'),
        'source_authority': FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'windows': frozen,
    }


def try_build_workload_window_capture(*, snapshot, team_id) -> dict | None:
    """Read an optional workload carrier without blocking existing domains."""
    try:
        return build_workload_window_capture(snapshot=snapshot, team_id=team_id)
    except Exception as exc:  # noqa: BLE001 - optional prospective domain
        logger.warning(
            'Workload window capture withheld team_id=%s snapshot_id=%s reason=%s.',
            team_id,
            getattr(snapshot, 'id', None),
            type(exc).__name__,
        )
        return None


def _valid_deployment_profile(value, represented_date):
    value = _mapping(value)
    if (
        value.get('contract') != DEPLOYMENT_PROFILE_CARRIER_CONTRACT
        or value.get('status') != DEPLOYMENT_PROFILE_COMPLETE
        or value.get('data_through') != represented_date
        or value.get('window_days') != DEPLOYMENT_PROFILE_WINDOW_DAYS
        or value.get('population_basis') != DEPLOYMENT_PROFILE_POPULATION_BASIS
        or not isinstance(value.get('profiles'), list)
        or not isinstance(value.get('team_summary'), Mapping)
        or not isinstance(value.get('summary'), str)
        or not isinstance(value.get('limitations'), list)
    ):
        return False
    seen = set()
    for raw in value.get('profiles') or []:
        profile = _mapping(raw)
        pitcher_id = profile.get('pitcher_id')
        if type(pitcher_id) is not int or pitcher_id in seen:
            return False
        seen.add(pitcher_id)
        if not isinstance(profile.get('pitcher_name'), str) or not profile.get('pitcher_name'):
            return False
        for field in (
            'appearances_analyzed', 'saves', 'holds', 'games_finished',
            'appearances_with_games_finished', 'multi_inning_appearances',
            'appearances_with_outs',
        ):
            if type(profile.get(field)) is not int or profile.get(field) < 0:
                return False
        if (
            profile.get('appearances_with_outs') > profile.get('appearances_analyzed')
            or profile.get('appearances_with_games_finished') > profile.get('appearances_analyzed')
            or profile.get('multi_inning_appearances') > profile.get('appearances_with_outs')
            or not isinstance(profile.get('summary'), str)
            or not isinstance(profile.get('limitations'), list)
        ):
            return False
    return True


def build_deployment_profile_capture(*, snapshot, team_id) -> dict | None:
    """Copy one same-cycle deployment carrier; never replay appearance rows."""
    package, team = _trusted_team_package(snapshot, team_id, domain='deployment')
    if 'deployment_profile' not in team:
        return None
    value = _mapping(team.get('deployment_profile'))
    authority = _mapping(team.get('deployment_profile_authority'))
    represented_date = _iso(getattr(snapshot, 'data_through', None))
    if not _valid_deployment_profile(value, represented_date):
        raise DeltaStampError('deployment_value_invalid')
    expected_population = {
        'basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
        'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
        'membership_authority': DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
    }
    if (
        authority.get('method_version') != DEPLOYMENT_PROFILE_METHOD_VERSION
        or authority.get('public_contract_version')
        != DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
        or authority.get('carrier_contract_version')
        != DEPLOYMENT_PROFILE_CARRIER_CONTRACT
        or authority.get('team_board_package_contract') != package.get('contract')
        or authority.get('reference_date_policy')
        != DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY
        or authority.get('data_through') != represented_date
        or dict(_mapping(authority.get('population_basis'))) != expected_population
    ):
        raise DeltaStampError('deployment_authority_unproven')
    return {
        'team_id': int(team_id),
        'represented_date': represented_date,
        'method_version': authority.get('method_version'),
        'public_contract_version': authority.get('public_contract_version'),
        'carrier_contract_version': authority.get('carrier_contract_version'),
        'contract_version': authority.get('team_board_package_contract'),
        'population_basis': deepcopy(dict(authority.get('population_basis'))),
        'reference_date_policy': authority.get('reference_date_policy'),
        'source_authority': FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'value': deepcopy(dict(value)),
    }


def try_build_deployment_profile_capture(*, snapshot, team_id) -> dict | None:
    try:
        return build_deployment_profile_capture(snapshot=snapshot, team_id=team_id)
    except Exception as exc:  # noqa: BLE001 - optional prospective domain
        logger.warning(
            'Deployment profile capture withheld team_id=%s snapshot_id=%s reason=%s.',
            team_id,
            getattr(snapshot, 'id', None),
            type(exc).__name__,
        )
        return None


def _trusted_team_package(snapshot, team_id, *, domain):
    payload = _mapping(getattr(snapshot, 'payload', None))
    package = _mapping(payload.get('trusted_team_boards'))
    team = _mapping(_mapping(package.get('by_team_id')).get(str(int(team_id))))
    if package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT:
        raise DeltaStampError(f'{domain}_package_contract_unproven')
    if package.get('data_through') != _iso(getattr(snapshot, 'data_through', None)):
        raise DeltaStampError(f'{domain}_package_date_mismatch')
    if _mapping(team.get('team')).get('team_id') != int(team_id):
        raise DeltaStampError(f'{domain}_team_identity_mismatch')
    return package, team


def build_rotation_impact_capture(*, snapshot, team_id) -> dict | None:
    """Copy the already-frozen Rotation Impact object without recalculation."""
    package, team = _trusted_team_package(snapshot, team_id, domain='rotation')
    if 'rotation_support_pressure' not in team:
        return None
    value = _mapping(team.get('rotation_support_pressure'))
    authority = _mapping(team.get('rotation_support_pressure_authority'))
    represented_date = _iso(getattr(snapshot, 'data_through', None))
    if not value:
        return None
    if value.get('capability') != ROTATION_IMPACT_CAPABILITY:
        raise DeltaStampError('rotation_capability_invalid')
    if value.get('version') != ROTATION_IMPACT_METHOD_VERSION:
        raise DeltaStampError('rotation_method_version_unproven')
    if value.get('team_id') != int(team_id):
        raise DeltaStampError('rotation_team_identity_mismatch')
    rotation_reference_date = value.get('reference_date')
    if (
        _as_date(rotation_reference_date) is None
        or rotation_reference_date != package.get('availability_reference_date')
    ):
        raise DeltaStampError('rotation_reference_date_mismatch')
    if type(value.get('window_days')) is not int or value.get('window_days') <= 0:
        raise DeltaStampError('rotation_window_invalid')
    for field in (
        'games_in_window', 'games_analyzed', 'games_excluded',
        'starter_outs', 'bullpen_outs_required', 'short_start_count',
    ):
        if type(value.get(field)) is not int or value.get(field) < 0:
            raise DeltaStampError('rotation_value_invalid')
    if not isinstance(value.get('summary'), str) or not isinstance(
        value.get('limitations'), list
    ):
        raise DeltaStampError('rotation_value_invalid')
    if authority.get('method_version') != ROTATION_IMPACT_METHOD_VERSION:
        raise DeltaStampError('rotation_method_version_unproven')
    if (
        authority.get('public_contract_version')
        != ROTATION_IMPACT_PUBLIC_CONTRACT_VERSION
        or authority.get('carrier_contract_version')
        != ROTATION_IMPACT_CARRIER_CONTRACT
        or authority.get('team_board_package_contract') != package.get('contract')
    ):
        raise DeltaStampError('rotation_contract_unproven')
    population_basis = authority.get('population_basis')
    if (
        not isinstance(population_basis, Mapping)
        or dict(population_basis) != _canonical_rotation_population_basis()
    ):
        raise DeltaStampError('rotation_population_basis_unproven')
    if (
        authority.get('reference_date_policy')
        != ROTATION_IMPACT_REFERENCE_DATE_POLICY
        or authority.get('reference_date') != rotation_reference_date
    ):
        raise DeltaStampError('rotation_reference_date_unproven')
    return {
        'team_id': int(team_id),
        'represented_date': represented_date,
        'method_version': authority.get('method_version'),
        'public_contract_version': authority.get('public_contract_version'),
        'carrier_contract_version': authority.get('carrier_contract_version'),
        'contract_version': authority.get('team_board_package_contract'),
        'population_basis': deepcopy(dict(population_basis)),
        'reference_date_policy': authority.get('reference_date_policy'),
        'reference_date': rotation_reference_date,
        'source_authority': FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'value': deepcopy(dict(value)),
    }


def try_build_rotation_impact_capture(*, snapshot, team_id) -> dict | None:
    try:
        return build_rotation_impact_capture(snapshot=snapshot, team_id=team_id)
    except Exception as exc:  # noqa: BLE001 - optional prospective domain
        logger.warning(
            'Rotation Impact capture withheld team_id=%s snapshot_id=%s reason=%s.',
            team_id,
            getattr(snapshot, 'id', None),
            type(exc).__name__,
        )
        return None


def build_bullpen_membership_capture(*, snapshot, team_id) -> dict | None:
    """Copy the frozen default-visible bullpen membership and public identity."""
    package, team = _trusted_team_package(snapshot, team_id, domain='membership')
    if 'default_pitcher_ids' not in team:
        return None
    authority = _mapping(team.get('bullpen_membership_authority'))
    represented_date = _iso(getattr(snapshot, 'data_through', None))
    raw_ids = team.get('default_pitcher_ids')
    if not isinstance(raw_ids, list) or any(type(value) is not int for value in raw_ids):
        raise DeltaStampError('membership_values_invalid')
    member_ids = sorted(raw_ids)
    if len(member_ids) != len(set(member_ids)):
        raise DeltaStampError('membership_values_invalid')
    records_by_id = {}
    for record in team.get('records') or []:
        record = _mapping(record)
        pitcher_id = record.get('pitcher_id')
        if type(pitcher_id) is int and pitcher_id not in records_by_id:
            records_by_id[pitcher_id] = record
    members = []
    for pitcher_id in member_ids:
        record = records_by_id.get(pitcher_id)
        if not record or not isinstance(record.get('name'), str) or not record.get('name'):
            raise DeltaStampError('membership_identity_missing')
        members.append({'pitcher_id': pitcher_id, 'pitcher_name': record.get('name')})
    if authority.get('method_version') != BULLPEN_MEMBERSHIP_METHOD_VERSION:
        raise DeltaStampError('membership_method_version_unproven')
    if (
        authority.get('public_contract_version')
        != BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION
        or authority.get('carrier_contract_version')
        != BULLPEN_MEMBERSHIP_CARRIER_CONTRACT
        or authority.get('team_board_package_contract') != package.get('contract')
    ):
        raise DeltaStampError('membership_contract_unproven')
    population_basis = authority.get('population_basis')
    if (
        not isinstance(population_basis, Mapping)
        or dict(population_basis) != _canonical_membership_population_basis()
    ):
        raise DeltaStampError('membership_population_basis_unproven')
    if (
        authority.get('reference_date_policy')
        != BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY
        or _as_date(authority.get('membership_reference_date')) is None
        or authority.get('membership_reference_date')
        != package.get('availability_reference_date')
    ):
        raise DeltaStampError('membership_reference_date_unproven')
    return {
        'team_id': int(team_id),
        'represented_date': represented_date,
        'method_version': authority.get('method_version'),
        'public_contract_version': authority.get('public_contract_version'),
        'carrier_contract_version': authority.get('carrier_contract_version'),
        'contract_version': authority.get('team_board_package_contract'),
        'population_basis': deepcopy(dict(population_basis)),
        'reference_date_policy': authority.get('reference_date_policy'),
        'membership_reference_date': authority.get('membership_reference_date'),
        'source_authority': FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'member_pitcher_ids': member_ids,
        'members': members,
    }


def try_build_bullpen_membership_capture(*, snapshot, team_id) -> dict | None:
    try:
        return build_bullpen_membership_capture(snapshot=snapshot, team_id=team_id)
    except Exception as exc:  # noqa: BLE001 - optional prospective domain
        logger.warning(
            'Bullpen membership capture withheld team_id=%s snapshot_id=%s reason=%s.',
            team_id,
            getattr(snapshot, 'id', None),
            type(exc).__name__,
        )
        return None


def build_rest_status_capture(*, snapshot, team_id) -> dict | None:
    """Copy one frozen D-055 carrier without recalculating historical rest."""
    package, team = _trusted_team_package(snapshot, team_id, domain='rest_status')
    if 'rest_status' not in team:
        return None
    value = team.get('rest_status')
    authority = _mapping(team.get('rest_status_authority'))
    represented_date = _iso(getattr(snapshot, 'data_through', None))
    reference_date = _iso(getattr(snapshot, 'availability_reference_date', None))
    if (
        getattr(snapshot, 'status', None) != 'ready'
        or getattr(snapshot, 'is_published', False) is not True
        or getattr(snapshot, 'published_at', None) is None
        or not is_valid_rest_status_carrier(value)
    ):
        raise DeltaStampError('rest_status_value_unproven')
    represented = _as_date(represented_date)
    reference = _as_date(reference_date)
    if represented is None or reference != represented + timedelta(days=1):
        raise DeltaStampError('rest_status_reference_date_unproven')
    if package.get('availability_reference_date') != reference_date:
        raise DeltaStampError('rest_status_reference_date_unproven')
    if (
        authority.get('method_version') != REST_STATUS_METHOD_VERSION
        or authority.get('public_contract_version')
        != REST_STATUS_PUBLIC_CONTRACT_VERSION
        or authority.get('team_board_package_contract')
        != TEAM_BOARD_PACKAGE_CONTRACT
        or authority.get('population_basis')
        != _canonical_rest_status_population_basis()
        or authority.get('reference_date_policy')
        != REST_STATUS_REFERENCE_DATE_POLICY
        or authority.get('availability_reference_date') != reference_date
    ):
        raise DeltaStampError('rest_status_authority_unproven')
    return {
        'team_id': int(team_id),
        'represented_date': represented_date,
        'availability_reference_date': reference_date,
        'method_version': authority.get('method_version'),
        'public_contract_version': authority.get('public_contract_version'),
        'contract_version': authority.get('team_board_package_contract'),
        'population_basis': deepcopy(dict(authority.get('population_basis'))),
        'reference_date_policy': authority.get('reference_date_policy'),
        'source_authority': FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'value': deepcopy(dict(value)),
    }


def try_build_rest_status_capture(*, snapshot, team_id) -> dict | None:
    try:
        return build_rest_status_capture(snapshot=snapshot, team_id=team_id)
    except Exception as exc:  # noqa: BLE001 - optional prospective domain
        logger.warning(
            'Rest Status capture withheld team_id=%s snapshot_id=%s reason=%s.',
            team_id,
            getattr(snapshot, 'id', None),
            type(exc).__name__,
        )
        return None


def build_prospective_envelope(
    *, source, readiness, artifact, arm_read_capture=None,
    workload_window_capture=None, rotation_impact_capture=None,
    bullpen_membership_capture=None, deployment_profile_capture=None,
    rest_status_capture=None,
) -> dict:
    """Build metadata from the exact governed read frozen by ``artifact``.

    No classifier or historical service is called.  The method stamp is read
    from the canonical Team State evidence vector and must agree with the one
    canonical owner imported from ``team_operations``; disagreement fails
    closed instead of recording a second method identity.
    """
    readiness = _mapping(readiness)
    evidence = _mapping(readiness.get('team_state_evidence'))
    evidence_references = _mapping(evidence.get('evidence_references'))
    snapshot = getattr(source, 'snapshot', None)
    represented_date = getattr(snapshot, 'data_through', None)
    method_version = evidence.get('method_version')

    if method_version != TEAM_STATE_METHOD_VERSION:
        raise DeltaStampError('team_state_method_version_unproven')
    if not isinstance(represented_date, date):
        raise DeltaStampError('represented_date_missing')
    if getattr(snapshot, 'snapshot_id', None) is None:
        raise DeltaStampError('source_snapshot_identity_missing')
    if getattr(artifact, 'id', None) is None:
        raise DeltaStampError('source_artifact_identity_missing')
    if getattr(artifact, 'lifecycle_state', None) != 'published':
        raise DeltaStampError('source_artifact_not_published')

    population_basis = {
        'basis': evidence.get('basis'),
        'population_authority': evidence_references.get('population_authority'),
        'membership_authority': evidence_references.get('membership_authority'),
    }
    if any(value in (None, '') for value in population_basis.values()):
        raise DeltaStampError('team_state_population_basis_unproven')

    state = _artifact_public_state(artifact)
    if (
        state.get('public_state') in (None, '')
        or state.get('public_label') in (None, '')
    ):
        raise DeltaStampError('team_state_value_missing')

    contract_version = readiness.get('contract_version')
    if contract_version in (None, ''):
        raise DeltaStampError('team_state_contract_version_missing')

    source_authority = (
        getattr(snapshot, 'subject_type', None) or 'dashboard_snapshot'
    )
    trusted = bool(
        getattr(snapshot, 'is_trusted', False)
        and getattr(artifact, 'published_at', None) is not None
        and readiness.get('contract_state') in {'available', 'degraded'}
    )

    domain_metadata = {
        'method_version': method_version,
        'contract_version': contract_version,
        'public_contract_version': PUBLIC_TEAM_STATE_CONTRACT,
        'population_basis': population_basis,
        'trust_state': evidence.get('trust_state'),
        'trust_data_state': evidence.get('trust_data_state'),
        'freshness_state': evidence.get('freshness_state'),
        'trusted': trusted,
    }
    envelope = {
        'capability': CAPABILITY,
        'envelope_version': ENVELOPE_VERSION,
        'team_id': int(getattr(source, 'team_id')),
        'represented_date': represented_date.isoformat(),
        'source': {
            'frozen_value_source': 'team_state_share_artifact',
            'artifact_id': artifact.id,
            'artifact_payload_version': getattr(artifact, 'render_version', None),
            'snapshot_authority': source_authority,
            'snapshot_id': snapshot.snapshot_id,
            'sync_run_id': snapshot.sync_run_id,
            'subject_key': getattr(snapshot, 'subject_key', None),
        },
        'domains': {
            'team_state': deepcopy(domain_metadata),
            'active_arm_count': deepcopy(domain_metadata),
        },
        'values': {
            'team_state': state,
            # Null stays null.  It is never normalized to zero.
            'active_arm_count': evidence.get('active_pitcher_count'),
        },
    }
    arm_read_capture = _mapping(arm_read_capture)
    if arm_read_capture:
        if arm_read_capture.get('team_id') != envelope['team_id']:
            raise DeltaStampError('arm_read_team_identity_mismatch')
        records = arm_read_capture.get('records')
        member_ids = arm_read_capture.get('member_pitcher_ids')
        population_basis = arm_read_capture.get('population_basis')
        if not isinstance(records, list) or not isinstance(member_ids, list):
            raise DeltaStampError('arm_read_values_missing')
        if not isinstance(population_basis, Mapping):
            raise DeltaStampError('arm_read_population_basis_unproven')
        envelope['domains']['arm_read'] = {
            'method_version': arm_read_capture.get('method_version'),
            'public_contract_version': arm_read_capture.get('public_contract_version'),
            'population_basis': deepcopy(dict(population_basis)),
            'membership_reference_date': arm_read_capture.get('membership_reference_date'),
            'availability_reference_date': arm_read_capture.get('availability_reference_date'),
            'trusted': trusted,
        }
        envelope['values']['arm_read'] = {
            'member_pitcher_ids': deepcopy(member_ids),
            'missing_record_pitcher_ids': deepcopy(
                arm_read_capture.get('missing_record_pitcher_ids') or []
            ),
            'records': deepcopy(records),
        }
    workload_window_capture = _mapping(workload_window_capture)
    if workload_window_capture:
        if workload_window_capture.get('team_id') != envelope['team_id']:
            raise DeltaStampError('workload_team_identity_mismatch')
        if workload_window_capture.get('represented_date') != envelope['represented_date']:
            raise DeltaStampError('workload_represented_date_mismatch')
        windows = _mapping(workload_window_capture.get('windows'))
        for window_days in WINDOW_DAYS:
            domain = f'workload_{window_days}d'
            value_key = f'window_{window_days}'
            value = windows.get(value_key)
            if not isinstance(value, Mapping):
                raise DeltaStampError(f'{value_key}_value_missing')
            envelope['domains'][domain] = {
                'method_version': workload_window_capture.get('method_version'),
                'contract_version': workload_window_capture.get('contract_version'),
                'public_contract_version': (
                    workload_window_capture.get('public_contract_version')
                ),
                'carrier_contract_version': (
                    workload_window_capture.get('carrier_contract_version')
                ),
                'population_basis': deepcopy(
                    workload_window_capture.get('population_basis')
                ),
                'reference_date_policy': (
                    workload_window_capture.get('reference_date_policy')
                ),
                'source_authority': workload_window_capture.get('source_authority'),
                'window_days': window_days,
                'trusted': trusted,
            }
            envelope['values'][domain] = deepcopy(dict(value))
    rotation_impact_capture = _mapping(rotation_impact_capture)
    if rotation_impact_capture:
        if (
            rotation_impact_capture.get('team_id') != envelope['team_id']
            or rotation_impact_capture.get('represented_date')
            != envelope['represented_date']
        ):
            raise DeltaStampError('rotation_identity_mismatch')
        envelope['domains']['rotation_impact'] = {
            'method_version': rotation_impact_capture.get('method_version'),
            'contract_version': rotation_impact_capture.get('contract_version'),
            'public_contract_version': (
                rotation_impact_capture.get('public_contract_version')
            ),
            'carrier_contract_version': (
                rotation_impact_capture.get('carrier_contract_version')
            ),
            'population_basis': deepcopy(
                rotation_impact_capture.get('population_basis')
            ),
            'reference_date_policy': (
                rotation_impact_capture.get('reference_date_policy')
            ),
            'source_authority': rotation_impact_capture.get('source_authority'),
            'reference_date': rotation_impact_capture.get('reference_date'),
            'window_days': _mapping(
                rotation_impact_capture.get('value')
            ).get('window_days'),
            'trusted': trusted,
        }
        envelope['values']['rotation_impact'] = deepcopy(
            dict(_mapping(rotation_impact_capture.get('value')))
        )
    bullpen_membership_capture = _mapping(bullpen_membership_capture)
    if bullpen_membership_capture:
        if (
            bullpen_membership_capture.get('team_id') != envelope['team_id']
            or bullpen_membership_capture.get('represented_date')
            != envelope['represented_date']
        ):
            raise DeltaStampError('membership_identity_mismatch')
        envelope['domains']['bullpen_membership'] = {
            'method_version': bullpen_membership_capture.get('method_version'),
            'contract_version': bullpen_membership_capture.get('contract_version'),
            'public_contract_version': (
                bullpen_membership_capture.get('public_contract_version')
            ),
            'carrier_contract_version': (
                bullpen_membership_capture.get('carrier_contract_version')
            ),
            'population_basis': deepcopy(
                bullpen_membership_capture.get('population_basis')
            ),
            'reference_date_policy': (
                bullpen_membership_capture.get('reference_date_policy')
            ),
            'source_authority': bullpen_membership_capture.get('source_authority'),
            'membership_reference_date': (
                bullpen_membership_capture.get('membership_reference_date')
            ),
            'trusted': trusted,
        }
        envelope['values']['bullpen_membership'] = {
            'member_pitcher_ids': deepcopy(
                bullpen_membership_capture.get('member_pitcher_ids')
            ),
            'members': deepcopy(bullpen_membership_capture.get('members')),
        }
    deployment_profile_capture = _mapping(deployment_profile_capture)
    if deployment_profile_capture:
        if (
            deployment_profile_capture.get('team_id') != envelope['team_id']
            or deployment_profile_capture.get('represented_date')
            != envelope['represented_date']
        ):
            raise DeltaStampError('deployment_identity_mismatch')
        envelope['domains']['deployment_profile'] = {
            'method_version': deployment_profile_capture.get('method_version'),
            'contract_version': deployment_profile_capture.get('contract_version'),
            'public_contract_version': (
                deployment_profile_capture.get('public_contract_version')
            ),
            'carrier_contract_version': (
                deployment_profile_capture.get('carrier_contract_version')
            ),
            'population_basis': deepcopy(
                deployment_profile_capture.get('population_basis')
            ),
            'reference_date_policy': (
                deployment_profile_capture.get('reference_date_policy')
            ),
            'source_authority': deployment_profile_capture.get('source_authority'),
            'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
            'trusted': trusted,
        }
        envelope['values']['deployment_profile'] = deepcopy(
            dict(_mapping(deployment_profile_capture.get('value')))
        )
    rest_status_capture = _mapping(rest_status_capture)
    if rest_status_capture:
        if (
            rest_status_capture.get('team_id') != envelope['team_id']
            or rest_status_capture.get('represented_date')
            != envelope['represented_date']
        ):
            raise DeltaStampError('rest_status_identity_mismatch')
        envelope['domains']['rest_status'] = {
            'method_version': rest_status_capture.get('method_version'),
            'contract_version': rest_status_capture.get('contract_version'),
            'public_contract_version': (
                rest_status_capture.get('public_contract_version')
            ),
            'population_basis': deepcopy(
                rest_status_capture.get('population_basis')
            ),
            'reference_date_policy': (
                rest_status_capture.get('reference_date_policy')
            ),
            'availability_reference_date': (
                rest_status_capture.get('availability_reference_date')
            ),
            'source_authority': rest_status_capture.get('source_authority'),
            'trusted': trusted,
        }
        envelope['values']['rest_status'] = deepcopy(
            dict(_mapping(rest_status_capture.get('value')))
        )
    return envelope


def stamp_prospective_snapshot(
    *, source, readiness, artifact, arm_read_capture=None,
    workload_window_capture=None, rotation_impact_capture=None,
    bullpen_membership_capture=None, deployment_profile_capture=None,
    rest_status_capture=None, session=None,
):
    """Stage one append-only sidecar for a newly published Team State artifact."""
    session = session or db.session
    envelope = build_prospective_envelope(
        source=source,
        readiness=readiness,
        artifact=artifact,
        arm_read_capture=arm_read_capture,
        workload_window_capture=workload_window_capture,
        rotation_impact_capture=rotation_impact_capture,
        bullpen_membership_capture=bullpen_membership_capture,
        deployment_profile_capture=deployment_profile_capture,
        rest_status_capture=rest_status_capture,
    )
    represented_date = _as_date(envelope.get('represented_date'))
    source_key = f'{SNAPSHOT_SOURCE_PREFIX}{envelope["team_id"]}'
    candidates = (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.source == source_key)
        .filter(DashboardSnapshot.data_through == represented_date)
        .all()
    )
    for candidate in candidates:
        candidate_source = _mapping(_payload(candidate).get('source'))
        if candidate_source.get('artifact_id') == artifact.id:
            # Publication identity is immutable. Re-entry returns the exact
            # existing sidecar and never refreshes it from newer mutable rows.
            return candidate
    row = DashboardSnapshot(
        snapshot_type=SNAPSHOT_TYPE,
        # This observational sidecar is created by Share Artifact publication,
        # not by the source SyncRun. Preserve that immutable source identity in
        # the comparison envelope without claiming relational ownership here.
        sync_run_id=None,
        status='ready',
        is_published=False,
        # Durable proof that the sidecar was captured from a publication that
        # completed its immutable lifecycle transition.
        published_at=getattr(artifact, 'published_at', None),
        payload=deepcopy(envelope),
        payload_version=SNAPSHOT_PAYLOAD_VERSION,
        data_through=represented_date,
        availability_reference_date=None,
        snapshot_generated_at=utc_now_naive(),
        source=source_key,
    )
    session.add(row)
    session.flush()
    return row


def try_stamp_prospective_snapshot(
    *, source, readiness, artifact, arm_read_capture=None,
    workload_window_capture=None, rotation_impact_capture=None,
    bullpen_membership_capture=None, deployment_profile_capture=None,
    rest_status_capture=None, session=None,
):
    """Capture a sidecar without making Share Artifact publication depend on it.

    The nested transaction confines any capture problem to this observational
    substrate.  Publication remains authoritative and succeeds; a missing row
    simply makes that date incomparable, which is the required fail-closed
    behavior.
    """
    session = session or db.session
    try:
        with session.begin_nested():
            return stamp_prospective_snapshot(
                source=source,
                readiness=readiness,
                artifact=artifact,
                arm_read_capture=arm_read_capture,
                workload_window_capture=workload_window_capture,
                rotation_impact_capture=rotation_impact_capture,
                bullpen_membership_capture=bullpen_membership_capture,
                deployment_profile_capture=deployment_profile_capture,
                rest_status_capture=rest_status_capture,
                session=session,
            )
    except Exception as exc:  # noqa: BLE001 - optional capture must not block publish
        logger.warning(
            'Team Board delta snapshot capture withheld team_id=%s artifact_id=%s reason=%s.',
            getattr(source, 'team_id', None),
            getattr(artifact, 'id', None),
            type(exc).__name__,
        )
        return None


def get_previous_snapshot(*, team_id, represented_date, session=None):
    """Return the nearest prior frozen team/date sidecar with one bounded query."""
    session = session or db.session
    represented_date = _as_date(represented_date)
    if represented_date is None:
        return None
    return (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.status == 'ready')
        .filter(DashboardSnapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION)
        .filter(DashboardSnapshot.published_at.isnot(None))
        .filter(DashboardSnapshot.source == f'{SNAPSHOT_SOURCE_PREFIX}{int(team_id)}')
        .filter(DashboardSnapshot.data_through < represented_date)
        .order_by(
            DashboardSnapshot.data_through.desc(),
            DashboardSnapshot.id.desc(),
        )
        .limit(1)
        .one_or_none()
    )


def get_latest_snapshot(*, team_id, session=None):
    """Return the latest frozen publication sidecar for one team."""
    session = session or db.session
    return (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.status == 'ready')
        .filter(DashboardSnapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION)
        .filter(DashboardSnapshot.published_at.isnot(None))
        .filter(DashboardSnapshot.source == f'{SNAPSHOT_SOURCE_PREFIX}{int(team_id)}')
        .order_by(
            DashboardSnapshot.data_through.desc(),
            DashboardSnapshot.id.desc(),
        )
        .limit(1)
        .one_or_none()
    )


def _payload(snapshot) -> Mapping[str, Any]:
    return _mapping(getattr(snapshot, 'payload', None))


def _domain_metadata(payload, domain) -> Mapping[str, Any]:
    return _mapping(_mapping(payload.get('domains')).get(domain))


def _team_state_carrier_value(snapshot) -> Mapping[str, Any] | None:
    """Return one valid scalar Team State value without mutating its sidecar.

    Team State 1.2 artifacts were briefly frozen into sidecars with the
    canonical ``public_state`` object nested where the scalar public code
    belongs.  Only that exact, version-bound shape is projected at read time;
    every other missing, contradictory, or unknown shape remains unavailable.
    """
    payload = _payload(snapshot)
    value = _mapping(payload.get('values')).get('team_state')
    if not isinstance(value, Mapping):
        return None
    if set(value) not in (
        {'public_state'},
        {'public_state', 'public_label'},
    ):
        return None

    public_state = value.get('public_state')
    public_label = value.get('public_label')
    if (
        isinstance(public_state, str)
        and public_state
        and isinstance(public_label, str)
        and public_label
    ):
        return {
            'public_state': public_state,
            'public_label': public_label,
        }

    source = _mapping(payload.get('source'))
    if source.get('artifact_payload_version') != TEAM_STATE_V1_2:
        return None
    if public_label is not None or not isinstance(public_state, Mapping):
        return None
    if set(public_state) != {'public_code', 'public_label'}:
        return None

    nested_code = public_state.get('public_code')
    nested_label = public_state.get('public_label')
    if (
        not isinstance(nested_code, str)
        or not nested_code
        or not isinstance(nested_label, str)
        or not nested_label
    ):
        return None
    return {
        'public_state': nested_code,
        'public_label': nested_label,
    }


def _withheld(domain, reason):
    return {
        'readiness': DOMAIN_READINESS[domain],
        'status': reason,
        'reason_code': reason,
    }


def _compatible_domain(previous, current, domain, value_key):
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)

    previous_payload = _payload(previous)
    current_payload = _payload(current)
    previous_envelope_version = previous_payload.get('envelope_version')
    current_envelope_version = current_payload.get('envelope_version')
    if (
        previous_envelope_version in (None, '')
        or current_envelope_version in (None, '')
        or previous_envelope_version != current_envelope_version
    ):
        return _withheld(domain, CONTRACT_INCOMPATIBLE)
    previous_team = previous_payload.get('team_id')
    current_team = current_payload.get('team_id')
    if previous_team is None or current_team is None or previous_team != current_team:
        return _withheld(domain, TEAM_ID_MISMATCH)

    previous_date = _as_date(previous_payload.get('represented_date'))
    current_date = _as_date(current_payload.get('represented_date'))
    if previous_date is None or current_date is None or previous_date >= current_date:
        return _withheld(domain, REPRESENTED_DATE_INVALID)

    previous_source = _mapping(previous_payload.get('source'))
    current_source = _mapping(current_payload.get('source'))
    for source in (previous_source, current_source):
        if (
            source.get('artifact_id') is None
            or source.get('snapshot_id') is None
            or source.get('snapshot_authority') in (None, '')
        ):
            return _withheld(domain, SOURCE_IDENTITY_MISSING)

    previous_metadata = _domain_metadata(previous_payload, domain)
    current_metadata = _domain_metadata(current_payload, domain)
    previous_method = previous_metadata.get('method_version')
    current_method = current_metadata.get('method_version')
    if previous_method in (None, '') or current_method in (None, ''):
        return _withheld(domain, METHOD_VERSION_MISSING)
    if previous_method != current_method:
        return _withheld(domain, METHOD_VERSION_MISMATCH)

    contract_fields = (
        ('public_contract_version',)
        if domain == 'arm_read'
        else ('contract_version', 'public_contract_version')
    )
    if any(
        previous_metadata.get(field) in (None, '')
        or current_metadata.get(field) in (None, '')
        or previous_metadata.get(field) != current_metadata.get(field)
        for field in contract_fields
    ):
        return _withheld(domain, CONTRACT_INCOMPATIBLE)

    previous_population = previous_metadata.get('population_basis')
    current_population = current_metadata.get('population_basis')
    if not isinstance(previous_population, Mapping) or not isinstance(
        current_population, Mapping
    ):
        return _withheld(domain, POPULATION_BASIS_MISSING)
    population_fields = ('basis', 'population_authority', 'membership_authority')
    if any(
        population.get(field) in (None, '')
        for population in (previous_population, current_population)
        for field in population_fields
    ):
        return _withheld(domain, POPULATION_BASIS_MISSING)
    if dict(previous_population) != dict(current_population):
        return _withheld(domain, POPULATION_BASIS_MISMATCH)

    if previous_metadata.get('trusted') is not True or current_metadata.get('trusted') is not True:
        return _withheld(domain, FRESHNESS_UNTRUSTED)

    if domain == 'team_state':
        previous_value = _team_state_carrier_value(previous)
        current_value = _team_state_carrier_value(current)
    else:
        previous_value = _mapping(previous_payload.get('values')).get(value_key)
        current_value = _mapping(current_payload.get('values')).get(value_key)
    if previous_value is None or current_value is None:
        return _withheld(domain, VALUE_MISSING)
    if domain == 'team_state' and (
        not isinstance(previous_value, Mapping)
        or not isinstance(current_value, Mapping)
        or previous_value.get('public_state') in (None, '')
        or current_value.get('public_state') in (None, '')
        or previous_value.get('public_label') in (None, '')
        or current_value.get('public_label') in (None, '')
    ):
        return _withheld(domain, VALUE_MISSING)

    return {
        'readiness': DOMAIN_READINESS[domain],
        'status': COMPARABLE,
        'reason_code': None,
        'previous': deepcopy(previous_value),
        'current': deepcopy(current_value),
    }


def _arm_records(value):
    records = _mapping(value).get('records')
    if not isinstance(records, list):
        return None
    result = {}
    for record in records:
        record = _mapping(record)
        pitcher_id = record.get('pitcher_id')
        public_read = _mapping(record.get('public_read'))
        public_key = public_read.get('key')
        governed_read = _mapping(READ_PUBLIC_LABELS.get(public_key))
        if (
            pitcher_id is None
            or not governed_read
            or public_read.get('kind') != governed_read.get('kind')
            or public_read.get('label') != governed_read.get('label')
            or int(pitcher_id) in result
        ):
            return None
        result[int(pitcher_id)] = record
    return result


def _compatible_arm_read_domain(previous, current):
    if previous is None:
        return _withheld('arm_read', PREVIOUS_MISSING)
    if current is None:
        return _withheld('arm_read', CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), 'arm_read')
        or not _domain_metadata(_payload(current), 'arm_read')
    ):
        # Older sidecars remain prospective-only.  Their Team State values can
        # still compare, but no Arm Read is reconstructed or retro-stamped.
        return _withheld('arm_read', DOMAIN_NOT_READY)
    base = _compatible_domain(previous, current, 'arm_read', 'arm_read')
    if base.get('status') != COMPARABLE:
        return base

    previous_metadata = _domain_metadata(_payload(previous), 'arm_read')
    current_metadata = _domain_metadata(_payload(current), 'arm_read')
    for snapshot, metadata in (
        (previous, previous_metadata),
        (current, current_metadata),
    ):
        represented_date = _as_date(_payload(snapshot).get('represented_date'))
        membership_reference_date = _as_date(
            metadata.get('membership_reference_date')
        )
        availability_reference_date = _as_date(
            metadata.get('availability_reference_date')
        )
        if (
            represented_date is None
            or membership_reference_date != represented_date
            or availability_reference_date != represented_date + timedelta(days=1)
        ):
            return _withheld('arm_read', REPRESENTED_DATE_INVALID)

    previous_value = _mapping(base.get('previous'))
    current_value = _mapping(base.get('current'))
    previous_records = _arm_records(previous_value)
    current_records = _arm_records(current_value)
    previous_members = previous_value.get('member_pitcher_ids')
    current_members = current_value.get('member_pitcher_ids')
    if (
        previous_records is None
        or current_records is None
        or not isinstance(previous_members, list)
        or not isinstance(current_members, list)
    ):
        return _withheld('arm_read', VALUE_MISSING)

    previous_member_ids = {int(value) for value in previous_members}
    current_member_ids = {int(value) for value in current_members}
    if (
        len(previous_member_ids) != len(previous_members)
        or len(current_member_ids) != len(current_members)
        or not set(previous_records).issubset(previous_member_ids)
        or not set(current_records).issubset(current_member_ids)
    ):
        return _withheld('arm_read', VALUE_MISSING)
    previous_team_id = _payload(previous).get('team_id')
    current_team_id = _payload(current).get('team_id')
    if any(
        record.get('team_id') != expected_team_id
        for records, expected_team_id in (
            (previous_records.values(), previous_team_id),
            (current_records.values(), current_team_id),
        )
        for record in records
    ):
        return _withheld('arm_read', TEAM_ID_MISMATCH)
    comparisons = []
    movements = []
    for pitcher_id in sorted(previous_member_ids | current_member_ids):
        previous_record = previous_records.get(pitcher_id)
        current_record = current_records.get(pitcher_id)
        if pitcher_id not in previous_member_ids:
            comparison = {
                'pitcher_id': pitcher_id,
                'comparable': False,
                'reason_code': PREVIOUS_MISSING,
                'population_change': 'added',
                'previous': None,
                'current': deepcopy(current_record),
            }
        elif pitcher_id not in current_member_ids:
            comparison = {
                'pitcher_id': pitcher_id,
                'comparable': False,
                'reason_code': CURRENT_MISSING,
                'population_change': 'removed',
                'previous': deepcopy(previous_record),
                'current': None,
            }
        elif previous_record is None or current_record is None:
            comparison = {
                'pitcher_id': pitcher_id,
                'comparable': False,
                'reason_code': VALUE_MISSING,
                'population_change': None,
                'previous': deepcopy(previous_record),
                'current': deepcopy(current_record),
            }
        else:
            previous_read = _mapping(previous_record.get('public_read'))
            current_read = _mapping(current_record.get('public_read'))
            previous_mlb_id = previous_record.get('mlb_id')
            current_mlb_id = current_record.get('mlb_id')
            previous_name = previous_record.get('pitcher_name')
            current_name = current_record.get('pitcher_name')
            if not all(
                isinstance(value, str) and value.strip()
                for value in (previous_name, current_name)
            ):
                comparison = {
                    'pitcher_id': pitcher_id,
                    'comparable': False,
                    'reason_code': VALUE_MISSING,
                    'population_change': None,
                    'previous': deepcopy(previous_record),
                    'current': deepcopy(current_record),
                }
            elif (
                previous_mlb_id is not None
                and current_mlb_id is not None
                and previous_mlb_id != current_mlb_id
            ):
                comparison = {
                    'pitcher_id': pitcher_id,
                    'comparable': False,
                    'reason_code': PITCHER_IDENTITY_MISMATCH,
                    'population_change': None,
                    'previous': deepcopy(previous_record),
                    'current': deepcopy(current_record),
                }
            else:
                changed = previous_read.get('key') != current_read.get('key')
                comparison = {
                    'pitcher_id': pitcher_id,
                    'comparable': True,
                    'reason_code': None,
                    'population_change': None,
                    'previous': deepcopy(previous_record),
                    'current': deepcopy(current_record),
                    'movement': changed,
                }
                if changed:
                    movements.append(deepcopy(comparison))
        comparisons.append(comparison)

    return {
        'readiness': DOMAIN_READINESS['arm_read'],
        'status': COMPARABLE,
        'reason_code': None,
        'previous': deepcopy(previous_value),
        'current': deepcopy(current_value),
        'method_version': current_metadata.get('method_version'),
        'public_contract_version': current_metadata.get(
            'public_contract_version'
        ),
        'arm_comparisons': comparisons,
        'movement_candidates': movements,
    }


def _compatible_workload_domain(previous, current, *, window_days):
    domain = f'workload_{window_days}d'
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), domain)
        or not _domain_metadata(_payload(current), domain)
    ):
        # Older sidecars remain valid for domains they already carried. No
        # workload value is reconstructed from historical GameLog rows.
        return _withheld(domain, DOMAIN_NOT_READY)

    base = _compatible_domain(previous, current, domain, domain)
    if base.get('status') != COMPARABLE:
        return base

    previous_metadata = _domain_metadata(_payload(previous), domain)
    current_metadata = _domain_metadata(_payload(current), domain)
    for field in (
        'carrier_contract_version',
        'reference_date_policy',
        'source_authority',
    ):
        if (
            previous_metadata.get(field) in (None, '')
            or current_metadata.get(field) in (None, '')
            or previous_metadata.get(field) != current_metadata.get(field)
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
    if (
        previous_metadata.get('window_days') != window_days
        or current_metadata.get('window_days') != window_days
    ):
        return _withheld(domain, CONTRACT_INCOMPATIBLE)

    previous_date = _payload(previous).get('represented_date')
    current_date = _payload(current).get('represented_date')
    previous_value = base.get('previous')
    current_value = base.get('current')
    if not _valid_workload_window(
        previous_value,
        window_days=window_days,
        represented_date=previous_date,
    ) or not _valid_workload_window(
        current_value,
        window_days=window_days,
        represented_date=current_date,
    ):
        return _withheld(domain, VALUE_MISSING)

    material_fields = (
        'relief_appearances',
        'pitchers_in_relief',
        'pitches_total',
        'appearances_with_pitches',
        'start_relief_unknown',
        # When pitch coverage is partial, the governed known-pitch subtotal is
        # carried only in this backend-authored sentence. It is material data,
        # not presentation regenerated by the comparator.
        'pitches_sentence',
    )
    changed_fields = [
        field
        for field in material_fields
        if previous_value.get(field) != current_value.get(field)
    ]
    base['movement'] = bool(changed_fields)
    base['changed_fields'] = changed_fields
    return base


def _compatible_rotation_domain(previous, current):
    domain = 'rotation_impact'
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), domain)
        or not _domain_metadata(_payload(current), domain)
    ):
        return _withheld(domain, DOMAIN_NOT_READY)
    base = _compatible_domain(previous, current, domain, domain)
    if base.get('status') != COMPARABLE:
        return base
    previous_metadata = _domain_metadata(_payload(previous), domain)
    current_metadata = _domain_metadata(_payload(current), domain)
    expected_population = _canonical_rotation_population_basis()
    for metadata in (previous_metadata, current_metadata):
        if (
            metadata.get('method_version') != ROTATION_IMPACT_METHOD_VERSION
            or metadata.get('contract_version') != TEAM_BOARD_PACKAGE_CONTRACT
            or metadata.get('public_contract_version')
            != ROTATION_IMPACT_PUBLIC_CONTRACT_VERSION
            or metadata.get('carrier_contract_version')
            != ROTATION_IMPACT_CARRIER_CONTRACT
            or metadata.get('source_authority')
            != FROZEN_TEAM_BOARD_SOURCE_AUTHORITY
            or metadata.get('reference_date_policy')
            != ROTATION_IMPACT_REFERENCE_DATE_POLICY
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
        population = metadata.get('population_basis')
        if not isinstance(population, Mapping):
            return _withheld(domain, POPULATION_BASIS_MISSING)
        if dict(population) != expected_population:
            return _withheld(domain, POPULATION_BASIS_MISMATCH)
    for field in (
        'carrier_contract_version', 'reference_date_policy', 'source_authority',
        'window_days',
    ):
        if (
            previous_metadata.get(field) in (None, '')
            or current_metadata.get(field) in (None, '')
            or previous_metadata.get(field) != current_metadata.get(field)
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
    previous_value = _mapping(base.get('previous'))
    current_value = _mapping(base.get('current'))
    previous_reference_date = _as_date(previous_metadata.get('reference_date'))
    current_reference_date = _as_date(current_metadata.get('reference_date'))
    if (
        previous_reference_date is None
        or current_reference_date is None
        or previous_reference_date >= current_reference_date
        or previous_value.get('reference_date')
        != previous_metadata.get('reference_date')
        or current_value.get('reference_date')
        != current_metadata.get('reference_date')
    ):
        return _withheld(domain, REPRESENTED_DATE_INVALID)
    material_fields = (
        'status', 'games_in_window', 'games_analyzed', 'games_excluded',
        'starter_outs', 'starter_avg_outs', 'bullpen_outs_required',
        'short_start_count', 'short_start_rate', 'opener_bulk_games',
        'bullpen_games', 'summary', 'limitations',
    )
    if any(field not in previous_value or field not in current_value for field in material_fields):
        return _withheld(domain, VALUE_MISSING)
    changed_fields = [
        field for field in material_fields
        if previous_value.get(field) != current_value.get(field)
    ]
    base['movement'] = bool(changed_fields)
    base['changed_fields'] = changed_fields
    return base


def _membership_records(value):
    value = _mapping(value)
    member_ids = value.get('member_pitcher_ids')
    members = value.get('members')
    if not isinstance(member_ids, list) or not isinstance(members, list):
        return None
    if any(type(pitcher_id) is not int for pitcher_id in member_ids):
        return None
    if len(member_ids) != len(set(member_ids)):
        return None
    records = {}
    for member in members:
        member = _mapping(member)
        pitcher_id = member.get('pitcher_id')
        if (
            type(pitcher_id) is not int
            or pitcher_id in records
            or not isinstance(member.get('pitcher_name'), str)
            or not member.get('pitcher_name')
        ):
            return None
        records[pitcher_id] = dict(member)
    if set(records) != set(member_ids):
        return None
    return records


def _compatible_membership_domain(previous, current):
    domain = 'bullpen_membership'
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), domain)
        or not _domain_metadata(_payload(current), domain)
    ):
        return _withheld(domain, DOMAIN_NOT_READY)
    base = _compatible_domain(previous, current, domain, domain)
    if base.get('status') != COMPARABLE:
        return base
    previous_metadata = _domain_metadata(_payload(previous), domain)
    current_metadata = _domain_metadata(_payload(current), domain)
    expected_population = _canonical_membership_population_basis()
    for metadata in (previous_metadata, current_metadata):
        if (
            metadata.get('method_version') != BULLPEN_MEMBERSHIP_METHOD_VERSION
            or metadata.get('contract_version') != TEAM_BOARD_PACKAGE_CONTRACT
            or metadata.get('public_contract_version')
            != BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION
            or metadata.get('carrier_contract_version')
            != BULLPEN_MEMBERSHIP_CARRIER_CONTRACT
            or metadata.get('source_authority')
            != FROZEN_TEAM_BOARD_SOURCE_AUTHORITY
            or metadata.get('reference_date_policy')
            != BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
        population = metadata.get('population_basis')
        if not isinstance(population, Mapping):
            return _withheld(domain, POPULATION_BASIS_MISSING)
        if dict(population) != expected_population:
            return _withheld(domain, POPULATION_BASIS_MISMATCH)
    for field in ('carrier_contract_version', 'reference_date_policy', 'source_authority'):
        if (
            previous_metadata.get(field) in (None, '')
            or current_metadata.get(field) in (None, '')
            or previous_metadata.get(field) != current_metadata.get(field)
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
    previous_membership_date = _as_date(
        previous_metadata.get('membership_reference_date')
    )
    current_membership_date = _as_date(
        current_metadata.get('membership_reference_date')
    )
    if (
        previous_membership_date is None
        or current_membership_date is None
        or previous_membership_date >= current_membership_date
    ):
        return _withheld(domain, REPRESENTED_DATE_INVALID)
    previous_records = _membership_records(base.get('previous'))
    current_records = _membership_records(base.get('current'))
    if previous_records is None or current_records is None:
        return _withheld(domain, VALUE_MISSING)
    added_ids = sorted(set(current_records).difference(previous_records))
    removed_ids = sorted(set(previous_records).difference(current_records))
    base['movement'] = bool(added_ids or removed_ids)
    base['added'] = [deepcopy(current_records[pitcher_id]) for pitcher_id in added_ids]
    base['removed'] = [deepcopy(previous_records[pitcher_id]) for pitcher_id in removed_ids]
    return base


def _deployment_records(value):
    value = _mapping(value)
    profiles = value.get('profiles')
    if not isinstance(profiles, list):
        return None
    records = {}
    for raw in profiles:
        profile = _mapping(raw)
        pitcher_id = profile.get('pitcher_id')
        if type(pitcher_id) is not int or pitcher_id in records:
            return None
        records[pitcher_id] = dict(profile)
    return records


def _compatible_deployment_domain(previous, current):
    domain = 'deployment_profile'
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), domain)
        or not _domain_metadata(_payload(current), domain)
    ):
        return _withheld(domain, DOMAIN_NOT_READY)
    base = _compatible_domain(previous, current, domain, domain)
    if base.get('status') != COMPARABLE:
        return base
    previous_metadata = _domain_metadata(_payload(previous), domain)
    current_metadata = _domain_metadata(_payload(current), domain)
    expected_population = {
        'basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
        'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
        'membership_authority': DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
    }
    for metadata in (previous_metadata, current_metadata):
        if (
            metadata.get('method_version') != DEPLOYMENT_PROFILE_METHOD_VERSION
            or metadata.get('contract_version') != TEAM_BOARD_PACKAGE_CONTRACT
            or metadata.get('public_contract_version')
            != DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
            or metadata.get('carrier_contract_version')
            != DEPLOYMENT_PROFILE_CARRIER_CONTRACT
            or metadata.get('reference_date_policy')
            != DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY
            or metadata.get('source_authority')
            != FROZEN_TEAM_BOARD_SOURCE_AUTHORITY
            or metadata.get('window_days') != DEPLOYMENT_PROFILE_WINDOW_DAYS
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
        if dict(_mapping(metadata.get('population_basis'))) != expected_population:
            return _withheld(domain, POPULATION_BASIS_MISMATCH)
    previous_value = _mapping(base.get('previous'))
    current_value = _mapping(base.get('current'))
    if not _valid_deployment_profile(
        previous_value, _payload(previous).get('represented_date')
    ) or not _valid_deployment_profile(
        current_value, _payload(current).get('represented_date')
    ):
        return _withheld(domain, VALUE_MISSING)
    previous_records = _deployment_records(previous_value)
    current_records = _deployment_records(current_value)
    if previous_records is None or current_records is None:
        return _withheld(domain, VALUE_MISSING)
    material_fields = (
        'appearances_analyzed', 'saves', 'holds', 'games_finished',
        'appearances_with_games_finished', 'multi_inning_appearances',
        'appearances_with_outs', 'most_recent_multi_inning_date',
    )
    pitcher_ids = sorted(set(previous_records) | set(current_records))
    changed_pitcher_ids = [
        pitcher_id
        for pitcher_id in pitcher_ids
        if pitcher_id not in previous_records
        or pitcher_id not in current_records
        or any(
            previous_records[pitcher_id].get(field)
            != current_records[pitcher_id].get(field)
            for field in material_fields
        )
    ]
    base['movement'] = bool(changed_pitcher_ids)
    base['changed_pitcher_ids'] = changed_pitcher_ids
    return base


def _compatible_rest_status_domain(previous, current):
    domain = 'rest_status'
    if previous is None:
        return _withheld(domain, PREVIOUS_MISSING)
    if current is None:
        return _withheld(domain, CURRENT_MISSING)
    if (
        not _domain_metadata(_payload(previous), domain)
        or not _domain_metadata(_payload(current), domain)
    ):
        return _withheld(domain, DOMAIN_NOT_READY)
    base = _compatible_domain(previous, current, domain, domain)
    if base.get('status') != COMPARABLE:
        return base
    previous_metadata = _domain_metadata(_payload(previous), domain)
    current_metadata = _domain_metadata(_payload(current), domain)
    for metadata, snapshot in (
        (previous_metadata, previous),
        (current_metadata, current),
    ):
        if (
            metadata.get('method_version') != REST_STATUS_METHOD_VERSION
            or metadata.get('contract_version') != TEAM_BOARD_PACKAGE_CONTRACT
            or metadata.get('public_contract_version')
            != REST_STATUS_PUBLIC_CONTRACT_VERSION
            or metadata.get('reference_date_policy')
            != REST_STATUS_REFERENCE_DATE_POLICY
            or metadata.get('source_authority')
            != FROZEN_TEAM_BOARD_SOURCE_AUTHORITY
            or dict(_mapping(metadata.get('population_basis')))
            != _canonical_rest_status_population_basis()
        ):
            return _withheld(domain, CONTRACT_INCOMPATIBLE)
        represented_date = _as_date(_payload(snapshot).get('represented_date'))
        reference_date = _as_date(metadata.get('availability_reference_date'))
        if (
            represented_date is None
            or reference_date != represented_date + timedelta(days=1)
        ):
            return _withheld(domain, REPRESENTED_DATE_INVALID)
    previous_value = base.get('previous')
    current_value = base.get('current')
    if (
        not is_valid_rest_status_carrier(previous_value)
        or not is_valid_rest_status_carrier(current_value)
        or previous_value.get('available') is not True
        or current_value.get('available') is not True
        or type(previous_value.get('rested_arm_count')) is not int
        or type(current_value.get('rested_arm_count')) is not int
    ):
        return _withheld(domain, VALUE_MISSING)
    base['movement'] = (
        previous_value.get('rested_arm_count')
        != current_value.get('rested_arm_count')
    )
    base['changed_fields'] = ['rested_arm_count'] if base['movement'] else []
    return base


def compare_snapshots(previous, current) -> dict:
    """Return raw values only for domains whose compatibility is proven."""
    previous_payload = _payload(previous)
    current_payload = _payload(current)
    domains = {
        'team_state': _compatible_domain(
            previous, current, 'team_state', 'team_state'
        ),
        'active_arm_count': _compatible_domain(
            previous, current, 'active_arm_count', 'active_arm_count'
        ),
        'arm_read': _compatible_arm_read_domain(previous, current),
        'rest_status': _compatible_rest_status_domain(previous, current),
        'workload_7d': _compatible_workload_domain(
            previous, current, window_days=7
        ),
        'workload_14d': _compatible_workload_domain(
            previous, current, window_days=14
        ),
        'rotation_impact': _compatible_rotation_domain(previous, current),
        'bullpen_membership': _compatible_membership_domain(previous, current),
        'deployment_profile': _compatible_deployment_domain(previous, current),
    }
    for domain, readiness in DOMAIN_READINESS.items():
        if domain in domains:
            continue
        reason = (
            DOMAIN_NOT_READY
            if readiness == READINESS_NOT_YET_COMPARABLE
            else DOMAIN_NOT_INCLUDED
        )
        domains[domain] = _withheld(domain, reason)

    return {
        'capability': CAPABILITY,
        'envelope_version': ENVELOPE_VERSION,
        'comparison': {
            'team_id': current_payload.get('team_id') or previous_payload.get('team_id'),
            'from_represented_date': previous_payload.get('represented_date'),
            'to_represented_date': current_payload.get('represented_date'),
            'previous_delta_snapshot_id': getattr(previous, 'id', None),
            'current_delta_snapshot_id': getattr(current, 'id', None),
        },
        'domains': domains,
    }


def _project_frozen_rest_status(sidecars, *, team_id, session):
    """Read legacy D-055 carriers from their immutable source snapshots.

    This is a read-only bridge for natural publications created after the D-055
    writer rollout but before Gap #31 sidecar stamping. It never recalculates,
    writes, or backfills a historical package.
    """
    source_ids = {
        _mapping(_payload(sidecar).get('source')).get('snapshot_id')
        for sidecar in sidecars
        if not _domain_metadata(_payload(sidecar), 'rest_status')
        and _mapping(_payload(sidecar).get('source')).get('snapshot_authority')
        == 'dashboard_snapshot'
    }
    source_ids.discard(None)
    if not source_ids:
        return list(sidecars)
    source_snapshots = {
        snapshot.id: snapshot
        for snapshot in (
            session.query(DashboardSnapshot)
            .filter(DashboardSnapshot.id.in_(source_ids))
            .all()
        )
    }
    projected = []
    for sidecar in sidecars:
        payload = deepcopy(dict(_payload(sidecar)))
        if not _domain_metadata(payload, 'rest_status'):
            source_id = _mapping(payload.get('source')).get('snapshot_id')
            capture = try_build_rest_status_capture(
                snapshot=source_snapshots.get(source_id),
                team_id=team_id,
            )
            if capture:
                payload.setdefault('domains', {})['rest_status'] = {
                    'method_version': capture.get('method_version'),
                    'contract_version': capture.get('contract_version'),
                    'public_contract_version': capture.get('public_contract_version'),
                    'population_basis': deepcopy(capture.get('population_basis')),
                    'reference_date_policy': capture.get('reference_date_policy'),
                    'availability_reference_date': (
                        capture.get('availability_reference_date')
                    ),
                    'source_authority': capture.get('source_authority'),
                    'trusted': True,
                }
                payload.setdefault('values', {})['rest_status'] = deepcopy(
                    capture.get('value')
                )
        projected.append(SimpleNamespace(
            id=sidecar.id,
            payload=payload,
            data_through=sidecar.data_through,
        ))
    return projected


def resolve_latest_team_state_comparison(
    *, team_id, session=None, current_source_snapshot_id=None,
) -> dict:
    """Compare the latest publication with its nearest compatible predecessor.

    Candidate rows are visited newest first. An incompatible publication is
    never reinterpreted; the resolver only moves farther back to find the
    nearest endpoint that the existing Team State compatibility contract proves
    comparable. If none qualifies, the nearest fail-closed result is returned.
    """
    session = session or db.session
    snapshots = (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.status == 'ready')
        .filter(DashboardSnapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION)
        .filter(DashboardSnapshot.published_at.isnot(None))
        .filter(DashboardSnapshot.source == f'{SNAPSHOT_SOURCE_PREFIX}{int(team_id)}')
        .order_by(
            DashboardSnapshot.data_through.desc(),
            DashboardSnapshot.id.desc(),
        )
        .all()
    )
    artifact_ids = {
        _mapping(_payload(snapshot).get('source')).get('artifact_id')
        for snapshot in snapshots
    }
    artifact_ids.discard(None)
    active_artifact_ids = set()
    if artifact_ids:
        active_artifact_ids = {
            artifact_id
            for artifact_id, in (
                session.query(ShareArtifact.id)
                .filter(ShareArtifact.id.in_(artifact_ids))
                .filter(ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED)
                .all()
            )
        }
    active_snapshots = [
        snapshot
        for snapshot in snapshots
        if _mapping(_payload(snapshot).get('source')).get('artifact_id')
        in active_artifact_ids
    ]
    active_snapshots = _project_frozen_rest_status(
        active_snapshots,
        team_id=int(team_id),
        session=session,
    )
    if current_source_snapshot_id is not None:
        current = next((
            snapshot for snapshot in active_snapshots
            if _mapping(_payload(snapshot).get('source')).get('snapshot_id')
            == int(current_source_snapshot_id)
        ), None)
        latest_represented_date = (
            _as_date(getattr(current, 'data_through', None))
            if current is not None else None
        )
    else:
        latest_represented_date = (
            _as_date(getattr(snapshots[0], 'data_through', None))
            if snapshots else None
        )
        current = next((
            snapshot
            for snapshot in active_snapshots
            if _as_date(getattr(snapshot, 'data_through', None))
            == latest_represented_date
        ), None)
    if current is None:
        return compare_snapshots(None, None)

    nearest_withheld = compare_snapshots(None, current)
    current_date = _as_date(_payload(current).get('represented_date'))
    if current_date is None:
        return nearest_withheld

    candidates = []
    for snapshot in active_snapshots:
        represented_date = _as_date(getattr(snapshot, 'data_through', None))
        if (
            snapshot.id != current.id
            and represented_date is not None
            and represented_date < current_date
        ):
            candidates.append(snapshot)
    for previous in candidates:
        result = compare_snapshots(previous, current)
        if nearest_withheld['domains']['team_state']['status'] == PREVIOUS_MISSING:
            nearest_withheld = result
        if result['domains']['team_state']['status'] == COMPARABLE:
            return result
    return nearest_withheld
