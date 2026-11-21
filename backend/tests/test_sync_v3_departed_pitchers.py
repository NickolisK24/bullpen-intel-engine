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
    monkeypatch.setattr(product_reads, '_forty_man_identities', lambda *args: ({}, set()))
    players, status = product_reads._pitcher_directory(Cursor(), 'pinned')
    assert status == 'historical_departure_identity_unresolved'
    assert players == {20: dict(team_id=120, public_id=43)}


def test_forty_man_identity_conflicts_withhold_only_disputed_members():
    class Cursor:
        def execute(self, sql, args):
            assert args == ('candidate', product_reads.DOMAINS['depth'][1])

        def __iter__(self):
            for team, mlb, name, sha in [(111, 1, 'One', 'a'), (111, 1, 'One', 'a'), (111, 2, 'Two', 'a'),
                                          (111, 3, None, 'a'), (120, 2, 'Two', 'b'), (120, 4, 'Four', 'b')]:
                yield team, date(2026, 10, 6), 'facts', 'inputs', sha, dict(id=mlb, name=name, position='1'), mlb+10

    players, conflicts = product_reads._forty_man_identities(Cursor(), 'candidate', {4})
    assert set(players) == {1} and conflicts == {2, 3}
    assert players[1]['team_id'] is None and players[1]['roster_observation']['team_id'] == 111
