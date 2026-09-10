from datetime import date, datetime
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services import sync_metadata
from services.appearance_context_evidence import (
    APPEARANCE_RULE_IDS,
    BASE_STATE_LIMITATION,
    BASE_STATE_RULE_ID,
    ENTRY_RULE_ID,
    EXIT_RULE_ID,
    INNINGS_RULE_ID,
    ORDER_RULE_ID,
    PHASE_RULE_ID,
    PLAY_GRANULARITY_LIMITATION,
    RECONCILIATION_ENTITY_TYPE,
    RECONCILIATION_RULE_ID,
    REASON_APPEARANCE_ROLE_UNKNOWN,
    REASON_BASE_STATE_UNAVAILABLE,
    REASON_ENTRY_FLAG_MISSING,
    REASON_EXIT_OUTS_UNKNOWN,
    REASON_GAME_LOG_ROW_MISSING,
    REASON_NON_CONTIGUOUS_PITCHER_SPAN,
    REASON_ORDER_INCONSISTENT,
    REASON_OUTS_IMPLAUSIBLE,
    REASON_PBP_APPEARANCE_MISSING,
    REASON_PBP_EVENT_CORRECTED,
    REASON_RESUMED_GAME_SPANS_DATES,
    RULE_VERSION,
    _event_citation,
    _game_log_citation,
    _marker_citation,
    _readiness_payload,
    _register_appearance_rule,
    _register_appearance_template,
    _template_id,
    appearance_rule_definitions,
    build_appearance_context_evidence,
    mark_game_log_correction_for_appearance_context,
    mark_pbp_event_correction_for_appearance_context,
    rebuild_marked_appearance_context_evidence,
    register_appearance_context_rules,
)
from services.evidence_contract import build_evidence_object
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 4)
HOME_TEAM = 100
AWAY_TEAM = 200


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
        job_name='phase0d_appearance_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(seed, team_id, name=None):
    pitcher = Pitcher(
        mlb_id=800000 + seed,
        full_name=name or f'Appearance Pitcher {seed}',
        team_id=team_id,
        team_abbreviation=f'T{team_id}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _marker(game_pk, day=PRODUCT_DATE, *, status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED):
    marker = PlayByPlayProcessedGame(
        mlb_game_pk=game_pk,
        game_date=day,
        game_type='R',
        home_team_id=HOME_TEAM,
        away_team_id=AWAY_TEAM,
        final_state='final',
        processing_status=status,
        attempt_count=1,
        last_attempted_at=datetime(2026, 7, 4, 12, 0, 0),
        events_seen=1,
        events_stored=1,
        pitcher_events_seen=1,
        unresolved_pitcher_count=0,
        reconciliation_mismatch_count=0,
        event_fingerprint=f'fp-{game_pk}',
        source='mlb_stats_api:final_play_by_play',
        source_endpoint='/game/{gamePk}/playByPlay',
        processed_at=datetime(2026, 7, 4, 12, 0, 1) if status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED else None,
    )
    db.session.add(marker)
    db.session.flush()
    return marker


def _schedule(game_pk, day=PRODUCT_DATE, *, resumed=False):
    db.session.add_all([
        ScheduledGame(
            team_id=HOME_TEAM,
            opponent_team_id=AWAY_TEAM,
            game_pk=game_pk,
            game_date=day,
            home_away='home',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=12345 if resumed else None,
        ),
        ScheduledGame(
            team_id=AWAY_TEAM,
            opponent_team_id=HOME_TEAM,
            game_pk=game_pk,
            game_date=day,
            home_away='away',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=12345 if resumed else None,
        ),
    ])
    db.session.flush()


def _log(pitcher, game_pk, *, games_started=0, outs=3, day=PRODUCT_DATE):
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=day,
        game_type='R',
        opponent='Opponent',
        opponent_abbreviation='OPP',
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
        batters_faced=4,
    )
    db.session.add(log)
    db.session.flush()
    return log


