from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.sync_run import SyncRun
from services.evidence_contract import (
    EvidenceBuildError,
    EvidenceCitationInput,
    build_evidence_object,
    mark_dependent_evidence_for_recompute,
)
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleNotRegistered,
    EvidenceRuleRegistry,
    claim_template_registry,
    evidence_rule_registry,
)
from services.source_correction_policies import (
    correction_policy,
    validate_correction_sensitive_model,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_PAYLOAD_SURFACES = (
    REPO_ROOT / 'backend/api/bullpen.py',
    REPO_ROOT / 'backend/services/dashboard_snapshot.py',
    REPO_ROOT / 'backend/services/bullpen_board.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
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


def _rule_registry():
    registry = EvidenceRuleRegistry()
    registry.register(_dummy_rule())
    return registry


def _dummy_rule(**overrides):
    payload = {
        'rule_id': 'test_only_pitch_count_observation',
        'rule_version': 1,
        'evidence_type': 'test_only_observation',
        'plain_language_definition': (
            'Test-only rule records the cited game-log pitch count when the '
            'game_logs source family is ready and the cited value is present.'
        ),
        'required_input_families': ('game_logs',),
        'required_cited_fields': ('game_logs.pitches_thrown',),
    }
    payload.update(overrides)
    return EvidenceRule(**payload)


def _claim_template(text=None):
    return ClaimTemplate(
        template_id='test_only_pitch_count_claim',
        template_version=1,
        template_text=text or (
            'Cited final game log records {pitches} pitches for {pitcher_name}.'
        ),
    )


def _create_sync_run(*, source='phase0d_test'):
    run = SyncRun(
        job_name='phase0d_evidence_contract_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source=source,
    )
    db.session.add(run)
    db.session.flush()
    return run


def _citation(row_id=99, value=18, role='supporting_input', sync_run_id=None):
    return EvidenceCitationInput(
        source_family='game_logs',
        source_table='game_logs',
        source_pk=row_id,
        source_field_names=('pitches_thrown',),
        citation_role=role,
        cited_values={'pitches_thrown': value},
        provenance={
            'source': 'game_logs',
            'sync_run_id': sync_run_id,
            'first_seen_at': '2026-07-04T12:00:00',
        },
    )


def _ready_payload(status='ready'):
    return {
        'families': {
            'game_logs': {
                'status': status,
                'reason_codes': [] if status == 'ready' else ['source_stale'],
                'coverage': {},
                'details': {},
            }
        }
    }


def _build_complete(
    subject_id=42,
    row_id=99,
    registry=None,
    rule_version=None,
    sync_run_id=None,
):
    return build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        rule_version=rule_version,
        claim_template=_claim_template(),
        claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=subject_id,
        product_date=date(2026, 7, 4),
        cited_inputs=(_citation(row_id=row_id, sync_run_id=sync_run_id),),
        computation_trace={
            'steps': ['Read cited game_logs.pitches_thrown.', 'Rendered test-only claim.'],
            'notes': ['No production evidence family registered.'],
        },
        input_values={'game_logs.pitches_thrown': 18},
        readiness_payload=_ready_payload(),
        registry=registry or _rule_registry(),
        sync_run_id=sync_run_id,
    )


def test_global_registries_do_not_ship_production_evidence_rules():
    assert evidence_rule_registry.all_rules() == ()
    assert claim_template_registry._templates == {}


def test_evidence_contract_round_trip_claim_citations_trace_posture_and_provenance(app):
    with app.app_context():
        sync_run = _create_sync_run()
        evidence = _build_complete(sync_run_id=sync_run.id)
        db.session.add(evidence)
        db.session.commit()

        stored = EvidenceObject.query.one()
        payload = stored.to_dict()
        sync_run_id = sync_run.id

    assert payload['evidence_type'] == 'test_only_observation'
    assert payload['subject_type'] == 'pitcher'
    assert payload['subject_id'] == '42'
    assert payload['product_date'] == '2026-07-04'
    assert payload['rendered_claim'] == 'Cited final game log records 18 pitches for Test Pitcher.'
    assert payload['rule_id'] == 'test_only_pitch_count_observation'
    assert payload['rule_version'] == 1
    assert payload['completeness_state'] == EvidenceObject.COMPLETENESS_COMPLETE
    assert payload['posture'] == EvidenceObject.POSTURE_INTERNAL_ONLY
    assert payload['source'] == 'phase0d:evidence_contract'
    assert payload['sync_run_id'] == sync_run_id
    assert payload['typed_cited_inputs'][0]['source_table'] == 'game_logs'
    assert payload['computation_trace']['steps'][0] == 'Read cited game_logs.pitches_thrown.'
    assert payload['citations'][0]['provenance']['source'] == 'game_logs'
    assert payload['citations'][0]['provenance']['sync_run_id'] == sync_run_id
    assert 'score' not in payload
    assert EvidenceCitation.query.count() == 1


def test_registered_dummy_rule_can_emit_and_unregistered_rule_cannot_emit():
    evidence = _build_complete()
    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE

    with pytest.raises(EvidenceRuleNotRegistered):
        build_evidence_object(
            rule_id='missing_rule',
            claim_template=_claim_template(),
            claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
            subject_type='pitcher',
            subject_id=42,
            product_date=date(2026, 7, 4),
            cited_inputs=(_citation(),),
            computation_trace={'steps': ['Attempted missing rule.']},
            input_values={'game_logs.pitches_thrown': 18},
            readiness_payload=_ready_payload(),
            registry=EvidenceRuleRegistry(),
        )


def test_rule_version_changes_are_visible_in_evidence_identity():
    registry = EvidenceRuleRegistry()
    registry.register(_dummy_rule(rule_version=1))
    registry.register(_dummy_rule(
        rule_version=2,
        plain_language_definition=(
            'Test-only version two rule records the cited game-log pitch count '
            'when the game_logs source family is ready and the cited value is present.'
        ),
    ))

    first = _build_complete(registry=registry, rule_version=1)
    second = build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        rule_version=2,
        claim_template=_claim_template(),
        claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=42,
        product_date=date(2026, 7, 4),
        cited_inputs=(_citation(),),
        computation_trace={'steps': ['Rendered version two test-only claim.']},
        input_values={'game_logs.pitches_thrown': 18},
        readiness_payload=_ready_payload(),
        registry=registry,
    )

    assert first.rule_version == 1
    assert second.rule_version == 2
    assert first.evidence_key != second.evidence_key
    assert first.rule_definition_hash != second.rule_definition_hash


