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


def test_lane1_il_placement(scenario):
    d = _lane1_by_id(_run(scenario))[300]
    assert d['change_type'] == intraday_reconcile.CHANGE_IL_PLACEMENT
    assert d['observed_official_status'] == STATUS_IL_15
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_il_activation(scenario):
    d = _lane1_by_id(_run(scenario))[301]
    assert d['change_type'] == intraday_reconcile.CHANGE_IL_ACTIVATION
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_ENTER
    assert d['targeted_recent_work_required'] is True


def test_lane1_option(scenario):
    d = _lane1_by_id(_run(scenario))[302]
    assert d['change_type'] == intraday_reconcile.CHANGE_OPTION
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


def test_lane1_dfa(scenario):
    d = _lane1_by_id(_run(scenario))[303]
    assert d['change_type'] == intraday_reconcile.CHANGE_DFA
    assert d['bullpen_population_effect'] == intraday_reconcile.EFFECT_LEAVE


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
    assert by_txid['t1']['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert by_txid['t1']['player_mlb_id'] == 999
    assert by_txid['t2']['classification'] == intraday_reconcile.TX_NON_PLAYER
    assert by_txid['t3']['classification'] == intraday_reconcile.TX_UNRESOLVED_IDENTITY
    assert by_txid['t4']['classification'] == intraday_reconcile.TX_ALREADY_REFLECTED
    checked = lane['checked']
    assert checked['actionable_player_transactions'] == 1
    assert checked['non_player_transactions'] == 1
    assert checked['unresolved_identity'] == 1


def test_lane2_stored_effect_not_reflected(scenario):
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_TRANSACTIONS]
    by_txid = {r.get('transaction_id'): r for r in lane['differences']}
    t5 = by_txid['t5']
    # Stored transaction whose recall (to NYM) is not reflected by the current
    # roster snapshot (which still shows PHI): a misaligned, unreflected effect.
    assert t5['roster_snapshot_alignment'] == transaction_ingestion.ALIGNMENT_MISALIGNED
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
    assert parsed['capability'] == 'intraday_reconciliation_audit'
    assert parsed['version'] == '1.0.0'
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
        'capability': 'intraday_reconciliation_audit', 'version': '1.0.0', 'mode': 'intraday',
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
