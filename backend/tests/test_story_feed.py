"""Unit tests for the canonical story adapter (services/story_feed.py).

These are pure-function tests: the adapter maps Story Intelligence V1 payloads
to the canonical story contract and assembles the feed. No database or app
context is required.
"""

from datetime import date

from services.story_feed import (
    POSITIVE_BEAT_LIMITATION,
    QUALITY_PUBLISHED,
    QUALITY_REVIEW,
    QUALITY_SUPPRESSED,
    SOURCE_ENGINE,
    build_canonical_story_feed,
    canonical_story_from_service_payload,
    story_id_for,
)

# The canonical contract keys every item must carry.
REQUIRED_KEYS = {
    'story_id', 'team_id', 'team_name', 'date', 'story_available',
    'suppression_reason', 'story_type', 'category', 'tone', 'headline',
    'narrative', 'beats', 'evidence', 'freshness', 'trust_metadata',
    'limitations', 'share_ready', 'share_title', 'share_summary',
    'source_engine', 'quality_status',
}

AS_OF = date(2026, 6, 22)


def _available_payload(team_id=1, observation_type='rotation_pressure', story_type='coverage_pressure'):
    return {
        'team_id': team_id,
        'team_name': f'Team {team_id}',
        'team_abbreviation': f'T{team_id}',
        'as_of_date': '2026-06-22',
        'story_available': True,
        'story_type': story_type,
        'story_type_label': 'Coverage Pressure',
        'selected_observation': {'type': observation_type, 'severity': 'high'},
        'construction_frame': {'observation_type': observation_type},
        'public_story_beat': {'story_type': story_type, 'story_type_label': 'Coverage Pressure'},
        'written_story': {
            'headline': 'Team leans on its setup arms',
            'observation_paragraph': 'Observation text.',
            'baseline_paragraph': 'Baseline text.',
            'cause_paragraph': 'Cause text.',
            'constraint_paragraph': 'Constraint text.',
        },
        'freshness': {'data_through': '2026-06-21'},
        'trust_metadata': {'external_generation_used': False},
        'limitations': [],
    }


def _neutral_payload(team_id=2, reason='no_story_observations'):
    return {
        'team_id': team_id,
        'team_name': f'Team {team_id}',
        'team_abbreviation': f'T{team_id}',
        'as_of_date': '2026-06-22',
        'story_available': False,
        'neutral_reason': reason,
        'freshness': {},
        'trust_metadata': {},
        'limitations': [],
    }


def _builder(mapping):
    def build(team_id, as_of_date=None):
        result = mapping.get(team_id)
        if isinstance(result, Exception):
            raise result
        return result
    return build


def _descriptor(team_id):
    return {'team_id': team_id, 'team_name': f'Team {team_id}', 'team_abbreviation': f'T{team_id}'}


class TestStableId:
    def test_id_is_team_and_date_only(self):
        assert story_id_for(7, AS_OF) == '7:2026-06-22'

    def test_id_excludes_beat_type(self):
        # Same team and date but different story types must yield the same id so
        # share links and continuity survive an intraday beat change.
        a = canonical_story_from_service_payload(
            _available_payload(1, story_type='coverage_pressure'), date=AS_OF)
        b = canonical_story_from_service_payload(
            _available_payload(1, story_type='route_change'), date=AS_OF)
        assert a['story_id'] == b['story_id'] == '1:2026-06-22'


class TestAvailableMapping:
    def test_available_story_has_all_contract_keys(self):
        story = canonical_story_from_service_payload(_available_payload(1), date=AS_OF)
        assert REQUIRED_KEYS.issubset(story.keys())

    def test_available_story_content(self):
        story = canonical_story_from_service_payload(_available_payload(1), date=AS_OF)
        assert story['story_available'] is True
        assert story['suppression_reason'] is None
        assert story['source_engine'] == SOURCE_ENGINE
        assert story['quality_status'] == QUALITY_PUBLISHED
        assert story['headline'] == 'Team leans on its setup arms'
        assert story['narrative'] == (
            'Observation text.\n\nBaseline text.\n\nCause text.\n\nConstraint text.'
        )
        assert [beat['key'] for beat in story['beats']] == [
            'observation', 'baseline', 'cause', 'constraint',
        ]
        # Evidence draws only on the two evidentiary beats.
        assert [item['key'] for item in story['evidence']] == ['baseline', 'cause']
        # Tone/category derive from the underlying observation read.
        assert story['tone'] == 'stress'
        assert story['category'] == 'stressed'

    def test_share_fields_ready(self):
        story = canonical_story_from_service_payload(_available_payload(1), date=AS_OF)
        assert story['share_ready'] is True
        assert story['share_title'] == 'Team 1 bullpen: coverage pressure'
        assert story['share_summary'] == 'Observation text.'

    def test_rest_observation_maps_to_rest_tone(self):
        payload = _available_payload(
            3, observation_type='optionality_strength', story_type='sustainability_question')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['tone'] == 'rest'
        assert story['category'] == 'rested'