def _event(
    game_pk,
    index,
    inning,
    half,
    pitcher,
    *,
    outs,
    home_score,
    away_score,
    is_change=False,
    fielding_team_id=None,
    batting_team_id=None,
    day=PRODUCT_DATE,
    pitcher_mlb_id=None,
):
    if fielding_team_id is None:
        fielding_team_id = HOME_TEAM if half == 'top' else AWAY_TEAM
    if batting_team_id is None:
        batting_team_id = AWAY_TEAM if half == 'top' else HOME_TEAM
    event = GamePlayByPlayEvent(
        mlb_game_pk=game_pk,
        event_index=index,
        source_play_id=f'{game_pk}-{index}',
        at_bat_index=index,
        game_date=day,
        game_type='R',
        home_team_id=HOME_TEAM,
        away_team_id=AWAY_TEAM,
        event_type='plate_appearance',
        event_type_code='field_out',
        inning=inning,
        half_inning=half,
        is_top_inning=half == 'top',
        outs_at_event=outs,
        home_score_at_event=home_score,
        away_score_at_event=away_score,
        pitcher_mlb_id=pitcher_mlb_id if pitcher is None else pitcher.mlb_id,
        pitcher_id=None if pitcher is None else pitcher.id,
        batter_mlb_id=900000 + index,
        batting_team_id=batting_team_id,
        fielding_team_id=fielding_team_id,
        is_pitching_change=is_change,
        is_scoring_play=False,
        is_mound_visit=False,
        source='mlb_stats_api:final_play_by_play',
        source_endpoint='/game/{gamePk}/playByPlay',
    )
    db.session.add(event)
    db.session.flush()
    return event


def _standard_game(game_pk=9001, *, entry_flag=False, resumed=False):
    _schedule(game_pk, resumed=resumed)
    marker = _marker(game_pk)
    seed_base = game_pk * 10
    home_starter = _pitcher(seed_base + 1, HOME_TEAM, 'Home Starter')
    home_reliever = _pitcher(seed_base + 2, HOME_TEAM, 'Home Reliever')
    home_second = _pitcher(seed_base + 3, HOME_TEAM, 'Home Second Reliever')
    away_starter = _pitcher(seed_base + 4, AWAY_TEAM, 'Away Starter')
    away_reliever = _pitcher(seed_base + 5, AWAY_TEAM, 'Away Reliever')
    _log(home_starter, game_pk, games_started=1, outs=21)
    home_log = _log(home_reliever, game_pk, games_started=0, outs=3)
    _log(home_second, game_pk, games_started=0, outs=1)
    _log(away_starter, game_pk, games_started=1, outs=21)
    away_log = _log(away_reliever, game_pk, games_started=0, outs=1)
    _event(game_pk, 0, 1, 'top', home_starter, outs=0, home_score=0, away_score=0)
    _event(game_pk, 1, 1, 'bottom', away_starter, outs=0, home_score=0, away_score=0)
    _event(game_pk, 2, 8, 'top', home_starter, outs=1, home_score=4, away_score=3)
    prior = _event(
        game_pk,
        3,
        8,
        'top',
        home_reliever,
        outs=2,
        home_score=4,
        away_score=3,
        is_change=entry_flag,
    )
    _event(game_pk, 4, 8, 'top', home_reliever, outs=3, home_score=4, away_score=3)
    exit_event = _event(game_pk, 5, 9, 'top', home_reliever, outs=1, home_score=4, away_score=3)
    _event(game_pk, 6, 9, 'top', home_second, outs=2, home_score=4, away_score=3, is_change=True)
    _event(game_pk, 7, 8, 'bottom', away_starter, outs=1, home_score=5, away_score=4)
    _event(game_pk, 8, 8, 'bottom', away_reliever, outs=2, home_score=5, away_score=4, is_change=True)
    db.session.flush()
    return {
        'marker': marker,
        'home_starter': home_starter,
        'home_reliever': home_reliever,
        'home_second': home_second,
        'away_starter': away_starter,
        'away_reliever': away_reliever,
        'home_log': home_log,
        'away_log': away_log,
        'entry_event': prior,
        'exit_event': exit_event,
        'game_pk': game_pk,
    }


def _rows(rule_id):
    return EvidenceObject.query.filter_by(rule_id=rule_id).order_by(EvidenceObject.id).all()


def _appearance_row(rule_id, pitcher, game_pk):
    return EvidenceObject.query.filter_by(
        rule_id=rule_id,
        subject_id=f'{pitcher.id}:{game_pk}',
    ).one()


