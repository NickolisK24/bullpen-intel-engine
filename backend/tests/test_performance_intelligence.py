"""Current Active-Pen Performance framework and M-001 (D-021).

The framework owns group resolution, qualifying appearances, sample
validation, evidence, freshness, limitations and fail-closed publication, so
these tests live here once. A future metric should need only a registry test
and its own formula test.
"""

from datetime import date

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import performance_intelligence as pi
from services import performance_metrics
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TEAM_ID = 113
OTHER_TEAM_ID = 158
SEASON = 2026
REFERENCE_DATE = date(2026, 7, 30)
M001 = performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA


@pytest.fixture()
def app():
    application = Flask('test_performance_intelligence')
    configure_test_database(application)
    db.init_app(application)
    with application.app_context():
        create_test_schema(application)
        try:
            yield application
        finally:
            db.session.remove()
            drop_test_schema(application)


_next_mlb_id = [810000]


def _pitcher(name, *, team_id=TEAM_ID, active=True):
    _next_mlb_id[0] += 1
    p = Pitcher(
        mlb_id=_next_mlb_id[0], full_name=name, team_id=team_id,
        team_name='Cincinnati Reds', team_abbreviation='CIN',
        active=active, roster_status='Active', position='P',
    )
    db.session.add(p)
    db.session.flush()
    return p


_next_pk = [910000]


def _log(pitcher, *, outs=3, earned_runs=0, games_started=0,
         appearance_team_id=TEAM_ID, game_type='R', game_date=None,
         appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED):
    _next_pk[0] += 1
    log = GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=_next_pk[0],
        game_date=game_date or date(2026, 7, 20), game_type=game_type,
        opponent='Milwaukee Brewers', opponent_abbreviation='MIL',
        games_started=games_started, innings_pitched=outs / 3,
        innings_pitched_outs=outs, earned_runs=earned_runs, runs_allowed=earned_runs,
        pitches_thrown=15, appearance_team_id=appearance_team_id,
        appearance_team_status=appearance_team_status,
        appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    )
    db.session.add(log)
    return log


def _read(team_id=TEAM_ID, metric_id=M001):
    return pi.build_metric_read(
        metric_id, team_id, season=SEASON, reference_date=REFERENCE_DATE,
    )


# ── Registry ────────────────────────────────────────────────────────────────
def test_m001_is_registered_and_is_the_only_approved_metric():
    assert pi.registry.metric_ids() == [M001]
    definition = pi.registry.get(M001)
    assert definition.public_name == 'Current Active-Pen ERA'
    assert definition.family_id == pi.FAMILY_ID
    assert definition.formula == 'earned_runs * 27 / recorded_outs'


def test_registry_rejects_duplicate_registration():
    with pytest.raises(ValueError):
        pi.registry.register(performance_metrics.CURRENT_ACTIVE_PEN_ERA)


def test_registration_is_idempotent():
    before = pi.registry.metric_ids()
    performance_metrics.register_approved_metrics()
    assert pi.registry.metric_ids() == before


def test_unregistered_metric_refuses(app):
    _pitcher('Anyone')
    db.session.commit()
    read = _read(metric_id='M-999')
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_UNKNOWN_METRIC
    assert read['publication']['publishable'] is False


# ── Formula and formatter ───────────────────────────────────────────────────
def test_era_formula_matches_the_canonical_convention():
    components = pi.AppearanceComponents(earned_runs=4, outs=27)
    definition = pi.registry.get(M001)
    assert definition.numerator(components) == 108
    assert definition.denominator(components) == 27
    # 4 earned runs over 9 innings is a 4.00 ERA.
    assert pi._exact_ratio(108, 27) == '4.00'


def test_formatter_never_substitutes_a_placeholder():
    definition = pi.registry.get(M001)
    assert definition.formatter(None) is None
    assert definition.formatter('3.45') == '3.45'


