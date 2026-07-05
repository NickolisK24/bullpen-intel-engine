from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import EvidenceRuleRegistry
from services.team_relief_composition_evidence import (
    APPEARANCE_FINISH_CONTEXT_RULE_ID,
    BASIS_DISCLAIMER,
    COMPOSITION_ATTRIBUTION_CONFLICT_ENTITY_TYPE,
    FLOORED_ENTRY_BAND_USAGE_OBSERVATION_RULE_IDS,
    LOCKED_BAND_RULE_IDS,
    OUTING_CLEAN_RULE_ID,
    OUTING_CONTEXT_UNKNOWN_RULE_ID,
    OUTING_TRAFFIC_RULE_ID,
    REASON_ATTRIBUTION_CONFLICT,
    REASON_ATTRIBUTION_UNKNOWN,
    REASON_BASIS_LOWER_BOUND,
    REASON_CONCENTRATION_CORROBORATION_MISMATCH,
    REASON_INCOMPLETE_SLATE_DAY,
    REASON_MEMBER_EVIDENCE_UNAVAILABLE,
    REASON_OUTING_FAMILY_COVERAGE_GAP,
    REASON_SHARE_EXCLUSION_PRESENT,
    REASON_SOURCE_EVIDENCE_SUPERSEDED,
    RULE_VERSION,
    TEAM_BULLPEN_OUTS_WINDOW_RULE_ID,
    TEAM_RELIEF_COMPOSITION_RULE_IDS,
    TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
    TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID,
    TEAM_RELIEF_FINISH_SPREAD_RULE_ID,
    TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID,
    TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID,
    TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID,
    USAGE_BACK_TO_BACK_RULE_ID,
    USAGE_FOUR_IN_SIX_RULE_ID,
    USAGE_THREE_IN_FOUR_RULE_ID,
    WORKLOAD_DAYS_OF_REST_RULE_ID,
    assert_team_relief_composition_language_allowed,
    build_team_relief_composition_evidence,
    mark_game_log_correction_for_team_relief_composition,
    mark_source_evidence_supersession_for_team_relief_composition,
    rebuild_marked_team_relief_composition_evidence,
    register_team_relief_composition_rules,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 4)
TEAM_A = 116
TEAM_B = 117
TEAM_C = 118


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _sync_run():
    run = SyncRun(
        job_name='phase0d_team_relief_composition_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _fixture_sync_run_id():
    existing = SyncRun.query.filter_by(
        job_name='phase0d_team_relief_composition_fixture',
        source='test_fixture',
    ).first()
    if existing is not None:
        return existing.id
    run = SyncRun(
        job_name='phase0d_team_relief_composition_fixture',
        started_at=datetime(2026, 7, 4, 9, 0, 0),
        completed_at=datetime(2026, 7, 4, 9, 0, 1),
        status='success',
        stage='fixture',
        source='test_fixture',
    )
    db.session.add(run)
    db.session.flush()
    return run.id


def _pitcher(seed, team_id=TEAM_A, name=None):
    row = Pitcher(
        mlb_id=870000 + seed,
        full_name=name or f'Team Relief Pitcher {seed}',
        team_id=team_id,
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _game_pk(day, suffix=0):
    return int(day.strftime('%Y%m%d')) * 100 + suffix


def _complete_slate(day, *, suffix=0, home_team_id=TEAM_A, away_team_id=TEAM_B):
    game_pk = _game_pk(day, suffix)
    if ScheduledGame.query.filter_by(game_pk=game_pk).first() is None:
        db.session.add_all([
            ScheduledGame(
                team_id=home_team_id,
                opponent_team_id=away_team_id,
                game_pk=game_pk,
                game_date=day,
                home_away='home',
                status_state=ScheduledGame.STATE_FINAL,
                status_code='F',
                game_type='R',
            ),
            ScheduledGame(
                team_id=away_team_id,
                opponent_team_id=home_team_id,
                game_pk=game_pk,
                game_date=day,
                home_away='away',
                status_state=ScheduledGame.STATE_FINAL,
                status_code='F',
                game_type='R',
            ),
        ])
    if PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first() is None:
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk,
            game_date=day,
            game_type='R',
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            processed_at=datetime(2026, 7, 4, 12, 0, 0),
            sync_run_id=_fixture_sync_run_id(),
        ))
    db.session.flush()
    return game_pk


