"""Unit tests for the canonical story adapter (services/story_feed.py).

These are pure-function tests: the adapter maps Story Intelligence V1 payloads
to the canonical story contract and assembles the feed. No database or app
context is required.
"""

from datetime import date

from services.story_feed import (
    CONTINUITY_CHANGED,
    CONTINUITY_NEW,
    CONTINUITY_ONGOING,
    CONTINUITY_RESOLVED,
    CONTINUITY_UNAVAILABLE,
    CONTINUITY_UNCHANGED,
    DAY_LOW_STORY,
    DAY_NO_STORY,
    DAY_NORMAL,
    DAY_QUIET,
    LEAGUE_CONTEXT_CAPABILITY,
    LEAGUE_MODE_BROADLY_CONSTRAINED,
    LEAGUE_MODE_BROADLY_STABLE,
    LEAGUE_MODE_DEPTH_HEALTHY,
    LEAGUE_MODE_NEUTRAL,
    LEAGUE_MODE_PRESSURE_CONCENTRATED,
    POSITIVE_BEAT_LIMITATION,
    QUALITY_NEUTRAL,
    QUALITY_PUBLISHED,
    QUALITY_REVIEW,
    QUALITY_SUPPRESSED,
    SOURCE_ENGINE,
    build_canonical_story_feed,
    build_league_context,
    build_story_continuity,
    canonical_story_from_service_payload,
    classify_story_day,
    story_id_for,
)


def _item(team_id, *, available=True, story_type='coverage_pressure', headline='Headline', date='2026-06-22'):
    """Minimal canonical-story shape for continuity tests."""
    return {
        'story_id': f'{team_id}:{date}',
        'team_id': team_id,
        'story_available': available,
        'story_type': story_type if available else None,
        'headline': headline if available else None,
        'date': date,
    }

# Public-facing copy must never contain prediction/betting/ranking language.
_FORBIDDEN_LEAGUE_TERMS = (
    'bet', 'odds', 'predict', 'probability', 'guaranteed', 'lock',
    'will win', 'ranked', 'ranking', 'best option',
)


def _story(category, *, available=True):
    return {'story_available': available, 'category': category}


def _no_forbidden_language(context):
    text = f"{context['headline']} {context['summary']}".lower()
    return not any(term in text for term in _FORBIDDEN_LEAGUE_TERMS)

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

    def test_trust_lane_observation_maps_to_trust_lane_category(self):
        payload = _available_payload(
            5, observation_type='trust_lane_pressure', story_type='trust_lane')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        # Trust-lane gets its own category and the supported `watch` tone so every
        # surface renders it (rather than falling back to neutral).
        assert story['tone'] == 'watch'
        assert story['category'] == 'trust_lane'
        assert story['story_available'] is True
        assert story['quality_status'] == QUALITY_PUBLISHED

    def test_trust_lane_beat_tone_used_when_observation_type_absent(self):
        payload = _available_payload(6, observation_type=None, story_type='trust_lane')
        payload['selected_observation'] = {}
        payload['construction_frame'] = {}
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['tone'] == 'watch'
        assert story['category'] == 'trust_lane'

    def test_bridge_observation_maps_to_bridge_category(self):
        payload = _available_payload(
            7, observation_type='bridge_instability', story_type='bridge')
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        # Bridge gets its own category and the supported `watch` tone.
        assert story['tone'] == 'watch'
        assert story['category'] == 'bridge'
        assert story['story_available'] is True
        assert story['quality_status'] == QUALITY_PUBLISHED

    def test_bridge_beat_tone_used_when_observation_type_absent(self):
        payload = _available_payload(8, observation_type=None, story_type='bridge')
        payload['selected_observation'] = {}
        payload['construction_frame'] = {}
        story = canonical_story_from_service_payload(payload, date=AS_OF)
        assert story['tone'] == 'watch'
        assert story['category'] == 'bridge'


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

    def test_feed_includes_league_context(self):
        feed = build_canonical_story_feed(
            [_descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1)}),
            league_signal={'team_count': 30, 'constrained_team_count': 3, 'available_team_count': 10},
        )
        context = feed['league_context']
        assert context['capability'] == LEAGUE_CONTEXT_CAPABILITY
        assert context['mode']
        assert context['day_class']
        assert _no_forbidden_language(context)


