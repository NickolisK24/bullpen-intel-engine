from datetime import date

from sync_v3 import product_reads


def test_contradictory_or_anonymous_departure_preserves_unrelated_routable_players(monkeypatch):
    def arms(cur, digest):
        return {10: dict(team_id=111, public_id=42), 20: dict(team_id=120, public_id=43)}, 'mapped'

    class Cursor:
        def execute(self, sql, args):
            assert args == ('pinned',)

        def __iter__(self):
            for player, club, name in [(10, 111, 'A'), (30, 137, None), (40, 137, 'B'), (40, 120, 'B')]:
                event = dict(player=player, pitcher_name=name, kind='active_roster_removed')
                yield club, date(2026, 10, 6), 'facts', 'inputs', 1, [], event, 42 if player == 10 else 44

    monkeypatch.setattr(product_reads, '_public_arms', arms)
    monkeypatch.setattr(product_reads, '_roster_identities', lambda *args: ({}, set()))
    players, status = product_reads._pitcher_directory(Cursor(), 'pinned')
    assert status == 'historical_departure_identity_unresolved'
    assert players == {20: dict(team_id=120, public_id=43)}


def test_forty_man_identity_conflicts_withhold_only_disputed_members():
    class Cursor:
        def execute(self, sql, args):
            assert args == ('40Man', 'candidate', product_reads.DOMAINS['depth'][1], '40Man', '40Man', '40Man', '40Man')

        def __iter__(self):
            for team, mlb, name, sha in [(111, 1, 'One', 'a'), (111, 1, 'One', 'a'), (111, 2, 'Two', 'a'),
                                          (111, 3, None, 'a'), (120, 2, 'Two', 'b'), (120, 4, 'Four', 'b')]:
                yield team, date(2026, 10, 6), 'facts', 'inputs', sha, dict(id=mlb, name=name, position='1'), mlb+10

    players, conflicts = product_reads._roster_identities(Cursor(), 'candidate', '40Man', {4})
    assert set(players) == {1} and conflicts == {2, 3}
    assert players[1]['team_id'] is None and players[1]['roster_observation']['team_id'] == 111


def test_active_roster_requires_one_club_and_active_status():
    class Cursor:
        def execute(self, sql, args):
            assert args[0] == 'active'

        def __iter__(self):
            for club, player, status in [(111, 10, 'A'), (120, 10, 'A'), (111, 11, 'RM'), (111, 12, 'A')]:
                member = dict(id=player, name=f'Player {player}', position='1', status=status)
                yield club, date(2026, 10, 7), 'facts', 'inputs', 'digest', member, None

    players, conflicts = product_reads._roster_identities(Cursor(), 'candidate', 'active', set())
    assert conflicts == {10, 11}
    assert list(players) == [12] and players[12]['team_id'] == 111
    assert players[12]['public_id'] is None


def test_quiet_search_skips_pitcher_directory_and_preserves_optional_group_boundary(monkeypatch):
    from unittest.mock import Mock
    cursor = Mock()
    monkeypatch.setattr(product_reads, '_read_transaction', lambda connection, run: run(cursor))
    monkeypatch.setattr(product_reads, '_selected', lambda cur, rev: (1, 'edition', None, '2026-10-30'))
    calls = []

    def unavailable(cur, digest):
        calls.append(digest)
        raise ValueError('No pitcher directory for this edition')

    monkeypatch.setattr(product_reads, '_pitcher_directory', unavailable)
    monkeypatch.setattr(product_reads, '_schedule_rows', lambda *args: [])
    quiet = product_reads.read_search(None, 'B')
    assert calls == [] and quiet['search']['status'] == 'quiet'
    assert quiet['pitcher_identity_status'] == 'not_evaluated'
    result = product_reads.read_search(None, 'Boston')
    assert calls == ['edition'] and result['search']['status'] == 'partial'
    teams, pitchers, matchups = result['search']['groups']
    assert teams['results'] and pitchers['status'] == 'unavailable' and matchups['status'] == 'available'
