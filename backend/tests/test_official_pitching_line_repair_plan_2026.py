"""Official pitching-line repair PLAN (2026) — read-only planner.

Covers the accepted production baseline and its fail-closed drift guard, the official
population partition, the three permitted action types (and the absence of any delete type),
identity prerequisites counted by unique person rather than dependent appearance, the
position-player safety rules (no defaulted position, no invented current team / roster /
activity), insert and update planning, one normalized update per defective row however many
fields differ, contradictory-population failure, deterministic action ids and ordering,
source / comparison / manifest fingerprint stability and sensitivity, preview bounding that
never touches the manifest, the CLI and dispatch-only workflow, and the read-only guarantee:
the planner never mutates a row and never emits write SQL.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_repair_plan_2026 as planner
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


A, B, C = 100, 200, 300
SEASON = 2026
AS_OF = date(2026, 7, 25)
GDATE = date(2026, 6, 10)
GAME_PK = 9001
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'official_pitching_line_repair_plan_2026.py'
CLI_PATH = REPO_ROOT / 'backend' / 'scripts' / 'run_official_pitching_line_repair_plan_2026.py'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'official_pitching_line_repair_plan.yml'
DECISION_RECORD = (REPO_ROOT / 'docs' / 'decisions'
                   / '2026-07-27-official-pitching-line-repair-plan.md')


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


# ── Local ledger fixtures ─────────────────────────────────────────────────────
def _pitcher(mlb_id, *, current_team=None, name=None):
    existing = db.session.query(Pitcher).filter_by(mlb_id=mlb_id).first()
    if existing:
        return existing
    row = Pitcher(mlb_id=mlb_id, full_name=name or f'P{mlb_id}', active=True,
                  team_id=current_team)
    db.session.add(row)
    db.session.commit()
    return row


def _log(mlb_id, game_pk=GAME_PK, *, team, gs=0, outs=3, r=0, er=0, h=0, bb=0, k=0, hr=0,
         gdate=GDATE, game_type='R', pitcher_row=None):
    row = pitcher_row or _pitcher(mlb_id)
    log = GameLog(
        pitcher_id=row.id, mlb_game_pk=game_pk, game_date=gdate, game_type=game_type,
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        runs_allowed=r, earned_runs=er, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr, appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=team, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    )
    db.session.add(log)
    db.session.commit()
    return log


# ── Official evidence fakes ───────────────────────────────────────────────────
def _ip(outs):
    return f'{outs // 3}.{outs % 3}'


def _pline(mlb_id, *, gs, outs, r=0, er=0, h=0, bb=0, k=0, hr=0, drop=()):
    stats = {'gamesStarted': gs, 'inningsPitched': _ip(outs), 'runs': r, 'earnedRuns': er,
             'hits': h, 'baseOnBalls': bb, 'strikeOuts': k, 'homeRuns': hr}
    for key in drop:
        stats.pop(key, None)
    return (mlb_id, stats)


def _side(team_id, name, lines):
    return {
        'team': {'id': team_id, 'name': name},
        'pitchers': [mlb_id for mlb_id, _stats in lines],
        'players': {f'ID{mlb_id}': {'person': {'id': mlb_id, 'fullName': f'P{mlb_id}'},
                                    'stats': {'pitching': stats}}
                    for mlb_id, stats in lines},
    }


def _boxscore(home_lines, away_lines, *, home=A, away=B):
    return {'teams': {'home': _side(home, f'Team{home}', home_lines),
                      'away': _side(away, f'Team{away}', away_lines)}}


def _official_game(game_pk=GAME_PK, home=A, away=B, gdate=GDATE, *, game_type='R',
                   status_code='F'):
    return {'gamePk': game_pk, 'officialDate': gdate.isoformat(), 'gameType': game_type,
            'status': {'statusCode': status_code, 'detailedState': 'Final',
                       'abstractGameState': 'Final'},
            'teams': {'home': {'team': {'id': home}}, 'away': {'team': {'id': away}}}}


def _person(mlb_id, *, name=None, position='P', throws='R'):
    payload = {'id': mlb_id, 'fullName': name or f'P{mlb_id}'}
    if position is not None:
        payload['primaryPosition'] = {'abbreviation': position, 'code': '1', 'name': 'Pitcher'}
    if throws is not None:
        payload['pitchHand'] = {'code': throws}
    return payload


class _FakeMlbClient:
    def __init__(self, games=(), boxscores=None, people=None, raise_windows=(), raise_pks=(),
                 raise_people=()):
        self.games = list(games)
        self.boxscores = dict(boxscores or {})
        self.people = dict(people or {})
        self.raise_windows = set(raise_windows)
        self.raise_pks = set(raise_pks)
        self.raise_people = set(raise_people)
        self.person_calls = []

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        if start_date in self.raise_windows:
            raise RuntimeError('schedule unavailable')
        return [g for g in self.games if start_date <= g['officialDate'] <= end_date]

    def get_game_boxscore(self, game_pk):
        if game_pk in self.raise_pks:
            raise RuntimeError('boxscore unavailable')
        return self.boxscores.get(game_pk)

    def get_player_info(self, player_id):
        self.person_calls.append(player_id)
        if player_id in self.raise_people:
            raise RuntimeError('person unavailable')
        return self.people.get(player_id)


_HOME_LINES = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
               _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
               _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
_AWAY_LINES = [_pline(4, gs=1, outs=15, r=3, er=3, h=6, k=4),
               _pline(5, gs=0, outs=4, r=1, er=1, bb=1),
               _pline(6, gs=0, outs=2, r=0, er=0)]
_ALL_PEOPLE = {i: _person(i) for i in range(1, 12)}


def _client(home_lines=None, away_lines=None, *, games=None, boxscores=None, people=None,
            **kwargs):
    if boxscores is None:
        boxscores = {GAME_PK: _boxscore(home_lines or _HOME_LINES, away_lines or _AWAY_LINES)}
    return _FakeMlbClient(games=games or [_official_game()], boxscores=boxscores,
                          people=people if people is not None else _ALL_PEOPLE, **kwargs)


def _seed_matching_local():
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(3, team=A, gs=0, outs=3, r=0, er=0, k=1)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)


def _plan(**kwargs):
    kwargs.setdefault('client', _client())
    return planner.run_repair_plan(**kwargs)


def _actions(payload, action_type=None):
    return [a for a in payload['repair_manifest']
            if action_type is None or a['action_type'] == action_type]


def _action_for(payload, action_id):
    for action in payload['repair_manifest']:
        if action['action_id'] == action_id:
            return action
    raise AssertionError(f'action {action_id} not in manifest')


def _pin_baseline(monkeypatch, payload_or_dict):
    """Pin ACCEPTED_BASELINE to a small fixture's own observed population."""
    observed = (payload_or_dict['observed_population']
                if isinstance(payload_or_dict, dict) and 'observed_population' in payload_or_dict
                else payload_or_dict)
    pinned = {key: observed[key] for key in planner.ACCEPTED_BASELINE}
    monkeypatch.setattr(planner, 'ACCEPTED_BASELINE', pinned)
    return pinned


