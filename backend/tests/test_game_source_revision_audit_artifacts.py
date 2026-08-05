"""Game 824487 source-revision audit — retained artifact contract.

Requirements 1-15.

Two retained scheduled daily runs are the ONLY evidence of what each run
observed. These tests own the properties that make an artifact usable as
evidence: it is addressed by exact repository, run id, artifact id, and name;
its identity is read from INSIDE the documents rather than from a directory
name; a metadata mismatch is FAILED; a missing required file is UNPROVEN; and
the absence of prior row-level normalized values is reported positively as
``not_retained`` rather than inferred away.
"""

import json

import pytest

from services import game_source_revision_audit as audit


PRIOR = audit.RUN_PRIOR
LATER = audit.RUN_LATER


def _sync_summary(
    *,
    game_pk=audit.GAME_PK,
    source_revision=audit.PRIOR_SOURCE_REVISION,
    plan_fingerprint=audit.EXPECTED_PLAN_FINGERPRINT,
    appearances=audit.EXPECTED_APPEARANCE_COUNT,
    unchanged=audit.EXPECTED_UNCHANGED_COUNT,
    inserted=0,
    updated=0,
    blocked=0,
    mode='shadow',
    extra_games=(),
    rows=None,
):
    """A daily sync summary shaped exactly like the retained one."""
    games = [{
        'game_pk': game_pk,
        'represented_date': audit.REPRESENTED_DATE.isoformat(),
        'candidate_reason': 'corrected_final',
        'criticality': 'publication_critical',
        'status': 'projected',
        'source_revision': source_revision,
        'appearances_extracted': appearances,
        'inserted': inserted,
        'updated': updated,
        'unchanged': unchanged,
        'blocked': blocked,
        'reconciliation_plan_fingerprint': plan_fingerprint,
        'error_class': None,
    }]
    games.extend(extra_games)
    lane = {
        'mode': mode,
        'status': 'complete',
        'games_planned': 94,
        'games_fetched': 94,
        'games_completed': 94,
        'games_failed': 0,
        'rows_expected': 778,
        'rows_unchanged': 778,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_blocked': 0,
        'execution_effects': {
            'writes_enabled': False,
            'publication_authoritative': False,
        },
        'projected_differences': list(rows or ()),
        'games': games,
    }
    return {'sync': {'status': 'success', 'game_driven_ingestion': lane}}


def _activation_summary(*, result='PASS', runner_exit_code=0):
    return {
        'result': result,
        'cycle_kind': 'daily',
        'runner_exit_code': runner_exit_code,
    }


def _handoff(run_id, head_sha):
    return {
        'run_id': run_id,
        'repository_sha': head_sha,
        'cycle_kind': 'daily',
        'handoff_status': 'ready',
        'branch': 'main',
    }


def write_artifact(root, run_key, *, sync_summary=None, activation=None,
                   handoff=None, omit=()):
    """Lay out one retained artifact exactly as download-artifact does."""
    spec = audit.RUN_EXPECTATIONS[run_key]
    directory = root / spec['artifact_name']
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        'daily-sync-summary.json': (
            _sync_summary(source_revision=spec['source_revision'])
            if sync_summary is None else sync_summary
        ),
        'daily-activation-summary.json': (
            _activation_summary(
                result=spec['activation_result'],
                runner_exit_code=0 if spec['activation_result'] == 'PASS' else 1,
            ) if activation is None else activation
        ),
        'handoff-metadata.json': (
            _handoff(spec['workflow_run_id'], spec['head_sha'])
            if handoff is None else handoff
        ),
    }
    for name, payload in files.items():
        if name in omit:
            continue
        (directory / name).write_text(
            json.dumps(payload, indent=2), encoding='utf-8',
        )
    return directory


def _metadata(*run_keys, digest_override=None, artifact_id_override=None):
    payload = {}
    for run_key in run_keys:
        spec = audit.RUN_EXPECTATIONS[run_key]
        payload[spec['artifact_name']] = {
            'artifact_id': (
                spec['artifact_id'] if artifact_id_override is None
                else artifact_id_override
            ),
            'digest': (
                spec['digest'] if digest_override is None else digest_override
            ),
            'expired': False,
        }
    return payload


@pytest.fixture
def evidence(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(tmp_path, LATER)
    return tmp_path


# ── 1-2. Exact run identity is accepted ─────────────────────────────────────

def test_the_exact_prior_run_id_is_accepted(evidence):
    result = audit.ingest_run_artifacts(
        evidence, observed_metadata=_metadata(PRIOR, LATER),
    )
    entry = result['runs'][PRIOR]
    assert entry['checks']['workflow_run_id'] == 'match'
    assert entry['expected_workflow_run_id'] == audit.PRIOR_RUN_ID
    assert entry['identity_verified'] is True


def test_the_exact_later_run_id_is_accepted(evidence):
    result = audit.ingest_run_artifacts(
        evidence, observed_metadata=_metadata(PRIOR, LATER),
    )
    entry = result['runs'][LATER]
    assert entry['checks']['workflow_run_id'] == 'match'
    assert entry['expected_workflow_run_id'] == audit.LATER_RUN_ID
    assert entry['identity_verified'] is True


# ── 3-8. Every identity mismatch is caught ──────────────────────────────────

def test_a_wrong_run_id_inside_the_artifact_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        handoff=_handoff('30000000000', audit.HISTORICAL_SHAS[PRIOR]),
    )
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'workflow_run_id' in result['runs'][PRIOR]['mismatched_fields']
    assert PRIOR in result['identity_mismatches']


