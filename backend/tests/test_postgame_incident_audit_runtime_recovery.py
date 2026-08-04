"""What the audit does when one of its own stages raises.

The first production dispatch of this audit stopped inside the completeness
observer and produced an artifact that said, in full, ``audit_execution_error``
— true, unactionable, and identical to what it would have said had the run
died anywhere else. It also reported ``required_fingerprint_unavailable``
despite having computed a perfectly good read-only baseline seconds earlier,
because that baseline was held in a local until the end of the run.

These drive the REAL staged orchestration against a REAL PostgreSQL database
with a stage deliberately raising, and assert the three things a reader of a
partial artifact needs: everything observed before the stop survives, the
proof that nothing changed still completes, and the artifact says where the
run stopped and what class of thing stopped it — without saying one word
about what it read.
"""

import json
from datetime import date, timedelta

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import models.completed_game_context  # noqa: F401
import models.game_ingestion_work_item  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.scheduled_game import ScheduledGame
from services import postgame_publication_incident_audit as audit
from utils.db import db

import scripts.run_postgame_publication_incident_audit as runner


SLATE = audit.INCIDENT_SLATE_DATE
GAME = audit.INCIDENT_GAME_PK

# The evidence blocks each question is built from, named as the document
# names them. Q1-Q5 read the first group; Q6-Q8 read the second. The
# production partial state is exactly the boundary between them.
BEFORE_THE_STOP = (
    'official_game_evidence', 'stored_game_evidence',
    'appearance_ledger_evidence',
)
AFTER_THE_STOP = (
    'player_attribution', 'snapshot_publication', 'dead_letter_backlog',
    'unresolved_final_games', 'game_ingestion_completeness',
)


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


class _Client:
    """A source that answers, so a stop can only come from the audit itself."""

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        return [_game(GAME)]

    def get_game_boxscore(self, game_pk):
        return {'teams': {'home': {'pitchers': []}, 'away': {'pitchers': []}}}


def _game(game_pk):
    return {
        'gamePk': game_pk,
        'gameDate': f'{SLATE.isoformat()}T23:05:00Z',
        'officialDate': SLATE.isoformat(),
        'status': {
            'abstractGameState': 'Final', 'codedGameState': 'F',
            'detailedState': 'Final', 'statusCode': 'F',
        },
        'teams': {
            'home': {'team': {'id': 137}}, 'away': {'team': {'id': 140}},
        },
    }


def _seed():
    """A production-shaped slate, not a single hand-placed row.

    The crash this file exists for only appears when the REAL planner builds a
    REAL plan over a populated horizon. A two-row fixture reaches none of it.
    """
    game_pk = 820000
    for offset in range(11):
        day = SLATE - timedelta(days=offset)
        for pair in range(8):
            game_pk += 1
            for team, side in ((100 + pair, 'home'), (140 + pair, 'away')):
                db.session.add(ScheduledGame(
                    game_pk=game_pk, team_id=team, game_date=day,
                    opponent_team_id=(
                        (140 + pair) if side == 'home' else (100 + pair)
                    ),
                    home_away=side, status_state='final', status_code='F',
                    game_type='R',
                ))
            if pair < 5:
                db.session.add(GameIngestionWorkItem(
                    mlb_game_pk=game_pk, represented_date=day,
                    status=GameIngestionWorkItem.STATUS_PLANNED,
                    criticality=(
                        GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
                    ),
                    candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
                ))
    for team, side, opponent in ((137, 'home', 140), (140, 'away', 137)):
        db.session.add(ScheduledGame(
            game_pk=GAME, team_id=team, game_date=SLATE,
            opponent_team_id=opponent, home_away=side, status_state='final',
            status_code='F', game_type='R',
        ))
    db.session.commit()


class _Guard:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