# ═══════════════ 1. Accepted production baseline ════════════════════════════
def test_accepted_baseline_pins_the_production_population():
    b = planner.ACCEPTED_BASELINE
    assert b['official_games_selected'] == 1570
    assert b['official_games_fetched'] == 1570
    assert b['official_team_game_sides'] == 3140
    assert b['official_pitching_lines'] == 13301
    assert b['official_starter_lines'] == 3140
    assert b['official_relief_lines'] == 10161
    assert b['local_pitching_lines'] == 12856
    assert b['local_starter_lines'] == 3110
    assert b['local_relief_lines'] == 9746
    assert b['exact_match_count'] == 12697
    assert b['missing_line_count'] == 445
    assert b['defective_matched_line_count'] == 159
    assert b['defect_line_action_count'] == 604
    assert b['missing_lines_dependent_on_identity_creation'] == 342
    assert b['role_corrections_planned'] == 2
    for zero_key in ('appearance_team_mismatch_count', 'extra_local_line_count',
                     'duplicate_local_line_count', 'local_pitcher_identity_missing_count',
                     'official_evidence_unavailable_count'):
        assert b[zero_key] == 0


# ═══════════════ 2-3. Population partition + 604 defect actions ═════════════
def test_accepted_baseline_partitions_exactly():
    b = planner.ACCEPTED_BASELINE
    # 13,301 = 12,697 + 445 + 159
    assert (b['exact_match_count'] + b['missing_line_count']
            + b['defective_matched_line_count']) == b['official_pitching_lines']
    # 3,140 starter + 10,161 relief = 13,301
    assert b['official_starter_lines'] + b['official_relief_lines'] == b['official_pitching_lines']
    # 604 = 445 + 159
    assert b['missing_line_count'] + b['defective_matched_line_count'] == 604
    assert b['defect_line_action_count'] == 604
    # Sides are two per official game.
    assert b['official_team_game_sides'] == b['official_games_fetched'] * 2
    assert b['official_starter_lines'] == b['official_team_game_sides']
    # The 342 identity-dependent appearances are a subset of the 445 missing lines.
    assert b['missing_lines_dependent_on_identity_creation'] < b['missing_line_count']


def test_defect_line_action_count_equals_missing_plus_defective(app):
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=9, r=1, er=1, h=1, k=2)     # stat defect
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)                # line 3 missing
    payload = _plan()
    assert payload['missing_line_count'] == 1
    assert payload['defective_matched_line_count'] == 1
    assert payload['defect_line_action_count'] == 2
    assert len(_actions(payload, planner.ACTION_GAME_LOG_INSERT)) == 1
    assert len(_actions(payload, planner.ACTION_GAME_LOG_UPDATE)) == 1
    assert payload['reconciliations']['defect_line_action_count_equals_defect_lines'] is True


def test_planner_population_matches_the_completeness_diagnostic(app):
    """The planner must never become a second interpretation of the same evidence."""
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=9, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    diagnostic = completeness.run_diagnostic(client=_client())
    plan = _plan()
    for key in ('official_games_selected', 'official_games_fetched', 'official_team_game_sides',
                'official_pitching_lines', 'official_starter_lines', 'official_relief_lines',
                'local_pitching_lines', 'local_starter_lines', 'local_relief_lines',
                'exact_match_count'):
        assert plan[key] == diagnostic[key], key
    assert plan['missing_line_count'] == diagnostic['missing_local_line_count']
    assert plan['defective_matched_line_count'] == (
        diagnostic['official_pitching_lines_compared'] - diagnostic['exact_match_count']
        - diagnostic['missing_local_line_count'])


# ═══════════════ 4-5. Identity prerequisites ════════════════════════════════
def test_missing_identity_with_multiple_dependent_appearances(app):
    # Pitcher 3 has no local Pitcher row and pitched in two official games.
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)
    _log(1, 9002, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(4, 9002, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, 9002, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, 9002, team=B, gs=0, outs=2, r=0, er=0)
    _log(2, 9002, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002, gdate=date(2026, 6, 11))],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES),
                   9002: _boxscore(_HOME_LINES, _AWAY_LINES)},
        people=_ALL_PEOPLE)
    payload = planner.run_repair_plan(client=client)
    identity = _actions(payload, planner.ACTION_IDENTITY_CREATE)
    assert len(identity) == 1                                   # one unique person
    assert payload['unique_identities_requiring_creation'] == 1
    assert payload['missing_lines_dependent_on_identity_creation'] == 2   # two appearances
    assert len(identity[0]['dependent_game_log_action_ids']) == 2
    assert payload['reconciliations'][
        'identity_actions_reconcile_to_dependent_appearances'] is True


