from datetime import date
from hashlib import sha256

import pytest

from sync_v3 import editorial_reads
from sync_v3.evidence import encode_json


@pytest.mark.parametrize('case,expected', [
    ('both_windows', 'complete_comparison_windows'),
    ('missing_day', 'incomplete_comparison_calendar'),
    ('missing_name', 'missing_official_reliever_identity'),
    ('missing_pitches', 'incomplete_workload_or_ambiguous_boxscore'),
    ('empty_window', 'insufficient_comparable_workload'),
])
def test_frozen_workload_core_requires_two_supported_windows(monkeypatch, case, expected):
    player = dict(id=19, fullName='Fixture Reliever')
    if case == 'missing_name':
        del player['fullName']
    encoded = encode_json(dict(teams=dict(home=dict(team=dict(id=111), players=dict(ID19=dict(person=player))))))
    sha = sha256(encoded).hexdigest()
    lines = [dict(game_date='2024-08-05', mlb_id=19, pitches_thrown=15, boxscore_digests=[sha])]
    if case != 'empty_window':
        lines.append(dict(lines[0], game_date='2024-07-27', pitches_thrown=10))
    if case == 'missing_pitches':
        lines[1]['pitches_thrown'] = None
    ledger = dict(citation=dict(facts_digest='fixture'), appearances=lines,
                  gaps={'2024-07-25' if case == 'missing_day' else '2024-07-10': 'missing_schedule'})
    monkeypatch.setattr(editorial_reads, 'appearance_ledger', lambda *args: ledger)

    class PayloadCursor:
        def execute(self, sql, args):
            assert args == ([sha],)

        def __iter__(self):
            return iter([(sha, encoded)])

    layer, status, citation = editorial_reads._stability(PayloadCursor(), 'fixture', 111, date(2024, 8, 7))
    assert status == expected
    assert citation == dict(start='2024-07-19', through='2024-08-07', facts_digest='fixture')
    if case == 'both_windows':
        assert layer['core_stability_pct'] == 100
        assert (layer['current_workload_total_10d'], layer['previous_workload_total_10d']) == (15, 10)
    else:
        assert layer is None
