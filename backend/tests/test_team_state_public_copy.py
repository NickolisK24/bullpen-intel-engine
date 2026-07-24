"""SC-04B — canonical public vocabulary, deterministic copy authority, evidence
display contract, copy guard, versioned public copy, and the version-aware public
read (including the Arizona production-shaped fixture and the medium fixture).

All copy is deterministic and backend-owned: identical governed input produces
byte-identical public copy, no AI or external language service is used, internal
Team Operations codes never reach public prose, and the banned-language guard
fails closed before an artifact is built.
"""

from datetime import date, datetime

import pytest
from flask import Flask

import models.share_artifact  # noqa: F401  (registers ORM immutability listeners)
from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
from services import team_state_public_copy as copy_module
from services import team_state_public_vocabulary as vocab
from services.share_artifact_public import load_public_share_artifact
from services.share_artifacts import (
    build_share_artifact_draft,
    publish_share_artifact,
    verify_share_artifact_integrity,
)
from services.team_state_eligibility import TEAM_STATE_V1
from services.team_state_payload import (
    TEAM_STATE_V1_1,
    build_team_state_payload,
)
from services.team_state_public_copy import build_public_copy
from services.team_state_public_vocabulary import (
    PublicCopyGuardError,
    UnmappedTeamStateError,
)
from services.team_state_source import TeamStateSnapshotAuthority, TeamStateSource
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TEAM_ID = 109
SNAPSHOT_ID = 7001

# Arizona production-shaped constraints: constrained availability, partial active-
# bullpen coverage, incomplete handedness, elevated recent workload.
ARIZONA_CONSTRAINTS = [
    {'constraint_id': 'availability_constrained', 'category': 'availability',
     'severity': 'caution', 'affected_area': 'availability_distribution', 'count': 2,
     'message': 'Availability distribution contains constrained inventory.'},
    {'constraint_id': 'coverage_partial', 'category': 'coverage', 'severity': 'caution',
     'affected_area': 'coverage_inventory', 'count': 1,
     'message': 'Some active pitcher records have incomplete readiness evidence.'},
    {'constraint_id': 'handedness_partial', 'category': 'coverage',
     'severity': 'informational', 'affected_area': 'handedness_coverage', 'count': 1,
     'message': 'Some active pitcher records are missing throwing-hand data.'},
    {'constraint_id': 'workload_elevated', 'category': 'workload', 'severity': 'caution',
     'affected_area': 'workload_pressure', 'count': 3,
     'message': 'Elevated team-level workload pressure is present.'},
]


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


# ---------------------------------------------------------------------------
# Governed input builders
# ---------------------------------------------------------------------------


def _readiness(
    *, status_code='operationally_stressed', confidence='high', data_state='fresh',
    freshness_state='current', team_name='Arizona Diamondbacks', team_abbreviation='AZ',
    constraints=None, limitations=None, active_bullpen_coverage=None,
):
    trust_metadata = {
        'confidence': confidence, 'confidence_reasons': [], 'data_state': data_state,
        'source_evidence_state': 'complete', 'governance_state': 'compliant',
        'generated_at': '2026-07-23T12:00:00Z',
        'limitations': list(limitations or []), 'explanations': [], 'refusal_reasons': [],
        'trust_validation_errors': [], 'ranking_applied': False, 'selection_made': False,
    }
    if active_bullpen_coverage is not None:
        trust_metadata['active_bullpen_coverage'] = active_bullpen_coverage
    return {
        'capability': 'team_operations_bullpen_readiness',
        'scope': 'team_bullpen_readiness',
        'contract': 'team_operations_bullpen_readiness_api_contract',
        'contract_version': 'v3_phase_4', 'contract_state': 'degraded',
        'ranking_applied': False, 'selection_made': False,
        'generated_at': '2026-07-23T12:00:00Z',
        'team': {'team_id': TEAM_ID, 'team_name': team_name, 'team_abbreviation': team_abbreviation},
        'readiness': {
            'status': 'Operationally Stressed', 'status_code': status_code,
            'summary': 'Team-level bullpen readiness is stressed by current workload or availability constraints.',
            'basis': [],
        },
        'constraints': constraints if constraints is not None else list(ARIZONA_CONSTRAINTS),
        'trust_metadata': trust_metadata,
        'freshness': {
            'freshness_state': freshness_state, 'data_through': '2026-07-23',
            'latest_workload_date': '2026-07-23', 'last_successful_sync': '2026-07-23T11:00:00Z',
            'latest_sync_status': 'success', 'latest_fatigue_calculated_at': '2026-07-23T11:30:00Z',
            'generated_at': '2026-07-23T12:00:00Z', 'stale_warning': None,
            'missing_data_warning': None, 'limitations': [],
        },
        'fail_closed': {'failed_closed': False, 'state': 'degraded_safe_output'},
        'refusal': {'refused': False},
    }


