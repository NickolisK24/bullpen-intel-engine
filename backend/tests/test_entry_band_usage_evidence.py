from datetime import date, datetime, timedelta
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services import sync_metadata
import services.entry_band_usage_evidence as entry_service
from services.entry_band_usage_evidence import (
    APPEARANCE_ENTRY_BAND_RULE_ID,
    APPEARANCE_FINISH_CONTEXT_RULE_ID,
    BASE_STATE_LIMITATION,
    ENTRY_BAND_CELLS,
    ENTRY_BAND_USAGE_RULE_IDS,
    FINISH_CONTEXT_CONTRADICTION_ENTITY_TYPE,
    LOCKED_INTERNAL_RULE_IDS,
    PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
    PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID,
    PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID,
    PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID,
    PITCHER_SAVE_HOLD_WINDOW_RULE_ID,
    REASON_BAND_UNKNOWN_IN_WINDOW,
    REASON_ENTRY_CONTEXT_INCOHERENT,
    REASON_ENTRY_CONTEXT_UNAVAILABLE,
    REASON_GAMES_FINISHED_UNKNOWN,
    REASON_INCOMPLETE_SLATE_DAY,
    REASON_INSUFFICIENT_SAMPLE,
    REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT,
    REASON_MULTI_INNING_UNKNOWN_IN_WINDOW,
    REASON_ORDER_UNKNOWN_IN_WINDOW,
    RULE_VERSION,
    _entry_band_usage_rule,
    _entry_phase,
    _margin_band,
    _register_entry_band_usage_rule,
    _register_entry_band_usage_template,
    build_entry_band_usage_evidence,
    mark_game_log_correction_for_entry_band_usage,
    mark_source_evidence_supersession_for_entry_band_usage,
    rebuild_marked_entry_band_usage_evidence,
    register_entry_band_usage_rules,
)
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
        job_name='phase0d_entry_band_usage_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(seed=1, team_id=1):
    pitcher = Pitcher(
        mlb_id=810000 + seed,
        full_name=f'Entry Band Pitcher {seed}',
        team_id=team_id,
        team_abbreviation=f'T{team_id}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _game_pk(day, suffix=0):
    return int(day.strftime('%Y%m%d')) * 10 + suffix


def _complete_slate(day, *, suffix=0):
    game_pk = _game_pk(day, suffix)
    if ScheduledGame.query.filter_by(game_pk=game_pk).first() is None:
        db.session.add_all([
            ScheduledGame(
                team_id=1,
                opponent_team_id=2,
                game_pk=game_pk,
                game_date=day,
                home_away='home',
                status_state=ScheduledGame.STATE_FINAL,
                status_code='F',
                game_type='R',
            ),
            ScheduledGame(
                team_id=2,
                opponent_team_id=1,
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
            home_team_id=1,
            away_team_id=2,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            processed_at=datetime(2026, 7, 4, 12, 0, 0),
        ))
    db.session.flush()
    return game_pk


def _incomplete_slate(day, *, suffix=8):
    game_pk = _game_pk(day, suffix)
    db.session.add_all([
        ScheduledGame(
            team_id=11,
            opponent_team_id=12,
            game_pk=game_pk,
            game_date=day,
            home_away='home',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
        ),
        ScheduledGame(
            team_id=12,
            opponent_team_id=11,
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


def _log(
    pitcher,
    day=PRODUCT_DATE,
    *,
    suffix=0,
    games_started=0,
    games_finished=0,
    save_situation=False,
    save=False,
    hold=False,
    blown_save=False,
    win=False,
    loss=False,
    batters_faced=3,
    outs=3,
):
    game_pk = _game_pk(day, suffix)
    if ScheduledGame.query.filter_by(game_pk=game_pk).first() is None:
        _complete_slate(day, suffix=suffix)
    row = GameLog(
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
        batters_faced=batters_faced,
        games_finished=games_finished,
        save_situation=save_situation,
        save=save,
        hold=hold,
        blown_save=blown_save,
        win=win,
        loss=loss,
    )
    db.session.add(row)
    db.session.flush()
    if batters_faced is None:
        row.batters_faced = None
        db.session.flush()
    return row


def _entry_context(log, *, inning=8, margin=1, state=EvidenceObject.COMPLETENESS_COMPLETE, suffix='entry'):
    row = EvidenceObject(
        evidence_key=f'entry-context-{log.id}-{suffix}',
        evidence_type='appearance_context_fact',
        subject_type='pitcher_appearance',
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=f'pitcher_appearance:{log.pitcher_id}:{log.mlb_game_pk}:entry:{suffix}',
        product_date=log.game_date,
        claim_template_id='appearance_entry_context_claim',
        rendered_claim='Stored entry context fixture.',
        rule_id='appearance_entry_context',
        rule_version=1,
        rule_definition_hash='entry-context-test-hash',
        typed_cited_inputs=[],
        computation_trace={'margin_arithmetic': {'margin': margin}},
        completeness_state=state,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0d:appearance_context_evidence',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
    )
    row.citations = [
        EvidenceCitation(
            source_family='final_play_by_play',
            source_table='game_play_by_play_events',
            source_pk=f'entry-{log.id}',
            source_field_names=['mlb_game_pk', 'inning'],
            citation_role='entry_event',
            cited_values={'mlb_game_pk': log.mlb_game_pk, 'inning': inning},
            provenance={'source': 'test_final_event'},
        ),
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=str(log.id),
            source_field_names=['games_started'],
            citation_role='supporting_input',
            cited_values={'games_started': log.games_started},
            provenance={'source': 'game_logs'},
        ),
    ]
    db.session.add(row)
    db.session.flush()
    return row


def _order_context(log, *, order=2, state=EvidenceObject.COMPLETENESS_COMPLETE, suffix='order'):
    row = EvidenceObject(
        evidence_key=f'order-context-{log.id}-{suffix}',
        evidence_type='appearance_context_fact',
        subject_type='pitcher_appearance',
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=f'pitcher_appearance:{log.pitcher_id}:{log.mlb_game_pk}:order:{suffix}',
        product_date=log.game_date,
        claim_template_id='appearance_order_in_game_claim',
        rendered_claim='Stored team sequence fixture.',
        rule_id='appearance_order_in_game',
        rule_version=1,
        rule_definition_hash='order-context-test-hash',
        typed_cited_inputs=[],
        computation_trace={'order': order},
        completeness_state=state,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0d:appearance_context_evidence',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
    )
    row.citations = [
        EvidenceCitation(
            source_family='final_play_by_play',
            source_table='game_play_by_play_events',
            source_pk=f'order-{log.id}',
            source_field_names=['mlb_game_pk', 'event_index'],
            citation_role='team_sequence_entry',
            cited_values={'mlb_game_pk': log.mlb_game_pk, 'event_index': order},
            provenance={'source': 'test_final_event'},
        ),
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=str(log.id),
            source_field_names=['games_started'],
            citation_role='supporting_input',
            cited_values={'games_started': log.games_started},
            provenance={'source': 'game_logs'},
        ),
    ]
    db.session.add(row)
    db.session.flush()
    return row


def _multi_inning_object(log, *, state=EvidenceObject.COMPLETENESS_COMPLETE, suffix='multi'):
    row = EvidenceObject(
        evidence_key=f'multi-inning-{log.id}-{suffix}',
        evidence_type='workload_recovery_fact',
        subject_type='pitcher',
        subject_id=str(log.pitcher_id),
        subject_key=f'pitcher:{log.pitcher_id}:{log.game_date.isoformat()}:multi:{suffix}',
        product_date=log.game_date,
        claim_template_id='outing_multi_inning_claim',
        rendered_claim='Stored multi-inning fixture.',
        rule_id='outing_multi_inning',
        rule_version=1,
        rule_definition_hash='multi-inning-test-hash',
        typed_cited_inputs=[],
        computation_trace={'outing_fixture': suffix},
        completeness_state=state,
        reason_codes=[] if state == EvidenceObject.COMPLETENESS_COMPLETE else ['unknown_fixture'],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0d:workload_recovery_evidence',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
    )
    row.citations = [
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=str(log.id),
            source_field_names=['game_date', 'mlb_game_pk', 'innings_pitched_outs'],
            citation_role='supporting_input',
            cited_values={
                'game_date': log.game_date.isoformat(),
                'mlb_game_pk': log.mlb_game_pk,
                'innings_pitched_outs': log.innings_pitched_outs,
            },
            provenance={'source': 'game_logs'},
        )
    ]
    db.session.add(row)
    db.session.flush()
    return row


def _row(rule_id, *, subject_contains=None):
    query = EvidenceObject.query.filter_by(rule_id=rule_id)
    if subject_contains:
        query = query.filter(EvidenceObject.subject_key.contains(subject_contains))
    return query.one()


def _rows(rule_id):
    return EvidenceObject.query.filter_by(rule_id=rule_id).order_by(EvidenceObject.subject_key).all()


def _window_fixture(pitcher, count, *, finished_count=0, start_suffix=0):
    _seed_complete_coverage()
    rows = []
    for index in range(count):
        day = PRODUCT_DATE - timedelta(days=count - 1 - index)
        row = _log(
            pitcher,
            day,
            suffix=start_suffix + index,
            games_finished=1 if index < finished_count else 0,
            save_situation=index % 2 == 0,
            hold=index % 3 == 0,
        )
        _entry_context(row, inning=8 if index % 2 == 0 else 10, margin=1)
        _order_context(row, order=2 if index % 2 == 0 else 3)
        rows.append(row)
    return rows


def test_registration_lint_and_posture_lock_guards():
    registry, templates = register_entry_band_usage_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    rules = registry.all_rules()

    assert [rule.rule_id for rule in rules] == sorted(ENTRY_BAND_USAGE_RULE_IDS)
    assert len(rules) == 7
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert set(LOCKED_INTERNAL_RULE_IDS) == {
        APPEARANCE_ENTRY_BAND_RULE_ID,
        PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID,
    }
    assert all(registry.get(rule_id).posture_default == EvidenceObject.POSTURE_INTERNAL_ONLY for rule_id in LOCKED_INTERNAL_RULE_IDS)
    assert templates.get('pitcher_save_hold_window_claim_7d').template_text == '{claim}'
    assert templates.get('pitcher_save_hold_window_claim_14d_degraded').template_text == '{claim}'

    for rule_id in LOCKED_INTERNAL_RULE_IDS:
        with pytest.raises(EvidenceRuleError):
            _register_entry_band_usage_rule(
                EvidenceRuleRegistry(),
                EvidenceRule(
                    rule_id=rule_id,
                    rule_version=1,
                    evidence_type=rule_id,
                    plain_language_definition='A neutral test definition.',
                    required_input_families=('game_logs',),
                    required_cited_fields=('game_logs.games_started',),
                    posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
                ),
            )

    for text in ('closer', 'high-leverage', 'trusted', '50% conversion template'):
        with pytest.raises(EvidenceLanguageError):
            _register_entry_band_usage_template(
                ClaimTemplateRegistry(),
                ClaimTemplate('bad_entry_band_template', 1, text),
            )


def test_posture_locked_emitted_objects_remain_internal(app):
    with app.app_context():
        pitcher = _pitcher()
        rows = _window_fixture(pitcher, 5, finished_count=1)
        for row in rows[:2]:
            _multi_inning_object(row)

        build_entry_band_usage_evidence(PRODUCT_DATE)
        emitted = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(LOCKED_INTERNAL_RULE_IDS)).all()

    assert emitted
    assert {row.posture for row in emitted} == {EvidenceObject.POSTURE_INTERNAL_ONLY}


def test_12_cell_band_boundaries_and_perspective_signs(app):
    assert _entry_phase(3) == 'early'
    assert _entry_phase(4) == 'middle'
    assert _entry_phase(6) == 'middle'
    assert _entry_phase(7) == 'late'
    assert _entry_phase(9) == 'late'
    assert _entry_phase(10) == 'extras'
    assert _margin_band(0) == 'one_run'
    assert _margin_band(1) == 'one_run'
    assert _margin_band(-1) == 'one_run'
    assert _margin_band(2) == 'two_three'
    assert _margin_band(3) == 'two_three'
    assert _margin_band(4) == 'four_plus'
    assert len(ENTRY_BAND_CELLS) == 12

    with app.app_context():
        pitcher = _pitcher()
        plus = _log(pitcher, suffix=1)
        minus = _log(pitcher, suffix=2)
        _entry_context(plus, inning=8, margin=1)
        _entry_context(minus, inning=10, margin=-1)

        build_entry_band_usage_evidence(PRODUCT_DATE)
        plus_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(plus.mlb_game_pk))
        minus_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(minus.mlb_game_pk))

    assert plus_row.computation_trace['band_cell'] == 'late_one_run'
    assert minus_row.computation_trace['band_cell'] == 'extras_one_run'
    assert BASE_STATE_LIMITATION in plus_row.limitations


