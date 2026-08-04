"""Authority comparison, ledger, player attribution, unresolved games, gate.

Requirements 58-98.

Every classification here must rest on POSITIVE evidence. The recurring failure
mode this file guards against is concluding something from the absence of a
contradiction — attributing all nine players to one game because they appeared
in one report, or calling a game final because nothing said it was not.
"""

import json

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import models.scheduled_game  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import postgame_publication_incident_audit as audit
from utils.db import db

import scripts.run_postgame_publication_incident_audit as runner


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


class _Row:
    """A stored scheduled_games row, only the fields the classifier reads."""

    def __init__(self, team_id, status_state):
        self.team_id = team_id
        self.status_state = status_state


class _WorkItem:
    def __init__(self, status=None, rows_expected=None, error_class=None):
        self.status = status
        self.rows_expected = rows_expected
        self.error_class = error_class
        self.attempt_count = 0


def _observations(**overrides):
    base = {
        'official_status': {
            'game_found_in_source': True,
            'official_classification': audit.OFFICIAL_CLASS_FINAL,
            'canonical_finality_state': 'final_pending_data',
            'canonical_finality_reason': 'final_status_pending_boxscore',
            'canonical_status_state': 'final',
            'normalized': {'detailed_state': 'Final', 'status_code': 'F'},
            'relationship': {
                'is_rescheduled': False, 'is_resumed': False,
                'rescheduled_from_game_pk': None,
                'resumed_from_game_pk': None,
                'replacement_game_pk': None, 'resolved': True,
            },
        },
        'stored_schedule': {
            'row_count': 2, 'rows': [], 'team_ids': [1, 2],
            'duplicate_team_rows': False,
            'distinct_status_states': ['final'], 'rows_agree': True,
            'paired_row_disagreement': False, 'stored_status_state': 'final',
            'counts_as_ledger_final': True, 'all_rows_final': True,
            'unresolved_resumed_linkage': False,
            'linked_replacement_game_pks': [],
        },
        'baseball_state': {'game_logs': {'row_count': 8}},
        'appearance_ledger': {
            'disputed_game_has_stored_final_row': True,
            'disputed_game_in_deficit_set': False,
            'reasons': [], 'membership_rule': 'rule',
        },
        'completeness': {
            'plan': {
                'disputed_game_planned': True,
                'disputed_game_exclusion_reason': None,
                'finality_conflicts': [],
            },
            'completeness': {'horizon_days': 7},
            'unresolved_classification': {
                'reconciles_with_authority': True, 'scope_invalid_count': 0,
                'classification_counts': {}, 'reconstructed_count': 0,
            },
        },
        'snapshot_gate': {
            'slate_coverage': {
                'complete_enough_to_publish': False,
                'validations_passed': True,
                'reason_codes': ['scheduled_games_not_final'],
            },
            'candidate_still_pending': True,
            'candidate_snapshot': {'id': 344, 'status': 'pending'},
            'currently_served_snapshot_id': 343,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            merged.update(value)
            base[key] = merged
        else:
            base[key] = value
    return base


def _findings(observations):
    drift = audit.canonical_module_drift({})
    return {
        entry['classification']: entry
        for entry in runner.build_findings(
            observations, runner.build_authority_comparison(observations),
            drift,
        )
    }


def _runner_source():
    return open(runner.__file__, encoding='utf-8').read()


# ── 58-65 Official status and canonical mapping ─────────────────────────────

def test_058_official_final_plus_stored_other_is_mapping_drift():
    observations = _observations(
        stored_schedule={
            'distinct_status_states': ['other'],
            'stored_status_state': 'other',
            'counts_as_ledger_final': False, 'all_rows_final': False,
        },
        completeness={'plan': {
            'disputed_game_planned': False,
            'disputed_game_exclusion_reason': 'cancelled',
            'finality_conflicts': [],
        }},
    )
    finding = _findings(observations)[
        audit.CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT
    ]
    assert finding['proven'] is True
    assert finding['supporting_evidence']
    assert finding['counter_evidence']


def test_059_official_postponed_plus_ledger_completed_is_ledger_defect():
    observations = _observations(official_status={
        'official_classification': audit.OFFICIAL_CLASS_POSTPONED,
        'canonical_status_state': 'postponed',
    })
    finding = _findings(observations)[
        audit.CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT
    ]
    assert finding['proven'] is True
    assert finding['supporting_evidence']


def test_060_a_suspended_or_resumed_relationship_is_represented():
    observations = _observations(official_status={
        'official_classification': audit.OFFICIAL_CLASS_SUSPENDED,
        'relationship': {
            'is_rescheduled': False, 'is_resumed': True,
            'resumed_from_game_pk': 822000, 'rescheduled_from_game_pk': None,
            'replacement_game_pk': None, 'resolved': True,
        },
    })
    comparison = runner.build_authority_comparison(observations)
    assert comparison['official_source_classification'] == (
        audit.OFFICIAL_CLASS_SUSPENDED
    )
    finding = _findings(observations)[
        audit.CLASSIFICATION_RESCHEDULE_OR_SUSPENSION_IDENTITY_DEFECT
    ]
    assert finding['proven'] is True


def test_061_a_cancelled_game_is_not_treated_as_completed():
    entry = runner._classify_one_unresolved_game(
        900001, work_item=None, rows=[_Row(1, 'final')], stored_row_count=0,
        official={'classification': audit.OFFICIAL_CLASS_CANCELLED,
                  'relationship': {}},
        schedule_missing=False,
    )
    assert entry['classification'] == audit.UNRESOLVED_CANCELLED
    assert entry['classification'] in audit.UNRESOLVED_NON_DEFICIT_CATEGORIES


def test_062_a_makeup_game_identity_is_not_silently_merged():
    entry = runner._classify_one_unresolved_game(
        900002, work_item=None, rows=[_Row(1, 'final')], stored_row_count=0,
        official={
            'classification': audit.OFFICIAL_CLASS_FINAL,
            'relationship': {'is_rescheduled': True,
                             'replacement_game_pk': 900003},
        },
        schedule_missing=False,
    )
    assert entry['classification'] == audit.UNRESOLVED_RESCHEDULED
    assert entry['classification'] != audit.UNRESOLVED_FINAL_MISSING_ROWS


def test_063_paired_schedule_row_disagreement_is_detected():
    observations = _observations(stored_schedule={
        'distinct_status_states': ['final', 'other'],
        'rows_agree': False, 'paired_row_disagreement': True,
        'stored_status_state': None,
    })
    finding = _findings(observations)[
        audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT
    ]
    assert finding['proven'] is True
    comparison = runner.build_authority_comparison(observations)
    assert 'paired_schedule_rows_disagree' in comparison['exact_disagreements']


def test_064_the_canonical_mapper_is_reused_not_copied():
    text = _runner_source()
    assert 'game_finality.classify_status' in text
    assert 'game_finality.normalize_schedule_status_state' in text
    # No second status vocabulary is defined in the audit.
    for invented in (
        "'postponed':", 'FINAL_GAME_STATUS_CODES', 'SCHEDULED_DETAILED_STATES',
    ):
        assert invented not in text


def test_065_current_non_reproduction_is_not_rewritten_as_incident_proof():
    """When the current mapping no longer returns `other`, the audit must not
    claim the incident state — the incident value stays reported separately."""
    observations = _observations()
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(
            observations, runner.build_authority_comparison(observations),
            audit.canonical_module_drift({}),
        )
    }
    third = questions[audit.QUESTION_PREFLIGHT_PRODUCED_OTHER]
    assert third['evidence']['incident_preflight_status_state'] == 'other'
    assert third['evidence']['canonical_mapped_status_state'] == 'final'
    assert third['evidence']['reproduces_incident_result'] is False


# ── 66-72 Appearance ledger ─────────────────────────────────────────────────

def test_066_canonical_ledger_logic_is_reused():
    text = _runner_source()
    assert 'appearance_ledger.build_appearance_ledger' in text
    # No second membership definition.
    assert 'STATE_FINAL' not in text
    assert 'def build_appearance_ledger' not in text


def test_067_the_game_membership_source_is_reported():
    observations = _observations()
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(
            observations, runner.build_authority_comparison(observations),
            audit.canonical_module_drift({}),
        )
    }
    fourth = questions[audit.QUESTION_LEDGER_COUNTED_COMPLETED]
    assert fourth['evidence']['authority'] == (
        'services.appearance_ledger.build_appearance_ledger'
    )


