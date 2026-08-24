"""Tests for the Tonight intelligence service (public envelope wrapper).

The wrapper resolves the reference date, derives candidates, strips internal
fields (strength), and shapes the public envelope with honest empty reasons.
These inject schedule/bullpen context for determinism; the endpoint test drives
the HTTP layer and the real schedule path.
"""

import pytest

from services import tonight_intelligence_service as svc
from services.tonight_intelligence_service import serve_tonight

REF = '2026-06-26'
_REAL_DEFAULT_TEAM_STATE_LISTING_BUILDER = svc._default_team_state_listing_builder
_REAL_DEFAULT_WORKLOAD_LISTING_BUILDER = svc._default_workload_listing_builder
_REAL_DEFAULT_PUBLICATION_SIDECAR_BUILDER = svc._default_publication_sidecar_builder

_BANNED = (
    'will win', 'will lose', 'guaranteed', 'probability', 'odds', 'recommend',
    'ranked', 'ranking', 'predict', 'projection', 'betting', 'best option',
    ' lock', 'pick', 'edge', 'fatigue score', 'confidence score',
    'will happen', 'expected to happen', 'healthy', 'injury-free',
)


@pytest.fixture(autouse=True)
def _empty_published_team_state_listing(monkeypatch):
    monkeypatch.setattr(
        svc,
        '_default_team_state_listing_builder',
        lambda: {'teams': []},
    )
    monkeypatch.setattr(
        svc,
        '_default_workload_listing_builder',
        lambda: {'teams': []},
    )
    monkeypatch.setattr(
        svc,
        '_default_publication_sidecar_builder',
        lambda: ({'teams': []}, {'teams': []}),
    )


def _sc(team_id=116, *, playing=True, days_until=3, games_until=3, games_next3=3,
        limitations=None):
    return {
        'team_id': team_id, 'reference_date': REF, 'context_available': True,
        'is_playing_today': playing, 'opponent_today': 'Minnesota Twins',
        'opponent_team_id_today': 142, 'home_away_today': 'home',
        'game_time_today': '2026-06-26T23:10:00Z', 'doubleheader_today': False,
        'games_today_count': 1 if playing else 0,
        'games_played_last_3_days': 3, 'games_played_last_5_days': 5,
        'games_in_next_3_days': games_next3, 'next_off_day': '2026-06-30',
        'days_until_next_off_day': days_until, 'games_until_next_off_day': games_until,
        'is_first_game_after_off_day': False, 'is_last_game_before_off_day': False,
        'consecutive_games_played_entering_today': 3,
        'consecutive_games_scheduled_from_today': 4,
        'limitations': list(limitations or []),
    }


def _pen(*, clean=1, band='thin', paths=2, conc='normal', share=40.0,
         name='Detroit Tigers', names=None):
    return {
        'context_available': True, 'clean_options_count': clean,
        'clean_workload_option_names': list(names or []),
        'optionality_band': band, 'practical_close_game_paths_count': paths,
        'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 1,
        'restricted_arms_count': 3, 'concentration_band': conc,
        'top_three_workload_share_10d': share, 'team_name': name,
    }


def _builder(pen_by_team):
    return lambda team_id, reference_date: pen_by_team.get(team_id)


def _game(game_pk=900001, *, away=116, home=142, status='upcoming'):
    return {
        'game_pk': game_pk,
        'game_date_et': REF,
        'game_time_utc': '2026-06-26T23:10:00Z',
        'away_team_id': away,
        'home_team_id': home,
        'status': {
            'abstract': 'Preview',
            'detailed': 'Scheduled',
            'code': 'S',
            'normalized': status,
        },
        'doubleheader_flag': 'N',
        'game_number': 1,
    }


def _team_state(label, *, data_through='2026-06-25'):
    code = label.lower()
    return {
        'contract': 'team_state_public_v1',
        'available': True,
        'public_state': code,
        'public_label': label,
        'summary': f'Exact {label} summary.',
        'outcome': 'available',
        'unavailable_message': None,
        'reason_code': None,
        'data_through': data_through,
    }


def _team_state_listing(states):
    return {
        'capability': 'league_team_state_listing_v1',
        'teams': [
            {'team_id': team_id, 'team_state': state}
            for team_id, state in states.items()
        ],
    }


