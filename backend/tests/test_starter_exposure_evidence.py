from datetime import date, datetime, timedelta
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from models.team_game_pitching_split import TeamGamePitchingSplit
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
from services.starter_exposure_evidence import (
    APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION,
    APPEARANCES_RULE_ID,
    CONSECUTIVE_RULE_ID,
    DENSITY_RULE_ID,
    DOUBLEHEADER_TODAY_RULE_ID,
    OFF_DAY_TOMORROW_RULE_ID,
    OFF_DAY_YESTERDAY_RULE_ID,
    OUTS_RULE_ID,
    PITCHES_RULE_ID,
    REASON_AMBIGUOUS_RESUMED_GAME,
    REASON_CALENDAR_CONTEXT_UNAVAILABLE,
    REASON_SHARE_DENOMINATOR_UNAVAILABLE,
    REASON_SPLIT_ROW_PARTIAL,
    REASON_STARTER_IDENTITY_UNKNOWN,
    REASON_STARTER_OUTS_UNKNOWN,
    REASON_UNKNOWN_PITCH_COUNT,
    RECENT_DOUBLEHEADER_RULE_ID,
    RULE_VERSION,
    SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION,
    SHARE_RULE_ID,
    SHORT_START_MAX_OUTS,
    SHORT_START_RULE_ID,
    STARTER_EXPOSURE_RULE_IDS,
    _register_starter_exposure_rule,
    _register_starter_exposure_template,
    build_starter_exposure_evidence,
    mark_team_game_pitching_split_correction_for_starter_exposure,
    rebuild_marked_starter_exposure_evidence,
    register_starter_exposure_rules,
    starter_exposure_rule_definitions,
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
        job_name='phase0d_starter_exposure_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _split(
    *,
    team_id=116,
    game_pk=5000,
    days_ago=0,
    split_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    split_reasons=None,
    calendar_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    calendar_reasons=None,
    starter_status=TeamGamePitchingSplit.STARTER_KNOWN,
    starter_outs=15,
    bullpen_outs=12,
    bullpen_pitches=45,
    relievers=2,
    total_outs=27,
    doubleheader=False,
    doubleheader_code='N',
    game_number=1,
    off_day_before=False,
    off_day_after=False,
    consecutive=1,
    linkage=TeamGamePitchingSplit.LINKAGE_NONE,
):
    row = TeamGamePitchingSplit(
        team_id=team_id,
        mlb_game_pk=game_pk,
        game_date=PRODUCT_DATE - timedelta(days=days_ago),
        game_type='R',
        opponent_team_id=999,
        home_away='home',
        starter_pitcher_id=None,
        starter_mlb_id=None,
        starter_identity_status=starter_status,
        starter_outs_recorded=starter_outs,
        starter_pitches_thrown=80,
        starter_batters_faced=20,
        starter_balls=30,
        starter_games_started=1 if starter_status == TeamGamePitchingSplit.STARTER_KNOWN else None,
        bullpen_outs_recorded=bullpen_outs,
        bullpen_pitches_thrown=bullpen_pitches,
        bullpen_batters_faced=13,
        bullpen_balls=18,
        relievers_used_count=relievers,
        total_team_outs=total_outs,
        total_team_pitches=(80 if starter_status == TeamGamePitchingSplit.STARTER_KNOWN else 0) + (bullpen_pitches or 0),
        total_team_batters_faced=33,
        total_team_balls=48,
        split_completeness_status=split_status,
        split_reason_codes=list(split_reasons or []),
        off_day_before=off_day_before if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        off_day_after=off_day_after if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        consecutive_game_day_count_entering=consecutive if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        series_game_number=1,
        games_in_series=3,
        doubleheader_flag=doubleheader if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        doubleheader_code=doubleheader_code,
        game_number=game_number,
        postponed_or_makeup_indicator=False,
        suspended_resumed_linkage_status=linkage,
        extra_inning_indicator=False,
        calendar_context_status=calendar_status,
        calendar_reason_codes=list(calendar_reasons or []),
        source='test_split_fixture',
        last_derived_at=datetime(2026, 7, 4, 12, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _rows(rule_id, team_id=116):
    return (
        EvidenceObject.query
        .filter_by(rule_id=rule_id, subject_id=str(team_id))
        .order_by(EvidenceObject.subject_key, EvidenceObject.id)
        .all()
    )


def _row(rule_id, team_id=116, *, subject_key_contains=None):
    query = EvidenceObject.query.filter_by(rule_id=rule_id, subject_id=str(team_id))
    if subject_key_contains:
        query = query.filter(EvidenceObject.subject_key.contains(subject_key_contains))
    return query.one()


def test_registration_guards_thresholds_and_language():
    registry, templates = register_starter_exposure_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    rules = registry.all_rules()

    assert [rule.rule_id for rule in rules] == sorted(STARTER_EXPOSURE_RULE_IDS)
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert len(templates._templates) == 11
    assert registry.get(SHORT_START_RULE_ID).thresholds['short_start_max_outs'] == SHORT_START_MAX_OUTS
    definitions = ' '.join(starter_exposure_rule_definitions().values())
    assert '14' in definitions
    assert '7-day' in definitions
    assert '14-day' in definitions

    with pytest.raises(EvidenceRuleError):
        _register_starter_exposure_rule(
            EvidenceRuleRegistry(),
            EvidenceRule(
                rule_id='bad_public_starter_exposure_rule',
                rule_version=1,
                evidence_type='bad_public_starter_exposure_rule',
                plain_language_definition='A neutral team split fact.',
                required_input_families=('team_game_pitching_splits',),
                required_cited_fields=('team_game_pitching_splits.team_id',),
                posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
            ),
        )

    for text in (
        'overworked bullpen',
        'rotation struggling',
        'opener',
        'likely available',
        'should be rested',
        'pressure',
        'fatigue',
        'score',
        'rank',
    ):
        with pytest.raises(EvidenceLanguageError):
            _register_starter_exposure_template(
                ClaimTemplateRegistry(),
                ClaimTemplate(
                    template_id=f'bad_{text.split()[0]}',
                    template_version=1,
                    template_text=text,
                ),
            )


def test_share_degrades_to_unknown_while_count_uses_lower_bound(app):
    with app.app_context():
        _split(team_id=116, game_pk=5100, days_ago=0, bullpen_outs=12, total_outs=27)
        _split(team_id=116, game_pk=5101, days_ago=1, bullpen_outs=9, total_outs=27)
        partial = _split(
            team_id=116,
            game_pk=5102,
            days_ago=2,
            split_status=TeamGamePitchingSplit.STATUS_PARTIAL,
            split_reasons=['starter_identity_unknown'],
            bullpen_outs=None,
            total_outs=27,
        )
        _split(team_id=117, game_pk=5200, days_ago=0, bullpen_outs=12, total_outs=27)
        _split(team_id=117, game_pk=5201, days_ago=1, bullpen_outs=12, total_outs=27)

        build_starter_exposure_evidence(PRODUCT_DATE)
        outs = _row(OUTS_RULE_ID, subject_key_contains='window-7')
        share = _row(SHARE_RULE_ID, subject_key_contains='window-7')
        complete_share = _row(SHARE_RULE_ID, team_id=117, subject_key_contains='window-7')

        assert outs.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
        assert 'at least 21 outs' in outs.rendered_claim
        assert 'at least' in outs.rendered_claim
        assert REASON_SPLIT_ROW_PARTIAL in outs.reason_codes
        assert any(
            citation.source_pk == str(partial.id)
            and citation.citation_role == 'excluded_input'
            for citation in outs.citations
        )
        assert share.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert '%' not in share.rendered_claim
        assert complete_share.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert '24 of 54 team outs' in complete_share.rendered_claim
        assert '%' in complete_share.rendered_claim


def test_pitch_unknown_uses_known_subtotal_and_outs_unaffected(app):
    with app.app_context():
        _split(team_id=118, game_pk=5300, days_ago=0, bullpen_outs=12, bullpen_pitches=45)
        _split(team_id=118, game_pk=5301, days_ago=1, bullpen_outs=9, bullpen_pitches=None)

        build_starter_exposure_evidence(PRODUCT_DATE)
        pitches = _row(PITCHES_RULE_ID, team_id=118, subject_key_contains='window-7')
        outs = _row(OUTS_RULE_ID, team_id=118, subject_key_contains='window-7')

        assert pitches.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_UNKNOWN_PITCH_COUNT in pitches.reason_codes
        assert 'known-value subtotal 45' in pitches.rendered_claim
        assert pitches.computation_trace['known_value_subtotal'] == 45
        assert outs.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert '21 outs' in outs.rendered_claim


def test_short_start_boundaries_and_exclusions(app):
    with app.app_context():
        _split(team_id=119, game_pk=5400, days_ago=0, starter_outs=14)
        _split(team_id=119, game_pk=5401, days_ago=1, starter_outs=15)
        identity_unknown = _split(
            team_id=119,
            game_pk=5402,
            days_ago=2,
            starter_status=TeamGamePitchingSplit.STARTER_UNKNOWN,
            starter_outs=None,
        )
        outs_unknown = _split(team_id=119, game_pk=5403, days_ago=3, starter_outs=None)

        build_starter_exposure_evidence(PRODUCT_DATE)
        short_7 = _row(SHORT_START_RULE_ID, team_id=119, subject_key_contains='window-7')
        short_14 = _row(SHORT_START_RULE_ID, team_id=119, subject_key_contains='window-14')

        for row in (short_7, short_14):
            assert row.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
            assert 'At least 1 starts shorter than five innings (14 outs or fewer)' in row.rendered_claim
            assert REASON_STARTER_IDENTITY_UNKNOWN in row.reason_codes
            assert REASON_STARTER_OUTS_UNKNOWN in row.reason_codes
            excluded_pks = {
                citation.source_pk
                for citation in row.citations
                if citation.citation_role == 'excluded_input'
            }
            assert str(identity_unknown.id) in excluded_pks
            assert str(outs_unknown.id) in excluded_pks


def test_doubleheader_off_day_calendar_and_density(app):
    with app.app_context():
        first = _split(
            team_id=120,
            game_pk=5500,
            days_ago=0,
            doubleheader=True,
            doubleheader_code='Y',
            game_number=1,
            off_day_before=True,
            off_day_after=True,
            consecutive=3,
        )
        second = _split(
            team_id=120,
            game_pk=5501,
            days_ago=0,
            doubleheader=True,
            doubleheader_code='Y',
            game_number=2,
            off_day_before=True,
            off_day_after=True,
            consecutive=3,
        )
        _split(
            team_id=121,
            game_pk=5600,
            days_ago=0,
            calendar_status=TeamGamePitchingSplit.STATUS_UNKNOWN,
        )
        _split(
            team_id=122,
            game_pk=5700,
            days_ago=0,
            off_day_before=False,
            off_day_after=False,
        )

        build_starter_exposure_evidence(PRODUCT_DATE)
        today = _row(DOUBLEHEADER_TODAY_RULE_ID, team_id=120)
        recent = _row(RECENT_DOUBLEHEADER_RULE_ID, team_id=120)
        density = _row(DENSITY_RULE_ID, team_id=120)
        yesterday = _row(OFF_DAY_YESTERDAY_RULE_ID, team_id=120)
        tomorrow = _row(OFF_DAY_TOMORROW_RULE_ID, team_id=120)
        consecutive = _row(CONSECUTIVE_RULE_ID, team_id=120)
        unknown_tomorrow = _row(OFF_DAY_TOMORROW_RULE_ID, team_id=121)

        assert {citation.source_pk for citation in today.citations} == {str(first.id), str(second.id)}
        assert 'games 5500, 5501 cited' in today.rendered_claim
        assert '5500' in recent.rendered_claim and '5501' in recent.rendered_claim
        assert '2 final games, 1 distinct game days' in density.rendered_claim
        assert '0 score' not in density.rendered_claim
        assert 'had no game' in yesterday.rendered_claim
        assert SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION in tomorrow.limitations
        assert 'No game appears on the team 120 schedule' in tomorrow.rendered_claim
        assert '3 consecutive game days' in consecutive.rendered_claim
        assert unknown_tomorrow.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_CALENDAR_CONTEXT_UNAVAILABLE in unknown_tomorrow.reason_codes
        assert not _rows(OFF_DAY_TOMORROW_RULE_ID, team_id=122)


def test_ambiguous_resumed_linkage_degrades_window_metrics(app):
    with app.app_context():
        _split(team_id=123, game_pk=5800, days_ago=0)
        _split(
            team_id=123,
            game_pk=5801,
            days_ago=1,
            linkage=TeamGamePitchingSplit.LINKAGE_AMBIGUOUS,
        )

        build_starter_exposure_evidence(PRODUCT_DATE)
        outs = _row(OUTS_RULE_ID, team_id=123, subject_key_contains='window-7')
        share = _row(SHARE_RULE_ID, team_id=123, subject_key_contains='window-7')

        assert outs.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
        assert REASON_AMBIGUOUS_RESUMED_GAME in outs.reason_codes
        assert share.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_AMBIGUOUS_RESUMED_GAME in share.reason_codes


def test_expected_team_game_limitation_and_no_game_log_or_pbp_imports(app):
    service_path = REPO_ROOT / 'backend/services/starter_exposure_evidence.py'
    service_text = service_path.read_text(encoding='utf-8')
    blocked_service_imports = (
        'models.game_log',
        'GameLog',
        'models.play_by_play_foundation',
        'GamePlayByPlayEvent',
        'PlayByPlayProcessedGame',
        'services.play_by_play_foundation',
    )
    for needle in blocked_service_imports:
        assert needle not in service_text
    assert 'not_supportable_without_existing_team_scoped_helper' in service_text

    public_paths = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    )
    blocked_public = (
        'services.starter_exposure_evidence',
        'starter_exposure_evidence',
        *STARTER_EXPOSURE_RULE_IDS,
    )
    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for needle in blocked_public:
            assert needle not in text

    with app.app_context():
        _split(team_id=124, game_pk=5900, days_ago=0)
        build_starter_exposure_evidence(PRODUCT_DATE)
        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())
    for forbidden in (
        'overworked',
        'rotation struggling',
        'opener',
        'likely available',
        'should be rested',
        'pressure',
        'fatigue',
        ' score ',
        ' rank ',
    ):
        assert forbidden not in f' {rendered} '


