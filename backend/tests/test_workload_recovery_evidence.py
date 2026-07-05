from datetime import date, datetime, timedelta
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.prospect  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services import sync_metadata
import services.workload_recovery_evidence as workload_service
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from services.workload_recovery_evidence import (
    HIGH_PITCH_THRESHOLD,
    LOOKBACK_DAYS,
    RULE_VERSION,
    WINDOW_DAYS,
    WORKLOAD_RULE_IDS,
    _register_workload_rule,
    _register_workload_template,
    build_workload_recovery_evidence,
    mark_game_log_correction_for_workload_recovery,
    rebuild_marked_workload_recovery_evidence,
    register_workload_recovery_rules,
    workload_rule_definitions,
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
        job_name='phase0d_workload_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(seed=1, name='Workload Pitcher'):
    pitcher = Pitcher(
        mlb_id=700000 + seed,
        full_name=name,
        team_id=seed,
        team_abbreviation=f'T{seed}',
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


def _incomplete_slate(day):
    game_pk = _game_pk(day, 8)
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


def _unresolved_resumed_slate(day):
    game_pk = _game_pk(day, 9)
    db.session.add_all([
        ScheduledGame(
            team_id=21,
            opponent_team_id=22,
            game_pk=game_pk,
            game_date=day,
            home_away='home',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=12345,
        ),
        ScheduledGame(
            team_id=22,
            opponent_team_id=21,
            game_pk=game_pk,
            game_date=day,
            home_away='away',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=12345,
        ),
    ])
    db.session.flush()
    return game_pk


def _seed_complete_coverage(end=PRODUCT_DATE, days=LOOKBACK_DAYS):
    start = end - timedelta(days=days - 1)
    for offset in range(days):
        _complete_slate(start + timedelta(days=offset))


def _log(
    pitcher,
    day,
    *,
    suffix=0,
    pitches=12,
    outs=3,
    batters_faced=4,
    games_started=0,
):
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=_game_pk(day, suffix),
        game_date=day,
        game_type='R',
        opponent='Opponent',
        opponent_abbreviation='OPP',
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        strikes=8,
        hits_allowed=0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        batters_faced=batters_faced,
        last_stat_correction_sync_run_id=None,
    )
    db.session.add(log)
    db.session.flush()
    return log


def _rows(rule_id):
    return EvidenceObject.query.filter_by(rule_id=rule_id).order_by(EvidenceObject.subject_key).all()


def _row(rule_id, text=None, subject_contains=None):
    query = EvidenceObject.query.filter_by(rule_id=rule_id)
    if text:
        query = query.filter(EvidenceObject.rendered_claim.contains(text))
    if subject_contains:
        query = query.filter(EvidenceObject.subject_key.contains(subject_contains))
    return query.one()


def test_registration_lint_and_branch_guard():
    registry, templates = register_workload_recovery_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )

    rules = registry.all_rules()
    assert [rule.rule_id for rule in rules] == sorted(WORKLOAD_RULE_IDS)
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert len(templates._templates) == 12
    definitions = workload_rule_definitions()
    for rule in rules:
        definition = definitions[rule.rule_id]
        for value in rule.thresholds.values():
            assert str(value) in definition

    with pytest.raises(EvidenceLanguageError):
        _register_workload_template(
            ClaimTemplateRegistry(),
            ClaimTemplate(
                template_id='bad_workload_claim',
                template_version=1,
                template_text='Pitcher is available after the appearance.',
            ),
        )

    with pytest.raises(EvidenceLanguageError):
        _register_workload_template(
            ClaimTemplateRegistry(),
            ClaimTemplate(
                template_id='bad_workload_claim_2',
                template_version=1,
                template_text='Pitcher is fatigued after the appearance.',
            ),
        )

    with pytest.raises(EvidenceRuleError):
        _register_workload_rule(
            EvidenceRuleRegistry(),
            EvidenceRule(
                rule_id='bad_public_workload_rule',
                rule_version=1,
                evidence_type='workload_recovery_fact',
                plain_language_definition='Records a test-only workload fact.',
                required_input_families=('game_logs', 'slate_coverage'),
                required_cited_fields=('slate_coverage.slate_date',),
                posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
            ),
        )