def test_068_the_inclusion_path_for_the_disputed_game_is_proven():
    observations = _observations()
    comparison = runner.build_authority_comparison(observations)
    assert comparison['appearance_ledger_classification'] == (
        'counted_as_completed_game'
    )
    observations = _observations(appearance_ledger={
        'disputed_game_has_stored_final_row': False,
    })
    assert runner.build_authority_comparison(observations)[
        'appearance_ledger_classification'
    ] == 'not_counted'


def test_069_existing_rows_plus_ledger_missing_is_a_query_defect():
    observations = _observations(
        appearance_ledger={'disputed_game_in_deficit_set': True},
        baseball_state={'game_logs': {'row_count': 8}},
    )
    finding = _findings(observations)[
        audit.CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT
    ]
    assert finding['proven'] is True


def test_070_no_rows_plus_both_authorities_final_is_an_ingestion_gap():
    observations = _observations(
        baseball_state={'game_logs': {'row_count': 0}},
        appearance_ledger={'disputed_game_in_deficit_set': True},
    )
    findings = _findings(observations)
    gap = findings[audit.CLASSIFICATION_EXACT_GAME_INGESTION_GAP]
    assert gap['proven'] is True
    assert gap['genuine_source_gap'] is True
    # And the query defect must NOT also fire, because no rows exist.
    assert findings[
        audit.CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT
    ]['proven'] is False


