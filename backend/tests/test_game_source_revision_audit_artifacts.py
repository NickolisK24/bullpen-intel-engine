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


_UNSET = object()

LANE_ACCOUNTING = dict(audit.LATER_LANE_EXPECTATIONS)


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


def _activation_summary(
    *,
    result='PASS',
    runner_exit_code=0,
    source_revision_match=True,
    safe_digest_match=True,
    all_projected_targets_realized=True,
    unresolved_rows=0,
    prohibited_identity_actions=0,
    configured_mode='shadow',
    writes_enabled=False,
    publication_authoritative=False,
    lane=None,
    drop_realization=False,
    realization=_UNSET,
    drop=(),
):
    """An activation summary shaped exactly like the retained one.

    Mirrors ``scripts/validate_game_driven_shadow_cycle._decision``: top-level
    result/cycle/runner exit code, a ``projected`` block, a ``realization``
    block, and an ``execution_effects`` block. The realization keys are emitted
    conditionally by the producer, so a key can legitimately be absent — which
    is exactly the case the audit has to survive.
    """
    accounting = dict(LANE_ACCOUNTING)
    accounting.update(lane or {})
    payload = {
        'result': result,
        'cycle_kind': 'daily',
        'runner_exit_code': runner_exit_code,
        'work_state': 'candidates_planned',
        'configured_mode': configured_mode,
        'games_planned': accounting['games_planned'],
        'games_fetched': accounting['games_fetched'],
        'games_completed': accounting['games_completed'],
        'games_failed': accounting['games_failed'],
        'projected': {
            'rows_expected': accounting['rows_expected'],
            'rows_unchanged': accounting['rows_unchanged'],
            'rows_inserted': accounting['rows_inserted'],
            'rows_updated': accounting['rows_updated'],
            'rows_blocked': accounting['rows_blocked'],
        },
        'execution_effects': {
            'writes_enabled': writes_enabled,
            'publication_authoritative': publication_authoritative,
        },
        'run_fingerprint': audit.EXPECTED_PLAN_FINGERPRINT,
        'failed_invariants': [],
        'write_approved': False,
        'future_write_authorized': False,
    }
    if realization is not _UNSET:
        if realization is not None:
            payload['realization'] = realization
    elif not drop_realization:
        payload['realization'] = {
            'applicable': True,
            'work_state': 'candidates_planned',
            'unresolved_rows': unresolved_rows,
            'prohibited_identity_actions': prohibited_identity_actions,
            'source_revision_match': source_revision_match,
            'safe_digest_match': safe_digest_match,
            'all_projected_targets_realized': all_projected_targets_realized,
        }
    for key in drop:
        payload.pop(key, None)
        (payload.get('realization') or {}).pop(key, None)
        (payload.get('execution_effects') or {}).pop(key, None)
        (payload.get('projected') or {}).pop(key, None)
    return payload


def workflow_metadata(*run_keys, head_branch='main', head_sha=None,
                      omit=(), malformed=False):
    """GitHub workflow-run metadata, the ONLY source of the branch fact."""
    payload = {}
    for run_key in run_keys or audit.RUN_KEYS:
        spec = audit.RUN_EXPECTATIONS[run_key]
        if run_key in omit:
            continue
        if malformed:
            payload[spec['workflow_run_id']] = 'not-a-mapping'
            continue
        record = {
            'run_id': spec['workflow_run_id'],
            'head_branch': head_branch,
            'head_sha': head_sha or spec['head_sha'],
            'event': 'schedule',
            'status': 'completed',
            'conclusion': 'success',
        }
        if head_branch is None:
            record.pop('head_branch')
        payload[spec['workflow_run_id']] = record
    return payload