def test_unique_identity_count_is_distinct_from_dependent_appearance_count(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    assert payload['unique_identities_requiring_creation'] == 1
    assert payload['missing_lines_dependent_on_identity_creation'] == 1
    assert payload['repair_manifest_action_count'] == (
        payload['unique_identities_requiring_creation']
        + payload['game_log_inserts_planned']
        + payload['existing_game_logs_requiring_updates'])


# ═══════════════ 6-9. Position-player and current-state safety ══════════════
def test_position_player_in_official_pitching_section_keeps_its_position(app):
    # Person 3 is a catcher who pitched. The plan must carry C, never P.
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    people = dict(_ALL_PEOPLE)
    people[3] = _person(3, name='Position Player', position='C', throws='R')
    payload = planner.run_repair_plan(client=_client(people=people))
    identity = _action_for(payload, 'identity:create:3')
    assert identity['proposed_identity_fields']['position'] == 'C'
    assert identity['proposed_identity_fields']['full_name'] == 'Position Player'
    assert identity['safe_to_apply'] is True


def test_position_is_never_defaulted_to_p_without_evidence(app, monkeypatch):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    people = dict(_ALL_PEOPLE)
    people[3] = _person(3, position=None)          # official position evidence absent
    client = _client(people=people)
    # Pin the baseline so the identity blocker, not baseline drift, is the governing status.
    _pin_baseline(monkeypatch, planner.run_repair_plan(client=client))
    payload = planner.run_repair_plan(client=client)
    identity = _action_for(payload, 'identity:create:3')
    assert identity['proposed_identity_fields'] == {}
    assert planner.BLOCK_IDENTITY_POSITION_ABSENT in identity['blocking_reasons']
    assert planner.BLOCK_IDENTITY_MODEL_REQUIREMENT in identity['blocking_reasons']
    assert identity['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_IDENTITY_MODEL
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED


def test_current_team_is_never_assigned_from_a_historical_appearance(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    identity = _action_for(payload, 'identity:create:3')
    for mutable in ('team_id', 'team_name', 'team_abbreviation', 'team_assignment_status'):
        assert mutable not in identity['proposed_identity_fields']
        assert mutable in identity['explicitly_omitted_mutable_fields']


def test_current_roster_and_activity_state_is_not_invented(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    identity = _action_for(payload, 'identity:create:3')
    assert 'active' not in identity['proposed_identity_fields']
    assert 'active' in identity['explicitly_null_fields']
    for roster_field in ('roster_status', 'roster_status_source', 'roster_status_updated_at'):
        assert roster_field in identity['explicitly_omitted_mutable_fields']
    # The model defaults that would invent state are named explicitly.
    assert set(identity['model_default_hazards']) == {'position', 'active'}


# ═══════════════ 10-13. Insert planning ═════════════════════════════════════
def test_missing_line_with_existing_pitcher_identity_needs_no_prerequisite(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()                            # Pitcher row 3 still exists
    payload = _plan()
    assert payload['unique_identities_requiring_creation'] == 0
    assert payload['missing_lines_using_existing_identity'] == 1
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['dependency_action_ids'] == []
    assert insert['local_pitcher_id'] == _pitcher(3).id
    assert insert['safe_to_apply'] is True


def test_missing_official_starter_line_is_planned_as_a_start(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(1).id).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:1:{A}')
    assert insert['official_role'] == planner.ROLE_STARTER
    assert insert['proposed_values']['games_started'] == 1
    assert insert['proposed_values']['innings_pitched_outs'] == 18
    assert insert['proposed_values']['appearance_team_id'] == A


def test_missing_official_relief_line_is_planned_as_relief(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(5).id).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:5:{B}')
    assert insert['official_role'] == planner.ROLE_RELIEF
    assert insert['proposed_values']['games_started'] == 0
    assert insert['proposed_values']['appearance_team_id'] == B
    assert insert['proposed_values']['appearance_team_status'] == 'resolved'
    assert insert['proposed_values']['appearance_team_source'] == 'boxscore_side'


def test_legitimate_official_zero_out_line_is_planned(app):
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=0, r=1, er=1, h=1)]      # legitimate 0-out appearance
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)
    payload = planner.run_repair_plan(client=_client(home_lines=home))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['innings_pitched_outs'] == 0
    assert insert['proposed_values']['innings_pitched'] == 0.0
    assert insert['proposed_values']['runs_allowed'] == 1
    assert insert['safe_to_apply'] is True


# ═══════════════ 14-17. Update planning ═════════════════════════════════════
def test_single_stat_mismatch_produces_one_update(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    updates = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)
    assert len(updates) == 1
    assert updates[0]['changed_fields'] == ['strikeouts']
    assert updates[0]['current_values']['strikeouts'] == 9
    assert updates[0]['proposed_values']['strikeouts'] == 2
    assert updates[0]['field_reason_codes']['strikeouts'] == 'strikeouts_mismatch'


def test_multiple_stat_mismatches_produce_one_update(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9, 'walks': 4, 'hits_allowed': 7}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    updates = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)
    assert len(updates) == 1                                  # one row, one action
    assert updates[0]['changed_fields'] == ['hits_allowed', 'strikeouts', 'walks']
    assert payload['stat_correction_rows_planned'] == 1


def test_role_and_stat_corrections_combine_into_one_update(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'games_started': 1, 'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    updates = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)
    assert len(updates) == 1
    assert updates[0]['changed_fields'] == ['games_started', 'strikeouts']
    assert updates[0]['proposed_values']['games_started'] == 0
    assert updates[0]['field_reason_codes']['games_started'] == (
        'starter_relief_classification_mismatch')
    assert payload['role_corrections_planned'] == 1
    assert payload['stat_correction_rows_planned'] == 1
    assert payload['reconciliations']['role_corrections_subset_of_updates'] is True


def test_exactly_two_role_corrections_under_accepted_baseline_fixtures(app, monkeypatch):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'games_started': 1}, synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(5).id).update(
        {'games_started': 1}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    assert payload['role_corrections_planned'] == 2
    assert len(_actions(payload, planner.ACTION_GAME_LOG_UPDATE)) == 2
    _pin_baseline(monkeypatch, payload)
    repinned = _plan()
    assert repinned['baseline_matches_accepted_diagnostic'] is True
    assert repinned['role_corrections_planned'] == 2
    assert repinned['result'] == planner.RESULT_PASS
    assert repinned['plan_status'] == planner.PLAN_READY
    assert repinned['repair_apply_gate'] == planner.GATE_BLOCKED_PENDING_REVIEW


def test_innings_pitched_stays_consistent_with_outs_on_update(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'innings_pitched_outs': 9, 'innings_pitched': 3.0}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    update = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)[0]
    assert update['proposed_values']['innings_pitched_outs'] == 3
    assert update['proposed_values']['innings_pitched'] == 1.0
    assert 'innings_pitched' in update['changed_fields']


# ═══════════════ 18-20. Authority and evidence rules ════════════════════════
def test_pitcher_team_id_is_never_historical_authority(app):
    _seed_matching_local()
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 2).update(
        {'team_id': C}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    assert payload['repair_manifest'] == []
    assert payload['defect_line_action_count'] == 0
    code = _code_without_prose(SERVICE_PATH)
    assert 'Pitcher.team_id' not in code
    assert 'pitcher.team_id' not in code


def test_identity_is_never_inferred_from_a_name(app):
    # A same-named person under a different MLB id must not satisfy the official line.
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    stray = _pitcher(999, name='P3')
    _log(999, team=A, gs=0, outs=3, r=0, er=0, k=1, pitcher_row=stray)
    payload = _plan()
    assert payload['result'] == planner.RESULT_FAIL
    assert payload['plan_status'] == planner.PLAN_BLOCKED_CONTRADICTORY
    assert 'local_line_not_in_official_pitching_section' in payload['decision_reasons']


def test_missing_official_stat_blocks_the_action_and_is_never_zero(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1, drop=('homeRuns',))]
    payload = planner.run_repair_plan(client=_client(home_lines=home))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert 'home_runs_allowed' not in insert['proposed_values']   # never defaulted to 0
    assert planner.BLOCK_OFFICIAL_STAT_ABSENT in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE


def test_identity_evidence_unavailable_blocks_the_prerequisite(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    payload = planner.run_repair_plan(client=_client(raise_people=(3,)))
    identity = _action_for(payload, 'identity:create:3')
    assert planner.BLOCK_IDENTITY_EVIDENCE_UNAVAILABLE in identity['blocking_reasons']
    assert identity['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE


# ═══════════════ 22. Baseline drift ═════════════════════════════════════════
def test_baseline_drift_is_inconclusive_and_reports_each_difference(app):
    _seed_matching_local()
    payload = _plan()          # small fixture never matches the pinned production baseline
    assert payload['baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_BASELINE_DRIFT
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED
    assert planner.BLOCK_BASELINE_DRIFT in payload['decision_reasons']
    comparison = payload['baseline_comparison']
    assert set(comparison) == set(planner.ACCEPTED_BASELINE)
    entry = comparison['official_pitching_lines']
    assert entry['expected_value'] == 13301
    assert entry['observed_value'] == 6
    assert entry['difference'] == 6 - 13301
    assert entry['matches'] is False


def test_pinned_baseline_match_allows_a_ready_plan(app, monkeypatch):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    _pin_baseline(monkeypatch, _plan())
    payload = _plan()
    assert payload['baseline_matches_accepted_diagnostic'] is True
    assert payload['result'] == planner.RESULT_PASS
    assert payload['plan_status'] == planner.PLAN_READY
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_PENDING_REVIEW
    assert payload['exit_code'] == 0


def test_no_baseline_override_input_exists():
    code = _code_without_prose(SERVICE_PATH)
    for token in ('override', 'force', 'ignore_baseline', 'skip_baseline'):
        assert token not in code, token
    assert 'override' not in _code_without_prose(CLI_PATH)


# ═══════════════ 23-25. Contradictory population ════════════════════════════
def test_extra_local_line_fails(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6, r=2, er=2)
    payload = _plan()
    assert payload['result'] == planner.RESULT_FAIL
    assert payload['exit_code'] == 1
    assert payload['plan_status'] == planner.PLAN_BLOCKED_CONTRADICTORY
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED
    assert 'local_line_not_in_official_pitching_section' in payload['decision_reasons']


def test_appearance_team_mismatch_fails(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'appearance_team_id': B}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    assert payload['result'] == planner.RESULT_FAIL
    assert payload['plan_status'] == planner.PLAN_BLOCKED_CONTRADICTORY
    assert 'appearance_team_mismatch' in payload['decision_reasons']


def test_duplicate_local_line_fails(app, monkeypatch):
    # The unique index makes two rows for one identity unstorable, so the guard is exercised
    # by handing the planner a duplicated local population directly.
    _seed_matching_local()
    real_local_lines = completeness._local_lines

    def _duplicated(session, game_pks):
        rows = real_local_lines(session, game_pks)
        target = [r for r in rows if r.mlb_id == 2]
        return rows + target

    monkeypatch.setattr(completeness, '_local_lines', _duplicated)
    payload = _plan()
    assert payload['result'] == planner.RESULT_FAIL
    assert payload['plan_status'] == planner.PLAN_BLOCKED_CONTRADICTORY
    assert 'local_duplicate_line' in payload['decision_reasons']


# ═══════════════ 26-30. Structural safety ═══════════════════════════════════
def test_no_delete_action_type_exists():
    assert set(planner.ACTION_TYPES) == {
        planner.ACTION_IDENTITY_CREATE,
        planner.ACTION_GAME_LOG_INSERT,
        planner.ACTION_GAME_LOG_UPDATE,
    }
    code = _code_without_prose(SERVICE_PATH)
    for token in ('delete_required', 'game_log_delete', 'identity_delete', 'ACTION_DELETE'):
        assert token not in code, token


def test_no_action_mutates_appearance_team_or_current_team(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9, 'games_started': 1}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    forbidden = {'appearance_team_id', 'appearance_team_status', 'appearance_team_source',
                 'appearance_team_reason', 'pitcher_id', 'mlb_game_pk', 'game_date',
                 'team_id', 'team_name', 'team_abbreviation', 'active', 'roster_status'}
    for action in _actions(payload, planner.ACTION_GAME_LOG_UPDATE):
        assert not (set(action['changed_fields']) & forbidden)
    assert payload['reconciliations']['no_action_changes_appearance_team_id'] is True
    assert payload['reconciliations']['no_action_changes_current_team_fields'] is True
    assert payload['no_action_confirmations']['delete_actions'] == 0
    assert payload['no_action_confirmations']['appearance_team_id_update_actions'] == 0
    assert payload['no_action_confirmations']['current_team_updates'] == 0
    assert payload['no_action_confirmations']['current_role_updates'] == 0
    assert payload['no_action_confirmations']['public_surface_changes'] == 0


def test_no_local_row_or_official_line_is_targeted_twice(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    payload = _plan()
    log_ids = [a['local_game_log_id'] for a in _actions(payload, planner.ACTION_GAME_LOG_UPDATE)]
    assert len(log_ids) == len(set(log_ids))
    line_keys = [(a['mlb_game_pk'], a['official_mlb_person_id'], a['official_team_id'])
                 for a in payload['repair_manifest']
                 if a['action_type'] != planner.ACTION_IDENTITY_CREATE]
    assert len(line_keys) == len(set(line_keys))
    assert payload['reconciliations']['every_local_row_targeted_at_most_once'] is True
    assert payload['reconciliations']['every_defect_line_maps_to_exactly_one_action'] is True


# ═══════════════ Exact defect-line coverage ════════════════════════════════
def _defect_keys(payload):
    return {(a['mlb_game_pk'], a['official_mlb_person_id'], a['official_team_id'])
            for a in payload['repair_manifest']
            if a['action_type'] != planner.ACTION_IDENTITY_CREATE}


def _reconcile(manifest, *, population, insert_actions, update_actions,
               observed_official_line_keys, observed_defect_line_keys,
               planned_defect_line_keys):
    """Call the reconciliation surface directly with a controlled population."""
    return planner._reconciliations(
        population=population, observed=population.as_dict(), manifest=manifest,
        identity_actions=[], insert_actions=insert_actions, update_actions=update_actions,
        baseline_matches=False, duplicate_action_ids=set(), targeted_local_rows=set(),
        observed_official_line_keys=observed_official_line_keys,
        observed_defect_line_keys=observed_defect_line_keys,
        planned_defect_line_keys=planned_defect_line_keys)


def test_exact_matches_never_enter_the_defect_key_population(app):
    _seed_matching_local()                       # six lines, all exact
    payload = _plan()
    recon = payload['reconciliations']
    assert payload['exact_match_count'] == 6
    assert payload['defect_line_action_count'] == 0
    assert _defect_keys(payload) == set()
    assert recon['no_exact_line_maps_to_a_repair_action'] is True
    assert recon['observed_defect_key_count_equals_defect_lines'] is True
    assert recon['every_defect_line_maps_to_exactly_one_action'] is True


def test_missing_and_defective_lines_enter_the_defect_population_exactly_once(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)   # missing
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)                             # defective
    db.session.commit()
    payload = _plan()
    recon = payload['reconciliations']
    assert payload['missing_line_count'] == 1
    assert payload['defective_matched_line_count'] == 1
    assert _defect_keys(payload) == {(GAME_PK, 2, A), (GAME_PK, 3, A)}
    assert recon['observed_defect_line_keys_unique'] is True
    assert recon['planned_defect_line_keys_unique'] is True
    assert recon['observed_defect_keys_equal_planned_defect_keys'] is True
    assert recon['defect_keys_are_a_subset_of_observed_official_lines'] is True


def test_observed_defect_keys_equal_planned_defect_keys_on_the_clean_fixture(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(5).id).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(1).id).update(
        {'earned_runs': 7}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    assert payload['reconciliations']['observed_defect_keys_equal_planned_defect_keys'] is True
    assert payload['reconciliations']['every_defect_line_maps_to_exactly_one_action'] is True
    assert _defect_keys(payload) == {(GAME_PK, 1, A), (GAME_PK, 5, B)}


def test_omitting_one_defect_action_fails_reconciliation_despite_many_official_lines():
    # 500 official lines, 2 defects observed, only 1 planned. The old >= check would pass.
    population = planner._Population(
        official_lines_compared=500, exact_match_count=498,
        missing_line_count=1, defective_matched_line_count=1)
    official_keys = [(9001, i, 100) for i in range(1, 501)]
    observed = [(9001, 1, 100), (9001, 2, 100)]
    planned = [(9001, 1, 100)]                                   # one action omitted
    insert_actions = [{'action_id': 'gamelog:insert:9001:1:100', 'safe_to_apply': True,
                       'dependency_action_ids': [], 'blocking_reasons': []}]
    recon = _reconcile([], population=population, insert_actions=insert_actions,
                       update_actions=[], observed_official_line_keys=official_keys,
                       observed_defect_line_keys=observed, planned_defect_line_keys=planned)
    assert recon['observed_defect_keys_equal_planned_defect_keys'] is False
    assert recon['every_defect_line_maps_to_exactly_one_action'] is False


def test_substituting_a_different_line_fails_even_when_action_counts_match():
    # Same number of actions, wrong line: count-based checks pass, key equality must not.
    population = planner._Population(
        official_lines_compared=500, exact_match_count=498,
        missing_line_count=1, defective_matched_line_count=1)
    official_keys = [(9001, i, 100) for i in range(1, 501)]
    observed = [(9001, 1, 100), (9001, 2, 100)]
    planned = [(9001, 1, 100), (9001, 499, 100)]                 # wrong second line
    actions = [{'action_id': f'gamelog:insert:9001:{pid}:100', 'safe_to_apply': True,
                'dependency_action_ids': [], 'blocking_reasons': []}
               for pid in (1, 499)]
    recon = _reconcile([], population=population, insert_actions=actions,
                       update_actions=[], observed_official_line_keys=official_keys,
                       observed_defect_line_keys=observed, planned_defect_line_keys=planned)
    assert recon['planned_defect_key_count_equals_line_actions'] is True   # counts agree
    assert recon['observed_defect_keys_equal_planned_defect_keys'] is False
    assert recon['every_defect_line_maps_to_exactly_one_action'] is False
    assert recon['no_exact_line_maps_to_a_repair_action'] is False   # 499 was an exact match


def test_duplicate_planned_defect_keys_fail_reconciliation():
    population = planner._Population(
        official_lines_compared=3, exact_match_count=1,
        missing_line_count=1, defective_matched_line_count=1)
    official_keys = [(9001, 1, 100), (9001, 2, 100), (9001, 3, 100)]
    observed = [(9001, 1, 100), (9001, 2, 100)]
    planned = [(9001, 1, 100), (9001, 1, 100)]                   # same line twice
    actions = [{'action_id': 'a', 'safe_to_apply': True, 'dependency_action_ids': [],
                'blocking_reasons': []},
               {'action_id': 'b', 'safe_to_apply': True, 'dependency_action_ids': [],
                'blocking_reasons': []}]
    recon = _reconcile([], population=population, insert_actions=actions,
                       update_actions=[], observed_official_line_keys=official_keys,
                       observed_defect_line_keys=observed, planned_defect_line_keys=planned)
    assert recon['planned_defect_line_keys_unique'] is False
    assert recon['every_defect_line_maps_to_exactly_one_action'] is False


def test_duplicate_official_source_line_is_a_contradiction(app, monkeypatch):
    _seed_matching_local()
    real_sides = completeness._official_sides

    def _duplicated(boxscore, *, game_pk, game_date):
        sides = real_sides(boxscore, game_pk=game_pk, game_date=game_date)
        for side in sides:
            if side.lines:
                side.lines.append(side.lines[-1])       # same official line twice
                side.enumerated_line_count += 1
                break
        return sides

    monkeypatch.setattr(completeness, '_official_sides', _duplicated)
    payload = _plan()
    assert payload['result'] == planner.RESULT_FAIL
    assert payload['plan_status'] == planner.PLAN_BLOCKED_CONTRADICTORY
    assert 'duplicate_official_source_line' in payload['decision_reasons']


# ═══════════════ Dependency safety ══════════════════════════════════════════
def _blocked_identity_fixture():
    """Two dependent appearances for one person whose official position is unavailable."""
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)
    _log(1, 9002, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, 9002, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, 9002, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, 9002, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, 9002, team=B, gs=0, outs=2, r=0, er=0)
    return _FakeMlbClient(
        games=[_official_game(), _official_game(9002, gdate=date(2026, 6, 11))],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES),
                   9002: _boxscore(_HOME_LINES, _AWAY_LINES)},
        people=_ALL_PEOPLE)