def test_registration_guards_and_base_state_lock(app):
    registry, templates = register_appearance_context_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    rules = registry.all_rules()

    assert [rule.rule_id for rule in rules] == sorted(APPEARANCE_RULE_IDS)
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert len(templates._templates) == 7
    assert registry.get(BASE_STATE_RULE_ID).allowed_completeness == (
        EvidenceObject.COMPLETENESS_UNKNOWN,
    )
    assert 'appearance_entry_context' in appearance_rule_definitions()

    with pytest.raises(EvidenceRuleError):
        _register_appearance_rule(
            EvidenceRuleRegistry(),
            EvidenceRule(
                rule_id='bad_public_appearance_rule',
                rule_version=1,
                evidence_type='appearance_context_fact',
                plain_language_definition='Records a test-only appearance fact.',
                required_input_families=('final_play_by_play', 'game_logs'),
                required_cited_fields=('final_play_by_play.mlb_game_pk',),
                posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
            ),
        )
    with pytest.raises(EvidenceLanguageError):
        _register_appearance_template(
            ClaimTemplateRegistry(),
            ClaimTemplate(
                template_id='bad_high_leverage_claim',
                template_version=1,
                template_text='High-leverage entry recorded.',
            ),
        )

    with app.app_context():
        sample = _standard_game()
        rule = registry.get(BASE_STATE_RULE_ID)
        template = templates.get(_template_id(BASE_STATE_RULE_ID))
        evidence = build_evidence_object(
            rule_id=BASE_STATE_RULE_ID,
            rule_version=RULE_VERSION,
            claim_template=template,
            claim_values={'claim': 'Base state complete test claim.'},
            subject_type='pitcher_appearance',
            subject_id=f'{sample["home_reliever"].id}:{sample["game_pk"]}',
            product_date=PRODUCT_DATE,
            cited_inputs=(
                _marker_citation(sample['marker']),
                _game_log_citation(sample['home_log'], ('games_started', 'innings_pitched_outs')),
                _event_citation(sample['entry_event'], ('event_index',), 'entry_event'),
            ),
            computation_trace={'steps': ['Tried to emit complete base state.']},
            input_values={
                'final_play_by_play.mlb_game_pk': sample['game_pk'],
                'game_logs.games_started': 0,
            },
            readiness_payload=_readiness_payload(),
            registry=registry,
        )

    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_WITHHELD
    assert 'completeness_not_allowed_by_rule' in evidence.reason_codes


def test_entry_exit_phase_order_and_base_state_semantics(app):
    with app.app_context():
        sample = _standard_game(entry_flag=False)
        result = build_appearance_context_evidence(PRODUCT_DATE)
        entry = _appearance_row(ENTRY_RULE_ID, sample['home_reliever'], sample['game_pk'])
        exit_row = _appearance_row(EXIT_RULE_ID, sample['home_reliever'], sample['game_pk'])
        order = _appearance_row(ORDER_RULE_ID, sample['home_reliever'], sample['game_pk'])
        innings = _appearance_row(INNINGS_RULE_ID, sample['home_reliever'], sample['game_pk'])
        phase = _appearance_row(PHASE_RULE_ID, sample['home_reliever'], sample['game_pk'])
        base = _appearance_row(BASE_STATE_RULE_ID, sample['home_reliever'], sample['game_pk'])
        away_entry = _appearance_row(ENTRY_RULE_ID, sample['away_reliever'], sample['game_pk'])

    assert result['objects_built'] >= 14
    assert entry.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
    assert REASON_ENTRY_FLAG_MISSING in entry.reason_codes
    assert 'top of the 8' in entry.rendered_claim
    assert '1 out' in entry.rendered_claim
    assert 'team leading 4-3 (margin +1)' in entry.rendered_claim
    assert 'mid-inning entry' in entry.rendered_claim
    assert 'runners on base at entry unknown' in entry.rendered_claim
    assert PLAY_GRANULARITY_LIMITATION in entry.limitations
    assert BASE_STATE_LIMITATION in entry.limitations
    assert entry.computation_trace['preceding_same_half_event_index'] == 2
    assert entry.computation_trace['margin_arithmetic']['margin'] == 1
    assert 'team trailing 4-5 (margin -1)' in away_entry.rendered_claim

    assert 'top of the 9' in exit_row.rendered_claim
    assert '1 out recorded post-play' in exit_row.rendered_claim
    assert 'removed mid-inning' in exit_row.rendered_claim
    assert PLAY_GRANULARITY_LIMITATION in exit_row.limitations
    assert 'Second pitcher used by the team' in order.rendered_claim
    assert order.computation_trace['team_entry_event_indexes'] == [0, 3, 6]
    assert '2 inning(s): 8 through 9' in innings.rendered_claim
    assert "registered 'late' band (innings 7-9)" in phase.rendered_claim
    assert base.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert base.reason_codes == [REASON_BASE_STATE_UNAVAILABLE]
    assert 'base-runner state' in base.rendered_claim
    assert not any('runners_on_base_at_entry' in str(value) for value in (
        base.typed_cited_inputs,
        base.computation_trace,
        base.rendered_claim,
    ))


