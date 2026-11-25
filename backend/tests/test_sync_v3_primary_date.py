from datetime import date

import pytest

from sync_v3.primary_date import workload_cutoff


def test_postgame_advances_only_after_the_competitive_slate_settles():
    yesterday, today = date(2026, 8, 28), date(2026, 8, 29)
    games = {1:(yesterday, {'status_state':'final'}, {}),
             2:(today, {'status_state':'final'}, {'status': {'statusCode': 'F'}}),
             3:(today, {'status_state':'other'}, {'status': {'statusCode': 'I'}})}
    assert workload_cutoff(games, today, after_finals=False) == yesterday
    assert workload_cutoff(games, today, after_finals=True) == yesterday
    games[3][2]['status'] = {'statusCode': 'C', 'detailedState': 'Cancelled'}
    assert workload_cutoff(games, today, after_finals=True) == today
    assert workload_cutoff(games, today, after_finals=False) == yesterday
    assert workload_cutoff(games, date(2026,11,25), after_finals=False) == today


def test_a_future_game_cannot_supply_workload():
    with pytest.raises(ValueError, match='No confirmed'):
        workload_cutoff({1:(date(2026,8,29),{'status_state':'final'}, {})},
                        date(2026,8,28), after_finals=True)
