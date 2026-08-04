"""Incident evidence ingestion and the bounded MLB source-call budget.

Requirements 57-88.

Two properties matter most here. First, an artifact that is absent, truncated,
or unparseable must be REPORTED as such — never quietly treated as an empty but
successful reading. Second, the upstream source-call budget must refuse before
it overspends, and an exhausted budget must be UNPROVEN rather than a shortcut
to a verdict.
"""

import json

import pytest

from services import postgame_publication_incident_audit as audit


LEDGER_REPORT = """\
================================================================================

APPEARANCE LEDGER AUDIT

Window: 2026-07-25 .. 2026-08-03 (10 day(s))

Completed games expected:      118
Completed games represented:   117
Expected reliever appearances: 1002 (pitching lines seen by completed-game ingests; includes starters)
Stored appearances:            995
Latest appearance mismatches:  9
Players affected:              9
  - First Pitcher (100001, last stored: 2026-07-30)
  - Second Pitcher (100002, last stored: never)
  ! boxscore unavailable for game 822867: upstream error
Missing game_pks:              822867
Count-deficit game_pks:        822801, 822802
Incomplete-marker game_pks:    822803
Dates with holes:              2026-08-03 (14/15)

Publish eligible:

NO

Reasons: final_games_without_appearance_rows, appearance_rows_below_ingested_pitching_lines

================================================================================
"""


@pytest.fixture
def evidence_root(tmp_path):
    return tmp_path / 'incident-evidence'


def _write_shadow(root, *, sync_summary=None, activation_summary=None):
    directory = root / audit.ARTIFACT_SHADOW
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'postgame-sync-summary.json').write_text(
        json.dumps(sync_summary if sync_summary is not None else {
            'status': 'success',
            'publication_proof': {
                'verified': False,
                'reason_codes': ['candidate_snapshot_not_ready'],
            },
        }),
        encoding='utf-8',
    )
    if activation_summary is not None:
        (directory / 'postgame-activation-summary.json').write_text(
            json.dumps(activation_summary), encoding='utf-8',
        )
    return directory


def _write_ledger(root, text=LEDGER_REPORT):
    directory = root / audit.ARTIFACT_LEDGER_AUDIT
    directory.mkdir(parents=True, exist_ok=True)
    (directory / audit.LEDGER_REPORT_FILENAME).write_text(
        text, encoding='utf-8',
    )
    return directory


# ── 57-64 Artifact discovery ────────────────────────────────────────────────

def test_057_required_and_optional_artifacts_are_named_by_run_id():
    assert audit.ARTIFACT_SHADOW == 'game-driven-shadow-30873422601'
    assert audit.ARTIFACT_LEDGER_AUDIT == (
        'appearance-ledger-audit-30873422601'
    )
    assert audit.ARTIFACT_SHADOW_HANDOFF == (
        'game-driven-shadow-handoff-30873422601'
    )


def test_058_shadow_and_ledger_are_required_handoff_is_optional():
    assert audit.REQUIRED_ARTIFACTS == (
        audit.ARTIFACT_SHADOW, audit.ARTIFACT_LEDGER_AUDIT,
    )
    assert audit.OPTIONAL_ARTIFACTS == (audit.ARTIFACT_SHADOW_HANDOFF,)


def test_059_all_required_present_when_both_are_ingested(evidence_root):
    _write_shadow(evidence_root)
    _write_ledger(evidence_root)
    result = audit.ingest_incident_artifacts(evidence_root)
    assert result['all_required_present'] is True
    assert result['missing_required'] == []


def test_060_a_missing_required_artifact_is_reported(evidence_root):
    _write_shadow(evidence_root)
    result = audit.ingest_incident_artifacts(evidence_root)
    assert result['missing_required'] == [audit.ARTIFACT_LEDGER_AUDIT]
    assert result['all_required_present'] is False


def test_061_a_missing_optional_artifact_is_reported_not_inferred_away(
    evidence_root,
):
    _write_shadow(evidence_root)
    _write_ledger(evidence_root)
    result = audit.ingest_incident_artifacts(evidence_root)
    assert result['missing_optional'] == [audit.ARTIFACT_SHADOW_HANDOFF]
    assert result['all_required_present'] is True


