"""Tests for the Intelligence Surface service (League Today's Lead Story).

The service selects the single most important publishable COIN StoryPackage for a
reference date. These cover deterministic ranking, publishability filtering, the
empty/fallback state, fail-closed candidate handling, reference-date passthrough,
the rendered drafts, no future language, and that selection neither mutates data
nor disturbs the legacy story path. Ranking tests inject a controlled
``inspect_fn`` so the order is exercised independently of the narrative engine;
end-to-end tests drive the real pipeline through the seeded fixtures.
"""

import copy

from services import intelligence_surface_service as surface
from services.coin_seeded_fixtures import SEEDED_FIXTURES, fixture_for
from services.coin_story_inspection import inspect_team_story
from services.intelligence_surface_service import (
    EMPTY_NO_CANDIDATES,
    EMPTY_NO_PUBLISHABLE,
    build_today_lead_story,
)

_FORBIDDEN_FUTURE = ('tomorrow', 'tonight', 'next game', 'next week', 'upcoming', 'series')


# ── Controlled-package helpers (ranking decoupled from the engine) ─────────────

def _fake_inspected(team_id, *, publishable=True, priority='HIGH', importance='MEDIUM',
                    confidence='HIGH', primary='protected_game_shape', game_pk=None,
                    late_runs=0, largest_lead=0, largest_deficit=0):
    game_pk = game_pk if game_pk is not None else team_id * 1000
    return {
        'team_id': team_id,
        'game_pk': game_pk,
        'publishable': publishable,
        'publish_reason': 'high_priority_narrative',
        'confidence': confidence,
        'story_priority': priority,
        'game_importance': importance,
        'package': {
            'team_id': team_id,
            'game_pk': game_pk,
            'publish_reason': 'high_priority_narrative',
            'primary_story': primary,
            'story_priority': priority,
            'game_importance': importance,
            'confidence': confidence,
            'completed_game_context': {
                'team_id': team_id,
                'game_pk': game_pk,
                'late_runs_allowed': late_runs,
                'largest_lead': largest_lead,
                'largest_deficit': largest_deficit,
            },
        },
        'drafts': [
            {'writer': 'team_story', 'headline': f'H{team_id}', 'body': 'b',
             'observations': [], 'evidence': [], 'text': 't', 'rendered_text': 'r',
             'metadata': {}, 'is_internal_preview': False},
        ],
    }


def _inspect_fn_from(table):
    """An inspect_fn that returns a pre-built inspected dict keyed by team_id."""
    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        return copy.deepcopy(table[team_id])
    return inspect


def _contexts(*team_ids):
    return [{'team_id': tid} for tid in team_ids]


def _completed_context(team_id, *, tag='lost_game_shape', confidence='HIGH', **over):
    base = {
        'team_id': team_id,
        'game_pk': team_id * 1000,
        'bullpen_story_tag': tag,
        'confidence': confidence,
        'starter_name': 'Sample Starter',
        'starter_ip': 6.0,
        'bullpen_entry_inning': 7,
        'bullpen_entry_score_for': 6,
        'bullpen_entry_score_against': 2,
        'lead_when_bullpen_entered': 4,
        'largest_lead': 4,
        'largest_deficit': 3,
        'late_runs_allowed': 7,
        'runs_allowed_innings_7_to_9': 7,
        'lead_protected': False,
        'lead_lost': True,
        'turning_inning': 8,
        'game_shape_created': 'normal_start',
    }
    base.update(over)
    return base


# ── Ranking: priority dominates ───────────────────────────────────────────────

def test_selects_critical_over_high():
    table = {
        1: _fake_inspected(1, priority='HIGH'),
        2: _fake_inspected(2, priority='CRITICAL'),
        3: _fake_inspected(3, priority='HIGH'),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2, 3),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['status'] == 'ok'
    assert result['lead_story']['team_id'] == 2
    assert result['lead_story']['selection']['rank'] == 1
    assert result['lead_story']['selection']['story_priority'] == 'CRITICAL'


