"""Tests for the Evidence Composition Engine (ECE).

ECE reorganizes facts already in the NarrativeFeed into labeled evidence blocks.
These verify it is deterministic, invents nothing, carries through correct names
and numbers, generates no prose, fails closed on missing data, and that the
StoryPackage now includes evidence_blocks.
"""

from services.narrative_feed_builder import build_narrative_feed
from services.evidence_composition_service import (
    EVIDENCE_BLOCK_NAMES,
    EVIDENCE_VERSION,
    compose_evidence_blocks,
)
from services.coin_seeded_fixtures import fixture_for
from story_orchestrator import build_story_package, StoryPackage


def _completed_ctx(**over):
    base = {
        'team_id': 1, 'game_pk': 700, 'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape', 'game_shape_created': 'normal_start',
        'lead_protected': False, 'lead_lost': True, 'lead_when_bullpen_entered': 4,
        'bullpen_entry_inning': 7, 'bullpen_entry_score_for': 6,
        'bullpen_entry_score_against': 2, 'largest_lead': 4, 'largest_deficit': 3,
        'late_runs_allowed': 7, 'runs_allowed_innings_7_to_9': 7, 'turning_inning': 8,
        'starter_name': 'Logan Webb', 'starter_ip': 6.0, 'starter_pitch_count': 95,
        'starter_exit_inning': 6, 'starter_exit_score_for': 6, 'starter_exit_score_against': 2,
        'key_relief_appearances': [
            {'name': 'Caleb Kilian', 'innings': 1.1, 'runs_allowed': 3},
        ],
    }
    base.update(over)
    return base


def _team_context(clean_names=('Erik Miller', 'Tyler Rogers')):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 3,
            'monitor_arms_count': 1, 'limited_arms_count': 1, 'unavailable_arms_count': 1,
            'clean_workload_options': [
                {'player_id': i, 'name': n, 'availability': 'Available'}
                for i, n in enumerate(clean_names)
            ],
            'secondary_options': [],
            'practical_close_game_paths_count': 2, 'optionality_band': 'thin',
        },
        'bullpen_concentration_context': {'concentration_band': 'concentrated',
                                          'window_days': 10, 'bullpen_workload_total_10d': 240,
                                          'top_three_workload_share_10d': 47.0},
        'rotation_context': {'bullpen_coverage_ip_7d': 9.0},
        'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _feed(completed=None, team=None):
    return build_narrative_feed(
        1,
        completed_game_context=completed if completed is not None else _completed_ctx(),
        team_context=team if team is not None else _team_context(),
    )


# ── Stable shape / version ────────────────────────────────────────────────────

def test_all_blocks_present_with_version():
    blocks = compose_evidence_blocks(_feed())
    for name in EVIDENCE_BLOCK_NAMES:
        assert name in blocks
    assert blocks['evidence_version'] == EVIDENCE_VERSION


# ── Correct names / numbers (no invention) ────────────────────────────────────

def test_starter_summary_carries_exact_values():
    blocks = compose_evidence_blocks(_feed())
    starter = blocks['starter_summary']
    assert starter['name'] == 'Logan Webb'
    assert starter['innings'] == 6.0
    assert starter['pitch_count'] == 95
    assert starter['exit_inning'] == 6


def test_key_relief_appearances_carry_exact_names_and_numbers():
    blocks = compose_evidence_blocks(_feed())
    assert blocks['key_relief_appearances'] == [
        {'name': 'Caleb Kilian', 'innings': 1.1, 'runs_allowed': 3},
    ]


def test_named_relievers_pass_through_unchanged():
    blocks = compose_evidence_blocks(_feed(team=_team_context(['Ryan Walker', 'Tyler Rogers'])))
    names = [r['name'] for r in blocks['available_relievers']]
    assert names == ['Ryan Walker', 'Tyler Rogers']
    assert all(r['status'] == 'Available' for r in blocks['available_relievers'])
    assert blocks['clean_options'] == blocks['available_relievers']


