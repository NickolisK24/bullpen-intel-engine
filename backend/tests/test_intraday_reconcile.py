"""Tests for the audit-only intraday reconciliation mode (Phase 1).

This suite proves change detection is accurate across all lanes AND that the
audit is strictly read-only and correctly coordinated with the public sync
writer lock, before any write behavior is authorized.

Requirement-to-test coverage map (acceptance behaviors → proving test):

  1  No-change roster audit .............. test_lane1_no_change
  2  Stored inactive observed active ..... test_lane1_recall
  3  Stored active observed inactive ..... test_lane1_il_placement / test_lane1_option
  4  Recall (Seth Johnson class) ......... test_lane1_recall
  5  IL placement ........................ test_lane1_il_placement
  6  IL activation ....................... test_lane1_il_activation
  7  Option .............................. test_lane1_option
  8  DFA / active-roster removal ......... test_lane1_dfa
  9  Team-assignment change .............. test_lane1_team_assignment_change
  10 Newly discovered active player ...... test_lane1_newly_discovered_active_pitcher
  11 Unresolved identity stays unresolved  test_lane1_reports_unresolvable_source_identity
  12 Identity never guessed from name .... test_lane1_never_guesses_identity_by_name
  13 Conflicting official team evidence .. test_lane1_conflicting_official_team_evidence
  14 Non-player transaction .............. test_lane2_classifies_transactions
  15 New actionable player transaction ... test_lane2_classifies_transactions
  16 Already-reflected transaction ....... test_lane2_classifies_transactions
  17 Stored tx roster effect unreflected . test_lane2_stored_effect_not_reflected
  18 Transaction identity failure ........ test_lane2_classifies_transactions
  19 Newly final game .................... test_lane3_detects_newly_final_game
  20 Postponed game ...................... test_lane3_detects_postponed
  21 Rescheduled game .................... test_lane3_detects_rescheduled
  22 In-progress game .................... test_lane3_detects_in_progress
  23 Stored finality conflict ............ test_lane3_detects_stored_finality_conflict
  24 Newly discovered game ............... test_lane3_detects_newly_discovered_game
  25 Doubleheader / identity preserved ... test_lane3_preserves_doubleheader_identity,
                                           test_lane3_flags_reschedule_identity_issue
  26 Partial roster failure != no-change . test_lane1_partial_source_failure_is_not_false_no_change
  27 Partial tx failure != no-change ..... test_lane2_partial_source_failure_is_not_false_no_change
  28 Partial schedule failure != nochange  test_lane3_partial_source_failure_is_not_false_no_change
  29 No-change returns changed:false ..... test_no_change_returns_changed_false
  30 Changed result has lanes/teams/ids .. test_changed_result_includes_lanes_teams_pitchers
  31 would_refresh is descriptive only ... test_would_refresh_is_descriptive_only
  32 No roster mutation helper invoked ... test_no_mutation_helper_is_invoked
  33 No assignment mutation helper ....... test_no_mutation_helper_is_invoked
  34 No transaction mutation helper ...... test_no_mutation_helper_is_invoked
  35 No schedule mutation helper ......... test_no_mutation_helper_is_invoked
  36 No boxscore/player-log ingestion .... test_no_boxscore_or_gamelog_ingestion
  37 No fatigue recalculation ............ test_no_mutation_helper_is_invoked
  38 No snapshot built ................... test_no_write_sql_is_executed (+ safety block)
  39 No snapshot published ............... test_no_write_sql_is_executed (+ safety block)
  40 No Tonight warm ..................... test_no_write_sql_is_executed (+ safety block)
  41 No story generation ................. test_no_write_sql_is_executed (+ safety block)
  42 No dead-letter write/resolve/delete . test_no_mutation_helper_is_invoked
  43 No canonical ORM pending writes ..... test_audit_leaves_no_pending_orm_writes
  44 Writer-lock conflict safely skips ... test_lock_conflict_produces_skipped_result
  45 Lock release exception-safe ......... test_lock_released_on_unexpected_exception
  46 Intraday cannot fall through mode ... (workflow) test_intraday_job_is_gated_to_mode
  47 No intraday cron exists ............. (workflow) test_no_intraday_cron_added
  48 JSON output valid & versioned ....... test_artifact_is_json_serializable_and_versioned
  49 Deterministic content ............... test_identical_inputs_are_deterministic
  50 CLI stderr progress, stdout json .... test_cli_main_emits_single_json_object
  51 CLI exit 0 for success .............. test_cli_exit_code_success
  52 CLI exit 0 for safe lock skip ....... test_cli_exit_code_skipped
  53 CLI exit 1 for partial/failed ....... test_cli_exit_code_partial, test_cli_exit_code_failed
  54 --output equals stdout json ......... test_cli_output_matches_stdout
  55 --lanes cannot falsely mark skipped . test_lane_selection_runs_only_requested_lane

Lock coverage (Correction 2):
  same public advisory key ............... test_read_lock_uses_public_sync_writer_key
  lock conflict -> skipped ............... test_lock_conflict_produces_skipped_result
  no source calls after conflict ......... test_no_source_calls_after_lock_conflict
  no db mutation on conflict ............. test_no_db_mutation_on_lock_conflict
  lock released on success ............... test_lock_released_on_success
  lock released on partial ............... test_lock_released_on_partial_failure
  lock released on exception ............. test_lock_released_on_unexpected_exception
  no SyncRun reclaim/mutation ............ test_does_not_mutate_running_sync_run

Read-only proof (Correction 7): test_no_write_sql_is_executed inspects the SQL
actually issued; test_specific_rows_unchanged inspects DB row state; the mutator
tests replace prohibited functions with tripwires.

Private-helper regression (Correction 5): test_read_transaction_values_matches_internal.
"""

from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import event
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import intraday_reconcile
from services import sync_metadata
from services import transaction_ingestion
from services.roster_status import (
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_OPTIONED,
)
from services.roster_status_sync import (
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
)
from utils.db import db
from utils.time import utc_now_naive


PRODUCT_DATE = date(2026, 7, 16)
PHI = 143
NYM = 121


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


class _FakeMetrics:
    def __init__(self):
        self._calls = 0

    def reset(self):
        self._calls = 0

    def snapshot(self):
        return {'api_calls': self._calls, 'retries': 0, 'by_endpoint': {}}


class FakeMlbClient:
    """Read-only MLB client stand-in that counts every source method call."""

    def __init__(self, *, rosters=None, transactions=None, schedule=None, teams=None,
                 roster_errors=None, transactions_error=None, schedule_error=None):
        self.rosters = rosters or {}
        self.transactions = transactions or []
        self.schedule = schedule or []
        self.teams = teams or []
        self.roster_errors = roster_errors or {}
        self.transactions_error = transactions_error
        self.schedule_error = schedule_error
        self.metrics = _FakeMetrics()
        self.calls = {}

    def _count(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1
        self.metrics._calls += 1

    def get_all_teams(self, sport_id=1):
        self._count('get_all_teams')
        return list(self.teams)

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        self._count('get_team_roster')
        if (team_id, roster_type) in self.roster_errors:
            raise RuntimeError(self.roster_errors[(team_id, roster_type)])
        return list(self.rosters.get((team_id, roster_type), []))

    def get_transactions(self, start_date=None, end_date=None, **_kwargs):
        self._count('get_transactions')
        if self.transactions_error:
            raise RuntimeError(self.transactions_error)
        return list(self.transactions)

    def get_schedule(self, start_date=None, end_date=None, **_kwargs):
        self._count('get_schedule')
        if self.schedule_error:
            raise RuntimeError(self.schedule_error)
        return list(self.schedule)

    # Ingestion-only endpoints; must never be called by an audit.
    def get_game_boxscore(self, game_pk):
        self._count('get_game_boxscore')
        return {}

    def get_game_linescore(self, game_pk):
        self._count('get_game_linescore')
        return {}

    def get_pitcher_game_logs(self, player_id, season=None):
        self._count('get_pitcher_game_logs')
        return []


def roster_entry(player_id, name='Player', position='P', status=None):
    person = {'fullName': name}
    if player_id is not None:
        person['id'] = player_id
    entry = {'person': person, 'position': {'abbreviation': position}}
    if status is not None:
        entry['status'] = status
    return entry


ACTIVE = {'code': 'A', 'description': 'Active'}
IL15 = {'code': 'D15', 'description': '15-day IL'}
DFA_STATUS = 'Designated for assignment'


def _seed_pitcher(mlb_id, name, team_id, abbreviation, *, roster_status, active):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=team_id, team_name=f'Team {team_id}',
        team_abbreviation=abbreviation, position='P', active=active,
        roster_status=roster_status, roster_status_source='test_fixture',
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _seed_snapshot(pitcher, team_id, snapshot_date, roster_status):
    db.session.add(RosterStatusSnapshot(
        pitcher_id=pitcher.id, mlb_id=pitcher.mlb_id, team_id=team_id,
        snapshot_date=snapshot_date, roster_status=roster_status, active_roster=True,
        source='test_fixture',
    ))
    db.session.commit()


def _seed_stored_transaction(transaction):
    values, detail = transaction_ingestion.read_transaction_values(
        transaction,
        start_date=PRODUCT_DATE - timedelta(days=7),
        end_date=PRODUCT_DATE,
        timestamp=utc_now_naive(),
        sync_run_id=None,
    )
    assert detail is None, detail
    db.session.add(PlayerTransaction(**values))
    db.session.commit()


def _scheduled_pair(game_pk, home_id, away_id, *, status_code, status_state, game_date=PRODUCT_DATE):
    for team_id, home_away, opp in ((home_id, 'home', away_id), (away_id, 'away', home_id)):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=game_date, home_away=home_away,
            opponent_team_id=opp, status_code=status_code, status_state=status_state,
            source='test_fixture',
        ))
    db.session.commit()


