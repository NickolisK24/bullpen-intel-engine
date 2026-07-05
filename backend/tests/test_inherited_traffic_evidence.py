from datetime import date, datetime
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services import sync_metadata
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from services.inherited_traffic_evidence import (
    AUTOMATIC_RUNNER_LIMITATION,
    CLEAN_RULE_ID,
    CONTRADICTION_ENTITY_TYPE,
    ENTRY_CORROBORATION_RULE_ID,
    HBP_ROE_LIMITATION,
    INHERITED_RUNNERS_RULE_ID,
    INHERITED_RUNNERS_SCORED_RULE_ID,
    INHERITED_TRAFFIC_OUTCOME_RULE_ID,
    INHERITED_TRAFFIC_RULE_IDS,
    LEGACY_TRAFFIC_LIMITATION,
    REASON_APPEARANCE_ROLE_UNKNOWN,
    REASON_ENTRY_CONTEXT_INCOHERENT,
    REASON_ENTRY_CONTEXT_UNAVAILABLE,
    REASON_EXTRAS_AUTOMATIC_RUNNER,
    REASON_INHERITED_EXCEEDS_CONTEXT,
    REASON_INHERITED_FIELDS_UNKNOWN,
    REASON_INHERITED_SCORED_UNKNOWN,
    REASON_LEGACY_ROW_PRE_EXPANSION,
    REASON_OUTING_COMPONENT_UNKNOWN,
    RULE_VERSION,
    TRAFFIC_RULE_ID,
    UNKNOWN_RULE_ID,
    _register_inherited_traffic_rule,
    _register_inherited_traffic_template,
    build_inherited_traffic_evidence,
    inherited_traffic_rule_definitions,
    mark_entry_context_supersession_for_inherited_traffic,
    mark_game_log_correction_for_inherited_traffic,
    rebuild_marked_inherited_traffic_evidence,
    register_inherited_traffic_rules,
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
        job_name='phase0d_inherited_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(seed=1):
    pitcher = Pitcher(
        mlb_id=900000 + seed,
        full_name=f'Inherited Pitcher {seed}',
        team_id=seed,
        team_abbreviation=f'T{seed}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _schedule(game_pk, *, resumed=False):
    db.session.add_all([
        ScheduledGame(
            team_id=1,
            opponent_team_id=2,
            game_pk=game_pk,
            game_date=PRODUCT_DATE,
            home_away='home',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=111 if resumed else None,
        ),
        ScheduledGame(
            team_id=2,
            opponent_team_id=1,
            game_pk=game_pk,
            game_date=PRODUCT_DATE,
            home_away='away',
            status_state=ScheduledGame.STATE_FINAL,
            status_code='F',
            game_type='R',
            resumed_from_game_pk=111 if resumed else None,
        ),
    ])
    db.session.flush()


def _log(
    *,
    seed=1,
    pitcher=None,
    game_pk=10001,
    games_started=0,
    inherited_runners=0,
    inherited_runners_scored=0,
    hits=0,
    walks=0,
    runs=0,
    batters_faced=3,
    outs=3,
    resumed=False,
):
    _schedule(game_pk, resumed=resumed)
    pitcher = pitcher or _pitcher(seed)
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=PRODUCT_DATE,
        game_type='R',
        opponent='Opponent',
        opponent_abbreviation='OPP',
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=12,
        strikes=8,
        hits_allowed=hits,
        runs_allowed=runs,
        earned_runs=runs,
        walks=walks,
        strikeouts=1,
        home_runs_allowed=0,
        batters_faced=batters_faced,
        inherited_runners=inherited_runners,
        inherited_runners_scored=inherited_runners_scored,
    )
    db.session.add(log)
    db.session.flush()
    nullable_overrides = {
        'hits_allowed': hits,
        'walks': walks,
        'runs_allowed': runs,
        'earned_runs': runs,
    }
    for field, value in nullable_overrides.items():
        if value is None:
            setattr(log, field, None)
    db.session.flush()
    return log


def _entry_context(
    log,
    *,
    claim='Entered in the top of the 8 with 1 out, team leading 4-3 (margin +1); mid-inning entry; runners on base at entry unknown.',
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    suffix='entry',
):
    row = EvidenceObject(
        evidence_key=f'entry-context-{log.id}-{suffix}',
        evidence_type='appearance_context_fact',
        subject_type='pitcher_appearance',
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
        subject_key=f'pitcher_appearance:{log.pitcher_id}:{log.mlb_game_pk}:{suffix}',
        product_date=log.game_date,
        claim_template_id='appearance_entry_context_claim',
        rendered_claim=claim,
        rule_id='appearance_entry_context',
        rule_version=1,
        rule_definition_hash='entry-context-test-hash',
        typed_cited_inputs=[],
        computation_trace={'entry_fixture': suffix},
        completeness_state=state,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0d:appearance_context_evidence',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    db.session.add(row)
    db.session.flush()
    return row


def _rows(rule_id):
    return EvidenceObject.query.filter_by(rule_id=rule_id).order_by(EvidenceObject.id).all()


def _row(rule_id, log):
    return EvidenceObject.query.filter_by(
        rule_id=rule_id,
        subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}',
    ).one()


def test_registration_guards_and_no_bequeathed_rule():
    registry, templates = register_inherited_traffic_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    rules = registry.all_rules()

    assert [rule.rule_id for rule in rules] == sorted(INHERITED_TRAFFIC_RULE_IDS)
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert registry.get(UNKNOWN_RULE_ID).allowed_completeness == (
        EvidenceObject.COMPLETENESS_UNKNOWN,
    )
    assert len(templates._templates) == 7
    assert 'bequeath' not in ' '.join(INHERITED_TRAFFIC_RULE_IDS)
    assert 'bequeath' not in ' '.join(inherited_traffic_rule_definitions())

    with pytest.raises(EvidenceRuleError):
        _register_inherited_traffic_rule(
            EvidenceRuleRegistry(),
            EvidenceRule(
                rule_id='bad_public_inherited_rule',
                rule_version=1,
                evidence_type='inherited_traffic_fact',
                plain_language_definition='Records a test-only inherited fact.',
                required_input_families=('game_logs',),
                required_cited_fields=('game_logs.inherited_runners',),
                posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
            ),
        )
    for text in (
        'shutdown inning',
        'high-pressure escape',
        'dominant inning',
        'shaky entry',
        'available arm',
        'fatigued arm',
    ):
        with pytest.raises(EvidenceLanguageError):
            _register_inherited_traffic_template(
                ClaimTemplateRegistry(),
                ClaimTemplate(
                    template_id=f'bad_{text.split()[0]}',
                    template_version=1,
                    template_text=text,
                ),
            )


def test_clean_truth_table_unknowns_and_limitations(app):
    with app.app_context():
        clean = _log(seed=1, game_pk=11001)
        inherited_clean = _log(seed=2, game_pk=11002, inherited_runners=2, inherited_runners_scored=0)
        scored = _log(seed=3, game_pk=11003, inherited_runners=2, inherited_runners_scored=1)
        legacy = _log(seed=4, game_pk=11004, batters_faced=None)
        null_rows = [
            _log(seed=10, game_pk=11010, hits=None),
            _log(seed=11, game_pk=11011, walks=None),
            _log(seed=12, game_pk=11012, runs=None),
            _log(seed=13, game_pk=11013, inherited_runners=None),
            _log(seed=14, game_pk=11014, inherited_runners=1, inherited_runners_scored=None),
        ]

        build_inherited_traffic_evidence(PRODUCT_DATE)
        clean_row = _row(CLEAN_RULE_ID, clean)
        inherited_clean_row = _row(CLEAN_RULE_ID, inherited_clean)
        legacy_unknown = _row(UNKNOWN_RULE_ID, legacy)

        assert clean_row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert HBP_ROE_LIMITATION in clean_row.limitations
        assert inherited_clean_row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert _rows(CLEAN_RULE_ID)
        assert EvidenceObject.query.filter_by(rule_id=CLEAN_RULE_ID, subject_id=f'{scored.pitcher_id}:{scored.mlb_game_pk}').first() is None
        assert legacy_unknown.reason_codes == [REASON_LEGACY_ROW_PRE_EXPANSION]
        for log in null_rows[:3]:
            assert REASON_OUTING_COMPONENT_UNKNOWN in _row(UNKNOWN_RULE_ID, log).reason_codes
            assert EvidenceObject.query.filter_by(rule_id=CLEAN_RULE_ID, subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}').first() is None
        assert REASON_INHERITED_FIELDS_UNKNOWN in _row(UNKNOWN_RULE_ID, null_rows[3]).reason_codes
        assert REASON_INHERITED_SCORED_UNKNOWN in _row(UNKNOWN_RULE_ID, null_rows[4]).reason_codes


def test_traffic_truth_table_boundaries_and_legacy_caveat(app):
    with app.app_context():
        no_flag = [
            _log(seed=20, game_pk=12000, hits=0, walks=0),
            _log(seed=21, game_pk=12001, hits=1, walks=0),
            _log(seed=22, game_pk=12002, hits=1, walks=1),
        ]
        boundary = _log(seed=23, game_pk=12003, hits=2, walks=1, outs=2)
        three_hits = _log(seed=24, game_pk=12004, hits=3, walks=0, outs=1)
        above = _log(seed=25, game_pk=12005, hits=4, walks=1, outs=4)
        legacy = _log(seed=26, game_pk=12006, hits=3, walks=0, batters_faced=None, outs=2)

        build_inherited_traffic_evidence(PRODUCT_DATE)
        boundary_row = _row(TRAFFIC_RULE_ID, boundary)
        three_hits_row = _row(TRAFFIC_RULE_ID, three_hits)
        above_row = _row(TRAFFIC_RULE_ID, above)
        legacy_row = _row(TRAFFIC_RULE_ID, legacy)

        for log in no_flag:
            assert EvidenceObject.query.filter_by(rule_id=TRAFFIC_RULE_ID, subject_id=f'{log.pitcher_id}:{log.mlb_game_pk}').first() is None
        assert 'allowed 3 baserunners (2 hits, 1 walks) across 2 outs recorded' in boundary_row.rendered_claim
        assert '3-baserunner threshold' in boundary_row.rendered_claim
        assert three_hits_row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert above_row.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert HBP_ROE_LIMITATION in boundary_row.limitations
        assert LEGACY_TRAFFIC_LIMITATION in legacy_row.limitations
        for row in (boundary_row, three_hits_row, above_row, legacy_row):
            assert EvidenceObject.query.filter_by(rule_id=CLEAN_RULE_ID, subject_id=row.subject_id).first() is None


def test_inherited_runner_rules_outcomes_and_contradictions(app):
    with app.app_context():
        zero = _log(seed=30, game_pk=13000, inherited_runners=0, inherited_runners_scored=0)
        known = _log(seed=31, game_pk=13001, inherited_runners=2, inherited_runners_scored=1)
        unknown_ir = _log(seed=32, game_pk=13002, inherited_runners=None, inherited_runners_scored=None)
        unknown_irs = _log(seed=33, game_pk=13003, inherited_runners=2, inherited_runners_scored=None)
        stranded = _log(seed=34, game_pk=13004, inherited_runners=2, inherited_runners_scored=0)
        all_scored = _log(seed=35, game_pk=13005, inherited_runners=2, inherited_runners_scored=2)
        exceeds = _log(seed=36, game_pk=13006, inherited_runners=1, inherited_runners_scored=2)
        zero_conflict = _log(seed=37, game_pk=13007, inherited_runners=0, inherited_runners_scored=1)

        build_inherited_traffic_evidence(PRODUCT_DATE)

        assert 'inherited 0 runner' in _row(INHERITED_RUNNERS_RULE_ID, zero).rendered_claim
        assert 'inherited 2 runner' in _row(INHERITED_RUNNERS_RULE_ID, known).rendered_claim
        assert _row(INHERITED_RUNNERS_RULE_ID, unknown_ir).completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert _row(INHERITED_RUNNERS_SCORED_RULE_ID, unknown_irs).reason_codes == [REASON_INHERITED_SCORED_UNKNOWN]
        assert 'allowed_some' in _row(INHERITED_TRAFFIC_OUTCOME_RULE_ID, known).rendered_claim
        assert 'stranded_all' in _row(INHERITED_TRAFFIC_OUTCOME_RULE_ID, stranded).rendered_claim
        assert 'allowed_all' in _row(INHERITED_TRAFFIC_OUTCOME_RULE_ID, all_scored).rendered_claim
        assert _row(INHERITED_RUNNERS_SCORED_RULE_ID, exceeds).completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
        assert _row(INHERITED_RUNNERS_SCORED_RULE_ID, zero_conflict).completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
        reasons = {
            (failure.payload or {}).get('reason')
            for failure in SyncFailure.query.filter_by(entity_type=CONTRADICTION_ENTITY_TYPE)
        }
        assert REASON_INHERITED_EXCEEDS_CONTEXT in reasons


def test_entry_corroboration_matrix_and_boxscore_authority(app):
    with app.app_context():
        mid = _log(seed=40, game_pk=14000, inherited_runners=2, inherited_runners_scored=1)
        _entry_context(mid)
        regulation = _log(seed=41, game_pk=14001, inherited_runners=1, inherited_runners_scored=0)
        _entry_context(
            regulation,
            claim='Entered in the bottom of the 8 with 0 outs, teams tied 0-0 (margin +0); half-inning start; runners on base at entry unknown.',
        )
        extras = _log(seed=42, game_pk=14002, inherited_runners=1, inherited_runners_scored=0)
        _entry_context(
            extras,
            claim='Entered in the top of the 10 with 0 outs, teams tied 0-0 (margin +0); half-inning start; runners on base at entry unknown.',
        )
        missing = _log(seed=43, game_pk=14003, inherited_runners=1, inherited_runners_scored=0)
        unknown = _log(seed=44, game_pk=14004, inherited_runners=1, inherited_runners_scored=0)
        _entry_context(unknown, state=EvidenceObject.COMPLETENESS_UNKNOWN)
        conflict = _log(seed=45, game_pk=14005, inherited_runners=1, inherited_runners_scored=0)
        _entry_context(conflict, state=EvidenceObject.COMPLETENESS_CONFLICT)
        duplicate = _log(seed=46, game_pk=14006, inherited_runners=1, inherited_runners_scored=0)
        _entry_context(duplicate, suffix='a')
        _entry_context(duplicate, suffix='b')

        build_inherited_traffic_evidence(PRODUCT_DATE)
        mid_row = _row(ENTRY_CORROBORATION_RULE_ID, mid)
        regulation_row = _row(ENTRY_CORROBORATION_RULE_ID, regulation)
        extras_row = _row(ENTRY_CORROBORATION_RULE_ID, extras)
        missing_row = _row(ENTRY_CORROBORATION_RULE_ID, missing)
        unknown_row = _row(ENTRY_CORROBORATION_RULE_ID, unknown)
        conflict_row = _row(ENTRY_CORROBORATION_RULE_ID, conflict)
        duplicate_row = _row(ENTRY_CORROBORATION_RULE_ID, duplicate)

        assert 'coherent' in mid_row.rendered_claim
        assert regulation_row.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
        assert regulation_row.reason_codes == [REASON_INHERITED_EXCEEDS_CONTEXT]
        assert _row(INHERITED_RUNNERS_RULE_ID, regulation).completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert 'coherent_extras_exception' in extras_row.rendered_claim
        assert REASON_EXTRAS_AUTOMATIC_RUNNER in extras_row.reason_codes
        assert AUTOMATIC_RUNNER_LIMITATION in extras_row.limitations
        assert missing_row.reason_codes == [REASON_ENTRY_CONTEXT_UNAVAILABLE]
        assert unknown_row.reason_codes == [REASON_ENTRY_CONTEXT_UNAVAILABLE]
        assert conflict_row.reason_codes == [REASON_ENTRY_CONTEXT_INCOHERENT]
        assert duplicate_row.reason_codes == [REASON_ENTRY_CONTEXT_INCOHERENT]
        payloads = [failure.payload or {} for failure in SyncFailure.query.filter_by(entity_type=CONTRADICTION_ENTITY_TYPE)]
        assert any(payload.get('reason') == REASON_INHERITED_EXCEEDS_CONTEXT for payload in payloads)
        assert any(payload.get('duplicate_current_entry_context_ids') for payload in payloads)


def test_scoping_doubleheader_resumed_and_idempotency(app):
    with app.app_context():
        starter = _log(seed=50, game_pk=15000, games_started=1)
        unknown_role = _log(seed=51, game_pk=15001, games_started=None)
        doubleheader_pitcher = _pitcher(seed=52)
        first = _log(seed=52, pitcher=doubleheader_pitcher, game_pk=15002)
        second = _log(seed=52, pitcher=doubleheader_pitcher, game_pk=15003)
        resumed = _log(seed=53, game_pk=15004, resumed=True)

        build_inherited_traffic_evidence(PRODUCT_DATE)
        first_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(INHERITED_TRAFFIC_RULE_IDS)).count()
        build_inherited_traffic_evidence(PRODUCT_DATE)
        second_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(INHERITED_TRAFFIC_RULE_IDS)).count()
        unknown_row = _row(UNKNOWN_RULE_ID, unknown_role)
        resumed_row = _row(CLEAN_RULE_ID, resumed)

        assert EvidenceObject.query.filter(EvidenceObject.subject_id.like(f'{starter.pitcher_id}:{starter.mlb_game_pk}')).count() == 0
        assert unknown_row.reason_codes == [REASON_APPEARANCE_ROLE_UNKNOWN]
        assert EvidenceObject.query.filter_by(rule_id=UNKNOWN_RULE_ID, subject_id=f'{unknown_role.pitcher_id}:{unknown_role.mlb_game_pk}').count() == 1
        assert _row(INHERITED_RUNNERS_RULE_ID, first).subject_id != _row(INHERITED_RUNNERS_RULE_ID, second).subject_id
        assert first_count == second_count
        assert any('suspended and resumed' in item for item in resumed_row.limitations)