def _recent_volume(*, appearances=8, pitchers=5, pitches=121,
                   data_through='2026-06-25'):
    return {
        'contract': 'team_board_workload_windows_carrier_v1',
        'status': 'complete',
        'reason_code': None,
        'data_through': data_through,
        'window_days': 7,
        'window': {
            'through': data_through,
            'relief_appearances': appearances,
            'pitchers_in_relief': pitchers,
            'pitches_total': pitches,
            'appearances_with_pitches': appearances if pitches is not None else 0,
            'start_relief_unknown': 0,
            'sentence': 'Exact canonical appearance sentence.',
            'pitchers_sentence': 'Exact canonical pitcher sentence.',
            'pitches_sentence': 'Exact canonical pitch sentence.',
        },
    }


def _workload_listing(volumes):
    return {
        'capability': 'published_team_workload_listing_v1',
        'teams': [
            {'team_id': team_id, 'recent_bullpen_volume': volume}
            for team_id, volume in volumes.items()
        ],
    }


# ── Status ok with cards ──────────────────────────────────────────────────────

def test_ok_with_cards():
    out = serve_tonight(REF, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['status'] == 'ok'
    assert out['reference_date'] == REF
    assert out['card_count'] == len(out['cards']) == 1
    assert out['empty_reason'] is None
    card = out['cards'][0]
    assert card['team_id'] == 116
    assert card['team_name'] == 'Detroit Tigers'


# ── 7 & 8. Public card field hygiene ──────────────────────────────────────────

def test_public_card_omits_strength_and_keeps_public_fields():
    out = serve_tonight(REF, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    card = out['cards'][0]
    assert 'strength' not in card
    assert 'reference_date' not in card     # carried by the envelope, not the card
    for key in ('team_id', 'team_name', 'headline', 'summary', 'signal_type',
                'signal_family', 'pregame_story', 'evidence', 'schedule_context',
                'bullpen_context', 'limitations'):
        assert key in card
    story = card['pregame_story']
    assert story['label'] == "Tonight's Bullpen Watch"
    assert story['watching'].startswith('Watch ')
    assert not story['why_it_matters'].startswith('This matters because')
    assert story['watch_point'].startswith('The key question is')


def test_card_count_matches_cards_length():
    out = serve_tonight(
        REF, limit=3,
        schedule_contexts=[_sc(116), _sc(118, games_next3=3), _sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({
            116: _pen(clean=1, band='thin'),
            118: _pen(clean=3, band='flexible', conc='narrow', share=55.0),
            120: _pen(clean=0, band='thin', paths=0),
        }))
    assert out['card_count'] == len(out['cards'])


def test_every_game_composes_both_existing_team_contexts_without_duplicate_builds():
    calls = []
    listing_calls = []
    pens = {
        116: _pen(name='Detroit Tigers', names=['Alex Lange', 'Tyler Holton']),
        142: _pen(name='Minnesota Twins', clean=3, band='flexible',
                  conc='balanced', share=31.2, names=['Jhoan Duran']),
    }

    def builder(team_id, reference_date):
        calls.append((team_id, str(reference_date)))
        return pens[team_id]

    away_state = _team_state('Fresh')
    home_state = _team_state('Stretched')

    def state_listing_builder():
        listing_calls.append('called')
        return _team_state_listing({116: away_state, 142: home_state})

    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=builder,
        slate_games=[_game()],
        team_state_listing_builder=state_listing_builder,
    )

    assert out['game_count'] == 1
    assert len(out['games']) == 1
    game = out['games'][0]
    assert game['game_pk'] == 900001
    assert game['game_time_utc'] == '2026-06-26T23:10:00Z'
    assert game['status'] == _game()['status']
    assert game['away']['bullpen_context']['clean_workload_option_names'] == [
        'Alex Lange', 'Tyler Holton',
    ]
    assert game['home']['bullpen_context']['top_three_workload_share_10d'] == 31.2
    assert game['away']['team_state'] == away_state
    assert game['home']['team_state'] == home_state
    assert sorted(team_id for team_id, _ in calls) == [116, 142]
    assert len(calls) == 2
    assert listing_calls == ['called']


def test_recent_volume_passes_through_once_without_cross_team_leakage():
    workload_calls = []
    away_volume = _recent_volume(appearances=9, pitchers=6, pitches=144)
    home_volume = _recent_volume(appearances=4, pitchers=3, pitches=None)

    def workload_listing_builder():
        workload_calls.append('called')
        return _workload_listing({116: away_volume, 142: home_volume})

    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=_builder({116: _pen(), 142: _pen()}),
        slate_games=[_game()],
        workload_listing_builder=workload_listing_builder,
    )

    game = out['games'][0]
    assert workload_calls == ['called']
    assert game['away']['recent_bullpen_volume'] == away_volume
    assert game['home']['recent_bullpen_volume'] == home_volume
    assert game['away']['recent_bullpen_volume'] != game['home']['recent_bullpen_volume']


def test_recent_volume_failure_is_local_to_its_optional_domain():
    def fail_listing():
        raise RuntimeError('frozen workload unavailable')

    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=_builder({116: _pen(), 142: _pen()}),
        slate_games=[_game()],
        team_state_listing_builder=lambda: _team_state_listing({
            116: _team_state('Fresh'),
            142: _team_state('Stretched'),
        }),
        workload_listing_builder=fail_listing,
    )

    game = out['games'][0]
    assert game['away']['status'] == 'available'
    assert game['home']['status'] == 'available'
    assert game['away']['team_state']['public_label'] == 'Fresh'
    assert game['home']['team_state']['public_label'] == 'Stretched'
    assert game['away']['recent_bullpen_volume']['status'] == 'withheld'
    assert game['home']['recent_bullpen_volume']['status'] == 'withheld'
    assert game['away']['recent_bullpen_volume']['window'] is None


