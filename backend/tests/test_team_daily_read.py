from datetime import date, datetime
from pathlib import Path
import re

import pytest
from flask import Flask

import models.composed_read  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import (
    ComposedRead,
    ComposedReadComponent,
    ComposedReadEvidenceCitation,
)
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services.composed_read import mark_dependent_reads_for_recompute
from services.composed_read_registry import (
    ComponentSpec,
    ComposedReadRegistryError,
    ReadType,
    ReadTypeRegistry,
    validate_read_type_registry,
)
from services.evidence_classification import (
    EvidenceClassification,
    validate_evidence_classifications,
)
from services.reliever_daily_read import (
    READ_TYPE as RELIEVER_READ_TYPE,
    build_reliever_daily_reads,
)
from services.team_daily_read import (
    READ_DEFINITION,
    READ_TYPE,
    assert_roster_churn_content_allowed,
    build_team_daily_reads,
    rebuild_marked_team_daily_reads,
    register_team_daily_read,
)
from services.team_relief_composition_evidence import BASIS_DISCLAIMER
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


def _create_sync_run(*, source='phase0e_team_daily_test'):
    run = SyncRun(
        job_name='phase0e_team_daily_test',
        started_at=datetime(2026, 7, 5, 12, 0, 0),
        completed_at=datetime(2026, 7, 5, 12, 0, 1),
        status='success',
        stage='complete',
        source=source,
    )
    db.session.add(run)
    db.session.flush()
    return run


def _pitcher(mlb_id, *, team_id=147):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Pitcher {mlb_id}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _snapshot(team_id, pitcher, *, snapshot_date=PRODUCT_DATE, sync_run_id=None):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id,
        snapshot_date=snapshot_date,
        roster_status='active',
        active_roster=True,
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


def _game_log(pitcher, *, game_pk=990001):
    row = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=PRODUCT_DATE,
        opponent='Opponent',
        opponent_abbreviation='OPP',
        game_type='R',
        games_started=0,
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
    rule_id,
    *,
    team_id=None,
    pitcher=None,
    key=None,
    sync_run_id=None,
    completeness=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=(),
    limitations=(),
    evidence_type=None,
):
    subject_type = 'team' if team_id is not None else 'pitcher'
    subject_id = str(team_id if team_id is not None else pitcher.id)
    key = key or f'{subject_type}-{subject_id}-{rule_id}'
    evidence = EvidenceObject(
        evidence_key=f'test:evidence:{key}',
        evidence_type=evidence_type or rule_id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_key=f'{subject_type}:{subject_id}:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id='test_claim',
        rendered_claim='Stored test evidence.',
        rule_id=rule_id,
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
            source_family='test_source',
            source_table='test_source',
            source_pk=str(key),
            source_field_names=['product_date'],
            citation_role='supporting_input',
            cited_values={'product_date': PRODUCT_DATE.isoformat()},
            provenance={'source': 'test', 'sync_run_id': sync_run_id},
        )
    ]
    db.session.add(evidence)
    db.session.flush()
    return evidence


def _required_team_evidence(team_id, sync_run_id, *, suffix='base'):
    basis = _evidence(
        'team_relief_contributor_basis',
        team_id=team_id,
        key=f'{suffix}-basis-{team_id}',
        sync_run_id=sync_run_id,
    )
    exposure = _evidence(
        'team_bullpen_outs_window',
        team_id=team_id,
        key=f'{suffix}-exposure-{team_id}',
        sync_run_id=sync_run_id,
    )
    roster = _evidence(
        'team_active_pitcher_census',
        team_id=team_id,
        key=f'{suffix}-roster-{team_id}',
        sync_run_id=sync_run_id,
    )
    return basis, exposure, roster


def _component(read, name):
    return [item for item in read.components if item.component_name == name][0]


