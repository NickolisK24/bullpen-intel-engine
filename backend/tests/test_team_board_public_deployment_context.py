"""Public TB-05 facts stay separate from internal entry and leverage rules."""

from datetime import date
from types import SimpleNamespace as Row

from models.play_by_play_foundation import PlayByPlayProcessedGame
from services.team_board_public_deployment_context import (
    CONTRACT,
    build_public_deployment_context,
)
from services.public_serving_authority import (
    _frozen_roles_deployment_carrier,
    _frozen_legacy_deployment_profile_for_view,
    _frozen_roles_deployment_for_view,
)
from services.pitcher_public_labels import ROLE_PUBLIC_LABELS


DAY = date(2026, 9, 21)
TEAM = 110
OTHER = 111


def _log(game, *, team=TEAM, li=None, day=DAY, save=False, hold=False):
    return Row(
        mlb_game_pk=game, appearance_team_id=team, game_date=day,
        games_started=0, game_type='R', leverage_index=li,
        save=save, hold=hold,
    )


def _pitcher(pid=1):
    return Row(id=pid, mlb_id=1000 + pid)


def _event(game, index, pitcher, *, inning, fielding, home=TEAM,
           away=OTHER, home_score=0, away_score=0):
    return Row(
        mlb_game_pk=game, id=index, event_index=index,
        pitcher_mlb_id=pitcher, inning=inning,
        fielding_team_id=fielding, home_team_id=home, away_team_id=away,
        home_score_at_event=home_score, away_score_at_event=away_score,
    )


def _marker(*, home=TEAM, away=OTHER):
    return Row(
        processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
        game_date=DAY, home_team_id=home, away_team_id=away,
    )


def _build(rows, events=None, markers=None):
    return build_public_deployment_context(
        TEAM, rows, DAY,
        events_by_game=events or {}, markers=markers or {},
    )


def test_entry_score_and_recorded_li_bands_are_factual_and_complete():
    pitcher = _pitcher()
    rows = [
        (_log(1, li=1.5), pitcher),
        (_log(2, li=.85), pitcher),
        (_log(3, li=1.1), pitcher),
    ]
    events = {
        1: [_event(1, 1, 2000, inning=8, fielding=OTHER, home_score=3, away_score=1),
            _event(1, 2, 1001, inning=8, fielding=TEAM, home_score=3, away_score=1)],
        2: [_event(2, 1, 2000, inning=9, fielding=OTHER, home_score=2, away_score=2),
            _event(2, 2, 1001, inning=9, fielding=TEAM, home_score=2, away_score=2)],
        3: [_event(3, 1, 2000, inning=10, fielding=OTHER, home_score=1, away_score=2),
            _event(3, 2, 1001, inning=10, fielding=TEAM, home_score=1, away_score=2)],
    }
    profile = _build(rows, events, {game: _marker() for game in events})['profiles'][0]
    assert profile['entry_inning']['status'] == 'complete'
    assert profile['entry_inning']['by_inning'] == [
        {'inning': 8, 'appearances': 1},
        {'inning': 9, 'appearances': 1},
        {'inning': 10, 'appearances': 1},
    ]
    assert profile['entry_inning']['eighth_or_later_appearances'] == 3
    assert profile['entry_inning']['extra_inning_appearances'] == 1
    assert [profile['score_context'][key] for key in ('leading', 'tied', 'trailing')] == [1, 1, 1]
    assert [profile['leverage'][key] for key in ('low', 'middle', 'high')] == [1, 1, 1]
    assert profile['leverage']['status'] == 'complete'


def test_missing_evidence_is_independent_and_save_hold_never_fills_li():
    pitcher = _pitcher()
    rows = [(_log(1, li=None, save=True, hold=True), pitcher), (_log(2, li=2.1), pitcher)]
    events = {1: [
        _event(1, 1, 2000, inning=6, fielding=OTHER, home_score=None),
        _event(1, 2, 1001, inning=6, fielding=TEAM),
    ]}
    profile = _build(rows, events, {1: _marker()})['profiles'][0]
    assert profile['entry_inning']['status'] == 'partial'
    assert profile['entry_inning']['by_inning'] == [{'inning': 6, 'appearances': 1}]
    assert profile['score_context']['status'] == 'unknown'
    assert profile['score_context']['tied'] == 0
    assert profile['leverage']['status'] == 'partial'
    assert profile['leverage']['known_appearances'] == 1
    assert profile['leverage']['high'] == 1


def test_missing_li_is_unknown_not_low_even_with_save_and_hold():
    result = _build([(_log(1, save=True, hold=True), _pitcher())])
    leverage = result['profiles'][0]['leverage']
    assert leverage['status'] == 'unknown'
    assert leverage['known_appearances'] == 0
    assert leverage['low'] == leverage['middle'] == leverage['high'] == 0


def test_early_entry_and_away_team_score_perspective_are_observed():
    pitcher = _pitcher()
    events = {1: [
        _event(1, 1, 2000, inning=3, fielding=OTHER, home=OTHER,
               away=TEAM, home_score=4, away_score=2),
        _event(1, 2, 1001, inning=3, fielding=TEAM, home=OTHER,
               away=TEAM, home_score=4, away_score=2),
    ]}
    profile = _build([(_log(1, li=float('nan')), pitcher)], events, {
        1: _marker(home=OTHER, away=TEAM),
    })['profiles'][0]
    assert profile['entry_inning']['by_inning'] == [{'inning': 3, 'appearances': 1}]
    assert profile['score_context']['trailing'] == 1
    assert profile['leverage']['status'] == 'unknown'


