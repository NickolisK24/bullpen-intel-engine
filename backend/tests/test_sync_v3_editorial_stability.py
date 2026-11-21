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


def test_concentration_requires_every_relief_pitch_count_in_its_own_window():
    day = date(2024, 8, 7)
    arm = dict(game_date='2024-08-07', games_started=0, game_type='R', mlb_game_pk=1, player_id=12,
               pitcher_name='One', pitches_thrown=14, innings_pitched_outs=3)
    other = dict(arm, player_id=13, pitcher_name='Two', pitches_thrown=None, game_date='2024-07-29')
    assert editorial_reads._concentration([arm, other], day) == (None, 'missing_relief_pitch_count')
    assert editorial_reads._concentration([arm, dict(other, pitches_thrown=-1)], day) == (None, 'invalid_relief_pitch_count')
    assert editorial_reads._concentration([arm, dict(other, pitches_thrown=10, pitcher_name=None)], day) == (
        None, 'missing_official_reliever_identity')
    for excluded in [dict(other, game_date='2024-07-28', pitcher_name=None), dict(other, games_started=1),
                    dict(other, pitches_thrown=0, innings_pitched_outs=0)]:
        layer, coverage = editorial_reads._concentration([arm, excluded], day)
        assert coverage == 'complete_calendar' and layer['bullpen_workload_total_10d'] == 14


@pytest.mark.parametrize('defect,expected', [
    ('absent_club', 'incomplete_league_clubs'),
    ('missing_day', 'incomplete_league_calendar'),
    ('one_sided_game', 'conflicting_league_game'),
    ('unconfirmed_final', 'missing_or_conflicting_league_final'),
    ('missing_pitches', 'incomplete_league_pitch_counts'),
    ('all_idle', 'no_qualifying_league_workload'),
])
def test_league_concentration_requires_the_whole_window(defect, expected):
    from datetime import timedelta
    from services.mlb_club_directory import MLB_TEAM_IDS
    from sync_v3.editorial_league_baseline import league_concentration

    through = date(2024, 8, 7)
    clubs = sorted(MLB_TEAM_IDS)
    snapshots = []
    for team in clubs:
        dates = {(through - timedelta(days=i)).isoformat(): dict(reason=None, games=[]) for i in range(10)}
        if team in clubs[:2] and defect != 'all_idle':
            dates[str(through)]['games'] = [dict(game_pk=42)]
        if team == clubs[-1] and defect == 'missing_day':
            del dates[str(through)]
        if team == clubs[0] and defect == 'one_sided_game':
            dates[str(through)]['games'] = []
        snapshots.append((team + 1000, team, dates, 'facts', 'inputs'))
    lines = [dict(team_id=club, game_pk=42, game_date=str(through), games_started=0,
                  pitches_thrown=None, pitcher_mlb_id=club, outs_recorded=3) for club in clubs[:2]]

    class Cursor:
        def execute(self, sql, args):
            if args[0] == 'generation':
                self.rows = snapshots[:-1] if defect == 'absent_club' else snapshots
            else:
                assert args[1] == ([] if defect == 'all_idle' else ['42', '42'])
                self.rows = [('42', lines)] if defect == 'missing_pitches' else []

        def fetchall(self):
            return self.rows

    value, reason, citation = league_concentration(Cursor(), 'generation', through)
    assert value is None and reason == expected
    assert citation['start'] == '2024-07-29' and citation['through'] == '2024-08-07'


def test_story_roster_evidence_keeps_status_codes_separate_from_bullpen_role():
    from sync_v3.depth import named_roster_lists, roster_depth_evidence

    day = date(2024, 8, 7)
    active = dict(reason=None, pitchers={'1': dict(status_codes=['A'])})
    forty = dict(reason=None, pitchers={**active['pitchers'], '12': dict(status_codes=['D15']),
                                       '2': dict(status_codes=['D60', 'RM'])})
    facts = dict(team=118, represented=str(day), views={'active': active, '40Man': forty},
                 forty_man_outside_active=[2, 12])
    depth = dict(value=facts, citation=dict(input_digest='captured'))
    evidence = roster_depth_evidence(depth, 118, day)
    assert evidence['forty_man_listed_outside_active'] == [2, 12]
    assert (evidence['active_listed'], evidence['forty_man_listed']) == (1, 3)
    assert evidence['status_codes'] == {2: ['D60', 'RM'], 12: ['D15']}
    assert evidence['reason'] == 'off_active_bullpen_population_unverified'
    assert evidence['citation'] == depth['citation']
    directory = {
        1: dict(team_id=111, name='Other club'),
        2: dict(name='Prior listing', roster_observation=dict(team_id=118, membership='40Man', represented='2024-08-06')),
        12: dict(name='Dated name', roster_observation=dict(team_id=118, membership='40Man', represented=str(day))),
    }
    assert named_roster_lists(depth, evidence, directory) == dict(
        active=[dict(mlb_id=1, name=None)],
        forty_man_only=[dict(mlb_id=2, name=None), dict(mlb_id=12, name='Dated name')])
    for team, when in [(111, day), (118, date(2024, 8, 8))]:
        with pytest.raises(ValueError, match='another club or date'):
            roster_depth_evidence(depth, team, when)
    inconsistent = dict(depth, value=dict(facts, forty_man_outside_active=[2]))
    with pytest.raises(ValueError, match='disagrees with its frozen depth'):
        roster_depth_evidence(inconsistent, 118, day)
    facts['active_profiles'] = dict(reason='mlb_active_rosters_disagree')
    assert roster_depth_evidence(depth, 118, day)['status_codes'] is None
    forty.update(reason='parent_club_conflict', pitchers=None)
    refused = roster_depth_evidence(depth, 118, day)
    assert (refused['active_listed'], refused['forty_man_listed']) == (None, None)
    assert refused['forty_man_listed_outside_active'] is None and refused['reason'] == 'parent_club_conflict'
    assert named_roster_lists(depth, refused, directory) is None