# ── Active group ────────────────────────────────────────────────────────────
def test_active_group_resolves_from_the_governed_population(app):
    kept = _pitcher('Active Arm')
    # The governed population classifies role from usage, so a group member
    # needs recent relief work to be recognised as a bullpen arm.
    for day in (24, 26, 28):
        _log(kept, outs=3, game_date=date(2026, 7, day))
    other = _pitcher('Other Club Arm', team_id=OTHER_TEAM_ID)
    for day in (24, 26, 28):
        _log(other, outs=3, appearance_team_id=OTHER_TEAM_ID,
             game_date=date(2026, 7, day))
    db.session.commit()

    group = pi.resolve_active_group(TEAM_ID, reference_date=REFERENCE_DATE)
    assert kept.id in group['pitcher_ids']
    assert group['membership_authority'] == 'governed_bullpen_population'
    assert group['size'] == len(group['pitcher_ids'])


def test_empty_active_group_refuses(app):
    _pitcher('Elsewhere', team_id=OTHER_TEAM_ID)
    db.session.commit()
    read = _read()
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_ACTIVE_GROUP_EMPTY


# ── Qualifying appearances ──────────────────────────────────────────────────
def test_starts_never_count(app):
    arm = _pitcher('Swing Arm')
    _log(arm, outs=15, earned_runs=5, games_started=1)   # a start
    _log(arm, outs=3, earned_runs=1, games_started=0)    # relief
    db.session.commit()

    logs = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert len(logs) == 1
    assert pi.build_components(logs).outs == 3


def test_appearances_for_another_organization_never_count(app):
    traded = _pitcher('Traded Arm')
    _log(traded, outs=6, earned_runs=2, appearance_team_id=TEAM_ID)
    _log(traded, outs=9, earned_runs=6, appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    components = pi.build_components(
        pi.qualifying_appearances(TEAM_ID, [traded.id], season=SEASON)
    )
    # Only the appearances made FOR this team, even though he is on this
    # roster now and the prior-club line is his own.
    assert components.appearances == 1
    assert components.outs == 6
    assert components.earned_runs == 2


def test_traded_pitcher_keeps_group_membership_without_moving_history(app):
    traded = _pitcher('Acquired In July')
    _log(traded, outs=3, earned_runs=0, appearance_team_id=TEAM_ID)
    _log(traded, outs=12, earned_runs=9, appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    group = pi.resolve_active_group(TEAM_ID, reference_date=REFERENCE_DATE)
    assert traded.id in group['pitcher_ids']

    read = _read()
    assert read['exact_denominator'] == 3
    assert read['exact_numerator'] == 0


def test_unresolved_appearance_authority_never_counts(app):
    arm = _pitcher('Unresolved Arm')
    _log(arm, outs=3, earned_runs=1, appearance_team_id=None,
         appearance_team_status=GameLog.APPEARANCE_TEAM_UNRESOLVED)
    db.session.commit()
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON) == []


def test_non_regular_season_never_counts(app):
    arm = _pitcher('Spring Arm')
    _log(arm, outs=3, earned_runs=1, game_type='S')
    db.session.commit()
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON) == []


def test_unknown_start_flag_never_counts(app):
    arm = _pitcher('Unknown Flag Arm')
    log = _log(arm, outs=3, earned_runs=1)
    log.games_started = None
    db.session.commit()
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON) == []


# ── Sample, refusal, publication ────────────────────────────────────────────
def test_no_qualifying_appearances_refuses(app):
    # In the group by current membership, but every appearance he has was
    # made for his previous organization, so none of them qualifies here.
    arm = _pitcher('Just Acquired')
    for day in (24, 26, 28):
        _log(arm, outs=3, earned_runs=1, appearance_team_id=OTHER_TEAM_ID,
             game_date=date(2026, 7, day))
    db.session.commit()
    read = _read()
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_NO_QUALIFYING_APPEARANCES
    assert read['publication']['publishable'] is False


