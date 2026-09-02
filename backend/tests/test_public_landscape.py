"""F-007: public Landscape has one trusted publication authority."""

from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace

import pytest

import api.bullpen as bullpen_api
from services import dashboard_snapshot
from services.mlb_club_directory import MLB_CLUBS
from services.public_landscape import (
    LANDSCAPE_AUTHORITY_INVALID,
    LANDSCAPE_INCOMPLETE,
    LANDSCAPE_TEAM_STATE_INCOMPLETE,
    build_public_landscape,
)
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_CONTRACT


DATA_THROUGH = date(2026, 8, 31)
REFERENCE_DATE = date(2026, 9, 1)


def _state(label='Fresh'):
    return {
        'contract': PUBLIC_TEAM_STATE_CONTRACT,
        'available': True,
        'public_state': label.lower(),
        'public_label': label,
        'summary': 'Published Team State summary.',
        'outcome': 'available',
        'unavailable_message': None,
        'reason_code': None,
        'data_through': DATA_THROUGH.isoformat(),
    }


def _listing(*, missing_team_id=None, contract=PUBLIC_TEAM_STATE_CONTRACT):
    teams = []
    labels = ('Fresh', 'Stretched', 'Vulnerable')
    for index, club in enumerate(MLB_CLUBS):
        state = _state(labels[index % len(labels)])
        state['contract'] = contract
        if club.team_id == missing_team_id:
            state.update(available=False, public_state=None, public_label=None)
        teams.append({
            'team_id': club.team_id,
            'team_abbreviation': club.abbreviation,
            'team_name': club.team_name,
            'team_state': state,
        })
    represented = sum(1 for row in teams if row['team_state']['available'])
    return {
        'status': 'ok',
        'team_count': len(teams),
        'represented_team_count': represented,
        'teams': teams,
        'freshness': {
            'data_through': DATA_THROUGH.isoformat(),
            'freshness_state': 'current',
        },
    }


def _landscape():
    first, second, third = MLB_CLUBS[:3]
    return {
        'capability': 'tonights_bullpen_landscape',
        'ranking_applied': False,
        'selection_made': False,
        'reference_date': REFERENCE_DATE.isoformat(),
        'teams_evaluated': 30,
        'games': {'available': True, 'data_state': 'current'},
        'constrained_bullpens': [{
            'team_id': first.team_id,
            'team_state': {'public_label': 'legacy competing value'},
        }],
        'available_bullpens': [{'team_id': second.team_id}],
        'monitoring_concentration': [{'team_id': third.team_id}],
        'freshness': {'data_through': DATA_THROUGH.isoformat()},
        'notes': ['Published landscape note.'],
    }


def _snapshot(*, landscape=None, payload_version=None):
    return SimpleNamespace(
        id=707,
        sync_run_id=808,
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
        is_published=True,
        published_at=datetime(2026, 9, 1, 9, 10),
        payload_version=(
            dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION
            if payload_version is None
            else payload_version
        ),
        data_through=DATA_THROUGH,
        availability_reference_date=REFERENCE_DATE,
        snapshot_generated_at=datetime(2026, 9, 1, 9, 0),
        payload={
            'landscape': _landscape() if landscape is None else landscape,
            'freshness': {
                'data_through': DATA_THROUGH.isoformat(),
                'availability_reference_date': REFERENCE_DATE.isoformat(),
            },
        },
    )


def _build(snapshot, listing=None):
    listing = deepcopy(listing or _listing())
    calls = []

    def builder(**kwargs):
        calls.append(kwargs)
        selected, reason = kwargs['snapshot_resolver']()
        assert selected is snapshot
        assert reason is None
        return deepcopy(listing)

    return build_public_landscape(
        snapshot,
        team_state_listing_builder=builder,
    ), calls


@pytest.fixture(autouse=True)
def trusted_snapshot_policy(monkeypatch):
    monkeypatch.setattr(
        dashboard_snapshot,
        'snapshot_unavailable_reason',
        lambda snapshot: None if snapshot is not None else 'dashboard_snapshot_missing',
    )


