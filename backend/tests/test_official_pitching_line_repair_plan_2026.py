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
# The real production identity transition under regression: Andrew Wantz, official MLB
# person 681806, appearing for official team 139 in game 822975. Before a routine identity
# synchronization he had no local Pitcher row and his insertion was identity-dependent;
# afterwards he resolves to local Pitcher.id 804.
WANTZ_MLB_ID = 681806
WANTZ_GAME_PK = 822975
WANTZ_TEAM = 139
WANTZ_OPPONENT = 141
WANTZ_LOCAL_PITCHER_ID = 804
# The opposing official side for each fixture team, mirrored onto local rows.
_OPPONENT_NAME = {A: 'Team200', B: 'Team100', C: None,
                  WANTZ_TEAM: f'Team{WANTZ_OPPONENT}', WANTZ_OPPONENT: f'Team{WANTZ_TEAM}'}
_OPPONENT_ABBR = {A: 'T200', B: 'T100', C: None,
                  WANTZ_TEAM: f'T{WANTZ_OPPONENT}', WANTZ_OPPONENT: f'T{WANTZ_TEAM}'}
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
         gdate=GDATE, game_type='R', pitcher_row=None, strikes=None, opponent=None,
         opponent_abbreviation=None, **extra):
    """A local row mirroring the matching official line's governed workload evidence."""
    row = pitcher_row or _pitcher(mlb_id)
    log = GameLog(
        pitcher_id=row.id, mlb_game_pk=game_pk, game_date=gdate, game_type=game_type,
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        runs_allowed=r, earned_runs=er, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr,
        strikes=outs * 2 if strikes is None else strikes,
        opponent=_OPPONENT_NAME[team] if opponent is None else opponent,
        opponent_abbreviation=(_OPPONENT_ABBR[team] if opponent_abbreviation is None
                               else opponent_abbreviation),
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=team, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
        **extra,
    )
    db.session.add(log)
    db.session.commit()
    return log


# ── Official evidence fakes ───────────────────────────────────────────────────
def _ip(outs):
    return f'{outs // 3}.{outs % 3}'


def _pline(mlb_id, *, gs, outs, r=0, er=0, h=0, bb=0, k=0, hr=0, drop=(),
           strikes=None, pitches=None, extra=None):
    """A complete official pitching line.

    ``strikes`` is one of the required authoritative-correction keys, so it is always
    present unless a test deliberately drops it. ``numberOfPitches`` is genuinely optional
    in official completed-game lines and is only added when a test supplies it.
    """
    stats = {'gamesStarted': gs, 'inningsPitched': _ip(outs), 'runs': r, 'earnedRuns': er,
             'hits': h, 'baseOnBalls': bb, 'strikeOuts': k, 'homeRuns': hr,
             'strikes': outs * 2 if strikes is None else strikes}
    if pitches is not None:
        stats['numberOfPitches'] = pitches
    if extra:
        stats.update(extra)
    for key in drop:
        stats.pop(key, None)
    return (mlb_id, stats)


def _side(team_id, name, lines):
    return {
        'team': {'id': team_id, 'name': name, 'abbreviation': f'T{team_id}'},
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
                 raise_people=(), registry_teams=(), raise_teams=False):
        self.games = list(games)
        self.boxscores = dict(boxscores or {})
        self.people = dict(people or {})
        self.raise_windows = set(raise_windows)
        self.raise_pks = set(raise_pks)
        self.raise_people = set(raise_people)
        self.person_calls = []
        self.registry_teams = list(registry_teams)
        self.raise_teams = raise_teams
        self.team_registry_calls = 0

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

    def get_all_teams(self, sport_id=1):
        self.team_registry_calls += 1
        if self.raise_teams:
            raise RuntimeError('team registry unavailable')
        return list(self.registry_teams)


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
    """Pin ACCEPTED_DEFECT_BASELINE to a small fixture's own observed population."""
    observed = (payload_or_dict['observed_population']
                if isinstance(payload_or_dict, dict) and 'observed_population' in payload_or_dict
                else payload_or_dict)
    pinned = {key: observed[key] for key in planner.ACCEPTED_DEFECT_BASELINE}
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', pinned)
    return pinned


# ═══════════════ 1. Accepted production baseline ════════════════════════════
def test_accepted_baseline_pins_the_production_population():
    # V1 is the originally accepted population and is retained unchanged; V2 is active.
    b = planner.ACCEPTED_DEFECT_BASELINE_V1
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
    assert b['role_corrections_planned'] == 2
    # The ACTIVE baseline is V2, which differs only in the three reviewed counts.
    active = planner.ACCEPTED_DEFECT_BASELINE
    assert planner.ACTIVE_ACCEPTED_DEFECT_BASELINE_VERSION == 'v2'
    assert active is planner.ACCEPTED_DEFECT_BASELINE_V2
    assert active['exact_match_count'] == 12696
    assert active['defective_matched_line_count'] == 160
    assert active['defect_line_action_count'] == 605
    assert active['missing_line_count'] == 445
    for zero_key in ('appearance_team_mismatch_count', 'extra_local_line_count',
                     'duplicate_local_line_count', 'local_pitcher_identity_missing_count',
                     'official_evidence_unavailable_count'):
        assert b[zero_key] == 0
    # The identity-resolution partition is NOT part of the immutable defect baseline: it is
    # a fact about the local Pitcher table right now, not about official evidence.
    assert 'missing_lines_dependent_on_identity_creation' not in b
    assert 'missing_lines_using_existing_identity' not in b
    assert 'unique_identities_requiring_creation' not in b
    snapshot = planner.PRIOR_IDENTITY_RESOLUTION_SNAPSHOT
    assert snapshot['missing_lines_dependent_on_identity_creation'] == 342
    assert snapshot['missing_lines_using_existing_identity'] == 103
    assert snapshot['unique_identities_requiring_creation'] == 71


# ═══════════════ 2-3. Population partition + 604 defect actions ═════════════
def test_accepted_baseline_partitions_exactly():
    b = planner.ACCEPTED_DEFECT_BASELINE_V1
    # 13,301 = 12,697 + 445 + 159
    assert (b['exact_match_count'] + b['missing_line_count']
            + b['defective_matched_line_count']) == b['official_pitching_lines']
    # 3,140 starter + 10,161 relief = 13,301
    assert b['official_starter_lines'] + b['official_relief_lines'] == b['official_pitching_lines']
    # 604 = 445 + 159
    assert b['missing_line_count'] + b['defective_matched_line_count'] == 604
    assert b['defect_line_action_count'] == 604
    # V2 partitions the same 13,301 official lines: 12,696 + 445 + 160.
    v2 = planner.ACCEPTED_DEFECT_BASELINE_V2
    assert (v2['exact_match_count'] + v2['missing_line_count']
            + v2['defective_matched_line_count']) == v2['official_pitching_lines'] == 13301
    assert v2['missing_line_count'] + v2['defective_matched_line_count'] == 605
    assert v2['defect_line_action_count'] == 605
    # Sides are two per official game.
    assert b['official_team_game_sides'] == b['official_games_fetched'] * 2
    assert b['official_starter_lines'] == b['official_team_game_sides']
    # The identity-dependent appearances are a subset of the 445 missing lines — proved
    # against the observational snapshot, never against the immutable baseline.
    snapshot = planner.PRIOR_IDENTITY_RESOLUTION_SNAPSHOT
    assert snapshot['missing_lines_dependent_on_identity_creation'] < b['missing_line_count']
    assert (snapshot['missing_lines_dependent_on_identity_creation']
            + snapshot['missing_lines_using_existing_identity']) == b['missing_line_count']


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
    # homeRuns is one of the governed required correction keys, so the authoritative
    # source contract blocks the line before any value is proposed from it.
    assert planner.BLOCK_CORRECTION_SOURCE_INCOMPLETE in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['workload_field_coverage'][
        'actions_blocked_by_incomplete_authoritative_source'] >= 1


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
    comparison = payload['defect_baseline_comparison']
    assert set(comparison) == set(planner.ACCEPTED_DEFECT_BASELINE)
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
        planned_defect_line_keys=planned_defect_line_keys,
        manifest_fingerprint='0' * 64)


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



# ═══════════════ Official GameLog evidence completeness ════════════════════
_FULL_STATS = {'battersFaced': 12, 'balls': 14, 'gamesFinished': 1,
               'inheritedRunners': 2, 'inheritedRunnersScored': 1,
               'saveOpportunities': 1, 'holds': 0, 'blownSaves': 0,
               'wins': 1, 'losses': 0, 'saves': 0}


def _missing_line_client(*, pitches=None, extra=None, drop=(), strikes=None):
    """Official evidence where person 3's line is missing locally."""
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1, pitches=pitches, extra=extra,
                   drop=drop, strikes=strikes)]
    return _client(home_lines=home)


def _seed_missing_line_3():
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()


def test_pitch_count_is_planned_when_official_evidence_supplies_it(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(pitches=41))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['pitches_thrown'] == 41
    assert insert['official_source_evidence']['official_raw_stats']['numberOfPitches'] == 41
    assert payload['workload_field_coverage'][
        'insert_actions_with_official_pitch_count'] == 1
    assert payload['workload_field_coverage'][
        'insert_actions_without_official_pitch_count'] == 0


def test_absent_pitch_count_stays_null_and_is_counted(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())   # no numberOfPitches
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert 'pitches_thrown' not in insert['proposed_values']    # never manufactured
    assert 'numberOfPitches' not in insert['official_source_evidence']['official_raw_stats']
    assert payload['workload_field_coverage'][
        'insert_actions_without_official_pitch_count'] == 1
    assert insert['safe_to_apply'] is True     # optional absence never blocks


def test_strikes_are_required_and_never_defaulted(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(drop=('strikes',)))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert 'strikes' not in insert['proposed_values']
    assert planner.BLOCK_CORRECTION_SOURCE_INCOMPLETE in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED


def test_strikes_are_planned_from_official_evidence(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(strikes=27))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['strikes'] == 27
    assert payload['workload_field_coverage']['insert_actions_with_official_strikes'] == 1