def _drive(app, monkeypatch, *, break_completeness=None):
    """Run the real orchestration, optionally breaking one stage.

    Only the things outside the audit's own logic are substituted: the app
    factory, the advisory guard, artifact ingestion, and authorization. The
    stage driver, the observers, the fingerprints, and the reducer are the
    real ones running against real PostgreSQL.
    """
    guard = _Guard()
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    monkeypatch.setattr(runner, 'validate_authorization', lambda context: [])
    monkeypatch.setattr(
        runner, 'load_observed_artifact_metadata', lambda directory: {},
    )
    monkeypatch.setattr(
        audit, 'ingest_incident_artifacts',
        lambda directory, observed_metadata=None: {
            'missing_required': [], 'unreadable_required': [],
            'missing_optional': [], 'digest_mismatches': [],
            'all_required_present': True,
            'incident_validation': {'any_mismatch': False},
            'artifacts': {},
        },
    )

    from services import sync_metadata
    monkeypatch.setattr(
        sync_metadata, 'acquire_public_sync_read_lock',
        lambda source=None: guard,
    )

    if break_completeness is not None:
        def _raise(game_pk, gateway):
            raise break_completeness

        monkeypatch.setattr(runner, 'observe_completeness', _raise)

    monkeypatch.setattr(
        runner.SourceGateway, 'client', property(lambda self: _Client()),
    )

    args = runner.parse_args([
        '--expected-head-sha', 'a' * 40,
        '--confirmation', audit.CONFIRMATION,
        '--evidence-dir', '/nonexistent',
        '--operator-note', 'runtime recovery regression',
    ])
    document = runner.run(args)
    return document, guard


# ── The production partial state, reproduced exactly ────────────────────────

def test_the_production_partial_state_is_reproduced(app, monkeypatch):
    """Q1-Q5 evidence present, completeness raises, Q6-Q8 evidence absent."""
    _seed()
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )

    for key in BEFORE_THE_STOP:
        assert document.get(key), f'{key} was observed and must survive'
    # The four observers that ran before the stop each left their evidence.
    stored = document['stored_game_evidence']
    assert stored.get('schedule') is not None
    assert stored.get('baseball_state') is not None
    for key in AFTER_THE_STOP:
        assert document.get(key) is None, f'{key} runs after the stop'


def test_the_stage_ledger_names_where_the_run_stopped(app, monkeypatch):
    _seed()
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )

    execution = document['execution']
    assert execution['last_completed_stage'] == audit.STAGE_APPEARANCE_LEDGER
    assert execution['failed_stage'] == audit.STAGE_COMPLETENESS
    assert execution['error_observed'] is True
    assert execution['execution_complete'] is False
    # Everything before the stop is listed; nothing after it is.
    assert audit.STAGE_STORED_SCHEDULE in execution['completed_stages']
    assert audit.STAGE_COMPLETENESS not in execution['completed_stages']
    assert audit.STAGE_COMPLETE not in execution['completed_stages']
    # The closing digest deliberately runs after the stop to finish the
    # read-only proof. It is recorded as having run, but it must not move
    # last_completed_stage past where the run actually died.
    assert audit.STAGE_AFTER_FINGERPRINTS in execution['completed_stages']
    assert execution['last_completed_stage'] != audit.STAGE_AFTER_FINGERPRINTS


def test_the_baseline_survives_the_stop(app, monkeypatch):
    """The regression that made a good baseline look unavailable."""
    _seed()
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )

    proof = document['read_only_proof']
    assert proof['before_fingerprints'] is not None
    assert proof['after_fingerprints'] is not None
    assert proof['fingerprints_match'] is True
    assert proof['changed_scopes'] == []
    assert audit.UNPROVEN_FINGERPRINTS_UNAVAILABLE not in (
        document['verdict']['unproven_reasons']
    )


def test_the_guard_is_released_even_when_a_stage_raises(app, monkeypatch):
    _seed()
    document, guard = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )
    assert guard.released is True
    assert document['read_only_proof']['advisory_guard_released'] is True