def _authority(*, snapshot_id=SNAPSHOT_ID, sync_run_id=None):
    return TeamStateSnapshotAuthority(
        snapshot_id=snapshot_id, sync_run_id=sync_run_id, data_through=date(2026, 7, 23),
        published_at=datetime(2026, 7, 23, 13, 0, 0), unavailable_reason=None,
    )


def _source(*, readiness=None, snapshot=None):
    return TeamStateSource(
        team_id=TEAM_ID, team_valid=True,
        snapshot=snapshot if snapshot is not None else _authority(),
        readiness=readiness if readiness is not None else _readiness(),
        requested_date=None,
    )


def _publish(payload):
    kwargs = payload.to_share_artifact_kwargs()
    draft = build_share_artifact_draft(session=db.session, **kwargs)
    artifact = publish_share_artifact(draft, dedup=True, session=db.session)
    db.session.commit()
    return artifact


# ===========================================================================
# Workstream A — public state vocabulary
# ===========================================================================


def test_state_mapping_is_exactly_fresh_stretched_vulnerable():
    assert vocab.public_state_for('operationally_stable') == {
        'public_code': 'fresh', 'public_label': 'Fresh'}
    assert vocab.public_state_for('operationally_constrained') == {
        'public_code': 'stretched', 'public_label': 'Stretched'}
    assert vocab.public_state_for('operationally_stressed') == {
        'public_code': 'vulnerable', 'public_label': 'Vulnerable'}


def test_data_limited_and_refused_have_no_public_state():
    assert vocab.is_publishable_state('data_limited') is False
    assert vocab.is_publishable_state('refused') is False
    with pytest.raises(UnmappedTeamStateError):
        vocab.public_state_for('data_limited')
    with pytest.raises(UnmappedTeamStateError):
        vocab.public_state_for('refused')


def test_unmapped_state_fails_closed():
    with pytest.raises(UnmappedTeamStateError):
        vocab.public_state_for('something_new')


def test_no_fourth_public_team_state():
    assert set(vocab.PUBLIC_STATE_LABELS) == {'fresh', 'stretched', 'vulnerable'}
    assert set(vocab.INTERNAL_TO_PUBLIC_STATE) == {
        'operationally_stable', 'operationally_constrained', 'operationally_stressed'}


def test_public_labels_are_not_title_cased_enums():
    # An internal code title-cased would be "Operationally Stressed", never a
    # public label; the map yields the canonical dictionary word instead.
    for code, label in vocab.PUBLIC_STATE_LABELS.items():
        assert '_' not in label
        assert label in ('Fresh', 'Stretched', 'Vulnerable')


# ===========================================================================
# Workstream B/C/D — deterministic copy authority
# ===========================================================================


def _arizona_copy():
    return build_public_copy(
        team_name='Arizona Diamondbacks', team_abbreviation='AZ',
        status_code='operationally_stressed', confidence='high',
        constraints=ARIZONA_CONSTRAINTS, limitations=[], active_bullpen_coverage=None,
        product_date='2026-07-23',
    )