def test_071_non_final_official_state_plus_ledger_inclusion_is_ledger_defect():
    observations = _observations(official_status={
        'official_classification': audit.OFFICIAL_CLASS_CANCELLED,
        'canonical_status_state': 'other',
    })
    assert _findings(observations)[
        audit.CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT
    ]['proven'] is True


def test_072_the_audit_cannot_change_the_ledger_count():
    """Reading the ledger result is the whole point; ASSIGNING into it is the
    violation. Matched against assignment, not against subscript reads."""
    text = _runner_source()
    for marker in (
        "ledger['complete'] =", "ledger['expected_games'] =",
        "ledger['missing_games'] =", 'ledger.update(', 'ledger.pop(',
    ):
        assert marker not in text


# ── 73-79 Player attribution ────────────────────────────────────────────────

def _attribute(app, *, boxscore_ids=(), tracked=(), rows=()):
    for mlb_id in tracked:
        db.session.add(Pitcher(mlb_id=mlb_id, full_name=f'Pitcher {mlb_id}'))
    db.session.commit()
    lookup = {p.mlb_id: p.id for p in Pitcher.query.all()}
    for mlb_id, game_pk, game_date in rows:
        db.session.add(GameLog(
            pitcher_id=lookup[mlb_id], mlb_game_pk=game_pk,
            game_date=game_date, innings_pitched_outs=3,
            innings_pitched=1.0,
        ))
    db.session.commit()
    return runner.attribute_player_mismatches(
        {'player_mismatches': [
            {'player_id': entry['player_id']}
            for entry in audit.INCIDENT_PLAYER_MISMATCHES
        ]},
        {'deficit_game_pks': [audit.INCIDENT_GAME_PK]},
        {
            'boxscore_pitcher_ids': list(boxscore_ids),
            'official_classification': audit.OFFICIAL_CLASS_FINAL,
        },
    )


def test_073_all_nine_players_appear_exactly_once(app):
    result = _attribute(app, boxscore_ids=audit.INCIDENT_PLAYER_IDS,
                        tracked=audit.INCIDENT_PLAYER_IDS)
    assert result['attributed_count'] == 9
    ids = [entry['player_id'] for entry in result['players']]
    assert sorted(ids) == sorted(audit.INCIDENT_PLAYER_IDS)
    assert len(ids) == len(set(ids))
    assert result['all_attributed_exactly_once'] is True


def test_074_player_ids_are_preserved(app):
    result = _attribute(app, tracked=audit.INCIDENT_PLAYER_IDS)
    assert {entry['player_id'] for entry in result['players']} == set(
        audit.INCIDENT_PLAYER_IDS
    )
    for entry in result['players']:
        assert isinstance(entry['player_id'], int)


def test_075_each_player_gets_exactly_one_classification(app):
    result = _attribute(app, tracked=audit.INCIDENT_PLAYER_IDS)
    for entry in result['players']:
        assert entry['classification'] in audit.PLAYER_CLASSIFICATIONS
        assert entry['reason_codes'] == [entry['classification']]
    assert sum(result['classification_counts'].values()) == 9


