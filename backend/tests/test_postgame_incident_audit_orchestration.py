"""Runtime orchestration: what the audit actually does, not what it declares.

These exercise the real call paths behind the five runtime blockers. A constant
or a docstring can say the box score is fetched once; only driving the code
with a counting client proves it, and only comparing that count against the
artifact proves the accounting is honest.

The recurring hazard here is an audit that reports a number it did not earn.
Every assertion below compares ACTUAL behaviour against REPORTED behaviour.
"""

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
from models.dashboard_snapshot import DashboardSnapshot
from models.scheduled_game import ScheduledGame
from services import game_ingestion_completeness
from services import postgame_publication_incident_audit as audit
from utils.db import db

import scripts.run_postgame_publication_incident_audit as runner


SLATE = audit.INCIDENT_SLATE_DATE
GAME = audit.INCIDENT_GAME_PK


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


class CountingClient:
    """Stands in for the MLB client and records every call it receives."""

    def __init__(self, *, games=None, boxscore=None, fail=()):
        self.schedule_calls = []
        self.boxscore_calls = []
        self._games = games if games is not None else []
        self._boxscore = boxscore
        self._fail = set(fail)

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        self.schedule_calls.append((start_date, end_date))
        if 'schedule' in self._fail:
            raise RuntimeError('upstream unavailable')
        return [
            game for game in self._games
            if start_date <= game['officialDate'] <= end_date
        ]

    def get_game_boxscore(self, game_pk):
        self.boxscore_calls.append(game_pk)
        if 'boxscore' in self._fail:
            raise RuntimeError('upstream unavailable')
        return self._boxscore

    @property
    def total_calls(self):
        return len(self.schedule_calls) + len(self.boxscore_calls)


def _game(game_pk, official_date, *, detailed='Final', coded='F',
          abstract='Final'):
    return {
        'gamePk': game_pk,
        'officialDate': official_date,
        'gameType': 'R',
        'doubleHeader': 'N',
        'gameNumber': 1,
        'status': {
            'abstractGameState': abstract,
            'detailedState': detailed,
            'codedGameState': coded,
            'statusCode': coded,
        },
        'teams': {'home': {'team': {'id': 1}}, 'away': {'team': {'id': 2}}},
        'venue': {'id': 9},
    }


def _boxscore(pitcher_ids):
    players = {}
    for index, mlb_id in enumerate(pitcher_ids):
        players[f'ID{mlb_id}'] = {
            'person': {'id': mlb_id, 'fullName': f'P{mlb_id}'},
            'position': {'abbreviation': 'P'},
            'stats': {'pitching': {
                'inningsPitched': '1.0', 'outs': 3, 'pitchesThrown': 12,
                'battersFaced': 3, 'hits': 0, 'runs': 0, 'earnedRuns': 0,
                'baseOnBalls': 0, 'strikeOuts': 1,
            }},
            'gameStatus': {},
        }
    return {
        'teams': {
            'home': {'players': players, 'pitchers': list(pitcher_ids)},
            'away': {'players': {}, 'pitchers': []},
        },
    }


def _gateway(client, budget=None):
    return runner.SourceGateway(budget or audit.SourceCallBudget(), client)


# ── Blocker 1: the box score is bought once ─────────────────────────────────

def test_the_disputed_box_score_is_requested_exactly_once():
    client = CountingClient(
        games=[_game(GAME, SLATE.isoformat())],
        boxscore=_boxscore([687239, 615698]),
    )
    gateway = _gateway(client)
    window = gateway.fetch_window(SLATE - timedelta(days=7), SLATE)

    observation = runner.observe_official_status(
        GAME, {'rows': []}, gateway, window_games=window,
    )

    assert client.boxscore_calls == [GAME]
    assert observation['boxscore_observed'] is True
    assert observation['boxscore_pitcher_ids'] == [615698, 687239]
    assert observation['raw_boxscore_retained'] is False
    # The disputed game was inside the window, so it cost no extra call.
    assert observation['found_in_window_response'] is True
    assert len(client.schedule_calls) == 1


