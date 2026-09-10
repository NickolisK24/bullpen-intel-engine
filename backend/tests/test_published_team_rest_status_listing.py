from types import SimpleNamespace

from services import public_serving_authority
from services import published_team_rest_status_listing as listing


def _snapshot():
    return SimpleNamespace(
        payload={
            public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'by_team_id': {'116': {}, '142': {}},
            },
        },
    )


def _rest_status(team_id):
    rested = 6 if team_id == 116 else 8
    return {
        'available': True,
        'active_arm_count': 8,
        'rested_arm_count': rested,
        'worked_yesterday_count': 8 - rested,
        'back_to_back_count': 0,
        'summary': f'{rested} of 8 active bullpen arms have at least one full day of rest.',
        'reason_code': None,
    }


def test_listing_projects_exact_frozen_rest_status_without_recalculation(monkeypatch):
    snapshot = _snapshot()
    calls = []

    def capture(*, snapshot, team_id):
        calls.append((snapshot, team_id))
        return {'value': _rest_status(team_id)}

    monkeypatch.setattr(listing, 'build_rest_status_capture', capture)
    result = listing.build_published_team_rest_status_listing(
        snapshot_resolver=lambda: (snapshot, None),
    )

    assert result['status'] == 'ok'
    assert result['teams'] == [
        {'team_id': 116, 'rest_status': _rest_status(116)},
        {'team_id': 142, 'rest_status': _rest_status(142)},
    ]
    assert calls == [(snapshot, 116), (snapshot, 142)]


def test_listing_fails_closed_when_trusted_snapshot_is_unavailable():
    result = listing.build_published_team_rest_status_listing(
        snapshot_resolver=lambda: (None, 'publication_not_ready'),
    )

    assert result == {
        'capability': 'published_team_rest_status_listing_v1',
        'status': 'snapshot_unavailable',
        'reason_code': 'publication_not_ready',
        'teams': [],
    }
