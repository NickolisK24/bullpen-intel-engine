from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from flask import Flask

from services import current_bullpen_comparison as comparison
from services import public_serving_authority
from services import public_team_relief_work
from services import rotation_support_pressure
from services import trusted_compare_authority
from services.bullpen_board import (
    REST_STATUS_METHOD_VERSION,
    REST_STATUS_PUBLIC_CONTRACT_VERSION,
)


DATA_THROUGH = '2026-08-24'
REFERENCE_DATE = '2026-08-25'


def _record(pitcher_id, status):
    return {
        'name': f'Pitcher {pitcher_id}',
        'pitcher_id': pitcher_id,
        'fatigue_score': None,
        'workload_facts': {},
        'availability': {
            'availability_status': status,
            'confidence': 'high',
            'data_state': 'fresh',
            'reasons': [],
            'limitations': [],
        },
        'role': {},
        'pitcher_labels': {},
        'public_role_read': {},
        'eligibility': {},
        'roster_status': {},
        'visibility': {'is_visible_by_default': True},
    }


def _team(team_id, abbreviation, statuses):
    records = [_record(team_id * 100 + index, status) for index, status in enumerate(statuses)]
    return {
        'team': {
            'team_id': team_id,
            'team_name': f'Team {abbreviation}',
            'team_abbreviation': abbreviation,
        },
        'records': records,
        'default_pitcher_ids': [record['pitcher_id'] for record in records],
        'roster_authority': {'readiness': {'counts_withheld': False, 'claims_available': True}},
        'rest_status': {
            'available': True,
            'active_arm_count': len(records),
            'rested_arm_count': 2,
            'worked_yesterday_count': 1,
            'back_to_back_count': 0,
            'summary': 'Exact frozen rest summary.',
            'reason_code': None,
        },
        'rest_status_authority': {
            'method_version': REST_STATUS_METHOD_VERSION,
            'public_contract_version': REST_STATUS_PUBLIC_CONTRACT_VERSION,
            'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'availability_reference_date': REFERENCE_DATE,
            'reference_date_policy': 'publication_availability_reference_date',
            'population_basis': {'basis': 'same-publication active bullpen'},
        },
    }


def _snapshot():
    return SimpleNamespace(
        id=88,
        sync_run_id=99,
        data_through=date.fromisoformat(DATA_THROUGH),
        availability_reference_date=date.fromisoformat(REFERENCE_DATE),
        snapshot_generated_at=None,
        published_at=None,
        payload={
            public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': DATA_THROUGH,
                'availability_reference_date': REFERENCE_DATE,
                'by_team_id': {
                    '1': _team(1, 'ACE', ['Available', 'Monitor', 'Avoid']),
                    '2': _team(2, 'BEA', ['Available', 'Limited', 'Unavailable']),
                },
            },
        },
    )


def _state(label):
    return {
        'contract': 'team_state_public_v1',
        'available': True,
        'public_state': label.lower(),
        'public_label': label,
        'summary': 'Exact state summary.',
        'outcome': 'available',
        'unavailable_message': None,
        'reason_code': None,
        'data_through': DATA_THROUGH,
    }


def _workload_capture(team_id, pitches=100):
    return {
        'team_id': team_id,
        'represented_date': DATA_THROUGH,
        'method_version': public_team_relief_work.WORKLOAD_WINDOWS_METHOD_VERSION,
        'public_contract_version': public_team_relief_work.WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
        'reference_date_policy': public_team_relief_work.WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
        'population_basis': {'basis': 'official relief appearances'},
        'windows': {'window_7': {
            'through': DATA_THROUGH,
            'relief_appearances': 8,
            'pitchers_in_relief': 5,
            'pitches_total': pitches,
        }},
    }


def _rotation_capture(team_id):
    return {
        'team_id': team_id,
        'represented_date': DATA_THROUGH,
        'method_version': rotation_support_pressure.VERSION,
        'public_contract_version': rotation_support_pressure.PUBLIC_CONTRACT_VERSION,
        'reference_date_policy': rotation_support_pressure.REFERENCE_DATE_POLICY,
        'population_basis': {'basis': 'completed rotation games'},
        'value': {
            'status': 'moderate',
            'reference_date': REFERENCE_DATE,
            'window_days': 7,
            'games_analyzed': 4,
            'short_start_count': 2,
            'bullpen_innings_required': 14.0,
            'limitations': [],
        },
    }


def _install_owners(monkeypatch, *, pitches_a=100, pitches_b=0):
    monkeypatch.setattr(
        comparison.authority,
        '_published_team_state',
        lambda _snapshot, team_id: _state('Fresh' if team_id == 1 else 'Stretched'),
    )
    monkeypatch.setattr(
        comparison,
        'try_build_workload_window_capture',
        lambda snapshot, team_id: _workload_capture(team_id, pitches_a if team_id == 1 else pitches_b),
    )
    monkeypatch.setattr(
        comparison,
        'try_build_rotation_impact_capture',
        lambda snapshot, team_id: _rotation_capture(team_id),
    )