def test_window_math_doubleheaders_boundaries_and_back_to_back(app):
    with app.app_context():
        _seed_complete_coverage()
        run = _sync_run()
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, suffix=1, pitches=10)
        _log(pitcher, PRODUCT_DATE, suffix=2, pitches=11)
        _log(pitcher, PRODUCT_DATE - timedelta(days=1), suffix=3, pitches=12)
        _log(pitcher, PRODUCT_DATE - timedelta(days=3), suffix=4, pitches=13)
        _log(pitcher, PRODUCT_DATE - timedelta(days=6), suffix=5, pitches=14)

        result = build_workload_recovery_evidence(PRODUCT_DATE, sync_run_id=run.id)

        counts = {
            row.subject_key.rsplit(':', 1)[-1]: row.rendered_claim
            for row in _rows('workload_window_appearances')
        }
        back_to_back = _row('usage_back_to_back')

    assert result['objects_built'] > 0
    assert 'recorded 3 final appearances across 2 distinct appearance days' in counts['window-3']
    assert 'recorded 4 final appearances across 3 distinct appearance days' in counts['window-5']
    assert 'recorded 5 final appearances across 4 distinct appearance days' in counts['window-7']
    assert 'recorded 5 final appearances across 4 distinct appearance days' in counts['window-14']
    assert back_to_back.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE


def test_same_day_doubleheader_pair_does_not_satisfy_back_to_back(app):
    with app.app_context():
        _seed_complete_coverage()
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, suffix=1)
        _log(pitcher, PRODUCT_DATE, suffix=2)

        build_workload_recovery_evidence(PRODUCT_DATE)

    assert _rows('usage_back_to_back') == []


def test_suspended_resumed_gap_makes_pattern_unknown(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        unresolved_day = PRODUCT_DATE - timedelta(days=2)
        _unresolved_resumed_slate(unresolved_day)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE)
        _log(pitcher, PRODUCT_DATE - timedelta(days=1), suffix=1)
        _log(pitcher, unresolved_day, suffix=2)

        build_workload_recovery_evidence(PRODUCT_DATE)
        row = _row('usage_three_in_four')

    assert row.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert row.reason_codes == ['ambiguous_resumed_game_in_window']


def test_incomplete_windows_null_arithmetic_role_unknown_and_rest_gap(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        incomplete_day = PRODUCT_DATE - timedelta(days=1)
        _incomplete_slate(incomplete_day)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, pitches=None, batters_faced=None, games_started=None)
        _log(pitcher, incomplete_day, suffix=1, pitches=9, batters_faced=3)

        build_workload_recovery_evidence(PRODUCT_DATE)
        appearance_count = _row(
            'workload_window_appearances',
            'At least',
            subject_contains='window-3',
        )
        pitch_total = _row(
            'workload_window_pitches',
            'Pitches total is unknown',
            subject_contains='window-3',
        )
        bf_total = _row(
            'workload_window_batters_faced',
            'Batters Faced total is unknown',
            subject_contains='window-3',
        )
        role_unknown = _row('outing_high_pitch', 'games-started value')

    assert appearance_count.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
    assert 'incomplete_slate_day_in_window' in appearance_count.reason_codes
    assert pitch_total.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert 'incomplete_slate_day_in_window' in pitch_total.reason_codes
    assert bf_total.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert role_unknown.reason_codes == ['appearance_role_unknown']


def test_null_pitch_and_batters_faced_totals_keep_known_subtotals(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, pitches=None, batters_faced=None)
        _log(pitcher, PRODUCT_DATE - timedelta(days=1), suffix=1, pitches=9, batters_faced=3)

        build_workload_recovery_evidence(PRODUCT_DATE)
        pitch_total = _row(
            'workload_window_pitches',
            'known subtotal is 9',
            subject_contains='window-3',
        )
        bf_total = _row(
            'workload_window_batters_faced',
            'known subtotal is 3',
            subject_contains='window-3',
        )

    assert pitch_total.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert pitch_total.reason_codes == ['unknown_pitch_count_in_window']
    assert pitch_total.computation_trace['known_count'] == 1
    assert pitch_total.computation_trace['known_subtotal'] == 9
    assert 'recorded 9 pitches' not in pitch_total.rendered_claim
    assert bf_total.reason_codes == ['unknown_batters_faced_in_window']


