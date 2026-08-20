"""Current Active-Pen Performance framework and M-001 (D-021).

The framework owns group resolution, qualifying appearances, sample
validation, evidence, freshness, limitations and fail-closed publication, so
these tests live here once. A future metric should need only a registry test
and its own formula test.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import bullpen_eligibility
from services import performance_intelligence as pi
from services import performance_metrics
from services import role_authority
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
    assert definition.public_name == 'Active Bullpen ERA'
    assert definition.internal_name == 'Current Active-Pen ERA'
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


def test_a_satisfied_sample_is_still_not_publishable(app):
    """Meeting D-023 makes the metric reviewable. It does not open a gate."""
    arm = _pitcher('Sample Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    read = _read()
    # The value computes exactly and the approved sample is satisfied...
    assert read['value'] == '3.00'
    assert read['display_value'] == '3.00'
    assert read['sample']['minimum_sample'] == 108
    assert read['sample']['meets_minimum_sample'] is True
    assert read['metric_readiness']['ready_for_internal_review'] is True
    # ...and it is still refused for publication, because the public gate is
    # blocked. Readiness and publication are separate questions.
    assert read['publication']['publishable'] is False
    assert read['publication']['reason'] == pi.PUBLICATION_BLOCKED_BY_GATE


def test_below_the_approved_sample_refuses(app):
    arm = _pitcher('Thin Sample Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    read = _read()
    # The value computes exactly and is deliberately not offered for review.
    assert read['value'] == '4.00'
    assert read['sample']['meets_minimum_sample'] is False
    assert read['metric_readiness']['ready_for_internal_review'] is False
    assert read['publication']['publishable'] is False
    assert read['publication']['reason'] == pi.REFUSAL_BELOW_MINIMUM_SAMPLE


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
    rows = evidence['evidence']['appearances']
    assert len(rows) == 2
    assert all(row['appearance_team_id'] == TEAM_ID for row in rows)
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


def test_limitations_disclose_appearance_ownership(app):
    arm = _pitcher('Limitation Arm')
    _log(arm, outs=27, earned_runs=4)
    db.session.commit()

    limitations = _read()['limitations']
    # The unapproved-sample limitation is gone because D-023 approved one; the
    # ownership limitation is permanent.
    assert not any('No approved minimum sample' in text for text in limitations)
    assert any('made for this team' in text for text in limitations)
    assert any('newly active arm' in text for text in limitations)


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


# ── Realistic relief work ───────────────────────────────────────────────────
def _relief(arm, *, outs_each, appearances, earned_runs=0, end=date(2026, 7, 29),
            appearance_team_id=TEAM_ID, step=2):
    """Spread work across short outings so the governed population sees a
    reliever rather than a starter, and so the freshness window is satisfied.

    Earned runs land on the first appearance created; the totals are what the
    pooled metric consumes either way.
    """
    created = []
    for index in range(appearances):
        created.append(_log(
            arm,
            outs=outs_each,
            earned_runs=earned_runs if index == 0 else 0,
            appearance_team_id=appearance_team_id,
            game_date=end - timedelta(days=index * step),
        ))
    return created


# ── Approved registry parameters (D-023 to D-028) ──────────────────────────
def test_approved_minimum_sample_is_108_recorded_outs_under_d023():
    d = pi.registry.get(M001)
    assert d.minimum_sample == 108
    assert d.minimum_sample_unit == 'recorded_outs'
    assert d.minimum_sample_authority == 'D-023'
    # 108 outs is exactly 36.0 innings, and is exactly the point at which one
    # earned run moves the value by 0.25 and no more.
    assert pi.innings_display(d.minimum_sample) == '36.0'
    assert (27 * 1) / d.minimum_sample == 0.25


def test_threshold_never_travels_as_a_bare_number():
    """A registry entry cannot gate on an unexplained integer."""
    base = dict(
        metric_id='M-TEST', public_name='Test', version='0.0.1',
        formula='x', numerator=lambda c: 1, denominator=lambda c: 1,
        formatter=lambda v: v, denominator_zero_reason='zero',
    )
    registry = pi.MetricRegistry()
    for missing in ('sample_measure', 'minimum_sample_unit', 'minimum_sample_authority'):
        kwargs = dict(
            base, minimum_sample=10, sample_measure=lambda c: c.outs,
            minimum_sample_unit='recorded_outs', minimum_sample_authority='D-023',
        )
        kwargs[missing] = None
        with pytest.raises(ValueError):
            registry.register(pi.MetricDefinition(**kwargs))
    registry.register(pi.MetricDefinition(
        **base, minimum_sample=10, sample_measure=lambda c: c.outs,
        minimum_sample_unit='recorded_outs', minimum_sample_authority='D-023',
    ))
    assert registry.metric_ids() == ['M-TEST']


def test_a_metric_without_an_approved_sample_still_registers_and_refuses():
    """The pre-approval state stays reachable for a future metric."""
    registry = pi.MetricRegistry()
    registry.register(pi.MetricDefinition(
        metric_id='M-FUTURE', public_name='Future', version='0.0.1',
        formula='x', numerator=lambda c: 1, denominator=lambda c: 1,
        formatter=lambda v: v, denominator_zero_reason='zero',
    ))
    definition = registry.get('M-FUTURE')
    assert definition.minimum_sample is None
    sample = pi._sample(definition, pi.AppearanceComponents(appearances=1, outs=300))
    assert sample['meets_minimum_sample'] is None
    read = {'value': '1.00', 'reason_code': None}
    assert pi._publication_decision(definition, read, sample)['reason'] == (
        pi.REFUSAL_MINIMUM_SAMPLE_UNAPPROVED
    )


def test_a_future_metric_declares_its_own_sample_measure():
    """No ERA-specific conditional lives in the family engine."""
    registry = pi.MetricRegistry()
    registry.register(pi.MetricDefinition(
        metric_id='M-BF', public_name='Per-Batter Metric', version='0.0.1',
        formula='x', numerator=lambda c: c.walks, denominator=lambda c: c.batters_faced,
        formatter=lambda v: v, denominator_zero_reason='zero',
        minimum_sample=50, sample_measure=lambda c: c.batters_faced,
        minimum_sample_unit='batters_faced', minimum_sample_authority='D-030',
    ))
    definition = registry.get('M-BF')
    components = pi.AppearanceComponents(outs=6, batters_faced=60)
    sample = pi._sample(definition, components)
    # Gated on its own declared measure, not on outs and not on appearances.
    assert sample['measured_sample'] == 60
    assert sample['minimum_sample_unit'] == 'batters_faced'
    assert sample['meets_minimum_sample'] is True


def test_approved_authorities_are_carried_on_the_definition():
    d = pi.registry.get(M001)
    assert d.denominator_authority == 'D-024'
    assert d.rounding_authority == 'D-025'
    assert d.below_sample_language_authority == 'D-026'
    assert d.evidence_authority == 'D-029'
    assert d.below_sample_public_wording == 'Not Enough Innings Yet'
    assert d.display_precision == 2
    assert d.effective_date == '2026-07-30'


# ── Sample logic is counted in outs, never appearances (D-023) ─────────────
def test_one_out_short_of_the_threshold_refuses(app):
    arm = _pitcher('107 Arm')
    _relief(arm, outs_each=3, appearances=35, earned_runs=10)   # 105 outs
    _relief(arm, outs_each=2, appearances=1, end=date(2026, 7, 28))  # +2 = 107
    db.session.commit()

    read = _read()
    assert read['sample']['outs'] == 107
    assert read['sample']['measured_sample'] == 107
    assert read['sample']['meets_minimum_sample'] is False
    assert read['metric_readiness']['ready_for_internal_review'] is False
    assert read['publication']['reason'] == pi.REFUSAL_BELOW_MINIMUM_SAMPLE


def test_exactly_the_threshold_satisfies_the_sample(app):
    arm = _pitcher('108 Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=10)   # 108 outs
    db.session.commit()

    read = _read()
    assert read['sample']['outs'] == 108
    assert read['sample']['meets_minimum_sample'] is True
    assert read['metric_readiness']['ready_for_internal_review'] is True


def test_one_out_past_the_threshold_satisfies_the_sample(app):
    arm = _pitcher('109 Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=10)
    _relief(arm, outs_each=1, appearances=1, end=date(2026, 7, 28))
    db.session.commit()

    read = _read()
    assert read['sample']['outs'] == 109
    assert read['sample']['meets_minimum_sample'] is True


def test_many_appearances_with_too_few_outs_still_refuse(app):
    """Forty one-out appearances is forty appearances and only forty outs."""
    arm = _pitcher('One Out Specialist')
    _relief(arm, outs_each=1, appearances=40, earned_runs=2)
    db.session.commit()

    read = _read()
    assert read['sample']['appearances'] == 40
    assert read['sample']['outs'] == 40
    assert read['sample']['appearances'] > 0
    assert read['sample']['meets_minimum_sample'] is False
    assert read['publication']['reason'] == pi.REFUSAL_BELOW_MINIMUM_SAMPLE


def test_fewer_appearances_with_enough_outs_satisfy_the_sample(app):
    """Eighteen two-inning outings clear the gate forty one-out ones did not."""
    arm = _pitcher('Long Relief Arm')
    _relief(arm, outs_each=6, appearances=18, earned_runs=10)
    db.session.commit()

    read = _read()
    assert read['sample']['appearances'] == 18
    assert read['sample']['outs'] == 108
    assert read['sample']['meets_minimum_sample'] is True


def test_zero_outs_refuses_as_denominator_zero_before_the_sample_check(app):
    arm = _pitcher('No Outs Arm')
    _relief(arm, outs_each=0, appearances=6, earned_runs=2)
    db.session.commit()

    read = _read()
    assert read['sample']['outs'] == 0
    assert read['reason_code'] == 'era_denominator_zero'
    assert read['publication']['reason'] == 'era_denominator_zero'
    assert read['metric_readiness']['reason'] == 'era_denominator_zero'


def test_appearance_count_is_evidence_and_never_the_gate(app):
    """Fewer appearances than the threshold integer, and still enough sample."""
    arm = _pitcher('Evidence Not Gate Arm')
    _relief(arm, outs_each=6, appearances=18, earned_runs=4)
    db.session.commit()

    read = _read()
    assert read['sample']['appearances'] == 18
    assert read['sample']['appearances'] < read['sample']['minimum_sample']
    assert read['sample']['meets_minimum_sample'] is True


# ── Below-sample reader wording (D-026) ────────────────────────────────────
def test_below_sample_read_carries_wording_and_both_counts(app):
    arm = _pitcher('Below Sample Arm')
    _relief(arm, outs_each=3, appearances=22, earned_runs=8)    # 66 outs
    db.session.commit()

    below = _read()['below_sample_read']
    assert below['wording'] == 'Not Enough Innings Yet'
    assert below['authority'] == 'D-026'
    assert below['current_innings'] == '22.0'
    assert below['required_innings'] == '36.0'
    assert below['current_outs'] == 66
    assert below['required_outs'] == 108
    assert below['unit'] == 'recorded_outs'


def test_no_below_sample_read_once_the_sample_is_satisfied(app):
    arm = _pitcher('Satisfied Arm')
    _relief(arm, outs_each=3, appearances=40, earned_runs=8)
    db.session.commit()
    assert _read()['below_sample_read'] is None


def test_below_sample_never_borrows_an_arm_read_label(app):
    arm = _pitcher('Vocabulary Arm')
    _relief(arm, outs_each=3, appearances=10, earned_runs=2)
    db.session.commit()

    text = repr(_read())
    for forbidden in ('Limited Read', 'Unavailable', 'Monitor'):
        assert forbidden not in text


# ── Arithmetic (D-025) ─────────────────────────────────────────────────────
@pytest.mark.parametrize('earned_runs,outs,expected', [
    (31, 289, '2.90'),
    (12, 108, '3.00'),
    (0, 130, '0.00'),
    (1, 216, '0.13'),
])
def test_approved_arithmetic_examples(earned_runs, outs, expected):
    assert pi._exact_ratio(earned_runs * 27, outs) == expected


def test_half_up_not_bankers_rounding():
    # 27/216 is exactly 0.125. Half-up gives 0.13; round-half-to-even gives
    # 0.12, which no reader dividing by hand would arrive at.
    assert pi._exact_ratio(27, 216) == '0.13'
    assert round(27 / 216, 2) == 0.12


def test_trailing_zeros_are_preserved_through_the_formatter():
    definition = pi.registry.get(M001)
    for value in ('0.00', '3.00', '2.90', '12.10'):
        assert definition.formatter(value) == value


def test_the_authoritative_value_is_never_a_float(app):
    arm = _pitcher('String Value Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    read = _read()
    assert isinstance(read['value'], str)
    assert isinstance(read['display_value'], str)
    assert isinstance(read['exact_numerator'], int)
    assert isinstance(read['exact_denominator'], int)
    assert not isinstance(read['exact_numerator'], bool)


def test_a_real_zero_is_a_value_and_not_a_refusal(app):
    arm = _pitcher('Scoreless Long Arm')
    _relief(arm, outs_each=3, appearances=40, earned_runs=0)
    db.session.commit()

    read = _read()
    assert read['value'] == '0.00'
    assert read['display_value'] == '0.00'
    assert read['reason_code'] is None
    assert read['below_sample_read'] is None
    assert read['metric_readiness']['ready_for_internal_review'] is True


def test_rounding_happens_once(app):
    """Re-rounding the published string must be a no-op."""
    arm = _pitcher('Single Rounding Arm')
    _relief(arm, outs_each=3, appearances=96, earned_runs=31, step=1)   # 288 outs
    _relief(arm, outs_each=1, appearances=1, end=date(2026, 7, 30))     # 289 outs
    db.session.commit()

    read = _read()
    assert read['exact_numerator'] == 837
    assert read['exact_denominator'] == 289
    assert read['value'] == '2.90'
    assert pi._exact_ratio(read['exact_numerator'], read['exact_denominator']) == '2.90'


def test_precision_is_declared_by_the_metric_not_hardcoded():
    assert pi._exact_ratio(1, 3, 2) == '0.33'
    assert pi._exact_ratio(1, 3, 3) == '0.333'
    assert pi._exact_ratio(1, 3, 0) == '0'


# ── Pooled components only (D-024) ─────────────────────────────────────────
def test_pooled_components_not_an_average_of_pitcher_rates(app):
    """A one-out disaster must not weigh the same as ninety clean innings."""
    workhorse = _pitcher('Workhorse')
    _relief(workhorse, outs_each=3, appearances=90, earned_runs=30)   # 270 outs
    blowup = _pitcher('One Bad Out')
    _relief(blowup, outs_each=1, appearances=1, earned_runs=3)        # 1 out
    db.session.commit()

    read = _read()
    # Pooled: (30 + 3) earned runs over (270 + 1) outs.
    assert read['exact_numerator'] == 33 * 27
    assert read['exact_denominator'] == 271
    assert read['value'] == '3.29'

    # Averaging the two pitchers' own rates gives a wildly different answer.
    workhorse_rate = Decimal(pi._exact_ratio(30 * 27, 270))     # 3.00
    blowup_rate = Decimal(pi._exact_ratio(3 * 27, 1))           # 81.00
    average_of_rates = (workhorse_rate + blowup_rate) / 2
    assert str(average_of_rates.quantize(Decimal('0.01'))) == '42.00'
    assert read['value'] != '42.00'


def test_pooled_components_not_an_average_of_appearance_rates(app):
    arm = _pitcher('Uneven Arm')
    _relief(arm, outs_each=6, appearances=5, earned_runs=0)      # 30 clean outs
    _relief(arm, outs_each=3, appearances=1, earned_runs=3,
            end=date(2026, 7, 27))                              # 3 outs, 3 ER
    db.session.commit()

    read = _read()
    assert read['exact_numerator'] == 3 * 27
    assert read['exact_denominator'] == 33
    assert read['value'] == '2.45'
    # Per-appearance rates are five 0.00 and one 27.00; their mean is 4.50.
    per_appearance = [Decimal('0.00')] * 5 + [Decimal('27.00')]
    mean = sum(per_appearance) / len(per_appearance)
    assert str(mean.quantize(Decimal('0.01'))) == '4.50'
    assert read['value'] != '4.50'


def test_pooled_components_are_not_assembled_from_rounded_parts(app):
    arm_a = _pitcher('Rounded A')
    _relief(arm_a, outs_each=2, appearances=55, earned_runs=11)   # 110 outs
    arm_b = _pitcher('Rounded B')
    _relief(arm_b, outs_each=2, appearances=55, earned_runs=14,
            end=date(2026, 7, 28))                               # 110 outs
    db.session.commit()

    read = _read()
    # One division over the pooled integers, not a combination of two rates.
    assert read['exact_numerator'] == 25 * 27
    assert read['exact_denominator'] == 220
    assert read['value'] == str(
        (Decimal(25 * 27) / Decimal(220)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
    )


# ── Active group and contributing arms (D-027) ─────────────────────────────
def _group_with_a_noncontributing_member():
    """A group member whose only relief work was for another organization."""
    contributor = _pitcher('Contributor')
    _relief(contributor, outs_each=3, appearances=36, earned_runs=12)   # 108 outs
    acquired = _pitcher('Acquired No Usage')
    _relief(acquired, outs_each=3, appearances=6, earned_runs=6,
            appearance_team_id=OTHER_TEAM_ID, end=date(2026, 7, 28))
    db.session.commit()
    return contributor, acquired


def test_no_usage_member_stays_in_the_group_and_contributes_nothing(app):
    contributor, acquired = _group_with_a_noncontributing_member()

    group = _read()['group']
    assert acquired.id in group['pitcher_ids']
    assert group['active_group_size'] == 2
    assert group['contributing_pitcher_count'] == 1
    assert group['noncontributing_active_pitcher_count'] == 1

    member = next(m for m in group['members'] if m['pitcher_id'] == acquired.id)
    assert member['qualifying_appearances'] == 0
    assert member['recorded_outs'] == 0
    assert member['earned_runs'] == 0
    assert member['contributing'] is False
    # He receives no rate of his own.
    assert 'era' not in member and 'value' not in member


def test_no_usage_member_moves_neither_numerator_nor_denominator(app):
    _group_with_a_noncontributing_member()

    read = _read()
    assert read['exact_numerator'] == 12 * 27
    assert read['exact_denominator'] == 108
    assert read['value'] == '3.00'
    # His prior-club earned runs stay with his prior club.
    assert read['sample']['earned_runs'] == 12


def test_no_usage_member_does_not_by_itself_refuse_the_read(app):
    _group_with_a_noncontributing_member()

    read = _read()
    assert read['reason_code'] is None
    assert read['metric_readiness']['ready_for_internal_review'] is True


def test_group_and_contributing_difference_is_disclosed_factually(app):
    _group_with_a_noncontributing_member()

    limitations = _read()['limitations']
    disclosure = [t for t in limitations if 'have pitched for this team' in t]
    assert len(disclosure) == 1
    assert '1 of the 2 arms' in disclosure[0]
    # A factual disclosure, never a warning or a failure.
    for alarm in ('warning', 'error', 'outage', 'missing data', 'failure', 'degraded'):
        assert alarm not in disclosure[0].lower()


def test_group_counts_reconcile(app):
    _group_with_a_noncontributing_member()
    group = _read()['group']
    assert (
        group['contributing_pitcher_count']
        + group['noncontributing_active_pitcher_count']
        == group['active_group_size']
        == len(group['members'])
    )


# ── Evidence (D-029) ───────────────────────────────────────────────────────
def test_all_four_evidence_levels_are_present(app):
    _group_with_a_noncontributing_member()
    evidence = _read()['evidence']

    assert evidence['summary']['public_name'] == 'Active Bullpen ERA'
    assert evidence['summary']['internal_name'] == 'Current Active-Pen ERA'

    context = evidence['context']
    for field_name in (
        'active_group_size', 'contributing_pitcher_count',
        'noncontributing_active_pitcher_count', 'qualifying_appearances',
        'recorded_outs', 'innings_display', 'earned_runs', 'exact_numerator',
        'exact_denominator', 'minimum_sample', 'minimum_sample_unit',
        'minimum_sample_authority', 'method_version', 'effective_date',
        'membership_authority', 'membership_represented_date',
    ):
        assert field_name in context, field_name

    assert set(evidence['evidence']) == {'members', 'appearances'}
    official = evidence['official_record']
    for field_name in (
        'source', 'appearance_team_authority', 'appearance_team_authority_status',
        'appearance_team_authority_sources', 'schedule_authority',
        'start_relief_authority', 'method_version', 'effective_date',
    ):
        assert field_name in official, field_name


def test_evidence_members_reconcile_to_the_summary_totals(app):
    _group_with_a_noncontributing_member()
    read = _read()
    members = read['evidence']['evidence']['members']

    assert sum(m['recorded_outs'] for m in members) == read['exact_denominator']
    assert sum(m['earned_runs'] for m in members) * 27 == read['exact_numerator']
    assert sum(m['qualifying_appearances'] for m in members) == (
        read['evidence']['context']['qualifying_appearances']
    )


def test_evidence_appearance_rows_reconcile_to_member_totals(app):
    arm_a = _pitcher('Row A')
    _relief(arm_a, outs_each=3, appearances=20, earned_runs=5)
    arm_b = _pitcher('Row B')
    _relief(arm_b, outs_each=3, appearances=10, earned_runs=1,
            end=date(2026, 7, 28))
    db.session.commit()

    read = _read()
    rows = read['evidence']['evidence']['appearances']
    members = {m['pitcher_id']: m for m in read['evidence']['evidence']['members']}

    for pitcher_id, member in members.items():
        owned = [r for r in rows if r['pitcher_id'] == pitcher_id]
        assert len(owned) == member['qualifying_appearances']
        assert sum(r['outs'] for r in owned) == member['recorded_outs']
        assert sum(r['earned_runs'] for r in owned) == member['earned_runs']


def test_evidence_rows_carry_official_identity_not_raw_rows(app):
    arm = _pitcher('Identity Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=3)
    db.session.commit()

    row = _read()['evidence']['evidence']['appearances'][0]
    assert set(row) == {
        'pitcher_id', 'mlb_game_pk', 'game_date', 'opponent',
        'opponent_abbreviation', 'appearance_team_id', 'outs',
        'innings_display', 'earned_runs',
    }
    # No stored internals leak.
    assert 'id' not in row and 'pitches_thrown' not in row


def test_incomplete_level_four_authority_refuses_the_read(app):
    """A row whose schedule authority cannot be proved blocks the whole read."""
    arm = _pitcher('No Schedule Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=3)
    _log(arm, outs=3, earned_runs=0, schedule=False, game_date=date(2026, 7, 27))
    db.session.commit()

    read = _read()
    assert read['value'] is None
    assert read['reason_code'] == pi.REFUSAL_QUALIFYING_ROW_INVALID
    assert read['evidence'] is None
    assert read['invalid_rows'][0]['reason'] == pi.ROW_SCHEDULE_AUTHORITY_MISSING


def test_exclusions_stay_bounded_reason_codes(app):
    arm = _pitcher('Bounded Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=3)
    _log(arm, outs=15, earned_runs=5, games_started=1, game_date=date(2026, 7, 27))
    db.session.commit()

    selection = pi.qualifying_appearances(
        TEAM_ID, [arm.id], season=SEASON,
        required_components=('innings_pitched_outs', 'earned_runs'),
    )
    assert selection.is_valid
    assert selection.excluded
    for issue in selection.excluded:
        assert issue.reason in {pi.ROW_GAME_NOT_FINAL, pi.ROW_STARTER_EXCLUDED}
        assert set(issue.to_dict()) == {'mlb_game_pk', 'pitcher_id', 'field', 'reason'}


def test_evidence_ordering_is_deterministic(app):
    arm = _pitcher('Ordered Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=4)
    db.session.commit()

    dates = [r['game_date'] for r in _read()['evidence']['evidence']['appearances']]
    assert dates == sorted(dates)
    assert _read() == _read()


# ── Gates stay blocked (D-021, unchanged) ──────────────────────────────────
def test_meeting_the_sample_opens_no_gate(app):
    arm = _pitcher('Gate Safety Arm')
    _relief(arm, outs_each=3, appearances=100, earned_runs=20)
    db.session.commit()

    read = _read()
    assert read['metric_readiness']['ready_for_internal_review'] is True
    assert read['gates'] == {
        'public_reader_gate': 'blocked',
        'team_state_performance_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
    }
    assert read['publication']['publishable'] is False
    assert read['publication']['reason'] == pi.PUBLICATION_BLOCKED_BY_GATE


def test_readiness_and_publication_are_different_questions(app):
    arm = _pitcher('Distinct Arm')
    _relief(arm, outs_each=3, appearances=100, earned_runs=20)
    db.session.commit()

    read = _read()
    assert read['metric_readiness']['ready_for_internal_review'] is True
    assert read['publication']['publishable'] is False
    # The ambiguous generic value is deliberately not used in either place.
    assert 'ready_for_review' not in repr(read['metric_readiness'])
    assert 'ready_for_review' not in repr(read['publication'])


# ── Refusals stay distinct ─────────────────────────────────────────────────
def test_each_refusal_keeps_its_own_reason_code(app):
    _pitcher('Nobody', team_id=OTHER_TEAM_ID)
    db.session.commit()
    assert _read()['reason_code'] == pi.REFUSAL_ACTIVE_GROUP_EMPTY
    assert _read(metric_id='M-999')['reason_code'] == pi.REFUSAL_UNKNOWN_METRIC

    # The distinct facts the contract requires to stay separable.
    assert len({
        pi.REFUSAL_UNKNOWN_METRIC,
        pi.REFUSAL_ACTIVE_GROUP_EMPTY,
        pi.REFUSAL_NO_QUALIFYING_APPEARANCES,
        'era_denominator_zero',
        pi.REFUSAL_BELOW_MINIMUM_SAMPLE,
        pi.REFUSAL_QUALIFYING_ROW_INVALID,
        pi.PUBLICATION_BLOCKED_BY_GATE,
    }) == 7


def test_a_refusal_never_substitutes_a_value(app):
    arm = _pitcher('Refusal Arm')
    _relief(arm, outs_each=3, appearances=22, earned_runs=8)   # 66 outs
    db.session.commit()

    read = _read()
    assert read['publication']['publishable'] is False
    # The value is computed internally; nothing is published, and no substitute
    # of any kind appears in its place.
    assert read['display_value'] == '3.27'
    assert read['publication']['reason'] == pi.REFUSAL_BELOW_MINIMUM_SAMPLE
    assert read['below_sample_read']['wording'] == 'Not Enough Innings Yet'


# ── Position-player pitching never creates bullpen membership ───────────────
def _position_player(name, *, position='SS', team_id=TEAM_ID, mlb_id=None):
    """An active position player, stored like any other player row."""
    if mlb_id is None:
        _next_mlb_id[0] += 1
        mlb_id = _next_mlb_id[0]
    player = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=team_id,
        team_name='New York Yankees', team_abbreviation='NYY',
        active=True, roster_status='Active', position=position,
    )
    db.session.add(player)
    db.session.flush()
    return player


def test_a_shortstop_with_one_relief_appearance_is_not_a_bullpen_member(app):
    reliever = _pitcher('Genuine Reliever')
    _relief(reliever, outs_each=3, appearances=40, earned_runs=12)
    infielder = _position_player('Mop-Up Infielder')
    _relief(infielder, outs_each=3, appearances=1, end=date(2026, 7, 28))
    db.session.commit()

    group = _read()['group']
    assert infielder.id not in group['pitcher_ids']
    assert reliever.id in group['pitcher_ids']
    assert group['active_group_size'] == 1


def test_his_pitching_appearance_remains_in_the_historical_ledger(app):
    reliever = _pitcher('Genuine Reliever')
    _relief(reliever, outs_each=3, appearances=40, earned_runs=12)
    infielder = _position_player('Mop-Up Infielder')
    _relief(infielder, outs_each=3, appearances=1, earned_runs=1,
            end=date(2026, 7, 28))
    db.session.commit()
    _read()

    rows = GameLog.query.filter_by(pitcher_id=infielder.id).all()
    assert len(rows) == 1
    assert rows[0].innings_pitched_outs == 3
    assert rows[0].earned_runs == 1
    assert rows[0].appearance_team_id == TEAM_ID


def test_his_outs_and_earned_runs_do_not_enter_the_metric(app):
    reliever = _pitcher('Genuine Reliever')
    _relief(reliever, outs_each=3, appearances=40, earned_runs=12)
    infielder = _position_player('Mop-Up Infielder')
    _relief(infielder, outs_each=3, appearances=1, earned_runs=9,
            end=date(2026, 7, 28))
    db.session.commit()

    read = _read()
    assert read['exact_denominator'] == 120           # not 123
    assert read['exact_numerator'] == 12 * 27         # not 21 * 27
    members = read['evidence']['evidence']['members']
    assert all(m['pitcher_id'] != infielder.id for m in members)


def test_the_production_yankees_contamination_is_corrected(app):
    """110 ER over 1010 contaminated outs (2.94) vs 1007 clean outs (2.95).

    Three of those outs were a position player's mop-up inning. The fixture
    mirrors the production read that proved the defect.
    """
    # 1007 official relief outs across five bullpen arms, 110 earned runs.
    arms = [_pitcher(f'Pen Arm {index}') for index in range(5)]
    for index, arm in enumerate(arms):
        _relief(arm, outs_each=3, appearances=67, earned_runs=22,
                end=date(2026, 7, 29) - timedelta(days=index), step=1)
    _relief(arms[0], outs_each=2, appearances=1, end=date(2026, 7, 30))

    infielder = _position_player('Mop-Up Infielder')
    _relief(infielder, outs_each=3, appearances=1, end=date(2026, 7, 28))
    db.session.commit()

    read = _read()
    assert read['sample']['earned_runs'] == 110
    assert read['exact_denominator'] == 1007
    assert read['exact_numerator'] == 110 * 27

    contaminated = pi._exact_ratio(110 * 27, 1010)
    corrected = pi._exact_ratio(110 * 27, 1007)
    assert contaminated == '2.94'
    assert corrected == '2.95'
    assert read['value'] == corrected


def test_a_legitimate_reliever_with_one_appearance_stays_eligible(app):
    arm = _pitcher('One Appearance Reliever')
    _relief(arm, outs_each=3, appearances=1, earned_runs=1)
    db.session.commit()

    group = pi.resolve_active_group(TEAM_ID, reference_date=REFERENCE_DATE)
    assert arm.id in group['pitcher_ids']


def test_a_legitimate_multi_inning_reliever_stays_eligible(app):
    arm = _pitcher('Long Reliever')
    _relief(arm, outs_each=6, appearances=20, earned_runs=8)
    db.session.commit()

    group = pi.resolve_active_group(TEAM_ID, reference_date=REFERENCE_DATE)
    assert arm.id in group['pitcher_ids']


def test_a_bullpen_pitcher_who_previously_started_is_not_auto_excluded(app):
    """Current bullpen membership is supported, so a past start does not remove him."""
    arm = _pitcher('Converted Starter')
    _log(arm, outs=15, earned_runs=4, games_started=1, game_date=date(2026, 4, 10))
    _relief(arm, outs_each=3, appearances=20, earned_runs=6)
    db.session.commit()

    group = pi.resolve_active_group(TEAM_ID, reference_date=REFERENCE_DATE)
    assert arm.id in group['pitcher_ids']


def test_unknown_role_evidence_does_not_default_to_reliever(app):
    arm = _pitcher('No Usage Pitcher')       # position P, zero logs
    db.session.commit()

    result = role_authority.classify_role(arm, [], reference_date=REFERENCE_DATE)
    assert result['role'] == role_authority.ROLE_UNKNOWN
    assert result['eligible'] is False


def test_a_non_pitching_position_resolves_as_its_own_role_not_unknown(app):
    infielder = _position_player('Any Infielder')
    db.session.commit()

    result = role_authority.classify_role(infielder, [], reference_date=REFERENCE_DATE)
    assert result['role'] == role_authority.ROLE_NON_PITCHER
    assert result['eligible'] is False
    assert result['status'] == role_authority.STATUS_ROLE_NON_PITCHER


@pytest.mark.parametrize('position', ['SS', '2B', '1B', '3B', 'C', 'LF', 'CF', 'RF', 'DH', 'OF', 'IF'])
def test_no_non_pitching_position_can_enter_any_bullpen(app, position):
    reliever = _pitcher('Genuine Reliever')
    _relief(reliever, outs_each=3, appearances=40, earned_runs=12)
    player = _position_player(f'{position} Player', position=position)
    _relief(player, outs_each=3, appearances=3, end=date(2026, 7, 28))
    db.session.commit()

    assert player.id not in _read()['group']['pitcher_ids']


@pytest.mark.parametrize('position', ['P', 'SP', 'RP', 'CL', 'LHP', 'RHP'])
def test_every_pitching_position_remains_eligible(app, position):
    arm = _pitcher('Pitcher', )
    arm.position = position
    _relief(arm, outs_each=3, appearances=20, earned_runs=5)
    db.session.commit()

    assert arm.id in _read()['group']['pitcher_ids']


def test_no_player_specific_or_team_specific_exception_exists():
    """The gate is positional. No name, id, or club may appear in it."""
    sources = [
        (BACKEND_DIR / 'services' / 'role_authority.py').read_text(encoding='utf-8'),
        (BACKEND_DIR / 'services' / 'bullpen_population.py').read_text(encoding='utf-8'),
        (BACKEND_DIR / 'services' / 'performance_intelligence.py').read_text(encoding='utf-8'),
    ]
    for source in sources:
        for forbidden in ('Schuemann', '680474', 'Yankee', '147'):
            assert forbidden not in source


# ── Role evidence travels with every member ────────────────────────────────
def test_every_member_carries_bounded_role_evidence(app):
    arm = _pitcher('Evidence Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    member = _read()['group']['members'][0]
    evidence = member['role_evidence']
    assert set(evidence) == {
        'roster_status', 'roster_status_source', 'roster_status_is_authoritative',
        'roster_position', 'bullpen_role', 'role_confidence',
        'role_resolution_status', 'role_authority', 'role_evidence_date',
    }
    assert evidence['roster_position'] == 'P'
    assert evidence['bullpen_role'] == role_authority.ROLE_RELIEVER
    assert evidence['role_evidence_date'] == REFERENCE_DATE.isoformat()
    assert evidence['role_authority']


def test_role_evidence_exposes_no_raw_source_payload(app):
    arm = _pitcher('Bounded Evidence Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    evidence = _read()['group']['members'][0]['role_evidence']
    for value in evidence.values():
        assert not isinstance(value, (dict, list)), value


# ── Freshness comes from the canonical authority ───────────────────────────
def test_a_normal_read_carries_non_null_freshness(app):
    arm = _pitcher('Freshness Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    freshness = _read()['freshness']
    assert freshness is not None
    assert freshness['authority'] == 'durable_sync_metadata'
    assert freshness['freshness_state']


def test_freshness_keeps_the_date_concepts_distinct(app):
    arm = _pitcher('Date Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    read = _read()
    freshness = read['freshness']
    assert freshness['represented_date'] == REFERENCE_DATE.isoformat()
    assert freshness['data_through_date'] != freshness['represented_date']
    # Membership carries its own represented date, separate from both.
    assert read['group']['reference_date'] == REFERENCE_DATE.isoformat()
    assert 'request_timestamp' not in freshness


def test_freshness_does_not_use_the_request_clock_as_a_data_authority(app):
    arm = _pitcher('Clock Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    freshness = _read()['freshness']
    today = date.today().isoformat()
    assert freshness['data_through_date'] != today
    assert freshness['represented_date'] == REFERENCE_DATE.isoformat()
    # Two reads separated in wall-clock time produce identical freshness.
    assert _read()['freshness'] == freshness


def test_unprovable_freshness_withholds_internal_readiness(app, monkeypatch):
    arm = _pitcher('Unprovable Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    def _unavailable(reference_date=None):
        return {
            'represented_date': reference_date.isoformat() if reference_date else None,
            'data_through_date': None,
            'freshness_state': 'metadata_unavailable',
            'fail_closed': True,
            'authority': 'durable_sync_metadata',
            'provable': False,
        }

    monkeypatch.setattr(pi, 'resolve_freshness', _unavailable)
    read = _read()
    # The value still computes; it is simply not offered for review.
    assert read['value'] == '3.00'
    assert read['metric_readiness']['ready_for_internal_review'] is False
    assert read['metric_readiness']['reason'] == pi.REFUSAL_FRESHNESS_UNPROVABLE
    assert read['publication']['reason'] == pi.REFUSAL_FRESHNESS_UNPROVABLE
    assert read['freshness'] is not None


def test_stale_freshness_is_labeled_and_not_hidden(app, monkeypatch):
    arm = _pitcher('Stale Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    def _stale(reference_date=None):
        return {
            'represented_date': reference_date.isoformat() if reference_date else None,
            'data_through_date': '2026-07-20',
            'freshness_state': 'stale',
            'is_stale': True,
            'is_current': False,
            'data_age_days': 10,
            'degradation_state': 'stale',
            'fail_closed': False,
            'authority': 'durable_sync_metadata',
            'provable': True,
        }

    monkeypatch.setattr(pi, 'resolve_freshness', _stale)
    read = _read()
    assert read['freshness']['freshness_state'] == 'stale'
    assert read['freshness']['is_stale'] is True
    # Stale but provable stays reviewable — labelled, not suppressed.
    assert read['metric_readiness']['ready_for_internal_review'] is True


def test_public_gates_stay_blocked_regardless_of_freshness(app, monkeypatch):
    arm = _pitcher('Gate Freshness Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    for state, provable in (('current', True), ('stale', True), ('metadata_unavailable', False)):
        monkeypatch.setattr(pi, 'resolve_freshness', lambda reference_date=None,
                            _s=state, _p=provable: {
            'represented_date': None, 'data_through_date': None,
            'freshness_state': _s, 'fail_closed': not _p,
            'authority': 'durable_sync_metadata', 'provable': _p,
        })
        read = _read()
        assert read['gates'] == {
            'public_reader_gate': 'blocked',
            'team_state_performance_gate': 'blocked',
            'share_card_performance_gate': 'blocked',
        }
        assert read['publication']['publishable'] is False


def test_an_injected_freshness_is_still_carried_through_untouched(app):
    arm = _pitcher('Injected Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)
    db.session.commit()

    injected = {'data_through': '2026-07-29', 'state': 'current'}
    read = pi.build_metric_read(
        M001, TEAM_ID, season=SEASON, reference_date=REFERENCE_DATE,
        freshness=injected,
    )
    assert read['freshness'] == injected


# ── Cross-team population audit ────────────────────────────────────────────
ALL_TEAM_IDS = [
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121,
    133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
    147, 158,
]


def test_no_active_group_member_across_any_team_has_a_non_pitching_role(app):
    """Sweep every club: a resolved member must be a pitcher by roster position.

    Each club gets a genuine reliever and a position player who pitched. The
    audit asserts the population never admits the second, on any team, and
    reports every offender rather than only the first.
    """
    planted = {}
    for index, team_id in enumerate(ALL_TEAM_IDS):
        arm = _pitcher(f'Reliever {team_id}', team_id=team_id)
        _relief(arm, outs_each=3, appearances=40, earned_runs=10,
                appearance_team_id=team_id,
                end=date(2026, 7, 29) - timedelta(days=index % 3))
        player = _position_player(f'Position Player {team_id}', team_id=team_id)
        _relief(player, outs_each=3, appearances=2, appearance_team_id=team_id,
                end=date(2026, 7, 28))
        planted[team_id] = (arm.id, player.id)
    db.session.commit()

    offenders = []
    audited = 0
    for team_id in ALL_TEAM_IDS:
        group = pi.resolve_active_group(team_id, reference_date=REFERENCE_DATE)
        audited += 1
        for member in group['members']:
            position = (member['role_evidence']['roster_position'] or '').upper()
            if position and position not in bullpen_eligibility.PITCHING_POSITIONS:
                offenders.append({
                    'team_id': team_id,
                    'pitcher_id': member['pitcher_id'],
                    'roster_position': position,
                    'bullpen_role': member['role_evidence']['bullpen_role'],
                })
        arm_id, player_id = planted[team_id]
        assert arm_id in group['pitcher_ids'], team_id
        assert player_id not in group['pitcher_ids'], team_id

    assert audited == 30
    assert offenders == [], offenders