def test_recompute_from_game_log_and_entry_context_is_bounded(app):
    with app.app_context():
        run = _sync_run()
        target = _log(seed=60, game_pk=16000, inherited_runners=2, inherited_runners_scored=0)
        entry = _entry_context(target)
        unrelated = _log(seed=61, game_pk=16001, inherited_runners=2, inherited_runners_scored=0)
        _entry_context(unrelated)
        build_inherited_traffic_evidence(PRODUCT_DATE, sync_run_id=run.id)

        target_ir = _row(INHERITED_RUNNERS_RULE_ID, target)
        target_corr = _row(ENTRY_CORROBORATION_RULE_ID, target)
        unrelated_ir = _row(INHERITED_RUNNERS_RULE_ID, unrelated)
        unrelated_updated_at = unrelated_ir.updated_at

        target.inherited_runners = 3
        marked_log = mark_game_log_correction_for_inherited_traffic(
            target,
            sync_run_id=run.id,
            batch_size=1,
        )
        rebuilt = rebuild_marked_inherited_traffic_evidence(sync_run_id=run.id)
        target_after_rebuild = db.session.get(EvidenceObject, target_ir.id)

        marked_entry = mark_entry_context_supersession_for_inherited_traffic(
            entry,
            sync_run_id=run.id,
            batch_size=10,
        )
        target_corr_after_mark = db.session.get(EvidenceObject, target_corr.id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_ir.id)

    assert marked_log['marked_count'] == 1
    assert marked_log['evidence_ids'] == [target_ir.id]
    assert rebuilt['objects_rebuilt'] == 1
    assert target_after_rebuild.recompute_status == EvidenceObject.RECOMPUTE_CURRENT
    assert target_after_rebuild.computation_trace['superseded_prior']['rendered_claim']
    assert 'inherited 3 runner' in target_after_rebuild.rendered_claim
    assert marked_entry['marked_count'] >= 1
    assert target_corr_after_mark.recompute_status == EvidenceObject.RECOMPUTE_NEEDED
    assert unrelated_after.updated_at == unrelated_updated_at