def test_rule1_missing_unknown_conflict_and_source_supersession_recompute(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher()
        missing = _log(pitcher, suffix=10)
        unknown = _log(pitcher, suffix=11)
        conflict = _log(pitcher, suffix=12)
        changed = _log(pitcher, suffix=13)
        _entry_context(unknown, state=EvidenceObject.COMPLETENESS_UNKNOWN, suffix='unknown')
        _entry_context(conflict, state=EvidenceObject.COMPLETENESS_CONFLICT, suffix='conflict')
        source = _entry_context(changed, inning=8, margin=1, suffix='changed')

        build_entry_band_usage_evidence(PRODUCT_DATE, sync_run_id=run.id)
        missing_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(missing.mlb_game_pk))
        unknown_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(unknown.mlb_game_pk))
        conflict_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(conflict.mlb_game_pk))
        changed_row = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(changed.mlb_game_pk))
        source.computation_trace = {'margin_arithmetic': {'margin': 4}}
        marked = mark_source_evidence_supersession_for_entry_band_usage(source, sync_run_id=run.id, batch_size=100)
        rebuilt = rebuild_marked_entry_band_usage_evidence(sync_run_id=run.id)
        changed_after = db.session.get(EvidenceObject, changed_row.id)

    assert missing_row.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert REASON_ENTRY_CONTEXT_UNAVAILABLE in missing_row.reason_codes
    assert REASON_ENTRY_CONTEXT_UNAVAILABLE in unknown_row.reason_codes
    assert REASON_ENTRY_CONTEXT_INCOHERENT in conflict_row.reason_codes
    assert changed_row.id in marked['evidence_ids']
    assert marked['marked_count'] <= 100
    assert rebuilt['objects_rebuilt'] >= 1
    assert changed_after.recompute_status == EvidenceObject.RECOMPUTE_CURRENT
    assert changed_after.computation_trace['band_cell'] == 'late_four_plus'
    assert changed_after.computation_trace['superseded_prior']['rendered_claim']