def test_half_start_first_event_exit_unknown_extras_and_finished_game(app):
    with app.app_context():
        game_pk = 9100
        _schedule(game_pk)
        _marker(game_pk)
        starter = _pitcher(100, HOME_TEAM)
        reliever = _pitcher(101, HOME_TEAM)
        away_starter = _pitcher(102, AWAY_TEAM)
        _log(starter, game_pk, games_started=1, outs=27)
        _log(reliever, game_pk, games_started=0, outs=5)
        _log(away_starter, game_pk, games_started=1, outs=27)
        first = _event(game_pk, 0, 1, 'top', starter, outs=0, home_score=0, away_score=0)
        _event(game_pk, 1, 1, 'bottom', away_starter, outs=1, home_score=0, away_score=0)
        _event(game_pk, 2, 10, 'top', reliever, outs=1, home_score=7, away_score=7)
        _event(game_pk, 3, 11, 'top', reliever, outs=None, home_score=8, away_score=7)

        from services.appearance_context_evidence import _entry_state, _pitching_segments
        first_segment = _pitching_segments([first])[1][HOME_TEAM][0]
        first_entry = _entry_state(first_segment, [first])
        build_appearance_context_evidence(PRODUCT_DATE)
        entry = _appearance_row(ENTRY_RULE_ID, reliever, game_pk)
        exit_row = _appearance_row(EXIT_RULE_ID, reliever, game_pk)
        innings = _appearance_row(INNINGS_RULE_ID, reliever, game_pk)
        phase = _appearance_row(PHASE_RULE_ID, reliever, game_pk)
        reconciliation = _appearance_row(RECONCILIATION_RULE_ID, reliever, game_pk)

    assert first_entry['outs_at_entry'] == 0
    assert first_entry['home_score'] == 0
    assert first_entry['away_score'] == 0
    assert '0 outs' in entry.rendered_claim
    assert 'half-inning start' in entry.rendered_claim
    assert exit_row.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert exit_row.reason_codes == [REASON_EXIT_OUTS_UNKNOWN]
    assert 'finished the team pitching sequence' in exit_row.rendered_claim
    assert '2 inning(s): 10 through 11' in innings.rendered_claim
    assert "registered 'extras' band (inning 10 or later)" in phase.rendered_claim
    assert reconciliation.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE


def test_gating_statuses_and_resumed_single_product_day(app):
    statuses = (
        PlayByPlayProcessedGame.STATUS_INCOMPLETE,
        PlayByPlayProcessedGame.STATUS_FAILED,
        PlayByPlayProcessedGame.STATUS_ABSENT,
        PlayByPlayProcessedGame.STATUS_AMBIGUOUS,
        PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
    )
    with app.app_context():
        for offset, status in enumerate(statuses):
            game_pk = 9200 + offset
            _schedule(game_pk, resumed=status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED)
            _marker(game_pk, status=status)
            starter = _pitcher(200 + offset * 3, HOME_TEAM)
            reliever = _pitcher(201 + offset * 3, HOME_TEAM)
            away_starter = _pitcher(202 + offset * 3, AWAY_TEAM)
            _log(starter, game_pk, games_started=1, outs=24)
            _log(reliever, game_pk, games_started=0, outs=1)
            _log(away_starter, game_pk, games_started=1, outs=27)
            _event(game_pk, 0, 1, 'top', starter, outs=0, home_score=0, away_score=0)
            _event(game_pk, 1, 8, 'top', reliever, outs=1, home_score=3, away_score=3)

        result = build_appearance_context_evidence(PRODUCT_DATE)
        rows = _rows(ENTRY_RULE_ID)
        resumed_entry = rows[0]

    assert result['games_considered'] == len(statuses)
    assert len(rows) == 1
    assert REASON_RESUMED_GAME_SPANS_DATES in resumed_entry.reason_codes
    assert any('game was suspended and resumed' in item for item in resumed_entry.limitations)