def test_recompute_from_split_row_is_bounded_and_idempotent(app):
    with app.app_context():
        run = _sync_run()
        target = _split(team_id=130, game_pk=6000, days_ago=0, bullpen_outs=12)
        unrelated = _split(team_id=131, game_pk=6100, days_ago=0, bullpen_outs=9)
        build_starter_exposure_evidence(PRODUCT_DATE, sync_run_id=run.id)
        first_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(STARTER_EXPOSURE_RULE_IDS)).count()
        build_starter_exposure_evidence(PRODUCT_DATE, sync_run_id=run.id)
        second_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(STARTER_EXPOSURE_RULE_IDS)).count()

        target_outs = _row(OUTS_RULE_ID, team_id=130, subject_key_contains='window-7')
        unrelated_outs = _row(OUTS_RULE_ID, team_id=131, subject_key_contains='window-7')
        unrelated_updated_at = unrelated_outs.updated_at
        target.bullpen_outs_recorded = 15
        marked = mark_team_game_pitching_split_correction_for_starter_exposure(
            target,
            sync_run_id=run.id,
            batch_size=100,
        )
        rebuilt = rebuild_marked_starter_exposure_evidence(sync_run_id=run.id)
        target_after = db.session.get(EvidenceObject, target_outs.id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_outs.id)

        assert first_count == second_count
        assert target_outs.id in marked['evidence_ids']
        assert marked['marked_count'] <= 100
        assert rebuilt['objects_rebuilt'] >= 1
        assert target_after.recompute_status == EvidenceObject.RECOMPUTE_CURRENT
        assert target_after.computation_trace['superseded_prior']['rendered_claim']
        assert '15 outs' in target_after.rendered_claim
        assert unrelated_after.updated_at == unrelated_updated_at


def test_sync_stage_fail_soft_kill_switch_and_public_payload_shape(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        before = set(sync_metadata.build_sync_status_payload().keys())
        _split(team_id=140, game_pk=6200, days_ago=0)
        result = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        after = set(sync_metadata.build_sync_status_payload().keys())

        def boom(*args, **kwargs):
            raise RuntimeError('starter exposure stage exploded')

        import services.starter_exposure_evidence as starter_service
        monkeypatch.setattr(starter_service, 'build_starter_exposure_evidence', boom)
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
            starter_service,
            'build_starter_exposure_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )

    assert result['status'] == 'built'
    assert result['starter_exposure_builds'][0]['objects_built'] > 0
    assert after == before
    assert failed['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'