def test_finish_context_unknown_legacy_caveat_and_contradiction_dead_letter(app):
    with app.app_context():
        pitcher = _pitcher()
        legacy = _log(pitcher, suffix=20, games_finished=None, batters_faced=None)
        contradiction = _log(pitcher, suffix=21, games_finished=1, save=True, blown_save=True)

        build_entry_band_usage_evidence(PRODUCT_DATE)
        legacy_row = _row(APPEARANCE_FINISH_CONTEXT_RULE_ID, subject_contains=str(legacy.mlb_game_pk))
        conflict_row = _row(APPEARANCE_FINISH_CONTEXT_RULE_ID, subject_contains=str(contradiction.mlb_game_pk))
        failure = SyncFailure.query.filter_by(entity_type=FINISH_CONTEXT_CONTRADICTION_ENTITY_TYPE).one()

    assert legacy_row.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert REASON_GAMES_FINISHED_UNKNOWN in legacy_row.reason_codes
    assert REASON_LEGACY_ROW_DEFAULT_FALSE_CAVEAT in legacy_row.reason_codes
    assert conflict_row.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert failure.payload['game_log_id'] == contradiction.id


def test_sample_floor_n4_withheld_n5_emits_and_zero_counts_emit(app):
    with app.app_context():
        small_pitcher = _pitcher(seed=30)
        full_pitcher = _pitcher(seed=31)
        _window_fixture(small_pitcher, 4, start_suffix=30)
        rows = _window_fixture(full_pitcher, 5, finished_count=0, start_suffix=40)
        for row in rows[:2]:
            _multi_inning_object(row)

        build_entry_band_usage_evidence(PRODUCT_DATE)
        withheld = [
            row for row in _rows(PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID)
            if row.subject_id == str(small_pitcher.id)
        ][0]
        emitted = [
            row for row in _rows(PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID)
            if row.subject_id == str(full_pitcher.id)
        ][0]

    assert withheld.completeness_state == EvidenceObject.COMPLETENESS_WITHHELD
    assert REASON_INSUFFICIENT_SAMPLE in withheld.reason_codes
    assert 'Finished 0 of 5 relief appearances' in emitted.rendered_claim
    assert emitted.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE


def test_coverage_gap_lower_bound_grammar_and_days_cited(app):
    with app.app_context():
        pitcher = _pitcher(seed=40)
        _seed_complete_coverage()
        gap_day = PRODUCT_DATE - timedelta(days=2)
        _incomplete_slate(gap_day)
        for index in range(5):
            day = PRODUCT_DATE - timedelta(days=4 - index)
            row = _log(pitcher, day, suffix=60 + index, games_finished=1)
            _entry_context(row, inning=8, margin=1)

        build_entry_band_usage_evidence(PRODUCT_DATE)
        row = [
            item for item in _rows(PITCHER_SAVE_HOLD_WINDOW_RULE_ID)
            if item.subject_id == str(pitcher.id) and 'save-hold-7' in item.subject_key
        ][0]
        coverage_citations = [citation for citation in row.citations if citation.source_family == 'slate_coverage']

    assert row.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
    assert row.rendered_claim.startswith('At least 7-day')
    assert REASON_INCOMPLETE_SLATE_DAY in row.reason_codes
    assert any(citation.source_pk == gap_day.isoformat() for citation in coverage_citations)


def test_unknown_band_order_and_multi_inning_items_degrade_observations(app):
    with app.app_context():
        pitcher = _pitcher(seed=50)
        rows = _window_fixture(pitcher, 5, finished_count=5, start_suffix=70)
        _multi_inning_object(rows[0])
        _multi_inning_object(rows[1], state=EvidenceObject.COMPLETENESS_UNKNOWN, suffix='unknown')
        entry_to_remove = EvidenceObject.query.filter_by(
            rule_id='appearance_entry_context',
            subject_id=f'{rows[2].pitcher_id}:{rows[2].mlb_game_pk}',
        ).one()
        order_to_remove = EvidenceObject.query.filter_by(
            rule_id='appearance_order_in_game',
            subject_id=f'{rows[3].pitcher_id}:{rows[3].mlb_game_pk}',
        ).one()
        db.session.delete(entry_to_remove)
        db.session.delete(order_to_remove)
        db.session.flush()

        build_entry_band_usage_evidence(PRODUCT_DATE)
        finish = _row(PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID)
        distribution = _row(PITCHER_ENTRY_BAND_DISTRIBUTION_RULE_ID)
        multi = _row(PITCHER_MULTI_INNING_USAGE_OBSERVATION_RULE_ID)
        first = _row(PITCHER_FIRST_RELIEVER_USAGE_OBSERVATION_RULE_ID)

    assert REASON_BAND_UNKNOWN_IN_WINDOW in finish.reason_codes
    assert REASON_BAND_UNKNOWN_IN_WINDOW in distribution.reason_codes
    assert REASON_MULTI_INNING_UNKNOWN_IN_WINDOW in multi.reason_codes
    assert REASON_ORDER_UNKNOWN_IN_WINDOW in first.reason_codes
    assert finish.rendered_claim.startswith('At least')
    assert multi.rendered_claim.startswith('At least')