class TestStoryDayClassification:
    def test_no_story_day(self):
        assert classify_story_day(0) == DAY_NO_STORY

    def test_quiet_day(self):
        assert classify_story_day(1) == DAY_QUIET
        assert classify_story_day(2) == DAY_QUIET

    def test_low_story_day(self):
        assert classify_story_day(3) == DAY_LOW_STORY
        assert classify_story_day(5) == DAY_LOW_STORY

    def test_normal_day(self):
        assert classify_story_day(6) == DAY_NORMAL
        assert classify_story_day(20) == DAY_NORMAL


class TestLeagueContext:
    def test_normal_day_classification(self):
        context = build_league_context([_story('stressed') for _ in range(6)], as_of_date=AS_OF)
        assert context['day_class'] == DAY_NORMAL
        assert context['evidence']['publishable_story_count'] == 6

    def test_quiet_day_is_stable_and_neutral_quality(self):
        context = build_league_context([_story('watch'), _story('watch')], as_of_date=AS_OF)
        assert context['day_class'] == DAY_QUIET
        assert context['mode'] == LEAGUE_MODE_BROADLY_STABLE
        assert context['generated'] is False
        assert context['quality_status'] == QUALITY_NEUTRAL
        assert 'no major bullpen story' in context['headline'].lower()
        assert _no_forbidden_language(context)

    def test_no_story_day_returns_honest_fallback(self):
        context = build_league_context([], as_of_date=AS_OF)
        assert context['day_class'] == DAY_NO_STORY
        assert context['mode'] == LEAGUE_MODE_BROADLY_STABLE
        assert context['generated'] is False
        assert context['quality_status'] == QUALITY_NEUTRAL
        assert context['evidence']['publishable_story_count'] == 0
        assert _no_forbidden_language(context)

    def test_league_pressure_concentration(self):
        items = [_story('stressed'), _story('stressed'), _story('watch')]
        context = build_league_context(
            items,
            league_signal={'team_count': 30, 'constrained_team_count': 5, 'available_team_count': 8},
            as_of_date=AS_OF,
        )
        assert context['mode'] == LEAGUE_MODE_PRESSURE_CONCENTRATED
        assert context['generated'] is True
        assert context['quality_status'] == QUALITY_PUBLISHED
        # The club count in the copy matches the evidence (no fabrication).
        assert 'contained to 5 clubs' in context['summary']
        assert context['evidence']['constrained_team_count'] == 5
        assert _no_forbidden_language(context)

    def test_broadly_constrained_league(self):
        context = build_league_context(
            [_story('stressed') for _ in range(8)],
            league_signal={'team_count': 30, 'constrained_team_count': 14, 'available_team_count': 4},
            as_of_date=AS_OF,
        )
        assert context['mode'] == LEAGUE_MODE_BROADLY_CONSTRAINED
        assert context['generated'] is True
        assert '14 clubs' in context['summary']
        assert _no_forbidden_language(context)

    def test_league_depth_health(self):
        context = build_league_context(
            [_story('rested') for _ in range(7)],
            league_signal={'team_count': 30, 'constrained_team_count': 0, 'available_team_count': 18},
            as_of_date=AS_OF,
        )
        assert context['mode'] == LEAGUE_MODE_DEPTH_HEALTHY
        assert context['generated'] is True
        assert _no_forbidden_language(context)

    def test_neutral_fallback_when_no_dominant_pattern(self):
        # A low-story day with only watch-level stories and no league signal: no
        # pressure, no broad depth -> a truthful neutral observation, no drama.
        context = build_league_context([_story('watch') for _ in range(4)], as_of_date=AS_OF)
        assert context['day_class'] == DAY_LOW_STORY
        assert context['mode'] == LEAGUE_MODE_NEUTRAL
        assert context['generated'] is False
        assert context['quality_status'] == QUALITY_NEUTRAL
        assert _no_forbidden_language(context)

    def test_no_fabricated_claims_evidence_matches_items(self):
        items = [
            _story('stressed'),
            _story('rested'),
            _story('watch'),
            _story('stressed', available=False),
        ]
        context = build_league_context(items, as_of_date=AS_OF)
        evidence = context['evidence']
        assert evidence['team_story_count'] == 4
        assert evidence['publishable_story_count'] == 3  # suppressed item excluded
        assert evidence['pressure_story_count'] == 1
        assert evidence['rest_story_count'] == 1
        assert evidence['watch_story_count'] == 1
        assert _no_forbidden_language(context)