def test_a_wrong_artifact_name_is_a_missing_artifact(tmp_path):
    directory = tmp_path / 'game-driven-shadow-99999999999'
    directory.mkdir(parents=True)
    (directory / 'daily-sync-summary.json').write_text('{}', encoding='utf-8')
    result = audit.ingest_run_artifacts(tmp_path)
    assert result['missing_artifacts'] == sorted([PRIOR, LATER])
    assert result['all_required_present'] is False


def test_a_wrong_artifact_id_reported_by_github_fails(evidence):
    result = audit.ingest_run_artifacts(
        evidence,
        observed_metadata=_metadata(
            PRIOR, LATER, artifact_id_override=1234567890,
        ),
    )
    assert result['runs'][PRIOR]['artifact_id_status'] == 'mismatch'
    assert result['runs'][PRIOR]['identity_verified'] is False


def test_a_wrong_head_sha_inside_the_artifact_fails(tmp_path):
    write_artifact(
        tmp_path, LATER,
        handoff=_handoff(audit.LATER_RUN_ID, '0' * 40),
    )
    write_artifact(tmp_path, PRIOR)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'head_sha' in result['runs'][LATER]['mismatched_fields']


def test_a_wrong_cycle_kind_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(result='PASS', runner_exit_code=0)
        | {'cycle_kind': 'postgame'},
        handoff=dict(
            _handoff(audit.PRIOR_RUN_ID, audit.HISTORICAL_SHAS[PRIOR]),
            cycle_kind='postgame',
        ),
    )
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'cycle_kind' in result['runs'][PRIOR]['mismatched_fields']


def test_a_wrong_branch_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        handoff=dict(
            _handoff(audit.PRIOR_RUN_ID, audit.HISTORICAL_SHAS[PRIOR]),
            branch='feature/other',
        ),
    )
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'branch' in result['runs'][PRIOR]['mismatched_fields']


# ── 9. Digest handling ──────────────────────────────────────────────────────

def test_a_digest_mismatch_exposed_by_github_fails(evidence):
    result = audit.ingest_run_artifacts(
        evidence,
        observed_metadata=_metadata(
            PRIOR, LATER, digest_override='sha256:' + ('b' * 64),
        ),
    )
    assert result['digest_mismatches'] == sorted([PRIOR, LATER])
    assert result['runs'][PRIOR]['digest_status'] == 'mismatch'


def test_a_digest_github_no_longer_exposes_is_unverified_not_failed(evidence):
    result = audit.ingest_run_artifacts(evidence, observed_metadata={})
    entry = result['runs'][PRIOR]
    assert entry['digest_status'] == 'not_exposed_by_github'
    assert entry['digest_verified'] is False
    assert entry['digest_mismatch'] is False
    assert result['digest_mismatches'] == []


def test_the_expected_digest_is_verified_when_github_exposes_it(evidence):
    result = audit.ingest_run_artifacts(
        evidence, observed_metadata=_metadata(PRIOR, LATER),
    )
    assert result['runs'][LATER]['digest_verified'] is True
    assert result['runs'][LATER]['digest_status'] == 'verified'


# ── 10. A missing required file is UNPROVEN, not FAILED ─────────────────────

def test_a_missing_required_file_is_reported_without_an_identity_failure(
    tmp_path,
):
    write_artifact(tmp_path, PRIOR, omit=('daily-sync-summary.json',))
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert PRIOR in result['artifacts_missing_required_files']
    assert result['all_required_present'] is False
    assert result['digest_mismatches'] == []


def test_an_unparseable_artifact_file_never_leaks_a_filesystem_path(tmp_path):
    directory = write_artifact(tmp_path, PRIOR)
    (directory / 'daily-sync-summary.json').write_text('{', encoding='utf-8')
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    error = result['runs'][PRIOR]['parse_error']
    assert error == 'artifact_file_unparseable'
    assert str(tmp_path) not in json.dumps(result)


# ── 11-14. The evidence the audit exists to read ────────────────────────────

def test_the_prior_source_revision_is_extracted_from_inside_the_document(
    evidence,
):
    result = audit.ingest_run_artifacts(evidence)
    assert result['runs'][PRIOR]['observed_source_revision'] == (
        audit.PRIOR_SOURCE_REVISION
    )


def test_the_later_source_revision_is_extracted_from_inside_the_document(
    evidence,
):
    result = audit.ingest_run_artifacts(evidence)
    assert result['runs'][LATER]['observed_source_revision'] == (
        audit.LATER_SOURCE_REVISION
    )
    assert result['revision_change_proven'] is True