def test_score_and_lead_blocks_match_completed_context():
    blocks = compose_evidence_blocks(_feed())
    assert blocks['largest_lead'] == {'runs': 4}
    assert blocks['largest_deficit'] == {'runs': 3}
    assert blocks['turning_point'] == {'inning': 8}
    assert blocks['late_runs'] == {'late_runs_allowed': 7, 'runs_allowed_innings_7_to_9': 7}
    entry = blocks['bullpen_entry_situation']
    assert entry['inning'] == 7 and entry['score_for'] == 6 and entry['lead_when_entered'] == 4


def test_story_evidence_mirrors_narrative_facts():
    feed = _feed()
    blocks = compose_evidence_blocks(feed)
    se = blocks['story_evidence']
    assert se['primary_story'] == 'lost_game_shape'
    assert se['supporting_facts'] == feed.to_dict()['supporting_facts']
    assert se['supporting_observations'] == feed.to_dict()['supporting_observations']


# ── No prose ──────────────────────────────────────────────────────────────────

def test_blocks_contain_no_prose():
    blocks = compose_evidence_blocks(_feed())

    def _check(value):
        if isinstance(value, str):
            # Identifiers / names only — never a sentence with terminal punctuation.
            assert '.' not in value or value.replace('.', '').isdigit()
            assert not value.endswith(('!', '?'))
        elif isinstance(value, dict):
            for v in value.values():
                _check(v)
        elif isinstance(value, list):
            for v in value:
                _check(v)

    for name, block in blocks.items():
        if name == 'evidence_version':
            continue
        _check(block)


# ── Determinism ───────────────────────────────────────────────────────────────

def test_evidence_is_deterministic():
    feed = _feed()
    assert compose_evidence_blocks(feed) == compose_evidence_blocks(feed)


# ── Fail-closed behavior ──────────────────────────────────────────────────────

def test_missing_data_fails_closed_to_empty():
    # An empty feed: every collection is [], every summary is {}, nothing invented.
    blocks = compose_evidence_blocks({})
    for name in ('available_relievers', 'monitor_relievers', 'limited_relievers',
                 'unavailable_relievers', 'key_relief_appearances', 'clean_options'):
        assert blocks[name] == []
    for name in ('starter_summary', 'largest_lead', 'turning_point',
                 'bullpen_entry_situation', 'late_runs', 'coverage_depth'):
        assert blocks[name] == {}
    assert blocks['evidence_version'] == EVIDENCE_VERSION


def test_unnamed_relievers_are_dropped_not_invented():
    # clean options without names must not produce phantom reliever records.
    team = _team_context()
    team['bullpen_optionality_context']['clean_workload_options'] = [
        {'player_id': 5}, {'player_id': 6},
    ]
    blocks = compose_evidence_blocks(_feed(team=team))
    assert blocks['available_relievers'] == []
    assert blocks['clean_options'] == []


def test_status_buckets_without_named_source_stay_empty():
    blocks = compose_evidence_blocks(_feed())
    # Counts are preserved in the summary; the named lists fail closed.
    assert blocks['monitor_relievers'] == []
    assert blocks['limited_relievers'] == []
    assert blocks['unavailable_relievers'] == []
    assert blocks['bullpen_summary']['monitor_count'] == 1
    assert blocks['bullpen_summary']['unavailable_count'] == 1


# ── StoryPackage integration ──────────────────────────────────────────────────

def test_story_package_includes_evidence_blocks():
    pkg = build_story_package(1, completed_game_context=_completed_ctx(),
                              team_context=_team_context())
    assert isinstance(pkg, StoryPackage)
    assert isinstance(pkg.evidence_blocks, dict)
    assert pkg.evidence_blocks['starter_summary']['name'] == 'Logan Webb'
    assert 'evidence_blocks' in pkg.to_dict()
    assert pkg.to_dict()['evidence_blocks'] == pkg.evidence_blocks


def test_seeded_fixture_drives_evidence_through_orchestrator():
    fix = fixture_for(137)
    pkg = build_story_package(137, completed_game_context=fix['completed_game_context'],
                              team_context=fix['team_context'])
    eb = pkg.evidence_blocks
    assert eb['starter_summary']['name'] == 'Logan Webb'
    assert [a['name'] for a in eb['key_relief_appearances']] == ['Ryan Walker', 'Tyler Rogers']
    assert eb['available_relievers'][0]['name'] == 'Erik Miller'
    assert eb['late_runs']['late_runs_allowed'] == 7
