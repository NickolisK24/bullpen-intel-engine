"""Incident artifact ingestion and evidence-artifact safety.

Requirements 31-40 (ingestion) and 107-117 (artifact safety).

Two properties matter most. First, evidence that is absent, truncated,
unparseable, or from the wrong run must be REPORTED as such — never quietly
treated as an empty but successful reading. Second, the document this audit
writes must never carry a raw payload, a completion proof, a credential, an
exception body, or the SQL text of its own probe.
"""

import json

import pytest

import scripts.run_postgame_publication_incident_audit as runner
import scripts.scan_forbidden_artifact_content as scanner
from services import postgame_publication_incident_audit as audit


SHADOW_DIGEST = (
    'sha256:7527ffef431e811379e1e149e4593039157f12f2c66694ac2bbfbd48bb6f4d1f'
)
LEDGER_DIGEST = (
    'sha256:71fecf0df910ee303566030cedc23ba6169a25a7d7673391c138451afd7d475e'
)

LEDGER_REPORT = """\
================================================================================

APPEARANCE LEDGER AUDIT

Window: 2026-07-25 .. 2026-08-03 (10 day(s))

Completed games expected:      133
Completed games represented:   132
Expected reliever appearances: 1110 (pitching lines seen by completed-game ingests; includes starters)
Stored appearances:            1110
Latest appearance mismatches:  9
Players affected:              9
  - Ben Peoples (687239, last stored: 2026-08-02)
  - Cal Quantrill (615698, last stored: 2026-07-28)
  - Keaton Winn (676775, last stored: 2026-08-01)
  - Logan Webb (657277, last stored: 2026-07-29)
  - Nolan Kingham (663884, last stored: never)
  - Peyton Gray (682608, last stored: 2026-08-01)
  - Reiver Sanmartin (665665, last stored: 2026-06-13)
  - Sam Hentges (656529, last stored: 2026-08-02)
  - Tristan Beck (663941, last stored: 2026-07-25)
Missing game_pks:              822867
Dates with holes:              2026-08-03 (5/6)

Publish eligible:

NO

Reasons: final_games_without_appearance_rows

================================================================================
"""


def _shadow(root, *, run_id='30873422601', cycle='postgame',
            head_sha=audit.INCIDENT_HEAD_SHA, slate='2026-08-03',
            exit_code=1, with_handoff=True):
    directory = root / audit.ARTIFACT_SHADOW
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'postgame-sync-summary.json').write_text(json.dumps({
        'status': 'success',
        'schedule_date': slate,
        'publication_proof': {
            'verified': False,
            'reason_codes': list(audit.INCIDENT_PUBLICATION_REASON_CODES),
        },
    }), encoding='utf-8')
    (directory / 'postgame-activation-summary.json').write_text(json.dumps({
        'result': 'PASS', 'cycle_kind': cycle, 'runner_exit_code': exit_code,
    }), encoding='utf-8')
    if with_handoff:
        handoff = root / audit.ARTIFACT_SHADOW_HANDOFF
        handoff.mkdir(parents=True, exist_ok=True)
        (handoff / 'handoff-metadata.json').write_text(json.dumps({
            'run_id': run_id, 'repository_sha': head_sha, 'cycle_kind': cycle,
        }), encoding='utf-8')
    return directory


def _ledger(root, text=LEDGER_REPORT):
    directory = root / audit.ARTIFACT_LEDGER_AUDIT
    directory.mkdir(parents=True, exist_ok=True)
    (directory / audit.LEDGER_REPORT_FILENAME).write_text(
        text, encoding='utf-8',
    )
    return directory


def _metadata(**overrides):
    metadata = {
        audit.ARTIFACT_SHADOW: {'digest': SHADOW_DIGEST},
        audit.ARTIFACT_LEDGER_AUDIT: {'digest': LEDGER_DIGEST},
    }
    metadata.update(overrides)
    return metadata


@pytest.fixture
def evidence(tmp_path):
    return tmp_path / 'incident-evidence'


# ── 31-40 Incident artifact ingestion ───────────────────────────────────────

def test_031_correct_incident_artifacts_parse(evidence):
    _shadow(evidence)
    _ledger(evidence)
    result = audit.ingest_incident_artifacts(
        evidence, observed_metadata=_metadata(),
    )
    assert result['all_required_present'] is True
    assert result['missing_required'] == []
    ledger = result['artifacts'][audit.ARTIFACT_LEDGER_AUDIT]['ledger_report']
    assert ledger['expected_games'] == 133
    assert ledger['missing_game_pks'] == [audit.INCIDENT_GAME_PK]
    assert len(ledger['player_mismatches']) == 9


def test_032_a_wrong_run_id_refuses(evidence):
    _shadow(evidence, run_id='99999999999')
    _ledger(evidence)
    result = audit.ingest_incident_artifacts(evidence)
    validation = result['incident_validation']
    assert 'run_id' in validation['mismatched_fields']
    assert validation['any_mismatch'] is True


