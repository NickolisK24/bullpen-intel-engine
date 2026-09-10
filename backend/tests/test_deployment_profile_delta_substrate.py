from types import SimpleNamespace
from datetime import date, datetime

import pytest

from services.public_serving_authority import TEAM_BOARD_PACKAGE_CONTRACT
from services.public_team_relief_work import (
    DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
    DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
    DEPLOYMENT_PROFILE_METHOD_VERSION,
    DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
    DEPLOYMENT_PROFILE_POPULATION_BASIS,
    DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
    DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
    DEPLOYMENT_PROFILE_WINDOW_DAYS,
)
from services.team_board_delta_substrate import (
    COMPARABLE,
    CONTRACT_INCOMPATIBLE,
    CURRENT_MISSING,
    DOMAIN_NOT_READY,
    FRESHNESS_UNTRUSTED,
    METHOD_VERSION_MISMATCH,
    POPULATION_BASIS_MISMATCH,
    PREVIOUS_MISSING,
    build_deployment_profile_capture,
    build_prospective_envelope,
    compare_snapshots,
)
from team_operations import TEAM_STATE_METHOD_VERSION


TEAM_ID = 110


def _profile(day, *, saves=0, holds=0, multi=0):
    return {
        'contract': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
        'status': 'complete',
        'reason_code': None,
        'data_through': day,
        'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
        'population_basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
        'profiles': [{
            'pitcher_id': 7,
            'pitcher_mlb_id': 7007,
            'pitcher_name': 'Observed Pitcher',
            'appearances_analyzed': 4,
            'saves': saves,
            'holds': holds,
            'games_finished': 1,
            'appearances_with_games_finished': 4,
            'multi_inning_appearances': multi,
            'appearances_with_outs': 4,
            'most_recent_multi_inning_date': day if multi else None,
            'limitations': [],
            'summary': 'Backend-authored observed deployment summary.',
        }],
        'team_summary': {
            'represented_arm_count': 1,
            'pitchers_with_save_or_hold': int(bool(saves or holds)),
            'pitchers_with_multi_inning_appearance': int(bool(multi)),
        },
        'summary': 'Backend-authored team deployment summary.',
        'limitations': [],
    }


def _authority():
    return {
        'method_version': DEPLOYMENT_PROFILE_METHOD_VERSION,
        'public_contract_version': DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION,
        'carrier_contract_version': DEPLOYMENT_PROFILE_CARRIER_CONTRACT,
        'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'population_basis': {
            'basis': DEPLOYMENT_PROFILE_POPULATION_BASIS,
            'population_authority': DEPLOYMENT_PROFILE_POPULATION_AUTHORITY,
            'membership_authority': DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY,
        },
        'reference_date_policy': DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY,
    }


def _publication(day, *, value=None, authority=None):
    value = value or _profile(day)
    authority = authority or _authority()
    authority = {**authority, 'data_through': day}
    return SimpleNamespace(
        id=9,
        data_through=day,
        payload={
            'trusted_team_boards': {
                'contract': TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': day,
                'by_team_id': {
                    str(TEAM_ID): {
                        'team': {'team_id': TEAM_ID},
                        'deployment_profile': value,
                        'deployment_profile_authority': authority,
                    },
                },
            },
        },
    )


def _sidecar(day, *, value=None, authority=None, include=True):
    domains = {
        'team_state': {
            'method_version': 'team_state_method_v1',
            'contract_version': 'team_state_contract_v1',
            'public_contract_version': 'public_team_state_v1',
            'population_basis': {
                'basis': 'active_bullpen',
                'population_authority': 'frozen_population',
                'membership_authority': 'frozen_membership',
            },
            'trusted': True,
        },
    }
    values = {
        'team_state': {
            'public_state': 'fresh',
            'public_label': 'Fresh',
        },
    }
    if include:
        meta = authority or _authority()
        domains['deployment_profile'] = {
            'method_version': meta['method_version'],
            'contract_version': TEAM_BOARD_PACKAGE_CONTRACT,
            'public_contract_version': meta['public_contract_version'],
            'carrier_contract_version': meta['carrier_contract_version'],
            'population_basis': meta['population_basis'],
            'reference_date_policy': meta['reference_date_policy'],
            'source_authority': 'trusted_team_board_publication',
            'window_days': DEPLOYMENT_PROFILE_WINDOW_DAYS,
            'trusted': True,
        }
        values['deployment_profile'] = value or _profile(day)
    return SimpleNamespace(
        id=int(day[-2:]),
        payload={
            'envelope_version': 'team_board_delta_envelope_v1',
            'team_id': TEAM_ID,
            'represented_date': day,
            'source': {
                'artifact_id': int(day[-2:]),
                'snapshot_id': int(day[-2:]),
                'snapshot_authority': 'dashboard_snapshot',
            },
            'domains': domains,
            'values': values,
        },
    )