def test_rule_without_plain_language_definition_fails_registration():
    with pytest.raises(EvidenceRuleError):
        EvidenceRuleRegistry().register(_dummy_rule(plain_language_definition=''))


def test_threshold_values_must_appear_in_rule_definition():
    with pytest.raises(EvidenceRuleError):
        EvidenceRuleRegistry().register(_dummy_rule(thresholds={'minimum_pitches': 20}))


@pytest.mark.parametrize('template_text', [
    'Pitcher will be available tonight.',
    'Pitcher is healthy.',
    'Manager trusts this pitcher.',
    'Betting odds favor use tonight.',
    'Pitcher pressure score is green.',
    'Pitcher is the closer tonight.',
])
def test_claim_template_lint_blocks_forbidden_language(template_text):
    with pytest.raises(EvidenceLanguageError):
        ClaimTemplateRegistry().register(_claim_template(template_text))


def test_claim_template_lint_blocks_forbidden_rendered_values():
    with pytest.raises(EvidenceLanguageError):
        build_evidence_object(
            rule_id='test_only_pitch_count_observation',
            claim_template=_claim_template('Cited final game log records {status}.'),
            claim_values={'status': 'healthy'},
            subject_type='pitcher',
            subject_id=42,
            product_date=date(2026, 7, 4),
            cited_inputs=(_citation(),),
            computation_trace={'steps': ['Rendered unsafe value.']},
            input_values={'game_logs.pitches_thrown': 18},
            readiness_payload=_ready_payload(),
            registry=_rule_registry(),
        )


