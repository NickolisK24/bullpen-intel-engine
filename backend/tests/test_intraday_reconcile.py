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
                 roster_errors=None, transactions_error=None, schedule_error=None,
                 people=None, people_errors=None):
        self.rosters = rosters or {}
        self.transactions = transactions or []
        self.schedule = schedule or []
        self.teams = teams or []
        self.roster_errors = roster_errors or {}
        self.transactions_error = transactions_error
        self.schedule_error = schedule_error
        # people: {mlb_id: {'primaryPosition': {...}}}; people_errors: {mlb_id: msg}
        self.people = people or {}
        self.people_errors = people_errors or {}
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

    def get_player_info(self, player_id):
        self._count('get_player_info')
        if player_id in self.people_errors:
            raise RuntimeError(self.people_errors[player_id])
        return self.people.get(player_id)


# Official position evidence builders (role verification fixtures).
POSITION_PITCHER = {'code': '1', 'abbreviation': 'P', 'type': 'Pitcher', 'name': 'Pitcher'}
POSITION_TWO_WAY = {'code': 'Y', 'abbreviation': 'TWP', 'type': 'Two-Way Player',
                    'name': 'Two-Way Player'}
POSITION_CATCHER = {'code': '2', 'abbreviation': 'C', 'type': 'Catcher', 'name': 'Catcher'}
POSITION_OUTFIELD = {'code': '8', 'abbreviation': 'CF', 'type': 'Outfielder', 'name': 'Outfielder'}