def test_reconciliation_truth_table_and_subject_identity_guard(app):
    with app.app_context():
        matched = _standard_game(game_pk=9300)
        pbp_missing_game = 9301
        _schedule(pbp_missing_game)
        _marker(pbp_missing_game)
        starter = _pitcher(400, HOME_TEAM)
        missing = _pitcher(401, HOME_TEAM)
        away_starter = _pitcher(402, AWAY_TEAM)
        _log(starter, pbp_missing_game, games_started=1, outs=27)
        _log(missing, pbp_missing_game, games_started=0, outs=0)
        _log(away_starter, pbp_missing_game, games_started=1, outs=27)
        _event(pbp_missing_game, 0, 1, 'top', starter, outs=1, home_score=0, away_score=0)

        row_missing_game = 9302
        _schedule(row_missing_game)
        _marker(row_missing_game)
        row_missing_starter = _pitcher(410, HOME_TEAM)
        row_missing_pitcher = _pitcher(411, HOME_TEAM)
        row_missing_away = _pitcher(412, AWAY_TEAM)
        _log(row_missing_starter, row_missing_game, games_started=1, outs=27)
        _log(row_missing_away, row_missing_game, games_started=1, outs=27)
        _event(row_missing_game, 0, 1, 'top', row_missing_starter, outs=1, home_score=0, away_score=0)
        _event(row_missing_game, 1, 7, 'top', row_missing_pitcher, outs=2, home_score=2, away_score=1)

        no_identity_game = 9303
        _schedule(no_identity_game)
        _marker(no_identity_game)
        known_starter = _pitcher(420, HOME_TEAM)
        known_away = _pitcher(421, AWAY_TEAM)
        _log(known_starter, no_identity_game, games_started=1, outs=27)
        _log(known_away, no_identity_game, games_started=1, outs=27)
        _event(no_identity_game, 0, 1, 'top', known_starter, outs=1, home_score=0, away_score=0)
        _event(no_identity_game, 1, 7, 'top', None, outs=2, home_score=2, away_score=1, pitcher_mlb_id=999999)

        build_appearance_context_evidence(PRODUCT_DATE)
        matched_row = _appearance_row(RECONCILIATION_RULE_ID, matched['home_reliever'], matched['game_pk'])
        missing_row = _appearance_row(RECONCILIATION_RULE_ID, missing, pbp_missing_game)
        row_missing = _appearance_row(RECONCILIATION_RULE_ID, row_missing_pitcher, row_missing_game)
        failures = SyncFailure.query.filter_by(entity_type=RECONCILIATION_ENTITY_TYPE).all()

    assert matched_row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
    assert missing_row.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert missing_row.reason_codes == [REASON_PBP_APPEARANCE_MISSING]
    assert row_missing.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert REASON_GAME_LOG_ROW_MISSING in row_missing.reason_codes
    assert any((failure.payload or {}).get('reason') == REASON_GAME_LOG_ROW_MISSING for failure in failures)
    assert any((failure.payload or {}).get('identity_guard') == 'internal_pitcher_not_found' for failure in failures)
    assert EvidenceObject.query.filter(EvidenceObject.subject_id.like(f'%:{no_identity_game}')).count() == 0
    assert Pitcher.query.filter_by(mlb_id=999999).first() is None