def test_rest_coverage_gap_and_no_recent_appearance_claim(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        gap_day = PRODUCT_DATE - timedelta(days=1)
        _incomplete_slate(gap_day)
        pitcher = _pitcher(seed=1)
        _log(pitcher, PRODUCT_DATE)
        _log(pitcher, PRODUCT_DATE - timedelta(days=2), suffix=1)
        old_pitcher = _pitcher(seed=2)
        _log(old_pitcher, PRODUCT_DATE - timedelta(days=45), suffix=2)

        build_workload_recovery_evidence(PRODUCT_DATE)
        short_rest = _row('appearance_short_rest', 'rest-window coverage')
        no_recent = _row('workload_last_final_appearance', 'No final appearance')

    assert short_rest.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert short_rest.reason_codes == ['rest_window_coverage_gap']
    assert no_recent.reason_codes == ['no_recent_appearance_in_lookback']
    assert any(citation.source_family == 'slate_coverage' for citation in no_recent.citations)


def test_zero_windows_emit_counts_but_no_vacuous_sums(app):
    with app.app_context():
        _seed_complete_coverage(days=LOOKBACK_DAYS)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE - timedelta(days=20), suffix=1)

        build_workload_recovery_evidence(PRODUCT_DATE)
        count_rows = _rows('workload_window_appearances')

    assert len(count_rows) == len(WINDOW_DAYS)
    assert all('recorded 0 final appearances' in row.rendered_claim for row in count_rows)
    assert _rows('workload_window_pitches') == []
    assert _rows('workload_window_outs') == []
    assert _rows('workload_window_batters_faced') == []


def test_zero_current_log_build_is_batched_and_active_bounded(app, monkeypatch):
    with app.app_context():
        _seed_complete_coverage(days=LOOKBACK_DAYS)
        active_old = _pitcher(seed=1, name='Active Historical Pitcher')
        inactive_old = _pitcher(seed=2, name='Inactive Historical Pitcher')
        inactive_old.active = False
        recent_inactive = _pitcher(seed=3, name='Recent Inactive Pitcher')
        recent_inactive.active = False
        _log(active_old, PRODUCT_DATE - timedelta(days=45), suffix=1)
        _log(inactive_old, PRODUCT_DATE - timedelta(days=45), suffix=2)
        _log(recent_inactive, PRODUCT_DATE - timedelta(days=20), suffix=3)
        db.session.flush()

        monkeypatch.setattr(
            workload_service,
            '_pitcher_rows',
            lambda *_args, **_kwargs: pytest.fail('per-pitcher workload row query was used'),
        )

        result = build_workload_recovery_evidence(PRODUCT_DATE)
        no_recent_rows = [
            row for row in _rows('workload_last_final_appearance')
            if 'No final appearance' in row.rendered_claim
        ]

    assert result['pitchers_considered'] == 2
    assert any(row.subject_id == str(active_old.id) for row in no_recent_rows)
    assert not any(row.subject_id == str(inactive_old.id) for row in no_recent_rows)


def test_met_and_false_flag_emission_policy(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, pitches=HIGH_PITCH_THRESHOLD, outs=4)
        _log(pitcher, PRODUCT_DATE - timedelta(days=1), suffix=1)
        _log(pitcher, PRODUCT_DATE - timedelta(days=2), suffix=2)
        _log(pitcher, PRODUCT_DATE - timedelta(days=4), suffix=4)

        build_workload_recovery_evidence(PRODUCT_DATE)

        assert _row('outing_high_pitch').completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert _row('outing_multi_inning').completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert _row('usage_three_in_four').completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert _row('usage_four_in_six').completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert _row('appearance_short_rest').completeness_state == EvidenceObject.COMPLETENESS_COMPLETE


def test_provably_false_flags_emit_nothing(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE, pitches=12, outs=3)

        build_workload_recovery_evidence(PRODUCT_DATE)

    for rule_id in (
        'usage_back_to_back',
        'usage_three_in_four',
        'usage_four_in_six',
        'outing_multi_inning',
        'outing_high_pitch',
        'appearance_short_rest',
    ):
        assert _rows(rule_id) == []