def test_player_attribution_reuses_the_already_observed_pitcher_ids(app):
    from models.pitcher import Pitcher

    for mlb_id in audit.INCIDENT_PLAYER_IDS:
        db.session.add(Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}'))
    db.session.commit()

    client = CountingClient(
        games=[_game(GAME, SLATE.isoformat())],
        boxscore=_boxscore(list(audit.INCIDENT_PLAYER_IDS[:2])),
    )
    gateway = _gateway(client)
    window = gateway.fetch_window(SLATE - timedelta(days=7), SLATE)
    official = runner.observe_official_status(
        GAME, {'rows': []}, gateway, window_games=window,
    )
    before = len(client.boxscore_calls)

    result = runner.attribute_player_mismatches({}, {}, official)

    # Attribution issues no further network call of any kind.
    assert len(client.boxscore_calls) == before == 1
    assert result['attributed_to_disputed_game'] == 2
    attributed = {
        entry['player_id'] for entry in result['players']
        if entry['attributable_to_disputed_game']
    }
    assert attributed == set(audit.INCIDENT_PLAYER_IDS[:2])


def test_no_mlb_client_call_exists_outside_the_gateway():
    """Structural: only SourceGateway may name a client method."""
    import ast

    source = open(runner.__file__, encoding='utf-8').read()
    tree = ast.parse(source)
    gateway = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == 'SourceGateway'
    )
    inside = {id(node) for node in ast.walk(gateway)}

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in (
            'get_schedule', 'get_game_boxscore',
        ) and id(node) not in inside:
            offenders.append(func.attr)
    assert offenders == []
    assert source.count('get_game_boxscore') == 1


def test_actual_calls_equal_artifact_reported_calls():
    client = CountingClient(
        games=[_game(GAME, SLATE.isoformat())],
        boxscore=_boxscore([687239]),
    )
    budget = audit.SourceCallBudget()
    gateway = _gateway(client, budget)
    window = gateway.fetch_window(SLATE - timedelta(days=7), SLATE)
    runner.observe_official_status(
        GAME, {'rows': []}, gateway, window_games=window,
    )

    state = budget.state()
    assert state['total_attempted'] == client.total_calls
    assert state['calls_attempted'][audit.CALL_KIND_SCHEDULE] == len(
        client.schedule_calls
    )
    assert state['calls_attempted'][audit.CALL_KIND_BOXSCORE] == len(
        client.boxscore_calls
    )
    assert state['total_succeeded'] == client.total_calls
    assert state['total_failed'] == 0


def test_a_source_failure_is_counted_as_attempted_and_failed():
    client = CountingClient(games=[], fail={'schedule'})
    budget = audit.SourceCallBudget()
    gateway = _gateway(client, budget)
    assert gateway.fetch_window(SLATE - timedelta(days=7), SLATE) is None

    state = budget.state()
    assert state['calls_attempted'][audit.CALL_KIND_SCHEDULE] == 1
    assert state['calls_failed'][audit.CALL_KIND_SCHEDULE] == 1
    assert state['total_attempted'] == client.total_calls


# ── Blocker 2: the schedule allowance is never guaranteed to run out ────────

def test_the_whole_horizon_costs_one_schedule_call():
    days = [SLATE - timedelta(days=offset) for offset in range(8)]
    client = CountingClient(
        games=[_game(900000 + i, day.isoformat())
               for i, day in enumerate(days)],
    )
    gateway = _gateway(client)
    gateway.fetch_window(SLATE - timedelta(days=7), SLATE)

    assert len(client.schedule_calls) == 1
    assert client.schedule_calls[0] == ('2026-07-27', '2026-08-03')
    assert len(gateway.window_games) == 8


def test_the_window_is_fetched_once_however_many_consumers_ask():
    client = CountingClient(games=[_game(GAME, SLATE.isoformat())])
    gateway = _gateway(client)
    for _ in range(4):
        gateway.fetch_window(SLATE - timedelta(days=7), SLATE)
    assert len(client.schedule_calls) == 1


def test_the_normal_path_stays_inside_eight_schedule_calls_with_no_refusals():
    client = CountingClient(
        games=[_game(GAME, SLATE.isoformat())],
        boxscore=_boxscore([687239]),
    )
    budget = audit.SourceCallBudget()
    gateway = _gateway(client, budget)
    window = gateway.fetch_window(SLATE - timedelta(days=7), SLATE)
    runner.observe_official_status(
        GAME, {'rows': []}, gateway, window_games=window,
    )

    state = budget.state()
    assert state['calls_attempted'][audit.CALL_KIND_SCHEDULE] <= 8
    assert state['total_refused_by_budget'] == 0
    assert state['required_call_refused'] is False
    assert state['total_attempted'] <= audit.SOURCE_CALL_TOTAL_BUDGET