def _handoff(run_id, head_sha, **overrides):
    """Handoff metadata with EXACTLY the producer's keys.

    ``scripts/prepare_shadow_handoff.build_metadata`` emits schema version,
    run id, repository SHA, cycle kind, runner exit code, the expected summary
    filename, and three booleans. It emits NO branch and NO ref — which is
    precisely why the audit must read the branch from GitHub workflow-run
    metadata instead of inventing it. A fixture that carried a branch here
    would be testing a document that does not exist.
    """
    payload = {
        'schema_version': '1',
        'run_id': run_id,
        'repository_sha': head_sha,
        'cycle_kind': 'daily',
        'runner_exit_code': 0,
        'expected_summary_filename': 'daily-sync-summary.json',
        'summary_present': True,
        'preupload_scan_safe': True,
        'handoff_status': 'ready',
    }
    payload.update(overrides)
    return payload


def _default_activation(run_key):
    spec = audit.RUN_EXPECTATIONS[run_key]
    return _activation_summary(
        result=spec['activation_result'],
        # BOTH runs' public daily sync succeeded, so the runner exited 0 in
        # both. The observer's own verdict is the separate ``result`` field.
        runner_exit_code=spec['runner_exit_code'],
        source_revision_match=spec['source_revision_match'],
        safe_digest_match=spec['safe_digest_match'],
        all_projected_targets_realized=spec[
            'all_projected_targets_realized'
        ],
        unresolved_rows=spec['unresolved_rows'],
        prohibited_identity_actions=spec['prohibited_identity_actions'],
    )


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
            _default_activation(run_key) if activation is None else activation
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


def _ingest(root, *, metadata=None, workflow=None):
    """Ingest with BOTH metadata sources, as the workflow supplies them."""
    return audit.ingest_run_artifacts(
        root,
        observed_metadata=metadata,
        workflow_metadata=(
            workflow_metadata() if workflow is None else workflow
        ),
    )


# ── 1-2. Exact run identity is accepted ─────────────────────────────────────

def test_the_exact_prior_run_id_is_accepted(evidence):
    result = _ingest(evidence, metadata=_metadata(PRIOR, LATER))
    entry = result['runs'][PRIOR]
    assert audit.observation_state(
        entry['observations'], 'workflow_run_id',
    ) == audit.OBS_VERIFIED
    assert entry['expected_workflow_run_id'] == audit.PRIOR_RUN_ID
    assert entry['identity_state'] == audit.STATE_VERIFIED
    assert entry['identity_verified'] is True
    assert entry['unobserved_fields'] == []
    # Every mandatory identity field is positively observed AND matched.
    assert set(audit.IDENTITY_FIELDS) <= set(entry['verified_fields'])


def test_the_exact_later_run_id_is_accepted(evidence):
    result = _ingest(evidence, metadata=_metadata(PRIOR, LATER))
    entry = result['runs'][LATER]
    assert audit.observation_state(
        entry['observations'], 'workflow_run_id',
    ) == audit.OBS_VERIFIED
    assert entry['expected_workflow_run_id'] == audit.LATER_RUN_ID
    assert entry['identity_state'] == audit.STATE_VERIFIED
    assert entry['content_state'] == audit.STATE_VERIFIED
    assert entry['unobserved_fields'] == []
    # The later run's 94/94/778 accounting is COMPARED, not merely reported.
    assert entry['lane_accounting_state'] == audit.STATE_VERIFIED
    assert entry['lane_accounting'] == dict(audit.LATER_LANE_EXPECTATIONS)


# ── 3-8. Every identity mismatch is caught ──────────────────────────────────

def test_a_wrong_run_id_inside_the_artifact_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        handoff=_handoff('30000000000', audit.HISTORICAL_SHAS[PRIOR]),
    )
    write_artifact(tmp_path, LATER)
    result = _ingest(tmp_path)
    assert 'workflow_run_id' in result['runs'][PRIOR]['mismatched_fields']
    assert PRIOR in result['identity_mismatches']