def test_reconciliation_conflicts_for_non_contiguous_order_and_outs(app):
    with app.app_context():
        non_contig_game = 9400
        _schedule(non_contig_game)
        _marker(non_contig_game)
        starter = _pitcher(500, HOME_TEAM)
        target = _pitcher(501, HOME_TEAM)
        other = _pitcher(502, HOME_TEAM)
        away = _pitcher(503, AWAY_TEAM)
        for pitcher, gs in ((starter, 1), (target, 0), (other, 0), (away, 1)):
            _log(pitcher, non_contig_game, games_started=gs, outs=1 if gs == 0 else 27)
        _event(non_contig_game, 0, 1, 'top', starter, outs=1, home_score=0, away_score=0)
        _event(non_contig_game, 1, 7, 'top', target, outs=1, home_score=2, away_score=1)
        _event(non_contig_game, 2, 7, 'top', other, outs=2, home_score=2, away_score=1)
        _event(non_contig_game, 3, 7, 'top', target, outs=3, home_score=2, away_score=1)

        outs_game = 9401
        _schedule(outs_game)
        _marker(outs_game)
        starter2 = _pitcher(510, HOME_TEAM)
        target2 = _pitcher(511, HOME_TEAM)
        away2 = _pitcher(512, AWAY_TEAM)
        _log(starter2, outs_game, games_started=1, outs=27)
        _log(target2, outs_game, games_started=0, outs=5)
        _log(away2, outs_game, games_started=1, outs=27)
        _event(outs_game, 0, 1, 'top', starter2, outs=1, home_score=0, away_score=0)
        _event(outs_game, 1, 8, 'top', starter2, outs=2, home_score=2, away_score=1)
        _event(outs_game, 2, 8, 'top', target2, outs=3, home_score=2, away_score=1)

        order_game = 9402
        _schedule(order_game)
        _marker(order_game)
        starter3 = _pitcher(520, HOME_TEAM)
        target3 = _pitcher(521, HOME_TEAM)
        away3 = _pitcher(522, AWAY_TEAM)
        _log(starter3, order_game, games_started=1, outs=27)
        _log(target3, order_game, games_started=0, outs=1)
        _log(away3, order_game, games_started=1, outs=27)
        _event(order_game, 0, 1, 'top', target3, outs=1, home_score=0, away_score=0)

        build_appearance_context_evidence(PRODUCT_DATE)
        non_contig = _appearance_row(RECONCILIATION_RULE_ID, target, non_contig_game)
        outs = _appearance_row(RECONCILIATION_RULE_ID, target2, outs_game)
        order = _appearance_row(RECONCILIATION_RULE_ID, target3, order_game)
        failures = [failure.payload for failure in SyncFailure.query.filter_by(entity_type=RECONCILIATION_ENTITY_TYPE).all()]

    assert non_contig.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert REASON_NON_CONTIGUOUS_PITCHER_SPAN in non_contig.reason_codes
    assert outs.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert REASON_OUTS_IMPLAUSIBLE in outs.reason_codes
    assert 'cannot hold that total' in outs.rendered_claim
    assert order.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert REASON_ORDER_INCONSISTENT in order.reason_codes
    assert {payload.get('reason') for payload in failures} >= {
        REASON_NON_CONTIGUOUS_PITCHER_SPAN,
        REASON_OUTS_IMPLAUSIBLE,
        REASON_ORDER_INCONSISTENT,
    }


def test_role_unknown_doubleheader_and_idempotency(app):
    with app.app_context():
        first = _standard_game(game_pk=9500)
        second = _standard_game(game_pk=9501)
        second['home_log'].games_started = None
        db.session.flush()

        build_appearance_context_evidence(PRODUCT_DATE)
        first_count = EvidenceObject.query.count()
        build_appearance_context_evidence(PRODUCT_DATE)
        second_count = EvidenceObject.query.count()
        unknown = _appearance_row(RECONCILIATION_RULE_ID, second['home_reliever'], second['game_pk'])
        entry_subjects = {
            row.subject_id
            for row in EvidenceObject.query.filter_by(rule_id=ENTRY_RULE_ID).all()
        }

    assert first_count == second_count
    assert unknown.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert unknown.reason_codes == [REASON_APPEARANCE_ROLE_UNKNOWN]
    assert f'{first["home_reliever"].id}:{first["game_pk"]}' in entry_subjects
    assert f'{second["home_reliever"].id}:{second["game_pk"]}' not in entry_subjects