def test_publication_capture_copies_exact_frozen_profile_and_versions():
    publication = _publication('2026-08-20')
    capture = build_deployment_profile_capture(
        snapshot=publication,
        team_id=TEAM_ID,
    )

    assert capture['value'] == _profile('2026-08-20')
    assert capture['method_version'] == DEPLOYMENT_PROFILE_METHOD_VERSION
    assert capture['public_contract_version'] == DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
    assert capture['carrier_contract_version'] == DEPLOYMENT_PROFILE_CARRIER_CONTRACT

    source = SimpleNamespace(
        team_id=TEAM_ID,
        snapshot=SimpleNamespace(
            data_through=date(2026, 8, 20),
            snapshot_id=91,
            sync_run_id=12,
            subject_type=None,
            subject_key=None,
            is_trusted=True,
        ),
    )
    readiness = {
        'contract_version': TEAM_STATE_METHOD_VERSION,
        'contract_state': 'available',
        'team_state_evidence': {
            'method_version': TEAM_STATE_METHOD_VERSION,
            'basis': 'status_only',
            'active_pitcher_count': 7,
            'trust_state': 'trusted',
            'evidence_references': {
                'population_authority': 'frozen_population',
                'membership_authority': 'frozen_membership',
            },
        },
    }
    artifact = SimpleNamespace(
        id=44,
        render_version='team-state-1.2.0',
        lifecycle_state='published',
        published_at=datetime(2026, 8, 20, 12, 30),
        payload={
            'team_state': {
                'public_state': {
                    'public_code': 'fresh',
                    'public_label': 'Fresh',
                },
            },
        },
    )
    envelope = build_prospective_envelope(
        source=source,
        readiness=readiness,
        artifact=artifact,
        deployment_profile_capture=capture,
    )
    assert envelope['values']['deployment_profile'] == capture['value']
    assert envelope['domains']['deployment_profile']['carrier_contract_version'] == (
        DEPLOYMENT_PROFILE_CARRIER_CONTRACT
    )


def test_deployment_profiles_compare_without_reader_materiality():
    previous = _sidecar('2026-08-19', value=_profile('2026-08-19'))
    current = _sidecar('2026-08-20', value=_profile('2026-08-20', holds=1, multi=1))

    domains = compare_snapshots(previous, current)['domains']
    result = domains['deployment_profile']

    assert result['status'] == COMPARABLE
    assert result['movement'] is True
    assert result['changed_pitcher_ids'] == [7]
    assert domains['workload_7d']['status'] == DOMAIN_NOT_READY


def test_deployment_contract_mismatch_fails_closed():
    previous = _sidecar('2026-08-19')
    bad = {**_authority(), 'carrier_contract_version': 'future_carrier_v2'}
    current = _sidecar('2026-08-20', authority=bad)

    result = compare_snapshots(previous, current)['domains']['deployment_profile']

    assert result['status'] == CONTRACT_INCOMPATIBLE


def test_equal_deployment_profiles_are_comparable_without_movement():
    previous = _sidecar('2026-08-19', value=_profile('2026-08-19'))
    current = _sidecar('2026-08-20', value=_profile('2026-08-20'))

    result = compare_snapshots(previous, current)['domains']['deployment_profile']

    assert result['status'] == COMPARABLE
    assert result['movement'] is False
    assert result['changed_pitcher_ids'] == []


@pytest.mark.parametrize(
    ('previous', 'current', 'expected'),
    [
        (None, _sidecar('2026-08-20'), PREVIOUS_MISSING),
        (_sidecar('2026-08-19'), None, CURRENT_MISSING),
    ],
)
def test_missing_deployment_endpoint_fails_closed(previous, current, expected):
    result = compare_snapshots(previous, current)['domains']['deployment_profile']
    assert result['status'] == expected


@pytest.mark.parametrize(
    ('field', 'value', 'expected'),
    [
        ('method_version', 'future_method', METHOD_VERSION_MISMATCH),
        ('public_contract_version', 'future_public', CONTRACT_INCOMPATIBLE),
        ('carrier_contract_version', 'future_carrier', CONTRACT_INCOMPATIBLE),
        ('reference_date_policy', 'future_reference', CONTRACT_INCOMPATIBLE),
    ],
)
def test_deployment_compatibility_stamps_fail_closed(field, value, expected):
    previous = _sidecar('2026-08-19')
    authority = {**_authority(), field: value}
    current = _sidecar('2026-08-20', authority=authority)

    result = compare_snapshots(previous, current)['domains']['deployment_profile']
    assert result['status'] == expected


def test_deployment_population_and_trust_fail_closed():
    previous = _sidecar('2026-08-19')
    population = _authority()
    population['population_basis'] = {
        **population['population_basis'],
        'basis': 'current_roster',
    }
    current = _sidecar('2026-08-20', authority=population)
    assert (
        compare_snapshots(previous, current)['domains']['deployment_profile']['status']
        == POPULATION_BASIS_MISMATCH
    )

    current = _sidecar('2026-08-20')
    current.payload['domains']['deployment_profile']['trusted'] = False
    assert (
        compare_snapshots(previous, current)['domains']['deployment_profile']['status']
        == FRESHNESS_UNTRUSTED
    )


def test_old_sidecar_is_domain_not_ready_without_invalidating_siblings():
    previous = _sidecar('2026-08-19', include=False)
    current = _sidecar('2026-08-20')

    result = compare_snapshots(previous, current)

    assert result['domains']['deployment_profile']['status'] == DOMAIN_NOT_READY
    assert result['domains']['team_state']['status'] == COMPARABLE