def test_identical_input_produces_byte_identical_copy():
    a = _arizona_copy()
    b = _arizona_copy()
    assert a == b
    import json
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_copy_authority_uses_no_ai_or_external_language_service():
    import inspect
    src = inspect.getsource(copy_module) + inspect.getsource(vocab)
    lowered = src.lower()
    for banned in ('openai', 'anthropic', 'requests.', 'httpx', 'http://', 'https://',
                   'llm', 'gpt', 'random.', 'chatcompletion'):
        assert banned not in lowered, f'copy authority must not reference {banned}'


def test_headline_uses_approved_public_vocabulary():
    copy = _arizona_copy()
    assert copy['headline'] == 'Arizona Diamondbacks bullpen — Vulnerable'
    assert 'Vulnerable' in copy['headline']


def test_why_names_a_baseball_cause_without_internal_language():
    copy = _arizona_copy()
    why = copy['why']
    assert 'workload' in why and 'clean options' in why
    assert 'Vulnerable' not in why  # never repeats the state label
    for banned in ('team-level', 'readiness', 'constrained inventory', 'status_code',
                   'data_state', 'availability_distribution'):
        assert banned.lower() not in why.lower()


def test_alt_text_follows_state_why_evidence_freshness():
    copy = _arizona_copy()
    alt = copy['alt_text']
    assert alt.startswith('Arizona Diamondbacks bullpen is Vulnerable.')
    assert 'Evidence:' in alt
    assert 'Data through July 23, 2026' in alt


def test_platform_neutral_description_is_deterministic_and_readable():
    copy = _arizona_copy()
    assert copy['description'] == build_public_copy(
        team_name='Arizona Diamondbacks', team_abbreviation='AZ',
        status_code='operationally_stressed', confidence='high',
        constraints=ARIZONA_CONSTRAINTS, product_date='2026-07-23',
    )['description']
    assert 'BaseballOS' in copy['description']


def test_state_specific_why_templates():
    fresh = build_public_copy(team_name='Test Club', team_abbreviation='TST',
                              status_code='operationally_stable', confidence='high',
                              constraints=[], product_date='2026-07-23')
    assert 'full set of clean options' in fresh['why']
    stretched = build_public_copy(
        team_name='Test Club', team_abbreviation='TST',
        status_code='operationally_constrained', confidence='high',
        constraints=[{'constraint_id': 'workload_elevated', 'category': 'workload',
                      'affected_area': 'workload_pressure', 'severity': 'caution', 'count': 2}],
        product_date='2026-07-23')
    assert 'narrowed' in stretched['why']


# ===========================================================================
# Workstream E — evidence display contract
# ===========================================================================


def test_every_evidence_family_has_a_reader_facing_label_no_enum():
    copy = _arizona_copy()
    labels = [item['label'] for item in copy['evidence']]
    assert labels == [
        'Available bullpen options', 'Active bullpen coverage',
        'Bullpen handedness', 'Recent bullpen workload',
    ]
    for item in copy['evidence']:
        assert '_' not in item['label']
        assert '_' not in item['detail']
        assert item['detail']  # a concrete reader-facing fact


def test_evidence_details_preserve_governed_counts():
    copy = _arizona_copy()
    details = {item['evidence_id']: item['detail'] for item in copy['evidence']}
    assert '2 relievers are limited or unavailable.' == details['availability_constrained']
    assert '3 relievers are carrying elevated recent workload.' == details['workload_elevated']
    assert '1 active reliever is missing throwing-hand data.' == details['handedness_partial']


def test_unknown_evidence_family_uses_generic_label_without_leaking_enum():
    label = vocab.evidence_display_label('some_new_internal_family', 'mystery')
    assert label == vocab.GENERIC_EVIDENCE_LABEL
    assert '_' not in label


def test_evidence_order_is_canonical():
    copy = _arizona_copy()
    assert [i['evidence_id'] for i in copy['evidence']] == [
        'availability_constrained', 'coverage_partial', 'handedness_partial', 'workload_elevated']


# ===========================================================================
# Workstream F — public copy guard fails closed before publication
# ===========================================================================