def test_team_daily_read_registration_locks_and_classification_contract():
    registry = ReadTypeRegistry()
    register_team_daily_read(registry=registry)
    read_type = registry.get(READ_TYPE, 1)
    components = {component.name: component for component in read_type.components}

    assert validate_read_type_registry(registry) == {
        'read_type_count': 1,
        'classified_count': 1,
    }
    assert read_type.classification == EvidenceClassification.INTERNAL_ONLY_FOR_NOW
    assert read_type.subject_type == ComposedRead.SUBJECT_TEAM_DAY
    assert read_type.plain_language_definition == READ_DEFINITION
    assert set(components) == {
        'contributor_composition_component',
        'exposure_component',
        'calendar_component',
        'roster_churn_component',
        'slate_data_completeness_component',
    }
    for component in components.values():
        assert 'appearance_entry_band' not in component.allowed_evidence_types
        assert 'pitcher_entry_band_distribution' not in component.allowed_evidence_types
        assert 'team_active_reliever_count' not in component.allowed_evidence_types
    with pytest.raises(ComposedReadRegistryError, match='duplicate read type'):
        registry.register(read_type)
    with pytest.raises(ComposedReadRegistryError, match='locked band evidence'):
        _invalid_team_registry(('team_active_reliever_count',))
    with pytest.raises(ComposedReadRegistryError, match='locked band evidence'):
        _invalid_team_registry(('appearance_entry_band',))
    with pytest.raises(ComposedReadRegistryError, match='forbidden'):
        _invalid_team_registry(('team_active_pitcher_census',), component_name='thin_component')

    classification = validate_evidence_classifications()
    assert classification['rule_count'] == 65
    assert classification['tallies']['PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'] == 44
    assert classification['tallies']['ELIGIBLE_PUBLIC_CANDIDATE_LATER'] == 9
    assert classification['tallies']['INTERNAL_ONLY_FOR_NOW'] == 4
    assert classification['tallies']['PERMANENTLY_INTERNAL'] == 8


def test_rollup_deferral_guard_schema_and_registry_are_unchanged():
    assert 'allowed_read_types' not in ComponentSpec.__dataclass_fields__
    fk_targets = {
        fk.column.table.name
        for fk in ComposedReadEvidenceCitation.__table__.foreign_keys
    }
    assert fk_targets == {'composed_read_components', 'evidence_objects'}
    assert not any(
        table.name == 'composed_read_read_citations'
        for table in ComposedRead.metadata.tables.values()
    )
    assert ComposedReadComponent.__table__.foreign_keys
    assert all(
        fk.column.table.name == 'composed_reads'
        for fk in ComposedReadComponent.__table__.foreign_keys
    )


def test_population_off_day_calendar_absent_and_missing_basis_degrades(app):
    with app.app_context():
        sync_run = _create_sync_run()
        team_complete = 147
        team_missing_basis = 158
        pitcher_a = _pitcher(2101, team_id=team_complete)
        pitcher_b = _pitcher(2102, team_id=team_missing_basis)
        _snapshot(team_complete, pitcher_a, sync_run_id=sync_run.id)
        _snapshot(team_missing_basis, pitcher_b, sync_run_id=sync_run.id)
        _required_team_evidence(team_complete, sync_run.id)
        _evidence(
            'team_bullpen_outs_window',
            team_id=team_missing_basis,
            key='missing-basis-exposure',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'team_active_pitcher_census',
            team_id=team_missing_basis,
            key='missing-basis-roster',
            sync_run_id=sync_run.id,
        )

        result = build_team_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        reads = {
            int(row.subject_id): row
            for row in ComposedRead.query.filter_by(read_type=READ_TYPE).all()
        }

    assert result['reads_built'] == 2
    assert set(reads) == {team_complete, team_missing_basis}
    assert reads[team_complete].completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert reads[team_complete].component_summary['calendar_component']['state'] == 'absent'
    contributor = _component(reads[team_complete], 'contributor_composition_component')
    assert BASIS_DISCLAIMER in contributor.limitations
    assert reads[team_missing_basis].completeness_state == ComposedRead.COMPLETENESS_UNKNOWN
    assert (
        reads[team_missing_basis]
        .component_summary['contributor_composition_component']['state']
        == ComposedRead.COMPLETENESS_UNKNOWN
    )