class TestStoryContinuity:
    def test_new_when_no_prior(self):
        cont = build_story_continuity(_item(1), None)
        assert cont['state'] == CONTINUITY_NEW
        assert cont['reason'] == 'no_prior_canonical_story'
        assert cont['compared'] is False

    def test_new_when_prior_was_suppressed(self):
        cont = build_story_continuity(_item(1), _item(1, available=False))
        assert cont['state'] == CONTINUITY_NEW
        assert cont['reason'] == 'prior_story_was_suppressed'

    def test_ongoing_same_type_different_headline(self):
        prior = _item(1, story_type='coverage_pressure', headline='Old', date='2026-06-21')
        cont = build_story_continuity(
            _item(1, story_type='coverage_pressure', headline='New'), prior)
        assert cont['state'] == CONTINUITY_ONGOING
        assert cont['reason'] == 'story_type_persisted'
        assert cont['previous_story_id'] == '1:2026-06-21'
        assert cont['previous_story_type'] == 'coverage_pressure'
        assert cont['changed_since'] == '2026-06-21'

    def test_unchanged_same_type_same_headline(self):
        prior = _item(1, story_type='coverage_pressure', headline='Same', date='2026-06-21')
        cont = build_story_continuity(
            _item(1, story_type='coverage_pressure', headline='Same'), prior)
        assert cont['state'] == CONTINUITY_UNCHANGED
        assert cont['reason'] == 'story_unchanged'

    def test_changed_when_story_type_changes(self):
        prior = _item(1, story_type='coverage_pressure', date='2026-06-21')
        cont = build_story_continuity(_item(1, story_type='depth_constraint'), prior)
        assert cont['state'] == CONTINUITY_CHANGED
        assert cont['reason'] == 'story_type_changed'
        assert cont['evidence']['story_type_changed'] is True

    def test_resolved_when_prior_published_today_suppressed(self):
        prior = _item(1, story_type='coverage_pressure', date='2026-06-21')
        cont = build_story_continuity(_item(1, available=False), prior)
        assert cont['state'] == CONTINUITY_RESOLVED
        assert cont['reason'] == 'prior_story_no_longer_publishes'

    def test_unavailable_when_both_suppressed(self):
        cont = build_story_continuity(_item(1, available=False), _item(1, available=False))
        assert cont['state'] == CONTINUITY_UNAVAILABLE
        assert cont['reason'] == 'no_publishable_story_today'

    def test_unavailable_when_no_prior_and_suppressed(self):
        cont = build_story_continuity(_item(1, available=False), None)
        assert cont['state'] == CONTINUITY_UNAVAILABLE
        assert cont['reason'] == 'no_prior_canonical_story'

    def test_suppressed_story_never_claims_continuation(self):
        # A suppressed story is never ongoing/unchanged/changed.
        cont = build_story_continuity(_item(1, available=False), _item(1, story_type='coverage_pressure'))
        assert cont['state'] in (CONTINUITY_RESOLVED, CONTINUITY_UNAVAILABLE)
        assert cont['evidence']['today_publishable'] is False

    def test_deterministic(self):
        prior = _item(1, story_type='coverage_pressure', headline='X', date='2026-06-21')
        today = _item(1, story_type='coverage_pressure', headline='Y')
        assert build_story_continuity(today, prior) == build_story_continuity(today, prior)

    def test_feed_items_have_continuity_new_without_prior(self):
        feed = build_canonical_story_feed(
            [_descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1)}),
        )
        assert feed['items'][0]['continuity']['state'] == CONTINUITY_NEW

    def test_feed_continuity_ongoing_with_prior(self):
        prior = [_item(1, story_type='coverage_pressure', headline='Yesterday headline', date='2026-06-21')]
        feed = build_canonical_story_feed(
            [_descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1)}),  # coverage_pressure
            prior_stories=prior,
        )
        cont = feed['items'][0]['continuity']
        assert cont['state'] == CONTINUITY_ONGOING
        assert cont['previous_story_id'] == '1:2026-06-21'

    def test_feed_continuity_resolved_when_today_suppressed(self):
        prior = [_item(2, story_type='coverage_pressure', headline='Yesterday', date='2026-06-21')]
        feed = build_canonical_story_feed(
            [_descriptor(2)],
            as_of_date=AS_OF,
            story_builder=_builder({2: _neutral_payload(2)}),
            prior_stories=prior,
        )
        assert feed['items'][0]['continuity']['state'] == CONTINUITY_RESOLVED

    def test_league_context_has_continuity(self):
        feed = build_canonical_story_feed(
            [_descriptor(1)],
            as_of_date=AS_OF,
            story_builder=_builder({1: _available_payload(1)}),
            prior_league_context={'mode': 'broadly_stable', 'as_of_date': '2026-06-21'},
        )
        cont = feed['league_context']['continuity']
        assert cont['state'] in ('new', 'unchanged', 'changed')
        assert cont['previous_mode'] == 'broadly_stable'
