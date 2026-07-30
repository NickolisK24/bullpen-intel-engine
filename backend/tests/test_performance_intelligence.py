"""Current Active-Pen Performance framework and M-001 (D-021).

The framework owns group resolution, qualifying appearances, sample
validation, evidence, freshness, limitations and fail-closed publication, so
these tests live here once. A future metric should need only a registry test
and its own formula test.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import performance_intelligence as pi
from services import performance_metrics
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


BACKEND_DIR = Path(__file__).resolve().parents[1]


class _Stub:
    """Minimal row stand-in for validating a state the schema forecloses."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

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


def _schedule(game_pk, game_date, *, team_id=TEAM_ID, opponent_id=OTHER_TEAM_ID,
              status_state=ScheduledGame.STATE_FINAL, game_type='R'):
    """Canonical schedule authority: one row per side, both must agree."""
    for side in (team_id, opponent_id):
        db.session.add(ScheduledGame(
            team_id=side, game_pk=game_pk, game_date=game_date,
            game_type=game_type, status_state=status_state,
            status_code='F' if status_state == ScheduledGame.STATE_FINAL else 'S',
        ))


def _log(pitcher, *, outs=3, earned_runs=0, games_started=0,
         appearance_team_id=TEAM_ID, game_type='R', game_date=None,
         appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
         schedule=True, schedule_status=ScheduledGame.STATE_FINAL,
         schedule_game_type=None, opponent_id=None):
    _next_pk[0] += 1
    when = game_date or date(2026, 7, 20)
    owner = appearance_team_id if appearance_team_id is not None else TEAM_ID
    if opponent_id is None:
        # The two sides of a game must be different teams.
        opponent_id = OTHER_TEAM_ID if owner != OTHER_TEAM_ID else TEAM_ID
    if schedule:
        _schedule(
            _next_pk[0], when,
            team_id=owner,
            opponent_id=opponent_id,
            status_state=schedule_status,
            game_type=schedule_game_type or game_type,
        )
    log = GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=_next_pk[0],
        game_date=when, game_type=game_type,
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

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert selection.is_valid
    assert len(selection.rows) == 1
    assert pi.build_components(selection.rows).outs == 3


def test_appearances_for_another_organization_never_count(app):
    traded = _pitcher('Traded Arm')
    _log(traded, outs=6, earned_runs=2, appearance_team_id=TEAM_ID)
    _log(traded, outs=9, earned_runs=6, appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [traded.id], season=SEASON)
    assert selection.is_valid
    components = pi.build_components(selection.rows)
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
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON).rows == ()


def test_non_regular_season_never_counts(app):
    arm = _pitcher('Spring Arm')
    _log(arm, outs=3, earned_runs=1, game_type='S')
    db.session.commit()
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON).rows == ()


def test_unknown_start_flag_never_counts(app):
    arm = _pitcher('Unknown Flag Arm')
    log = _log(arm, outs=3, earned_runs=1)
    log.games_started = None
    db.session.commit()
    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    # Cannot prove starter vs relief for a completed game: blocking, not silent.
    assert selection.rows == ()
    assert [i.reason for i in selection.blocking] == [pi.ROW_STARTER_IDENTITY_UNKNOWN]


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


# ── Unknowns stay unknown (gate correction 2) ───────────────────────────────
def test_a_real_zero_is_accepted_as_a_real_zero(app):
    arm = _pitcher('Scoreless Arm')
    _log(arm, outs=27, earned_runs=0)
    db.session.commit()

    read = _read()
    assert read['reason_code'] is None
    assert read['exact_numerator'] == 0
    assert read['value'] == '0.00'


def test_missing_earned_runs_refuses_rather_than_counting_zero(app):
    arm = _pitcher('Missing ER Arm')
    log = _log(arm, outs=27, earned_runs=0)
    db.session.commit()
    # earned_runs defaults to 0 on INSERT, so a genuine NULL can only arrive
    # via a later write. That is exactly the case the validator must catch.
    log.earned_runs = None
    db.session.commit()

    read = _read()
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_QUALIFYING_ROW_INVALID
    issue = read['invalid_rows'][0]
    assert issue['reason'] == pi.ROW_COMPONENT_MISSING
    assert issue['field'] == 'earned_runs'


