from flask import Flask

from api import bullpen
from api import team_board_v2
from services import atomic_publication_reads, public_serving_authority


class FrozenAtomicContext:
    def __init__(self):
        self.calls = []

    def team_board(self, team_id):
        self.calls.append(('team', team_id))
        return {'team': {'team_id': team_id}, 'atomic_publication': {'publication_id': 7}}

    def pitcher(self, pitcher_id):
        self.calls.append(('pitcher', pitcher_id))
        return {'data': {'workload': {'pitches': 12}}, 'atomic_publication': {'publication_id': 7}}

    def team_board_v2(self, team_id, *, view='full'):
        self.calls.append((f'team_board_v2_{view}', team_id))
        return {
            'team': {'team_id': team_id}, 'view': view,
            'atomic_publication': {'publication_id': 7},
        }

    def game(self, game_pk):
        self.calls.append(('game', game_pk))
        return {'game_pk': game_pk, 'atomic_publication': {'publication_id': 7}}

    def league(self, team_ids):
        self.calls.append(('league', tuple(team_ids)))
        return {
            'teams': [{'team_id': team_id} for team_id in team_ids],
            'atomic_publication': {'publication_id': 7},
        }

    def what_changed(self, team_id):
        self.calls.append(('what_changed', team_id))
        return {'changes': [], 'atomic_publication': {'publication_id': 7}}


def _app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = True
    return app


def test_atomic_route_boundaries_use_frozen_context(monkeypatch):
    context = FrozenAtomicContext()
    monkeypatch.setattr(bullpen, '_atomic_read_context', lambda: context)
    app = _app()

    with app.test_request_context('/api/bullpen/teams/110/board'):
        assert bullpen.get_team_bullpen_board(110).get_json()['atomic_publication']['publication_id'] == 7
    with app.test_request_context('/api/bullpen/fatigue/53'):
        assert bullpen.get_pitcher_fatigue(53).get_json()['atomic_publication']['publication_id'] == 7
    with app.test_request_context('/api/bullpen/matchups/824794'):
        assert bullpen.get_scheduled_game_matchup(824794).get_json()['atomic_publication']['publication_id'] == 7
    with app.test_request_context('/api/bullpen/team-states'):
        league = bullpen.get_league_team_states().get_json()
        assert league['atomic_publication']['publication_id'] == 7
        assert len(league['teams']) == 30
    with app.test_request_context('/api/bullpen/teams/110/changes'):
        assert bullpen.get_team_changes(110).get_json()['atomic_publication']['publication_id'] == 7

    assert [kind for kind, _value in context.calls] == [
        'team', 'pitcher', 'game', 'league', 'what_changed',
    ]


def test_production_team_board_override_keeps_atomic_boundary(monkeypatch):
    context = FrozenAtomicContext()
    monkeypatch.setattr(
        atomic_publication_reads,
        'resolve_request_atomic_read_context',
        lambda **_kwargs: context,
    )
    app = _app()

    with app.test_request_context('/api/bullpen/teams/110/board'):
        response = public_serving_authority.trusted_team_board_view(110)

    assert response.get_json()['atomic_publication']['publication_id'] == 7
    assert context.calls == [('team', 110)]


def test_team_board_v2_routes_use_atomic_artifact_without_legacy_build(monkeypatch):
    context = FrozenAtomicContext()
    monkeypatch.setattr(team_board_v2, '_atomic_read_context', lambda: context)
    app = _app()

    for suffix, view in (('', 'full'), ('/core', 'core'), ('/details', 'details')):
        with app.test_request_context(f'/api/bullpen/teams/110/board-v2{suffix}'):
            handler = {
                'full': team_board_v2.get_team_board_v2,
                'core': team_board_v2.get_team_board_core,
                'details': team_board_v2.get_team_board_details,
            }[view]
            payload = handler(110).get_json()
            assert payload['view'] == view
            assert payload['atomic_publication']['publication_id'] == 7

    assert context.calls == [
        ('team_board_v2_full', 110),
        ('team_board_v2_core', 110),
        ('team_board_v2_details', 110),
    ]