def person(position):
    """An MLB /people response person object carrying a primaryPosition."""
    return {'primaryPosition': dict(position)}


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
    # Only meaningful findings are serialized: t1 (actionable new, proven pitcher)
    # and t3 (unresolved identity). Benign t2 (non-player), t4 (already reflected),
    # and t5 (exact-detail mismatch, membership aligned) are counted, not serialized.
    assert by_txid['t1']['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert by_txid['t1']['player_mlb_id'] == 999
    assert by_txid['t1']['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_PITCHER
    assert by_txid['t3']['classification'] == intraday_reconcile.TX_UNRESOLVED_IDENTITY
    assert 't2' not in by_txid  # non-player is informational, not a difference
    assert 't4' not in by_txid  # already reflected is benign, not a difference
    assert 't5' not in by_txid  # membership aligned -> benign, not a difference
    checked = lane['checked']
    assert checked['actionable_differences'] == 1  # t1 only (t5 is now benign)
    assert checked['non_player_transactions'] == 1
    assert checked['already_reflected'] >= 1
    assert checked['unresolved_identity'] == 1
    assert lane['informational_counts']['non_player_count'] == 1


def test_lane2_stored_effect_is_membership_aware(scenario):
    # t5: a stored RECALL-to-NYM for pitcher 400, whose same-day snapshot was PHI
    # (exact-state misaligned). But current official active-bullpen membership
    # (400 is active on PHI) already matches stored state, so under the
    # bullpen-relevance correction this is a benign exact-detail mismatch — never
    # a material public-state change.
    lane = _run(scenario)['lanes'][intraday_reconcile.LANE_TRANSACTIONS]
    assert all(d.get('transaction_id') != 't5' for d in lane['differences'])
    sample = lane['informational_samples'].get(
        intraday_reconcile.TX_TRANSACTION_DETAIL_MISMATCH, []
    )
    t5 = {r.get('transaction_id'): r for r in sample}.get('t5')
    assert t5 is not None
    assert t5['classification'] == intraday_reconcile.TX_TRANSACTION_DETAIL_MISMATCH
    assert t5['classification'] != intraday_reconcile.TX_STATUS_EFFECT_UNREFLECTED
    assert t5['public_bullpen_membership_alignment'] == intraday_reconcile.MEMBERSHIP_ALIGNED
    assert t5['severity'] is None
    assert lane['checked']['transaction_detail_mismatches'] >= 1
    assert lane['checked']['public_bullpen_effect_unreflected'] == 0


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
        'summary': {'total_meaningful_findings': 0, 'material_change_detected': False},
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


def _tx_client(transactions, *, rosters=None, teams=None, schedule=None,
               people=None, people_errors=None):
    return FakeMlbClient(
        rosters=rosters or {}, transactions=transactions,
        schedule=schedule or [], teams=teams or [],
        people=people or {}, people_errors=people_errors or {},
    )


def _pitchers(*mlb_ids):
    """Role-evidence map marking each id as a proven pitcher."""
    return {mlb_id: person(POSITION_PITCHER) for mlb_id in mlb_ids}


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


# ── C4/C5: exact-state alignment vs public bullpen membership ─────────────────

def test_public_bullpen_effect_unreflected_is_material(app):
    # A proven pitcher officially RECALLED (now active on PHI) while BaseballOS
    # still shows him inactive AND the stored same-day snapshot disagreed with the
    # transaction team (exact state misaligned): current public bullpen membership
    # is misaligned — a genuine, materially actionable public-state mismatch.
    p = _seed_pitcher(676467, 'Colton Gordon', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    _seed_snapshot(p, NYM, SIGNAL_DATE, STATUS_ACTIVE)  # BaseballOS thought NYM -> misaligned
    tx = _tx('recall1', 676467, type_code='RECALL', to_team_id=PHI, player_full_name='Colton Gordon')
    _seed_stored_transaction(tx)
    client = _tx_client(
        [tx],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(676467, 'Colton Gordon', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    d = {r.get('transaction_id'): r for r in _tx_lane(_run(client, team_ids=[PHI]))['differences']}
    assert d['recall1']['classification'] == intraday_reconcile.TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED
    assert d['recall1']['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert d['recall1']['public_bullpen_membership_alignment'] == intraday_reconcile.MEMBERSHIP_MISALIGNED
    assert d['recall1']['classification'] != intraday_reconcile.TX_STORED_CONFLICT


def test_exact_state_misalignment_is_not_a_conflict(app):
    # A misaligned exact roster snapshot alone is never a stored source-fact
    # conflict, and — when current membership is correct — never material.
    _seed_pitcher(681911, 'Cam Sanders', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    p = Pitcher.query.filter_by(mlb_id=681911).first()
    _seed_snapshot(p, PHI, SIGNAL_DATE, STATUS_ACTIVE)
    tx = _tx('se2', 681911, type_code='RECALL', to_team_id=NYM, player_full_name='Cam Sanders')
    _seed_stored_transaction(tx)
    client = _tx_client(
        [tx],
        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(681911, 'Cam Sanders', status=ACTIVE)]},
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
    )
    lane = _tx_lane(_run(client, team_ids=[PHI]))
    assert lane['checked']['stored_conflicts'] == 0
    assert lane['checked']['public_bullpen_effect_unreflected'] == 0


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
    lane = _tx_lane(_run(_tx_client(components, people=_pitchers(660003, 660004)),
                         team_ids=[PHI], lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
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
    lane = _tx_lane(_run(_tx_client(components, people=_pitchers(660007, 660008)),
                         team_ids=[PHI], lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
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
    for key in ('total_meaningful_findings', 'records_checked',
                'total_actionable_findings', 'review_required_findings',
                'unresolved_findings', 'transaction_record_actionable_count',
                'transaction_ledger_only_findings',
                'transaction_public_bullpen_material_count',
                'public_roster_change_count', 'schedule_public_change_count',
                'public_bullpen_change_count', 'informational_records',
                'benign_records_suppressed', 'material_change_detected',
                'affected_team_ids'):
        assert key in summary, key
    assert summary['total_actionable_findings'] + summary['review_required_findings'] \
        == summary['total_meaningful_findings']
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
    # A brand-new, not-yet-stored PROVEN-PITCHER transaction with NO roster
    # confirmation is transaction-ledger actionable but NOT public-material
    # (Observation #3 correction): it never publishes a snapshot by itself.
    source = [_tx('m1', 996, type_code='RECALL', to_team_id=PHI)]
    artifact = _run(_tx_client(source, people=_pitchers(996)), team_ids=[PHI])
    assert artifact['changed'] is True
    assert artifact['transaction_ledger_change_detected'] is True
    assert artifact['public_bullpen_change_detected'] is False
    assert artifact['material_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False
    assert 996 in artifact['would_refresh']['transaction_ledger']['transaction_participant_mlb_ids']


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
        _tx('a3', 700101, type_code='RECALL', to_team_id=PHI),       # ledger-actionable
    ]
    artifact = _run(_tx_client(source, people=_pitchers(700101)), team_ids=[PHI])
    # Public affected pitchers require roster confirmation — a missing transaction
    # alone (700101) is ledger-only, benign (700100) never counts either.
    assert artifact['affected_pitcher_mlb_ids'] == []
    ledger = artifact['would_refresh']['transaction_ledger']['transaction_participant_mlb_ids']
    assert 700101 in ledger
    assert 700100 not in ledger


def test_publish_snapshot_not_from_benign(app):
    _seed_stored_transaction(_tx('p1', 700200, type_code='SFA'))
    artifact = _run(_tx_client([_tx('p1', 700200, type_code='SFA')]), team_ids=[PHI])
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_publish_snapshot_not_from_review_only(app):
    source = [_tx('p2', None, type_code='SIGNED', player_full_name='Ghost')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_warm_tonight_not_from_transaction_only(app):
    # A ledger-only transaction (missing record, no roster confirmation) must not
    # warm Tonight and is not material.
    source = [_tx('w1', 700300, type_code='RECALL', to_team_id=PHI)]
    artifact = _run(_tx_client(source, people=_pitchers(700300)), team_ids=[PHI])
    assert artifact['material_change_detected'] is False
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
    # The compound-new components are proven pitchers via role evidence.
    people = _pitchers(650003, 650004)
    return _tx_client(transactions, rosters=rosters, teams=teams, people=people)


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
    # The three former status-effect contradictions (proven pitchers whose current
    # active-bullpen membership is correct) are now benign exact-detail mismatches,
    # not material findings.
    assert checked['transaction_detail_mismatches'] == 3
    assert checked['public_bullpen_effect_unreflected'] == 0
    # Benign already-reflected records beyond the sample are suppressed.
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
    # includes the 5 already-reflected + 2 non-player + 1 reflected-compound + 3
    # exact-detail-mismatch benign rows.
    assert artifact['changed'] is True
    assert summary['informational_records'] == 5 + 2 + 1 + 3
    assert summary['total_meaningful_findings'] == summary['total_actionable_findings'] + summary['review_required_findings']
    # Actionable findings exist (compound_new, newly-discovered proven pitchers),
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
    lane = _tx_lane(_run(
        _tx_client([_tx('n', 800, type_code='RECALL', to_team_id=PHI)], people=_pitchers(800)),
        team_ids=[PHI], lanes=[intraday_reconcile.LANE_TRANSACTIONS]))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert d['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_PITCHER


def test_lane2_single_player_stored_conflict(app):
    _seed_stored_transaction(_tx('sc', 801, type_code='RECALL', to_team_id=PHI))
    lane = _tx_lane(_run(
        _tx_client([_tx('sc', 801, type_code='RECALL', to_team_id=NYM)], people=_pitchers(801)),
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


def test_lane2_compound_new_contributes_ledger_teams(app):
    # A missing compound event is transaction-ledger actionable (not public) —
    # its MLB teams land in the ledger plan, never in public affected teams.
    components = _compound_pair('cn', 820001, 820002)  # PHI<->NYM trade
    artifact = _run(_tx_client(components, people=_pitchers(820001, 820002)), team_ids=[PHI])
    tx = _tx_lane(artifact)
    ledger = tx['transaction_ledger']
    assert PHI in ledger['transaction_related_mlb_team_ids']
    assert NYM in ledger['transaction_related_mlb_team_ids']
    assert 820001 in ledger['transaction_participant_mlb_ids']
    assert tx['affected_team_ids'] == []
    assert tx['affected_pitcher_mlb_ids'] == []


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
    assert artifact['summary']['total_meaningful_findings'] == serialized


def test_changed_true_when_only_review_finding(app):
    source = [_tx('ro', None, type_code='SIGNED', player_full_name='Prospect X')]
    artifact = _run(_tx_client(source), team_ids=[PHI])
    assert artifact['changed'] is True
    assert artifact['summary']['review_required_findings'] >= 1
    assert artifact['summary']['total_actionable_findings'] == 0


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


# ═════════════════════════════════════════════════════════════════════════════
# Bullpen-relevance correction (contract v1.2.0) — Production Observation #2
#
# Observation #2 (2026-07-17, v1.1.0) passed infrastructure, read-only safety,
# API efficiency, compactness, compound grouping, and source-name preservation,
# but FAILED bullpen-relevance filtering, MLB-team impact scoping, and
# public-state materiality: four unstored players with no proof of pitcher role
# became actionable; minor-league team ids (512/556/568) entered public team
# planning; and historical option/IL effects were treated as material without
# chronology or current-membership proof. These tests pin the correction.
# ═════════════════════════════════════════════════════════════════════════════

BAL, DET, PIT, SEA, ATL, WSH = 110, 116, 134, 136, 144, 158
AFFILIATE_A, AFFILIATE_B, AFFILIATE_C = 512, 556, 568
OPT = 'OPT'


def _two_way(*ids):
    return {i: person(POSITION_TWO_WAY) for i in ids}


def _non_pitchers(*ids):
    return {i: person(POSITION_CATCHER) for i in ids}


def _tx2(client, **kw):
    kw.setdefault('team_ids', [PHI])
    kw['lanes'] = [intraday_reconcile.LANE_TRANSACTIONS]
    return _tx_lane(_run(client, **kw))


# ── C1: prove bullpen relevance before actionable classification ─────────────

def test_unstored_proven_pitcher_actionable(app):
    lane = _tx2(_tx_client([_tx('p', 900001, type_code='RECALL', to_team_id=PHI)],
                           people=_pitchers(900001)))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE
    assert d['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_PITCHER


def test_unstored_two_way_actionable(app):
    lane = _tx2(_tx_client([_tx('tw', 900002, type_code='RECALL', to_team_id=PHI)],
                           people=_two_way(900002)))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert d['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_TWO_WAY
    assert d['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_unstored_non_pitcher_is_informational(app):
    lane = _tx2(_tx_client([_tx('np', 900003, type_code='RECALL', to_team_id=PHI)],
                           people=_non_pitchers(900003)))
    assert lane['differences'] == []
    assert lane['checked']['non_pitcher_transactions'] == 1
    assert lane['informational_counts']['non_pitcher_count'] == 1
    sample = lane['informational_samples'][intraday_reconcile.TX_NON_PITCHER][0]
    assert sample['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_NON_PITCHER
    assert sample['severity'] is None


def test_unstored_unresolved_role_is_review(app):
    lane = _tx2(_tx_client([_tx('u', 900004, type_code='RECALL', to_team_id=PHI)]))
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_BULLPEN_RELEVANCE_UNRESOLVED
    assert d['severity'] == intraday_reconcile.SEVERITY_REVIEW
    assert d['bullpen_relevance'] == intraday_reconcile.ROLE_UNRESOLVED
    assert lane['limitations']  # role could not be verified


def test_unresolved_role_not_in_targeted(app):
    artifact = _run(_tx_client([_tx('u', 900005, type_code='RECALL', to_team_id=PHI)]),
                    team_ids=[PHI])
    assert 900005 not in artifact['would_refresh']['targeted_pitcher_mlb_ids']
    assert 900005 not in artifact['affected_pitcher_mlb_ids']


def test_non_pitcher_not_in_targeted(app):
    artifact = _run(_tx_client([_tx('np', 900006, type_code='RECALL', to_team_id=PHI)],
                               people=_non_pitchers(900006)), team_ids=[PHI])
    assert 900006 not in artifact['would_refresh']['targeted_pitcher_mlb_ids']
    assert 900006 not in artifact['affected_pitcher_mlb_ids']


def test_role_identity_uses_mlb_id_only(app):
    # A participant whose NAME reads like a pitcher but whose official position is
    # a catcher is a proven non-pitcher — role is never inferred from the name.
    lane = _tx2(_tx_client(
        [_tx('n', 900007, type_code='RECALL', to_team_id=PHI, player_full_name='Ace Fireballer')],
        people=_non_pitchers(900007)))
    assert lane['differences'] == []
    assert lane['checked']['non_pitcher_transactions'] == 1


def test_role_evidence_preserves_position_fields(app):
    lane = _tx2(_tx_client([_tx('p', 900008, type_code='RECALL', to_team_id=PHI)],
                           people=_pitchers(900008)))
    d = lane['differences'][0]
    assert d['official_position_code'] == '1'
    assert d['official_position_abbreviation'] == 'P'
    assert d['official_position_type'] == 'Pitcher'
    assert d['role_verification_status'] == intraday_reconcile.ROLE_SOURCE_PEOPLE_LOOKUP


# ── C2: role acquisition is targeted and bounded ─────────────────────────────

def test_role_lookup_deduplicated(app):
    # Same player in two separate events -> exactly one /people lookup.
    client = _tx_client(
        [_tx('a', 900009, type_code='RECALL', to_team_id=PHI),
         _tx('b', 900009, type_code='RECALL', to_team_id=NYM)],
        people=_pitchers(900009),
    )
    _tx2(client)
    assert client.calls.get('get_player_info', 0) == 1


def test_role_lookup_only_for_unstored_meaningful(app):
    # An already-reflected transaction and a non-player row never trigger a lookup.
    _seed_stored_transaction(_tx('ar', 900010, type_code='SFA'))
    client = _tx_client(
        [_tx('ar', 900010, type_code='SFA'), _tx('np', None, type_code='CASH')],
        people=_pitchers(900010),
    )
    _tx2(client)
    assert 'get_player_info' not in client.calls


def test_role_lookup_budget_enforced(app):
    ids = [900101, 900102, 900103]
    client = _tx_client([_tx(f'b{i}', mlb, type_code='RECALL', to_team_id=PHI)
                         for i, mlb in enumerate(ids)], people=_pitchers(*ids))
    lane = _tx_lane(_run(client, team_ids=[PHI],
                         lanes=[intraday_reconcile.LANE_TRANSACTIONS], max_role_lookups=1))
    assert lane['role_verification']['lookups_used'] == 1
    assert lane['role_verification']['budget_exceeded'] is True
    # Two participants remain unresolved (never assumed pitchers).
    assert lane['checked']['bullpen_relevance_unresolved'] == 2
    assert client.calls.get('get_player_info', 0) == 1


def test_role_lookup_failure_fails_closed(app):
    client = _tx_client([_tx('f', 900012, type_code='RECALL', to_team_id=PHI)],
                        people_errors={900012: 'people endpoint down'})
    lane = _tx2(client)
    d = lane['differences'][0]
    assert d['classification'] == intraday_reconcile.TX_BULLPEN_RELEVANCE_UNRESOLVED
    assert d['severity'] == intraday_reconcile.SEVERITY_REVIEW
    assert lane['role_verification']['lookup_failures'] >= 1


# ── C3: MLB-team impact scope ────────────────────────────────────────────────

def test_non_mlb_team_ids_preserved_but_not_public(app):
    # Proven pitcher, missing RECALL PIT(MLB) -> 512(affiliate). This is a ledger
    # record (no roster confirmation), so PIT lands in the ledger plan and 512
    # stays evidence-only — neither enters public affected teams / recomputation.
    tx = _tx('aff', 930001, type_code='RECALL', from_team_id=PIT, to_team_id=AFFILIATE_A)
    artifact = _run(_tx_client([tx], people=_pitchers(930001)), team_ids=[PHI])
    lane = _tx_lane(artifact)
    finding = lane['differences'][0]
    assert finding['from_team_id'] == PIT and finding['to_team_id'] == AFFILIATE_A
    assert AFFILIATE_A in lane['related_non_mlb_team_ids']
    ledger = lane['transaction_ledger']
    assert PIT in ledger['transaction_related_mlb_team_ids']
    assert AFFILIATE_A in ledger['transaction_related_non_mlb_team_ids']
    # Public impact contains neither (ledger-only, no roster confirmation).
    assert lane['affected_team_ids'] == []
    assert PIT not in artifact['would_refresh']['affected_team_ids']
    assert AFFILIATE_A not in artifact['would_refresh']['affected_team_ids']
    assert AFFILIATE_A not in artifact['would_refresh']['recalculate_team_reads']
    assert AFFILIATE_A in artifact['summary']['non_mlb_team_ids_observed']


def test_mlb_teams_in_ledger_not_public(app):
    # A missing MLB<->MLB transaction is a ledger record; its teams never enter
    # public affected-team planning without roster confirmation.
    tx = _tx('mlb', 930002, type_code='RECALL', from_team_id=BAL, to_team_id=DET)
    artifact = _run(_tx_client([tx], people=_pitchers(930002)), team_ids=[PHI])
    ledger = artifact['would_refresh']['transaction_ledger']
    assert BAL in ledger['transaction_related_mlb_team_ids']
    assert DET in ledger['transaction_related_mlb_team_ids']
    assert artifact['would_refresh']['affected_team_ids'] == []


# ── C4/C5/C6/C7: state alignment vs public membership; chronology; cross-lane ─

def _seed_membership_case(mlb_id, *, stored_active, snapshot_team, tx_id, type_code,
                          to_team_id=None, from_team_id=None):
    status = STATUS_ACTIVE if stored_active else STATUS_OPTIONED
    p = _seed_pitcher(mlb_id, f'P{mlb_id}', PHI, 'PHI', roster_status=status, active=stored_active)
    _seed_snapshot(p, snapshot_team, SIGNAL_DATE, STATUS_ACTIVE)
    tx = _tx(tx_id, mlb_id, type_code=type_code, to_team_id=to_team_id, from_team_id=from_team_id)
    _seed_stored_transaction(tx)
    return tx


def test_transaction_state_alignment_distinct_from_membership(app):
    # Optioned pitcher correctly outside the active bullpen: exact stored state is
    # misaligned, but public membership is aligned -> benign detail mismatch.
    tx = _seed_membership_case(931001, stored_active=False, snapshot_team=PHI,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    lane = _tx_lane(_run(client, team_ids=[PHI]))
    d = {r.get('transaction_id'): r for r in
         lane['informational_samples'].get(intraday_reconcile.TX_TRANSACTION_DETAIL_MISMATCH, [])}
    f = d['opt']
    assert f['transaction_state_alignment'] == 'misaligned'
    assert f['public_bullpen_membership_alignment'] == intraday_reconcile.MEMBERSHIP_ALIGNED
    assert f['classification'] == intraday_reconcile.TX_TRANSACTION_DETAIL_MISMATCH


def test_affiliate_mismatch_non_material_when_membership_correct(app):
    tx = _seed_membership_case(931002, stored_active=False, snapshot_team=PHI,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    assert artifact['material_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_official_inactive_stored_active_is_material(app):
    # Stored ACTIVE but officially gone from the active roster (option), exact
    # state misaligned -> material public mismatch.
    tx = _seed_membership_case(931003, stored_active=True, snapshot_team=NYM,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    d = {r.get('transaction_id'): r for r in _tx_lane(_run(client, team_ids=[PHI]))['differences']}
    assert d['opt']['classification'] == intraday_reconcile.TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED
    assert d['opt']['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_option_superseded_by_recall_is_non_material(app):
    p = _seed_pitcher(932001, 'Sup', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(p, PHI, date(2026, 7, 12), STATUS_ACTIVE)
    option = _tx('opt', 932001, type_code=OPT, to_team_id=AFFILIATE_A, transaction_date='2026-07-12')
    recall = _tx('rec', 932001, type_code='RECALL', to_team_id=PHI, transaction_date='2026-07-14')
    _seed_stored_transaction(option)
    _seed_stored_transaction(recall)
    client = _tx_client([option, recall],
                        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(932001, 'Sup', status=ACTIVE)]},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    lane = _tx_lane(_run(client, team_ids=[PHI]))
    sup = {r.get('transaction_id'): r for r in
           lane['informational_samples'].get(intraday_reconcile.TX_SUPERSEDED_TRANSACTION, [])}
    assert 'opt' in sup
    assert sup['opt']['classification'] == intraday_reconcile.TX_SUPERSEDED_TRANSACTION
    assert sup['opt']['superseded_by_event_key'] == 'statsapi:rec'
    assert sup['opt']['severity'] is None


def test_recall_superseded_by_option_is_non_material(app):
    p = _seed_pitcher(932002, 'Sup2', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    _seed_snapshot(p, NYM, date(2026, 7, 12), STATUS_ACTIVE)
    recall = _tx('rec', 932002, type_code='RECALL', to_team_id=PHI, transaction_date='2026-07-12')
    option = _tx('opt', 932002, type_code=OPT, to_team_id=AFFILIATE_A, transaction_date='2026-07-14')
    _seed_stored_transaction(recall)
    _seed_stored_transaction(option)
    client = _tx_client([recall, option], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    lane = _tx_lane(_run(client, team_ids=[PHI]))
    sup = {r.get('transaction_id'): r for r in
           lane['informational_samples'].get(intraday_reconcile.TX_SUPERSEDED_TRANSACTION, [])}
    assert 'rec' in sup
    assert sup['rec']['latest_applicable_event_key'] == 'statsapi:opt'


def test_ambiguous_chronology_is_review_and_no_publish(app):
    p = _seed_pitcher(933001, 'Amb', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(p, PHI, date(2026, 7, 15), STATUS_ACTIVE)
    option = _tx('opt', 933001, type_code=OPT, to_team_id=AFFILIATE_A, transaction_date='2026-07-15')
    recall = _tx('rec', 933001, type_code='RECALL', to_team_id=PHI, transaction_date='2026-07-15')
    _seed_stored_transaction(option)
    _seed_stored_transaction(recall)
    client = _tx_client([option, recall],
                        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(933001, 'Amb', status=ACTIVE)]},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    lane = _tx_lane(artifact)
    d = {r.get('transaction_id'): r for r in lane['differences']}
    assert d['opt']['classification'] == intraday_reconcile.TX_CHRONOLOGY_UNRESOLVED
    assert d['opt']['severity'] == intraday_reconcile.SEVERITY_REVIEW
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_current_roster_overrides_historical_option(app):
    # A stored option (implying the pitcher LEFT) is misaligned, but the roster
    # lane proves the pitcher is currently ACTIVE. The historical option's
    # implication is overridden by current evidence: the audit asserts no material
    # mismatch (it is a review-only chronology finding, never material).
    tx = _seed_membership_case(934001, stored_active=True, snapshot_team=NYM,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx],
                        rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(934001, 'P934001', status=ACTIVE)]},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    lane = _tx_lane(artifact)
    assert lane['checked']['public_bullpen_effect_unreflected'] == 0
    d = {r.get('transaction_id'): r for r in lane['differences']}
    assert d['opt']['classification'] == intraday_reconcile.TX_CHRONOLOGY_UNRESOLVED
    assert d['opt']['severity'] == intraday_reconcile.SEVERITY_REVIEW


# ── C8: impact-plan safety ───────────────────────────────────────────────────

def test_detail_mismatch_does_not_warm_tonight(app):
    tx = _seed_membership_case(935001, stored_active=False, snapshot_team=PHI,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    assert artifact['would_refresh']['warm_tonight'] is False


def test_membership_mismatch_may_warm_tonight(app):
    tx = _seed_membership_case(935002, stored_active=True, snapshot_team=NYM,
                               tx_id='opt', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    assert artifact['would_refresh']['warm_tonight'] is True


def test_non_pitcher_does_not_set_transactions_refresh(app):
    artifact = _run(_tx_client([_tx('np', 936001, type_code='RECALL', to_team_id=PHI)],
                               people=_non_pitchers(936001)), team_ids=[PHI])
    assert artifact['would_refresh']['transactions'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False


def test_review_role_finding_changed_not_material(app):
    artifact = _run(_tx_client([_tx('u', 936002, type_code='RECALL', to_team_id=PHI)]),
                    team_ids=[PHI])
    assert artifact['changed'] is True
    assert artifact['material_change_detected'] is False
    assert artifact['summary']['role_unresolved_findings'] >= 1


def test_ledger_participants_only_proven_pitchers(app):
    # A missing proven-pitcher transaction is a ledger participant (public affected
    # pitchers require roster confirmation, which this run does not have).
    artifact = _run(_tx_client([_tx('p', 937001, type_code='RECALL', to_team_id=PHI)],
                               people=_pitchers(937001)), team_ids=[PHI])
    assert artifact['affected_pitcher_mlb_ids'] == []
    ledger = artifact['would_refresh']['transaction_ledger']
    assert 937001 in ledger['transaction_participant_mlb_ids']


def test_ledger_participants_exclude_non_pitcher_and_unresolved(app):
    source = [
        _tx('p', 938001, type_code='RECALL', to_team_id=PHI),   # proven pitcher -> ledger
        _tx('np', 938002, type_code='RECALL', to_team_id=PHI),  # non-pitcher -> informational
        _tx('u', 938003, type_code='RECALL', to_team_id=PHI),   # unresolved -> review
    ]
    artifact = _run(_tx_client(source, people={**_pitchers(938001), **_non_pitchers(938002)}),
                    team_ids=[PHI])
    ledger = artifact['would_refresh']['transaction_ledger']
    assert ledger['transaction_participant_mlb_ids'] == [938001]
    assert artifact['affected_pitcher_mlb_ids'] == []


# ── C10: Production Observation #2 regression fixture ────────────────────────

@pytest.fixture
def observation_two(app):
    """Compact fixture mirroring the structure of Production Observation #2:
    two newly-discovered active pitchers (with source names), four unstored
    transaction participants covering every role outcome, minor-league team ids
    that must stay evidence-only, and the three named historical option/recall
    players covering supersession, correct-membership, and genuine mismatch."""
    # Named chronology players (stored pitchers on PHI).
    granillo = _seed_pitcher(701552, 'Andre Granillo', PHI, 'PHI',
                             roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(granillo, PHI, date(2026, 7, 12), STATUS_ACTIVE)
    g_option = _tx('gran-opt', 701552, type_code=OPT, to_team_id=AFFILIATE_A,
                   transaction_date='2026-07-12')
    g_recall = _tx('gran-rec', 701552, type_code='RECALL', to_team_id=PHI,
                   transaction_date='2026-07-14')
    _seed_stored_transaction(g_option)
    _seed_stored_transaction(g_recall)

    sanders = _seed_pitcher(676742, 'Cam Sanders', PHI, 'PHI',
                            roster_status=STATUS_OPTIONED, active=False)
    _seed_snapshot(sanders, PHI, SIGNAL_DATE, STATUS_ACTIVE)
    s_option = _tx('san-opt', 676742, type_code=OPT, to_team_id=AFFILIATE_B)
    _seed_stored_transaction(s_option)

    gordon = _seed_pitcher(676467, 'Colton Gordon', PHI, 'PHI',
                           roster_status=STATUS_OPTIONED, active=False)
    _seed_snapshot(gordon, NYM, SIGNAL_DATE, STATUS_ACTIVE)
    go_recall = _tx('gor-rec', 676467, type_code='RECALL', to_team_id=PHI)
    _seed_stored_transaction(go_recall)

    # Four unstored transaction participants — every role outcome.
    risley = _tx('risley', 836083, type_code=OPT, from_team_id=PIT, to_team_id=AFFILIATE_A,
                 player_full_name='Braydon Risley')            # proven pitcher
    taylor = _tx('taylor', 694930, type_code='TR', from_team_id=SEA, to_team_id=AFFILIATE_B,
                 player_full_name='Carson Taylor')             # proven non-pitcher
    brenner = _tx('brenner', 836200, type_code='RECALL', from_team_id=WSH, to_team_id=ATL,
                  player_full_name='Jack Brenner')             # unresolved role
    dorland = _tx('dorland', 836451, type_code='RECALL', from_team_id=ATL, to_team_id=AFFILIATE_C,
                  player_full_name='Cole Dorland')             # proven two-way
    bal_det = _tx('baldet', 939001, type_code='TR', from_team_id=BAL, to_team_id=DET)  # pitcher

    transactions = [
        g_option, g_recall, s_option, go_recall,
        risley, taylor, brenner, dorland, bal_det,
    ]
    rosters = {
        (PHI, ROSTER_TYPE_ACTIVE): [
            roster_entry(701552, 'Andre Granillo', status=ACTIVE),  # stays active
            roster_entry(676467, 'Colton Gordon', status=ACTIVE),   # genuine mismatch
        ],
        (TOR, ROSTER_TYPE_ACTIVE): [roster_entry(669310, 'CJ Van Eyk', status=ACTIVE)],
        (ATH, ROSTER_TYPE_ACTIVE): [roster_entry(814305, 'Yunior Tur', status=ACTIVE)],
    }
    teams = [
        {'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
        {'id': TOR, 'name': 'Blue Jays', 'abbreviation': 'TOR'},
        {'id': ATH, 'name': 'Athletics', 'abbreviation': 'ATH'},
    ]
    people = {
        **_pitchers(836083, 939001),
        **_two_way(836451),
        **_non_pitchers(694930),
        # 836200 (Jack Brenner) intentionally absent -> unresolved role.
    }
    return _tx_client(transactions, rosters=rosters, teams=teams, people=people)


def _obs2_run(observation_two):
    return _run(observation_two, team_ids=[PHI, TOR, ATH])


def test_observation_two_role_gating(observation_two):
    lane = _tx_lane(_obs2_run(observation_two))
    by_txid = {r.get('transaction_id'): r for r in lane['differences']}
    # Proven pitcher and two-way become actionable.
    assert by_txid['risley']['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    assert by_txid['risley']['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_PITCHER
    assert by_txid['dorland']['bullpen_relevance'] == intraday_reconcile.ROLE_PROVEN_TWO_WAY
    assert by_txid['dorland']['classification'] == intraday_reconcile.TX_ACTIONABLE_NOT_STORED
    # Proven non-pitcher is informational, never a difference.
    assert 'taylor' not in by_txid
    assert lane['checked']['non_pitcher_transactions'] == 1
    # Unresolved role is review-required, never actionable.
    assert by_txid['brenner']['classification'] == intraday_reconcile.TX_BULLPEN_RELEVANCE_UNRESOLVED
    assert by_txid['brenner']['severity'] == intraday_reconcile.SEVERITY_REVIEW


def test_observation_two_non_mlb_scoping(observation_two):
    artifact = _obs2_run(observation_two)
    lane = _tx_lane(artifact)
    for affiliate in (AFFILIATE_A, AFFILIATE_B, AFFILIATE_C):
        assert affiliate not in artifact['would_refresh']['affected_team_ids']
        assert affiliate not in artifact['would_refresh']['recalculate_team_reads']
        assert affiliate not in lane['affected_team_ids']
    # The affiliate ids remain visible as evidence.
    observed = set(artifact['summary']['non_mlb_team_ids_observed'])
    assert {AFFILIATE_A, AFFILIATE_C}.issubset(observed)
    # Risley (missing OPT from Pittsburgh, no roster confirmation) is ledger-only:
    # PIT lands in the ledger plan, never in public impact.
    assert PIT in lane['transaction_ledger']['transaction_related_mlb_team_ids']
    assert PIT not in lane['affected_team_ids']


def test_observation_two_chronology(observation_two):
    lane = _tx_lane(_obs2_run(observation_two))
    # Granillo: the older option superseded by the later recall is non-material.
    superseded = {r.get('transaction_id'): r for r in
                  lane['informational_samples'].get(intraday_reconcile.TX_SUPERSEDED_TRANSACTION, [])}
    assert superseded['gran-opt']['classification'] == intraday_reconcile.TX_SUPERSEDED_TRANSACTION
    # Sanders: option correctly reflected (still inactive) -> benign detail mismatch.
    detail = {r.get('transaction_id'): r for r in
              lane['informational_samples'].get(intraday_reconcile.TX_TRANSACTION_DETAIL_MISMATCH, [])}
    assert detail['san-opt']['public_bullpen_membership_alignment'] == intraday_reconcile.MEMBERSHIP_ALIGNED
    # Gordon: genuine current membership mismatch -> material.
    by_txid = {r.get('transaction_id'): r for r in lane['differences']}
    assert by_txid['gor-rec']['classification'] == intraday_reconcile.TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED
    assert by_txid['gor-rec']['severity'] == intraday_reconcile.SEVERITY_ACTIONABLE


def test_observation_two_newly_discovered_names(observation_two):
    diffs = _lane1_by_id(_obs2_run(observation_two))
    assert diffs[669310]['change_type'] == intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE
    assert diffs[669310]['player_name'] == 'CJ Van Eyk'
    assert diffs[814305]['player_name'] == 'Yunior Tur'


def test_observation_two_honest_materiality(observation_two):
    artifact = _obs2_run(observation_two)
    summary = artifact['summary']
    # There ARE proven material findings (Gordon mismatch, unstored proven pitchers,
    # newly-discovered active pitchers), so a future write would be required.
    assert artifact['material_change_detected'] is True
    assert summary['transaction_public_bullpen_material_count'] >= 1
    assert summary['superseded_transactions'] >= 1
    assert summary['non_pitcher_transactions'] == 1
    assert summary['role_unresolved_findings'] >= 1
    # The non-pitcher and unresolved-role players never enter any write plan.
    assert 694930 not in artifact['affected_pitcher_mlb_ids']  # Carson Taylor (non-pitcher)
    assert 836200 not in artifact['affected_pitcher_mlb_ids']  # Jack Brenner (unresolved)
    ledger = artifact['would_refresh']['transaction_ledger']
    assert 694930 not in ledger['transaction_participant_mlb_ids']
    assert 836200 not in ledger['transaction_participant_mlb_ids']
    # Braydon Risley (proven pitcher, missing record) is ledger-only, not public.
    assert 836083 in ledger['transaction_participant_mlb_ids']
    assert 836083 not in artifact['affected_pitcher_mlb_ids']
    assert summary['mlb_teams_affected'] == artifact['would_refresh']['affected_team_ids']


# ═════════════════════════════════════════════════════════════════════════════
# Transaction-ledger vs public-materiality split (contract v1.3.0) — Obs #3
#
# Observation #3 (2026-07-17, v1.2.0) passed role verification, lookup governance,
# MLB-team scoping, chronology, and read-only safety, but still conflated a
# MISSING transaction record with a current public bullpen change: 20 missing
# org/ledger records drove public workload + team recomputation despite zero
# public membership mismatches, while the roster lane proved only four real
# current bullpen-population changes. These tests pin the ledger/public split.
# ═════════════════════════════════════════════════════════════════════════════

BOS, TB = 111, 139


def _lg(artifact):
    return artifact['would_refresh']['transaction_ledger']


# ── C1/C2/C3: ledger actionability is independent of public materiality ───────

def test_missing_sgn_pitcher_is_ledger_actionable(app):
    artifact = _run(_tx_client([_tx('s', 950001, type_code='SGN', to_team_id=PIT)],
                               people=_pitchers(950001)), team_ids=[PHI])
    lane = _tx_lane(artifact)
    d = lane['differences'][0]
    assert d['transaction_record_actionable'] is True
    assert d['transaction_effect_scope'] == intraday_reconcile.EFFECT_SCOPE_LEDGER_ONLY
    assert 950001 in _lg(artifact)['transaction_participant_mlb_ids']


def test_missing_sgn_not_public_without_roster(app):
    artifact = _run(_tx_client([_tx('s', 950001, type_code='SGN', to_team_id=PIT)],
                               people=_pitchers(950001)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['public_bullpen_material'] is False
    assert artifact['public_bullpen_change_detected'] is False
    assert artifact['material_change_detected'] is False


def test_missing_sfa_not_public(app):
    artifact = _run(_tx_client([_tx('s', 950002, type_code='SFA', to_team_id=SEA)],
                               people=_pitchers(950002)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['transaction_record_actionable'] is True
    assert d['public_bullpen_material'] is False


def test_missing_asg_not_public(app):
    artifact = _run(_tx_client([_tx('a', 950003, type_code='ASG', to_team_id=ATL)],
                               people=_pitchers(950003)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['public_bullpen_material'] is False
    assert d['may_change_active_mlb_membership'] is False


def test_effect_none_cannot_be_public_alone(app):
    artifact = _run(_tx_client([_tx('s', 950004, type_code='SGN', to_team_id=PHI)],
                               people=_pitchers(950004)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['effect_direction'] == intraday_reconcile.EFFECT_NONE
    assert d['public_bullpen_material'] is False


def test_unknown_transaction_type_fails_closed(app):
    artifact = _run(_tx_client([_tx('x', 950005, type_code='ZZZ', to_team_id=PHI)],
                               people=_pitchers(950005)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['transaction_effect_scope'] == intraday_reconcile.EFFECT_SCOPE_UNKNOWN
    assert d['public_bullpen_material'] is False
    assert d['transaction_record_actionable'] is True


def test_active_affecting_public_with_roster_confirmation(app):
    # Stored inactive pitcher, missing RECALL, roster confirms now active -> public.
    _seed_pitcher(950006, 'Conf Arm', BOS, 'BOS', roster_status=STATUS_OPTIONED, active=False)
    tx = _tx('r', 950006, type_code='RECALL', to_team_id=BOS)
    client = _tx_client([tx],
                        rosters={(BOS, ROSTER_TYPE_ACTIVE): [roster_entry(950006, 'Conf Arm', status=ACTIVE)]},
                        teams=[{'id': BOS, 'name': 'BoSox', 'abbreviation': 'BOS'}])
    artifact = _run(client, team_ids=[BOS])
    d = {r.get('transaction_id'): r for r in _tx_lane(artifact)['differences']}['r']
    assert d['public_bullpen_material'] is True
    assert d['roster_confirmation_status'] == intraday_reconcile.ROSTER_CONFIRM_CHANGE
    assert artifact['material_change_detected'] is True


def test_active_affecting_not_public_without_confirmation(app):
    # Missing RECALL for a pitcher not on any fetched active roster -> unverified.
    artifact = _run(_tx_client([_tx('r', 950007, type_code='RECALL', to_team_id=PHI)],
                               people=_pitchers(950007)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['public_bullpen_material'] is False
    assert d['roster_confirmation_status'] == intraday_reconcile.ROSTER_CONFIRM_UNVERIFIED


def test_two_axes_independent(app):
    artifact = _run(_tx_client([_tx('s', 950008, type_code='SGN', to_team_id=PHI)],
                               people=_pitchers(950008)), team_ids=[PHI])
    d = _tx_lane(artifact)['differences'][0]
    assert d['transaction_record_actionable'] != d['public_bullpen_material']


# ── C10: ledger-only findings never enter the public plan ────────────────────

def _ledger_only_artifact(app_ignored):
    return _run(_tx_client([_tx('s', 950009, type_code='SGN', from_team_id=PIT, to_team_id=AFFILIATE_A)],
                           people=_pitchers(950009)), team_ids=[PHI])


def test_ledger_only_sets_changed_true(app):
    a = _ledger_only_artifact(app)
    assert a['changed'] is True
    assert a['transaction_ledger_change_detected'] is True


def test_ledger_only_not_material(app):
    assert _ledger_only_artifact(app)['material_change_detected'] is False


def test_ledger_only_no_publish(app):
    assert _ledger_only_artifact(app)['would_refresh']['publish_snapshot'] is False


def test_ledger_only_no_warm(app):
    assert _ledger_only_artifact(app)['would_refresh']['warm_tonight'] is False


def test_ledger_only_no_team_recompute(app):
    assert _ledger_only_artifact(app)['would_refresh']['recalculate_team_reads'] == []


def test_ledger_only_not_in_targeted(app):
    a = _ledger_only_artifact(app)
    assert a['would_refresh']['targeted_pitcher_mlb_ids'] == []
    assert 950009 not in a['would_refresh']['targeted_pitcher_mlb_ids']


# ── C4/C6/C7: roster authority + cross-lane dedup ─────────────────────────────

def test_roster_activation_enters_targeted_and_public_team(app):
    _seed_pitcher(951001, 'Act Arm', TB, 'TB', roster_status=STATUS_OPTIONED, active=False)
    client = _tx_client([], rosters={(TB, ROSTER_TYPE_ACTIVE): [roster_entry(951001, 'Act Arm', status=ACTIVE)]},
                        teams=[{'id': TB, 'name': 'Rays', 'abbreviation': 'TB'}])
    artifact = _run(client, team_ids=[TB])
    assert 951001 in artifact['would_refresh']['targeted_pitcher_mlb_ids']
    assert TB in artifact['would_refresh']['affected_team_ids']


def test_roster_and_transaction_overlap_deduplicated(app):
    # Same pitcher activated (roster) AND missing recall (transaction, public):
    # appears once in targeted workload and the team once in recompute.
    _seed_pitcher(951002, 'Dup Arm', BOS, 'BOS', roster_status=STATUS_OPTIONED, active=False)
    tx = _tx('r', 951002, type_code='RECALL', to_team_id=BOS)
    client = _tx_client([tx],
                        rosters={(BOS, ROSTER_TYPE_ACTIVE): [roster_entry(951002, 'Dup Arm', status=ACTIVE)]},
                        teams=[{'id': BOS, 'name': 'BoSox', 'abbreviation': 'BOS'}])
    wr = _run(client, team_ids=[BOS])['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'].count(951002) == 1
    assert wr['affected_team_ids'].count(BOS) == 1


# ── C5: split ledger plan ────────────────────────────────────────────────────

def test_ledger_plan_retains_event_keys_and_teams(app):
    tx = _tx('s', 951003, type_code='SGN', from_team_id=BAL, to_team_id=AFFILIATE_A)
    ledger = _lg(_run(_tx_client([tx], people=_pitchers(951003)), team_ids=[PHI]))
    assert 'statsapi:s' in ledger['ingest_transaction_event_keys']
    assert BAL in ledger['transaction_related_mlb_team_ids']
    assert AFFILIATE_A in ledger['transaction_related_non_mlb_team_ids']
    assert ledger['record_actionable_count'] == 1


def test_stored_conflict_goes_to_reconcile_event_keys(app):
    _seed_stored_transaction(_tx('sc', 951004, type_code='RECALL', to_team_id=PHI))
    ledger = _lg(_run(_tx_client([_tx('sc', 951004, type_code='RECALL', to_team_id=NYM)],
                                 people=_pitchers(951004)), team_ids=[PHI]))
    assert 'statsapi:sc' in ledger['reconcile_transaction_event_keys']


# ── C9: role-lookup gating + metrics ─────────────────────────────────────────

def test_role_lookup_reused_from_roster_evidence(app):
    # A stored pitcher on the active roster is resolved from stored/roster
    # evidence — no /people lookup is spent.
    _seed_pitcher(951005, 'Roster Arm', BOS, 'BOS', roster_status=STATUS_ACTIVE, active=True)
    tx = _tx('s', 951005, type_code='SGN', to_team_id=BOS)
    client = _tx_client([tx],
                        rosters={(BOS, ROSTER_TYPE_ACTIVE): [roster_entry(951005, 'Roster Arm', status=ACTIVE)]},
                        teams=[{'id': BOS, 'name': 'BoSox', 'abbreviation': 'BOS'}])
    artifact = _run(client, team_ids=[BOS])
    rv = _tx_lane(artifact)['role_verification']
    assert client.calls.get('get_player_info', 0) == 0
    assert rv['role_lookups_used'] == 0
    assert rv['role_lookups_avoided'] >= 1


def test_role_lookup_performed_when_needed(app):
    client = _tx_client([_tx('s', 951006, type_code='SGN', to_team_id=PHI)], people=_pitchers(951006))
    artifact = _run(client, team_ids=[PHI])
    rv = _tx_lane(artifact)['role_verification']
    assert rv['role_lookups_used'] == 1
    assert rv['role_lookup_candidates'] >= 1


def test_role_lookup_metrics_accurate(app):
    # Two unstored candidates -> two lookups; one stored -> avoided.
    _seed_pitcher(951007, 'Stored', PHI, 'PHI', roster_status=STATUS_ACTIVE, active=True)
    source = [
        _tx('a', 951007, type_code='SGN', to_team_id=PHI),   # stored -> avoided
        _tx('b', 951008, type_code='SGN', to_team_id=PHI),   # lookup
        _tx('c', 951009, type_code='SGN', to_team_id=PHI),   # lookup
    ]
    client = _tx_client(source, people=_pitchers(951008, 951009))
    rv = _tx_lane(_run(client, team_ids=[PHI]))['role_verification']
    assert rv['role_lookups_used'] == 2
    assert rv['role_lookups_avoided'] >= 1
    assert rv['role_lookup_candidates'] == 3


# ── C12: Production Observation #3 regression fixture ─────────────────────────

@pytest.fixture
def observation_three(app):
    """Compact fixture mirroring Observation #3: four real roster-driven current
    bullpen changes (two newly-discovered, two activations) plus a spread of
    transaction-ledger records (org signings, assignments, an MLB-org signing,
    an affiliate destination, a non-pitcher, an unresolved role, a benign detail
    mismatch, and a reflected compound event)."""
    _seed_pitcher(669438, 'Mason Englert', TB, 'TB', roster_status=STATUS_OPTIONED, active=False)
    _seed_pitcher(687941, 'Alec Gamboa', BOS, 'BOS', roster_status=STATUS_OPTIONED, active=False)
    dmp = _seed_pitcher(950110, 'Detail Arm', PHI, 'PHI', roster_status=STATUS_OPTIONED, active=False)
    _seed_snapshot(dmp, PHI, SIGNAL_DATE, STATUS_ACTIVE)
    dm_opt = _tx('dm-opt', 950110, type_code=OPT, to_team_id=AFFILIATE_B)
    _seed_stored_transaction(dm_opt)
    c_reflected = _compound_pair('cref', 950120, 950121)
    _seed_stored_transaction(c_reflected[0])

    transactions = [
        _tx('sgn1', 950101, type_code='SGN', from_team_id=PIT, to_team_id=AFFILIATE_A),  # ledger pitcher
        _tx('sfa1', 950102, type_code='SFA', from_team_id=SEA, to_team_id=SEA),          # ledger pitcher
        _tx('asg-eng', 669438, type_code='ASG', to_team_id=TB),                          # ledger (stored, overlaps roster)
        _tx('rec-gam', 687941, type_code='RECALL', to_team_id=BOS),                      # active-affecting, overlaps roster
        _tx('np1', 950103, type_code='SGN', from_team_id=ATL, to_team_id=AFFILIATE_C),   # non-pitcher
        _tx('unr1', 950104, type_code='SGN', from_team_id=WSH, to_team_id=WSH),          # unresolved role
        _tx('mlborg', 950105, type_code='SGN', from_team_id=BAL, to_team_id=DET),        # ledger MLB org
        dm_opt,
    ] + c_reflected
    rosters = {
        (TB, ROSTER_TYPE_ACTIVE): [roster_entry(669438, 'Mason Englert', status=ACTIVE)],
        (BOS, ROSTER_TYPE_ACTIVE): [roster_entry(687941, 'Alec Gamboa', status=ACTIVE)],
        (TOR, ROSTER_TYPE_ACTIVE): [roster_entry(669310, 'CJ Van Eyk', status=ACTIVE)],
        (ATH, ROSTER_TYPE_ACTIVE): [roster_entry(814305, 'Yunior Tur', status=ACTIVE)],
        (PHI, ROSTER_TYPE_ACTIVE): [],
    }
    teams = [{'id': t, 'name': f'Team{t}', 'abbreviation': f'T{t}'}
             for t in (TB, BOS, TOR, ATH, PHI)]
    people = {**_pitchers(950101, 950102, 950105), **_non_pitchers(950103)}
    return _tx_client(transactions, rosters=rosters, teams=teams, people=people)


def _obs3_run(observation_three):
    return _run(observation_three, team_ids=[TB, BOS, TOR, ATH, PHI])


def test_observation_three_public_targeted_only_roster_four(observation_three):
    wr = _obs3_run(observation_three)['would_refresh']
    # Public targeted workload contains ONLY the four roster-driven players.
    assert sorted(wr['targeted_pitcher_mlb_ids']) == [669310, 669438, 687941, 814305]


def test_observation_three_public_teams_only_roster_four(observation_three):
    wr = _obs3_run(observation_three)['would_refresh']
    # Public affected teams contain ONLY the four roster clubs (111/133/139/141).
    assert sorted(wr['affected_team_ids']) == [BOS, ATH, TB, TOR]  # 111, 133, 139, 141
    assert sorted(wr['recalculate_team_reads']) == [BOS, ATH, TB, TOR]


def test_observation_three_ledger_orgs_not_public(observation_three):
    artifact = _obs3_run(observation_three)
    ledger = _lg(artifact)
    public_teams = set(artifact['would_refresh']['affected_team_ids'])
    # Transaction-ledger MLB organizations stay in the ledger plan, never public.
    for org in (PIT, SEA, WSH, BAL, DET, ATL):
        assert org in ledger['transaction_related_mlb_team_ids'] or org not in public_teams
    assert PIT not in public_teams and BAL not in public_teams and DET not in public_teams
    # Affiliate ids evidence-only.
    for aff in (AFFILIATE_A, AFFILIATE_B, AFFILIATE_C):
        assert aff not in public_teams
        assert aff in artifact['summary']['non_mlb_team_ids_observed']


def test_observation_three_ledger_participants_exclude_non_public(observation_three):
    ledger = _lg(_obs3_run(observation_three))
    participants = set(ledger['transaction_participant_mlb_ids'])
    # Proven-pitcher ledger records are participants.
    assert {950101, 950102}.issubset(participants)
    # Non-pitcher (950103) and unresolved (950104) are never ledger participants.
    assert 950103 not in participants and 950104 not in participants


def test_observation_three_honest_change_and_material(observation_three):
    artifact = _obs3_run(observation_three)
    summary = artifact['summary']
    assert artifact['changed'] is True
    assert artifact['public_bullpen_change_detected'] is True     # four roster changes
    assert artifact['transaction_ledger_change_detected'] is True  # missing records
    assert artifact['material_change_detected'] is True            # roster changes are material
    assert summary['transaction_ledger_only_findings'] >= 1
    assert summary['public_roster_change_count'] >= 4


def test_observation_three_newly_discovered_names(observation_three):
    diffs = _lane1_by_id(_obs3_run(observation_three))
    assert diffs[669310]['player_name'] == 'CJ Van Eyk'
    assert diffs[814305]['player_name'] == 'Yunior Tur'


# ── C8: Production Observation #4 regression fixture (summary contract) ────────

@pytest.fixture
def observation_four(app):
    """Compact fixture mirroring Production Observation #4: four real
    roster-driven current public bullpen changes (two stored activations, two
    source-only newly-discovered actives) plus 24 transaction-record-actionable
    ledger findings (SGN / SFA / ASG / CU, none public-material), two of which
    overlap roster-proven players, alongside benign inventory (three
    transaction_detail_mismatch cases, informational non-pitcher records, a
    reflected compound event, and non-MLB affiliate evidence). The reconciliation
    and impact plan are the 1.3.0 behavior; only the summary counts are exercised.
    """
    # Two STORED pitchers activated (optioned -> active on the same club).
    _seed_pitcher(669438, 'Mason Englert', TB, 'TB', roster_status=STATUS_OPTIONED, active=False)
    _seed_pitcher(687941, 'Alec Gamboa', BOS, 'BOS', roster_status=STATUS_OPTIONED, active=False)
    # Three benign transaction_detail_mismatch cases, stored active on PHI.
    se = [
        _seed_status_effect_case(990001, 'DM One', 'dm1'),
        _seed_status_effect_case(990002, 'DM Two', 'dm2'),
        _seed_status_effect_case(990003, 'DM Three', 'dm3'),
    ]
    # One reflected compound event (one component already stored) — benign.
    c_reflected = _compound_pair('cref4', 980001, 980002)
    _seed_stored_transaction(c_reflected[0])

    # 24 transaction-record-actionable ledger findings; NONE public-material
    # because every type is ledger-only (SGN/SFA/ASG) or unknown scope (CU). The
    # first two overlap roster-proven players (669438 / 687941).
    ledger = [
        _tx('asg-eng', 669438, type_code='ASG', to_team_id=TB),
        _tx('asg-gam', 687941, type_code='ASG', to_team_id=BOS),
    ]
    ledger += [_tx(f'sgn{i}', 960000 + i, type_code='SGN', from_team_id=PIT, to_team_id=AFFILIATE_A)
               for i in range(1, 7)]                                   # 960001..960006
    ledger += [_tx(f'sfa{i}', 960006 + i, type_code='SFA', from_team_id=SEA, to_team_id=SEA)
               for i in range(1, 7)]                                   # 960007..960012
    ledger += [_tx(f'asg{i}', 960012 + i, type_code='ASG', from_team_id=BAL, to_team_id=DET)
               for i in range(1, 7)]                                   # 960013..960018
    ledger += [_tx(f'cu{i}', 960018 + i, type_code='CU', from_team_id=WSH, to_team_id=ATL)
               for i in range(1, 5)]                                   # 960019..960022
    # Informational non-pitcher records (never serialized, never public).
    non_pitchers = [_tx(f'np{i}', 970000 + i, type_code='SGN', to_team_id=AFFILIATE_C)
                    for i in range(1, 19)]                             # 18 records

    transactions = ledger + non_pitchers + se + c_reflected
    rosters = {
        (TB, ROSTER_TYPE_ACTIVE): [roster_entry(669438, 'Mason Englert', status=ACTIVE)],
        (BOS, ROSTER_TYPE_ACTIVE): [roster_entry(687941, 'Alec Gamboa', status=ACTIVE)],
        (TOR, ROSTER_TYPE_ACTIVE): [roster_entry(669310, 'CJ Van Eyk', status=ACTIVE)],
        (ATH, ROSTER_TYPE_ACTIVE): [roster_entry(814305, 'Yunior Tur', status=ACTIVE)],
        # PHI still carries the three detail-mismatch pitchers, so lane 1 reports
        # no roster change for them and PHI never becomes a public team.
        (PHI, ROSTER_TYPE_ACTIVE): [
            roster_entry(990001, 'DM One', status=ACTIVE),
            roster_entry(990002, 'DM Two', status=ACTIVE),
            roster_entry(990003, 'DM Three', status=ACTIVE),
        ],
    }
    teams = [{'id': t, 'name': f'Team{t}', 'abbreviation': f'T{t}'}
             for t in (TB, BOS, TOR, ATH, PHI)]
    people = {**_pitchers(*range(960001, 960023)), **_non_pitchers(*range(970001, 970019))}
    return _tx_client(transactions, rosters=rosters, teams=teams, people=people)


def _obs4_run(observation_four):
    return _run(observation_four, team_ids=[TB, BOS, TOR, ATH, PHI])


# The exact controlled Observation #4 canonical summary values (test items 1-8).
OBS4_EXPECTED = {
    'total_meaningful_findings': 28,
    'total_actionable_findings': 28,
    'transaction_record_actionable_count': 24,
    'transaction_ledger_only_findings': 24,
    'public_roster_change_count': 4,
    'transaction_public_bullpen_material_count': 0,
    'schedule_public_change_count': 0,
    'public_bullpen_change_count': 4,
    'review_required_findings': 0,
    'unresolved_findings': 0,
}


def test_observation_four_canonical_summary_values(observation_four):
    summary = _obs4_run(observation_four)['summary']
    for key, expected in OBS4_EXPECTED.items():
        assert summary[key] == expected, (key, summary[key], expected)


def test_observation_four_public_bullpen_change_count_is_four_not_28(observation_four):
    # The whole point of the correction: 28 meaningful/actionable findings but only
    # FOUR are current public bullpen changes. No summary field reports 28 as a
    # public bullpen change.
    summary = _obs4_run(observation_four)['summary']
    assert summary['public_bullpen_change_count'] == 4
    assert summary['total_actionable_findings'] == 28
    assert 28 not in (summary['public_bullpen_change_count'],
                      summary['public_roster_change_count'],
                      summary['transaction_public_bullpen_material_count'])


def test_observation_four_change_and_material_flags(observation_four):
    artifact = _obs4_run(observation_four)
    assert artifact['changed'] is True
    assert artifact['public_bullpen_change_detected'] is True
    assert artifact['transaction_ledger_change_detected'] is True
    assert artifact['material_change_detected'] is True


def test_observation_four_impact_plan_unchanged(observation_four):
    # Correction 5: the correct 1.3.0 impact plan must be byte-for-byte preserved.
    wr = _obs4_run(observation_four)['would_refresh']
    pub = wr['public_bullpen_state']
    assert sorted(wr['targeted_pitcher_mlb_ids']) == [669310, 669438, 687941, 814305]
    assert sorted(wr['affected_team_ids']) == [BOS, ATH, TB, TOR]  # 111, 133, 139, 141
    assert sorted(pub['targeted_pitcher_mlb_ids']) == [669310, 669438, 687941, 814305]
    assert sorted(pub['affected_team_ids']) == [BOS, ATH, TB, TOR]
    assert pub['publish_snapshot'] is True
    assert pub['warm_tonight'] is True
    assert wr['roster_statuses'] is True
    assert wr['transactions'] is False  # no public membership mismatch


def test_observation_four_transaction_ledger_unchanged(observation_four):
    ledger = _lg(_obs4_run(observation_four))
    assert ledger['record_actionable_count'] == 24
    # The 24 missing records surface as ingest event keys; overlaps included.
    assert len(ledger['ingest_transaction_event_keys']) == 24
    keys = ledger['ingest_transaction_event_keys']
    assert any(k.endswith('asg-eng') for k in keys)
    assert any(k.endswith('asg-gam') for k in keys)


def test_observation_four_roster_transaction_overlap_counts_once(observation_four):
    # 669438 / 687941 each have a roster activation AND a ledger ASG record. The
    # public change count is 4 (the four roster players), never inflated by the
    # overlapping ledger records.
    summary = _obs4_run(observation_four)['summary']
    assert summary['public_bullpen_change_count'] == 4
    assert summary['public_roster_change_count'] == 4
    assert summary['transaction_record_actionable_count'] == 24


def test_observation_four_ledger_only_findings_not_public(observation_four):
    artifact = _obs4_run(observation_four)
    public_teams = set(artifact['would_refresh']['affected_team_ids'])
    # Ledger-only organizations and affiliates never become public teams.
    for org in (PIT, SEA, BAL, DET, WSH, ATL):
        assert org not in public_teams
    for aff in (AFFILIATE_A, AFFILIATE_C):
        assert aff not in public_teams


def test_observation_four_legacy_fields_removed(observation_four):
    # Correction 2: the ambiguous legacy names are gone from the contract.
    summary = _obs4_run(observation_four)['summary']
    for legacy in ('actionable_bullpen_differences', 'actionable_differences',
                   'public_bullpen_material_count', 'public_roster_changes',
                   'total_differences', 'public_membership_mismatches'):
        assert legacy not in summary, legacy


def test_observation_four_deterministic(observation_four):
    first = _obs4_run(observation_four)['summary']
    second = _run(observation_four, team_ids=[TB, BOS, TOR, ATH, PHI])['summary']
    assert first == second


def test_observation_four_role_metrics_unchanged(observation_four):
    # Correction 6: summary derivation does not alter role-lookup behavior.
    artifact = _obs4_run(observation_four)
    summary = artifact['summary']
    role = artifact['lanes'][intraday_reconcile.LANE_TRANSACTIONS].get('role_verification') or {}
    assert summary['role_lookups_used'] == role.get('role_lookups_used', 0)
    assert summary['role_lookups_avoided'] == role.get('role_lookups_avoided', 0)
    assert summary['role_lookups_used'] <= intraday_reconcile.DEFAULT_MAX_ROLE_LOOKUPS


def test_observation_four_summary_invariants_hold(observation_four):
    artifact = _obs4_run(observation_four)
    impact = {
        'would_refresh': artifact['would_refresh'],
        'public_bullpen_change_detected': artifact['public_bullpen_change_detected'],
        'transaction_ledger_change_detected': artifact['transaction_ledger_change_detected'],
        'material_change_detected': artifact['material_change_detected'],
    }
    assert intraday_reconcile._summary_contract_invariants(artifact['summary'], impact) == []


# ── Production Observation #5: targeted-workload authority (contract v1.4.1) ──
#
# The impact plan must derive targeted recent-work acquisition EXCLUSIVELY from the
# roster lane's governed targeted_recent_work_* output. A public-material
# transaction for a roster-DEPARTING pitcher (effect=leave,
# targeted_recent_work_required=false) must never re-enter the targeted workload
# lists — the Observation #5 defect (Jared Koenig).

_LANE_R = intraday_reconcile.LANE_ROSTER_ASSIGNMENT
_LANE_T = intraday_reconcile.LANE_TRANSACTIONS
_LANE_S = intraday_reconcile.LANE_SCHEDULE_FINALITY
_ACT = intraday_reconcile.SEVERITY_ACTIONABLE
_REV = intraday_reconcile.SEVERITY_REVIEW


def _o5_roster(*, targeted_ids=(), targeted_mlb=(), affected_mlb=(), affected_teams=(),
               roster_status_diffs=0, team_assignment_diffs=0, differences=()):
    return {
        'checked': {
            'roster_status_differences': roster_status_diffs,
            'team_assignment_differences': team_assignment_diffs,
        },
        'affected_team_ids': list(affected_teams),
        'affected_pitcher_ids': [],
        'affected_pitcher_mlb_ids': list(affected_mlb),
        'targeted_recent_work_pitcher_ids': list(targeted_ids),
        'targeted_recent_work_mlb_ids': list(targeted_mlb),
        'differences': list(differences),
    }


def _o5_tx(*, record_actionable=0, public_material=0, affected_teams=(), affected_mlb=(),
           ledger=None, differences=()):
    return {
        'checked': {
            'transaction_record_actionable': record_actionable,
            'public_bullpen_material': public_material,
        },
        'affected_team_ids': list(affected_teams),
        'affected_pitcher_ids': [],
        'affected_pitcher_mlb_ids': list(affected_mlb),
        'transaction_ledger': ledger or {
            'ingest_transaction_event_keys': [],
            'reconcile_transaction_event_keys': [],
            'transaction_participant_mlb_ids': [],
            'transaction_related_mlb_team_ids': [],
            'transaction_related_non_mlb_team_ids': [],
            'record_actionable_count': record_actionable,
        },
        'differences': list(differences),
    }


def _o5_sched(*, completed_game_pks=(), differences=()):
    return {'completed_game_pks': list(completed_game_pks), 'differences': list(differences)}


def _o5_plan(roster, tx, sched):
    return intraday_reconcile.build_impact_plan(roster, tx, sched)


def _o5_summary(roster, tx, sched):
    plan = intraday_reconcile.build_impact_plan(roster, tx, sched)
    counts = intraday_reconcile._derive_summary_counts(
        {_LANE_R: roster, _LANE_T: tx, _LANE_S: sched}, plan)
    return counts, plan


def _o5_diff(severity, **extra):
    d = {'severity': severity}
    d.update(extra)
    return d


# ── Focused targeted-workload authority invariants (Corrections 1/5/6) ────────

def test_targeted_stored_ids_only_from_roster():
    # Item 1 + 3: transaction affected stored ids never expand targeted stored ids.
    roster = _o5_roster(targeted_ids=[10, 20], targeted_mlb=[1000, 2000])
    tx = _o5_tx(public_material=1, affected_mlb=[9999])
    tx['affected_pitcher_ids'] = [999]
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_logs'] == [10, 20]
    assert 999 not in wr['targeted_pitcher_logs']


def test_targeted_mlb_ids_only_from_roster():
    # Item 2 + 4: transaction affected mlb ids never expand targeted mlb ids.
    roster = _o5_roster(targeted_ids=[10], targeted_mlb=[1000])
    tx = _o5_tx(public_material=1, affected_mlb=[9999])
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'] == [1000]
    assert 9999 not in wr['targeted_pitcher_mlb_ids']


def test_public_material_leaving_pitcher_not_targeted():
    # Item 5: a public-material transaction for a roster-departing pitcher (not in
    # the roster targeted list) must not target workload.
    roster = _o5_roster(targeted_ids=[10], targeted_mlb=[1000],
                        affected_mlb=[1000, 657649], roster_status_diffs=2)
    tx = _o5_tx(record_actionable=1, public_material=1, affected_mlb=[657649])
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert 657649 not in wr['targeted_pitcher_mlb_ids']
    assert wr['targeted_pitcher_mlb_ids'] == [1000]


def test_ledger_only_pitcher_not_targeted():
    # Item 6: a transaction-ledger-only pitcher (no public-material, not roster
    # targeted) never targets workload.
    roster = _o5_roster(targeted_ids=[10], targeted_mlb=[1000])
    tx = _o5_tx(record_actionable=5, public_material=0, affected_mlb=[])
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'] == [1000]


def test_transaction_only_public_material_pitcher_not_targeted():
    # Item 7: even a transaction-only affected mlb id marked public-material never
    # enters the targeted plan; only the roster lane authorizes targeting.
    roster = _o5_roster(targeted_ids=[], targeted_mlb=[], affected_mlb=[555],
                        roster_status_diffs=1)
    tx = _o5_tx(public_material=1, affected_mlb=[555])
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'] == []
    assert wr['targeted_pitcher_logs'] == []


def test_roster_entering_pitcher_remains_targeted():
    # Item 8: a roster-entering pitcher with targeted_recent_work_required=true
    # remains targeted.
    roster = _o5_roster(targeted_ids=[392], targeted_mlb=[676742], roster_status_diffs=1)
    wr = _o5_plan(roster, _o5_tx(), _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_logs'] == [392]
    assert wr['targeted_pitcher_mlb_ids'] == [676742]


def test_roster_transaction_overlap_targets_once():
    # Item 9 + Correction 5 (Cam Sanders): a roster/transaction overlap for an
    # entering pitcher is targeted exactly once, authorized by the roster lane.
    roster = _o5_roster(targeted_ids=[392], targeted_mlb=[676742],
                        affected_mlb=[676742], roster_status_diffs=1)
    tx = _o5_tx(public_material=1, affected_mlb=[676742])
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'].count(676742) == 1
    assert wr['targeted_pitcher_logs'].count(392) == 1


def test_targeted_flat_and_nested_lists_match():
    # Correction 4: the flat compatibility fields and nested public-state fields
    # never diverge.
    roster = _o5_roster(targeted_ids=[10, 20], targeted_mlb=[1000, 2000],
                        roster_status_diffs=2)
    tx = _o5_tx(public_material=1, affected_mlb=[9999])
    plan = _o5_plan(roster, tx, _o5_sched())
    wr = plan['would_refresh']
    pub = wr['public_bullpen_state']
    assert wr['targeted_pitcher_logs'] == pub['targeted_pitcher_logs']
    assert wr['targeted_pitcher_mlb_ids'] == pub['targeted_pitcher_mlb_ids']
    assert 9999 not in pub['targeted_pitcher_mlb_ids']


# ── Exact Production Observation #5 reconstruction (Corrections 2/3/4/8) ──────

OBS5_TARGETED_STORED = [77, 242, 243, 392, 520]
OBS5_TARGETED_MLB = [621121, 656240, 669310, 669438, 676742, 678906, 687941, 814305]
OBS5_PUBLIC_TEAMS = [110, 111, 114, 117, 133, 134, 138, 139, 141, 158]
KOENIG_STORED, KOENIG_MLB, KOENIG_TEAM = 744, 657649, 158
SANDERS_STORED, SANDERS_MLB = 392, 676742
OBS5_EVENT_KEY = 'statsapi:928241'
OBS5_LEDGER_RECORD_COUNT = 35
OBS5_SUMMARY = {
    'total_meaningful_findings': 91,
    'total_actionable_findings': 47,
    'review_required_findings': 44,
    'unresolved_findings': 44,
    'transaction_record_actionable_count': 35,
    'transaction_ledger_only_findings': 34,
    'transaction_public_bullpen_material_count': 2,
    'public_roster_change_count': 10,
    'schedule_public_change_count': 2,
    'public_bullpen_change_count': 10,
}


def _obs5_lanes():
    """Reconstruct the exact Production Observation #5 aggregate as three lane
    results, with the real production IDs. The roster lane authorizes eight
    entering targeted pitchers (five stored, three source-only) and reports ten
    public roster changes; Jared Koenig is a roster-DEPARTING pitcher whose OPT is
    public-material and record-actionable, so he appears in transaction evidence,
    the ledger plan, and the summary dedup — but never in the targeted lists."""
    # Roster lane: 10 actionable current roster changes (feeds the tallies); the
    # governed targeted output authorizes only the 8 entering pitchers. The
    # affected-mlb set (used only by the summary dedup) includes departing Koenig.
    roster_diffs = [_o5_diff(_ACT, change_type='roster_change') for _ in range(10)]
    roster = _o5_roster(
        targeted_ids=OBS5_TARGETED_STORED,
        targeted_mlb=OBS5_TARGETED_MLB,
        affected_mlb=sorted(set(OBS5_TARGETED_MLB) | {KOENIG_MLB, SANDERS_MLB}),
        affected_teams=OBS5_PUBLIC_TEAMS,
        roster_status_diffs=10,
        team_assignment_diffs=0,
        differences=roster_diffs,
    )

    # Transaction lane: 35 record-actionable ledger findings (34 ledger-only + the
    # Koenig OPT which is BOTH record-actionable and public-material), 2 public-
    # material total (Koenig + Sanders), and 44 review-required role-unresolved
    # findings (role budget exhausted, fail-closed). 34+1+44 = 79 differences.
    ledger_only = [
        _o5_diff(_ACT, transaction_record_actionable=True, public_bullpen_material=False,
                 classification='transaction_record_actionable')
        for _ in range(34)
    ]
    koenig = [_o5_diff(_ACT, transaction_record_actionable=True, public_bullpen_material=True,
                       classification=intraday_reconcile.TX_PUBLIC_BULLPEN_EFFECT_UNREFLECTED,
                       mlb_player_id=KOENIG_MLB, stored_pitcher_id=KOENIG_STORED)]
    role_unresolved = [
        _o5_diff(_REV, classification=intraday_reconcile.TX_BULLPEN_RELEVANCE_UNRESOLVED)
        for _ in range(44)
    ]
    event_keys = [OBS5_EVENT_KEY] + [f'statsapi:{900000 + i}' for i in range(34)]
    tx = _o5_tx(
        record_actionable=OBS5_LEDGER_RECORD_COUNT,
        public_material=2,
        affected_teams=[KOENIG_TEAM, 111],
        affected_mlb=[KOENIG_MLB, SANDERS_MLB],
        ledger={
            'ingest_transaction_event_keys': event_keys,
            'reconcile_transaction_event_keys': [],
            'transaction_participant_mlb_ids': [KOENIG_MLB, SANDERS_MLB],
            'transaction_related_mlb_team_ids': [KOENIG_TEAM],
            'transaction_related_non_mlb_team_ids': [],
            'record_actionable_count': OBS5_LEDGER_RECORD_COUNT,
        },
        differences=ledger_only + koenig + role_unresolved,
    )

    # Schedule lane: one completed game + two actionable public schedule changes.
    sched = _o5_sched(
        completed_game_pks=[824766],
        differences=[
            _o5_diff(_ACT, affected_team_ids=[139]),
            _o5_diff(_ACT, affected_team_ids=[141]),
        ],
    )
    return roster, tx, sched


def test_observation_five_summary_counts_unchanged():
    # Items 26/27/28: the fix touches only targeted workload; every summary count
    # matches Observation #5 exactly.
    counts, _ = _o5_summary(*_obs5_lanes())
    assert counts == OBS5_SUMMARY


def test_observation_five_summary_invariants_hold():
    roster, tx, sched = _obs5_lanes()
    counts, plan = _o5_summary(roster, tx, sched)
    assert intraday_reconcile._summary_contract_invariants(counts, plan) == []


def test_observation_five_targeted_stored_ids_exact():
    # Item 19 + 21: exact roster-authoritative stored targeted ids; Koenig absent.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    assert wr['targeted_pitcher_logs'] == OBS5_TARGETED_STORED
    assert KOENIG_STORED not in wr['targeted_pitcher_logs']


def test_observation_five_targeted_mlb_ids_exact():
    # Item 20 + 22: exact roster-authoritative mlb targeted ids; Koenig absent.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'] == OBS5_TARGETED_MLB
    assert KOENIG_MLB not in wr['targeted_pitcher_mlb_ids']


def test_observation_five_source_only_entering_in_mlb_targeted():
    # Source-only entering pitchers (no stored id) still appear in the mlb targeted
    # list; stored entering pitchers appear in both lists.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    source_only = set(OBS5_TARGETED_MLB) - {621121, 656240, 669310, 676742, 687941}
    assert source_only.issubset(set(wr['targeted_pitcher_mlb_ids']))
    assert len(wr['targeted_pitcher_logs']) == 5
    assert len(wr['targeted_pitcher_mlb_ids']) == 8


def test_observation_five_sanders_targeted_once():
    # Correction 5: the roster/transaction overlap (Cam Sanders) targets once.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    assert wr['targeted_pitcher_mlb_ids'].count(SANDERS_MLB) == 1
    assert wr['targeted_pitcher_logs'].count(SANDERS_STORED) == 1


def test_observation_five_public_teams_unchanged():
    # Items 12/15/23: public affected teams stay the exact ten, including Koenig's
    # club (158). Team scope is unchanged by the targeted-workload fix.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    assert sorted(wr['affected_team_ids']) == OBS5_PUBLIC_TEAMS
    assert sorted(wr['recalculate_team_reads']) == OBS5_PUBLIC_TEAMS
    assert KOENIG_TEAM in wr['affected_team_ids']


def test_observation_five_public_flags_unchanged():
    # Item 14/16: public flags match Observation #5.
    plan = _o5_plan(*_obs5_lanes())
    wr = plan['would_refresh']
    assert wr['roster_statuses'] is True
    assert wr['team_assignments'] is False
    assert wr['transactions'] is True
    assert wr['publish_snapshot'] is True
    assert wr['warm_tonight'] is True
    assert plan['material_change_detected'] is True
    assert plan['public_bullpen_change_detected'] is True
    assert plan['transaction_ledger_change_detected'] is True


def test_observation_five_completed_game_planning_unchanged():
    # Items 13/17/18: completed-game planning ties Current-Pen ERA and league ERA
    # rank recalculation to the completed game only.
    wr = _o5_plan(*_obs5_lanes())['would_refresh']
    assert wr['completed_game_pks'] == [824766]
    assert wr['recalculate_current_pen_era'] is True
    assert wr['recalculate_league_era_rank'] is True


def test_observation_five_current_pen_era_requires_completed_game():
    # Current-Pen ERA / league ERA rank recalculation is False without a completed
    # game, even with public roster and transaction changes present.
    roster, tx, _ = _obs5_lanes()
    wr = _o5_plan(roster, tx, _o5_sched())['would_refresh']
    assert wr['recalculate_current_pen_era'] is False
    assert wr['recalculate_league_era_rank'] is False
    assert wr['publish_snapshot'] is True  # roster/transaction changes still material


def test_observation_five_transaction_ledger_unchanged():
    # Items 11/16/24/25: Koenig stays in the ledger plan; 35 records and the OPT
    # event key are preserved.
    plan = _o5_plan(*_obs5_lanes())
    ledger = plan['would_refresh']['transaction_ledger']
    assert ledger['record_actionable_count'] == OBS5_LEDGER_RECORD_COUNT
    assert len(ledger['ingest_transaction_event_keys']) == OBS5_LEDGER_RECORD_COUNT
    assert OBS5_EVENT_KEY in ledger['ingest_transaction_event_keys']
    assert KOENIG_MLB in ledger['transaction_participant_mlb_ids']
    assert KOENIG_TEAM in ledger['transaction_related_mlb_team_ids']


def test_observation_five_koenig_public_but_not_targeted():
    # Item 10: Koenig stays public/ledger relevant (public-material count, team,
    # ledger participant) yet is excluded from targeted workload.
    roster, tx, sched = _obs5_lanes()
    counts, plan = _o5_summary(roster, tx, sched)
    wr = plan['would_refresh']
    assert counts['transaction_public_bullpen_material_count'] == 2
    assert counts['public_bullpen_change_count'] == 10
    assert KOENIG_MLB in tx['affected_pitcher_mlb_ids']
    assert KOENIG_MLB not in wr['targeted_pitcher_mlb_ids']
    assert KOENIG_STORED not in wr['targeted_pitcher_logs']


# ── Real-lane enter/leave proof through the full pipeline ────────────────────

def test_observation_five_real_lane_departing_pitcher_not_targeted(app):
    # End-to-end: a stored-active pitcher gone from the active roster with a
    # public-material OPT (roster removal, effect=leave) plus an activated pitcher.
    # The departing pitcher stays public-material but is never targeted; the
    # entering pitcher is targeted exactly once.
    leaver = _seed_pitcher(657649, 'Jared Koenig', PHI, 'PHI',
                           roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(leaver, NYM, SIGNAL_DATE, STATUS_ACTIVE)
    leave_tx = _tx('koenig-opt', 657649, type_code=OPT, to_team_id=AFFILIATE_A)
    _seed_stored_transaction(leave_tx)
    _seed_pitcher(676742, 'Cam Sanders', BOS, 'BOS',
                  roster_status=STATUS_OPTIONED, active=False)
    rosters = {
        (PHI, ROSTER_TYPE_ACTIVE): [],
        (BOS, ROSTER_TYPE_ACTIVE): [roster_entry(676742, 'Cam Sanders', status=ACTIVE)],
    }
    teams = [{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
             {'id': BOS, 'name': 'Red Sox', 'abbreviation': 'BOS'}]
    artifact = _run(_tx_client([leave_tx], rosters=rosters, teams=teams),
                    team_ids=[PHI, BOS])
    wr = artifact['would_refresh']
    tx_lane = _tx_lane(artifact)
    # The OPT is a proven public membership mismatch: it must be public-material.
    assert 657649 in tx_lane['affected_pitcher_mlb_ids']
    assert wr['transactions'] is True
    # The fix: the departing pitcher is NOT targeted; the entering one is, once.
    assert 657649 not in wr['targeted_pitcher_mlb_ids']
    assert wr['targeted_pitcher_mlb_ids'].count(676742) == 1


def test_observation_five_real_lane_departing_pitcher_stays_public(app):
    # The departing pitcher remains in public evidence (his club is a public team)
    # even though he is not targeted for recent-work acquisition.
    leaver = _seed_pitcher(657649, 'Jared Koenig', PHI, 'PHI',
                           roster_status=STATUS_ACTIVE, active=True)
    _seed_snapshot(leaver, NYM, SIGNAL_DATE, STATUS_ACTIVE)
    leave_tx = _tx('koenig-opt', 657649, type_code=OPT, to_team_id=AFFILIATE_A)
    _seed_stored_transaction(leave_tx)
    artifact = _run(_tx_client([leave_tx],
                               rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                               teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}]),
                    team_ids=[PHI])
    wr = artifact['would_refresh']
    assert PHI in wr['affected_team_ids']
    assert wr['publish_snapshot'] is True
    assert 657649 not in wr['targeted_pitcher_mlb_ids']


def test_observation_five_artifact_version_is_1_4_1_and_validates(app):
    # Item 42: a fresh artifact is version 1.4.1 and passes the output-contract
    # validator (capability/mode/check_only/status unchanged).
    from scripts.validate_intraday_artifact import validate_artifact
    import json as _json
    artifact = _run(_tx_client([], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                               teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}]),
                    team_ids=[PHI])
    assert artifact['version'] == '1.4.1'
    assert intraday_reconcile.VERSION == '1.4.1'
    ok, reason = validate_artifact(_json.dumps(artifact))
    assert ok is True, reason


# ── Summary-contract behavior (Corrections 1-4) ──────────────────────────────

def _ledger_only_client(n):
    """n proven-pitcher, not-stored ledger-only signings and an empty PHI roster:
    ledger-actionable findings with zero public bullpen change."""
    txns = [_tx(f'sgn{i}', 940000 + i, type_code='SGN', to_team_id=AFFILIATE_A)
            for i in range(1, n + 1)]
    return _tx_client(txns, rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                      teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
                      people=_pitchers(*range(940001, 940001 + n)))


def test_ledger_only_no_public_change_count_zero(app):
    summary = _run(_ledger_only_client(5), team_ids=[PHI])['summary']
    assert summary['transaction_record_actionable_count'] == 5
    assert summary['public_bullpen_change_count'] == 0
    assert summary['transaction_ledger_only_findings'] == 5


def test_ledger_only_change_detected_but_not_public(app):
    artifact = _run(_ledger_only_client(3), team_ids=[PHI])
    assert artifact['transaction_ledger_change_detected'] is True
    assert artifact['public_bullpen_change_detected'] is False
    assert artifact['would_refresh']['publish_snapshot'] is False
    assert artifact['would_refresh']['warm_tonight'] is False
    assert artifact['would_refresh']['recalculate_team_reads'] == []


def test_public_bullpen_change_detected_matches_count_positive(app):
    # A roster activation -> public_bullpen_change_count > 0 and detected True.
    _seed_pitcher(945001, 'Act', TB, 'TB', roster_status=STATUS_OPTIONED, active=False)
    client = _tx_client([], rosters={(TB, ROSTER_TYPE_ACTIVE): [roster_entry(945001, 'Act', status=ACTIVE)]},
                        teams=[{'id': TB, 'name': 'Rays', 'abbreviation': 'TB'}])
    artifact = _run(client, team_ids=[TB])
    summary = artifact['summary']
    assert summary['public_bullpen_change_count'] >= 1
    assert artifact['public_bullpen_change_detected'] is (summary['public_bullpen_change_count'] > 0)


def test_public_bullpen_change_detected_matches_count_zero(app):
    artifact = _run(_ledger_only_client(2), team_ids=[PHI])
    summary = artifact['summary']
    assert summary['public_bullpen_change_count'] == 0
    assert artifact['public_bullpen_change_detected'] is (summary['public_bullpen_change_count'] > 0)


def test_roster_transaction_public_overlap_counts_once(app):
    # 931003 is officially gone from PHI's active roster (roster removal change) AND
    # its transaction proves the same unreflected public bullpen effect. One player,
    # one public change.
    tx = _seed_membership_case(946001, stored_active=True, snapshot_team=NYM,
                               tx_id='pm', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    summary = _run(client, team_ids=[PHI])['summary']
    assert summary['transaction_public_bullpen_material_count'] >= 1
    assert summary['public_roster_change_count'] >= 1
    # The single player is not counted twice.
    assert summary['public_bullpen_change_count'] == summary['public_roster_change_count']


def test_public_membership_mismatch_single_player_counts_once(app):
    # One player surfaces via BOTH the roster lane (removed from PHI's active
    # roster) and the transaction lane (unreflected public effect). It is one
    # deduplicated public bullpen change, not two.
    tx = _seed_membership_case(947001, stored_active=True, snapshot_team=NYM,
                               tx_id='pm', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    summary = _run(client, team_ids=[PHI])['summary']
    assert summary['transaction_public_bullpen_material_count'] >= 1
    assert summary['public_bullpen_change_count'] == 1


def test_roster_aligned_transaction_not_public_material(app):
    # When the roster still carries the pitcher active, the transaction's implied
    # effect is aligned with current state: not public-material, no public change.
    tx = _seed_membership_case(947002, stored_active=True, snapshot_team=NYM,
                               tx_id='al', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(947002, 'P947002', status=ACTIVE)]},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    summary = _run(client, team_ids=[PHI])['summary']
    assert summary['public_roster_change_count'] == 0
    assert summary['transaction_public_bullpen_material_count'] == 0
    assert summary['public_bullpen_change_count'] == 0


def test_schedule_public_change_counted_under_governed_rule(app):
    # A newly-final game is a governed schedule public change; it feeds
    # schedule_public_change_count but NOT the bullpen-membership change count.
    client = FakeMlbClient(
        rosters={(PHI, ROSTER_TYPE_ACTIVE): []}, transactions=[],
        schedule=[_game(870, PHI, NYM, status_code='F', detailed='Final', abstract='Final')],
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
               {'id': NYM, 'name': 'Mets', 'abbreviation': 'NYM'}],
    )
    artifact = _run(client, team_ids=[PHI])
    summary = artifact['summary']
    assert summary['schedule_public_change_count'] >= 1
    assert summary['public_bullpen_change_count'] == 0
    assert artifact['public_bullpen_change_detected'] is False


def test_review_required_increments_meaningful_not_actionable(app):
    source = [_tx('ro', None, type_code='SIGNED', player_full_name='Prospect X')]
    summary = _run(_tx_client(source), team_ids=[PHI])['summary']
    assert summary['review_required_findings'] >= 1
    assert summary['total_meaningful_findings'] >= summary['total_actionable_findings']
    assert summary['total_meaningful_findings'] == summary['total_actionable_findings'] + summary['review_required_findings']


def test_informational_records_not_in_meaningful_or_actionable(app):
    # A proven non-pitcher signing is informational only: it changes neither total.
    client = _tx_client([_tx('np', 948001, type_code='SGN', to_team_id=AFFILIATE_A)],
                        rosters={(PHI, ROSTER_TYPE_ACTIVE): []},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}],
                        people=_non_pitchers(948001))
    summary = _run(client, team_ids=[PHI])['summary']
    assert summary['non_pitcher_transactions'] == 1
    assert summary['total_meaningful_findings'] == 0
    assert summary['total_actionable_findings'] == 0


def test_transaction_record_actionable_matches_ledger_plan(app):
    artifact = _run(_ledger_only_client(4), team_ids=[PHI])
    assert artifact['summary']['transaction_record_actionable_count'] \
        == artifact['would_refresh']['transaction_ledger']['record_actionable_count']


def test_transaction_ledger_only_never_exceeds_actionable(observation_four):
    summary = _obs4_run(observation_four)['summary']
    assert summary['transaction_ledger_only_findings'] <= summary['transaction_record_actionable_count']


def test_transaction_public_material_matches_serialized(app):
    tx = _seed_membership_case(949001, stored_active=True, snapshot_team=NYM,
                               tx_id='pm', type_code=OPT, to_team_id=AFFILIATE_A)
    client = _tx_client([tx], rosters={(PHI, ROSTER_TYPE_ACTIVE): [roster_entry(949001, 'P949001', status=ACTIVE)]},
                        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'}])
    artifact = _run(client, team_ids=[PHI])
    serialized = sum(1 for d in _tx_lane(artifact)['differences'] if d.get('public_bullpen_material'))
    assert artifact['summary']['transaction_public_bullpen_material_count'] == serialized


def test_public_roster_change_count_matches_roster_findings(observation_four):
    artifact = _obs4_run(observation_four)
    checked = artifact['lanes'][intraday_reconcile.LANE_ROSTER_ASSIGNMENT]['checked']
    expected = checked['roster_status_differences'] + checked['team_assignment_differences']
    assert artifact['summary']['public_roster_change_count'] == expected


def test_schedule_public_change_count_matches_schedule_findings(app):
    client = FakeMlbClient(
        rosters={(PHI, ROSTER_TYPE_ACTIVE): []}, transactions=[],
        schedule=[_game(871, PHI, NYM, status_code='F', detailed='Final', abstract='Final')],
        teams=[{'id': PHI, 'name': 'Phillies', 'abbreviation': 'PHI'},
               {'id': NYM, 'name': 'Mets', 'abbreviation': 'NYM'}],
    )
    artifact = _run(client, team_ids=[PHI])
    sched = artifact['lanes'][intraday_reconcile.LANE_SCHEDULE_FINALITY]['differences']
    expected = sum(1 for d in sched if d.get('severity') == intraday_reconcile.SEVERITY_ACTIONABLE)
    assert artifact['summary']['schedule_public_change_count'] == expected


# Canonical 1.4.x summary count fields and the ambiguous names removed from the
# contract, asserted structurally by the pure (no-database) contract tests below.
_CANONICAL_SUMMARY_KEYS = (
    'total_meaningful_findings', 'total_actionable_findings',
    'review_required_findings', 'unresolved_findings',
    'transaction_record_actionable_count', 'transaction_ledger_only_findings',
    'transaction_public_bullpen_material_count', 'public_roster_change_count',
    'schedule_public_change_count', 'public_bullpen_change_count',
)
_REMOVED_LEGACY_SUMMARY_KEYS = (
    'actionable_bullpen_differences', 'actionable_differences',
    'public_bullpen_material_count', 'public_roster_changes',
    'total_differences', 'public_membership_mismatches',
)


class _StubLockConflict:
    """Minimal stand-in for the writer-lock conflict object consumed by the
    skipped-artifact builder — no Flask app context or database required."""
    reason = sync_metadata.SYNC_WRITER_ALREADY_RUNNING
    message = 'A public sync writer already holds the advisory lock.'

    def to_dict(self):
        return {'reason': self.reason, 'message': self.message}


def _assert_canonical_zero_summary(summary):
    # Every canonical count is present and zero; no ambiguous legacy name remains;
    # no public or ledger count is accidentally populated.
    for key in _CANONICAL_SUMMARY_KEYS:
        assert key in summary, key
        assert summary[key] == 0, (key, summary[key])
    for legacy in _REMOVED_LEGACY_SUMMARY_KEYS:
        assert legacy not in summary, legacy


def _assert_zero_work_contract(artifact, *, status):
    assert artifact['capability'] == 'intraday_reconciliation_audit_v1'
    assert artifact['mode'] == 'intraday'
    assert artifact['phase'] == 1
    assert artifact['check_only'] is True
    assert artifact['audit_only'] is True
    assert artifact['status'] == status
    assert artifact['version'] == intraday_reconcile.VERSION  # 1.4.1
    _assert_canonical_zero_summary(artifact['summary'])


# Pure contract tests: these validate dictionary construction only, so they take
# no app/db fixture and open no Postgres connection (a fixture that ran
# db.create_all() per test accumulated connections and exhausted the CI Postgres
# ceiling). build_bootstrap_failure_artifact, _skipped_artifact, _empty_summary,
# and _summary_contract_invariants need no Flask app context or database.

def test_skipped_and_bootstrap_summaries_use_canonical_names():
    # Bootstrap-failure artifact (pure builder).
    boot = intraday_reconcile.build_bootstrap_failure_artifact(
        source='manual', started_at_iso='2026-07-17T00:00:00Z')
    _assert_zero_work_contract(boot, status='failed')

    # Skipped artifact, built with stub client/conflict — no app context, no DB.
    skipped = intraday_reconcile._skipped_artifact(
        client=FakeMlbClient(),
        source='manual',
        product_date=date(2026, 7, 17),
        lanes=intraday_reconcile.ALL_LANES,
        check_timestamp_iso='2026-07-17T00:00:00Z',
        conflict=_StubLockConflict(),
    )
    _assert_zero_work_contract(skipped, status='skipped')
    # Ledger/public plans are empty and no public work is implied.
    assert skipped['public_bullpen_change_detected'] is False
    assert skipped['transaction_ledger_change_detected'] is False
    assert skipped['would_refresh']['transaction_ledger']['record_actionable_count'] == 0
    assert skipped['would_refresh']['public_bullpen_state']['affected_team_ids'] == []


def test_empty_summary_passes_invariants():
    summary = intraday_reconcile._empty_summary()
    _assert_canonical_zero_summary(summary)
    impact = {'would_refresh': intraday_reconcile._empty_would_refresh(),
              'public_bullpen_change_detected': False,
              'transaction_ledger_change_detected': False}
    assert intraday_reconcile._summary_contract_invariants(summary, impact) == []
