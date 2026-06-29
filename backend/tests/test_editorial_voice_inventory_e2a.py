"""E2A editorial voice inventory governance.

This test documents which public storytelling surfaces draw from the shared
story voice library and which ones still use independent public copy systems.
It is diagnostic only: no runtime story output is changed by this inventory.
"""

from pathlib import Path

from services import story_voice_library_v1 as voice


REPO_ROOT = Path(__file__).resolve().parents[2]

STATUS_VALUES = {'yes', 'no', 'partial'}

PUBLIC_STORY_SURFACE_INVENTORY = (
    {
        'surface': "Homepage Today's Story",
        'writer_component': 'intelligence_surface_service -> story_writers',
        'voice_source': 'completed-game writer phrase banks',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'independent',
        'files': (
            'backend/services/intelligence_surface_service.py',
            'backend/services/intelligence_surface_snapshot.py',
            'backend/story_writers/base_story_writer.py',
            'backend/story_writers/team_story_writer.py',
            'frontend/src/components/home/IntelligenceSurface.jsx',
        ),
    },
    {
        'surface': 'Stories feed',
        'writer_component': 'story_feed -> story_writer_v1 -> story_blueprint_v1',
        'voice_source': 'story_voice_library_v1 plus evidence and league helpers',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'files': (
            'backend/services/story_feed.py',
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_evidence_case_v1.py',
            'backend/services/story_voice_library_v1.py',
            'frontend/src/components/stories/storiesCanonicalFeedView.js',
            'frontend/src/components/stories/Stories.jsx',
        ),
    },
    {
        'surface': 'Team bullpen stories',
        'writer_component': 'build_team_story -> StoryCard',
        'voice_source': 'story_voice_library_v1 plus story_writer_v1 templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'files': (
            'backend/services/story_intelligence_service_v1.py',
            'backend/api/bullpen.py',
            'frontend/src/components/bullpen/board/storyCardView.js',
            'frontend/src/components/bullpen/board/StoryCard.jsx',
        ),
    },
    {
        'surface': 'Compare Bullpens',
        'writer_component': 'build_team_comparison',
        'voice_source': 'local comparison statements',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'no',
        'voice_system': 'independent',
        'files': (
            'backend/services/bullpen_comparison.py',
            'backend/api/bullpen.py',
        ),
    },
    {
        'surface': 'What Changed',
        'writer_component': 'build_what_changed_public_copy',
        'voice_source': 'local headline, summary, and context pools',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'independent',
        'files': (
            'backend/services/what_changed_since_yesterday_copy.py',
            'backend/services/what_changed_since_yesterday_public.py',
            'frontend/src/components/dashboard/WhatChangedCard.jsx',
            'frontend/src/components/home/IntelligenceSurface.jsx',
        ),
    },
    {
        'surface': "Today's Watch",
        'writer_component': 'tonight_candidate_selection -> serve_tonight',
        'voice_source': 'local pregame card copy helpers',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'no',
        'voice_system': 'independent',
        'files': (
            'backend/services/tonight_candidate_selection.py',
            'backend/services/tonight_intelligence_service.py',
            'backend/services/tonight_intelligence_snapshot.py',
            'frontend/src/components/home/IntelligenceSurface.jsx',
        ),
    },
    {
        'surface': 'Completed-game stories',
        'writer_component': 'StoryPackage -> Team/Dashboard/MorningBrief writers',
        'voice_source': 'completed-game writer phrase banks',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'independent',
        'files': (
            'backend/story_orchestrator/story_orchestrator.py',
            'backend/story_writers/base_story_writer.py',
            'backend/story_writers/team_story_writer.py',
            'backend/story_writers/dashboard_story_writer.py',
            'backend/story_writers/morning_brief_writer.py',
            'backend/services/coin_story_corpus.py',
        ),
    },
    {
        'surface': 'Bridge stories',
        'writer_component': 'story_writer_v1._bridge_instability',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_BRIDGE,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Route Change stories',
        'writer_component': 'story_writer_v1._core_transition',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_ROUTE_CHANGE,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Coverage Pressure stories',
        'writer_component': 'story_writer_v1._rotation_pressure',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_COVERAGE_PRESSURE,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Depth Constraint stories',
        'writer_component': 'story_writer_v1._depth_pressure',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_DEPTH_CONSTRAINT,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Sustainability Question stories',
        'writer_component': 'story_writer_v1._concentration_pressure',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_SUSTAINABILITY_QUESTION,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Availability Depth stories',
        'writer_component': 'story_writer_v1._optionality_strength',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_AVAILABILITY_DEPTH,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Trust Lane stories',
        'writer_component': 'story_writer_v1._trust_lane_pressure',
        'voice_source': 'story_voice_library_v1 plus beat fact templates',
        'shared_library': 'partial',
        'hardcoded': 'partial',
        'uses_editorial_pools': 'yes',
        'voice_system': 'shared_story_engine',
        'beat': voice.BEAT_TRUST_LANE,
        'files': (
            'backend/services/story_writer_v1.py',
            'backend/services/story_blueprint_v1.py',
            'backend/services/story_voice_library_v1.py',
        ),
    },
    {
        'surface': 'Pitcher Context explanations',
        'writer_component': 'pitcher labels and availability/readiness explanations',
        'voice_source': 'public label and explanation catalogs',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'public_label_layer',
        'files': (
            'backend/services/pitcher_public_labels.py',
            'backend/services/availability_explanations.py',
            'backend/explanations/readiness.py',
        ),
    },
    {
        'surface': 'Team bullpen shape explanations',
        'writer_component': 'team_bullpen_shape reads',
        'voice_source': 'team shape label and explanation catalogs',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'public_label_layer',
        'files': (
            'backend/services/team_bullpen_shape.py',
            'frontend/src/utils/teamBullpenScoring.js',
            'frontend/src/utils/bullpenConcepts.js',
        ),
    },
    {
        'surface': 'Dormant frontend language layer',
        'writer_component': 'bullpenLanguage SIGNAL_HEADLINES',
        'voice_source': 'frontend headline pools',
        'shared_library': 'no',
        'hardcoded': 'yes',
        'uses_editorial_pools': 'yes',
        'voice_system': 'dormant_duplicate',
        'currently_imported': False,
        'files': (
            'frontend/src/utils/bullpenLanguage.js',
            'docs/product/LANGUAGE_ENGINE_V1.md',
        ),
    },
)