def test_selects_high_over_medium():
    table = {
        1: _fake_inspected(1, priority='MEDIUM'),
        2: _fake_inspected(2, priority='HIGH'),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['lead_story']['team_id'] == 2
    assert result['lead_story']['selection']['story_priority'] == 'HIGH'


def test_importance_then_confidence_then_primary_break_ties():
    # Same priority; importance breaks first (team 2 HIGH beats team 1 LOW).
    table = {
        1: _fake_inspected(1, priority='HIGH', importance='LOW'),
        2: _fake_inspected(2, priority='HIGH', importance='HIGH'),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['lead_story']['team_id'] == 2

    # Same priority+importance+confidence; primary_story weight breaks the tie:
    # lost_game_shape outranks protected_game_shape.
    table = {
        5: _fake_inspected(5, primary='protected_game_shape'),
        6: _fake_inspected(6, primary='lost_game_shape'),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(5, 6),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['lead_story']['team_id'] == 6
    assert result['lead_story']['selection']['primary_story'] == 'lost_game_shape'


def test_late_runs_then_swing_break_further_ties():
    # Everything equal except late damage: more late runs sorts first.
    table = {
        1: _fake_inspected(1, primary='lost_game_shape', late_runs=2, largest_lead=3),
        2: _fake_inspected(2, primary='lost_game_shape', late_runs=7, largest_lead=3),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['lead_story']['team_id'] == 2

    # Equal late runs: larger lead/deficit swing sorts first.
    table = {
        1: _fake_inspected(1, primary='lost_game_shape', late_runs=4, largest_lead=2),
        2: _fake_inspected(2, primary='lost_game_shape', late_runs=4, largest_deficit=6),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['lead_story']['team_id'] == 2


def test_deterministic_team_id_tiebreaker():
    # Identical on every signal -> lowest team_id wins, and repeated runs agree.
    table = {
        9: _fake_inspected(9, primary='lost_game_shape', late_runs=3, largest_lead=3),
        4: _fake_inspected(4, primary='lost_game_shape', late_runs=3, largest_lead=3),
        7: _fake_inspected(7, primary='lost_game_shape', late_runs=3, largest_lead=3),
    }
    contexts = _contexts(9, 4, 7)
    first = build_today_lead_story(candidate_contexts=contexts,
                                   inspect_fn=_inspect_fn_from(table))
    second = build_today_lead_story(candidate_contexts=contexts,
                                    inspect_fn=_inspect_fn_from(table))
    assert first['lead_story']['team_id'] == 4
    assert first == second


# ── Publishability filtering ──────────────────────────────────────────────────

def test_filters_unpublishable_packages():
    table = {
        1: _fake_inspected(1, publishable=False, priority='CRITICAL'),
        2: _fake_inspected(2, publishable=True, priority='MEDIUM'),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    # The CRITICAL one is unpublishable, so the publishable MEDIUM is the lead.
    assert result['lead_story']['team_id'] == 2
    assert result['candidates_considered'] == 2
    assert result['publishable_candidates'] == 1


# ── Empty / fallback states ───────────────────────────────────────────────────

def test_empty_when_no_publishable_stories():
    table = {
        1: _fake_inspected(1, publishable=False),
        2: _fake_inspected(2, publishable=False),
    }
    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=_inspect_fn_from(table))
    assert result['status'] == 'empty'
    assert result['lead_story'] is None
    assert result['empty_reason'] == EMPTY_NO_PUBLISHABLE
    assert result['candidates_considered'] == 2
    assert result['publishable_candidates'] == 0


def test_empty_when_no_candidates():
    result = build_today_lead_story(candidate_contexts=[],
                                    inspect_fn=_inspect_fn_from({}))
    assert result['status'] == 'empty'
    assert result['lead_story'] is None
    assert result['empty_reason'] == EMPTY_NO_CANDIDATES
    assert result['candidates_considered'] == 0


# ── Fail closed: one bad candidate does not sink the slate ────────────────────

def test_skips_one_failed_candidate_without_failing_all():
    good = _fake_inspected(2, priority='CRITICAL')

    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        if team_id == 1:
            raise RuntimeError('boom')
        return copy.deepcopy(good)

    result = build_today_lead_story(candidate_contexts=_contexts(1, 2),
                                    inspect_fn=inspect)
    assert result['status'] == 'ok'
    assert result['lead_story']['team_id'] == 2
    assert result['candidates_considered'] == 2
    assert result['errors'] == 1
    assert result['publishable_candidates'] == 1


# ── Bounded on-demand snapshot warming ────────────────────────────────────────

def test_bounded_regeneration_renders_top_ranked_candidate_first():
    contexts = [
        _completed_context(
            147,
            tag='bullpen_overexposed',
            confidence='MEDIUM',
            game_shape_created='short_start',
            late_runs_allowed=1,
            runs_allowed_innings_7_to_9=1,
            lead_lost=None,
        ),
        _completed_context(137),
    ]
    seen = []

    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        seen.append(team_id)
        if team_id == 137:
            return _fake_inspected(
                team_id,
                priority='CRITICAL',
                importance='HIGH',
                primary='lost_game_shape',
                late_runs=7,
                largest_lead=4,
            )
        return _fake_inspected(
            team_id,
            priority='MEDIUM',
            importance='LOW',
            primary='bullpen_overexposed',
        )

    result = build_today_lead_story(
        reference_date='2026-06-25',
        candidate_contexts=contexts,
        inspect_fn=inspect,
        bounded=True,
    )

    assert result['status'] == 'ok'
    assert result['lead_story']['team_id'] == 137
    assert seen == [137]
    assert result['candidates_considered'] == 2
    assert result['publishable_candidates'] == 2
    assert result['errors'] == 0


def test_bounded_regeneration_continues_after_top_candidate_error():
    contexts = [
        _completed_context(137),
        _completed_context(
            147,
            tag='bullpen_overexposed',
            confidence='MEDIUM',
            game_shape_created='short_start',
            late_runs_allowed=1,
            runs_allowed_innings_7_to_9=1,
            lead_lost=None,
        ),
    ]
    seen = []

    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        seen.append(team_id)
        if team_id == 137:
            raise RuntimeError('render failed')
        return _fake_inspected(
            team_id,
            priority='MEDIUM',
            importance='LOW',
            primary='bullpen_overexposed',
        )

    result = build_today_lead_story(
        reference_date='2026-06-25',
        candidate_contexts=contexts,
        inspect_fn=inspect,
        bounded=True,
    )

    assert result['status'] == 'ok'
    assert result['lead_story']['team_id'] == 147
    assert seen == [137, 147]
    assert result['candidates_considered'] == 2
    assert result['publishable_candidates'] == 2
    assert result['errors'] == 1


# ── Reference date passthrough ────────────────────────────────────────────────

def test_respects_reference_date():
    seen = {}

    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        seen['reference_date'] = reference_date
        return _fake_inspected(team_id, priority='HIGH')

    result = build_today_lead_story(reference_date='2026-06-26',
                                    candidate_contexts=_contexts(1),
                                    inspect_fn=inspect)
    assert result['reference_date'] == '2026-06-26'
    assert seen['reference_date'] == '2026-06-26'


# ── End-to-end through the real pipeline (seeded fixtures) ─────────────────────

def _seeded_inspect_fn():
    """Real inspection driven by the seeded fixtures (no DB, no MLB)."""
    def inspect(team_id, *, app=None, reference_date=None, completed_game_context=None):
        fixture = fixture_for(team_id)
        return inspect_team_story(
            team_id, app=None, reference_date=reference_date,
            completed_game_context=fixture['completed_game_context'],
            team_context=fixture['team_context'],
        )
    return inspect


def _seeded_candidate_contexts():
    return [copy.deepcopy(f['completed_game_context']) for f in SEEDED_FIXTURES]


def test_seeded_pipeline_selects_giants_critical_lead():
    result = build_today_lead_story(
        reference_date='2026-06-25',
        candidate_contexts=_seeded_candidate_contexts(),
        inspect_fn=_seeded_inspect_fn(),
    )
    assert result['status'] == 'ok'
    lead = result['lead_story']
    # Giants are the only CRITICAL story among the four seeded fixtures.
    assert lead['team_id'] == 137
    assert lead['selection']['story_priority'] == 'CRITICAL'
    assert lead['selection']['primary_story'] == 'lost_game_shape'
    assert result['publishable_candidates'] == 4
    assert result['candidates_considered'] == 4


def test_seeded_pipeline_returns_package_and_rendered_drafts():
    result = build_today_lead_story(
        candidate_contexts=_seeded_candidate_contexts(),
        inspect_fn=_seeded_inspect_fn(),
    )
    lead = result['lead_story']
    assert lead['package']['primary_story'] == 'lost_game_shape'
    drafts = lead['drafts']
    # A CRITICAL story renders all three existing writers, keyed by writer name.
    assert set(drafts) == {'team_story', 'dashboard', 'morning_brief'}
    assert drafts['team_story']['headline']
    assert drafts['team_story']['body']
    # The drafts come from the existing writers, not recomposed here.
    assert 'the Giants' in drafts['team_story']['body']


def test_seeded_pipeline_introduces_no_future_language():
    result = build_today_lead_story(
        candidate_contexts=_seeded_candidate_contexts(),
        inspect_fn=_seeded_inspect_fn(),
    )
    lead = result['lead_story']
    blob = ' '.join(
        ' '.join([d.get('rendered_text', ''), d.get('text', '')])
        for d in lead['drafts'].values()
    ).lower()
    # Plus the metadata strings the service itself adds.
    blob += ' ' + str(lead['selection']).lower()
    for term in _FORBIDDEN_FUTURE:
        assert term not in blob, term


# ── Determinism / no mutation of the candidate input ──────────────────────────

def test_does_not_mutate_candidate_contexts():
    contexts = _seeded_candidate_contexts()
    before = copy.deepcopy(contexts)
    build_today_lead_story(candidate_contexts=contexts, inspect_fn=_seeded_inspect_fn())
    assert contexts == before


def test_service_module_does_not_import_mlb_or_models_at_top_level():
    # Selection reads existing context; it must not fetch MLB data. Model access
    # is deferred (imported lazily inside the DB path), not at module import.
    import inspect as _inspect

    source = _inspect.getsource(surface)
    assert 'mlb_api' not in source
    assert 'import requests' not in source