def test_a_partial_run_is_unproven_not_a_pass(app, monkeypatch):
    _seed()
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )
    verdict = document['verdict']
    assert verdict['result'] == 'UNPROVEN'
    assert verdict['exit_code'] == 2
    assert audit.UNPROVEN_AUDIT_EXECUTION_ERROR in verdict['unproven_reasons']


# ── The error class is bounded, and says nothing about the data ────────────

@pytest.mark.parametrize('exception,expected', [
    (NameError("name '_as_date' is not defined"),
     audit.ERROR_CLASS_AUDIT_CODE_DEFECT),
    (KeyError('window_start'), audit.ERROR_CLASS_MISSING_ATTRIBUTE),
    (AttributeError('status_state'), audit.ERROR_CLASS_MISSING_ATTRIBUTE),
    (TypeError("'<' not supported between 'str' and 'NoneType'"),
     audit.ERROR_CLASS_UNEXPECTED_SHAPE),
    (ZeroDivisionError('division by zero'), audit.ERROR_CLASS_ARITHMETIC),
])
def test_each_error_class_is_from_the_closed_vocabulary(exception, expected):
    assert audit.classify_error(exception) == expected
    assert expected in audit.SAFE_ERROR_CLASSES


def test_an_unknown_exception_type_is_classified_not_described():
    class SomethingNobodyAnticipated(Exception):
        pass

    assert audit.classify_error(SomethingNobodyAnticipated('detail')) == (
        audit.ERROR_CLASS_UNCLASSIFIED
    )


def test_a_database_error_subclass_resolves_through_its_bases():
    from sqlalchemy.exc import ProgrammingError

    assert audit.classify_error(
        ProgrammingError('SELECT secret', {}, Exception('boom')),
    ) in audit.SAFE_ERROR_CLASSES


def test_the_exception_text_never_reaches_the_document(app, monkeypatch):
    """The whole point of a bounded class: the message stays out."""
    _seed()
    secret = 'CONNECTION postgres://user:hunter2@db.internal/prod ROW 822867x'
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError(secret),
    )

    rendered = json.dumps(document, default=str) + runner.render_markdown(
        document
    )
    assert secret not in rendered
    assert 'hunter2' not in rendered
    assert 'db.internal' not in rendered
    assert 'Traceback' not in rendered
    assert 'RuntimeError' not in rendered
    assert document['execution']['safe_error_class'] in (
        audit.SAFE_ERROR_CLASSES
    )
    assert document['execution']['error_detail_withheld'] is True


def test_a_stage_name_outside_the_vocabulary_is_refused():
    ledger = runner._StageLedger()
    ledger.completed('a stage that does not exist')
    assert ledger.last_completed == audit.STAGE_NOT_STARTED
    ledger.failed('another invented stage', RuntimeError('x'))
    assert ledger.failed_stage == audit.STAGE_NOT_STARTED


def test_only_the_first_failure_is_recorded():
    """A cascade must not rewrite where the run actually stopped."""
    ledger = runner._StageLedger()
    ledger.failed(audit.STAGE_COMPLETENESS, NameError('first'))
    ledger.failed(audit.STAGE_AFTER_FINGERPRINTS, RuntimeError('second'))
    assert ledger.failed_stage == audit.STAGE_COMPLETENESS
    assert ledger.error_class == audit.ERROR_CLASS_AUDIT_CODE_DEFECT


# ── The clean run: every stage completes ───────────────────────────────────

def test_a_clean_run_reaches_the_final_stage(app, monkeypatch):
    _seed()
    document, _ = _drive(app, monkeypatch)

    execution = document['execution']
    assert execution['failed_stage'] is None
    assert execution['safe_error_class'] == audit.ERROR_CLASS_NONE
    assert execution['last_completed_stage'] == audit.STAGE_COMPLETE
    assert execution['execution_complete'] is True
    assert audit.UNPROVEN_AUDIT_EXECUTION_ERROR not in (
        document['verdict']['unproven_reasons']
    )