def test_a_wrong_artifact_name_is_a_missing_artifact(tmp_path):
    directory = tmp_path / 'game-driven-shadow-99999999999'
    directory.mkdir(parents=True)
    (directory / 'daily-sync-summary.json').write_text('{}', encoding='utf-8')
    result = _ingest(tmp_path)
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
    result = _ingest(tmp_path)
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
    result = _ingest(tmp_path)
    assert 'cycle_kind' in result['runs'][PRIOR]['mismatched_fields']


def test_a_wrong_branch_in_workflow_metadata_fails(evidence):
    result = _ingest(
        evidence, workflow=workflow_metadata(head_branch='feature/other'),
    )
    entry = result['runs'][PRIOR]
    assert 'branch' in entry['mismatched_fields']
    assert entry['identity_state'] == audit.STATE_FAILED
    assert PRIOR in result['identity_failures']


def test_a_branch_absent_everywhere_is_unproven_never_a_match(evidence):
    """The handoff schema has no branch, so absence must stay absence."""
    result = _ingest(evidence, workflow=workflow_metadata(head_branch=None))
    entry = result['runs'][PRIOR]
    assert audit.observation_state(
        entry['observations'], 'branch',
    ) == audit.OBS_ABSENT
    assert 'branch' in entry['unobserved_fields']
    assert 'branch' not in entry['verified_fields']
    assert 'branch' not in entry['mismatched_fields']
    assert entry['identity_state'] == audit.STATE_UNPROVEN
    assert entry['identity_verified'] is False


def test_no_retained_artifact_carries_a_branch_to_fall_back_on(evidence):
    """Pins the schema fact the repair depends on."""
    payload = json.loads(
        (
            evidence / audit.RUN_EXPECTATIONS[PRIOR]['artifact_name']
            / 'handoff-metadata.json'
        ).read_text(encoding='utf-8')
    )
    assert 'branch' not in payload
    assert 'ref' not in payload


def test_absent_workflow_metadata_leaves_branch_unverified(evidence):
    result = _ingest(evidence, workflow={})
    entry = result['runs'][PRIOR]
    assert entry['workflow_metadata_available'] is False
    assert audit.observation_state(
        entry['observations'], 'branch',
    ) == audit.OBS_CONTAINER_ABSENT
    assert entry['identity_state'] == audit.STATE_UNPROVEN


def test_malformed_workflow_metadata_leaves_branch_unverified(evidence):
    result = _ingest(evidence, workflow=workflow_metadata(malformed=True))
    entry = result['runs'][PRIOR]
    assert audit.observation_state(
        entry['observations'], 'branch',
    ) == audit.OBS_CONTAINER_MALFORMED
    assert entry['identity_state'] == audit.STATE_UNPROVEN


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
    result = _ingest(tmp_path)
    assert PRIOR in result['artifacts_missing_required_files']
    assert result['all_required_present'] is False
    assert result['digest_mismatches'] == []


def test_an_unparseable_artifact_file_never_leaks_a_filesystem_path(tmp_path):
    directory = write_artifact(tmp_path, PRIOR)
    (directory / 'daily-sync-summary.json').write_text('{', encoding='utf-8')
    write_artifact(tmp_path, LATER)
    result = _ingest(tmp_path)
    error = result['runs'][PRIOR]['parse_error']
    assert error == 'artifact_file_unparseable'
    assert str(tmp_path) not in json.dumps(result)


# ── 11-14. The evidence the audit exists to read ────────────────────────────

def test_the_prior_source_revision_is_extracted_from_inside_the_document(
    evidence,
):
    result = _ingest(evidence)
    assert result['runs'][PRIOR]['observed_source_revision'] == (
        audit.PRIOR_SOURCE_REVISION
    )


def test_the_later_source_revision_is_extracted_from_inside_the_document(
    evidence,
):
    result = _ingest(evidence)
    assert result['runs'][LATER]['observed_source_revision'] == (
        audit.LATER_SOURCE_REVISION
    )
    assert result['revision_change_proven'] is True