def test_033_a_wrong_cycle_kind_refuses(evidence):
    _shadow(evidence, cycle='daily')
    _ledger(evidence)
    validation = audit.ingest_incident_artifacts(
        evidence
    )['incident_validation']
    assert 'cycle_kind' in validation['mismatched_fields']


def test_034_a_wrong_incident_sha_is_reported_from_observed_evidence(evidence):
    _shadow(evidence, head_sha='b' * 40)
    _ledger(evidence)
    validation = audit.ingest_incident_artifacts(
        evidence
    )['incident_validation']
    assert 'head_sha' in validation['mismatched_fields']

    # And when the SHA is simply not present, that is UNOBSERVED, not a
    # mismatch — absent evidence never manufactures a violation.
    absent = evidence.parent / 'absent'
    _shadow(absent, with_handoff=False)
    _ledger(absent)
    other = audit.ingest_incident_artifacts(absent)['incident_validation']
    assert 'head_sha' in other['unobserved_fields']
    assert other['any_mismatch'] is False


def test_035_a_wrong_game_id_refuses(evidence):
    _shadow(evidence)
    _ledger(evidence, LEDGER_REPORT.replace('822867', '111111'))
    validation = audit.ingest_incident_artifacts(
        evidence
    )['incident_validation']
    assert 'disputed_game_pk' in validation['mismatched_fields']


def test_036_a_missing_required_artifact_is_unproven(evidence):
    _shadow(evidence)
    result = audit.ingest_incident_artifacts(evidence)
    assert result['missing_required'] == [audit.ARTIFACT_LEDGER_AUDIT]
    decision = _decide(artifact_ingestion=result)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_REQUIRED_ARTIFACT_MISSING in (
        decision['unproven_reasons']
    )


def test_037_a_missing_optional_handoff_artifact_is_reported(evidence):
    _shadow(evidence, with_handoff=False)
    _ledger(evidence)
    result = audit.ingest_incident_artifacts(
        evidence, observed_metadata=_metadata(),
    )
    assert result['missing_optional'] == [audit.ARTIFACT_SHADOW_HANDOFF]
    assert result['all_required_present'] is True
    assert _decide(artifact_ingestion=result)['result'] != (
        audit.RESULT_UNPROVEN
    )


def test_038_a_digest_mismatch_is_failed(evidence):
    _shadow(evidence)
    _ledger(evidence)
    result = audit.ingest_incident_artifacts(
        evidence,
        observed_metadata=_metadata(**{
            audit.ARTIFACT_SHADOW: {'digest': 'sha256:' + '0' * 64},
        }),
    )
    assert result['digest_mismatches'] == [audit.ARTIFACT_SHADOW]
    decision = _decide(artifact_ingestion=result)
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_ARTIFACT_DIGEST_MISMATCH in decision['failed_reasons']


def test_039_raw_artifact_secrets_are_never_copied(evidence):
    _shadow(evidence)
    _ledger(evidence)
    directory = evidence / audit.ARTIFACT_SHADOW
    (directory / 'postgame-sync-summary.json').write_text(json.dumps({
        'status': 'success',
        'schedule_date': '2026-08-03',
        'DATABASE_URL': 'postgresql://user:pw@host/db',
        'publication_proof': {'verified': False, 'reason_codes': []},
    }), encoding='utf-8')
    result = audit.ingest_incident_artifacts(evidence)
    document = _document(artifact_ingestion=result)
    rendered = json.dumps(document, default=str)
    assert 'postgresql://' not in rendered
    assert 'DATABASE_URL' not in rendered


def test_040_incident_facts_stay_separate_from_current_facts(evidence):
    _shadow(evidence)
    _ledger(evidence)
    result = audit.ingest_incident_artifacts(evidence)
    document = _document(artifact_ingestion=result)
    incident = document['incident_identity']['immutable_incident_facts']
    assert incident['evidence_source'] == audit.SOURCE_INCIDENT
    assert incident['shadow_lane']['games_planned'] == 35
    assert incident['appearance_ledger']['completed_games_expected'] == 133
    assert incident['game_ingestion_completeness'][
        'unresolved_final_games'
    ] == 60
    # The four sources are named and distinct.
    assert set(audit.EVIDENCE_SOURCES) == {
        'incident_artifact', 'current_database', 'official_mlb_source',
        'derived_inference',
    }


# ── 107-117 Evidence-artifact safety ────────────────────────────────────────

REQUIRED_JSON_SECTIONS = (
    'identity', 'incident_identity', 'request', 'read_only_proof',
    'source_call_budget', 'canonical_module_drift', 'official_game_evidence',
    'stored_game_evidence', 'authority_comparison',
    'appearance_ledger_evidence', 'player_attribution',
    'unresolved_final_games', 'snapshot_publication', 'questions',
    'root_cause', 'verdict',
)


def test_107_json_required_fields_present(tmp_path):
    document = _document()
    for key in REQUIRED_JSON_SECTIONS:
        assert key in document, key
    assert document['verdict']['non_authorization_statement'] == (
        audit.NON_AUTHORIZATION_STATEMENT
    )