def test_unready_source_family_withholds_evidence_with_reason_code():
    evidence = build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        claim_template=_claim_template(),
        claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=42,
        product_date=date(2026, 7, 4),
        cited_inputs=(_citation(),),
        computation_trace={'steps': ['Checked readiness.']},
        input_values={'game_logs.pitches_thrown': 18},
        readiness_payload=_ready_payload(status='stale'),
        registry=_rule_registry(),
    )

    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_WITHHELD
    assert evidence.reason_codes == ['source_family_unready:game_logs']
    assert evidence.rendered_claim == 'Evidence withheld: required source family is not ready.'


def test_null_required_input_becomes_unknown_without_zero_imputation():
    evidence = build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        claim_template=_claim_template(),
        claim_values={'pitches': 0, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=42,
        product_date=date(2026, 7, 4),
        cited_inputs=(_citation(value=None),),
        computation_trace={'steps': ['Read null cited value.']},
        input_values={'game_logs.pitches_thrown': None},
        readiness_payload=_ready_payload(),
        registry=_rule_registry(),
    )

    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
    assert evidence.reason_codes == ['required_input_unknown:game_logs.pitches_thrown']
    assert evidence.rendered_claim == 'Evidence unknown: required cited input is unavailable.'
    assert evidence.typed_cited_inputs[0]['cited_values']['pitches_thrown'] is None


def test_contradictory_inputs_become_conflict_with_both_sides_cited():
    evidence = build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        claim_template=_claim_template(),
        claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=42,
        product_date=date(2026, 7, 4),
        cited_inputs=(
            _citation(row_id=99, value=18, role='left_side'),
            _citation(row_id=100, value=22, role='right_side'),
        ),
        computation_trace={'steps': ['Compared cited rows.']},
        input_values={'game_logs.pitches_thrown': 18},
        readiness_payload=_ready_payload(),
        contradictions=({'left': 99, 'right': 100, 'reason': 'pitch_count_disagree'},),
        registry=_rule_registry(),
    )

    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_CONFLICT
    assert evidence.reason_codes == ['contradictory_inputs']
    assert evidence.rendered_claim == 'Evidence conflict: cited inputs disagree.'
    assert len(evidence.typed_cited_inputs) == 2


def test_uncleared_source_posture_withholds_evidence():
    evidence = build_evidence_object(
        rule_id='test_only_pitch_count_observation',
        claim_template=_claim_template(),
        claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
        subject_type='pitcher',
        subject_id=42,
        product_date=date(2026, 7, 4),
        cited_inputs=(_citation(),),
        computation_trace={'steps': ['Checked source posture.']},
        input_values={'game_logs.pitches_thrown': 18},
        readiness_payload=_ready_payload(),
        source_posture='needs_legal_review',
        registry=_rule_registry(),
    )

    assert evidence.completeness_state == EvidenceObject.COMPLETENESS_WITHHELD
    assert evidence.reason_codes == ['source_posture_uncleared']


def test_correction_policy_registration_covers_evidence_contract_models():
    assert validate_correction_sensitive_model(EvidenceObject)
    assert validate_correction_sensitive_model(EvidenceCitation)
    assert correction_policy('evidence_object_corrections').source_family == (
        'phase0d_evidence_contract'
    )
    assert correction_policy('evidence_citation_corrections').source_family == (
        'phase0d_evidence_contract'
    )


def test_upstream_correction_marks_dependent_evidence_for_bounded_recompute(app):
    with app.app_context():
        initial_run = _create_sync_run()
        first = _build_complete(subject_id=1, row_id=55, sync_run_id=initial_run.id)
        second = _build_complete(subject_id=2, row_id=55, sync_run_id=initial_run.id)
        db.session.add_all([first, second])
        db.session.commit()
        first_correction_run = _create_sync_run(source='phase0d_test_correction_one')
        second_correction_run = _create_sync_run(source='phase0d_test_correction_two')

        first_batch = mark_dependent_evidence_for_recompute(
            source_table='game_logs',
            source_pk=55,
            reason_code='game_log_corrected',
            batch_size=1,
            sync_run_id=first_correction_run.id,
        )
        second_batch = mark_dependent_evidence_for_recompute(
            source_table='game_logs',
            source_pk=55,
            reason_code='game_log_corrected',
            batch_size=1,
            sync_run_id=second_correction_run.id,
        )
        rows = EvidenceObject.query.order_by(EvidenceObject.id.asc()).all()

    assert first_batch['marked_count'] == 1
    assert second_batch['marked_count'] == 1
    assert {row.recompute_status for row in rows} == {EvidenceObject.RECOMPUTE_NEEDED}
    assert rows[0].recompute_reason_codes == ['game_log_corrected']
    assert rows[0].invalidated_by_source_table == 'game_logs'
    assert rows[0].invalidated_by_source_pk == '55'
    assert rows[0].correction_count == 1