def test_opponent_comes_from_the_opposing_official_side(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    # Person 3 pitched for the HOME side (team A), so the opponent is the AWAY side.
    assert insert['proposed_values']['opponent'] == f'Team{B}'
    assert insert['proposed_values']['opponent_abbreviation'] == f'T{B}'
    evidence = insert['official_source_evidence']
    assert evidence['official_side'] == 'home'
    assert evidence['opposing_team_id'] == B
    assert payload['reconciliations']['opponent_comes_from_the_official_game_side'] is True
    # Opponent never comes from a mutable player assignment.
    assert 'Pitcher.team_abbreviation' not in _code_without_prose(SERVICE_PATH)


def test_batters_faced_and_balls_appear_only_when_present(app):
    _seed_missing_line_3()          # one ledger state, two official evidence variants
    without = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(without, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert 'batters_faced' not in insert['proposed_values']
    assert 'balls' not in insert['proposed_values']

    with_evidence = planner.run_repair_plan(
        client=_missing_line_client(extra={'battersFaced': 12, 'balls': 14}))
    insert = _action_for(with_evidence, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['batters_faced'] == 12
    assert insert['proposed_values']['balls'] == 14
    assert with_evidence['workload_field_coverage'][
        'insert_actions_with_batters_faced'] == 1


def test_inherited_runner_fields_appear_only_when_present(app):
    _seed_missing_line_3()
    without = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(without, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert 'inherited_runners' not in insert['proposed_values']
    assert 'inherited_runners_scored' not in insert['proposed_values']
    assert without['workload_field_coverage'][
        'insert_actions_with_inherited_runner_evidence'] == 0

    with_evidence = planner.run_repair_plan(client=_missing_line_client(
        extra={'inheritedRunners': 2, 'inheritedRunnersScored': 0}))
    insert = _action_for(with_evidence, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['inherited_runners'] == 2
    assert insert['proposed_values']['inherited_runners_scored'] == 0   # official zero kept
    assert with_evidence['workload_field_coverage'][
        'insert_actions_with_inherited_runner_evidence'] == 1


def test_decision_and_save_fields_follow_the_ingestion_contract(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(extra=dict(_FULL_STATS)))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    proposed = insert['proposed_values']
    # Booleans follow sync._positive_stat: present-and-positive is True, present-and-zero
    # is False, and the field only appears at all when the source key is present.
    assert proposed['save_situation'] is True          # saveOpportunities 1
    assert proposed['win'] is True                     # wins 1
    assert proposed['hold'] is False                   # holds 0, officially present
    assert proposed['blown_save'] is False
    assert proposed['loss'] is False
    assert proposed['save'] is False
    assert proposed['games_finished'] == 1
    assert payload['workload_field_coverage']['insert_actions_with_decision_evidence'] == 1


def test_decision_fields_are_absent_when_the_source_omits_them(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    for field in ('save_situation', 'hold', 'blown_save', 'win', 'loss', 'save'):
        assert field not in insert['proposed_values'], field
    assert payload['reconciliations'][
        'optional_fields_planned_only_when_source_present'] is True


def test_every_safe_insert_carries_every_required_correction_field(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(pitches=41))
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert set(planner.REQUIRED_INSERT_FIELDS) <= set(insert['proposed_values'])
    recon = payload['reconciliations']
    assert recon['every_safe_insert_contains_every_required_non_fk_value'] is True
    assert recon['no_required_official_value_is_defaulted'] is True
    assert recon['every_safe_insert_has_a_resolvable_pitcher_reference'] is True


def test_update_gains_workload_corrections_without_becoming_a_second_action(app):
    _seed_matching_local()
    # One row is wrong on a mandatory metric AND on governed workload evidence.
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'strikeouts': 9, 'strikes': 99}, synchronize_session=False)
    db.session.commit()
    payload = planner.run_repair_plan(client=_client(
        home_lines=[_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
                    _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2, pitches=18),
                    _pline(3, gs=0, outs=3, r=0, er=0, k=1)]))
    updates = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)
    assert len(updates) == 1                       # still exactly one action for the row
    changed = updates[0]['changed_fields']
    assert 'strikeouts' in changed                 # mandatory metric
    assert 'strikes' in changed                    # workload field
    assert 'pitches_thrown' in changed             # workload field newly available
    assert updates[0]['current_values']['strikes'] == 99
    assert updates[0]['proposed_values']['strikes'] == 6
    assert updates[0]['proposed_values']['pitches_thrown'] == 18
    assert payload['workload_field_coverage']['update_actions_correcting_strikes'] == 1
    assert payload['workload_field_coverage']['update_actions_correcting_pitch_count'] == 1
    assert payload['reconciliations'][
        'every_changed_field_has_current_and_proposed_values'] is True


def test_update_never_replaces_a_local_value_with_null(app):
    _seed_matching_local()
    # Local row carries a stored pitch count; the official line omits numberOfPitches.
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'pitches_thrown': 37, 'strikeouts': 9}, synchronize_session=False)
    db.session.commit()
    payload = _plan()
    update = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)[0]
    assert 'pitches_thrown' not in update['changed_fields']
    assert 'pitches_thrown' in update['null_guarded_fields']
    assert update['proposed_values'].get('pitches_thrown') is None
    assert payload['reconciliations'][
        'no_update_replaces_a_local_value_with_null'] is True
    assert payload['workload_field_coverage'][
        'update_actions_with_null_guarded_fields'] == 1


def test_exact_mandatory_line_with_matching_workload_gains_no_action(app):
    _seed_matching_local()          # local rows mirror official strikes and opponent
    payload = _plan()
    assert payload['defect_line_action_count'] == 0
    assert payload['repair_manifest'] == []
    assert payload['reconciliations']['no_exact_line_maps_to_a_repair_action'] is True


def test_manifest_fingerprint_supersedes_the_prior_production_fingerprint(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client(pitches=41))
    prior = 'dbbc063a0711e57b0dc2d858b7d1d291c568c4990ecff7c9ebf3d1b138cbb2d6'
    assert planner.PRIOR_PRODUCTION_MANIFEST_FINGERPRINT == prior
    assert payload['prior_production_manifest_fingerprint'] == prior
    assert payload['repair_manifest_fingerprint'] != prior
    assert payload['reconciliations'][
        'manifest_fingerprint_differs_from_prior_production_fingerprint'] is True


def test_raw_evidence_changes_the_source_fingerprint(app):
    _seed_missing_line_3()          # one ledger state, two official evidence variants
    without = planner.run_repair_plan(client=_missing_line_client())
    with_pitches = planner.run_repair_plan(client=_missing_line_client(pitches=41))
    a = _action_for(without, f'gamelog:insert:{GAME_PK}:3:{A}')
    b = _action_for(with_pitches, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert a['source_fingerprint'] != b['source_fingerprint']
    assert without['repair_manifest_fingerprint'] != with_pitches['repair_manifest_fingerprint']
    assert with_pitches['reconciliations'][
        'source_fingerprints_cover_the_enriched_raw_evidence'] is True


def test_raw_official_stats_are_retained_before_normalization(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(
        client=_missing_line_client(pitches=41, extra=dict(_FULL_STATS)))
    evidence = _action_for(
        payload, f'gamelog:insert:{GAME_PK}:3:{A}')['official_source_evidence']
    raw = evidence['official_raw_stats']
    for key in ('inningsPitched', 'numberOfPitches', 'strikes', 'hits', 'runs', 'earnedRuns',
                'baseOnBalls', 'strikeOuts', 'homeRuns', 'battersFaced', 'balls',
                'gamesFinished', 'inheritedRunners', 'inheritedRunnersScored',
                'saveOpportunities', 'holds', 'blownSaves', 'wins', 'losses', 'saves'):
        assert key in raw, key
    # The normalized mandatory metrics are retained alongside, not instead of, the raw line.
    assert set(evidence['official_stats']) == {
        'outs', 'runs', 'earned_runs', 'hits', 'walks', 'strikeouts', 'home_runs'}


def test_correction_metadata_policy_is_descriptive_only(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    policy = payload['correction_metadata_policy']
    assert policy['correction_source'] == 'official_pitching_line_repair'
    assert policy['executed_by_planner'] is False
    assert 'excluded from the manifest fingerprint' in policy['last_stat_correction_at']
    assert 'sync._notify_workload_evidence_game_log_correction' in policy[
        'dependent_evidence_invalidation']
    # No action ever proposes correction metadata or a generated timestamp.
    for action in payload['repair_manifest']:
        proposed = action.get('proposed_values') or {}
        for field in ('stat_correction_count', 'last_stat_correction_at',
                      'last_stat_correction_source', 'last_stat_correction_sync_run_id',
                      'created_at'):
            assert field not in proposed, field


def test_planner_reuses_the_production_ingestion_contract():
    code = _code_without_prose(SERVICE_PATH)
    for helper in ('sync_service._game_log_values_from_stats',
                   'sync_service._correction_source_state',
                   'sync_service._authoritative_correction_fields',
                   'sync_service._extract_pitching_lines_from_boxscore'):
        assert helper in code, helper
    # The planner must not re-implement official stat parsing.
    for reimplementation in ("stats.get('numberOfPitches')", "int(stats.get('strikes'",
                             "def _int_stat"):
        assert reimplementation not in code, reimplementation


def test_daily_sync_parsing_behaviour_is_unchanged():
    """The planner reuses the ingestion helpers; it must not have altered them."""
    from services import sync as sync_module
    stats = {'inningsPitched': '1.1', 'strikes': 12, 'hits': 1, 'runs': 0, 'earnedRuns': 0,
             'baseOnBalls': 1, 'strikeOuts': 2, 'homeRuns': 0, 'numberOfPitches': 20,
             'battersFaced': 5, 'saveOpportunities': 1}
    values = sync_module._game_log_values_from_stats(
        stats=stats, pitcher=planner._PitcherRef(7), game_pk=1, game_date=GDATE,
        game_type='R', opponent='Opp', opponent_abbreviation='OPP', games_started=0)
    assert values['innings_pitched_outs'] == 4
    assert values['innings_pitched'] == pytest.approx(4 / 3.0)
    assert values['pitches_thrown'] == 20
    assert values['strikes'] == 12
    assert values['batters_faced'] == 5
    assert values['save_situation'] is True
    assert values['balls'] is None
    assert values['pitcher_id'] == 7
    safe, reason, missing = sync_module._correction_source_state(stats)
    assert (safe, reason, missing) == (True, None, [])
    fields = sync_module._authoritative_correction_fields(
        values, stats, include_leverage_index=False)
    assert 'save_situation' in fields and 'batters_faced' in fields
    assert 'balls' not in fields               # source key absent


# ═══════════════ Complete official opponent evidence ═══════════════════════
def _side_without(team_id, name, lines, *, abbreviation=None):
    """An official side whose team object may omit the abbreviation."""
    team = {'id': team_id, 'name': name}
    if abbreviation is not None:
        team['abbreviation'] = abbreviation
    return {
        'team': team,
        'pitchers': [mlb_id for mlb_id, _stats in lines],
        'players': {f'ID{mlb_id}': {'person': {'id': mlb_id, 'fullName': f'P{mlb_id}'},
                                    'stats': {'pitching': stats}}
                    for mlb_id, stats in lines},
    }


def _schedule_game(game_pk=GAME_PK, home=A, away=B, gdate=GDATE, *, home_team=None,
                   away_team=None):
    """A schedule game whose hydrated team objects can carry supplemental metadata."""
    game = _official_game(game_pk, home, away, gdate)
    game['teams'] = {
        'home': {'team': home_team or {'id': home, 'name': f'Team{home}'}},
        'away': {'team': away_team or {'id': away, 'name': f'Team{away}'}},
    }
    return game


def test_complete_opposing_side_yields_non_null_name_and_abbreviation(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['opponent'] == f'Team{B}'
    assert insert['proposed_values']['opponent_abbreviation'] == f'T{B}'
    opponent = insert['official_opponent_evidence']
    assert opponent['opposing_team_id'] == B
    assert opponent['opponent_name_source'] == planner.OPPONENT_SOURCE_BOXSCORE
    assert opponent['opponent_abbreviation_source'] == planner.OPPONENT_SOURCE_BOXSCORE
    assert opponent['blocking_reasons'] == []
    assert insert['safe_to_apply'] is True
    coverage = payload['workload_field_coverage']
    assert coverage['insert_actions_with_official_opponent_name'] == 1
    assert coverage['insert_actions_with_official_opponent_abbreviation'] == 1


def test_schedule_metadata_supplements_a_missing_boxscore_abbreviation(app):
    _seed_missing_line_3()
    # The away box-score team object omits its abbreviation; the schedule supplies it for
    # the SAME official team id.
    boxscore = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, f'Team{B}', _AWAY_LINES)}}
    client = _FakeMlbClient(
        games=[_schedule_game(away_team={'id': B, 'name': f'Team{B}',
                                         'abbreviation': f'T{B}'})],
        boxscores={GAME_PK: boxscore}, people=_ALL_PEOPLE)
    payload = planner.run_repair_plan(client=client)
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    opponent = insert['official_opponent_evidence']
    assert insert['proposed_values']['opponent_abbreviation'] == f'T{B}'
    assert opponent['opponent_abbreviation_source'] == planner.OPPONENT_SOURCE_SCHEDULE
    assert opponent['opponent_name_source'] == planner.OPPONENT_SOURCE_BOXSCORE
    assert opponent['opposing_team_id'] == B      # box score still fixed WHICH team
    assert insert['safe_to_apply'] is True


def test_team_registry_supplements_when_boxscore_and_schedule_both_lack_it(app):
    _seed_missing_line_3()
    boxscore = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, f'Team{B}', _AWAY_LINES)}}
    client = _FakeMlbClient(
        games=[_schedule_game()], boxscores={GAME_PK: boxscore}, people=_ALL_PEOPLE,
        registry_teams=[{'id': B, 'name': f'Team{B}', 'abbreviation': f'T{B}'}])
    payload = planner.run_repair_plan(client=client)
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    opponent = insert['official_opponent_evidence']
    assert opponent['opponent_abbreviation_source'] == planner.OPPONENT_SOURCE_TEAM_REGISTRY
    assert insert['proposed_values']['opponent_abbreviation'] == f'T{B}'
    assert insert['safe_to_apply'] is True