def test_062_a_present_optional_artifact_is_recorded(evidence_root):
    _write_shadow(evidence_root)
    _write_ledger(evidence_root)
    handoff = evidence_root / audit.ARTIFACT_SHADOW_HANDOFF
    handoff.mkdir(parents=True)
    (handoff / 'handoff-metadata.json').write_text('{}', encoding='utf-8')
    result = audit.ingest_incident_artifacts(evidence_root)
    assert result['missing_optional'] == []
    entry = result['artifacts'][audit.ARTIFACT_SHADOW_HANDOFF]
    assert entry['present'] is True
    assert entry['files'] == ['handoff-metadata.json']


def test_063_every_expected_artifact_appears_in_the_report(evidence_root):
    result = audit.ingest_incident_artifacts(evidence_root)
    assert set(result['artifacts']) == set(audit.EXPECTED_ARTIFACTS)


def test_064_an_entirely_absent_evidence_root_is_not_a_success(evidence_root):
    result = audit.ingest_incident_artifacts(evidence_root / 'nope')
    assert result['all_required_present'] is False
    assert sorted(result['missing_required']) == sorted(
        audit.REQUIRED_ARTIFACTS
    )


# ── 65-70 Shadow artifact reading ───────────────────────────────────────────

def test_065_the_postgame_sync_summary_is_parsed(evidence_root):
    _write_shadow(evidence_root)
    _write_ledger(evidence_root)
    entry = audit.ingest_incident_artifacts(
        evidence_root
    )['artifacts'][audit.ARTIFACT_SHADOW]
    assert entry['sync_summary']['publication_proof']['verified'] is False


def test_066_the_activation_summary_is_parsed_when_present(evidence_root):
    _write_shadow(evidence_root, activation_summary={'result': 'PASS'})
    _write_ledger(evidence_root)
    entry = audit.ingest_incident_artifacts(
        evidence_root
    )['artifacts'][audit.ARTIFACT_SHADOW]
    assert entry['activation_summary'] == {'result': 'PASS'}


def test_067_a_shadow_artifact_without_a_sync_summary_reports_a_parse_error(
    evidence_root,
):
    directory = evidence_root / audit.ARTIFACT_SHADOW
    directory.mkdir(parents=True)
    (directory / 'handoff-metadata.json').write_text('{}', encoding='utf-8')
    _write_ledger(evidence_root)
    result = audit.ingest_incident_artifacts(evidence_root)
    entry = result['artifacts'][audit.ARTIFACT_SHADOW]
    assert entry['parse_error'] == 'shadow_sync_summary_missing'
    assert result['unreadable_required'] == [audit.ARTIFACT_SHADOW]


def test_068_unparseable_shadow_json_is_reported_not_silently_empty(
    evidence_root,
):
    directory = evidence_root / audit.ARTIFACT_SHADOW
    directory.mkdir(parents=True)
    (directory / 'postgame-sync-summary.json').write_text(
        'not json', encoding='utf-8',
    )
    _write_ledger(evidence_root)
    entry = audit.ingest_incident_artifacts(
        evidence_root
    )['artifacts'][audit.ARTIFACT_SHADOW]
    assert entry['parse_error'] == 'shadow_artifact_unparseable'


def test_069_a_parse_error_never_leaks_a_filesystem_path(evidence_root):
    directory = evidence_root / audit.ARTIFACT_SHADOW
    directory.mkdir(parents=True)
    (directory / 'postgame-sync-summary.json').write_text(
        'not json', encoding='utf-8',
    )
    entry = audit.ingest_incident_artifacts(
        evidence_root
    )['artifacts'][audit.ARTIFACT_SHADOW]
    assert '/' not in str(entry['parse_error'])
    assert str(evidence_root) not in json.dumps(entry, default=str)


def test_070_a_missing_ledger_report_file_is_a_parse_error(evidence_root):
    _write_shadow(evidence_root)
    (evidence_root / audit.ARTIFACT_LEDGER_AUDIT).mkdir(parents=True)
    result = audit.ingest_incident_artifacts(evidence_root)
    entry = result['artifacts'][audit.ARTIFACT_LEDGER_AUDIT]
    assert entry['parse_error'] == 'ledger_report_missing'
    assert result['unreadable_required'] == [audit.ARTIFACT_LEDGER_AUDIT]


# ── 71-80 Ledger audit report parsing ───────────────────────────────────────

def test_071_a_document_that_is_not_the_report_is_not_parsed():
    assert audit.parse_ledger_audit_report('hello')['parsed'] is False


def test_072_an_empty_document_is_not_parsed():
    assert audit.parse_ledger_audit_report('')['parsed'] is False
    assert audit.parse_ledger_audit_report(None)['parsed'] is False


def test_073_the_window_is_parsed():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert parsed['window_start'] == '2026-07-25'
    assert parsed['window_end'] == '2026-08-03'