def test_wrong_game_marker_withholds_entry_but_not_recorded_li():
    events = {1: [
        _event(1, 1, 2000, inning=8, fielding=OTHER),
        _event(1, 2, 1001, inning=8, fielding=TEAM),
    ]}
    wrong = Row(
        processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
        game_date=date(2026, 9, 20), home_team_id=TEAM, away_team_id=OTHER,
    )
    profile = _build([(_log(1, li=2.0), _pitcher())], events, {1: wrong})['profiles'][0]
    assert profile['entry_inning']['status'] == 'unknown'
    assert profile['score_context']['status'] == 'unknown'
    assert profile['leverage']['high'] == 1


def test_appearance_team_and_14_day_boundary_exclude_prior_club_and_old_work():
    pitcher = _pitcher()
    result = _build([
        (_log(1, team=OTHER, li=2.0), pitcher),
        (_log(2, li=2.0, day=date(2026, 9, 7)), pitcher),
        (_log(3, li=2.0, day=date(2026, 9, 8)), pitcher),
    ])
    assert result['contract'] == CONTRACT
    assert result['role_movement'] == {'status': 'unavailable', 'reason_code': 'not_published'}
    assert len(result['profiles']) == 1
    assert result['profiles'][0]['leverage']['appearances'] == 1


def test_no_qualifying_appearance_has_no_fabricated_profile():
    result = _build([(_log(1, team=OTHER), _pitcher())])
    assert result['profiles'] == []


def test_current_arm_without_qualifying_work_has_unavailable_domains_not_zero_evidence():
    result = build_public_deployment_context(
        TEAM, [], DAY, markers={}, events_by_game={}, pitcher_ids=[1],
    )
    profile = result['profiles'][0]
    assert profile['pitcher_id'] == 1
    for name in ('entry_inning', 'score_context', 'leverage'):
        assert profile[name]['status'] == 'unavailable'
        assert profile[name]['appearances'] == 0
        assert profile[name]['known_appearances'] == 0


def test_frozen_attachment_rejects_other_team_or_date_without_affecting_board():
    snapshot = Row(data_through=DAY)
    carrier = {
        'contract': CONTRACT, 'method_version': CONTRACT,
        'team_id': TEAM, 'data_through': DAY.isoformat(),
        'window_days': 14, 'profiles': [{
            'team_id': TEAM, 'pitcher_id': 1,
            'public_role_read': {'key': 'limited_read'},
            'context': {'pitcher_id': 1},
            'observed_profile': None,
        }],
    }
    authority = {
        'method_version': CONTRACT, 'public_contract_version': CONTRACT,
        'team_board_package_contract': 'trusted_team_board_publication_v1',
        'data_through': DAY.isoformat(),
    }
    package = {'roles_deployment': carrier, 'roles_deployment_authority': authority}
    assert _frozen_roles_deployment_for_view(snapshot, package, TEAM) == carrier
    assert _frozen_roles_deployment_for_view(snapshot, package, OTHER) is None
    assert _frozen_roles_deployment_for_view(Row(data_through=date(2026, 9, 20)), package, TEAM) is None
    altered = {**carrier, 'profiles': [{**carrier['profiles'][0], 'context': {'pitcher_id': 2}}]}
    assert _frozen_roles_deployment_for_view(
        snapshot, {**package, 'roles_deployment': altered}, TEAM,
    ) is None


def test_public_role_vocabulary_is_unchanged_and_has_no_closer():
    assert {value['label'] for value in ROLE_PUBLIC_LABELS.values()} == {
        'Trusted Arm', 'Setup Arm', 'Coverage Arm', 'Middle Relief Arm', 'Role Unclear',
    }


def test_older_frozen_profile_stays_readable_without_request_time_recomputation():
    profile = {
        'contract': 'team_board_deployment_profile_carrier_v1',
        'data_through': DAY.isoformat(), 'profiles': [],
    }
    package = {
        'deployment_profile': profile,
        'deployment_profile_authority': {
            'method_version': 'public_team_deployment_profile_v1',
            'public_contract_version': 'public_team_deployment_profile_public_v1',
            'team_board_package_contract': 'trusted_team_board_publication_v1',
            'data_through': DAY.isoformat(),
        },
    }
    snapshot = Row(data_through=DAY)
    assert _frozen_legacy_deployment_profile_for_view(snapshot, package) == profile
    assert _frozen_legacy_deployment_profile_for_view(
        snapshot, {**package, 'roles_deployment': {'corrupt': True}},
    ) is None


def test_public_role_is_copied_verbatim_without_closer_inference():
    role = {'kind': 'public_role_read', 'key': 'limited_read', 'label': 'Role Unclear'}
    observed = {'pitcher_id': 1, 'saves': 2, 'holds': 1, 'games_finished': 2}
    context = {
        'contract': CONTRACT, 'data_through': DAY.isoformat(), 'window_days': 14,
        'profiles': [{'pitcher_id': 1, 'entry_inning': {'by_inning': [{'inning': 9, 'appearances': 1}]}}],
    }
    carrier = _frozen_roles_deployment_carrier(
        TEAM, [{'pitcher_id': 1, 'name': 'Observed Arm', 'public_role_read': role}],
        {'profiles': [observed]}, context,
    )
    profile = carrier['profiles'][0]
    assert profile['public_role_read'] == role
    assert profile['observed_profile'] == observed
    assert profile['context']['entry_inning']['by_inning'][0]['inning'] == 9
    assert 'closer' not in repr(carrier).lower()