def _incomplete_slate(day, *, suffix=90):
    game_pk = _game_pk(day, suffix)
    db.session.add_all([
        ScheduledGame(
            team_id=TEAM_A,
            opponent_team_id=TEAM_B,
            game_pk=game_pk,
            game_date=day,
            home_away='home',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
        ),
        ScheduledGame(
            team_id=TEAM_B,
            opponent_team_id=TEAM_A,
            game_pk=game_pk,
            game_date=day,
            home_away='away',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
        ),
    ])
    db.session.flush()
    return game_pk


def _seed_complete_coverage(end=PRODUCT_DATE, days=14):
    start = end - timedelta(days=days - 1)
    for offset in range(days):
        _complete_slate(start + timedelta(days=offset), suffix=offset)


def _snapshot(
    pitcher,
    *,
    team_id=TEAM_A,
    snapshot_date=PRODUCT_DATE,
    active_roster=True,
    roster_status='active',
):
    existing = RosterStatusSnapshot.query.filter_by(
        pitcher_id=pitcher.id,
        snapshot_date=snapshot_date,
    ).first()
    if existing is not None:
        existing.team_id = team_id
        existing.active_roster = active_roster
        existing.roster_status = roster_status
        db.session.flush()
        return existing
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id,
        snapshot_date=snapshot_date,
        roster_status=roster_status,
        active_roster=active_roster,
        forty_man_roster=True,
        position_code='P',
        position_name='Pitcher',
        position_type='Pitcher',
        two_way_eligible=False,
        roster_status_raw='stored',
        roster_status_raw_code='stored',
        roster_status_raw_description='stored',
        source='test_roster_snapshot',
        sync_run_id=_fixture_sync_run_id(),
        first_seen_at=datetime(2026, 7, 4, 10, 0, 0),
        created_at=datetime(2026, 7, 4, 10, 0, 0),
        updated_at=datetime(2026, 7, 4, 10, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _log(
    pitcher,
    day=PRODUCT_DATE,
    *,
    suffix=0,
    games_started=0,
    outs=3,
    games_finished=0,
    save_situation=False,
    save=False,
    hold=False,
    blown_save=False,
):
    game_pk = _complete_slate(day, suffix=suffix)
    row = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=day,
        game_type='R',
        opponent=None,
        opponent_abbreviation=None,
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=12,
        strikes=8,
        hits_allowed=0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        batters_faced=3,
        games_finished=games_finished,
        save_situation=save_situation,
        save=save,
        hold=hold,
        blown_save=blown_save,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _pbp(log, *, fielding_team_id, event_index=1):
    row = GamePlayByPlayEvent(
        mlb_game_pk=log.mlb_game_pk,
        event_index=event_index,
        source_play_id=f'play-{log.mlb_game_pk}-{event_index}',
        at_bat_index=event_index,
        game_date=log.game_date,
        game_type='R',
        home_team_id=TEAM_A,
        away_team_id=TEAM_B,
        event_type='plate_appearance',
        event_type_code='pa',
        inning=8,
        half_inning='top',
        is_top_inning=True,
        outs_at_event=0,
        home_score_at_event=0,
        away_score_at_event=0,
        pitcher_mlb_id=db.session.get(Pitcher, log.pitcher_id).mlb_id,
        pitcher_id=log.pitcher_id,
        batter_mlb_id=999001,
        batting_team_id=TEAM_B,
        fielding_team_id=fielding_team_id,
        is_pitching_change=False,
        is_scoring_play=False,
        is_mound_visit=False,
        source='test_play_by_play',
        source_endpoint='test',
        sync_run_id=_fixture_sync_run_id(),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _evidence_object(
    rule_id,
    *,
    subject_type='pitcher',
    subject_id='1',
    product_date=PRODUCT_DATE,
    trace=None,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=None,
    claim='Stored fixture evidence.',
):
    row = EvidenceObject(
        evidence_key=f'fixture:{rule_id}:{subject_type}:{subject_id}:{product_date}:{_fixture_seq()}',
        evidence_type=rule_id,
        subject_type=subject_type,
        subject_id=str(subject_id),
        subject_key=f'{subject_type}:{subject_id}:{rule_id}',
        product_date=product_date,
        claim_template_id=f'{rule_id}_fixture_claim',
        rendered_claim=claim,
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash=f'{rule_id}-fixture-hash',
        typed_cited_inputs=[],
        computation_trace=dict(trace or {}),
        completeness_state=state,
        reason_codes=list(reason_codes or []),
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='test_fixture',
        sync_run_id=_fixture_sync_run_id(),
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    db.session.add(row)
    db.session.flush()
    return row


_FIXTURE_COUNTER = 0


def _fixture_seq():
    global _FIXTURE_COUNTER
    _FIXTURE_COUNTER += 1
    return _FIXTURE_COUNTER


def _basis(team_id=TEAM_A):
    return EvidenceObject.query.filter_by(
        rule_id=TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID,
        subject_id=str(team_id),
        product_date=PRODUCT_DATE,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
    ).order_by(EvidenceObject.id.desc()).first()


def _object(rule_id, team_id=TEAM_A):
    return EvidenceObject.query.filter_by(
        rule_id=rule_id,
        subject_id=str(team_id),
        product_date=PRODUCT_DATE,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
    ).order_by(EvidenceObject.id.desc()).first()


def _build_basic_basis(*, team_id=TEAM_A, pitcher_count=3):
    _seed_complete_coverage()
    pitchers = [_pitcher(index + 1, team_id=team_id) for index in range(pitcher_count)]
    for index, pitcher in enumerate(pitchers):
        day = PRODUCT_DATE - timedelta(days=index)
        _snapshot(pitcher, team_id=team_id, snapshot_date=day)
        _snapshot(pitcher, team_id=team_id, snapshot_date=PRODUCT_DATE)
        log = _log(pitcher, day, suffix=30 + index, outs=(index + 1) * 3)
        _pbp(log, fielding_team_id=team_id)
    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)
    return pitchers


def test_registration_lint_internal_only_and_source_exclusions(app):
    registry, templates = register_team_relief_composition_rules()
    rules = registry.all_rules()
    assert len(rules) == 6
    assert {rule.rule_id for rule in rules} == set(TEAM_RELIEF_COMPOSITION_RULE_IDS)
    assert all(rule.rule_version == RULE_VERSION for rule in rules)
    assert all(rule.posture_default == EvidenceObject.POSTURE_INTERNAL_ONLY for rule in rules)
    assert all(rule.evidence_type == rule.rule_id for rule in rules)
    assert templates.get('team_relief_workload_concentration_claim_7d_degraded')
    assert set(LOCKED_BAND_RULE_IDS).isdisjoint(TEAM_RELIEF_COMPOSITION_RULE_IDS)
    assert set(FLOORED_ENTRY_BAND_USAGE_OBSERVATION_RULE_IDS).isdisjoint(
        TEAM_RELIEF_COMPOSITION_RULE_IDS
    )
    assert all(
        locked not in ''.join(rule.required_input_families) + ''.join(rule.required_cited_fields)
        for rule in rules
        for locked in LOCKED_BAND_RULE_IDS
    )
    for text in ('thin', 'workhorse', 'struc' + 'ture', 'available', 'team grade A'):
        with pytest.raises(EvidenceLanguageError):
            assert_team_relief_composition_language_allowed(text)


def test_attribution_truth_table_snapshot_pbp_conflict_trade_doubleheader(app):
    _seed_complete_coverage()
    run = _sync_run()
    p1 = _pitcher(1, team_id=TEAM_A)
    p2 = _pitcher(2, team_id=TEAM_A)
    p3 = _pitcher(3, team_id=TEAM_A)
    p4 = _pitcher(4, team_id=TEAM_A)

    for day_suffix in (20, 21):
        _snapshot(p1, team_id=TEAM_A, snapshot_date=PRODUCT_DATE)
        log = _log(p1, PRODUCT_DATE, suffix=day_suffix, outs=3)
        _pbp(log, fielding_team_id=TEAM_A, event_index=day_suffix)

    missing_day = PRODUCT_DATE - timedelta(days=2)
    _snapshot(p2, team_id=TEAM_A, snapshot_date=PRODUCT_DATE)
    _log(p2, missing_day, suffix=22, outs=3)

    conflict_day = PRODUCT_DATE - timedelta(days=3)
    _snapshot(p3, team_id=TEAM_A, snapshot_date=conflict_day)
    _snapshot(p3, team_id=TEAM_A, snapshot_date=PRODUCT_DATE)
    conflict_log = _log(p3, conflict_day, suffix=23, outs=3)
    _pbp(conflict_log, fielding_team_id=TEAM_B)

    team_a_day = PRODUCT_DATE - timedelta(days=6)
    team_c_day = PRODUCT_DATE - timedelta(days=1)
    _snapshot(p4, team_id=TEAM_A, snapshot_date=team_a_day)
    _snapshot(p4, team_id=TEAM_C, snapshot_date=team_c_day)
    _snapshot(p4, team_id=TEAM_C, snapshot_date=PRODUCT_DATE)
    log_a = _log(p4, team_a_day, suffix=24, outs=3)
    log_c = _log(p4, team_c_day, suffix=25, outs=3)
    _pbp(log_a, fielding_team_id=TEAM_A)
    _pbp(log_c, fielding_team_id=TEAM_C)

    result = build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=run.id)
    assert result['objects_built'] >= 2

    basis_a = _basis(TEAM_A)
    basis_c = _basis(TEAM_C)
    assert basis_a is not None
    assert basis_c is not None
    trace_a = basis_a.computation_trace
    assert trace_a['excluded_appearances_by_reason'][REASON_ATTRIBUTION_UNKNOWN] == 1
    assert trace_a['excluded_appearances_by_reason'][REASON_ATTRIBUTION_CONFLICT] == 1
    assert any(member['pitcher_id'] == p4.id for member in trace_a['members'])
    assert any(member['pitcher_id'] == p4.id for member in basis_c.computation_trace['members'])
    p1_member = next(member for member in trace_a['members'] if member['pitcher_id'] == p1.id)
    assert p1_member['appearance_count'] == 2
    assert all(
        decision['team_id'] in {TEAM_A, TEAM_C}
        for decision in trace_a['attribution_decisions']
    )
    assert SyncFailure.query.filter_by(
        entity_type=COMPOSITION_ATTRIBUTION_CONFLICT_ENTITY_TYPE,
        error=REASON_ATTRIBUTION_CONFLICT,
    ).count() == 1
    assert 'opponent' not in str(trace_a).lower()


def test_basis_lower_bound_roster_membership_and_disclaimer(app):
    _seed_complete_coverage()
    gap_day = PRODUCT_DATE - timedelta(days=4)
    _incomplete_slate(gap_day)
    active = _pitcher(10, team_id=TEAM_A)
    inactive = _pitcher(11, team_id=TEAM_A)
    unknown = _pitcher(12, team_id=TEAM_A)
    for index, pitcher in enumerate((active, inactive, unknown)):
        day = PRODUCT_DATE - timedelta(days=index)
        _snapshot(pitcher, team_id=TEAM_A, snapshot_date=day)
        log = _log(pitcher, day, suffix=40 + index, outs=3)
        _pbp(log, fielding_team_id=TEAM_A)
    _snapshot(active, team_id=TEAM_A, snapshot_date=PRODUCT_DATE, active_roster=True)
    _snapshot(
        inactive,
        team_id=TEAM_A,
        snapshot_date=PRODUCT_DATE,
        active_roster=False,
        roster_status='optional_assignment',
    )

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    basis = _basis(TEAM_A)
    assert basis.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
    assert REASON_INCOMPLETE_SLATE_DAY in basis.reason_codes
    assert REASON_BASIS_LOWER_BOUND in basis.reason_codes
    assert BASIS_DISCLAIMER in basis.rendered_claim
    relationships = {
        row['relationship']: row['pitcher_id']
        for row in basis.computation_trace['current_roster_relationships']
    }
    assert relationships['on_current_active_roster'] == active.id
    assert relationships['not_on_current_active_roster'] == inactive.id
    assert relationships['unknown'] == unknown.id
    rest = _object(TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID)
    assert rest.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
    assert any(
        citation.citation_role == 'composition_basis'
        for citation in rest.citations
    )


def test_rest_buckets_and_member_evidence_states(app):
    pitchers = _build_basic_basis(pitcher_count=5)
    for pitcher, days in zip(pitchers[:4], (0, 1, 2, 4)):
        _evidence_object(
            WORKLOAD_DAYS_OF_REST_RULE_ID,
            subject_id=pitcher.id,
            trace={'full_off_days': days},
        )
    _evidence_object(
        WORKLOAD_DAYS_OF_REST_RULE_ID,
        subject_id=pitchers[4].id,
        trace={},
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
    )

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    rest = _object(TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID)
    assert rest is not None
    assert rest.computation_trace['buckets']['0'][0]['pitcher_id'] == pitchers[0].id
    assert rest.computation_trace['buckets']['1'][0]['pitcher_id'] == pitchers[1].id
    assert rest.computation_trace['buckets']['2'][0]['pitcher_id'] == pitchers[2].id
    assert rest.computation_trace['buckets']['3+'][0]['pitcher_id'] == pitchers[3].id
    assert rest.computation_trace['buckets']['unknown'][0]['pitcher_id'] == pitchers[4].id
    assert REASON_MEMBER_EVIDENCE_UNAVAILABLE in rest.reason_codes


def test_density_trichotomy_present_absent_unknown(app):
    pitchers = _build_basic_basis(pitcher_count=3)
    _evidence_object(USAGE_BACK_TO_BACK_RULE_ID, subject_id=pitchers[0].id)
    _evidence_object(
        USAGE_THREE_IN_FOUR_RULE_ID,
        subject_id=pitchers[1].id,
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
    )

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    density = _object(TEAM_RELIEF_DENSITY_USAGE_COUNT_RULE_ID)
    patterns = density.computation_trace['patterns']
    assert patterns[USAGE_BACK_TO_BACK_RULE_ID]['present'][0]['pitcher_id'] == pitchers[0].id
    assert len(patterns[USAGE_BACK_TO_BACK_RULE_ID]['absent']) == 2
    assert patterns[USAGE_THREE_IN_FOUR_RULE_ID]['unassessable'][0]['pitcher_id'] == pitchers[1].id
    assert patterns[USAGE_FOUR_IN_SIX_RULE_ID]['present'] == []
    assert density.computation_trace['locked_band_rule_ids_consumed'] == []


def test_concentration_counts_shares_exclusions_and_corrob_conflict(app):
    pitchers = _build_basic_basis(pitcher_count=3)
    _evidence_object(
        TEAM_BULLPEN_OUTS_WINDOW_RULE_ID,
        subject_type='team',
        subject_id=TEAM_A,
        trace={'window_days': 7, 'bullpen_outs': 99},
    )

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    concentration = EvidenceObject.query.filter_by(
        rule_id=TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID,
        subject_id=str(TEAM_A),
        product_date=PRODUCT_DATE,
        completeness_state=EvidenceObject.COMPLETENESS_CONFLICT,
    ).first()
    assert concentration is not None
    assert REASON_CONCENTRATION_CORROBORATION_MISMATCH in concentration.reason_codes
    assert concentration.computation_trace['contradiction']['source_relief_outs'] == 99
    assert SyncFailure.query.filter_by(
        entity_type='composition_concentration_conflict',
        error=REASON_CONCENTRATION_CORROBORATION_MISMATCH,
    ).count() == 1

    conflict_source = EvidenceObject.query.filter_by(rule_id=TEAM_BULLPEN_OUTS_WINDOW_RULE_ID).first()
    conflict_source.recompute_status = EvidenceObject.RECOMPUTE_SUPERSEDED
    missing = _pitcher(99, team_id=TEAM_A)
    missing_day = PRODUCT_DATE - timedelta(days=1)
    _snapshot(missing, team_id=TEAM_A, snapshot_date=PRODUCT_DATE)
    _log(missing, missing_day, suffix=99, outs=3)
    db.session.flush()

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    partial = EvidenceObject.query.filter_by(
        rule_id=TEAM_RELIEF_WORKLOAD_CONCENTRATION_RULE_ID,
        subject_id=str(TEAM_A),
        product_date=PRODUCT_DATE,
        completeness_state=EvidenceObject.COMPLETENESS_PARTIAL,
    ).first()
    assert partial is not None
    assert REASON_SHARE_EXCLUSION_PRESENT in partial.reason_codes
    assert 'shares unknown' in partial.rendered_claim
    assert 'member contributor set' in partial.rendered_claim
    assert partial.computation_trace['share_state'] == 'unknown'
    assert partial.computation_trace['per_pitcher_outs'][0]['outs'] >= 9


def test_rule5_emission_policy_pin_provably_neither_bucket(app):
    pitchers = _build_basic_basis(pitcher_count=2)
    day = PRODUCT_DATE
    clean_log = GameLog.query.filter_by(pitcher_id=pitchers[0].id, game_date=day).first()
    _evidence_object(
        OUTING_CLEAN_RULE_ID,
        subject_type='pitcher_appearance',
        subject_id=f'{clean_log.pitcher_id}:{clean_log.mlb_game_pk}',
        product_date=day,
    )
    _evidence_object(
        OUTING_CONTEXT_UNKNOWN_RULE_ID,
        subject_type='pitcher_appearance',
        subject_id='fixture:family-ran-marker',
        product_date=day - timedelta(days=1),
    )

    # Pinned cross-family dependency: a 0D-04 family run plus no object means provably neither.
    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    mix = _object(TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID)
    assert mix is not None
    assert len(mix.computation_trace['counts']['clean']) == 1
    assert len(mix.computation_trace['counts']['provably_neither']) == 1
    neither = mix.computation_trace['counts']['provably_neither'][0]
    assert neither['pitcher_id'] == pitchers[1].id
    assert mix.computation_trace['emission_policy_dependency']


def test_rule5_family_gap_unknown_without_partial_arithmetic(app):
    _build_basic_basis(pitcher_count=1)

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    mix = _object(TEAM_RELIEF_OUTING_CONTEXT_MIX_RULE_ID)
    assert mix.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert REASON_OUTING_FAMILY_COVERAGE_GAP in mix.reason_codes
    assert mix.computation_trace['partial_arithmetic_performed'] is False


def test_finish_spread_distinct_pitchers_unknown_and_legacy_caveat(app):
    pitchers = _build_basic_basis(pitcher_count=3)
    logs = [
        GameLog.query.filter_by(pitcher_id=pitcher.id).order_by(GameLog.id).first()
        for pitcher in pitchers
    ]
    _evidence_object(
        APPEARANCE_FINISH_CONTEXT_RULE_ID,
        subject_type='pitcher_appearance',
        subject_id=f'{logs[0].pitcher_id}:{logs[0].mlb_game_pk}',
        product_date=logs[0].game_date,
        trace={'finish_values': {
            'games_finished': 1,
            'save_situation': True,
            'save': True,
            'hold': False,
            'blown_save': False,
        }},
    )
    _evidence_object(
        APPEARANCE_FINISH_CONTEXT_RULE_ID,
        subject_type='pitcher_appearance',
        subject_id=f'{logs[1].pitcher_id}:{logs[1].mlb_game_pk}',
        product_date=logs[1].game_date,
        trace={'finish_values': {
            'games_finished': None,
            'save_situation': False,
            'save': False,
            'hold': True,
            'blown_save': True,
        }},
        reason_codes=['legacy_row_default_false_caveat'],
    )

    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    spread = _object(TEAM_RELIEF_FINISH_SPREAD_RULE_ID)
    assert spread.computation_trace['distinct_pitchers']['games_finished'] == {
        str(pitchers[0].id): pitchers[0].full_name
    } or spread.computation_trace['distinct_pitchers']['games_finished'] == {
        pitchers[0].id: pitchers[0].full_name
    }
    assert len(spread.computation_trace['distinct_pitchers']['save_situation']) == 1
    assert len(spread.computation_trace['distinct_pitchers']['hold']) == 1
    assert len(spread.computation_trace['games_finished_unknown']) == 2
    assert spread.computation_trace['floored_observation_rule_ids_consumed'] == []
    assert spread.computation_trace['legacy_caveat_carried'] is True


def test_recompute_basis_first_bounded_idempotent_and_sync(app, monkeypatch):
    pitchers = _build_basic_basis(pitcher_count=2)
    first_count = EvidenceObject.query.filter(
        EvidenceObject.rule_id.in_(TEAM_RELIEF_COMPOSITION_RULE_IDS)
    ).count()
    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)
    second_count = EvidenceObject.query.filter(
        EvidenceObject.rule_id.in_(TEAM_RELIEF_COMPOSITION_RULE_IDS)
    ).count()
    assert first_count == second_count

    basis = _basis(TEAM_A)
    rest = _object(TEAM_RELIEF_REST_DISTRIBUTION_RULE_ID)
    assert any(
        citation.source_pk == str(basis.id) and citation.citation_role == 'composition_basis'
        for citation in rest.citations
    )
    source = _evidence_object(WORKLOAD_DAYS_OF_REST_RULE_ID, subject_id=pitchers[0].id)
    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)
    marked = mark_source_evidence_supersession_for_team_relief_composition(
        source,
        reason_code=REASON_SOURCE_EVIDENCE_SUPERSEDED,
        batch_size=5,
    )
    assert marked['marked_count'] <= 5

    log = GameLog.query.filter_by(pitcher_id=pitchers[0].id).first()
    marked_log = mark_game_log_correction_for_team_relief_composition(log, batch_size=5)
    assert marked_log['marked_count'] <= 5

    result = rebuild_marked_team_relief_composition_evidence(sync_run_id=_sync_run().id, batch_size=20)
    assert result['basis_first'] is True
    if 'dependents' in result['rebuild_order']:
        assert result['rebuild_order'].index('basis') < result['rebuild_order'].index('dependents')

    monkeypatch.setenv('PHASE0D_EVIDENCE_BUILD', 'false')
    skipped = sync_service._safe_build_workload_recovery_evidence_stage(
        [PRODUCT_DATE],
        sync_run_id=_sync_run().id,
        source='test',
    )
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'