def test_both_runs_retained_the_same_per_game_plan_fingerprint(evidence):
    result = _ingest(evidence)
    assert result['plan_fingerprint_stable'] is True
    for run_key in audit.RUN_KEYS:
        assert result['runs'][run_key]['observed_plan_fingerprint'] == (
            audit.EXPECTED_PLAN_FINGERPRINT
        )


def test_twelve_appearances_and_twelve_unchanged_rows_are_verified(evidence):
    result = _ingest(evidence)
    for run_key in audit.RUN_KEYS:
        entry = result['runs'][run_key]
        assert entry['observed_appearances_extracted'] == 12
        assert entry['observed_unchanged'] == 12
        assert entry['observed_inserted'] == 0
        assert entry['observed_updated'] == 0
        assert entry['observed_blocked'] == 0
        for field in ('appearances_extracted', 'unchanged'):
            assert audit.observation_state(
                entry['observations'], field,
            ) == audit.OBS_VERIFIED


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
    result = _ingest(tmp_path)
    assert 'appearances_extracted' in result['runs'][LATER][
        'mismatched_fields'
    ]


def test_the_shadow_posture_of_each_run_is_read_from_the_document(evidence):
    result = _ingest(evidence)
    for run_key in audit.RUN_KEYS:
        entry = result['runs'][run_key]
        for field in (
            'configured_mode', 'writes_enabled', 'publication_authoritative',
        ):
            assert audit.observation_state(
                entry['observations'], field,
            ) == audit.OBS_VERIFIED


def test_a_write_capable_run_artifact_is_a_mismatch(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(writes_enabled=True),
    )
    write_artifact(tmp_path, LATER)
    result = _ingest(tmp_path)
    entry = result['runs'][PRIOR]
    assert 'writes_enabled' in entry['mismatched_fields']
    assert entry['content_state'] == audit.STATE_FAILED