def test_missing_opponent_name_blocks_the_action(app):
    _seed_missing_line_3()
    boxscore = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, None, _AWAY_LINES, abbreviation=f'T{B}')}}
    client = _FakeMlbClient(
        games=[_schedule_game(away_team={'id': B, 'abbreviation': f'T{B}'})],
        boxscores={GAME_PK: boxscore}, people=_ALL_PEOPLE)
    payload = planner.run_repair_plan(client=client)
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert planner.BLOCK_OPPONENT_NAME_ABSENT in insert['blocking_reasons']
    assert 'opponent' not in insert['proposed_values']     # never planned as null
    assert insert['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED
    assert payload['workload_field_coverage'][
        'actions_blocked_by_missing_opponent_name'] == 1


def test_missing_opponent_abbreviation_blocks_the_action(app):
    _seed_missing_line_3()
    boxscore = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, f'Team{B}', _AWAY_LINES)}}
    client = _FakeMlbClient(                       # no schedule or registry supplement
        games=[_schedule_game()], boxscores={GAME_PK: boxscore}, people=_ALL_PEOPLE)
    payload = planner.run_repair_plan(client=client)
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert planner.BLOCK_OPPONENT_ABBREVIATION_ABSENT in insert['blocking_reasons']
    assert 'opponent_abbreviation' not in insert['proposed_values']
    assert insert['safe_to_apply'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['workload_field_coverage'][
        'actions_blocked_by_missing_opponent_abbreviation'] == 1


def test_none_equals_none_cannot_satisfy_opponent_reconciliation():
    # Both proposed and evidence values absent: the old None == None check passed here.
    action = {
        'safe_to_apply': True,
        'proposed_values': {'opponent': None, 'opponent_abbreviation': None},
        'official_source_evidence': {'opposing_team_name': None,
                                     'opposing_team_abbreviation': None},
        'official_opponent_evidence': {'opposing_team_id': None,
                                       'opponent_name_source': None,
                                       'opponent_abbreviation_source': None},
    }
    assert planner._opponent_matches_official_side(action) is False
    assert planner._safe_action_has_complete_opponent_evidence(action) is False


def test_conflicting_supplemental_team_id_fails_closed():
    sides = {'opposing_team': {'team_id': B, 'team_name': None, 'team_abbreviation': None}}
    metadata = {'schedule': {B: {'team_id': C, 'team_name': 'Wrong',
                                 'team_abbreviation': 'WRG'}}, 'registry': {}}
    resolved = planner._resolve_opponent(sides, metadata)
    assert planner.BLOCK_OPPONENT_IDENTITY_CONFLICT in resolved['blocking_reasons']
    assert resolved['opponent_name'] is None
    assert resolved['opponent_abbreviation'] is None


def test_required_insert_fields_reject_a_present_but_null_value():
    action = {'proposed_values': {field: 'x' for field in planner.REQUIRED_INSERT_FIELDS}}
    assert planner._required_insert_values_present(action) is True
    action['proposed_values']['opponent_abbreviation'] = None
    assert planner._required_insert_values_present(action) is False
    action['proposed_values']['opponent_abbreviation'] = '   '
    assert planner._required_insert_values_present(action) is False


def test_update_opponent_correction_is_source_backed_and_single_action(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'opponent': 'Stale Club', 'opponent_abbreviation': 'STL', 'strikeouts': 9},
        synchronize_session=False)
    db.session.commit()
    payload = _plan()
    updates = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)
    assert len(updates) == 1                       # opponent correction stays in one action
    update = updates[0]
    assert 'opponent' in update['changed_fields']
    assert update['current_values']['opponent'] == 'Stale Club'
    assert update['proposed_values']['opponent'] == f'Team{B}'
    assert update['proposed_values']['opponent_abbreviation'] == f'T{B}'
    assert update['official_opponent_evidence']['opposing_team_id'] == B
    assert planner._opponent_matches_official_side(update) is True
    assert payload['workload_field_coverage']['update_actions_correcting_opponent'] == 1


def test_update_never_nulls_opponent_when_official_evidence_is_incomplete(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'opponent': 'Stored Club', 'opponent_abbreviation': 'STC', 'strikeouts': 9},
        synchronize_session=False)
    db.session.commit()
    boxscore = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, None, _AWAY_LINES)}}      # no name, no abbreviation
    client = _FakeMlbClient(
        games=[_schedule_game(away_team={'id': B})],
        boxscores={GAME_PK: boxscore}, people=_ALL_PEOPLE)
    payload = planner.run_repair_plan(client=client)
    update = _actions(payload, planner.ACTION_GAME_LOG_UPDATE)[0]
    assert 'opponent' not in update['changed_fields']
    assert 'opponent_abbreviation' not in update['changed_fields']
    assert 'opponent' in update['null_guarded_fields']
    assert 'opponent_abbreviation' in update['null_guarded_fields']
    assert payload['reconciliations'][
        'no_update_replaces_a_local_value_with_null'] is True


def test_opponent_reconciliation_covers_inserts_and_updates(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)   # insert
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'opponent': 'Stale Club', 'strikeouts': 9}, synchronize_session=False)   # update
    db.session.commit()
    payload = _plan()
    assert len(_actions(payload, planner.ACTION_GAME_LOG_INSERT)) == 1
    assert len(_actions(payload, planner.ACTION_GAME_LOG_UPDATE)) == 1
    recon = payload['reconciliations']
    for name in ('opponent_comes_from_the_official_game_side',
                 'every_safe_insertion_has_a_non_empty_opponent',
                 'every_safe_insertion_has_a_non_empty_opponent_abbreviation',
                 'opponent_values_resolve_from_one_opposing_official_team',
                 'no_safe_action_has_missing_opponent_evidence',
                 'every_proposed_opponent_field_is_non_null_and_source_backed'):
        assert recon[name] is True, name


def test_opponent_evidence_change_moves_the_manifest_fingerprint(app):
    _seed_missing_line_3()
    baseline = planner.run_repair_plan(client=_missing_line_client())
    renamed = {'teams': {
        'home': _side_without(A, f'Team{A}', _HOME_LINES, abbreviation=f'T{A}'),
        'away': _side_without(B, 'Renamed Club', _AWAY_LINES, abbreviation='RNC')}}
    payload = planner.run_repair_plan(client=_FakeMlbClient(
        games=[_schedule_game()], boxscores={GAME_PK: renamed}, people=_ALL_PEOPLE))
    assert payload['repair_manifest_fingerprint'] != baseline['repair_manifest_fingerprint']
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['opponent'] == 'Renamed Club'
    assert insert['source_fingerprint'] != _action_for(
        baseline, f'gamelog:insert:{GAME_PK}:3:{A}')['source_fingerprint']


def test_opponent_resolution_never_consults_a_current_team_source(app):
    _seed_missing_line_3()
    # A stale current-team assignment must not influence the resolved opponent.
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 3).update(
        {'team_id': C, 'team_name': 'Current Club', 'team_abbreviation': 'CUR'},
        synchronize_session=False)
    db.session.commit()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')
    assert insert['proposed_values']['opponent'] == f'Team{B}'
    assert insert['proposed_values']['opponent_abbreviation'] == f'T{B}'
    code = _code_without_prose(SERVICE_PATH)
    for token in ('Pitcher.team_id', 'Pitcher.team_name', 'Pitcher.team_abbreviation'):
        assert token not in code, token

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
                'migration_head', 'season', 'as_of_date', 'accepted_defect_baseline',
                'observed_population', 'defect_baseline_comparison',
                'defect_baseline_matches_accepted_diagnostic',
                'identity_resolution_snapshot', 'identity_resolution_partition',
                'identity_resolution_transition_from_prior_snapshot',
                'identity_resolution_partition_valid',
                'prior_identity_resolution_snapshot',
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
                'pitcher_reference_coverage', 'pitcher_reference_resolution_policy',
                'failed_production_manifest_fingerprint',
                'failed_production_manifest_fingerprint_approved',
                'repair_manifest_action_count', 'repair_manifest',
                'repair_manifest_fingerprint', 'bounded_preview', 'preview_limit',
                'preview_truncated', 'verification_plan', 'plan_status',
                'repair_apply_gate', 'foundation_3b_gate', 'public_reader_gate',
                'share_card_performance_gate', 'database_writes_performed'):
        assert key in payload, key
    assert payload['mode'] == 'read_only'
    assert payload['database_writes_performed'] is False


# ═══════════════ Pitcher reference: local FK vs official identity ═══════════
# GameLog.pitcher_id is a LOCAL foreign key, not an official value. For an insertion whose
# official person has no local Pitcher row yet, that primary key does not exist and cannot be
# known by a read-only planner — it is produced when the identity prerequisite is applied. A
# null there is a deferred reference, not a missing value, and must never be filled with the
# official MLB person id or any other placeholder.

def _seed_deferred_identity():
    """Every official line has a local counterpart except person 3, who has no identity."""
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)


def _deferred_insert(payload):
    return _action_for(payload, f'gamelog:insert:{GAME_PK}:3:{A}')


def _reference_action(**overrides):
    """A minimal insert action for direct classification, defaulting to a valid State A."""
    action = {
        'action_id': 'gamelog:insert:9001:7:100',
        'action_type': planner.ACTION_GAME_LOG_INSERT,
        'official_mlb_person_id': 7,
        'local_pitcher_id': 55,
        'local_pitcher_mlb_id': 7,
        'dependency_action_ids': [],
        'proposed_values': {'pitcher_id': 55},
        'safe_to_apply': True,
        'blocking_reasons': [],
    }
    action.update(overrides)
    return action


def _identity(mlb_person_id=7, *, action_id=None, dependents=('gamelog:insert:9001:7:100',),
              safe=True, blocking=()):
    return {
        'action_id': action_id or f'identity:create:{mlb_person_id}',
        'action_type': planner.ACTION_IDENTITY_CREATE,
        'official_mlb_person_id': mlb_person_id,
        'dependent_game_log_action_ids': list(dependents),
        'dependency_action_ids': [],
        'safe_to_apply': safe,
        'blocking_reasons': list(blocking),
    }


def _classify(action, identities=()):
    by_id = {}
    for identity in identities:
        by_id.setdefault(identity['action_id'], []).append(identity)
    return planner._classify_pitcher_reference(action, by_id)


# ── 1-3. State A: existing local identity ────────────────────────────────────
def test_existing_identity_insert_requires_a_positive_local_pitcher_id(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _deferred_insert(payload)
    assert insert['pitcher_reference_state'] == planner.PITCHER_REFERENCE_EXISTING
    assert insert['local_pitcher_id'] == _pitcher(3).id
    assert insert['local_pitcher_id'] > 0
    assert payload['reconciliations'][
        'every_existing_identity_insert_uses_its_local_pitcher_id'] is True


@pytest.mark.parametrize('placeholder', [0, -1, -9999])
def test_placeholder_local_pitcher_ids_are_rejected(placeholder):
    state, blocking = _classify(_reference_action(
        local_pitcher_id=placeholder, proposed_values={'pitcher_id': placeholder}))
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_UNRESOLVABLE in blocking


def test_existing_identity_proposed_pitcher_id_equals_the_local_pitcher_id(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _deferred_insert(payload)
    assert insert['proposed_values']['pitcher_id'] == insert['local_pitcher_id']
    # A proposed value that drifts from the resolved local row is a conflict, not a variant.
    state, blocking = _classify(_reference_action(proposed_values={'pitcher_id': 56}))
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_CONFLICT in blocking


def test_existing_identity_insert_carries_no_identity_dependency(app):
    _seed_missing_line_3()
    payload = planner.run_repair_plan(client=_missing_line_client())
    insert = _deferred_insert(payload)
    assert insert['dependency_action_ids'] == []
    assert not _actions(payload, planner.ACTION_IDENTITY_CREATE)


# ── 4-6. State B: deferred identity creation ─────────────────────────────────
def test_deferred_insert_deliberately_keeps_pitcher_id_null(app):
    _seed_deferred_identity()
    payload = _plan()
    insert = _deferred_insert(payload)
    assert insert['pitcher_reference_state'] == planner.PITCHER_REFERENCE_DEFERRED
    assert 'pitcher_id' in insert['proposed_values']       # the key is present by contract
    assert insert['proposed_values']['pitcher_id'] is None  # the value is deferred by design
    assert insert['local_pitcher_id'] is None
    assert insert['safe_to_apply'] is True                  # null FK does not block
    assert payload['reconciliations'][
        'every_deferred_identity_insert_has_null_pitcher_id'] is True


def test_deferred_insert_requires_exactly_one_identity_dependency(app):
    _seed_deferred_identity()
    payload = _plan()
    insert = _deferred_insert(payload)
    assert insert['dependency_action_ids'] == ['identity:create:3']
    state, blocking = _classify(
        _reference_action(local_pitcher_id=None, local_pitcher_mlb_id=None,
                          proposed_values={'pitcher_id': None},
                          dependency_action_ids=['identity:create:7', 'identity:create:8']),
        identities=[_identity(7), _identity(8)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_AMBIGUOUS in blocking


def test_a_safe_matching_dependency_satisfies_the_pitcher_reference_contract(app):
    _seed_deferred_identity()
    payload = _plan()
    identity = _action_for(payload, 'identity:create:3')
    insert = _deferred_insert(payload)
    assert identity['safe_to_apply'] is True
    assert identity['blocking_reasons'] == []
    assert identity['official_mlb_person_id'] == insert['official_mlb_person_id']
    assert insert['action_id'] in identity['dependent_game_log_action_ids']
    recon = payload['reconciliations']
    assert recon['every_deferred_identity_insert_has_exactly_one_safe_matching_dependency'] \
        is True
    assert recon['every_safe_insert_has_a_resolvable_pitcher_reference'] is True


# ── 7-12. Fail-closed pitcher-reference states ───────────────────────────────
def test_missing_dependency_blocks_the_insertion():
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None},
        dependency_action_ids=['identity:create:7']), identities=[])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_UNRESOLVED in blocking


def test_duplicate_dependency_blocks_the_insertion():
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None},
        dependency_action_ids=['identity:create:7']),
        identities=[_identity(7), _identity(7)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_AMBIGUOUS in blocking


def test_blocked_dependency_blocks_the_insertion(app):
    _seed_deferred_identity()
    people = dict(_ALL_PEOPLE)
    people[3] = _person(3, position=None)          # no official position evidence
    payload = _plan(client=_client(people=people))
    insert = _deferred_insert(payload)
    assert insert['pitcher_reference_state'] == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_BLOCKED in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False
    assert insert['proposed_values']['pitcher_id'] is None    # still never invented
    assert payload['pitcher_reference_coverage'][
        'deferred_identity_inserts_with_unresolved_dependency'] == 1
    assert payload['pitcher_reference_coverage'][
        'deferred_identity_inserts_with_safe_dependency'] == 0


def test_mlb_identity_mismatch_between_insert_and_dependency_blocks():
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None},
        dependency_action_ids=['identity:create:7']),
        identities=[_identity(7, action_id='identity:create:7')
                    | {'official_mlb_person_id': 99}])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_IDENTITY_MISMATCH in blocking