def test_the_completeness_path_runs_against_a_real_plan(app, monkeypatch):
    """The exact path that raised NameError in production.

    Every pre-existing test drove membership with a stub plan, which is why a
    dead reference to a helper the runner never imported survived review and
    reached production. This one builds the plan from the database.
    """
    _seed()
    document, _ = _drive(app, monkeypatch)

    assert document['game_ingestion_completeness'] is not None
    classification = document['unresolved_final_games']
    assert classification['membership_available'] is True
    # The reconstruction covers exactly the canonical set, no more and no less.
    assert classification['reconstructed_count'] == (
        classification['authority_unresolved_final_games']
    )
    assert classification['reconciles_with_authority'] is True
    assert classification['missing_canonical_members'] == []
    assert classification['every_member_classified_once'] is True
    assert classification['reconstructed_count'] > 0


def test_the_remaining_evidence_areas_complete(app, monkeypatch):
    """Player attribution, the snapshot gate, and the backlog all finish."""
    _seed()
    document, _ = _drive(app, monkeypatch)

    for key in BEFORE_THE_STOP + AFTER_THE_STOP:
        assert document.get(key) is not None, key

    gate = document['snapshot_publication']
    # Incident facts and current facts stay in separate blocks.
    assert 'incident' in gate and 'current' in gate


def test_the_read_only_proof_is_complete_on_a_clean_run(app, monkeypatch):
    _seed()
    document, _ = _drive(app, monkeypatch)

    proof = document['read_only_proof']
    assert proof['transaction_read_only_enabled'] is True
    assert proof['read_only_probe_refused'] is True
    assert proof['before_fingerprints'] is not None
    assert proof['after_fingerprints'] is not None
    assert proof['fingerprints_match'] is True
    assert proof['durable_write_attempts'] == 0
    assert proof['advisory_guard_released'] is True


# ── Question 3: current non-reproduction is not an incident explanation ────

def test_question_three_is_unanswered_without_the_incident_input(
    app, monkeypatch,
):
    _seed()
    document, _ = _drive(app, monkeypatch)

    third = _question(document, audit.QUESTION_PREFLIGHT_PRODUCED_OTHER)
    assert third['answered'] is False
    assert third['unproven_reason'] == audit.MAPPING_INPUT_NOT_RECONSTRUCTED
    evidence = third['evidence']
    assert evidence['incident_mapping_input_recovered'] is False
    assert evidence['incident_reconstructible_from_artifacts'] is False


def test_question_three_is_not_answered_by_a_current_reproduction():
    """Even when today's mapping DOES return 'other', that is not the answer.

    A current run reproducing the incident value is a coincidence of inputs
    until the incident's own input is recovered. Answering on it would let a
    game that happens to be postponed today explain a mapping from days ago.
    """
    observations = _observations(current_state='other')
    questions = runner.build_questions(
        observations, runner.build_authority_comparison(observations),
        audit.canonical_module_drift({}),
        incident_mapping=audit.incident_mapping_input(None),
    )
    third = _by_id(questions)[audit.QUESTION_PREFLIGHT_PRODUCED_OTHER]
    assert third['evidence']['current_result_reproduces_incident'] is True
    assert third['answered'] is False


def test_question_three_answers_on_a_positive_reconstruction():
    observations = _observations(current_state='final')
    shadow = {
        'sync_summary': {
            'preflight_status_payloads': {
                str(GAME): {
                    'abstractGameState': 'Live', 'codedGameState': 'I',
                    'detailedState': 'In Progress', 'statusCode': 'I',
                },
            },
        },
    }
    reconstruction = audit.incident_mapping_input(shadow)
    assert reconstruction['input_recovered'] is True
    assert reconstruction['remapped_status_state'] == 'other'
    assert reconstruction['reproduces_incident_state'] is True

    questions = runner.build_questions(
        observations, runner.build_authority_comparison(observations),
        audit.canonical_module_drift({}), incident_mapping=reconstruction,
    )
    third = _by_id(questions)[audit.QUESTION_PREFLIGHT_PRODUCED_OTHER]
    assert third['answered'] is True
    assert third['unproven_reason'] is None
    # Answered from the incident, while today's differing result is still
    # reported rather than quietly dropped.
    assert third['evidence']['current_mapped_status_state'] == 'final'


