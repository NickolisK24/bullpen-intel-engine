from services.atomic_publication_reads import (
    AtomicPublicationReadContext,
    AtomicReadUnavailable,
    atomic_reads_enabled,
    resolve_atomic_read_context,
    resolve_request_atomic_read_context,
)

import pytest
from flask import Flask


def _bundle(publication_id, marker='one', team_ids=(110, 111)):
    artifacts = []
    for team_id in team_ids:
        artifacts.append({
            'publication_id': publication_id,
            'artifact_type': 'team_intelligence',
            'entity_type': 'team',
            'entity_key': str(team_id),
            'payload': {'read_models': {
                'team_board': {'team': {'team_id': team_id}, 'marker': marker},
                'league_row': {'team_id': team_id, 'marker': marker},
            }},
        })
    artifacts.extend((
        {
            'publication_id': publication_id,
            'artifact_type': 'pitcher_intelligence',
            'entity_type': 'pitcher',
            'entity_key': '53',
            'payload': {'workload': {'marker': marker}},
        },
        {
            'publication_id': publication_id,
            'artifact_type': 'game_intelligence',
            'entity_type': 'game',
            'entity_key': '824794',
            'payload': {
                'game_context': {'marker': marker},
                'read_models': {'matchup': {'game_pk': 824794, 'marker': marker}},
            },
        },
    ))
    return {
        'publication_id': publication_id,
        'publication_fingerprint': f'fingerprint-{publication_id}',
        'published_at': '2026-09-10T18:00:00',
        'source_data_through': '2026-09-10T17:55:00',
        'authority_class': 'final',
        'method_versions': {'team_state': 'team-state-v1'},
        'artifacts': artifacts,
    }


def test_atomic_reads_default_off_and_resolve_bundle_once():
    assert atomic_reads_enabled({}) is False
    calls = []

    def reader():
        calls.append(True)
        return _bundle(10)

    assert resolve_atomic_read_context(env={}, bundle_reader=reader) is None
    context = resolve_atomic_read_context(
        env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
        bundle_reader=reader,
    )

    assert len(calls) == 1
    assert context.team_board(110)['atomic_publication']['publication_id'] == 10
    assert context.pitcher(53)['atomic_publication']['publication_id'] == 10
    assert context.game(824794)['atomic_publication']['publication_id'] == 10
    assert context.league((110, 111))['atomic_publication']['publication_id'] == 10
    assert len(calls) == 1


def test_request_context_cannot_mix_when_current_pointer_changes():
    current = {'bundle': _bundle(20, marker='old')}
    context = resolve_atomic_read_context(
        env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
        bundle_reader=lambda: current['bundle'],
    )
    current['bundle'] = _bundle(21, marker='new')

    assert context.team_board(110)['marker'] == 'old'
    assert {row['marker'] for row in context.league((110, 111))['teams']} == {'old'}
    assert context.publication_id == 20


def test_flask_request_resolves_current_publication_once():
    app = Flask(__name__)
    calls = []
    current = {'bundle': _bundle(40, marker='old')}

    def reader():
        calls.append(current['bundle']['publication_id'])
        return AtomicPublicationReadContext(current['bundle'])

    with app.test_request_context('/api/bullpen/teams/110/board'):
        first = resolve_request_atomic_read_context(
            env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
            context_reader=lambda **_kwargs: reader(),
        )
        current['bundle'] = _bundle(41, marker='new')
        second = resolve_request_atomic_read_context(
            env={'SYNC_PIPELINE_ATOMIC_READS_ENABLED': 'true'},
            context_reader=lambda **_kwargs: reader(),
        )

        assert first is second
        assert second.team_board(110)['marker'] == 'old'
        assert second.game(824794)['marker'] == 'old'
        assert calls == [40]


def test_mixed_or_incomplete_generation_fails_closed():
    mixed = _bundle(30)
    mixed['artifacts'][0]['publication_id'] = 29
    with pytest.raises(AtomicReadUnavailable, match='generation_mixed'):
        AtomicPublicationReadContext(mixed)

    context = AtomicPublicationReadContext(_bundle(30, team_ids=(110,)))
    with pytest.raises(AtomicReadUnavailable, match='atomic_artifact_unavailable'):
        context.league((110, 111))