def test_missing_reciprocal_dependent_reference_fails_reconciliation():
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None},
        dependency_action_ids=['identity:create:7']),
        identities=[_identity(7, dependents=())])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_NOT_RECIPROCAL in blocking


def test_an_insert_cannot_have_both_a_local_pitcher_id_and_a_dependency():
    state, blocking = _classify(
        _reference_action(dependency_action_ids=['identity:create:7']),
        identities=[_identity(7)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert blocking == [planner.BLOCK_PITCHER_REFERENCE_CONFLICT]


# ── 13-14. No external id, no placeholder ────────────────────────────────────
def test_mlb_person_id_is_never_written_into_game_log_pitcher_id(app):
    _seed_deferred_identity()
    payload = _plan()
    for insert in _actions(payload, planner.ACTION_GAME_LOG_INSERT):
        proposed = insert['proposed_values']['pitcher_id']
        assert proposed != insert['official_mlb_person_id'] or (
            insert['local_pitcher_id'] == proposed
            and insert['local_pitcher_mlb_id'] == insert['official_mlb_person_id'])
    assert payload['reconciliations'][
        'no_insert_uses_an_external_id_as_a_local_pitcher_id'] is True

    # Substituting the official person id for the deferred primary key is typed and fatal.
    external = _reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': 7},                  # the official MLB person id
        dependency_action_ids=['identity:create:7'])
    state, blocking = _classify(external, identities=[_identity(7)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_EXTERNAL_ID in blocking
    assert planner._no_external_id_as_local_pitcher_id(external) is False


def test_a_local_pitcher_row_must_belong_to_the_official_identity():
    # A positive integer is not enough: the local row must have been resolved BY this
    # official MLB person id.
    action = _reference_action(local_pitcher_mlb_id=999)
    state, blocking = _classify(action)
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_CONFLICT in blocking
    assert planner._no_external_id_as_local_pitcher_id(action) is False


def test_an_insert_with_neither_identity_nor_dependency_is_unresolvable():
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None}, dependency_action_ids=[]))
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert blocking == [planner.BLOCK_PITCHER_REFERENCE_UNRESOLVABLE]


# ── 15-18. Every other evidence requirement still holds ──────────────────────
def test_all_other_required_game_log_fields_remain_mandatory(app):
    _seed_deferred_identity()
    payload = _plan()
    insert = _deferred_insert(payload)
    # pitcher_id is out of the VALUE contract; nothing else is.
    assert 'pitcher_id' not in planner.REQUIRED_INSERT_VALUE_FIELDS
    assert set(planner.REQUIRED_INSERT_VALUE_FIELDS) <= set(insert['proposed_values'])
    for field in planner.REQUIRED_INSERT_VALUE_FIELDS:
        assert insert['proposed_values'][field] is not None, field
    assert planner._required_insert_values_present(insert) is True
    for field in planner.REQUIRED_INSERT_VALUE_FIELDS:
        stripped = dict(insert)
        stripped['proposed_values'] = {k: v for k, v in insert['proposed_values'].items()
                                       if k != field}
        assert planner._required_insert_values_present(stripped) is False, field


def test_missing_opponent_name_still_blocks_a_deferred_insert(app):
    _seed_deferred_identity()
    boxscore = _boxscore(_HOME_LINES, _AWAY_LINES)
    boxscore['teams']['away']['team'].pop('name')
    payload = _plan(client=_client(boxscores={GAME_PK: boxscore}))
    insert = _deferred_insert(payload)
    assert planner.BLOCK_OPPONENT_NAME_ABSENT in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False


def test_missing_opponent_abbreviation_still_blocks_a_deferred_insert(app):
    _seed_deferred_identity()
    boxscore = _boxscore(_HOME_LINES, _AWAY_LINES)
    boxscore['teams']['away']['team'].pop('abbreviation')
    payload = _plan(client=_client(boxscores={GAME_PK: boxscore}))
    insert = _deferred_insert(payload)
    assert planner.BLOCK_OPPONENT_ABBREVIATION_ABSENT in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False


def test_missing_required_official_stat_still_blocks_a_deferred_insert(app):
    _seed_deferred_identity()
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1, drop=('strikes',))]
    payload = _plan(client=_client(home_lines=home))
    insert = _deferred_insert(payload)
    assert planner.BLOCK_CORRECTION_SOURCE_INCOMPLETE in insert['blocking_reasons']
    assert insert['safe_to_apply'] is False
    assert payload['reconciliations']['no_required_official_value_is_defaulted'] is True


# ── 19-23. The accepted production population ────────────────────────────────
def test_accepted_population_partitions_into_deferred_and_existing_inserts():
    b = planner.ACCEPTED_DEFECT_BASELINE
    snapshot = planner.PRIOR_IDENTITY_RESOLUTION_SNAPSHOT
    deferred = snapshot['missing_lines_dependent_on_identity_creation']
    existing = snapshot['missing_lines_using_existing_identity']
    assert deferred == 342           # observational only, never compared for equality
    assert existing == 103
    assert deferred + existing == b['missing_line_count'] == 445


def test_pitcher_reference_coverage_is_derived_from_the_manifest(app):
    _seed_deferred_identity()
    payload = _plan()
    coverage = payload['pitcher_reference_coverage']
    inserts = _actions(payload, planner.ACTION_GAME_LOG_INSERT)
    deferred = [a for a in inserts if a['dependency_action_ids']]
    existing = [a for a in inserts if not a['dependency_action_ids']]
    assert coverage['insert_actions_with_deferred_identity_dependency'] == len(deferred)
    assert coverage['insert_actions_with_existing_local_pitcher_id'] == len(existing)
    assert coverage['deferred_identity_inserts_with_safe_dependency'] == len(deferred)
    assert coverage['deferred_identity_inserts_with_unresolved_dependency'] == 0
    assert coverage['deferred_identity_inserts_with_mismatched_identity'] == 0
    assert coverage['inserts_with_invalid_pitcher_reference'] == 0
    # The production shape: every missing line is one or the other, never both or neither.
    assert (coverage['insert_actions_with_deferred_identity_dependency']
            + coverage['insert_actions_with_existing_local_pitcher_id']) == len(inserts)


def test_populations_and_identity_count_are_unchanged_by_reference_validation(app,
                                                                              monkeypatch):
    _seed_deferred_identity()
    payload = _plan()
    _pin_baseline(monkeypatch, payload)
    payload = _plan()
    assert payload['game_log_inserts_planned'] == payload['missing_line_count']
    assert payload['existing_game_logs_requiring_updates'] == \
        payload['defective_matched_line_count']
    assert payload['defect_line_action_count'] == (
        payload['missing_line_count'] + payload['defective_matched_line_count'])
    assert payload['unique_identities_requiring_creation'] == 1     # one unique person
    assert payload['reconciliations']['defect_line_action_count_equals_defect_lines'] is True
    assert payload['reconciliations']['planned_inserts_equal_missing_lines'] is True
    assert payload['reconciliations']['planned_updates_equal_defective_rows'] is True


def test_every_reconciliation_passes_on_the_corrected_accepted_fixture(app, monkeypatch):
    _seed_deferred_identity()
    payload = _plan()
    _pin_baseline(monkeypatch, payload)
    payload = _plan()
    failed = [name for name, ok in payload['reconciliations'].items() if not ok]
    assert failed == []
    assert payload['result'] == planner.RESULT_PASS
    assert payload['plan_status'] == planner.PLAN_READY
    # The exact reconciliations this change introduces.
    for name in ('every_safe_insert_has_a_resolvable_pitcher_reference',
                 'every_existing_identity_insert_uses_its_local_pitcher_id',
                 'every_deferred_identity_insert_has_null_pitcher_id',
                 'every_deferred_identity_insert_has_exactly_one_safe_matching_dependency',
                 'every_identity_dependency_is_reciprocal',
                 'no_insert_uses_an_external_id_as_a_local_pitcher_id',
                 'every_safe_insert_contains_every_required_non_fk_value',
                 'no_required_official_value_is_defaulted'):
        assert payload['reconciliations'][name] is True, name
    # The superseded name is gone, not merely renamed alongside the old one.
    assert 'every_safe_insert_contains_every_required_correction_field' \
        not in payload['reconciliations']


def test_a_deferred_insert_no_longer_fails_the_required_value_contract(app):
    """The production defect: a null deferred FK failed required-insert validation."""
    _seed_deferred_identity()
    payload = _plan()
    insert = _deferred_insert(payload)
    assert insert['proposed_values']['pitcher_id'] is None
    assert planner._required_insert_values_present(insert) is True
    assert payload['reconciliations'][
        'every_safe_insert_contains_every_required_non_fk_value'] is True


def test_failed_production_fingerprint_is_pinned_but_not_approved(app):
    _seed_deferred_identity()
    payload = _plan()
    assert planner.FAILED_PRODUCTION_MANIFEST_FINGERPRINT == (
        '9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7')
    assert payload['failed_production_manifest_fingerprint'] == \
        planner.FAILED_PRODUCTION_MANIFEST_FINGERPRINT
    assert payload['failed_production_manifest_fingerprint_approved'] is False
    assert payload['repair_apply_gate'] != 'open'


# ── 24-28. Read-only guarantees still hold ───────────────────────────────────
def test_reference_validation_writes_nothing(app):
    _seed_deferred_identity()
    before = {(row.pitcher_id, row.mlb_game_pk): row.strikeouts
              for row in db.session.query(GameLog).all()}
    pitchers_before = db.session.query(Pitcher).count()
    payload = _plan()
    db.session.expire_all()
    after = {(row.pitcher_id, row.mlb_game_pk): row.strikeouts
             for row in db.session.query(GameLog).all()}
    assert after == before
    assert db.session.query(Pitcher).count() == pitchers_before   # no identity was created
    assert payload['database_writes_performed'] is False
    assert payload['mode'] == 'read_only'


def test_reference_validation_emits_no_write_sql(app):
    _seed_deferred_identity()
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        _plan()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    for statement in statements:
        head = statement.strip().split(None, 1)[0].upper() if statement.strip() else ''
        assert head not in ('INSERT', 'UPDATE', 'DELETE'), statement


# ═════ Immutable defect baseline vs mutable identity resolution ═════════════
# The 604-line defect population is a property of official MLB evidence and the stored
# GameLog ledger: it cannot move without the reviewed repair changing meaning. How those
# lines split between "the local Pitcher row already exists" and "an identity must be created
# first" is a property of the local database RIGHT NOW, and ordinary identity synchronization
# may legitimately move a line across that boundary between runs.

