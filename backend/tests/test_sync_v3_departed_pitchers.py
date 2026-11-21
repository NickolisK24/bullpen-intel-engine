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
    players, status = product_reads._pitcher_directory(Cursor(), 'pinned')
    assert status == 'historical_departure_identity_unresolved'
    assert players == {20: dict(team_id=120, public_id=43)}