def test_spending_an_allowance_exactly_is_not_unproven():
    """Eight successful schedule calls is a completed observation."""
    budget = audit.SourceCallBudget()
    for _ in range(8):
        assert budget.reserve(audit.CALL_KIND_SCHEDULE) is True
        budget.record_success(audit.CALL_KIND_SCHEDULE)

    state = budget.state()
    assert state['budget_exhausted'] is True        # informational only
    assert state['required_call_refused'] is False  # decision-relevant
    assert _decide(budget_state=state)['result'] != audit.RESULT_UNPROVEN


def test_a_refused_required_call_is_unproven():
    budget = audit.SourceCallBudget()
    for _ in range(8):
        budget.reserve(audit.CALL_KIND_SCHEDULE)
    assert budget.reserve(audit.CALL_KIND_SCHEDULE, required=True) is False

    state = budget.state()
    assert state['required_call_refused'] is True
    decision = _decide(budget_state=state)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_SOURCE_BUDGET_EXHAUSTED in (
        decision['unproven_reasons']
    )


def test_a_refused_optional_call_is_not_unproven():
    budget = audit.SourceCallBudget()
    for _ in range(8):
        budget.reserve(audit.CALL_KIND_SCHEDULE)
    assert budget.reserve(audit.CALL_KIND_SCHEDULE, required=False) is False

    state = budget.state()
    assert state['budget_refused_a_call'] is True
    assert state['required_call_refused'] is False
    assert _decide(budget_state=state)['result'] != audit.RESULT_UNPROVEN


def test_total_source_calls_never_exceed_twenty():
    budget = audit.SourceCallBudget()
    attempted = 0
    for kind in audit.CALL_KINDS:
        for _ in range(50):
            if budget.reserve(kind, required=False):
                attempted += 1
    assert attempted <= audit.SOURCE_CALL_TOTAL_BUDGET == 20
    assert budget.state()['total_attempted'] == attempted


# ── Blocker 3: membership is the canonical unresolved set ──────────────────

def test_the_published_count_is_len_of_the_canonical_membership(app):
    """94 planned critical games with 63 unresolved must classify 63."""
    from models.game_ingestion_work_item import GameIngestionWorkItem

    # 63 games carry an unresolved critical work item; 31 more are planned
    # critical and already completed, so planned=94 but unresolved=63.
    for index in range(63):
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=700000 + index, represented_date=SLATE,
            status=GameIngestionWorkItem.STATUS_PLANNED,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        ))
    db.session.commit()

    plan = {'items': [], 'schedule_authority_missing': []}
    membership = game_ingestion_completeness.unresolved_final_game_membership(
        SLATE, plan=plan,
    )
    completeness = (
        game_ingestion_completeness.build_game_ingestion_completeness(
            SLATE, plan=plan,
        )
    )

    assert len(membership['game_pks']) == 63
    assert completeness['unresolved_final_games'] == 63
    assert completeness['unresolved_final_games'] == len(
        membership['game_pks']
    )


def test_membership_is_smaller_than_the_planned_critical_total(app):
    """The distinction the old code collapsed: planned != unresolved."""
    from models.game_ingestion_work_item import GameIngestionWorkItem

    class _Planned:
        def __init__(self, game_pk, reason):
            self.game_pk = game_pk
            self.criticality = (
                GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
            )
            self.candidate_reason = reason

    # 94 planned critical, of which 31 are corrected_final re-checks that are
    # complete at their last known revision and therefore not unresolved.
    items = [
        _Planned(800000 + i, GameIngestionWorkItem.REASON_NEWLY_FINAL)
        for i in range(63)
    ] + [
        _Planned(900000 + i, GameIngestionWorkItem.REASON_CORRECTED_FINAL)
        for i in range(31)
    ]
    plan = {'items': items, 'schedule_authority_missing': []}

    membership = game_ingestion_completeness.unresolved_final_game_membership(
        SLATE, plan=plan,
    )
    assert len(membership['critical_planned_game_pks']) == 94
    assert len(membership['game_pks']) == 63
    assert len(membership['game_pks']) < len(
        membership['critical_planned_game_pks']
    )