def test_valid_publication_projects_one_complete_governed_landscape():
    snapshot = _snapshot()
    payload, calls = _build(snapshot)

    assert payload['status'] == 'ok'
    assert payload['teams_evaluated'] == 30
    assert payload['expected_team_count'] == 30
    assert payload['team_count'] == 30
    assert payload['represented_team_count'] == 30
    assert len(payload['teams']) == 30
    assert len({row['team_id'] for row in payload['teams']}) == 30
    assert calls and calls[0]['directory_loader']() == {}


def test_landscape_and_dashboard_expose_the_same_publication_identity():
    snapshot = _snapshot()
    landscape, _calls = _build(snapshot)
    dashboard = bullpen_api._dashboard_payload_with_snapshot_metadata(
        snapshot.payload,
        'cache',
        snapshot=snapshot,
    )

    for key in (
        'snapshot_id',
        'sync_run_id',
        'data_through',
        'availability_reference_date',
        'snapshot_generated_at',
        'published_at',
        'payload_version',
    ):
        assert landscape['snapshot'][key] == dashboard['snapshot'][key]


def test_lane_team_states_are_exact_published_projections_not_stored_substitutes():
    snapshot = _snapshot()
    listing = _listing()
    payload, _calls = _build(snapshot, listing)
    state_by_team = {row['team_id']: row['team_state'] for row in listing['teams']}

    for lane in (
        'constrained_bullpens',
        'available_bullpens',
        'monitoring_concentration',
    ):
        for entry in payload[lane]:
            assert entry['team_state'] == state_by_team[entry['team_id']]
            assert entry['team_state']['public_label'] != 'legacy competing value'


def test_missing_publication_fails_closed_without_a_team_denominator():
    payload = build_public_landscape(None)

    assert payload['status'] == 'snapshot_unavailable'
    assert payload['reason'] == 'dashboard_snapshot_missing'
    assert payload['teams_evaluated'] is None
    assert payload['teams'] is None
    assert payload['available_bullpens'] is None
    assert payload['publication_authority'] is None


def test_incomplete_landscape_is_withheld_without_live_patching():
    landscape = _landscape()
    landscape['teams_evaluated'] = 29
    payload, calls = _build(_snapshot(landscape=landscape))

    assert payload['status'] == 'snapshot_unavailable'
    assert payload['reason'] == LANDSCAPE_INCOMPLETE
    assert payload['teams'] is None
    assert calls == []


def test_reference_date_mismatch_is_an_invalid_authority():
    landscape = _landscape()
    landscape['reference_date'] = '2026-08-30'
    payload, calls = _build(_snapshot(landscape=landscape))

    assert payload['status'] == 'snapshot_unavailable'
    assert payload['reason'] == LANDSCAPE_AUTHORITY_INVALID
    assert calls == []


@pytest.mark.parametrize(
    'listing',
    [
        _listing(missing_team_id=MLB_CLUBS[0].team_id),
        _listing(contract='obsolete_team_state_contract'),
    ],
)
def test_incomplete_or_incompatible_governed_team_states_fail_closed(listing):
    payload, _calls = _build(_snapshot(), listing)

    assert payload['status'] == 'snapshot_unavailable'
    assert payload['reason'] == LANDSCAPE_TEAM_STATE_INCOMPLETE
    assert payload['teams'] is None


def test_snapshot_method_version_mismatch_fails_before_projection(monkeypatch):
    snapshot = _snapshot(payload_version=999)
    monkeypatch.setattr(
        dashboard_snapshot,
        'snapshot_unavailable_reason',
        lambda _snapshot: 'dashboard_snapshot_version_mismatch',
    )
    payload, calls = _build(snapshot)

    assert payload['status'] == 'snapshot_unavailable'
    assert payload['reason'] == 'dashboard_snapshot_version_mismatch'
    assert calls == []


def test_stale_but_still_governed_publication_preserves_explicit_currentness():
    listing = _listing()
    listing['freshness'] = {
        'data_through': DATA_THROUGH.isoformat(),
        'freshness_state': 'stale',
        'reason_codes': ['serving_previous_published_view'],
    }
    payload, _calls = _build(_snapshot(), listing)

    assert payload['status'] == 'ok'
    assert payload['snapshot']['snapshot_id'] == 707
    assert payload['freshness'] == listing['freshness']


