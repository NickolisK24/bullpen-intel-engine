"""WP44 private briefing and durable posting receipt contracts."""

from datetime import datetime, timezone

import pytest
from flask import Flask

from models.editorial_post_history import EditorialPostHistory
from services import slate_briefing
from services.slate_briefing import (
    PostingValidationError,
    build_slate_briefing,
    mark_candidate_posted,
    recent_posting_history,
    resolve_briefing_date,
)
from services.slate_editorial_ranker import repetition_penalty
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
import models.prospect  # noqa: F401


NOW = datetime(2026, 7, 18, 14, tzinfo=timezone.utc)


def arm(name, player_id):
    return {
        'player_id': player_id, 'name': name, 'last_outing_date': '2026-07-17',
        'last_outing_pitch_count': 20, 'trailing_pitches': 30,
        'workload_share_pct': 30.0,
        'appearances': [{'date': '2026-07-17', 'pitch_count': 20, 'game_pk': 8000 + player_id}],
    }


def candidate(*, candidate_id='2026-07-19:2-1:7001', score=72, publishable=True,
              reasons=None, game_pks=None, doubleheader=False, shape='narrow'):
    home = {'team_id': 1, 'team_name': 'Home Club', 'team_abbreviation': 'HOM', 'data_freshness': {'state': 'fresh', 'data_through': '2026-07-18'}, 'named_arms_evidence': {'complete': True, 'top_relievers': [arm('Home Arm', 1)]}}
    away = {'team_id': 2, 'team_name': 'Away Club', 'team_abbreviation': 'AWY', 'data_freshness': {'state': 'fresh', 'data_through': '2026-07-18'}, 'named_arms_evidence': {'complete': True, 'top_relievers': [arm('Away Arm', 2)]}}
    return {
        'candidate_id': candidate_id, 'briefing_date': '2026-07-19', 'game_pk': 7001,
        'game_pks': game_pks or [7001], 'doubleheader': doubleheader,
        'first_pitch_et': '2026-07-19T19:10:00-04:00',
        'games': [{'game_pk': pk, 'status': {'detailed': 'Scheduled', 'normalized': 'upcoming'}} for pk in (game_pks or [7001])],
        'score_version': 'slate_editorial_v1', 'home_team': home, 'away_team': away,
        'home_team_story_score': score, 'away_team_story_score': 30,
        'matchup_contrast_score': 0, 'final_editorial_score': score,
        'featured_team': home, 'component_breakdown': {'home_team': {}, 'away_team': {}},
        'shape': shape, 'publishable': publishable,
        'withholding_reasons': reasons or ([] if publishable else ['no_distinct_editorial_signal']),
        'evidence_completeness': {'home_team': True, 'away_team': True, 'featured_team': True},
        'data_freshness': {'schedule': {'state': 'fresh', 'schedule_data_through': '2026-07-18T12:00:00Z'}, 'featured_team': home['data_freshness']},
        'plain_one_liner': 'Home Club has a narrow relief-work pattern worth monitoring.' if publishable else None,
        'evidence_reference': f'evidence-{candidate_id}',
    }


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_resolves_today_tomorrow_and_explicit_date_and_rejects_invalid():
    assert resolve_briefing_date('today', now=NOW).isoformat() == '2026-07-18'
    assert resolve_briefing_date('tomorrow', now=NOW).isoformat() == '2026-07-19'
    assert resolve_briefing_date('2026-08-01', now=NOW).isoformat() == '2026-08-01'
    with pytest.raises(PostingValidationError, match='invalid_briefing_date'):
        resolve_briefing_date('next-week', now=NOW)


def test_empty_slate_and_all_withheld_have_no_top_recommendation(app, monkeypatch):
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [])
    assert 'top_recommendation' not in build_slate_briefing('tomorrow', now=NOW)
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [candidate(publishable=False)])
    briefing = build_slate_briefing('tomorrow', now=NOW)
    assert briefing['ranked_highest'] == candidate()['candidate_id']
    assert 'top_recommendation' not in briefing
    assert briefing['candidates'][0]['ranked_highest'] is True