def test_malformed_earned_runs_is_rejected_by_the_column_and_by_the_validator(app):
    """earned_runs is an integer column; the validator is defence in depth.

    PostgreSQL rejects a non-integer earned_runs at the write, so the malformed
    case cannot be produced through persistence there. The column guarantee is
    asserted, then the validator is checked directly for the case the column
    forecloses — the same shape used for outs above.
    """
    column = GameLog.__table__.columns['earned_runs']
    assert isinstance(column.type, db.Integer)

    issue = pi._validate_required_components(
        _Stub(innings_pitched_outs=27, earned_runs='not-a-number'),
        ('innings_pitched_outs', 'earned_runs'),
        lambda reason, field=None: pi.RowIssue(1, 1, field, reason),
    )
    assert issue.reason == pi.ROW_COMPONENT_MALFORMED
    assert issue.field == 'earned_runs'


def test_null_outs_are_prevented_by_the_schema_and_by_the_validator(app):
    """Persistence already guarantees this; the validator is defence in depth.

    innings_pitched_outs is NOT NULL with a non-negative CHECK, so a NULL can
    never be stored. The guarantee is asserted here rather than assumed, and
    the validator is checked directly for the case the schema forecloses.
    """
    column = GameLog.__table__.columns['innings_pitched_outs']
    assert column.nullable is False

    arm = _pitcher('Null Outs Arm')
    log = _log(arm, outs=27, earned_runs=2)
    db.session.commit()
    log.innings_pitched_outs = None
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    issue = pi._validate_required_components(
        _Stub(innings_pitched_outs=None, earned_runs=0),
        ('innings_pitched_outs', 'earned_runs'),
        lambda reason, field=None: pi.RowIssue(1, 1, field, reason),
    )
    assert issue.reason == pi.ROW_COMPONENT_MISSING
    assert issue.field == 'innings_pitched_outs'


def test_malformed_outs_are_prevented_by_the_schema_and_by_the_validator(app):
    """Outs are protected at three layers; the validator is the last of them.

    NOT NULL, a non-negative CHECK, and ck_game_logs_innings_pitched_matches_outs
    together make a malformed value unstorable. The database guarantee is
    asserted, then the validator is checked directly for the same case.
    """
    checks = {c.name for c in GameLog.__table__.constraints if c.name}
    assert 'ck_game_logs_innings_pitched_outs_nonnegative' in checks
    assert 'ck_game_logs_innings_pitched_matches_outs' in checks

    arm = _pitcher('Malformed Outs Arm')
    log = _log(arm, outs=27, earned_runs=2)
    db.session.commit()
    log.innings_pitched_outs = 'x'
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()

    issue = pi._validate_required_components(
        _Stub(innings_pitched_outs='x', earned_runs=0),
        ('innings_pitched_outs', 'earned_runs'),
        lambda reason, field=None: pi.RowIssue(1, 1, field, reason),
    )
    assert issue.reason == pi.ROW_COMPONENT_MALFORMED
    assert issue.field == 'innings_pitched_outs'


def test_one_invalid_row_refuses_the_whole_read(app):
    arm = _pitcher('Mostly Good Arm')
    _log(arm, outs=15, earned_runs=1)
    _log(arm, outs=9, earned_runs=1)
    bad = _log(arm, outs=3, earned_runs=0)
    db.session.commit()
    bad.earned_runs = None
    db.session.commit()

    read = _read()
    # Not ignored, not zero-filled: the whole read refuses.
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_QUALIFYING_ROW_INVALID
    assert len(read['invalid_rows']) == 1


def test_refusal_carries_bounded_identity_only(app):
    arm = _pitcher('Bounded Arm')
    log = _log(arm, outs=27, earned_runs=0)
    db.session.commit()
    log.earned_runs = None
    db.session.commit()

    issue = _read()['invalid_rows'][0]
    # Enough to find the row again, and nothing more.
    assert set(issue) == {'mlb_game_pk', 'pitcher_id', 'field', 'reason'}
    assert issue['pitcher_id'] == arm.id
    assert issue['mlb_game_pk'] is not None