def test_component_degradation_optional_calendar_and_data_completeness(app):
    with app.app_context():
        sync_run = _create_sync_run()
        partial_team = 201
        conflict_team = 202
        stale_team = 203
        calendar_team = 204
        for index, team_id in enumerate((partial_team, conflict_team, stale_team, calendar_team), start=1):
            _snapshot(team_id, _pitcher(2200 + index, team_id=team_id), sync_run_id=sync_run.id)

        _evidence(
            'team_relief_contributor_basis',
            team_id=partial_team,
            key='partial-basis',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_PARTIAL,
            reason_codes=('basis_lower_bound',),
        )
        _evidence('team_bullpen_outs_window', team_id=partial_team, key='partial-exposure', sync_run_id=sync_run.id)
        _evidence(
            'team_transaction_churn_window',
            team_id=partial_team,
            key='partial-roster',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_PARTIAL,
            reason_codes=('transaction_window_uncovered',),
            limitations=('uncovered range cited',),
        )

        _evidence(
            'team_relief_contributor_basis',
            team_id=conflict_team,
            key='conflict-basis',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_CONFLICT,
            reason_codes=('attribution_conflict',),
        )
        _evidence('team_bullpen_outs_window', team_id=conflict_team, key='conflict-exposure', sync_run_id=sync_run.id)
        _evidence('team_active_pitcher_census', team_id=conflict_team, key='conflict-roster', sync_run_id=sync_run.id)

        _evidence('team_relief_contributor_basis', team_id=stale_team, key='stale-basis', sync_run_id=sync_run.id)
        _evidence('team_bullpen_outs_window', team_id=stale_team, key='stale-exposure', sync_run_id=sync_run.id)
        _evidence(
            'team_active_pitcher_census',
            team_id=stale_team,
            key='stale-roster',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_UNKNOWN,
            reason_codes=('snapshot_stale',),
        )

        _required_team_evidence(calendar_team, sync_run.id, suffix='calendar')
        _evidence(
            'team_calendar_density',
            team_id=calendar_team,
            key='calendar-conflict',
            sync_run_id=sync_run.id,
            completeness=EvidenceObject.COMPLETENESS_CONFLICT,
            reason_codes=('calendar_context_unavailable',),
        )

        build_team_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        reads = {
            int(row.subject_id): row
            for row in ComposedRead.query.filter_by(read_type=READ_TYPE).all()
        }
        calendar_read = reads[calendar_team]

    assert reads[partial_team].completeness_state == ComposedRead.COMPLETENESS_PARTIAL
    assert 'contributor_composition_component:basis_lower_bound' in reads[partial_team].reason_codes
    assert 'roster_churn_component:transaction_window_uncovered' in reads[partial_team].reason_codes
    assert reads[conflict_team].completeness_state == ComposedRead.COMPLETENESS_CONFLICT
    assert 'contributor_composition_component:attribution_conflict' in reads[conflict_team].reason_codes
    assert reads[stale_team].completeness_state == ComposedRead.COMPLETENESS_UNKNOWN
    assert 'roster_churn_component:snapshot_stale' in reads[stale_team].reason_codes
    assert calendar_read.completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert calendar_read.component_summary['calendar_component']['state'] == ComposedRead.COMPLETENESS_CONFLICT
    completeness = _component(calendar_read, 'slate_data_completeness_component')
    assert completeness.evidence_citations == []
    completeness_text = ' '.join(
        list(completeness.reason_codes or []) + list(completeness.limitations or [])
    )
    assert not re.search(r'[%0-9]|\b(score|grade|rank|confidence)\b', completeness_text, re.I)


def test_roster_churn_language_negative_and_definition_wording():
    for text in ('thin staff', 'deep group', 'depth concern', 'roster shakeup', 'available arm', 'quality issue'):
        with pytest.raises(AssertionError):
            assert_roster_churn_content_allowed(text)
    service_text = (REPO_ROOT / 'backend/services/team_daily_read.py').read_text(encoding='utf-8')
    non_evidence_lines = [
        line for line in service_text.splitlines()
        if 'team_bullpen_' not in line
    ]
    assert not re.search(r'\bbullpen\b', '\n'.join(non_evidence_lines), re.I)
    assert 'appearance-evidenced set — not' in READ_DEFINITION
    assert 'Relief work is defined per game as pitching by pitchers who did not start that game.' in READ_DEFINITION


