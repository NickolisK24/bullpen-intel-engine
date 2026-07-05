from datetime import date
from pathlib import Path
import re

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.player_transaction  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.sync_run  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.evidence_contract import EvidenceCitation, EvidenceObject
from services.evidence_classification import (
    CLASSIFICATION_ENTRIES,
    DECISION_REGISTER_CLASSIFICATIONS,
    EXPECTED_CLASSIFICATION_TALLIES,
    FULL_MISUSE_PREVENTION_TAGS,
    PERMANENTLY_INTERNAL_RULE_IDS,
    PUBLIC_CANDIDATE_GATES,
    EvidenceClassification,
    EvidenceClassificationEntry,
    EvidenceClassificationError,
    classification_tallies,
    phase0d_rule_registry,
    registered_phase0d_rule_ids,
    validate_evidence_classifications,
    validate_stored_evidence_integrity,
)
from services.evidence_rules import EvidenceRule
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
LANGUAGE_DOC = REPO_ROOT / 'docs/phase0d/public_language_rules.md'
DECISION_DOC = REPO_ROOT / 'docs/phase0d/decision_register.md'
PRODUCT_DATE = date(2026, 7, 4)


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


def test_registry_completeness_both_directions_and_future_rule_guard():
    registry, _ = phase0d_rule_registry()
    result = validate_evidence_classifications(registry=registry)
    assert result['rule_count'] == 64
    assert result['classified_count'] == 64
    assert set(registered_phase0d_rule_ids(registry)) == set(CLASSIFICATION_ENTRIES)

    registry.register(EvidenceRule(
        rule_id='test_only_future_rule_without_classification',
        rule_version=1,
        evidence_type='test_only_future_rule_without_classification',
        plain_language_definition='Test-only future rule requiring classification.',
        required_input_families=('test_family',),
        required_cited_fields=('test_family.field',),
    ))
    with pytest.raises(EvidenceClassificationError, match='missing classifications'):
        validate_evidence_classifications(registry=registry)


def test_classification_tallies_and_pi_set_exactness():
    tallies = classification_tallies()
    assert {
        key: tallies.get(key, 0)
        for key in EXPECTED_CLASSIFICATION_TALLIES
    } == EXPECTED_CLASSIFICATION_TALLIES
    assert tallies[EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE] == 43
    assert tallies[EvidenceClassification.ELIGIBLE_PUBLIC_CANDIDATE_LATER] == 9
    assert tallies[EvidenceClassification.INTERNAL_ONLY_FOR_NOW] == 4
    assert tallies[EvidenceClassification.PERMANENTLY_INTERNAL] == 8
    actual_pi = {
        rule_id
        for rule_id, entry in CLASSIFICATION_ENTRIES.items()
        if entry.classification == EvidenceClassification.PERMANENTLY_INTERNAL
    }
    assert actual_pi == PERMANENTLY_INTERNAL_RULE_IDS
    assert actual_pi == {
        'appearance_entry_band',
        'pitcher_entry_band_distribution',
        'appearance_entry_base_state',
        'team_active_reliever_count',
        'appearance_pbp_reconciliation',
        'team_transaction_alignment_state',
        'team_roster_snapshot_state',
        'appearance_inherited_entry_corroboration',
    }


def test_posture_immutability_and_no_public_candidate_fixture_rows(app):
    registry, _ = phase0d_rule_registry()
    assert all(
        rule.posture_default == EvidenceObject.POSTURE_INTERNAL_ONLY
        for rule in registry.all_rules()
    )
    source = _evidence('workload_last_final_appearance', key='source')
    db.session.add(source)
    db.session.flush()
    assert EvidenceObject.query.filter(
        EvidenceObject.posture != EvidenceObject.POSTURE_INTERNAL_ONLY
    ).count() == 0
    text = (REPO_ROOT / 'backend/services/evidence_classification.py').read_text(encoding='utf-8')
    assert 'POSTURE_PUBLIC_CANDIDATE' not in text


def test_enum_discipline_deferred_rejected_not_registered():
    for state in (EvidenceClassification.DEFERRED, EvidenceClassification.REJECTED):
        entries = dict(CLASSIFICATION_ENTRIES)
        entries['workload_days_of_rest'] = EvidenceClassificationEntry(
            rule_id='workload_days_of_rest',
            classification=state,
            rationale='test-only invalid state',
            preconditions=('test invalid',),
        )
        with pytest.raises(EvidenceClassificationError):
            validate_evidence_classifications(entries=entries)
    assert all(
        item.classification in {EvidenceClassification.DEFERRED, EvidenceClassification.REJECTED}
        for item in DECISION_REGISTER_CLASSIFICATIONS.values()
    )


def test_pc_el_entries_have_language_refs_gates_and_misuse_tags():
    anchors = _language_doc_anchors()
    for entry in CLASSIFICATION_ENTRIES.values():
        if entry.classification not in {
            EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE,
            EvidenceClassification.ELIGIBLE_PUBLIC_CANDIDATE_LATER,
        }:
            continue
        assert entry.required_language_ref
        assert entry.required_language_ref.startswith('docs/phase0d/public_language_rules.md#')
        assert entry.required_language_ref.rsplit('#', 1)[1] in anchors
        assert set(PUBLIC_CANDIDATE_GATES).issubset(entry.global_gates)
        assert set(entry.misuse_prevention_tags) == set(FULL_MISUSE_PREVENTION_TAGS)