def _game(pk, home, away, *, status_code, detailed, abstract, game_date=PRODUCT_DATE,
          doubleheader='N', game_number=None):
    game = {
        'gamePk': pk,
        'officialDate': game_date.isoformat(),
        'status': {'statusCode': status_code, 'detailedState': detailed, 'abstractGameState': abstract},
        'teams': {'home': {'team': {'id': home}}, 'away': {'team': {'id': away}}},
        'doubleHeader': doubleheader,
    }
    if game_number is not None:
        game['gameNumber'] = game_number
    return game


# Transaction fixtures reused by seeding + source.
TX_ALREADY = {
    'transaction_id': 't4', 'transaction_date': '2026-07-15', 'player_mlb_id': 100,
    'transaction_type_code': 'ACT', 'source_endpoint': transaction_ingestion.SOURCE_ENDPOINT,
}
TX_MISALIGNED = {
    'transaction_id': 't5', 'transaction_date': '2026-07-16', 'player_mlb_id': 400,
    'transaction_type_code': 'RECALL', 'to_team_id': NYM,
    'source_endpoint': transaction_ingestion.SOURCE_ENDPOINT,
}


@pytest.fixture
def scenario(app):
    """Seed stored state + a fake client that covers every detected delta."""
    _seed_pitcher(999, 'Seth Johnson', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    _seed_pitcher(100, 'Aaron Nola', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_pitcher(200, 'Traded Reliever', NYM, 'NYM', roster_status=STATUS_ACTIVE, active=True)
    _seed_pitcher(300, 'Injured Reliever', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_pitcher(301, 'Returning Reliever', PHI, 'PHI', roster_status=STATUS_IL_15, active=False)
    _seed_pitcher(302, 'Optioned Reliever', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_pitcher(303, 'Dfa Reliever', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_pitcher(555, 'Conflicted Reliever', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    misaligned = _seed_pitcher(400, 'Aligned Name', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(misaligned, PHI, PRODUCT_DATE, STATUS_ACTIVE)

    _seed_stored_transaction(TX_ALREADY)
    _seed_stored_transaction(TX_MISALIGNED)

    # Stored schedule.
    _scheduled_pair(700, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SCHEDULED)
    _scheduled_pair(702, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SCHEDULED)
    _scheduled_pair(703, PHI, NYM, status_code='DR', status_state=ScheduledGame.STATE_POSTPONED)
    _scheduled_pair(704, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SCHEDULED)
    _scheduled_pair(705, PHI, NYM, status_code='F', status_state=ScheduledGame.STATE_FINAL)
    _scheduled_pair(706, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SCHEDULED)
    _scheduled_pair(708, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SUSPENDED)

    rosters = {
        (PHI, ROSTER_TYPE_ACTIVE): [
            roster_entry(999, 'Seth Johnson', status=ACTIVE),
            roster_entry(100, 'Aaron Nola', status=ACTIVE),
            roster_entry(200, 'Traded Reliever', status=ACTIVE),
            roster_entry(301, 'Returning Reliever', status=ACTIVE),
            roster_entry(400, 'Aligned Name', status=ACTIVE),
            roster_entry(555, 'Conflicted Reliever', status=ACTIVE),
            roster_entry(777, 'New Reliever', status=ACTIVE),
            # Source row that shares a name with a stored pitcher but has NO id:
            # it must stay unresolved and never be name-matched to pitcher 100.
            roster_entry(None, 'Aaron Nola', status=ACTIVE),
        ],
        (PHI, ROSTER_TYPE_40_MAN): [
            roster_entry(300, 'Injured Reliever', status=IL15),
            roster_entry(303, 'Dfa Reliever', status=DFA_STATUS),
        ],
        (PHI, ROSTER_TYPE_FULL): [
            roster_entry(302, 'Optioned Reliever', status='Optioned to minors'),
        ],
        (NYM, ROSTER_TYPE_ACTIVE): [
            roster_entry(555, 'Conflicted Reliever', status=ACTIVE),
        ],
    }
    transactions = [
        {'transaction_id': 't1', 'transaction_date': '2026-07-16', 'player_mlb_id': 999,
         'player_full_name': 'Seth Johnson', 'from_team_id': PHI, 'to_team_id': PHI,
         'transaction_type_code': 'RECALL'},
        {'transaction_id': 't2', 'transaction_date': '2026-07-16', 'transaction_type_code': 'CASH'},
        {'transaction_id': 't3', 'transaction_date': '2026-07-16',
         'player_full_name': 'Unknown Prospect', 'transaction_type_code': 'SIGNED'},
        TX_ALREADY,
        TX_MISALIGNED,
    ]
    schedule = [
        _game(700, PHI, NYM, status_code='F', detailed='Final', abstract='Final'),
        _game(701, NYM, PHI, status_code='S', detailed='Scheduled', abstract='Preview'),
        _game(702, PHI, NYM, status_code='DR', detailed='Postponed', abstract='Preview'),
        _game(703, PHI, NYM, status_code='S', detailed='Scheduled', abstract='Preview'),
        _game(704, PHI, NYM, status_code='I', detailed='In Progress', abstract='Live'),
        _game(705, PHI, NYM, status_code='S', detailed='Scheduled', abstract='Preview'),
        _game(706, PHI, NYM, status_code='S', detailed='Scheduled', abstract='Preview',
              doubleheader='S', game_number=1),
        _game(707, PHI, NYM, status_code='S', detailed='Scheduled', abstract='Preview',
              doubleheader='S', game_number=2),
        _game(708, PHI, NYM, status_code='S', detailed='Scheduled', abstract='Preview'),
    ]
    teams = [
        {'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
        {'id': NYM, 'name': 'Mets', 'abbreviation': 'NYM'},
    ]
    return FakeMlbClient(rosters=rosters, transactions=transactions, schedule=schedule, teams=teams)


def _run(client, **kwargs):
    kwargs.setdefault('product_date', PRODUCT_DATE)
    kwargs.setdefault('team_ids', [PHI, NYM])
    return intraday_reconcile.run_intraday_audit(client=client, **kwargs)


def _lane1_by_id(artifact):
    lane = artifact['lanes'][intraday_reconcile.LANE_ROSTER_ASSIGNMENT]
    return {d['mlb_player_id']: d for d in lane['differences'] if d.get('mlb_player_id') is not None}


def _lane3_by_pk(artifact):
    lane = artifact['lanes'][intraday_reconcile.LANE_SCHEDULE_FINALITY]
    return {d['game_pk']: d for d in lane['differences']}


# ── Lane 1 ───────────────────────────────────────────────────────────────────

def test_lane1_no_change(scenario):
    diffs = _lane1_by_id(_run(scenario))
    assert 100 not in diffs   # Nola: active in both source and stored
    assert 400 not in diffs   # active in both


def test_lane1_recall(scenario):
    d = _lane1_by_id(_run(scenario))[999]
    assert d['change_type'] == intraday_reconcile.CHANGE_RECALL
    assert d['stored_status'] == STATUS_OPTIONED
    assert d['observed_official_status'] == STATUS_ACTIVE
    assert d['observed_official_team_id'] == PHI
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_ENTER
    assert d['targeted_recent_work_required'] is True
    assert d['stored_pitcher_id'] is not None


def _deep(client, **kwargs):
    # The specific inactive-destination classifications (IL / option / DFA) are a
    # DEEP-diagnostic capability that reads non-active roster evidence directly.
    kwargs['roster_types'] = intraday_reconcile.DEEP_ROSTER_TYPES
    return _run(client, **kwargs)


def test_lane1_il_placement_deep(scenario):
    d = _lane1_by_id(_deep(scenario))[300]
    assert d['change_type'] == intraday_reconcile.CHANGE_IL_PLACEMENT
    assert d['observed_official_status'] == STATUS_IL_15
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_il_activation(scenario):
    # Activation is inferred from the STORED status, so it is detected even under
    # the active-only default (the pitcher appears on the active roster now).
    d = _lane1_by_id(_run(scenario))[301]
    assert d['change_type'] == intraday_reconcile.CHANGE_IL_ACTIVATION
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_ENTER
    assert d['targeted_recent_work_required'] is True


def test_lane1_option_deep(scenario):
    d = _lane1_by_id(_deep(scenario))[302]
    assert d['change_type'] == intraday_reconcile.CHANGE_OPTION
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_dfa_deep(scenario):
    d = _lane1_by_id(_deep(scenario))[303]
    assert d['change_type'] == intraday_reconcile.CHANGE_DFA
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_active_only_default_uses_neutral_departure(scenario):
    # Under the active-only production default, 300/302/303 are absent from the
    # active roster and are reported with the neutral departure change type — an
    # exact inactive destination is never inferred from active-roster absence.
    diffs = _lane1_by_id(_run(scenario))
    for mlb_id in (300, 302, 303):
        assert diffs[mlb_id]['change_type'] == intraday_reconcile.CHANGE_REMOVED_FROM_ACTIVE_ROSTER
        assert diffs[mlb_id]['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_team_assignment_change(scenario):
    d = _lane1_by_id(_run(scenario))[200]
    assert d['change_type'] == intraday_reconcile.CHANGE_TEAM_ASSIGNMENT_CHANGE
    assert d['stored_team_id'] == NYM
    assert d['observed_official_team_id'] == PHI
    assert d['targeted_recent_work_required'] is True


def test_lane1_newly_discovered_active_pitcher(scenario):
    d = _lane1_by_id(_run(scenario))[777]
    assert d['change_type'] == intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE
    assert d['stored_pitcher_id'] is None
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_ENTER
    assert d['targeted_recent_work_required'] is True


def test_lane1_conflicting_official_team_evidence(scenario):
    d = _lane1_by_id(_run(scenario))[555]
    assert d['change_type'] == intraday_reconcile.CHANGE_CONFLICTING_OFFICIAL_TEAM
    assert sorted(d['conflicting_official_team_ids']) == [NYM, PHI]


def test_lane1_reports_unresolvable_source_identity(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_ROSTER_ASSIGNMENT]
    assert len(lane['unresolved_source_identities']) == 1
    assert lane['unresolved_source_identities'][0]['team_id'] == PHI


def test_lane1_never_guesses_identity_by_name(scenario):
    diffs = _lane1_by_id(_run(scenario))
    # The id-less "Aaron Nola" source row must not be matched to pitcher 100,
    # and no difference is ever keyed on a missing id.
    assert None not in diffs
    assert 100 not in diffs


def test_lane1_partial_source_failure_is_not_false_no_change(app):
    # Pitcher 900 is stored active on CHC(112); CHC's active roster fetch fails.
    _seed_pitcher(900, 'Cubs Reliever', 112, 'CHC', roster_status=STATUS_ACTIVE, active=True)
    client = FakeMlbClient(
        rosters={(112, ROSTER_TYPE_ACTIVE): []},
        roster_errors={(112, ROSTER_TYPE_ACTIVE): 'boom'},
        teams=[{'id': 112, 'name': 'Cubs', 'abbreviation': 'CHC'}],
    )
    artifact = _run(client, team_ids=[112])
    lane = artifact['lanes'][intraday_reconcile.LANE_ROSTER_ASSIGNMENT]
    # 900 must NOT be reported as removed just because the source could not be read.
    assert all(d.get('mlb_player_id') != 900 for d in lane['differences'])
    assert lane['verification_status'] == intraday_reconcile.LANE_PARTIAL
    assert lane['limitations']
    assert artifact['status'] == intraday_reconcile.STATUS_PARTIAL


# ── Lane 2 ───────────────────────────────────────────────────────────────────

def test_lane2_classifies_transactions(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_TRANSACTIONS]
    by_txid = {r.get('transaction_id'): r for r in lane['differences']}
    # Only meaningful findings are serialized: t1 (actionable new), t3 (unresolved
    # identity), t5 (status-effect unreflected). Benign t2 (non-player) and t4
    # (already reflected) are counted, not serialized.
    assert by_txid['t1']['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert by_txid['t1']['player_mlb_id'] == 999
    assert by_txid['t3']['classification'] == intraday_reconcile.TX_UNRESOLVED_IDENTITY
    assert 't2' not in by_txid  # non-player is informational, not a difference
    assert 't4' not in by_txid  # already reflected is benign, not a difference
    checked = lane['checked']
    assert checked['actionable_differences'] >= 2  # t1 + t5
    assert checked['non_player_transactions'] == 1
    assert checked['already_reflected'] >= 1
    assert checked['unresolved_identity'] == 1
    assert lane['informational_counts']['non_player_count'] == 1


def test_lane2_stored_effect_not_reflected(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_TRANSACTIONS]
    by_txid = {r.get('transaction_id'): r for r in lane['differences']}
    t5 = by_txid['t5']
    # A stored transaction whose recall (to NYM) is not reflected by the current
    # roster snapshot (still PHI) gets its OWN classification — never
    # already_reflected — and is an actionable difference.
    assert t5['classification'] == intraday_reconcile.TX_STATUS_EFFECT_UNREFLECTED
    assert t5['classification'] != intraday_reconcile.TX_ALREADY_REFLECTED
    assert t5['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert t5['status_effect_unreflected'] is True
    assert lane['checked']['status_effect_unreflected'] >= 1


def test_lane2_partial_source_failure_is_not_false_no_change(scenario):
    scenario.transactions_error = 'transactions endpoint down'
    artifact = _run(scenario)
    lane = artifact['lanes'][intraday_reconcile.LANE_TRANSACTIONS]
    assert lane['verification_status'] == intraday_reconcile.LANE_FAILED
    assert lane['limitations']
    assert artifact['status'] == intraday_reconcile.STATUS_PARTIAL


# ── Lane 3 ───────────────────────────────────────────────────────────────────

def test_lane3_detects_newly_final_game(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_SCHEDULE_FINALITY]
    d = {x['game_pk']: x for x in lane['differences']}[700]
    assert d['change_type'] == intraday_reconcile.GAME_NOW_FINAL
    assert d['official_status_state'] == 'final'
    assert d['stored_status_state'] == 'scheduled'
    assert d['would_require_targeted_postgame'] is True
    assert 700 in lane['completed_game_pks']


def test_lane3_detects_newly_discovered_game(scenario):
    assert _lane3_by_pk(_run(scenario))[701]['change_type'] == intraday_reconcile.GAME_NEWLY_DISCOVERED


def test_lane3_detects_postponed(scenario):
    assert _lane3_by_pk(_run(scenario))[702]['change_type'] == intraday_reconcile.GAME_POSTPONED


def test_lane3_detects_rescheduled(scenario):
    assert _lane3_by_pk(_run(scenario))[703]['change_type'] == intraday_reconcile.GAME_RESCHEDULED


def test_lane3_detects_in_progress(scenario):
    assert _lane3_by_pk(_run(scenario))[704]['change_type'] == intraday_reconcile.GAME_IN_PROGRESS


def test_lane3_detects_stored_finality_conflict(scenario):
    assert _lane3_by_pk(_run(scenario))[705]['change_type'] == intraday_reconcile.GAME_STORED_FINALITY_CONFLICT


def test_lane3_preserves_doubleheader_identity(scenario):
    diffs = _lane3_by_pk(_run(scenario))
    # 706 (stored, matching) is unchanged; 707 (same teams/date, distinct pk) is
    # a separate newly-discovered game — identity is preserved by game_pk.
    assert 706 not in diffs
    assert diffs[707]['change_type'] == intraday_reconcile.GAME_NEWLY_DISCOVERED
    assert diffs[707]['doubleheader'] is True


def test_lane3_flags_reschedule_identity_issue(scenario):
    assert _lane3_by_pk(_run(scenario))[708]['change_type'] == intraday_reconcile.GAME_RESCHEDULE_IDENTITY_ISSUE


def test_lane3_partial_source_failure_is_not_false_no_change(scenario):
    scenario.schedule_error = 'schedule endpoint down'
    artifact = _run(scenario)
    lane = artifact['lanes'][intraday_reconcile.LANE_SCHEDULE_FINALITY]
    assert lane['verification_status'] == intraday_reconcile.LANE_FAILED
    assert lane['limitations']
    # Stored games still surface as absent-from-source; not a clean no-change.
    assert any(d['change_type'] == intraday_reconcile.GAME_ABSENT_FROM_SOURCE
               for d in lane['differences'])
    assert artifact['status'] == intraday_reconcile.STATUS_PARTIAL


# ── impact plan / contract ───────────────────────────────────────────────────

def test_changed_result_includes_lanes_teams_pitchers(scenario):
    artifact = _run(scenario)
    assert artifact['changed'] is True
    assert set(artifact['changed_lanes']) == set(intraday_reconcile.ALL_LANES)
    assert PHI in artifact['affected_team_ids'] and NYM in artifact['affected_team_ids']
    assert 999 in artifact['affected_pitcher_mlb_ids']
    assert artifact['affected_pitcher_ids']  # internal ids present


def test_would_refresh_is_descriptive_only(scenario):
    artifact = _run(scenario)
    wr = artifact['would_refresh']
    assert wr['roster_statuses'] is True
    assert wr['team_assignments'] is True
    assert wr['transactions'] is True
    assert wr['completed_game_pks'] == [700]
    assert wr['recalculate_current_pen_era'] is True
    assert wr['publish_snapshot'] is True
    assert wr['warm_tonight'] is True
    assert 777 in wr['targeted_pitcher_mlb_ids']
    # Descriptive only: the audit certifies it performed none of this.
    assert artifact['safety']['snapshot_published'] is False
    assert artifact['safety']['writes_performed'] is False


def test_no_change_returns_changed_false(app):
    _seed_pitcher(100, 'Aaron Nola', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    client = FakeMlbClient(
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(100, 'Aaron Nola', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    artifact = _run(client, team_ids=[PHI])
    assert artifact['status'] == intraday_reconcile.STATUS_SUCCESS
    assert artifact['changed'] is False
    assert artifact['changed_lanes'] == []
    assert artifact['material_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_artifact_is_json_serializable_and_versioned(scenario):
    import json
    artifact = _run(scenario)
    parsed = json.loads(json.dumps(artifact, sort_keys=True))
    assert parsed['capability'] == 'intraday_reconciliation_audit_v1'
    assert parsed['capability'] == intraday_reconcile.CAPABILITY
    assert parsed['version'] == intraday_reconcile.VERSION
    assert parsed['mode'] == 'intraday'
    assert parsed['check_only'] is True
    assert parsed['status'] in ('success', 'partial', 'failed', 'skipped')
    for key in ('capability', 'version', 'mode', 'check_only', 'status', 'source',
                'started_at', 'completed_at', 'product_date', 'changed', 'changed_lanes',
                'affected_team_ids', 'affected_pitcher_ids', 'affected_pitcher_mlb_ids',
                'lanes', 'would_refresh', 'safety', 'source_api', 'limitations'):
        assert key in parsed, key


def _scrub(value):
    """Drop non-deterministic fields (timestamps, api metrics) for comparison."""
    if isinstance(value, dict):
        return {
            k: _scrub(v) for k, v in value.items()
            if k not in ('started_at', 'completed_at', 'check_timestamp', 'source_api')
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def test_identical_inputs_are_deterministic(scenario):
    first = _run(scenario)
    second = _run(scenario)
    assert _scrub(first) == _scrub(second)


def test_lane_selection_runs_only_requested_lane(scenario):
    artifact = _run(scenario, lanes=[intraday_reconcile.LANE_TRANSACTIONS])
    assert set(artifact['lanes'].keys()) == {intraday_reconcile.LANE_TRANSACTIONS}
    assert artifact['lanes_run'] == [intraday_reconcile.LANE_TRANSACTIONS]
    # Skipped lanes are simply absent — never falsely reported as verified.
    assert all(lane in artifact['changed_lanes'] or lane == intraday_reconcile.LANE_TRANSACTIONS
               for lane in artifact['changed_lanes'])
    assert intraday_reconcile.LANE_ROSTER_ASSIGNMENT not in artifact['lanes']


# ── read-only proof ──────────────────────────────────────────────────────────

def _row_snapshot():
    return {
        'pitchers': {p.mlb_id: (p.team_id, p.roster_status, p.active) for p in Pitcher.query.all()},
        'snapshots': RosterStatusSnapshot.query.count(),
        'transactions': PlayerTransaction.query.count(),
        'scheduled': ScheduledGame.query.count(),
        'game_logs': GameLog.query.count(),
        'fatigue': FatigueScore.query.count(),
        'dashboards': DashboardSnapshot.query.count(),
    }


def test_specific_rows_unchanged(scenario):
    before = _row_snapshot()
    _run(scenario)
    assert _row_snapshot() == before


def test_audit_leaves_no_pending_orm_writes(scenario):
    artifact = _run(scenario)
    assert artifact['write_guard']['clean'] is True
    assert artifact['write_guard']['pending_new'] == 0
    assert not db.session.new and not db.session.dirty and not db.session.deleted


def test_no_write_sql_is_executed(scenario):
    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        _run(scenario)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    writes = [
        s for s in statements
        if s.strip().split(' ', 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE')
    ]
    assert writes == [], writes


def test_no_mutation_helper_is_invoked(scenario, monkeypatch):
    import services.roster_status_sync as rss
    import services.team_assignment_sync as tas
    import services.schedule_ingestion as sched
    import services.dead_letter as dead_letter
    import services.sync as sync_service

    def _tripwire(name):
        def _raise(*_a, **_k):
            raise AssertionError(f'prohibited mutation helper invoked: {name}')
        return _raise

    for module, attr in (
        (rss, 'sync_roster_statuses'), (rss, '_upsert_roster_status_snapshot'),
        (tas, 'sync_team_assignments'),
        (transaction_ingestion, 'sync_transactions'),
        (transaction_ingestion, '_upsert_player_transaction'),
        (sched, 'ingest_schedule'), (sched, 'ingest_games'),
        (sync_service, 'recalculate_all_fatigue'),
        (dead_letter, 'record_failure'), (dead_letter, 'resolve_entity_failures'),
    ):
        if hasattr(module, attr):
            monkeypatch.setattr(module, attr, _tripwire(attr))

    artifact = _run(scenario)  # completes only if none of the tripwires fired
    assert artifact['status'] in (intraday_reconcile.STATUS_SUCCESS, intraday_reconcile.STATUS_PARTIAL)


def test_no_boxscore_or_gamelog_ingestion(scenario):
    _run(scenario)
    assert 'get_game_boxscore' not in scenario.calls
    assert 'get_game_linescore' not in scenario.calls
    assert 'get_pitcher_game_logs' not in scenario.calls


# ── read transaction-values regression (private-helper extraction) ───────────

def test_read_transaction_values_matches_internal(app):
    tx = {'transaction_id': 'z1', 'transaction_date': '2026-07-16', 'player_mlb_id': 5,
          'transaction_type_code': 'RECALL'}
    kwargs = dict(start_date=date(2026, 7, 9), end_date=PRODUCT_DATE,
                  timestamp=utc_now_naive(), sync_run_id=None)
    # Public read-only wrapper returns exactly what the internal path returns.
    assert (transaction_ingestion.read_transaction_values(tx, **kwargs)
            == transaction_ingestion._values_from_transaction(tx, **kwargs))
    assert transaction_ingestion.TRANSACTION_FACT_FIELDS is transaction_ingestion._TRANSACTION_FACT_FIELDS


# ── writer lock (Correction 2) ───────────────────────────────────────────────

def test_read_lock_uses_public_sync_writer_key(app):
    guard = sync_metadata.acquire_public_sync_read_lock()
    try:
        assert guard.lock_key == sync_metadata.SYNC_WRITER_LOCK_KEY
        assert guard.lock_scope == sync_metadata.LOCK_SCOPE_PUBLIC
        # The daily/postgame public writers resolve to the SAME key.
        daily_scope = sync_metadata._normalize_lock_scope(job_name=sync_metadata.JOB_DAILY_SYNC)
        assert sync_metadata._lock_key_for_scope(daily_scope) == guard.lock_key
    finally:
        guard.release()


def test_lock_conflict_produces_skipped_result(scenario):
    held = sync_metadata.acquire_public_sync_read_lock()
    try:
        artifact = _run(scenario)
    finally:
        held.release()
    assert artifact['status'] == intraday_reconcile.STATUS_SKIPPED
    assert artifact['reason_code'] == intraday_reconcile.REASON_PUBLIC_SYNC_WRITER_ACTIVE
    assert artifact['changed'] is False
    assert artifact['check_only'] is True
    assert artifact['lanes'] == {}
    assert artifact['safety']['writes_performed'] is False


def test_no_source_calls_after_lock_conflict(scenario):
    held = sync_metadata.acquire_public_sync_read_lock()
    try:
        _run(scenario)
    finally:
        held.release()
    assert scenario.calls == {}  # not a single MLB source method was called


def test_no_db_mutation_on_lock_conflict(scenario):
    before = _row_snapshot()
    held = sync_metadata.acquire_public_sync_read_lock()
    try:
        _run(scenario)
    finally:
        held.release()
    assert _row_snapshot() == before


def test_lock_released_on_success(scenario):
    _run(scenario)
    # The lock must be free again immediately after a successful audit.
    guard = sync_metadata.acquire_public_sync_read_lock()
    guard.release()


def test_lock_released_on_partial_failure(scenario):
    scenario.schedule_error = 'down'
    artifact = _run(scenario)
    assert artifact['status'] == intraday_reconcile.STATUS_PARTIAL
    guard = sync_metadata.acquire_public_sync_read_lock()
    guard.release()


def test_lock_released_on_unexpected_exception(scenario, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError('unexpected')
    monkeypatch.setattr(intraday_reconcile, 'build_impact_plan', _boom)
    with pytest.raises(RuntimeError):
        _run(scenario)
    # finally-block released the advisory lock despite the crash.
    guard = sync_metadata.acquire_public_sync_read_lock()
    guard.release()


def test_does_not_mutate_running_sync_run(scenario):
    run = SyncRun(job_name='daily_sync', status='running', stage='ingest', source='test',
                  started_at=utc_now_naive())
    db.session.add(run)
    db.session.commit()
    run_id, started_at = run.id, run.started_at

    _run(scenario)  # lock is free; audit runs and must not touch the SyncRun

    refreshed = db.session.get(SyncRun, run_id)
    assert SyncRun.query.count() == 1
    assert refreshed.status == 'running'
    assert refreshed.started_at == started_at
    assert refreshed.completed_at is None


# ── CLI (Correction 3 / 6) ───────────────────────────────────────────────────

def _canned(status='success', **extra):
    artifact = {
        'capability': intraday_reconcile.CAPABILITY, 'version': intraday_reconcile.VERSION, 'mode': 'intraday',
        'phase': 1, 'check_only': True, 'status': status, 'source': 'manual',
        'product_date': '2026-07-16', 'started_at': 'x', 'completed_at': 'y',
        'changed': False, 'changed_lanes': [], 'affected_team_ids': [],
        'affected_pitcher_ids': [], 'affected_pitcher_mlb_ids': [], 'lanes': {},
        'would_refresh': intraday_reconcile._empty_would_refresh(),
        'material_change_detected': False, 'limitations': [],
        'source_api': {}, 'safety': {}, 'write_guard': {'clean': True},
        'summary': {'total_differences': 0, 'material_change_detected': False},
        'reason_code': 'public_sync_writer_active',
    }
    artifact.update(extra)
    return artifact


def _install_fake_app(monkeypatch):
    import sys
    import types
    from utils.db import db as real_db
    flask_app = Flask('cli_main_test')
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    real_db.init_app(flask_app)
    fake_app_module = types.ModuleType('app')
    fake_app_module.app = flask_app
    monkeypatch.setitem(sys.modules, 'app', fake_app_module)


def test_cli_main_emits_single_json_object(monkeypatch, tmp_path, capsys, caplog):
    import json
    import logging
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned('success'))
    import scripts.run_intraday_reconcile as cli

    out_path = tmp_path / 'artifact.json'
    with caplog.at_level(logging.INFO):
        rc = cli.main(['--source', 'manual', '--json', '--output', str(out_path)])
    captured = capsys.readouterr()

    assert rc == 0
    parsed = json.loads(captured.out)  # exactly one clean JSON object on stdout
    assert parsed['mode'] == 'intraday'
    assert captured.out.strip().count('\n') == 0  # no extra stdout noise
    # Human-readable progress is logged (routed to stderr, never stdout).
    assert any('Intraday audit summary' in r.message for r in caplog.records)


def test_cli_output_matches_stdout(monkeypatch, tmp_path, capsys):
    import json
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit',
                        lambda **_k: _canned('success', changed=True))
    import scripts.run_intraday_reconcile as cli
    out_path = tmp_path / 'artifact.json'
    cli.main(['--json', '--output', str(out_path)])
    stdout = capsys.readouterr().out
    assert json.loads(out_path.read_text()) == json.loads(stdout)


@pytest.mark.parametrize('status,expected', [
    ('success', 0), ('skipped', 0), ('partial', 1), ('failed', 1),
])
def test_cli_exit_codes(monkeypatch, status, expected):
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned(status))
    import scripts.run_intraday_reconcile as cli
    assert cli.main(['--source', 'manual']) == expected


def test_cli_exit_code_success(monkeypatch):
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned('success'))
    import scripts.run_intraday_reconcile as cli
    assert cli.main([]) == 0


def test_cli_exit_code_skipped(monkeypatch):
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned('skipped'))
    import scripts.run_intraday_reconcile as cli
    assert cli.main([]) == 0


def test_cli_exit_code_partial(monkeypatch):
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned('partial'))
    import scripts.run_intraday_reconcile as cli
    assert cli.main([]) == 1


def test_cli_exit_code_failed(monkeypatch):
    _install_fake_app(monkeypatch)
    monkeypatch.setattr(intraday_reconcile, 'run_intraday_audit', lambda **_k: _canned('failed'))
    import scripts.run_intraday_reconcile as cli
    assert cli.main([]) == 1


def test_cli_selected_lanes_helpers():
    import scripts.run_intraday_reconcile as cli
    assert cli._selected_lanes(None, intraday_reconcile.ALL_LANES) == list(intraday_reconcile.ALL_LANES)
    assert cli._selected_lanes('transactions,roster_assignment', intraday_reconcile.ALL_LANES) == [
        intraday_reconcile.LANE_ROSTER_ASSIGNMENT, intraday_reconcile.LANE_TRANSACTIONS,
    ]
    with pytest.raises(SystemExit):
        cli._selected_lanes('bogus', intraday_reconcile.ALL_LANES)


def test_cli_defaults_disable_auto_sync():
    import os
    import scripts.run_intraday_reconcile  # noqa: F401 - import sets the AUTO_SYNC guard
    assert os.environ.get('AUTO_SYNC') == 'false'


# ═════════════════════════════════════════════════════════════════════════════
# Signal-quality correction (contract v1.1.0)
#
# These tests pin the corrections that Production Observation #1 (the first valid
# production intraday run, 2026-07-17) exposed. That run passed the read-only,
# infrastructure, and source-coverage checks but its SIGNAL classification was
# wrong: all 354 transaction records (342 already-reflected + 7 non-player) were
# serialized into transactions.differences, so `changed=true` and a "360
# differences" total presented benign inventory as a changed lane; three records
# carried a self-contradictory already_reflected + status_effect_unreflected
# label; five stored_conflict findings were manufactured from compound events
# (multiple player components sharing one MLB transaction id compared against one
# stored PlayerTransaction row); and two newly-discovered active pitchers lost
# their source names. Observation #1 therefore did NOT prove signal accuracy and
# a fresh observation is required after this correction.
#
# Signal-quality item → proving test:
#   C1 benign transactions never serialized ..... test_lane2_all_reflected_no_differences,
#                                                 test_lane2_already_reflected_not_serialized
#   C1 non-player is informational .............. test_lane2_non_player_is_informational
#   C1 benign counted + bounded-sampled ......... test_lane2_benign_suppressed_count,
#                                                 test_lane2_informational_samples_bounded
#   C1 differences carry only meaningful ........ test_lane2_differences_are_meaningful_only
#   C2 status_effect is its own class ........... test_lane2_status_effect_precedence,
#                                                 test_lane2_status_effect_not_a_conflict
#   C3 compound reflected -> no false conflict .. test_lane2_compound_reflected_no_false_conflict
#   C3 compound new -> exactly one finding ...... test_lane2_compound_new_single_finding
#   C3 compound ambiguous -> one review ......... test_lane2_compound_ambiguous_single_review
#   C3 event conflict excludes player fields .... test_lane2_compound_conflict_excludes_player_fields
#   C3 components grouped into one event ........ test_lane2_compound_groups_components
#   C4 changed derives from meaningful only ..... test_changed_false_when_only_benign_transactions
#   C4 changed_lanes excludes benign tx ......... test_changed_lanes_excludes_benign_transactions
#   C4 summary buckets present + accurate ....... test_summary_buckets_present_and_accurate,
#                                                 test_summary_records_checked
#   C4 material only when write required ......... test_material_change_only_when_actionable
#   C4 review-required is changed, not material . test_review_required_changed_not_material
#   C5 affected excludes benign/review .......... test_affected_excludes_benign_and_review
#   C5 publish_snapshot not from benign ......... test_publish_snapshot_not_from_benign,
#                                                 test_publish_snapshot_not_from_review_only
#   C5 warm_tonight not from transaction-only ... test_warm_tonight_not_from_transaction_only,
#                                                 test_warm_tonight_true_on_roster_change
#   C6 active-roster budget <= 30 calls ......... test_active_roster_budget_is_bounded
#   C6 deep sweep reads every roster type ....... test_deep_roster_sweeps_all_types
#   C6 active-only neutral departure ............ test_lane1_active_only_default_uses_neutral_departure
#   C7 newly-discovered source name preserved ... test_lane1_newly_discovered_preserves_name
#   C8 minor version bump, capability stable .... test_contract_is_backward_compatible_minor_bump
#   C8 informational samples deterministic ...... test_informational_samples_deterministic
#   C9 Observation #1 regression fixture ........ test_observation_one_* (five tests)
# ═════════════════════════════════════════════════════════════════════════════

TOR = 141
ATH = 133
SIGNAL_DATE = date(2026, 7, 16)


def _tx(transaction_id, player_mlb_id=None, *, type_code='RECALL', to_team_id=None,
        from_team_id=None, transaction_date='2026-07-16', player_full_name=None):
    """Build a source transaction row for the signal-quality suite."""
    row = {
        'transaction_id': transaction_id,
        'transaction_date': transaction_date,
        'transaction_type_code': type_code,
        'source_endpoint': transaction_ingestion.SOURCE_ENDPOINT,
    }
    if player_mlb_id is not None:
        row['player_mlb_id'] = player_mlb_id
    if to_team_id is not None:
        row['to_team_id'] = to_team_id
    if from_team_id is not None:
        row['from_team_id'] = from_team_id
    if player_full_name is not None:
        row['player_full_name'] = player_full_name
    return row


def _tx_client(transactions, *, rosters=None, teams=None, schedule=None):
    return FakeMlbClient(
        rosters=rosters or {}, transactions=transactions,
        schedule=schedule or [], teams=teams or [],
    )


def _tx_lane(artifact):
    return artifact['lanes'][intraday_reconcile.LANE_TRANSACTIONS]


def _tx_by_class(lane):
    out = {}
    for d in lane['differences']:
        out.setdefault(d['classification'], []).append(d)
    return out


def _seed_status_effect_case(mlb_id, name, transaction_id):
    """Stored pitcher active on PHI + a same-day PHI roster snapshot + a stored
    RECALL-to-NYM transaction. The transaction's roster effect (now on NYM) is
    not reflected by the snapshot (still PHI): a status_effect_unreflected case,
    exactly the Andre Granillo / Cam Sanders / Colton Gordon contradiction."""
    pitcher = _seed_pitcher(mlb_id, name, PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(pitcher, PHI, SIGNAL_DATE, STATUS_ACTIVE)
    tx = _tx(transaction_id, mlb_id, type_code='RECALL', to_team_id=NYM, player_full_name=name)
    _seed_stored_transaction(tx)
    return tx


# ── C1: benign transactions are counted, never serialized ────────────────────

def test_lane2_all_reflected_no_differences(app):
    for i in range(4):
        _seed_stored_transaction(_tx(f'r{i}', 900 + i, type_code='SFA'))
    source = [_tx(f'r{i}', 900 + i, type_code='SFA') for i in range(4)]
    artifact = _run(_tx_client(source), team_ids=[PHI],
                    lanes=[intraday_reconcile.LANE_TRANSACTIONS])
    lane = _tx_lane(artifact)
    assert lane['differences'] == []
    assert lane['checked']['already_reflected'] == 4
    assert lane['checked']['meaningful_differences'] == 0
    assert artifact['changed'] is False
    assert artifact['changed_lanes'] == []


def test_lane2_already_reflected_not_serialized(app):
    _seed_stored_transaction(_tx('ar', 950, type_code='SFA'))
    lane = _tx_lane(_run(_tx_client([_tx('ar', 950, type_code='SFA')]), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert all(d['classification'] != intraday_reconcile.TX_ALREADY_REFLECTED
               for d in lane['differences'])
    assert lane['informational_counts']['already_reflected_count'] == 1


def test_lane2_non_player_is_informational(app):
    source = [_tx('np1', None, type_code='CASH'), _tx('np2', None, type_code='CASH')]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert all(d['classification'] != intraday_reconcile.TX_NON_PLAYER
               for d in lane['differences'])
    assert lane['checked']['non_player_transactions'] == 2
    assert lane['informational_counts']['non_player_count'] == 2
    # A bounded sample is retained for evidence, but not in differences.
    assert lane['informational_samples'][intraday_reconcile.TX_NON_PLAYER]


def test_lane2_benign_suppressed_count(app):
    # Seven already-reflected records; only the first sample_limit are sampled.
    for i in range(7):
        _seed_stored_transaction(_tx(f'b{i}', 960 + i, type_code='SFA'))
    source = [_tx(f'b{i}', 960 + i, type_code='SFA') for i in range(7)]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert lane['checked']['already_reflected'] == 7
    sampled = lane['informational_samples'].get(intraday_reconcile.TX_ALREADY_REFLECTED, [])
    assert len(sampled) == intraday_reconcile.DEFAULT_TX_SAMPLE_LIMIT
    assert lane['suppressed_counts']['benign_records_suppressed'] == 7 - intraday_reconcile.DEFAULT_TX_SAMPLE_LIMIT


def test_lane2_informational_samples_bounded(app):
    for i in range(5):
        _seed_stored_transaction(_tx(f's{i}', 970 + i, type_code='SFA'))
    source = [_tx(f's{i}', 970 + i, type_code='SFA') for i in range(5)]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    for cls, sample in lane['informational_samples'].items():
        assert len(sample) <= intraday_reconcile.DEFAULT_TX_SAMPLE_LIMIT, cls


def test_lane2_differences_are_meaningful_only(app):
    _seed_stored_transaction(_tx('ok', 980, type_code='SFA'))       # already reflected
    source = [
        _tx('ok', 980, type_code='SFA'),                             # benign
        _tx('np', None, type_code='CASH'),                           # benign
        _tx('new', 981, type_code='RECALL', to_team_id=PHI),         # actionable (not stored)
    ]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    for d in lane['differences']:
        assert d['classification'] in intraday_reconcile.TX_MEANINGFUL_CLASSES
        assert d.get('severity') in (intraday_reconcile.SEVERITY_ACTIONABLE,
                                     intraday_reconcile.SEVERITY_REVIEW)


# ── C2: status_effect_unreflected is its own class with deterministic precedence

def test_lane2_status_effect_precedence(app):
    tx = _seed_status_effect_case(690916, 'Andre Granillo', 'se1')
    lane = _tx_lane(_run(_tx_client([tx]), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    d = {r['transaction_id']: r for r in lane['differences']}['se1']
    assert d['classification'] == intraday_reconcile.TX_STATUS_EFFECT_UNREFLECTED
    assert d['classification'] != intraday_reconcile.TX_ALREADY_REFLECTED
    assert d['status_effect_unreflected'] is True
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_lane2_status_effect_not_a_conflict(app):
    tx = _seed_status_effect_case(681911, 'Cam Sanders', 'se2')
    lane = _tx_lane(_run(_tx_client([tx]), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    d = {r['transaction_id']: r for r in lane['differences']}['se2']
    # A misaligned roster effect is NOT a stored source-fact conflict.
    assert d['classification'] != intraday_reconcile.TX_STORED_CONFLICT
    assert lane['checked']['stored_conflicts'] == 0
    assert lane['checked']['status_effect_unreflected'] == 1


# ── C3: compound events are event-aware (one finding per MLB transaction id) ──

def _compound_pair(transaction_id, id_a, id_b, *, type_code='TR', transaction_date='2026-07-16'):
    return [
        _tx(transaction_id, id_a, type_code=type_code, from_team_id=PHI, to_team_id=NYM,
            transaction_date=transaction_date),
        _tx(transaction_id, id_b, type_code=type_code, from_team_id=NYM, to_team_id=PHI,
            transaction_date=transaction_date),
    ]


def test_lane2_compound_reflected_no_false_conflict(app):
    # 927651: two player components share one transaction id; one is already
    # stored. The event is reflected — it must NOT manufacture a stored conflict.
    components = _compound_pair('927651', 660001, 660002)
    _seed_stored_transaction(components[0])
    lane = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert lane['checked']['stored_conflicts'] == 0
    assert lane['checked']['compound_events_reflected'] == 1
    assert all(d.get('event_key') != 'statsapi:927651' for d in lane['differences'])


def test_lane2_compound_new_single_finding(app):
    # 926870: two components, no stored row -> exactly one compound_new finding.
    components = _compound_pair('926870', 660003, 660004)
    lane = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    compound = [d for d in lane['differences'] if d.get('event_key') == 'statsapi:926870']
    assert len(compound) == 1
    finding = compound[0]
    assert finding['classification'] == intraday_reconcile.TX_COMPOUND_NEW
    assert finding['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert finding['component_count'] == 2
    assert finding['player_mlb_ids'] == [660003, 660004]


def test_lane2_compound_ambiguous_single_review(app):
    # 926807: two components, a stored row for a DIFFERENT player under the same
    # transaction id. Per-component equivalence cannot be proven -> one review.
    components = _compound_pair('926807', 660005, 660006)
    _seed_stored_transaction(_tx('926807', 660099, type_code='TR',
                                 from_team_id=PHI, to_team_id=NYM))
    lane = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    compound = [d for d in lane['differences'] if d.get('event_key') == 'statsapi:926807']
    assert len(compound) == 1
    assert compound[0]['classification'] == intraday_reconcile.TX_COMPOUND_REVIEW
    assert compound[0]['severity'] == intraday_reconcile.SEVERITY_REVIEW
    assert compound[0].get('reason')


def test_lane2_compound_conflict_excludes_player_fields(app):
    # Same transaction id, but the stored event date differs from the source:
    # the event-level conflict names only shared event-level fields, never a
    # per-component player field.
    components = _compound_pair('930000', 660007, 660008, transaction_date='2026-07-16')
    _seed_stored_transaction(_tx('930000', 660007, type_code='TR',
                                 from_team_id=PHI, to_team_id=NYM,
                                 transaction_date='2026-07-10'))
    lane = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    finding = [d for d in lane['differences'] if d.get('event_key') == 'statsapi:930000'][0]
    assert finding['classification'] == intraday_reconcile.TX_STORED_CONFLICT
    assert 'transaction_date' in finding['conflicting_fields']
    assert set(finding['conflicting_fields']).issubset(set(intraday_reconcile._TX_EVENT_LEVEL_FIELDS))
    assert 'player_mlb_id' not in finding['conflicting_fields']


def test_lane2_compound_groups_components(app):
    # Three components under one id collapse to a single source event.
    components = [
        _tx('940000', 660010, type_code='TR', from_team_id=PHI, to_team_id=NYM),
        _tx('940000', 660011, type_code='TR', from_team_id=NYM, to_team_id=PHI),
        _tx('940000', 660012, type_code='TR', from_team_id=NYM, to_team_id=PHI),
    ]
    lane = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert lane['checked']['source_transactions'] == 3
    assert lane['checked']['source_events'] == 1
    finding = [d for d in lane['differences'] if d.get('event_key') == 'statsapi:940000'][0]
    assert finding['player_component_count'] == 3
    assert finding['player_mlb_ids'] == [660010, 660011, 660012]


# ── C4: changed / material / summary semantics ───────────────────────────────

def test_changed_false_when_only_benign_transactions(app):
    _seed_stored_transaction(_tx('c1', 991, type_code='SFA'))
    source = [_tx('c1', 991, type_code='SFA'), _tx('c2', None, type_code='CASH')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['changed'] is False
    assert artifact['material_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_changed_lanes_excludes_benign_transactions(app):
    # A real roster recall (lane 1) alongside a benign-only transaction lane:
    # transactions must NOT appear as a changed lane.
    _seed_pitcher(992, 'Recalled Arm', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    _seed_stored_transaction(_tx('c3', 993, type_code='SFA'))
    client = _tx_client(
        [_tx('c3', 993, type_code='SFA')],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(992, 'Recalled Arm', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    artifact = _run(client, team_ids=[PHI])
    assert intraday_reconcile.LANE_ROSTER_ASSIGNMENT in artifact['changed_lanes']
    assert intraday_reconcile.LANE_TRANSACTIONS not in artifact['changed_lanes']


def test_summary_buckets_present_and_accurate(scenario):
    summary = _run(scenario)['summary']
    for key in ('total_differences', 'records_checked', 'actionable_differences',
                'review_required_findings', 'unresolved_findings',
                'informational_records', 'benign_records_suppressed',
                'material_change_detected', 'affected_team_ids'):
        assert key in summary, key
    assert summary['actionable_differences'] + summary['review_required_findings'] \
        == summary['total_differences']
    assert summary['informational_records'] >= 0


def test_summary_records_checked(app):
    _seed_stored_transaction(_tx('rc', 994, type_code='SFA'))
    _seed_pitcher(995, 'Any Arm', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    client = _tx_client(
        [_tx('rc', 994, type_code='SFA')],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(995, 'Any Arm', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    summary = _run(client, team_ids=[PHI])['summary']
    # records_checked aggregates source transactions + stored pitchers + source games.
    assert summary['records_checked'] >= 1


def test_material_change_only_when_actionable(app):
    # A brand-new, not-yet-stored player transaction is actionable -> material.
    source = [_tx('m1', 996, type_code='RECALL', to_team_id=PHI)]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['changed'] is True
    assert artifact['material_change_detected'] is True
    assert artifact['would_refresh']['publish_snapshot'] is True


def test_review_required_changed_not_material(app):
    # A source row with a name but no id is an unresolved identity (review): a
    # real finding that sets changed=true but is NOT a material (writable) change.
    source = [_tx('rev', None, type_code='SIGNED', player_full_name='Unknown Prospect')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    lane = _tx_lane(artifact)
    assert any(d['classification'] == intraday_reconcile.TX_UNRESOLVED_IDENTITY
               for d in lane['differences'])
    assert artifact['changed'] is True
    assert artifact['material_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False
    assert artifact['summary']['unresolved_findings'] >= 1


# ── C5: impact plan derives from actionable findings only ────────────────────

def test_affected_excludes_benign_and_review(app):
    _seed_stored_transaction(_tx('a1', 700100, type_code='SFA'))     # benign player 700100
    source = [
        _tx('a1', 700100, type_code='SFA'),                          # benign
        _tx('a2', None, type_code='SIGNED', player_full_name='Ghost'),  # review (unresolved)
        _tx('a3', 700101, type_code='RECALL', to_team_id=PHI),       # actionable
    ]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert 700101 in artifact['affected_pitcher_mlb_ids']
    assert 700100 not in artifact['affected_pitcher_mlb_ids']


def test_publish_snapshot_not_from_benign(app):
    _seed_stored_transaction(_tx('p1', 700200, type_code='SFA'))
    artifact = _run(_tx_client([_tx('p1', 700200, type_code='SFA')]), team_ids=[PHI])
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_publish_snapshot_not_from_review_only(app):
    source = [_tx('p2', None, type_code='SIGNED', player_full_name='Ghost')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_warm_tonight_not_from_transaction_only(app):
    # An actionable transaction with no roster/schedule population change must not
    # warm Tonight, even though it is material (publish_snapshot true).
    source = [_tx('w1', 700300, type_code='RECALL', to_team_id=PHI)]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['material_change_detected'] is True
    assert artifact['would_refresh']['warm_tonight'] is False


def test_warm_tonight_true_on_roster_change(app):
    _seed_pitcher(700400, 'Warm Arm', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    client = _tx_client(
        [],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(700400, 'Warm Arm', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    artifact = _run(client, team_ids=[PHI])
    assert artifact['would_refresh']['warm_tonight'] is True


# ── C6: active-roster-only default budget + deep sweep ───────────────────────

def test_active_roster_budget_is_bounded(app):
    team_ids = list(range(1000, 1030))  # 30 teams
    rosters = {(tid, ROSTER_TYPE_ACTIVE): [] for tid in team_ids}
    client = _tx_client([], rosters=rosters)
    _run(client, team_ids=team_ids, lanes=[intraday_reconcile.LANE_ROSTER_ASSIGNMENT])
    # Active-only default: exactly one roster fetch per team, never the 4x sweep.
    assert client.calls.get('get_team_roster', 0) <= 30
    assert client.calls.get('get_team_roster', 0) == len(team_ids)


def test_deep_roster_sweeps_all_types(app):
    team_ids = list(range(1100, 1105))  # 5 teams
    rosters = {(tid, rt): [] for tid in team_ids for rt in intraday_reconcile.DEEP_ROSTER_TYPES}
    client = _tx_client([], rosters=rosters)
    _deep(client, team_ids=team_ids, lanes=[intraday_reconcile.LANE_ROSTER_ASSIGNMENT])
    # Deep diagnostic reads every roster type: strictly more calls than active-only.
    assert client.calls.get('get_team_roster', 0) == len(team_ids) * len(intraday_reconcile.DEEP_ROSTER_TYPES)
    assert client.calls['get_team_roster'] > len(team_ids)


# ── C7: newly-discovered source names are preserved ──────────────────────────

def test_lane1_newly_discovered_preserves_name(app):
    client = _tx_client(
        [],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(700500, 'Fresh Arm', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    d = _lane1_by_id(_run(client, team_ids=[PHI]))[700500]
    assert d['change_type'] == intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE
    assert d['stored_pitcher_id'] is None
    # The MLB-supplied name is retained (identity matching still used the id only).
    assert d['player_name'] == 'Fresh Arm'


# ── C8: contract compactness / versioning ────────────────────────────────────

def test_contract_is_backward_compatible_minor_bump(scenario):
    artifact = _run(scenario)
    assert artifact['capability'] == 'intraday_reconciliation_audit_v1'  # unchanged
    assert artifact['version'] == intraday_reconcile.VERSION
    assert artifact['version'].startswith('1.')  # minor bump, not a new major
    assert artifact['check_only'] is True
    assert artifact['mode'] == 'intraday'


def test_informational_samples_deterministic(app):
    for i in range(6):
        _seed_stored_transaction(_tx(f'd{i}', 700600 + i, type_code='SFA'))
    source = [_tx(f'd{i}', 700600 + i, type_code='SFA') for i in range(6)]
    first = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                          lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    second = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                           lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    # Sample identity/order/content is deterministic (timestamps aside).
    assert _scrub(first['informational_samples']) == _scrub(second['informational_samples'])
    assert first['suppressed_counts'] == second['suppressed_counts']


# ── C9: Production Observation #1 regression fixture ─────────────────────────

@pytest.fixture
def observation_one(app):
    """A compact fixture mirroring the structure of Production Observation #1:
    a large benign already-reflected inventory, non-player components, the three
    status_effect_unreflected contradictions, three compound events (reflected /
    new / ambiguous), and two newly-discovered active pitchers that arrive with
    source names. Kept small but structurally faithful."""
    # Status-effect contradictions (Granillo / Sanders / Gordon), stored active
    # on PHI, so lane 1 sees no roster change for them.
    se = [
        _seed_status_effect_case(690916, 'Andre Granillo', 'se-granillo'),
        _seed_status_effect_case(681911, 'Cam Sanders', 'se-sanders'),
        _seed_status_effect_case(700241, 'Colton Gordon', 'se-gordon'),
    ]
    # Five already-reflected transactions (benign, suppressed beyond the sample).
    reflected = []
    for i in range(5):
        row = _tx(f'reflected-{i}', 640000 + i, type_code='SFA')
        _seed_stored_transaction(row)
        reflected.append(row)
    # Two non-player components (cash considerations).
    non_player = [_tx('cash-1', None, type_code='CASH'), _tx('cash-2', None, type_code='CASH')]
    # Compound event 927651 — reflected (one component already stored).
    c_reflected = _compound_pair('927651', 650001, 650002)
    _seed_stored_transaction(c_reflected[0])
    # Compound event 926870 — new (no stored row).
    c_new = _compound_pair('926870', 650003, 650004)
    # Compound event 926807 — ambiguous (stored row for a different player).
    c_review = _compound_pair('926807', 650005, 650006)
    _seed_stored_transaction(_tx('926807', 650099, type_code='TR',
                                 from_team_id=PHI, to_team_id=NYM))

    transactions = (
        se + reflected + non_player + c_reflected + c_new + c_review
    )
    rosters = {
        # PHI active roster still carries the three status_effect pitchers, so
        # lane 1 reports no roster change for them.
        (PHI, ROSTER_TYPE_ACTIVE): [
            roster_entry(690916, 'Andre Granillo', status=ACTIVE),
            roster_entry(681911, 'Cam Sanders', status=ACTIVE),
            roster_entry(700241, 'Colton Gordon', status=ACTIVE),
        ],
        # Two newly-discovered active pitchers arrive WITH names from the source.
        (TOR, ROSTER_TYPE_ACTIVE): [roster_entry(669310, 'CJ Van Eyk', status=ACTIVE)],
        (ATH, ROSTER_TYPE_ACTIVE): [roster_entry(814305, 'Yunior Tur', status=ACTIVE)],
    }
    teams = [
        {'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
        {'id': TOR, 'name': 'Blue Jays', 'abbreviation': 'TOR'},
        {'id': ATH, 'name': 'Athletics', 'abbreviation': 'ATH'},
    ]
    return _tx_client(transactions, rosters=rosters, teams=teams)


def _obs_run(observation_one):
    return _run(observation_one, team_ids=[PHI, TOR, ATH])


def test_observation_one_transactions_signal(observation_one):
    lane = _tx_lane(_obs_run(observation_one))
    checked = lane['checked']
    # Benign inventory is counted, never serialized.
    assert checked['already_reflected'] == 5
    assert checked['non_player_transactions'] == 2
    assert checked['compound_events_reflected'] == 1
    for d in lane['differences']:
        assert d['classification'] in intraday_reconcile.TX_MEANINGFUL_CLASSES
    # The three status-effect contradictions surface as their own class.
    assert checked['status_effect_unreflected'] == 3
    # Benign records beyond the sample are suppressed with a count.
    assert lane['suppressed_counts']['benign_records_suppressed'] == 5 - intraday_reconcile.DEFAULT_TX_SAMPLE_LIMIT


def test_observation_one_no_false_stored_conflicts(observation_one):
    lane = _tx_lane(_obs_run(observation_one))
    # The compound-event false-conflict class of bug is gone.
    assert lane['checked']['stored_conflicts'] == 0


def test_observation_one_compound_events(observation_one):
    lane = _tx_lane(_obs_run(observation_one))
    by_event = {d.get('event_key'): d for d in lane['differences'] if d.get('event_key')}
    # 927651 reflected -> benign, not serialized.
    assert 'statsapi:927651' not in by_event
    # 926870 new -> one actionable finding.
    assert by_event['statsapi:926870']['classification'] == intraday_reconcile.TX_COMPOUND_NEW
    # 926807 ambiguous -> one review finding.
    assert by_event['statsapi:926807']['classification'] == intraday_reconcile.TX_COMPOUND_REVIEW
    # Each compound id yields at most one finding.
    for event_key in ('statsapi:926870', 'statsapi:926807'):
        assert sum(1 for d in lane['differences'] if d.get('event_key') == event_key) == 1


def test_observation_one_newly_discovered_names(observation_one):
    diffs = _lane1_by_id(_obs_run(observation_one))
    assert diffs[669310]['change_type'] == intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE
    assert diffs[669310]['player_name'] == 'CJ Van Eyk'
    assert diffs[814305]['player_name'] == 'Yunior Tur'
    # The status_effect pitchers are unchanged on the active roster (no lane-1 diff).
    for mlb_id in (690916, 681911, 700241):
        assert mlb_id not in diffs


def test_observation_one_summary_and_material(observation_one):
    artifact = _obs_run(observation_one)
    summary = artifact['summary']
    # Changed is true (there ARE meaningful findings), but the honest total never
    # includes the 5 already-reflected + 2 non-player + 1 reflected-compound rows.
    assert artifact['changed'] is True
    assert summary['informational_records'] == 5 + 2 + 1
    assert summary['total_differences'] == summary['actionable_differences'] + summary['review_required_findings']
    # Actionable findings exist (compound_new, status_effect, newly-discovered),
    # so a future write would be required.
    assert summary['material_change_detected'] is True
    # The already-reflected benign players never enter the affected write plan.
    assert 640000 not in artifact['affected_pitcher_mlb_ids']


# ── additional focused coverage (per-behavior signal-quality assertions) ─────

def test_lane2_invalid_shape_is_review(app):
    lane = _tx_lane(_run(_tx_client([42, 'not-a-dict']), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    invalid = [d for d in lane['differences']
               if d['classification'] == intraday_reconcile.TX_INVALID_SHAPE]
    assert len(invalid) == 2
    assert all(d['severity'] == intraday_reconcile.SEVERITY_REVIEW for d in invalid)
    assert lane['checked']['invalid_shape'] == 2


def test_lane2_actionable_not_stored_is_actionable(app):
    lane = _tx_lane(_run(_tx_client([_tx('n', 800, type_code='RECALL', to_team_id=PHI)]),
                         team_ids=[PHI], lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_lane2_single_player_stored_conflict(app):
    _seed_stored_transaction(_tx('sc', 801, type_code='RECALL', to_team_id=PHI))
    lane = _tx_lane(_run(_tx_client([_tx('sc', 801, type_code='RECALL', to_team_id=NYM)]),
                         team_ids=[PHI], lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_STORED_CONFLICT
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert 'to_team_id' in d['conflicting_fields']


def test_lane2_benign_sample_has_no_severity(app):
    _seed_stored_transaction(_tx('bs', 802, type_code='SFA'))
    lane = _tx_lane(_run(_tx_client([_tx('bs', 802, type_code='SFA')]), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    sample = lane['informational_samples'][intraday_reconcile.TX_ALREADY_REFLECTED][0]
    assert sample['severity'] is None


def test_lane2_benign_suppressed_zero_under_limit(app):
    for i in range(2):  # fewer than the sample limit
        _seed_stored_transaction(_tx(f'u{i}', 803 + i, type_code='SFA'))
    source = [_tx(f'u{i}', 803 + i, type_code='SFA') for i in range(2)]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    assert lane['suppressed_counts']['benign_records_suppressed'] == 0


def test_informational_records_equals_informational_counts_sum(app):
    for i in range(3):
        _seed_stored_transaction(_tx(f'ir{i}', 810 + i, type_code='SFA'))
    source = (
        [_tx(f'ir{i}', 810 + i, type_code='SFA') for i in range(3)]
        + [_tx('np-a', None, type_code='CASH'), _tx('np-b', None, type_code='CASH')]
    )
    artifact = _run(_tx_client(source), team_ids=[PHI])
    tx = _tx_lane(artifact)
    assert sum(tx['informational_counts'].values()) == artifact['summary']['informational_records']
    assert artifact['summary']['informational_records'] == 5


def test_lane2_compound_new_contributes_affected_teams(app):
    components = _compound_pair('cn', 820001, 820002)  # PHI<->NYM trade
    artifact = _run(_tx_client(components), team_ids=[PHI])
    tx = _tx_lane(artifact)
    assert PHI in tx['affected_team_ids'] and NYM in tx['affected_team_ids']
    assert 820001 in tx['affected_pitcher_mlb_ids']


def test_lane2_compound_review_adds_no_affected_pitchers(app):
    components = _compound_pair('cr', 821001, 821002)
    _seed_stored_transaction(_tx('cr', 821099, type_code='TR', from_team_id=PHI, to_team_id=NYM))
    tx = _tx_lane(_run(_tx_client(components), team_ids=[PHI],
                       lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    # Review-required compound events never plan a write.
    assert tx['affected_pitcher_mlb_ids'] == []
    assert 821001 not in tx['affected_pitcher_mlb_ids']


def test_lane2_compound_counts_non_player_component(app):
    source = [
        _tx('mix', 822001, type_code='TR', from_team_id=PHI, to_team_id=NYM),
        _tx('mix', 822002, type_code='TR', from_team_id=NYM, to_team_id=PHI),
        _tx('mix', None, type_code='CASH'),  # non-player component of the SAME event
    ]
    lane = _tx_lane(_run(_tx_client(source), team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    finding = [d for d in lane['differences'] if d.get('event_key') == 'statsapi:mix'][0]
    assert finding['non_player_component_count'] == 1
    assert finding['player_component_count'] == 2
    assert lane['checked']['non_player_transactions'] == 1


def test_summary_total_equals_serialized_differences(scenario):
    artifact = _run(scenario)
    serialized = sum(
        len(artifact['lanes'][lane]['differences'])
        for lane in intraday_reconcile.ALL_LANES
        if lane in artifact['lanes']
    )
    assert artifact['summary']['total_differences'] == serialized


def test_changed_true_when_only_review_finding(app):
    source = [_tx('ro', None, type_code='SIGNED', player_full_name='Prospect X')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['changed'] is True
    assert artifact['summary']['review_required_findings'] >= 1
    assert artifact['summary']['actionable_differences'] == 0


def test_lane1_recall_severity_is_actionable(scenario):
    assert _lane1_by_id(_run(scenario))[999]['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_lane1_conflicting_team_severity_is_review(scenario):
    assert _lane1_by_id(_run(scenario))[555]['severity'] == intraday_reconcile.SEVERITY_REVIEW


def test_lane1_unresolved_identity_severity_is_review(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_ROSTER_ASSIGNMENT]
    unresolved = [d for d in lane['differences']
                  if d.get('change_type') == intraday_reconcile.CHANGE_UNRESOLVED_SOURCE_IDENTITY]
    assert unresolved
    assert all(d['severity'] == intraday_reconcile.SEVERITY_REVIEW for d in unresolved)


def test_lane1_newly_discovered_severity_is_actionable(scenario):
    assert _lane1_by_id(_run(scenario))[777]['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_lane3_newly_final_severity_is_actionable(scenario):
    assert _lane3_by_pk(_run(scenario))[700]['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_lane3_stored_finality_conflict_severity_is_review(scenario):
    assert _lane3_by_pk(_run(scenario))[705]['severity'] == intraday_reconcile.SEVERITY_REVIEW


def test_material_true_on_newly_final_game(app):
    _scheduled_pair(800, PHI, NYM, status_code='S', status_state=ScheduledGame.STATE_SCHEDULED)
    client = _tx_client(
        [], schedule=[_game(800, PHI, NYM, status_code='F', detailed='Final', abstract='Final')],
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
               {'id': NYM, 'name': 'Mets', 'abbreviation': 'NYM'}],
    )
    artifact = _run(client, team_ids=[PHI, NYM])
    assert 800 in artifact['would_refresh']['completed_game_pks']
    assert artifact['material_change_detected'] is True
    assert artifact['would_refresh']['publish_snapshot'] is True


def test_active_only_default_does_not_read_non_active_types(app):
    # A pitcher who is stored active but absent from the (empty) active roster is
    # a neutral departure; the audit must not have fetched 40-man/full/nonRoster.
    _seed_pitcher(830, 'Gone Arm', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    client = _tx_client([], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    _run(client, team_ids=[PHI], lanes=[intraday_reconcile.LANE_ROSTER_ASSIGNMENT])
    assert client.calls.get('get_team_roster', 0) == 1  # active only