def test_citation_integrity_and_correction_provenance(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        run = _sync_run()
        pitcher = _pitcher()
        log = _log(pitcher, PRODUCT_DATE, pitches=18)
        log.stat_correction_count = 2
        log.last_stat_correction_at = datetime(2026, 7, 4, 13, 0, 0)
        log.last_stat_correction_source = 'test_correction'
        log.last_stat_correction_sync_run_id = run.id
        db.session.flush()

        build_workload_recovery_evidence(PRODUCT_DATE, sync_run_id=run.id)
        row = _row('workload_window_pitches', '18 pitches', subject_contains='window-3')
        game_citations = [c for c in row.citations if c.source_family == 'game_logs']
        coverage_citations = [c for c in row.citations if c.source_family == 'slate_coverage']

    assert game_citations
    assert game_citations[0].source_pk == str(log.id)
    assert 'pitches_thrown' in game_citations[0].source_field_names
    assert game_citations[0].provenance['sync_run_id'] == run.id
    assert game_citations[0].provenance['stat_correction_count'] == 2
    assert coverage_citations
    assert coverage_citations[0].citation_role == 'window_validity'


def test_recompute_refreshes_cited_evidence_and_leaves_unrelated_rows(app):
    with app.app_context():
        _seed_complete_coverage(days=10)
        run = _sync_run()
        pitcher = _pitcher(seed=1)
        other_pitcher = _pitcher(seed=2)
        corrected_log = _log(pitcher, PRODUCT_DATE, pitches=18)
        _log(other_pitcher, PRODUCT_DATE, suffix=1, pitches=7)
        build_workload_recovery_evidence(PRODUCT_DATE, sync_run_id=run.id)
        target_before = _row(
            'workload_window_pitches',
            '18 pitches',
            subject_contains='window-3',
        )
        unrelated_before = _row(
            'workload_window_pitches',
            '7 pitches',
            subject_contains='window-3',
        )
        target_id = target_before.id
        unrelated_updated_at = unrelated_before.updated_at

        corrected_log.pitches_thrown = 31
        corrected_log.stat_correction_count = 1
        corrected_log.last_stat_correction_sync_run_id = run.id
        marked = mark_game_log_correction_for_workload_recovery(corrected_log, sync_run_id=run.id)
        rebuilt = rebuild_marked_workload_recovery_evidence(sync_run_id=run.id)
        target_after = db.session.get(EvidenceObject, target_id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_before.id)

    assert marked['marked_count'] >= 1
    assert rebuilt['objects_rebuilt'] >= 1
    assert target_after.recompute_status == EvidenceObject.RECOMPUTE_CURRENT
    assert '31 pitches' in target_after.rendered_claim
    assert target_after.computation_trace['superseded_prior']['rendered_claim']
    assert unrelated_after.rendered_claim == unrelated_before.rendered_claim
    assert unrelated_after.updated_at == unrelated_updated_at


def test_sync_stage_fail_soft_dead_letter_and_kill_switch(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()

        def boom(*args, **kwargs):
            raise RuntimeError('stage exploded')

        import services.workload_recovery_evidence as workload_service
        monkeypatch.setattr(workload_service, 'build_workload_recovery_evidence', boom)
        with caplog.at_level(logging.WARNING, logger='baseballos.daily_sync'):
            result = sync_service._safe_build_workload_recovery_evidence_stage(
                [PRODUCT_DATE],
                sync_run_id=run.id,
                source='test',
                run_logger=logging.getLogger('baseballos.daily_sync'),
            )
        failure = SyncFailure.query.one()

        monkeypatch.setenv('PHASE0D_EVIDENCE_BUILD', 'false')
        monkeypatch.setattr(
            workload_service,
            'build_workload_recovery_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )

    assert result['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'


def test_sync_stage_logs_phase0d_substep_counts_and_runs_required_work(app, caplog):
    with app.app_context():
        _seed_complete_coverage(days=LOOKBACK_DAYS)
        run = _sync_run()
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE)

        with caplog.at_level(logging.INFO, logger='baseballos.daily_sync'):
            result = sync_service._safe_build_workload_recovery_evidence_stage(
                [PRODUCT_DATE],
                sync_run_id=run.id,
                source='test',
                run_logger=logging.getLogger('baseballos.daily_sync'),
            )
        messages = [record.getMessage() for record in caplog.records]

    assert result['status'] == 'built'
    assert result['builds'][0]['objects_built'] > 0
    assert any(
        'Phase 0D evidence step starting: '
        f'step=workload_recovery_build:{PRODUCT_DATE.isoformat()}' in message
        for message in messages
    )
    assert any(
        'Phase 0D evidence step completed: '
        f'step=workload_recovery_build:{PRODUCT_DATE.isoformat()}' in message
        and 'objects_built=' in message
        and 'elapsed_ms=' in message
        for message in messages
    )


def test_public_sync_status_payload_shape_is_unchanged(app):
    with app.app_context():
        before = set(sync_metadata.build_sync_status_payload().keys())
        _seed_complete_coverage(days=10)
        pitcher = _pitcher()
        _log(pitcher, PRODUCT_DATE)
        build_workload_recovery_evidence(PRODUCT_DATE)
        after = set(sync_metadata.build_sync_status_payload().keys())

    assert after == before


def test_public_surface_isolation_static_sweep():
    public_paths = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    )
    blocked = (
        'services.workload_recovery_evidence',
        'workload_recovery_evidence',
        'workload_last_final_appearance',
        'workload_window_pitches',
        'evidence_objects',
        'evidence_citations',
    )

    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for reference in blocked:
            assert reference not in text, f'{reference} leaked into {path}'
