"""Contract tests for the frozen seven-day Team Board workload listing."""

from datetime import date
from types import SimpleNamespace

from services import public_serving_authority
from services import public_team_relief_work as relief
from services import published_team_workload_listing as listing


DATA_THROUGH = '2026-06-25'


def _window(*, pitches=121, appearances=8, pitchers=5):
    return {
        'through': DATA_THROUGH,
        'relief_appearances': appearances,
        'pitchers_in_relief': pitchers,
        'pitches_total': pitches,
        'appearances_with_pitches': appearances if pitches is not None else 0,
        'start_relief_unknown': 0,
        'sentence': 'Exact canonical appearance sentence.',
        'pitchers_sentence': 'Exact canonical pitcher sentence.',
        'pitches_sentence': 'Exact canonical pitch sentence.',
    }


def _team(team_id, *, window=None):
    carrier = {
        'contract': relief.WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': relief.WORKLOAD_WINDOWS_COMPLETE,
        'reason_code': None,
        'data_through': DATA_THROUGH,
        'windows': {'window_7': window or _window(), 'window_14': {}},
    }
    return {
        'team': {'team_id': team_id},
        'workload_windows': carrier,
        'workload_windows_authority': {
            'method_version': relief.WORKLOAD_WINDOWS_METHOD_VERSION,
            'public_contract_version': relief.WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
            'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'population_basis': {
                'basis': relief.WORKLOAD_WINDOWS_POPULATION_BASIS,
                'population_authority': relief.WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
                'membership_authority': relief.WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY,
            },
            'reference_date_policy': relief.WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
            'data_through': DATA_THROUGH,
        },
    }


def _snapshot(teams):
    return SimpleNamespace(
        id=44,
        data_through=date.fromisoformat(DATA_THROUGH),
        payload={
            public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': DATA_THROUGH,
                'by_team_id': {str(team_id): team for team_id, team in teams.items()},
            },
        },
    )


def _build(snapshot):
    calls = []

    def resolver():
        calls.append('called')
        return snapshot, None

    return listing.build_published_team_workload_listing(
        snapshot_resolver=resolver,
    ), calls


def test_exact_frozen_window_passes_through_from_one_snapshot_read():
    source_window = _window(pitches=137, appearances=9, pitchers=6)
    result, calls = _build(_snapshot({116: _team(116, window=source_window)}))

    assert calls == ['called']
    assert result['status'] == 'ok'
    carrier = result['teams'][0]['recent_bullpen_volume']
    assert carrier['contract'] == relief.WORKLOAD_WINDOWS_CARRIER_CONTRACT
    assert carrier['status'] == 'complete'
    assert carrier['data_through'] == DATA_THROUGH
    assert carrier['window_days'] == 7
    assert carrier['window'] == source_window


def test_null_pitch_evidence_remains_null_and_legitimate_zero_remains_zero():
    result, _ = _build(_snapshot({
        116: _team(116, window=_window(pitches=None)),
        142: _team(142, window=_window(pitches=0, appearances=0, pitchers=0)),
    }))
    rows = {row['team_id']: row['recent_bullpen_volume'] for row in result['teams']}

    assert rows[116]['window']['pitches_total'] is None
    assert rows[142]['window']['relief_appearances'] == 0
    assert rows[142]['window']['pitchers_in_relief'] == 0
    assert rows[142]['window']['pitches_total'] == 0


def test_invalid_team_authority_is_withheld_without_affecting_other_teams():
    invalid = _team(116)
    invalid['workload_windows_authority']['method_version'] = 'wrong'
    result, _ = _build(_snapshot({116: invalid, 142: _team(142)}))
    rows = {row['team_id']: row['recent_bullpen_volume'] for row in result['teams']}

    assert rows[116]['status'] == 'withheld'
    assert rows[116]['window'] is None
    assert rows[142]['status'] == 'complete'


def test_snapshot_unavailable_returns_no_reconstructed_or_zero_workload():
    result = listing.build_published_team_workload_listing(
        snapshot_resolver=lambda: (None, 'snapshot_not_ready'),
    )

    assert result['status'] == 'snapshot_unavailable'
    assert result['reason_code'] == 'snapshot_not_ready'
    assert result['teams'] == []