def _wantz_lines():
    """Official evidence for game 822975: Wantz relieves for team 139."""
    home = [_pline(9001, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(WANTZ_MLB_ID, gs=0, outs=3, r=0, er=0, k=1)]
    away = [_pline(9003, gs=1, outs=15, r=3, er=3, h=6, k=4),
            _pline(9004, gs=0, outs=6, r=1, er=1, bb=1)]
    return home, away


def _wantz_client():
    home, away = _wantz_lines()
    people = {i: _person(i) for i in (9001, 9003, 9004)}
    people[WANTZ_MLB_ID] = _person(WANTZ_MLB_ID, name='Andrew Wantz')
    return _FakeMlbClient(
        games=[_official_game(WANTZ_GAME_PK, home=WANTZ_TEAM, away=WANTZ_OPPONENT)],
        boxscores={WANTZ_GAME_PK: _boxscore(home, away,
                                            home=WANTZ_TEAM, away=WANTZ_OPPONENT)},
        people=people)


def _seed_wantz_ledger(*, wantz_identity_exists):
    """Every official line has a local GameLog except Wantz's, which is missing.

    ``wantz_identity_exists`` selects the two production states: before the identity
    synchronization (no local Pitcher row) and after it (local Pitcher.id 804).
    """
    _log(9001, WANTZ_GAME_PK, team=WANTZ_TEAM, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(9003, WANTZ_GAME_PK, team=WANTZ_OPPONENT, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(9004, WANTZ_GAME_PK, team=WANTZ_OPPONENT, gs=0, outs=6, r=1, er=1, bb=1)
    if wantz_identity_exists:
        # The identity synchronization created the row. Its local primary key is pinned to
        # the production value so the fixture reproduces the real transition exactly.
        row = Pitcher(id=WANTZ_LOCAL_PITCHER_ID, mlb_id=WANTZ_MLB_ID,
                      full_name='Andrew Wantz', active=True)
        db.session.add(row)
        db.session.commit()


_WANTZ_INSERT_ID = f'gamelog:insert:{WANTZ_GAME_PK}:{WANTZ_MLB_ID}:{WANTZ_TEAM}'
_WANTZ_IDENTITY_ID = f'identity:create:{WANTZ_MLB_ID}'


def _wantz_plan(*, wantz_identity_exists, monkeypatch=None):
    _seed_wantz_ledger(wantz_identity_exists=wantz_identity_exists)
    payload = planner.run_repair_plan(client=_wantz_client())
    if monkeypatch is not None:
        _pin_baseline(monkeypatch, payload)
        payload = planner.run_repair_plan(client=_wantz_client())
    return payload


# ── 1-5. The immutable defect baseline still fails closed ────────────────────
def test_immutable_defect_baseline_still_requires_exact_equality(app):
    payload = _wantz_plan(wantz_identity_exists=False)
    comparison = payload['defect_baseline_comparison']
    assert set(comparison) == set(planner.ACCEPTED_DEFECT_BASELINE)
    # The small fixture is nowhere near the production population, so it must drift.
    assert payload['defect_baseline_matches_accepted_diagnostic'] is False
    assert payload['baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_BASELINE_DRIFT
    assert planner.BLOCK_BASELINE_DRIFT in payload['decision_reasons']


@pytest.mark.parametrize('field', [
    'official_pitching_lines', 'missing_line_count', 'defective_matched_line_count',
    'defect_line_action_count', 'exact_match_count', 'official_games_fetched',
    'local_pitching_lines', 'role_corrections_planned', 'extra_local_line_count',
    'duplicate_local_line_count', 'appearance_team_mismatch_count',
    'local_pitcher_identity_missing_count', 'official_evidence_unavailable_count',
])
def test_any_immutable_defect_field_moving_is_baseline_drift(app, monkeypatch, field):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['defect_baseline_matches_accepted_diagnostic'] is True
    # Move exactly one immutable value; the plan must refuse to call itself reviewable.
    drifted = dict(planner.ACCEPTED_DEFECT_BASELINE)
    drifted[field] = drifted[field] + 1
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', drifted)
    payload = planner.run_repair_plan(client=_wantz_client())
    assert payload['defect_baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_BASELINE_DRIFT
    assert payload['defect_baseline_comparison'][field]['matches'] is False


def test_a_changed_defect_line_action_population_remains_blocked(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['result'] == planner.RESULT_PASS
    # A genuinely new defect line moves the 604-equivalent population and must block.
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(9003).id).update(
        {'strikeouts': 99}, synchronize_session=False)
    db.session.commit()
    payload = planner.run_repair_plan(client=_wantz_client())
    assert payload['defect_baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['defect_baseline_comparison'][
        'defect_line_action_count']['matches'] is False


# ── 6-8. The safe deferred-to-existing transition ────────────────────────────
def test_safe_identity_transition_does_not_cause_baseline_drift(app, monkeypatch):
    """The exact production defect: a resolved identity must not read as drift."""
    _seed_wantz_ledger(wantz_identity_exists=False)
    _pin_baseline(monkeypatch, planner.run_repair_plan(client=_wantz_client()))
    before = planner.run_repair_plan(client=_wantz_client())
    assert before['defect_baseline_matches_accepted_diagnostic'] is True
    assert before['result'] == planner.RESULT_PASS

    # A routine identity synchronization creates the local row. Nothing official moved.
    row = Pitcher(id=WANTZ_LOCAL_PITCHER_ID, mlb_id=WANTZ_MLB_ID,
                  full_name='Andrew Wantz', active=True)
    db.session.add(row)
    db.session.commit()

    after = planner.run_repair_plan(client=_wantz_client())
    assert after['defect_baseline_matches_accepted_diagnostic'] is True   # NOT drift
    assert after['result'] == planner.RESULT_PASS
    assert after['plan_status'] == planner.PLAN_READY
    assert planner.BLOCK_BASELINE_DRIFT not in after['decision_reasons']
    # Same official evidence, same defect population.
    for field in ('official_pitching_lines', 'missing_line_count',
                  'defective_matched_line_count', 'defect_line_action_count'):
        assert after[field] == before[field], field
    # The manifest itself changed, so the fingerprint must move normally.
    assert after['repair_manifest_fingerprint'] != before['repair_manifest_fingerprint']


def test_andrew_wantz_transitions_from_identity_prerequisite_to_local_pitcher_804(app):
    _seed_wantz_ledger(wantz_identity_exists=False)
    before = planner.run_repair_plan(client=_wantz_client())
    insert = _action_for(before, _WANTZ_INSERT_ID)
    identity = _action_for(before, _WANTZ_IDENTITY_ID)
    assert insert['pitcher_reference_state'] == planner.PITCHER_REFERENCE_DEFERRED
    assert insert['proposed_values']['pitcher_id'] is None
    assert insert['local_pitcher_id'] is None
    assert insert['dependency_action_ids'] == [_WANTZ_IDENTITY_ID]
    assert identity['official_mlb_person_id'] == WANTZ_MLB_ID
    assert insert['action_id'] in identity['dependent_game_log_action_ids']

    row = Pitcher(id=WANTZ_LOCAL_PITCHER_ID, mlb_id=WANTZ_MLB_ID,
                  full_name='Andrew Wantz', active=True)
    db.session.add(row)
    db.session.commit()

    after = planner.run_repair_plan(client=_wantz_client())
    insert = _action_for(after, _WANTZ_INSERT_ID)
    assert insert['pitcher_reference_state'] == planner.PITCHER_REFERENCE_EXISTING
    assert insert['local_pitcher_id'] == WANTZ_LOCAL_PITCHER_ID          # 804
    assert insert['proposed_values']['pitcher_id'] == WANTZ_LOCAL_PITCHER_ID
    assert insert['local_pitcher_mlb_id'] == WANTZ_MLB_ID                # 681806
    assert insert['dependency_action_ids'] == []
    assert insert['local_identity_resolution'] == planner.IDENTITY_RESOLUTION_CONTRACT
    assert insert['safe_to_apply'] is True
    with pytest.raises(AssertionError):
        _action_for(after, _WANTZ_IDENTITY_ID)      # the prerequisite is gone
    assert planner._identity_transition_is_verified(insert) is True


def test_transition_moves_342_103_71_to_341_104_70_without_touching_445_159_604():
    """The production arithmetic, evaluated on the real numbers."""
    partition = {
        'missing_lines_dependent_on_identity_creation': 341,
        'missing_lines_using_existing_identity': 104,
        'unique_identities_requiring_creation': 70,
    }
    transition = planner._identity_resolution_transition(partition)
    assert transition['prior_snapshot'] == {
        'missing_lines_dependent_on_identity_creation': 342,
        'missing_lines_using_existing_identity': 103,
        'unique_identities_requiring_creation': 71,
    }
    assert transition['deltas'] == {
        'missing_lines_dependent_on_identity_creation': -1,
        'missing_lines_using_existing_identity': 1,
        'unique_identities_requiring_creation': -1,
    }
    assert transition['transition_kind'] == planner.TRANSITION_ADVANCED
    assert transition['net_identities_resolved_since_snapshot'] == 1
    assert transition['snapshot_is_compared_for_equality'] is False
    # The defect population is untouched by any identity movement. Missing lines are 445 in
    # both baseline versions; the defective/action counts are quoted from V1, which the
    # amendment retains unchanged.
    b = planner.ACCEPTED_DEFECT_BASELINE
    v1 = planner.ACCEPTED_DEFECT_BASELINE_V1
    assert (partition['missing_lines_dependent_on_identity_creation']
            + partition['missing_lines_using_existing_identity']) == b['missing_line_count']
    assert b['missing_line_count'] == v1['missing_line_count'] == 445
    assert v1['defective_matched_line_count'] == 159
    assert v1['defect_line_action_count'] == 604


# ── Appearances resolved is not identities resolved ──────────────────────────
# One official person may have many dependent missing insertions, so resolving a single
# identity can move many deferred appearances at once. The two counts are reported from two
# different partition fields and must never be derived from each other.

def _transition(deferred, existing, identities):
    return planner._identity_resolution_transition({
        'missing_lines_dependent_on_identity_creation': deferred,
        'missing_lines_using_existing_identity': existing,
        'unique_identities_requiring_creation': identities,
    })


# ═════ Governed defect-baseline amendment (V1 retained, V2 active) ══════════
# One reviewed line moved from exact to defective. The baseline is AMENDED under an explicit
# versioned record rather than overwritten, and the amendment accepts current official
# authority without making any claim about which side changed historically.

GARCIA_GAME_PK = 825058
GARCIA_PERSON = 805299
GARCIA_TEAM = 109
GARCIA_LOG_ID = 43765
_V1_LITERAL = {
    'official_games_selected': 1570, 'official_games_fetched': 1570,
    'official_team_game_sides': 3140, 'official_pitching_lines': 13301,
    'official_starter_lines': 3140, 'official_relief_lines': 10161,
    'local_pitching_lines': 12856, 'local_starter_lines': 3110,
    'local_relief_lines': 9746, 'exact_match_count': 12697, 'missing_line_count': 445,
    'defective_matched_line_count': 159, 'defect_line_action_count': 604,
    'role_corrections_planned': 2, 'appearance_team_mismatch_count': 0,
    'extra_local_line_count': 0, 'duplicate_local_line_count': 0,
    'local_pitcher_identity_missing_count': 0, 'official_evidence_unavailable_count': 0,
}


def test_v1_baseline_is_retained_byte_for_byte():
    assert planner.ACCEPTED_DEFECT_BASELINE_V1 == _V1_LITERAL
    assert len(planner.ACCEPTED_DEFECT_BASELINE_V1) == 19
    # V1 stays reachable and is not the active baseline.
    assert planner.ACCEPTED_DEFECT_BASELINE_VERSIONS['v1'] is \
        planner.ACCEPTED_DEFECT_BASELINE_V1
    assert planner.ACCEPTED_DEFECT_BASELINE is not planner.ACCEPTED_DEFECT_BASELINE_V1
    assert planner.PRIOR_ACCEPTED_DEFECT_BASELINE_VERSION == 'v1'


def test_v2_changes_only_the_three_reviewed_counts():
    v1, v2 = planner.ACCEPTED_DEFECT_BASELINE_V1, planner.ACCEPTED_DEFECT_BASELINE_V2
    changed = {k for k in v1 if v1[k] != v2[k]}
    assert changed == {'exact_match_count', 'defective_matched_line_count',
                       'defect_line_action_count'}
    assert v2['exact_match_count'] == 12696
    assert v2['defective_matched_line_count'] == 160
    assert v2['defect_line_action_count'] == 605
    assert len(v2) == 19


def test_the_exact_v1_to_v2_deltas_are_minus_one_plus_one_plus_one():
    v1, v2 = planner.ACCEPTED_DEFECT_BASELINE_V1, planner.ACCEPTED_DEFECT_BASELINE_V2
    deltas = {k: v2[k] - v1[k] for k in v1 if v1[k] != v2[k]}
    assert deltas == {'exact_match_count': -1, 'defective_matched_line_count': 1,
                      'defect_line_action_count': 1}
    assert planner.DEFECT_BASELINE_AMENDMENT_1['field_deltas'] == deltas


def test_all_sixteen_other_governed_values_remain_identical():
    v1, v2 = planner.ACCEPTED_DEFECT_BASELINE_V1, planner.ACCEPTED_DEFECT_BASELINE_V2
    unchanged = [k for k in v1 if v1[k] == v2[k]]
    assert len(unchanged) == 16
    for key in ('official_pitching_lines', 'missing_line_count', 'role_corrections_planned',
                'duplicate_local_line_count', 'extra_local_line_count',
                'appearance_team_mismatch_count', 'official_evidence_unavailable_count',
                'local_pitcher_identity_missing_count', 'official_games_selected',
                'official_games_fetched', 'official_team_game_sides',
                'official_starter_lines', 'official_relief_lines', 'local_pitching_lines',
                'local_starter_lines', 'local_relief_lines'):
        assert v1[key] == v2[key], key


def test_the_amendment_key_is_exactly_the_garcia_line():
    a = planner.DEFECT_BASELINE_AMENDMENT_1
    assert a['reviewed_transition_stable_key'] == '825058:805299:109'
    assert a['reviewed_transition_key'] == {
        'mlb_game_pk': GARCIA_GAME_PK, 'official_mlb_person_id': GARCIA_PERSON,
        'appearance_team_id': GARCIA_TEAM}
    assert a['local_game_log_id'] == GARCIA_LOG_ID
    assert a['field'] == 'hits_allowed'
    assert a['official_stat_key'] == 'hits'
    assert a['current_official_value'] == 0
    assert a['current_local_value'] == 1
    assert a['reason_code'] == 'hits_mismatch'
    assert a['prior_classification'] == 'exact_match'
    assert a['amended_classification'] == 'defective_matched_line'
    assert a['update_action_id'] == 'gamelog:update:43765:825058:805299'
    assert len(planner.DEFECT_BASELINE_AMENDMENTS) == 1


def test_the_amendment_claims_no_historical_causation():
    a = planner.DEFECT_BASELINE_AMENDMENT_1
    assert a['historical_transition_classification'] == 'historical_state_unprovable'
    assert a['confidence'] == 'not_provable_from_retained_evidence'
    assert a['causation_claimed'] is False
    assert a['official_source_change_claimed'] is False    # no claim that MLB changed
    assert a['local_game_log_change_claimed'] is False     # no claim the ledger changed
    assert a['prior_values_recovered'] is False
    assert planner.HISTORICAL_CAUSATION_CLAIMED is False
    assert planner.CURRENT_AUTHORITY_BASIS == 'current_official_mlb_boxscore_evidence'
    # The bounded window is source-backed and does not imply a direction.
    assert a['transition_window']['after'] == '2026-07-28T00:57:38.449240Z'
    assert a['transition_window']['on_or_before'] == '2026-07-28T10:22:18.985546Z'
    runs = {item['run_id'] for item in a['supporting_artifacts']}
    assert runs == {30284218611, 30295617314, 30315122495, 30318846061, 30350475893}


def test_baseline_lineage_shows_v1_retained_and_v2_active(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['accepted_defect_baseline_version'] == 'v2'
    assert payload['prior_accepted_defect_baseline_version'] == 'v1'
    assert payload['defect_baseline_amendment_count'] == 1
    assert payload['accepted_defect_baseline_v1'] == _V1_LITERAL
    assert payload['historical_causation_claimed'] is False
    assert payload['historical_transition_classification'] == 'historical_state_unprovable'
    assert payload['current_authority_basis'] == 'current_official_mlb_boxscore_evidence'
    lineage = payload['defect_baseline_lineage']
    assert [x['version'] for x in lineage] == ['v1', 'v2']
    assert lineage[0]['status'] == 'retained' and lineage[0]['active'] is False
    assert lineage[1]['status'] == 'active' and lineage[1]['active'] is True
    assert lineage[1]['reviewed_transition_stable_key'] == '825058:805299:109'
    assert lineage[1]['causation_claimed'] is False


@pytest.mark.parametrize('field,delta', [
    ('exact_match_count', -1), ('defective_matched_line_count', 1),
    ('defect_line_action_count', 1), ('missing_line_count', 1),
    ('official_pitching_lines', 1), ('role_corrections_planned', 1),
])
def test_a_second_unreviewed_drift_remains_blocked(app, monkeypatch, field, delta):
    """Only the reviewed amendment is accepted; any further movement still fails closed."""
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['result'] == planner.RESULT_PASS
    drifted = dict(planner.ACCEPTED_DEFECT_BASELINE)
    drifted[field] = drifted[field] + delta
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', drifted)
    payload = planner.run_repair_plan(client=_wantz_client())
    assert payload['defect_baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_BASELINE_DRIFT


@pytest.mark.parametrize('mutation', [
    {'reviewed_transition_stable_key': '825059:805299:109'},
    {'reviewed_transition_stable_key': '825058:805300:109'},
    {'reviewed_transition_stable_key': '825058:805299:110'},
])
def test_a_different_line_key_remains_blocked(mutation):
    """The amendment names one stable key; a different key is a different amendment."""
    amended = dict(planner.DEFECT_BASELINE_AMENDMENT_1, **mutation)
    assert amended['reviewed_transition_stable_key'] != planner.AMENDMENT_1_STABLE_KEY
    assert planner.AMENDMENT_1_STABLE_KEY == '825058:805299:109'


def test_a_different_changed_field_or_value_remains_blocked():
    a = planner.DEFECT_BASELINE_AMENDMENT_1
    # Only hits_allowed is amended, and only for the recorded official/local pair.
    assert a['field'] == 'hits_allowed'
    assert a['field'] != 'runs_allowed'
    assert (a['current_official_value'], a['current_local_value']) == (0, 1)
    assert (a['current_official_value'], a['current_local_value']) != (1, 0)
    assert (a['current_official_value'], a['current_local_value']) != (0, 2)
    assert set(a['changed_fields']) == {
        'exact_match_count', 'defective_matched_line_count', 'defect_line_action_count'}


def test_the_old_604_population_now_reports_drift_against_active_v2(app, monkeypatch):
    """A run that reproduces the V1 population is drift now that V2 is active."""
    _seed_wantz_ledger(wantz_identity_exists=True)
    payload = planner.run_repair_plan(client=_wantz_client())
    v1_shaped = dict(payload['observed_population'])
    v1_shaped['defective_matched_line_count'] = \
        v1_shaped['defective_matched_line_count'] + 1
    v1_shaped['exact_match_count'] = v1_shaped['exact_match_count'] - 1
    pinned = {k: v1_shaped[k] for k in planner.ACCEPTED_DEFECT_BASELINE}
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', pinned)
    payload = planner.run_repair_plan(client=_wantz_client())
    assert payload['defect_baseline_matches_accepted_diagnostic'] is False
    assert payload['result'] == planner.RESULT_INCONCLUSIVE
    assert payload['plan_status'] == planner.PLAN_BLOCKED_BASELINE_DRIFT


def test_amendment_structural_reconciliations_always_pass(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    recon = payload['reconciliations']
    for name in ('accepted_defect_baseline_v1_is_retained_unchanged',
                 'accepted_defect_baseline_v2_differs_from_v1_in_exactly_three_fields',
                 'amendment_deltas_are_minus_one_exact_plus_one_defective_plus_one_action',
                 'every_non_amended_baseline_field_is_identical_between_v1_and_v2',
                 'amended_baseline_still_partitions_the_official_population',
                 'amended_missing_plus_defective_equals_amended_defect_actions',
                 'amendment_identifies_exactly_one_stable_official_line_key',
                 'historical_causation_is_explicitly_unproven',
                 'no_official_source_change_is_claimed',
                 'no_local_ledger_change_is_claimed',
                 'current_official_evidence_is_the_repair_authority'):
        assert recon[name] is True, name


def test_editing_v1_in_place_fails_closed(app, monkeypatch):
    """V1 is evidence. Rewriting it must break a reconciliation, not pass silently."""
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['reconciliations'][
        'accepted_defect_baseline_v1_is_retained_unchanged'] is True
    tampered = dict(planner.ACCEPTED_DEFECT_BASELINE_V1, exact_match_count=12696)
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE_V1', tampered)
    payload = planner.run_repair_plan(client=_wantz_client())
    assert payload['reconciliations'][
        'accepted_defect_baseline_v1_is_retained_unchanged'] is False
    assert payload['result'] == planner.RESULT_FAIL


def test_the_transition_diagnostic_is_not_weakened_by_the_amendment():
    """The amendment governs current repair authority, not historical causation."""
    from services import official_pitching_line_transition_diagnostic_2026 as td
    # The diagnostic still refuses to pass without a durable prior value.
    assert td.TRANSITION_UNPROVABLE == 'historical_state_unprovable'
    assert td.TRANSITION_UNPROVABLE not in td.PROVEN_CLASSIFICATIONS
    assert td.CONFIDENCE_UNPROVABLE == 'not_provable_from_retained_evidence'
    # Its target is unchanged and it still approves no fingerprint.
    assert td.TARGET_GAME_PK == GARCIA_GAME_PK
    assert td.TARGET_OFFICIAL_MLB_PERSON_ID == GARCIA_PERSON
    assert td.TARGET_LOCAL_GAME_LOG_ID == GARCIA_LOG_ID
    assert planner.DEFECT_BASELINE_AMENDMENT_1[
        'historical_transition_classification'] == td.TRANSITION_UNPROVABLE


def test_no_fingerprint_is_approved_by_the_amendment(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['reconciliations']['no_manifest_fingerprint_is_approved'] is True \
        if 'no_manifest_fingerprint_is_approved' in payload['reconciliations'] else True
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_PENDING_REVIEW
    assert payload['repair_apply_gate'] != 'open'
    source = SERVICE_PATH.read_text(encoding='utf-8')
    for token in ('APPROVED_FINGERPRINT', 'approved_fingerprint', 'accept_fingerprint',
                  'fingerprint_acceptance'):
        assert token not in source, token
    for unapproved in ('9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7',
                       'dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6',
                       '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b'):
        assert f"'{unapproved}': 'approved'" not in source


# ── The amended line, exercised end to end ──────────────────────────────────
# A fixture carrying the REAL 825058:805299:109 key as a hits_allowed defect, with the active
# baseline pinned to that population, so the per-line amendment reconciliations actually fire
# instead of being vacuously satisfied.

GARCIA_STARTER = 700101
GARCIA_OPPONENT = 133


def _garcia_client(*, official_hits=0):
    home = [(GARCIA_STARTER, 'Home Starter',
             {'gamesStarted': 1, 'inningsPitched': '6.0', 'runs': 2, 'earnedRuns': 2,
              'hits': 5, 'baseOnBalls': 1, 'strikeOuts': 6, 'homeRuns': 0, 'strikes': 60}),
            (GARCIA_PERSON, 'Brandyn Garcia',
             {'gamesStarted': 0, 'inningsPitched': '1.0', 'runs': 0, 'earnedRuns': 0,
              'hits': official_hits, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
              'strikes': 6})]
    away = [(700102, 'Away Starter',
             {'gamesStarted': 1, 'inningsPitched': '5.0', 'runs': 3, 'earnedRuns': 3,
              'hits': 6, 'baseOnBalls': 0, 'strikeOuts': 4, 'homeRuns': 0, 'strikes': 50})]

    def _side_of(team_id, name, lines):
        return {'team': {'id': team_id, 'name': name, 'abbreviation': f'T{team_id}'},
                'pitchers': [i for i, _n, _s in lines],
                'players': {f'ID{i}': {'person': {'id': i, 'fullName': n},
                                       'stats': {'pitching': s}} for i, n, s in lines}}

    boxscore = {'teams': {
        'home': _side_of(GARCIA_TEAM, 'Arizona Diamondbacks', home),
        'away': _side_of(GARCIA_OPPONENT, f'Team{GARCIA_OPPONENT}', away)}}
    people = {i: _person(i) for i in (GARCIA_STARTER, 700102)}
    people[GARCIA_PERSON] = _person(GARCIA_PERSON, name='Brandyn Garcia')
    return _FakeMlbClient(
        games=[_official_game(GARCIA_GAME_PK, home=GARCIA_TEAM, away=GARCIA_OPPONENT,
                              gdate=date(2026, 7, 20))],
        boxscores={GARCIA_GAME_PK: boxscore}, people=people)


def _seed_garcia_ledger(*, local_hits=1):
    _OPPONENT_NAME.setdefault(GARCIA_TEAM, f'Team{GARCIA_OPPONENT}')
    _OPPONENT_ABBR.setdefault(GARCIA_TEAM, f'T{GARCIA_OPPONENT}')
    _OPPONENT_NAME.setdefault(GARCIA_OPPONENT, f'Team{GARCIA_TEAM}')
    _OPPONENT_ABBR.setdefault(GARCIA_OPPONENT, f'T{GARCIA_TEAM}')
    _log(GARCIA_STARTER, GARCIA_GAME_PK, team=GARCIA_TEAM, gs=1, outs=18, r=2, er=2,
         h=5, bb=1, k=6, gdate=date(2026, 7, 20), strikes=60)
    _log(700102, GARCIA_GAME_PK, team=GARCIA_OPPONENT, gs=1, outs=15, r=3, er=3, h=6,
         k=4, gdate=date(2026, 7, 20), strikes=50)
    garcia = _pitcher(GARCIA_PERSON, name='Brandyn Garcia')
    log = _log(GARCIA_PERSON, GARCIA_GAME_PK, team=GARCIA_TEAM, gs=0, outs=3, r=0, er=0,
               h=local_hits, k=1, gdate=date(2026, 7, 20), strikes=6, pitcher_row=garcia)
    db.session.query(GameLog).filter(GameLog.id == log.id).update(
        {'id': GARCIA_LOG_ID}, synchronize_session=False)
    db.session.commit()
    return garcia


def _pin_active_v2(monkeypatch, payload):
    """Pin only the ACTIVE baseline. V1 and V2 constants stay real and unmodified, so the
    structural lineage reconciliations remain meaningful in this fixture."""
    observed = payload['observed_population']
    pinned = {k: observed[k] for k in planner.ACCEPTED_DEFECT_BASELINE}
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', pinned)
    return pinned


def test_the_amended_line_reconciles_end_to_end(app, monkeypatch):
    _seed_garcia_ledger(local_hits=1)
    _pin_active_v2(monkeypatch, planner.run_repair_plan(client=_garcia_client()))
    payload = planner.run_repair_plan(client=_garcia_client())

    assert payload['defect_baseline_matches_accepted_diagnostic'] is True
    update = _action_for(payload, 'gamelog:update:43765:825058:805299')
    assert update['local_game_log_id'] == GARCIA_LOG_ID
    assert update['mlb_game_pk'] == GARCIA_GAME_PK
    assert update['official_mlb_person_id'] == GARCIA_PERSON
    assert update['official_team_id'] == GARCIA_TEAM
    assert update['changed_fields'] == ['hits_allowed']
    assert update['current_values']['hits_allowed'] == 1
    assert update['proposed_values']['hits_allowed'] == 0
    assert update['reason_codes'] == ['hits_mismatch']
    assert update['safe_to_apply'] is True
    assert update['blocking_reasons'] == []

    recon = payload['reconciliations']
    for name in ('amended_line_occurs_exactly_once_in_the_observed_official_population',
                 'amended_line_maps_to_exactly_one_update_action',
                 'amended_update_action_targets_the_reviewed_local_game_log',
                 'amended_update_action_changes_only_hits_allowed',
                 'amended_line_current_official_value_is_zero',
                 'amended_line_current_local_value_is_one'):
        assert recon[name] is True, name
    assert [n for n, ok in recon.items() if not ok] == []
    assert payload['result'] == planner.RESULT_PASS
    assert payload['plan_status'] == planner.PLAN_READY
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_PENDING_REVIEW
    assert payload['blocking_counts_by_reason'] == {}
    assert payload['database_writes_performed'] is False


def test_a_different_current_official_value_fails_the_amendment(app, monkeypatch):
    """Official 1 instead of 0 makes the line exact; the amendment no longer reconciles."""
    _seed_garcia_ledger(local_hits=1)
    _pin_active_v2(monkeypatch, planner.run_repair_plan(client=_garcia_client()))
    payload = planner.run_repair_plan(client=_garcia_client(official_hits=1))
    assert payload['result'] != planner.RESULT_PASS
    with pytest.raises(AssertionError):
        _action_for(payload, 'gamelog:update:43765:825058:805299')


def test_a_different_current_local_value_fails_the_amendment(app, monkeypatch):
    """Local 2 instead of 1 is a different defect than the one reviewed."""
    _seed_garcia_ledger(local_hits=2)
    _pin_active_v2(monkeypatch, planner.run_repair_plan(client=_garcia_client()))
    payload = planner.run_repair_plan(client=_garcia_client())
    update = _action_for(payload, 'gamelog:update:43765:825058:805299')
    assert update['current_values']['hits_allowed'] == 2
    assert payload['reconciliations']['amended_line_current_local_value_is_one'] is False
    assert payload['result'] == planner.RESULT_FAIL


def test_amended_production_population_arithmetic():
    """The production shape the amended baseline governs."""
    v2 = planner.ACCEPTED_DEFECT_BASELINE_V2
    assert v2['exact_match_count'] == 12696
    assert v2['missing_line_count'] == 445
    assert v2['defective_matched_line_count'] == 160
    assert v2['defect_line_action_count'] == 605
    assert v2['exact_match_count'] + v2['missing_line_count'] \
        + v2['defective_matched_line_count'] == 13301
    # 675 total manifest actions = 445 inserts + 160 updates + 70 identity actions.
    inserts, updates, identities = 445, 160, 70
    assert inserts == v2['missing_line_count']
    assert updates == v2['defective_matched_line_count']
    assert inserts + updates == v2['defect_line_action_count'] == 605
    assert inserts + updates + identities == 675
    # The identity partition is mutable and derived, and still sums to the missing lines.
    deferred, existing = 341, 104
    assert deferred + existing == inserts == 445
    assert identities <= deferred


def test_wantz_transition_is_one_appearance_and_one_identity():
    t = _transition(341, 104, 70)          # the real production transition
    assert t['net_deferred_appearances_resolved_since_snapshot'] == 1
    assert t['net_identities_resolved_since_snapshot'] == 1
    assert t['transition_kind'] == planner.TRANSITION_ADVANCED


def test_one_identity_with_fifteen_appearances_reports_one_identity():
    """342 -> 327 deferred with 71 -> 70 identities is 15 appearances, ONE identity."""
    t = _transition(327, 118, 70)
    assert t['deltas']['missing_lines_dependent_on_identity_creation'] == -15
    assert t['deltas']['unique_identities_requiring_creation'] == -1
    assert t['net_deferred_appearances_resolved_since_snapshot'] == 15
    assert t['net_identities_resolved_since_snapshot'] == 1     # never 15
    assert t['transition_kind'] == planner.TRANSITION_ADVANCED
    assert t['appearance_partition_balances'] is True


def test_two_identities_with_fifteen_appearances_reports_two_identities():
    t = _transition(327, 118, 69)
    assert t['net_deferred_appearances_resolved_since_snapshot'] == 15
    assert t['net_identities_resolved_since_snapshot'] == 2
    assert t['transition_kind'] == planner.TRANSITION_ADVANCED


def test_appearance_advance_with_identity_regression_is_mixed():
    # Fewer deferred appearances but MORE identities to create: contradictory directions.
    t = _transition(327, 118, 73)
    assert t['deltas']['missing_lines_dependent_on_identity_creation'] == -15
    assert t['deltas']['unique_identities_requiring_creation'] == 2
    assert t['transition_kind'] == planner.TRANSITION_MIXED


def test_an_unbalanced_appearance_partition_is_mixed():
    # Whatever leaves deferred must arrive at existing; 445 cannot silently change here.
    t = _transition(327, 103, 70)
    assert t['appearance_partition_balances'] is False
    assert t['transition_kind'] == planner.TRANSITION_MIXED


def test_identity_regression_with_more_deferred_appearances_is_regressed():
    t = _transition(357, 88, 74)
    assert t['net_deferred_appearances_resolved_since_snapshot'] == -15
    assert t['net_identities_resolved_since_snapshot'] == -3
    assert t['transition_kind'] == planner.TRANSITION_REGRESSED


def test_identity_counts_are_never_derived_from_appearance_deltas():
    # Hold identities fixed and vary appearances: the identity count must not move.
    for deferred, existing in ((341, 104), (327, 118), (300, 145), (200, 245)):
        t = _transition(deferred, existing, 71)
        assert t['net_identities_resolved_since_snapshot'] == 0
        assert t['net_deferred_appearances_resolved_since_snapshot'] == 342 - deferred
    # Hold appearances fixed and vary identities: the appearance count must not move.
    for identities in (71, 70, 65, 40):
        t = _transition(342, 103, identities)
        assert t['net_deferred_appearances_resolved_since_snapshot'] == 0
        assert t['net_identities_resolved_since_snapshot'] == 71 - identities
    # Each reported count names the partition field it comes from.
    sources = _transition(327, 118, 70)['counts_are_distinct']
    assert sources['net_identities_resolved_since_snapshot'] == \
        'unique_identities_requiring_creation'
    assert sources['net_deferred_appearances_resolved_since_snapshot'] == \
        'missing_lines_dependent_on_identity_creation'


def test_nothing_moved_is_reported_as_unchanged():
    t = _transition(342, 103, 71)
    assert t['transition_kind'] == planner.TRANSITION_NONE
    assert t['net_identities_resolved_since_snapshot'] == 0
    assert t['net_deferred_appearances_resolved_since_snapshot'] == 0


def test_the_transition_remains_observational_and_never_gates(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    transition = payload['identity_resolution_transition_from_prior_snapshot']
    assert transition['snapshot_is_observational_only'] is True
    assert transition['snapshot_is_compared_for_equality'] is False
    # It reports a large drift against the production snapshot and the plan still passes,
    # because only the immutable defect baseline and the current partition gate the result.
    assert transition['transition_kind'] != planner.TRANSITION_NONE
    assert payload['result'] == planner.RESULT_PASS
    assert payload['defect_baseline_matches_accepted_diagnostic'] is True
    assert payload['identity_resolution_partition_valid'] is True
    # No transition field participates in the defect-baseline comparison.
    for key in ('net_identities_resolved_since_snapshot',
                'net_deferred_appearances_resolved_since_snapshot',
                'transition_kind'):
        assert key not in payload['defect_baseline_comparison']
        assert key not in planner.ACCEPTED_DEFECT_BASELINE


def test_replacing_342_with_341_would_have_been_the_wrong_fix():
    """A second legitimate transition must not require another baseline edit."""
    for deferred, existing, identities in ((341, 104, 70), (340, 105, 69), (300, 145, 60)):
        transition = planner._identity_resolution_transition({
            'missing_lines_dependent_on_identity_creation': deferred,
            'missing_lines_using_existing_identity': existing,
            'unique_identities_requiring_creation': identities,
        })
        assert transition['transition_kind'] == planner.TRANSITION_ADVANCED
        assert deferred + existing == 445
    # No identity count of any kind is pinned as immutable.
    for key in ('missing_lines_dependent_on_identity_creation',
                'missing_lines_using_existing_identity',
                'unique_identities_requiring_creation'):
        assert key not in planner.ACCEPTED_DEFECT_BASELINE


# ── 9-12. The partition is derived and internally reconciled ─────────────────
def test_identity_partition_counts_are_derived_not_hardcoded(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    partition = payload['identity_resolution_partition']
    inserts = _actions(payload, planner.ACTION_GAME_LOG_INSERT)
    deferred = [a for a in inserts if a['dependency_action_ids']]
    existing = [a for a in inserts if not a['dependency_action_ids']]
    assert partition['missing_lines_dependent_on_identity_creation'] == len(deferred) == 0
    assert partition['missing_lines_using_existing_identity'] == len(existing) == 1
    assert partition['unique_identities_requiring_creation'] == 0
    assert partition['missing_line_count'] == payload['missing_line_count']
    # Derived from THIS database, not from the production snapshot.
    assert partition['missing_lines_using_existing_identity'] != planner. \
        PRIOR_IDENTITY_RESOLUTION_SNAPSHOT['missing_lines_using_existing_identity']


def test_existing_plus_deferred_insertions_equal_every_missing_line(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=False, monkeypatch=monkeypatch)
    partition = payload['identity_resolution_partition']
    assert (partition['missing_lines_using_existing_identity']
            + partition['missing_lines_dependent_on_identity_creation']
            ) == payload['missing_line_count'] == payload['game_log_inserts_planned']
    assert payload['reconciliations'][
        'missing_lines_equal_existing_plus_deferred_identity_inserts'] is True
    assert payload['reconciliations'][
        'identity_partition_covers_every_missing_line_when_baseline_matches'] is True


def test_identity_actions_reconcile_to_unique_deferred_official_identities(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=False, monkeypatch=monkeypatch)
    identities = _actions(payload, planner.ACTION_IDENTITY_CREATE)
    deferred = [a for a in _actions(payload, planner.ACTION_GAME_LOG_INSERT)
                if a['dependency_action_ids']]
    assert {a['official_mlb_person_id'] for a in identities} == \
        {a['official_mlb_person_id'] for a in deferred} == {WANTZ_MLB_ID}
    assert len(identities) == 1
    assert payload['reconciliations'][
        'unique_identity_actions_reconcile_to_deferred_official_identities'] is True
    assert payload['reconciliations'][
        'no_identity_action_for_an_already_resolved_local_identity'] is True


def test_existing_identity_requires_exact_mlb_id_equality_and_blocks_a_mismatch():
    action = _reference_action(local_pitcher_mlb_id=WANTZ_MLB_ID,
                               official_mlb_person_id=WANTZ_MLB_ID,
                               local_identity_resolution=planner.IDENTITY_RESOLUTION_CONTRACT)
    assert planner._identity_transition_is_verified(action) is True
    mismatched = _reference_action(local_pitcher_mlb_id=WANTZ_MLB_ID + 1,
                                   official_mlb_person_id=WANTZ_MLB_ID)
    state, blocking = _classify(mismatched)
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_CONFLICT in blocking
    assert planner._identity_transition_is_verified(mismatched) is False


def test_duplicate_local_identity_resolution_blocks(app):
    """Two local Pitcher rows cannot both claim one official MLB identity."""
    _seed_wantz_ledger(wantz_identity_exists=True)
    with pytest.raises(Exception):
        db.session.add(Pitcher(id=805, mlb_id=WANTZ_MLB_ID, full_name='Andrew Wantz',
                               active=True))
        db.session.commit()
    db.session.rollback()
    # Storage forbids it; the classifier independently refuses an ambiguous resolution.
    state, blocking = _classify(_reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        proposed_values={'pitcher_id': None},
        dependency_action_ids=['identity:create:7']),
        identities=[_identity(7), _identity(7)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_DEPENDENCY_AMBIGUOUS in blocking


# ── 15-16. Name and current team are never identity authority ────────────────
def test_identity_resolution_never_uses_name_matching(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    insert = _action_for(payload, _WANTZ_INSERT_ID)
    assert insert['local_identity_resolution'] == 'pitcher.mlb_id_exact_match'
    assert payload['reconciliations'][
        'no_local_identity_is_accepted_through_name_matching'] is True
    assert 'full_name' in payload['identity_resolution_snapshot']['excluded_signals']
    # A same-named local row with a different MLB id is NOT this identity.
    other = Pitcher(mlb_id=WANTZ_MLB_ID + 5000, full_name='Andrew Wantz', active=True)
    db.session.add(other)
    db.session.commit()
    payload = planner.run_repair_plan(client=_wantz_client())
    insert = _action_for(payload, _WANTZ_INSERT_ID)
    assert insert['local_pitcher_id'] == WANTZ_LOCAL_PITCHER_ID     # still 804, by id
    assert insert['local_pitcher_mlb_id'] == WANTZ_MLB_ID
    # The local identity lookup queries Pitcher.mlb_id only; no name column participates.
    source = _code_without_prose(SERVICE_PATH)
    lookup = source.split('pitcher_rows = {')[-1].split('local_lines =')[0]
    assert 'Pitcher.mlb_id' in lookup
    assert 'full_name' not in lookup
    assert 'Pitcher.team_id' not in source


def test_current_team_is_never_identity_authority(app, monkeypatch):
    _seed_wantz_ledger(wantz_identity_exists=True)
    # A current team assignment that contradicts the historical appearance team.
    db.session.query(Pitcher).filter(Pitcher.mlb_id == WANTZ_MLB_ID).update(
        {'team_id': WANTZ_OPPONENT}, synchronize_session=False)
    db.session.commit()
    payload = planner.run_repair_plan(client=_wantz_client())
    _pin_baseline(monkeypatch, payload)
    payload = planner.run_repair_plan(client=_wantz_client())
    insert = _action_for(payload, _WANTZ_INSERT_ID)
    # Historical appearance team stays the official box-score side, not the current team.
    assert insert['proposed_values']['appearance_team_id'] == WANTZ_TEAM
    assert insert['local_pitcher_id'] == WANTZ_LOCAL_PITCHER_ID
    assert payload['reconciliations'][
        'current_team_and_roster_are_irrelevant_to_identity_resolution'] is True
    assert payload['result'] == planner.RESULT_PASS


# ── 17-20. The reference contract is unchanged by the partition split ────────
def test_deferred_insertion_still_requires_a_safe_reciprocal_dependency(app):
    _seed_wantz_ledger(wantz_identity_exists=False)
    client = _wantz_client()
    client.people[WANTZ_MLB_ID] = _person(WANTZ_MLB_ID, name='Andrew Wantz', position=None)
    payload = planner.run_repair_plan(client=client)
    insert = _action_for(payload, _WANTZ_INSERT_ID)
    assert insert['safe_to_apply'] is False
    assert planner.BLOCK_DEPENDENCY_BLOCKED in insert['blocking_reasons']
    assert insert['proposed_values']['pitcher_id'] is None
    assert payload['identity_resolution_partition_valid'] is True   # partition still sound


def test_existing_insertion_still_forbids_an_identity_dependency():
    state, blocking = _classify(
        _reference_action(local_pitcher_id=WANTZ_LOCAL_PITCHER_ID,
                          local_pitcher_mlb_id=WANTZ_MLB_ID,
                          official_mlb_person_id=WANTZ_MLB_ID,
                          proposed_values={'pitcher_id': WANTZ_LOCAL_PITCHER_ID},
                          dependency_action_ids=[_WANTZ_IDENTITY_ID]),
        identities=[_identity(WANTZ_MLB_ID, action_id=_WANTZ_IDENTITY_ID)])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert blocking == [planner.BLOCK_PITCHER_REFERENCE_CONFLICT]


def test_external_mlb_id_is_never_accepted_as_a_local_pitcher_id_after_transition(app,
                                                                                  monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    insert = _action_for(payload, _WANTZ_INSERT_ID)
    assert insert['proposed_values']['pitcher_id'] != WANTZ_MLB_ID    # 804, never 681806
    assert payload['reconciliations'][
        'no_insert_uses_an_external_id_as_a_local_pitcher_id'] is True
    substituted = _reference_action(
        local_pitcher_id=None, local_pitcher_mlb_id=None,
        official_mlb_person_id=WANTZ_MLB_ID,
        proposed_values={'pitcher_id': WANTZ_MLB_ID},
        dependency_action_ids=[_WANTZ_IDENTITY_ID])
    state, blocking = _classify(
        substituted, identities=[_identity(WANTZ_MLB_ID, action_id=_WANTZ_IDENTITY_ID,
                                           dependents=(substituted['action_id'],))])
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_EXTERNAL_ID in blocking


@pytest.mark.parametrize('placeholder', [0, -1, -804])
def test_placeholder_ids_remain_rejected_after_the_partition_split(placeholder):
    state, blocking = _classify(_reference_action(
        local_pitcher_id=placeholder, local_pitcher_mlb_id=WANTZ_MLB_ID,
        official_mlb_person_id=WANTZ_MLB_ID,
        proposed_values={'pitcher_id': placeholder}))
    assert state == planner.PITCHER_REFERENCE_INVALID
    assert planner.BLOCK_PITCHER_REFERENCE_UNRESOLVABLE in blocking


# ── 21-23. Result semantics for the resolved production shape ────────────────
def test_every_reconciliation_passes_for_the_resolved_identity_fixture(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    failed = [name for name, ok in payload['reconciliations'].items() if not ok]
    assert failed == []
    assert payload['identity_resolution_partition_valid'] is True
    for name in planner.IDENTITY_PARTITION_RECONCILIATIONS:
        assert payload['reconciliations'][name] is True, name


def test_planner_result_is_pass_for_the_resolved_production_shape(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['result'] == planner.RESULT_PASS
    assert payload['exit_code'] == 0
    assert payload['plan_status'] == planner.PLAN_READY
    assert payload['defect_baseline_matches_accepted_diagnostic'] is True
    assert payload['identity_resolution_partition_valid'] is True
    assert payload['blocking_counts_by_reason'] == {}
    assert payload['database_writes_performed'] is False


def test_repair_apply_gate_is_never_open(app, monkeypatch):
    payload = _wantz_plan(wantz_identity_exists=True, monkeypatch=monkeypatch)
    assert payload['repair_apply_gate'] == planner.GATE_BLOCKED_PENDING_REVIEW
    assert payload['repair_apply_gate'] != 'open'
    # The current inconclusive production fingerprint is pinned, never approved.
    assert payload['failed_production_manifest_fingerprint_approved'] is False
    for gate in ('foundation_3b_gate', 'public_reader_gate',
                 'share_card_performance_gate'):
        assert payload[gate] == planner.GATE_BLOCKED


# ── 24-28. Read-only guarantees survive the split ────────────────────────────
def test_identity_partition_planning_writes_nothing(app):
    _seed_wantz_ledger(wantz_identity_exists=True)
    before = {(r.pitcher_id, r.mlb_game_pk): r.strikeouts
              for r in db.session.query(GameLog).all()}
    pitchers_before = db.session.query(Pitcher).count()
    payload = planner.run_repair_plan(client=_wantz_client())
    db.session.expire_all()
    assert {(r.pitcher_id, r.mlb_game_pk): r.strikeouts
            for r in db.session.query(GameLog).all()} == before
    assert db.session.query(Pitcher).count() == pitchers_before
    assert payload['database_writes_performed'] is False
    assert payload['mode'] == 'read_only'


def test_identity_partition_planning_emits_no_write_sql(app):
    _seed_wantz_ledger(wantz_identity_exists=False)
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        planner.run_repair_plan(client=_wantz_client())
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    for statement in statements:
        head = statement.strip().split(None, 1)[0].upper() if statement.strip() else ''
        assert head not in ('INSERT', 'UPDATE', 'DELETE'), statement


def test_workflow_remains_dispatch_only_and_read_only_after_the_split():
    workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
    header = workflow.split('jobs:', 1)[0]
    assert 'workflow_dispatch' in header
    for trigger in ('schedule:', 'push:', 'pull_request:'):
        assert trigger not in header, trigger
    for token in ('apply', 'accept_fingerprint', 'fingerprint_acceptance'):
        assert f'{token}:' not in header, token
    assert 'retention-days: 14' in workflow
    assert 'permissions:' in workflow and 'contents: read' in workflow
    for mutation in ('db.session.commit', 'INSERT INTO', 'UPDATE ', 'DELETE FROM',
                     'flask db upgrade'):
        assert mutation not in workflow, mutation


def test_no_apply_mode_exists_for_pitcher_reference_resolution():
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert planner.PITCHER_REFERENCE_RESOLUTION_POLICY['executed_by_planner'] is False
    for token in ('def apply', 'apply_repair', 'apply_manifest', 'resolve_and_insert'):
        assert token not in source, token
    workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch' in workflow
    for token in ('apply', 'accept_fingerprint', 'fingerprint_acceptance'):
        assert f'{token}:' not in workflow.split('jobs:', 1)[0], token


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
    for phrase in ('bounded', '445', '159', '604', '342', '341', '103', '104', '71', '70',
                   'fingerprint', 'position player', 'delete', 'appearance-team', 'apply',
                   'foreign key', 'primary key', 'deferred_identity_creation',
                   'existing_local_identity', 'pitcher_reference_coverage',
                   'immutable', 'mutable', 'andrew wantz', '681806', '804', '822975',
                   'prior_identity_resolution_snapshot',
                   'snapshot_is_compared_for_equality',
                   '12,696', '160', '605', 'v1', 'v2', 'amendment',
                   'brandyn garcia', '805299', '825058', '43765',
                   'historical_state_unprovable', 'causation_claimed',
                   'current_official_mlb_boxscore_evidence',
                   '825058:805299:109',
                   '9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7',
                   'dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6'):
        assert phrase in text.lower(), phrase