def test_the_recovered_status_content_is_never_reported():
    shadow = {
        'sync_summary': {
            'preflight_status_payloads': {
                str(GAME): {
                    'abstractGameState': 'Live', 'codedGameState': 'I',
                    'detailedState': 'Suspended: Rain at Nationals Park',
                    'statusCode': 'I',
                },
            },
        },
    }
    rendered = json.dumps(audit.incident_mapping_input(shadow), default=str)
    assert 'Nationals Park' not in rendered
    assert 'abstractGameState' not in rendered
    assert 'Live' not in rendered
    assert 'mapping_input_fields_recovered' in rendered


# ── Question 4: an unobserved plan is not an exclusion ─────────────────────

def test_an_unobserved_plan_is_unproven_not_excluded(app, monkeypatch):
    """The exact misreport in the production artifact."""
    _seed()
    document, _ = _drive(
        app, monkeypatch, break_completeness=RuntimeError('boom'),
    )

    comparison = document['authority_comparison']
    assert comparison['planner_classification'] == (
        audit.PLANNER_CLASS_UNPROVEN
    )
    assert comparison['planner_classification'] != (
        audit.PLANNER_CLASS_EXCLUDED
    )
    assert comparison['planner_evidence_observed'] is False
    assert comparison['planner_exclusion_reason'] is None

    fourth = _question(document, audit.QUESTION_LEDGER_COUNTED_COMPLETED)
    assert fourth['answered'] is False
    assert fourth['unproven_reason'] == 'planner_evidence_not_observed'


def test_an_observed_plan_still_classifies_normally(app, monkeypatch):
    _seed()
    document, _ = _drive(app, monkeypatch)

    comparison = document['authority_comparison']
    assert comparison['planner_evidence_observed'] is True
    assert comparison['planner_classification'] in (
        audit.PLANNER_CLASS_PLANNED, audit.PLANNER_CLASS_EXCLUDED,
    )
    fourth = _question(document, audit.QUESTION_LEDGER_COUNTED_COMPLETED)
    assert fourth['answered'] is True


def test_an_exclusion_reason_requires_a_proven_exclusion():
    """A reason without an exclusion would read as a planner finding."""
    observations = _observations()
    observations['completeness'] = {
        'plan': {'disputed_game_exclusion_reason': 'outside_window'},
    }
    comparison = runner.build_authority_comparison(observations)
    assert comparison['planner_classification'] == (
        audit.PLANNER_CLASS_UNPROVEN
    )
    assert comparison['planner_exclusion_reason'] is None


# ── Helpers ────────────────────────────────────────────────────────────────

def _question(document, question_id):
    return _by_id(document['questions'])[question_id]


def _by_id(questions):
    return {entry['question_id']: entry for entry in questions}


def _observations(*, current_state='final'):
    return {
        'official_status': {
            'game_found_in_source': True,
            'normalized': {'detailed_state': 'Final', 'status_code': 'F'},
            'canonical_status_state': current_state,
            'canonical_finality_state': 'final',
            'canonical_finality_reason': 'final_status',
            'official_classification': audit.OFFICIAL_CLASS_FINAL,
        },
        'stored_schedule': {
            'row_count': 2, 'stored_status_state': 'final',
            'distinct_status_states': ['final'], 'team_ids': [137, 140],
            'rows_agree': True, 'linked_replacement_game_pks': [],
        },
        'appearance_ledger': {
            'disputed_game_has_stored_final_row': True,
            'membership_rule': 'rule', 'reasons': [],
        },
    }