def test_public_language_packages_and_claim_templates_reject_forbidden_terms():
    safe_text = _strip_forbidden_master_list(LANGUAGE_DOC.read_text(encoding='utf-8'))
    for term in ('available', 'pressure', 'leverage', 'workhorse', 'closer', 'score'):
        assert not re.search(rf'(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])', safe_text, re.I)
    with pytest.raises(AssertionError):
        _assert_public_package_language_allowed('this package says available')

    _, templates = phase0d_rule_registry()
    for template in templates._templates.values():
        _assert_public_package_language_allowed(template.template_text)


def test_black_box_audit_validates_rule_definitions_and_citation_resolution(app):
    source = _evidence('workload_last_final_appearance', key='source')
    dependent = _evidence('workload_days_of_rest', key='dependent')
    dependent.citations = [
        EvidenceCitation(
            source_family='phase0d_evidence_contract',
            source_table='evidence_objects',
            source_pk='1',
            source_field_names=['rule_id'],
            citation_role='supporting_input',
            cited_values={'rule_id': source.rule_id},
            provenance={'source': 'test'},
        )
    ]
    db.session.add_all([source, dependent])
    db.session.flush()
    dependent.citations[0].source_pk = str(source.id)
    db.session.flush()
    assert validate_stored_evidence_integrity() == {
        'evidence_rows_checked': 2,
        'citation_rows_checked': 1,
    }

    orphan = _evidence('unknown_rule_id', key='orphan')
    db.session.add(orphan)
    db.session.flush()
    with pytest.raises(EvidenceClassificationError, match='unknown_rule'):
        validate_stored_evidence_integrity()
    db.session.delete(orphan)
    db.session.flush()

    dependent.citations[0].source_pk = '999999'
    db.session.flush()
    with pytest.raises(EvidenceClassificationError, match='unresolved_source'):
        validate_stored_evidence_integrity()


def test_behavior_freeze_public_modules_do_not_import_or_reference_classification():
    public_paths = [
        REPO_ROOT / 'backend/api',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'frontend/src',
        REPO_ROOT / 'frontend/public',
    ]
    needles = (
        'evidence_classification',
        'EvidenceClassification',
        'PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE',
        'team_relief_contributor_basis',
        'team_relief_workload_concentration',
    )
    scanned = []
    for path in public_paths:
        if path.is_dir():
            files = [
                file for file in path.rglob('*')
                if file.is_file() and file.suffix in {'.py', '.js', '.jsx', '.ts', '.tsx', '.json'}
            ]
        elif path.exists():
            files = [path]
        else:
            files = []
        for file in files:
            scanned.append(file)
            text = file.read_text(encoding='utf-8', errors='ignore')
            assert not any(needle in text for needle in needles), str(file)
    assert scanned


def test_decision_register_lint_and_rule5_pin_reference():
    text = DECISION_DOC.read_text(encoding='utf-8')
    required = {
        'Reliever/Starter Partition': 'RESOLVED-REFUSED',
        'Base-State / Runners At Entry': 'RESOLVED-RATIFIED',
        'Bequeathed Traffic': 'DEFERRED',
        'Handedness Exposure': 'DEFERRED',
        'Opener/Bulk Patterns': 'DEFERRED permanently as a label',
        'Team-Level Entry-Band Aggregation': 'REJECTED',
        'Pressure/Leverage Vocabulary': 'REJECTED permanently',
        'Appearance Team-Attribution Method': 'RATIFIED',
        'Contributor-Set Vs Roster-Reliever Distinction': 'RATIFIED',
        '0D-04 Emission-Policy Coupling': 'RATIFIED',
    }
    for heading, state in required.items():
        assert f'### {heading}' in text
        assert f'State: {state}' in text
    assert 'test_rule5_emission_policy_pin_provably_neither_bucket' in text
    assert 'no per-inning clean/traffic granularity' in text
    assert 'no bequeathed traffic' in text
    assert 'no entry-band traffic axis' in text


def _evidence(rule_id, *, key):
    return EvidenceObject(
        evidence_key=f'test:{key}:{rule_id}',
        evidence_type=rule_id,
        subject_type='test',
        subject_id=key,
        subject_key=f'test:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id='test_claim',
        rendered_claim='Stored test evidence.',
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='test-hash',
        typed_cited_inputs=[],
        computation_trace={'steps': ['test']},
        completeness_state=EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='test',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )


def _language_doc_anchors():
    anchors = set()
    for line in LANGUAGE_DOC.read_text(encoding='utf-8').splitlines():
        if not line.startswith('## '):
            continue
        heading = line.strip('# ').strip()
        anchor = re.sub(r'[^a-z0-9 -]', '', heading.lower()).replace(' ', '-')
        anchors.add(anchor)
    return anchors


def _strip_forbidden_master_list(text):
    marker = '## Forbidden Master List'
    return text.split(marker, 1)[0]


def _assert_public_package_language_allowed(text):
    forbidden = ('available', 'pressure', 'leverage', 'workhorse', 'closer', 'score')
    for term in forbidden:
        if re.search(rf'(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])', text, re.I):
            raise AssertionError(f'forbidden language: {term}')
    return True