def test_076_no_attribution_to_the_disputed_game_without_positive_evidence(app):
    """Nothing in the disputed game's official lines means nothing attributed
    to it — being listed in the same ledger report is not evidence."""
    result = _attribute(app, boxscore_ids=(), tracked=audit.INCIDENT_PLAYER_IDS)
    assert result['attributed_to_disputed_game'] == 0
    for entry in result['players']:
        assert entry['attributable_to_disputed_game'] is False
        assert entry['expected_source_game_pk'] is None


def test_077_another_game_mismatches_are_reported_separately(app):
    one = audit.INCIDENT_PLAYER_IDS[0]
    result = _attribute(
        app, boxscore_ids=(one,), tracked=audit.INCIDENT_PLAYER_IDS,
    )
    by_id = {entry['player_id']: entry for entry in result['players']}
    assert by_id[one]['classification'] == audit.PLAYER_CAUSED_BY_DISPUTED_GAME
    others = {
        entry['classification'] for entry in result['players']
        if entry['player_id'] != one
    }
    assert audit.PLAYER_CAUSED_BY_DISPUTED_GAME not in others


def test_078_identity_ambiguity_is_unproven_rather_than_guessed(app):
    """An untracked pitcher is an identity problem, and a player with no
    official lines to compare against is unproven — never a guess."""
    result = _attribute(app, boxscore_ids=(), tracked=())
    for entry in result['players']:
        assert entry['classification'] == (
            audit.PLAYER_CAUSED_BY_IDENTITY_PROBLEM
        )
        assert entry['pitcher_tracked'] is False


def test_079_raw_boxscores_are_excluded_from_the_artifact(app):
    result = _attribute(app, tracked=audit.INCIDENT_PLAYER_IDS)
    assert result['raw_boxscore_excluded'] is True
    rendered = json.dumps(result, default=str)
    for marker in ('gameData', 'liveData', '"players": {"ID', 'lastFirstName'):
        assert marker not in rendered


# ── 80-90 Unresolved-game classification ────────────────────────────────────

def test_080_canonical_completeness_computation_is_reused():
    text = _runner_source()
    assert (
        'game_ingestion_completeness.build_game_ingestion_completeness' in text
    )
    assert 'def build_game_ingestion_completeness' not in text


def test_081_incident_membership_and_current_reconstruction_are_distinct():
    assert audit.MEMBERSHIP_INCIDENT_ARTIFACT != (
        audit.MEMBERSHIP_CURRENT_RECONSTRUCTION
    )
    text = _runner_source()
    assert 'MEMBERSHIP_CURRENT_RECONSTRUCTION' in text
    assert 'membership_note' in text


@pytest.mark.parametrize('case,expected', [
    ({'official': None, 'rows': [_Row(1, 'final')], 'stored': 0,
      'work_item': None, 'missing': False}, audit.UNRESOLVED_UNPROVEN),
    ({'official': {'classification': audit.OFFICIAL_CLASS_POSTPONED,
                   'relationship': {}},
      'rows': [_Row(1, 'scheduled')], 'stored': 0, 'work_item': None,
      'missing': False}, audit.UNRESOLVED_POSTPONED),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 0,
      'work_item': _WorkItem(status='terminal_failure'), 'missing': False},
     audit.UNRESOLVED_TERMINAL_FAILURE),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 0, 'work_item': None,
      'missing': True}, audit.UNRESOLVED_SCHEDULE_AUTHORITY_MISSING),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 5, 'work_item': None,
      'missing': False}, audit.UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 0, 'work_item': None,
      'missing': False}, audit.UNRESOLVED_FINAL_MISSING_ROWS),
    ({'official': {'classification': audit.OFFICIAL_CLASS_NON_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 0, 'work_item': None,
      'missing': False}, audit.UNRESOLVED_STORED_FINAL_SOURCE_NON_FINAL),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'scheduled')], 'stored': 0, 'work_item': None,
      'missing': False}, audit.UNRESOLVED_SOURCE_FINAL_STORED_NON_FINAL),
    ({'official': {'classification': audit.OFFICIAL_CLASS_FINAL,
                   'relationship': {}},
      'rows': [_Row(1, 'final')], 'stored': 3,
      'work_item': _WorkItem(status='completed', rows_expected=8),
      'missing': False}, audit.UNRESOLVED_FINAL_PARTIAL),
])
def test_082_every_unresolved_game_gets_one_deterministic_category(
    case, expected,
):
    entry = runner._classify_one_unresolved_game(
        123456, work_item=case['work_item'], rows=case['rows'],
        stored_row_count=case['stored'], official=case['official'],
        schedule_missing=case['missing'],
    )
    assert entry['classification'] == expected
    assert entry['classification'] in audit.UNRESOLVED_CLASSIFICATIONS