class TestPositiveBeatBlocker:
    def test_published_positive_story_is_rested_and_not_flagged(self):
        # A positive read published under the availability_depth beat is a clean,
        # published rest/depth story — no review flag, no parity limitation.
        payload = _available_payload(
            3, observation_type='optionality_strength', story_type='availability_depth')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['story_available'] is True
        assert story['tone'] == 'rest'
        assert story['category'] == 'rested'
        assert story['quality_status'] == QUALITY_PUBLISHED
        assert POSITIVE_BEAT_LIMITATION not in story['limitations']

    def test_stable_core_positive_story_is_rested(self):
        payload = _available_payload(
            4, observation_type='stable_core', story_type='availability_depth')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['tone'] == 'rest'
        assert story['category'] == 'rested'
        assert story['quality_status'] == QUALITY_PUBLISHED

    def test_reframed_positive_observation_is_still_flagged(self):
        # Defensive: if a positive observation is ever still mapped to a
        # non-positive beat, it is flagged for review rather than presented clean.
        payload = _available_payload(
            3, observation_type='optionality_strength', story_type='sustainability_question')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['quality_status'] == QUALITY_REVIEW
        assert POSITIVE_BEAT_LIMITATION in story['limitations']
        # The engine's authored copy is preserved verbatim.
        assert story['headline'] == 'Team leans on its setup arms'
        assert story['narrative'].startswith('Observation text.')


class TestSuppression:
    def test_neutral_payload_returns_suppressed_item(self):
        story = canonical_story_from_service_payload(_neutral_payload(2), date=AS_OF)
        assert story['story_available'] is False
        assert story['suppression_reason'] == 'no_story_observations'
        assert story['quality_status'] == QUALITY_SUPPRESSED
        # No fabricated story.
        assert story['headline'] is None
        assert story['narrative'] is None
        assert story['beats'] == []
        assert story['evidence'] == []
        assert story['share_ready'] is False
        # Identity and date are still present on a suppressed item.
        assert story['team_id'] == 2
        assert story['team_name'] == 'Team 2'
        assert story['date'] == '2026-06-22'

    def test_missing_payload_is_suppressed_unavailable(self):
        story = canonical_story_from_service_payload(
            None, team_id=9, team={'team_name': 'Team 9', 'team_abbreviation': 'T9'}, date=AS_OF)
        assert story['story_available'] is False
        assert story['suppression_reason'] == 'story_unavailable'
        assert story['quality_status'] == QUALITY_SUPPRESSED
        assert story['team_name'] == 'Team 9'
        assert story['story_id'] == '9:2026-06-22'


class TestFeed:
    def test_orders_available_first_with_counts(self):
        feed = build_canonical_story_feed(
            [_descriptor(1), _descriptor(2), _descriptor(3)],
            as_of_date=AS_OF,
            story_builder=_builder({
                1: _available_payload(1),
                2: _neutral_payload(2),
                3: _available_payload(3),
            }),
        )
        assert [story['team_id'] for story in feed['items']] == [1, 3, 2]
        assert feed['available_count'] == 2
        assert feed['suppressed_count'] == 1
        assert feed['suppression_reasons'] == {'no_story_observations': 1}
        assert feed['source_engine'] == SOURCE_ENGINE
        assert feed['as_of_date'] == '2026-06-22'

    def test_no_fabrication_when_no_observations(self):
        feed = build_canonical_story_feed(
            [_descriptor(2)],
            as_of_date=AS_OF,
            story_builder=_builder({2: _neutral_payload(2)}),
        )
        item = feed['items'][0]
        assert item['story_available'] is False
        assert item['headline'] is None
        assert item['narrative'] is None
        assert item['beats'] == []

    def test_builder_exception_becomes_suppressed_item(self):
        feed = build_canonical_story_feed(
            [_descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: RuntimeError('boom')}),
        )
        item = feed['items'][0]
        assert item['story_available'] is False
        assert item['suppression_reason'] == 'story_unavailable'
        assert feed['suppressed_count'] == 1

    def test_dedupes_repeated_team_ids(self):
        feed = build_canonical_story_feed(
            [_descriptor(1), _descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1)}),
        )
        assert len(feed['items']) == 1

    def test_every_item_carries_required_keys(self):
        feed = build_canonical_story_feed(
            [_descriptor(1), _descriptor(2)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1), 2: _neutral_payload(2)}),
        )
        for item in feed['items']:
            assert REQUIRED_KEYS.issubset(item.keys())