def test_guard_rejects_banned_language_and_snake_case():
    with pytest.raises(PublicCopyGuardError):
        vocab.guard_public_copy({'headline': 'Operational inventory is constrained'})
    with pytest.raises(PublicCopyGuardError):
        vocab.guard_public_copy({'why': 'workload_pressure is elevated'})
    with pytest.raises(PublicCopyGuardError):
        vocab.guard_public_copy({'evidence': [{'label': 'ok', 'detail': 'team-level readiness note'}]})


def test_guard_allows_clean_baseball_copy():
    # No exception for legitimate baseball language.
    vocab.guard_public_copy(_arizona_copy())


def test_guard_does_not_over_ban_ordinary_baseball_words():
    # "leverage" and "edge" are legitimate; only the banned phrases/words trip.
    vocab.guard_public_copy({'why': 'A high-leverage arm has an edge in the eighth.'})


# ===========================================================================
# Workstream G — versioning + immutability
# ===========================================================================


def test_v1_1_payload_stamps_version_and_carries_public_copy():
    payload = build_team_state_payload(_source(), version=TEAM_STATE_V1_1)
    assert payload.payload_version == TEAM_STATE_V1_1
    assert payload.document['payload_version'] == TEAM_STATE_V1_1
    public_copy = payload.document['public_copy']
    assert public_copy['state'] == {'public_code': 'vulnerable', 'public_label': 'Vulnerable'}
    assert payload.document['team_state']['public_state'] == public_copy['state']


def test_v1_0_payload_still_builds_unchanged():
    payload = build_team_state_payload(_source(), version=TEAM_STATE_V1)
    assert payload.payload_version == TEAM_STATE_V1
    assert 'public_copy' not in payload.document


def test_meaning_bearing_copy_participates_in_equivalence(app):
    # Two sources whose ONLY difference is a copy-affecting governed input
    # (status_code -> public state + why) must not be equivalent.
    stressed = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stressed')), version=TEAM_STATE_V1_1)
    stable = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stable', constraints=[])), version=TEAM_STATE_V1_1)
    a = build_share_artifact_draft(session=db.session, **stressed.to_share_artifact_kwargs())
    b = build_share_artifact_draft(session=db.session, **stable.to_share_artifact_kwargs())
    assert a.equivalence_key != b.equivalence_key


def test_equivalent_revised_requests_reuse(app):
    first = _publish(build_team_state_payload(_source(), version=TEAM_STATE_V1_1))
    payload2 = build_team_state_payload(_source(), version=TEAM_STATE_V1_1)
    draft2 = build_share_artifact_draft(session=db.session, **payload2.to_share_artifact_kwargs())
    assert draft2.equivalence_key == first.equivalence_key


def test_legacy_and_revised_versions_both_load_and_verify(app):
    revised = _publish(build_team_state_payload(_source(), version=TEAM_STATE_V1_1))
    assert verify_share_artifact_integrity(revised) is True
    legacy = _publish(build_team_state_payload(
        _source(snapshot=_authority(snapshot_id=9002)), version=TEAM_STATE_V1))
    assert verify_share_artifact_integrity(legacy) is True
    assert load_public_share_artifact(revised.public_id).is_ok
    assert load_public_share_artifact(legacy.public_id).is_ok


# ===========================================================================
# Workstream H — Arizona production-shaped fixture (end to end)
# ===========================================================================


def test_arizona_fixture_public_read_is_baseball_native(app):
    artifact = _publish(build_team_state_payload(_source(), version=TEAM_STATE_V1_1))
    result = load_public_share_artifact(artifact.public_id)
    assert result.is_ok
    view = result.view

    assert view['team_state']['public_label'] == 'Vulnerable'
    assert view['payload_version'] == TEAM_STATE_V1_1
    assert view['revised'] is True

    # Baseball-native, no internal engine language anywhere public.
    public_blob = ' '.join([
        view['copy']['headline'] or '', view['copy']['why'] or '',
        ' '.join(f"{e['label']} {e['detail']}" for e in view['evidence']),
        ' '.join(view['limitations']),
    ]).lower()
    for banned in ('operationally stressed', 'team-level bullpen readiness',
                   'constrained inventory', 'availability_distribution',
                   'coverage_inventory', 'workload_pressure', 'status_code'):
        assert banned not in public_blob

    # Four governed evidence facts remain, reader-facing.
    assert len(view['evidence']) == 4
    assert [e['label'] for e in view['evidence']] == [
        'Available bullpen options', 'Active bullpen coverage',
        'Bullpen handedness', 'Recent bullpen workload']

    # High confidence, empty limitations omitted.
    assert view['trust']['confidence'] == 'high'
    assert view['limitations'] == []