REQUIRED_PUBLIC_SURFACES = {
    "Homepage Today's Story",
    'Stories feed',
    'Team bullpen stories',
    'Compare Bullpens',
    'What Changed',
    "Today's Watch",
    'Completed-game stories',
    'Bridge stories',
    'Route Change stories',
    'Coverage Pressure stories',
    'Depth Constraint stories',
    'Sustainability Question stories',
    'Availability Depth stories',
    'Trust Lane stories',
    'Pitcher Context explanations',
}

EXPECTED_INDEPENDENT_SYSTEMS = {
    "Homepage Today's Story",
    'Compare Bullpens',
    'What Changed',
    "Today's Watch",
    'Completed-game stories',
}

EXPECTED_PUBLIC_BEATS = {
    voice.BEAT_BRIDGE,
    voice.BEAT_ROUTE_CHANGE,
    voice.BEAT_COVERAGE_PRESSURE,
    voice.BEAT_DEPTH_CONSTRAINT,
    voice.BEAT_SUSTAINABILITY_QUESTION,
    voice.BEAT_AVAILABILITY_DEPTH,
    voice.BEAT_TRUST_LANE,
}


def test_required_public_story_surfaces_are_inventoried():
    surfaces = {row['surface'] for row in PUBLIC_STORY_SURFACE_INVENTORY}
    assert REQUIRED_PUBLIC_SURFACES <= surfaces


def test_voice_inventory_classifications_are_complete():
    for row in PUBLIC_STORY_SURFACE_INVENTORY:
        assert row['writer_component']
        assert row['voice_source']
        assert row['shared_library'] in STATUS_VALUES
        assert row['hardcoded'] in STATUS_VALUES
        assert row['uses_editorial_pools'] in STATUS_VALUES
        assert row['voice_system']
        assert row['files']


def test_voice_inventory_paths_still_exist():
    missing = []
    for row in PUBLIC_STORY_SURFACE_INVENTORY:
        for rel_path in row['files']:
            if not (REPO_ROOT / rel_path).exists():
                missing.append((row['surface'], rel_path))
    assert missing == []


def test_known_independent_public_voice_systems_are_documented():
    independent = {
        row['surface']
        for row in PUBLIC_STORY_SURFACE_INVENTORY
        if row['voice_system'] == 'independent'
    }
    assert EXPECTED_INDEPENDENT_SYSTEMS <= independent


def test_shared_story_voice_library_covers_documented_public_beats():
    beats = {
        row['beat']
        for row in PUBLIC_STORY_SURFACE_INVENTORY
        if row.get('beat')
    }
    assert EXPECTED_PUBLIC_BEATS <= beats
    assert beats <= set(voice.VOICE_LIBRARY)
    for beat in beats:
        purposes = voice.VOICE_LIBRARY[beat]
        for purpose in (
            voice.PURPOSE_OPENING,
            voice.PURPOSE_FORWARD,
            voice.PURPOSE_SURFACE,
            voice.PURPOSE_LESSON,
            voice.PURPOSE_WATCH,
        ):
            assert purposes.get(purpose), (beat, purpose)


def test_dormant_duplicate_frontend_language_layer_is_explicitly_marked():
    row = next(
        item for item in PUBLIC_STORY_SURFACE_INVENTORY
        if item['surface'] == 'Dormant frontend language layer'
    )
    assert row['voice_system'] == 'dormant_duplicate'
    assert row['currently_imported'] is False