def test_exact_canonical_domains_project_without_full_board_payload(monkeypatch):
    _install_owners(monkeypatch)
    carrier, reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    assert reason is None
    assert carrier['status'] == 'available'
    assert carrier['teams']['team_a']['team_board_href'] == '/bullpen?view=board&team=ACE&source=comparison'
    assert carrier['domains']['team_state']['team_a']['public_label'] == 'Fresh'
    assert carrier['domains']['rest']['team_a'] == {
        'rested_options': 2, 'worked_yesterday': 1, 'back_to_back': 0,
    }
    assert carrier['domains']['workload']['team_a']['pitches'] == 100
    assert carrier['domains']['workload']['team_b']['pitches'] == 0
    assert carrier['domains']['rotation']['team_a']['short_starts'] == 2
    assert carrier['domains']['availability']['team_a']['unavailable'] == 1
    assert carrier['domains']['availability']['team_b']['unavailable'] == 1
    assert 'groups' not in carrier['teams']['team_a']
    assert 'context' not in carrier['teams']['team_a']


def test_missing_workload_is_withheld_for_both_while_other_domains_survive(monkeypatch):
    _install_owners(monkeypatch)
    monkeypatch.setattr(
        comparison,
        'try_build_workload_window_capture',
        lambda snapshot, team_id: None if team_id == 1 else _workload_capture(team_id),
    )
    carrier, _reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    workload = carrier['domains']['workload']
    assert workload['status'] == 'withheld'
    assert workload['team_a'] is None
    assert workload['team_b'] is None
    assert carrier['domains']['rest']['status'] == 'available'
    assert carrier['domains']['rotation']['status'] == 'available'


def test_optional_owner_exception_withholds_only_its_domain(monkeypatch):
    _install_owners(monkeypatch)

    def state(_snapshot, team_id):
        if team_id == 1:
            raise RuntimeError('optional Team State read failed')
        return _state('Stretched')

    monkeypatch.setattr(comparison.authority, '_published_team_state', state)
    carrier, _reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    assert carrier['domains']['team_state']['status'] == 'withheld'
    assert carrier['domains']['rest']['status'] == 'available'
    assert carrier['domains']['workload']['status'] == 'available'
    assert carrier['domains']['rotation']['status'] == 'available'
    assert carrier['domains']['availability']['status'] == 'available'


def test_mismatched_reference_withholds_only_rotation(monkeypatch):
    _install_owners(monkeypatch)

    def rotation(snapshot, team_id):
        value = _rotation_capture(team_id)
        if team_id == 2:
            value['value']['reference_date'] = '2026-08-23'
        return value

    monkeypatch.setattr(comparison, 'try_build_rotation_impact_capture', rotation)
    carrier, _reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    assert carrier['domains']['rotation']['status'] == 'withheld'
    assert carrier['domains']['rotation']['reason_code'] == 'comparison_authority_mismatch'
    assert carrier['domains']['workload']['status'] == 'available'


def test_partial_rotation_limitations_pass_through_without_hiding_values(monkeypatch):
    _install_owners(monkeypatch)

    def rotation(snapshot, team_id):
        value = _rotation_capture(team_id)
        if team_id == 1:
            value['value']['status'] = 'limited_read'
            value['value']['limitations'] = [
                'One completed game lacks full split coverage.'
            ]
        return value

    monkeypatch.setattr(comparison, 'try_build_rotation_impact_capture', rotation)
    carrier, _reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    assert carrier['status'] == 'partial'
    assert carrier['domains']['rotation']['status'] == 'partial'
    assert carrier['domains']['rotation']['team_a']['short_starts'] == 2
    assert carrier['domains']['rotation']['limitations'] == [
        'One completed game lacks full split coverage.'
    ]


def test_null_pitch_evidence_stays_null_and_valid_zero_stays_zero(monkeypatch):
    _install_owners(monkeypatch, pitches_a=None, pitches_b=0)
    carrier, _reason = comparison.build_current_bullpen_comparison(_snapshot(), 1, 2)

    assert carrier['domains']['workload']['team_a']['pitches'] is None
    assert carrier['domains']['workload']['team_b']['pitches'] == 0


def test_trusted_route_selects_snapshot_once_and_never_builds_boards(monkeypatch):
    _install_owners(monkeypatch)
    calls = []
    snapshot = _snapshot()
    monkeypatch.setattr(
        trusted_compare_authority.authority.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: calls.append('snapshot') or snapshot,
    )
    app = Flask(__name__)
    with app.test_request_context('/api/bullpen/teams/compare?team_a=1&team_b=2'):
        response = trusted_compare_authority.trusted_team_compare_view()
        body = response.get_json()

    assert calls == ['snapshot']
    assert body['comparison']['capability'] == comparison.CAPABILITY
    assert 'team_a' not in body
    assert 'team_b' not in body


def test_installed_public_route_uses_compact_projection_without_board_builds(monkeypatch):
    _install_owners(monkeypatch)
    snapshot = _snapshot()
    calls = []
    monkeypatch.setattr(
        public_serving_authority.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: calls.append('snapshot') or snapshot,
    )
    monkeypatch.setattr(
        public_serving_authority,
        'build_published_team_board',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('full board rebuilt')),
    )
    app = Flask(__name__)
    with app.test_request_context('/api/bullpen/teams/compare?team_a=1&team_b=2'):
        response = public_serving_authority.trusted_team_compare_view()
        body = response.get_json()

    assert calls == ['snapshot']
    assert body['comparison']['domains']['rest']['status'] == 'available'
    assert 'team_a' not in body
    assert 'team_b' not in body


def test_source_has_no_board_reconstruction_or_winner_fields():
    source = open(trusted_compare_authority.__file__, encoding='utf-8').read()
    assert 'build_board_payload' not in source
    assert '_board_from_snapshot' not in source
    carrier_source = open(comparison.__file__, encoding='utf-8').read().lower()
    for forbidden in ('winner', 'advantage', 'recommendation', "'score'", "'rank'"):
        assert forbidden not in carrier_source