def test_a_reconstruction_that_does_not_reconcile_leaves_q7_unanswered():
    observations = _observations()
    observations['completeness']['unresolved_classification'] = {
        'all_classified': True, 'category_totals_match': True,
        'reconciles_with_authority': False, 'missing_canonical_members': [7],
        'reconstructed_count': 94, 'authority_unresolved_final_games': 63,
        'classification_counts': {}, 'represented_dates': [],
    }
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(
            observations, runner.build_authority_comparison(observations),
            audit.canonical_module_drift({}),
        )
    }
    seventh = questions[audit.QUESTION_UNRESOLVED_GAME_CLASSIFICATION]
    assert seventh['answered'] is False
    assert seventh['unproven_reason'] == (
        'unresolved_membership_does_not_reconcile_with_authority'
    )
    assert _decide(questions=list(questions.values()))['result'] == (
        audit.RESULT_UNPROVEN
    )


# ── Blocker 4: incident facts survive production recovery ──────────────────

def test_incident_withholding_survives_a_recovered_production(app, monkeypatch):
    """Incident served 343, candidate 344 withheld, today serves 347.

    Which snapshot is servable is `dashboard_snapshot`'s decision, not this
    audit's, so that boundary is stubbed rather than re-derived here — the
    behaviour under test is whether the incident verdict survives production
    having moved on, and it must not depend on today's selection at all.
    """
    from services import dashboard_snapshot as snapshot_service
    from datetime import datetime

    from models.sync_run import SyncRun

    # Published snapshots are constrained to carry a sync run, so the fixture
    # has to be as real as the schema demands.
    run = SyncRun(job_name='fixture', status='success')
    db.session.add(run)
    db.session.flush()
    for snapshot_id, status, through in (
        (343, 'ready', SLATE - timedelta(days=1)),
        (344, 'pending', SLATE),
        (347, 'ready', date.today()),
    ):
        published = status == 'ready'
        db.session.add(DashboardSnapshot(
            id=snapshot_id, snapshot_type='bullpen_dashboard', status=status,
            is_published=published, payload={}, payload_version=1,
            data_through=through,
            sync_run_id=run.id if published else None,
            published_at=datetime.utcnow() if published else None,
        ))
    db.session.commit()

    recovered = db.session.get(DashboardSnapshot, 347)
    monkeypatch.setattr(
        snapshot_service, 'get_latest_valid_dashboard_snapshot',
        lambda *args, **kwargs: recovered,
    )

    gate = runner.observe_snapshot_gate(
        {'publication_proof': {
            'verified': False,
            'reason_codes': list(audit.INCIDENT_PUBLICATION_REASON_CODES),
        }},
        {'unresolved_classification': {}, 'completeness': {}},
    )

    incident = gate['incident']
    current = gate['current']

    # The incident verdict is unchanged by what production serves today.
    assert incident['incident_served_snapshot_id'] == 343
    assert incident['incident_candidate_status'] == 'pending'
    assert incident['incident_withholding_was_fail_closed'] is True
    assert current['current_served_snapshot_id'] != 343
    assert current['current_condition_recovered'] is True
    assert current['prior_snapshot_still_serving'] is False


def test_candidate_still_pending_is_exact_not_merely_not_ready(app):
    db.session.add(DashboardSnapshot(
        id=audit.INCIDENT_CANDIDATE_SNAPSHOT_ID,
        snapshot_type='bullpen_dashboard', status='failed',
        is_published=False, payload={}, payload_version=1, data_through=SLATE,
    ))
    db.session.commit()

    gate = runner.observe_snapshot_gate({}, {})
    # A failed snapshot is not a pending one.
    assert gate['current']['candidate_current_status'] == 'failed'
    assert gate['current']['candidate_still_pending'] is False