def test_test_only_dummy_rule_lifecycle_emit_degrade_and_recompute_path(app):
    with app.app_context():
        sync_run = _create_sync_run()
        complete = _build_complete(subject_id=9, row_id=909, sync_run_id=sync_run.id)
        db.session.add(complete)
        db.session.commit()

        withheld = build_evidence_object(
            rule_id='test_only_pitch_count_observation',
            claim_template=_claim_template(),
            claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
            subject_type='pitcher',
            subject_id=10,
            product_date=date(2026, 7, 4),
            cited_inputs=(_citation(row_id=910, sync_run_id=sync_run.id),),
            computation_trace={'steps': ['Readiness degraded in test-only path.']},
            input_values={'game_logs.pitches_thrown': 18},
            readiness_payload=_ready_payload(status='unavailable'),
            registry=_rule_registry(),
            sync_run_id=sync_run.id,
        )
        db.session.add(withheld)
        db.session.commit()

        marked = mark_dependent_evidence_for_recompute(
            source_table='game_logs',
            source_pk=909,
            reason_code='test_only_source_correction',
            batch_size=10,
        )
        complete_state = complete.completeness_state
        withheld_state = withheld.completeness_state
        marked_count = marked['marked_count']

    assert complete_state == EvidenceObject.COMPLETENESS_COMPLETE
    assert withheld_state == EvidenceObject.COMPLETENESS_WITHHELD
    assert marked_count == 1


def test_evidence_tables_and_services_are_not_consumed_by_public_surfaces():
    blocked_references = (
        'EvidenceObject',
        'EvidenceCitation',
        'evidence_objects',
        'evidence_citations',
        'services.evidence_contract',
        'services.evidence_rules',
    )

    for path in PUBLIC_PAYLOAD_SURFACES:
        text = path.read_text(encoding='utf-8')
        for reference in blocked_references:
            assert reference not in text, f'{reference} leaked into {path}'


def test_phase0d_docs_record_contract_language_and_public_isolation():
    readme = (REPO_ROOT / 'docs/phase0d/README.md').read_text(encoding='utf-8')
    language = (REPO_ROOT / 'docs/phase0d/language_rules.md').read_text(
        encoding='utf-8'
    )
    contract = (REPO_ROOT / 'docs/phase0d/evidence_contract.md').read_text(
        encoding='utf-8'
    )

    assert '0D-01: evidence contract and language rules.' in readme
    assert 'All 0D output remains internal-only during Phase 0D.' in readme
    assert 'No public IL flag' in language
    assert 'official role-title assertions' in language
    assert 'does not contain a generic score, grade, rank, or color field' in contract
    assert 'Public' in contract
    assert 'What Changed' in contract


def test_evidence_requires_citations_with_provenance():
    missing_provenance = EvidenceCitationInput(
        source_family='game_logs',
        source_table='game_logs',
        source_pk=1,
        source_field_names=('pitches_thrown',),
        cited_values={'pitches_thrown': 18},
        provenance={},
    )

    with pytest.raises(EvidenceBuildError):
        build_evidence_object(
            rule_id='test_only_pitch_count_observation',
            claim_template=_claim_template(),
            claim_values={'pitches': 18, 'pitcher_name': 'Test Pitcher'},
            subject_type='pitcher',
            subject_id=42,
            product_date=date(2026, 7, 4),
            cited_inputs=(missing_provenance,),
            computation_trace={'steps': ['Missing provenance.']},
            input_values={'game_logs.pitches_thrown': 18},
            readiness_payload=_ready_payload(),
            registry=_rule_registry(),
        )