def test_recompute_from_pbp_and_game_log_corrections_is_bounded(app):
    with app.app_context():
        run = _sync_run()
        sample = _standard_game(game_pk=9600)
        unrelated = _standard_game(game_pk=9601)
        build_appearance_context_evidence(PRODUCT_DATE, sync_run_id=run.id)
        target_before = _appearance_row(ENTRY_RULE_ID, sample['home_reliever'], sample['game_pk'])
        unrelated_before = _appearance_row(ENTRY_RULE_ID, unrelated['home_reliever'], unrelated['game_pk'])
        target_id = target_before.id
        unrelated_updated_at = unrelated_before.updated_at

        preceding = GamePlayByPlayEvent.query.filter_by(
            mlb_game_pk=sample['game_pk'],
            event_index=2,
        ).one()
        preceding.outs_at_event = 0
        marked_pbp = mark_pbp_event_correction_for_appearance_context(
            preceding,
            sync_run_id=run.id,
            batch_size=1,
        )
        rebuilt = rebuild_marked_appearance_context_evidence(sync_run_id=run.id)
        target_after = db.session.get(EvidenceObject, target_id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_before.id)
        target_status_after_rebuild = target_after.recompute_status
        target_reasons_after_rebuild = list(target_after.recompute_reason_codes or [])
        target_trace_after_rebuild = dict(target_after.computation_trace or {})
        target_claim_after_rebuild = target_after.rendered_claim

        sample['home_log'].innings_pitched_outs = 2
        sample['home_log'].innings_pitched = 2 / 3.0
        marked_log = mark_game_log_correction_for_appearance_context(
            sample['home_log'],
            sync_run_id=run.id,
            batch_size=10,
        )
        target_status_after_log_mark = db.session.get(EvidenceObject, target_id).recompute_status

    assert marked_pbp['marked_count'] == 1
    assert marked_pbp['evidence_ids'] == [target_id]
    assert rebuilt['objects_rebuilt'] == 1
    assert target_status_after_rebuild == EvidenceObject.RECOMPUTE_CURRENT
    assert target_reasons_after_rebuild == []
    assert target_trace_after_rebuild['superseded_prior']['rendered_claim']
    assert '0 outs' in target_claim_after_rebuild
    assert unrelated_after.updated_at == unrelated_updated_at
    assert marked_log['marked_count'] >= 1
    assert target_status_after_log_mark == EvidenceObject.RECOMPUTE_NEEDED
    assert REASON_PBP_EVENT_CORRECTED not in unrelated_after.recompute_reason_codes


def test_sync_stage_fail_soft_kill_switch_and_public_payload_shape(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        before = set(sync_metadata.build_sync_status_payload().keys())
        _standard_game(game_pk=9700)
        result = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        after = set(sync_metadata.build_sync_status_payload().keys())

        def boom(*args, **kwargs):
            raise RuntimeError('appearance stage exploded')

        import services.appearance_context_evidence as appearance_service
        monkeypatch.setattr(appearance_service, 'build_appearance_context_evidence', boom)
        with caplog.at_level(logging.WARNING, logger='baseballos.daily_sync'):
            failed = sync_service._safe_build_workload_recovery_evidence_stage(
                [PRODUCT_DATE],
                sync_run_id=run.id,
                source='test',
                run_logger=logging.getLogger('baseballos.daily_sync'),
            )
        failure = SyncFailure.query.order_by(SyncFailure.id.desc()).first()

        monkeypatch.setenv('PHASE0D_EVIDENCE_BUILD', 'false')
        monkeypatch.setattr(
            appearance_service,
            'build_appearance_context_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )

    assert result['status'] == 'built'
    assert result['appearance_builds'][0]['objects_built'] > 0
    assert after == before
    assert failed['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'


def test_public_surface_isolation_static_sweep_and_claim_language(app):
    with app.app_context():
        _standard_game(game_pk=9800)
        build_appearance_context_evidence(PRODUCT_DATE)
        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())

    blocked_terms = ('leverage', 'pressure', 'availability', 'fatigue', 'prediction')
    assert not any(term in rendered for term in blocked_terms)
    public_paths = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    )
    blocked = (
        'services.appearance_context_evidence',
        'appearance_context_evidence',
        *APPEARANCE_RULE_IDS,
        'appearance_context_fact',
    )
    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for needle in blocked:
            assert needle not in text