def test_sync_stage_fail_soft_kill_switch_and_public_payload_shape(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        before = set(sync_metadata.build_sync_status_payload().keys())
        _log(seed=70, game_pk=17000)
        result = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        after = set(sync_metadata.build_sync_status_payload().keys())

        def boom(*args, **kwargs):
            raise RuntimeError('inherited stage exploded')

        import services.inherited_traffic_evidence as inherited_service
        monkeypatch.setattr(inherited_service, 'build_inherited_traffic_evidence', boom)
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
            inherited_service,
            'build_inherited_traffic_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )

    assert result['status'] == 'built'
    assert result['inherited_builds'][0]['objects_built'] > 0
    assert after == before
    assert failed['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'


def test_public_surface_isolation_and_no_raw_pbp_imports(app):
    service_path = REPO_ROOT / 'backend/services/inherited_traffic_evidence.py'
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
        'services.inherited_traffic_evidence',
        'inherited_traffic_evidence',
        *INHERITED_TRAFFIC_RULE_IDS,
        'inherited_traffic_fact',
    )
    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for needle in blocked_public:
            assert needle not in text

    with app.app_context():
        _log(seed=80, game_pk=18000, hits=3, walks=0)
        build_inherited_traffic_evidence(PRODUCT_DATE)
        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())
    for forbidden in ('shutdown', 'high-pressure', 'dominant', 'shaky', 'available', 'fatigued'):
        assert forbidden not in rendered
