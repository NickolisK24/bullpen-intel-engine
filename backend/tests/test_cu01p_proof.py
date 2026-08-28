import copy
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/run_cu01p_proof.py'
SPEC = importlib.util.spec_from_file_location('run_cu01p_proof', SCRIPT)
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


def _passing_proof():
    return {
        'cu': {
            'per_game': [{
                'finality': 'PASS',
                'appearance_team_ownership': 'PASS',
                'supported_line_coverage': 'PASS',
                'affected_entities': 'PASS',
                'workload_parity': 'PASS',
                'publication_affected': False,
            }],
            'idempotency': {
                'canonical_facts_unchanged': True,
                'affected_entities_noop_safe': True,
            },
            'restart': {'passed': True},
            'controlled_correction': {'stale_revision_rejection_proven': True},
            'coverage': {'batted_ball_scope_passed': True},
            'publication_safety': {'passed': True},
            'position_players': [{'current_identity_preserved': True}],
        },
        'optional_failure': {'passed': True},
    }


def test_real_game_set_is_bounded_unique_and_replay_subset_is_meaningful():
    game_pks = [row[0] for row in proof.SELECTED_GAMES]
    assert 10 <= len(game_pks) <= 20
    assert len(game_pks) == len(set(game_pks))
    assert len(proof.REPLAY_GAME_PKS) >= 5
    assert set(proof.REPLAY_GAME_PKS) <= set(game_pks)


def test_proof_environment_tracks_only_publication_safety_tables():
    assert 'dashboard_snapshots' in proof.PUBLICATION_TABLES
    assert 'share_artifacts' in proof.PUBLICATION_TABLES
    assert 'team_progressive_publications' in proof.PUBLICATION_TABLES
    assert 'game_logs' not in proof.PUBLICATION_TABLES
    assert 'game_pitch_events' not in proof.PUBLICATION_TABLES


def test_optional_pbp_capture_seam_fails_without_hiding_core_source():
    source = {
        'boxscores': {'1': {'teams': {'home': {}, 'away': {}}}},
        'play_by_play': {'1': {'allPlays': []}},
        'linescores': {'1': {'innings': []}},
    }
    client = proof.CapturedMlbClient(copy.deepcopy(source), pbp_failures={1})
    assert client.get_game_boxscore(1) == source['boxscores']['1']
    try:
        client.get_game_play_by_play(1)
    except TimeoutError as exc:
        assert 'controlled CU-01P optional PBP failure' in str(exc)
    else:
        raise AssertionError('controlled PBP failure did not fire')


def test_verdict_blocks_noop_affected_entities_and_stale_revision_gap():
    candidate = _passing_proof()
    candidate['cu']['idempotency']['affected_entities_noop_safe'] = False
    candidate['cu']['controlled_correction']['stale_revision_rejection_proven'] = False
    result = proof._verdict(candidate)
    assert result['classification'] == 'BLOCKED'
    assert result['blockers'] == [
        'no_op_replay_emits_affected_entities',
        'stale_source_revision_rejection_unproven',
    ]


def test_verdict_blocks_batted_ball_over_attribution():
    candidate = _passing_proof()
    candidate['cu']['coverage']['batted_ball_scope_passed'] = False
    result = proof._verdict(candidate)
    assert result['classification'] == 'BLOCKED'
    assert result['blockers'] == [
        'batted_ball_result_over_attributed_to_non_in_play_pitches',
    ]


def test_verdict_accepts_only_complete_evidence():
    result = proof._verdict(_passing_proof())
    assert result == {
        'classification': 'PASS',
        'blockers': [],
        'acceptance_statement_supported': True,
    }