def test_required_int_accepts_zero_and_rejects_unknowns():
    assert pi._required_int(0) == (True, 0)
    assert pi._required_int(4) == (True, 4)
    assert pi._required_int(None)[0] is False
    assert pi._required_int('x')[0] is False
    assert pi._required_int(True)[0] is False
    assert pi._required_int(-1)[0] is False


# ── Canonical completed-game authority (gate correction 3) ──────────────────
def test_final_supported_regular_season_relief_qualifies(app):
    arm = _pitcher('Final Game Arm')
    _log(arm, outs=27, earned_runs=3)
    db.session.commit()

    selection = pi.qualifying_appearances(
        TEAM_ID, [arm.id], season=SEASON,
        required_components=('innings_pitched_outs', 'earned_runs'),
    )
    assert selection.is_valid
    assert len(selection.rows) == 1


def test_in_progress_game_does_not_qualify(app):
    arm = _pitcher('In Progress Arm')
    _log(arm, outs=3, earned_runs=1,
         schedule_status=ScheduledGame.STATE_SCHEDULED)
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert selection.rows == ()
    # A harmless exclusion, never a blocking evidence gap.
    assert selection.blocking == ()
    assert [i.reason for i in selection.excluded] == [pi.ROW_GAME_NOT_FINAL]


def test_postponed_game_does_not_qualify(app):
    arm = _pitcher('Postponed Arm')
    _log(arm, outs=3, earned_runs=1,
         schedule_status=ScheduledGame.STATE_POSTPONED)
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert selection.rows == ()
    assert [i.reason for i in selection.excluded] == [pi.ROW_GAME_NOT_FINAL]


def test_suspended_unresolved_game_does_not_qualify(app):
    arm = _pitcher('Suspended Arm')
    _log(arm, outs=3, earned_runs=1,
         schedule_status=ScheduledGame.STATE_SUSPENDED)
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert selection.rows == ()
    assert [i.reason for i in selection.excluded] == [pi.ROW_GAME_NOT_FINAL]


def test_unsupported_game_type_does_not_qualify(app):
    arm = _pitcher('Spring Type Arm')
    _log(arm, outs=3, earned_runs=1, game_type='S')
    db.session.commit()
    assert pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON).rows == ()


def test_unprovable_game_finality_blocks_rather_than_being_dropped(app):
    arm = _pitcher('No Schedule Arm')
    _log(arm, outs=3, earned_runs=1, schedule=False)
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert selection.rows == ()
    # Missing authority is BLOCKING, matching the canonical rule; a canonical
    # read must not omit an in-scope appearance for want of authority.
    assert [i.reason for i in selection.blocking] == [
        pi.ROW_SCHEDULE_AUTHORITY_MISSING
    ]
    assert _read()['reason_code'] == pi.REFUSAL_QUALIFYING_ROW_INVALID


def test_contradictory_game_authority_blocks(app):
    arm = _pitcher('Contradictory Arm')
    log = _log(arm, outs=3, earned_runs=1)
    # The two sides disagree on finality.
    row = ScheduledGame.query.filter_by(
        game_pk=log.mlb_game_pk, team_id=OTHER_TEAM_ID).first()
    row.status_state = ScheduledGame.STATE_SCHEDULED
    db.session.commit()

    selection = pi.qualifying_appearances(TEAM_ID, [arm.id], season=SEASON)
    assert [i.reason for i in selection.blocking] == [
        pi.ROW_CONTRADICTORY_GAME_AUTHORITY
    ]


def test_no_second_finality_classifier_is_defined(app):
    """Finality must be proved through the canonical authority, not restated."""
    source = (BACKEND_DIR / 'services/performance_intelligence.py').read_text()
    assert 'schedule_authority._schedule_authority(' in source
    for reimplementation in (
        "status_state == 'final'", 'STATE_FINAL', 'FINAL_GAME_STATUS_CODES',
        'classify_game_finality', 'ScheduledGame.query',
    ):
        assert reimplementation not in source, reimplementation


# ── Governance boundaries hold after the corrections ───────────────────────
def test_membership_completeness_limitation_is_disclosed(app):
    arm = _pitcher('Disclosure Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    limitations = _read()['limitations']
    assert any('not yet guaranteed complete' in text for text in limitations)
    assert any('newly active arm' in text for text in limitations)