@pytest.mark.parametrize('unresolved,ledger_missing,expected', [
    (60, [audit.INCIDENT_GAME_PK], 'unproven'),   # membership unknown
    (0, [audit.INCIDENT_GAME_PK], True),          # exactly one blocker
    (0, [], False),                               # zero deficits
    (0, [audit.INCIDENT_GAME_PK, 999999], False),  # one unrelated deficit
])
def test_sole_blocker_requires_positive_exact_evidence(
    monkeypatch, unresolved, ledger_missing, expected,
):
    monkeypatch.setitem(
        audit.INCIDENT_COMPLETENESS, 'unresolved_final_games', unresolved,
    )
    result = runner._incident_blocker_set(
        {'missing_game_pks': ledger_missing}
    )
    assert result['sole_blocker'] == expected


def test_the_sixty_game_signal_contribution_is_unproven_without_evidence():
    assert runner._incident_signal_contribution(
        list(audit.INCIDENT_PUBLICATION_REASON_CODES)
    ) == 'unproven'
    assert runner._incident_signal_contribution(
        ['unresolved_final_games']
    ) is True


def test_gate_scope_reads_actual_classified_dates(app):
    db.session.add(DashboardSnapshot(
        id=audit.INCIDENT_CANDIDATE_SNAPSHOT_ID,
        snapshot_type='bullpen_dashboard', status='pending',
        is_published=False, payload={}, payload_version=1, data_through=SLATE,
    ))
    db.session.commit()

    same_slate = runner.observe_snapshot_gate({}, {
        'completeness': {'horizon_days': 7},
        'unresolved_classification': {
            'represented_dates': [SLATE.isoformat()],
            'dates_outside_incident_slate': [],
        },
    })
    assert same_slate['gate_scope']['requires_games_outside_slate'] is False

    wider = runner.observe_snapshot_gate({}, {
        'completeness': {'horizon_days': 7},
        'unresolved_classification': {
            'represented_dates': ['2026-07-29', SLATE.isoformat()],
            'dates_outside_incident_slate': ['2026-07-29'],
        },
    })
    assert wider['gate_scope']['requires_games_outside_slate'] is True
    # A horizon existing is not the same fact as the gate reaching outside it.
    assert same_slate['gate_scope']['publication_horizon_days'] == 7


# ── Blocker 5: governed row agreement ──────────────────────────────────────

