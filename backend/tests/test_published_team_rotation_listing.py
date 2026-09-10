from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from services import public_serving_authority
from services import rotation_support_pressure
from services.published_team_rotation_listing import (
    CARRIER_CONTRACT,
    REASON_AUTHORITY_INVALID,
    STATUS_AVAILABLE,
    STATUS_PARTIAL,
    STATUS_WITHHELD,
    build_published_team_rotation_listing,
)


TEAM_ID = 147
REFERENCE_DATE = '2026-08-24'
DATA_THROUGH = date(2026, 8, 23)


def _rotation(**overrides):
    value = {
        'capability': rotation_support_pressure.CAPABILITY,
        'version': rotation_support_pressure.VERSION,
        'team_id': TEAM_ID,
        'status': rotation_support_pressure.STATUS_MODERATE,
        'reference_date': REFERENCE_DATE,
        'window_days': 7,
        'games_in_window': 5,
        'games_analyzed': 4,
        'games_excluded': 1,
        'starter_outs': 54,
        'bullpen_outs_required': 42,
        'bullpen_innings_required': 14.0,
        'short_start_count': 2,
        'summary': 'The rotation transferred 14.0 bullpen innings.',
        'limitations': [],
        'limitation_reasons': [],
    }
    value.update(overrides)
    return value


def _authority(**overrides):
    value = {
        'method_version': rotation_support_pressure.VERSION,
        'public_contract_version': rotation_support_pressure.PUBLIC_CONTRACT_VERSION,
        'carrier_contract_version': rotation_support_pressure.DELTA_CARRIER_CONTRACT,
        'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
        'population_basis': {
            'basis': rotation_support_pressure.POPULATION_BASIS,
            'population_authority': rotation_support_pressure.POPULATION_AUTHORITY,
            'membership_authority': rotation_support_pressure.MEMBERSHIP_AUTHORITY,
        },
        'reference_date_policy': rotation_support_pressure.REFERENCE_DATE_POLICY,
        'reference_date': REFERENCE_DATE,
    }
    value.update(overrides)
    return value


def _snapshot(rotation=None, authority=None):
    team = {
        'team': {'team_id': TEAM_ID, 'team_abbreviation': 'NYY'},
        'rotation_support_pressure': deepcopy(rotation or _rotation()),
        'rotation_support_pressure_authority': deepcopy(authority or _authority()),
    }
    return SimpleNamespace(
        data_through=DATA_THROUGH,
        payload={
            public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': DATA_THROUGH.isoformat(),
                'availability_reference_date': REFERENCE_DATE,
                'by_team_id': {str(TEAM_ID): team},
            },
        },
    )


def _build(snapshot):
    calls = {'count': 0}

    def resolver():
        calls['count'] += 1
        return snapshot, None

    return build_published_team_rotation_listing(snapshot_resolver=resolver), calls


def test_projects_only_exact_canonical_rotation_facts_from_one_snapshot():
    result, calls = _build(_snapshot())

    assert calls['count'] == 1
    carrier = result['teams'][0]['rotation_context']
    assert carrier == {
        'contract': CARRIER_CONTRACT,
        'source_contract': rotation_support_pressure.DELTA_CARRIER_CONTRACT,
        'status': STATUS_AVAILABLE,
        'reason_code': None,
        'reference_date': REFERENCE_DATE,
        'window_days': 7,
        'short_start_count': 2,
        'bullpen_innings_required': 14.0,
    }
    assert 'summary' not in carrier
    assert 'starter_avg_innings' not in carrier


def test_partial_owner_status_and_reason_pass_through_without_hiding_facts():
    result, _calls = _build(_snapshot(rotation=_rotation(
        status=rotation_support_pressure.STATUS_LIMITED,
        limitations=['Some completed games lack complete splits.'],
        limitation_reasons=['partial_source_coverage'],
    )))

    carrier = result['teams'][0]['rotation_context']
    assert carrier['status'] == STATUS_PARTIAL
    assert carrier['reason_code'] == 'partial_source_coverage'
    assert carrier['short_start_count'] == 2
    assert carrier['bullpen_innings_required'] == 14.0


def test_missing_sample_stays_missing_while_governed_zero_survives():
    missing, _calls = _build(_snapshot(rotation=_rotation(
        status=rotation_support_pressure.STATUS_LIMITED,
        games_analyzed=0,
        starter_outs=0,
        bullpen_outs_required=0,
        bullpen_innings_required=0.0,
        short_start_count=0,
        limitations=['Fewer than three trustworthy rotation starts are available.'],
        limitation_reasons=['insufficient_trustworthy_games'],
    )))
    missing_carrier = missing['teams'][0]['rotation_context']
    assert missing_carrier['short_start_count'] is None
    assert missing_carrier['bullpen_innings_required'] is None

    zero, _calls = _build(_snapshot(rotation=_rotation(
        bullpen_outs_required=0,
        bullpen_innings_required=0.0,
        short_start_count=0,
    )))
    zero_carrier = zero['teams'][0]['rotation_context']
    assert zero_carrier['short_start_count'] == 0
    assert zero_carrier['bullpen_innings_required'] == 0.0


def test_invalid_frozen_authority_is_withheld_without_recalculation():
    result, _calls = _build(_snapshot(authority=_authority(
        reference_date_policy='wrong_policy',
    )))

    carrier = result['teams'][0]['rotation_context']
    assert carrier['status'] == STATUS_WITHHELD
    assert carrier['reason_code'] == REASON_AUTHORITY_INVALID
    assert carrier['short_start_count'] is None
    assert carrier['bullpen_innings_required'] is None


def test_one_invalid_team_carrier_does_not_withhold_a_healthy_team():
    snapshot = _snapshot()
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    invalid_team = deepcopy(package['by_team_id'][str(TEAM_ID)])
    invalid_team['team']['team_id'] = 142
    invalid_team['rotation_support_pressure']['team_id'] = 142
    invalid_team['rotation_support_pressure_authority'][
        'reference_date_policy'
    ] = 'wrong_policy'
    package['by_team_id']['142'] = invalid_team

    result, _calls = _build(snapshot)
    contexts = {
        row['team_id']: row['rotation_context']
        for row in result['teams']
    }

    assert contexts[TEAM_ID]['status'] == STATUS_AVAILABLE
    assert contexts[TEAM_ID]['short_start_count'] == 2
    assert contexts[142]['status'] == STATUS_WITHHELD
    assert contexts[142]['short_start_count'] is None


def test_missing_snapshot_returns_one_local_listing_failure():
    result = build_published_team_rotation_listing(
        snapshot_resolver=lambda: (None, 'snapshot_read_failed'),
    )

    assert result['status'] == 'snapshot_unavailable'
    assert result['reason_code'] == 'snapshot_read_failed'
    assert result['teams'] == []


def test_listing_uses_frozen_capture_without_raw_rotation_recalculation():
    source = Path(
        'services/published_team_rotation_listing.py'
    ).read_text(encoding='utf-8')

    assert 'build_rotation_impact_capture' in source
    assert 'build_team_rotation_support_pressure' not in source
    assert 'GameLog' not in source
    assert 'team_game_pitching_splits' not in source