def test_an_absent_write_posture_is_unproven_not_a_match(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(drop=('writes_enabled',)),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert audit.observation_state(
        entry['observations'], 'writes_enabled',
    ) == audit.OBS_ABSENT
    assert 'writes_enabled' in entry['unobserved_fields']
    assert 'writes_enabled' not in entry['verified_fields']
    assert entry['content_state'] == audit.STATE_UNPROVEN


def test_an_artifact_without_the_target_game_is_a_wrong_game_failure(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        sync_summary=_sync_summary(
            game_pk=999999, source_revision=audit.PRIOR_SOURCE_REVISION,
        ),
    )
    write_artifact(tmp_path, LATER)
    result = _ingest(tmp_path)
    assert PRIOR in result['wrong_game']


# ── 15. The evidence limit, reported positively ─────────────────────────────

def test_absent_prior_row_level_values_are_reported_as_not_retained(evidence):
    result = _ingest(evidence)
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
    result = _ingest(tmp_path)
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
    result = _ingest(tmp_path)
    row_level = result['runs'][PRIOR]['row_level_evidence']
    assert row_level['row_level_normalized_values_retained'] is False
    assert row_level['evidence_status'] == audit.EVIDENCE_NOT_RETAINED


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER 1 — Question 10 must consume OBSERVED activation values
# ══════════════════════════════════════════════════════════════════════════

def _later_only(tmp_path, **activation_kwargs):
    """Write both artifacts, varying only the later run's activation."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(
            result='FAILED',
            source_revision_match=False,
            all_projected_targets_realized=False,
            **activation_kwargs,
        ),
    )
    return _ingest(tmp_path)['runs'][LATER]


def test_activation_values_are_parsed_from_the_retained_document(tmp_path):
    entry = _later_only(tmp_path)
    evidence = audit.activation_evidence(entry)
    assert evidence['all_required_observed'] is True
    assert evidence['source_revision_match'] is False
    assert evidence['all_projected_targets_realized'] is False
    assert evidence['safe_digest_match'] is True
    assert evidence['unresolved_rows'] == 0
    assert evidence['prohibited_identity_actions'] == 0
    assert evidence['missing_fields'] == []
    paths = {item['evidence_path'] for item in evidence['observations']}
    assert 'realization.unresolved_rows' in paths
    assert 'realization.source_revision_match' in paths


def test_an_absent_unresolved_rows_stays_absent(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(drop=('unresolved_rows',)),
    )
    evidence = audit.activation_evidence(_ingest(tmp_path)['runs'][LATER])
    assert 'unresolved_rows' in evidence['missing_fields']
    assert evidence['unresolved_rows'] is None
    assert evidence['all_required_observed'] is False


def test_an_absent_prohibited_identity_count_stays_absent(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(
            drop=('prohibited_identity_actions',),
        ),
    )
    evidence = audit.activation_evidence(_ingest(tmp_path)['runs'][LATER])
    assert 'prohibited_identity_actions' in evidence['missing_fields']
    assert evidence['prohibited_identity_actions'] is None


def test_artifact_presence_alone_proves_no_activation_counter(tmp_path):
    """The whole point of Blocker 1: presence is not a value."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER, activation=_activation_summary(drop_realization=True),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert entry['present'] is True
    evidence = audit.activation_evidence(entry)
    assert sorted(evidence['missing_fields']) == sorted(audit.Q10_FIELDS)
    for field in audit.Q10_FIELDS:
        assert evidence[field] is None
    assert evidence['all_required_observed'] is False


def test_a_missing_realization_object_is_a_container_absence(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER, activation=_activation_summary(drop_realization=True),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert audit.observation_state(
        entry['observations'], 'unresolved_rows',
    ) == audit.OBS_CONTAINER_ABSENT


def test_a_malformed_realization_object_is_distinguishable(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(realization='not-a-mapping'),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert audit.observation_state(
        entry['observations'], 'unresolved_rows',
    ) == audit.OBS_CONTAINER_MALFORMED


def test_a_wrong_typed_activation_field_is_malformed_not_observed(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(unresolved_rows='zero'),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert audit.observation_state(
        entry['observations'], 'unresolved_rows',
    ) == audit.OBS_MALFORMED
    assert audit.activation_evidence(entry)['unresolved_rows'] is None


def test_a_nonzero_unresolved_row_count_is_observed_as_such(tmp_path):
    entry = _later_only(tmp_path, unresolved_rows=3)
    assert audit.activation_evidence(entry)['unresolved_rows'] == 3


def test_a_nonzero_prohibited_identity_count_is_observed_as_such(tmp_path):
    entry = _later_only(tmp_path, prohibited_identity_actions=2)
    assert audit.activation_evidence(entry)[
        'prohibited_identity_actions'
    ] == 2


def test_an_unexpected_matched_revision_is_a_mismatch_not_a_substitution(
    tmp_path,
):
    """The expectation says False. The artifact saying True must SHOW."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(source_revision_match=True),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert 'source_revision_match' in entry['mismatched_fields']
    assert audit.activation_evidence(entry)['source_revision_match'] is True


def test_an_unexpected_realized_target_is_a_mismatch(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(all_projected_targets_realized=True),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert 'all_projected_targets_realized' in entry['mismatched_fields']


def test_no_expected_constant_can_supply_a_missing_activation_value(tmp_path):
    """The locked expectations exist. None of them may become an observation."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER, activation=_activation_summary(drop_realization=True),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    spec = audit.RUN_EXPECTATIONS[LATER]
    evidence = audit.activation_evidence(entry)
    for field in audit.Q10_FIELDS:
        assert spec[field] is not None       # the expectation genuinely exists
        assert evidence[field] is None       # and it did NOT leak through
    for item in entry['observations']:
        if item['state'] in audit.GAP_STATES:
            assert item['observed'] is None
            assert item['observed_present'] is False


def test_activation_evidence_paths_are_safe_to_publish(tmp_path):
    entry = _later_only(tmp_path)
    rendered = json.dumps(audit.activation_evidence(entry))
    for forbidden in ('/home/', 'Traceback', 'postgresql://', 'Bearer '):
        assert forbidden not in rendered


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER 2 — identity/content/digest verification
# ══════════════════════════════════════════════════════════════════════════

def test_an_absent_runner_exit_code_is_unproven_not_a_match(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(drop=('runner_exit_code',)),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'runner_exit_code' in entry['unobserved_fields']
    assert 'runner_exit_code' not in entry['verified_fields']
    assert entry['identity_state'] == audit.STATE_UNPROVEN


def test_a_wrong_runner_exit_code_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(runner_exit_code=1),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'runner_exit_code' in entry['mismatched_fields']
    assert entry['identity_state'] == audit.STATE_FAILED


def test_a_wrong_typed_runner_exit_code_is_malformed(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(runner_exit_code='0'),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert audit.observation_state(
        entry['observations'], 'runner_exit_code',
    ) == audit.OBS_MALFORMED
    assert entry['identity_state'] == audit.STATE_UNPROVEN


def test_an_absent_activation_result_is_unproven(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(drop=('result',)),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'activation_result' in entry['unobserved_fields']
    assert entry['content_state'] == audit.STATE_UNPROVEN


def test_a_wrong_activation_result_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(result='FAILED'),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'activation_result' in entry['mismatched_fields']
    assert entry['content_state'] == audit.STATE_FAILED


def test_an_absent_safe_digest_match_is_unproven(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(
            drop=('safe_digest_match',),
        ),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'safe_digest_match' in entry['unobserved_fields']


def test_a_wrong_safe_digest_match_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR, activation=_activation_summary(
            safe_digest_match=False,
        ),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'safe_digest_match' in entry['mismatched_fields']


def test_an_absent_configured_mode_is_unproven(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(drop=('configured_mode',)),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'configured_mode' in entry['unobserved_fields']
    assert entry['content_state'] == audit.STATE_UNPROVEN


def test_an_authoritative_publication_posture_fails(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(publication_authoritative=True),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert 'publication_authoritative' in entry['mismatched_fields']


@pytest.mark.parametrize('field', sorted(audit.LATER_LANE_EXPECTATIONS))
def test_a_one_count_lane_accounting_difference_is_caught(tmp_path, field):
    """94/94/778 is COMPARED. Off-by-one must be visible and blocking."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(
            result='FAILED', source_revision_match=False,
            all_projected_targets_realized=False,
            lane={field: audit.LATER_LANE_EXPECTATIONS[field] + 1},
        ),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert field in entry['mismatched_fields']
    assert entry['lane_accounting_state'] == audit.STATE_FAILED
    assert entry['content_verified'] is False


def test_an_absent_lane_count_is_unproven_not_verified(tmp_path):
    write_artifact(tmp_path, PRIOR)
    write_artifact(
        tmp_path, LATER,
        activation=_activation_summary(
            result='FAILED', source_revision_match=False,
            all_projected_targets_realized=False,
            drop=('games_planned',),
        ),
    )
    entry = _ingest(tmp_path)['runs'][LATER]
    assert 'games_planned' in entry['unobserved_fields']
    assert 'games_planned' not in entry['verified_fields']
    assert entry['lane_accounting_state'] == audit.STATE_UNPROVEN


def test_the_prior_run_is_not_held_to_later_lane_accounting(evidence):
    """The 94/94/778 record belongs to the later run only."""
    entry = _ingest(evidence)['runs'][PRIOR]
    assert 'games_planned' not in entry['verified_fields']
    assert 'games_planned' not in entry['unobserved_fields']
    assert entry['content_state'] == audit.STATE_VERIFIED


def test_an_exposed_but_wrong_artifact_id_fails(evidence):
    result = _ingest(
        evidence,
        metadata=_metadata(PRIOR, LATER, artifact_id_override=999),
    )
    entry = result['runs'][PRIOR]
    assert entry['artifact_id_status'] == 'mismatch'
    assert entry['identity_state'] == audit.STATE_FAILED


def test_an_unexposed_artifact_id_is_unverified_not_matched(evidence):
    entry = _ingest(evidence, metadata={})['runs'][PRIOR]
    assert entry['artifact_id_status'] == 'not_exposed_by_github'
    assert entry['identity_state'] != audit.STATE_FAILED


def test_identity_digest_and_content_stay_three_separate_verdicts(evidence):
    """A verified identity with an unexposed digest is a real, distinct state."""
    entry = _ingest(evidence, metadata={})['runs'][PRIOR]
    assert entry['identity_state'] == audit.STATE_VERIFIED
    assert entry['content_state'] == audit.STATE_VERIFIED
    assert entry['digest_state'] == audit.STATE_UNVERIFIED
    assert entry['identity_verified'] is True
    assert entry['digest_verified'] is False


def test_a_verified_identity_can_coexist_with_unproven_content(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(drop=('configured_mode',)),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert entry['identity_state'] == audit.STATE_VERIFIED
    assert entry['content_state'] == audit.STATE_UNPROVEN


def test_an_unobserved_field_is_never_reported_as_verified(tmp_path):
    write_artifact(
        tmp_path, PRIOR,
        activation=_activation_summary(
            drop=('runner_exit_code', 'result', 'configured_mode'),
        ),
    )
    write_artifact(tmp_path, LATER)
    entry = _ingest(tmp_path)['runs'][PRIOR]
    assert set(entry['unobserved_fields']) & {
        'runner_exit_code', 'activation_result', 'configured_mode',
    }
    assert not set(entry['unobserved_fields']) & set(entry['verified_fields'])


def test_the_mandatory_registry_covers_every_gate(evidence):
    registry = audit.mandatory_field_registry()
    gates = {gate for row in registry for gate in row['gates']}
    assert gates == {audit.GATE_IDENTITY, audit.GATE_CONTENT, audit.GATE_Q10}
    for row in registry:
        assert row['source'] in audit.OBSERVATION_SOURCES
        assert row['source'] != audit.SOURCE_INFERRED
        assert row['absence_outcome'] == audit.ABSENCE_UNPROVEN
        assert row['evidence_path']


def test_q1_and_q2_cannot_answer_from_required_file_presence_alone(tmp_path):
    """All three files exist; the branch does not. That is not an answer."""
    write_artifact(tmp_path, PRIOR)
    write_artifact(tmp_path, LATER)
    result = _ingest(tmp_path, workflow={})
    assert result['all_required_present'] is True
    assert result['identity_all_verified'] is False
    assert result['revision_change_proven'] is False
    assert result['plan_fingerprint_stable'] is False


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER 4 — historical value extraction and association
# ══════════════════════════════════════════════════════════════════════════

def _with_rows(tmp_path, run_key, rows):
    spec = audit.RUN_EXPECTATIONS[run_key]
    write_artifact(
        tmp_path, run_key,
        sync_summary=_sync_summary(
            source_revision=spec['source_revision'], rows=rows,
        ),
    )


def test_a_fully_associated_historical_value_is_extracted(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is True
    record = audit.historical_value_for(extract, 605400, 'outs_recorded')
    assert record['value'] == 18
    assert record['status'] == audit.HISTORICAL_PROVEN
    assert record['game_pk'] == audit.GAME_PK
    assert record['run_id'] == audit.PRIOR_RUN_ID
    assert record['evidence_path']


def test_a_retained_null_is_proven_null_not_absent(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'pitches_thrown': None,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    record = audit.historical_value_for(extract, 605400, 'pitches_thrown')
    assert record['value'] is None
    assert record['status'] == audit.HISTORICAL_PROVEN_NULL
    assert record['status'] != audit.HISTORICAL_ABSENT
    assert record['status'] != audit.HISTORICAL_NOT_RETAINED
    assert record['status'] != audit.HISTORICAL_UNPROVEN


def test_a_value_without_a_pitcher_identity_is_not_associable(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is False
    assert extract['evidence_status'] == audit.HISTORICAL_UNPROVEN
    assert extract['unassociable_candidates'][0]['status'] == (
        audit.HISTORICAL_IDENTITY_MISSING
    )


def test_a_value_for_the_wrong_game_is_rejected(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': 999999, 'pitcher_mlb_id': 605400, 'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is False
    assert extract['unassociable_candidates'][0]['status'] == (
        audit.HISTORICAL_WRONG_GAME
    )


def test_a_value_with_no_game_identity_is_rejected(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'pitcher_mlb_id': 605400, 'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is False


def test_a_non_integer_pitcher_identity_is_rejected(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 'Arm 605400',
        'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is False


def test_two_conflicting_values_for_one_coordinate_are_inconsistent(tmp_path):
    _with_rows(tmp_path, PRIOR, [
        {'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
         'outs_recorded': 18},
        {'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
         'outs_recorded': 17},
    ])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    record = audit.historical_value_for(extract, 605400, 'outs_recorded')
    assert record['status'] == audit.HISTORICAL_INCONSISTENT
    assert extract['inconsistent_coordinates']


def test_field_names_and_digests_alone_extract_no_value(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'changed_fields': ['outs_recorded'],
        'target_state_digest': 'a' * 64, 'stored_state_digest': 'b' * 64,
        'mutation_digest': 'c' * 64,
    }])
    write_artifact(tmp_path, LATER)
    extract = _ingest(tmp_path)['runs'][PRIOR]['historical_values']
    assert extract['exact_values_retained'] is False
    assert extract['evidence_status'] == audit.HISTORICAL_NOT_RETAINED


def test_only_one_side_retaining_values_identifies_no_delta(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'outs_recorded': 18,
    }])
    write_artifact(tmp_path, LATER)
    delta = _ingest(tmp_path)['historical_delta']
    assert delta['prior_value_count'] == 1
    assert delta['later_value_count'] == 0
    assert delta['comparable_coordinates'] == 0
    assert delta['delta_identified'] is False
    assert delta['identified_fields'] == []


def test_both_sides_retaining_the_same_value_identifies_no_delta(tmp_path):
    for run_key in (PRIOR, LATER):
        _with_rows(tmp_path, run_key, [{
            'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
            'outs_recorded': 18,
        }])
    delta = _ingest(tmp_path)['historical_delta']
    assert delta['comparable_coordinates'] == 1
    assert delta['delta_identified'] is False


def test_both_sides_retaining_different_values_identifies_the_delta(tmp_path):
    _with_rows(tmp_path, PRIOR, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'outs_recorded': 18,
    }])
    _with_rows(tmp_path, LATER, [{
        'game_pk': audit.GAME_PK, 'pitcher_mlb_id': 605400,
        'outs_recorded': 17,
    }])
    delta = _ingest(tmp_path)['historical_delta']
    assert delta['delta_identified'] is True
    assert delta['identified_fields'] == ['outs_recorded']
    changed = delta['changed_coordinates'][0]
    assert changed['pitcher_mlb_id'] == 605400
    assert changed['prior_value'] == 18
    assert changed['later_value'] == 17


def test_the_real_retained_schema_identifies_no_field(evidence):
    """The honest headline for these two artifacts, proven not assumed."""
    result = _ingest(evidence)
    assert result['exact_historical_values_retained'] is False
    assert result['unassociable_historical_candidates'] == 0
    assert result['historical_delta']['delta_identified'] is False
    for run_key in audit.RUN_KEYS:
        extract = result['runs'][run_key]['historical_values']
        assert extract['evidence_status'] == audit.HISTORICAL_NOT_RETAINED