def test_083_category_totals_equal_the_classified_total():
    cases = [
        (audit.OFFICIAL_CLASS_FINAL, 0), (audit.OFFICIAL_CLASS_FINAL, 5),
        (audit.OFFICIAL_CLASS_POSTPONED, 0),
        (audit.OFFICIAL_CLASS_CANCELLED, 0),
    ]
    counts = {}
    for index, (official_class, stored) in enumerate(cases):
        entry = runner._classify_one_unresolved_game(
            index, work_item=None, rows=[_Row(1, 'final')],
            stored_row_count=stored,
            official={'classification': official_class, 'relationship': {}},
            schedule_missing=False,
        )
        counts[entry['classification']] = counts.get(
            entry['classification'], 0
        ) + 1
    assert sum(counts.values()) == len(cases)


def test_084_no_game_appears_in_multiple_primary_categories():
    entry = runner._classify_one_unresolved_game(
        1, work_item=None, rows=[_Row(1, 'final')], stored_row_count=0,
        official={'classification': audit.OFFICIAL_CLASS_POSTPONED,
                  'relationship': {'is_rescheduled': True}},
        schedule_missing=False,
    )
    # Postponed wins over rescheduled by declared precedence; exactly one.
    assert entry['classification'] == audit.UNRESOLVED_POSTPONED
    assert isinstance(entry['classification'], str)


def test_085_ordered_lists_are_deterministic():
    first = runner._classify_one_unresolved_game(
        99, work_item=None, rows=[_Row(2, 'final'), _Row(1, 'final')],
        stored_row_count=0,
        official={'classification': audit.OFFICIAL_CLASS_FINAL,
                  'relationship': {}},
        schedule_missing=False,
    )
    second = runner._classify_one_unresolved_game(
        99, work_item=None, rows=[_Row(1, 'final'), _Row(2, 'final')],
        stored_row_count=0,
        official={'classification': audit.OFFICIAL_CLASS_FINAL,
                  'relationship': {}},
        schedule_missing=False,
    )
    assert first == second


def test_086_games_outside_publication_scope_are_identified():
    assert audit.UNRESOLVED_FINAL_OUT_OF_SCOPE in (
        audit.UNRESOLVED_NON_DEFICIT_CATEGORIES
    )
    assert audit.UNRESOLVED_GATE_SCOPE_MISMATCH in (
        audit.UNRESOLVED_NON_DEFICIT_CATEGORIES
    )


def test_087_postponed_and_cancelled_do_not_inflate_true_deficits():
    for category in (
        audit.UNRESOLVED_POSTPONED, audit.UNRESOLVED_CANCELLED,
        audit.UNRESOLVED_SUSPENDED, audit.UNRESOLVED_RESCHEDULED,
    ):
        assert category in audit.UNRESOLVED_NON_DEFICIT_CATEGORIES
    for category in (
        audit.UNRESOLVED_FINAL_MISSING_ROWS, audit.UNRESOLVED_FINAL_PARTIAL,
    ):
        assert category not in audit.UNRESOLVED_NON_DEFICIT_CATEGORIES


def test_088_missing_source_evidence_stays_unproven():
    entry = runner._classify_one_unresolved_game(
        7, work_item=None, rows=[_Row(1, 'final')], stored_row_count=0,
        official=None, schedule_missing=False,
    )
    assert entry['classification'] == audit.UNRESOLVED_UNPROVEN


def test_089_the_source_call_budget_is_enforced():
    budget = audit.SourceCallBudget()
    for _ in range(8):
        assert budget.reserve(audit.CALL_KIND_SCHEDULE) is True
    assert budget.reserve(audit.CALL_KIND_SCHEDULE) is False
    state = budget.state()
    assert state['calls_attempted'][audit.CALL_KIND_SCHEDULE] == 8
    assert state['calls_refused_by_budget'][audit.CALL_KIND_SCHEDULE] == 1
    assert state['total_limit'] == 20