def test_repeated_reads_project_the_frozen_publication_without_mutable_derivation():
    snapshot = _snapshot()
    listing = _listing()
    calls = []

    def builder(**kwargs):
        calls.append(kwargs['snapshot_resolver']()[0].id)
        return deepcopy(listing)

    first = build_public_landscape(snapshot, team_state_listing_builder=builder)
    second = build_public_landscape(snapshot, team_state_listing_builder=builder)

    assert first == second
    assert calls == [snapshot.id, snapshot.id]
    assert first['publication_authority']['snapshot_id'] == snapshot.id


def test_dashboard_carries_the_same_projection_without_losing_other_domains(monkeypatch):
    snapshot = _snapshot()
    landscape, _calls = _build(snapshot)
    snapshot.payload.update({
        'capability': 'bullpen_dashboard',
        'context': {'health': {'state': 'published'}},
        'what_changed_since_yesterday': {'state': 'available'},
    })
    monkeypatch.setattr(
        bullpen_api.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        bullpen_api,
        'build_public_landscape',
        lambda selected: deepcopy(landscape) if selected is snapshot else None,
    )

    payload = bullpen_api.bullpen_dashboard_response_payload()

    assert payload['snapshot']['snapshot_id'] == snapshot.id
    assert payload['landscape']['snapshot']['snapshot_id'] == snapshot.id
    assert payload['landscape']['teams'] == landscape['teams']
    assert payload['context'] == {'health': {'state': 'published'}}
    assert payload['what_changed_since_yesterday'] == {'state': 'available'}


def test_invalid_landscape_is_withheld_only_inside_an_otherwise_healthy_dashboard(
    monkeypatch,
):
    snapshot = _snapshot()
    snapshot.payload.update({
        'capability': 'bullpen_dashboard',
        'context': {'health': {'state': 'published'}},
    })
    monkeypatch.setattr(
        bullpen_api.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: snapshot,
    )
    monkeypatch.setattr(
        bullpen_api,
        'build_public_landscape',
        lambda _snapshot: {
            'capability': 'tonights_bullpen_landscape',
            'status': 'snapshot_unavailable',
            'reason': LANDSCAPE_INCOMPLETE,
        },
    )

    payload = bullpen_api.bullpen_dashboard_response_payload()

    assert payload['capability'] == 'bullpen_dashboard'
    assert payload['snapshot']['snapshot_id'] == snapshot.id
    assert payload['context'] == {'health': {'state': 'published'}}
    assert payload['landscape']['status'] == 'snapshot_unavailable'
    assert payload['landscape']['reason'] == LANDSCAPE_INCOMPLETE


def test_dashboard_live_fallback_cannot_feed_home_a_mutable_landscape(monkeypatch):
    monkeypatch.setattr(
        bullpen_api.dashboard_snapshot_service,
        'get_latest_valid_dashboard_snapshot',
        lambda: None,
    )
    monkeypatch.setattr(
        bullpen_api.dashboard_snapshot_service,
        'get_latest_dashboard_snapshot_record',
        lambda: None,
    )
    monkeypatch.setattr(bullpen_api, '_dashboard_live_fallback_enabled', lambda: True)
    monkeypatch.setattr(
        bullpen_api,
        '_mutable_landscape_allowed_for_nonproduction_validation',
        lambda: False,
    )
    monkeypatch.setattr(
        bullpen_api,
        'build_bullpen_dashboard_payload',
        lambda: {
            'capability': 'bullpen_dashboard',
            'context': {'health': {'state': 'live_non_landscape_domain'}},
            'landscape': {
                'capability': 'tonights_bullpen_landscape',
                'teams_evaluated': 30,
            },
        },
    )

    payload = bullpen_api.bullpen_dashboard_response_payload()

    assert payload['snapshot']['served_from'] == 'live_fallback'
    assert payload['context'] == {'health': {'state': 'live_non_landscape_domain'}}
    assert payload['landscape']['status'] == 'snapshot_unavailable'
    assert payload['landscape']['reason'] == 'dashboard_snapshot_missing'
    assert payload['landscape']['teams_evaluated'] is None