def test_blocked_identity_makes_every_dependent_insertion_unsafe(app):
    client = _blocked_identity_fixture()
    people = dict(_ALL_PEOPLE)
    people[3] = _person(3, position=None)          # identity cannot be represented safely
    client.people = people
    payload = planner.run_repair_plan(client=client)

    identity = _action_for(payload, 'identity:create:3')
    assert identity['safe_to_apply'] is False
    dependents = [a for a in _actions(payload, planner.ACTION_GAME_LOG_INSERT)
                  if 'identity:create:3' in a['dependency_action_ids']]
    assert len(dependents) == 2                    # both appearances
    for action in dependents:
        assert action['safe_to_apply'] is False
        assert planner.BLOCK_DEPENDENCY_BLOCKED in action['blocking_reasons']
        assert action['dependency_action_ids'] == ['identity:create:3']  # preserved
        assert action['local_pitcher_id'] is None                        # never invented
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED
    recon = payload['reconciliations']
    assert recon['every_blocked_identity_blocks_its_dependent_insertions'] is True
    assert recon['every_safe_dependent_insertion_has_a_safe_dependency'] is True


def test_blocked_dependent_insertion_reports_identity_dependency_blocked(app):
    client = _blocked_identity_fixture()
    client.raise_people = {3}                      # official identity evidence unavailable
    payload = planner.run_repair_plan(client=client)
    dependents = [a for a in _actions(payload, planner.ACTION_GAME_LOG_INSERT)
                  if 'identity:create:3' in a['dependency_action_ids']]
    assert dependents
    for action in dependents:
        assert planner.BLOCK_DEPENDENCY_BLOCKED in action['blocking_reasons']
        assert action['safe_to_apply'] is False
    assert planner.BLOCK_DEPENDENCY_BLOCKED in payload['blocking_counts_by_reason']
    assert payload['result'] == planner.RESULT_INCONCLUSIVE