def test_team_state_passes_through_withheld_and_missing_without_cross_team_leakage():
    withheld = {
        'contract': 'team_state_public_v1',
        'available': False,
        'public_state': None,
        'public_label': None,
        'summary': None,
        'outcome': 'readiness_unavailable',
        'unavailable_message': 'Exact governed unavailable message.',
        'reason_code': 'published_team_state_artifact_missing',
        'data_through': '2026-06-25',
    }
    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=_builder({116: _pen(), 142: _pen()}),
        slate_games=[_game()],
        team_state_listing_builder=lambda: _team_state_listing({116: withheld}),
    )

    game = out['games'][0]
    assert game['away']['team_state'] == withheld
    assert game['home']['team_state']['available'] is False
    assert game['home']['team_state']['public_label'] is None
    assert game['home']['team_state']['reason_code'] == 'tonight_team_state_listing_unavailable'
    assert game['home']['team_state'] != game['away']['team_state']


def test_team_state_listing_failure_is_local_to_team_state_domain():
    def fail_listing():
        raise RuntimeError('published Team State unavailable')

    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=_builder({116: _pen(), 142: _pen()}),
        slate_games=[_game()],
        team_state_listing_builder=fail_listing,
    )

    game = out['games'][0]
    assert game['away']['status'] == 'available'
    assert game['home']['status'] == 'available'
    assert game['away']['bullpen_context']['context_available'] is True
    assert game['home']['bullpen_context']['context_available'] is True
    assert game['away']['team_state']['available'] is False
    assert game['home']['team_state']['available'] is False


def test_default_team_state_builder_delegates_to_canonical_listing(monkeypatch):
    import services.league_team_state_listing as listing

    expected = _team_state_listing({116: _team_state('Vulnerable')})
    calls = []

    def build_listing():
        calls.append('called')
        return expected

    monkeypatch.setattr(listing, 'build_league_team_state_listing', build_listing)

    assert _REAL_DEFAULT_TEAM_STATE_LISTING_BUILDER() is expected
    assert calls == ['called']


def test_default_workload_builder_delegates_to_frozen_canonical_listing(monkeypatch):
    import services.published_team_workload_listing as listing

    expected = _workload_listing({116: _recent_volume()})
    calls = []

    def build_listing():
        calls.append('called')
        return expected

    monkeypatch.setattr(
        listing,
        'build_published_team_workload_listing',
        build_listing,
    )

    assert _REAL_DEFAULT_WORKLOAD_LISTING_BUILDER() is expected
    assert calls == ['called']


def test_default_publication_sidecars_share_one_trusted_snapshot_resolution(monkeypatch):
    import services.league_team_state_listing as state_listing
    import services.published_team_workload_listing as workload_listing

    resolved = (object(), None)
    resolver_calls = []
    received = []

    def resolve_snapshot():
        resolver_calls.append('called')
        return resolved

    def build_states(*, snapshot_resolver):
        received.append(snapshot_resolver())
        return {'teams': [{'team_id': 116, 'team_state': _team_state('Fresh')}]}

    def build_workload(*, snapshot_resolver):
        received.append(snapshot_resolver())
        return _workload_listing({116: _recent_volume()})

    monkeypatch.setattr(
        state_listing,
        'resolve_current_trusted_dashboard_snapshot',
        resolve_snapshot,
    )
    monkeypatch.setattr(state_listing, 'build_league_team_state_listing', build_states)
    monkeypatch.setattr(
        workload_listing,
        'build_published_team_workload_listing',
        build_workload,
    )

    states, workload = _REAL_DEFAULT_PUBLICATION_SIDECAR_BUILDER()

    assert resolver_calls == ['called']
    assert received == [resolved, resolved]
    assert states['teams'][0]['team_state']['public_label'] == 'Fresh'
    assert workload['teams'][0]['recent_bullpen_volume']['status'] == 'complete'