def test_both_runs_retained_the_same_per_game_plan_fingerprint(evidence):
    result = audit.ingest_run_artifacts(evidence)
    assert result['plan_fingerprint_stable'] is True
    for run_key in audit.RUN_KEYS:
        assert result['runs'][run_key]['observed_plan_fingerprint'] == (
            audit.EXPECTED_PLAN_FINGERPRINT
        )


def test_twelve_appearances_and_twelve_unchanged_rows_are_verified(evidence):
    result = audit.ingest_run_artifacts(evidence)
    for run_key in audit.RUN_KEYS:
        entry = result['runs'][run_key]
        assert entry['observed_appearances_extracted'] == 12
        assert entry['observed_unchanged'] == 12
        assert entry['observed_inserted'] == 0
        assert entry['observed_updated'] == 0
        assert entry['observed_blocked'] == 0
        assert entry['checks']['appearances_extracted'] == 'match'
        assert entry['checks']['unchanged'] == 'match'


def test_a_different_appearance_count_is_a_mismatch(tmp_path):
    spec = audit.RUN_EXPECTATIONS[LATER]
    write_artifact(
        tmp_path, LATER,
        sync_summary=_sync_summary(
            source_revision=spec['source_revision'], appearances=11,
            unchanged=11,
        ),
    )
    write_artifact(tmp_path, PRIOR)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'appearances_extracted' in result['runs'][LATER][
        'mismatched_fields'
    ]


def test_the_shadow_posture_of_each_run_is_read_from_the_document(evidence):
    result = audit.ingest_run_artifacts(evidence)
    for run_key in audit.RUN_KEYS:
        checks = result['runs'][run_key]['checks']
        assert checks['configured_mode'] == 'match'
        assert checks['writes_enabled'] == 'match'
        assert checks['publication_authoritative'] == 'match'


def test_a_write_capable_run_artifact_is_a_mismatch(tmp_path):
    summary = _sync_summary(source_revision=audit.PRIOR_SOURCE_REVISION)
    summary['sync']['game_driven_ingestion']['execution_effects'][
        'writes_enabled'
    ] = True
    write_artifact(tmp_path, PRIOR, sync_summary=summary)
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert 'writes_enabled' in result['runs'][PRIOR]['mismatched_fields']


def test_an_artifact_without_the_target_game_is_a_wrong_game_failure(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        sync_summary=_sync_summary(
            game_pk=999999, source_revision=audit.PRIOR_SOURCE_REVISION,
        ),
    )
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    assert PRIOR in result['wrong_game']


# ── 15. The evidence limit, reported positively ─────────────────────────────

def test_absent_prior_row_level_values_are_reported_as_not_retained(evidence):
    result = audit.ingest_run_artifacts(evidence)
    for run_key in audit.RUN_KEYS:
        row_level = result['runs'][run_key]['row_level_evidence']
        assert row_level['row_level_normalized_values_retained'] is False
        assert row_level['evidence_status'] == audit.EVIDENCE_NOT_RETAINED
        assert row_level['normalized_value_fields_found'] == []
    assert result['prior_row_level_values_retained'] is False
    assert result['later_row_level_values_retained'] is False


def test_retained_row_level_values_would_be_reported_as_proven(tmp_path):
    """The scan is positive evidence, not a hardcoded conclusion.

    A retained document that DOES pair a pitcher identity with governed field
    values must be recognised as such, or "not retained" would be an assertion
    about the code rather than an observation about the artifact.
    """
    summary = _sync_summary(
        source_revision=audit.PRIOR_SOURCE_REVISION,
        rows=[{
            'game_pk': audit.GAME_PK,
            'pitcher_mlb_id': 605400,
            'outs_recorded': 18,
            'strikeouts': 7,
        }],
    )
    write_artifact(tmp_path, PRIOR, sync_summary=summary)
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    row_level = result['runs'][PRIOR]['row_level_evidence']
    assert row_level['row_level_normalized_values_retained'] is True
    assert row_level['evidence_status'] == audit.EVIDENCE_PROVEN
    assert 'outs_recorded' in row_level['normalized_value_fields_found']
    assert result['prior_row_level_values_retained'] is True


def test_field_names_and_digests_alone_are_not_row_level_values(tmp_path):
    """A plan row naming FIELDS is not a plan row carrying VALUES."""
    summary = _sync_summary(
        source_revision=audit.PRIOR_SOURCE_REVISION,
        rows=[{
            'game_pk': audit.GAME_PK,
            'pitcher_mlb_id': 605400,
            'changed_fields': ['outs_recorded', 'strikeouts'],
            'target_state_digest': 'a' * 64,
            'stored_state_digest': 'b' * 64,
        }],
    )
    write_artifact(tmp_path, PRIOR, sync_summary=summary)
    write_artifact(tmp_path, LATER)
    result = audit.ingest_run_artifacts(tmp_path)
    row_level = result['runs'][PRIOR]['row_level_evidence']
    assert row_level['row_level_normalized_values_retained'] is False
    assert row_level['evidence_status'] == audit.EVIDENCE_NOT_RETAINED