def test_safe_identity_leaves_its_dependent_insertions_safe(app):
    client = _blocked_identity_fixture()
    payload = planner.run_repair_plan(client=client)   # person 3 has full official evidence
    identity = _action_for(payload, 'identity:create:3')
    assert identity['safe_to_apply'] is True
    assert identity['blocking_reasons'] == []
    dependents = [a for a in _actions(payload, planner.ACTION_GAME_LOG_INSERT)
                  if 'identity:create:3' in a['dependency_action_ids']]
    assert len(dependents) == 2
    for action in dependents:
        assert action['safe_to_apply'] is True
        assert planner.BLOCK_DEPENDENCY_BLOCKED not in action['blocking_reasons']
    recon = payload['reconciliations']
    assert recon['every_safe_dependent_insertion_has_a_safe_dependency'] is True
    assert recon['every_dependency_references_one_identity_action'] is True
    assert recon['identity_dependent_lists_reconcile_to_insertion_references'] is True


def test_dependency_safety_changes_the_manifest_fingerprint(app):
    client = _blocked_identity_fixture()
    safe_fingerprint = planner.run_repair_plan(client=client)['repair_manifest_fingerprint']
    # Identical official pitching evidence; only the identity becomes unrepresentable, so
    # the propagated safe_to_apply and blocking_reasons must move the fingerprint.
    people = dict(_ALL_PEOPLE)
    people[3] = _person(3, position=None)
    client.people = people
    blocked = planner.run_repair_plan(client=client)
    assert blocked['repair_manifest_fingerprint'] != safe_fingerprint
    assert any(planner.BLOCK_DEPENDENCY_BLOCKED in (a['blocking_reasons'] or ())
               for a in blocked['repair_manifest'])


def test_dependency_safety_propagation_is_pure():
    identity = {'action_id': 'identity:create:7', 'action_type': planner.ACTION_IDENTITY_CREATE,
                'safe_to_apply': False, 'blocking_reasons': ['official_position_evidence_absent']}
    insert = {'action_id': 'gamelog:insert:1:7:100',
              'action_type': planner.ACTION_GAME_LOG_INSERT,
              'dependency_action_ids': ['identity:create:7'],
              'safe_to_apply': True, 'blocking_reasons': []}
    planner._propagate_dependency_safety([identity], [insert])
    assert insert['safe_to_apply'] is False
    assert insert['blocking_reasons'] == [planner.BLOCK_DEPENDENCY_BLOCKED]
    assert insert['dependency_action_ids'] == ['identity:create:7']


def test_missing_dependency_action_is_unresolved_not_silently_safe():
    insert = {'action_id': 'gamelog:insert:1:7:100',
              'action_type': planner.ACTION_GAME_LOG_INSERT,
              'dependency_action_ids': ['identity:create:404'],
              'safe_to_apply': True, 'blocking_reasons': []}
    planner._propagate_dependency_safety([], [insert])
    assert insert['safe_to_apply'] is False
    assert planner.BLOCK_DEPENDENCY_UNRESOLVED in insert['blocking_reasons']