def test_090_budget_exhaustion_is_unproven():
    budget = audit.SourceCallBudget(per_kind={'schedule': 0}, total=0)
    budget.reserve(audit.CALL_KIND_SCHEDULE)
    decision = audit.decide(
        questions=[
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        findings=[],
        read_only_proof={
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        artifact_ingestion={
            'missing_required': [], 'unreadable_required': [],
            'digest_mismatches': [], 'all_required_present': True,
            'incident_validation': {'any_mismatch': False},
        },
        budget_state=budget.state(),
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_SOURCE_BUDGET_EXHAUSTED in (
        decision['unproven_reasons']
    )


# ── 91-98 Snapshot publication gate ─────────────────────────────────────────

MUTATION_MARKERS = (
    'snapshot.status =', 'snapshot.is_published =', 'snapshot.published_at =',
    'candidate.status =', 'prior.status =', 'sync_run.status =',
    'sync_run.stage =', 'session.add(', 'session.commit(', 'session.delete(',
)


def test_091_snapshot_344_is_read_only():
    text = _runner_source()
    assert 'INCIDENT_CANDIDATE_SNAPSHOT_ID' in text
    assert 'db.session.get(' in text
    for marker in MUTATION_MARKERS:
        assert marker not in text


def test_092_snapshot_343_is_read_only():
    text = _runner_source()
    assert 'INCIDENT_SERVING_SNAPSHOT_ID' in text
    # The prior snapshot is fetched and rendered; never assigned to.
    for marker in (
        'prior.status =', 'prior.is_published =', 'prior.published_at =',
    ):
        assert marker not in text


def test_093_sync_run_596_is_read_only():
    text = _runner_source()
    assert 'db.session.get(SyncRun, audit.INCIDENT_SYNC_RUN_ID)' in text
    for marker in (
        'sync_run.status =', 'sync_run.stage =',
        'sync_run.published_dashboard_snapshot_id =',
    ):
        assert marker not in text


def test_094_no_snapshot_state_transition_is_invoked():
    text = _runner_source()
    for marker in (
        'publish_dashboard_snapshot(', 'mark_dashboard_snapshot_failed(',
        'store_dashboard_snapshot(',
    ):
        assert marker not in text


def test_095_the_gate_scope_is_reported():
    assert 'gate_scope' in _runner_source()
    docstring = runner.observe_snapshot_gate.__doc__ or ''
    assert 'scope' in docstring.lower()


def test_096_correct_withholding_can_produce_no_platform_defect_proven():
    observations = _observations(
        baseball_state={'game_logs': {'row_count': 0}},
        appearance_ledger={'disputed_game_in_deficit_set': True},
    )
    gap = _findings(observations)[
        audit.CLASSIFICATION_EXACT_GAME_INGESTION_GAP
    ]
    assert gap['genuine_source_gap'] is True
    # With the gap NOT proven, a genuine-source-gap flag still routes to
    # no_platform_defect_proven rather than to a defect.
    decision = audit.decide(
        questions=[
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        findings=[{**gap, 'proven': False, 'genuine_source_gap': True}],
        read_only_proof={
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        artifact_ingestion={
            'missing_required': [], 'unreadable_required': [],
            'digest_mismatches': [], 'all_required_present': True,
            'incident_validation': {'any_mismatch': False},
        },
        budget_state=audit.SourceCallBudget().state(),
    )
    assert decision['result'] == audit.RESULT_NO_PLATFORM_DEFECT_PROVEN
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN
    )


def test_097_overbroad_scope_can_produce_publication_gate_scope_defect():
    observations = _observations(completeness={
        'plan': {'disputed_game_planned': True,
                 'disputed_game_exclusion_reason': None,
                 'finality_conflicts': []},
        'completeness': {'horizon_days': 7},
        'unresolved_classification': {
            'reconciles_with_authority': True, 'scope_invalid_count': 41,
            'classification_counts': {audit.UNRESOLVED_POSTPONED: 41},
            'reconstructed_count': 60,
        },
    })
    finding = _findings(observations)[
        audit.CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT
    ]
    assert finding['proven'] is True
    assert finding['supporting_evidence']


def test_098_missing_snapshot_evidence_is_unproven():
    observations = _observations()
    observations['snapshot_gate'] = {}
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(
            observations, runner.build_authority_comparison(observations),
            audit.canonical_module_drift({}),
        )
    }
    eighth = questions[audit.QUESTION_SNAPSHOT_GATE]
    assert eighth['answered'] is False
    assert eighth['unproven_reason'] == audit.UNPROVEN_SNAPSHOT_EVIDENCE_MISSING