def test_team_daily_read_recompute_isolates_team_and_reliever_reads(app):
    with app.app_context():
        sync_run = _create_sync_run()
        team_id = 301
        reliever_team_id = 302
        team_pitcher = _pitcher(2301, team_id=team_id)
        reliever = _pitcher(2302, team_id=reliever_team_id)
        _snapshot(team_id, team_pitcher, sync_run_id=sync_run.id)
        _snapshot(reliever_team_id, reliever, sync_run_id=sync_run.id)
        team_basis, _, _ = _required_team_evidence(team_id, sync_run.id, suffix='recompute')
        reliever_workload = _evidence(
            'workload_window_appearances',
            evidence_type='workload_recovery_fact',
            pitcher=reliever,
            key='reliever-workload',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'workload_days_of_rest',
            evidence_type='workload_recovery_fact',
            pitcher=reliever,
            key='reliever-rest',
            sync_run_id=sync_run.id,
        )
        _evidence(
            'appearance_entry_context',
            evidence_type='appearance_context_fact',
            pitcher=reliever,
            key='reliever-appearance',
            sync_run_id=sync_run.id,
        )
        _game_log(reliever)
        build_team_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        build_reliever_daily_reads(PRODUCT_DATE, sync_run_id=sync_run.id)
        db.session.commit()
        team_read = ComposedRead.query.filter_by(read_type=READ_TYPE, subject_id=str(team_id)).one()
        reliever_read = ComposedRead.query.filter_by(read_type=RELIEVER_READ_TYPE, subject_id=str(reliever.id)).one()
        team_read_id = team_read.id
        reliever_read_id = reliever_read.id

        marked_team = mark_dependent_reads_for_recompute(
            evidence_object_ids=(team_basis.id,),
            reason_code='component_evidence_superseded',
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        rebuild_marked_team_daily_reads(sync_run_id=sync_run.id)
        db.session.commit()
        old_team_status = db.session.get(ComposedRead, team_read_id).recompute_status
        current_reliever_status = db.session.get(ComposedRead, reliever_read_id).recompute_status

        marked_reliever = mark_dependent_reads_for_recompute(
            evidence_object_ids=(reliever_workload.id,),
            reason_code='component_evidence_superseded',
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        team_noop = rebuild_marked_team_daily_reads(sync_run_id=sync_run.id)
        db.session.commit()
        still_marked_reliever_status = db.session.get(ComposedRead, reliever_read_id).recompute_status

    assert marked_team == {'marked_count': 1, 'read_ids': [team_read_id]}
    assert old_team_status == ComposedRead.RECOMPUTE_SUPERSEDED
    assert current_reliever_status == ComposedRead.RECOMPUTE_CURRENT
    assert marked_reliever == {'marked_count': 1, 'read_ids': [reliever_read_id]}
    assert team_noop == {'status': 'noop', 'reads_rebuilt': 0, 'dates_rebuilt': []}
    assert still_marked_reliever_status == ComposedRead.RECOMPUTE_NEEDED


def test_phase0e_sync_stage_team_failure_is_fail_soft_after_reliever(monkeypatch, app):
    from services import sync as sync_service

    calls = []

    def _reliever_build(*args, **kwargs):
        calls.append('reliever')
        return {'status': 'built', 'reads_built': 1}

    def _reliever_rebuild(*args, **kwargs):
        return {'status': 'noop', 'reads_rebuilt': 0}

    def _team_rebuild(*args, **kwargs):
        return {'status': 'noop', 'reads_rebuilt': 0}

    def _team_build(*args, **kwargs):
        calls.append('team')
        raise RuntimeError('test team read failure')

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

        monkeypatch.setenv('PHASE0E_READ_BUILD', 'true')
        import services.reliever_daily_read as reliever_daily_read_service
        import services.team_daily_read as team_daily_read_service

        monkeypatch.setattr(reliever_daily_read_service, 'build_reliever_daily_reads', _reliever_build)
        monkeypatch.setattr(reliever_daily_read_service, 'rebuild_marked_reliever_daily_reads', _reliever_rebuild)
        monkeypatch.setattr(team_daily_read_service, 'build_team_daily_reads', _team_build)
        monkeypatch.setattr(team_daily_read_service, 'rebuild_marked_team_daily_reads', _team_rebuild)
        result = sync_service._safe_build_composed_reads_stage(
            [PRODUCT_DATE],
            sync_run_id=sync_run_id,
            source='test',
        )
        failure = SyncFailure.query.one()

    assert calls == ['reliever', 'team']
    assert result['status'] == 'partial'
    assert result['reliever']['status'] == 'built'
    assert result['team']['status'] == 'failed'
    assert failure.entity_type == sync_service.COMPOSED_READ_FAILURE_ENTITY_TYPE
    assert failure.payload['read_type'] == READ_TYPE


def test_build_composed_reads_script_keeps_flags_and_mentions_both_read_types():
    source = (REPO_ROOT / 'backend/scripts/build_composed_reads.py').read_text(encoding='utf-8')
    assert 'build_reliever_daily_reads' in source
    assert 'build_team_daily_reads' in source
    from scripts.build_composed_reads import _parse_args

    args = _parse_args(['--date', PRODUCT_DATE.isoformat(), '--source', 'manual'])
    assert args.product_date == PRODUCT_DATE.isoformat()
    assert args.source == 'manual'


def test_public_surfaces_do_not_import_team_daily_read_or_composed_reads():
    blocked_references = (
        'team_daily_read',
        'build_team_daily_reads',
        'ComposedRead',
        'composed_reads',
        'team_daily_read',
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


def _invalid_team_registry(allowed_evidence_types, *, component_name='roster_churn_component'):
    registry = ReadTypeRegistry()
    registry.register(ReadType(
        read_type='team_daily_read_test_only',
        read_version=1,
        subject_type=ComposedRead.SUBJECT_TEAM_DAY,
        plain_language_definition=(
            'Test-only read bundles team evidence and does not conclude state.'
        ),
        classification=EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
        components=(
            ComponentSpec(
                name=component_name,
                required=True,
                allowed_evidence_types=tuple(allowed_evidence_types),
                plain_language_definition='Test-only component.',
            ),
        ),
    ))
    return registry