def _row(team_id, opponent, home_away, **overrides):
    row = ScheduledGame(
        team_id=team_id, game_pk=GAME, game_date=SLATE,
        opponent_team_id=opponent, home_away=home_away,
        status_state='final', status_code='F', game_type='R',
        game_number=1, doubleheader='N', source='schedule_ingestion',
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_agreeing_rows_report_full_governance_agreement():
    rows = [_row(1, 2, 'home'), _row(2, 1, 'away')]
    agreement = runner._row_agreement(rows)
    assert agreement['full_row_governance_agreement'] is True
    assert agreement['disagreeing_fields'] == []
    assert set(agreement['checks']) == set(audit.ROW_AGREEMENT_FIELDS)


@pytest.mark.parametrize('field,value', [
    ('status_code', 'O'),
    ('game_type', 'S'),
    ('game_number', 2),
    ('doubleheader', 'Y'),
    ('resumed_from_game_pk', 811111),
    ('resumed_to_game_pk', 822222),
    ('source', 'other_source'),
    ('game_date', date(2026, 8, 2)),
])
def test_any_governed_field_conflict_breaks_agreement(field, value):
    rows = [_row(1, 2, 'home'), _row(2, 1, 'away', **{field: value})]
    agreement = runner._row_agreement(rows)
    assert agreement['full_row_governance_agreement'] is False
    assert field in agreement['disagreeing_fields']


def test_non_reciprocal_team_identity_is_a_conflict():
    rows = [_row(1, 2, 'home'), _row(2, 99, 'away')]
    agreement = runner._row_agreement(rows)
    assert agreement['checks']['reciprocal_team_identity'] is False
    assert agreement['full_row_governance_agreement'] is False


def test_two_home_rows_are_a_conflict():
    rows = [_row(1, 2, 'home'), _row(2, 1, 'home')]
    agreement = runner._row_agreement(rows)
    assert agreement['checks']['reciprocal_home_away_roles'] is False


def test_duplicate_team_rows_are_a_conflict():
    rows = [_row(1, 2, 'home'), _row(1, 2, 'away')]
    agreement = runner._row_agreement(rows)
    assert agreement['checks']['unique_team_rows'] is False


def test_timestamp_differences_are_not_baseball_conflicts():
    from datetime import datetime

    first = _row(1, 2, 'home')
    second = _row(2, 1, 'away')
    first.created_at = datetime(2026, 8, 3, 23, 59, 59)
    second.created_at = datetime(2026, 8, 4, 0, 0, 1)
    first.updated_at = datetime(2026, 8, 4, 1, 0, 0)
    second.updated_at = datetime(2026, 8, 4, 2, 0, 0)

    agreement = runner._row_agreement([first, second])
    assert agreement['full_row_governance_agreement'] is True
    assert agreement['timestamps_excluded'] == ['created_at', 'updated_at']


def test_a_conflict_in_any_governed_field_proves_the_row_conflict_finding():
    observations = _observations(stored_schedule={
        'disagreeing_fields': ['game_number'],
        'full_row_governance_agreement': False,
        'rows_agree': False, 'paired_row_disagreement': True,
        'distinct_status_states': ['final'],   # status_state alone agrees
        'status_state_agreement': True,
    })
    finding = _findings(observations)[
        audit.CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT
    ]
    assert finding['proven'] is True
    assert any('game_number' in item for item in
               finding['supporting_evidence'])


def test_probable_classification_is_populated_not_left_null():
    normalized = runner._normalize_official_game(
        _game(GAME, SLATE.isoformat()), audit.OFFICIAL_CLASS_FINAL,
    )
    assert normalized['probable_classification'] == audit.OFFICIAL_CLASS_FINAL
    assert set(normalized) == set(audit.OFFICIAL_STATUS_FIELDS)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _observations(**overrides):
    base = {
        'official_status': {
            'game_found_in_source': True,
            'official_classification': audit.OFFICIAL_CLASS_FINAL,
            'canonical_finality_state': 'final_and_usable',
            'canonical_finality_reason': 'final',
            'canonical_status_state': 'final',
            'normalized': {'detailed_state': 'Final', 'status_code': 'F'},
            'relationship': {
                'is_rescheduled': False, 'is_resumed': False,
                'replacement_game_pk': None, 'resolved': True,
            },
        },
        'stored_schedule': {
            'row_count': 2, 'rows': [], 'team_ids': [1, 2],
            'duplicate_team_rows': False, 'distinct_status_states': ['final'],
            'rows_agree': True, 'paired_row_disagreement': False,
            'full_row_governance_agreement': True, 'disagreeing_fields': [],
            'stored_status_state': 'final', 'counts_as_ledger_final': True,
            'all_rows_final': True, 'linked_replacement_game_pks': [],
        },
        'baseball_state': {'game_logs': {'row_count': 8}},
        'appearance_ledger': {
            'disputed_game_has_stored_final_row': True,
            'disputed_game_in_deficit_set': False, 'reasons': [],
            'membership_rule': 'rule',
        },
        'completeness': {
            'plan': {'disputed_game_planned': True,
                     'disputed_game_exclusion_reason': None,
                     'finality_conflicts': []},
            'completeness': {'horizon_days': 7},
            'unresolved_classification': {
                'all_classified': True, 'category_totals_match': True,
                'reconciles_with_authority': True,
                'missing_canonical_members': [],
                'scope_invalid_count': 0, 'classification_counts': {},
                'reconstructed_count': 0, 'represented_dates': [],
            },
        },
        'snapshot_gate': {
            'incident': {'incident_withholding_was_fail_closed': True},
            'current': {
                'candidate_still_pending': True,
                'candidate_snapshot': {'id': 344, 'status': 'pending'},
                'slate_coverage': {'complete_enough_to_publish': False,
                                   'validations_passed': True,
                                   'reason_codes': ['coverage_incomplete']},
            },
            'gate_scope': {},
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
    return {
        entry['classification']: entry
        for entry in runner.build_findings(
            observations, runner.build_authority_comparison(observations),
            audit.canonical_module_drift({}),
        )
    }


def _decide(**overrides):
    kwargs = {
        'questions': [
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        'findings': [],
        'read_only_proof': {
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        'artifact_ingestion': {
            'missing_required': [], 'unreadable_required': [],
            'digest_mismatches': [], 'all_required_present': True,
            'incident_validation': {'any_mismatch': False},
        },
        'budget_state': audit.SourceCallBudget().state(),
    }
    kwargs.update(overrides)
    return audit.decide(**kwargs)