def test_historical_editorial_selection_preserves_governed_suppression_without_loading_live_context(monkeypatch):
    from services import story_intelligence_service_v1 as writer

    def unexpected(*args, **kwargs):
        pytest.fail('The historical writer requested live club context')

    monkeypatch.setattr(writer, 'build_team_bullpen_context', unexpected)
    context = dict(team_id=111, team_name='Boston Red Sox', team_abbreviation='BOS',
                   reference_date='2024-08-08', data_through_date='2024-08-07')
    assert editorial_reads._qualified_story(context, [], {})[0] == dict(status='withheld', reason=writer.NEUTRAL_NO_OBSERVATIONS)


def test_historical_selection_matches_canonical_copy_only_for_cited_inputs():
    from services.story_feed import canonical_story_from_service_payload
    from services.story_intelligence_service_v1 import build_team_story

    rotation = dict(context_available=True, rotation_avg_ip_7d=3.2, rotation_avg_ip_14d=5.8,
                    rotation_ip_trend=-2.6, early_bullpen_entry_rate=80, bullpen_coverage_ip_7d=5.8,
                    rotation_games_analyzed_7d=6, rotation_games_analyzed_14d=12, rotation_early_bullpen_entry_games_14d=9)
    context = dict(team_id=111, team_name='Boston Red Sox', team_abbreviation='BOS', reference_date='2024-08-08',
                   data_through_date='2024-08-07', rotation_context=rotation)
    rows = editorial_reads.build_team_story_observation_payload(context)['observations']
    service = build_team_story(111, as_of_date=context['reference_date'], team_context=context)
    original = canonical_story_from_service_payload(service, team_id=111, date=context['reference_date'])
    expected = sha256(encode_json({field: original[field] for field in ('headline', 'narrative')})).hexdigest()
    assert editorial_reads._qualified_story(context, rows, {'rotation_context': rotation})[0] == dict(
        status='selected', observation_type='rotation_pressure', source_layers=['rotation_context'], copy_sha256=expected)
    for evidence, layers in (([], {'rotation_context': rotation}), (rows, {}),
                             (rows, {'rotation_context': {'context_available': False}})):
        assert editorial_reads._qualified_story(context, evidence, layers)[0] == dict(
            status='withheld', reason='incomplete_editorial_evidence')


def test_forty_man_status_wording_uses_only_the_pinned_club_date_and_recorded_codes(monkeypatch):
    from types import SimpleNamespace
    from sync_v3 import depth
    from sync_v3.discovery import Request

    day = '2017-08-28'
    request = Request('/teams/111/roster', (('date', day), ('rosterType', '40Man')), 0)
    members = [dict(person={'id': 12}, status=dict(code='D10', description='Injured 10-Day')),
               dict(person={'id': 12}, status=dict(code='RM', description='One wording')),
               dict(person={'id': 12}, status=dict(code='RM', description='Different wording'))]
    capture = SimpleNamespace(request=request, body={'roster': members})

    def replay(cur, source):
        assert source == 37
        return capture

    monkeypatch.setattr(depth, 'replay', replay)
    from unittest.mock import Mock
    cursor = Mock()
    cursor.fetchall.return_value = [(37,)]
    evidence = dict(status_codes={12: ['D10', 'RM']}, represented=day, team=111, citation={'methodology': 'candidate_roster_depth_v1'})
    assert depth.forty_man_status_labels(cursor, 'edition', evidence) == {12: {'D10': 'Injured 10-Day'}}
    for patch in [dict(team=110), dict(represented='2017-08-29')]:
        with pytest.raises(ValueError):
            depth.forty_man_status_labels(cursor, 'edition', dict(evidence, **patch))
    assert depth.forty_man_status_labels(cursor, 'edition', dict(evidence, status_codes={12: ['D10']})) == {}
    for receipts in ([], [(37,), (38,)]):
        cursor.fetchall.return_value = receipts
        assert depth.forty_man_status_labels(cursor, 'edition', evidence) == {}
    assert depth.forty_man_status_labels(cursor, 'edition', dict(evidence, status_codes=None)) == {}