def test_arizona_fixture_integrity_and_reuse(app):
    first = _publish(build_team_state_payload(_source(), version=TEAM_STATE_V1_1))
    assert verify_share_artifact_integrity(first) is True
    # Equivalent rerun reuses (same equivalence key -> dedup to the same row).
    payload2 = build_team_state_payload(_source(), version=TEAM_STATE_V1_1)
    draft2 = build_share_artifact_draft(session=db.session, **payload2.to_share_artifact_kwargs())
    assert draft2.equivalence_key == first.equivalence_key


# ===========================================================================
# Workstream I — medium-confidence fixture
# ===========================================================================


def _medium_source():
    readiness = _readiness(
        status_code='operationally_constrained', confidence='medium',
        team_name='Seattle Mariners', team_abbreviation='SEA',
        constraints=[{'constraint_id': 'workload_elevated', 'category': 'workload',
                      'severity': 'caution', 'affected_area': 'workload_pressure', 'count': 2,
                      'message': 'Elevated team-level workload pressure is present.'}],
        limitations=['Current readiness reflects 6 of 8 active bullpen pitchers; 2 have incomplete current workload records.'],
        active_bullpen_coverage={'active_bullpen_count': 8, 'usable_record_count': 6,
                                 'unresolved_record_count': 2},
    )
    return _source(readiness=readiness)


def test_medium_fixture_partial_coverage_is_disclosed_exactly(app):
    artifact = _publish(build_team_state_payload(_medium_source(), version=TEAM_STATE_V1_1))
    result = load_public_share_artifact(artifact.public_id)
    view = result.view

    assert view['trust']['confidence'] == 'medium'
    assert view['team_state']['public_label'] == 'Stretched'
    assert view['limitations'] == [
        'This read covers 6 of 8 active bullpen pitchers. Two current workload records remain incomplete.']
    # No unresolved pitcher described as available; no injury inference.
    blob = ' '.join(view['limitations']).lower()
    assert 'available' not in blob
    assert 'injur' not in blob
    # Immutable limitation data is preserved on the frozen document.
    stored = artifact.payload['trust']['limitations']
    assert any('6 of 8 active bullpen pitchers' in s for s in stored)


def test_medium_fixture_why_is_baseball_native(app):
    artifact = _publish(build_team_state_payload(_medium_source(), version=TEAM_STATE_V1_1))
    view = load_public_share_artifact(artifact.public_id).view
    assert 'narrowed' in view['copy']['why'].lower() or 'clean options' in view['copy']['why'].lower()
    assert 'team-level' not in view['copy']['why'].lower()


# ===========================================================================
# Version-aware legacy read — coded labels mapped, original claim preserved
# ===========================================================================


def test_legacy_read_maps_state_label_and_preserves_original_why(app):
    legacy = _publish(build_team_state_payload(_source(), version=TEAM_STATE_V1))
    view = load_public_share_artifact(legacy.public_id).view
    # Coded state label mapped for reader-facing presentation...
    assert view['team_state']['public_label'] == 'Vulnerable'
    assert view['revised'] is False
    # ...but the original stored claim is preserved verbatim (historical fidelity).
    assert view['team_state']['summary'] == (
        'Team-level bullpen readiness is stressed by current workload or availability constraints.')
    assert view['copy']['why'] == view['team_state']['summary']
    # Evidence labels are still reader-facing (version-aware presentation).
    assert 'Recent bullpen workload' in [e['label'] for e in view['evidence']]