# ═══════════════ 31-32. Determinism ═════════════════════════════════════════
def test_action_ids_are_deterministic_and_unique(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    first, second = _plan(), _plan()
    ids = [a['action_id'] for a in first['repair_manifest']]
    assert ids == [a['action_id'] for a in second['repair_manifest']]
    assert len(ids) == len(set(ids))
    assert first['duplicate_action_ids'] == []
    assert first['reconciliations']['action_ids_unique'] is True
    assert f'gamelog:insert:{GAME_PK}:3:{A}' in ids
    log_id = db.session.query(GameLog).join(Pitcher).filter(Pitcher.mlb_id == 2).one().id
    assert f'gamelog:update:{log_id}:{GAME_PK}:2' in ids


def test_manifest_ordering_is_deterministic_and_phase_first(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    manifest = _plan()['repair_manifest']
    phases = [planner._ACTION_PHASE[a['action_type']] for a in manifest]
    assert phases == sorted(phases)
    assert manifest[0]['action_type'] == planner.ACTION_IDENTITY_CREATE
    assert [a['action_id'] for a in manifest] == [
        a['action_id'] for a in sorted(manifest, key=planner._action_sort_key)]


# ═══════════════ 33-38. Fingerprints ════════════════════════════════════════
def test_source_and_comparison_fingerprints_are_stable(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    first, second = _plan(), _plan()
    a1 = _actions(first, planner.ACTION_GAME_LOG_UPDATE)[0]
    a2 = _actions(second, planner.ACTION_GAME_LOG_UPDATE)[0]
    assert a1['source_fingerprint'] == a2['source_fingerprint']
    assert a1['comparison_fingerprint'] == a2['comparison_fingerprint']
    assert len(a1['source_fingerprint']) == 64
    assert len(a1['comparison_fingerprint']) == 64
    assert a1['source_fingerprint'] != a1['comparison_fingerprint']


def test_manifest_fingerprint_is_stable_across_identical_runs(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    assert _plan()['repair_manifest_fingerprint'] == _plan()['repair_manifest_fingerprint']
    assert len(_plan()['repair_manifest_fingerprint']) == 64


def test_volatile_fields_do_not_change_the_fingerprint(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    first = _plan(generated_at='2026-07-27T00:00:00Z')
    second = _plan(generated_at='2099-01-01T23:59:59Z')
    assert first['generated_at'] != second['generated_at']
    assert first['repair_manifest_fingerprint'] == second['repair_manifest_fingerprint']


@pytest.mark.parametrize('mutate', [
    lambda m: m.append({**m[0], 'action_id': 'gamelog:insert:1:1:1'}),   # action added
    lambda m: m.pop(),                                                   # action removed
    lambda m: m[0].__setitem__('action_id', 'changed'),                  # id changed
    lambda m: m[0].__setitem__('official_source_evidence', {'x': 1}),    # source changed
    lambda m: m[0].__setitem__('proposed_values', {'runs_allowed': 99}),  # proposal changed
    lambda m: m[0].__setitem__('changed_fields', ['runs_allowed']),      # changed field
    lambda m: m[0].__setitem__('reason_codes', ['other']),               # reason changed
    lambda m: m[0].__setitem__('dependency_action_ids', ['identity:create:999']),
    lambda m: m[0].__setitem__('safe_to_apply', not m[0]['safe_to_apply']),
    lambda m: m[0].__setitem__('blocking_reasons', ['newly_blocked']),
    lambda m: m.reverse(),                                               # ordering changed
])
def test_manifest_fingerprint_changes_for_every_meaningful_mutation(app, mutate):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    baseline_fingerprint = payload['repair_manifest_fingerprint']
    mutated = [dict(a) for a in payload['repair_manifest']]
    mutate(mutated)
    assert planner.sha256_of(mutated) != baseline_fingerprint


def test_current_value_change_changes_the_fingerprint(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    first = _plan()['repair_manifest_fingerprint']
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 8}, synchronize_session=False)
    db.session.commit()
    assert _plan()['repair_manifest_fingerprint'] != first


def test_null_is_distinct_from_zero_in_the_fingerprint():
    assert planner.sha256_of({'v': None}) != planner.sha256_of({'v': 0})
    assert planner.canonical_json({'v': None}) == '{"v":null}'
    assert planner.canonical_json({'v': 0}) == '{"v":0}'


def test_preview_bounding_never_changes_the_manifest_or_fingerprint(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    full = _plan(preview_limit=500)
    bounded = _plan(preview_limit=1)
    assert bounded['preview_limit'] == 1
    assert len(bounded['bounded_preview']) == 1
    assert bounded['preview_truncated'] is True
    assert bounded['repair_manifest'] == full['repair_manifest']
    assert bounded['repair_manifest_fingerprint'] == full['repair_manifest_fingerprint']
    assert bounded['repair_manifest_action_count'] == full['repair_manifest_action_count']


def test_full_manifest_is_never_truncated(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    payload = _plan(preview_limit=0)
    assert payload['bounded_preview'] == []
    assert payload['repair_manifest_action_count'] == 2
    assert len(payload['repair_manifest']) == 2
    assert payload['reconciliations']['manifest_action_count_equals_sum'] is True


# ═══════════════ 40-41. Read-only guarantee ═════════════════════════════════
def test_planner_emits_no_write_sql(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).delete(synchronize_session=False)
    db.session.commit()
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        payload = _plan()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [s for s in statements
              if s.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []
    assert payload['database_writes_performed'] is False


def test_database_rows_are_unchanged_after_planning(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    before_logs = {r.id: (r.games_started, r.innings_pitched_outs, r.strikeouts,
                          r.appearance_team_id) for r in db.session.query(GameLog).all()}
    before_pitchers = {p.id: (p.mlb_id, p.team_id, p.active, p.position)
                       for p in db.session.query(Pitcher).all()}
    _plan()
    assert before_logs == {r.id: (r.games_started, r.innings_pitched_outs, r.strikeouts,
                                  r.appearance_team_id)
                           for r in db.session.query(GameLog).all()}
    assert before_pitchers == {p.id: (p.mlb_id, p.team_id, p.active, p.position)
                               for p in db.session.query(Pitcher).all()}


def _code_without_prose(path):
    """Source with docstrings and comment lines removed, so prose cannot satisfy a guard."""
    import ast
    src = path.read_text(encoding='utf-8')
    prose_lines = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            prose_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return '\n'.join(
        line for number, line in enumerate(src.splitlines(), start=1)
        if number not in prose_lines and not line.strip().startswith('#')
    )


def test_service_contains_no_write_path_and_no_apply_mode():
    code = _code_without_prose(SERVICE_PATH)
    for token in ('session.add', 'session.commit', 'session.delete', 'session.merge',
                  'session.flush', 'session.bulk', 'INSERT INTO', 'DELETE FROM',
                  'db.create_all', 'db.drop_all', 'def apply', 'apply_manifest',
                  'execute_plan', 'def repair('):
        assert token not in code, token


def test_service_never_reads_current_team_or_roster_as_authority():
    code = _code_without_prose(SERVICE_PATH)
    # No current-state column is ever READ as authority.
    for token in ('Pitcher.team_id', 'Pitcher.active', 'Pitcher.roster_status',
                  'Pitcher.team_abbreviation', 'Pitcher.team_name'):
        assert token not in code, token
    # Every mutable current-state field appears only in the explicit omission declaration.
    for omitted in ('team_id', 'team_abbreviation', 'roster_status'):
        assert omitted in planner.OMITTED_MUTABLE_IDENTITY_FIELDS


# ═══════════════ Scoped runs ════════════════════════════════════════════════
def test_scoped_team_run_is_not_apply_eligible(app):
    _seed_matching_local()
    payload = _plan(team_id=A)
    assert payload['plan_scope'] == planner.PLAN_SCOPE_SUBSET
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_SUBSET
    assert payload['baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE


def test_scoped_game_run_is_not_apply_eligible(app):
    _seed_matching_local()
    payload = _plan(game_pk=GAME_PK)
    assert payload['plan_scope'] == planner.PLAN_SCOPE_SUBSET
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_SUBSET


def test_full_scope_is_reported_for_an_unscoped_run(app):
    _seed_matching_local()
    assert _plan()['plan_scope'] == planner.PLAN_SCOPE_FULL


def test_official_evidence_unavailable_is_inconclusive(app):
    _seed_matching_local()
    payload = planner.run_repair_plan(client=_client(raise_pks=(GAME_PK,)))
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['official_games_fetched'] == 0
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED


def test_non_regular_game_type_is_refused(app):
    with pytest.raises(ValueError):
        planner.run_repair_plan(game_type='P', client=_client())


# ═══════════════ Output contract + verification plan ════════════════════════
def test_report_has_every_required_field(app):
    _seed_matching_local()
    payload = _plan()
    for key in ('capability', 'mode', 'result', 'exit_code', 'generated_at', 'git_sha',
                'migration_head', 'season', 'as_of_date', 'accepted_baseline',
                'observed_population', 'baseline_comparison',
                'baseline_matches_accepted_diagnostic', 'official_games_selected',
                'official_games_fetched', 'official_team_game_sides',
                'official_pitching_lines', 'official_starter_lines', 'official_relief_lines',
                'local_pitching_lines', 'local_starter_lines', 'local_relief_lines',
                'exact_match_count', 'missing_line_count', 'defective_matched_line_count',
                'defect_line_action_count', 'unique_identities_requiring_creation',
                'missing_lines_dependent_on_identity_creation',
                'missing_lines_using_existing_identity', 'game_log_inserts_planned',
                'existing_game_logs_requiring_updates', 'role_corrections_planned',
                'stat_correction_rows_planned', 'actions_by_type', 'actions_by_team',
                'blocking_counts_by_reason', 'no_action_confirmations',
                'repair_manifest_action_count', 'repair_manifest',
                'repair_manifest_fingerprint', 'bounded_preview', 'preview_limit',
                'preview_truncated', 'verification_plan', 'plan_status',
                'repair_apply_gate', 'foundation_3b_gate', 'public_reader_gate',
                'share_card_performance_gate', 'database_writes_performed'):
        assert key in payload, key
    assert payload['mode'] == 'read_only'
    assert payload['database_writes_performed'] is False


def test_verification_plan_is_ordered_and_descriptive(app):
    _seed_matching_local()
    steps = _plan()['verification_plan']
    assert [s['step'] for s in steps] == list(range(1, 9))
    assert 'completeness' in steps[0]['action']
    assert 'local_only' in steps[2]['action']
    assert 'official_validation' in steps[4]['action']
    assert 'foundation_3b' in steps[7]['action']
    # Descriptive only: the planner exposes no runner for these steps.
    code = _code_without_prose(SERVICE_PATH)
    assert 'run_aggregation(' not in code
    assert 'run_diagnostic(' not in code


def test_downstream_gates_remain_blocked(app):
    _seed_matching_local()
    payload = _plan()
    assert payload['foundation_3b_gate'] == 'blocked'
    assert payload['public_reader_gate'] == 'blocked'
    assert payload['share_card_performance_gate'] == 'blocked'


def test_report_contains_no_secret_or_raw_payload(app):
    _seed_matching_local()
    blob = str(_plan()).lower()
    for token in ('password', 'secret', 'postgres://', 'database_url', 'statuscode',
                  'abstractgamestate'):
        assert token not in blob


def test_exit_code_map():
    assert planner.EXIT_BY_RESULT[planner.RESULT_PASS] == 0
    assert planner.EXIT_BY_RESULT[planner.RESULT_FAIL] == 1
    assert planner.EXIT_BY_RESULT[planner.RESULT_INCONCLUSIVE] == 2


# ═══════════════ 42. CLI ════════════════════════════════════════════════════
def test_cli_helpers_and_defaults():
    import argparse
    from scripts import run_official_pitching_line_repair_plan_2026 as cli
    assert cli.CAPABILITY == planner.CAPABILITY
    assert cli._iso_date('2026-07-25') == date(2026, 7, 25)
    with pytest.raises(argparse.ArgumentTypeError):
        cli._iso_date('nope')
    assert cli._bounded_limit('100') == 100
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_limit('9999')
    with pytest.raises(argparse.ArgumentTypeError):
        cli._positive_int('0')
    parsed = cli._parse_args([])
    assert parsed.season == 2026
    assert parsed.as_of_date == date(2026, 7, 25)
    assert parsed.preview_limit == 100
    assert parsed.team_id is None and parsed.game_pk is None


def test_cli_exit_codes_follow_the_result():
    from scripts import run_official_pitching_line_repair_plan_2026 as cli
    assert cli.CRASH_EXIT_CODE == 1
    secret_message = 'postgres://user:hunter2@db.internal/prod'
    payload = cli._failure_payload(ValueError(secret_message))
    assert payload['exit_code'] == 1
    assert payload['database_writes_performed'] is False
    assert payload['error_type'] == 'ValueError'
    assert secret_message not in str(payload)      # message discarded, only the class name
    assert 'hunter2' not in str(payload)


def test_cli_has_no_apply_or_fingerprint_acceptance_flag():
    src = CLI_PATH.read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in src
    for token in ('--apply', '--repair', '--backfill', '--fix', '--accept-fingerprint',
                  '--confirm'):
        assert token not in src, token


# ═══════════════ 43-48. Workflow ════════════════════════════════════════════
def _workflow_lines():
    return WORKFLOW_PATH.read_text(encoding='utf-8').splitlines()


def _workflow_without_comments():
    return '\n'.join(line for line in _workflow_lines()
                     if not line.strip().startswith('#'))


def test_workflow_dispatch_only():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in src
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                    '\n  workflow_call:', '\n  repository_dispatch:'):
        assert trigger not in src


def test_workflow_read_only_controls():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'permissions:' in src and 'contents: read' in src
    assert 'concurrency:' in src
    assert 'run_official_pitching_line_repair_plan_2026.py' in src
    assert 'retention-days: 14' in src


def test_workflow_sources_every_production_secret():
    lines = _workflow_lines()
    for entry in ('      APP_ENV: production',
                  "      AUTO_SYNC: 'false'",
                  '      FLASK_APP: app.py',
                  '      DATABASE_URL: ${{ secrets.DATABASE_URL }}',
                  '      SECRET_KEY: ${{ secrets.SECRET_KEY }}',
                  '      ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'):
        assert entry in lines, entry


def test_workflow_validates_all_required_secrets_without_printing_them():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    for guard in ('[ -z "${DATABASE_URL:-}" ]', '[ -z "${SECRET_KEY:-}" ]',
                  '[ -z "${ADMIN_API_TOKEN:-}" ]'):
        assert guard in src, guard
    assert 'echo "::error::Missing required production repository secret."' in src
    for leak in ('${#ADMIN_API_TOKEN}', '${#SECRET_KEY}', '${#DATABASE_URL}'):
        assert leak not in src, leak
    for line in src.splitlines():
        if line.strip().startswith('echo'):
            for name in ('ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL'):
                assert name not in line, line


def test_workflow_rejects_write_or_non_read_only_payloads():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert "if payload.get('database_writes_performed') is not False:" in src
    assert "raise SystemExit('Repair plan must not perform database writes.')" in src
    assert "if payload.get('mode') != 'read_only':" in src
    assert "raise SystemExit('Repair plan must run in read_only mode.')" in src


def test_workflow_contains_no_apply_path():
    src = _workflow_without_comments()
    for token in ('--apply', '--repair', '--backfill', '--fix', '--accept-fingerprint',
                  'apply:', 'confirmation:', 'expected_fingerprint', 'accepted_fingerprint',
                  'flask db upgrade', 'psql'):
        assert token not in src, token


def test_workflow_ships_full_manifest_and_bounded_summary():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert "payload.get('bounded_preview')" in src
    assert "payload.get('repair_manifest_fingerprint')" in src
    assert "payload.get('repair_manifest_action_count')" in src
    assert 'never truncated' in src
    # The step summary must not attempt to render the unbounded manifest.
    assert "payload.get('repair_manifest')" not in src


def test_decision_record_documents_the_governed_contract():
    text = DECISION_RECORD.read_text(encoding='utf-8')
    for phrase in ('bounded', '445', '159', '604', '342', 'fingerprint', 'position player',
                   'delete', 'appearance-team', 'apply'):
        assert phrase in text.lower(), phrase