def test_uncitable_denominator_blocks_observation_emission(app, monkeypatch):
    import services.entry_band_usage_evidence as service

    with app.app_context():
        pitcher = _pitcher(seed=60)
        _window_fixture(pitcher, 5, start_suffix=90)
        monkeypatch.setattr(service, '_denominator_citable', lambda rows: False)

        build_entry_band_usage_evidence(PRODUCT_DATE)

    assert not _rows(PITCHER_FINISH_USAGE_OBSERVATION_RULE_ID)


def test_no_pbp_model_imports_public_isolation_and_rendered_claim_sweep(app):
    service_path = REPO_ROOT / 'backend/services/entry_band_usage_evidence.py'
    service_text = service_path.read_text(encoding='utf-8')
    blocked_service_imports = (
        'models.play_by_play_foundation',
        'GamePlayByPlayEvent',
        'PlayByPlayProcessedGame',
        'services.play_by_play_foundation',
    )
    for needle in blocked_service_imports:
        assert needle not in service_text

    public_paths = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    )
    blocked_public = (
        'services.entry_band_usage_evidence',
        'entry_band_usage_evidence',
        *ENTRY_BAND_USAGE_RULE_IDS,
    )
    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for needle in blocked_public:
            assert needle not in text


def test_idempotency_bounded_recompute_sync_stage_and_public_payload_shape(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        before = set(sync_metadata.build_sync_status_payload().keys())
        pitcher = _pitcher(seed=70)
        target = _log(pitcher, suffix=101)
        unrelated_pitcher = _pitcher(seed=71)
        unrelated = _log(unrelated_pitcher, suffix=102)
        _entry_context(target, inning=8, margin=1)
        _entry_context(unrelated, inning=8, margin=1)
        build_entry_band_usage_evidence(PRODUCT_DATE, sync_run_id=run.id)
        first_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(ENTRY_BAND_USAGE_RULE_IDS)).count()
        build_entry_band_usage_evidence(PRODUCT_DATE, sync_run_id=run.id)
        second_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(ENTRY_BAND_USAGE_RULE_IDS)).count()
        target_band = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(target.mlb_game_pk))
        unrelated_band = _row(APPEARANCE_ENTRY_BAND_RULE_ID, subject_contains=str(unrelated.mlb_game_pk))
        target_band_id = target_band.id
        unrelated_updated_at = unrelated_band.updated_at
        marked = mark_game_log_correction_for_entry_band_usage(target, sync_run_id=run.id, batch_size=100)
        rebuilt = rebuild_marked_entry_band_usage_evidence(sync_run_id=run.id)
        target_after = db.session.get(EvidenceObject, target_band.id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_band.id)
        target_after_status = target_after.recompute_status
        target_after_prior_claim = target_after.computation_trace['superseded_prior']['rendered_claim']
        unrelated_after_updated_at = unrelated_after.updated_at

        result = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        after = set(sync_metadata.build_sync_status_payload().keys())

        def boom(*args, **kwargs):
            raise RuntimeError('entry band stage exploded')

        import services.entry_band_usage_evidence as entry_service
        monkeypatch.setattr(entry_service, 'build_entry_band_usage_evidence', boom)
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
            entry_service,
            'build_entry_band_usage_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())

    assert first_count == second_count
    assert target_band_id in marked['evidence_ids']
    assert marked['marked_count'] <= 100
    assert rebuilt['objects_rebuilt'] >= 1
    assert target_after_status == EvidenceObject.RECOMPUTE_CURRENT
    assert target_after_prior_claim
    assert unrelated_after_updated_at == unrelated_updated_at
    assert result['status'] == 'built'
    assert result['entry_band_usage_builds'][0]['objects_built'] > 0
    assert after == before
    assert failed['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'

    for forbidden in (
        'pres' + 'sure',
        'lever' + 'age',
        'high-' + 'lever' + 'age',
        'stress',
        'closer',
        'setup man',
        'fireman',
        'stopper',
        'long man',
        'bullpen ace',
        'ninth-inning guy',
        'trusted',
        'go-to',
        'leans on',
        'prefers',
        "manager's choice",
        'dominant',
        'reliable',
        'shaky',
        ' will ',
        ' should ',
        ' expect ',
        ' likely ',
        ' available ',
        ' ready ',
        'percentage',
        ' rate ',
        ' score ',
        ' grade ',
        ' rank ',
        '-like role',
    ):
        assert forbidden not in f' {rendered} '


def test_entry_band_usage_build_batches_evidence_upserts(app, monkeypatch):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(seed=80)
        log = _log(pitcher, suffix=180)
        _entry_context(log, inning=8, margin=1)

        monkeypatch.setattr(
            entry_service,
            '_upsert_evidence',
            lambda *_args, **_kwargs: pytest.fail('per-object entry-band upsert was used'),
        )

        result = build_entry_band_usage_evidence(PRODUCT_DATE, sync_run_id=run.id)

    assert result['status'] == 'built'
    assert result['objects_built'] > 0


def test_no_disallowed_rule_families_or_reliever_partition_registered():
    registry, _ = register_entry_band_usage_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    registered = {rule.rule_id for rule in registry.all_rules()}

    assert registered == set(ENTRY_BAND_USAGE_RULE_IDS)
    assert not any('handedness' in rule_id for rule_id in registered)
    assert not any('opener' in rule_id or 'bulk' in rule_id for rule_id in registered)
    assert 'team_active_reliever_count' not in registered