def test_zero_denominator_refuses_without_fabricating(app):
    arm = _pitcher('Zero Out Arm')
    _log(arm, outs=0, earned_runs=1)
    db.session.commit()

    read = _read()
    assert read['exact_denominator'] == 0
    assert read['value'] is None
    assert read['display_value'] is None
    assert read['reason_code'] == performance_metrics.ERA_DENOMINATOR_ZERO
    assert read['publication']['publishable'] is False


def test_computed_value_is_still_not_publishable_without_an_approved_sample(app):
    arm = _pitcher('Sample Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    read = _read()
    # The value computes exactly...
    assert read['value'] == '4.00'
    assert read['display_value'] == '4.00'
    # ...and is still refused for publication, because no governed decision
    # has approved a minimum sample for M-001.
    assert read['sample']['minimum_sample'] is None
    assert read['publication']['publishable'] is False
    assert read['publication']['reason'] == pi.REFUSAL_MINIMUM_SAMPLE_UNAPPROVED


def test_below_an_approved_sample_refuses(app):
    arm = _pitcher('Thin Sample Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    approved = pi.registry.get(M001)
    object.__setattr__(approved, 'minimum_sample', 5)
    try:
        read = _read()
        assert read['value'] == '4.00'
        assert read['publication']['publishable'] is False
        assert read['publication']['reason'] == pi.REFUSAL_BELOW_MINIMUM_SAMPLE
    finally:
        object.__setattr__(approved, 'minimum_sample', None)


def test_every_gate_stays_blocked(app):
    arm = _pitcher('Gate Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    read = _read()
    assert read['gates'] == {
        'public_reader_gate': 'blocked',
        'team_state_performance_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
    }
    # Nothing this family produces is publishable today.
    assert read['publication']['publishable'] is False


# ── Evidence, freshness, reproducibility ────────────────────────────────────
def test_evidence_chains_summary_to_official_record(app):
    arm = _pitcher('Evidence Arm')
    _log(arm, outs=15, earned_runs=2, game_date=date(2026, 7, 21))
    _log(arm, outs=12, earned_runs=2, game_date=date(2026, 7, 22))
    db.session.commit()

    evidence = _read()['evidence']
    assert set(evidence) >= {'summary', 'context', 'evidence', 'official_record'}
    assert evidence['summary']['metric_id'] == M001
    assert evidence['context']['appearance_ownership_authority'] == (
        'game_log_appearance_team_id'
    )
    assert 'starts' in evidence['context']['excluded']
    assert len(evidence['evidence']) == 2
    assert all(row['appearance_team_id'] == TEAM_ID for row in evidence['evidence'])
    assert evidence['official_record']['outs'] == 27
    assert evidence['official_record']['earned_runs'] == 4


def test_freshness_is_carried_through_untouched(app):
    arm = _pitcher('Freshness Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    freshness = {'data_through': '2026-07-29', 'freshness_state': 'current'}
    read = pi.build_metric_read(
        M001, TEAM_ID, season=SEASON, reference_date=REFERENCE_DATE,
        freshness=freshness,
    )
    assert read['freshness'] == freshness
    assert read['represented_date'] == REFERENCE_DATE.isoformat()


def test_limitations_disclose_the_unapproved_sample_and_ownership(app):
    arm = _pitcher('Limitation Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    limitations = _read()['limitations']
    assert any('minimum sample' in text for text in limitations)
    assert any('made for this team' in text for text in limitations)


def test_read_is_reproducible(app):
    arm = _pitcher('Reproducible Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()
    assert _read() == _read()


def test_integer_outs_are_the_denominator_authority(app):
    arm = _pitcher('Outs Arm')
    # 1.2 IP and 1.1 IP are 5 and 4 outs, never 1.2 + 1.1.
    _log(arm, outs=5, earned_runs=1)
    _log(arm, outs=4, earned_runs=0)
    db.session.commit()

    read = _read()
    assert read['exact_denominator'] == 9
    assert read['sample']['outs'] == 9