def test_public_isolation_rendered_claim_sweep_and_denominator_disclaimer(app):
    _build_basic_basis(pitcher_count=2)
    build_team_relief_composition_evidence(PRODUCT_DATE, sync_run_id=_sync_run().id)

    rows = EvidenceObject.query.filter(
        EvidenceObject.rule_id.in_(TEAM_RELIEF_COMPOSITION_RULE_IDS)
    ).all()
    assert rows
    basis_rows = [row for row in rows if row.rule_id == TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID]
    assert basis_rows
    assert all(BASIS_DISCLAIMER in row.rendered_claim for row in basis_rows)
    forbidden = ('thin', 'workhorse', 'struc' + 'ture', 'available', 'team grade')
    for row in rows:
        assert row.posture == EvidenceObject.POSTURE_INTERNAL_ONLY
        rendered = row.rendered_claim.lower()
        for term in forbidden:
            assert term not in rendered
    public_paths = [
        REPO_ROOT / 'backend' / 'api',
        REPO_ROOT / 'frontend' / 'src',
    ]
    public_text = ''
    for path in public_paths:
        if path.exists():
            public_text += '\n'.join(
                file.read_text(encoding='utf-8', errors='ignore')
                for file in path.rglob('*')
                if file.is_file() and file.suffix in {'.py', '.js', '.jsx', '.ts', '.tsx'}
            )
    assert 'team_relief_composition_evidence' not in public_text
    assert TEAM_RELIEF_CONTRIBUTOR_BASIS_RULE_ID not in public_text