def test_one_team_context_failure_is_local_to_that_game_side():
    def builder(team_id, reference_date):
        if team_id == 142:
            raise RuntimeError('sidecar unavailable')
        return _pen(names=['Alex Lange'])

    out = serve_tonight(
        REF,
        schedule_contexts=[
            _sc(116),
            {**_sc(142), 'opponent_team_id_today': 116, 'home_away_today': 'away'},
        ],
        bullpen_context_builder=builder,
        slate_games=[_game()],
    )

    game = out['games'][0]
    assert game['away']['status'] == 'available'
    assert game['away']['bullpen_context']['clean_workload_option_names'] == ['Alex Lange']
    assert game['home']['status'] == 'unavailable'
    assert game['home']['limitations'] == ['bullpen_context_unavailable']
    assert game['home']['bullpen_context']['context_available'] is False


# ── Empty states ──────────────────────────────────────────────────────────────

def test_empty_no_schedule_context():
    out = serve_tonight(REF, schedule_contexts=[])
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_schedule_context'
    assert out['cards'] == [] and out['card_count'] == 0


def test_empty_no_teams_playing():
    out = serve_tonight(REF, schedule_contexts=[_sc(116, playing=False)])
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_teams_playing_today'


def test_postponed_game_keeps_canonical_status_without_manufacturing_bullpen_context():
    postponed = _game(status='cancelled')
    postponed['status'] = {
        'abstract': 'Preview',
        'detailed': 'Postponed',
        'code': 'DR',
        'normalized': 'cancelled',
    }
    out = serve_tonight(
        REF,
        schedule_contexts=[_sc(116, playing=False)],
        slate_games=[postponed],
    )

    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_teams_playing_today'
    assert out['game_count'] == 1
    assert out['games'][0]['status'] == postponed['status']
    assert out['games'][0]['away']['status'] == 'unavailable'
    assert out['games'][0]['home']['status'] == 'unavailable'


def test_empty_no_signals():
    # Team plays but its bullpen is deep with an off day right after -> no signal.
    out = serve_tonight(
        REF, schedule_contexts=[_sc(116, days_until=5, games_until=5, games_next3=1)],
        bullpen_context_builder=_builder({116: _pen(clean=5, band='deep', paths=5,
                                                    conc='balanced', share=20.0)}),
        slate_games=[_game(home=116, away=142)])
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_tonight_signals'
    assert out['game_count'] == 1
    assert out['games'][0]['game_pk'] == 900001


# ── Reference date resolution ─────────────────────────────────────────────────

def test_defaults_to_product_current_date(monkeypatch):
    from datetime import date
    monkeypatch.setattr(svc, 'product_current_date', lambda: date(2026, 6, 26))
    out = serve_tonight(None, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['reference_date'] == '2026-06-26'


def test_explicit_reference_date_is_honored():
    out = serve_tonight('2026-07-04', schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['reference_date'] == '2026-07-04'


# ── No ranking / recommendation language ──────────────────────────────────────

def test_response_has_no_forbidden_language():
    out = serve_tonight(
        REF, limit=3,
        schedule_contexts=[_sc(116), _sc(118, games_next3=3), _sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({
            116: _pen(clean=1, band='thin'),
            118: _pen(clean=3, band='flexible', conc='narrow', share=55.0),
            120: _pen(clean=0, band='thin', paths=0),
        }))
    blob = str(out).lower()
    for term in _BANNED:
        assert term not in blob, term


# ── Determinism ───────────────────────────────────────────────────────────────

def test_deterministic_for_same_inputs():
    args = dict(schedule_contexts=[_sc(116), _sc(118, games_next3=3)],
                bullpen_context_builder=_builder({
                    116: _pen(clean=1, band='thin'),
                    118: _pen(clean=3, band='flexible', conc='narrow', share=55.0)}))
    assert serve_tonight(REF, **args) == serve_tonight(REF, **args)


# ── Envelope aggregates card limitations ──────────────────────────────────────

def test_envelope_aggregates_card_limitations():
    out = serve_tonight(
        REF, schedule_contexts=[_sc(116, limitations=['doubleheader_today'])],
        bullpen_context_builder=_builder({116: _pen()}))
    assert 'doubleheader_today' in out['limitations']