def test_recommendation_can_skip_higher_scoring_withheld_candidate(app, monkeypatch):
    withheld = candidate(candidate_id='2026-07-19:4-3:7000', score=90, publishable=False, reasons=['schedule_data_not_fresh'])
    allowed = candidate(score=70)
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [withheld, allowed])
    briefing = build_slate_briefing('tomorrow', now=NOW)
    assert briefing['ranked_highest'] == withheld['candidate_id']
    assert briefing['top_recommendation'] == allowed['candidate_id']
    assert briefing['candidates'][0]['recommended_to_post'] is False
    assert briefing['candidates'][1]['recommended_to_post'] is True


def test_split_doubleheader_and_deterministic_order_are_preserved(app, monkeypatch):
    first = candidate(candidate_id='2026-07-19:2-1:7001-7002', game_pks=[7001, 7002], doubleheader=True, score=80)
    second = candidate(candidate_id='2026-07-19:4-3:7003', score=70)
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [first, second])
    briefing = build_slate_briefing('tomorrow', now=NOW)
    assert [item['candidate_id'] for item in briefing['candidates']] == [first['candidate_id'], second['candidate_id']]
    assert briefing['candidates'][0]['game_pks'] == [7001, 7002]
    assert briefing['candidates'][0]['doubleheader'] is True


def test_stale_schedule_and_bullpen_reasons_remain_visible(app, monkeypatch):
    stale = candidate(publishable=False, reasons=['schedule_data_not_fresh', 'team_data_not_fresh'])
    stale['data_freshness']['schedule']['state'] = 'stale'
    stale['featured_team']['data_freshness']['state'] = 'stale'
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [stale])
    result = build_slate_briefing('tomorrow', now=NOW)['candidates'][0]
    assert result['withholding_reasons'] == ['schedule_data_not_fresh', 'team_data_not_fresh']
    assert result['platform_drafts'] == {}


def _posting_payload(item, **overrides):
    payload = {
        'candidate_id': item['candidate_id'], 'evidence_reference': item['evidence_reference'],
        'source_briefing_date': '2026-07-19', 'platform': 'X',
        'generated_draft_text': item['plain_one_liner'], 'final_post_text': 'Edited final post.',
    }
    payload.update(overrides)
    return payload


def test_mark_posted_persists_complete_receipt_and_feeds_repetition(app, monkeypatch):
    item = candidate()
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [item])
    briefing_item = build_slate_briefing('tomorrow', now=NOW)['candidates'][0]
    payload = _posting_payload(briefing_item, generated_draft_text=briefing_item['platform_drafts']['X']['text'], external_post_url='https://example.com/post/1')
    receipt = mark_candidate_posted(payload, now=NOW)
    assert receipt.platform == 'X'
    assert receipt.final_post_text == 'Edited final post.'
    assert receipt.external_post_url == 'https://example.com/post/1'
    assert receipt.source_briefing_date.isoformat() == '2026-07-19'
    assert receipt.to_dict()['team_ids'] == [1, 2]
    assert recent_posting_history()[0]['candidate_id'] == item['candidate_id']
    assert repetition_penalty(1, 'narrow', [receipt], as_of='2026-07-20') == 18


@pytest.mark.parametrize('overrides,code', [
    ({'platform': 'TikTok'}, 'invalid_platform'),
    ({'final_post_text': '  '}, 'final_post_text_required'),
    ({'candidate_id': 'unknown'}, 'unknown_or_stale_candidate'),
    ({'evidence_reference': 'old-evidence'}, 'evidence_mismatch'),
    ({'external_post_url': 'javascript:alert(1)'}, 'invalid_external_post_url'),
])
def test_mark_posted_rejects_invalid_or_stale_contracts(app, monkeypatch, overrides, code):
    item = candidate()
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [item])
    briefing_item = build_slate_briefing('tomorrow', now=NOW)['candidates'][0]
    with pytest.raises(PostingValidationError) as exc:
        mark_candidate_posted(_posting_payload(briefing_item, generated_draft_text=briefing_item['platform_drafts']['X']['text'], **overrides), now=NOW)
    assert exc.value.code == code


def test_mark_posted_rejects_withheld_candidate(app, monkeypatch):
    item = candidate(publishable=False)
    monkeypatch.setattr(slate_briefing, 'build_ranked_slate', lambda *_args, **_kwargs: [item])
    with pytest.raises(PostingValidationError) as exc:
        mark_candidate_posted(_posting_payload(item), now=NOW)
    assert exc.value.code == 'candidate_not_publishable'