def test_108_markdown_required_sections_present():
    rendered = runner.render_markdown(_document())
    for section in runner.REQUIRED_MARKDOWN_SECTIONS:
        assert section in rendered, section
    assert audit.NON_AUTHORIZATION_STATEMENT in rendered


def test_109_metadata_references_the_correct_filenames(tmp_path):
    metadata = runner.write_artifacts(_document(), tmp_path)
    assert metadata['summary_filename'] == runner.SUMMARY_JSON
    assert metadata['markdown_filename'] == runner.SUMMARY_MARKDOWN
    assert metadata['metadata_filename'] == runner.METADATA_JSON
    for name in (
        runner.SUMMARY_JSON, runner.SUMMARY_MARKDOWN, runner.METADATA_JSON,
    ):
        assert (tmp_path / name).exists()


def test_110_raw_mlb_payload_is_absent():
    document = _document()
    rendered = json.dumps(document, default=str)
    # Markers distinctive of a RAW payload, not of legitimate field names:
    # the budget honestly reports a "boxscore" call class, which is not a
    # payload, so the marker set has to discriminate between the two.
    for marker in (
        '"gamePk"', 'abstractGameState', 'liveData', 'gameData',
        '"players": {"ID', 'lastFirstName',
    ):
        assert marker not in rendered
    # The normalized field set is what travels instead.
    assert set(audit.OFFICIAL_STATUS_FIELDS) >= {
        'game_pk', 'detailed_state', 'status_code', 'source_revision',
    }


def test_111_raw_completion_proof_is_absent():
    rendered = json.dumps(_document(), default=str)
    assert 'completion_proof"' not in rendered
    assert '"completion_proof"' not in rendered


@pytest.mark.parametrize('marker', [
    'postgresql://', 'DATABASE_URL', 'SECRET_KEY',
])
def test_112_database_url_absent(marker):
    assert marker not in json.dumps(_document(), default=str)


@pytest.mark.parametrize('marker', [
    'ADMIN_API_TOKEN', 'X-Admin-Token', 'Authorization:',
])
def test_113_tokens_absent(marker):
    assert marker not in json.dumps(_document(), default=str)


def test_114_raw_exceptions_absent():
    rendered = json.dumps(_document(), default=str)
    assert 'Traceback (most recent call last)' not in rendered


def test_115_sql_probe_text_absent():
    rendered = json.dumps(_document(), default=str) + runner.render_markdown(
        _document()
    )
    assert 'WHERE 1 = 0' not in rendered
    assert 'SET TRANSACTION READ ONLY' not in rendered
    assert 'stat_correction_count = stat_correction_count' not in rendered


def test_116_the_artifact_scanner_fails_closed(tmp_path):
    runner.write_artifacts(_document(), tmp_path)
    assert scanner.main(['--directory', str(tmp_path)]) == scanner.EXIT_SAFE

    unsafe = tmp_path / 'leak.json'
    unsafe.write_text('postgresql://user:pw@host/db', encoding='utf-8')
    assert scanner.main(['--directory', str(tmp_path)]) == scanner.EXIT_UNSAFE


def test_117_upload_failure_is_unproven():
    decision = _decide(extra_unproven=[audit.UNPROVEN_ARTIFACT_UPLOAD_FAILED])
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_ARTIFACT_UPLOAD_FAILED in (
        decision['unproven_reasons']
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clean_proof():
    return {
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }


def _clean_ingestion():
    return {
        'missing_required': [], 'unreadable_required': [],
        'missing_optional': [], 'digest_mismatches': [],
        'all_required_present': True,
        'incident_validation': {'any_mismatch': False},
        'artifacts': {},
    }


def _decide(**overrides):
    kwargs = {
        'questions': [
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        'findings': [],
        'read_only_proof': _clean_proof(),
        'artifact_ingestion': _clean_ingestion(),
        'budget_state': audit.SourceCallBudget().state(),
    }
    kwargs.update(overrides)
    return audit.decide(**kwargs)


def _document(**overrides):
    decision = _decide(**{
        key: value for key, value in overrides.items()
        if key in {'questions', 'findings', 'read_only_proof',
                   'artifact_ingestion', 'budget_state', 'extra_unproven'}
    })
    return runner.build_document(
        context={
            'repository': 'NickolisK24/bullpen-intel-engine',
            'workflow': 'Manual Postgame Publication Incident Audit',
            'run_id': '1', 'run_attempt': '1', 'github_sha': 'a' * 40,
            'ref': 'refs/heads/main', 'actor': 'NickolisK24',
            'event_name': 'workflow_dispatch',
        },
        note='operator note',
        observations={},
        questions=[],
        comparison={},
        module_drift=audit.canonical_module_drift({}),
        read_only=_clean_proof(),
        artifact_ingestion=overrides.get(
            'artifact_ingestion', _clean_ingestion()
        ),
        budget_state=audit.SourceCallBudget().state(),
        decision=decision,
    )