def test_074_the_headline_counts_are_parsed():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert parsed['expected_games'] == 118
    assert parsed['represented_games'] == 117
    assert parsed['expected_appearances'] == 1002
    assert parsed['stored_appearances'] == 995
    assert parsed['latest_appearance_mismatches'] == 9
    assert parsed['players_affected'] == 9


def test_075_the_deficit_game_lists_are_parsed():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert parsed['missing_game_pks'] == [822867]
    assert parsed['count_deficit_game_pks'] == [822801, 822802]
    assert parsed['incomplete_marker_game_pks'] == [822803]


def test_076_player_mismatches_are_parsed_by_mlb_player_id():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert [entry['player_id'] for entry in parsed['player_mismatches']] == [
        100001, 100002,
    ]


def test_077_a_never_stored_appearance_parses_as_none():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    by_id = {
        entry['player_id']: entry for entry in parsed['player_mismatches']
    }
    assert by_id[100001]['latest_stored_appearance'] == '2026-07-30'
    assert by_id[100002]['latest_stored_appearance'] is None


def test_078_player_names_are_not_retained():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    for entry in parsed['player_mismatches']:
        assert 'name' not in entry
    assert 'First Pitcher' not in json.dumps(parsed)


def test_079_the_publish_verdict_and_reasons_are_parsed():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert parsed['publish_eligible'] is False
    assert parsed['reasons'] == [
        'final_games_without_appearance_rows',
        'appearance_rows_below_ingested_pitching_lines',
    ]


def test_080_an_unfetchable_boxscore_line_is_counted_not_ignored():
    parsed = audit.parse_ledger_audit_report(LEDGER_REPORT)
    assert parsed['unfetchable_game_count'] == 1


# ── 81-88 Bounded MLB source-call budget ────────────────────────────────────

def test_081_the_declared_budget_matches_the_incident_brief():
    assert audit.SOURCE_CALL_BUDGET == {
        'schedule': 8, 'exact_game': 10, 'boxscore': 10,
    }
    assert audit.SOURCE_CALL_TOTAL_BUDGET == 20


def test_082_a_fresh_budget_spends_nothing():
    state = audit.SourceCallBudget().state()
    assert state['total_spent'] == 0
    assert state['budget_exhausted'] is False
    assert state['budget_refused_a_call'] is False


def test_083_each_kind_is_capped_independently():
    budget = audit.SourceCallBudget()
    for _ in range(8):
        assert budget.reserve('schedule') is True
    assert budget.reserve('schedule') is False
    assert budget.reserve('boxscore') is True


def test_084_the_total_cap_bounds_the_sum_of_all_kinds():
    budget = audit.SourceCallBudget()
    for _ in range(8):
        budget.reserve('schedule')
    for _ in range(10):
        budget.reserve('exact_game')
    assert budget.total_spent == 18
    assert budget.reserve('boxscore') is True
    assert budget.reserve('boxscore') is True
    assert budget.total_spent == 20
    assert budget.reserve('boxscore') is False


def test_085_a_refused_call_is_counted_and_reported():
    budget = audit.SourceCallBudget(per_kind={'schedule': 0}, total=5)
    assert budget.reserve('schedule') is False
    state = budget.state()
    assert state['calls_refused_by_budget']['schedule'] == 1
    assert state['budget_refused_a_call'] is True


def test_086_an_unknown_call_kind_is_refused_loudly():
    with pytest.raises(audit.AuditInputError):
        audit.SourceCallBudget().reserve('play_by_play')


def test_087_source_errors_are_counted_separately_from_spend():
    budget = audit.SourceCallBudget()
    budget.reserve('boxscore')
    budget.record_error('boxscore')
    state = budget.state()
    assert state['calls_spent']['boxscore'] == 1
    assert state['source_errors']['boxscore'] == 1


def test_088_an_exhausted_budget_makes_the_audit_unproven():
    budget = audit.SourceCallBudget(per_kind={'schedule': 0}, total=0)
    budget.reserve('schedule')
    decision = audit.decide(
        questions=[
            {'question_id': question_id, 'answered': True}
            for question_id in audit.QUESTION_IDS
        ],
        classifications=[
            audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
        ],
        read_only_proof={
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        artifact_ingestion={
            'missing_required': [], 'unreadable_required': [],
            'all_required_present': True,
        },
        budget_state=budget.state(),
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_SOURCE_BUDGET_EXHAUSTED in (
        decision['unproven_reasons']
    )
