from datetime import date, datetime, timedelta
from pathlib import Path
import re

import pytest
from flask import Flask

import models.composed_read  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.player_transaction  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import ComposedRead
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services.composed_read import mark_dependent_reads_for_recompute
from services.composed_read_registry import (
    ComposedReadRegistryError,
    ReadTypeRegistry,
    validate_read_type_registry,
)
from services.evidence_classification import (
    EvidenceClassification,
    validate_evidence_classifications,
)
from services.evidence_language import EvidenceLanguageError
from services.reliever_daily_read import (
    READ_TYPE,
    build_reliever_daily_reads,
    register_reliever_daily_read,
)
from services.roster_membership_evidence import (
    PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID,
    REASON_SNAPSHOT_MISSING,
    REASON_SNAPSHOT_STALE,
    build_roster_membership_evidence,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 5)
PUBLIC_PAYLOAD_SURFACES = (
    REPO_ROOT / 'backend/api/bullpen.py',
    REPO_ROOT / 'backend/services/dashboard_snapshot.py',
    REPO_ROOT / 'backend/services/bullpen_board.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    REPO_ROOT / 'frontend/src',
    REPO_ROOT / 'frontend/public',
)


@pytest.fixture
def app():
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


def _create_sync_run(*, source='phase0e_reliever_daily_test'):
    run = SyncRun(
        job_name='phase0e_reliever_daily_test',
        started_at=datetime(2026, 7, 5, 12, 0, 0),
        completed_at=datetime(2026, 7, 5, 12, 0, 1),
        status='success',
        stage='complete',
        source=source,
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(mlb_id, *, team_id=147, name=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name or f'Pitcher {mlb_id}',
        team_id=team_id,
        team_name='Test Team',
        team_abbreviation='TST',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _snapshot(pitcher, snapshot_date, *, active=True, sync_run_id=None, team_id=None):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id or pitcher.team_id or 147,
        snapshot_date=snapshot_date,
        roster_status='active' if active else 'inactive',
        active_roster=active,
        forty_man_roster=True,
        position_code='P',
        position_name='Pitcher',
        position_type='Pitcher',
        source='test_roster_snapshot',
        sync_run_id=sync_run_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _game_log(pitcher, game_date, *, games_started=0, game_pk=None):
    row = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk or (900000 + pitcher.id * 100 + game_date.day),
        game_date=game_date,
        opponent='Opponent',
        opponent_abbreviation='OPP',
        game_type='R',
        games_started=games_started,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=14,
        strikes=9,
        hits_allowed=0,
        runs_allowed=0,
        earned_runs=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        batters_faced=3,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _evidence(
    evidence_type,
    *,
    rule_id=None,
    pitcher=None,
    team_id=None,
    key,
    sync_run_id=None,
    completeness=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=(),
    limitations=(),
):
    subject_type = 'team' if team_id is not None else 'pitcher'
    subject_id = str(team_id if team_id is not None else pitcher.id)
    evidence = EvidenceObject(
        evidence_key=f'test:evidence:{key}',
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_key=f'{subject_type}:{subject_id}:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id='test_claim',
        rendered_claim='Stored test evidence.',
        rule_id=rule_id or evidence_type,
        rule_version=1,
        rule_definition_hash='test-hash',
        typed_cited_inputs=[],
        computation_trace={'steps': ['test']},
        completeness_state=completeness,
        reason_codes=list(reason_codes),
        limitations=list(limitations),
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='test',
        sync_run_id=sync_run_id,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    evidence.citations = [
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=str(key),
            source_field_names=['game_date'],
            citation_role='supporting_input',
            cited_values={'game_date': PRODUCT_DATE.isoformat()},
            provenance={'source': 'test', 'sync_run_id': sync_run_id},
        )
    ]
    db.session.add(evidence)
    db.session.flush()
    return evidence


def _component(read, name):
    return [item for item in read.components if item.component_name == name][0]


def test_roster_membership_evidence_fresh_stale_missing_and_scoped_emission(app):
    with app.app_context():
        sync_run = _create_sync_run()
        active = _pitcher(1001)
        inactive = _pitcher(1002)
        stale = _pitcher(1003)
        missing = _pitcher(1004)
        out_of_scope = _pitcher(1005)
        _snapshot(active, PRODUCT_DATE, active=True, sync_run_id=sync_run.id)
        _snapshot(inactive, PRODUCT_DATE, active=False, sync_run_id=sync_run.id)
        _snapshot(stale, PRODUCT_DATE - timedelta(days=1), active=True, sync_run_id=sync_run.id)
        _snapshot(out_of_scope, PRODUCT_DATE, active=True, sync_run_id=sync_run.id)
        active_id = active.id
        active_team_id = active.team_id
        inactive_id = inactive.id
        stale_id = stale.id
        missing_id = missing.id
        out_of_scope_id = out_of_scope.id

        result = build_roster_membership_evidence(
            PRODUCT_DATE,
            pitcher_ids=(active_id, inactive_id, stale_id, missing_id),
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        rows = {
            int(row.subject_id): row
            for row in EvidenceObject.query
            .filter_by(rule_id=PITCHER_ROSTER_MEMBERSHIP_CONTEXT_RULE_ID)
            .all()
        }

    assert result['objects_built'] == 4
    assert set(rows) == {active_id, inactive_id, stale_id, missing_id}
    assert rows[active_id].completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
    assert rows[active_id].rendered_claim == (
        f'On the active roster per the {PRODUCT_DATE.isoformat()} snapshot '
        f'(team {active_team_id}).'
    )
    assert rows[inactive_id].rendered_claim == (
        f'Not on the active roster per the {PRODUCT_DATE.isoformat()} snapshot.'
    )
    assert rows[stale_id].completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert rows[stale_id].reason_codes == [REASON_SNAPSHOT_STALE]
    assert rows[missing_id].completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert rows[missing_id].reason_codes == [REASON_SNAPSHOT_MISSING]
    assert rows[missing_id].citations[0].source_pk.startswith('missing:')
    assert out_of_scope_id not in rows


def test_roster_membership_claim_language_rejects_forbidden_status_terms(app):
    from services.roster_membership_evidence import _assert_text_has_no_membership_forbidden_terms

    with app.app_context():
        for claim in ('Pitcher is available.', 'Pitcher is healthy.'):
            with pytest.raises(EvidenceLanguageError):
                _assert_text_has_no_membership_forbidden_terms(claim)


def test_reliever_daily_read_registration_and_classification_contract():
    registry = ReadTypeRegistry()
    register_reliever_daily_read(registry=registry)
    read_type = registry.get(READ_TYPE, 1)
    components = {component.name: component for component in read_type.components}

    assert validate_read_type_registry(registry) == {
        'read_type_count': 1,
        'classified_count': 1,
    }
    assert read_type.classification == EvidenceClassification.INTERNAL_ONLY_FOR_NOW
    assert read_type.subject_type == ComposedRead.SUBJECT_PITCHER_DAY
    with pytest.raises(ComposedReadRegistryError, match='duplicate read type'):
        registry.register(read_type)
    assert set(components) == {
        'workload_component',
        'rest_component',
        'recent_outing_component',
        'roster_il_context',
        'situational_component',
        'usage_observation_component',
        'data_completeness_component',
    }
    for component in components.values():
        assert 'appearance_entry_band' not in component.allowed_evidence_types
        assert 'pitcher_entry_band_distribution' not in component.allowed_evidence_types

    classification = validate_evidence_classifications()
    assert classification['rule_count'] == 65
    assert classification['tallies']['PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'] == 44
    assert classification['tallies']['PERMANENTLY_INTERNAL'] == 8


def test_reliever_daily_read_population_boundary_components_and_optional_degrade(app):
    with app.app_context():
        sync_run = _create_sync_run()
        qualifying = _pitcher(1101, team_id=147)
        boundary = _pitcher(1102, team_id=147)
        starter_only = _pitcher(1103, team_id=147)
        unknown_role = _pitcher(1104, team_id=147)
        outside_window = _pitcher(1105, team_id=147)
        _game_log(qualifying, PRODUCT_DATE, games_started=0)
        _game_log(boundary, PRODUCT_DATE - timedelta(days=29), games_started=0)
        _game_log(starter_only, PRODUCT_DATE, games_started=1)
        _game_log(unknown_role, PRODUCT_DATE, games_started=None)
        _game_log(outside_window, PRODUCT_DATE - timedelta(days=30), games_started=0)
        _snapshot(qualifying, PRODUCT_DATE, active=True, sync_run_id=sync_run.id)
        _snapshot(boundary, PRODUCT_DATE, active=True, sync_run_id=sync_run.id)
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_window_appearances',
            pitcher=qualifying,
            key='qual-workload',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_days_of_rest',
            pitcher=qualifying,
            key='qual-rest',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'appearance_context_fact',
            rule_id='appearance_entry_context',
            pitcher=qualifying,
            key='qual-appearance',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'pitcher_save_hold_window',
            rule_id='pitcher_save_hold_window',
            pitcher=qualifying,
            key='qual-optional-conflict',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_CONFLICT,
            reason_codes=('component_evidence_conflict',),
        )
        qualifying_id = qualifying.id
        boundary_id = boundary.id

        result = build_reliever_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        reads = {
            int(row.subject_id): row
            for row in ComposedRead.query.filter_by(read_type=READ_TYPE).all()
        }
        qualifying_read = reads[qualifying_id]

    assert result['reads_built'] == 2
    assert set(reads) == {qualifying_id, boundary_id}
    assert qualifying_read.completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert qualifying_read.posture == ComposedRead.POSTURE_INTERNAL_ONLY
    assert qualifying_read.component_summary['situational_component']['state'] == (
        ComposedRead.COMPLETENESS_CONFLICT
    )
    assert _component(qualifying_read, 'data_completeness_component').evidence_citations == []
    data_text = ' '.join(
        list(_component(qualifying_read, 'data_completeness_component').reason_codes or [])
        + list(_component(qualifying_read, 'data_completeness_component').limitations or [])
    )
    assert not re.search(r'[%0-9]|\b(score|grade|rank|confidence)\b', data_text, re.I)
    payload = qualifying_read.to_dict()
    assert 'headline' not in payload
    assert 'read_label' not in payload
    assert 'score' not in payload


def test_reliever_daily_read_degrades_when_roster_membership_is_stale(app):
    with app.app_context():
        sync_run = _create_sync_run()
        pitcher = _pitcher(1201)
        _game_log(pitcher, PRODUCT_DATE, games_started=0)
        _snapshot(pitcher, PRODUCT_DATE - timedelta(days=1), active=True, sync_run_id=sync_run.id)
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_window_appearances',
            pitcher=pitcher,
            key='stale-workload',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_days_of_rest',
            pitcher=pitcher,
            key='stale-rest',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'appearance_context_fact',
            rule_id='appearance_entry_context',
            pitcher=pitcher,
            key='stale-appearance',
            sync_run_id=sync_run.id,
        )

        build_reliever_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        read = ComposedRead.query.filter_by(read_type=READ_TYPE, subject_id=str(pitcher.id)).one()

    assert read.completeness_state == ComposedRead.COMPLETENESS_UNKNOWN
    assert read.component_summary['roster_il_context']['state'] == ComposedRead.COMPLETENESS_UNKNOWN
    assert 'roster_il_context:snapshot_stale' in read.reason_codes


def test_reliever_daily_read_recompute_marks_only_dependent_read_and_rebuilds(app):
    with app.app_context():
        sync_run = _create_sync_run()
        first = _pitcher(1301)
        second = _pitcher(1302)
        for pitcher in (first, second):
            _game_log(pitcher, PRODUCT_DATE, games_started=0)
            _snapshot(pitcher, PRODUCT_DATE, active=True, sync_run_id=sync_run.id)
        first_workload = _evidence(
            'workload_recovery_fact',
            rule_id='workload_window_appearances',
            pitcher=first,
            key='first-workload',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_days_of_rest',
            pitcher=first,
            key='first-rest',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'appearance_context_fact',
            rule_id='appearance_entry_context',
            pitcher=first,
            key='first-appearance',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_window_appearances',
            pitcher=second,
            key='second-workload',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_recovery_fact',
            rule_id='workload_days_of_rest',
            pitcher=second,
            key='second-rest',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'appearance_context_fact',
            rule_id='appearance_entry_context',
            pitcher=second,
            key='second-appearance',
            sync_run_id=sync_run.id,
        )
        build_reliever_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        first_read = ComposedRead.query.filter_by(read_type=READ_TYPE, subject_id=str(first.id)).one()
        second_read = ComposedRead.query.filter_by(read_type=READ_TYPE, subject_id=str(second.id)).one()

        marked = mark_dependent_reads_for_recompute(
            evidence_object_ids=(first_workload.id,),
            reason_code='component_evidence_superseded',
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        build_reliever_daily_reads(
            PRODUCT_DATE,
            pitcher_ids=(first.id,),
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        old_first = db.session.get(ComposedRead, first_read.id)
        current_second = db.session.get(ComposedRead, second_read.id)
        rebuilt_first = (
            ComposedRead.query
            .filter_by(read_type=READ_TYPE, subject_id=str(first.id))
            .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_CURRENT)
            .one()
        )

    assert marked == {'marked_count': 1, 'read_ids': [first_read.id]}
    assert old_first.recompute_status == ComposedRead.RECOMPUTE_SUPERSEDED
    assert old_first.superseded_by_read_id == rebuilt_first.id
    assert current_second.recompute_status == ComposedRead.RECOMPUTE_CURRENT


def test_phase0e_sync_stage_kill_switch_and_fail_soft_dead_letter(app, monkeypatch):
    from services import sync as sync_service

    with app.app_context():
        sync_run = _create_sync_run()
        sync_run_id = sync_run.id
        monkeypatch.setenv('PHASE0E_READ_BUILD', 'false')
        skipped = sync_service._safe_build_composed_reads_stage(
            [PRODUCT_DATE],
            sync_run_id=sync_run_id,
            source='test',
        )
        assert skipped['status'] == 'skipped'
        assert skipped['reason'] == 'disabled'

        monkeypatch.setenv('PHASE0E_READ_BUILD', 'true')

        def _boom(*args, **kwargs):
            raise RuntimeError('test composed read failure')

        import services.reliever_daily_read as reliever_daily_read_service

        monkeypatch.setattr(reliever_daily_read_service, 'build_reliever_daily_reads', _boom)
        failed = sync_service._safe_build_composed_reads_stage(
            [PRODUCT_DATE],
            sync_run_id=sync_run_id,
            source='test',
        )
        failure = SyncFailure.query.one()
        failure_entity_type = failure.entity_type
        failure_sync_run_id = failure.sync_run_id

    assert failed['status'] == 'failed'
    assert 'test composed read failure' in failed['error']
    assert failure_entity_type == sync_service.COMPOSED_READ_FAILURE_ENTITY_TYPE
    assert failure_sync_run_id == sync_run_id


def test_public_surfaces_do_not_import_reliever_daily_read_or_composed_reads():
    blocked_references = (
        'reliever_daily_read',
        'build_reliever_daily_reads',
        'ComposedRead',
        'composed_reads',
        'pitcher_roster_membership_context',
    )
    scanned = []
    for path in PUBLIC_PAYLOAD_SURFACES:
        files = (
            [file for file in path.rglob('*') if file.is_file()]
            if path.is_dir()
            else [path]
        )
        for file in files:
            if file.suffix not in {'.py', '.js', '.jsx', '.ts', '.tsx', '.json'}:
                continue
            scanned.append(file)
            text = file.read_text(encoding='utf-8', errors='ignore')
            for reference in blocked_references:
                assert reference not in text, f'{reference} leaked into {file}'
    assert scanned
